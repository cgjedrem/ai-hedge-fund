"""Spec005 T027 cross-process paper writer races.

Real child interpreters compete for the same synthetic, test-owned paper fund
through the production admission lanes and ``Ledger`` writers used by the
CLI, web services and runner (``manual_session`` + ``Ledger.append``), redo
(``Ledger.rewind``) and lifecycle/archive (``deployment_lock``). Outcomes are
decided by OS locks and file handshakes, never by sleeps. No provider, LLM or
real fund is touched.
"""

from __future__ import annotations

import os
import threading
import time
from contextlib import contextmanager, nullcontext
from pathlib import Path

import pytest

from hedge_fund import paths
from hedge_fund.fund import FundSpec
from hedge_fund.paper.deployed import deploy
from hedge_fund.paper.ledger import Ledger, LedgerError
from hedge_fund.pipeline.session import code_version, mandate_hash, SessionRecord
from hedge_fund.runtime.admission import (
    AdmissionCoordinator,
    MAX_CONTROL_WAIT_SECONDS,
    OwnershipUnknown,
    RootOwnerLease,
    WriterConflict,
)
from hedge_fund.runtime.handover import enroll_fresh, write_authority
from hedge_fund.runtime.root import RootContext

FUNDS = ("alpha", "beta")


def _spec(name: str) -> FundSpec:
    return FundSpec.model_validate(
        {
            "schema_version": 2,
            "name": name,
            "strategies": [{"name": "solo", "models": [{"name": "pead"}], "blend": {"mode": "long_short"}}],
            "risk": {"max_position_pct": 1, "max_gross_exposure": 1},
            "capital": 100_000,
            "rebalance": "daily",
        }
    )


def _record(name: str, session: str = "2024-06-07", prev_hash: str | None = None) -> SessionRecord:
    spec = _spec(name)
    record = SessionRecord(
        fund=name,
        session=session,
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
        prev_hash=prev_hash,
    )
    record.hash = record.compute_hash()
    return record


@pytest.fixture
def race_root(tmp_path):
    root_path = tmp_path / "root"
    root_path.mkdir()
    with RootContext.open(root_path) as root:
        enroll_fresh(root)
        with RootOwnerLease.acquire(root) as owner:
            admission = AdmissionCoordinator(root, owner_lease=owner)
            for name in FUNDS:
                with admission.deployment_lock(name):
                    deploy(name, _spec(name), ["AAPL"], root=root_path / "paper")
            with paths.bound_root(root):
                yield root_path, admission


_MANUAL_WRITER = """
import sys, time
from pathlib import Path
from hedge_fund import paths
from hedge_fund.paper.ledger import Ledger, LedgerError
from hedge_fund.pipeline.session import SessionRecord
from hedge_fund.runtime.admission import AdmissionCoordinator, RootOwnerLease, WriterConflict
from hedge_fund.runtime.root import RootContext

root_path, fund, record_file = Path(ROOT), FUND, Path(RECORD)
ready, go, status, release, final = Path(READY), Path(GO), Path(STATUS), Path(RELEASE), Path(FINAL)
record = SessionRecord.model_validate_json(record_file.read_text(encoding="utf-8"))


def wait_for(path):
    deadline = time.monotonic() + 60
    while not path.exists():
        if time.monotonic() > deadline:
            sys.exit(3)
        time.sleep(0.01)

def write_signal(path, value):
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(value, encoding="utf-8")
    temporary.replace(path)


with RootContext.open(root_path) as root:
    with RootOwnerLease.acquire(root, timeout=5) as owner, paths.bound_root(root):
        coordinator = AdmissionCoordinator(root, owner_lease=owner)
        ledger = Ledger(root_path / "paper" / fund)
        write_signal(ready, "ready")
        wait_for(go)
        try:
            with coordinator.manual_session(fund, timeout=0):
                write_signal(status, "admitted")
                wait_for(release)
                try:
                    ledger.append(record)
                    result = "appended"
                except LedgerError:
                    result = "ledger-error"
        except WriterConflict:
            write_signal(status, "conflict")
            result = "conflict"
        write_signal(final, result)
sys.exit(0)
"""

_RESEARCH_HOLDER = """
import sys, time
from pathlib import Path
from hedge_fund.runtime.admission import AdmissionCoordinator, RootOwnerLease
from hedge_fund.runtime.root import RootContext

root_path, identity, ready, release = Path(ROOT), IDENTITY, Path(READY), Path(RELEASE)
with RootContext.open(root_path) as root:
    with RootOwnerLease.acquire(root, timeout=5) as owner:
        coordinator = AdmissionCoordinator(root, owner_lease=owner)
        with coordinator.research_lane(identity, timeout=0):
            ready.write_text("held", encoding="utf-8")
            deadline = time.monotonic() + 60
            while not release.exists() and time.monotonic() < deadline:
                time.sleep(0.01)
sys.exit(0 if release.exists() else 3)
"""

_AUDIT_APPENDER = """
import sys, time
from pathlib import Path
from hedge_fund import paths
from hedge_fund.paper.ledger import Ledger
from hedge_fund.runtime.admission import AdmissionCoordinator, RootOwnerLease, WriterConflict
from hedge_fund.runtime.root import RootContext

root_path, fund, writer = Path(ROOT), FUND, WRITER
ready, go, final, error = Path(READY), Path(GO), Path(FINAL), Path(ERROR)
count, payload = int(COUNT), PAYLOAD

def publish(path, value):
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(value, encoding="utf-8")
    temporary.replace(path)

try:
    with RootContext.open(root_path) as root:
        with RootOwnerLease.acquire(root, timeout=5) as owner, paths.bound_root(root):
            coordinator = AdmissionCoordinator(root, owner_lease=owner)
            ledger = Ledger(root_path / "paper" / fund)
            publish(ready, "ready")
            deadline = time.monotonic() + 60
            while not go.exists():
                if time.monotonic() > deadline:
                    sys.exit(3)
                time.sleep(0.01)
            for sequence in range(count):
                deadline = time.monotonic() + 30
                while True:
                    try:
                        with coordinator.control_lane(fund, timeout=0.5):
                            ledger.log_event("cross-process-audit", writer=writer, sequence=sequence, payload=payload)
                        break
                    except WriterConflict:
                        if time.monotonic() >= deadline:
                            raise
                        time.sleep(0.01)
            publish(final, "done")
except BaseException as exc:
    publish(error, f"{type(exc).__name__}: {exc}")
    raise
sys.exit(0)
"""

_LOGICAL_OPERATION_SUBMITTER = """
import json, sys, time
from datetime import datetime
from pathlib import Path
from hedge_fund import paths
from hedge_fund.brokers.models import Order
from hedge_fund.brokers.paper import PaperBroker
from hedge_fund.paper.ledger import Ledger
from hedge_fund.runtime.admission import AdmissionCoordinator, RootOwnerLease
from hedge_fund.runtime.operations import DuplicateLogicalOperationRefusal, OperationStore
from hedge_fund.runtime.root import RootContext

final_path = Path(FINAL)
try:
    root_path, request_path, ready_path, go_path, decision_path, fill_go_path = (
        Path(ROOT),
        Path(REQUEST),
        Path(READY),
        Path(GO),
        Path(DECISION),
        Path(FILL_GO),
    )
    request = json.loads(request_path.read_text(encoding="utf-8"))
    now = datetime.fromisoformat(request["now"])

    def wait_for(path):
        deadline = time.monotonic() + 60
        while not path.exists():
            if time.monotonic() > deadline:
                raise TimeoutError("logical-operation start signal missing")
            time.sleep(0.01)

    with RootContext.open(root_path) as root, RootOwnerLease.acquire(root) as owner:
        admission = AdmissionCoordinator(root, owner_lease=owner)
        store = OperationStore(root, admission=admission)
        ready_path.write_text("ready", encoding="utf-8")
        wait_for(go_path)

        def execute_fake_fill(operation):
            decision_path.write_text("accepted", encoding="utf-8")
            wait_for(fill_go_path)
            with paths.bound_root(root):
                with admission.runner_reservation("alpha", timeout=5):
                    with admission.execution_lease("alpha", timeout=5):
                        broker = PaperBroker(root_path / "paper" / "alpha" / "broker.json")
                        fill = broker.place_order(Order(ticker="AAPL", side="buy", quantity=1, price=100))
                        Ledger(root_path / "paper" / "alpha").log_event(
                            "logical-duplicate-fake-fill",
                            operation_id=operation.operation_id,
                            ticker=fill.ticker,
                            side=fill.side,
                            quantity=fill.quantity,
                            price=fill.price,
                            durable=True,
                        )

        try:
            operation = store.accept_request(
                request_id=request["request_id"],
                action=request["action"],
                subject_id=request["subject_id"],
                preview_id=request["preview_id"],
                preview_digest=request["preview_digest"],
                confirmation_token=request["confirmation_token"],
                operator_session=request["operator_session"],
                expected_head=request["expected_head"],
                due_set=tuple(request["due_set"]),
                payload=request["payload"],
                now=now,
                start_worker=execute_fake_fill,
            )
            outcome = {"outcome": "accepted", "operation_id": operation.operation_id}
        except DuplicateLogicalOperationRefusal as exc:
            decision_path.write_text("duplicate", encoding="utf-8")
            outcome = {"outcome": "duplicate", "refusal": exc.fields}

    final_path.write_text(json.dumps(outcome, sort_keys=True), encoding="utf-8")
except BaseException as exc:
    final_path.write_text(
        json.dumps(
            {
                "outcome": "error",
                "error": f"{type(exc).__name__}: {exc}",
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    raise
"""


def _render(template: str, **values: str) -> str:
    for key, value in values.items():
        template = template.replace(key, repr(value))
    return template


def _wait_file(path: Path, process, what: str, timeout: float = 30) -> str:
    deadline = time.monotonic() + timeout
    last_error = None
    while time.monotonic() < deadline:
        try:
            value = path.read_text(encoding="utf-8")
            if value:
                return value
        except (FileNotFoundError, PermissionError) as exc:
            last_error = exc
        if process is not None and process.poll() is not None:
            if path.exists():
                raise AssertionError(f"{what} exited without a complete report: {process.returncode}") from last_error
            raise AssertionError(f"{what} exited early: {process.returncode}") from last_error
        time.sleep(0.01)
    detail = f"{what} did not report"
    if last_error is not None:
        detail += f"; last read failed: {type(last_error).__name__}"
    raise AssertionError(detail) from last_error


def test_logical_wait_file_retries_empty_handshake():
    class EmptyThenReady:
        def __init__(self):
            self.reads = 0

        def read_text(self, encoding):
            self.reads += 1
            return "" if self.reads == 1 else "ready"

    handshake = EmptyThenReady()

    assert _wait_file(handshake, None, "logical start signal", timeout=1) == "ready"
    assert handshake.reads == 2


class _Racer:
    def __init__(self, owned_test_process, workdir: Path, root: Path, fund: str, record: SessionRecord, go: Path, release: Path, tag: str):
        self.workdir = workdir
        record_file = workdir / f"record-{tag}.json"
        record_file.write_text(record.model_dump_json(), encoding="utf-8")
        self.ready = workdir / f"ready-{tag}"
        self.status = workdir / f"status-{tag}"
        self.final = workdir / f"final-{tag}"
        script = _render(
            _MANUAL_WRITER,
            ROOT=str(root),
            FUND=fund,
            RECORD=str(record_file),
            READY=str(self.ready),
            GO=str(go),
            STATUS=str(self.status),
            RELEASE=str(release),
            FINAL=str(self.final),
        )
        self.process = owned_test_process(script)
        self.tag = tag

    def wait_ready(self) -> None:
        _wait_file(self.ready, self.process, f"racer {self.tag}")

    def wait_status(self) -> str:
        return _wait_file(self.status, self.process, f"racer {self.tag} status")

    def wait_final(self) -> str:
        result = _wait_file(self.final, self.process, f"racer {self.tag} result")
        assert self.process.wait(timeout=15) == 0
        return result


def _start_racers(owned_test_process, workdir: Path, root: Path, fund: str, record: SessionRecord, count: int, *, release: Path, prefix: str) -> list[_Racer]:
    go = workdir / f"go-{prefix}"
    racers = [_Racer(owned_test_process, workdir, root, fund, record, go, release, f"{prefix}-{index}") for index in range(count)]
    for racer in racers:
        racer.wait_ready()
    go.write_text("go", encoding="utf-8")
    return racers


@contextmanager
def _session_held_by_child(owned_test_process, workdir: Path, root: Path, fund: str, record: SessionRecord, tag: str):
    release = workdir / f"release-{tag}"
    (racer,) = _start_racers(owned_test_process, workdir, root, fund, record, 1, release=release, prefix=tag)
    assert racer.wait_status() == "admitted"
    yield racer, release


@contextmanager
def _research_held_by_child(owned_test_process, workdir: Path, root: Path, identity: str):
    ready = workdir / f"research-ready-{identity}"
    release = workdir / f"research-release-{identity}"
    process = owned_test_process(_render(_RESEARCH_HOLDER, ROOT=str(root), IDENTITY=identity, READY=str(ready), RELEASE=str(release)))
    try:
        _wait_file(ready, process, f"research holder {identity}")
        yield
    finally:
        release.write_text("release", encoding="utf-8")
        assert process.wait(timeout=15) == 0


def _recorded(root: Path, fund: str) -> list[str]:
    return Ledger(root / "paper" / fund).sessions()


def _recorded_fills(root: Path, fund: str) -> list[dict]:
    records = Ledger(root / "paper" / fund).records()
    return [fill.model_dump(mode="json") for record in records if record.executed is not None for fill in record.executed.fills]


def _paper_files(root: Path, fund: str) -> dict[str, bytes]:
    directory = root / "paper" / fund
    return {str(path.relative_to(directory)): path.read_bytes() for path in directory.rglob("*") if path.is_file()}


def test_owned_runner_intent_refusal_is_durable_and_not_retried(tmp_path, monkeypatch):
    from hedge_fund.paper.ledger import UnresolvedTickIntentRefusal
    from hedge_fund.runtime.capture import freeze_capture
    from hedge_fund.runtime.configuration import resolve_settings
    from hedge_fund.runtime.handover import record_ledger_head
    from hedge_fund.runtime.owned_runner import (
        read_runner_record,
        validate_runner_state,
        write_runner_record,
    )
    from hedge_fund.runtime.owned_runner_child import run_owned_runner
    from hedge_fund.runtime.test_owned_runner_child import (
        _DUE_SESSION,
        _fund_spec,
        _GuardedOfflineDataClient,
        _INITIAL_SESSION,
        _install_runner_records,
        _OfflineDataClient,
        _OfflineFund,
        _RUNNER_NOW,
    )

    root_path = tmp_path / "owned-runner-root"
    root_path.mkdir()
    spec = _fund_spec()
    data_client = _OfflineDataClient()
    data_client.release.set()
    with RootContext.open(root_path) as root:
        enroll_fresh(root)
        with RootOwnerLease.acquire(root) as owner:
            admission = AdmissionCoordinator(root, owner_lease=owner)
            with admission.deployment_lock("alpha", timeout=0):
                directory = deploy("alpha", spec, ["AAPL"], root=root_path / "paper")
            initial = _record("alpha", _INITIAL_SESSION)
            ledger = Ledger(directory)
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
            _install_runner_records(root, "alpha", capture, _INITIAL_SESSION)
            launch = read_runner_record(root, "alpha", "launch")
            launch["authorization"]["max_sessions"] = 1
            write_runner_record(root, "alpha", "launch", launch)
            state = read_runner_record(root, "alpha", "state")
            state["max_sessions"] = 1
            write_runner_record(root, "alpha", "state", state)
            interrupted_id = "interrupted-runner-tick"
            interrupted_digest = ledger.tick_request_digest(
                interrupted_id,
                expected_head=initial.hash,
                session=_DUE_SESSION,
            )
            with admission.runner_reservation("alpha", timeout=0):
                with admission.execution_lease("alpha", timeout=0):
                    ledger.log_event(
                        "tick_intent",
                        request_id=interrupted_id,
                        request_action="tick",
                        request_digest=interrupted_digest,
                        expected_head=initial.hash,
                        requested_session=_DUE_SESSION,
                        session=_DUE_SESSION,
                        durable=True,
                    )
            events_before = ledger.events()
            broker_before = (directory / "broker.json").read_bytes()
            import hedge_fund.runtime.owned_runner_child as owned_runner_child

            original_tick = owned_runner_child.tick
            attempts = []

            def observed_tick(*args, **kwargs):
                attempts.append(dict(kwargs))
                return original_tick(*args, **kwargs)

            monkeypatch.setattr(owned_runner_child, "tick", observed_tick)
            with pytest.raises(UnresolvedTickIntentRefusal):
                run_owned_runner(
                    root,
                    "alpha",
                    data_client_factory=lambda _capture, _root, dispatch: _GuardedOfflineDataClient(data_client, dispatch),
                    build_fund=_OfflineFund,
                    now=lambda: _RUNNER_NOW,
                    resolver=lambda _host, _port: ["93.184.216.34"],
                )

            final = read_runner_record(root, "alpha", "state")
            assert final["status"] == "failed"
            assert final["reason"] == "unresolved-tick-intent"
            assert validate_runner_state(root, "alpha", final)
            assert final["refusal"] == {
                "reason": "unresolved-tick-intent",
                "fund": "alpha",
                "intent_request_id": interrupted_id,
                "intent_session": _DUE_SESSION,
                "recovery": "reconcile-tick-request",
            }
            assert final["sessions_completed"] == 0
            assert final["last_session"] == _INITIAL_SESSION
            assert len(attempts) == 1
            assert ledger.sessions() == [_INITIAL_SESSION]
            assert ledger.events() == events_before
            assert (directory / "broker.json").read_bytes() == broker_before


def test_two_process_audit_appends_are_complete_and_uninterleaved(race_root, tmp_path, owned_test_process):
    root, _admission = race_root
    go = tmp_path / "audit-go"
    count = 24
    payload = "x" * 4096
    children = []
    for writer in ("first", "second"):
        ready = tmp_path / f"audit-ready-{writer}"
        final = tmp_path / f"audit-final-{writer}"
        error = tmp_path / f"audit-error-{writer}"
        script = _render(
            _AUDIT_APPENDER,
            ROOT=str(root),
            FUND="alpha",
            WRITER=writer,
            READY=str(ready),
            GO=str(go),
            FINAL=str(final),
            ERROR=str(error),
            COUNT=str(count),
            PAYLOAD=payload,
        )
        children.append((writer, ready, final, error, owned_test_process(script)))

    try:
        for writer, ready, _final, _error, process in children:
            assert _wait_file(ready, process, f"audit writer {writer}") == "ready"
        go.write_text("go", encoding="utf-8")
        for writer, _ready, final, error, process in children:
            try:
                assert _wait_file(final, process, f"audit writer {writer}") == "done"
            except AssertionError as exc:
                detail = error.read_text(encoding="utf-8") if error.exists() else "child error unavailable"
                raise AssertionError(f"{exc}; child error: {detail}") from exc
            assert process.wait(timeout=60) == 0
    finally:
        go.write_text("release", encoding="utf-8")

    events = Ledger(root / "paper" / "alpha").events()
    audit = [event for event in events if event["kind"] == "cross-process-audit"]
    expected = {(writer, sequence) for writer in ("first", "second") for sequence in range(count)}
    observed = {(event["writer"], event["sequence"]) for event in audit}
    assert len(audit) == count * 2
    assert observed == expected
    assert all(event["payload"] == payload for event in audit)


def test_concurrent_manual_appends_to_one_fund_admit_exactly_one_writer(race_root, tmp_path, owned_test_process):
    root, admission = race_root
    record = _record("alpha")
    release = tmp_path / "release-first"
    racers = _start_racers(owned_test_process, tmp_path, root, "alpha", record, 4, release=release, prefix="first")
    statuses = sorted(racer.wait_status() for racer in racers)
    assert statuses == ["admitted", "conflict", "conflict", "conflict"]

    # Every other in-process entrypoint for the same fund is refused while the winner holds it.
    with pytest.raises(WriterConflict):
        with admission.manual_session("alpha", timeout=0):
            pytest.fail("a second manual/runner session was admitted")
    with pytest.raises(WriterConflict):
        with admission.deployment_lock("alpha", timeout=0):
            pytest.fail("archive/lifecycle was admitted during a running session")
    with pytest.raises(LedgerError, match="admission denied"):
        Ledger(root / "paper" / "alpha").append(record)
    assert _recorded(root, "alpha") == []

    release.write_text("release", encoding="utf-8")
    finals = sorted(racer.wait_final() for racer in racers)
    assert finals == ["appended", "conflict", "conflict", "conflict"]
    assert _recorded(root, "alpha") == [record.session]

    # A second wave replaying the same session cannot duplicate the append.
    replay_release = tmp_path / "release-replay"
    replay_release.write_text("release", encoding="utf-8")
    replays = _start_racers(owned_test_process, tmp_path, root, "alpha", record, 3, release=replay_release, prefix="replay")
    replay_finals = [racer.wait_final() for racer in replays]
    assert set(replay_finals) <= {"ledger-error", "conflict"}
    assert "ledger-error" in replay_finals
    assert _recorded(root, "alpha") == [record.session]


def test_process_logical_duplicate_submissions_share_durable_key_and_one_fake_fill(
    race_root,
    tmp_path,
    owned_test_process,
):
    import json
    from datetime import datetime, timedelta, timezone

    from hedge_fund.brokers.paper import PaperBroker
    from hedge_fund.paper.deployed import load_deployed
    from hedge_fund.runtime.capture import freeze_capture
    from hedge_fund.runtime.configuration import resolve_settings
    from hedge_fund.runtime.operations import OperationStore

    root, admission = race_root
    root_context = admission._root
    store = OperationStore(root_context, admission=admission)
    now = datetime(2026, 10, 31, 12, 0, tzinfo=timezone.utc)
    capture = freeze_capture(
        root=root_context,
        subject_id="alpha",
        mandate_digest="a" * 64,
        universe=("AAPL",),
        broker="paper",
        settings=resolve_settings(root_context),
        credential_versions={},
        code_version="synthetic-writer-race",
    )
    initial_book = PaperBroker(root / "paper" / "alpha" / "broker.json")
    initial_cash = initial_book.cash()
    initial_positions = {ticker: position.shares for ticker, position in initial_book.positions().items()}
    go = tmp_path / "logical-go"
    fill_go = tmp_path / "logical-fill-go"
    children = []
    for suffix in ("left", "right"):
        preview = store.create_preview(
            action="paper-run",
            subject_id="alpha",
            expected_head="head-1",
            due_set=("2024-06-07",),
            capture=capture,
            operator_session="synthetic-operator",
            payload={"mode": "manual"},
            now=now,
            expires_at=now + timedelta(minutes=5),
        )
        request = {
            "request_id": f"logical-{suffix}-request",
            "action": preview.action,
            "subject_id": preview.subject_id,
            "preview_id": preview.preview_id,
            "preview_digest": preview.digest,
            "confirmation_token": preview.confirmation_token,
            "operator_session": "synthetic-operator",
            "expected_head": preview.expected_head,
            "due_set": list(preview.due_set),
            "payload": {"mode": "manual"},
            "now": now.isoformat(),
        }
        request_path = tmp_path / f"logical-{suffix}-request.json"
        ready = tmp_path / f"logical-{suffix}-ready"
        decision = tmp_path / f"logical-{suffix}-decision"
        final = tmp_path / f"logical-{suffix}-final.json"
        request_path.write_text(json.dumps(request), encoding="utf-8")
        process = owned_test_process(
            _render(
                _LOGICAL_OPERATION_SUBMITTER,
                ROOT=str(root),
                REQUEST=str(request_path),
                READY=str(ready),
                DECISION=str(decision),
                FILL_GO=str(fill_go),
                GO=str(go),
                FINAL=str(final),
            )
        )
        children.append((suffix, ready, decision, final, process))

    try:
        for suffix, ready, _decision, _final, process in children:
            assert _wait_file(ready, process, f"logical submitter {suffix}") == "ready"
        go.write_text("go", encoding="utf-8")
        for suffix, _ready, decision, _final, process in children:
            assert _wait_file(decision, process, f"logical submitter {suffix} decision", timeout=60) in {"accepted", "duplicate"}
        fill_go.write_text("go", encoding="utf-8")
        outcomes = []
        for suffix, _ready, _decision, final, process in children:
            result = json.loads(_wait_file(final, process, f"logical submitter {suffix} result", timeout=60))
            assert process.wait(timeout=60) == 0, result
            outcomes.append(result)
    finally:
        go.write_text("release", encoding="utf-8")
        fill_go.write_text("release", encoding="utf-8")

    accepted = [outcome for outcome in outcomes if outcome["outcome"] == "accepted"]
    refused = [outcome for outcome in outcomes if outcome["outcome"] == "duplicate"]
    assert len(accepted) == 1
    assert len(refused) == 1
    assert refused[0]["refusal"]["reason"] == "duplicate-logical-operation"
    assert refused[0]["refusal"]["existing_operation_id"] == accepted[0]["operation_id"]
    fill_events = [event for event in Ledger(root / "paper" / "alpha").events() if event["kind"] == "logical-duplicate-fake-fill"]
    assert len(fill_events) == 1
    assert fill_events[0]["operation_id"] == accepted[0]["operation_id"]
    book = PaperBroker(root / "paper" / "alpha" / "broker.json")
    positions = {ticker: position.shares for ticker, position in book.positions().items()}
    assert positions == {**initial_positions, "AAPL": initial_positions.get("AAPL", 0) + 1}
    costs = load_deployed(root / "paper" / "alpha").spec.costs
    expected_price = costs.fill_price("buy", 100)
    expected_cash = initial_cash - expected_price - costs.commission(1, 100)
    assert book.cash() == pytest.approx(expected_cash)


def test_independent_fund_progresses_while_another_fund_session_is_held(race_root, tmp_path, owned_test_process):
    root, admission = race_root
    alpha = _record("alpha")
    beta = _record("beta")
    with _session_held_by_child(owned_test_process, tmp_path, root, "alpha", alpha, "alpha-held") as (racer, release):
        with admission.manual_session("beta", timeout=0):
            Ledger(root / "paper" / "beta").append(beta)
        with admission.deployment_lock("beta", timeout=0):
            pass
        assert _recorded(root, "beta") == [beta.session]
        assert _recorded(root, "alpha") == []
        release.write_text("release", encoding="utf-8")
        assert racer.wait_final() == "appended"
    assert _recorded(root, "alpha") == [alpha.session]


def test_redo_cannot_interleave_with_a_running_append(race_root, tmp_path, owned_test_process):
    root, admission = race_root
    ledger = Ledger(root / "paper" / "alpha")
    first = _record("alpha", "2024-06-07")
    with admission.manual_session("alpha", timeout=0):
        ledger.append(first)
    second = _record("alpha", "2024-06-10", prev_hash=first.hash)
    with _session_held_by_child(owned_test_process, tmp_path, root, "alpha", second, "redo") as (racer, release):
        with pytest.raises(WriterConflict):
            with admission.manual_session("alpha", timeout=0):
                ledger.rewind()
        with pytest.raises(LedgerError, match="admission denied"):
            ledger.rewind()
        assert _recorded(root, "alpha") == [first.session]
        release.write_text("release", encoding="utf-8")
        assert racer.wait_final() == "appended"
    assert _recorded(root, "alpha") == [first.session, second.session]
    with admission.manual_session("alpha", timeout=0):
        assert ledger.rewind().session == second.session
    assert _recorded(root, "alpha") == [first.session]


def test_legacy_runner_presence_denies_every_racing_writer(race_root, tmp_path, owned_test_process):
    root, admission = race_root
    record = _record("alpha")
    (root / "paper" / "alpha" / "runner.pid").write_text("1", encoding="utf-8")
    release = tmp_path / "release-legacy"
    release.write_text("release", encoding="utf-8")
    go = tmp_path / "go-legacy"
    go.write_text("go", encoding="utf-8")
    racers = [_Racer(owned_test_process, tmp_path, root, "alpha", record, go, release, f"legacy-{index}") for index in range(3)]
    for racer in racers:
        assert racer.process.wait(timeout=60) != 0
        assert not racer.status.exists()
        assert not racer.final.exists()
    with RootContext.open(root) as context:
        assert write_authority(context) == {"authority": "ownership-unknown", "reason": "legacy-runner-present"}
    with pytest.raises(OwnershipUnknown):
        with admission.manual_session("alpha", timeout=0):
            pytest.fail("a writer was admitted while legacy runner presence is unknown")
    with pytest.raises(OwnershipUnknown):
        with admission.manual_session("beta", timeout=0):
            pytest.fail("legacy presence must make the whole root read-only")
    assert _recorded(root, "alpha") == []
    assert _recorded(root, "beta") == []


@pytest.mark.parametrize("revocation", ["legacy-runner", "synthetic-test-owner"])
def test_authority_revoked_across_processes_blocks_an_admitted_append(race_root, tmp_path, owned_test_process, revocation):
    root, _admission = race_root
    marker = Path(os.environ["HEDGE_FUND_TEST_ROOT"]) / ".test-owned"
    moved_marker = tmp_path / "revoked-test-marker"
    record = _record("alpha")
    with _session_held_by_child(owned_test_process, tmp_path, root, "alpha", record, f"revoked-{revocation}") as (racer, release):
        try:
            if revocation == "legacy-runner":
                (root / "paper" / "alpha" / "runner.pid").write_text("unverified", encoding="utf-8")
                reason = "legacy-runner-present"
            else:
                marker.rename(moved_marker)
                reason = "operator-single-writer-acknowledgement-required"
            with RootContext.open(root) as context:
                assert write_authority(context) == {"authority": "ownership-unknown", "reason": reason}
            release.write_text("release", encoding="utf-8")
            assert racer.wait_final() == "ledger-error"
            assert _recorded(root, "alpha") == []
        finally:
            if moved_marker.exists():
                moved_marker.rename(marker)


def test_halt_and_verdict_lanes_stay_responsive_under_research_saturation(race_root, tmp_path, owned_test_process):
    root, admission = race_root
    identities = ("alpha", "beta", "research-1", "research-2", "research-3")
    with _research_held_by_child(owned_test_process, tmp_path, root, identities[0]), _research_held_by_child(owned_test_process, tmp_path, root, identities[1]), _research_held_by_child(owned_test_process, tmp_path, root, identities[2]), _research_held_by_child(owned_test_process, tmp_path, root, identities[3]), _research_held_by_child(owned_test_process, tmp_path, root, identities[4]):
        with _session_held_by_child(owned_test_process, tmp_path, root, "alpha", _record("alpha"), "saturated") as (racer, release):
            for identity in identities:
                with pytest.raises(WriterConflict):
                    with admission.research_lane(identity, timeout=0):
                        pass
            ledger = Ledger(root / "paper" / "alpha")
            started = time.monotonic()
            with admission.halt_lane("alpha", timeout=0.1):
                ledger.halt("T027 saturation halt")
            with admission.control_lane("alpha", timeout=0.1):
                pass
            elapsed = time.monotonic() - started
            assert elapsed < MAX_CONTROL_WAIT_SECONDS + 5
            assert ledger.halted() is not None
            release.write_text("release", encoding="utf-8")
            racer.wait_final()


def test_web_archive_waits_for_real_cli_redo_admission_without_duplicate_fills(tmp_path, owned_test_process):
    from fastapi.testclient import TestClient

    from hedge_fund.web.app import create_app
    from hedge_fund.web.demo import seed_demo

    root = seed_demo(tmp_path / "redo-archive")
    fund = "demo-quality"
    before_files = _paper_files(root, fund)
    before_fills = _recorded_fills(root, fund)
    assert [(fill["ticker"], fill["side"], fill["quantity"]) for fill in before_fills] == [("AAPL", "buy", 100)]
    ready = tmp_path / "redo-admitted"
    release = tmp_path / "redo-release"
    outcome = tmp_path / "redo-outcome"
    expected_head = Ledger(root / "paper" / fund).latest().hash
    script = "\n".join(
        [
            "import contextlib, time, traceback",
            "from pathlib import Path",
            "from hedge_fund import run",
            f"ready, release, outcome = Path({str(ready)!r}), Path({str(release)!r}), Path({str(outcome)!r})",
            "class StagedStop(Exception): pass",
            "original_lane = run._paper_lane",
            "@contextlib.contextmanager",
            "def staged_lane(participant, name, lane):",
            "    with original_lane(participant, name, lane):",
            "        if lane == 'manual_session':",
            "            ready.write_text('redo-admitted', encoding='utf-8')",
            "            deadline = time.monotonic() + 90",
            "            while not release.exists() and time.monotonic() < deadline: time.sleep(0.01)",
            "            if not release.exists(): raise TimeoutError('redo release missing')",
            "            raise StagedStop()",
            "        yield",
            "run._paper_lane = staged_lane",
            "try:",
            f"    run.main(['--root', {str(root)!r}, '--enable-network', 'paper', 'tick', {fund!r}, '--again', '--expected-head', {expected_head!r}, '--request-id', 'redo-archive-cli-001'])",
            "except StagedStop:",
            "    outcome.write_text('stopped-before-redo-effects', encoding='utf-8')",
            "except BaseException:",
            "    outcome.write_text(traceback.format_exc(), encoding='utf-8')",
            "    raise",
            "else:",
            "    outcome.write_text('unexpected-return', encoding='utf-8')",
        ]
    )
    app = create_app(root=root, allow_writes=True, network_enabled=True, demo=True)
    with TestClient(app, client=("127.0.0.1", 50000)) as client:
        capabilities = client.get("/api/capabilities", headers={"host": "127.0.0.1"}).json()
        headers = {
            "host": "127.0.0.1",
            "origin": "http://127.0.0.1",
            "x-csrf-token": capabilities["mutation_token"],
        }
        archive = {"action": "archive", "kind": "deployment", "identity": fund}
        response = client.post("/api/lifecycle/preview", headers=headers, json=archive)
        assert response.status_code == 200, response.text
        preview = response.json()
        request = {
            **archive,
            "request_id": "redo-archive-race",
            "preview_id": preview["preview_id"],
            "preview_digest": preview["preview_digest"],
            "confirmation_token": preview["confirmation_token"],
            "expected_head": preview["expected_head"],
        }
        child = owned_test_process(script)
        try:
            assert _wait_file(ready, child, "CLI redo admission", timeout=60) == "redo-admitted"
            denied = client.post("/api/lifecycle/accept", headers=headers, json=request)
            assert denied.status_code == 409, denied.text
            assert denied.json()["code"] == "writer-conflict"
            assert client.get("/api/operations/by-request/redo-archive-race", headers=headers).status_code == 404
            assert _paper_files(root, fund) == before_files
            assert _recorded_fills(root, fund) == before_fills
        finally:
            release.write_text("release", encoding="utf-8")
            assert child.wait(timeout=60) == 0, outcome.read_text(encoding="utf-8") if outcome.exists() else "CLI child did not exit"

        assert outcome.read_text(encoding="utf-8") == "stopped-before-redo-effects"
        accepted = client.post("/api/lifecycle/accept", headers=headers, json=request)
        assert accepted.status_code == 202, accepted.text
        assert accepted.json()["status"] == "completed"
        assert not (root / "paper" / fund).exists()

        archive_id = accepted.json()["result"]["archive_id"]
        restore = {"action": "restore", "archive_id": archive_id}
        response = client.post("/api/lifecycle/preview", headers=headers, json=restore)
        assert response.status_code == 200, response.text
        preview = response.json()
        restored = client.post(
            "/api/lifecycle/accept",
            headers=headers,
            json={
                **restore,
                "request_id": "redo-archive-restore",
                "preview_id": preview["preview_id"],
                "preview_digest": preview["preview_digest"],
                "confirmation_token": preview["confirmation_token"],
                "expected_head": preview["expected_head"],
            },
        )
        assert restored.status_code == 202, restored.text
        assert restored.json()["status"] == "completed"
        assert _paper_files(root, fund) == before_files
        assert _recorded_fills(root, fund) == before_fills


def test_real_cli_and_web_manual_competition_produces_one_fake_fill(tmp_path, owned_test_process, request):
    from datetime import datetime

    from fastapi.testclient import TestClient

    from hedge_fund.backtesting.test_fund import FakeAnalyst, FakeDataClient, SERIES
    from hedge_fund.brokers.paper import PaperBroker
    from hedge_fund.data.sessions import NEW_YORK
    from hedge_fund.fund import Fund, FundSpec
    from hedge_fund.llm import load_api_models
    from hedge_fund.paper import deploy, tick
    from hedge_fund.web.app import create_app
    from hedge_fund.web.demo import seed_demo

    root = seed_demo(tmp_path / "manual-fills")
    fund = "race-fill"
    ready = tmp_path / "tick-admitted"
    release = tmp_path / "tick-release"
    winner_result = tmp_path / "tick-winner"
    loser_result = tmp_path / "tick-loser"
    factory_calls = []

    def forbidden_data_client():
        factory_calls.append(True)
        raise AssertionError("a denied web preview constructed a data client")

    app = create_app(
        root=root,
        allow_writes=True,
        network_enabled=True,
        demo=True,
        data_client_factory=forbidden_data_client,
    )
    service = app.state.service
    request.addfinalizer(service.close)
    spec = FundSpec(
        schema_version=2,
        name=fund,
        strategies=[{"name": "solo", "models": [{"name": "pead"}], "blend": {"mode": "long_short"}}],
        risk={"max_position_pct": 1.0, "max_gross_exposure": 1.0},
        capital=100_000,
        costs={"spread_bps": 0, "commission_per_share": 0},
        approval_required=True,
        rebalance="daily",
    )

    def build_fund(mandate):
        return Fund(mandate, models={"solo": [FakeAnalyst("pead", {"AAPL": 1.0})]})

    with paths.bound_root(service.root_context):
        with service._admission.deployment_lock(fund, timeout=0):
            directory = deploy(fund, spec, ["AAPL"], root=root / "paper")
        with service._admission.manual_session(fund, timeout=0):
            latest = tick(
                directory,
                FakeDataClient(SERIES),
                session="2024-06-03",
                build_fund=build_fund,
                now=lambda: datetime(2024, 6, 4, 12, tzinfo=NEW_YORK),
            )
    ledger = Ledger(directory)
    before_fills = _recorded_fills(root, fund)
    assert latest.decision is not None
    assert before_fills == []

    script = """
import contextlib, io, time, traceback
from pathlib import Path
from hedge_fund import run
from hedge_fund.backtesting.test_fund import FakeAnalyst, FakeDataClient, SERIES, WEEKDAYS
from hedge_fund.fund import Fund

root, fund, ready, release, result, stage, mode = Path(ROOT), FUND, Path(READY), Path(RELEASE), Path(RESULT), STAGE, MODE
expected_head, request_id = EXPECTED_HEAD, REQUEST_ID
original_load = run._load_runtime
original_lane = run._paper_lane

class FixtureData(FakeDataClient):
    def get_prices(self, ticker, start, end, interval="day", interval_multiplier=1):
        assert interval == "day" and interval_multiplier == 1
        return super().get_prices(ticker, start, end)

@contextlib.contextmanager
def fake_data_client(**_kwargs):
    series = dict(SERIES)
    series["MSFT"] = {day: 50.0 for day in WEEKDAYS}
    yield FixtureData(series)

def load_fakes():
    original_load()
    run.make_data_client = fake_data_client
    run._cli_fund = lambda spec, _settings, _dispatch, _key: Fund(spec, models={"solo": [FakeAnalyst("pead", {"AAPL": 1.0})]})

@contextlib.contextmanager
def staged_lane(participant, name, lane):
    with original_lane(participant, name, lane):
        if lane == "manual_session" and stage == "winner":
            ready.write_text("admitted", encoding="utf-8")
            deadline = time.monotonic() + 90
            while not release.exists() and time.monotonic() < deadline:
                time.sleep(0.01)
            if not release.exists():
                raise TimeoutError("tick release missing")
        yield

run._load_runtime = load_fakes
run._paper_lane = staged_lane
output = io.StringIO()
try:
    with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
        try:
            options = ["--again"] if mode == "redo" else ["--session", "2024-06-04"]
            run.main(["--root", str(root), "--enable-network", "paper", "tick", fund, *options, "--expected-head", expected_head, "--request-id", request_id])
        except SystemExit as exc:
            outcome = str(exc.code)
        else:
            outcome = "returned"
except BaseException:
    result.write_text(traceback.format_exc(), encoding="utf-8")
    raise
result.write_text(outcome + "\\n" + output.getvalue(), encoding="utf-8")
"""
    try:
        with TestClient(app, client=("127.0.0.1", 50000)) as client:
            capabilities = client.get("/api/capabilities", headers={"host": "127.0.0.1"}).json()
            headers = {
                "host": "127.0.0.1",
                "origin": "http://127.0.0.1",
                "x-csrf-token": capabilities["mutation_token"],
            }
            settings = client.get("/api/settings", headers=headers).json()
            model = next(model_id for _, model_id, provider in load_api_models() if provider == "Ollama" and not model_id.endswith(":cloud"))
            configured = client.post("/api/settings/model", headers=headers, json={"model": model, "expected_version": settings["version"]})
            assert configured.status_code == 200, configured.text
            approved = client.post(
                f"/api/paper/{fund}/approval",
                headers=headers,
                json={
                    "request_id": "race-fill-verdict-001",
                    "verdict": "approve",
                    "decision_as_of": latest.decision.as_of,
                    "source_record_hash": latest.hash,
                },
            )
            assert approved.status_code == 200, approved.text
            before_files = _paper_files(root, fund)

            def child_script(stage: str, result: Path, *, ready_path: Path = ready, release_path: Path = release, mode: str = "tick") -> str:
                return _render(
                    script,
                    ROOT=str(root),
                    FUND=fund,
                    READY=str(ready_path),
                    RELEASE=str(release_path),
                    RESULT=str(result),
                    STAGE=stage,
                    MODE=mode,
                    EXPECTED_HEAD=ledger.latest().hash,
                    REQUEST_ID=f"race-cli-{mode}-001",
                )

            winner = owned_test_process(child_script("winner", winner_result))
            try:
                assert _wait_file(ready, winner, "CLI tick admission", timeout=60) == "admitted"
                loser = owned_test_process(child_script("contender", loser_result))
                denied = client.post(f"/api/paper/{fund}/tick/preview", headers=headers, json={"expected_head": latest.hash})
                assert loser.wait(timeout=60) == 0, loser_result.read_text(encoding="utf-8") if loser_result.exists() else "CLI contender failed"
                loser_output = loser_result.read_text(encoding="utf-8")
                assert loser_output.startswith("1\n") and "busy or unavailable" in loser_output, loser_output
                assert denied.status_code == 409, denied.text
                assert denied.json()["code"] == "writer-conflict"
                assert factory_calls == []
                assert _paper_files(root, fund) == before_files
                assert _recorded_fills(root, fund) == before_fills
            finally:
                release.write_text("release", encoding="utf-8")
                assert winner.wait(timeout=90) == 0, winner_result.read_text(encoding="utf-8") if winner_result.exists() else "CLI winner failed"

            assert winner_result.read_text(encoding="utf-8").startswith("returned\n"), winner_result.read_text(encoding="utf-8")
            sessions = ledger.sessions()
            assert sessions == ["2024-06-03", "2024-06-04"]
            recorded = ledger.read("2024-06-04")
            assert recorded.executed is not None
            assert len(recorded.executed.fills) == 1
            assert recorded.executed.fills[0].ticker == "AAPL"
            assert recorded.executed.fills[0].side == "buy"
            assert recorded.executed.fills[0].quantity == 500
            assert len(_recorded_fills(root, fund)) == len(before_fills) + 1
            events = ledger.events()
            assert [event["kind"] for event in events] == ["tick", "approve", "approval_commit", "tick_intent", "consume", "tick"]
            assert events[2]["request_id"] == "race-fill-verdict-001"
            assert events[3]["request_id"] == "race-cli-tick-001"
            assert events[3]["request_action"] == "tick"
            assert ledger.approval() is None
            book = PaperBroker(root / "paper" / fund / "broker.json")
            assert book.cash() == pytest.approx(recorded.cash)
            assert {ticker: position.shares for ticker, position in book.positions().items()} == recorded.positions

            archive = {"action": "archive", "kind": "deployment", "identity": fund}
            response = client.post("/api/lifecycle/preview", headers=headers, json=archive)
            assert response.status_code == 200, response.text
            preview = response.json()
            archive_request = {
                **archive,
                "request_id": "redo-filled-archive-race",
                "preview_id": preview["preview_id"],
                "preview_digest": preview["preview_digest"],
                "confirmation_token": preview["confirmation_token"],
                "expected_head": preview["expected_head"],
            }
            before_redo = _paper_files(root, fund)
            redo_ready = tmp_path / "filled-redo-admitted"
            redo_release = tmp_path / "filled-redo-release"
            redo_result = tmp_path / "filled-redo-result"
            redo_child = owned_test_process(child_script("winner", redo_result, ready_path=redo_ready, release_path=redo_release, mode="redo"))
            try:
                assert _wait_file(redo_ready, redo_child, "filled CLI redo admission", timeout=60) == "admitted"
                denied = client.post("/api/lifecycle/accept", headers=headers, json=archive_request)
                assert denied.status_code == 409, denied.text
                assert denied.json()["code"] == "writer-conflict"
                assert client.get("/api/operations/by-request/redo-filled-archive-race", headers=headers).status_code == 404
                assert _paper_files(root, fund) == before_redo
            finally:
                redo_release.write_text("release", encoding="utf-8")
                assert redo_child.wait(timeout=90) == 0, redo_result.read_text(encoding="utf-8") if redo_result.exists() else "CLI redo failed"

            redo_output = redo_result.read_text(encoding="utf-8")
            assert redo_output.startswith("returned\n"), redo_output
            redone = ledger.read("2024-06-04")
            assert ledger.sessions() == ["2024-06-03", "2024-06-04"]
            assert redone.hash != recorded.hash and redone.prev_hash == recorded.prev_hash
            assert redone.executed is not None
            assert len(redone.executed.fills) == 1
            assert redone.executed.fills[0].ticker == "AAPL"
            assert redone.executed.fills[0].side == "buy"
            assert redone.executed.fills[0].quantity == 500
            assert len(_recorded_fills(root, fund)) == 1
            assert ledger.approval() is None
            events = ledger.events()
            assert sum(event["kind"] == "consume" for event in events) == 1
            assert sum(event["kind"] == "redo" for event in events) == 1
            superseded = list((ledger.records_dir / "superseded").glob("*.json"))
            assert len(superseded) == 1
            assert SessionRecord.model_validate_json(superseded[0].read_text()).hash == recorded.hash
            book = PaperBroker(root / "paper" / fund / "broker.json")
            assert book.cash() == pytest.approx(redone.cash)
            assert {ticker: position.shares for ticker, position in book.positions().items()} == redone.positions
            stale = client.post("/api/lifecycle/accept", headers=headers, json=archive_request)
            assert stale.status_code == 409, stale.text
            assert stale.json()["code"] == "stale-preview"
            assert client.get("/api/operations/by-request/redo-filled-archive-race", headers=headers).status_code == 404
    finally:
        service.close()


def test_owned_runner_executes_one_fake_fill_while_cli_web_and_archive_compete(tmp_path, owned_test_process, monkeypatch, request):
    import subprocess
    from datetime import datetime

    from fastapi.testclient import TestClient

    import hedge_fund.runtime.dispatch as dispatch_module
    import hedge_fund.runtime.owned_runner as owned_runner
    from hedge_fund.backtesting.test_fund import FakeAnalyst, FakeDataClient, SERIES
    from hedge_fund.brokers.paper import PaperBroker
    from hedge_fund.data.sessions import NEW_YORK
    from hedge_fund.fund import Fund
    from hedge_fund.paper import tick
    from hedge_fund.web.app import create_app
    from hedge_fund.web.demo import seed_demo
    from hedge_fund.web.test_paper_operations import _wait_for_operation

    root = seed_demo(Path(os.environ["HEDGE_FUND_TEST_ROOT"]) / "runner-race")
    fund = "runner-fill"
    ready = tmp_path / "runner-before-fill"
    release = tmp_path / "runner-release"
    terminal_ready = tmp_path / "runner-terminal"
    terminal_release = tmp_path / "runner-terminal-release"
    runner_error = tmp_path / "runner-error"
    bootstrap_error = tmp_path / "runner-bootstrap-error"
    cli_result = tmp_path / "runner-cli-result"
    preview_calls = []

    def fake_data_client():
        preview_calls.append(True)
        return nullcontext(FakeDataClient(SERIES))

    original_resolve = dispatch_module.resolve_destination

    def fake_public_ip(_host, _port):
        return ["93.184.216.34"]

    def fake_dns(host, port, *, local, resolver=None):
        if host == "query1.finance.yahoo.com" and not local:
            resolver = fake_public_ip
        return original_resolve(host, port, local=local, resolver=resolver)

    monkeypatch.setattr(dispatch_module, "resolve_destination", fake_dns)
    runner_script = _render(
        """
import argparse, time, traceback
from pathlib import Path
from hedge_fund import paths
from hedge_fund.backtesting.test_fund import FakeAnalyst, FakeDataClient, SERIES
from hedge_fund.fund import Fund
import hedge_fund.runtime.owned_runner_child as runner_child
from hedge_fund.runtime.owned_runner_child import run_owned_runner
from hedge_fund.runtime.policy import ProviderTarget
from hedge_fund.runtime.root import RootContext

ready, release, error = Path(READY), Path(RELEASE), Path(ERROR)
terminal_ready, terminal_release = Path(FINISHED_WAIT), Path(FINISHED_GO)
parser = argparse.ArgumentParser()
parser.add_argument("--root", required=True)
parser.add_argument("--fund", required=True)
args = parser.parse_args()

def signal(path, value):
    pending = path.with_name(path.name + ".pending")
    pending.write_text(value, encoding="utf-8")
    pending.replace(path)

class FixtureData(FakeDataClient):
    def __init__(self, dispatch):
        super().__init__(SERIES)
        self.dispatch = dispatch
        self.blocked = False

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def get_prices(self, ticker, start, end, interval="day", interval_multiplier=1):
        assert interval == "day" and interval_multiplier == 1
        self.dispatch.authorize_transport(
            ProviderTarget(kind="data", provider="yfinance"),
            url="https://query1.finance.yahoo.com/mock",
            method="GET",
        )
        if ticker == "AAPL" and not self.blocked:
            self.blocked = True
            signal(ready, "before-fill")
            deadline = time.monotonic() + 90
            while not release.exists() and time.monotonic() < deadline:
                time.sleep(0.01)
            if not release.exists():
                raise TimeoutError("runner release missing")
        return super().get_prices(ticker, start, end)

def build_fund(spec, _capture, _root, _dispatch):
    return Fund(spec, models={"solo": [FakeAnalyst("pead", {"AAPL": 1.0})]})

original_write_status = runner_child._write_status
def hold_terminal(root, fund, nonce_hash, status):
    original_write_status(root, fund, nonce_hash, status)
    if status["status"] == "completed":
        signal(terminal_ready, "completed-held")
        deadline = time.monotonic() + 90
        while not terminal_release.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        if not terminal_release.exists():
            raise TimeoutError("terminal release missing")
runner_child._write_status = hold_terminal

try:
    with RootContext.open(args.root) as root, paths.bound_root(root):
        run_owned_runner(
            root,
            args.fund,
            data_client_factory=lambda _capture, _root, dispatch: FixtureData(dispatch),
            build_fund=build_fund,
            resolver=lambda _host, _port: ["93.184.216.34"],
        )
except BaseException:
    error.write_text(traceback.format_exc(), encoding="utf-8")
    raise
""",
        READY=str(ready),
        RELEASE=str(release),
        FINISHED_WAIT=str(terminal_ready),
        FINISHED_GO=str(terminal_release),
        ERROR=str(runner_error),
    )
    original_command = owned_runner._runner_command

    def fake_runner_command(root_context, name):
        command = original_command(root_context, name)
        module = "hedge_fund.runtime.owned_runner_child"
        if "-m" in command:
            index = command.index("-m")
            assert command[index + 1] == module
            command[index] = "-c"
            command[index + 1] = runner_script
        else:
            index = command.index("-c") + 1
            marker = f"runpy.run_module({module!r},run_name='__main__')"
            assert command[index].count(marker) == 1
            command[index] = command[index].replace(marker, f"exec({runner_script!r})")
        return command

    monkeypatch.setattr(owned_runner, "_runner_command", fake_runner_command)
    stderr_file = bootstrap_error.open("wb")
    request.addfinalizer(stderr_file.close)
    runner_processes = []

    class CaptureRunnerSubprocess:
        def __getattr__(self, name):
            return getattr(subprocess, name)

        def Popen(self, *args, **kwargs):
            kwargs["stderr"] = stderr_file
            process = subprocess.Popen(*args, **kwargs)
            runner_processes.append(process)
            return process

    monkeypatch.setattr(owned_runner, "subprocess", CaptureRunnerSubprocess())
    app = create_app(
        root=root,
        allow_writes=True,
        network_enabled=True,
        demo=True,
        data_client_factory=fake_data_client,
    )
    service = app.state.service
    request.addfinalizer(service.close)
    spec = FundSpec(
        schema_version=2,
        name=fund,
        strategies=[{"name": "solo", "models": [{"name": "pead"}], "blend": {"mode": "long_short"}}],
        risk={"max_position_pct": 1.0, "max_gross_exposure": 1.0},
        capital=100_000,
        costs={"spread_bps": 0, "commission_per_share": 0},
        approval_required=True,
        rebalance="daily",
    )

    def build_fund(mandate):
        return Fund(mandate, models={"solo": [FakeAnalyst("pead", {"AAPL": 1.0})]})

    with paths.bound_root(service.root_context):
        with service._admission.deployment_lock(fund, timeout=0):
            directory = deploy(fund, spec, ["AAPL"], root=root / "paper")
        with service._admission.manual_session(fund, timeout=0):
            first = tick(
                directory,
                FakeDataClient(SERIES),
                session="2024-06-03",
                build_fund=build_fund,
                now=lambda: datetime(2024, 6, 4, 12, tzinfo=NEW_YORK),
            )
    assert first.decision is not None
    ledger = Ledger(directory)

    cli_script = _render(
        """
import contextlib, io, traceback
from pathlib import Path
from hedge_fund import run

result = Path(RESULT)
original_load = run._load_runtime
def deny_provider(*_args, **_kwargs):
    raise AssertionError("denied CLI reached a provider")
def load_fakes():
    original_load()
    run.make_data_client = deny_provider
    run._cli_fund = deny_provider
run._load_runtime = load_fakes
output = io.StringIO()
try:
    with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
        try:
            run.main(["--root", ROOT, "--enable-network", "paper", "tick", FUND, "--expected-head", EXPECTED_HEAD, "--request-id", REQUEST_ID])
        except SystemExit as exc:
            outcome = str(exc.code)
        else:
            outcome = "returned"
except BaseException:
    result.write_text(traceback.format_exc(), encoding="utf-8")
    raise
result.write_text(outcome + "\\n" + output.getvalue(), encoding="utf-8")
""",
        ROOT=str(root),
        FUND=fund,
        RESULT=str(cli_result),
        EXPECTED_HEAD=first.hash,
        REQUEST_ID="runner-cli-tick-001",
    )
    try:
        with TestClient(app, client=("127.0.0.1", 50000)) as client:
            capabilities = client.get("/api/capabilities", headers={"host": "127.0.0.1"}).json()
            headers = {
                "host": "127.0.0.1",
                "origin": "http://127.0.0.1",
                "x-csrf-token": capabilities["mutation_token"],
            }
            settings = client.get("/api/settings", headers=headers).json()
            configured = client.put(
                "/api/settings",
                headers=headers,
                json={
                    "data_provider": "yfinance",
                    "model": "gemma3:4b",
                    "endpoint": "http://127.0.0.1:11434",
                    "timeout_seconds": 1.0,
                    "parameters": {"max_tokens": 32},
                    "expected_version": settings["version"],
                },
            )
            assert configured.status_code == 200, configured.text
            approved = client.post(
                f"/api/paper/{fund}/approval",
                headers=headers,
                json={
                    "request_id": "runner-fill-verdict-001",
                    "verdict": "approve",
                    "decision_as_of": first.decision.as_of,
                    "source_record_hash": first.hash,
                },
            )
            assert approved.status_code == 200, approved.text

            archive = {"action": "archive", "kind": "deployment", "identity": fund}
            response = client.post("/api/lifecycle/preview", headers=headers, json=archive)
            assert response.status_code == 200, response.text
            archive_preview = response.json()
            archive_request = {
                **archive,
                "request_id": "running-fill-archive",
                "preview_id": archive_preview["preview_id"],
                "preview_digest": archive_preview["preview_digest"],
                "confirmation_token": archive_preview["confirmation_token"],
                "expected_head": archive_preview["expected_head"],
            }
            response = client.post(
                f"/api/paper/{fund}/runner/preview",
                headers=headers,
                json={"expected_head": first.hash, "max_sessions": 1, "max_runtime_minutes": 2},
            )
            assert response.status_code == 201, response.text
            preview = response.json()
            assert preview["due_set"] == ["2024-06-04"]
            accepted = client.post(
                f"/api/paper/{fund}/runner",
                headers=headers,
                json={
                    "request_id": "running-fill-start",
                    "preview_id": preview["preview_id"],
                    "preview_digest": preview["preview_digest"],
                    "confirmation_token": preview["confirmation_token"],
                    "expected_head": first.hash,
                    "due_set": preview["due_set"],
                    "max_sessions": 1,
                    "max_runtime_minutes": 2,
                },
            )
            assert accepted.status_code == 202, accepted.text
            operation = _wait_for_operation(service, accepted.json()["operation_id"])
            if operation["status"] != "completed":
                raise AssertionError(f"{operation}\n{runner_error.read_text() if runner_error.exists() else ''}\n{bootstrap_error.read_text(errors='replace')}")
            process_ref = service._runner_manager._processes[owned_runner.runner_key(fund)]
            process = process_ref.process
            assert _wait_file(ready, process, "runner pre-fill admission", timeout=60) == "before-fill"
            assert service.runner_status(fund)["status"] == "running"
            before_files = _paper_files(root, fund)
            before_preview_calls = len(preview_calls)
            contender = owned_test_process(cli_script)
            denied_tick = client.post(f"/api/paper/{fund}/tick/preview", headers=headers, json={"expected_head": first.hash})
            denied_archive = client.post("/api/lifecycle/accept", headers=headers, json=archive_request)
            assert contender.wait(timeout=60) == 0, cli_result.read_text() if cli_result.exists() else "CLI contender failed"
            output = cli_result.read_text(encoding="utf-8")
            assert output.startswith("1\n") and "busy or unavailable" in output, output
            assert denied_tick.status_code == 409 and denied_tick.json()["code"] == "writer-conflict", denied_tick.text
            assert denied_archive.status_code == 409 and denied_archive.json()["code"] == "writer-conflict", denied_archive.text
            assert client.get("/api/operations/by-request/running-fill-archive", headers=headers).status_code == 404
            assert len(preview_calls) == before_preview_calls
            assert _paper_files(root, fund) == before_files
            assert _recorded_fills(root, fund) == []

            release.write_text("release", encoding="utf-8")
            assert _wait_file(terminal_ready, process, "completed runner still holding its reservation", timeout=60) == "completed-held"
            assert service.runner_status(fund)["status"] == "completed"
            blocked_terminal = client.post("/api/lifecycle/accept", headers=headers, json=archive_request)
            assert blocked_terminal.status_code == 409 and blocked_terminal.json()["code"] == "writer-conflict", blocked_terminal.text
            assert client.get("/api/operations/by-request/running-fill-archive", headers=headers).status_code == 404
            terminal_release.write_text("release", encoding="utf-8")
            assert process.wait(timeout=90) == 0, runner_error.read_text() if runner_error.exists() else "runner child failed"
            status = service.runner_status(fund)
            assert status["status"] == "completed" and status["sessions_completed"] == 1, status
            assert ledger.sessions() == ["2024-06-03", "2024-06-04"]
            recorded = ledger.read("2024-06-04")
            assert recorded.executed is not None and len(recorded.executed.fills) == 1
            fill = recorded.executed.fills[0]
            assert (fill.ticker, fill.side, fill.quantity) == ("AAPL", "buy", 500)
            assert len(_recorded_fills(root, fund)) == 1
            events = ledger.events()
            assert [event["kind"] for event in events] == ["tick", "approve", "approval_commit", "tick_intent", "consume", "tick"]
            assert events[2]["request_id"] == "runner-fill-verdict-001"
            assert events[3]["request_action"] == "tick"
            assert events[3]["request_id"].startswith("runner:")
            assert ledger.approval() is None
            book = PaperBroker(directory / "broker.json")
            assert book.cash() == pytest.approx(recorded.cash)
            assert {ticker: position.shares for ticker, position in book.positions().items()} == recorded.positions
            stale = client.post("/api/lifecycle/accept", headers=headers, json=archive_request)
            assert stale.status_code == 409 and stale.json()["code"] == "stale-preview", stale.text
            assert client.get("/api/operations/by-request/running-fill-archive", headers=headers).status_code == 404
            refreshed = client.post("/api/lifecycle/preview", headers=headers, json=archive)
            assert refreshed.status_code == 200, refreshed.text
            refreshed = refreshed.json()
            runner_review = refreshed["payload"]["runner_state"][fund]
            assert runner_review["status"] == "completed" and runner_review["available"] is False
            assert len(runner_review["state_digest"]) == len(runner_review["control_digest"]) == 64
            archived = client.post(
                "/api/lifecycle/accept",
                headers=headers,
                json={
                    **archive,
                    "request_id": "completed-fill-archive",
                    "preview_id": refreshed["preview_id"],
                    "preview_digest": refreshed["preview_digest"],
                    "confirmation_token": refreshed["confirmation_token"],
                    "expected_head": refreshed["expected_head"],
                },
            )
            assert archived.status_code == 202 and archived.json()["status"] == "completed", archived.text
            assert not directory.exists()
            archive_id = archived.json()["result"]["archive_id"]
            restore = {"action": "restore", "archive_id": archive_id}
            restored_preview = client.post("/api/lifecycle/preview", headers=headers, json=restore)
            assert restored_preview.status_code == 200, restored_preview.text
            restored_preview = restored_preview.json()
            restored = client.post(
                "/api/lifecycle/accept",
                headers=headers,
                json={
                    **restore,
                    "request_id": "completed-fill-restore",
                    "preview_id": restored_preview["preview_id"],
                    "preview_digest": restored_preview["preview_digest"],
                    "confirmation_token": restored_preview["confirmation_token"],
                    "expected_head": restored_preview["expected_head"],
                },
            )
            assert restored.status_code == 202 and restored.json()["status"] == "completed", restored.text
            assert Ledger(directory).sessions() == ["2024-06-03", "2024-06-04"]
            assert len(_recorded_fills(root, fund)) == 1
            assert service.runner_status(fund)["status"] == "completed"
            assert len(preview_calls) == before_preview_calls
    finally:
        release.write_text("release", encoding="utf-8")
        terminal_release.write_text("release", encoding="utf-8")
        for process in runner_processes:
            if process.poll() is not None:
                continue
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                process.terminate()
                process.wait(timeout=15)
        service.close()


def test_web_verdict_and_halt_remain_responsive_during_cross_process_research_saturation(tmp_path, owned_test_process):
    from fastapi.testclient import TestClient

    from hedge_fund.backtesting.test_fund import FakeAnalyst, FakeDataClient, SERIES
    from hedge_fund.fund import Fund, load_spec
    from hedge_fund.llm import load_api_models
    from hedge_fund.web.app import create_app
    from hedge_fund.web.demo import seed_demo

    root = seed_demo(tmp_path / "saturated-controls")
    fund = "demo-quality"
    ledger = Ledger(root / "paper" / fund)
    before_records = {session: ledger.path(session).read_bytes() for session in ledger.sessions()}
    before_fills = _recorded_fills(root, fund)
    assert [(fill["ticker"], fill["side"], fill["quantity"]) for fill in before_fills] == [("AAPL", "buy", 100)]
    entered = threading.Event()
    release = threading.Event()
    data_calls = []
    data_fetches = []

    class RecordingDataClient(FakeDataClient):
        def get_prices(self, *args, **kwargs):
            data_fetches.append((args, kwargs))
            return super().get_prices(*args, **kwargs)

    def fake_data_client():
        data_calls.append(True)
        return nullcontext(RecordingDataClient(SERIES))

    def blocking_fund(spec):
        entered.set()
        if not release.wait(90):
            raise TimeoutError("test did not release the synthetic backtest")
        return Fund(spec, models={"earnings-drift": [FakeAnalyst("pead", {"AAPL": 1.0})]})

    app = create_app(
        root=root,
        allow_writes=True,
        network_enabled=True,
        demo=True,
        data_client_factory=fake_data_client,
        fund_factory=blocking_fund,
    )
    try:
        with TestClient(app, client=("127.0.0.1", 50000)) as client:
            capabilities = client.get("/api/capabilities", headers={"host": "127.0.0.1"}).json()
            headers = {
                "host": "127.0.0.1",
                "origin": "http://127.0.0.1",
                "x-csrf-token": capabilities["mutation_token"],
            }
            pending = client.get(f"/api/paper/{fund}", headers=headers).json()["pending"]
            settings = client.get("/api/settings", headers=headers).json()
            model = next(model_id for _, model_id, provider in load_api_models() if provider == "Ollama" and not model_id.endswith(":cloud"))
            configured = client.post("/api/settings/model", headers=headers, json={"model": model, "expected_version": settings["version"]})
            assert configured.status_code == 200, configured.text
            head = mandate_hash(load_spec(root / "mandates" / f"{fund}.yaml"))
            payload = {
                "fund": fund,
                "universe": ["AAPL"],
                "start": "2024-06-03",
                "end": "2024-06-07",
                "provider": "yfinance",
                "model": model,
                "mandate_hash": head,
            }

            def preview():
                response = client.post(
                    "/api/operations/preview",
                    headers=headers,
                    json={"action": "backtest", "subject_id": fund, "expected_head": head, "payload": payload},
                )
                assert response.status_code == 201, response.text
                return response.json()

            def accept(review, request_id):
                return client.post(
                    "/api/operations",
                    headers=headers,
                    json={
                        "request_id": request_id,
                        "action": "backtest",
                        "subject_id": fund,
                        "preview_id": review["preview_id"],
                        "preview_digest": review["preview_digest"],
                        "confirmation_token": review["confirmation_token"],
                        "expected_head": head,
                        "due_set": [],
                        "payload": payload,
                    },
                )

            started = accept(preview(), "saturation-running")
            assert started.status_code == 202, started.text
            assert entered.wait(60), "synthetic backtest did not occupy its worker"
            waiting = preview()
            with _research_held_by_child(owned_test_process, tmp_path, root, fund):
                denied = accept(waiting, "saturation-denied")
                assert denied.status_code == 429, denied.text
                assert denied.json()["code"] == "capacity-denied"
                assert client.get("/api/operations/by-request/saturation-denied", headers=headers).status_code == 404
                assert not release.is_set()
                assert data_calls == []

                started_at = time.monotonic()
                verdict = client.post(
                    f"/api/paper/{fund}/approval",
                    headers=headers,
                    json={
                        "request_id": "t027-saturation-approval-001",
                        "verdict": "approve",
                        "decision_as_of": pending["decision_as_of"],
                        "source_record_hash": pending["source_record_hash"],
                    },
                )
                verdict_seconds = time.monotonic() - started_at
                assert verdict.status_code == 200, verdict.text
                assert verdict_seconds < MAX_CONTROL_WAIT_SECONDS + 5
                assert ledger.approval()["decision_hash"] == pending["source_record_hash"]

                started_at = time.monotonic()
                halted = client.post(
                    f"/api/paper/{fund}/halt",
                    headers=headers,
                    json={"request_id": "halt-t027-saturation-001", "reason": "synthetic saturation halt"},
                )
                halt_seconds = time.monotonic() - started_at
                assert halted.status_code == 200, halted.text
                assert halt_seconds < MAX_CONTROL_WAIT_SECONDS + 5
                assert ledger.halted() == "synthetic saturation halt"
                assert {session: ledger.path(session).read_bytes() for session in ledger.sessions()} == before_records
                assert _recorded_fills(root, fund) == before_fills
                print(f"T027 bounded controls: verdict={verdict_seconds:.3f}s halt={halt_seconds:.3f}s")

            cancelled = client.post(
                f"/api/operations/{started.json()['operation_id']}/cancel",
                headers=headers,
                json={"request_id": "saturation-cancel"},
            )
            assert cancelled.status_code == 200, cancelled.text
            assert cancelled.json()["status"] == "cancel-requested"
            release.set()
            deadline = time.monotonic() + 60
            latest = None
            while time.monotonic() < deadline:
                status = client.get(f"/api/operations/{started.json()['operation_id']}", headers=headers)
                assert status.status_code == 200, status.text
                latest = status.json()
                if latest["status"] in {"completed", "failed", "cancelled", "interrupted"}:
                    break
                time.sleep(0.05)
            assert latest is not None and latest["status"] == "cancelled", latest
            assert data_fetches == []
            assert _recorded_fills(root, fund) == before_fills
    finally:
        release.set()
        app.state.service.close()
