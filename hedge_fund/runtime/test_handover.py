import json
import os

import pytest

from hedge_fund.fund import FundSpec
from hedge_fund.paper.deployed import deploy
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
    verify_ledger_head,
)
from hedge_fund.runtime.root import PRIVATE_ROOT, RootContext


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
