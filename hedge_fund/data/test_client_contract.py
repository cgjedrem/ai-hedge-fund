"""FDClient contract tests — mocked HTTP, no API key required.

Pins the two Phase 0 guarantees:

1. Fail-loud: infrastructure failures RAISE FDClientError instead of
   silently returning empty (silent empties poison backtests — missing
   data reads as "no signal").
2. Point-in-time: get_financial_metrics filters on filing_date (when the
   data became public), not report_period (which leaks 3-6 weeks of
   future into a backtest).
"""

import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest

from hedge_fund.data import FDClient, FDClientError
from hedge_fund.runtime.dispatch import make_one_shot_dispatch
from hedge_fund.runtime.policy import AuthorizationDenied, BudgetDenied, ProviderTarget


class _FakeResponse:
    def __init__(self, status_code=200, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text

    def json(self):
        return self._payload


class _FakeTransport(httpx.BaseTransport):
    def __init__(self):
        self.responses = []
        self.calls = []

    def handle_request(self, request):
        self.calls.append({"method": request.method, "url": str(request.url)})
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise httpx.ConnectError("synthetic transport failure", request=request)
        content = response.text
        if not content:
            content = json.dumps(response._payload)
        return httpx.Response(
            response.status_code,
            content=content.encode(),
            headers={"content-type": "application/json"},
            request=request,
        )


@pytest.fixture
def client(request):
    target = ProviderTarget(kind="data", provider="fd")
    now = datetime(2026, 10, 31, 12, 0, tzinfo=timezone.utc)
    dispatch = make_one_shot_dispatch(
        root_id="synthetic-root",
        subject_id="research-1",
        capture_digest="a" * 64,
        operation_id="operation-1",
        operation_digest="b" * 64,
        expires_at=now + timedelta(hours=1),
        targets=(target,),
        max_calls=100,
        max_cost=Decimal("10.00"),
        max_resources=100,
        upper_bound_costs={target.identity: Decimal("0.16")},
        clock=lambda: now,
        resolver=lambda _host, _port: ["8.8.8.8"],
    )
    transport = _FakeTransport()
    c = FDClient(
        api_key=getattr(request, "param", "test-key"),
        dispatch=dispatch,
        inner_transport=transport,
    )
    c._test_dispatch = dispatch
    c._test_transport = transport
    yield c
    c.close()


def _stub(client, responses):
    """Replace the session's request method; each call pops one response.

    A response that is an Exception instance is raised instead.
    """
    client._test_transport.responses = list(responses)
    client._test_transport.calls = []
    return client._test_transport.calls


def test_ambient_credential_does_not_authorize_fd_dispatch(monkeypatch):
    target = ProviderTarget(kind="data", provider="fd")
    now = datetime(2026, 10, 31, 12, 0, tzinfo=timezone.utc)
    dispatch = make_one_shot_dispatch(
        root_id="synthetic-root",
        subject_id="research-1",
        capture_digest="a" * 64,
        operation_id="ambient-key-test",
        operation_digest="b" * 64,
        expires_at=now + timedelta(minutes=5),
        targets=(target,),
        max_calls=1,
        max_cost=Decimal("0.16"),
        max_resources=1,
        upper_bound_costs={target.identity: Decimal("0.16")},
        clock=lambda: now,
        resolver=lambda _host, _port: ["8.8.8.8"],
    )
    transport = _FakeTransport()
    monkeypatch.setenv("FINANCIAL_DATASETS_API_KEY", "ambient-fixture-secret")

    with pytest.raises(AuthorizationDenied, match="credential is required"):
        FDClient(dispatch=dispatch, inner_transport=transport)

    assert transport.calls == []


# ---------------------------------------------------------------------------
# Fail-loud contract
# ---------------------------------------------------------------------------

def test_http_500_raises(client):
    _stub(client, [_FakeResponse(500, text="internal error")])
    with pytest.raises(FDClientError) as exc_info:
        client.get_prices("AAPL", "2024-01-01", "2024-12-31")
    assert exc_info.value.status_code == 500


def test_http_401_raises(client):
    _stub(client, [_FakeResponse(401, text="bad key")])
    with pytest.raises(FDClientError) as exc_info:
        client.get_financial_metrics("AAPL", "2024-12-31")
    assert exc_info.value.status_code == 401


@pytest.mark.parametrize("client", ["test-key", "fd-captured-credential-with-a-tail", "opaque-captured-credential-with-a-tail"], indirect=True)
@pytest.mark.parametrize("status", [401, 429, 500])
def test_http_error_redacts_every_captured_credential_prefix_across_truncation(client, status):
    key = client._session.headers["X-API-Key"]
    for prefix_length in range(1, len(key)):
        response = "~" * (200 - prefix_length) + key + "tail-only-after-the-boundary"
        _stub(client, [_FakeResponse(status, text=response)])

        with pytest.raises(FDClientError) as caught:
            client.get_prices("AAPL", "2024-01-01", "2024-12-31")

        message = str(caught.value)
        assert caught.value.status_code == status
        assert key not in message
        assert "~" + key[:prefix_length] not in message
        assert len(message.split(": ", 1)[1]) <= 200


@pytest.mark.parametrize("client", ["fd-captured-credential-with-a-tail"], indirect=True)
def test_http_error_redacts_full_response_before_later_credentials_move_inside_excerpt(client):
    key = client._session.headers["X-API-Key"]
    response = key + "|" + "~" * 170 + key + "tail"
    assert response.index(key, len(key)) > 200
    _stub(client, [_FakeResponse(500, text=response)])

    with pytest.raises(FDClientError) as caught:
        client.get_prices("AAPL", "2024-01-01", "2024-12-31")

    assert str(caught.value) == "GET /prices/ returned 500: [REDACTED]|" + "~" * 170 + "[REDACTED]tail"


def test_network_error_raises(client):
    _stub(client, [RuntimeError("boom")])
    with pytest.raises(FDClientError):
        client.get_prices("AAPL", "2024-01-01", "2024-12-31")


def test_404_means_no_data_not_failure(client):
    """404 is 'this data does not exist' — a data fact, not a failure."""
    _stub(client, [_FakeResponse(404)])
    assert client.get_financial_metrics("ZZZZ", "2024-12-31") == []


def test_429_is_not_retried(client):
    calls = _stub(client, [_FakeResponse(429), _FakeResponse(200, {"prices": []})])
    with pytest.raises(FDClientError) as exc_info:
        client.get_prices("AAPL", "2024-01-01", "2024-12-31")
    assert exc_info.value.status_code == 429
    assert len(calls) == 1


def test_429_retry_after_is_ignored(client):
    calls = _stub(client, [
        _FakeResponse(429),
        _FakeResponse(200, {"prices": [{
            "open": 1.0, "close": 2.0, "high": 2.0, "low": 1.0,
            "volume": 100, "time": "2024-01-02",
        }]}),
    ])
    with pytest.raises(FDClientError):
        client.get_prices("AAPL", "2024-01-01", "2024-12-31")
    assert len(calls) == 1


# ---------------------------------------------------------------------------
# Point-in-time contract
# ---------------------------------------------------------------------------

def test_financial_metrics_filters_on_filing_date(client):
    """The metrics query must use filing_date_lte (public-knowledge date),
    never report_period_lte (fiscal period end = lookahead leak)."""
    calls = _stub(client, [_FakeResponse(200, {"financial_metrics": []})])

    client.get_financial_metrics("AAPL", "2024-06-30", period="ttm", limit=4)

    params = parse_qs(urlsplit(calls[0]["url"]).query)
    assert params["filing_date_lte"] == ["2024-06-30"]
    assert "report_period_lte" not in params


# ---------------------------------------------------------------------------
# Pagination contract
# ---------------------------------------------------------------------------

def _price_row(day):
    return {
        "open": 1.0, "close": 2.0, "high": 2.0, "low": 1.0,
        "volume": 100, "time": f"2024-01-{day:02d}",
    }


def test_follows_next_page_url_to_the_end(client):
    """The API caps list responses at a fixed page size; the client must
    reassemble the full result by following next_page_url until absent."""
    calls = _stub(client, [
        _FakeResponse(200, {
            "prices": [_price_row(1), _price_row(2)],
            "next_page_url": "https://api.financialdatasets.ai/prices/?cursor=page2",
        }),
        _FakeResponse(200, {
            "prices": [_price_row(3), _price_row(4)],
            "next_page_url": "https://api.financialdatasets.ai/prices/?cursor=page3",
        }),
        _FakeResponse(200, {"prices": [_price_row(5)]}),
    ])

    prices = client.get_prices("AAPL", "2024-01-01", "2024-12-31")

    assert [p.time for p in prices] == [f"2024-01-0{d}" for d in (1, 2, 3, 4, 5)]
    # Pages 2+ request the next_page_url verbatim — no re-derived params.
    assert calls[1]["url"] == "https://api.financialdatasets.ai/prices/?cursor=page2"
    assert calls[2]["url"] == "https://api.financialdatasets.ai/prices/?cursor=page3"
    assert parse_qs(urlsplit(calls[1]["url"]).query) == {"cursor": ["page2"]}
    authorization = next(iter(client._test_dispatch._one_shot.values()))
    assert authorization.calls_reserved == 3
    assert authorization.cost_reserved == Decimal("0.48")
    assert authorization.resources_reserved == 3


def test_pagination_budget_denies_before_next_transport(client):
    target = ProviderTarget(kind="data", provider="fd")
    now = datetime(2026, 10, 31, 12, 0, tzinfo=timezone.utc)
    dispatch = make_one_shot_dispatch(
        root_id="synthetic-root",
        subject_id="research-1",
        capture_digest="a" * 64,
        operation_id="operation-2",
        operation_digest="c" * 64,
        expires_at=now + timedelta(hours=1),
        targets=(target,),
        max_calls=10,
        max_cost=Decimal("0.16"),
        max_resources=10,
        upper_bound_costs={target.identity: Decimal("0.16")},
        clock=lambda: now,
        resolver=lambda _host, _port: ["8.8.8.8"],
    )
    transport = _FakeTransport()
    bounded = FDClient(
        api_key="synthetic-only",
        dispatch=dispatch,
        inner_transport=transport,
    )
    transport.responses = [
        _FakeResponse(
            200,
            {
                "prices": [_price_row(1)],
                "next_page_url": "https://api.financialdatasets.ai/prices/?cursor=page2",
            },
        )
    ]

    with pytest.raises(BudgetDenied):
        bounded.get_prices("AAPL", "2024-01-01", "2024-12-31")

    authorization = next(iter(dispatch._one_shot.values()))
    assert authorization.calls_reserved == 1
    assert authorization.cost_reserved == Decimal("0.16")
    assert len(transport.calls) == 1
    bounded.close()


def test_no_next_page_url_means_single_request(client):
    calls = _stub(client, [_FakeResponse(200, {"prices": [_price_row(1)]})])
    prices = client.get_prices("AAPL", "2024-01-01", "2024-12-31")
    assert len(prices) == 1
    assert len(calls) == 1


def test_mid_walk_404_keeps_accumulated_rows(client):
    """A 404 on page 2+ ends the stream; rows already fetched are kept."""
    _stub(client, [
        _FakeResponse(200, {
            "prices": [_price_row(1)],
            "next_page_url": "https://api.financialdatasets.ai/prices/?cursor=page2",
        }),
        _FakeResponse(404),
    ])
    prices = client.get_prices("AAPL", "2024-01-01", "2024-12-31")
    assert len(prices) == 1


def test_mid_walk_500_still_fails_loud(client):
    """The fail-loud contract survives pagination: a real failure on any
    page raises instead of silently returning a partial series."""
    _stub(client, [
        _FakeResponse(200, {
            "prices": [_price_row(1)],
            "next_page_url": "https://api.financialdatasets.ai/prices/?cursor=page2",
        }),
        _FakeResponse(500, text="internal error"),
    ])
    with pytest.raises(FDClientError):
        client.get_prices("AAPL", "2024-01-01", "2024-12-31")


def test_snapshot_is_a_single_quote_not_a_list(client):
    calls = _stub(client, [_FakeResponse(200, {"snapshot": {
        "ticker": "BRK.A", "price": 756000.0, "day_change": 1210.0,
        "day_change_percent": 0.16, "time": "2026-10-05T14:28:39Z",
        "time_milliseconds": 1791210519441,
    }})])

    snap = client.get_snapshot("BRK.A")

    assert urlsplit(calls[0]["url"]).path.endswith("/prices/snapshot/")
    assert parse_qs(urlsplit(calls[0]["url"]).query) == {"ticker": ["BRK.A"]}
    assert snap.price == 756000.0
    assert snap.time == "2026-10-05T14:28:39Z"


def test_snapshot_404_means_unknown_ticker(client):
    _stub(client, [_FakeResponse(404)])
    assert client.get_snapshot("ZZZZ") is None


def test_snapshot_500_fails_loud(client):
    _stub(client, [_FakeResponse(500, text="internal error")])
    with pytest.raises(FDClientError):
        client.get_snapshot("AAPL")


def test_financial_metrics_parses_filing_metadata(client):
    _stub(client, [_FakeResponse(200, {"financial_metrics": [{
        "ticker": "AAPL",
        "report_period": "2024-03-30",
        "period": "quarterly",
        "filing_date": "2024-05-02",
        "filing_datetime": "2024-05-02T16:31:00-04:00",
        "market_cap": 3.0e12,
    }]})])

    m = client.get_financial_metrics("AAPL", "2024-06-30")[0]

    assert m.filing_date == "2024-05-02"
    assert m.filing_datetime == "2024-05-02T16:31:00-04:00"
    assert m.report_period == "2024-03-30"
