import pytest

from hedge_fund import paths
from hedge_fund.fund import FundSpec
from hedge_fund.fund.storage import save_spec, StorageAdmissionError
from hedge_fund.runtime.admission import (
    AdmissionCoordinator,
    RootMigrationLease,
    RootOwnerLease,
)
from hedge_fund.runtime.handover import enroll_fresh
from hedge_fund.runtime.root import RootContext


def _spec(name="alpha"):
    return FundSpec.model_validate(
        {
            "schema_version": 2,
            "name": name,
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


def test_save_spec_fails_closed_when_shared_admission_is_unavailable(tmp_path):
    with RootContext.open(tmp_path) as root:
        enroll_fresh(root)
        migration = RootMigrationLease.acquire(root, timeout=0)
        try:
            with paths.bound_root(root):
                with pytest.raises(StorageAdmissionError):
                    save_spec(_spec(), tmp_path / "mandates")
        finally:
            migration.close()

        assert not (tmp_path / "mandates").exists()


def test_save_spec_uses_root_context_and_registry_lane(tmp_path):
    with RootContext.open(tmp_path) as root:
        enroll_fresh(root)
        owner = RootOwnerLease.acquire(root)
        admission = AdmissionCoordinator(root, owner_lease=owner)
        with paths.bound_root(root):
            try:
                path = save_spec(_spec(), tmp_path / "mandates", admission=admission)
            finally:
                owner.close()

        assert path == tmp_path / "mandates" / "alpha.yaml"
        assert path.read_text(encoding="utf-8").startswith("schema_version: 2")


def test_save_spec_denial_preserves_existing_bytes(tmp_path):
    target = tmp_path / "mandates" / "alpha.yaml"
    target.parent.mkdir()
    target.write_bytes(b"reviewed bytes")

    with RootContext.open(tmp_path) as root:
        with paths.bound_root(root):
            before = target.read_bytes()
            with pytest.raises(StorageAdmissionError):
                save_spec(_spec(), target.parent)

            assert target.read_bytes() == before
