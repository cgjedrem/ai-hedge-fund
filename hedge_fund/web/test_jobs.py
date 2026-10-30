import threading
import time

import pytest

from hedge_fund.backtesting.test_fund import FakeAnalyst, FakeDataClient, SERIES
from hedge_fund.fund import Fund
from hedge_fund.paper.deployed import load_deployed
from hedge_fund.web.jobs import JobConflict, JobRegistry
from hedge_fund.web.schemas import BacktestRequest, DeployRequest
from hedge_fund.web.services import DeskService, ServiceError


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
    service = DeskService(
        demo_root,
        allow_writes=True,
        network_enabled=True,
        data_client_factory=lambda: FakeDataClient(SERIES),
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

    def slow_work(progress):
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
