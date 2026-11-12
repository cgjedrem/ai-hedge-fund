"""Write-authority classification and relocation import.

Existing roots stay read-only without explicit root-specific operator trust.
Every test uses isolated synthetic roots and a synthetic HOME.
"""

import hashlib
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from hedge_fund.fund import FundSpec
from hedge_fund.paper.deployed import deploy
from hedge_fund.pipeline.session import code_version
from hedge_fund.runtime import handover
from hedge_fund.runtime.admission import OwnershipUnknown, RootOwnerLease
from hedge_fund.runtime.handover import build_head_inventory, enroll_fresh, enrollment_status, HANDOVER_PATH, HandoverError, inspect_relocation_source, inventory_digest, migrate_existing, OPERATOR_ATTESTATION, relocate_existing, require_enrollment, require_write_authority, write_authority, WriteAuthorityDenied
from hedge_fund.runtime.root import RootContext

_ORIGINAL_RUNTIME_SCOPE_IDENTITY = handover._runtime_scope_identity


@pytest.fixture(autouse=True)
def synthetic_home(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    for variable in ("HOME", "USERPROFILE"):
        monkeypatch.setenv(variable, str(home))
    monkeypatch.delenv("HOMEDRIVE", raising=False)
    monkeypatch.delenv("HOMEPATH", raising=False)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    monkeypatch.setattr(
        handover,
        "_runtime_scope_identity",
        lambda _root: _synthetic_runtime_scope("100"),
    )
    return home


def _spec(name="alpha", **updates):
    spec = FundSpec.model_validate(
        {
            "schema_version": 2,
            "name": name,
            "strategies": [{"name": "solo", "models": [{"name": "graham"}], "blend": {"mode": "long_short"}}],
            "risk": {"max_position_pct": 1, "max_gross_exposure": 1},
            "capital": 100_000,
            "costs": {"spread_bps": 0, "commission_per_share": 0},
            "rebalance": "daily",
        }
    )
    return spec.model_copy(update=updates) if updates else spec


def _legacy_source(path: Path) -> Path:
    path.mkdir()
    (path / "paper").mkdir()
    deploy("alpha", _spec(), ["AAPL"], root=path / "paper")
    (path / "paper" / "alpha" / ".paper-audit.lock").write_bytes(b"")
    (path / "mandates").mkdir()
    (path / "mandates" / "alpha.yaml").write_text("name: alpha\n", encoding="utf-8")
    (path / "research" / "alpha").mkdir(parents=True)
    (path / "research" / "alpha" / "note.json").write_text("{}", encoding="utf-8")
    (path / "research" / "empty").mkdir()
    (path / ".env").write_text("SYNTHETIC_ONLY=1\n", encoding="utf-8")
    (path / "cache" / "llm").mkdir(parents=True)
    (path / "cache" / "llm" / "entry.json").write_text("{}", encoding="utf-8")
    return path


def _tree(path: Path) -> dict[str, object]:
    observed: dict[str, object] = {}
    for item in sorted(path.rglob("*")):
        relative = item.relative_to(path).as_posix()
        if item.is_dir():
            observed[relative] = "dir"
        else:
            stat = item.stat()
            observed[relative] = (hashlib.sha256(item.read_bytes()).hexdigest(), stat.st_mtime_ns)
    return observed


def _filesystem_snapshot(path: Path) -> dict[str, object]:
    observed: dict[str, object] = {}
    items = [path, *sorted(path.rglob("*"))]
    for item in items:
        relative = "." if item == path else item.relative_to(path).as_posix()
        info = item.lstat()
        if item.is_symlink():
            observed[relative] = ("symlink", os.readlink(item), info.st_mode, info.st_mtime_ns)
        elif item.is_dir():
            observed[relative] = ("dir", info.st_mode, info.st_mtime_ns)
        else:
            observed[relative] = (
                "file",
                hashlib.sha256(item.read_bytes()).hexdigest(),
                info.st_mode,
                info.st_size,
                info.st_mtime_ns,
            )
    return observed


def _synthetic_runtime_scope(creation_time: str) -> dict[str, object]:
    return {
        "kind": "linux-pid1",
        "pid1": {
            "pid": 1,
            "creation_time": creation_time,
            "image": "/sbin/init",
            "host": "synthetic-boot-id",
            "namespace": "4026533000",
        },
        "namespace": "pid:[4026533000];mnt:[4026533001]",
    }


def test_linux_runtime_scope_uses_pid1_identity_and_checks_root_boot_and_namespaces(tmp_path, monkeypatch):
    root_path = tmp_path / "linux-scope"
    root_path.mkdir()
    pid1 = {
        "pid": 1,
        "creation_time": "123456",
        "image": "/usr/bin/aihf-web-supervisor",
        "host": "synthetic-boot-id",
        "namespace": "4026533000",
    }
    calls = []

    def process_identity(pid):
        calls.append(pid)
        return pid1

    fake_os = SimpleNamespace(
        name="posix",
        readlink=lambda name: {
            "/proc/self/ns/pid": "pid:[4026533000]",
            "/proc/self/ns/mnt": "mnt:[4026533001]",
        }[name],
        stat=lambda name: SimpleNamespace(st_ino=4026533000) if name == "/proc/self/ns/pid" else None,
    )
    monkeypatch.setattr(handover, "_runtime_scope_identity", _ORIGINAL_RUNTIME_SCOPE_IDENTITY)
    monkeypatch.setattr(handover, "sys", SimpleNamespace(platform="linux"))
    monkeypatch.setattr(handover, "os", fake_os)
    monkeypatch.setattr(handover, "process_identity", process_identity)
    with RootContext.open(root_path) as root:
        root.boot_identity = "synthetic-boot-id"
        root.namespace_identity = "pid:pid:[4026533000];mnt:mnt:[4026533001]"
        scope = handover._runtime_scope_identity(root)
        root.boot_identity = "different-boot-id"
        with pytest.raises(HandoverError, match="incomplete"):
            handover._runtime_scope_identity(root)

    assert calls == [1, 1]
    assert scope == {
        "kind": "linux-pid1",
        "pid1": pid1,
        "namespace": "pid:pid:[4026533000];mnt:mnt:[4026533001]",
    }


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("creation_time", "1" * 21),
        ("creation_time", "18446744073709551616"),
        ("namespace", "1" * 21),
        ("namespace", "18446744073709551616"),
    ],
)
def test_linux_runtime_scope_rejects_unbounded_pid1_numbers(tmp_path, monkeypatch, field, value):
    root_path = tmp_path / "linux-scope-bounds"
    root_path.mkdir()
    pid_namespace = value if field == "namespace" else "4026533000"
    pid1 = {
        "pid": 1,
        "creation_time": "123456",
        "image": "/usr/bin/aihf-web-supervisor",
        "host": "synthetic-boot-id",
        "namespace": pid_namespace,
    }
    pid1[field] = value
    expected_namespace = f"pid:pid:[{pid_namespace}];mnt:mnt:[4026533001]"
    fake_os = SimpleNamespace(
        name="posix",
        readlink=lambda name: {
            "/proc/self/ns/pid": f"pid:[{pid_namespace}]",
            "/proc/self/ns/mnt": "mnt:[4026533001]",
        }[name],
        stat=lambda name: SimpleNamespace(st_ino=int(pid_namespace)) if name == "/proc/self/ns/pid" else None,
    )
    monkeypatch.setattr(handover, "_runtime_scope_identity", _ORIGINAL_RUNTIME_SCOPE_IDENTITY)
    monkeypatch.setattr(handover, "sys", SimpleNamespace(platform="linux"))
    monkeypatch.setattr(handover, "os", fake_os)
    monkeypatch.setattr(handover, "process_identity", lambda _pid: pid1)

    with RootContext.open(root_path) as root:
        root.boot_identity = "synthetic-boot-id"
        root.namespace_identity = expected_namespace
        with pytest.raises(HandoverError, match="incomplete"):
            handover._runtime_scope_identity(root)


def test_windows_runtime_scope_binds_machine_account_and_volume(tmp_path, monkeypatch):
    root_path = tmp_path / "windows-scope"
    root_path.mkdir()
    monkeypatch.setattr(handover, "_runtime_scope_identity", _ORIGINAL_RUNTIME_SCOPE_IDENTITY)
    monkeypatch.setattr(handover, "sys", SimpleNamespace(platform="win32"))
    monkeypatch.setattr(handover, "_windows_current_user_sid", lambda: "S-1-5-21-100-200-300-1001")

    with RootContext.open(root_path) as root:
        scope = handover._runtime_scope_identity(root)

    assert scope == {
        "kind": "windows-user-volume",
        "machine": root.host_identity.casefold(),
        "operator_sid": "S-1-5-21-100-200-300-1001",
        "volume": root.device_identity.casefold(),
    }


def test_windows_trust_scope_mismatch_requires_fresh_review(tmp_path, monkeypatch):
    monkeypatch.setattr(handover, "out_of_band_exclusion_basis", lambda _root: None)
    runtime = {
        "scope": {
            "kind": "windows-user-volume",
            "machine": "synthetic-machine",
            "operator_sid": "S-1-5-21-100-200-300-1001",
            "volume": "c:synthetic-volume",
        }
    }
    monkeypatch.setattr(handover, "_runtime_scope_identity", lambda _root: runtime["scope"])
    root_path = _legacy_source(tmp_path / "windows-trust")
    with RootContext.open(root_path) as root:
        heads = build_head_inventory(root)
        migrate_existing(
            root,
            expected_inventory_digest=inventory_digest(heads),
            operator_attestation=OPERATOR_ATTESTATION,
        )
        first_review = handover.prepare_single_writer_acknowledgement(root)
        first_trust = handover.trust_single_writer(
            root,
            expected_inventory_digest=first_review["inventory_digest"],
            operator_acknowledgement=first_review["operator_acknowledgement"],
        )
        assert first_trust["authority"] == "operator-trusted-single-writer"

        prior_state = root.read_bytes(handover.SINGLE_WRITER_STATE_PATH)
        runtime["scope"] = {**runtime["scope"], "operator_sid": "S-1-5-21-100-200-300-1002"}
        assert handover.write_authority(root) == {
            "authority": "ownership-unknown",
            "reason": "operator-single-writer-runtime-scope-changed",
        }
        fresh_review = handover.prepare_single_writer_acknowledgement(root)
        with pytest.raises(HandoverError, match="acknowledgement"):
            handover.trust_single_writer(
                root,
                expected_inventory_digest=fresh_review["inventory_digest"],
                operator_acknowledgement=first_review["operator_acknowledgement"],
            )
        assert root.read_bytes(handover.SINGLE_WRITER_STATE_PATH) == prior_state

        second_trust = handover.trust_single_writer(
            root,
            expected_inventory_digest=fresh_review["inventory_digest"],
            operator_acknowledgement=fresh_review["operator_acknowledgement"],
        )
        assert second_trust["authority"] == "operator-trusted-single-writer"
        assert fresh_review["runtime_scope"] == runtime["scope"]


def _link_directory(link: Path, target: Path) -> None:
    if os.name == "nt":
        import _winapi

        _winapi.CreateJunction(str(target), str(link))
    else:
        os.symlink(target, link, target_is_directory=True)


def _migrated(tmp_path: Path) -> Path:
    root = _legacy_source(tmp_path / "attested")
    with RootContext.open(root) as context:
        heads = build_head_inventory(context)
        migrate_existing(context, expected_inventory_digest=inventory_digest(heads), operator_attestation=OPERATOR_ATTESTATION)
    return root


def test_attested_migration_is_ownership_unknown_for_every_writer_entry(tmp_path):
    root = _migrated(tmp_path)
    with RootContext.open(root) as context:
        assert enrollment_status(context)["state"] == "enrolled"
        assert write_authority(context) == {"authority": "ownership-unknown", "reason": "attested-migration-read-only"}
        with pytest.raises(WriteAuthorityDenied):
            require_write_authority(context)
        with pytest.raises(OwnershipUnknown, match="read-only"):
            RootOwnerLease.acquire(context)


def test_fresh_root_is_protocol_native(tmp_path):
    fresh = tmp_path / "fresh"
    fresh.mkdir()
    with RootContext.open(fresh) as context:
        enroll_fresh(context)
        assert write_authority(context) == {"authority": "protocol-native", "reason": None}
        RootOwnerLease.acquire(context).close()


def test_existing_root_needs_fresh_root_bound_trust_ack_and_revocation_is_fail_closed(tmp_path, monkeypatch):
    monkeypatch.setattr(handover, "out_of_band_exclusion_basis", lambda _root: None)
    root = _legacy_source(tmp_path / "attested")
    with RootContext.open(root) as context:
        heads = build_head_inventory(context)
        migrate_existing(
            context,
            expected_inventory_digest=inventory_digest(heads),
            operator_attestation=OPERATOR_ATTESTATION,
        )
        assert write_authority(context) == {
            "authority": "ownership-unknown",
            "reason": "attested-migration-read-only",
        }

        review = handover.prepare_single_writer_acknowledgement(context)
        acknowledgement = review["operator_acknowledgement"]
        assert acknowledgement
        assert review["inventory_digest"] == inventory_digest(heads)
        with pytest.raises(HandoverError, match="acknowledgement"):
            handover.trust_single_writer(
                context,
                expected_inventory_digest=review["inventory_digest"],
                operator_acknowledgement="I ACCEPT",
            )
        assert write_authority(context)["authority"] == "ownership-unknown"

        trust = handover.trust_single_writer(
            context,
            expected_inventory_digest=review["inventory_digest"],
            operator_acknowledgement=acknowledgement,
        )
        assert trust["authority"] == "operator-trusted-single-writer"
        assert handover.has_write_authority(trust)
        RootOwnerLease.acquire(context).close()

        revoked = handover.revoke_single_writer(context)
        assert revoked["authority"] == "ownership-unknown"
        assert revoked["reason"] == "operator-single-writer-acknowledgement-revoked"
        with pytest.raises(OwnershipUnknown):
            RootOwnerLease.acquire(context)
        with pytest.raises(HandoverError, match="stale|challenge"):
            handover.trust_single_writer(
                context,
                expected_inventory_digest=review["inventory_digest"],
                operator_acknowledgement=acknowledgement,
            )

        renewed_review = handover.prepare_single_writer_acknowledgement(context)
        assert renewed_review["operator_acknowledgement"] != acknowledgement
        renewed = handover.trust_single_writer(
            context,
            expected_inventory_digest=renewed_review["inventory_digest"],
            operator_acknowledgement=renewed_review["operator_acknowledgement"],
        )
        assert renewed["authority"] == "operator-trusted-single-writer"


@pytest.mark.parametrize(
    "scenario",
    ("unenrolled", "untrusted", "scope-mismatch", "inventory-mismatch", "second-writer"),
)
def test_denial_matrix_never_creates_partial_state(tmp_path, monkeypatch, scenario):
    if scenario == "unenrolled":
        root_path = tmp_path / "unenrolled-denial"
        root_path.mkdir()
        with RootContext.open(root_path) as root:
            root.prepare_private_storage()
            before = _filesystem_snapshot(root_path)
            assert enrollment_status(root) == {"state": "unenrolled", "reason": "handover-required"}
            assert write_authority(root) == {"authority": "unavailable", "reason": "handover-required"}
            with pytest.raises(handover.HandoverRequired):
                require_write_authority(root)
            assert _filesystem_snapshot(root_path) == before
        return

    monkeypatch.setattr(handover, "out_of_band_exclusion_basis", lambda _root: None)
    runtime = {"scope": _synthetic_runtime_scope("100")}
    monkeypatch.setattr(handover, "_runtime_scope_identity", lambda _root: runtime["scope"])
    root_path = _legacy_source(tmp_path / f"denial-{scenario}")
    with RootContext.open(root_path) as root:
        heads = build_head_inventory(root)
        migrate_existing(
            root,
            expected_inventory_digest=inventory_digest(heads),
            operator_attestation=OPERATOR_ATTESTATION,
        )
        if scenario == "untrusted":
            before = _filesystem_snapshot(root_path)
            assert write_authority(root) == {
                "authority": "ownership-unknown",
                "reason": "attested-migration-read-only",
            }
            with pytest.raises(WriteAuthorityDenied, match="acknowledgement"):
                require_write_authority(root)
            assert _filesystem_snapshot(root_path) == before
            return

        review = handover.prepare_single_writer_acknowledgement(root)
        handover.trust_single_writer(
            root,
            expected_inventory_digest=review["inventory_digest"],
            operator_acknowledgement=review["operator_acknowledgement"],
        )
        if scenario == "scope-mismatch":
            runtime["scope"] = _synthetic_runtime_scope("200")
            before = _filesystem_snapshot(root_path)
            assert write_authority(root)["reason"] == "operator-single-writer-runtime-scope-changed"
            with pytest.raises(WriteAuthorityDenied, match="another runtime"):
                require_write_authority(root)
            assert _filesystem_snapshot(root_path) == before
            return

        if scenario == "inventory-mismatch":
            fund_file = root_path / "paper" / "alpha" / "fund.yaml"
            fund_file.write_bytes(fund_file.read_bytes() + b"\n# synthetic inventory drift\n")
            before = _filesystem_snapshot(root_path)
            with pytest.raises(handover.LedgerDrift, match="inventory"):
                handover.verify_root_inventory(root)
            assert _filesystem_snapshot(root_path) == before
            return

        from hedge_fund.runtime.admission import AdmissionCoordinator, WriterConflict

        with RootOwnerLease.acquire(root, timeout=0) as owner:
            admission = AdmissionCoordinator(root, owner_lease=owner)
            with admission.control_lane("alpha", timeout=0):
                paper_path = root_path / "paper" / "alpha"
                before_paper = _filesystem_snapshot(paper_path)
                before_handover = root.read_bytes(HANDOVER_PATH)
                before_trust = root.read_bytes(handover.SINGLE_WRITER_STATE_PATH)
                with pytest.raises(WriterConflict):
                    with admission.control_lane("alpha", timeout=0):
                        pytest.fail("second participating writer entered the held lane")
                assert _filesystem_snapshot(paper_path) == before_paper
                assert root.read_bytes(HANDOVER_PATH) == before_handover
                assert root.read_bytes(handover.SINGLE_WRITER_STATE_PATH) == before_trust


def test_trusted_authority_is_bound_to_pid1_incarnation_and_retrust_is_explicit(tmp_path, monkeypatch):
    monkeypatch.setattr(handover, "out_of_band_exclusion_basis", lambda _root: None)
    runtime = {"scope": _synthetic_runtime_scope("100")}
    monkeypatch.setattr(
        handover,
        "_runtime_scope_identity",
        lambda _root: runtime["scope"],
        raising=False,
    )
    root_path = _legacy_source(tmp_path / "runtime-bound")
    with RootContext.open(root_path) as root:
        heads = build_head_inventory(root)
        migrate_existing(
            root,
            expected_inventory_digest=inventory_digest(heads),
            operator_attestation=OPERATOR_ATTESTATION,
        )
        enrollment_root = require_enrollment(root)["root"]
        review_a = handover.prepare_single_writer_acknowledgement(root)
        assert review_a["runtime_scope"] == runtime["scope"]
        trust_a = handover.trust_single_writer(
            root,
            expected_inventory_digest=review_a["inventory_digest"],
            operator_acknowledgement=review_a["operator_acknowledgement"],
        )
        state_a = json.loads(root.read_bytes(handover.SINGLE_WRITER_STATE_PATH))
        assert trust_a["authority"] == "operator-trusted-single-writer"
        assert write_authority(root)["authority"] == "operator-trusted-single-writer"
        assert state_a["runtime_scope"] == runtime["scope"]
        assert handover.root_binding(root) == enrollment_root
        assert "runtime_scope" not in enrollment_root

        runtime["scope"] = _synthetic_runtime_scope("200")
        assert runtime["scope"]["pid1"]["namespace"] == state_a["runtime_scope"]["pid1"]["namespace"]
        before_denial = _filesystem_snapshot(root_path)
        assert write_authority(root) == {
            "authority": "ownership-unknown",
            "reason": "operator-single-writer-runtime-scope-changed",
        }
        with pytest.raises(WriteAuthorityDenied, match="another runtime"):
            require_write_authority(root)
        with pytest.raises(OwnershipUnknown):
            RootOwnerLease.acquire(root)
        assert _filesystem_snapshot(root_path) == before_denial

        review_b = handover.prepare_single_writer_acknowledgement(root)
        assert review_b["runtime_scope"] == runtime["scope"]
        with pytest.raises(HandoverError, match="inventory"):
            handover.trust_single_writer(
                root,
                expected_inventory_digest="0" * 64,
                operator_acknowledgement=review_b["operator_acknowledgement"],
            )
        assert write_authority(root)["authority"] == "ownership-unknown"

        review_b = handover.prepare_single_writer_acknowledgement(root)
        with pytest.raises(HandoverError, match="acknowledgement"):
            handover.trust_single_writer(
                root,
                expected_inventory_digest=review_b["inventory_digest"],
                operator_acknowledgement="I ACCEPT",
            )
        assert root.read_bytes(handover.SINGLE_WRITER_STATE_PATH) == json.dumps(
            state_a,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        assert write_authority(root)["authority"] == "ownership-unknown"

        review_b = handover.prepare_single_writer_acknowledgement(root)
        trust_b = handover.trust_single_writer(
            root,
            expected_inventory_digest=review_b["inventory_digest"],
            operator_acknowledgement=review_b["operator_acknowledgement"],
        )
        state_b = json.loads(root.read_bytes(handover.SINGLE_WRITER_STATE_PATH))
        assert trust_b["authority"] == "operator-trusted-single-writer"
        assert state_b["runtime_scope"] == runtime["scope"]
        assert state_b["schema"] == 2
        assert state_b["challenge_id"] != state_a["challenge_id"]
        assert write_authority(root)["authority"] == "operator-trusted-single-writer"
        assert require_enrollment(root)["root"] == enrollment_root

        runtime["scope"] = _synthetic_runtime_scope("300")
        before_second_denial = _filesystem_snapshot(root_path)
        assert write_authority(root)["reason"] == "operator-single-writer-runtime-scope-changed"
        with pytest.raises(WriteAuthorityDenied):
            require_write_authority(root)
        assert _filesystem_snapshot(root_path) == before_second_denial


def test_single_writer_review_cannot_cross_pid1_incarnations(tmp_path, monkeypatch):
    monkeypatch.setattr(handover, "out_of_band_exclusion_basis", lambda _root: None)
    runtime = {"scope": _synthetic_runtime_scope("100")}
    monkeypatch.setattr(
        handover,
        "_runtime_scope_identity",
        lambda _root: runtime["scope"],
        raising=False,
    )
    root_path = _legacy_source(tmp_path / "runtime-review")
    with RootContext.open(root_path) as root:
        heads = build_head_inventory(root)
        migrate_existing(
            root,
            expected_inventory_digest=inventory_digest(heads),
            operator_attestation=OPERATOR_ATTESTATION,
        )
        review = handover.prepare_single_writer_acknowledgement(root)
        runtime["scope"] = _synthetic_runtime_scope("200")
        assert runtime["scope"]["pid1"]["namespace"] == "4026533000"
        with pytest.raises(HandoverError, match="runtime"):
            handover.trust_single_writer(
                root,
                expected_inventory_digest=review["inventory_digest"],
                operator_acknowledgement=review["operator_acknowledgement"],
            )
        with pytest.raises(FileNotFoundError):
            root.file_info(handover.SINGLE_WRITER_STATE_PATH)
        assert write_authority(root) == {
            "authority": "ownership-unknown",
            "reason": "attested-migration-read-only",
        }

        current_review = handover.prepare_single_writer_acknowledgement(root)
        trust = handover.trust_single_writer(
            root,
            expected_inventory_digest=current_review["inventory_digest"],
            operator_acknowledgement=current_review["operator_acknowledgement"],
        )
        assert trust["authority"] == "operator-trusted-single-writer"


def test_trusted_authority_fails_closed_when_runtime_identity_is_unavailable(tmp_path, monkeypatch):
    monkeypatch.setattr(handover, "out_of_band_exclusion_basis", lambda _root: None)
    runtime_scope = _synthetic_runtime_scope("100")
    monkeypatch.setattr(
        handover,
        "_runtime_scope_identity",
        lambda _root: runtime_scope,
        raising=False,
    )
    root_path = _legacy_source(tmp_path / "runtime-unavailable")
    with RootContext.open(root_path) as root:
        heads = build_head_inventory(root)
        migrate_existing(
            root,
            expected_inventory_digest=inventory_digest(heads),
            operator_attestation=OPERATOR_ATTESTATION,
        )
        review = handover.prepare_single_writer_acknowledgement(root)
        handover.trust_single_writer(
            root,
            expected_inventory_digest=review["inventory_digest"],
            operator_acknowledgement=review["operator_acknowledgement"],
        )

        def unavailable(_root):
            raise HandoverError("runtime identity unavailable")

        monkeypatch.setattr(handover, "_runtime_scope_identity", unavailable)
        before_denial = _filesystem_snapshot(root_path)
        assert write_authority(root) == {
            "authority": "ownership-unknown",
            "reason": "operator-single-writer-runtime-scope-unavailable",
        }
        with pytest.raises(WriteAuthorityDenied, match="runtime identity is unavailable"):
            require_write_authority(root)
        with pytest.raises(OwnershipUnknown):
            RootOwnerLease.acquire(root)
        assert _filesystem_snapshot(root_path) == before_denial


def test_inspection_issues_windows_runtime_challenge(tmp_path, monkeypatch):
    monkeypatch.setattr(handover, "out_of_band_exclusion_basis", lambda _root: None)
    monkeypatch.setattr(handover, "_runtime_scope_identity", _ORIGINAL_RUNTIME_SCOPE_IDENTITY)
    monkeypatch.setattr(handover, "sys", SimpleNamespace(platform="win32"))
    monkeypatch.setattr(handover, "_windows_current_user_sid", lambda: "S-1-5-21-100-200-300-1001")
    root_path = _legacy_source(tmp_path / "runtime-scope-unavailable")
    with RootContext.open(root_path) as root:
        heads = build_head_inventory(root)
        migrate_existing(
            root,
            expected_inventory_digest=inventory_digest(heads),
            operator_attestation=OPERATOR_ATTESTATION,
        )

        before = _filesystem_snapshot(root_path)
        assert handover.write_authority(root) == {
            "authority": "ownership-unknown",
            "reason": "attested-migration-read-only",
        }
        assert _filesystem_snapshot(root_path) == before

        review = handover.prepare_single_writer_acknowledgement(root)

        assert review["write_authority"] == "ownership-unknown"
        assert review["reason"] == "attested-migration-read-only"
        assert review["operator_acknowledgement"]
        assert review["runtime_scope"]["kind"] == "windows-user-volume"
        assert root.file_info(handover.SINGLE_WRITER_CHALLENGE_PATH).size > 0


def test_unexpected_runtime_scope_errors_are_not_silently_downgraded(tmp_path, monkeypatch):
    monkeypatch.setattr(handover, "out_of_band_exclusion_basis", lambda _root: None)
    root_path = _legacy_source(tmp_path / "runtime-scope-error")
    with RootContext.open(root_path) as root:
        heads = build_head_inventory(root)
        migrate_existing(
            root,
            expected_inventory_digest=inventory_digest(heads),
            operator_attestation=OPERATOR_ATTESTATION,
        )

        def unexpected_error(_root):
            raise AssertionError("synthetic runtime-scope implementation failure")

        monkeypatch.setattr(handover, "_runtime_scope_identity", unexpected_error)
        with pytest.raises(AssertionError, match="implementation failure"):
            write_authority(root)
        with pytest.raises(AssertionError, match="implementation failure"):
            handover.prepare_single_writer_acknowledgement(root)


def test_legacy_trust_record_without_runtime_scope_fails_closed(tmp_path, monkeypatch):
    monkeypatch.setattr(handover, "out_of_band_exclusion_basis", lambda _root: None)
    runtime_scope = _synthetic_runtime_scope("100")
    monkeypatch.setattr(
        handover,
        "_runtime_scope_identity",
        lambda _root: runtime_scope,
        raising=False,
    )
    root_path = _legacy_source(tmp_path / "legacy-trust-record")
    with RootContext.open(root_path) as root:
        heads = build_head_inventory(root)
        migrate_existing(
            root,
            expected_inventory_digest=inventory_digest(heads),
            operator_attestation=OPERATOR_ATTESTATION,
        )
        enrollment = require_enrollment(root)
        reviewed_digest = inventory_digest(build_head_inventory(root))
        challenge_id = "a" * 32
        root_digest = handover._digest(
            {
                "root": handover.root_binding(root),
                "protocol_version": handover.PROTOCOL_VERSION,
                "build_id": code_version(),
                "enrollment_identity": handover._enrollment_identity(enrollment),
            }
        )
        acknowledgement = f"I ACCEPT TRUSTED SINGLE-WRITER MODE ROOT={root_digest} " f"INVENTORY={reviewed_digest} CHALLENGE={challenge_id}; " "I ACCEPT RESPONSIBILITY FOR STOPPING AND EXCLUDING ALL OTHER PROGRAMS " "THAT CAN REACH THIS ROOT."
        handover._write_single_writer_state(
            root,
            {
                "schema": 1,
                "state": "trusted",
                "protocol_version": handover.PROTOCOL_VERSION,
                "build_id": code_version(),
                "root": handover.root_binding(root),
                "enrollment_identity": handover._enrollment_identity(enrollment),
                "reviewed_inventory_digest": reviewed_digest,
                "challenge_id": challenge_id,
                "operator_acknowledgement": acknowledgement,
                "acknowledged_at": datetime.now(timezone.utc).isoformat(),
            },
        )
        before_denial = _filesystem_snapshot(root_path)
        authority = write_authority(root)
        assert authority == {
            "authority": "ownership-unknown",
            "reason": "operator-single-writer-acknowledgement-invalid",
        }
        with pytest.raises(WriteAuthorityDenied):
            require_write_authority(root)
        assert _filesystem_snapshot(root_path) == before_denial

        review = handover.prepare_single_writer_acknowledgement(root)
        assert review["reason"] == "operator-single-writer-acknowledgement-invalid"
        renewed = handover.trust_single_writer(
            root,
            expected_inventory_digest=review["inventory_digest"],
            operator_acknowledgement=review["operator_acknowledgement"],
        )
        renewed_state = json.loads(root.read_bytes(handover.SINGLE_WRITER_STATE_PATH))
        assert renewed["authority"] == "operator-trusted-single-writer"
        assert renewed_state["schema"] == 2
        assert renewed_state["runtime_scope"] == runtime_scope


def test_trust_challenge_cannot_cross_roots_or_survive_inventory_drift(tmp_path, monkeypatch):
    monkeypatch.setattr(handover, "out_of_band_exclusion_basis", lambda _root: None)
    first_path = _legacy_source(tmp_path / "first")
    second_path = _legacy_source(tmp_path / "second")
    with RootContext.open(first_path) as first, RootContext.open(second_path) as second:
        for context in (first, second):
            heads = build_head_inventory(context)
            migrate_existing(
                context,
                expected_inventory_digest=inventory_digest(heads),
                operator_attestation=OPERATOR_ATTESTATION,
            )

        first_review = handover.prepare_single_writer_acknowledgement(first)
        second_review = handover.prepare_single_writer_acknowledgement(second)
        with pytest.raises(HandoverError, match="root|challenge|acknowledgement"):
            handover.trust_single_writer(
                second,
                expected_inventory_digest=second_review["inventory_digest"],
                operator_acknowledgement=first_review["operator_acknowledgement"],
            )

        (second_path / "paper" / "alpha" / "runner.pid").write_text("unknown", encoding="utf-8")
        with pytest.raises(HandoverError, match="legacy|runner|inventory|changed"):
            handover.trust_single_writer(
                second,
                expected_inventory_digest=second_review["inventory_digest"],
                operator_acknowledgement=second_review["operator_acknowledgement"],
            )
        assert write_authority(second) == {
            "authority": "ownership-unknown",
            "reason": "legacy-runner-present",
        }


def test_unverified_legacy_participant_blocks_trust_review_and_authority(tmp_path, monkeypatch):
    monkeypatch.setattr(handover, "out_of_band_exclusion_basis", lambda _root: None)
    root_path = _legacy_source(tmp_path / "unknown-legacy")
    with RootContext.open(root_path) as root:
        heads = build_head_inventory(root)
        migrate_existing(
            root,
            expected_inventory_digest=inventory_digest(heads),
            operator_attestation=OPERATOR_ATTESTATION,
        )
        monkeypatch.setattr(handover, "legacy_reachability_reason", lambda _root: "legacy-reachability-unverified")
        review = handover.prepare_single_writer_acknowledgement(root)
        assert review["operator_acknowledgement"] is None
        assert review["reason"] == "legacy-reachability-unverified"
        with pytest.raises(WriteAuthorityDenied, match="legacy-reachability-unverified"):
            handover.trust_single_writer(
                root,
                expected_inventory_digest=review["inventory_digest"],
                operator_acknowledgement="unverified",
            )
        assert write_authority(root) == {
            "authority": "ownership-unknown",
            "reason": "legacy-reachability-unverified",
        }
        with pytest.raises(FileNotFoundError):
            root.file_info(handover.SINGLE_WRITER_STATE_PATH)


def test_single_writer_review_expires_before_acknowledgement(tmp_path, monkeypatch):
    monkeypatch.setattr(handover, "out_of_band_exclusion_basis", lambda _root: None)
    root_path = _legacy_source(tmp_path / "expired-review")
    with RootContext.open(root_path) as root:
        heads = build_head_inventory(root)
        migrate_existing(
            root,
            expected_inventory_digest=inventory_digest(heads),
            operator_attestation=OPERATOR_ATTESTATION,
        )
        review = handover.prepare_single_writer_acknowledgement(root)

        base_datetime = handover.datetime

        class FutureDateTime(base_datetime):
            @classmethod
            def now(cls, tz=None):
                return base_datetime.now(tz) + timedelta(minutes=16)

        monkeypatch.setattr(handover, "datetime", FutureDateTime)
        with pytest.raises(HandoverError, match="review.*expired|review.*stale"):
            handover.trust_single_writer(
                root,
                expected_inventory_digest=review["inventory_digest"],
                operator_acknowledgement=review["operator_acknowledgement"],
            )
        assert write_authority(root) == {
            "authority": "ownership-unknown",
            "reason": "attested-migration-read-only",
        }


def test_relocation_copies_only_engine_data_and_never_writes_the_source(tmp_path):
    source_path = _legacy_source(tmp_path / "legacy")
    target_path = tmp_path / "native"
    target_path.mkdir()
    before = _tree(source_path)
    with RootContext.open(source_path) as source, RootContext.open(target_path) as target:
        described = inspect_relocation_source(source)
        assert _tree(source_path) == before
        assert described["funds"] == 1
        record = relocate_existing(target, source=source, expected_content_digest=described["content_digest"])
        assert record["mode"] == "relocated"
        assert record["attestation"] == {"source_inventory_digest": described["inventory_digest"], "source_content_digest": described["content_digest"]}
        assert record["heads"] == build_head_inventory(source)
        assert write_authority(target)["authority"] == "protocol-native"
        RootOwnerLease.acquire(target).close()
    assert _tree(source_path) == before
    assert not (source_path / "runtime").exists()
    assert (target_path / "mandates" / "alpha.yaml").read_text(encoding="utf-8") == "name: alpha\n"
    assert (target_path / "research" / "empty").is_dir()
    assert (target_path / "paper" / "alpha" / "fund.yaml").read_bytes() == (source_path / "paper" / "alpha" / "fund.yaml").read_bytes()
    assert not (target_path / ".env").exists()
    assert not (target_path / "cache").exists()
    assert not (target_path / "paper" / "alpha" / ".paper-audit.lock").exists()


def test_relocation_requires_the_reviewed_source_digest_before_touching_target(tmp_path):
    source_path = _legacy_source(tmp_path / "legacy")
    target_path = tmp_path / "native"
    target_path.mkdir()
    with RootContext.open(source_path) as source, RootContext.open(target_path) as target:
        with pytest.raises(HandoverError, match="source content changed"):
            relocate_existing(target, source=source, expected_content_digest="0" * 64)
    assert list(target_path.iterdir()) == []


def test_relocation_detects_source_change_during_copy_and_leaves_target_fail_closed(tmp_path, monkeypatch):
    source_path = _legacy_source(tmp_path / "legacy")
    target_path = tmp_path / "native"
    target_path.mkdir()
    original_write = RootContext.write_bytes

    def racing_write(self, relative, data, **kwargs):
        result = original_write(self, relative, data, **kwargs)
        if os.path.normcase(str(self.path)) == os.path.normcase(str(target_path)) and str(relative).startswith("mandates/"):
            (source_path / "research" / "alpha" / "note.json").write_text('{"legacy": "write"}', encoding="utf-8")
        return result

    with RootContext.open(source_path) as source, RootContext.open(target_path) as target:
        digest = inspect_relocation_source(source)["content_digest"]
        monkeypatch.setattr(RootContext, "write_bytes", racing_write)
        with pytest.raises(HandoverError, match="changed during relocation"):
            relocate_existing(target, source=source, expected_content_digest=digest)
        monkeypatch.undo()
        assert enrollment_status(target) == {"state": "invalid", "reason": "admission-state-without-handover"}
        assert write_authority(target)["authority"] == "unavailable"
        with pytest.raises(HandoverError):
            RootOwnerLease.acquire(target)
    assert not (target_path / HANDOVER_PATH).exists()


def test_relocation_detects_a_new_file_added_after_its_directory_was_copied(tmp_path, monkeypatch):
    source_path = _legacy_source(tmp_path / "legacy")
    target_path = tmp_path / "native"
    target_path.mkdir()
    original_write = RootContext.write_bytes

    def racing_write(self, relative, data, **kwargs):
        result = original_write(self, relative, data, **kwargs)
        if os.path.normcase(str(self.path)) == os.path.normcase(str(target_path)) and str(relative).startswith("mandates/"):
            (source_path / "mandates" / "late.yaml").write_text("name: late\n", encoding="utf-8")
        return result

    with RootContext.open(source_path) as source, RootContext.open(target_path) as target:
        digest = inspect_relocation_source(source)["content_digest"]
        monkeypatch.setattr(RootContext, "write_bytes", racing_write)
        with pytest.raises(HandoverError, match="changed during relocation"):
            relocate_existing(target, source=source, expected_content_digest=digest)
        monkeypatch.undo()
        assert write_authority(target)["authority"] == "unavailable"
    assert not (target_path / HANDOVER_PATH).exists()
    assert not (target_path / "mandates" / "late.yaml").exists()


@pytest.mark.parametrize("name", [".env", ".env.local", ".ENV"])
def test_relocation_refuses_nested_dotenv_files_before_reading_them(tmp_path, monkeypatch, name):
    source_path = _legacy_source(tmp_path / "legacy")
    secret = source_path / "research" / "alpha" / name
    secret.write_text("SYNTHETIC_ONLY=1\n", encoding="utf-8")
    original_read = RootContext.read_bytes
    read: list[str] = []

    def tracking_read(self, relative, *args, **kwargs):
        read.append(str(relative))
        return original_read(self, relative, *args, **kwargs)

    monkeypatch.setattr(RootContext, "read_bytes", tracking_read)
    target_path = tmp_path / "native"
    target_path.mkdir()
    with RootContext.open(source_path) as source, RootContext.open(target_path) as target:
        with pytest.raises(HandoverError, match=r"\.env"):
            inspect_relocation_source(source)
        with pytest.raises(HandoverError, match=r"\.env"):
            relocate_existing(target, source=source, expected_content_digest="0" * 64)
    assert not any(entry.rsplit("/", 1)[-1].casefold().startswith(".env") for entry in read)
    assert list(target_path.iterdir()) == []


@pytest.mark.parametrize(
    "mutate, message",
    [
        (lambda root: (root / "paper" / "alpha" / "runner.pid").write_text("123", encoding="utf-8"), "runner.pid"),
        (lambda root: (root / "research" / f".note.json.{os.getpid()}.{'a' * 32}.tmp").write_text("x", encoding="utf-8"), "interrupted write"),
    ],
)
def test_relocation_refuses_unknown_owners_and_interrupted_writes(tmp_path, mutate, message):
    source_path = _legacy_source(tmp_path / "legacy")
    mutate(source_path)
    target_path = tmp_path / "native"
    target_path.mkdir()
    with RootContext.open(source_path) as source, RootContext.open(target_path) as target:
        if message == "runner.pid":
            described = inspect_relocation_source(source)
            assert any(item["kind"] == "stale-marker-retirement" for item in described["blockers"])
            with pytest.raises(HandoverError, match="source blockers"):
                relocate_existing(target, source=source, expected_content_digest=described["content_digest"])
        else:
            with pytest.raises(HandoverError, match=message):
                inspect_relocation_source(source)
            with pytest.raises(HandoverError, match=message):
                relocate_existing(target, source=source, expected_content_digest="0" * 64)
    assert list(target_path.iterdir()) == []


def test_relocation_refuses_broker_backed_deployments(tmp_path):
    source_path = tmp_path / "legacy"
    (source_path / "paper").mkdir(parents=True)
    saxo = FundSpec.model_validate({**_spec().model_dump(mode="json"), "broker": "saxo", "rebalance": "minute", "interval": 30, "window": {"start": "09:30", "end": "15:59"}})
    from hedge_fund.brokers.test_saxo_doubles import write_fake_sim_deployment

    write_fake_sim_deployment("alpha", saxo, ["AAPL"], root=source_path / "paper")
    with RootContext.open(source_path) as source:
        with pytest.raises(HandoverError, match="broker-backed"):
            inspect_relocation_source(source)


def test_relocation_refuses_reparse_points_in_source(tmp_path):
    source_path = _legacy_source(tmp_path / "legacy")
    outside = tmp_path / "outside"
    outside.mkdir()
    _link_directory(source_path / "research" / "alias", outside)
    with RootContext.open(source_path) as source:
        with pytest.raises(HandoverError, match="reparse point"):
            inspect_relocation_source(source)


def test_relocation_target_must_be_empty_disjoint_and_legacy_unreachable(tmp_path, synthetic_home):
    source_path = _legacy_source(tmp_path / "legacy")
    with RootContext.open(source_path) as source:
        digest = inspect_relocation_source(source)["content_digest"]
        nonempty = tmp_path / "nonempty"
        nonempty.mkdir()
        (nonempty / "x").write_text("x", encoding="utf-8")
        with RootContext.open(nonempty) as target:
            with pytest.raises(HandoverError, match="empty target"):
                relocate_existing(target, source=source, expected_content_digest=digest)
        nested = source_path / "nested"
        nested.mkdir()
        with RootContext.open(nested) as target:
            with pytest.raises(HandoverError, match="overlap"):
                relocate_existing(target, source=source, expected_content_digest=digest)
        nested.rmdir()
        with RootContext.open(source_path) as same:
            with pytest.raises(HandoverError, match="differ"):
                relocate_existing(same, source=source, expected_content_digest=digest)
        legacy_layout = synthetic_home / ".hedge-fund"
        legacy_layout.mkdir()
        with RootContext.open(legacy_layout) as target:
            with pytest.raises(WriteAuthorityDenied, match="legacy-layout-path"):
                relocate_existing(target, source=source, expected_content_digest=digest)
        assert list(legacy_layout.iterdir()) == []


def test_fresh_enrollment_refuses_legacy_layout_and_alias_roots(tmp_path, synthetic_home):
    layout = synthetic_home / ".hedge-fund"
    layout.mkdir()
    with RootContext.open(layout) as context:
        with pytest.raises(WriteAuthorityDenied, match="legacy-layout-path"):
            enroll_fresh(context)
    assert list(layout.iterdir()) == []
    layout.rmdir()

    production = tmp_path / "production"
    production.mkdir()
    _link_directory(layout, production)
    with RootContext.open(production) as context:
        with pytest.raises(WriteAuthorityDenied, match="legacy-home-alias"):
            enroll_fresh(context)
    assert list(production.iterdir()) == []


def test_legacy_layout_component_match_is_case_insensitive(tmp_path):
    root = tmp_path / ".HEDGE-FUND" / "data"
    root.mkdir(parents=True)
    with RootContext.open(root) as context:
        with pytest.raises(WriteAuthorityDenied, match="legacy-layout-path"):
            enroll_fresh(context)
    assert list(root.iterdir()) == []


def test_unverifiable_legacy_reachability_fails_closed_for_every_writer_entry(tmp_path, synthetic_home, monkeypatch):
    root = tmp_path / "native"
    root.mkdir()
    (synthetic_home / ".hedge-fund").mkdir()
    with RootContext.open(root) as context:
        enroll_fresh(context)

        def unreadable(candidate, root_real):
            raise PermissionError("synthetic")

        monkeypatch.setattr(handover, "_legacy_tree_reaches", unreadable)
        assert write_authority(context) == {"authority": "ownership-unknown", "reason": "legacy-reachability-unverified"}
        with pytest.raises(WriteAuthorityDenied, match="legacy-reachability-unverified"):
            require_write_authority(context)
        with pytest.raises(OwnershipUnknown, match="legacy-reachability-unverified"):
            RootOwnerLease.acquire(context)

        def broken(root):
            raise RuntimeError("synthetic")

        monkeypatch.setattr(handover, "legacy_reachability_reason", broken)
        assert write_authority(context) == {"authority": "ownership-unknown", "reason": "legacy-reachability-unverified"}
        with pytest.raises(OwnershipUnknown, match="unverified"):
            RootOwnerLease.acquire(context)


@pytest.mark.parametrize("case", ["alias", "ancestor-alias", "subfolder-alias", "fund-alias", "nested", "runner-pid"])
def test_protocol_native_root_loses_authority_when_legacy_writers_can_reach_it(tmp_path, synthetic_home, case):
    root = tmp_path / "native"
    root.mkdir()
    with RootContext.open(root) as context:
        enroll_fresh(context)
        lease = RootOwnerLease.acquire(context)
        try:
            assert lease.matches(context)
            if case == "alias":
                _link_directory(synthetic_home / ".hedge-fund", root)
                expected = "legacy-home-alias"
            elif case == "ancestor-alias":
                _link_directory(synthetic_home / ".hedge-fund", tmp_path)
                expected = "legacy-home-alias"
            elif case == "subfolder-alias":
                (root / "paper").mkdir()
                (synthetic_home / ".hedge-fund").mkdir()
                _link_directory(synthetic_home / ".hedge-fund" / "paper", root / "paper")
                expected = "legacy-home-alias"
            elif case == "fund-alias":
                (root / "paper" / "alpha").mkdir(parents=True)
                (synthetic_home / ".hedge-fund" / "paper").mkdir(parents=True)
                _link_directory(synthetic_home / ".hedge-fund" / "paper" / "alpha", root / "paper" / "alpha")
                expected = "legacy-home-alias"
            elif case == "nested":
                (root / ".hedge-fund").mkdir()
                expected = "legacy-layout-nested"
            else:
                (root / "paper" / "alpha").mkdir(parents=True)
                (root / "paper" / "alpha" / "runner.pid").write_text("1", encoding="utf-8")
                expected = "legacy-runner-present"
            assert write_authority(context) == {"authority": "ownership-unknown", "reason": expected}
            assert not lease.matches(context)
        finally:
            lease.close()
        with pytest.raises(OwnershipUnknown, match=expected):
            RootOwnerLease.acquire(context)
        assert require_enrollment(context)["mode"] == "fresh"


def test_writer_already_holding_lanes_is_denied_at_write_time_after_authority_flips(tmp_path):
    from hedge_fund.runtime.admission import AdmissionCoordinator, require_paper_write_lanes, root_registry_writer

    root = tmp_path / "native"
    root.mkdir()
    with RootContext.open(root) as context:
        enroll_fresh(context)
        owner = RootOwnerLease.acquire(context)
        admission = AdmissionCoordinator(context, owner_lease=owner)
        try:
            with admission.control_lane("alpha", timeout=0), admission.registry_lock(timeout=0):
                assert require_paper_write_lanes(root / "paper" / "alpha", "alpha", lane_sets=(("control",),))
                with root_registry_writer(context, admission):
                    pass
                (root / "paper" / "alpha").mkdir(parents=True)
                (root / "paper" / "alpha" / "runner.pid").write_text("1", encoding="utf-8")
                with pytest.raises(OwnershipUnknown, match="legacy-runner-present"):
                    require_paper_write_lanes(root / "paper" / "alpha", "alpha", lane_sets=(("control",),))
                with pytest.raises(OwnershipUnknown, match="legacy-runner-present"):
                    with root_registry_writer(context, admission):
                        pytest.fail("registry write admitted after authority loss")
        finally:
            owner.close()


def test_relocated_record_provenance_is_validated(tmp_path):
    source_path = _legacy_source(tmp_path / "legacy")
    target_path = tmp_path / "native"
    target_path.mkdir()
    with RootContext.open(source_path) as source, RootContext.open(target_path) as target:
        digest = inspect_relocation_source(source)["content_digest"]
        relocate_existing(target, source=source, expected_content_digest=digest)
        record = json.loads(target.read_bytes(HANDOVER_PATH))
        record["attestation"] = None
        body = {key: value for key, value in record.items() if key != "record_digest"}
        record["record_digest"] = handover._digest(body)
        target.write_bytes(HANDOVER_PATH, json.dumps(record).encode())
        with pytest.raises(handover.EnrollmentInvalid, match="relocation provenance"):
            require_enrollment(target)
        assert write_authority(target)["authority"] == "unavailable"
