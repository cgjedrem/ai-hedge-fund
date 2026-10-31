import time
from contextlib import contextmanager
from pathlib import Path

import pytest

from hedge_fund.runtime.admission import AdmissionCoordinator, AdmissionError, LOCK_DIRECTORY, OwnershipState, OwnershipUnknown, WriterConflict
from hedge_fund.runtime.root import RootContext


@pytest.fixture
def admission_root(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    context = RootContext.open(root)
    coordinator = AdmissionCoordinator(
        context,
        ownership=OwnershipState.VERIFIED,
    )
    yield root, context, coordinator
    context.close()


def _wait_for(path: Path, process, timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while not path.exists():
        if process.poll() is not None:
            raise AssertionError(f"owned child exited early: {process.returncode}")
        if time.monotonic() >= deadline:
            raise TimeoutError(f"owned child did not create {path.name}")
        time.sleep(0.01)


def _holding_child_script(
    root: Path,
    ready: Path,
    release: Path,
    method: str,
    resource: str | None,
) -> str:
    timeout = 0.1 if method == "control_lane" else 1.0
    lease_call = f"coordinator.{method}({resource!r}, timeout={timeout})" if resource is not None else f"coordinator.{method}(timeout={timeout})"
    return "\n".join(
        [
            "import time",
            "from pathlib import Path",
            "from hedge_fund.runtime.admission import AdmissionCoordinator, OwnershipState",
            "from hedge_fund.runtime.root import RootContext",
            f"context = RootContext.open({str(root)!r})",
            "coordinator = AdmissionCoordinator(context, ownership=OwnershipState.VERIFIED)",
            f"lease = {lease_call}",
            "lease.__enter__()",
            f"Path({str(ready)!r}).write_text('ready', encoding='utf-8')",
            "deadline = time.monotonic() + 10.0",
            f"while not Path({str(release)!r}).exists() and time.monotonic() < deadline:",
            "    time.sleep(0.01)",
            "lease.__exit__(None, None, None)",
            "context.close()",
        ]
    )


def test_multi_deployment_acquires_registry_then_sorted_identities(admission_root, monkeypatch):
    _root, _context, coordinator = admission_root
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


def test_multi_deployment_rejects_canonical_aliases_before_lock_state(admission_root):
    root, _context, coordinator = admission_root

    with pytest.raises(AdmissionError):
        with coordinator.multi_deployment(["Alpha", "alpha.yaml"]):
            pass

    assert not (root / "runtime" / "admission").exists()


@pytest.mark.parametrize(
    ("method", "resource"),
    [("registry_lock", None), ("deployment_lock", "alpha")],
)
def test_registry_and_deployment_locks_contend_across_processes(admission_root, owned_test_process, tmp_path, method, resource):
    root, _context, coordinator = admission_root
    ready = tmp_path / f"{method}-ready"
    release = tmp_path / f"{method}-release"
    child = owned_test_process(_holding_child_script(root, ready, release, method, resource))

    try:
        _wait_for(ready, child)
        started = time.monotonic()
        with pytest.raises(WriterConflict):
            if resource is None:
                with coordinator.registry_lock(timeout=0.05):
                    pass
            else:
                with coordinator.deployment_lock(resource, timeout=0.05):
                    pass
        assert time.monotonic() - started < 0.5
    finally:
        release.write_text("release", encoding="utf-8")

    assert child.wait(timeout=10) == 0


def test_independent_fund_runs_while_other_runner_is_reserved(admission_root, owned_test_process, tmp_path):
    root, _context, coordinator = admission_root
    ready = tmp_path / "runner-ready"
    release = tmp_path / "runner-release"
    child = owned_test_process(
        _holding_child_script(
            root,
            ready,
            release,
            "runner_reservation",
            "alpha",
        )
    )

    try:
        _wait_for(ready, child)
        with coordinator.control_lane("alpha", timeout=0.1):
            pass

        with pytest.raises(WriterConflict):
            with coordinator.manual_session("alpha", timeout=0.05):
                pass

        with coordinator.manual_session("beta", timeout=0.5):
            assert child.poll() is None
    finally:
        release.write_text("release", encoding="utf-8")

    assert child.wait(timeout=10) == 0


def test_crashed_process_releases_execution_lock(admission_root, owned_test_process, tmp_path):
    root, _context, coordinator = admission_root
    acquired = tmp_path / "crash-lock-acquired"
    script = "\n".join(
        [
            "import os",
            "from pathlib import Path",
            "from hedge_fund.runtime.admission import AdmissionCoordinator, OwnershipState",
            "from hedge_fund.runtime.root import RootContext",
            f"context = RootContext.open({str(root)!r})",
            "coordinator = AdmissionCoordinator(context, ownership=OwnershipState.VERIFIED)",
            "lease = coordinator.execution_lease('alpha', timeout=1.0)",
            "lease.__enter__()",
            f"Path({str(acquired)!r}).write_text('locked', encoding='utf-8')",
            "os._exit(0)",
        ]
    )
    child = owned_test_process(script)

    _wait_for(acquired, child)
    assert child.wait(timeout=10) == 0

    with coordinator.execution_lease("alpha", timeout=0.5):
        pass


@pytest.mark.parametrize(
    "ownership",
    [None, OwnershipState.UNKNOWN, OwnershipState.LEGACY],
)
def test_unverified_owner_denies_before_creating_lock_state(tmp_path, ownership):
    root = tmp_path / "root"
    root.mkdir()

    with RootContext.open(root) as context:
        if ownership is None:
            coordinator = AdmissionCoordinator(context)
        else:
            coordinator = AdmissionCoordinator(context, ownership=ownership)

        with pytest.raises(OwnershipUnknown):
            with coordinator.manual_session("alpha", timeout=0):
                pass

    assert not (root / "runtime" / "admission").exists()


def test_registry_read_lock_uses_existing_lock_without_writer_authority(tmp_path):
    root = tmp_path / "root"
    root.mkdir()

    with RootContext.open(root) as context:
        writer = AdmissionCoordinator(context, ownership=OwnershipState.VERIFIED)
        with writer.registry_lock(timeout=0):
            pass
        observer = AdmissionCoordinator(context, ownership=OwnershipState.UNKNOWN)
        before = {path.relative_to(root) for path in root.rglob("*")}

        with observer.registry_read_lock(timeout=0):
            pass

        after = {path.relative_to(root) for path in root.rglob("*")}

    assert after == before


def test_registry_read_lock_does_not_create_missing_lock_state(tmp_path):
    root = tmp_path / "root"
    root.mkdir()

    with RootContext.open(root) as context:
        observer = AdmissionCoordinator(context, ownership=OwnershipState.UNKNOWN)

        with pytest.raises(AdmissionError):
            with observer.registry_read_lock(timeout=0):
                pass

    assert not (root / LOCK_DIRECTORY).exists()


@pytest.mark.parametrize("identity", ["../outside", r"C:\outside", ""])
def test_invalid_deployment_identity_denies_before_lock_state(admission_root, identity):
    root, _context, coordinator = admission_root

    with pytest.raises(AdmissionError):
        with coordinator.execution_lease(identity):
            pass

    assert not (root / "runtime" / "admission").exists()


@pytest.mark.parametrize(
    "timeout",
    [True, -0.01, float("nan"), float("inf"), 5.01],
)
def test_invalid_manual_timeout_denies_before_lock_state(admission_root, timeout):
    root, _context, coordinator = admission_root

    with pytest.raises(ValueError):
        with coordinator.manual_session("alpha", timeout=timeout):
            pass

    assert not (root / "runtime" / "admission").exists()


def test_control_lane_timeout_has_a_hard_upper_bound(admission_root):
    root, _context, coordinator = admission_root

    with pytest.raises(ValueError):
        with coordinator.control_lane("alpha", timeout=0.51):
            pass

    assert not (root / "runtime" / "admission").exists()


def test_control_lane_is_independent_and_has_a_bounded_wait(admission_root, owned_test_process, tmp_path):
    root, _context, coordinator = admission_root
    ready = tmp_path / "control-ready"
    release = tmp_path / "control-release"
    child = owned_test_process(
        _holding_child_script(
            root,
            ready,
            release,
            "control_lane",
            "alpha",
        )
    )

    try:
        _wait_for(ready, child)
        started = time.monotonic()
        with pytest.raises(WriterConflict):
            with coordinator.control_lane("alpha", timeout=0.05):
                pass
        assert time.monotonic() - started < 0.5
    finally:
        release.write_text("release", encoding="utf-8")

    assert child.wait(timeout=10) == 0
