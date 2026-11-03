import hashlib
import os
import subprocess
import sys
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from secrets import token_urlsafe
from types import SimpleNamespace

import pytest

import hedge_fund.runtime.owned_runner as owned_runner
from hedge_fund.pipeline.session import code_version
from hedge_fund.runtime.admission import (
    AdmissionCoordinator,
    PROTOCOL_VERSION,
    RootOwnerLease,
)
from hedge_fund.runtime.handover import root_binding
from hedge_fund.runtime.owned_runner import (
    OwnedRunnerManager,
    read_runner_record,
    REATTACHED_REASON,
    runner_key,
    RUNNER_ROOT,
    RunnerOwnershipUnknown,
    STALE_OWNER_REASON,
    validate_runner_control,
    validate_runner_owner,
    validate_runner_state,
    write_runner_record,
)
from hedge_fund.runtime.owned_runner_child import _runner_authorization
from hedge_fund.runtime.ownership import (
    launch_command_digest,
    process_identity,
    process_launch_fingerprint,
)
from hedge_fund.runtime.root import RootContext
from hedge_fund.test_support.handover import enroll_synthetic_root


def test_runner_authorization_accepts_frozen_authorization_record():
    capture = SimpleNamespace(
        root_id="a" * 64,
        subject_id="owned-runner",
        digest="b" * 64,
        data_provider="yfinance",
        llm_provider="Ollama",
        model="gemma3:4b",
        endpoint="http://127.0.0.1:11434",
    )
    raw = {
        "initial_due_set": [],
        "expires_at": "2027-01-01T00:00:00+00:00",
        "max_sessions": 1,
        "max_calls": 4,
        "max_resources": 8,
        "operation_id": "c" * 32,
        "operation_digest": "d" * 64,
    }

    authorization = _runner_authorization(raw, capture)

    assert authorization.root_id == capture.root_id
    assert authorization.deployment_id == capture.subject_id
    assert authorization.initial_due_set == ()
    assert authorization.expires_at == datetime(2027, 1, 1, tzinfo=timezone.utc)
    assert authorization.max_sessions == 1
    assert authorization.max_calls == 4
    assert authorization.max_resources == 8
    assert authorization.operation_id == "c" * 32
    assert authorization.operation_digest == "d" * 64


def test_runner_record_validators_require_timezone_aware_timestamps(tmp_path):
    with RootContext.open(tmp_path) as root:
        fund = "test-fund"
        nonce_hash = "a" * 64
        state = {
            "schema": 1,
            "protocol_version": PROTOCOL_VERSION,
            "build_id": code_version(),
            "root": root_binding(root),
            "fund": fund,
            "nonce_hash": nonce_hash,
            "status": "starting",
            "created_at": "2026-01-01T00:00:00+00:00",
            "expires_at": "2026-01-01T00:01:00+00:00",
            "max_sessions": 1,
            "sessions_completed": 0,
            "last_session": None,
            "reason": None,
            "pid": None,
            "process_identity": None,
        }
        assert validate_runner_state(root, fund, state)
        state["created_at"] = "2026-01-01T00:00:00"
        assert not validate_runner_state(root, fund, state)

        control = {
            "schema": 1,
            "protocol_version": PROTOCOL_VERSION,
            "build_id": code_version(),
            "root": root_binding(root),
            "fund": fund,
            "nonce_hash": nonce_hash,
            "launch_ready": True,
            "stop_requested": True,
            "requested_at": "2026-01-01T00:00:10+00:00",
        }
        assert validate_runner_control(root, fund, nonce_hash, control)
        control["requested_at"] = "2026-01-01T00:00:10"
        assert not validate_runner_control(root, fund, nonce_hash, control)


_FUND = "synthetic-runner"


def _synthetic_command(marker: str) -> list[str]:
    executable = getattr(sys, "_base_executable", None)
    if not isinstance(executable, str) or not os.path.isfile(executable):
        executable = sys.executable
    return [
        os.path.abspath(executable),
        "-S",
        "-c",
        f"import time\n# synthetic owned runner {marker}\ntime.sleep(120)\n",
    ]


def _write_owner(root: RootContext, owner: dict) -> None:
    owned_runner._write_record(root, f"{RUNNER_ROOT}/{runner_key(_FUND)}/owner.json", owner)


@contextmanager
def _held(lane):
    """Hold an admission lane in another thread, as the live child would."""
    entered = threading.Event()
    release = threading.Event()
    failures = []

    def hold():
        try:
            with lane():
                entered.set()
                release.wait(60)
        except BaseException as exc:  # pragma: no cover - surfaced below
            failures.append(exc)
            entered.set()

    thread = threading.Thread(target=hold, daemon=True)
    thread.start()
    assert entered.wait(30)
    assert not failures, failures
    try:
        yield
    finally:
        release.set()
        thread.join(30)


@pytest.fixture
def synthetic_runner(tmp_path, monkeypatch):
    """Launch a synthetic, test-owned Python child and its exact owner records."""
    root_path = tmp_path / "root"
    root_path.mkdir()
    enroll_synthetic_root(root_path)
    command = _synthetic_command(token_urlsafe(8))
    monkeypatch.setattr(owned_runner, "_runner_command", lambda _root, _fund: list(command))
    root = RootContext.open(root_path)
    lease = RootOwnerLease.acquire(root)
    admission = AdmissionCoordinator(root, owner_lease=lease)
    process = subprocess.Popen(
        command,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        cwd=os.fspath(tmp_path),
    )
    try:
        identity = process_identity(process.pid)
        fingerprint = process_launch_fingerprint(process.pid)
        nonce = token_urlsafe(32)
        nonce_hash = hashlib.sha256(nonce.encode("utf-8")).hexdigest()
        now = datetime.now(timezone.utc)
        binding = root_binding(root)
        common = {
            "schema": 1,
            "protocol_version": PROTOCOL_VERSION,
            "build_id": code_version(),
            "root": binding,
            "fund": _FUND,
        }
        root.mkdir(f"{RUNNER_ROOT}/{runner_key(_FUND)}", parents=True, mode=0o700)
        write_runner_record(
            root,
            _FUND,
            "launch",
            {
                **common,
                "nonce": nonce,
                "created_at": now.isoformat(),
                "authorization": {
                    "operation_id": "c" * 32,
                    "operation_digest": "d" * 64,
                },
            },
        )
        owner = {
            **common,
            "nonce_hash": nonce_hash,
            "operation_id": "c" * 32,
            "operation_digest": "d" * 64,
            "process_identity": identity,
            "launch_fingerprint": fingerprint,
            "command_sha256": launch_command_digest(command),
            "executable_sha256": owned_runner._executable_digest(command[0]),
            "manager_identity": process_identity(os.getpid()),
            "created_at": now.isoformat(),
        }
        assert validate_runner_owner(root, _FUND, owner)
        _write_owner(root, owner)
        state = {
            **common,
            "nonce_hash": nonce_hash,
            "status": "running",
            "created_at": now.isoformat(),
            "expires_at": (now + timedelta(hours=1)).isoformat(),
            "max_sessions": 1,
            "sessions_completed": 0,
            "last_session": None,
            "reason": None,
            "pid": process.pid,
            "process_identity": identity,
        }
        assert validate_runner_state(root, _FUND, state)
        write_runner_record(root, _FUND, "state", state)
        control = {
            **common,
            "nonce_hash": nonce_hash,
            "launch_ready": True,
            "stop_requested": False,
            "requested_at": None,
        }
        assert validate_runner_control(root, _FUND, nonce_hash, control)
        write_runner_record(root, _FUND, "control", control)
        yield SimpleNamespace(
            root=root,
            admission=admission,
            process=process,
            owner=owner,
            state=state,
            command=command,
            hold_reservation=lambda: _held(lambda: admission.runner_reservation(_FUND, timeout=5)),
            hold_deployment=lambda: _held(lambda: admission.deployment_lock(_FUND, timeout=5)),
            control_bytes=lambda: root.read_bytes(f"{RUNNER_ROOT}/{runner_key(_FUND)}/control.json"),
        )
    finally:
        if process.poll() is None:
            process.kill()
        process.wait(30)
        lease.close()
        root.close()


def test_restarted_and_parallel_managers_reattach_exact_child_and_stop_cooperatively(synthetic_runner):
    runner = synthetic_runner
    with runner.hold_reservation():
        restarted = OwnedRunnerManager(runner.root, runner.admission)
        parallel = OwnedRunnerManager(runner.root, runner.admission)

        status = restarted.status(_FUND)
        assert status["status"] == "running"
        assert status["available"] is True
        assert status["reason"] == REATTACHED_REASON
        assert "pid" not in status and "process_identity" not in status
        assert parallel.status(_FUND) == status

        stopping = parallel.request_stop(_FUND)
        assert stopping["status"] == "stopping"
        assert read_runner_record(runner.root, _FUND, "control")["stop_requested"] is True
        assert restarted.status(_FUND)["status"] == "stopping"
        # Stop is cooperative only: the manager never signals the process.
        assert runner.process.poll() is None
        assert read_runner_record(runner.root, _FUND, "state")["status"] == "running"


def test_reattach_fails_closed_when_child_does_not_hold_the_reservation(synthetic_runner):
    runner = synthetic_runner
    manager = OwnedRunnerManager(runner.root, runner.admission)
    before = runner.control_bytes()

    status = manager.status(_FUND)

    assert status["status"] == "unknown"
    assert status["available"] is False
    assert "reservation" in status["reason"]
    with pytest.raises(RunnerOwnershipUnknown):
        manager.request_stop(_FUND)
    assert runner.control_bytes() == before


def _tamper_pid_reuse(runner):
    identity = {**runner.owner["process_identity"], "creation_time": "reused-pid-incarnation"}
    _write_owner(runner.root, {**runner.owner, "process_identity": identity})
    write_runner_record(runner.root, _FUND, "state", {**runner.state, "process_identity": identity})
    return STALE_OWNER_REASON


def _tamper_foreign_command(runner):
    foreign = "f" * 64
    _write_owner(
        runner.root,
        {
            **runner.owner,
            "command_sha256": foreign,
            "launch_fingerprint": {**runner.owner["launch_fingerprint"], "command_sha256": foreign},
        },
    )
    return "does not match this server"


def _tamper_foreign_fingerprint(runner):
    _write_owner(
        runner.root,
        {**runner.owner, "launch_fingerprint": {**runner.owner["launch_fingerprint"], "user": "S-1-5-21-foreign"}},
    )
    return "does not match its recorded launch"


def _tamper_replaced_executable(runner):
    _write_owner(runner.root, {**runner.owner, "executable_sha256": "e" * 64})
    return "executable was replaced"


def _tamper_nonce(runner):
    _write_owner(runner.root, {**runner.owner, "nonce_hash": "a" * 64})
    return "does not match its launch"


def _tamper_operation(runner):
    _write_owner(runner.root, {**runner.owner, "operation_id": "b" * 32})
    return "does not match its launch"


def _tamper_wrong_root(runner):
    _write_owner(runner.root, {**runner.owner, "root": {**runner.owner["root"], "path": runner.owner["root"]["path"] + "-copied"}})
    return "owner record is invalid"


def _tamper_missing_owner(runner):
    os.remove(runner.root.resolve(f"{RUNNER_ROOT}/{runner_key(_FUND)}/owner.json"))
    return "owner record is unavailable"


def _tamper_state_identity(runner):
    other = {**runner.owner["process_identity"], "pid": runner.owner["process_identity"]["pid"] + 4}
    write_runner_record(runner.root, _FUND, "state", {**runner.state, "pid": other["pid"], "process_identity": other})
    return "does not match its launch"


def _tamper_server_command(runner):
    replacement = _synthetic_command("different-server-build")
    owned_runner._runner_command = lambda _root, _fund: replacement
    return "does not match this server"


@pytest.mark.parametrize(
    "tamper",
    [
        _tamper_pid_reuse,
        _tamper_foreign_command,
        _tamper_foreign_fingerprint,
        _tamper_replaced_executable,
        _tamper_nonce,
        _tamper_operation,
        _tamper_wrong_root,
        _tamper_missing_owner,
        _tamper_state_identity,
        _tamper_server_command,
    ],
    ids=lambda tamper: tamper.__name__.removeprefix("_tamper_"),
)
def test_reattach_rejects_unverifiable_incarnation_without_stop(synthetic_runner, tamper, monkeypatch):
    runner = synthetic_runner
    monkeypatch.setattr(owned_runner, "_runner_command", owned_runner._runner_command)
    expected = tamper(runner)
    before = runner.control_bytes()
    manager = OwnedRunnerManager(runner.root, runner.admission)

    with runner.hold_reservation():
        status = manager.status(_FUND)
        with pytest.raises(RunnerOwnershipUnknown):
            manager.request_stop(_FUND)

    assert status["status"] == "unknown"
    assert status["available"] is False
    assert expected in status["reason"]
    assert runner.control_bytes() == before
    assert runner.process.poll() is None


def test_crashed_child_requires_stale_reservation_review(synthetic_runner):
    runner = synthetic_runner
    runner.process.kill()
    runner.process.wait(30)
    manager = OwnedRunnerManager(runner.root, runner.admission)
    before = runner.control_bytes()

    status = manager.status(_FUND)

    assert status == {**status, "status": "unknown", "available": False, "reason": STALE_OWNER_REASON}
    with pytest.raises(RunnerOwnershipUnknown):
        manager.request_stop(_FUND)
    assert runner.control_bytes() == before


def test_starting_record_without_confirmed_launch_is_never_adopted(synthetic_runner):
    runner = synthetic_runner
    write_runner_record(runner.root, _FUND, "state", {**runner.state, "status": "starting"})
    manager = OwnedRunnerManager(runner.root, runner.admission)

    with runner.hold_reservation():
        status = manager.status(_FUND)

    assert status["status"] == "unknown"
    assert "not confirmed" in status["reason"]


def test_read_only_server_reports_unknown_owner_and_cannot_stop(synthetic_runner):
    runner = synthetic_runner
    read_only = OwnedRunnerManager(runner.root, AdmissionCoordinator(runner.root))
    before = runner.control_bytes()

    with runner.hold_reservation():
        status = read_only.status(_FUND)
        with pytest.raises(RunnerOwnershipUnknown):
            read_only.request_stop(_FUND)

    assert status["status"] == "unknown"
    assert "cannot be observed" in status["reason"]
    assert runner.control_bytes() == before


def test_stop_is_fenced_by_deployment_admission(synthetic_runner):
    runner = synthetic_runner
    manager = OwnedRunnerManager(runner.root, runner.admission)
    before = runner.control_bytes()

    with runner.hold_reservation(), runner.hold_deployment():
        assert manager.status(_FUND)["status"] == "running"
        with pytest.raises(RunnerOwnershipUnknown, match="busy"):
            manager.request_stop(_FUND)

    assert runner.control_bytes() == before


def test_admission_os_errors_fail_closed_without_stop(synthetic_runner, monkeypatch):
    runner = synthetic_runner
    manager = OwnedRunnerManager(runner.root, runner.admission)
    before = runner.control_bytes()

    def _broken(*_args, **_kwargs):
        raise OSError("lock file unavailable")

    monkeypatch.setattr(runner.admission, "runner_reservation", _broken)
    monkeypatch.setattr(runner.admission, "deployment_lock", _broken)

    status = manager.status(_FUND)
    assert status["status"] == "unknown"
    assert "cannot be observed" in status["reason"]
    with pytest.raises(RunnerOwnershipUnknown, match="no stop was recorded"):
        manager.request_stop(_FUND)
    assert runner.control_bytes() == before


def test_owner_record_validator_is_exact(synthetic_runner):
    runner = synthetic_runner
    owner = runner.owner
    assert validate_runner_owner(runner.root, _FUND, owner)
    assert not validate_runner_owner(runner.root, _FUND, {**owner, "pid": 1})
    assert not validate_runner_owner(runner.root, _FUND, {**owner, "created_at": "2026-01-01T00:00:00"})
    assert not validate_runner_owner(runner.root, "other-fund", owner)
    assert not validate_runner_owner(runner.root, _FUND, {**owner, "command_sha256": "not-a-digest"})
    assert not validate_runner_owner(
        runner.root,
        _FUND,
        {**owner, "launch_fingerprint": {**owner["launch_fingerprint"], "extra": "x"}},
    )
    identity = {key: value for key, value in owner["process_identity"].items() if key != "creation_time"}
    assert not validate_runner_owner(runner.root, _FUND, {**owner, "process_identity": identity})


def test_launch_fingerprint_matches_exact_child_command():
    command = _synthetic_command("fingerprint")
    process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    other = subprocess.Popen(
        _synthetic_command("foreign"),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        fingerprint = process_launch_fingerprint(process.pid)
        assert fingerprint["command_sha256"] == launch_command_digest(command)
        assert process_launch_fingerprint(other.pid)["command_sha256"] != fingerprint["command_sha256"]
        assert process_launch_fingerprint(os.getpid())["user"] == fingerprint["user"]
    finally:
        for child in (process, other):
            child.kill()
            child.wait(30)


def test_status_presents_terminal_record_written_while_owner_was_exiting(synthetic_runner, monkeypatch):
    runner = synthetic_runner
    manager = OwnedRunnerManager(runner.root, runner.admission)
    original = manager._verify_reattach

    def owner_exits_during_verification(name, key, state):
        write_runner_record(runner.root, _FUND, "state", {**runner.state, "status": "stopped", "reason": "stop-requested"})
        return original(name, key, state)

    monkeypatch.setattr(manager, "_verify_reattach", owner_exits_during_verification)

    status = manager.status(_FUND)

    assert status["status"] == "stopped"
    assert status["available"] is False
    assert status["reason"] == "stop-requested"
