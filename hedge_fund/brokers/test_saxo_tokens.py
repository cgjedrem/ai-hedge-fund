from __future__ import annotations

import hashlib
import threading
import time
from pathlib import Path

import pytest

from hedge_fund.brokers.saxo import (
    DemoTokenManager,
    LeaseBackedDemoTokenManager,
    SaxoAuthError,
    SaxoClient,
    SaxoReconcileError,
    TokenManager,
    TokenState,
)
from hedge_fund.brokers.test_saxo_doubles import FakeClock, FakeTransport
from hedge_fund.runtime.external_credentials import (
    INSPECTION_CAPABILITY_DESTINATIONS,
    RuntimeCredentialLeaseStore,
)


class SharedSecrets:
    def __init__(self):
        self.value = "refresh-old"
        self.resolves = []
        self.writes = []

    def resolve(self, variable, reference):
        self.resolves.append((variable, reference))
        return self.value

    def write_back(self, variable, reference, value):
        self.writes.append(value)
        self.value = value


def _manager(transport, secrets, clock, reference="op://vault/item/token", lock_dir=None, lock_timeout_s=90.0):
    return TokenManager(
        app_key="app-key",
        app_secret="secret-never-display",
        refresh_token_ref=reference,
        secrets_provider=secrets,
        transport=transport,
        clock=clock,
        lock_dir=lock_dir,
        lock_timeout_s=lock_timeout_s,
    )


def _inspection_manager(clock=None):
    clock = clock or FakeClock()
    store = RuntimeCredentialLeaseStore(
        root_id="a" * 64,
        instance_id="inspection-boot",
        allowed_capabilities=INSPECTION_CAPABILITY_DESTINATIONS,
        clock=clock.utcnow,
    )
    store.publish_capability(
        "saxo-demo-token",
        "synthetic-sim-token",
        expected_generation=0,
        delivery_id="inspection-delivery",
        root_id="a" * 64,
        instance_id="inspection-boot",
        destination="saxo-sim-readonly",
        expires_at="2026-10-31T12:00:00Z",
    )
    captured = store.capture_capability("saxo-demo-token", destination="saxo-sim-readonly")
    return store, LeaseBackedDemoTokenManager(
        lease_store=store,
        handle=captured,
        authority_check=lambda: None,
        clock=clock,
    )


def test_refresh_rotates_and_persists_before_authorizing_access_token(tmp_path):
    secrets = SharedSecrets()
    transport = FakeTransport([(200, {"access_token": "access-secret", "refresh_token": "refresh-new", "expires_in": 900})])
    manager = _manager(transport, secrets, FakeClock(), lock_dir=tmp_path / "locks")

    assert manager.get_access_token() == "access-secret"
    assert manager.state == TokenState.AUTHORIZED
    assert secrets.writes == ["refresh-new"]
    assert transport.calls[0]["data"]["grant_type"] == "refresh_token"
    assert transport.calls[0]["data"]["refresh_token"] == "refresh-old"
    assert transport.calls[0]["auth"] == ("app-key", "secret-never-display")
    assert list((tmp_path / "locks").iterdir()) == []


def test_refresh_lock_directory_requires_absolute_path():
    with pytest.raises(ValueError, match="absolute path"):
        TokenManager(
            app_key="key",
            app_secret="secret",
            refresh_token_ref="op://vault/item/token",
            secrets_provider=SharedSecrets(),
            lock_dir="relative-locks",
        )


def test_two_managers_reread_rotated_token_under_shared_reference_lock():
    secrets = SharedSecrets()

    class RacingTransport:
        def __init__(self):
            self.responses = [
                (200, {"access_token": "access-1", "refresh_token": "refresh-1", "expires_in": 900}),
                (200, {"access_token": "access-2", "refresh_token": "refresh-2", "expires_in": 900}),
            ]
            self.calls = []
            self.lock = threading.Lock()
            self.first_started = threading.Event()
            self.release_first = threading.Event()

        def request(self, method, url, **kwargs):
            with self.lock:
                index = len(self.calls)
                self.calls.append(kwargs["data"]["refresh_token"])
                response = self.responses[index]
            if index == 0:
                self.first_started.set()
                self.release_first.wait(timeout=5)
            return response

    transport = RacingTransport()
    first = _manager(transport, secrets, FakeClock(), "op://vault/concurrent/token")
    second = _manager(transport, secrets, FakeClock(), "op://vault/concurrent/token")
    results = []
    failures = []

    def refresh(manager):
        try:
            results.append(manager.get_access_token())
        except Exception as error:
            failures.append(error)

    first_thread = threading.Thread(target=refresh, args=(first,))
    second_thread = threading.Thread(target=refresh, args=(second,))
    first_thread.start()
    assert transport.first_started.wait(timeout=2)
    second_thread.start()
    time.sleep(0.05)
    transport.release_first.set()
    first_thread.join(timeout=5)
    second_thread.join(timeout=5)

    assert not first_thread.is_alive() and not second_thread.is_alive()
    assert failures == []
    assert sorted(results) == ["access-1", "access-2"]
    assert transport.calls == ["refresh-old", "refresh-1"]
    assert secrets.writes == ["refresh-1", "refresh-2"]


def test_access_token_refreshes_inside_margin_and_failure_requires_reauth():
    secrets = SharedSecrets()
    clock = FakeClock()
    transport = FakeTransport(
        [
            (200, {"access_token": "access-1", "refresh_token": "refresh-1", "expires_in": 180}),
            (400, {"error": "invalid_grant", "description": "refresh-1"}),
        ]
    )
    manager = _manager(transport, secrets, clock)
    assert manager.get_access_token() == "access-1"
    clock.value += 61

    with pytest.raises(SaxoAuthError, match="interactive Saxo login") as error:
        manager.get_access_token()
    assert "refresh-1" not in str(error.value)
    assert manager.state == TokenState.REAUTH_REQUIRED
    with pytest.raises(SaxoAuthError):
        manager.get_access_token()
    assert len(transport.calls) == 2


def test_writeback_failure_never_exposes_new_access_token():
    class BrokenWriteback(SharedSecrets):
        def write_back(self, variable, reference, value):
            raise RuntimeError(value)

    transport = FakeTransport([(200, {"access_token": "must-not-escape", "refresh_token": "rotated", "expires_in": 900})])
    manager = _manager(transport, BrokenWriteback(), FakeClock())

    with pytest.raises(SaxoAuthError):
        manager.get_access_token()

    assert manager.access_token is None
    assert manager.state == TokenState.REAUTH_REQUIRED


def test_existing_refresh_lock_times_out_with_owner_and_is_not_removed(tmp_path):
    reference = "op://vault/item/stale"
    lock_root = tmp_path / "locks"
    lock_path = lock_root / f"{hashlib.sha256(reference.encode()).hexdigest()}.lockdir"
    lock_path.mkdir(parents=True)
    owner = lock_path / "owner"
    owner.write_text("test-host:1234", encoding="utf-8")
    transport = FakeTransport()
    manager = _manager(
        transport,
        SharedSecrets(),
        FakeClock(),
        reference=reference,
        lock_dir=lock_root,
        lock_timeout_s=0.02,
    )

    with pytest.raises(SaxoAuthError, match="contention") as error:
        manager.get_access_token()

    assert "test-host:1234" in str(error.value)
    assert "retry" in str(error.value).lower()
    assert "interactive Saxo login" not in str(error.value)
    assert manager.state == TokenState.UNAUTHENTICATED
    assert owner.read_text(encoding="utf-8") == "test-host:1234"
    assert lock_path.is_dir()
    assert transport.calls == []


def test_default_refresh_lock_wait_is_at_least_ninety_seconds():
    assert _manager(FakeTransport(), SharedSecrets(), FakeClock()).lock_timeout_s >= 90


def test_refresh_lock_cleanup_failure_does_not_discard_persisted_token(tmp_path, monkeypatch, caplog):
    secrets = SharedSecrets()
    transport = FakeTransport([(200, {"access_token": "access-1", "refresh_token": "refresh-1", "expires_in": 900})])
    manager = _manager(transport, secrets, FakeClock(), lock_dir=tmp_path / "locks")
    original_unlink = Path.unlink

    def fail_owner_cleanup(path, *args, **kwargs):
        if path.name == "owner":
            raise OSError("permission denied")
        return original_unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", fail_owner_cleanup)

    assert manager.get_access_token() == "access-1"
    assert manager.state == TokenState.AUTHORIZED
    assert secrets.value == "refresh-1"
    assert "lock cleanup failed" in caplog.text.lower()
    assert list((tmp_path / "locks").glob("*.lockdir/owner"))


def test_demo_token_is_resolved_once_without_refresh_or_writeback():
    secrets = SharedSecrets()
    secrets.value = "demo-token-private"
    manager = DemoTokenManager(
        access_token_ref="op://vault/item/demo-token",
        secrets_provider=secrets,
    )

    assert manager.state == TokenState.UNAUTHENTICATED
    assert manager.get_access_token() == "demo-token-private"
    assert manager.get_access_token() == "demo-token-private"
    assert secrets.resolves == [("SAXO_DEMO_ACCESS_TOKEN_REF", "op://vault/item/demo-token")]
    assert secrets.writes == []
    assert not hasattr(manager, "expires_at")
    assert "demo-token-private" not in repr(manager)
    assert "demo-token" not in repr(manager)


def test_demo_token_requires_an_op_reference():
    with pytest.raises(ValueError, match="op://"):
        DemoTokenManager(
            access_token_ref="not-a-reference",
            secrets_provider=SharedSecrets(),
        )


def test_demo_token_lookup_failure_does_not_expose_secret(caplog):
    class BrokenSecrets:
        def resolve(self, variable, reference):
            raise RuntimeError("demo-token-private")

        def write_back(self, variable, reference, value):
            raise AssertionError

    manager = DemoTokenManager(
        access_token_ref="op://vault/item/demo-token",
        secrets_provider=BrokenSecrets(),
    )

    with pytest.raises(SaxoAuthError) as error:
        manager.get_access_token()

    assert "demo-token-private" not in str(error.value)
    assert error.value.__context__ is None
    assert "demo-token-private" not in repr(manager)
    assert "demo-token-private" not in caplog.text


def test_rejected_demo_token_fails_closed_without_retry_or_refresh():
    secrets = SharedSecrets()
    secrets.value = "demo-token-private"
    transport = FakeTransport([(401, {"error": "invalid_token", "description": "demo-token-private"})])
    manager = DemoTokenManager(
        access_token_ref="op://vault/item/demo-token",
        secrets_provider=secrets,
    )
    client = SaxoClient(tokens=manager, transport=transport, clock=FakeClock())

    with pytest.raises(SaxoAuthError, match="24-hour") as error:
        client.request("GET", "/port/v1/users/me")

    assert "demo-token-private" not in str(error.value)
    assert error.value.__context__ is None
    assert manager.state == TokenState.REAUTH_REQUIRED
    assert len(transport.calls) == 1
    assert transport.calls[0]["method"] == "GET"
    assert transport.calls[0]["url"].startswith("https://gateway.saxobank.com/sim/openapi/")
    assert transport.calls[0]["headers"]["Authorization"] == "******"
    assert not any(call["url"].endswith("/token") for call in transport.calls)
    assert secrets.writes == []


def test_demo_transport_error_does_not_retain_token_in_exception_context():
    token = "demo-token-private"
    secrets = SharedSecrets()
    secrets.value = token
    transport = FakeTransport([RuntimeError(token)])
    manager = DemoTokenManager(
        access_token_ref="op://vault/item/demo-token",
        secrets_provider=secrets,
    )
    client = SaxoClient(tokens=manager, transport=transport, clock=FakeClock())

    with pytest.raises(SaxoAuthError) as error:
        client.request("GET", "/port/v1/users/me")

    assert token not in str(error.value)
    assert token not in repr(error.value)
    assert error.value.__context__ is None
    assert transport.calls[0]["url"].startswith("https://gateway.saxobank.com/sim/openapi/")


class InspectionTransport:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        return self.response


@pytest.mark.parametrize("method,path", [("POST", "/port/v1/users/me"), ("GET", "/trade/v2/orders"), ("GET", "https://example.com/")])
def test_lease_backed_client_rejects_non_allowlisted_requests_before_transport(method, path):
    _store, tokens = _inspection_manager()
    transport = InspectionTransport((200, {"ClientKey": "sim"}))
    client = SaxoClient(tokens=tokens, transport=transport, clock=FakeClock())

    with pytest.raises(SaxoAuthError, match="read-only"):
        client.request(method, path)

    assert transport.calls == []


@pytest.mark.parametrize("status", [401, 403])
def test_lease_backed_client_rejects_without_refresh_and_invalidates_only_captured_generation(status):
    store, tokens = _inspection_manager()
    transport = InspectionTransport((status, {"error": "synthetic-sim-token"}))
    client = SaxoClient(tokens=tokens, transport=transport, clock=FakeClock())

    with pytest.raises(SaxoAuthError, match="rejected") as error:
        client.request("GET", "/port/v1/users/me")

    assert len(transport.calls) == 1
    assert transport.calls[0][2]["allow_redirects"] is False
    assert transport.calls[0][2]["proxies"] == {}
    assert transport.calls[0][2]["stream"] is True
    assert "synthetic-sim-token" not in repr(tokens)
    assert "synthetic-sim-token" not in str(error.value)
    assert store.capability_status("saxo-demo-token", destination="saxo-sim-readonly")["state"] == "requires-auth"


def test_lease_backed_client_invalidates_rejected_status_without_reading_reflected_body():
    store, tokens = _inspection_manager()

    class RejectedResponse:
        status_code = 403
        closed = False

        def iter_content(self, chunk_size):
            raise AssertionError("rejected response body must not be read")

        def close(self):
            self.closed = True

    response = RejectedResponse()
    transport = InspectionTransport(response)
    client = SaxoClient(tokens=tokens, transport=transport, clock=FakeClock())

    with pytest.raises(SaxoAuthError, match="rejected"):
        client.request("GET", "/port/v1/users/me")

    assert response.closed is True
    assert store.capability_status("saxo-demo-token", destination="saxo-sim-readonly")["state"] == "requires-auth"


def test_lease_backed_client_uses_fixed_timeout_and_refuses_redirects():
    _store, tokens = _inspection_manager()
    assert not hasattr(tokens, "access_token")
    assert not hasattr(tokens, "access_token_ref")
    transport = InspectionTransport((302, {"Location": "https://example.com/"}))
    client = SaxoClient(tokens=tokens, transport=transport, clock=FakeClock())

    with pytest.raises(SaxoAuthError, match="redirected"):
        client.request("GET", "/port/v1/users/me")

    assert transport.calls[0][2]["timeout"] == 10.0
    assert len(transport.calls) == 1


def test_lease_backed_response_body_is_bounded_and_not_reflected():
    _store, tokens = _inspection_manager()
    response_body = {"Data": ["x" * (1024 * 1024)]}
    transport = InspectionTransport((200, response_body))
    client = SaxoClient(tokens=tokens, transport=transport, clock=FakeClock())

    with pytest.raises(SaxoReconcileError, match="size limit") as error:
        client.request("GET", "/port/v1/accounts/me")

    assert "x" * 100 not in str(error.value)
    assert len(transport.calls) == 1


def test_demo_connection_check_uses_only_sim_user_read():
    secrets = SharedSecrets()
    secrets.value = "demo-token-private"
    transport = FakeTransport([(200, {"ClientKey": "sim-client"})])
    manager = DemoTokenManager(
        access_token_ref="op://vault/item/demo-token",
        secrets_provider=secrets,
    )
    client = SaxoClient(tokens=manager, transport=transport)

    client.check_connection()

    assert len(transport.calls) == 1
    assert transport.calls[0]["method"] == "GET"
    assert transport.calls[0]["url"] == "https://gateway.saxobank.com/sim/openapi/port/v1/users/me"
    assert transport.calls[0]["timeout"] == 15
    assert transport.calls[0]["headers"]["Authorization"] == "******"
    assert secrets.writes == []


def test_demo_connection_check_rejects_incomplete_user_response():
    manager = DemoTokenManager(
        access_token_ref="op://vault/item/demo-token",
        secrets_provider=SharedSecrets(),
    )
    client = SaxoClient(tokens=manager, transport=FakeTransport([(200, {"ClientKey": ""})]))

    with pytest.raises(SaxoAuthError, match="connection check failed"):
        client.check_connection()


@pytest.mark.parametrize(
    ("method", "order_post"),
    [("POST", False), ("PUT", False), ("DELETE", False), ("GET", True)],
)
def test_demo_token_client_rejects_mutations_before_token_resolution(method, order_post):
    secrets = SharedSecrets()
    transport = FakeTransport()
    manager = DemoTokenManager(
        access_token_ref="op://vault/item/demo-token",
        secrets_provider=secrets,
    )
    client = SaxoClient(tokens=manager, transport=transport)

    with pytest.raises(SaxoAuthError, match="read-only"):
        client.request(method, "/trade/v2/orders", order_post=order_post)

    assert manager.state == TokenState.UNAUTHENTICATED
    assert secrets.resolves == []
    assert transport.calls == []


@pytest.mark.parametrize("path", ["/trade/v2/orders", "/port/v1/users/me/../accounts/me", "/port/v1/clients/me"])
def test_demo_token_client_rejects_unallowlisted_gets_before_token_resolution(path):
    secrets = SharedSecrets()
    transport = FakeTransport()
    manager = DemoTokenManager(
        access_token_ref="op://vault/item/demo-token",
        secrets_provider=secrets,
    )
    client = SaxoClient(tokens=manager, transport=transport, clock=FakeClock())

    with pytest.raises(SaxoAuthError, match="read-only"):
        client.request("GET", path)

    assert manager.state == TokenState.UNAUTHENTICATED
    assert secrets.resolves == []
    assert transport.calls == []
