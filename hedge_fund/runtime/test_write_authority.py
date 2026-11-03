"""Write-authority classification and relocation import (T015 boundary).

Attested migrations and legacy-addressable roots are ownership-unknown and
read-only; only fresh or relocated, legacy-unreachable roots may hold writes.
Every test uses isolated synthetic roots and a synthetic HOME.
"""

import hashlib
import json
import os
from pathlib import Path

import pytest

from hedge_fund.fund import FundSpec
from hedge_fund.paper.deployed import deploy
from hedge_fund.runtime import handover
from hedge_fund.runtime.admission import OwnershipUnknown, RootOwnerLease
from hedge_fund.runtime.handover import (
    build_head_inventory,
    enroll_fresh,
    enrollment_status,
    HANDOVER_PATH,
    HandoverError,
    inspect_relocation_source,
    inventory_digest,
    migrate_existing,
    OPERATOR_ATTESTATION,
    relocate_existing,
    require_enrollment,
    require_write_authority,
    write_authority,
    WriteAuthorityDenied,
)
from hedge_fund.runtime.root import RootContext


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
    from hedge_fund.runtime.admission import (
        AdmissionCoordinator,
        require_paper_write_lanes,
        root_registry_writer,
    )

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
