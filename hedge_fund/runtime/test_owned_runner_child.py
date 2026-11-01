import hashlib
import json
import threading
from datetime import datetime, timedelta, timezone

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
    read_runner_record,
    runner_key,
    RUNNER_ROOT,
    write_runner_record,
)
from hedge_fund.runtime.owned_runner_child import run_owned_runner
from hedge_fund.runtime.ownership import current_process_identity
from hedge_fund.runtime.policy import ProviderTarget
from hedge_fund.runtime.root import RootContext

_INITIAL_SESSION = "2024-06-07"
_DUE_SESSION = "2024-06-10"
_RUNNER_NOW = datetime(2024, 6, 11, 20, tzinfo=timezone.utc)


class _OfflineDataClient:
    def __init__(self):
        self.started = threading.Event()
        self.release = threading.Event()
        self._blocked = False

    def __enter__(self):
        return self

    def __exit__(self, *_exc_info):
        return None

    def get_prices(self, ticker, start_date, end_date, **_kwargs):
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


def test_stop_during_inflight_session_finishes_once_then_stops(tmp_path):
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

            def execute():
                try:
                    run_owned_runner(
                        root,
                        "alpha",
                        data_client_factory=lambda _capture, _root, dispatch: _GuardedOfflineDataClient(
                            data_client,
                            dispatch,
                        ),
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

            with admission.control_lane("alpha", timeout=0.2):
                control = read_runner_record(root, "alpha", "control")
                assert control["nonce_hash"] == nonce_hash
                control["stop_requested"] = True
                control["requested_at"] = datetime.now(timezone.utc).isoformat()
                write_runner_record(root, "alpha", "control", control)

            data_client.release.set()
            worker.join(timeout=10)
            assert not worker.is_alive()
            assert errors == []

            final = read_runner_record(root, "alpha", "state")
            final_ledger = Ledger(directory)
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
