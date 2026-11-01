from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from threading import Event, Lock

from fastapi.testclient import TestClient

from hedge_fund.data.models import PriceSnapshot
from hedge_fund.paper.ledger import Ledger
from hedge_fund.runtime.admission import AdmissionCoordinator, RootOwnerLease
from hedge_fund.runtime.handover import record_ledger_head
from hedge_fund.runtime.root import RootContext
from hedge_fund.web.app import create_app
from hedge_fund.web.valuation import estimate_valuation


class FakeQuoteClient:
    def __init__(self, *, on_quote=None) -> None:
        self.calls: list[str] = []
        self.on_quote = on_quote

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return None

    def get_snapshot(self, ticker: str) -> PriceSnapshot:
        self.calls.append(ticker)
        if self.on_quote is not None:
            self.on_quote()
            self.on_quote = None
        price = 100.125 + len(self.calls) / 8
        now = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
        return PriceSnapshot(ticker=ticker, price=price, time=now)


class BlockingQuoteClient(FakeQuoteClient):
    def __init__(self) -> None:
        super().__init__()
        self.started = Event()
        self.release = Event()
        self.guard = Lock()

    def get_snapshot(self, ticker: str) -> PriceSnapshot:
        with self.guard:
            self.calls.append(ticker)
            call = len(self.calls)
        if call == 1:
            self.started.set()
            if not self.release.wait(timeout=5):
                raise TimeoutError("test quote release timed out")
        price = 100.125 + call / 8
        now = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
        return PriceSnapshot(ticker=ticker, price=price, time=now)


def _client(root, provider: FakeQuoteClient, *, network: bool) -> TestClient:
    app = create_app(
        root=root,
        allow_writes=True,
        network_enabled=network,
        demo=True,
        data_client_factory=lambda: provider,
    )
    return TestClient(app, client=("127.0.0.1", 50000))


def _mutation_headers(client: TestClient) -> dict[str, str]:
    caps = client.get("/api/capabilities", headers={"host": "127.0.0.1"}).json()
    return {
        "host": "127.0.0.1",
        "origin": "http://127.0.0.1",
        "x-csrf-token": caps["mutation_token"],
    }


def test_estimate_preserves_signed_fractional_values_and_recorded_nav():
    now = datetime(2026, 10, 29, 12, 0, tzinfo=timezone.utc)
    head = "a" * 64
    result = estimate_valuation(
        cash=10.125,
        positions={"AAPL": -0.5, "MSFT": 1.25},
        quotes={
            "AAPL": PriceSnapshot(
                ticker="AAPL",
                price=100.125,
                time="2026-10-29T11:59:59Z",
            ),
            "MSFT": PriceSnapshot(
                ticker="MSFT",
                price=200.5,
                time="2026-10-29T11:59:58Z",
            ),
        },
        errors={},
        as_of=now,
        expected_head=head,
        recorded_nav=123.4567,
    )

    assert result["status"] == "estimated"
    assert result["value"] == "210.6875"
    assert result["recorded_nav"] == "123.4567"
    assert result["expected_head"] == head
    assert [row["freshness"] for row in result["quotes"]] == ["unknown", "unknown"]


def test_missing_and_stale_quotes_never_return_a_complete_estimate():
    now = datetime(2026, 10, 29, 12, 0, tzinfo=timezone.utc)
    result = estimate_valuation(
        cash=50,
        positions={"AAPL": -0.5, "MSFT": 1.25},
        quotes={
            "AAPL": PriceSnapshot(
                ticker="AAPL",
                price=100,
                time="2026-10-29T11:59:00Z",
            ),
            "MSFT": PriceSnapshot(
                ticker="MSFT",
                price=200,
                time="2026-10-29T11:44:59Z",
            ),
        },
        errors={},
        as_of=now,
        expected_head=None,
        recorded_nav=None,
    )

    assert result["status"] == "stale"
    assert result["value"] is None
    assert result["partial_estimate"] == "0.00"
    assert result["coverage"]["stale"] == 1
    assert result["quotes"][1]["status"] == "stale"


def test_read_and_refresh_are_explicit_capability_gated_and_head_bound(demo_root):
    provider = FakeQuoteClient()
    with _client(demo_root, provider, network=False) as client:
        headers = _mutation_headers(client)
        detail = client.get("/api/paper/demo-quality", headers={"host": "127.0.0.1"}).json()
        observed = client.get(
            "/api/paper/demo-quality/valuation",
            headers={"host": "127.0.0.1"},
        )
        denied = client.post(
            "/api/paper/demo-quality/valuation",
            headers=headers,
            json={"expected_head": detail["last_record_hash"]},
        )
        stale = client.post(
            "/api/paper/demo-quality/valuation",
            headers=headers,
            json={"expected_head": "0" * 64},
        )

    assert observed.json()["status"] == "unavailable"
    assert denied.status_code == 403
    assert stale.status_code == 403
    assert provider.calls == []


def test_stale_head_is_rejected_before_provider_call(demo_root):
    provider = FakeQuoteClient()
    with _client(demo_root, provider, network=True) as client:
        headers = _mutation_headers(client)
        response = client.post(
            "/api/paper/demo-quality/valuation",
            headers=headers,
            json={"expected_head": "0" * 64},
        )
        invalid = client.post(
            "/api/paper/demo-quality/valuation",
            headers=headers,
            json={"expected_head": "invalid"},
        )

    assert response.status_code == 409
    assert invalid.status_code == 422
    assert provider.calls == []


def test_refresh_returns_estimate_without_changing_recorded_series(demo_root):
    provider = FakeQuoteClient()
    with _client(demo_root, provider, network=True) as client:
        headers = _mutation_headers(client)
        before = client.get("/api/paper/demo-quality", headers={"host": "127.0.0.1"}).json()
        assert before["positions"]

        response = client.post(
            "/api/paper/demo-quality/valuation",
            headers=headers,
            json={"expected_head": before["last_record_hash"]},
        )
        after = client.get("/api/paper/demo-quality", headers={"host": "127.0.0.1"}).json()
        observed = client.get(
            "/api/paper/demo-quality/valuation",
            headers={"host": "127.0.0.1"},
        )

    estimate = response.json()
    assert response.status_code == 200
    assert estimate["status"] == "estimated"
    assert estimate["provenance"] == "yfinance"
    assert estimate["coverage"]["total"] == len(before["positions"])
    assert estimate["coverage"]["usable"] == len(before["positions"])
    assert set(provider.calls) == {row["ticker"] for row in before["positions"]}
    assert after["nav"] == before["nav"]
    assert after["curve"] == before["curve"]
    assert after["sessions"] == before["sessions"]
    assert after["scorecard"] == before["scorecard"]
    assert after["live_value"]["value"] == estimate["value"]
    assert observed.json()["request_id"] == estimate["request_id"]


def test_refresh_discards_result_when_ledger_head_changes_during_quote(demo_root):
    directory = demo_root / "paper" / "demo-quality"

    def mutate_head():
        with RootContext.open(demo_root) as root:
            owner = RootOwnerLease.acquire(root)
            admission = AdmissionCoordinator(root, owner_lease=owner)
            try:
                with admission.manual_session("demo-quality", timeout=0):
                    Ledger(directory).rewind()
                record_ledger_head(root, "demo-quality", admission=admission)
            finally:
                owner.close()

    provider = FakeQuoteClient(on_quote=mutate_head)
    with _client(demo_root, provider, network=True) as client:
        headers = _mutation_headers(client)
        detail = client.get("/api/paper/demo-quality", headers={"host": "127.0.0.1"}).json()
        response = client.post(
            "/api/paper/demo-quality/valuation",
            headers=headers,
            json={"expected_head": detail["last_record_hash"]},
        )
        after = client.get(
            "/api/paper/demo-quality/valuation",
            headers={"host": "127.0.0.1"},
        )

    assert response.status_code == 409
    assert response.json()["detail"] == "Paper ledger changed during valuation; result discarded."
    assert len(provider.calls) == 1
    assert after.json()["status"] == "unavailable"


def test_late_refresh_cannot_replace_a_newer_estimate(demo_root):
    provider = BlockingQuoteClient()
    with _client(demo_root, provider, network=True) as client:
        headers = _mutation_headers(client)
        detail = client.get("/api/paper/demo-quality", headers={"host": "127.0.0.1"}).json()
        body = {"expected_head": detail["last_record_hash"]}
        with ThreadPoolExecutor(max_workers=1) as pool:
            earlier = pool.submit(
                client.post,
                "/api/paper/demo-quality/valuation",
                headers=headers,
                json=body,
            )
            assert provider.started.wait(timeout=5)
            newer = client.post(
                "/api/paper/demo-quality/valuation",
                headers=headers,
                json=body,
            )
            provider.release.set()
            obsolete = earlier.result(timeout=5)
        stored = client.get(
            "/api/paper/demo-quality/valuation",
            headers={"host": "127.0.0.1"},
        )

    assert newer.status_code == 200
    assert newer.json()["status"] == "estimated"
    assert obsolete.status_code == 200
    assert obsolete.json()["status"] == "obsolete"
    assert obsolete.json()["value"] is None
    assert stored.json()["request_id"] == newer.json()["request_id"]
