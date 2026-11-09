from datetime import datetime, timedelta

import pytest

from hedge_fund.brokers.protocol import OrderSubmissionDeferred
from hedge_fund.brokers.saxo import (
    DemoTokenManager,
    Pacer,
    RequestsTransport,
    SaxoAuthError,
    SaxoBroker,
    SaxoClient,
    SaxoOrderError,
    SaxoReconcileError,
    TokenManager,
    TokenState,
)
from hedge_fund.brokers.test_saxo_doubles import FakeClock, FakeTransport
from hedge_fund.data.sessions import NEW_YORK


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
    client.discover_account("usd")
    client._ticker_uic["ABC"] = 7

    assert client.account_key == "usd"
    assert client.positions()["ABC"].shares == -2
    assert client.balances()["CashBalance"] == 1250.0
    assert transport.calls[2]["url"].endswith("/port/v1/positions")
    assert transport.calls[2]["params"] == {"ClientKey": "client", "AccountKey": "usd"}
    assert transport.calls[3]["url"].endswith("/port/v1/balances")
    assert transport.calls[3]["params"] == {"ClientKey": "client", "AccountKey": "usd"}
    assert transport.auth_schemes == ["Bearer"] * 4


@pytest.mark.parametrize("result", [{}, {"Data": None}, {"Data": {}}, [], None])
def test_positions_require_an_explicit_list_of_rows(result):
    client, _ = _client([(200, result)])
    client.client_key, client.account_key = "client", "account"

    with pytest.raises(SaxoReconcileError, match="positions.*invalid shape"):
        client.positions()


def test_positions_reject_an_undecodable_success_response():
    class InvalidJson:
        status_code = 200

        def json(self):
            raise ValueError("invalid JSON")

    client, _ = _client([InvalidJson()])
    client.client_key, client.account_key = "client", "account"

    with pytest.raises(SaxoReconcileError, match="positions.*invalid shape"):
        client.positions()


def test_positions_read_all_pages_with_the_original_account_scope():
    client, transport = _client(
        [
            (
                200,
                {
                    "Data": [{"NetPositionId": "one", "PositionBase": {"Uic": 7, "Amount": 2}}],
                    "__next": "/openapi/port/v1/positions?$skip=1",
                },
            ),
            (200, {"Data": [{"NetPositionId": "two", "PositionBase": {"Uic": 8, "Amount": -3}}]}),
        ]
    )
    client.client_key, client.account_key = "client", "account"
    client._ticker_uic.update({"ABC": 7, "XYZ": 8})

    positions = client.positions()

    assert {ticker: position.shares for ticker, position in positions.items()} == {"ABC": 2, "XYZ": -3}
    assert [call["params"] for call in transport.calls] == [
        {"ClientKey": "client", "AccountKey": "account"},
        {"ClientKey": "client", "AccountKey": "account", "$skip": 1},
    ]


@pytest.mark.parametrize("second_page", [(200, {}), (503, {})])
def test_positions_reject_a_failed_later_page_instead_of_returning_a_partial_book(second_page):
    client, _ = _client(
        [
            (200, {"Data": [{"NetPositionId": "one", "PositionBase": {"Uic": 7, "Amount": 2}}], "__next": "?$skip=1"}),
            second_page,
        ]
    )
    client.client_key, client.account_key = "client", "account"
    client._ticker_uic["ABC"] = 7

    with pytest.raises(SaxoReconcileError, match="positions"):
        client.positions()


@pytest.mark.parametrize("next_link", ["?$skip=0", "?$skip=invalid", "?$skiptoken=opaque", 42, ""])
def test_positions_reject_invalid_or_nonadvancing_pagination(next_link):
    client, _ = _client([(200, {"Data": [], "__next": next_link})])
    client.client_key, client.account_key = "client", "account"

    with pytest.raises(SaxoReconcileError, match="pagination"):
        client.positions()


def test_no_currency_compatible_account_refuses_startup():
    client, _ = _client(
        [
            (200, {"ClientKey": "client"}),
            (200, {"Data": [{"AccountKey": "eur", "Currency": "EUR", "Active": True, "LegalAssetTypes": ["Stock"]}]}),
        ]
    )

    with pytest.raises(SaxoReconcileError) as error:
        client.account_candidates()

    assert "USD" in str(error.value)
    assert "EUR" in str(error.value)


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

    with pytest.raises(SaxoReconcileError, match="USD"):
        client.account_candidates()


def test_account_candidates_enumerates_eligible_accounts_without_binding():
    client, transport = _client(
        [
            (200, {"ClientKey": "client"}),
            (
                200,
                {
                    "Data": [
                        {"AccountKey": "inactive", "Currency": "USD", "Active": False, "LegalAssetTypes": ["Stock"]},
                        {"AccountKey": "eur", "Currency": "EUR", "Active": True, "LegalAssetTypes": ["Stock"]},
                        {"AccountKey": "cash", "Currency": "USD", "Active": True, "LegalAssetTypes": ["FxSpot"]},
                        {"AccountKey": "sim-one", "Currency": "USD", "Active": True, "LegalAssetTypes": ["Stock"]},
                        {"AccountKey": "sim-two", "Currency": "USD", "Active": True, "LegalAssetTypes": ["Stock"]},
                    ]
                },
            ),
        ]
    )

    candidates = client.account_candidates()

    assert [candidate.account_key for candidate in candidates] == ["sim-one", "sim-two"]
    assert all(candidate.currency == "USD" for candidate in candidates)
    assert client.account_key is None
    assert [call["method"] for call in transport.calls] == ["GET", "GET"]


def test_oauth_discover_account_preserves_legacy_first_eligible_selection():
    client, transport = _client(
        [
            (200, {"ClientKey": "client"}),
            (
                200,
                {
                    "Data": [
                        {"AccountKey": "sim-one", "Currency": "USD", "Active": True, "LegalAssetTypes": ["Stock"]},
                        {"AccountKey": "sim-two", "Currency": "USD", "Active": True, "LegalAssetTypes": ["Stock"]},
                    ]
                },
            ),
        ]
    )

    client.discover_account(None)

    assert client.account_key == "sim-one"
    assert [call["method"] for call in transport.calls] == ["GET", "GET"]
    assert all("/trade/" not in call["url"] for call in transport.calls)


def test_demo_token_account_discovery_still_requires_explicit_binding():
    client, transport = _client([])
    client.tokens = DemoTokenManager(
        access_token_ref="op://vault/item/demo-token",
        secrets_provider=type("Secrets", (), {"resolve": lambda self, variable, reference: "token"})(),
    )

    with pytest.raises(SaxoReconcileError, match="explicit"):
        client.discover_account(None)

    assert transport.calls == []


@pytest.mark.parametrize(
    "location",
    [
        "https://gateway.saxobank.com/openapi/port/v1/users/me",
        "https://gateway.saxobank.com/live/openapi/port/v1/users/me",
        "https://redirect.example.invalid/token",
    ],
)
def test_requests_transport_disables_redirects_and_saxo_client_rejects_them(monkeypatch, location):
    class RedirectResponse:
        status_code = 302
        headers = {"Location": location}

        @staticmethod
        def json():
            return {}

    request_kwargs = []

    def fake_request(method, url, **kwargs):
        request_kwargs.append((method, url, kwargs))
        return RedirectResponse()

    monkeypatch.setattr("hedge_fund.brokers.saxo.requests.request", fake_request)
    secrets = type("Secrets", (), {"resolve": lambda self, variable, reference: "demo-token"})()
    tokens = DemoTokenManager(
        access_token_ref="op://vault/item/demo-token",
        secrets_provider=secrets,
    )
    client = SaxoClient(tokens=tokens, transport=RequestsTransport())

    with pytest.raises(SaxoAuthError, match="redirected"):
        client.request("GET", "/port/v1/users/me")

    assert len(request_kwargs) == 1
    _, url, kwargs = request_kwargs[0]
    assert url.startswith("https://gateway.saxobank.com/sim/openapi/")
    assert kwargs["allow_redirects"] is False
    assert kwargs["timeout"] == 15


def test_discover_account_rejects_an_unlisted_identifier_without_binding():
    client, _ = _client(
        [
            (200, {"ClientKey": "client"}),
            (200, {"Data": [{"AccountKey": "sim-one", "Currency": "USD", "Active": True, "LegalAssetTypes": ["Stock"]}]}),
        ]
    )

    with pytest.raises(SaxoReconcileError, match="eligible account"):
        client.discover_account("not-listed")

    assert client.account_key is None


@pytest.mark.parametrize(
    "response",
    [
        {},
        {"Data": None},
        {"Data": [None]},
        {"Data": [{"AccountKey": "sim-one", "Currency": "USD", "Active": True}]},
        {
            "Data": [
                {"AccountKey": "sim-one", "Currency": "USD", "Active": True, "LegalAssetTypes": ["Stock"]},
                {"AccountKey": "sim-one", "Currency": "USD", "Active": True, "LegalAssetTypes": ["Stock"]},
            ]
        },
    ],
)
def test_account_candidates_fail_closed_on_malformed_or_duplicate_rows(response):
    client, transport = _client([(200, {"ClientKey": "client"}), (200, response)])

    with pytest.raises(SaxoReconcileError, match="account"):
        client.account_candidates()

    assert client.account_key is None
    assert [call["method"] for call in transport.calls] == ["GET", "GET"]


def test_account_inspection_reports_cash_and_position_summary_without_selection():
    client, transport = _client(
        [
            (200, {"ClientKey": "client"}),
            (200, {"Data": [{"AccountKey": "sim-one", "Currency": "USD", "Active": True, "LegalAssetTypes": ["Stock"]}]}),
            (200, {"Currency": "USD", "CashBalance": 1250.25}),
            (200, {"Data": [{"PositionBase": {"Uic": 44, "Amount": 3.5}}]}),
        ]
    )

    accounts = client.inspect_accounts()

    assert len(accounts) == 1
    assert accounts[0].account_key == "sim-one"
    assert accounts[0].currency == "USD"
    assert accounts[0].cash_balance == 1250.25
    assert [(position.uic, position.amount) for position in accounts[0].positions] == [(44, 3.5)]
    assert client.account_key is None
    assert [call["method"] for call in transport.calls] == ["GET"] * 4
    assert all("/trade/" not in call["url"] for call in transport.calls)


def test_account_inspection_returns_all_eligible_candidates_without_implicit_selection():
    client, transport = _client(
        [
            (200, {"ClientKey": "client"}),
            (
                200,
                {
                    "Data": [
                        {"AccountKey": "sim-one", "Currency": "USD", "Active": True, "LegalAssetTypes": ["Stock"]},
                        {"AccountKey": "sim-two", "Currency": "USD", "Active": True, "LegalAssetTypes": ["Stock"]},
                    ]
                },
            ),
            (200, {"Currency": "USD", "CashBalance": 100}),
            (200, {"Data": []}),
            (200, {"Currency": "USD", "CashBalance": 200}),
            (200, {"Data": []}),
        ]
    )

    accounts = client.inspect_accounts()

    assert [account.account_key for account in accounts] == ["sim-one", "sim-two"]
    assert client.account_key is None
    assert all(call["method"] == "GET" for call in transport.calls)
    assert all("/trade/" not in call["url"] for call in transport.calls)


@pytest.mark.parametrize(
    "balance_response",
    [
        (503, {}),
        (200, {"Currency": "EUR", "CashBalance": 100}),
        (200, {"Currency": "USD", "CashBalance": float("nan")}),
    ],
)
def test_account_inspection_rejects_unavailable_or_inconsistent_balances(balance_response):
    client, transport = _client(
        [
            (200, {"ClientKey": "client"}),
            (200, {"Data": [{"AccountKey": "sim-one", "Currency": "USD", "Active": True, "LegalAssetTypes": ["Stock"]}]}),
            balance_response,
        ]
    )

    with pytest.raises(SaxoReconcileError, match="balance"):
        client.inspect_accounts()

    assert client.account_key is None
    assert all(call["method"] == "GET" for call in transport.calls)


@pytest.mark.parametrize(
    "positions_response",
    [
        (503, {}),
        (200, {"Data": [None]}),
        (200, {"Data": [{"PositionBase": None}]}),
        (200, {"Data": [{"PositionBase": {"Uic": True, "Amount": 2}}]}),
        (200, {"Data": [{"PositionBase": {"Uic": 44, "Amount": float("nan")}}]}),
    ],
)
def test_account_inspection_rejects_unavailable_or_malformed_positions(positions_response):
    client, transport = _client(
        [
            (200, {"ClientKey": "client"}),
            (200, {"Data": [{"AccountKey": "sim-one", "Currency": "USD", "Active": True, "LegalAssetTypes": ["Stock"]}]}),
            (200, {"Currency": "USD", "CashBalance": 100}),
            positions_response,
        ]
    )

    with pytest.raises(SaxoReconcileError, match="position"):
        client.inspect_accounts()

    assert client.account_key is None
    assert all(call["method"] == "GET" for call in transport.calls)


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


def test_order_pacing_measures_actual_posts_after_token_acquisition():
    clock = FakeClock()

    class SlowFirstToken:
        calls = 0

        def get_access_token(self):
            self.calls += 1
            if self.calls == 1:
                clock.sleep(2)
            return "access"

    class TimedTransport(FakeTransport):
        def __init__(self):
            super().__init__([(200, {"OrderId": "one"}), (200, {"OrderId": "two"})])
            self.post_times = []

        def request(self, *args, **kwargs):
            self.post_times.append(clock.monotonic())
            return super().request(*args, **kwargs)

    transport = TimedTransport()
    client = SaxoClient(tokens=SlowFirstToken(), transport=transport, clock=clock)

    client.request("POST", "/trade/v2/orders", json_body={}, order_post=True)
    client.request("POST", "/trade/v2/orders", json_body={}, order_post=True)

    assert transport.post_times[1] - transport.post_times[0] >= 1


@pytest.mark.parametrize("delay", ["token", "pacer"])
def test_order_submission_cutoff_is_checked_after_token_and_pacing(delay):
    clock = FakeClock()
    cutoff = datetime(2026, 10, 30, 16, tzinfo=NEW_YORK)
    start = cutoff - timedelta(seconds=0.5)

    class DelayedTokens:
        def get_access_token(self):
            if delay == "token":
                clock.sleep(1)
            return "access"

    pacer = Pacer(clock=clock)
    if delay == "pacer":
        pacer.last_call_at["orders"] = 0
    transport = FakeTransport([(200, {"OrderId": "after-window"})])
    client = SaxoClient(tokens=DelayedTokens(), transport=transport, pacer=pacer, clock=clock)

    with client.order_submission_window(cutoff, now=lambda: start + timedelta(seconds=clock.value)):
        with pytest.raises(OrderSubmissionDeferred, match="market close"):
            client.request("POST", "/trade/v2/orders", json_body={}, order_post=True)
    assert transport.calls == []

    client.request("POST", "/trade/v2/orders", json_body={}, order_post=True)
    assert len(transport.calls) == 1


def test_order_submission_cutoff_is_rechecked_before_a_401_retry():
    clock = FakeClock()
    cutoff = datetime(2026, 10, 30, 16, tzinfo=NEW_YORK)
    start = cutoff - timedelta(seconds=0.5)

    class RetryTokens:
        access_expires_at = 100

        def get_access_token(self):
            return "access"

    class ClosingTransport(FakeTransport):
        def request(self, *args, **kwargs):
            result = super().request(*args, **kwargs)
            clock.value += 1
            return result

    transport = ClosingTransport([(401, {}), (200, {"OrderId": "too-late"})])
    client = SaxoClient(tokens=RetryTokens(), transport=transport, clock=clock)

    with client.order_submission_window(cutoff, now=lambda: start + timedelta(seconds=clock.value)):
        with pytest.raises(OrderSubmissionDeferred, match="market close"):
            client.request("POST", "/trade/v2/orders", json_body={}, order_post=True)
    assert len(transport.calls) == 1


def test_nested_submission_windows_restore_the_outer_cutoff():
    cutoff = datetime(2026, 10, 30, 16, tzinfo=NEW_YORK)
    client, transport = _client([(200, {"OrderId": "inner"}), (200, {"OrderId": "unscoped"})])

    with client.order_submission_window(cutoff, now=lambda: cutoff):
        with client.order_submission_window(cutoff + timedelta(hours=1), now=lambda: cutoff):
            client.request("POST", "/trade/v2/orders", json_body={}, order_post=True)
        with pytest.raises(OrderSubmissionDeferred, match="market close"):
            client.request("POST", "/trade/v2/orders", json_body={}, order_post=True)
    client.request("POST", "/trade/v2/orders", json_body={}, order_post=True)

    assert len(transport.calls) == 2


def test_submission_window_rejects_naive_clock_values():
    client, transport = _client([])
    naive = datetime(2026, 10, 30, 16)
    with pytest.raises(ValueError, match="cutoff must be timezone-aware"):
        with client.order_submission_window(naive, now=lambda: naive):
            pass
    with client.order_submission_window(naive.replace(tzinfo=NEW_YORK), now=lambda: naive):
        with pytest.raises(ValueError, match="clock must be timezone-aware"):
            client.request("POST", "/trade/v2/orders", json_body={}, order_post=True)
    assert transport.calls == []


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
    client.discover_account("usd")

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
    client.discover_account("usd")

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


def test_transaction_pagination_stops_at_the_execution_deadline():
    clock = FakeClock()

    class SlowTransport(FakeTransport):
        def request(self, *args, **kwargs):
            response = super().request(*args, **kwargs)
            clock.value += 1
            return response

    transport = SlowTransport(
        [
            (
                200,
                {
                    "Data": [{"Trades": [{"OrderId": "order", "TradedQuantity": 1, "Price": 15}]}],
                    "__next": "?$skip=1",
                },
            ),
            (200, {"Data": [{"Trades": [{"OrderId": "order", "TradedQuantity": 1, "Price": 15}]}]}),
        ]
    )
    client = SaxoClient(tokens=Tokens(), transport=transport, clock=clock)
    client.client_key, client.account_key = "client", "account"

    with pytest.raises(SaxoOrderError, match="partially filled"):
        client.order_fill("order", 2, uic=7, deadline=1)
    assert len(transport.calls) == 1
