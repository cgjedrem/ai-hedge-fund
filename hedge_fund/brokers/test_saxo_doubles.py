"""Network-free doubles for the Saxo adapter."""

from __future__ import annotations

from collections import deque
from datetime import datetime, timezone


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
