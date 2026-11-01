import time
from contextlib import contextmanager
from pathlib import Path

import pytest

from hedge_fund.runtime.admission import (
    AdmissionCoordinator,
    AdmissionError,
    LOCK_DIRECTORY,
    OwnershipUnknown,
    RootOwnerLease,
    WriterConflict,
)
from hedge_fund.runtime.root import PRIVATE_ROOT, RootContext


@pytest.fixture
def admission_root(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    context = RootContext.open(root)
    context.prepare_private_storage()
    owner_lease = RootOwnerLease.acquire(context)
    coordinator = AdmissionCoordinator(context, owner_lease=owner_lease)
    try:
        yield root, context, owner_lease, coordinator
    finally:
        owner_lease.close()
        context.close()


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


def test_multi_deployment_rejects_canonical_aliases_before_lane_creation(admission_root):
    root, _context, _owner, coordinator = admission_root

    with pytest.raises(AdmissionError):
        with coordinator.multi_deployment(["Alpha", "alpha.yaml"]):
            pass

    assert not list((root / LOCK_DIRECTORY).glob("deployment-*.lock"))


def test_second_process_cannot_claim_root_owner_lease(
    admission_root,
    owned_test_process,
    tmp_path,
):
    root, _context, _owner, _coordinator = admission_root
    result = tmp_path / "owner-conflict"
    script = "\n".join(
        [
            "from pathlib import Path",
            "from hedge_fund.runtime.admission import RootOwnerLease, WriterConflict",
            "from hedge_fund.runtime.root import RootContext",
            f"context = RootContext.open({str(root)!r})",
            "try:",
            "    try:",
            "        RootOwnerLease.acquire(context, timeout=0)",
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
