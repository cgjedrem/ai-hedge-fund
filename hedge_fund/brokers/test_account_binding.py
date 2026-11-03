"""Fake-only SIM account/environment binding policy tests (Spec 005 T096).

Every case uses synthetic roots and a synthetic registry under ``tmp_path``.
No broker, secret provider, network or real brokerage account is used.
"""

from __future__ import annotations

import hashlib
import json
import logging
import socket
import threading
from datetime import datetime, timedelta, timezone

import pytest

from hedge_fund.brokers import account_binding as ab
from hedge_fund.brokers.account_binding import (
    AccountAlreadyBound,
    AccountOwnershipUnknown,
    AccountRegistry,
    CustodyAssessment,
    DeploymentAlreadyBound,
    NotOwner,
    RealBrokerageDenied,
    ReleaseRequired,
    runner_quiescence,
    RunnerNotQuiescent,
    RunnerQuiescence,
    SimAccountIdentity,
    StaleRelease,
)
from hedge_fund.runtime.root import RootContext
from hedge_fund.test_support.handover import enroll_synthetic_root

SECRET_ACCOUNT = "SIM-ACCT-7f3c9e1d"
OTHER_ACCOUNT = "SIM-ACCT-0a1b2c3d"


class FakeVerifiedCustody:
    """Test-only stand-in for exclusivity evidence that production cannot yet produce."""

    def __init__(self) -> None:
        self.calls = 0

    def assess(self, registry, root):
        self.calls += 1
        return CustodyAssessment(True, "fake-verified")


def stopped(_root, _deployment):
    return RunnerQuiescence(True, "stopped")


def running(_root, _deployment):
    return RunnerQuiescence(False, "running")


@pytest.fixture
def account():
    return SimAccountIdentity("sim", SECRET_ACCOUNT)


@pytest.fixture
def custody():
    return FakeVerifiedCustody()


@pytest.fixture
def registry(tmp_path):
    location = tmp_path / "per-user-registry"
    location.mkdir()
    with AccountRegistry.initialize(location) as opened:
        yield opened


@pytest.fixture
def roots(tmp_path):
    opened = []
    for name in ("root-a", "root-b", "root-c"):
        path = tmp_path / name
        path.mkdir()
        enroll_synthetic_root(path)
        opened.append(RootContext.open(path))
    yield opened
    for root in opened:
        root.close()


def _state(registry):
    return json.loads(registry._context.read_bytes(ab.STATE_PATH))


def test_fake_sim_binding_is_exclusive(registry, roots, account, custody):
    root_a, root_b, _ = roots
    receipt = registry.bind(root_a, "demo-alpha", account, custody=custody)
    assert receipt["status"] == "active" and receipt["execution_authorized"] is False
    assert registry.bind(root_a, "demo-alpha", account, custody=custody) == receipt

    with pytest.raises(AccountAlreadyBound):
        registry.bind(root_a, "demo-beta", account, custody=custody)
    with pytest.raises(AccountAlreadyBound):
        registry.bind(root_b, "demo-alpha", account, custody=custody)
    with pytest.raises(DeploymentAlreadyBound):
        registry.bind(root_a, "DEMO-ALPHA", SimAccountIdentity("sim", OTHER_ACCOUNT), custody=custody)

    state = _state(registry)
    assert state["generation"] == 1
    assert [record["status"] for record in state["bindings"].values()] == ["active"]


def test_duplicate_across_roots_is_denied_through_shared_registry_handles(registry, roots, account, custody):
    root_a, root_b, _ = roots
    registry.bind(root_a, "demo-alpha", account, custody=custody)
    with AccountRegistry.open(registry.path) as second_handle:
        with pytest.raises(AccountAlreadyBound):
            second_handle.bind(root_b, "demo-gamma", account, custody=custody)
        assert second_handle.inspect(account)["status"] == "active"


def test_production_custody_denies_binding_and_transfer_as_ownership_unknown(registry, roots, account, custody):
    root_a, root_b, _ = roots
    with pytest.raises(AccountOwnershipUnknown, match="global-custody-unverifiable"):
        registry.bind(root_a, "demo-alpha", account)
    assert _state(registry)["generation"] == 0
    assert registry.inspect(account)["status"] == "unbound"

    registry.bind(root_a, "demo-alpha", account, custody=custody)
    released = registry.release(root_a, "demo-alpha", account, quiescence=stopped)
    with pytest.raises(AccountOwnershipUnknown, match="global-custody-unverifiable"):
        registry.bind(root_b, "demo-beta", account, release_digest=released["release_digest"])
    assert registry.inspect(account)["status"] == "released"


def test_invalid_custody_assessment_fails_closed(registry, roots, account):
    class Ambiguous:
        def assess(self, registry, root):
            return {"verified": True}

    with pytest.raises(AccountOwnershipUnknown):
        registry.bind(roots[0], "demo-alpha", account, custody=Ambiguous())
    assert _state(registry)["bindings"] == {}


def test_missing_registry_is_ownership_unknown(tmp_path):
    location = tmp_path / "never-initialized"
    with pytest.raises(AccountOwnershipUnknown):
        AccountRegistry.open(location)
    location.mkdir()
    with pytest.raises(AccountOwnershipUnknown):
        AccountRegistry.open(location)


@pytest.mark.parametrize("damage", ["truncate", "garbage", "non-canonical", "bad-record", "missing-state", "missing-key", "short-key"])
def test_unreadable_or_corrupt_registry_denies_and_inspects_unknown(registry, roots, account, custody, damage):
    registry.bind(roots[0], "demo-alpha", account, custody=custody)
    context = registry._context
    state_path = context.resolve(ab.STATE_PATH)
    key_path = context.resolve(ab.KEY_PATH)
    if damage == "truncate":
        state_path.write_bytes(state_path.read_bytes()[:20])
    elif damage == "garbage":
        state_path.write_bytes(b"\xff\xfe not json")
    elif damage == "non-canonical":
        state_path.write_text(json.dumps(_state(registry), indent=2), encoding="utf-8")
    elif damage == "bad-record":
        state = _state(registry)
        next(iter(state["bindings"].values()))["execution_authorized"] = True
        state_path.write_bytes(ab._canonical(state))
    elif damage == "missing-state":
        state_path.unlink()
    elif damage == "missing-key":
        key_path.unlink()
    else:
        key_path.write_bytes(b"short")

    with pytest.raises(AccountOwnershipUnknown):
        registry.bind(roots[1], "demo-beta", SimAccountIdentity("sim", OTHER_ACCOUNT), custody=custody)
    with pytest.raises(AccountOwnershipUnknown):
        registry.release(roots[0], "demo-alpha", account, quiescence=stopped)
    assert registry.inspect(account) == {"status": "ownership-unknown", "environment": None, "deployment": None, "execution_authorized": False}
    with pytest.raises(AccountOwnershipUnknown):
        AccountRegistry.open(registry.path)


def test_unverified_private_registry_storage_denies(registry, roots, account, custody, monkeypatch):
    monkeypatch.setattr(registry._context, "verify_private_storage", lambda: False)
    with pytest.raises(AccountOwnershipUnknown, match="private storage"):
        registry.bind(roots[0], "demo-alpha", account, custody=custody)
    assert registry.inspect(account)["status"] == "ownership-unknown"


def test_registry_initialization_requires_empty_directory(tmp_path):
    location = tmp_path / "occupied"
    location.mkdir()
    (location / "stray.txt").write_text("x", encoding="utf-8")
    with pytest.raises(AccountOwnershipUnknown):
        AccountRegistry.initialize(location)


def test_root_local_registry_is_rejected(tmp_path, roots, account, custody):
    nested = roots[0].path / "account-registry"
    nested.mkdir()
    with AccountRegistry.initialize(nested) as local:
        with pytest.raises(AccountOwnershipUnknown, match="root-local"):
            local.bind(roots[0], "demo-alpha", account, custody=custody)
    assert custody.calls == 0


def test_non_protocol_native_root_is_ownership_unknown(registry, tmp_path, account, custody):
    unenrolled = tmp_path / "unenrolled"
    unenrolled.mkdir()
    with RootContext.open(unenrolled) as root:
        with pytest.raises(AccountOwnershipUnknown, match="protocol-native"):
            registry.bind(root, "demo-alpha", account, custody=custody)
    assert custody.calls == 0 and _state(registry)["bindings"] == {}


def test_owned_stopped_release_and_transfer_records_provenance(registry, roots, account, custody):
    root_a, root_b, root_c = roots
    registry.bind(root_a, "demo-alpha", account, custody=custody)
    with pytest.raises(NotOwner):
        registry.release(root_b, "demo-alpha", account, quiescence=stopped)
    with pytest.raises(NotOwner):
        registry.release(root_a, "demo-beta", account, quiescence=stopped)

    released = registry.release(root_a, "demo-alpha", account, quiescence=stopped)
    assert released["status"] == "released" and len(released["release_digest"]) == 64
    assert registry.inspect(account) == {"status": "released", "environment": "sim", "deployment": None, "execution_authorized": False}

    with pytest.raises(ReleaseRequired):
        registry.bind(root_b, "demo-beta", account, custody=custody)
    with pytest.raises(StaleRelease):
        registry.bind(root_b, "demo-beta", account, release_digest="0" * 64, custody=custody)

    moved = registry.bind(root_b, "demo-beta", account, release_digest=released["release_digest"], custody=custody)
    assert moved["status"] == "active" and moved["transfers"] == 1 and moved["execution_authorized"] is False
    record = next(iter(_state(registry)["bindings"].values()))
    (hop,) = record["provenance"]
    assert hop["release_digest"] == released["release_digest"]
    assert hop["from_deployment_key"] == hashlib.sha256(b"demo-alpha").hexdigest()
    assert hop["from_owner"] != record["owner"]

    with pytest.raises(AccountAlreadyBound):
        registry.bind(root_c, "demo-gamma", account, release_digest=released["release_digest"], custody=custody)
    with pytest.raises(NotOwner):
        registry.release(root_a, "demo-alpha", account, quiescence=stopped)


def test_unsolicited_release_digest_on_unbound_account_is_stale(registry, roots, account, custody):
    with pytest.raises(StaleRelease):
        registry.bind(roots[0], "demo-alpha", account, release_digest="a" * 64, custody=custody)
    with pytest.raises(StaleRelease):
        registry.bind(roots[0], "demo-alpha", account, release_digest="not-a-digest", custody=custody)


@pytest.mark.parametrize("observation", [running, lambda root, name: RunnerQuiescence(False, "unknown"), lambda root, name: {"quiescent": True}, lambda root, name: RunnerQuiescence(1, "stopped")])
def test_active_or_unknown_runner_denies_release(registry, roots, account, custody, observation):
    registry.bind(roots[0], "demo-alpha", account, custody=custody)
    with pytest.raises(RunnerNotQuiescent):
        registry.release(roots[0], "demo-alpha", account, quiescence=observation)
    assert registry.inspect(account)["status"] == "active"
    assert _state(registry)["generation"] == 1


@pytest.mark.parametrize("lane", ["manual_session", "runner_reservation", "execution_lease", "deployment_lock"])
def test_held_deployment_lane_denies_release_even_without_runner_record(registry, roots, account, custody, lane):
    from hedge_fund.runtime.admission import AdmissionCoordinator, RootOwnerLease

    root = roots[0]
    registry.bind(root, "demo-alpha", account, custody=custody)
    assert runner_quiescence(root, "demo-alpha") == RunnerQuiescence(True, "never-started")
    with RootOwnerLease.acquire(root) as owner:
        coordinator = AdmissionCoordinator(root, owner_lease=owner)
        with getattr(coordinator, lane)("demo-alpha"):
            with pytest.raises(RunnerNotQuiescent):
                registry.release(root, "demo-alpha", account, quiescence=stopped)
    assert registry.inspect(account)["status"] == "active"
    assert registry.release(root, "demo-alpha", account, quiescence=stopped)["status"] == "released"


def test_bind_is_denied_while_deployment_lane_is_held(registry, roots, account, custody):
    from hedge_fund.runtime.admission import AdmissionCoordinator, RootOwnerLease

    root = roots[0]
    with RootOwnerLease.acquire(root) as owner:
        with AdmissionCoordinator(root, owner_lease=owner).deployment_lock("demo-alpha"):
            with pytest.raises(ab.RegistryBusy):
                registry.bind(root, "demo-alpha", account, custody=custody)
    assert _state(registry)["bindings"] == {}


def test_registry_on_another_drive_is_outside_root(registry, roots, monkeypatch):
    def different_drives(paths):
        raise ValueError("Paths don't have the same drive")

    monkeypatch.setattr(ab.os.path, "commonpath", different_drives)
    monkeypatch.setattr(ab.os.path, "splitdrive", lambda path: ("d:" if "per-user-registry" in path else "c:", path))
    # Different prefixes on the same volume (subst/UNC alias) must fail closed.
    assert registry._context.device_identity == roots[0].device_identity
    with pytest.raises(AccountOwnershipUnknown, match="not comparable"):
        registry._require_outside_root(roots[0])
    monkeypatch.setattr(registry._context, "device_identity", "other-volume")
    registry._require_outside_root(roots[0])
    monkeypatch.setattr(ab.os.path, "splitdrive", lambda path: ("c:", path))
    with pytest.raises(AccountOwnershipUnknown, match="not comparable"):
        registry._require_outside_root(roots[0])


def test_production_runner_quiescence_reads_owned_runner_records(roots):
    from hedge_fund.pipeline.session import code_version
    from hedge_fund.runtime.admission import PROTOCOL_VERSION
    from hedge_fund.runtime.handover import root_binding
    from hedge_fund.runtime.owned_runner import runner_paths

    root = roots[0]
    assert runner_quiescence(root, "demo-alpha") == RunnerQuiescence(True, "never-started")
    _launch, state_path, _control = runner_paths("demo-alpha")
    root.mkdir(state_path.rsplit("/", 1)[0], parents=True, mode=0o700)
    root.write_bytes(state_path, b"{not json", mode=0o600)
    assert runner_quiescence(root, "demo-alpha") == RunnerQuiescence(False, "unknown")

    created = datetime.now(timezone.utc).replace(microsecond=0)
    base = {
        "schema": 1,
        "protocol_version": PROTOCOL_VERSION,
        "build_id": code_version(),
        "root": root_binding(root),
        "fund": "demo-alpha",
        "nonce_hash": "b" * 64,
        "created_at": created.isoformat(),
        "expires_at": (created + timedelta(hours=1)).isoformat(),
        "max_sessions": 1,
        "sessions_completed": 0,
        "last_session": None,
        "reason": None,
        "pid": 4242,
        "process_identity": {"pid": 4242, "creation_time": "1", "image": "python", "host": "synthetic", "namespace": "synthetic"},
    }
    for status, expected in (("running", RunnerQuiescence(False, "running")), ("stopping", RunnerQuiescence(False, "stopping")), ("stopped", RunnerQuiescence(True, "stopped"))):
        root.write_bytes(state_path, json.dumps({**base, "status": status}).encode("utf-8"), mode=0o600)
        assert runner_quiescence(root, "demo-alpha") == expected


def test_concurrent_transfers_of_one_release_digest_admit_exactly_one(registry, roots, account, custody):
    root_a, root_b, root_c = roots
    registry.bind(root_a, "demo-alpha", account, custody=custody)
    digest = registry.release(root_a, "demo-alpha", account, quiescence=stopped)["release_digest"]
    barrier = threading.Barrier(2)
    outcomes: dict[str, object] = {}

    def transfer(label, path, deployment):
        with RootContext.open(path) as root, AccountRegistry.open(registry.path) as handle:
            barrier.wait()
            try:
                outcomes[label] = handle.bind(root, deployment, account, release_digest=digest, custody=FakeVerifiedCustody())
            except Exception as exc:  # noqa: BLE001 - outcome is asserted below
                outcomes[label] = exc

    threads = [threading.Thread(target=transfer, args=("b", root_b.path, "demo-beta")), threading.Thread(target=transfer, args=("c", root_c.path, "demo-gamma"))]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    assert not any(thread.is_alive() for thread in threads)

    winners = [value for value in outcomes.values() if isinstance(value, dict)]
    losers = [value for value in outcomes.values() if not isinstance(value, dict)]
    assert len(winners) == 1 and len(losers) == 1
    assert isinstance(losers[0], (AccountAlreadyBound, StaleRelease))
    record = next(iter(_state(registry)["bindings"].values()))
    assert record["status"] == "active" and [hop["release_digest"] for hop in record["provenance"]] == [digest]
    assert _state(registry)["generation"] == 3


def test_stale_digest_after_rebind_and_second_release_is_rejected(registry, roots, account, custody):
    root_a, root_b, _ = roots
    registry.bind(root_a, "demo-alpha", account, custody=custody)
    first = registry.release(root_a, "demo-alpha", account, quiescence=stopped)["release_digest"]
    registry.bind(root_b, "demo-beta", account, release_digest=first, custody=custody)
    second = registry.release(root_b, "demo-beta", account, quiescence=stopped)["release_digest"]
    assert second != first
    with pytest.raises(StaleRelease):
        registry.bind(root_a, "demo-alpha", account, release_digest=first, custody=custody)
    registry.bind(root_a, "demo-alpha", account, release_digest=second, custody=custody)
    record = next(iter(_state(registry)["bindings"].values()))
    assert [hop["release_digest"] for hop in record["provenance"]] == [first, second]


def test_registry_lock_contention_is_busy_without_effects(registry, roots, account, custody):
    from hedge_fund.runtime.admission import _acquire_os_lock, _release_os_lock

    handle = registry._context.open_lock_file(ab.LOCK_PATH)
    token = _acquire_os_lock(handle, 0.0, exclusive=True)
    try:
        with pytest.raises(ab.RegistryBusy):
            registry.bind(roots[0], "demo-alpha", account, custody=custody, lock_timeout=0.05)
    finally:
        _release_os_lock(handle, token)
        handle.close()
    assert _state(registry)["bindings"] == {}


@pytest.mark.parametrize("environment", ["live", "LIVE", "Sim", "production", "", "sim "])
def test_real_or_unknown_brokerage_environment_is_denied_before_effects(registry, roots, custody, environment):
    with pytest.raises(RealBrokerageDenied):
        registry.bind(roots[0], "demo-alpha", SimAccountIdentity(environment, SECRET_ACCOUNT), custody=custody)
    assert custody.calls == 0
    assert _state(registry)["bindings"] == {}


def test_configuration_never_builds_broker_resolves_secrets_or_connects(registry, roots, account, custody, monkeypatch):
    from hedge_fund.brokers import factory, saxo
    from hedge_fund.secrets import provider

    def forbidden(*_args, **_kwargs):
        raise AssertionError("account binding must not touch brokers, secrets or network")

    monkeypatch.setattr(factory, "build_broker", forbidden)
    monkeypatch.setattr(saxo.SaxoClient, "__init__", forbidden)
    monkeypatch.setattr(saxo.TokenManager, "__init__", forbidden)
    monkeypatch.setattr(provider.SecretProvider, "resolve", forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)

    root_a, root_b, _ = roots
    assert registry.bind(root_a, "demo-alpha", account, custody=custody)["execution_authorized"] is False
    digest = registry.release(root_a, "demo-alpha", account, quiescence=stopped)["release_digest"]
    assert registry.bind(root_b, "demo-beta", account, release_digest=digest, custody=custody)["execution_authorized"] is False
    assert registry.inspect(account)["execution_authorized"] is False
    assert all(record["execution_authorized"] is False and record["environment"] == "sim" for record in _state(registry)["bindings"].values())


def test_account_identity_never_persisted_reported_or_logged(registry, roots, account, custody, caplog):
    caplog.set_level(logging.DEBUG)
    root_a, root_b, _ = roots
    messages = []
    receipt = registry.bind(root_a, "demo-alpha", account, custody=custody)
    for call in (
        lambda: registry.bind(root_b, "demo-beta", account, custody=custody),
        lambda: registry.release(root_a, "demo-alpha", account, quiescence=running),
        lambda: registry.bind(root_b, "demo-beta", SimAccountIdentity("live", SECRET_ACCOUNT), custody=custody),
        lambda: registry.bind(root_b, "demo-beta", SimAccountIdentity("sim", SECRET_ACCOUNT + "/../x"), custody=custody),
    ):
        with pytest.raises(ab.AccountBindingError) as excinfo:
            call()
        messages.append(str(excinfo.value))

    stored = b"".join(path.read_bytes() for path in registry._context.resolve(ab.REGISTRY_DIRECTORY).iterdir() if path.is_file())
    surfaces = [repr(account), json.dumps(receipt), json.dumps(registry.inspect(account)), caplog.text, *messages]
    assert SECRET_ACCOUNT not in "\n".join(surfaces)
    assert SECRET_ACCOUNT.encode() not in stored
    assert SECRET_ACCOUNT.lower().encode() not in stored.lower()


def test_default_registry_location_is_per_user_and_outside_legacy_home(tmp_path):
    import os

    if os.name == "nt":
        location = ab.default_registry_location({"LOCALAPPDATA": str(tmp_path / "local")})
    else:
        location = ab.default_registry_location({"HOME": str(tmp_path / "home")})
    assert location.is_absolute() and location.parts[-3:] == ("hedge-fund", "sim-account-registry", "v1")
    assert ".hedge-fund" not in location.parts
    with pytest.raises(AccountOwnershipUnknown):
        ab.default_registry_location({"LOCALAPPDATA": "relative", "XDG_STATE_HOME": "relative", "HOME": ""})


def test_provisioning_module_is_not_wired_to_execution_or_web():
    import pathlib

    package = pathlib.Path(ab.__file__).resolve().parents[1]
    for relative in ("brokers/factory.py", "paper/deployed.py", "web/app.py", "web/services.py", "run.py"):
        assert "account_binding" not in (package / relative).read_text(encoding="utf-8")
