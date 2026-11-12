import hashlib
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from hedge_fund.fund import FundSpec
from hedge_fund.paper.deployed import deploy
from hedge_fund.paper.ledger import Ledger
from hedge_fund.pipeline.session import code_version, SessionRecord
from hedge_fund.runtime import handover
from hedge_fund.runtime.admission import (
    AdmissionCoordinator,
    OwnershipUnknown,
    require_paper_write_lanes,
    RootMigrationLease,
    RootOwnerLease,
    WriterConflict,
)
from hedge_fund.runtime.handover import (
    build_head_inventory,
    enroll_fresh,
    enrollment_status,
    EnrollmentInvalid,
    HANDOVER_PATH,
    HandoverError,
    inventory_digest,
    LedgerDrift,
    migrate_existing,
    OPERATOR_ATTESTATION,
    require_enrollment,
    root_binding,
    verify_ledger_head,
)
from hedge_fund.runtime.owned_runner import (
    read_runner_record,
    runner_key,
    RUNNER_ROOT,
    write_runner_record,
)
from hedge_fund.runtime.ownership import (
    process_identity,
    process_is_running,
    ProcessIdentityError,
)
from hedge_fund.runtime.root import PRIVATE_ROOT, RootContext, RootPathError


@pytest.fixture(autouse=True)
def synthetic_runtime_scope(monkeypatch):
    runtime_scope = {
        "kind": "linux-pid1",
        "pid1": {
            "pid": 1,
            "creation_time": "987654",
            "image": "/usr/bin/synthetic-supervisor",
            "host": "synthetic-boot-id",
            "namespace": "4026533000",
        },
        "namespace": "pid:[4026533000];mnt:[4026533001]",
    }
    monkeypatch.setattr(handover, "_runtime_scope_identity", lambda _root: runtime_scope)
    return runtime_scope


def _spec():
    return FundSpec.model_validate(
        {
            "schema_version": 2,
            "name": "alpha",
            "strategies": [
                {
                    "name": "solo",
                    "models": [{"name": "graham"}],
                    "blend": {"mode": "long_short"},
                }
            ],
            "risk": {"max_position_pct": 1, "max_gross_exposure": 1},
            "capital": 100_000,
            "costs": {"spread_bps": 0, "commission_per_share": 0},
            "rebalance": "daily",
        }
    )


def _tree_digest_snapshot(path):
    return {item.relative_to(path).as_posix(): ("dir" if item.is_dir() else hashlib.sha256(item.read_bytes()).hexdigest()) for item in sorted(path.rglob("*"))}


def _legacy_relocation_source(path, *, protected_fund=False, marker=None, settings=None):
    path.mkdir()
    (path / "paper").mkdir()
    deploy("alpha", _spec(), ["AAPL"], root=path / "paper")
    (path / "mandates").mkdir()
    (path / "mandates" / "alpha.yaml").write_text("name: alpha\n", encoding="utf-8")
    (path / "research" / "alpha").mkdir(parents=True)
    (path / "research" / "alpha" / "note.json").write_text("{}", encoding="utf-8")
    if protected_fund:
        (path / "paper" / "alpha").rename(path / "paper" / "umbrella")
        fund_file = path / "paper" / "umbrella" / "fund.yaml"
        fund_file.write_text(fund_file.read_text(encoding="utf-8").replace("name: alpha", "name: umbrella"), encoding="utf-8")
    if marker is not None:
        fund_name = "umbrella" if protected_fund else "alpha"
        (path / "paper" / fund_name / "runner.pid").write_text(marker, encoding="ascii")
    if settings is not None:
        settings_path = path / handover.RELOCATED_SETTINGS_PATH
        settings_path.parent.mkdir(parents=True)
        settings_path.write_bytes(settings)
    return path


def _write_protected_source_fund(root, name):
    staging_name = f"staging-{name}"
    spec_data = _spec().model_dump()
    spec_data["name"] = staging_name
    deploy(staging_name, FundSpec.model_validate(spec_data), ["AAPL"], root=root / "paper")
    staging = root / "paper" / staging_name
    protected = root / "paper" / name
    staging.rename(protected)
    fund_file = protected / "fund.yaml"
    content = fund_file.read_text(encoding="utf-8").replace(f"name: {staging_name}", f"name: {name}", 1)
    fund_file.write_text(content, encoding="utf-8")


def _copied_destination(tmp_path, *, protected_fund=False, marker=None, settings=None):
    source_path = _legacy_relocation_source(tmp_path / "source", protected_fund=protected_fund, marker=marker, settings=settings)
    destination_path = tmp_path / "destination"
    destination_path.mkdir()
    with RootContext.open(source_path) as source:
        source_review = handover.inspect_relocation_source(
            source,
            evidence_out=destination_path / handover.SOURCE_EVIDENCE_PATH,
        )
    with RootContext.open(source_path) as source, RootContext.open(destination_path) as destination:
        handover.relocate_copy(destination, source=source, expected_content_digest=source_review["content_digest"])
    return source_path, destination_path, source_review


def _terminated_dummy_pid(owned_test_process):
    for _attempt in range(10):
        process = owned_test_process("pass")
        pid = process.pid
        assert process.wait(timeout=10) == 0
        try:
            if not process_is_running(pid):
                return pid
        except (OSError, ProcessIdentityError):
            continue
    pytest.fail("could not obtain a recently terminated synthetic process ID")


def test_attestation_artifact_round_trip_rejects_another_root(tmp_path):
    first_path = tmp_path / "attestation-root-a"
    second_path = tmp_path / "attestation-root-b"
    first_path.mkdir()
    second_path.mkdir()

    with RootContext.open(first_path) as first, RootContext.open(second_path) as second:
        record = handover._new_attestation_artifact(
            first,
            kind="protected-fund-inclusion",
            subject="umbrella",
            evidence={"source_inventory_digest": "1" * 64},
            source_evidence_digest="2" * 64,
            operator_statement="I confirm this synthetic fund belongs to this destination.",
            recorded_at="2026-11-12T10:00:00+00:00",
        )
        round_trip = json.loads(json.dumps(record))

        assert handover._validate_attestation_artifact(first, round_trip) == record
        with pytest.raises(HandoverError, match="identity"):
            handover._validate_attestation_artifact(second, round_trip)


@pytest.mark.parametrize(
    ("kind", "evidence", "recorded_at"),
    [
        ([], {}, "2026-11-12T10:00:00+00:00"),
        ("protected-fund-inclusion", {"invalid": object()}, "2026-11-12T10:00:00+00:00"),
        ("protected-fund-inclusion", {}, ""),
    ],
)
def test_attestation_artifact_rejects_invalid_schema_values(tmp_path, kind, evidence, recorded_at):
    root_path = tmp_path / "invalid-attestation"
    root_path.mkdir()
    with RootContext.open(root_path) as root:
        with pytest.raises(HandoverError, match="attestation"):
            handover._new_attestation_artifact(
                root,
                kind=kind,
                subject="umbrella",
                evidence=evidence,
                source_evidence_digest="2" * 64,
                operator_statement="I confirm this synthetic fund belongs to this destination.",
                recorded_at=recorded_at,
            )


def test_attestation_artifact_storage_is_root_private_and_refuses_overwrite(tmp_path):
    root_path = tmp_path / "attestation-storage"
    root_path.mkdir()
    with RootContext.open(root_path) as root:
        root.prepare_private_storage()
        record = handover._new_attestation_artifact(
            root,
            kind="protected-fund-inclusion",
            subject="umbrella",
            evidence={"source_inventory_digest": "1" * 64},
            source_evidence_digest="2" * 64,
            operator_statement="I confirm this synthetic fund belongs to this destination.",
            recorded_at="2026-11-12T10:00:00+00:00",
        )
        relative = handover._write_attestation_artifact(root, record)

        assert json.loads(root.read_bytes(relative)) == record
        with pytest.raises(HandoverError, match="already exists"):
            handover._write_attestation_artifact(root, record)


def test_inspect_source_stages_destination_evidence_and_preserves_source(tmp_path):
    source_path = tmp_path / "legacy-source"
    destination_path = tmp_path / "native-target"
    source_path.mkdir()
    (source_path / "paper").mkdir()
    destination_path.mkdir()
    deploy("alpha", _spec(), ["AAPL"], root=source_path / "paper")
    protected = source_path / "paper" / "alpha"
    protected.rename(source_path / "paper" / "umbrella")
    fund_file = source_path / "paper" / "umbrella" / "fund.yaml"
    fund_file.write_text(fund_file.read_text(encoding="utf-8").replace("name: alpha", "name: umbrella"), encoding="utf-8")
    marker = source_path / "paper" / "umbrella" / "runner.pid"
    marker.write_text("4242\n", encoding="ascii")
    before = _tree_digest_snapshot(source_path)
    evidence_path = destination_path / handover.SOURCE_EVIDENCE_PATH

    with RootContext.open(source_path) as source:
        with pytest.raises(RootPathError, match="protected"):
            source.read_bytes("paper/umbrella/fund.yaml")
        observed = handover.inspect_relocation_source(source, evidence_out=evidence_path)
        bundle = json.loads(evidence_path.read_bytes())
        repeated = handover.inspect_relocation_source(source, evidence_out=evidence_path)

    assert _tree_digest_snapshot(source_path) == before
    assert observed["source_evidence_digest"] == bundle["record_digest"]
    assert repeated["source_evidence_digest"] == observed["source_evidence_digest"]
    assert handover._validate_source_evidence_bundle(bundle)["observed_inventory_digest"] == observed["observed_inventory_digest"]
    assert {(item["kind"], item["subject"]) for item in observed["blockers"]} == {
        ("protected-fund-inclusion", "umbrella"),
        ("stale-marker-retirement", "paper/umbrella/runner.pid"),
    }
    marker_blocker = next(item for item in observed["blockers"] if item["kind"] == "stale-marker-retirement")
    assert marker_blocker["evidence"]["content_class"] == "pid"
    assert marker_blocker["evidence"]["pid"] == 4242


def test_inspect_source_refuses_evidence_path_inside_source_without_writing(tmp_path):
    source_path = tmp_path / "source-without-staging"
    source_path.mkdir()
    (source_path / "paper").mkdir()
    deploy("alpha", _spec(), ["AAPL"], root=source_path / "paper")
    before = _tree_digest_snapshot(source_path)

    with RootContext.open(source_path) as source:
        with pytest.raises(HandoverError, match="source and target"):
            handover.inspect_relocation_source(source, evidence_out=source_path / handover.SOURCE_EVIDENCE_PATH)

    assert _tree_digest_snapshot(source_path) == before


def test_handover_inspect_lists_attestations_and_remaining_blockers(tmp_path, capsys):
    import hedge_fund.run as run

    source_path = _legacy_relocation_source(tmp_path / "source", protected_fund=True, marker="987654")
    destination_path = tmp_path / "destination"
    destination_path.mkdir()
    with RootContext.open(source_path) as source:
        source_review = handover.inspect_relocation_source(
            source,
            evidence_out=destination_path / handover.SOURCE_EVIDENCE_PATH,
        )

    protected_blocker = next(blocker for blocker in source_review["blockers"] if blocker["kind"] == "protected-fund-inclusion")
    with RootContext.open(source_path) as source, RootContext.open(destination_path) as destination:
        handover.relocate_copy(destination, source=source, expected_content_digest=source_review["content_digest"])
        artifact = handover._new_attestation_artifact(
            destination,
            kind=protected_blocker["kind"],
            subject=protected_blocker["subject"],
            evidence=protected_blocker["evidence"],
            source_evidence_digest=source_review["source_evidence_digest"],
            operator_statement="Synthetic destination retains the original fund identity.",
        )
        handover._write_attestation_artifact(destination, artifact)

    run.main(["--root", str(destination_path), "handover", "inspect"])
    inspected = json.loads(capsys.readouterr().out)

    assert inspected["source_evidence_digest"] == source_review["source_evidence_digest"]
    assert [(artifact["kind"], artifact["subject"]) for artifact in inspected["attestation_artifacts"]] == [("protected-fund-inclusion", "umbrella")]
    assert len(inspected["remaining_blockers"]) == 1
    blocker = inspected["remaining_blockers"][0]
    assert blocker["kind"] == "stale-marker-retirement"
    assert blocker["subject"] == "paper/umbrella/runner.pid"
    assert blocker["resolving_subcommand"] == "handover attest-stale-marker"
    assert blocker["resolving_arguments"] == [
        "--marker",
        "paper/umbrella/runner.pid",
        "--source-evidence",
        source_review["source_evidence_digest"],
        "--operator-statement",
        "<operator statement>",
    ]


def test_handover_inspect_skips_attestation_walk_for_enrolled_root_without_relocation_state(tmp_path, monkeypatch, capsys):
    import hedge_fund.run as run

    root_path = tmp_path / "ordinary-enrolled-root"
    root_path.mkdir()
    (root_path / "mandates").mkdir()
    (root_path / "paper").mkdir()
    (root_path / "research").mkdir()
    with RootContext.open(root_path) as root:
        heads = build_head_inventory(root)
        migrate_existing(
            root,
            expected_inventory_digest=inventory_digest(heads),
            operator_attestation=OPERATOR_ATTESTATION,
        )

    calls = []
    monkeypatch.setattr(handover, "inspect_attestation_state", lambda root: calls.append(root))

    run.main(["--root", str(root_path), "handover", "inspect"])
    inspected = json.loads(capsys.readouterr().out)

    assert calls == []
    assert inspected["state"] == "enrolled"
    assert inspected["source_evidence_digest"] is None
    assert inspected["attestation_artifacts"] == []
    assert inspected["remaining_blockers"] == []


def test_attest_stale_marker_retires_destination_and_refuses_repeat(tmp_path, capsys, owned_test_process):
    import hedge_fund.run as run

    marker_pid = _terminated_dummy_pid(owned_test_process)
    source_path, destination_path, source_review = _copied_destination(tmp_path, marker=f"{marker_pid}\n")
    source_before = _tree_digest_snapshot(source_path)
    marker = "paper/alpha/runner.pid"
    marker_path = destination_path / Path(marker)
    marker_bytes = marker_path.read_bytes()
    command = [
        "--root",
        str(destination_path),
        "handover",
        "attest-stale-marker",
        "--marker",
        marker,
        "--source-evidence",
        source_review["source_evidence_digest"],
        "--operator-statement",
        "Synthetic runner marker belongs to a terminated process.",
    ]

    run.main(command)
    result = json.loads(capsys.readouterr().out)

    assert result["state"] == "attested"
    assert result["kind"] == "stale-marker-retirement"
    assert result["subject"] == marker
    assert result["source_evidence_digest"] == source_review["source_evidence_digest"]
    assert not marker_path.exists()
    with RootContext.open(destination_path) as destination:
        artifact = handover._read_attestation_artifact(destination, kind="stale-marker-retirement", subject=marker)
        assert artifact is not None
        assert artifact["evidence"]["liveness"]["status"] == "not-running"
        retired_path = artifact["evidence"]["retired_marker_path"]
        assert destination.read_bytes(retired_path) == marker_bytes
        assert handover._list_attestation_artifacts(destination) == [artifact]

    before_repeat = _tree_digest_snapshot(destination_path)
    with pytest.raises(SystemExit) as repeated:
        run.main(command)
    error = capsys.readouterr().err
    assert repeated.value.code == 2
    assert "already exists" in error.lower()
    assert result["artifact_path"] in error
    assert _tree_digest_snapshot(destination_path) == before_repeat
    assert _tree_digest_snapshot(source_path) == source_before


def test_attest_stale_marker_rolls_back_partial_artifact_and_marker_move(tmp_path, owned_test_process, monkeypatch):
    marker_pid = _terminated_dummy_pid(owned_test_process)
    source_path, destination_path, source_review = _copied_destination(tmp_path, marker=f"{marker_pid}\n")
    marker = "paper/alpha/runner.pid"
    marker_path = destination_path / Path(marker)
    marker_before = marker_path.read_bytes()
    source_before = _tree_digest_snapshot(source_path)

    def reject_published_artifact(_root, _record, *, source_evidence=None):
        raise handover.HandoverError("synthetic post-publish validation failure")

    monkeypatch.setattr(handover, "_validate_marker_retirement_artifact", reject_published_artifact)
    with RootContext.open(destination_path) as destination:
        with pytest.raises(handover.HandoverError, match="post-publish"):
            handover.attest_stale_marker(
                destination,
                marker=marker,
                source_evidence_digest=source_review["source_evidence_digest"],
                operator_statement="Synthetic rollback restores the copied marker.",
            )
        assert handover._read_attestation_artifact(destination, kind="stale-marker-retirement", subject=marker) is None
        assert handover._list_attestation_artifacts(destination) == []
        with pytest.raises(FileNotFoundError):
            destination.file_info(handover._retired_marker_path(marker))

    assert marker_path.read_bytes() == marker_before
    assert _tree_digest_snapshot(source_path) == source_before


def test_attest_stale_marker_refuses_live_process_without_writes(tmp_path, capsys, owned_test_process):
    import hedge_fund.run as run

    process = owned_test_process("import time; time.sleep(120)")
    marker = "paper/alpha/runner.pid"
    source_path, destination_path, source_review = _copied_destination(tmp_path, marker=f"{process.pid}\n")
    source_before = _tree_digest_snapshot(source_path)
    destination_before = _tree_digest_snapshot(destination_path)
    marker_path = destination_path / Path(marker)
    marker_before = marker_path.read_bytes()
    assert process_identity(process.pid)["pid"] == process.pid

    try:
        with pytest.raises(SystemExit) as denied:
            run.main(
                [
                    "--root",
                    str(destination_path),
                    "handover",
                    "attest-stale-marker",
                    "--marker",
                    marker,
                    "--source-evidence",
                    source_review["source_evidence_digest"],
                    "--operator-statement",
                    "Synthetic live process must block marker retirement.",
                ]
            )
        error = capsys.readouterr().err
        assert denied.value.code == 2
        assert "live process" in error.lower()
        assert "Resolve with:" in error
        assert marker_path.read_bytes() == marker_before
        assert _tree_digest_snapshot(destination_path) == destination_before
        with RootContext.open(destination_path) as destination:
            assert handover._read_attestation_artifact(destination, kind="stale-marker-retirement", subject=marker) is None
    finally:
        process.terminate()
        process.wait(timeout=10)
    assert _tree_digest_snapshot(source_path) == source_before


def test_attest_stale_marker_refuses_unobservable_process_without_writes(tmp_path, capsys, owned_test_process, monkeypatch):
    import hedge_fund.run as run

    marker_pid = _terminated_dummy_pid(owned_test_process)
    source_path, destination_path, source_review = _copied_destination(tmp_path, marker=f"{marker_pid}\n")
    source_before = _tree_digest_snapshot(source_path)
    destination_before = _tree_digest_snapshot(destination_path)

    def unobservable(_pid):
        raise PermissionError("synthetic access denied")

    monkeypatch.setattr(handover, "process_is_running", unobservable)

    with pytest.raises(SystemExit) as denied:
        run.main(
            [
                "--root",
                str(destination_path),
                "handover",
                "attest-stale-marker",
                "--marker",
                "paper/alpha/runner.pid",
                "--source-evidence",
                source_review["source_evidence_digest"],
                "--operator-statement",
                "Synthetic unobservable process must block marker retirement.",
            ]
        )

    error = capsys.readouterr().err
    assert denied.value.code == 2
    assert "liveness" in error.lower() or "process identity" in error.lower()
    assert "Resolve with:" in error
    assert _tree_digest_snapshot(destination_path) == destination_before
    assert _tree_digest_snapshot(source_path) == source_before


def test_attest_stale_marker_second_liveness_denial_leaves_no_partial_storage(tmp_path, capsys, owned_test_process, monkeypatch):
    import hedge_fund.run as run

    marker_pid = _terminated_dummy_pid(owned_test_process)
    source_path, destination_path, source_review = _copied_destination(tmp_path, marker=f"{marker_pid}\n")
    source_before = _tree_digest_snapshot(source_path)
    destination_before = _tree_digest_snapshot(destination_path)
    calls = 0

    def changes_to_live(_pid):
        nonlocal calls
        calls += 1
        return calls == 2

    monkeypatch.setattr(handover, "process_is_running", changes_to_live)
    with pytest.raises(SystemExit) as denied:
        run.main(
            [
                "--root",
                str(destination_path),
                "handover",
                "attest-stale-marker",
                "--marker",
                "paper/alpha/runner.pid",
                "--source-evidence",
                source_review["source_evidence_digest"],
                "--operator-statement",
                "A changing liveness result must leave the copied marker untouched.",
            ]
        )

    assert denied.value.code == 2
    assert "live process" in capsys.readouterr().err
    assert calls == 2
    assert _tree_digest_snapshot(destination_path) == destination_before
    assert _tree_digest_snapshot(source_path) == source_before


def test_attest_stale_marker_refuses_missing_destination_marker_without_writes(tmp_path, capsys, owned_test_process):
    import hedge_fund.run as run

    marker_pid = _terminated_dummy_pid(owned_test_process)
    source_path, destination_path, source_review = _copied_destination(tmp_path, marker=f"{marker_pid}\n")
    source_before = _tree_digest_snapshot(source_path)
    marker = "paper/alpha/runner.pid"
    marker_path = destination_path / Path(marker)
    marker_path.unlink()
    destination_before = _tree_digest_snapshot(destination_path)

    with pytest.raises(SystemExit) as denied:
        run.main(
            [
                "--root",
                str(destination_path),
                "handover",
                "attest-stale-marker",
                "--marker",
                marker,
                "--source-evidence",
                source_review["source_evidence_digest"],
                "--operator-statement",
                "Synthetic missing marker must not create an attestation.",
            ]
        )

    error = capsys.readouterr().err
    assert denied.value.code == 2
    assert "marker" in error.lower() and "missing" in error.lower()
    assert "Resolve with:" in error
    assert _tree_digest_snapshot(destination_path) == destination_before
    assert _tree_digest_snapshot(source_path) == source_before


def test_attest_stale_marker_refuses_source_evidence_digest_mismatch_without_writes(tmp_path, capsys, owned_test_process):
    import hedge_fund.run as run

    marker_pid = _terminated_dummy_pid(owned_test_process)
    source_path, destination_path, source_review = _copied_destination(tmp_path, marker=f"{marker_pid}\n")
    source_before = _tree_digest_snapshot(source_path)
    destination_before = _tree_digest_snapshot(destination_path)

    with pytest.raises(SystemExit) as denied:
        run.main(
            [
                "--root",
                str(destination_path),
                "handover",
                "attest-stale-marker",
                "--marker",
                "paper/alpha/runner.pid",
                "--source-evidence",
                "0" * 64,
                "--operator-statement",
                "Synthetic mismatched evidence must not authorize retirement.",
            ]
        )

    error = capsys.readouterr().err
    assert denied.value.code == 2
    assert "source evidence" in error.lower()
    assert "digest" in error.lower()
    assert "Resolve with:" in error
    assert _tree_digest_snapshot(destination_path) == destination_before
    assert _tree_digest_snapshot(source_path) == source_before


def test_attest_protected_fund_records_original_identity(tmp_path, capsys):
    import hedge_fund.run as run

    source_path, destination_path, source_review = _copied_destination(tmp_path, protected_fund=True)
    source_before = _tree_digest_snapshot(source_path)

    run.main(
        [
            "--root",
            str(destination_path),
            "handover",
            "attest-protected-fund",
            "--fund",
            "umbrella",
            "--source-evidence",
            source_review["source_evidence_digest"],
            "--operator-statement",
            "Synthetic umbrella fund belongs to the operator and keeps its original name.",
        ]
    )
    result = json.loads(capsys.readouterr().out)

    assert result["state"] == "attested"
    assert result["kind"] == "protected-fund-inclusion"
    assert result["subject"] == "umbrella"
    assert result["source_evidence_digest"] == source_review["source_evidence_digest"]
    with RootContext.open(destination_path) as destination:
        artifact = handover._read_attestation_artifact(destination, kind="protected-fund-inclusion", subject="umbrella")
        assert artifact is not None
        assert artifact["evidence"]["fund_file_sha256"] == hashlib.sha256((destination_path / "paper" / "umbrella" / "fund.yaml").read_bytes()).hexdigest()
    assert _tree_digest_snapshot(source_path) == source_before


def test_attest_protected_fund_refuses_repeat_without_changes(tmp_path, capsys):
    import hedge_fund.run as run

    source_path, destination_path, source_review = _copied_destination(tmp_path, protected_fund=True)
    source_before = _tree_digest_snapshot(source_path)
    command = [
        "--root",
        str(destination_path),
        "handover",
        "attest-protected-fund",
        "--fund",
        "umbrella",
        "--source-evidence",
        source_review["source_evidence_digest"],
        "--operator-statement",
        "Synthetic umbrella fund keeps its original identity.",
    ]

    run.main(command)
    result = json.loads(capsys.readouterr().out)
    destination_before_repeat = _tree_digest_snapshot(destination_path)
    with pytest.raises(SystemExit) as repeated:
        run.main(command)

    error = capsys.readouterr().err
    assert repeated.value.code == 2
    assert "already exists" in error.lower()
    assert result["artifact_path"] in error
    assert _tree_digest_snapshot(destination_path) == destination_before_repeat
    assert _tree_digest_snapshot(source_path) == source_before


@pytest.mark.parametrize("fund", ["alpha", "unknown"])
def test_attest_protected_fund_refuses_unprotected_or_unknown_name(tmp_path, capsys, fund):
    import hedge_fund.run as run

    source_path, destination_path, source_review = _copied_destination(tmp_path, protected_fund=True)
    source_before = _tree_digest_snapshot(source_path)
    destination_before = _tree_digest_snapshot(destination_path)

    with pytest.raises(SystemExit) as denied:
        run.main(
            [
                "--root",
                str(destination_path),
                "handover",
                "attest-protected-fund",
                "--fund",
                fund,
                "--source-evidence",
                source_review["source_evidence_digest"],
                "--operator-statement",
                "Synthetic unknown identity must not be included.",
            ]
        )

    error = capsys.readouterr().err
    assert denied.value.code == 2
    assert "protected" in error.lower() or "source evidence" in error.lower()
    assert "Resolve with:" in error
    assert _tree_digest_snapshot(destination_path) == destination_before
    assert _tree_digest_snapshot(source_path) == source_before


def test_attest_protected_fund_cannot_authorize_renamed_identity(tmp_path, capsys):
    import hedge_fund.run as run

    source_path, destination_path, source_review = _copied_destination(tmp_path, protected_fund=True)
    source_before = _tree_digest_snapshot(source_path)
    protected = destination_path / "paper" / "umbrella"
    renamed = destination_path / "paper" / "ordinary"
    protected.rename(renamed)
    fund_file = renamed / "fund.yaml"
    fund_file.write_text(fund_file.read_text(encoding="utf-8").replace("name: umbrella", "name: ordinary"), encoding="utf-8")
    destination_before = _tree_digest_snapshot(destination_path)

    with pytest.raises(SystemExit) as denied:
        run.main(
            [
                "--root",
                str(destination_path),
                "handover",
                "attest-protected-fund",
                "--fund",
                "ordinary",
                "--source-evidence",
                source_review["source_evidence_digest"],
                "--operator-statement",
                "Renaming a synthetic protected fund must not satisfy the original blocker.",
            ]
        )

    error = capsys.readouterr().err
    assert denied.value.code == 2
    assert "protected" in error.lower() or "source evidence" in error.lower()
    assert "Resolve with:" in error
    assert _tree_digest_snapshot(destination_path) == destination_before
    assert _tree_digest_snapshot(source_path) == source_before


def test_full_attested_relocation_keeps_source_tree_hash_identical(tmp_path, capsys, owned_test_process, monkeypatch):
    import hedge_fund.run as run

    monkeypatch.setattr(handover, "out_of_band_exclusion_basis", lambda _root: None)
    marker_pid = _terminated_dummy_pid(owned_test_process)
    source_path = _legacy_relocation_source(tmp_path / "source", protected_fund=True)
    for name in ("watchtower", "watchtower-weekly"):
        _write_protected_source_fund(source_path, name)
    marker_paths = (
        "paper/umbrella/runner.pid",
        "paper/watchtower/runner.pid",
    )
    for marker in marker_paths:
        (source_path / Path(marker)).write_text(f"{marker_pid}\n", encoding="ascii")

    source_before = _tree_digest_snapshot(source_path)
    destination_path = tmp_path / "destination"
    destination_path.mkdir()
    evidence_path = destination_path / Path(handover.SOURCE_EVIDENCE_PATH)
    run.main(
        [
            "--root",
            str(source_path),
            "handover",
            "inspect-source",
            "--evidence-out",
            str(evidence_path),
        ]
    )
    source_review = json.loads(capsys.readouterr().out)

    run.main(
        [
            "--root",
            str(destination_path),
            "handover",
            "relocate-copy",
            str(source_path),
            "--content-digest",
            source_review["content_digest"],
        ]
    )
    capsys.readouterr()

    for marker in marker_paths:
        run.main(
            [
                "--root",
                str(destination_path),
                "handover",
                "attest-stale-marker",
                "--marker",
                marker,
                "--source-evidence",
                source_review["source_evidence_digest"],
                "--operator-statement",
                "Synthetic dead marker is retired at this destination only.",
            ]
        )
        capsys.readouterr()

    for name in ("umbrella", "watchtower", "watchtower-weekly"):
        run.main(
            [
                "--root",
                str(destination_path),
                "handover",
                "attest-protected-fund",
                "--fund",
                name,
                "--source-evidence",
                source_review["source_evidence_digest"],
                "--operator-statement",
                "Synthetic protected fund keeps its original name at this destination.",
            ]
        )
        capsys.readouterr()

    run.main(["--root", str(destination_path), "handover", "relocate-finalize"])
    finalized = json.loads(capsys.readouterr().out)

    assert finalized["mode"] == "relocated"
    assert _tree_digest_snapshot(source_path) == source_before
    with RootContext.open(destination_path) as destination:
        inventory = require_enrollment(destination)["heads"]
        assert build_head_inventory(destination) == inventory
        for name in ("umbrella", "watchtower", "watchtower-weekly"):
            artifact = handover._read_attestation_artifact(destination, kind="protected-fund-inclusion", subject=name)
            assert inventory[name]["attestation_refs"] == [handover._attestation_reference(artifact)]
        for marker in marker_paths:
            artifact = handover._read_attestation_artifact(destination, kind="stale-marker-retirement", subject=marker)
            key = handover._attestation_inventory_key("stale-marker-retirement", marker)
            assert inventory[key] == {
                "kind": "stale-marker-retirement",
                "subject": marker,
                "attestation_digest": artifact["record_digest"],
            }
        forged_inventory = json.loads(json.dumps(inventory))
        forged_inventory["umbrella"]["attestation_refs"][0]["record_digest"] = "0" * 64
        with pytest.raises(EnrollmentInvalid, match="attestation references"):
            handover._validate_enrollment_attestation_refs(destination, forged_inventory)
        assert handover._read_attestation_artifact(destination, kind="protected-fund-inclusion", subject="umbrella") is not None
        assert handover._read_attestation_artifact(destination, kind="stale-marker-retirement", subject=marker_paths[0]) is not None
        with pytest.raises(FileNotFoundError):
            destination.file_info(marker_paths[0])

        review = handover.prepare_single_writer_acknowledgement(destination)
        assert review["write_authority"] == "ownership-unknown"
        assert handover.out_of_band_exclusion_basis(destination) is None
        trusted = handover.trust_single_writer(
            destination,
            expected_inventory_digest=review["inventory_digest"],
            operator_acknowledgement=review["operator_acknowledgement"],
        )
        assert trusted["authority"] == handover.TRUSTED_SINGLE_WRITER_AUTHORITY
        assert handover.write_authority(destination)["authority"] == handover.TRUSTED_SINGLE_WRITER_AUTHORITY

        owner = RootOwnerLease.acquire(destination)
        coordinator = AdmissionCoordinator(destination, owner_lease=owner)
        try:
            with coordinator.manual_session("umbrella", timeout=0):
                assert require_paper_write_lanes(
                    destination.path / "paper" / "umbrella",
                    "umbrella",
                    lane_sets=(("runner",),),
                )
            record = SessionRecord(
                fund="umbrella",
                session="2025-01-21",
                universe=["AAPL"],
                nav=100_000,
                cash=100_000,
                positions={},
                marks={},
                benchmark="SPY",
                benchmark_close=100,
                rebalance=False,
                code_version=code_version(),
                mandate_hash="synthetic",
            )
            record.hash = record.compute_hash()
            ledger = Ledger(destination.path / "paper" / "umbrella")
            with coordinator.manual_session("umbrella", timeout=0):
                appended_path = ledger.append(record)
            assert appended_path.is_file()
            assert ledger.latest().hash == record.hash
            assert verify_ledger_head(destination, "umbrella")["head_hash"] == record.hash
        finally:
            owner.close()
    assert _tree_digest_snapshot(source_path) == source_before


def test_head_inventory_and_finalize_refuse_unattested_protected_fund(tmp_path):
    _, destination_path, _ = _copied_destination(tmp_path, protected_fund=True)
    with RootContext.open(destination_path) as destination:
        with pytest.raises(HandoverError, match="source blocker remains unresolved: umbrella"):
            build_head_inventory(destination)
        with pytest.raises(HandoverError, match="source blocker remains unresolved: umbrella"):
            handover.relocate_finalize(destination)
        with pytest.raises(FileNotFoundError):
            destination.file_info(HANDOVER_PATH)


def test_relocate_copy_transfers_settings_and_finalize_enrolls(tmp_path, monkeypatch):
    source_path = _legacy_relocation_source(tmp_path / "legacy", settings=b'{"model":"synthetic"}')
    destination_path = tmp_path / "destination"
    destination_path.mkdir()
    before = _tree_digest_snapshot(source_path)
    original_build_head_inventory = handover._build_head_inventory
    inventory_roots = []

    def track_inventory(root, **kwargs):
        inventory_roots.append(root.path)
        return original_build_head_inventory(root, **kwargs)

    with RootContext.open(source_path) as source, RootContext.open(destination_path) as destination:
        described = handover.inspect_relocation_source(source)
        monkeypatch.setattr(handover, "_build_head_inventory", track_inventory)
        copied = handover.relocate_copy(destination, source=source, expected_content_digest=described["content_digest"])

        assert copied["state"] == "copied"
        assert destination.path not in inventory_roots
        assert destination.read_bytes(handover.RELOCATED_SETTINGS_PATH) == b'{"model":"synthetic"}'
        assert json.loads(destination.read_bytes(handover.RELOCATION_STATE_PATH))["state"] == "copied"
        with pytest.raises(FileNotFoundError):
            destination.file_info(HANDOVER_PATH)

        record = handover.relocate_finalize(destination)

    assert destination_path in inventory_roots
    assert record["mode"] == "relocated"
    assert _tree_digest_snapshot(source_path) == before


def test_relocate_copy_digest_mismatch_leaves_destination_empty(tmp_path):
    source_path = _legacy_relocation_source(tmp_path / "legacy")
    destination_path = tmp_path / "destination"
    destination_path.mkdir()
    before = _tree_digest_snapshot(source_path)

    with RootContext.open(source_path) as source, RootContext.open(destination_path) as destination:
        with pytest.raises(HandoverError, match="source content changed"):
            handover.relocate_copy(destination, source=source, expected_content_digest="0" * 64)

    assert list(destination_path.iterdir()) == []
    assert _tree_digest_snapshot(source_path) == before


def test_interrupted_relocate_copy_is_marked_incomplete_and_retry_completes(tmp_path, monkeypatch):
    source_path = _legacy_relocation_source(tmp_path / "legacy")
    destination_path = tmp_path / "destination"
    destination_path.mkdir()
    before = _tree_digest_snapshot(source_path)
    original_write = RootContext.write_bytes

    def interrupt_after_first_copy(self, relative, data, **kwargs):
        result = original_write(self, relative, data, **kwargs)
        if os.path.normcase(str(self.path)) == os.path.normcase(str(destination_path)) and str(relative) == "mandates/alpha.yaml":
            raise OSError("synthetic relocation interruption")
        return result

    with RootContext.open(source_path) as source, RootContext.open(destination_path) as destination:
        digest = handover.inspect_relocation_source(source)["content_digest"]
        monkeypatch.setattr(RootContext, "write_bytes", interrupt_after_first_copy)
        with pytest.raises(OSError, match="synthetic relocation interruption"):
            handover.relocate_copy(destination, source=source, expected_content_digest=digest)
        monkeypatch.setattr(RootContext, "write_bytes", original_write)
        state = json.loads(destination.read_bytes(handover.RELOCATION_STATE_PATH))
        assert state["state"] == "incomplete"
        with pytest.raises(FileNotFoundError):
            destination.file_info(HANDOVER_PATH)

        copied = handover.relocate_copy(destination, source=source, expected_content_digest=digest)
        assert copied["state"] == "copied"
        record = handover.relocate_finalize(destination)

    assert record["mode"] == "relocated"
    assert _tree_digest_snapshot(source_path) == before


def test_relocate_copy_process_death_leaves_incomplete_state_and_retry_completes(tmp_path, owned_test_process):
    import time

    source_path = _legacy_relocation_source(tmp_path / "legacy")
    destination_path = tmp_path / "destination"
    destination_path.mkdir()
    pause_path = tmp_path / "copy-paused"
    before = _tree_digest_snapshot(source_path)
    with RootContext.open(source_path) as source:
        digest = handover.inspect_relocation_source(source)["content_digest"]

    script = "\n".join(
        [
            "import os",
            "import time",
            "from pathlib import Path",
            "from hedge_fund.runtime.handover import relocate_copy",
            "from hedge_fund.runtime.root import RootContext",
            f"source_path = Path({str(source_path)!r})",
            f"destination_path = Path({str(destination_path)!r})",
            f"pause_path = Path({str(pause_path)!r})",
            f"digest = {digest!r}",
            "original_write = RootContext.write_bytes",
            "def pause_after_first_copy(self, relative, data, **kwargs):",
            "    result = original_write(self, relative, data, **kwargs)",
            "    if os.path.normcase(os.fspath(self.path)) == os.path.normcase(os.fspath(destination_path)) and str(relative) == 'mandates/alpha.yaml':",
            "        pause_path.write_text('paused', encoding='ascii')",
            "        while True:",
            "            time.sleep(0.01)",
            "    return result",
            "RootContext.write_bytes = pause_after_first_copy",
            "source = RootContext.open(source_path)",
            "destination = RootContext.open(destination_path)",
            "relocate_copy(destination, source=source, expected_content_digest=digest)",
        ]
    )
    child = owned_test_process(script)
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        if pause_path.exists():
            try:
                if pause_path.read_text(encoding="ascii") == "paused":
                    break
            except (OSError, UnicodeError):
                pass
        if child.poll() is not None:
            pytest.fail(f"relocation child exited before copy barrier: {child.returncode}")
        time.sleep(0.02)
    else:
        pytest.fail("relocation child did not reach mid-copy barrier")

    child.terminate()
    child.wait(timeout=10)
    assert child.returncode not in (None, 0)
    assert _tree_digest_snapshot(source_path) == before

    with RootContext.open(destination_path) as destination:
        state = json.loads(destination.read_bytes(handover.RELOCATION_STATE_PATH))
        assert state["state"] == "incomplete"
        assert destination.read_bytes("mandates/alpha.yaml") == (source_path / "mandates" / "alpha.yaml").read_bytes()
        with pytest.raises(FileNotFoundError):
            destination.file_info(HANDOVER_PATH)

    with RootContext.open(source_path) as source, RootContext.open(destination_path) as destination:
        copied = handover.relocate_copy(destination, source=source, expected_content_digest=digest)
        assert copied["state"] == "copied"
        record = handover.relocate_finalize(destination)

    assert record["mode"] == "relocated"
    assert _tree_digest_snapshot(source_path) == before


def test_relocate_copy_keeps_blocked_data_unenrolled_and_source_unchanged(tmp_path):
    source_path = _legacy_relocation_source(tmp_path / "legacy", protected_fund=True, marker="4242\n")
    destination_path = tmp_path / "destination"
    destination_path.mkdir()
    before = _tree_digest_snapshot(source_path)
    evidence_path = destination_path / handover.SOURCE_EVIDENCE_PATH

    with RootContext.open(source_path) as source, RootContext.open(destination_path) as destination:
        described = handover.inspect_relocation_source(source)
        with pytest.raises(HandoverError, match="inspect-source --evidence-out"):
            handover.relocate_copy(destination, source=source, expected_content_digest=described["content_digest"])
        assert list(destination_path.iterdir()) == []

        described = handover.inspect_relocation_source(source, evidence_out=evidence_path)
        copied = handover.relocate_copy(destination, source=source, expected_content_digest=described["content_digest"])

        assert copied["state"] == "copied"
        with pytest.raises(RootPathError, match="protected"):
            destination.read_bytes("paper/umbrella/runner.pid")
        assert (destination_path / "paper" / "umbrella" / "runner.pid").read_bytes() == (source_path / "paper" / "umbrella" / "runner.pid").read_bytes()
        assert (destination_path / "paper" / "umbrella" / "fund.yaml").read_bytes()
        with pytest.raises(HandoverError, match="runner.pid"):
            build_head_inventory(destination)
        with pytest.raises(FileNotFoundError):
            destination.file_info(HANDOVER_PATH)

    assert _tree_digest_snapshot(source_path) == before


def test_fresh_enrollment_requires_empty_root_and_records_fixed_identity(tmp_path):
    root = tmp_path / "fresh"
    root.mkdir()
    with RootContext.open(root) as context:
        record = enroll_fresh(context)
        assert record["mode"] == "fresh"
        assert record["heads"] == {}
        assert require_enrollment(context)["root"]["path"] == os.path.normcase(str(root))

    nonempty = tmp_path / "nonempty"
    nonempty.mkdir()
    (nonempty / "note.txt").write_text("existing", encoding="utf-8")
    with RootContext.open(nonempty) as context:
        with pytest.raises(HandoverError, match="empty root"):
            enroll_fresh(context)

    assert not (nonempty / PRIVATE_ROOT).exists()


def test_child_process_admits_persisted_trust_and_rejects_revocation(
    tmp_path,
    monkeypatch,
    owned_test_process,
    synthetic_runtime_scope,
):
    monkeypatch.setattr(handover, "out_of_band_exclusion_basis", lambda _root: None)
    root_path = tmp_path / "trusted-child"
    root_path.mkdir()
    with RootContext.open(root_path) as root:
        enroll_fresh(root)
        review = handover.prepare_single_writer_acknowledgement(root)
        handover.trust_single_writer(
            root,
            expected_inventory_digest=review["inventory_digest"],
            operator_acknowledgement=review["operator_acknowledgement"],
        )

    def run_child(status_path):
        script = (
            "from pathlib import Path\n"
            "from hedge_fund.runtime import handover\n"
            "from hedge_fund.runtime.admission import RootOwnerLease\n"
            "from hedge_fund.runtime.root import RootContext\n"
            "handover.out_of_band_exclusion_basis = lambda _root: None\n"
            f"handover._runtime_scope_identity = lambda _root: {synthetic_runtime_scope!r}\n"
            f"with RootContext.open({str(root_path)!r}) as root:\n"
            "    try:\n"
            "        owner = RootOwnerLease.acquire(root, timeout=0)\n"
            "        owner.close()\n"
            "        result = 'admitted'\n"
            "    except Exception as exc:\n"
            "        result = type(exc).__name__\n"
            f"Path({str(status_path)!r}).write_text(result, encoding='utf-8')\n"
        )
        child = owned_test_process(script)
        assert child.wait(timeout=30) == 0
        return status_path.read_text(encoding="utf-8")

    assert run_child(tmp_path / "trusted-child.txt") == "admitted"
    with RootContext.open(root_path) as root:
        handover.revoke_single_writer(root)
    assert run_child(tmp_path / "revoked-child.txt") == "OwnershipUnknown"


def test_existing_root_requires_exact_attestation_and_inventory_digest(tmp_path):
    root = tmp_path / "legacy"
    root.mkdir()
    (root / "mandates").mkdir()
    with RootContext.open(root) as context:
        heads = build_head_inventory(context)
        digest = inventory_digest(heads)
        with pytest.raises(HandoverError, match="attestation"):
            migrate_existing(
                context,
                expected_inventory_digest=digest,
                operator_attestation="yes",
            )
        with pytest.raises(HandoverError, match="changed"):
            migrate_existing(
                context,
                expected_inventory_digest="0" * 64,
                operator_attestation=OPERATOR_ATTESTATION,
            )
        record = migrate_existing(
            context,
            expected_inventory_digest=digest,
            operator_attestation=OPERATOR_ATTESTATION,
        )

    assert record["mode"] == "migrate-existing"
    assert record["attestation"]["inventory_digest"] == digest


def test_migration_refuses_any_runner_pid_and_releases_exclusive_lease(tmp_path):
    root = tmp_path / "legacy"
    fund = root / "paper" / "alpha"
    fund.mkdir(parents=True)
    (fund / "runner.pid").write_text("stale-or-unknown", encoding="utf-8")

    with RootContext.open(root) as context:
        with pytest.raises(HandoverError, match="runner.pid"):
            migrate_existing(
                context,
                expected_inventory_digest=inventory_digest({}),
                operator_attestation=OPERATOR_ATTESTATION,
            )
        lease = RootMigrationLease.acquire(context, timeout=0)
        lease.close()

    assert not (root / HANDOVER_PATH).exists()


def test_handover_cli_unenrolled_trust_denial_prints_remedies_without_writing(tmp_path, capsys):
    import hedge_fund.run as run

    root_path = tmp_path / "cli-unenrolled"
    root_path.mkdir()
    before = _tree_digest_snapshot(root_path)

    with pytest.raises(SystemExit) as denied:
        run.main(
            [
                "--root",
                str(root_path),
                "handover",
                "trust-single-writer",
                "--inventory-digest",
                "0" * 64,
                "--operator-acknowledgement",
                "I ACCEPT",
            ]
        )

    assert denied.value.code == 2
    error = capsys.readouterr().err
    assert "private root storage is not verified" in error.lower()
    assert _tree_digest_snapshot(root_path) == before
    assert "handover inspect" in error
    assert "enroll-fresh" in error


@pytest.mark.parametrize(
    ("scenario", "failed_precondition"),
    [
        ("untrusted", "exact root-specific operator acknowledgement is required"),
        ("scope-mismatch", "another runtime"),
        ("inventory-mismatch", "inventory differs"),
        ("second-writer", "another root participant is active"),
    ],
)
def test_handover_cli_denials_print_remedies_without_partial_trust(
    tmp_path,
    monkeypatch,
    capsys,
    synthetic_runtime_scope,
    scenario,
    failed_precondition,
):
    import hedge_fund.run as run

    root_path = _legacy_relocation_source(tmp_path / f"cli-{scenario}")
    with RootContext.open(root_path) as root:
        heads = build_head_inventory(root)
        migrate_existing(
            root,
            expected_inventory_digest=inventory_digest(heads),
            operator_attestation=OPERATOR_ATTESTATION,
        )
        review = handover.prepare_single_writer_acknowledgement(root)
        if scenario == "second-writer":
            handover.trust_single_writer(
                root,
                expected_inventory_digest=review["inventory_digest"],
                operator_acknowledgement=review["operator_acknowledgement"],
            )

        if scenario == "scope-mismatch":
            changed_scope = {**synthetic_runtime_scope, "namespace": synthetic_runtime_scope["namespace"] + ";changed"}
            monkeypatch.setattr(handover, "_runtime_scope_identity", lambda _root: changed_scope)
        elif scenario == "inventory-mismatch":
            fund_file = root_path / "paper" / "alpha" / "fund.yaml"
            fund_file.write_bytes(fund_file.read_bytes() + b"\n# synthetic inventory drift\n")

        def trust_attempt():
            command = ["--root", str(root_path), "handover"]
            if scenario == "second-writer":
                command.append("revoke-single-writer")
            else:
                acknowledgement = "I ACCEPT" if scenario == "untrusted" else review["operator_acknowledgement"]
                command.extend(
                    [
                        "trust-single-writer",
                        "--inventory-digest",
                        review["inventory_digest"],
                        "--operator-acknowledgement",
                        acknowledgement,
                    ]
                )
            with pytest.raises(SystemExit) as denied:
                run.main(command)
            assert denied.value.code == 2
            error = capsys.readouterr().err
            assert failed_precondition in error
            assert "Resolve with:" in error
            assert "handover inspect" in error

        def state_snapshot():
            records = {}
            for relative in (
                HANDOVER_PATH,
                handover.SINGLE_WRITER_CHALLENGE_PATH,
                handover.SINGLE_WRITER_STATE_PATH,
            ):
                try:
                    records[relative] = hashlib.sha256(root.read_bytes(relative)).hexdigest()
                except FileNotFoundError:
                    records[relative] = None
            records["paper"] = _tree_digest_snapshot(root_path / "paper")
            return records

        before = state_snapshot()
        if scenario == "second-writer":
            with RootOwnerLease.acquire(root, timeout=0):
                trust_attempt()
        else:
            trust_attempt()
        assert state_snapshot() == before


def test_inventory_does_not_ignore_directory_walk_errors(tmp_path, monkeypatch):
    root = tmp_path / "synthetic"
    (root / "paper" / "alpha").mkdir(parents=True)

    def failed_walk(_path, *, followlinks, onerror):
        assert followlinks is False
        onerror(PermissionError("synthetic walk failure"))
        yield from ()

    monkeypatch.setattr(handover.os, "walk", failed_walk)
    with RootContext.open(root) as context:
        with pytest.raises(HandoverError, match="paper inventory is unavailable"):
            build_head_inventory(context)


def test_migration_exclusive_lock_conflicts_with_shared_participant(tmp_path):
    root = tmp_path / "fresh"
    root.mkdir()
    with RootContext.open(root) as context:
        enroll_fresh(context)
        participant = RootOwnerLease.acquire(context)
        try:
            with pytest.raises(WriterConflict):
                RootMigrationLease.acquire(context, timeout=0)
        finally:
            participant.close()
        migration = RootMigrationLease.acquire(context, timeout=0)
        migration.close()


@pytest.mark.parametrize("contents", [b"{", b"[]", b"{}"])
def test_malformed_record_denies_participation_without_lease_leak(tmp_path, contents):
    root = tmp_path / "fresh"
    root.mkdir()
    with RootContext.open(root) as context:
        enroll_fresh(context)
        context.write_bytes(HANDOVER_PATH, contents)
        with pytest.raises(EnrollmentInvalid):
            require_enrollment(context)
        with pytest.raises(EnrollmentInvalid):
            RootOwnerLease.acquire(context, timeout=0)
        lease = RootMigrationLease.acquire(context, timeout=0)
        lease.close()


def test_missing_handover_with_admission_artifacts_is_not_legacy(tmp_path):
    root = tmp_path / "fresh"
    root.mkdir()
    with RootContext.open(root) as context:
        enroll_fresh(context)
        (root / HANDOVER_PATH).unlink()

        assert enrollment_status(context) == {
            "state": "invalid",
            "reason": "admission-state-without-handover",
        }


def test_copied_record_is_bound_to_original_root(tmp_path):
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    with RootContext.open(first) as first_context:
        enroll_fresh(first_context)
        copied = first_context.read_bytes(HANDOVER_PATH)
    with RootContext.open(second) as second_context:
        second_context.prepare_private_storage()
        second_context.write_bytes(HANDOVER_PATH, copied)
        with pytest.raises(EnrollmentInvalid, match="identity"):
            require_enrollment(second_context)
        with pytest.raises(EnrollmentInvalid):
            RootOwnerLease.acquire(second_context, timeout=0)
        lease = RootMigrationLease.acquire(second_context, timeout=0)
        lease.close()


def test_unverified_private_storage_denies_participant_before_lock_creation(tmp_path, monkeypatch):
    root = tmp_path / "fresh"
    root.mkdir()
    with RootContext.open(root) as context:
        enroll_fresh(context)
        monkeypatch.setattr(context, "verify_private_storage", lambda: False)
        with pytest.raises(OwnershipUnknown, match="Private root storage"):
            RootOwnerLease.acquire(context, timeout=0)


def test_migration_replays_existing_ledger_and_unexplained_head_drift_fails_closed(tmp_path):
    root = tmp_path / "legacy"
    root.mkdir()
    paper_root = root / "paper"
    paper_root.mkdir()
    directory = deploy("alpha", _spec(), ["AAPL"], root=paper_root)

    with RootContext.open(root) as context:
        heads = build_head_inventory(context)
        migrate_existing(
            context,
            expected_inventory_digest=inventory_digest(heads),
            operator_attestation=OPERATOR_ATTESTATION,
        )
        assert verify_ledger_head(context, "alpha") == heads["alpha"]
        (directory / "fund.yaml").write_text("changed: true\n", encoding="utf-8")
        with pytest.raises(LedgerDrift):
            verify_ledger_head(context, "alpha")


def test_handover_record_digest_detects_tampering(tmp_path):
    root = tmp_path / "fresh"
    root.mkdir()
    with RootContext.open(root) as context:
        enroll_fresh(context)
        record = json.loads(context.read_bytes(HANDOVER_PATH))
        record["build_id"] = "copied-build"
        context.write_bytes(HANDOVER_PATH, json.dumps(record).encode())
        with pytest.raises(EnrollmentInvalid):
            require_enrollment(context)


def _active_runner_state(root, fund="alpha"):
    now = datetime.now(timezone.utc)
    created = now - timedelta(hours=2)
    root.mkdir(f"{RUNNER_ROOT}/{runner_key(fund)}", parents=True, mode=0o700)
    scope = process_identity(os.getpid())
    owner = {
        "pid": 987654321,
        "creation_time": "synthetic-incarnation",
        "image": "synthetic-runner",
        "host": scope["host"],
        "namespace": scope["namespace"],
    }
    return {
        "schema": 1,
        "protocol_version": 1,
        "build_id": code_version(),
        "root": root_binding(root),
        "fund": fund,
        "nonce_hash": "a" * 64,
        "status": "running",
        "created_at": created.isoformat(),
        "expires_at": (created + timedelta(hours=1)).isoformat(),
        "max_sessions": 1,
        "sessions_completed": 0,
        "last_session": None,
        "reason": None,
        "pid": owner["pid"],
        "process_identity": owner,
    }


def _recovery_evidence():
    return {
        "owner_quiescence": "Verified no runner process in the configured namespace.",
        "legacy_exclusion": "Legacy launcher and writable containers disabled for this root.",
    }


def test_stale_reservation_recovery_requires_attestation_and_leaves_no_record_on_denial(tmp_path):
    with RootContext.open(tmp_path) as root:
        enroll_fresh(root)
        write_runner_record(root, "alpha", "state", _active_runner_state(root))
        before = root.read_bytes(f"{RUNNER_ROOT}/{runner_key('alpha')}/state.json")

        with pytest.raises(HandoverError, match="attestation"):
            handover.recover_stale_reservation(
                root,
                "alpha",
                evidence=_recovery_evidence(),
                operator_attestation="not an attestation",
            )

        assert root.read_bytes(f"{RUNNER_ROOT}/{runner_key('alpha')}/state.json") == before
        assert not (tmp_path / handover.RECOVERY_ROOT).exists()


def test_stale_reservation_recovery_records_identity_evidence_and_operator_action(tmp_path):
    with RootContext.open(tmp_path) as root:
        enroll_fresh(root)
        original = _active_runner_state(root)
        write_runner_record(root, "alpha", "state", original)

        record = handover.recover_stale_reservation(
            root,
            "alpha",
            evidence=_recovery_evidence(),
            operator_attestation=handover.STALE_RECOVERY_ATTESTATION,
        )

        relative = f"{handover.RECOVERY_ROOT}/{runner_key('alpha')}/{original['nonce_hash']}.json"
        persisted = json.loads(root.read_bytes(relative))
        assert record == persisted
        assert persisted["root"] == root_binding(root)
        assert persisted["build_id"] == code_version()
        assert persisted["protocol_version"] == 1
        assert persisted["prior_owner_identity"]["process_identity"] == original["process_identity"]
        assert persisted["evidence"] == _recovery_evidence()
        assert persisted["operator_attestation"] == handover.STALE_RECOVERY_ATTESTATION
        assert len(persisted["record_digest"]) == 64
        assert handover.require_enrollment(root)["heads"] == {}
        assert handover.read_stale_recovery(root, "alpha") == persisted
        assert read_runner_record(root, "alpha", "state")["status"] == "failed"


def test_stale_reservation_recovery_rejects_owner_from_another_host_namespace(tmp_path):
    with RootContext.open(tmp_path) as root:
        enroll_fresh(root)
        original = _active_runner_state(root)
        foreign = {**original["process_identity"], "namespace": "foreign-namespace"}
        write_runner_record(root, "alpha", "state", {**original, "process_identity": foreign})
        before = root.read_bytes(f"{RUNNER_ROOT}/{runner_key('alpha')}/state.json")

        with pytest.raises(HandoverError, match="process identity"):
            handover.recover_stale_reservation(
                root,
                "alpha",
                evidence=_recovery_evidence(),
                operator_attestation=handover.STALE_RECOVERY_ATTESTATION,
            )

        assert root.read_bytes(f"{RUNNER_ROOT}/{runner_key('alpha')}/state.json") == before
        assert handover.read_stale_recovery(root, "alpha") is None


def test_stale_reservation_recovery_waits_for_shared_root_owners(tmp_path):
    with RootContext.open(tmp_path) as root:
        enroll_fresh(root)
        write_runner_record(root, "alpha", "state", _active_runner_state(root))
        participant = RootOwnerLease.acquire(root)
        try:
            with pytest.raises(HandoverError, match="quiescence"):
                handover.recover_stale_reservation(
                    root,
                    "alpha",
                    evidence=_recovery_evidence(),
                    operator_attestation=handover.STALE_RECOVERY_ATTESTATION,
                )
            assert not (tmp_path / handover.RECOVERY_ROOT).exists()
        finally:
            participant.close()
