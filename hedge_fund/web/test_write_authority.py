"""Web write authority: non-native or legacy-reachable roots are read-only."""

import pytest
from fastapi.testclient import TestClient

from hedge_fund.paper.ledger import Ledger
from hedge_fund.runtime import handover
from hedge_fund.runtime.handover import (
    build_head_inventory,
    inventory_digest,
    migrate_existing,
    OPERATOR_ATTESTATION,
)
from hedge_fund.runtime.root import RootContext
from hedge_fund.web.app import create_app
from hedge_fund.web.services import DeskService, ServiceError


def test_attested_migration_root_is_served_read_only_without_mutation_token(tmp_path, monkeypatch):
    root = tmp_path / "attested"
    (root / "mandates").mkdir(parents=True)
    with RootContext.open(root) as context:
        migrate_existing(context, expected_inventory_digest=inventory_digest(build_head_inventory(context)), operator_attestation=OPERATOR_ATTESTATION)

    monkeypatch.setattr(
        handover,
        "_runtime_scope_identity",
        lambda _root: {
            "kind": "linux-pid1",
            "pid1": {
                "pid": 1,
                "creation_time": "987654",
                "image": "/usr/bin/synthetic-supervisor",
                "host": "synthetic-boot-id",
                "namespace": "4026533000",
            },
            "namespace": "pid:[4026533000];mnt:[4026533001]",
        },
    )

    with TestClient(create_app(root=root, allow_writes=True), client=("127.0.0.1", 50000)) as client:
        capabilities = client.get("/api/capabilities", headers={"host": "127.0.0.1"}).json()

    assert capabilities["enrollment_state"] == "enrolled"
    assert capabilities["write_authority"] == "ownership-unknown"
    assert capabilities["write_unavailable_reason"] == "attested-migration-read-only"
    assert capabilities["writes"] is False
    assert capabilities["read_only"] is True
    assert capabilities["network"] is False
    assert capabilities["mutation_token"] is None


def test_service_revokes_writes_and_halt_when_a_legacy_runner_appears(demo_root):
    service = DeskService(demo_root, allow_writes=True, demo=True)
    try:
        assert service.capabilities("token")["write_authority"] == "protocol-native"
        assert service.capabilities("token")["writes"] is True
        runner_pid = demo_root / "paper" / "demo-quality" / "runner.pid"
        runner_pid.write_text("4242", encoding="utf-8")

        with pytest.raises(ServiceError) as halted:
            service.halt_fund("demo-quality", "legacy writer appeared", "halt-legacy-writer-001")
        assert halted.value.status_code in {403, 409}
        assert Ledger(demo_root / "paper" / "demo-quality").halted() is None

        with pytest.raises(ServiceError) as denied:
            service._require_writes()
        assert denied.value.status_code == 403
        capabilities = service.capabilities("token")
        assert capabilities["writes"] is False
        assert capabilities["write_authority"] == "ownership-unknown"
        assert capabilities["write_unavailable_reason"] == "legacy-runner-present"
        assert capabilities["mutation_token"] is None
        with pytest.raises(ServiceError) as after:
            service.halt_fund("demo-quality", "legacy writer appeared", "halt-legacy-writer-002")
        assert after.value.status_code == 403
        assert Ledger(demo_root / "paper" / "demo-quality").halted() is None
    finally:
        service.close()


def test_capabilities_reclassify_authority_without_a_prior_write_attempt(demo_root):
    service = DeskService(demo_root, allow_writes=True, demo=True)
    try:
        assert service.capabilities("token")["mutation_token"] == "token"
        (demo_root / "paper" / "demo-quality" / "runner.pid").write_text("4242", encoding="utf-8")

        capabilities = service.capabilities("token")
        assert capabilities["writes"] is False
        assert capabilities["network"] is False
        assert capabilities["write_authority"] == "ownership-unknown"
        assert capabilities["write_unavailable_reason"] == "legacy-runner-present"
        assert capabilities["mutation_token"] is None
        assert service._owner_lease is None
        with pytest.raises(ServiceError) as halted:
            service.halt_fund("demo-quality", "legacy writer appeared", "halt-legacy-writer-003")
        assert halted.value.status_code == 403
        assert Ledger(demo_root / "paper" / "demo-quality").halted() is None
    finally:
        service.close()
