import os
import threading
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest

import hedge_fund.runtime.owned_runner as owned_runner
import hedge_fund.web.services as web_services
from hedge_fund.data.models import Price
from hedge_fund.data.sessions import NEW_YORK
from hedge_fund.fund import FundSpec, load_spec
from hedge_fund.models import Signal
from hedge_fund.paper.deployed import load_deployed
from hedge_fund.paper.ledger import Ledger
from hedge_fund.pipeline.session import code_version, mandate_hash, SessionRecord
from hedge_fund.runtime.configuration import RuntimeSettings
from hedge_fund.runtime.dispatch import make_one_shot_dispatch
from hedge_fund.runtime.handover import record_ledger_head
from hedge_fund.runtime.owned_runner import read_runner_record, runner_key
from hedge_fund.runtime.policy import AuthorizationDenied, BudgetDenied, ProviderTarget
from hedge_fund.test_support.handover import enroll_synthetic_root
from hedge_fund.web.schemas import (
    DeployRequest,
    PaperTickAcceptRequest,
    PaperTickPreviewRequest,
    RunnerPreviewRequest,
    RunnerStartAcceptRequest,
)
from hedge_fund.web.services import DeskService, ServiceError


class _OfflineDataClient:
    def __init__(self):
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, *_exc_info):
        return None

    def get_prices(self, ticker, start_date, end_date, **_kwargs):
        self.calls.append((ticker, start_date, end_date))
        if start_date <= end_date:
            return [
                Price(
                    open=100,
                    close=101,
                    high=102,
                    low=99,
                    volume=1000,
                    time=f"{end_date}T16:00:00-04:00",
                )
            ]
        return []


class _OfflineAnalyst:
    name = "pead"

    def predict(self, ticker, as_of, _view):
        return Signal(
            model_name=self.name,
            ticker=ticker,
            date=as_of,
            value=0.1,
            reasoning="offline test signal",
            components={},
        )


class _OfflineFund:
    def __init__(self, spec: FundSpec):
        self.spec = spec
        self.strategies = [(spec.strategies[0], [_OfflineAnalyst()])]


def _local_settings() -> RuntimeSettings:
    return RuntimeSettings(
        data_provider="yfinance",
        llm_provider="Ollama",
        model="gemma3:4b",
        endpoint="http://127.0.0.1:11434",
        timeout_seconds=1,
        parameters={"max_tokens": 32},
        version=0,
    )


def _wait_for_operation(
    service: DeskService,
    operation_id: str,
    *,
    timeout: float = 60,
) -> dict:
    deadline = time.monotonic() + timeout
    latest = None
    while time.monotonic() < deadline:
        try:
            latest = service.get_operation(operation_id)
        except ServiceError as exc:
            if exc.status_code != 503 or exc.code != "observation-conflict":
                raise
            time.sleep(0.05)
            continue
        if latest["status"] in {"completed", "failed", "cancelled", "interrupted"}:
            return latest
        time.sleep(0.05)
    raise AssertionError(f"paper operation did not reach a terminal state: {latest}")


def _wait_for_runner_status(
    service: DeskService,
    name: str,
    expected: str,
    *,
    timeout: float = 30,
) -> dict:
    deadline = time.monotonic() + timeout
    latest = None
    while time.monotonic() < deadline:
        latest = service.runner_status(name)
        if latest["status"] == expected:
            return latest
        time.sleep(0.02)
    raise AssertionError(f"runner did not reach {expected!r}: {latest}")


def test_reviewed_manual_tick_executes_one_session_with_local_fakes(
    demo_root,
    monkeypatch,
):
    data_client = _OfflineDataClient()

    def no_provider_client(*_args, **_kwargs):
        raise AssertionError("manual tick must use the injected offline data client")

    monkeypatch.setattr(web_services, "make_data_client", no_provider_client)
    service = DeskService(
        demo_root,
        allow_writes=True,
        network_enabled=True,
        data_client_factory=lambda: data_client,
        fund_factory=_OfflineFund,
    )
    service._runtime_settings = _local_settings()
    try:
        spec = load_spec(demo_root / "mandates" / "demo-quality.yaml").model_copy(update={"name": "manual-test"})
        service.create_mandate(spec.model_dump(mode="python"))
        service.deploy_mandate("manual-test", DeployRequest(universe=["AAPL", "MSFT"]))
        ledger = Ledger(demo_root / "paper" / "manual-test")
        before = ledger.sessions()

        preview = service.create_manual_tick_preview(
            "manual-test",
            PaperTickPreviewRequest(expected_head=None),
            operator_session="offline-test-session",
        )
        due_session = preview["due_set"][0]
        assert preview["reviewed_head"] is None
        assert preview["estimate"]["maximum_cost_usd"] == 0.0
        assert preview["capture"]["llm_provider"] == "Ollama"

        request = PaperTickAcceptRequest(
            request_id="offline-manual-tick-1",
            preview_id=preview["preview_id"],
            preview_digest=preview["preview_digest"],
            confirmation_token=preview["confirmation_token"],
            expected_head=None,
            due_set=[due_session],
        )
        accepted = service.accept_manual_tick(
            "manual-test",
            request,
            operator_session="offline-test-session",
        )
        completed = _wait_for_operation(service, accepted["operation_id"])
        replayed = service.accept_manual_tick(
            "manual-test",
            request,
            operator_session="offline-test-session",
        )
        after = ledger.sessions()
        snapshot = service.paper_detail("manual-test")
    finally:
        service.close()

    assert completed["status"] == "completed"
    assert completed["result"]["session"] == due_session
    assert replayed["operation_id"] == accepted["operation_id"]
    assert after == [*before, due_session]
    assert snapshot["last_session"] == due_session
    assert len(data_client.calls) > 0


def test_interrupted_redo_denies_web_preview_before_provider_and_allows_halt(demo_root):
    calls = []

    def forbidden_factory():
        calls.append("provider")
        pytest.fail("interrupted redo reached a data provider")

    service = DeskService(
        demo_root,
        allow_writes=True,
        network_enabled=True,
        data_client_factory=forbidden_factory,
        fund_factory=_OfflineFund,
    )
    service._runtime_settings = _local_settings()
    try:
        name = "reconciliation-test"
        spec = load_spec(demo_root / "mandates" / "demo-quality.yaml").model_copy(update={"name": name})
        service.create_mandate(spec.model_dump(mode="python"))
        service.deploy_mandate(name, DeployRequest(universe=["AAPL"]))
        ledger = Ledger(demo_root / "paper" / name)
        record = SessionRecord(
            fund=name,
            session="2024-06-07",
            universe=["AAPL"],
            nav=spec.capital,
            cash=spec.capital,
            positions={},
            marks={},
            benchmark=spec.benchmark,
            benchmark_close=100.0,
            rebalance=True,
            code_version=code_version(),
            mandate_hash=mandate_hash(spec),
        )
        record.hash = record.compute_hash()
        with service._admission.manual_session(name, timeout=0):
            ledger.append(record)
            ledger.begin_redo(record)
        with pytest.raises(ServiceError) as exc:
            service.create_manual_tick_preview(
                name,
                PaperTickPreviewRequest(expected_head=record.hash),
                operator_session="offline-test-session",
            )
        assert exc.value.code == "reconciliation-required"
        assert calls == []
        service.halt_fund(name, "emergency")
        assert ledger.halted() == "emergency"
    finally:
        service.close()


@pytest.mark.parametrize("journal_state", ["unfinished", "malformed"])
def test_unfinished_consumption_denies_web_preview_before_provider_and_halts(demo_root, journal_state):
    from hedge_fund.runtime.admission import paper_approval_transition

    calls = []

    def forbidden_factory():
        calls.append("provider")
        pytest.fail("unfinished consumption reached a data provider")

    service = DeskService(
        demo_root,
        allow_writes=True,
        network_enabled=True,
        data_client_factory=forbidden_factory,
        fund_factory=_OfflineFund,
    )
    service._runtime_settings = _local_settings()
    try:
        name = "demo-quality"
        ledger = Ledger(demo_root / "paper" / name)
        latest = ledger.latest()
        assert latest.decision is not None
        with paper_approval_transition(service._admission, name) as proof:
            approval = ledger.set_approval("approve", latest.decision.as_of, latest.hash, "web", admission=proof)
        with service._admission.control_lane(name):
            if journal_state == "malformed":
                with ledger.events_path.open("a", encoding="utf-8") as history:
                    history.write("{invalid\n")
            else:
                ledger.log_event(
                    "consume",
                    decision_as_of=approval["decision_as_of"],
                    decision_hash=approval["decision_hash"],
                    approval_verdict=approval["verdict"],
                    approval_by=approval["by"],
                    approval_id=approval["approval_id"],
                    session="2025-01-07",
                    durable=True,
                )
        with pytest.raises(ServiceError) as exc:
            service.create_manual_tick_preview(
                name,
                PaperTickPreviewRequest(expected_head=latest.hash),
                operator_session="offline-test-session",
            )
        assert exc.value.code == "reconciliation-required"
        assert calls == []
        assert ledger.halted() == "approval journal requires reconciliation"
        service.halt_fund(name, "emergency")
        assert ledger.halted() == "emergency"
    finally:
        service.close()


def test_injected_data_client_reserves_each_call_before_fake(demo_root):
    data_client = _OfflineDataClient()
    factory_calls = []
    service = DeskService(
        demo_root,
        allow_writes=True,
        network_enabled=True,
        data_client_factory=lambda: factory_calls.append("factory") or data_client,
    )
    target = ProviderTarget(kind="data", provider="yfinance")
    now = datetime.now(timezone.utc)
    dispatch = make_one_shot_dispatch(
        root_id="synthetic-root",
        subject_id="demo-quality",
        capture_digest="a" * 64,
        operation_id="operation-1",
        operation_digest="b" * 64,
        expires_at=now + timedelta(minutes=5),
        targets=(target,),
        max_calls=1,
        max_cost=Decimal("0"),
        max_resources=1,
        upper_bound_costs={target.identity: Decimal("0")},
        clock=lambda: now,
        resolver=lambda _host, _port: ["8.8.8.8"],
    )
    try:
        with pytest.raises(AuthorizationDenied):
            with service._make_data_client(provider="yfinance"):
                pytest.fail("fake client factory ran without operation authority")
        assert factory_calls == []

        with service._make_data_client(
            provider="yfinance",
            dispatch=dispatch,
        ) as guarded:
            result = guarded.get_prices(
                "AAPL",
                "2024-06-03",
                "2024-06-03",
            )
            with pytest.raises(BudgetDenied):
                guarded.get_prices(
                    "AAPL",
                    "2024-06-04",
                    "2024-06-04",
                )
    finally:
        service.close()

    authorization = dispatch._one_shot[target.identity]
    assert result
    assert factory_calls == ["factory"]
    assert len(data_client.calls) == 1
    assert authorization.calls_reserved == 1


def test_manual_tick_denies_runner_lane_conflict_without_ledger_change(demo_root):
    data_client = _OfflineDataClient()
    service = DeskService(
        demo_root,
        allow_writes=True,
        network_enabled=True,
        data_client_factory=lambda: data_client,
        fund_factory=_OfflineFund,
    )
    service._runtime_settings = _local_settings()
    ledger = Ledger(demo_root / "paper" / "demo-quality")
    before = ledger.sessions()
    head = ledger.latest().hash

    try:
        with service._admission.runner_reservation("demo-quality", timeout=0):
            with pytest.raises(ServiceError) as conflict:
                service.create_manual_tick_preview(
                    "demo-quality",
                    PaperTickPreviewRequest(expected_head=head),
                    operator_session="offline-test-session",
                )
        after = ledger.sessions()
    finally:
        service.close()

    assert conflict.value.status_code == 409
    assert after == before


def test_web_saxo_deployment_denied_before_deploy_adapter(demo_root, monkeypatch):
    payload = load_spec(demo_root / "mandates" / "demo-quality.yaml").model_dump(mode="python")
    payload.update(
        {
            "name": "saxo-web-denied",
            "broker": "saxo",
            "rebalance": "minute",
            "interval": 5.0,
            "window": {"start": "09:30", "end": "15:59"},
        }
    )
    spec = FundSpec.model_validate(payload)
    service = DeskService(demo_root, allow_writes=True)
    service.create_mandate(spec.model_dump(mode="python"))
    calls = []

    def forbidden(*_args, **_kwargs):
        calls.append(True)
        raise AssertionError("web SIM deployment reached the deploy adapter")

    monkeypatch.setattr(web_services, "deploy", forbidden)
    try:
        with pytest.raises(ServiceError) as rejected:
            service.deploy_mandate(
                "saxo-web-denied",
                DeployRequest(universe=["AAPL"]),
            )
    finally:
        service.close()

    assert rejected.value.status_code == 403
    assert calls == []
    assert not (demo_root / "paper" / "saxo-web-denied").exists()


def test_manual_tick_rejects_stale_head_before_creating_operation(
    demo_root,
    monkeypatch,
):
    data_client = _OfflineDataClient()

    def no_provider_client(*_args, **_kwargs):
        raise AssertionError("manual tick must use the injected offline data client")

    monkeypatch.setattr(web_services, "make_data_client", no_provider_client)
    service = DeskService(
        demo_root,
        allow_writes=True,
        network_enabled=True,
        data_client_factory=lambda: data_client,
        fund_factory=_OfflineFund,
    )
    service._runtime_settings = _local_settings()
    ledger = Ledger(demo_root / "paper" / "demo-quality")
    try:
        latest = ledger.latest()
        preview = service.create_manual_tick_preview(
            "demo-quality",
            PaperTickPreviewRequest(expected_head=latest.hash),
            operator_session="offline-stale-head-session",
        )
        due_session = preview["due_set"][0]
        stale_sessions = ledger.sessions()
        deployed = load_deployed(demo_root / "paper" / "demo-quality")
        changed = SessionRecord(
            fund=deployed.name,
            session=due_session,
            universe=list(deployed.universe),
            nav=latest.nav,
            cash=latest.cash,
            positions=dict(latest.positions),
            marks=dict(latest.marks),
            benchmark=deployed.spec.benchmark,
            benchmark_close=latest.benchmark_close,
            rebalance=False,
            prev_hash=latest.hash,
            code_version=code_version(),
            mandate_hash=mandate_hash(deployed.spec),
        )
        changed.hash = changed.compute_hash()
        with service._admission.runner_reservation("demo-quality", timeout=0):
            with service._admission.execution_lease("demo-quality", timeout=0):
                ledger.append(changed)
        record_ledger_head(
            service.root_context,
            "demo-quality",
            admission=service._admission,
        )
        sessions_after_head_change = ledger.sessions()
        request = PaperTickAcceptRequest(
            request_id="offline-stale-manual-tick-1",
            preview_id=preview["preview_id"],
            preview_digest=preview["preview_digest"],
            confirmation_token=preview["confirmation_token"],
            expected_head=latest.hash,
            due_set=[due_session],
        )

        with pytest.raises(ServiceError) as conflict:
            service.accept_manual_tick(
                "demo-quality",
                request,
                operator_session="offline-stale-head-session",
            )
        after = ledger.sessions()
        accepted = service._operation_store.get_by_request(
            "offline-stale-manual-tick-1",
        )
    finally:
        service.close()

    assert conflict.value.status_code == 409
    assert sessions_after_head_change == [*stale_sessions, due_session]
    assert after == sessions_after_head_change
    assert accepted is None


def _start_owned_runner(demo_root, name: str):
    root_path = Path(os.environ["HEDGE_FUND_TEST_ROOT"]) / f"{name}-root"
    root_path.mkdir()
    enroll_synthetic_root(root_path)
    service = DeskService(
        root_path,
        allow_writes=True,
        network_enabled=True,
    )
    service._runtime_settings = _local_settings()
    try:
        payload = load_spec(demo_root / "mandates" / "demo-quality.yaml").model_dump(mode="python")
        payload.update(
            {
                "name": name,
                "rebalance": "minute",
                "interval": 1.0,
                "window": {"start": "04:30", "end": "04:35"},
            }
        )
        spec = FundSpec.model_validate(payload)
        service.create_mandate(spec.model_dump(mode="python"))
        service.deploy_mandate(name, DeployRequest(universe=["AAPL", "MSFT"]))
        ledger = Ledger(root_path / "paper" / name)
        session_record = SessionRecord(
            fund=name,
            session=f"{datetime.now(NEW_YORK).date().isoformat()}T04:35:00",
            universe=["AAPL", "MSFT"],
            nav=spec.capital,
            cash=spec.capital,
            positions={},
            marks={},
            benchmark=spec.benchmark,
            benchmark_close=100.0,
            rebalance=True,
            code_version=code_version(),
            mandate_hash=mandate_hash(spec),
        )
        session_record.hash = session_record.compute_hash()
        with service._admission.manual_session(name, timeout=0):
            ledger.append(session_record)
        record_ledger_head(
            service.root_context,
            name,
            admission=service._admission,
        )
        head = ledger.latest().hash
        preview = service.create_runner_preview(
            name,
            RunnerPreviewRequest(
                expected_head=head,
                max_sessions=1,
                max_runtime_minutes=1,
            ),
            operator_session="owned-runner-test-session",
        )
        assert preview["due_set"] == []
        assert preview["capture"]["llm_provider"] == "Ollama"

        accepted = service.accept_runner_start(
            name,
            RunnerStartAcceptRequest(
                request_id="owned-runner-start-1",
                preview_id=preview["preview_id"],
                preview_digest=preview["preview_digest"],
                confirmation_token=preview["confirmation_token"],
                expected_head=head,
                due_set=preview["due_set"],
                max_sessions=1,
                max_runtime_minutes=1,
            ),
            operator_session="owned-runner-test-session",
        )
    except BaseException:
        service.close()
        raise
    return service, root_path, session_record, head, accepted


def _stop_owned_runner(service: DeskService, name: str) -> None:
    try:
        if service.runner_status(name)["status"] in {
            "starting",
            "running",
            "stopping",
        }:
            service.stop_runner(name)
    finally:
        try:
            process_ref = service._runner_manager._processes.get(runner_key(name))
            if process_ref is not None and process_ref.process.poll() is None:
                process_ref.process.wait(timeout=30)
        finally:
            service.close()


def test_owned_runner_child_starts_and_stops_with_exact_process_identity(
    demo_root,
):
    name = "owned-runner-test"
    service, root_path, session_record, head, accepted = _start_owned_runner(demo_root, name)
    process = None
    try:
        completed = _wait_for_operation(service, accepted["operation_id"])
        state = read_runner_record(service.root_context, name, "state")
        assert completed["status"] == "completed", {
            "error": completed.get("error"),
            "runner": service.runner_status(name),
            "state": state,
            "control": read_runner_record(service.root_context, name, "control"),
        }
        running = service.runner_status(name)
        key = runner_key(name)
        process_ref = service._runner_manager._processes[key]
        process = process_ref.process
        runner_record = state

        assert completed["status"] == "completed"
        assert running["status"] == "running"
        assert running["available"] is True
        assert runner_record["pid"] == process.pid
        assert runner_record["process_identity"] == process_ref.identity
        assert runner_record["sessions_completed"] == 0
        assert process.poll() is None

        stopping = service.stop_runner(name)
        stopped = _wait_for_runner_status(service, name, "stopped")
        assert stopping["status"] == "stopping"
        assert stopped["available"] is False
        assert stopped["sessions_completed"] == 0
        after = Ledger(root_path / "paper" / name)
        assert after.sessions() == [session_record.session]
        assert after.latest().hash == head
        assert process.wait(timeout=30) == 0
    finally:
        _stop_owned_runner(service, name)


def test_owned_runner_readiness_timeout_fails_closed_and_stops_child(
    demo_root,
    monkeypatch,
):
    name = "owned-runner-timeout"
    monkeypatch.setattr(owned_runner, "_READINESS_TIMEOUT_SECONDS", 0.0)
    service, root_path, session_record, head, accepted = _start_owned_runner(demo_root, name)
    try:
        failed = _wait_for_operation(service, accepted["operation_id"], timeout=60)
        state = read_runner_record(service.root_context, name, "state")
        control = read_runner_record(service.root_context, name, "control")
        process_ref = service._runner_manager._processes[runner_key(name)]

        assert failed["status"] == "failed"
        assert state["status"] == "failed"
        assert state["reason"] == "runner-readiness-timeout"
        assert control["stop_requested"] is True
        assert process_ref.process.wait(timeout=60) is not None
        after = Ledger(root_path / "paper" / name)
        assert after.sessions() == [session_record.session]
        assert after.latest().hash == head
    finally:
        _stop_owned_runner(service, name)


def test_runner_start_rejects_head_changed_after_acceptance_before_spawn(
    demo_root,
    monkeypatch,
):
    name = "stale-runner-start"
    data_client = _OfflineDataClient()
    service = DeskService(
        demo_root,
        allow_writes=True,
        network_enabled=True,
        data_client_factory=lambda: data_client,
        fund_factory=_OfflineFund,
    )
    service._runtime_settings = _local_settings()
    ledger = Ledger(demo_root / "paper" / name)
    start_entered = threading.Event()
    release_start = threading.Event()
    popen_calls = []
    original_start = service._runner_manager.start

    def delayed_start(*args, **kwargs):
        start_entered.set()
        if not release_start.wait(timeout=60):
            raise TimeoutError("runner start barrier timed out")
        return original_start(*args, **kwargs)

    def forbidden_spawn(*_args, **_kwargs):
        popen_calls.append(True)
        raise OSError("stale runner preview must not spawn")

    monkeypatch.setattr(service._runner_manager, "start", delayed_start)
    monkeypatch.setattr(owned_runner.subprocess, "Popen", forbidden_spawn)
    accepted = None
    completed = None
    changed = None
    try:
        payload = load_spec(demo_root / "mandates" / "demo-quality.yaml").model_dump(mode="python")
        payload["name"] = name
        spec = FundSpec.model_validate(payload)
        service.create_mandate(spec.model_dump(mode="python"))
        service.deploy_mandate(name, DeployRequest(universe=["AAPL", "MSFT"]))
        service._runtime_settings = _local_settings()
        preview = service.create_runner_preview(
            name,
            RunnerPreviewRequest(
                expected_head=None,
                max_sessions=1,
                max_runtime_minutes=1,
            ),
            operator_session="stale-runner-start-session",
        )
        accepted = service.accept_runner_start(
            name,
            RunnerStartAcceptRequest(
                request_id="stale-runner-start-1",
                preview_id=preview["preview_id"],
                preview_digest=preview["preview_digest"],
                confirmation_token=preview["confirmation_token"],
                expected_head=None,
                due_set=preview["due_set"],
                max_sessions=1,
                max_runtime_minutes=1,
            ),
            operator_session="stale-runner-start-session",
        )
        assert start_entered.wait(timeout=60)

        deployed = load_deployed(demo_root / "paper" / name)
        changed = SessionRecord(
            fund=name,
            session=(datetime.now().date() + timedelta(days=1)).isoformat(),
            universe=list(deployed.universe),
            nav=deployed.spec.capital,
            cash=deployed.spec.capital,
            positions={},
            marks={},
            benchmark=deployed.spec.benchmark,
            benchmark_close=100.0,
            rebalance=False,
            prev_hash=None,
            code_version=code_version(),
            mandate_hash=mandate_hash(deployed.spec),
        )
        changed.hash = changed.compute_hash()
        with service._admission.manual_session(name, timeout=0):
            ledger.append(changed)
        record_ledger_head(
            service.root_context,
            name,
            admission=service._admission,
        )
        release_start.set()
        completed = _wait_for_operation(service, accepted["operation_id"])
    finally:
        release_start.set()
        service.close()

    assert completed["status"] == "failed"
    assert popen_calls == []
    assert ledger.latest().hash == changed.hash


@pytest.mark.parametrize(
    ("fault", "code", "policy"),
    [
        ("busy", "writer-conflict", "retry-later"),
        ("conflict", "request-conflict", "reload"),
        ("admission", "writer-conflict", "inspect-status"),
    ],
)
def test_paper_accept_retries_only_busy_storage_and_records_no_effects(demo_root, monkeypatch, fault, code, policy):
    from hedge_fund.runtime.admission import AdmissionError
    from hedge_fund.runtime.operations import OperationBusy, OperationConflict
    from hedge_fund.web.schemas import error_payload

    faults = {
        "busy": OperationBusy("synthetic busy"),
        "conflict": OperationConflict("synthetic conflict"),
        "admission": AdmissionError("synthetic admission"),
    }
    data_client = _OfflineDataClient()
    service = DeskService(
        demo_root,
        allow_writes=True,
        network_enabled=True,
        data_client_factory=lambda: data_client,
        fund_factory=_OfflineFund,
    )
    service._runtime_settings = _local_settings()
    try:
        spec = load_spec(demo_root / "mandates" / "demo-quality.yaml").model_copy(update={"name": "fault-test"})
        service.create_mandate(spec.model_dump(mode="python"))
        service.deploy_mandate("fault-test", DeployRequest(universe=["AAPL", "MSFT"]))
        ledger = Ledger(demo_root / "paper" / "fault-test")
        before = ledger.sessions()
        preview = service.create_manual_tick_preview(
            "fault-test",
            PaperTickPreviewRequest(expected_head=None),
            operator_session="offline-test-session",
        )

        def fail(*_args, **_kwargs):
            raise faults[fault]

        monkeypatch.setattr(service._operation_store, "accept_request", fail)
        with pytest.raises(ServiceError) as denied:
            service.accept_manual_tick(
                "fault-test",
                PaperTickAcceptRequest(
                    request_id=f"offline-fault-{fault}",
                    preview_id=preview["preview_id"],
                    preview_digest=preview["preview_digest"],
                    confirmation_token=preview["confirmation_token"],
                    expected_head=None,
                    due_set=preview["due_set"],
                ),
                operator_session="offline-test-session",
            )
        after = ledger.sessions()
    finally:
        service.close()

    body = error_payload(denied.value.status_code, denied.value.detail, code=denied.value.code, retry_policy=denied.value.retry_policy)
    assert (denied.value.status_code, body["code"], body["retry_policy"]) == (409, code, policy)
    assert "synthetic" not in denied.value.detail
    assert after == before
