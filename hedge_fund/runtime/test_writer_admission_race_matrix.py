"""Spec005 T021 deterministic writer race matrix.

Each admission class from ``test_writer_inventory.py`` is exercised against the
central primitives it relies on: same-object contention, independent-object
progress, authority loss while a lane is held (legacy runner marker, legacy
alias, and removal of the out-of-band exclusion basis), snapshot serialisation
during a commit, and crash/release followed by a successful retry.

Contention uses a real second interpreter holding the OS lock (no sleeps decide
outcomes; readiness and release are file handshakes). Every root is a synthetic
root inside the test-owned harness with a synthetic HOME.
"""

from __future__ import annotations

import os
import shutil
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

import pytest

from hedge_fund import paths
from hedge_fund.runtime import admission as admission_module
from hedge_fund.runtime.admission import (
    AdmissionCoordinator,
    OwnershipUnknown,
    require_paper_write_lanes,
    root_registry_writer,
    RootOwnerLease,
    WriterConflict,
)
from hedge_fund.runtime.exclusion import (
    out_of_band_exclusion_basis,
    SYNTHETIC_TEST_OWNED,
)
from hedge_fund.runtime.handover import (
    enroll_fresh,
    require_write_authority,
    write_authority,
    WriteAuthorityDenied,
)
from hedge_fund.runtime.root import RootConfigurationError, RootContext

IDENTITY_LANES = ("deployment", "runner", "execution", "control", "halt", "audit", "research")
ALL_LANES = ("registry", *IDENTITY_LANES)
PAPER_WRITE_LANES = ("deployment", "runner", "execution", "control", "halt")


@pytest.fixture
def synthetic_home(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    for variable in ("HOME", "USERPROFILE"):
        monkeypatch.setenv(variable, str(home))
    monkeypatch.delenv("HOMEDRIVE", raising=False)
    monkeypatch.delenv("HOMEPATH", raising=False)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    return home


@pytest.fixture
def native_root(tmp_path):
    root = tmp_path / "native"
    root.mkdir()
    context = RootContext.open(root)
    enroll_fresh(context)
    owner = RootOwnerLease.acquire(context)
    coordinator = AdmissionCoordinator(context, owner_lease=owner)
    try:
        yield root, context, coordinator
    finally:
        owner.close()
        context.close()


def _lane(coordinator: AdmissionCoordinator, lane: str, identity: str = "alpha"):
    if lane == "registry":
        return coordinator.registry_lock(timeout=0)
    return getattr(coordinator, {"deployment": "deployment_lock", "runner": "runner_reservation", "execution": "execution_lease", "control": "control_lane", "halt": "halt_lane", "audit": "audit_lane", "research": "research_lane"}[lane])(identity, timeout=0)


_HOLDER = """
import sys, time
from pathlib import Path
from hedge_fund.runtime.admission import AdmissionCoordinator, RootOwnerLease
from hedge_fund.runtime.root import RootContext

root_path, lane, ready, release = Path(ROOT), LANE, Path(READY), Path(RELEASE)
methods = {"deployment": "deployment_lock", "runner": "runner_reservation", "execution": "execution_lease", "control": "control_lane", "halt": "halt_lane", "audit": "audit_lane", "research": "research_lane"}
with RootContext.open(root_path) as root:
    with RootOwnerLease.acquire(root, timeout=5) as owner:
        coordinator = AdmissionCoordinator(root, owner_lease=owner)
        target = coordinator.registry_lock(timeout=5) if lane == "registry" else getattr(coordinator, methods[lane])("alpha", timeout=0)
        with target:
            ready.write_text("held", encoding="utf-8")
            deadline = time.monotonic() + 60
            while not release.exists() and time.monotonic() < deadline:
                time.sleep(0.01)
sys.exit(0 if release.exists() else 3)
"""


@contextmanager
def _held_by_child(owned_test_process, tmp_path: Path, root: Path, lane: str):
    ready = tmp_path / f"ready-{lane}-{time.monotonic_ns()}"
    release = tmp_path / f"release-{lane}-{time.monotonic_ns()}"
    script = _HOLDER.replace("ROOT", repr(str(root))).replace("LANE", repr(lane)).replace("READY", repr(str(ready))).replace("RELEASE", repr(str(release)))
    process = owned_test_process(script)
    deadline = time.monotonic() + 30
    while not ready.exists():
        if process.poll() is not None:
            raise AssertionError(f"lane holder exited early: {process.returncode}")
        if time.monotonic() > deadline:
            raise AssertionError("lane holder did not become ready")
        time.sleep(0.01)
    yield process, release


@pytest.mark.parametrize("lane", ALL_LANES)
def test_same_object_contention_conflicts_and_crash_release_allows_retry(native_root, tmp_path, owned_test_process, lane):
    root, _context, coordinator = native_root
    with _held_by_child(owned_test_process, tmp_path, root, lane) as (process, _release):
        with pytest.raises(WriterConflict):
            with _lane(coordinator, lane):
                pytest.fail("contended lane was admitted")
        process.kill()
        process.wait(timeout=10)
    with _lane(coordinator, lane):
        assert coordinator.lane_is_held(lane, None if lane == "registry" else "alpha")


@pytest.mark.parametrize("lane", ALL_LANES)
def test_cooperative_release_allows_retry(native_root, tmp_path, owned_test_process, lane):
    root, _context, coordinator = native_root
    with _held_by_child(owned_test_process, tmp_path, root, lane) as (process, release):
        with pytest.raises(WriterConflict):
            with _lane(coordinator, lane):
                pass
        release.write_text("release", encoding="utf-8")
        assert process.wait(timeout=15) == 0
    with _lane(coordinator, lane):
        pass


@pytest.mark.parametrize("lane", IDENTITY_LANES)
def test_independent_objects_progress_while_another_object_is_held(native_root, tmp_path, owned_test_process, lane):
    root, _context, coordinator = native_root
    with _held_by_child(owned_test_process, tmp_path, root, lane) as (process, release):
        with _lane(coordinator, lane, "beta"):
            assert coordinator.lane_is_held(lane, "beta")
        release.write_text("release", encoding="utf-8")
        assert process.wait(timeout=15) == 0


def test_registry_snapshot_is_serialised_against_an_inflight_commit(native_root, tmp_path, owned_test_process):
    root, _context, coordinator = native_root
    with _held_by_child(owned_test_process, tmp_path, root, "registry") as (process, release):
        with pytest.raises(WriterConflict):
            with coordinator.registry_read_lock(timeout=0):
                pytest.fail("snapshot observed an in-flight registry commit")
        with pytest.raises(WriterConflict):
            with root_registry_writer(_context, coordinator, timeout=0):
                pass
        release.write_text("release", encoding="utf-8")
        assert process.wait(timeout=15) == 0
    with coordinator.registry_read_lock(timeout=0):
        pass


def _flip(root: Path, home: Path, how: str, monkeypatch) -> str:
    if how == "runner-pid":
        (root / "paper" / "alpha").mkdir(parents=True, exist_ok=True)
        (root / "paper" / "alpha" / "runner.pid").write_text("1", encoding="utf-8")
        return "legacy-runner-present"
    if how == "legacy-alias":
        if os.name == "nt":
            import _winapi

            _winapi.CreateJunction(str(root), str(home / ".hedge-fund"))
        else:
            os.symlink(root, home / ".hedge-fund", target_is_directory=True)
        return "legacy-home-alias"
    monkeypatch.delenv("HEDGE_FUND_TEST_MODE")
    return "out-of-band-exclusion-unproven"


@pytest.mark.parametrize("how", ["runner-pid", "legacy-alias", "exclusion-basis-removed"])
@pytest.mark.parametrize("lane", ALL_LANES)
def test_authority_flip_while_lane_is_held_denies_every_write_time_check(native_root, synthetic_home, monkeypatch, lane, how):
    root, context, coordinator = native_root
    with _lane(coordinator, lane):
        reason = _flip(root, synthetic_home, how, monkeypatch)
        assert write_authority(context) == {"authority": "ownership-unknown", "reason": reason}
        with pytest.raises(OwnershipUnknown, match=reason):
            with root_registry_writer(context, coordinator, timeout=0):
                pytest.fail("registry write admitted after authority loss")
        if lane in PAPER_WRITE_LANES:
            with pytest.raises(OwnershipUnknown, match=reason):
                require_paper_write_lanes(root / "paper" / "alpha", "alpha", lane_sets=((lane,),))
        with pytest.raises(OwnershipUnknown):
            with _lane(coordinator, "deployment", "gamma"):
                pytest.fail("new lane admitted after authority loss")


def test_authority_lost_while_waiting_for_the_os_lock_is_denied_before_admission(native_root, monkeypatch):
    root, context, coordinator = native_root
    acquire = admission_module._acquire_os_lock

    def flip_then_acquire(handle, wait, **kwargs):
        token = acquire(handle, wait, **kwargs)
        (root / "paper" / "alpha").mkdir(parents=True, exist_ok=True)
        (root / "paper" / "alpha" / "runner.pid").write_text("1", encoding="utf-8")
        return token

    monkeypatch.setattr(admission_module, "_acquire_os_lock", flip_then_acquire)
    with pytest.raises(OwnershipUnknown):
        with coordinator.deployment_lock("alpha", timeout=0):
            pytest.fail("lane admitted after authority flipped during acquisition")
    assert not coordinator.lane_is_held("deployment", "alpha")


def test_production_root_without_exclusion_proof_is_read_only(native_root, monkeypatch):
    root, context, _coordinator = native_root
    assert out_of_band_exclusion_basis(context) == SYNTHETIC_TEST_OWNED
    monkeypatch.delenv("HEDGE_FUND_TEST_MODE")
    assert out_of_band_exclusion_basis(context) is None
    assert write_authority(context) == {"authority": "ownership-unknown", "reason": "out-of-band-exclusion-unproven"}
    with pytest.raises(WriteAuthorityDenied, match="out-of-band-exclusion-unproven"):
        require_write_authority(context)
    with pytest.raises(OwnershipUnknown, match="out-of-band-exclusion-unproven"):
        RootOwnerLease.acquire(context)
    with pytest.raises(RootConfigurationError) as denied:
        paths.write_text(root / "mandates" / "alpha.yaml", "name: alpha\n")
    assert "out-of-band-exclusion-unproven" in _denial_chain(denied.value)
    assert not (root / "mandates").exists()


@pytest.mark.parametrize("mutate", ["outside-test-root", "marker-missing", "marker-content", "marker-directory", "test-root-env"])
def test_synthetic_exclusion_basis_is_bound_to_the_test_owned_harness(tmp_path, monkeypatch, mutate):
    shared = Path(os.environ["HEDGE_FUND_TEST_ROOT"])
    if mutate == "outside-test-root":
        assert out_of_band_exclusion_basis(Path(os.path.abspath(os.sep)) / "aihf-not-test-owned") is None
        assert out_of_band_exclusion_basis(shared) is None
        return
    if mutate == "test-root-env":
        root = tmp_path / "native"
        root.mkdir()
        monkeypatch.setenv("HEDGE_FUND_TEST_ROOT", str(tmp_path))
        assert out_of_band_exclusion_basis(root) is None
        return
    # Mutate a private sibling harness root, never the session's shared marker.
    sibling = shared.parent / f"spec005-test-matrix-{uuid.uuid4().hex}"
    sibling.mkdir()
    try:
        marker = sibling / ".test-owned"
        marker.write_bytes(b"test-owned\n")
        root = sibling / "native"
        root.mkdir()
        monkeypatch.setenv("HEDGE_FUND_TEST_ROOT", str(sibling))
        assert out_of_band_exclusion_basis(root) == SYNTHETIC_TEST_OWNED
        marker.unlink()
        if mutate == "marker-content":
            marker.write_text("not-owned\n", encoding="utf-8")
        elif mutate == "marker-directory":
            marker.mkdir()
        assert out_of_band_exclusion_basis(root) is None
    finally:
        shutil.rmtree(sibling)


def _denial_chain(error: BaseException) -> str:
    messages = []
    while error is not None:
        messages.append(str(error))
        error = error.__cause__ or error.__context__
    return " | ".join(messages)


def test_unconfigured_writes_into_an_enrolled_root_are_routed_through_admission(native_root, tmp_path, owned_test_process):
    root, _context, _coordinator = native_root
    assert paths.root_context(required=False) is None or paths.root_context().path != root
    target = root / "cache" / "llm" / "entry.json"
    with _held_by_child(owned_test_process, tmp_path, root, "registry") as (process, release):
        with pytest.raises(RootConfigurationError):
            paths.write_text(target, "{}")
        assert not target.exists()
        release.write_text("release", encoding="utf-8")
        assert process.wait(timeout=15) == 0
    paths.write_text(target, "{}")
    assert target.read_text(encoding="utf-8") == "{}"


def test_unconfigured_paper_write_without_a_held_lane_is_denied(native_root):
    root, _context, coordinator = native_root
    book = root / "paper" / "alpha" / "broker.json"
    with pytest.raises(RootConfigurationError):
        paths.write_atomic(book, "{}")
    assert not book.exists()
    with coordinator.deployment_lock("alpha", timeout=0):
        paths.write_atomic(book, "{}")
    assert book.read_text(encoding="utf-8") == "{}"


def test_raw_writes_outside_any_enrolled_root_keep_working(tmp_path):
    target = tmp_path / "standalone" / "note.txt"
    paths.write_text(target, "ok")
    assert target.read_text(encoding="utf-8") == "ok"


def _alias(link: Path, target: Path) -> None:
    if os.name == "nt":
        import _winapi

        _winapi.CreateJunction(str(target), str(link))
    else:
        os.symlink(target, link, target_is_directory=True)


def test_alias_into_an_enrolled_root_subdirectory_is_routed_through_admission(native_root, tmp_path):
    root, _context, coordinator = native_root
    (root / "paper" / "alpha").mkdir(parents=True)
    alias = tmp_path / "outside-alias"
    _alias(alias, root / "paper")
    with pytest.raises(RootConfigurationError):
        paths.write_atomic(alias / "alpha" / "broker.json", "{}")
    assert not (root / "paper" / "alpha" / "broker.json").exists()
    with coordinator.deployment_lock("alpha", timeout=0):
        paths.write_atomic(alias / "alpha" / "broker.json", "{}")
    assert (root / "paper" / "alpha" / "broker.json").read_text(encoding="utf-8") == "{}"


@pytest.mark.parametrize("state", ["marker-directory", "admission-without-marker"])
def test_unusual_enrollment_state_never_falls_back_to_a_raw_write(tmp_path, state):
    root = tmp_path / "odd"
    if state == "marker-directory":
        (root / paths.ENROLLMENT_MARKER).mkdir(parents=True)
    else:
        (root / paths.ADMISSION_STATE).mkdir(parents=True)
    with pytest.raises(RootConfigurationError):
        paths.write_text(root / "mandates" / "alpha.yaml", "name: alpha\n")
    assert not (root / "mandates").exists()


def test_saxo_refresh_lock_directory_inside_an_enrolled_root_is_rejected(native_root):
    from hedge_fund.brokers.saxo import _refresh_lock

    root, _context, _coordinator = native_root
    with pytest.raises(ValueError, match="outside an enrolled engine root"):
        with _refresh_lock("reference", root / "cache" / "saxo-locks", timeout_s=1):
            pytest.fail("refresh lock created inside an enrolled root")
    assert not (root / "cache").exists()
