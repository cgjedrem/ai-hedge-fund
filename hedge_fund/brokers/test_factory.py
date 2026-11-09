from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from hedge_fund.brokers.factory import (
    build_broker,
    build_saxo_demo_client,
    build_saxo_inspection_client,
)
from hedge_fund.brokers.saxo import DemoTokenManager, LeaseBackedDemoTokenManager
from hedge_fund.brokers.test_saxo_doubles import FakeTransport
from hedge_fund.runtime.admission import OwnershipUnknown
from hedge_fund.runtime.external_credentials import (
    INSPECTION_CAPABILITY_DESTINATIONS,
    RuntimeCredentialLeaseStore,
)

DEMO_REF = "op://vault/item/demo-access-token"
OAUTH_REFS = {
    "SAXO_APP_KEY_REF": "op://vault/item/app-key",
    "SAXO_APP_SECRET_REF": "op://vault/item/app-secret",
    "SAXO_REFRESH_TOKEN_REF": "op://vault/item/refresh-token",
}


class FakeSecrets:
    def __init__(self):
        self.resolves = []
        self.writes = []

    def resolve(self, variable, reference):
        self.resolves.append((variable, reference))
        if variable == "SAXO_DEMO_ACCESS_TOKEN_REF":
            return "demo-token-private"
        return f"resolved-{variable}"

    def write_back(self, variable, reference, value):
        self.writes.append((variable, reference, value))


def _deployed():
    return SimpleNamespace(
        broker="saxo",
        spec=SimpleNamespace(
            broker="saxo",
            costs=None,
            saxo_account_key="sim-account-1",
        ),
        universe=["AAPL"],
    )


def test_read_only_builder_uses_only_demo_reference_and_defers_resolution():
    secrets = FakeSecrets()
    transport = FakeTransport()

    client = build_saxo_demo_client(
        secrets_provider=secrets,
        transport=transport,
        environ={"SAXO_DEMO_ACCESS_TOKEN_REF": DEMO_REF},
    )

    assert isinstance(client.tokens, DemoTokenManager)
    assert secrets.resolves == []
    assert transport.calls == []


def test_read_only_builder_uses_demo_token_only_for_sim_reads():
    secrets = FakeSecrets()
    transport = FakeTransport([(200, {"ClientKey": "client"})])
    client = build_saxo_demo_client(
        secrets_provider=secrets,
        transport=transport,
        environ={"SAXO_DEMO_ACCESS_TOKEN_REF": DEMO_REF},
    )

    assert isinstance(client.tokens, DemoTokenManager)
    assert secrets.resolves == []
    client.check_connection()
    assert secrets.resolves == [("SAXO_DEMO_ACCESS_TOKEN_REF", DEMO_REF)]
    assert secrets.writes == []
    sim_url_prefix = "https://gateway.saxobank.com/sim/openapi/"
    urls = [call["url"] for call in transport.calls]
    assert all(url.startswith(sim_url_prefix) for url in urls)
    assert all(call["method"] == "GET" for call in transport.calls)
    assert all(not call["url"].endswith("/token") for call in transport.calls)


def test_dedicated_inspection_builder_uses_only_a_pinned_memory_capability():
    store = RuntimeCredentialLeaseStore(
        root_id="d" * 64,
        instance_id="inspection-boot",
        allowed_capabilities=INSPECTION_CAPABILITY_DESTINATIONS,
        clock=lambda: datetime(2026, 10, 30, 12, 0, tzinfo=timezone.utc),
    )
    store.publish_capability(
        "saxo-demo-token",
        "synthetic-inspection-token",
        expected_generation=0,
        delivery_id="delivery",
        root_id="d" * 64,
        instance_id="inspection-boot",
        destination="saxo-sim-readonly",
        expires_at="2026-10-31T12:00:00Z",
    )
    handle = store.capture_capability("saxo-demo-token", destination="saxo-sim-readonly")
    secrets = FakeSecrets()

    class Transport:
        def __init__(self):
            self.calls = []

        def request(self, method, url, **kwargs):
            call = dict(kwargs)
            call["headers"] = {"Authorization": "******"}
            self.calls.append((method, url, call))
            return 200, {"ClientKey": "sim"}

    transport = Transport()

    client = build_saxo_inspection_client(
        lease_store=store,
        handle=handle,
        authority_check=lambda: None,
        transport=transport,
    )

    assert isinstance(client.tokens, LeaseBackedDemoTokenManager)
    assert not hasattr(client.tokens, "access_token")
    client.check_connection()
    assert secrets.resolves == []
    assert secrets.writes == []
    assert len(transport.calls) == 1
    assert transport.calls[0][0] == "GET"
    assert transport.calls[0][1].endswith("/port/v1/users/me")
    assert transport.calls[0][2]["headers"]["Authorization"] == "******"


@pytest.mark.parametrize(
    "environment",
    [
        {"SAXO_DEMO_ACCESS_TOKEN_REF": DEMO_REF},
        OAUTH_REFS,
    ],
)
def test_broker_factory_preserves_sim_ownership_denial_before_secret_resolution(environment):
    secrets = FakeSecrets()
    with pytest.raises(OwnershipUnknown, match="ownership-unknown"):
        build_broker(
            _deployed(),
            directory="unused",
            secrets_provider=secrets,
            environ=environment,
        )

    assert secrets.resolves == []
    assert secrets.writes == []


def test_read_only_builder_rejects_oauth_only_mode():
    secrets = FakeSecrets()

    with pytest.raises(ValueError, match="SAXO_DEMO_ACCESS_TOKEN_REF"):
        build_saxo_demo_client(secrets_provider=secrets, environ=OAUTH_REFS)

    assert secrets.resolves == []


def test_read_only_builder_rejects_mixed_mode_before_resolving_secrets():
    secrets = FakeSecrets()

    with pytest.raises(ValueError, match="cannot be combined"):
        build_saxo_demo_client(
            secrets_provider=secrets,
            environ={"SAXO_DEMO_ACCESS_TOKEN_REF": DEMO_REF, **OAUTH_REFS},
        )

    assert secrets.resolves == []
