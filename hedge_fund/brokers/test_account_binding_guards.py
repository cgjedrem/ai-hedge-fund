"""Fake-only regressions for the unsupported production SIM ownership boundary.

These assert unconditional denial under input/admission setups, not account
duplicate, quiescence or replay policy. That policy has separate simulation tests.
"""

import json
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from types import SimpleNamespace

import pytest

from hedge_fund.brokers.factory import build_broker
from hedge_fund.brokers.saxo_auth import interactive_login
from hedge_fund.fund import FundSpec
from hedge_fund.paper.deployed import deploy
from hedge_fund.runtime.admission import (
    AdmissionCoordinator,
    OwnershipUnknown,
    RootOwnerLease,
)
from hedge_fund.runtime.root import RootContext
from hedge_fund.test_support.handover import enroll_synthetic_root


@pytest.fixture
def native_roots(tmp_path):
    with ExitStack() as stack:
        roots = []
        for name in ("root-one", "root-two"):
            path = tmp_path / name
            path.mkdir()
            enroll_synthetic_root(path)
            roots.append(stack.enter_context(RootContext.open(path)))
        yield roots


def _tree_bytes(path):
    snapshot = {}
    for entry in path.rglob("*"):
        if entry.is_file():
            if entry.suffix == ".lock":
                # Windows byte-range locks prohibit reading even an empty lock.
                info = entry.stat()
                value = (info.st_size, info.st_mtime_ns, info.st_ino)
            else:
                value = entry.read_bytes()
            snapshot[str(entry.relative_to(path))] = value
    return snapshot


def test_factory_denies_unknown_account_control_before_environment_or_provider_access(tmp_path):
    class UnreadableEnvironment(dict):
        def get(self, *_args, **_kwargs):
            pytest.fail("unknown SIM ownership read credential configuration")

    class ForbiddenProvider:
        def resolve(self, *_args, **_kwargs):
            pytest.fail("unknown SIM ownership reached a secret provider")

    class ForbiddenTransport:
        def request(self, *_args, **_kwargs):
            pytest.fail("unknown SIM ownership reached the broker")

    deployed = SimpleNamespace(broker="saxo", spec=SimpleNamespace(broker="saxo"))
    with pytest.raises(OwnershipUnknown, match="ownership-unknown"):
        build_broker(
            deployed,
            directory=tmp_path / "not-created",
            environ=UnreadableEnvironment(),
            secrets_provider=ForbiddenProvider(),
            transport=ForbiddenTransport(),
        )
    assert list(tmp_path.iterdir()) == []


def test_headless_oauth_entry_denies_before_reading_ambient_credentials(monkeypatch):
    from hedge_fund.brokers import saxo_auth

    class UnreadableEnvironment(dict):
        def get(self, name, *args, **kwargs):
            if name.startswith("SAXO_"):
                pytest.fail("unknown SIM ownership read ambient OAuth credentials")
            return super().get(name, *args, **kwargs)

    monkeypatch.setattr(saxo_auth.os, "environ", UnreadableEnvironment(saxo_auth.os.environ))
    with pytest.raises(OwnershipUnknown, match="ownership-unknown"):
        saxo_auth.main()


def test_oauth_provisioning_denies_before_browser_prompt_token_or_lock_effects(tmp_path):
    def forbidden(*_args, **_kwargs):
        pytest.fail("unknown SIM ownership reached OAuth provisioning")

    with pytest.raises(OwnershipUnknown, match="ownership-unknown"):
        interactive_login(
            "fake-app-key",
            "fake-app-secret",
            "http://localhost/callback",
            "op://fake/item/refresh",
            SimpleNamespace(write_back=forbidden),
            browser_open=forbidden,
            prompt=forbidden,
            transport=SimpleNamespace(request=forbidden),
            lock_dir=tmp_path / "not-created",
        )
    assert list(tmp_path.iterdir()) == []


def test_sim_deployment_denies_before_creating_snapshot_ledger_or_registry(tmp_path):
    spec = FundSpec(
        schema_version=2,
        name="fake-sim",
        broker="saxo",
        rebalance="minute",
        strategies=[{"name": "event", "models": [{"name": "pead"}], "blend": {"mode": "long_short"}}],
        risk={"max_position_pct": 0.25, "max_gross_exposure": 1.0},
    )
    with pytest.raises(OwnershipUnknown, match="ownership-unknown"):
        deploy("fake-sim", spec, ["AAPL"], root=tmp_path / "not-created")
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("across_roots", [False, True])
def test_production_boundary_denies_repeated_account_setups_within_or_across_roots(native_roots, across_roots):
    from hedge_fund.brokers.account_binding import SIMAccountRegistry

    source, other = native_roots
    target = other if across_roots else source
    before = [_tree_bytes(root.path) for root in native_roots]
    for root, deployment in ((source, "alpha"), (target, "beta")):
        with pytest.raises(OwnershipUnknown, match="ownership-unknown"):
            SIMAccountRegistry(root).bind("sim", "fake-account-sentinel", deployment)
    assert [_tree_bytes(root.path) for root in native_roots] == before


def test_registry_inspection_is_redacted_read_only_and_never_execution_authority(native_roots):
    from hedge_fund.brokers.account_binding import SIMAccountRegistry

    root = native_roots[0]
    before = _tree_bytes(root.path)
    assert SIMAccountRegistry(root).inspect() == {
        "state": "ownership-unknown",
        "reason": "exclusive-account-control-unverifiable",
        "cross_root_inventory": "unverifiable",
        "binding_supported": False,
        "provisioning_supported": False,
        "execution_authorized": False,
    }
    assert _tree_bytes(root.path) == before


@pytest.mark.parametrize("active_runner", [False, True])
def test_production_release_denies_with_owned_sorted_lanes_regardless_of_runner_reservation(native_roots, active_runner):
    from hedge_fund.brokers.account_binding import SIMAccountRegistry

    root = native_roots[0]
    with RootOwnerLease.acquire(root) as owner:
        admission = AdmissionCoordinator(root, owner_lease=owner)
        with admission.multi_deployment(["beta", "alpha"]) as ordered, ExitStack() as stack:
            assert ordered == ("alpha", "beta")
            if active_runner:
                stack.enter_context(admission.runner_reservation("alpha"))
            before = _tree_bytes(root.path)
            with pytest.raises(OwnershipUnknown, match="ownership-unknown"):
                SIMAccountRegistry(root).release("alpha", expected_binding_digest="a" * 64, request_id="fake-release")
            assert _tree_bytes(root.path) == before


def test_production_transfer_unconditionally_denies_concurrent_and_replayed_calls(native_roots):
    from hedge_fund.brokers.account_binding import SIMAccountRegistry

    source, target = native_roots
    registry = SIMAccountRegistry(source)
    before = [_tree_bytes(root.path) for root in native_roots]
    ready = threading.Barrier(2)

    def attempt(target_deployment, synchronize=False):
        if synchronize:
            ready.wait(timeout=5)
        with pytest.raises(OwnershipUnknown, match="ownership-unknown"):
            registry.transfer(
                "alpha",
                target_root=target,
                target_deployment=target_deployment,
                expected_binding_digest="a" * 64,
                request_id="fake-transfer-replay",
            )

    with ThreadPoolExecutor(max_workers=2) as workers:
        results = [workers.submit(attempt, name, True) for name in ("beta", "gamma")]
        for result in results:
            result.result(timeout=5)
    attempt("beta")
    assert [_tree_bytes(root.path) for root in native_roots] == before


@pytest.mark.parametrize("environment", ["sim", "SIM", "live", "real", ""])
def test_no_environment_or_fake_account_identity_can_enable_binding(native_roots, environment, caplog):
    from hedge_fund.brokers.account_binding import (
        SIMAccountRegistry,
        SIMOwnershipUnknown,
    )

    root = native_roots[0]
    registry = SIMAccountRegistry(root)
    before = _tree_bytes(root.path)
    with pytest.raises(SIMOwnershipUnknown) as denied:
        registry.bind(environment, "fake-account-identity-sentinel", "fake-deployment-sentinel")
    assert denied.value.code == "ownership-unknown"
    public = json.dumps(registry.inspect()) + str(denied.value) + caplog.text
    assert "fake-account-identity-sentinel" not in public
    assert "fake-deployment-sentinel" not in public
    assert str(root.path) not in public
    assert _tree_bytes(root.path) == before


def test_unenrolled_closed_or_unverifiable_roots_never_gain_account_authority(tmp_path, monkeypatch):
    from hedge_fund.brokers.account_binding import SIMAccountRegistry

    with RootContext.open(tmp_path) as root:
        registry = SIMAccountRegistry(root)

        def forbidden(*_args, **_kwargs):
            pytest.fail("unsupported account authority accessed a root or namespace probe")

        for method in ("revalidate", "verify_private_storage", "read_bytes", "write_bytes", "mkdir", "open_lock_file"):
            monkeypatch.setattr(root, method, forbidden)
        with pytest.raises(OwnershipUnknown):
            registry.bind("sim", "fake-account", "alpha")
        root.close()
        with pytest.raises(OwnershipUnknown):
            registry.release("alpha", expected_binding_digest="a" * 64, request_id="fake-release")
        assert registry.inspect()["execution_authorized"] is False
    assert list(tmp_path.iterdir()) == []


def test_production_boundary_ignores_linked_caller_claims_and_creates_no_identity_key(native_roots):
    from hedge_fund.brokers.account_binding import SIMAccountRegistry

    source, target = native_roots
    claimed = source.path / "untrusted-account-registry.json"
    claimed.write_text('{"state":"released","proof":"caller-attestation"}', encoding="utf-8")
    os.link(claimed, target.path / "untrusted-account-registry.json")
    before = [_tree_bytes(root.path) for root in native_roots]
    with pytest.raises(OwnershipUnknown):
        SIMAccountRegistry(source).bind("sim", "fake-account", "alpha")
    with pytest.raises(OwnershipUnknown):
        SIMAccountRegistry(target).transfer(
            "alpha",
            target_root=source,
            target_deployment="beta",
            expected_binding_digest="a" * 64,
            request_id="fake-linked-transfer",
        )
    assert [_tree_bytes(root.path) for root in native_roots] == before


@pytest.mark.parametrize("missing", ["transport", "secrets_provider"])
def test_fake_adapter_helper_never_falls_back_to_real_dependencies(tmp_path, monkeypatch, missing):
    from hedge_fund.brokers import saxo
    from hedge_fund.brokers.test_saxo_doubles import fake_saxo_broker

    def forbidden(*_args, **_kwargs):
        pytest.fail("fake adapter helper reached the client without explicit fakes")

    monkeypatch.setattr(saxo, "SaxoClient", forbidden)
    dependencies = {
        "transport": SimpleNamespace(request=forbidden),
        "secrets_provider": SimpleNamespace(resolve=forbidden, write_back=forbidden),
    }
    dependencies[missing] = None
    with pytest.raises(RuntimeError, match="fake SIM adapter"):
        fake_saxo_broker(["AAPL"], lock_dir=tmp_path, **dependencies)
    assert list(tmp_path.iterdir()) == []
