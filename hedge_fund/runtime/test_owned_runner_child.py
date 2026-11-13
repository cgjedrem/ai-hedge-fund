import hashlib
import json
import threading
from datetime import datetime, timedelta, timezone

import pytest

from hedge_fund.data.models import Price
from hedge_fund.fund import FundSpec
from hedge_fund.models import Signal
from hedge_fund.paper.deployed import deploy
from hedge_fund.paper.ledger import Ledger
from hedge_fund.pipeline.session import code_version, mandate_hash, SessionRecord
from hedge_fund.runtime.admission import AdmissionCoordinator, RootOwnerLease
from hedge_fund.runtime.capture import freeze_capture
from hedge_fund.runtime.configuration import resolve_settings
from hedge_fund.runtime.handover import enroll_fresh, record_ledger_head, root_binding
from hedge_fund.runtime.owned_runner import (
    OwnedRunnerError,
    read_runner_record,
    runner_key,
    RUNNER_ROOT,
    write_runner_record,
)
from hedge_fund.runtime.owned_runner_child import run_owned_runner
from hedge_fund.runtime.ownership import current_process_identity
from hedge_fund.runtime.policy import AuthorizationDenied, ProviderTarget
from hedge_fund.runtime.root import RootContext

_INITIAL_SESSION = "2024-06-07"
_DUE_SESSION = "2024-06-10"
_RUNNER_NOW = datetime(2024, 6, 11, 20, tzinfo=timezone.utc)


class _OfflineDataClient:
    def __init__(self):
        self.started = threading.Event()
        self.release = threading.Event()
        self._blocked = False
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, *_exc_info):
        return None

    def get_prices(self, ticker, start_date, end_date, **_kwargs):
        self.calls.append(ticker)
        if ticker == "AAPL" and not self._blocked:
            self._blocked = True
            self.started.set()
            if not self.release.wait(timeout=10):
                raise TimeoutError("offline test release was not signalled")
        if start_date <= _DUE_SESSION <= end_date:
            return [
                Price(
                    open=100,
                    close=101,
                    high=102,
                    low=99,
                    volume=1000,
                    time=f"{_DUE_SESSION}T16:00:00-04:00",
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
    def __init__(self, spec, _capture, _root, _dispatch):
        self.spec = spec
        self.strategies = [(spec.strategies[0], [_OfflineAnalyst()])]


class _GuardedOfflineDataClient:
    def __init__(self, client, dispatch):
        self._client = client
        self._dispatch = dispatch
        self._target = ProviderTarget(kind="data", provider="yfinance")

    def __enter__(self):
        return self

    def __exit__(self, *_exc_info):
        return None

    def __getattr__(self, name):
        value = getattr(self._client, name)
        if not callable(value):
            return value

        def guarded(*args, **kwargs):
            self._dispatch.authorize_transport(
                self._target,
                url="https://query1.finance.yahoo.com/mock",
                method="GET",
            )
            return value(*args, **kwargs)

        return guarded


def _fund_spec() -> FundSpec:
    return FundSpec.model_validate(
        {
            "schema_version": 2,
            "name": "alpha",
            "strategies": [
                {
                    "name": "solo",
                    "models": [{"name": "pead"}],
                    "blend": {"mode": "long_short"},
                }
            ],
            "risk": {"max_position_pct": 1, "max_gross_exposure": 1},
            "capital": 100_000,
            "rebalance": "daily",
        }
    )


def _install_runner_records(root, fund, capture, last_session):
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(hours=1)
    nonce = "offline-runner-nonce-value-0123456789"
    nonce_hash = hashlib.sha256(nonce.encode("utf-8")).hexdigest()
    identity = current_process_identity()
    root.mkdir(f"{RUNNER_ROOT}/{runner_key(fund)}", parents=True, mode=0o700)
    authorization = {
        "initial_due_set": [_DUE_SESSION],
        "expires_at": expires_at.isoformat(),
        "max_sessions": 2,
        "max_calls": 100,
        "max_resources": 1000,
        "operation_id": "c" * 32,
        "operation_digest": "d" * 64,
    }
    write_runner_record(
        root,
        fund,
        "launch",
        {
            "schema": 1,
            "protocol_version": 1,
            "build_id": code_version(),
            "root": root_binding(root),
            "fund": fund,
            "nonce": nonce,
            "created_at": now.isoformat(),
            "capture": json.loads(capture.private_bytes().decode("utf-8")),
            "authorization": authorization,
        },
    )
    write_runner_record(
        root,
        fund,
        "state",
        {
            "schema": 1,
            "protocol_version": 1,
            "build_id": code_version(),
            "root": root_binding(root),
            "fund": fund,
            "nonce_hash": nonce_hash,
            "status": "starting",
            "created_at": now.isoformat(),
            "expires_at": expires_at.isoformat(),
            "max_sessions": 2,
            "sessions_completed": 0,
            "last_session": last_session,
            "reason": None,
            "pid": identity["pid"],
            "process_identity": identity,
        },
    )
    write_runner_record(
        root,
        fund,
        "control",
        {
            "schema": 1,
            "protocol_version": 1,
            "build_id": code_version(),
            "root": root_binding(root),
            "fund": fund,
            "nonce_hash": nonce_hash,
            "launch_ready": True,
            "stop_requested": False,
            "requested_at": None,
        },
    )
    return nonce_hash


@pytest.mark.parametrize("revocation", ["none", "legacy-runner", "exclusion-lost"])
def test_stop_during_inflight_session_finishes_once_then_stops(tmp_path, monkeypatch, revocation):
    root_path = tmp_path / "root"
    root_path.mkdir()
    data_client = _OfflineDataClient()
    spec = _fund_spec()

    with RootContext.open(root_path) as root:
        enroll_fresh(root)
        owner = RootOwnerLease.acquire(root)
        admission = AdmissionCoordinator(root, owner_lease=owner)
        worker = None
        try:
            with admission.deployment_lock("alpha", timeout=0):
                directory = deploy("alpha", spec, ["AAPL"], root=root_path / "paper")
            ledger = Ledger(directory)
            initial = SessionRecord(
                fund="alpha",
                session=_INITIAL_SESSION,
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
            initial.hash = initial.compute_hash()
            with admission.runner_reservation("alpha", timeout=0):
                with admission.execution_lease("alpha", timeout=0):
                    ledger.append(initial)
            record_ledger_head(root, "alpha", admission=admission)

            settings = resolve_settings(
                root,
                launch={
                    "data_provider": "yfinance",
                    "model": "gemma3:4b",
                    "endpoint": "http://127.0.0.1:11434",
                },
            )
            capture = freeze_capture(
                root=root,
                subject_id="alpha",
                mandate_digest=mandate_hash(spec),
                universe=("AAPL",),
                broker="paper",
                settings=settings,
                credential_versions={},
                code_version=code_version(),
                mandate_snapshot=spec.model_dump(mode="json"),
            )
            nonce_hash = _install_runner_records(
                root,
                "alpha",
                capture,
                _INITIAL_SESSION,
            )
            errors = []
            dispatches = []

            def data_client_factory(_capture, _root, dispatch):
                dispatches.append(dispatch)
                return _GuardedOfflineDataClient(data_client, dispatch)

            def execute():
                try:
                    run_owned_runner(
                        root,
                        "alpha",
                        data_client_factory=data_client_factory,
                        build_fund=_OfflineFund,
                        now=lambda: _RUNNER_NOW,
                        resolver=lambda _host, _port: ["93.184.216.34"],
                    )
                except Exception as exc:
                    errors.append(exc)

            worker = threading.Thread(target=execute)
            worker.start()
            assert data_client.started.wait(timeout=10)
            assert ledger.sessions() == [_INITIAL_SESSION]
            before_status = read_runner_record(root, "alpha", "state")
            before_calls = list(data_client.calls)
            provider_blocked = False
            if revocation != "none":
                if revocation == "legacy-runner":
                    (directory / "runner.pid").write_text("unverified", encoding="utf-8")
                else:
                    monkeypatch.delenv("HEDGE_FUND_TEST_MODE")
                try:
                    dispatches[0].authorize_transport(
                        ProviderTarget(kind="data", provider="yfinance"),
                        url="https://query1.finance.yahoo.com/mock",
                        method="GET",
                    )
                except AuthorizationDenied:
                    provider_blocked = True
            else:
                with admission.control_lane("alpha", timeout=0.2):
                    control = read_runner_record(root, "alpha", "control")
                    assert control["nonce_hash"] == nonce_hash
                    control["stop_requested"] = True
                    control["requested_at"] = datetime.now(timezone.utc).isoformat()
                    write_runner_record(root, "alpha", "control", control)

            data_client.release.set()
            worker.join(timeout=10)
            assert not worker.is_alive()
            final = read_runner_record(root, "alpha", "state")
            final_ledger = Ledger(directory)
            if revocation != "none":
                assert provider_blocked
                assert data_client.calls == before_calls
                assert len(errors) == 1 and isinstance(errors[0], OwnedRunnerError)
                assert final == before_status
                assert final_ledger.sessions() == [_INITIAL_SESSION]
                return

            assert errors == []
            assert final["status"] == "stopped"
            assert final["sessions_completed"] == 1
            assert final["last_session"] == _DUE_SESSION
            assert final_ledger.sessions() == [_INITIAL_SESSION, _DUE_SESSION]
            assert final_ledger.latest().session == _DUE_SESSION
        finally:
            data_client.release.set()
            if worker is not None:
                worker.join(timeout=10)
            owner.close()


@pytest.mark.parametrize("stage", ["runner-preflight", "tick-preflight"])
@pytest.mark.parametrize("outcome", ["complete", "stop", "expiry"])
def test_runner_retries_pre_effect_control_contention_without_spending_another_session(tmp_path, monkeypatch, stage, outcome):
    from hedge_fund.runtime import owned_runner_child

    root_path = tmp_path / "root"
    root_path.mkdir()
    data_client = _OfflineDataClient()
    data_client.release.set()
    spec = _fund_spec()
    gate = threading.Event()
    ready = threading.Event()
    retried = threading.Event()
    errors = []
    current_time = [_RUNNER_NOW]

    with RootContext.open(root_path) as root:
        enroll_fresh(root)
        owner = RootOwnerLease.acquire(root)
        admission = AdmissionCoordinator(root, owner_lease=owner)
        worker = None
        try:
            with admission.deployment_lock("alpha"):
                directory = deploy("alpha", spec, ["AAPL"], root=root_path / "paper")
            initial = SessionRecord(
                fund="alpha",
                session=_INITIAL_SESSION,
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
            initial.hash = initial.compute_hash()
            with admission.runner_reservation("alpha"):
                with admission.execution_lease("alpha"):
                    Ledger(directory).append(initial)
            settings = resolve_settings(
                root,
                launch={
                    "data_provider": "yfinance",
                    "model": "gemma3:4b",
                    "endpoint": "http://127.0.0.1:11434",
                },
            )
            capture = freeze_capture(
                root=root,
                subject_id="alpha",
                mandate_digest=mandate_hash(spec),
                universe=("AAPL",),
                broker="paper",
                settings=settings,
                credential_versions={},
                code_version=code_version(),
                mandate_snapshot=spec.model_dump(mode="json"),
            )
            _install_runner_records(root, "alpha", capture, _INITIAL_SESSION)
            launch = read_runner_record(root, "alpha", "launch")
            launch["authorization"]["max_sessions"] = 1
            write_runner_record(root, "alpha", "launch", launch)
            state = read_runner_record(root, "alpha", "state")
            state["max_sessions"] = 1
            write_runner_record(root, "alpha", "state", state)
            control_lane = AdmissionCoordinator.control_lane
            tick_once = owned_runner_child.tick
            control_attempts = 0
            tick_attempts = 0
            tick_requests = []

            def observed_control(current, identity, *, timeout=0.1):
                nonlocal control_attempts
                if threading.current_thread().name == "preflight-runner" and stage == "runner-preflight":
                    control_attempts += 1
                    if control_attempts > 1:
                        retried.set()
                return control_lane(current, identity, timeout=timeout)

            def observed_tick(*args, **kwargs):
                nonlocal tick_attempts
                tick_attempts += 1
                tick_requests.append(dict(kwargs))
                if stage == "tick-preflight":
                    if tick_attempts == 1:
                        ready.set()
                        if not gate.wait(timeout=10):
                            raise TimeoutError("test did not release tick")
                    else:
                        retried.set()
                return tick_once(*args, **kwargs)

            def execute():
                try:
                    run_owned_runner(
                        root,
                        "alpha",
                        data_client_factory=lambda _capture, _root, dispatch: _GuardedOfflineDataClient(data_client, dispatch),
                        build_fund=_OfflineFund,
                        now=lambda: current_time[0],
                        resolver=lambda _host, _port: ["93.184.216.34"],
                    )
                except Exception as exc:
                    errors.append(exc)

            def finish_if_stopped():
                if outcome == "stop":
                    control = read_runner_record(root, "alpha", "control")
                    control["stop_requested"] = True
                    control["requested_at"] = datetime.now(timezone.utc).isoformat()
                    write_runner_record(root, "alpha", "control", control)
                elif outcome == "expiry":
                    current_time[0] = datetime.fromisoformat(launch["authorization"]["expires_at"]) + timedelta(seconds=1)
                if outcome != "complete":
                    worker.join(timeout=10)
                    assert not worker.is_alive()
                    assert not data_client.started.is_set()

            monkeypatch.setattr(AdmissionCoordinator, "control_lane", observed_control)
            monkeypatch.setattr(owned_runner_child, "tick", observed_tick)
            worker = threading.Thread(target=execute, name="preflight-runner")
            if stage == "runner-preflight":
                with control_lane(admission, "alpha"):
                    worker.start()
                    assert retried.wait(timeout=3), read_runner_record(root, "alpha", "state")
                    assert not data_client.started.is_set()
                    finish_if_stopped()
            else:
                worker.start()
                assert ready.wait(timeout=10)
                with control_lane(admission, "alpha"):
                    gate.set()
                    assert retried.wait(timeout=3), read_runner_record(root, "alpha", "state")
                    assert not data_client.started.is_set()
                    finish_if_stopped()
            worker.join(timeout=15)
            assert not worker.is_alive()
            assert errors == []
            final = read_runner_record(root, "alpha", "state")
            if outcome == "complete":
                assert final["status"] == "completed"
                assert final["sessions_completed"] == 1
                assert final["last_session"] == _DUE_SESSION
                assert Ledger(directory).sessions() == [_INITIAL_SESSION, _DUE_SESSION]
                request = tick_requests[0]
                operation_id = launch["authorization"]["operation_id"]
                assert request["expected_head"] == initial.hash
                assert request["operation_id"] == operation_id
                assert request["request_id"] == f"runner:{operation_id}:{_DUE_SESSION}"
                assert request["capture_id"] == capture.capture_id
                assert request["capture_digest"] == capture.digest
            else:
                assert final["status"] == ("stopped" if outcome == "stop" else "completed")
                assert final["reason"] == ("stop-requested" if outcome == "stop" else "expiry-reached")
                assert final["sessions_completed"] == 0
                assert Ledger(directory).sessions() == [_INITIAL_SESSION]
        finally:
            gate.set()
            if worker is not None:
                worker.join(timeout=15)
            owner.close()


@pytest.mark.parametrize(
    "stage",
    ["bootstrap-inventory", "runner-inventory", "runner-audit", "session-inventory", "tick-audit"],
)
@pytest.mark.parametrize("outcome", ["complete", "stop", "expiry"])
def test_runner_retries_pre_effect_observation_contention(tmp_path, monkeypatch, stage, outcome):
    from hedge_fund.runtime import admission as admission_module
    from hedge_fund.runtime import handover, owned_runner_child

    root_path = tmp_path / "root"
    root_path.mkdir()
    data_client = _OfflineDataClient()
    data_client.release.set()
    spec = _fund_spec()
    ready = threading.Event()
    gate = threading.Event()
    retried = threading.Event()
    errors = []
    current_time = [_RUNNER_NOW]
    attempts = 0
    session_active = False

    def observe_attempt():
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            ready.set()
            if not gate.wait(timeout=10):
                raise TimeoutError("test did not release the observation")
        else:
            retried.set()

    with RootContext.open(root_path) as root:
        enroll_fresh(root)
        owner = RootOwnerLease.acquire(root)
        admission = AdmissionCoordinator(root, owner_lease=owner)
        worker = None
        try:
            with admission.deployment_lock("alpha"):
                directory = deploy("alpha", spec, ["AAPL"], root=root_path / "paper")
            initial = SessionRecord(
                fund="alpha",
                session=_INITIAL_SESSION,
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
            initial.hash = initial.compute_hash()
            with admission.runner_reservation("alpha"):
                with admission.execution_lease("alpha"):
                    Ledger(directory).append(initial)
            settings = resolve_settings(
                root,
                launch={
                    "data_provider": "yfinance",
                    "model": "gemma3:4b",
                    "endpoint": "http://127.0.0.1:11434",
                },
            )
            capture = freeze_capture(
                root=root,
                subject_id="alpha",
                mandate_digest=mandate_hash(spec),
                universe=("AAPL",),
                broker="paper",
                settings=settings,
                credential_versions={},
                code_version=code_version(),
                mandate_snapshot=spec.model_dump(mode="json"),
            )
            _install_runner_records(root, "alpha", capture, _INITIAL_SESSION)
            launch = read_runner_record(root, "alpha", "launch")
            launch["authorization"]["max_sessions"] = 1
            write_runner_record(root, "alpha", "launch", launch)
            state = read_runner_record(root, "alpha", "state")
            state["max_sessions"] = 1
            write_runner_record(root, "alpha", "state", state)
            verify_inventory = owned_runner_child.verify_root_inventory
            verify_head = owned_runner_child.verify_ledger_head
            require_ready = Ledger.require_ready_for_work
            execute_session = owned_runner_child._execute_session
            tick_once = owned_runner_child.tick

            def observed_inventory(*args, **kwargs):
                if stage == "bootstrap-inventory":
                    observe_attempt()
                return verify_inventory(*args, **kwargs)

            def observed_head(*args, **kwargs):
                if stage == "runner-inventory" and not session_active:
                    observe_attempt()
                elif stage == "session-inventory" and session_active:
                    observe_attempt()
                return verify_head(*args, **kwargs)

            def observed_ready(self, *args, **kwargs):
                if stage == "runner-audit" and threading.current_thread().name == "observation-runner":
                    observe_attempt()
                return require_ready(self, *args, **kwargs)

            def observed_execute(*args, **kwargs):
                nonlocal session_active
                session_active = True
                try:
                    return execute_session(*args, **kwargs)
                finally:
                    session_active = False

            def observed_tick(*args, **kwargs):
                if stage == "tick-audit":
                    observe_attempt()
                return tick_once(*args, **kwargs)

            def execute():
                try:
                    run_owned_runner(
                        root,
                        "alpha",
                        data_client_factory=lambda _capture, _root, dispatch: _GuardedOfflineDataClient(data_client, dispatch),
                        build_fund=_OfflineFund,
                        now=lambda: current_time[0],
                        resolver=lambda _host, _port: ["93.184.216.34"],
                    )
                except Exception as exc:
                    errors.append(exc)

            monkeypatch.setattr(owned_runner_child, "verify_root_inventory", observed_inventory)
            monkeypatch.setattr(owned_runner_child, "verify_ledger_head", observed_head)
            monkeypatch.setattr(Ledger, "require_ready_for_work", observed_ready)
            monkeypatch.setattr(owned_runner_child, "_execute_session", observed_execute)
            monkeypatch.setattr(owned_runner_child, "tick", observed_tick)
            monkeypatch.setattr(handover, "MAX_LOCK_WAIT_SECONDS", 0.1)
            monkeypatch.setattr(admission_module, "MAX_CONTROL_WAIT_SECONDS", 0.1)
            worker = threading.Thread(target=execute, name="observation-runner")
            worker.start()
            assert ready.wait(timeout=10), (errors, read_runner_record(root, "alpha", "state"))
            held_lane = admission.audit_lane("alpha", timeout=0.1) if stage.endswith("audit") else admission.registry_lock()
            with held_lane:
                gate.set()
                if not retried.wait(timeout=3):
                    current = read_runner_record(root, "alpha", "state")
                    pytest.fail(f"observation did not retry: {errors}, {current['status']}, {current['reason']}")
                if outcome == "stop":
                    control = read_runner_record(root, "alpha", "control")
                    control["stop_requested"] = True
                    control["requested_at"] = datetime.now(timezone.utc).isoformat()
                    write_runner_record(root, "alpha", "control", control)
                elif outcome == "expiry":
                    current_time[0] = datetime.fromisoformat(launch["authorization"]["expires_at"]) + timedelta(seconds=1)
                if outcome != "complete":
                    worker.join(timeout=10)
                    assert not worker.is_alive()
                    assert not data_client.started.is_set()
            worker.join(timeout=15)
            assert not worker.is_alive()
            assert errors == []
            final = read_runner_record(root, "alpha", "state")
            if outcome == "complete":
                assert final["status"] == "completed"
                assert final["sessions_completed"] == 1
                assert Ledger(directory).sessions() == [_INITIAL_SESSION, _DUE_SESSION]
            else:
                assert final["status"] == ("stopped" if outcome == "stop" else "completed")
                assert final["reason"] == ("stop-requested" if outcome == "stop" else "expiry-reached")
                assert final["sessions_completed"] == 0
                assert Ledger(directory).sessions() == [_INITIAL_SESSION]
        finally:
            gate.set()
            if worker is not None:
                worker.join(timeout=15)
            owner.close()


def test_runner_interrupted_redo_fails_before_provider(tmp_path):
    root_path = tmp_path / "root"
    root_path.mkdir()
    spec = _fund_spec()
    calls = []

    with RootContext.open(root_path) as root:
        enroll_fresh(root)
        owner = RootOwnerLease.acquire(root)
        admission = AdmissionCoordinator(root, owner_lease=owner)
        try:
            with admission.deployment_lock("alpha", timeout=0):
                directory = deploy("alpha", spec, ["AAPL"], root=root_path / "paper")
            ledger = Ledger(directory)
            initial = SessionRecord(
                fund="alpha",
                session=_INITIAL_SESSION,
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
            initial.hash = initial.compute_hash()
            with admission.manual_session("alpha", timeout=0):
                ledger.append(initial)
                ledger.begin_redo(initial)
            settings = resolve_settings(
                root,
                launch={
                    "data_provider": "yfinance",
                    "model": "gemma3:4b",
                    "endpoint": "http://127.0.0.1:11434",
                },
            )
            capture = freeze_capture(
                root=root,
                subject_id="alpha",
                mandate_digest=mandate_hash(spec),
                universe=("AAPL",),
                broker="paper",
                settings=settings,
                credential_versions={},
                code_version=code_version(),
                mandate_snapshot=spec.model_dump(mode="json"),
            )
            _install_runner_records(root, "alpha", capture, _INITIAL_SESSION)

            def forbidden_factory(*_args):
                calls.append("provider")
                raise AssertionError("interrupted redo reached a data provider")

            run_owned_runner(
                root,
                "alpha",
                data_client_factory=forbidden_factory,
                build_fund=_OfflineFund,
                now=lambda: _RUNNER_NOW,
                resolver=lambda _host, _port: ["93.184.216.34"],
            )
            final = read_runner_record(root, "alpha", "state")
            assert final["status"] == "failed"
            assert final["reason"] == "runner-PaperReconciliationRequired"
            assert calls == []
            assert ledger.sessions() == [_INITIAL_SESSION]
        finally:
            owner.close()


def test_runner_orphaned_tick_intent_is_blocked_without_halt(tmp_path):
    from hedge_fund.paper.ledger import UnresolvedTickIntentRefusal

    root_path = tmp_path / "root"
    root_path.mkdir()
    data_client = _OfflineDataClient()
    data_client.release.set()
    spec = _fund_spec()

    with RootContext.open(root_path) as root:
        enroll_fresh(root)
        owner = RootOwnerLease.acquire(root)
        admission = AdmissionCoordinator(root, owner_lease=owner)
        try:
            with admission.deployment_lock("alpha", timeout=0):
                directory = deploy("alpha", spec, ["AAPL"], root=root_path / "paper")
            ledger = Ledger(directory)
            initial = SessionRecord(
                fund="alpha",
                session=_INITIAL_SESSION,
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
            initial.hash = initial.compute_hash()
            request_id = "runner-orphaned-tick"
            request_digest = ledger.tick_request_digest(
                request_id,
                expected_head=initial.hash,
                session=_DUE_SESSION,
            )
            with admission.manual_session("alpha", timeout=0):
                ledger.append(initial)
                ledger.log_event(
                    "tick_intent",
                    request_id=request_id,
                    request_action="tick",
                    request_digest=request_digest,
                    expected_head=initial.hash,
                    requested_session=_DUE_SESSION,
                    session=_DUE_SESSION,
                    durable=True,
                )
            settings = resolve_settings(
                root,
                launch={
                    "data_provider": "yfinance",
                    "model": "gemma3:4b",
                    "endpoint": "http://127.0.0.1:11434",
                },
            )
            capture = freeze_capture(
                root=root,
                subject_id="alpha",
                mandate_digest=mandate_hash(spec),
                universe=("AAPL",),
                broker="paper",
                settings=settings,
                credential_versions={},
                code_version=code_version(),
                mandate_snapshot=spec.model_dump(mode="json"),
            )
            _install_runner_records(root, "alpha", capture, _INITIAL_SESSION)

            with pytest.raises(UnresolvedTickIntentRefusal) as refused:
                run_owned_runner(
                    root,
                    "alpha",
                    data_client_factory=lambda _capture, _root, dispatch: _GuardedOfflineDataClient(data_client, dispatch),
                    build_fund=_OfflineFund,
                    now=lambda: _RUNNER_NOW,
                    resolver=lambda _host, _port: ["93.184.216.34"],
                )

            final = read_runner_record(root, "alpha", "state")
            assert final["status"] == "blocked"
            assert final["reason"] == "unresolved-tick-intent"
            assert final["refusal"] == refused.value.fields
            assert ledger.halted() is None
            assert ledger.sessions() == [_INITIAL_SESSION]
            assert len(ledger.unresolved_tick_intents()) == 1
        finally:
            owner.close()


def test_runner_duplicate_logical_refusal_is_persisted_as_blocked(tmp_path, monkeypatch):
    from hedge_fund.brokers.account_binding import runner_quiescence, RunnerQuiescence
    from hedge_fund.runtime import owned_runner_child
    from hedge_fund.runtime.operations import DuplicateLogicalOperationRefusal
    from hedge_fund.runtime.owned_runner import validate_runner_state

    root_path = tmp_path / "root"
    root_path.mkdir()
    data_client = _OfflineDataClient()
    data_client.release.set()
    spec = _fund_spec()
    refusal = DuplicateLogicalOperationRefusal("a" * 32, "b" * 64)

    def refuse_tick(*_args, **_kwargs):
        raise refusal

    monkeypatch.setattr(owned_runner_child, "tick", refuse_tick)
    with RootContext.open(root_path) as root:
        enroll_fresh(root)
        owner = RootOwnerLease.acquire(root)
        admission = AdmissionCoordinator(root, owner_lease=owner)
        try:
            with admission.deployment_lock("alpha"):
                directory = deploy("alpha", spec, ["AAPL"], root=root_path / "paper")
            initial = SessionRecord(
                fund="alpha",
                session=_INITIAL_SESSION,
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
            initial.hash = initial.compute_hash()
            with admission.runner_reservation("alpha"):
                with admission.execution_lease("alpha"):
                    Ledger(directory).append(initial)
            settings = resolve_settings(
                root,
                launch={
                    "data_provider": "yfinance",
                    "model": "gemma3:4b",
                    "endpoint": "http://127.0.0.1:11434",
                },
            )
            capture = freeze_capture(
                root=root,
                subject_id="alpha",
                mandate_digest=mandate_hash(spec),
                universe=("AAPL",),
                broker="paper",
                settings=settings,
                credential_versions={},
                code_version=code_version(),
                mandate_snapshot=spec.model_dump(mode="json"),
            )
            _install_runner_records(root, "alpha", capture, _INITIAL_SESSION)

            with pytest.raises(DuplicateLogicalOperationRefusal) as raised:
                run_owned_runner(
                    root,
                    "alpha",
                    data_client_factory=lambda _capture, _root, dispatch: _GuardedOfflineDataClient(data_client, dispatch),
                    build_fund=_OfflineFund,
                    now=lambda: _RUNNER_NOW,
                    resolver=lambda _host, _port: ["93.184.216.34"],
                )

            final = read_runner_record(root, "alpha", "state")
            assert raised.value.fields == refusal.fields
            assert final["status"] == "blocked"
            assert final["reason"] == "duplicate-logical-operation"
            assert final["refusal"] == refusal.fields
            assert validate_runner_state(root, "alpha", final)
            assert runner_quiescence(root, "alpha") == RunnerQuiescence(True, "blocked")
            assert Ledger(directory).sessions() == [_INITIAL_SESSION]
        finally:
            owner.close()


@pytest.mark.parametrize("journal_state", ["unfinished", "malformed"])
def test_runner_unfinished_consumption_halts_before_provider(tmp_path, journal_state):
    from hedge_fund.pipeline.models import DecisionRecord
    from hedge_fund.runtime.admission import paper_approval_transition

    root_path = tmp_path / "root"
    root_path.mkdir()
    spec = _fund_spec().model_copy(update={"approval_required": True})
    calls = []

    with RootContext.open(root_path) as root:
        enroll_fresh(root)
        owner = RootOwnerLease.acquire(root)
        admission = AdmissionCoordinator(root, owner_lease=owner)
        try:
            with admission.deployment_lock("alpha", timeout=0):
                directory = deploy("alpha", spec, ["AAPL"], root=root_path / "paper")
            ledger = Ledger(directory)
            decision = DecisionRecord(
                fund="alpha",
                as_of=_INITIAL_SESSION,
                spec=spec,
                universe=["AAPL"],
                marks={"AAPL": 100.0},
                skipped=[],
                strategies=[],
                target_weights={},
                clamps=[],
                final_weights={},
            )
            initial = SessionRecord(
                fund="alpha",
                session=_INITIAL_SESSION,
                universe=["AAPL"],
                nav=spec.capital,
                cash=spec.capital,
                positions={},
                marks={},
                benchmark=spec.benchmark,
                benchmark_close=100.0,
                rebalance=True,
                decision=decision,
                code_version=code_version(),
                mandate_hash=mandate_hash(spec),
            )
            initial.hash = initial.compute_hash()
            with admission.manual_session("alpha", timeout=0):
                ledger.append(initial)
            with paper_approval_transition(admission, "alpha") as proof:
                approval = ledger.set_approval("approve", decision.as_of, initial.hash, "cli", admission=proof)
            with admission.control_lane("alpha"):
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
                        session=_DUE_SESSION,
                        durable=True,
                    )
            settings = resolve_settings(
                root,
                launch={
                    "data_provider": "yfinance",
                    "model": "gemma3:4b",
                    "endpoint": "http://127.0.0.1:11434",
                },
            )
            capture = freeze_capture(
                root=root,
                subject_id="alpha",
                mandate_digest=mandate_hash(spec),
                universe=("AAPL",),
                broker="paper",
                settings=settings,
                credential_versions={},
                code_version=code_version(),
                mandate_snapshot=spec.model_dump(mode="json"),
            )
            _install_runner_records(root, "alpha", capture, _INITIAL_SESSION)

            def forbidden_factory(*_args):
                calls.append("provider")
                raise AssertionError("unfinished consumption reached a data provider")

            run_owned_runner(
                root,
                "alpha",
                data_client_factory=forbidden_factory,
                build_fund=_OfflineFund,
                now=lambda: _RUNNER_NOW,
                resolver=lambda _host, _port: ["93.184.216.34"],
            )
            final = read_runner_record(root, "alpha", "state")
            assert final["status"] == "failed"
            assert final["reason"] == "runner-PaperReconciliationRequired"
            assert calls == []
            assert ledger.halted() == "approval journal requires reconciliation"
        finally:
            owner.close()
