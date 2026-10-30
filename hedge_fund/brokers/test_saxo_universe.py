from hedge_fund.brokers.saxo import SaxoBroker, SaxoClient, SaxoReconcileError
from hedge_fund.brokers.test_saxo_doubles import FakeClock, FakeTransport


class Tokens:
    transport = None

    def get_access_token(self):
        return "access"


def _client(responses, clock=None):
    transport = FakeTransport(responses)
    tokens = Tokens()
    tokens.transport = transport
    client = SaxoClient(tokens=tokens, transport=transport, clock=clock or FakeClock())
    client.client_key = "client"
    client.account_key = "account"
    return client, transport


def test_search_then_details_are_distinct_and_cacheable():
    clock = FakeClock()
    client, transport = _client(
        [
            (
                200,
                {
                    "Data": [
                        {"Identifier": 90, "Symbol": "ABC:xlon", "ExchangeId": "LSE", "PrimaryListing": 90},
                        {"Identifier": 42, "Symbol": "ABC:xnas", "ExchangeId": "NASDAQ", "PrimaryListing": 42},
                        {"Identifier": 43, "Symbol": "ABC:xnys", "ExchangeId": "NYSE"},
                    ]
                },
            ),
            (
                200,
                {
                    "IsTradable": True,
                    "LotSize": 0.1,
                    "SupportedOrderTypes": ["Market"],
                    "CurrencyCode": "USD",
                    "Exchange": {"CountryCode": "US", "ExchangeId": "NASDAQ"},
                },
            ),
        ],
        clock,
    )
    broker = SaxoBroker.__new__(SaxoBroker)
    broker.client = client
    broker.universe = ["ABC"]
    broker.cache_ttl_s = 3600
    broker._cache = {}

    broker.validate_universe()
    broker.validate_universe()

    assert [call["url"].split("/openapi")[-1] for call in transport.calls] == [
        "/ref/v1/instruments",
        "/ref/v1/instruments/details/42/Stock",
    ]
    assert transport.calls[0]["params"] == {"Keywords": "ABC", "AssetTypes": "Stock"}
    clock.value += 3600
    transport.responses.extend(
        [
            (200, {"Data": [{"Identifier": 42, "Symbol": "ABC:xnas", "ExchangeId": "NASDAQ"}]}),
            (
                200,
                {
                    "IsTradable": True,
                    "LotSize": 0.1,
                    "SupportedOrderTypes": ["Market"],
                    "CurrencyCode": "USD",
                    "Exchange": {"CountryCode": "US", "ExchangeId": "NASDAQ"},
                },
            ),
        ]
    )
    broker.validate_universe()
    assert len(transport.calls) == 4


def test_positions_revalidates_universe_after_cache_ttl_expires():
    clock = FakeClock()
    client, transport = _client(
        [
            (
                200,
                {"Data": [{"Identifier": 42, "Symbol": "ABC:xnas", "ExchangeId": "NASDAQ"}]},
            ),
            (
                200,
                {
                    "IsTradable": True,
                    "LotSize": 1,
                    "SupportedOrderTypes": ["Market"],
                    "CurrencyCode": "USD",
                    "Exchange": {"CountryCode": "US", "ExchangeId": "NASDAQ"},
                },
            ),
            (200, {"Data": []}),
            (
                200,
                {"Data": [{"Identifier": 43, "Symbol": "ABC:xnys", "ExchangeId": "NYSE"}]},
            ),
            (
                200,
                {
                    "IsTradable": True,
                    "LotSize": 1,
                    "SupportedOrderTypes": ["Market"],
                    "CurrencyCode": "USD",
                    "Exchange": {"CountryCode": "US", "ExchangeId": "NYSE"},
                },
            ),
            (200, {"Data": []}),
        ],
        clock,
    )
    broker = SaxoBroker.__new__(SaxoBroker)
    broker.client = client
    broker.universe = ["ABC"]
    broker.cache_ttl_s = 3600
    broker._cache = {}

    assert broker.positions() == {}
    assert len(transport.calls) == 3
    clock.value += 3601

    assert broker.positions() == {}
    assert len(transport.calls) == 6
    assert client._ticker_uic["ABC"] == 43


def test_untradable_details_fail_before_order_placement():
    client, _ = _client(
        [
            (200, {"Data": [{"Identifier": 42, "Symbol": "ABC:xnas", "ExchangeId": "NASDAQ"}]}),
            (200, {"IsTradable": False, "LotSize": 1}),
        ]
    )
    broker = SaxoBroker.__new__(SaxoBroker)
    broker.client = client
    broker.universe = ["ABC"]
    broker.cache_ttl_s = 3600
    broker._cache = {}

    try:
        broker.validate_universe()
    except SaxoReconcileError as error:
        assert "not tradable" in str(error)
    else:
        raise AssertionError("untradable instrument accepted")
    assert len(client.transport.calls) == 2


def test_missing_ticker_refuses_before_order_placement():
    client, transport = _client([(200, {"Data": []})])
    broker = SaxoBroker.__new__(SaxoBroker)
    broker.client = client
    broker.universe = ["MISSING"]
    broker.cache_ttl_s = 3600
    broker._cache = {}

    try:
        broker.validate_universe()
    except SaxoReconcileError as error:
        assert "not found" in str(error)
    else:
        raise AssertionError("missing ticker accepted")
    assert not any(call["method"] == "POST" for call in transport.calls)


def test_single_unmatched_search_result_is_not_assumed_to_be_ticker():
    client, transport = _client([(200, {"Data": [{"Identifier": 42, "Symbol": "OTHER:xnas"}]})])
    broker = SaxoBroker.__new__(SaxoBroker)
    broker.client = client
    broker.universe = ["ABC"]
    broker.cache_ttl_s = 3600
    broker._cache = {}

    try:
        broker.validate_universe()
    except SaxoReconcileError as error:
        assert "not found" in str(error)
    else:
        raise AssertionError("unmatched instrument accepted")
    assert not any(call["method"] == "POST" for call in transport.calls)


def test_non_us_exchange_and_non_us_currency_are_rejected():
    cases = [
        (
            {"Identifier": 42, "Symbol": "ABC:xlon", "ExchangeId": "LSE"},
            {"IsTradable": True, "CurrencyCode": "USD", "Exchange": {"CountryCode": "GB"}},
        ),
        (
            {"Identifier": 42, "Symbol": "ABC:xnas", "ExchangeId": "NASDAQ"},
            {"IsTradable": True, "CurrencyCode": "EUR", "Exchange": {"CountryCode": "US"}},
        ),
    ]
    for instrument, details in cases:
        client, _ = _client([(200, {"Data": [instrument]}), (200, details)])
        broker = SaxoBroker.__new__(SaxoBroker)
        broker.client = client
        broker.universe = ["ABC"]
        broker.cache_ttl_s = 3600
        broker._cache = {}

        try:
            broker.validate_universe()
        except SaxoReconcileError:
            pass
        else:
            raise AssertionError("non-US listing or currency accepted")
