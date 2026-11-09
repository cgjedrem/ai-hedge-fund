import pytest

from hedge_fund.brokers.saxo_auth import interactive_login
from hedge_fund.runtime.admission import OwnershipUnknown


class FakeTransport:
    def __init__(self):
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        return 200, {"refresh_token": "rotated-secret"}


class FakeSecrets:
    def __init__(self):
        self.writes = []

    def write_back(self, variable, reference, value):
        self.writes.append((variable, reference, value))


def test_interactive_login_denies_before_browser_pkce_or_rotating_token_effects(tmp_path):
    reference = "op://vault/item/token"
    lock_dir = tmp_path / "locks"
    transport = FakeTransport()
    secrets = FakeSecrets()
    opened = []

    with pytest.raises(OwnershipUnknown, match="ownership-unknown"):
        interactive_login(
            "app-key",
            "app-secret",
            "http://localhost/callback",
            reference,
            secrets,
            browser_open=opened.append,
            prompt=lambda _: "http://localhost/callback?code=auth-code&state=state-123",
            transport=transport,
            verifier="v" * 64,
            state="state-123",
            lock_dir=lock_dir,
        )
    assert opened == transport.calls == secrets.writes == []
    assert not lock_dir.exists()


@pytest.mark.parametrize(
    "redirect_uri,callback",
    [
        ("http://localhost", "http://localhost/?code=auth-code&state=state-123"),
        ("http://localhost/", "http://localhost?code=auth-code&state=state-123"),
    ],
)
def test_interactive_login_cannot_gain_authority_from_registered_redirect_uri(tmp_path, redirect_uri, callback):
    transport = FakeTransport()

    with pytest.raises(OwnershipUnknown, match="ownership-unknown"):
        interactive_login(
            "app-key",
            "app-secret",
            redirect_uri,
            "op://vault/item/token",
            FakeSecrets(),
            browser_open=lambda _: None,
            prompt=lambda _: callback,
            transport=transport,
            verifier="v" * 64,
            state="state-123",
            lock_dir=tmp_path,
        )
    assert transport.calls == []
    assert list(tmp_path.iterdir()) == []


def test_interactive_login_denies_unknown_ownership_before_callback_validation(tmp_path):
    transport = FakeTransport()

    with pytest.raises(OwnershipUnknown, match="ownership-unknown"):
        interactive_login(
            "app-key",
            "app-secret",
            "http://localhost/callback",
            "op://vault/item/token",
            FakeSecrets(),
            browser_open=lambda _: None,
            prompt=lambda _: "http://localhost/other?code=auth-code&state=state-123",
            transport=transport,
            verifier="v" * 64,
            state="state-123",
            lock_dir=tmp_path,
        )
    assert transport.calls == []
