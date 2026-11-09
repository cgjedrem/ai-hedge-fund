from __future__ import annotations

from types import SimpleNamespace

import pytest

from hedge_fund.brokers.factory import build_broker, build_saxo_demo_client
from hedge_fund.brokers.saxo import DemoTokenManager
from hedge_fund.brokers.test_saxo_doubles import FakeTransport
from hedge_fund.runtime.admission import OwnershipUnknown

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
