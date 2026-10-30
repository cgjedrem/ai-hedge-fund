from hedge_fund.brokers.saxo import (
    SaxoBroker,
    SaxoClient,
    SaxoOrderError,
    SaxoReconcileError,
    TokenManager,
    TokenState,
)
from hedge_fund.brokers.test_saxo_doubles import FakeClock, FakeTransport


class Tokens:
    def get_access_token(self):
        return "access"


def _client(responses, currency="USD", *, clock=None):
    transport = FakeTransport(responses)
    client = SaxoClient(tokens=Tokens(), transport=transport, base_currency=currency, clock=clock or FakeClock())
    return client, transport


def test_discovers_active_stock_account_and_scopes_book_reads():
    client, transport = _client(
        [
            (200, {"ClientKey": "client"}),
            (
                200,
                {
                    "Data": [
                        {"AccountKey": "inactive", "Currency": "USD", "Active": False, "LegalAssetTypes": ["Stock"]},
                        {"AccountKey": "non-stock", "Currency": "USD", "Active": True, "LegalAssetTypes": ["FxSpot"]},
                        {"AccountKey": "eur", "Currency": "EUR", "Active": True, "LegalAssetTypes": ["Stock"]},
                        {"AccountKey": "usd", "Currency": "USD", "Active": True, "LegalAssetTypes": ["Stock"]},
                    ]
                },
            ),
            (200, {"Data": [{"NetPositionId": "net-1", "PositionBase": {"Uic": 7, "Amount": -2}}]}),
            (200, {"Currency": "USD", "CashBalance": 1250.0, "CashAvailableForTrading": 900.0}),
        ]
    )
    client.discover_account()
    client._ticker_uic["ABC"] = 7

    assert client.account_key == "usd"
    assert client.positions()["ABC"].shares == -2
    assert client.balances()["CashBalance"] == 1250.0
    assert transport.calls[2]["url"].endswith("/port/v1/positions")
    assert transport.calls[2]["params"] == {"ClientKey": "client", "AccountKey": "usd"}
    assert transport.calls[3]["url"].endswith("/port/v1/balances")
    assert transport.calls[3]["params"] == {"ClientKey": "client", "AccountKey": "usd"}
    assert transport.auth_schemes == ["Bearer"] * 4


def test_no_currency_compatible_account_refuses_startup():
    client, _ = _client(
        [
            (200, {"ClientKey": "client"}),
            (200, {"Data": [{"AccountKey": "eur", "Currency": "EUR", "Active": True, "LegalAssetTypes": ["Stock"]}]}),
        ]
    )

    try:
        client.discover_account()
    except SaxoReconcileError as error:
        assert "USD" in str(error)
        assert "EUR" in str(error)
    else:
        raise AssertionError("currency mismatch accepted")


def test_inactive_or_non_stock_account_is_not_selected():
    client, _ = _client(
        [
            (200, {"ClientKey": "client"}),
            (
                200,
                {
                    "Data": [
                        {"AccountKey": "inactive", "Currency": "USD", "Active": False, "LegalAssetTypes": ["Stock"]},
                        {"AccountKey": "non-stock", "Currency": "USD", "Active": True, "LegalAssetTypes": ["FxSpot"]},
                    ]
                },
            ),
        ]
    )

    try:
        client.discover_account()
    except SaxoReconcileError as error:
        assert "USD" in str(error)
    else:
        raise AssertionError("account without trading indicator was selected")


def test_one_unauthorized_get_refreshes_then_retries_once():
    class Secrets:
        def resolve(self, variable, reference):
            return "refresh-old"

        def write_back(self, variable, reference, value):
            self.value = value

    transport = FakeTransport(
        [
            (401, {}),
            (200, {"access_token": "new-access", "refresh_token": "new-refresh", "expires_in": 900}),
            (200, {"ok": True}),
        ]
    )
    tokens = TokenManager(
        app_key="key",
        app_secret="secret",
        refresh_token_ref="op://vault/item/token",
        secrets_provider=Secrets(),
        transport=transport,
        clock=FakeClock(),
    )
    tokens.access_token = "old-access"
    tokens.access_expires_at = 900
    tokens.state = TokenState.AUTHORIZED
    client = SaxoClient(tokens=tokens, transport=transport, clock=FakeClock())

    assert client.request("GET", "/port/v1/users/me") == (200, {"ok": True})
    assert len(transport.calls) == 3
    assert transport.auth_schemes == ["Bearer", None, "Bearer"]


def test_order_attempts_get_distinct_request_ids_and_follow_pacer():
    clock = FakeClock()
    transport = FakeTransport([(200, {"OrderId": "one"}), (200, {"OrderId": "two"})])
    client = SaxoClient(tokens=Tokens(), transport=transport, clock=clock)

    client.request("POST", "/trade/v2/orders", json_body={}, order_post=True)
    client.request("POST", "/trade/v2/orders", json_body={}, order_post=True)

    request_ids = [call["headers"]["x-request-id"] for call in transport.calls]
    assert len(set(request_ids)) == 2
    assert clock.sleeps == [1.0]


def test_order_poll_has_a_bounded_deadline():
    clock = FakeClock()
    transport = FakeTransport([(200, {"IsOpen": True}), (200, {"IsOpen": True})])
    client = SaxoClient(
        tokens=Tokens(),
        transport=transport,
        clock=clock,
        execution_timeout_s=2,
        poll_interval_s=1,
    )
    client.client_key = "client"
    client.account_key = "account"

    try:
        client.wait_for_order("order")
    except SaxoOrderError as error:
        assert "deadline" in str(error)
    else:
        raise AssertionError("open order exceeded no deadline")
    assert clock.value == 2


def test_accounting_cash_is_distinct_from_buying_power():
    client, _ = _client(
        [
            (200, {"ClientKey": "client"}),
            (200, {"Data": [{"AccountKey": "usd", "Currency": "USD", "Active": True, "LegalAssetTypes": ["Stock"]}]}),
            (200, {"Currency": "USD", "CashBalance": 1250, "CashAvailableForTrading": 900}),
        ]
    )
    broker = SaxoBroker.__new__(SaxoBroker)
    broker.client = client
    broker.universe = ["ABC"]
    broker.cache_ttl_s = 3600
    broker._cache = {}
    client.discover_account()

    assert broker.cash() == 1250


def test_scoped_balance_requires_explicit_matching_currency():
    client, _ = _client(
        [
            (200, {"ClientKey": "client"}),
            (
                200,
                {
                    "Data": [
                        {
                            "AccountKey": "usd",
                            "Currency": "USD",
                            "Active": True,
                            "LegalAssetTypes": ["Stock"],
                        }
                    ]
                },
            ),
            (200, {"CashBalance": 1250}),
        ]
    )
    client.discover_account()

    try:
        client.balances()
    except SaxoReconcileError as error:
        assert "balance currency" in str(error)
    else:
        raise AssertionError("balance without currency accepted")


def test_transaction_feed_is_polled_until_correlated_fill_arrives():
    clock = FakeClock()
    client, _ = _client(
        [
            (200, {"Data": []}),
            (200, {"Data": [{"Trades": [{"OrderId": "order", "TradedQuantity": 2, "Price": 15}]}]}),
        ],
        clock=clock,
    )
    client.client_key = "client"
    client.account_key = "account"

    assert client.order_fill("order", 2, uic=7) == (2, 15)
    assert clock.sleeps == [1.0]


def test_transaction_feed_pages_nested_order_trades_with_documented_filters():
    clock = FakeClock()
    client, transport = _client(
        [
            (
                200,
                {
                    "Data": [
                        {"Trades": [{"OrderId": "other", "TradedQuantity": 99, "Price": 3}]},
                    ],
                    "__next": "/openapi/hist/v1/transactions?$skip=1",
                },
            ),
            (
                200,
                {
                    "Data": [
                        {
                            "Trades": [
                                {"OrderId": "order", "TradedQuantity": 1, "Price": 14},
                                {"OrderId": "order", "TradedQuantity": 1, "Price": 16},
                            ]
                        },
                    ],
                },
            ),
        ],
        clock=clock,
    )
    client.client_key = "client"
    client.account_key = "account"

    assert client.order_fill("order", 2, uic=7) == (2, 15)
    first, second = [call for call in transport.calls if call["url"].endswith("/hist/v1/transactions")]
    assert "OrderId" not in first["params"]
    assert first["params"]["AccountKeys"] == "account"
    assert first["params"]["ClientKey"] == "client"
    assert first["params"]["Uics"] == "7"
    assert "FromDate" in first["params"] and "ToDate" in first["params"]
    assert second["params"]["$skip"] == 1
