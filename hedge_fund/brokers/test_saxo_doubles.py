"""Network-free doubles for the Saxo adapter."""

from __future__ import annotations

import os
import socket
from collections import deque
from datetime import datetime, timezone
from pathlib import Path


class FakeTransport:
    def __init__(self, responses=()):
        self.responses = deque(responses)
        self.calls = []
        self.auth_schemes = []

    def request(self, method, url, *, headers=None, json=None, data=None, params=None, auth=None, timeout=None):
        recorded_headers = dict(headers or {})
        authorization = recorded_headers.get("Authorization", "")
        self.auth_schemes.append(authorization.split(" ", 1)[0] if authorization else None)
        if authorization:
            recorded_headers["Authorization"] = "******"
        self.calls.append(
            {
                "method": method,
                "url": url,
                "headers": recorded_headers,
                "json": json,
                "data": data,
                "params": params,
                "auth": auth,
                "timeout": timeout,
            }
        )
        if not self.responses:
            raise AssertionError(f"unexpected request: {method} {url}")
        response = self.responses.popleft()
        if isinstance(response, Exception):
            raise response
        return response


class FakeClock:
    def __init__(self, now=0.0, utc_now=None):
        self.value = now
        self._utc_now = utc_now or datetime(2026, 10, 30, 12, 0, tzinfo=timezone.utc)
        self.sleeps = []

    def monotonic(self):
        return self.value

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.value += seconds

    def utcnow(self):
        return self._utc_now


def _owned_test_path(path):
    if os.environ.get("HEDGE_FUND_TEST_MODE") != "1" or not getattr(socket.socket.connect, "__hedge_fund_test_network_guard__", False):
        raise RuntimeError("fake SIM fixtures require the isolated network-denied test harness")
    test_root = Path(os.environ["HEDGE_FUND_TEST_ROOT"]).resolve(strict=True)
    candidate = Path(path).resolve(strict=True)
    if not candidate.is_relative_to(test_root):
        raise RuntimeError("fake SIM fixtures require a test-owned path")
    return candidate


def write_fake_sim_deployment(name, spec, universe, *, root):
    """Seed historical SIM records, not an admitted deployment/account binding."""
    import yaml

    from hedge_fund.fund import normalize_universe
    from hedge_fund.paper.deployed import DeployedFund, FUND_FILE, validate_fund_name
    from hedge_fund.paper.ledger import Ledger

    root = _owned_test_path(root)
    validate_fund_name(name)
    if spec.broker != "saxo":
        raise ValueError("fake SIM deployment requires the Saxo mandate choice")
    directory = root / name
    deployed = DeployedFund(name=name, spec=spec, universe=normalize_universe(universe), broker="saxo", created="2026-10-29")
    directory.mkdir()
    (directory / FUND_FILE).write_text(yaml.safe_dump(deployed.model_dump(), sort_keys=False))
    Ledger(directory).init()
    return directory


def fake_saxo_broker(universe, *, secrets_provider, transport, lock_dir):
    """Exercise the low-level adapter with fakes, never the ownership factory."""
    from hedge_fund.brokers.saxo import (
        RequestsTransport,
        SaxoBroker,
        SaxoClient,
        TokenManager,
    )
    from hedge_fund.secrets.provider import SecretProvider

    lock_root = _owned_test_path(lock_dir)
    if isinstance(transport, RequestsTransport) or isinstance(secrets_provider, SecretProvider) or not callable(getattr(transport, "request", None)) or not callable(getattr(secrets_provider, "resolve", None)) or not callable(getattr(secrets_provider, "write_back", None)):
        raise RuntimeError("fake SIM adapter requires explicit fake transport and secret providers")
    tokens = TokenManager(
        app_key="fake-app-key",
        app_secret="fake-app-secret",
        refresh_token_ref="op://synthetic/adapter/refresh",
        secrets_provider=secrets_provider,
        transport=transport,
        lock_dir=lock_root,
    )
    return SaxoBroker(SaxoClient(tokens=tokens, transport=transport, base_currency="USD"), universe)
