import base64
import hashlib
from urllib.parse import parse_qs, urlparse

from hedge_fund.brokers.saxo_auth import interactive_login


class FakeTransport:
    def __init__(self, during_request=None):
        self.calls = []
        self.during_request = during_request

    def request(self, method, url, **kwargs):
        if self.during_request is not None:
            self.during_request()
        self.calls.append((method, url, kwargs))
        return 200, {"refresh_token": "rotated-secret"}


class FakeSecrets:
    def __init__(self, during_writeback=None):
        self.writes = []
        self.during_writeback = during_writeback

    def write_back(self, variable, reference, value):
        if self.during_writeback is not None:
            self.during_writeback()
        self.writes.append((variable, reference, value))


def test_interactive_login_uses_pkce_and_persists_rotating_token_under_refresh_lock(tmp_path):
    reference = "op://vault/item/token"
    lock_dir = tmp_path / "locks"
    lock_path = lock_dir / f"{hashlib.sha256(reference.encode()).hexdigest()}.lockdir"
    transport = FakeTransport(during_request=lambda: _assert_lock_held(lock_path))
    secrets = FakeSecrets(during_writeback=lambda: _assert_lock_held(lock_path))
    opened = []

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

    assert opened[0].startswith("https://sim.logonvalidation.net/authorize?")
    query = parse_qs(urlparse(opened[0]).query)
    expected = base64.urlsafe_b64encode(hashlib.sha256(("v" * 64).encode()).digest()).rstrip(b"=").decode()
    assert query["code_challenge"] == [expected]
    assert query["code_challenge_method"] == ["S256"]
    method, url, kwargs = transport.calls[0]
    assert method == "POST" and url.endswith("/token")
    assert kwargs["data"]["grant_type"] == "authorization_code"
    assert kwargs["data"]["code_verifier"] == "v" * 64
    assert secrets.writes == [("SAXO_REFRESH_TOKEN_REF", reference, "rotated-secret")]
    assert list(lock_dir.iterdir()) == []


def _assert_lock_held(lock_path):
    assert (lock_path / "owner").is_file()
