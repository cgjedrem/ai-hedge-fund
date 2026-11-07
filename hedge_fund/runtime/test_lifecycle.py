import json
import time

import pytest

from hedge_fund.runtime.admission import (
    AdmissionCoordinator,
    RootOwnerLease,
    WriterConflict,
)
from hedge_fund.runtime.handover import enrollment_status, HandoverRequired
from hedge_fund.runtime.lifecycle import (
    ARCHIVE_INDEX,
    ArchiveConflict,
    ArchiveError,
    LifecycleArchiveStore,
)
from hedge_fund.runtime.owned_runner import runner_key, RUNNER_ROOT, write_runner_record
from hedge_fund.runtime.root import RootContext
from hedge_fund.web.demo import seed_demo


@pytest.fixture
def archive_store(tmp_path):
    path = seed_demo(tmp_path / "synthetic")
    with RootContext.open(path) as root:
        owner = RootOwnerLease.acquire(root)
        admission = AdmissionCoordinator(root, owner_lease=owner)
        try:
            yield root, admission, LifecycleArchiveStore(root, admission)
        finally:
            owner.close()


def test_template_archive_restore_preserves_siblings_and_bytes(archive_store):
    root, _, store = archive_store
    original = root.read_bytes("mandates/demo-quality.yaml")
    root.write_bytes("mandates/decoy.yaml", b"keep: true\n")
    preview = store.preview("template", "demo-quality")
    record = store.archive("template", "demo-quality", expected_digest=preview["digest"], archive_id="a" * 32)
    assert record["state"] == "archived"
    assert not (root.path / "mandates" / "demo-quality.yaml").exists()
    assert root.read_bytes("mandates/decoy.yaml") == b"keep: true\n"
    restored = store.restore(record["archive_id"], expected_digest=preview["digest"], operation_id="b" * 32)
    assert restored["state"] == "restored"
    assert root.read_bytes("mandates/demo-quality.yaml") == original


def test_deployment_archive_restore_preserves_history_and_enrolled_heads(archive_store):
    root, _, store = archive_store
    preview = store.preview("deployment", "demo-quality")
    record = store.archive("deployment", "demo-quality", expected_digest=preview["digest"], archive_id="c" * 32)
    assert record["state"] == "archived"
    assert enrollment_status(root, verify_inventory=True)["state"] == "enrolled"
    restored = store.restore(record["archive_id"], expected_digest=preview["digest"], operation_id="d" * 32)
    assert restored["state"] == "restored"
    assert store.preview("deployment", "demo-quality")["digest"] == preview["digest"]
    assert enrollment_status(root, verify_inventory=True)["state"] == "enrolled"


def test_archive_rejects_stale_review_without_effects(archive_store):
    root, _, store = archive_store
    preview = store.preview("template", "demo-quality")
    root.write_bytes(preview["source_path"], root.read_bytes(preview["source_path"]) + b"\n# changed\n")
    with pytest.raises(ArchiveConflict, match="changed"):
        store.archive("template", "demo-quality", expected_digest=preview["digest"], archive_id="e" * 32)
    assert (root.path / preview["source_path"]).exists()
    assert store.list_archives() == []


def test_restore_rejects_yaml_alias_collision(archive_store):
    root, _, store = archive_store
    preview = store.preview("template", "demo-quality")
    record = store.archive("template", "demo-quality", expected_digest=preview["digest"], archive_id="f" * 32)
    root.write_bytes("mandates/DEMO-QUALITY.yml", b"decoy: true\n")
    with pytest.raises(ArchiveConflict, match="collision"):
        store.restore(record["archive_id"], expected_digest=preview["digest"], operation_id="1" * 32)
    assert root.read_bytes("mandates/DEMO-QUALITY.yml") == b"decoy: true\n"


def test_archive_interruption_is_explicitly_recoverable(archive_store, monkeypatch):
    root, _, store = archive_store
    preview = store.preview("deployment", "demo-quality")
    finalize = store._finalize_archive

    def crash(*args):
        raise RuntimeError("synthetic interruption after move")

    monkeypatch.setattr(store, "_finalize_archive", crash)
    with pytest.raises(RuntimeError, match="interruption"):
        store.archive("deployment", "demo-quality", expected_digest=preview["digest"], archive_id="2" * 32)
    view = store.inspect("2" * 32)
    assert view["recovery_required"] is True
    assert view["recovery_action"] == "finalize-archive"
    assert enrollment_status(root, verify_inventory=True)["state"] == "drift"
    monkeypatch.setattr(store, "_finalize_archive", finalize)
    assert store.recover("2" * 32, expected_digest=preview["digest"])["state"] == "archived"
    assert enrollment_status(root, verify_inventory=True)["state"] == "enrolled"


def test_archive_reuses_verified_outer_lanes(archive_store):
    _, admission, store = archive_store
    preview = store.preview("template", "demo-quality")
    with admission.registry_lock(timeout=0), admission.manual_session("demo-quality", timeout=0):
        record = store.archive("template", "demo-quality", expected_digest=preview["digest"], archive_id="3" * 32)
    assert record["state"] == "archived"


def test_unenrolled_root_cannot_create_lifecycle_store(tmp_path):
    with RootContext.open(tmp_path) as root:
        root.prepare_private_storage()
        admission = AdmissionCoordinator(root)
        with pytest.raises(HandoverRequired):
            LifecycleArchiveStore(root, admission)


def test_forged_archive_paths_and_unknown_phases_fail_closed(archive_store):
    root, _, store = archive_store
    preview = store.preview("template", "demo-quality")
    store.archive("template", "demo-quality", expected_digest=preview["digest"], archive_id="4" * 32)
    index = json.loads(root.read_bytes(ARCHIVE_INDEX))
    index["items"]["4" * 32]["source_path"] = "mandates/decoy.yaml"
    root.write_bytes(ARCHIVE_INDEX, json.dumps(index).encode())
    with pytest.raises(ArchiveError, match="malformed"):
        store.list_archives()


def test_report_filename_must_match_its_fund(archive_store):
    root, _, store = archive_store
    root.mkdir("research", parents=True)
    root.write_bytes("research/other-2026.json", b'{"fund":"demo-quality"}')
    with pytest.raises(ArchiveConflict, match="identity"):
        store.preview("research", "other-2026.json")


def test_cross_process_writer_conflict_preserves_independent_template(archive_store, owned_test_process):
    root, _, store = archive_store
    root.write_bytes("mandates/decoy.yaml", b"keep: true\n")
    ready = root.path / "writer-ready"
    release = root.path / "writer-release"
    script = (
        "from pathlib import Path\nimport time\n"
        "from hedge_fund.runtime.root import RootContext\n"
        "from hedge_fund.runtime.admission import RootOwnerLease, AdmissionCoordinator\n"
        f"with RootContext.open({str(root.path)!r}) as root:\n"
        " owner=RootOwnerLease.acquire(root)\n"
        " try:\n"
        "  admission=AdmissionCoordinator(root, owner_lease=owner)\n"
        "  with admission.execution_lease('demo-quality'):\n"
        f"   Path({str(ready)!r}).write_text('ready')\n"
        "   deadline=time.monotonic()+15\n"
        f"   while not Path({str(release)!r}).exists() and time.monotonic()<deadline: time.sleep(.02)\n"
        " finally: owner.close()\n"
    )
    child = owned_test_process(script)
    deadline = time.monotonic() + 10
    while not ready.exists() and child.poll() is None and time.monotonic() < deadline:
        time.sleep(0.02)
    assert ready.exists(), "synthetic writer did not acquire its lane"
    try:
        preview = store.preview("deployment", "demo-quality")
        with pytest.raises(WriterConflict):
            store.archive("deployment", "demo-quality", expected_digest=preview["digest"], archive_id="5" * 32)
        decoy = store.preview("template", "decoy")
        assert store.archive("template", "decoy", expected_digest=decoy["digest"], archive_id="6" * 32)["state"] == "archived"
        assert (root.path / "paper" / "demo-quality").is_dir()
    finally:
        release.write_text("release")
        assert child.wait(timeout=10) == 0


@pytest.mark.parametrize("identity", ["Watchtower.yaml", "umbrella", "CON", "alpha.", "alpha~1"])
def test_aliases_are_rejected_before_any_archive_access(archive_store, identity):
    _, _, store = archive_store
    with pytest.raises(ArchiveError):
        store.preview("template", identity)


def test_unverified_starting_record_blocks_archive_even_with_free_runner_lane(archive_store):
    root, _, store = archive_store
    preview = store.preview("deployment", "demo-quality")
    root.mkdir(f"{RUNNER_ROOT}/{runner_key('demo-quality')}", parents=True, mode=0o700)
    write_runner_record(root, "demo-quality", "state", {"status": "starting"})
    with pytest.raises(ArchiveConflict, match="runner"):
        store.archive("deployment", "demo-quality", expected_digest=preview["digest"], archive_id="7" * 32)
    assert (root.path / "paper" / "demo-quality").is_dir()


def test_recovery_keeps_legitimate_other_fund_inventory_changes(archive_store, monkeypatch):
    from hedge_fund.paper.deployed import deploy, load_deployed
    from hedge_fund.paper.ledger import Ledger
    from hedge_fund.pipeline.session import code_version, mandate_hash, SessionRecord
    from hedge_fund.runtime.handover import record_ledger_head

    root, admission, store = archive_store
    preview = store.preview("deployment", "demo-quality")
    spec = load_deployed(root.path / "paper" / "demo-quality").spec.model_copy(update={"name": "independent"})
    with admission.deployment_lock("independent"):
        directory = deploy("independent", spec, ["AAPL"], root=root.path / "paper")
    record_ledger_head(root, "independent", admission=admission)
    finalize = store._finalize_archive
    monkeypatch.setattr(store, "_finalize_archive", lambda *args: (_ for _ in ()).throw(RuntimeError("synthetic crash")))
    with pytest.raises(RuntimeError, match="crash"):
        store.archive("deployment", "demo-quality", expected_digest=preview["digest"], archive_id="8" * 32)
    monkeypatch.setattr(store, "_finalize_archive", finalize)
    # A pre-existing independent runner advances only its own enrolled head.
    record = SessionRecord(fund="independent", session="2024-06-03", universe=["AAPL"], nav=spec.capital, cash=spec.capital, positions={}, marks={}, benchmark="SPY", benchmark_close=100, rebalance=False, code_version=code_version(), mandate_hash=mandate_hash(spec))
    record.hash = record.compute_hash()
    with admission.manual_session("independent"):
        Ledger(directory).append(record)
    record_ledger_head(root, "independent", admission=admission)
    recovered = store.recover("8" * 32, expected_digest=preview["digest"])
    assert recovered["state"] == "archived"
    assert enrollment_status(root, verify_inventory=True)["state"] == "enrolled"
    assert (root.path / "paper" / "independent" / "fund.yaml").exists()


def test_changed_prepared_archive_does_not_authorize_another_funds_append(
    archive_store,
    monkeypatch,
):
    from hedge_fund.paper.deployed import deploy, load_deployed
    from hedge_fund.paper.ledger import Ledger
    from hedge_fund.pipeline.session import code_version, mandate_hash, SessionRecord
    from hedge_fund.runtime.handover import LedgerDrift

    root, admission, store = archive_store
    preview = store.preview("deployment", "demo-quality")
    spec = load_deployed(root.path / "paper" / "demo-quality").spec.model_copy(update={"name": "independent"})
    with admission.deployment_lock("independent"):
        directory = deploy("independent", spec, ["AAPL"], root=root.path / "paper")
    finalize = store._finalize_archive
    monkeypatch.setattr(store, "_finalize_archive", lambda *args: (_ for _ in ()).throw(RuntimeError("synthetic crash")))
    with pytest.raises(RuntimeError, match="crash"):
        store.archive("deployment", "demo-quality", expected_digest=preview["digest"], archive_id="9" * 32)
    monkeypatch.setattr(store, "_finalize_archive", finalize)
    archived_fund = root.path / "runtime" / "private" / "v1" / "archives" / "v1" / "objects" / ("9" * 32) / "fund.yaml"
    archived_fund.write_bytes(archived_fund.read_bytes() + b"\n")
    record = SessionRecord(fund="independent", session="2024-06-03", universe=["AAPL"], nav=spec.capital, cash=spec.capital, positions={}, marks={}, benchmark="SPY", benchmark_close=100, rebalance=False, code_version=code_version(), mandate_hash=mandate_hash(spec))
    record.hash = record.compute_hash()
    ledger = Ledger(directory)

    with admission.manual_session("independent"):
        with pytest.raises(LedgerDrift, match="lifecycle"):
            ledger.append(record)

    assert ledger.sessions() == []


def test_restore_recovery_keeps_another_funds_published_head(archive_store, monkeypatch):
    from hedge_fund.paper.deployed import deploy, load_deployed
    from hedge_fund.paper.ledger import Ledger
    from hedge_fund.pipeline.session import code_version, mandate_hash, SessionRecord

    root, admission, store = archive_store
    preview = store.preview("deployment", "demo-quality")
    spec = load_deployed(root.path / "paper" / "demo-quality").spec.model_copy(update={"name": "independent"})
    archive_id = "a" * 32
    operation_id = "b" * 32
    store.archive("deployment", "demo-quality", expected_digest=preview["digest"], archive_id=archive_id)
    with admission.deployment_lock("independent"):
        directory = deploy("independent", spec, ["AAPL"], root=root.path / "paper")
    finalize = store._finalize_restore
    monkeypatch.setattr(store, "_finalize_restore", lambda *args: (_ for _ in ()).throw(RuntimeError("synthetic crash")))
    with pytest.raises(RuntimeError, match="crash"):
        store.restore(archive_id, expected_digest=preview["digest"], operation_id=operation_id)
    monkeypatch.setattr(store, "_finalize_restore", finalize)

    record = SessionRecord(fund="independent", session="2024-06-03", universe=["AAPL"], nav=spec.capital, cash=spec.capital, positions={}, marks={}, benchmark="SPY", benchmark_close=100, rebalance=False, code_version=code_version(), mandate_hash=mandate_hash(spec))
    record.hash = record.compute_hash()
    with admission.manual_session("independent"):
        Ledger(directory).append(record)
    recovered = store.recover(archive_id, expected_digest=preview["digest"])

    assert recovered["state"] == "restored"
    assert operation_id in recovered["reconciled_operations"]
    assert enrollment_status(root, verify_inventory=True)["state"] == "enrolled"
    assert Ledger(directory).latest().hash == record.hash
