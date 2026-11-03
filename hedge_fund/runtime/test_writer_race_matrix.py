"""T021 deterministic writer race matrix.

Every race is ordered with monkeypatched seams and ``threading.Event``
barriers, never sleeps. Authority flips use the two shipped T015 triggers: a
legacy ``<HOME>/.hedge-fund`` alias and a legacy ``runner.pid``. The tests
prove denial at the next effect or publication boundary; they do not prove
exclusion of arbitrary same-account writers, which cooperative locks cannot
fence.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from threading import Event, Thread

import pytest

from hedge_fund import paths
from hedge_fund.paper.deployed import deploy
from hedge_fund.paper.ledger import (
    APPROVAL_FILE,
    EVENTS_FILE,
    Ledger,
    LedgerError,
    SUPERSEDED_SUBDIR,
)
from hedge_fund.runtime import handover
from hedge_fund.runtime.admission import (
    AdmissionCoordinator,
    RootOwnerLease,
    WriterConflict,
)
from hedge_fund.runtime.handover import (
    enroll_fresh,
    enrollment_status,
    HandoverError,
    require_enrollment,
    write_authority,
)
from hedge_fund.runtime.lifecycle import LifecycleArchiveStore
from hedge_fund.runtime.root import RootContext
from hedge_fund.runtime.test_inventory_cache_race import _record, _spec
from hedge_fund.runtime.test_write_authority import _link_directory
from hedge_fund.web.demo import seed_demo
from hedge_fund.web.services import DeskService, ServiceError

FLIPS = ("legacy-alias", "legacy-runner-pid")


@pytest.fixture(autouse=True)
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
def funds(tmp_path, synthetic_home):
    root_path = tmp_path / "root"
    root_path.mkdir()
    with RootContext.open(root_path) as root:
        enroll_fresh(root)
        with RootOwnerLease.acquire(root) as owner:
            admission = AdmissionCoordinator(root, owner_lease=owner)
            for name in ("alpha", "beta"):
                with admission.deployment_lock(name):
                    deploy(name, _spec(name), ["AAPL"], root=root_path / "paper")
            with paths.bound_root(root):
                yield root, admission


class _Flip:
    """Revoke protocol-native authority at an exact seam, then restore it."""

    def __init__(self, kind: str, root_path: Path, home: Path) -> None:
        self.kind = kind
        self.root_path = root_path
        self.home = home
        self.applied = False

    def __call__(self) -> None:
        if self.applied:
            return
        if self.kind == "legacy-alias":
            _link_directory(self.home / ".hedge-fund", self.root_path)
        else:
            (self.root_path / "paper" / "beta" / "runner.pid").write_text("4242\n", encoding="utf-8")
        self.applied = True

    def undo(self) -> None:
        if not self.applied:
            return
        if self.kind == "legacy-alias":
            os.rmdir(self.home / ".hedge-fund") if os.name == "nt" else os.unlink(self.home / ".hedge-fund")
        else:
            (self.root_path / "paper" / "beta" / "runner.pid").unlink()
        self.applied = False


def _hook_after(monkeypatch, owner, attribute, action):
    original = getattr(owner, attribute)

    def hooked(self, *args, **kwargs):
        result = original(self, *args, **kwargs)
        action()
        return result

    monkeypatch.setattr(owner, attribute, hooked)


def _tree(path: Path) -> dict[str, bytes]:
    return {item.relative_to(path).as_posix(): item.read_bytes() for item in sorted(path.rglob("*")) if item.is_file()}


# ---- authority flip while the lanes and registry transaction are held -----


@pytest.mark.parametrize("flip_kind", FLIPS)
@pytest.mark.parametrize("mutation", ["append", "rewind"])
def test_authority_flip_inside_ledger_transaction_denies_effect_and_publication(funds, synthetic_home, monkeypatch, flip_kind, mutation):
    root, admission = funds
    ledger = Ledger(root.path / "paper" / "alpha")
    record = _record(_spec("alpha"))
    if mutation == "rewind":
        with admission.manual_session("alpha"):
            ledger.append(record)
    before_heads = require_enrollment(root)["heads"]
    before_tree = _tree(root.path / "paper" / "alpha" / "ledger")
    flip = _Flip(flip_kind, root.path, synthetic_home)
    _hook_after(monkeypatch, handover.PaperInventoryTransition, "expect_entry", lambda _entry=None: flip())

    try:
        with pytest.raises(LedgerError, match="denied"):
            with admission.manual_session("alpha"):
                ledger.append(record) if mutation == "append" else ledger.rewind()
        assert write_authority(root)["authority"] == "ownership-unknown"
    finally:
        flip.undo()

    assert require_enrollment(root)["heads"] == before_heads
    assert _tree(root.path / "paper" / "alpha" / "ledger") == before_tree
    assert enrollment_status(root, verify_inventory=True)["state"] == "enrolled"


@pytest.mark.parametrize("flip_kind", FLIPS)
def test_authority_flip_after_rewind_effect_blocks_head_publication(funds, synthetic_home, monkeypatch, flip_kind):
    root, admission = funds
    ledger = Ledger(root.path / "paper" / "alpha")
    record = _record(_spec("alpha"))
    with admission.manual_session("alpha"):
        ledger.append(record)
    before_heads = require_enrollment(root)["heads"]
    flip = _Flip(flip_kind, root.path, synthetic_home)
    _hook_after(monkeypatch, handover.PaperInventoryTransition, "unlink_file", lambda: flip())

    try:
        with pytest.raises(handover.LedgerHeadPublicationError):
            with admission.manual_session("alpha"):
                ledger.rewind()
    finally:
        flip.undo()

    # The completed effect is detected as drift; the head is never published.
    assert require_enrollment(root)["heads"] == before_heads
    assert not ledger.path(record.session).exists()
    assert enrollment_status(root, verify_inventory=True)["state"] == "drift"
    with pytest.raises(handover.LedgerDrift):
        with admission.manual_session("alpha"):
            ledger.append(record)


@pytest.mark.parametrize("flip_kind", FLIPS)
def test_authority_flip_inside_deploy_creates_no_fund(funds, synthetic_home, monkeypatch, flip_kind):
    root, admission = funds
    flip = _Flip(flip_kind, root.path, synthetic_home)
    before_heads = require_enrollment(root)["heads"]
    _hook_after(monkeypatch, handover.PaperInventoryTransition, "expect_entry", lambda _entry=None: flip())
    try:
        with pytest.raises(HandoverError):
            with admission.deployment_lock("gamma"):
                deploy("gamma", _spec("gamma"), ["AAPL"], root=root.path / "paper")
    finally:
        flip.undo()
    assert not (root.path / "paper" / "gamma").exists()
    assert require_enrollment(root)["heads"] == before_heads


@pytest.mark.parametrize(
    ("after", "absent"),
    [
        ("mkdir", "fund.yaml"),
        ("write_bytes", "broker.json"),
        ("write_text", "ledger"),
    ],
)
def test_authority_flip_between_deploy_effects_denies_the_next_effect(funds, synthetic_home, monkeypatch, after, absent):
    root, admission = funds
    flip = _Flip("legacy-runner-pid", root.path, synthetic_home)
    before_heads = require_enrollment(root)["heads"]
    _hook_after(monkeypatch, handover.PaperInventoryTransition, after, lambda *_args, **_kwargs: flip())
    try:
        with pytest.raises((HandoverError, LedgerError)):
            with admission.deployment_lock("gamma"):
                deploy("gamma", _spec("gamma"), ["AAPL"], root=root.path / "paper")
        assert flip.applied
    finally:
        flip.undo()
    # Effects completed before the flip may remain (reconciliation), the next one must not run.
    assert not (root.path / "paper" / "gamma" / absent).exists()
    assert require_enrollment(root)["heads"] == before_heads


def test_authority_flip_after_ledger_init_admission_denies_its_mkdir(funds, synthetic_home, monkeypatch):
    root, admission = funds
    flip = _Flip("legacy-runner-pid", root.path, synthetic_home)
    before_heads = require_enrollment(root)["heads"]
    enrolled_root = Ledger._enrolled_root

    def flip_then_enter(self, *args, **kwargs):
        # Ledger.init already passed its entry admission; only the effect recheck remains.
        flip()
        return enrolled_root(self, *args, **kwargs)

    monkeypatch.setattr(Ledger, "_enrolled_root", flip_then_enter)
    try:
        with pytest.raises((HandoverError, LedgerError)):
            with admission.deployment_lock("gamma"):
                deploy("gamma", _spec("gamma"), ["AAPL"], root=root.path / "paper")
        assert flip.applied
    finally:
        flip.undo()
    assert (root.path / "paper" / "gamma" / "broker.json").exists()
    assert not (root.path / "paper" / "gamma" / "ledger").exists()
    assert require_enrollment(root)["heads"] == before_heads


def _flip_on_second_paper_admission(monkeypatch, flip):
    from hedge_fund.runtime import admission as admission_module

    original = admission_module.require_paper_write_lanes
    calls = []

    def counted(*args, **kwargs):
        if len(calls) == 1:
            flip()
        calls.append(None)
        return original(*args, **kwargs)

    monkeypatch.setattr(admission_module, "require_paper_write_lanes", counted)
    return calls


@pytest.mark.parametrize("flip_kind", FLIPS)
def test_authority_flip_between_entry_and_approval_unlink_keeps_approval(funds, synthetic_home, monkeypatch, flip_kind):
    root, admission = funds
    ledger = Ledger(root.path / "paper" / "alpha")
    approval = {"decision_as_of": "2024-06-07", "decision_hash": "0" * 64}
    with admission.control_lane("alpha"):
        paths.write_text(ledger.approval_path, json.dumps(approval))
    before = ledger.approval_path.read_bytes()
    flip = _Flip(flip_kind, root.path, synthetic_home)
    calls = _flip_on_second_paper_admission(monkeypatch, flip)
    try:
        with pytest.raises(LedgerError, match="denied"):
            with admission.control_lane("alpha"):
                ledger.clear_approval()
    finally:
        flip.undo()
    assert len(calls) >= 2
    assert (root.path / "paper" / "alpha" / APPROVAL_FILE).read_bytes() == before


@pytest.mark.parametrize("flip_kind", FLIPS)
def test_authority_flip_inside_audit_transition_appends_no_event(funds, synthetic_home, monkeypatch, flip_kind):
    root, admission = funds
    ledger = Ledger(root.path / "paper" / "alpha")
    events = root.path / "paper" / "alpha" / EVENTS_FILE
    before = events.read_bytes() if events.exists() else None
    flip = _Flip(flip_kind, root.path, synthetic_home)
    from hedge_fund.runtime import admission as admission_module

    original = admission_module.paper_audit_transition

    def flipping(*args, **kwargs):
        context = original(*args, **kwargs)

        class _Wrapped:
            def __enter__(self):
                value = context.__enter__()
                flip()
                return value

            def __exit__(self, *exc):
                return context.__exit__(*exc)

        return _Wrapped()

    monkeypatch.setattr(admission_module, "paper_audit_transition", flipping)
    try:
        with pytest.raises(LedgerError, match="denied"):
            with admission.manual_session("alpha"):
                ledger.log_event("synthetic")
    finally:
        flip.undo()
    assert (events.read_bytes() if events.exists() else None) == before


# ---- rename/link/snapshot: reparse swaps during an admitted transaction -----


def test_junction_swap_during_rewind_cannot_move_record_outside_root(funds, tmp_path, monkeypatch):
    root, admission = funds
    ledger = Ledger(root.path / "paper" / "alpha")
    record = _record(_spec("alpha"))
    with admission.manual_session("alpha"):
        ledger.append(record)
    outside = tmp_path / "outside"
    outside.mkdir()
    before_heads = require_enrollment(root)["heads"]
    keep = ledger.records_dir / SUPERSEDED_SUBDIR

    def swap(_entry=None):
        _link_directory(keep, outside)

    _hook_after(monkeypatch, handover.PaperInventoryTransition, "expect_entry", swap)
    try:
        with pytest.raises(LedgerError):
            with admission.manual_session("alpha"):
                ledger.rewind()
    finally:
        os.rmdir(keep) if os.name == "nt" else os.unlink(keep)
    assert list(outside.iterdir()) == []
    assert ledger.path(record.session).exists()
    assert require_enrollment(root)["heads"] == before_heads


def test_ledger_directory_swap_during_append_cannot_write_outside_root(funds, tmp_path, monkeypatch):
    root, admission = funds
    ledger = Ledger(root.path / "paper" / "alpha")
    record = _record(_spec("alpha"))
    outside = tmp_path / "outside"
    outside.mkdir()
    moved = ledger.records_dir.with_name("ledger.moved")
    before_heads = require_enrollment(root)["heads"]

    def swap(_entry=None):
        ledger.records_dir.rename(moved)
        _link_directory(ledger.records_dir, outside)

    _hook_after(monkeypatch, handover.PaperInventoryTransition, "expect_entry", swap)
    try:
        with pytest.raises(LedgerError):
            with admission.manual_session("alpha"):
                ledger.append(record)
    finally:
        os.rmdir(ledger.records_dir) if os.name == "nt" else os.unlink(ledger.records_dir)
        moved.rename(ledger.records_dir)
    assert list(outside.iterdir()) == []
    assert require_enrollment(root)["heads"] == before_heads


def test_junction_swap_before_approval_unlink_removes_nothing_outside(funds, tmp_path, monkeypatch):
    root, admission = funds
    ledger = Ledger(root.path / "paper" / "alpha")
    outside = tmp_path / "outside"
    outside.mkdir()
    victim = outside / APPROVAL_FILE
    victim.write_text("outside\n", encoding="utf-8")
    fund = root.path / "paper" / "alpha"
    moved = fund.with_name("alpha.moved")
    calls = []

    def swap():
        fund.rename(moved)
        _link_directory(fund, outside)

    from hedge_fund.runtime import admission as admission_module

    original = admission_module.require_paper_write_lanes

    def counted(*args, **kwargs):
        result = original(*args, **kwargs)
        calls.append(None)
        if len(calls) == 2:
            swap()
        return result

    monkeypatch.setattr(admission_module, "require_paper_write_lanes", counted)
    with admission.control_lane("alpha"):
        paths.write_text(ledger.approval_path, "{}")
    calls.clear()
    try:
        with admission.control_lane("alpha"):
            assert ledger.clear_approval() is False
    finally:
        if fund.is_symlink() or fund.is_junction():
            os.rmdir(fund) if os.name == "nt" else os.unlink(fund)
        if moved.exists():
            moved.rename(fund)
    assert victim.read_text(encoding="utf-8") == "outside\n"


# ---- same-object conflict and independent fund progress --------------------


def test_same_fund_writer_conflict_while_transaction_is_paused(funds, monkeypatch):
    root, admission = funds
    ledger = Ledger(root.path / "paper" / "alpha")
    record = _record(_spec("alpha"))
    inside = Event()
    release = Event()
    outcome = {}

    def pause(_entry=None):
        inside.set()
        assert release.wait(30)

    _hook_after(monkeypatch, handover.PaperInventoryTransition, "expect_entry", pause)

    def first():
        try:
            with admission.manual_session("alpha"):
                ledger.append(record)
            outcome["first"] = "ok"
        except BaseException as exc:  # pragma: no cover - reported below
            outcome["first"] = exc

    worker = Thread(target=first)
    worker.start()
    assert inside.wait(30)
    try:
        with pytest.raises(WriterConflict):
            with admission.manual_session("alpha"):
                pass
    finally:
        release.set()
        worker.join(30)
    assert outcome["first"] == "ok"
    assert require_enrollment(root)["heads"]["alpha"]["head_hash"] == record.hash


def test_independent_fund_progresses_while_other_fund_holds_its_lanes(funds):
    root, admission = funds
    alpha = Ledger(root.path / "paper" / "alpha")
    beta = Ledger(root.path / "paper" / "beta")
    holding = Event()
    release = Event()
    outcome = {}

    def hold_alpha():
        try:
            with admission.manual_session("alpha"):
                holding.set()
                assert release.wait(30)
                alpha.append(_record(_spec("alpha")))
            outcome["alpha"] = "ok"
        except BaseException as exc:  # pragma: no cover - reported below
            outcome["alpha"] = exc

    worker = Thread(target=hold_alpha)
    worker.start()
    assert holding.wait(30)
    try:
        with admission.manual_session("beta"):
            beta.append(_record(_spec("beta")))
        assert require_enrollment(root)["heads"]["beta"]["session_count"] == 1
        assert require_enrollment(root)["heads"]["alpha"]["session_count"] == 0
    finally:
        release.set()
        worker.join(30)
    assert outcome["alpha"] == "ok"
    heads = require_enrollment(root)["heads"]
    assert heads["alpha"]["session_count"] == heads["beta"]["session_count"] == 1
    assert enrollment_status(root, verify_inventory=True)["state"] == "enrolled"


# ---- cancellation / crash / restart / recovery ------------------------------


def test_crash_after_rewind_rename_requires_offline_reconciliation(funds, monkeypatch):
    root, admission = funds
    ledger = Ledger(root.path / "paper" / "alpha")
    record = _record(_spec("alpha"))
    with admission.manual_session("alpha"):
        ledger.append(record)
    before_heads = require_enrollment(root)["heads"]

    def crash(*_args, **_kwargs):
        raise KeyboardInterrupt("synthetic cancellation after rename")

    original = handover.PaperInventoryTransition.rename_file

    def rename_then_crash(self, *args, **kwargs):
        original(self, *args, **kwargs)
        crash()

    monkeypatch.setattr(handover.PaperInventoryTransition, "rename_file", rename_then_crash)
    with pytest.raises(KeyboardInterrupt):
        with admission.manual_session("alpha"):
            ledger.rewind()
    monkeypatch.setattr(handover.PaperInventoryTransition, "rename_file", original)

    # Restart: no durable intent exists, so nothing auto-publishes the rewind.
    with RootContext.open(root.path) as restarted:
        assert require_enrollment(restarted)["heads"] == before_heads
        assert enrollment_status(restarted, verify_inventory=True)["state"] == "drift"
        with RootOwnerLease.acquire(restarted) as owner:
            fresh = AdmissionCoordinator(restarted, owner_lease=owner)
            with paths.bound_root(restarted):
                # Drift is root-wide: every fund stays blocked until offline reconciliation.
                with pytest.raises(handover.LedgerDrift):
                    with fresh.manual_session("alpha"):
                        Ledger(restarted.path / "paper" / "alpha").append(record)
                with fresh.manual_session("beta"):
                    with pytest.raises(handover.LedgerDrift):
                        Ledger(restarted.path / "paper" / "beta").append(_record(_spec("beta")))


# ---- lifecycle and web mandate writers ---------------------------------------


@pytest.fixture
def demo_store(tmp_path):
    path = seed_demo(tmp_path / "demo")
    with RootContext.open(path) as root:
        owner = RootOwnerLease.acquire(root)
        admission = AdmissionCoordinator(root, owner_lease=owner)
        try:
            yield root, LifecycleArchiveStore(root, admission)
        finally:
            owner.close()


def test_authority_flip_after_lifecycle_journal_denies_move(demo_store, synthetic_home, monkeypatch):
    root, store = demo_store
    preview = store.preview("template", "demo-quality")
    source = root.path / preview["source_path"]
    before = source.read_bytes()
    flip = _Flip("legacy-alias", root.path, synthetic_home)
    original = store._write_index

    def journal_then_flip(index):
        original(index)
        flip()

    monkeypatch.setattr(store, "_write_index", journal_then_flip)
    try:
        with pytest.raises(Exception) as denied:
            store.archive("template", "demo-quality", expected_digest=preview["digest"], archive_id="a" * 32)
    finally:
        flip.undo()
    assert "authority" in str(denied.value).lower() or "ownership" in type(denied.value).__name__.lower()
    assert source.read_bytes() == before


def test_authority_flip_before_lifecycle_head_transition_keeps_heads(demo_store, synthetic_home, monkeypatch):
    root, store = demo_store
    preview = store.preview("deployment", "demo-quality")
    before_heads = require_enrollment(root)["heads"]
    flip = _Flip("legacy-alias", root.path, synthetic_home)
    original = store._transition_deployment_head

    def flip_then_transition(record, *, restore):
        flip()
        return original(record, restore=restore)

    monkeypatch.setattr(store, "_transition_deployment_head", flip_then_transition)
    try:
        with pytest.raises(HandoverError):
            store.archive("deployment", "demo-quality", expected_digest=preview["digest"], archive_id="c" * 32)
    finally:
        flip.undo()
    assert require_enrollment(root)["heads"] == before_heads
    monkeypatch.setattr(store, "_transition_deployment_head", original)
    view = store.inspect("c" * 32)
    assert view["recovery_required"] is True
    assert store.recover("c" * 32, expected_digest=preview["digest"])["state"] == "archived"
    assert enrollment_status(root, verify_inventory=True)["state"] == "enrolled"


@pytest.mark.parametrize("phase", ["before-rename", "between-rename-and-write", "before-write"])
def test_mandate_update_authority_flip_reports_exact_partial_state(tmp_path, synthetic_home, monkeypatch, phase):
    path = seed_demo(tmp_path / "desk")
    service = DeskService(path, allow_writes=True)
    flip = _Flip("legacy-alias", path, synthetic_home)
    try:
        original = service.get_mandate("demo-quality")
        candidate = json.loads(json.dumps(original["spec"]))
        if phase != "before-write":
            candidate["name"] = "demo-quality-renamed"
        else:
            candidate["capital"] = original["spec"]["capital"] + 1
        source = path / "mandates" / "demo-quality.yaml"
        target = path / "mandates" / "demo-quality-renamed.yaml"
        source_before = source.read_bytes()
        if phase == "between-rename-and-write":
            rename = service.root_context.rename_file

            def rename_then_flip(*args):
                result = rename(*args)
                flip()
                return result

            monkeypatch.setattr(service.root_context, "rename_file", rename_then_flip)
        else:
            load = service._load_mandate_entry

            def load_then_flip(name):
                result = load(name)
                flip()
                return result

            monkeypatch.setattr(service, "_load_mandate_entry", load_then_flip)
        with pytest.raises(ServiceError) as denied:
            service.update_mandate("demo-quality", candidate, expected_hash=original["mandate_hash"])
    finally:
        flip.undo()
        service.close()
    assert denied.value.status_code == 409
    if phase == "between-rename-and-write":
        assert "reconciliation" in str(denied.value)
        assert not source.exists()
        assert target.read_bytes() == source_before
    else:
        assert "nothing was written" in str(denied.value)
        assert source.read_bytes() == source_before
        assert not target.exists()


def test_matrix_leaves_no_legacy_alias_in_synthetic_home(synthetic_home):
    assert not (synthetic_home / ".hedge-fund").exists()
