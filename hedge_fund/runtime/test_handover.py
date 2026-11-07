import json
import os
from datetime import datetime, timedelta, timezone

import pytest

from hedge_fund.fund import FundSpec
from hedge_fund.paper.deployed import deploy
from hedge_fund.pipeline.session import code_version
from hedge_fund.runtime import handover
from hedge_fund.runtime.admission import (
    OwnershipUnknown,
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
from hedge_fund.runtime.ownership import process_identity
from hedge_fund.runtime.root import PRIVATE_ROOT, RootContext


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
