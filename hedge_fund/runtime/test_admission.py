import os
import signal
import time
from contextlib import contextmanager
from pathlib import Path
from threading import current_thread, Event, Thread

import pytest

from hedge_fund.runtime.admission import AdmissionCoordinator, AdmissionError, LOCK_DIRECTORY, OwnershipUnknown, require_paper_write_lanes, RootMigrationLease, RootOwnerLease, WriterConflict
from hedge_fund.runtime.handover import enroll_fresh
from hedge_fund.runtime.root import PRIVATE_ROOT, RootContext


def test_standalone_control_rejects_an_inherited_process_identity(tmp_path, monkeypatch):
    from hedge_fund.runtime import admission

    directory = tmp_path / "standalone"
    directory.mkdir()
    original_getpid = os.getpid
    with admission.paper_control_transition(directory, directory.name):
        with monkeypatch.context() as child:
            child.setattr(admission.os, "getpid", lambda: original_getpid() + 1)
            with pytest.raises(AdmissionError, match="fresh interpreter after fork"):
                with admission.paper_control_transition(directory, directory.name):
                    pass
    with admission.paper_control_transition(directory, directory.name):
        pass


@pytest.mark.skipif(not hasattr(os, "fork"), reason="POSIX fork is unavailable")
def test_forked_standalone_child_cannot_reenter_parent_control(tmp_path):
    from hedge_fund.runtime import admission

    directory = tmp_path / "standalone"
    directory.mkdir()
    with admission.paper_control_transition(directory, directory.name):
        pid = os.fork()
        if pid == 0:
            try:
                with admission.paper_control_transition(directory, directory.name):
                    os._exit(1)
            except AdmissionError:
                os._exit(0)
            except BaseException:
                os._exit(2)
        _, status = os.waitpid(pid, 0)
    assert os.WIFEXITED(status) and os.WEXITSTATUS(status) == 0


def test_enrolled_admission_rejects_an_inherited_process_identity(admission_root, monkeypatch):
    from hedge_fund.runtime import admission

    _root, context, owner, coordinator = admission_root
    original_getpid = os.getpid
    with coordinator.manual_session("alpha", timeout=0):
        with monkeypatch.context() as child:
            child.setattr(admission.os, "getpid", lambda: original_getpid() + 1)
            with pytest.raises(AdmissionError, match="fresh interpreter after fork"):
                coordinator.lane_is_held("runner", "alpha")
            with pytest.raises(AdmissionError, match="fresh interpreter after fork"):
                owner.matches(context)
            with pytest.raises(AdmissionError, match="fresh interpreter after fork"):
                with owner:
                    pass
        assert owner.matches(context)


def test_inherited_owner_cleanup_closes_only_the_child_handle(admission_root, monkeypatch):
    from hedge_fund.runtime import admission

    _root, context, _owner, _coordinator = admission_root

    class ChildHandle:
        closed = 0

        def close(self):
            self.closed += 1

    class InheritedGuard:
        def __enter__(self):
            pytest.fail("child attempted to acquire the inherited owner mutex")

    handle = ChildHandle()
    owner = RootOwnerLease(context, handle, object())
    owner._guard = InheritedGuard()
    original_getpid = os.getpid
    with monkeypatch.context() as child:
        child.setattr(admission.os, "getpid", lambda: original_getpid() + 1)
        child.setattr(admission, "_release_os_lock", lambda *_args: pytest.fail("child unlocked parent"))
        owner.close()
        owner.close()
    assert handle.closed == 1


@pytest.mark.skipif(not hasattr(os, "fork"), reason="POSIX fork is unavailable")
def test_forked_owner_close_preserves_parent_lock_and_releases_child_copy(tmp_path, admission_root, owned_test_process):
    root_path, _context, owner, _coordinator = admission_root
    ready = tmp_path / "child-owner-closed"
    release = tmp_path / "release-owner-child"
    pid = os.fork()
    if pid == 0:
        try:
            owner.close()
            ready.write_text("closed", encoding="utf-8")
            deadline = time.monotonic() + 30
            while not release.exists() and time.monotonic() < deadline:
                time.sleep(0.01)
            os._exit(0 if release.exists() else 3)
        except BaseException:
            os._exit(2)
    try:
        deadline = time.monotonic() + 10
        while not ready.exists() and time.monotonic() < deadline:
            waited, _status = os.waitpid(pid, os.WNOHANG)
            if waited:
                pid = None
                pytest.fail("child could not close its inherited owner handle")
            time.sleep(0.01)
        assert ready.exists(), "child blocked while closing its inherited owner handle"

        script = f"""
from pathlib import Path
from hedge_fund.runtime.admission import RootMigrationLease, WriterConflict
from hedge_fund.runtime.root import RootContext
with RootContext.open(Path({str(root_path)!r})) as root:
    try:
        with RootMigrationLease.acquire(root, timeout=0):
            acquired = True
    except WriterConflict:
        acquired = False
assert acquired is EXPECTED
"""
        contender = owned_test_process(script.replace("EXPECTED", "False"))
        assert contender.wait(timeout=30) == 0
        owner.close()
        contender = owned_test_process(script.replace("EXPECTED", "True"))
        assert contender.wait(timeout=30) == 0
    finally:
        release.write_text("release", encoding="utf-8")
        if pid is not None:
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                waited, _status = os.waitpid(pid, os.WNOHANG)
                if waited:
                    pid = None
                    break
                time.sleep(0.01)
            if pid is not None:
                os.kill(pid, signal.SIGKILL)
                os.waitpid(pid, 0)


@pytest.mark.parametrize("operation", ["construct", "registry_read"])
def test_inherited_coordinator_rejects_before_root_mutex(admission_root, monkeypatch, operation):
    from hedge_fund.runtime import admission

    _root, context, owner, coordinator = admission_root
    original_getpid = os.getpid
    with monkeypatch.context() as child:
        child.setattr(admission.os, "getpid", lambda: original_getpid() + 1)
        child.setattr(context, "revalidate", lambda: pytest.fail("inherited root mutex was reached"))
        with pytest.raises(OwnershipUnknown, match="fresh interpreter after fork"):
            if operation == "construct":
                AdmissionCoordinator(context, owner_lease=owner)
            else:
                with coordinator.registry_read_lock(timeout=0):
                    pass


@pytest.mark.skipif(not hasattr(os, "fork"), reason="POSIX fork is unavailable")
def test_forked_child_cannot_reuse_enrolled_parent_lanes(admission_root):
    _root, _context, _owner, coordinator = admission_root
    with coordinator.manual_session("alpha", timeout=0):
        pid = os.fork()
        if pid == 0:
            try:
                coordinator.lane_is_held("runner", "alpha")
                os._exit(1)
            except AdmissionError:
                os._exit(0)
            except BaseException:
                os._exit(2)
        _, status = os.waitpid(pid, 0)
    assert os.WIFEXITED(status) and os.WEXITSTATUS(status) == 0


@pytest.mark.parametrize("lane", ["standalone", "registry", "registry_read", "manual"])
@pytest.mark.parametrize("exceptional", [False, True])
def test_inherited_context_cleanup_does_not_unlock_parent(tmp_path, admission_root, monkeypatch, lane, exceptional):
    from hedge_fund.runtime import admission

    _root, _context, _owner, coordinator = admission_root
    directory = tmp_path / "standalone"
    directory.mkdir()
    if lane == "registry_read":
        with coordinator.registry_lock(timeout=0):
            pass
    managers = {
        "standalone": lambda: admission.paper_control_transition(directory, directory.name),
        "registry": lambda: coordinator.registry_lock(timeout=0),
        "registry_read": lambda: coordinator.registry_read_lock(timeout=0),
        "manual": lambda: coordinator.manual_session("alpha", timeout=0),
    }
    initial_keys = set(admission._LOCAL_LANES)
    manager = managers[lane]()
    manager.__enter__()
    created_keys = set(admission._LOCAL_LANES) - initial_keys
    releases = []
    original_getpid = os.getpid
    try:
        with monkeypatch.context() as child:
            child.setattr(admission.os, "getpid", lambda: original_getpid() + 1)
            child.setattr(admission, "_release_os_lock", lambda *_args: releases.append("unlock"))
            if exceptional:
                error = RuntimeError("child failure")
                assert manager.__exit__(RuntimeError, error, None) is False
            else:
                assert manager.__exit__(None, None, None) is False
    finally:
        with admission._LOCAL_LANES_GUARD:
            for key in created_keys:
                admission._LOCAL_LANES.pop(key, None)
        held = admission._held_locks()
        for key in created_keys:
            held.pop(key, None)
    assert releases == []


@pytest.mark.skipif(not hasattr(os, "fork"), reason="POSIX fork is unavailable")
@pytest.mark.parametrize("lane", ["standalone", "registry", "registry_read", "manual"])
def test_forked_child_unwind_keeps_parent_lock(tmp_path, admission_root, owned_test_process, lane):
    from hedge_fund.runtime import admission

    root_path, _context, _owner, coordinator = admission_root
    directory = tmp_path / "standalone"
    directory.mkdir()
    if lane == "registry_read":
        with coordinator.registry_lock(timeout=0):
            pass
    managers = {
        "standalone": lambda: admission.paper_control_transition(directory, directory.name),
        "registry": lambda: coordinator.registry_lock(timeout=0),
        "registry_read": lambda: coordinator.registry_read_lock(timeout=0),
        "manual": lambda: coordinator.manual_session("alpha", timeout=0),
    }
    manager = managers[lane]()
    manager.__enter__()
    pid = None
    try:
        pid = os.fork()
        if pid == 0:
            try:
                manager.__exit__(None, None, None)
            except BaseException:
                os._exit(2)
            os._exit(0)
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            waited, status = os.waitpid(pid, os.WNOHANG)
            if waited:
                pid = None
                assert os.WIFEXITED(status) and os.WEXITSTATUS(status) == 0
                break
            time.sleep(0.01)
        else:
            pytest.fail("child blocked while unwinding inherited admission")
        script = f"""
from pathlib import Path
from hedge_fund.runtime.admission import AdmissionCoordinator, RootOwnerLease, WriterConflict, paper_control_transition
from hedge_fund.runtime.root import RootContext

kind = {lane!r}
try:
    if kind == "standalone":
        with paper_control_transition(Path({str(directory)!r}), "standalone"):
            raise AssertionError("parent's control lane was released")
    else:
        with RootContext.open(Path({str(root_path)!r})) as root:
            with RootOwnerLease.acquire(root) as owner:
                coordinator = AdmissionCoordinator(root, owner_lease=owner)
                target = coordinator.manual_session("alpha", timeout=0) if kind == "manual" else coordinator.registry_lock(timeout=0)
                with target:
                    raise AssertionError("parent's admission lane was released")
except WriterConflict:
    pass
"""
        contender = owned_test_process(script)
        assert contender.wait(timeout=15) == 0
    finally:
        if pid:
            os.kill(pid, signal.SIGKILL)
            os.waitpid(pid, 0)
        manager.__exit__(None, None, None)


@pytest.fixture
def admission_root(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    context = RootContext.open(root)
    enroll_fresh(context)
    owner_lease = RootOwnerLease.acquire(context)
    coordinator = AdmissionCoordinator(context, owner_lease=owner_lease)
    try:
        yield root, context, owner_lease, coordinator
    finally:
        owner_lease.close()
        context.close()


def test_unattested_protected_fund_denies_admission_without_state_changes(admission_root):
    root_path, context, _owner_lease, _coordinator = admission_root
    handover_bytes = context.read_bytes("runtime/private/v1/handover.json")

    with pytest.raises(AdmissionError, match="destination-bound attestation"):
        require_paper_write_lanes(
            root_path / "paper" / "umbrella",
            "umbrella",
            lane_sets=(("control",),),
        )

    assert context.read_bytes("runtime/private/v1/handover.json") == handover_bytes
    assert not (root_path / "paper").exists()


def _wait_for(path: Path, process, timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while not path.exists():
        if process.poll() is not None:
            raise AssertionError(f"owned child exited early: {process.returncode}")
        if time.monotonic() >= deadline:
            raise TimeoutError(f"owned child did not create {path.name}")
        time.sleep(0.01)


def test_multi_deployment_acquires_registry_then_sorted_identities(admission_root, monkeypatch):
    _root, _context, _owner, coordinator = admission_root
    acquired = []
    original_lock = coordinator._lock

    @contextmanager
    def observe_lock(key, *, timeout):
        acquired.append(key)
        with original_lock(key, timeout=timeout):
            yield

    monkeypatch.setattr(coordinator, "_lock", observe_lock)

    with coordinator.multi_deployment(["Beta", "alpha"]):
        pass

    assert acquired == ["registry", "deployment:alpha", "deployment:beta"]


def test_registry_waiting_writer_cannot_be_overtaken_by_status_reader(admission_root, monkeypatch):
    import hedge_fund.runtime.admission as admission

    _root, context, owner, coordinator = admission_root
    observer = AdmissionCoordinator(context, owner_lease=owner)
    with coordinator.registry_lock():
        pass
    writer_at_native_lock = Event()
    release_writer = Event()
    reader_started = Event()
    reader_entered = Event()
    order = []
    errors = []
    try_lock = admission._try_acquire_os_lock

    def pause_writer(handle, *, exclusive=True):
        if current_thread().name == "queued-writer":
            writer_at_native_lock.set()
            assert release_writer.wait(timeout=5)
        return try_lock(handle, exclusive=exclusive)

    monkeypatch.setattr(admission, "_try_acquire_os_lock", pause_writer)

    def writer():
        try:
            with coordinator.registry_lock(timeout=5):
                order.append("writer")
        except BaseException as exc:
            errors.append(exc)

    def reader():
        reader_started.set()
        try:
            with observer.registry_read_lock(timeout=5):
                order.append("reader")
                reader_entered.set()
        except BaseException as exc:
            errors.append(exc)

    first = Thread(target=writer, name="queued-writer")
    second = Thread(target=reader, name="later-status-reader")
    first.start()
    try:
        assert writer_at_native_lock.wait(timeout=5)
        second.start()
        assert reader_started.wait(timeout=5)
        assert not reader_entered.wait(timeout=1), "status reader bypassed a pending writer"
    finally:
        release_writer.set()
        first.join(timeout=5)
        if second.ident is not None:
            second.join(timeout=5)
    assert not first.is_alive() and not second.is_alive()
    assert errors == []
    assert order == ["writer", "reader"]


def test_timed_out_local_waiter_preserves_holder_and_releases_queue(admission_root):
    import hedge_fund.runtime.admission as admission

    _root, context, _owner, coordinator = admission_root
    key = admission._thread_lock_key(context, f"{LOCK_DIRECTORY}/registry.lock")
    with coordinator.registry_lock():
        attempted = Event()
        completed = Event()
        result = []

        def wait_for_held_lane():
            attempted.set()
            try:
                with coordinator.registry_lock(timeout=0):
                    result.append("admitted")
            except WriterConflict as exc:
                result.append(exc)
            finally:
                completed.set()

        waiter = Thread(target=wait_for_held_lane, name="timed-out-local-waiter")
        waiter.start()
        assert attempted.wait(timeout=5)
        assert completed.wait(timeout=5)
        waiter.join(timeout=5)
        assert not waiter.is_alive()
        assert len(result) == 1 and isinstance(result[0], WriterConflict)
        assert coordinator.lane_is_held("registry")
        assert len(admission._LOCAL_LANES[key]) == 1
        with coordinator.registry_read_lock():
            assert coordinator.lane_is_held("registry")
    assert key not in admission._LOCAL_LANES
    with coordinator.registry_lock():
        assert coordinator.lane_is_held("registry")
    assert key not in admission._LOCAL_LANES


def test_multi_deployment_rejects_canonical_aliases_before_lane_creation(admission_root):
    root, _context, _owner, coordinator = admission_root

    with pytest.raises(AdmissionError):
        with coordinator.multi_deployment(["Alpha", "alpha.yaml"]):
            pass

    assert not list((root / LOCK_DIRECTORY).glob("deployment-*.lock"))


def test_second_process_can_join_shared_root_participants(
    admission_root,
    owned_test_process,
    tmp_path,
):
    root, _context, _owner, _coordinator = admission_root
    result = tmp_path / "participant-ready"
    script = "\n".join(
        [
            "from pathlib import Path",
            "from hedge_fund.runtime.admission import RootOwnerLease",
            "from hedge_fund.runtime.root import RootContext",
            f"context = RootContext.open({str(root)!r})",
            "try:",
            "    lease = RootOwnerLease.acquire(context, timeout=0)",
            f"    Path({str(result)!r}).write_text('joined', encoding='utf-8')",
            "    lease.close()",
            "finally:",
            "    context.close()",
        ]
    )
    child = owned_test_process(script)

    _wait_for(result, child)

    assert child.wait(timeout=10) == 0
    assert result.read_text(encoding="utf-8") == "joined"


def test_exclusive_migration_cannot_join_active_root_participant(
    admission_root,
    owned_test_process,
    tmp_path,
):
    root, _context, _owner, _coordinator = admission_root
    result = tmp_path / "migration-conflict"
    script = "\n".join(
        [
            "from pathlib import Path",
            "from hedge_fund.runtime.admission import RootMigrationLease, WriterConflict",
            "from hedge_fund.runtime.root import RootContext",
            f"context = RootContext.open({str(root)!r})",
            "try:",
            "    try:",
            "        RootMigrationLease.acquire(context, timeout=0)",
            "    except WriterConflict:",
            f"        Path({str(result)!r}).write_text('conflict', encoding='utf-8')",
            "    else:",
            "        raise SystemExit(2)",
            "finally:",
            "    context.close()",
        ]
    )
    child = owned_test_process(script)

    _wait_for(result, child)

    assert child.wait(timeout=10) == 0
    assert result.read_text(encoding="utf-8") == "conflict"


def test_subject_sessions_conflict_while_controls_remain_independent(admission_root):
    _root, _context, _owner, coordinator = admission_root

    with coordinator.manual_session("alpha", timeout=0.1):
        with coordinator.control_lane("alpha", timeout=0.1):
            pass
        with pytest.raises(WriterConflict):
            with coordinator.manual_session("alpha", timeout=0.05):
                pass
        with coordinator.manual_session("beta", timeout=0.1):
            pass


def test_manual_session_conflicts_with_runner_startup_deployment_lane(
    admission_root,
    owned_test_process,
    tmp_path,
):
    root, _context, _owner, coordinator = admission_root
    result = tmp_path / "manual-startup-admission"
    script = "\n".join(
        [
            "from pathlib import Path",
            "from hedge_fund.runtime.admission import AdmissionCoordinator, RootOwnerLease, WriterConflict",
            "from hedge_fund.runtime.root import RootContext",
            f"context = RootContext.open({str(root)!r})",
            "lease = RootOwnerLease.acquire(context, timeout=0)",
            "admission = AdmissionCoordinator(context, owner_lease=lease)",
            "try:",
            "    try:",
            "        with admission.manual_session('alpha', timeout=0):",
            f"            Path({str(result)!r}).write_text('entered', encoding='utf-8')",
            "    except WriterConflict:",
            f"        Path({str(result)!r}).write_text('blocked', encoding='utf-8')",
            "finally:",
            "    lease.close()",
            "    context.close()",
        ]
    )

    with coordinator.deployment_lock("alpha", timeout=0):
        child = owned_test_process(script)
        _wait_for(result, child)
        assert child.wait(timeout=10) == 0

    assert result.read_text(encoding="utf-8") == "blocked"


def test_closed_owner_lease_denies_writes_and_reacquisition_restores_them(admission_root):
    _root, context, owner_lease, coordinator = admission_root
    owner_lease.close()

    with pytest.raises(OwnershipUnknown):
        with coordinator.registry_lock(timeout=0):
            pass

    replacement = RootOwnerLease.acquire(context, timeout=0)
    try:
        replacement_coordinator = AdmissionCoordinator(
            context,
            owner_lease=replacement,
        )
        with replacement_coordinator.registry_lock(timeout=0):
            pass
    finally:
        replacement.close()


def test_participant_constructor_failure_releases_shared_native_lock(admission_root, monkeypatch):
    _root, context, owner, _coordinator = admission_root
    owner.close()
    original_init = RootOwnerLease.__init__

    def failed_init(*_args, **_kwargs):
        raise RuntimeError("synthetic lease constructor failure")

    monkeypatch.setattr(RootOwnerLease, "__init__", failed_init)
    with pytest.raises(RuntimeError, match="constructor"):
        RootOwnerLease.acquire(context, timeout=0)
    monkeypatch.setattr(RootOwnerLease, "__init__", original_init)

    migration = RootMigrationLease.acquire(context, timeout=0)
    migration.close()


def test_unowned_root_denies_mutations_without_creating_private_state(tmp_path):
    root = tmp_path / "root"
    root.mkdir()

    with RootContext.open(root) as context:
        observer = AdmissionCoordinator(context)
        with pytest.raises(OwnershipUnknown):
            with observer.manual_session("alpha", timeout=0):
                pass

    assert not (root / PRIVATE_ROOT).exists()


def test_registry_read_lock_uses_existing_lock_without_owner_authority(admission_root):
    root, context, _owner, writer = admission_root
    with writer.registry_lock(timeout=0):
        pass
    observer = AdmissionCoordinator(context)
    before = {path.relative_to(root) for path in root.rglob("*")}

    with observer.registry_read_lock(timeout=0):
        pass

    after = {path.relative_to(root) for path in root.rglob("*")}
    assert after == before


def test_registry_read_lock_does_not_create_missing_private_state(tmp_path):
    root = tmp_path / "root"
    root.mkdir()

    with RootContext.open(root) as context:
        observer = AdmissionCoordinator(context)
        with pytest.raises(AdmissionError):
            with observer.registry_read_lock(timeout=0):
                pass

    assert not (root / PRIVATE_ROOT).exists()


@pytest.mark.parametrize("identity", ["../outside", r"C:\outside", ""])
def test_invalid_deployment_identity_denies_before_lane_creation(admission_root, identity):
    root, _context, _owner, coordinator = admission_root

    with pytest.raises(AdmissionError):
        with coordinator.execution_lease(identity):
            pass

    assert not list((root / LOCK_DIRECTORY).glob("execution-*.lock"))


@pytest.mark.parametrize(
    "timeout",
    [True, -0.01, float("nan"), float("inf"), 5.01],
)
def test_invalid_manual_timeout_denies_before_lane_creation(admission_root, timeout):
    root, _context, _owner, coordinator = admission_root

    with pytest.raises(ValueError):
        with coordinator.manual_session("alpha", timeout=timeout):
            pass

    assert not list((root / LOCK_DIRECTORY).glob("runner-*.lock"))


def test_control_lane_timeout_has_a_hard_upper_bound(admission_root):
    root, _context, _owner, coordinator = admission_root

    with pytest.raises(ValueError):
        with coordinator.control_lane("alpha", timeout=0.51):
            pass

    assert not list((root / LOCK_DIRECTORY).glob("control-*.lock"))


def test_control_lane_conflict_has_a_bounded_wait(admission_root):
    _root, _context, _owner, coordinator = admission_root

    with coordinator.control_lane("alpha", timeout=0):
        started = time.monotonic()
        with pytest.raises(WriterConflict):
            with coordinator.control_lane("alpha", timeout=0.05):
                pass
        assert time.monotonic() - started < 0.5
