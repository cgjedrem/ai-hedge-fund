from __future__ import annotations

import hashlib
import threading
import time
from pathlib import Path

import pytest

from hedge_fund.brokers.saxo import SaxoAuthError, TokenManager, TokenState
from hedge_fund.brokers.test_saxo_doubles import FakeClock, FakeTransport


class SharedSecrets:
    def __init__(self):
        self.value = "refresh-old"
        self.writes = []

    def resolve(self, variable, reference):
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
