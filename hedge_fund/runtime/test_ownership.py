import ctypes
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from secrets import token_urlsafe
from types import SimpleNamespace

import pytest

import hedge_fund.runtime.owned_runner as owned_runner
from hedge_fund.fund import FundSpec
from hedge_fund.paper.deployed import deploy
from hedge_fund.pipeline.session import code_version, mandate_hash
from hedge_fund.runtime import ownership
from hedge_fund.runtime.admission import AdmissionCoordinator, PROTOCOL_VERSION, RootOwnerLease
from hedge_fund.runtime.capture import freeze_capture
from hedge_fund.runtime.configuration import resolve_settings
from hedge_fund.runtime.handover import root_binding
from hedge_fund.runtime.owned_runner import OwnedRunnerError, OwnedRunnerManager, read_runner_record, runner_key, RUNNER_ROOT, RunnerOwnershipUnknown, validate_runner_state, write_runner_record
from hedge_fund.runtime.owned_runner_child import _wait_for_launch, run_owned_runner
from hedge_fund.runtime.ownership import current_process_identity, identity_matches, process_identity, ProcessIdentityError
from hedge_fund.runtime.root import RootContext
from hedge_fund.test_support.handover import enroll_synthetic_root


def test_current_process_has_native_incarnation_and_namespace_identity():
    identity = current_process_identity()

    assert identity["pid"] == os.getpid()
    assert identity["creation_time"]
    assert identity["host"]
    assert identity["namespace"]
    assert identity_matches(os.getpid(), identity)


def test_process_identity_rejects_pid_only_and_invalid_inputs():
    identity = current_process_identity()

    assert not identity_matches(os.getpid(), {"pid": os.getpid()})
    assert not identity_matches(
        os.getpid(),
        {**identity, "creation_time": "unrelated-incarnation"},
    )
    with pytest.raises(ProcessIdentityError):
        process_identity(0)


@pytest.mark.skipif(
    os.name != "nt" or not isinstance(getattr(ctypes, "_pointer_type_cache", None), dict),
    reason="Windows CPython pointer-type cache is unavailable",
)
def test_windows_process_identity_does_not_retain_pointer_types_per_call():
    pointer_type_cache = ctypes._pointer_type_cache

    class PointerCacheProbe(ctypes.Structure):
        _fields_ = [("value", ctypes.c_int)]

    cache_size = len(pointer_type_cache)
    ctypes.POINTER(PointerCacheProbe)
    if len(pointer_type_cache) == cache_size:
        pytest.skip("this CPython version does not expose pointer-type cache growth")

    def retained_types():
        return {entry for entry in pointer_type_cache if getattr(entry, "__module__", None) == ownership.__name__}

    current_process_identity()
    before = retained_types()
    for _ in range(3):
        current_process_identity()
    assert retained_types() == before


_FUND = "ownership-fixture"


def _sleeping_command(marker: str) -> list[str]:
    executable = getattr(sys, "_base_executable", None)
    if not isinstance(executable, str) or not os.path.isfile(executable):
        executable = sys.executable
    return [os.path.abspath(executable), "-S", "-c", f"import time\n# unrelated process {marker}\ntime.sleep(120)\n"]


@pytest.fixture
def runner_root(tmp_path):
    root_path = tmp_path / "root"
    root_path.mkdir()
    enroll_synthetic_root(root_path)
    root = RootContext.open(root_path)
    lease = RootOwnerLease.acquire(root)
    admission = AdmissionCoordinator(root, owner_lease=lease)
    try:
        root.mkdir(f"{RUNNER_ROOT}/{runner_key(_FUND)}", parents=True, mode=0o700)
        yield SimpleNamespace(path=root_path, root=root, admission=admission)
    finally:
        lease.close()
        root.close()


def _state(context: RootContext, **overrides) -> dict:
    now = datetime.now(timezone.utc)
    state = {
        "schema": 1,
        "protocol_version": PROTOCOL_VERSION,
        "build_id": code_version(),
        "root": root_binding(context),
        "fund": _FUND,
        "nonce_hash": "a" * 64,
        "status": "starting",
        "created_at": now.isoformat(),
        "expires_at": (now + timedelta(hours=1)).isoformat(),
        "max_sessions": 1,
        "sessions_completed": 0,
        "last_session": None,
        "reason": None,
        "pid": None,
        "process_identity": None,
    }
    state.update(overrides)
    return state


def _control_path() -> str:
    return f"{RUNNER_ROOT}/{runner_key(_FUND)}/control.json"


@pytest.mark.parametrize(
    "field,value",
    [
        ("fund", "other-deployment"),
        ("protocol_version", PROTOCOL_VERSION + 1),
        ("build_id", "foreign-build"),
        ("nonce_hash", "not-a-nonce-digest"),
        ("schema", 2),
        ("status", "adopted"),
        ("pid", 4242),
    ],
)
def test_runner_state_is_bound_to_root_deployment_protocol_build_and_nonce(runner_root, field, value):
    root = runner_root.root
    assert validate_runner_state(root, _FUND, _state(root))

    assert not validate_runner_state(root, _FUND, _state(root, **{field: value}))


def test_runner_state_rejects_copied_root_binding(runner_root):
    root = runner_root.root
    binding = root_binding(root)

    assert not validate_runner_state(root, _FUND, _state(root, root={**binding, "path": binding["path"] + "-copied"}))
    assert not validate_runner_state(root, _FUND, _state(root, root="copied-root"))


def test_runner_state_binds_pid_to_its_native_incarnation(runner_root):
    root = runner_root.root
    identity = current_process_identity()
    running = _state(root, status="running", pid=identity["pid"], process_identity=identity)
    assert validate_runner_state(root, _FUND, running)

    assert not validate_runner_state(root, _FUND, {**running, "pid": identity["pid"] + 1})
    assert not validate_runner_state(root, _FUND, {**running, "process_identity": None})
    assert not validate_runner_state(root, _FUND, {**running, "process_identity": {"pid": identity["pid"]}})
    assert not validate_runner_state(root, _FUND, {**running, "process_identity": {**identity, "extra": "forged"}})
    assert not validate_runner_state(root, _FUND, {**running, "owner": "forged"})


@pytest.mark.parametrize("field", ["creation_time", "host", "namespace", "image"])
def test_process_identity_requires_every_incarnation_component(field):
    identity = current_process_identity()

    assert identity_matches(os.getpid(), identity)
    assert not identity_matches(os.getpid(), {**identity, field: f"foreign-{field}"})
    assert not identity_matches(os.getpid(), {key: value for key, value in identity.items() if key != field})


def test_forged_runner_record_reports_unknown_owner_without_stop_or_start(runner_root, monkeypatch):
    root = runner_root.root
    write_runner_record(root, _FUND, "state", _state(root, status="running", build_id="forged-build"))
    manager = OwnedRunnerManager(root, runner_root.admission)
    launches = []
    monkeypatch.setattr(owned_runner.subprocess, "Popen", lambda *args, **kwargs: launches.append(args))

    status = manager.status(_FUND)

    assert status["status"] == "unknown"
    assert status["available"] is False
    assert status["reason"] == "runner ownership record is invalid"
    with pytest.raises(RunnerOwnershipUnknown):
        manager.request_stop(_FUND)
    assert not os.path.exists(root.resolve(_control_path()))
    assert launches == []


def test_legacy_runner_pid_is_unknown_ownership_and_never_adopted(runner_root, monkeypatch):
    legacy = runner_root.path / "paper" / _FUND
    legacy.mkdir(parents=True)
    (legacy / "runner.pid").write_text(str(os.getpid()), encoding="utf-8")
    manager = OwnedRunnerManager(runner_root.root, runner_root.admission)
    launches = []
    monkeypatch.setattr(owned_runner.subprocess, "Popen", lambda *args, **kwargs: launches.append(args))

    status = manager.status(_FUND)

    assert status["status"] == "unknown"
    assert status["reason"] == "legacy runner presence is unverified"
    with pytest.raises(RunnerOwnershipUnknown):
        manager.request_stop(_FUND)
    assert (legacy / "runner.pid").read_text(encoding="utf-8") == str(os.getpid())
    assert launches == []


def test_unrelated_live_pid_is_never_adopted_signalled_or_stopped(runner_root, monkeypatch):
    root = runner_root.root
    unrelated = subprocess.Popen(_sleeping_command(token_urlsafe(8)), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        identity = process_identity(unrelated.pid)
        write_runner_record(root, _FUND, "state", _state(root, status="running", pid=unrelated.pid, process_identity=identity))
        manager = OwnedRunnerManager(root, runner_root.admission)
        launches = []
        monkeypatch.setattr(owned_runner.subprocess, "Popen", lambda *args, **kwargs: launches.append(args))

        with runner_root.admission.runner_reservation(_FUND, timeout=5):
            status = manager.status(_FUND)
            with pytest.raises(RunnerOwnershipUnknown):
                manager.request_stop(_FUND)

        assert status["status"] == "unknown"
        assert status["available"] is False
        assert "owner record" in status["reason"]
        assert "pid" not in status and "process_identity" not in status
        assert not os.path.exists(root.resolve(_control_path()))
        assert launches == []
        assert unrelated.poll() is None
    finally:
        unrelated.kill()
        unrelated.wait(30)


def test_absent_or_terminal_runner_status_never_starts_a_process(runner_root, monkeypatch):
    root = runner_root.root
    manager = OwnedRunnerManager(root, runner_root.admission)
    launches = []
    monkeypatch.setattr(owned_runner.subprocess, "Popen", lambda *args, **kwargs: launches.append(args))

    assert manager.status(_FUND)["status"] == "stopped"
    identity = current_process_identity()
    write_runner_record(root, _FUND, "state", _state(root, status="completed", pid=identity["pid"], process_identity=identity))
    assert manager.status(_FUND)["status"] == "completed"
    with pytest.raises(RunnerOwnershipUnknown):
        manager.request_stop(_FUND)

    assert launches == []


def _launch(context: RootContext, nonce: str, **overrides) -> dict:
    launch = {
        "schema": 1,
        "protocol_version": PROTOCOL_VERSION,
        "build_id": code_version(),
        "root": root_binding(context),
        "fund": _FUND,
        "nonce": nonce,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "capture": {"subject_id": _FUND, "forged": True},
        "authorization": {"operation_id": "c" * 32, "operation_digest": "d" * 64},
    }
    launch.update(overrides)
    return launch


def _handshake(context: RootContext, *, launch_ready: bool, nonce: str | None = None, **launch_overrides) -> str:
    nonce = nonce or token_urlsafe(32)
    nonce_hash = hashlib.sha256(nonce.encode("utf-8")).hexdigest()
    identity = current_process_identity()
    write_runner_record(context, _FUND, "launch", _launch(context, nonce, **launch_overrides))
    write_runner_record(context, _FUND, "state", _state(context, nonce_hash=nonce_hash, pid=identity["pid"], process_identity=identity))
    common = {key: value for key, value in _state(context).items() if key in {"schema", "protocol_version", "build_id", "root", "fund"}}
    write_runner_record(context, _FUND, "control", {**common, "nonce_hash": nonce_hash, "launch_ready": launch_ready, "stop_requested": False, "requested_at": None})
    return nonce_hash


@pytest.mark.parametrize(
    "overrides",
    [
        {"build_id": "foreign-build"},
        {"protocol_version": PROTOCOL_VERSION + 1},
        {"fund": "other-deployment"},
        {"root": "copied-root"},
        {"nonce": "short"},
        {"schema": 2},
    ],
    ids=["build", "protocol", "deployment", "root", "nonce", "schema"],
)
def test_child_bootstrap_rejects_foreign_launch_binding_before_any_effect(runner_root, overrides):
    root = runner_root.root
    _handshake(root, launch_ready=True, **overrides)
    before = sorted(path.name for path in (runner_root.path / "paper").glob("*")) if (runner_root.path / "paper").exists() else []

    with pytest.raises(OwnedRunnerError, match="bootstrap identity is invalid"):
        run_owned_runner(root, _FUND)

    after = sorted(path.name for path in (runner_root.path / "paper").glob("*")) if (runner_root.path / "paper").exists() else []
    assert after == before
    assert read_runner_record(root, _FUND, "state")["status"] == "starting"


def test_child_handshake_times_out_without_launch_confirmation(runner_root):
    root = runner_root.root
    nonce_hash = _handshake(root, launch_ready=False)

    with pytest.raises(OwnedRunnerError, match="authorization timed out"):
        _wait_for_launch(root, _FUND, nonce_hash, timeout=0.1)

    assert read_runner_record(root, _FUND, "state")["status"] == "starting"


def test_child_handshake_rejects_stop_and_foreign_incarnation(runner_root):
    root = runner_root.root
    nonce_hash = _handshake(root, launch_ready=True)
    other = {**current_process_identity(), "creation_time": "another-incarnation"}
    write_runner_record(root, _FUND, "state", {**read_runner_record(root, _FUND, "state"), "process_identity": other})

    with pytest.raises(OwnedRunnerError, match="process identity does not match"):
        _wait_for_launch(root, _FUND, nonce_hash, timeout=1.0)
    with pytest.raises(OwnedRunnerError, match="launch control is invalid"):
        _wait_for_launch(root, _FUND, "b" * 64, timeout=1.0)

    control = read_runner_record(root, _FUND, "control")
    write_runner_record(root, _FUND, "control", {**control, "stop_requested": True, "requested_at": datetime.now(timezone.utc).isoformat()})
    with pytest.raises(OwnedRunnerError, match="launch was stopped"):
        _wait_for_launch(root, _FUND, nonce_hash, timeout=1.0)


def test_child_rejects_forged_capture_after_confirmed_handshake(runner_root):
    root = runner_root.root
    _handshake(root, launch_ready=True)

    with pytest.raises(OwnedRunnerError, match="runner capture is invalid"):
        run_owned_runner(root, _FUND)
    _handshake(root, launch_ready=True, capture="not-a-capture")
    with pytest.raises(OwnedRunnerError, match="runner capture is invalid"):
        run_owned_runner(root, _FUND)

    assert read_runner_record(root, _FUND, "state")["status"] == "starting"


def _spec(**overrides) -> FundSpec:
    raw = {
        "schema_version": 2,
        "name": _FUND,
        "strategies": [{"name": "solo", "models": [{"name": "pead"}], "blend": {"mode": "long_short"}}],
        "risk": {"max_position_pct": 1, "max_gross_exposure": 1},
        "capital": 100_000,
        "rebalance": "daily",
    }
    raw.update(overrides)
    return FundSpec.model_validate(raw)


def _deployed_capture(context: RootContext, admission: AdmissionCoordinator, **capture_overrides):
    with admission.deployment_lock(_FUND, timeout=0):
        deploy(_FUND, _spec(), ["AAPL"], root=context.path / "paper")
    reviewed = _spec(**capture_overrides)
    settings = resolve_settings(context, launch={"data_provider": "yfinance", "model": "gemma3:4b", "endpoint": "http://127.0.0.1:11434"})
    return freeze_capture(
        root=context,
        subject_id=reviewed.name,
        mandate_digest=mandate_hash(reviewed),
        universe=("AAPL",),
        broker="paper",
        settings=settings,
        credential_versions={},
        code_version=code_version(),
        mandate_snapshot=reviewed.model_dump(mode="json"),
    )


@pytest.mark.parametrize(
    "binding,expected",
    [
        ({"name": "other-deployment"}, "capture does not match the deployment"),
        ({"capital": 50_000}, "deployment changed after review"),
    ],
    ids=["deployment", "mandate"],
)
def test_child_rejects_capture_bound_to_another_deployment_or_mandate(runner_root, binding, expected):
    root = runner_root.root
    capture = _deployed_capture(root, runner_root.admission, **binding)
    ledger_path = runner_root.path / "paper" / _FUND / "ledger.jsonl"
    before = ledger_path.read_bytes() if ledger_path.exists() else None
    _handshake(root, launch_ready=True, capture=json.loads(capture.private_bytes().decode("utf-8")))

    with pytest.raises(OwnedRunnerError, match=expected):
        run_owned_runner(root, _FUND)

    assert (ledger_path.read_bytes() if ledger_path.exists() else None) == before
    assert read_runner_record(root, _FUND, "state")["status"] == "starting"
