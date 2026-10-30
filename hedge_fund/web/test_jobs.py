import threading
import time

import pytest
from fastapi.testclient import TestClient

from hedge_fund.backtesting.test_fund import FakeAnalyst, FakeDataClient, SERIES
from hedge_fund.data import data_provider
from hedge_fund.fund import Fund
from hedge_fund.llm import DEFAULT_MODEL, load_api_models
from hedge_fund.llm.registry import is_supported
from hedge_fund.paper.deployed import load_deployed
from hedge_fund.web.app import create_app
from hedge_fund.web.jobs import JobCancelled, JobConflict, JobRegistry
from hedge_fund.web.schemas import BacktestRequest, DeployRequest, ModelRequest
from hedge_fund.web.services import DeskService, ServiceError


class ManagedFakeDataClient(FakeDataClient):
    def __init__(self, series):
        super().__init__(series)
        self.entered = False
        self.exited = False

    def __enter__(self):
        self.entered = True
        return self

    def __exit__(self, *_args):
        self.exited = True


def _spec(name="research-sample"):
    return {
        "schema_version": 2,
        "name": name,
        "strategies": [
            {
                "name": "earnings-drift",
                "models": [{"name": "pead"}],
                "blend": {"mode": "long_short"},
            }
        ],
        "risk": {"max_position_pct": 0.25, "max_gross_exposure": 1.0},
        "capital": 100_000,
        "rebalance": "daily",
    }


def test_builder_canonical_validation_conflicts_and_deployment(tmp_path):
    service = DeskService(tmp_path, allow_writes=True)
    created = service.create_mandate(_spec())

    assert created["name"] == "research-sample"
    deployed = service.deploy_mandate("research-sample", DeployRequest(universe=["aapl", "msft"]))
    assert deployed["universe"] == ["AAPL", "MSFT"]
    assert load_deployed(tmp_path / "paper" / "research-sample").universe == ["AAPL", "MSFT"]

    with pytest.raises(ServiceError) as conflict:
        service.create_mandate(_spec("RESEARCH-SAMPLE"))
    assert conflict.value.status_code == 409
    with pytest.raises(ServiceError) as duplicate_deploy:
        service.deploy_mandate("research-sample", DeployRequest(universe=["AAPL"]))
    assert duplicate_deploy.value.status_code == 409

    invalid = _spec("invalid-cadence")
    invalid["interval"] = 1.0
    with pytest.raises(ServiceError) as cadence:
        service.create_mandate(invalid)
    assert cadence.value.status_code == 422
    service.close()


def test_backtest_job_uses_fake_data_and_persists_report(demo_root):
    data_client = ManagedFakeDataClient(SERIES)
    service = DeskService(
        demo_root,
        allow_writes=True,
        network_enabled=True,
        data_client_factory=lambda: data_client,
        fund_factory=lambda spec: Fund(
            spec,
            models={"earnings-drift": [FakeAnalyst("pead", {"AAPL": 1.0})]},
        ),
    )
    request = BacktestRequest(
        fund="demo-quality",
        universe=["AAPL"],
        start="2024-06-03",
        end="2024-06-07",
        provider=data_provider(),
        model=service.settings()["model"],
        agent_count=1,
    )
    job = service.submit_backtest(request)
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        current = service.get_job(job["id"])
        if current["status"] in {"succeeded", "failed"}:
            break
        time.sleep(0.01)

    assert current["status"] == "succeeded", current
    assert current["progress"] == 100
    assert current["report_id"].endswith(".json")
    report = service.research_report(current["report_id"])
    assert report["fund"] == "demo-quality"
    assert report["universe"] == ["AAPL"]
    assert report["session_count"] == 5
    assert len(report["sessions"]) == 5
    assert (demo_root / "research" / current["report_id"]).is_file()
    assert data_client.entered is True
    assert data_client.exited is True
    service.close()


def test_network_capability_is_required_before_any_data_adapter(tmp_path):
    called = False

    def forbidden():
        nonlocal called
        called = True
        raise AssertionError("disabled network must not construct a data client")

    service = DeskService(
        tmp_path,
        allow_writes=True,
        network_enabled=False,
        data_client_factory=forbidden,
    )
    with pytest.raises(ServiceError) as blocked:
        service.submit_backtest(
            BacktestRequest(
                fund="missing",
                universe=["AAPL"],
                start="2024-06-03",
                end="2024-06-04",
                provider=data_provider(),
                model=DEFAULT_MODEL,
                agent_count=1,
            )
        )
    assert blocked.value.status_code == 403
    assert not called
    assert not (tmp_path / "research").exists()
    service.close()


def test_job_registry_is_single_worker_and_reports_completion():
    registry = JobRegistry()
    started = threading.Event()
    release = threading.Event()

    def slow_work(progress, _cancelled):
        started.set()
        release.wait(timeout=2)
        progress(50)
        return {"report_id": "sample.json"}

    try:
        first = registry.submit("sample", "fake", "fake-model", slow_work)
        assert started.wait(timeout=1)
        with pytest.raises(JobConflict):
            registry.submit("sample", "fake", "fake-model", slow_work)
    finally:
        release.set()

    deadline = time.monotonic() + 2
    current = registry.get(first["id"])
    while current["status"] not in {"succeeded", "failed"} and time.monotonic() < deadline:
        time.sleep(0.01)
        current = registry.get(first["id"])
    registry.close()

    assert current["status"] == "succeeded"
    assert current["report_id"] == "sample.json"


def test_job_registry_cancels_cooperatively_without_retry_or_result():
    registry = JobRegistry()
    started = threading.Event()
    release = threading.Event()
    calls = 0

    def slow_work(_progress, cancelled):
        nonlocal calls
        calls += 1
        started.set()
        release.wait(timeout=2)
        if cancelled():
            raise JobCancelled()
        return {"report_id": "must-not-exist.json"}

    try:
        submitted = registry.submit("sample", "fake", "fake-model", slow_work)
        assert started.wait(timeout=1)
        cancelling = registry.cancel(submitted["id"])
        assert cancelling["cancel_requested"] is True
    finally:
        release.set()

    deadline = time.monotonic() + 2
    current = registry.get(submitted["id"])
    while current["status"] in {"queued", "running"} and time.monotonic() < deadline:
        time.sleep(0.01)
        current = registry.get(submitted["id"])
    registry.close()

    assert current["status"] == "cancelled"
    assert current["report_id"] is None
    assert calls == 1


def test_job_registry_shutdown_requests_cancel_and_waits_for_boundary():
    registry = JobRegistry()
    started = threading.Event()
    release = threading.Event()
    shutdown_done = threading.Event()

    def blocked_work(_progress, cancelled):
        started.set()
        release.wait(timeout=2)
        if cancelled():
            raise JobCancelled()
        return {"report_id": "must-not-exist.json"}

    submitted = registry.submit("sample", "fake", "fake-model", blocked_work)
    assert started.wait(timeout=1)

    shutdown = threading.Thread(target=lambda: (registry.close(), shutdown_done.set()))
    shutdown.start()
    deadline = time.monotonic() + 1
    current = registry.get(submitted["id"])
    while not current["cancel_requested"] and time.monotonic() < deadline:
        time.sleep(0.01)
        current = registry.get(submitted["id"])
    assert current["cancel_requested"] is True
    assert not shutdown_done.is_set()

    release.set()
    assert shutdown_done.wait(timeout=1)
    shutdown.join(timeout=1)

    current = registry.get(submitted["id"])
    assert current["status"] == "cancelled"
    assert current["report_id"] is None


def test_backtest_cancellation_closes_fake_client_and_freezes_job_model(demo_root, monkeypatch):
    import hedge_fund.web.services as services

    data_client = ManagedFakeDataClient(SERIES)
    entered = threading.Event()
    release = threading.Event()
    selected_model = next(model_id for _, model_id, provider in load_api_models() if model_id != DEFAULT_MODEL and is_supported(provider))
    service = DeskService(
        demo_root,
        allow_writes=True,
        network_enabled=True,
        data_client_factory=lambda: data_client,
        fund_factory=lambda spec: Fund(
            spec,
            models={"earnings-drift": [FakeAnalyst("pead", {"AAPL": 1.0})]},
        ),
    )
    service.set_model(ModelRequest(model=selected_model))

    def paused_backtest(_fund, _start, _end, _client, _universe, *, on_valuation):
        on_valuation(0, 2, None)
        entered.set()
        release.wait(timeout=2)
        on_valuation(1, 2, None)

    monkeypatch.setattr(services, "backtest_fund", paused_backtest)
    job = service.submit_backtest(
        BacktestRequest(
            fund="demo-quality",
            universe=["AAPL"],
            start="2024-06-03",
            end="2024-06-04",
            provider=data_provider(),
            model=selected_model,
            agent_count=1,
        )
    )
    assert job["model"] == selected_model
    assert entered.wait(timeout=1)
    with pytest.raises(ServiceError) as active_change:
        service.set_model(ModelRequest(model=service.catalog()["models"][0]["id"]))
    assert active_change.value.status_code == 409
    service.cancel_job(job["id"])
    release.set()

    deadline = time.monotonic() + 2
    current = service.get_job(job["id"])
    while current["status"] in {"queued", "running"} and time.monotonic() < deadline:
        time.sleep(0.01)
        current = service.get_job(job["id"])
    service.close()

    assert current["status"] == "cancelled"
    assert current["report_id"] is None
    assert data_client.entered is True
    assert data_client.exited is True
    assert not (demo_root / "research" / "cancelled.json").exists()


def test_cancel_endpoint_uses_write_gate_and_cooperative_job_boundary(demo_root, monkeypatch):
    import hedge_fund.web.services as services

    data_client = ManagedFakeDataClient(SERIES)
    entered = threading.Event()
    release = threading.Event()

    def paused_backtest(_fund, _start, _end, _client, _universe, *, on_valuation):
        on_valuation(0, 2, None)
        entered.set()
        release.wait(timeout=2)
        on_valuation(1, 2, None)

    monkeypatch.setattr(services, "backtest_fund", paused_backtest)
    app = create_app(
        root=demo_root,
        allow_writes=True,
        network_enabled=True,
        data_client_factory=lambda: data_client,
        fund_factory=lambda spec: Fund(
            spec,
            models={"earnings-drift": [FakeAnalyst("pead", {"AAPL": 1.0})]},
        ),
    )
    with TestClient(app) as client:
        capabilities = client.get("/api/capabilities", headers={"host": "127.0.0.1"}).json()
        settings = client.get("/api/settings", headers={"host": "127.0.0.1"}).json()
        headers = {
            "host": "127.0.0.1",
            "origin": "http://127.0.0.1",
            "x-csrf-token": capabilities["mutation_token"],
        }
        try:
            response = client.post(
                "/api/backtests",
                headers=headers,
                json={
                    "fund": "demo-quality",
                    "universe": ["AAPL"],
                    "start": "2024-06-03",
                    "end": "2024-06-04",
                    "provider": data_provider(),
                    "model": settings["model"],
                    "agent_count": 1,
                },
            )
            assert response.status_code == 202
            job_id = response.json()["id"]
            assert entered.wait(timeout=1)
            cancelled = client.post(f"/api/jobs/{job_id}/cancel", headers=headers)
            assert cancelled.status_code == 200
            assert cancelled.json()["cancel_requested"] is True
            release.set()

            deadline = time.monotonic() + 2
            current = client.get(f"/api/jobs/{job_id}", headers={"host": "127.0.0.1"}).json()
            while current["status"] in {"queued", "running"} and time.monotonic() < deadline:
                time.sleep(0.01)
                current = client.get(f"/api/jobs/{job_id}", headers={"host": "127.0.0.1"}).json()
            assert current["status"] == "cancelled"
            assert current["report_id"] is None
        finally:
            release.set()

    assert data_client.entered is True
    assert data_client.exited is True
