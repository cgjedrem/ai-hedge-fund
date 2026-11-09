"""Saxo OpenAPI SIM broker adapter."""

from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import re
import socket
import tempfile
import threading
import time
import uuid
from contextlib import AbstractContextManager, contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_DOWN
from enum import Enum
from pathlib import Path
from typing import Callable, Iterator, Protocol
from urllib.parse import parse_qs, urlparse

import requests

from hedge_fund.brokers.models import Fill, Order, Position
from hedge_fund.brokers.protocol import OrderSubmissionDeferred
from hedge_fund.runtime.external_credentials import (
    ExternalCredentialError,
    RuntimeCredentialHandle,
    RuntimeCredentialLeaseStore,
)
from hedge_fund.secrets.provider import SecretProvider

BASE_URL = "https://gateway.saxobank.com/sim/openapi"
AUTH_URL = "https://sim.logonvalidation.net"
_LOG = logging.getLogger(__name__)
_THREAD_REFRESH_LOCKS: dict[str, threading.Lock] = {}
_THREAD_REFRESH_LOCKS_GUARD = threading.Lock()
_US_EXCHANGES = ("NASDAQ", "NYSE", "NYSEARCA", "NYSEAMERICAN", "BATS", "CBOE")
_DEMO_READ_ONLY_PATHS = frozenset(
    {
        "/port/v1/users/me",
        "/port/v1/accounts/me",
        "/port/v1/balances",
        "/port/v1/positions",
    }
)
_MAX_INSPECTION_BODY_BYTES = 1024 * 1024
_MAX_INSPECTION_REQUESTS = 12
_MAX_INSPECTION_PAGES = 5
_MAX_INSPECTION_ROWS = 500
_MAX_INSPECTION_PAGE_ROWS = 100
_INSPECTION_REQUEST_TIMEOUT_S = 10.0
_INSPECTION_ACTION_TIMEOUT_S = 30.0


class Transport(Protocol):
    def request(self, method: str, url: str, **kwargs):
        ...


class SaxoAuthError(RuntimeError):
    """Authentication failed; interactive login may be required."""


class SaxoOrderError(RuntimeError):
    """Saxo rejected an order or execution could not be confirmed."""

    def __init__(self, message: str, error_code: str | None = None):
        super().__init__(message)
        self.error_code = error_code


class SaxoReconcileError(RuntimeError):
    """Saxo book or instrument data cannot be reconciled safely."""


class TokenState(str, Enum):
    UNAUTHENTICATED = "UNAUTHENTICATED"
    AUTHORIZED = "AUTHORIZED"
    REAUTH_REQUIRED = "REAUTH_REQUIRED"


@dataclass(frozen=True)
class SaxoAccountCandidate:
    account_key: str
    currency: str


@dataclass(frozen=True)
class SaxoPositionSummary:
    uic: int
    amount: float


@dataclass(frozen=True)
class SaxoAccountSummary:
    account_key: str
    currency: str
    cash_balance: float
    positions: tuple[SaxoPositionSummary, ...]

    @property
    def position_count(self) -> int:
        return len(self.positions)


class TokenManager:
    auth_mode = "oauth"

    def __init__(
        self,
        *,
        app_key: str,
        app_secret: str,
        refresh_token_ref: str,
        secrets_provider: SecretProvider,
        transport: Transport | None = None,
        clock=None,
        refresh_margin_s: float = 120.0,
        lock_dir: str | Path | None = None,
        lock_timeout_s: float = 90.0,
    ):
        if not isinstance(app_key, str) or not app_key or not isinstance(app_secret, str) or not app_secret or not isinstance(refresh_token_ref, str) or not refresh_token_ref.startswith("op://"):
            raise ValueError("Saxo credentials must include app key, app secret, and an op:// refresh reference")
        if not math.isfinite(refresh_margin_s) or refresh_margin_s < 0:
            raise ValueError("refresh margin cannot be negative")
        if not math.isfinite(lock_timeout_s) or lock_timeout_s <= 0:
            raise ValueError("refresh lock timeout must be positive")
        if lock_dir is not None and (not isinstance(lock_dir, (str, Path)) or not str(lock_dir).strip() or not Path(lock_dir).is_absolute()):
            raise ValueError("refresh lock directory must be an absolute path")
        self.app_key = app_key
        self.app_secret = app_secret
        self.refresh_token_ref = refresh_token_ref
        self.secrets_provider = secrets_provider
        self.transport = transport or RequestsTransport()
        self.clock = clock or SystemClock()
        self.refresh_margin_s = refresh_margin_s
        self.lock_timeout_s = lock_timeout_s
        self.lock_dir = Path(lock_dir) if lock_dir is not None else None
        self.access_token: str | None = None
        self.access_expires_at = 0.0
        self.state = TokenState.UNAUTHENTICATED

    def __repr__(self) -> str:
        return "TokenManager(state={!r}, access_token=[redacted], refresh_token_ref=[redacted])".format(self.state.value)

    def get_access_token(self) -> str:
        if self.state == TokenState.REAUTH_REQUIRED:
            raise SaxoAuthError("Saxo authorization expired; run interactive Saxo login")
        if self.access_token and self.access_expires_at - self.clock.monotonic() >= self.refresh_margin_s:
            return self.access_token
        self._refresh()
        if not self.access_token:
            raise SaxoAuthError("Saxo authorization unavailable; run interactive Saxo login")
        return self.access_token

    def _refresh(self) -> None:
        try:
            with _refresh_lock(self.refresh_token_ref, self.lock_dir, timeout_s=self.lock_timeout_s):
                refresh_token = self.secrets_provider.resolve("SAXO_REFRESH_TOKEN_REF", self.refresh_token_ref)
                response = self.transport.request(
                    "POST",
                    f"{AUTH_URL}/token",
                    auth=(self.app_key, self.app_secret),
                    data={"grant_type": "refresh_token", "refresh_token": refresh_token},
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                    timeout=15,
                )
                status, body = _response(response)
                if status < 200 or status >= 300 or not isinstance(body, dict):
                    raise ValueError("token endpoint rejected refresh")
                access_token = body.get("access_token")
                rotated = body.get("refresh_token")
                expires_in = body.get("expires_in")
                if not isinstance(access_token, str) or not access_token or not isinstance(rotated, str) or not rotated:
                    raise ValueError("token response incomplete")
                lifetime = float(expires_in)
                if lifetime <= 0:
                    raise ValueError("token lifetime invalid")
                self.secrets_provider.write_back("SAXO_REFRESH_TOKEN_REF", self.refresh_token_ref, rotated)
        except _RefreshLockTimeout as exc:
            _LOG.warning("Saxo refresh lock contention; verify owner and retry")
            raise SaxoAuthError(str(exc)) from None
        except Exception:
            self.access_token = None
            self.access_expires_at = 0.0
            self.state = TokenState.REAUTH_REQUIRED
            _LOG.warning("Saxo token refresh failed; interactive login required")
            raise SaxoAuthError("Saxo token refresh failed; run interactive Saxo login") from None
        self.access_token = access_token
        self.access_expires_at = self.clock.monotonic() + lifetime
        self.state = TokenState.AUTHORIZED


class DemoTokenManager:
    auth_mode = "demo-token"

    def __init__(
        self,
        *,
        access_token_ref: str,
        secrets_provider: SecretProvider,
    ):
        if not isinstance(access_token_ref, str) or not access_token_ref.startswith("op://"):
            raise ValueError("SAXO_DEMO_ACCESS_TOKEN_REF requires an op:// reference")
        if not callable(getattr(secrets_provider, "resolve", None)):
            raise ValueError("Saxo demo token provider must support secret resolution")
        self.access_token_ref = access_token_ref
        self.secrets_provider = secrets_provider
        self.access_token: str | None = None
        self.state = TokenState.UNAUTHENTICATED

    def __repr__(self) -> str:
        return "DemoTokenManager(state={!r}, access_token=[redacted], access_token_ref=[redacted])".format(self.state.value)

    def get_access_token(self) -> str:
        if self.state == TokenState.REAUTH_REQUIRED:
            raise SaxoAuthError("Saxo SIM 24-hour token unavailable; refresh it in 1Password and retry")
        if self.access_token is not None:
            return self.access_token
        try:
            token = self.secrets_provider.resolve("SAXO_DEMO_ACCESS_TOKEN_REF", self.access_token_ref)
        except Exception:
            token = None
        if not isinstance(token, str) or not token or token.strip() != token or any(char.isspace() or not char.isprintable() for char in token):
            self.state = TokenState.REAUTH_REQUIRED
            raise SaxoAuthError("Saxo SIM 24-hour token unavailable; refresh it in 1Password and retry")
        self.access_token = token
        self.state = TokenState.AUTHORIZED
        return token

    def check_response_progress(self) -> float:
        remaining = self.remaining()
        self.authority_check()
        try:
            self.lease_store.assert_capability_dispatch_allowed(self.handle, destination="saxo-sim-readonly")
        except ExternalCredentialError:
            raise SaxoAuthError("Saxo SIM inspection credential is unavailable") from None
        return remaining

    def mark_rejected(self) -> None:
        self.access_token = None
        self.state = TokenState.REAUTH_REQUIRED


class LeaseBackedDemoTokenManager(DemoTokenManager):
    """Fetch an authorized SIM bearer from one pinned in-memory capability."""

    def __init__(
        self,
        *,
        lease_store: RuntimeCredentialLeaseStore,
        handle: RuntimeCredentialHandle,
        authority_check: Callable[[], None],
        clock=None,
        action_timeout_s: float = _INSPECTION_ACTION_TIMEOUT_S,
    ) -> None:
        if not isinstance(lease_store, RuntimeCredentialLeaseStore) or not isinstance(handle, RuntimeCredentialHandle):
            raise ValueError("Saxo inspection lease is unavailable")
        if handle.provider_id != "saxo-demo-token" or handle.destination != "saxo-sim-readonly" or handle.purpose != "saxo-sim-readonly":
            raise ValueError("Saxo inspection lease purpose is invalid")
        if not callable(authority_check) or not math.isfinite(action_timeout_s) or action_timeout_s <= 0 or action_timeout_s > _INSPECTION_ACTION_TIMEOUT_S:
            raise ValueError("Saxo inspection authority and timeout are required")
        self.lease_store = lease_store
        self.handle = handle
        self.authority_check = authority_check
        self.clock = clock or SystemClock()
        self.deadline = self.clock.monotonic() + action_timeout_s
        self.request_count = 0
        self.page_counts: dict[str, int] = {}
        self.row_counts: dict[str, int] = {}
        self.state = TokenState.UNAUTHENTICATED

    def __repr__(self) -> str:
        return "LeaseBackedDemoTokenManager(state={!r}, capability=[redacted])".format(self.state.value)

    def remaining(self) -> float:
        remaining = self.deadline - self.clock.monotonic()
        if remaining <= 0:
            raise SaxoAuthError("Saxo SIM inspection timed out")
        return remaining

    def before_request(self, method: str, path: str) -> float:
        if not isinstance(method, str) or method.upper() != "GET" or path not in _DEMO_READ_ONLY_PATHS:
            raise SaxoAuthError("Saxo SIM inspection is read-only")
        timeout = min(_INSPECTION_REQUEST_TIMEOUT_S, self.remaining())
        self.authority_check()
        try:
            self.lease_store.assert_capability_dispatch_allowed(self.handle, destination="saxo-sim-readonly")
        except ExternalCredentialError:
            raise SaxoAuthError("Saxo SIM inspection credential is unavailable") from None
        self.request_count += 1
        if self.request_count > _MAX_INSPECTION_REQUESTS:
            raise SaxoReconcileError("Saxo SIM inspection request limit exceeded")
        return timeout

    def get_access_token(self) -> str:
        self.authority_check()
        try:
            token = self.lease_store.capability_value_for_dispatch(
                self.handle,
                destination="saxo-sim-readonly",
            )
        except ExternalCredentialError:
            raise SaxoAuthError("Saxo SIM inspection credential is unavailable") from None
        self.state = TokenState.AUTHORIZED
        return token

    def record_page(self, collection: str, row_count: int) -> None:
        if collection not in {"accounts", "positions"} or type(row_count) is not int or row_count < 0 or row_count > _MAX_INSPECTION_PAGE_ROWS:
            raise SaxoReconcileError("Saxo SIM inspection response exceeds a page limit")
        pages = self.page_counts.get(collection, 0) + 1
        rows = self.row_counts.get(collection, 0) + row_count
        if pages > _MAX_INSPECTION_PAGES or rows > _MAX_INSPECTION_ROWS:
            raise SaxoReconcileError("Saxo SIM inspection response exceeds a collection limit")
        self.page_counts[collection] = pages
        self.row_counts[collection] = rows

    def mark_rejected(self) -> None:
        self.state = TokenState.REAUTH_REQUIRED
        try:
            self.lease_store.invalidate_capability(self.handle)
        except ExternalCredentialError:
            pass

    def verify_publish(self) -> None:
        self.remaining()
        self.authority_check()
        try:
            self.lease_store.assert_capability_dispatch_allowed(self.handle, destination="saxo-sim-readonly")
        except ExternalCredentialError:
            raise SaxoAuthError("Saxo SIM inspection credential is unavailable") from None


class SystemClock:
    def monotonic(self) -> float:
        return time.monotonic()

    def sleep(self, seconds: float) -> None:
        time.sleep(seconds)

    def utcnow(self) -> datetime:
        return datetime.now(timezone.utc)


class RequestsTransport:
    def request(self, method: str, url: str, **kwargs):
        disable_environment_proxies = kwargs.pop("_disable_environment_proxies", False)
        kwargs["allow_redirects"] = False
        if disable_environment_proxies:
            session = requests.Session()
            session.trust_env = False
            try:
                response = session.request(method, url, **kwargs)
                response._aihf_session = session
                return response
            except Exception:
                session.close()
                raise
        return requests.request(method, url, **kwargs)


class Pacer:
    def __init__(self, *, min_interval_s: dict[str, float] | None = None, clock=None):
        self.min_interval_s = dict(min_interval_s or {"orders": 1.0})
        if any(not key or not math.isfinite(value) or value < 0 for key, value in self.min_interval_s.items()):
            raise ValueError("pacer intervals must be non-negative")
        self.clock = clock or SystemClock()
        self.last_call_at: dict[str, float] = {}

    def wait_for(self, endpoint_class: str) -> None:
        if endpoint_class not in self.min_interval_s:
            return
        now = self.clock.monotonic()
        previous = self.last_call_at.get(endpoint_class)
        interval = self.min_interval_s[endpoint_class]
        if previous is not None and now - previous < interval:
            self.clock.sleep(interval - (now - previous))
        self.last_call_at[endpoint_class] = self.clock.monotonic()


class SaxoClient:
    def __init__(
        self,
        *,
        tokens: TokenManager | DemoTokenManager,
        transport: Transport | None = None,
        pacer: Pacer | None = None,
        base_currency: str = "USD",
        execution_timeout_s: float = 120.0,
        clock=None,
        poll_interval_s: float = 1.0,
    ):
        if not isinstance(base_currency, str) or not base_currency or not math.isfinite(execution_timeout_s) or execution_timeout_s <= 0 or not math.isfinite(poll_interval_s) or poll_interval_s <= 0:
            raise ValueError("currency and positive order polling bounds are required")
        self.tokens = tokens
        self.transport = transport or getattr(tokens, "transport", None) or RequestsTransport()
        self.pacer = pacer or Pacer(clock=clock)
        self.clock = clock or SystemClock()
        self.base_currency = base_currency.upper()
        self.execution_timeout_s = execution_timeout_s
        self.poll_interval_s = poll_interval_s
        self.client_key: str | None = None
        self.account_key: str | None = None
        self._ticker_uic: dict[str, int] = {}
        self._order_submission_cutoff: tuple[datetime, Callable[[], datetime]] | None = None

    @contextmanager
    def order_submission_window(self, cutoff: datetime, *, now: Callable[[], datetime]) -> Iterator[None]:
        if cutoff.tzinfo is None or cutoff.utcoffset() is None:
            raise ValueError("Saxo order cutoff must be timezone-aware")
        previous = self._order_submission_cutoff
        self._order_submission_cutoff = (cutoff, now)
        try:
            yield
        finally:
            self._order_submission_cutoff = previous

    def _prepare_order_post(self, headers: dict[str, str]) -> None:
        self.pacer.wait_for("orders")
        headers["x-request-id"] = str(uuid.uuid4())
        if self._order_submission_cutoff is not None:
            cutoff, now = self._order_submission_cutoff
            moment = now()
            if moment.tzinfo is None or moment.utcoffset() is None:
                raise ValueError("Saxo order clock must be timezone-aware")
            if moment >= cutoff:
                raise OrderSubmissionDeferred("market close reached before order submission")

    def request(self, method: str, path: str, *, params=None, json_body=None, order_post=False):
        if isinstance(self.tokens, DemoTokenManager):
            if not isinstance(method, str) or method.upper() != "GET" or order_post or path not in _DEMO_READ_ONLY_PATHS:
                raise SaxoAuthError("Saxo SIM 24-hour token client is read-only")
        url = f"{BASE_URL}{path}"
        inspection_tokens = self.tokens if isinstance(self.tokens, LeaseBackedDemoTokenManager) else None
        timeout = inspection_tokens.before_request(method, path) if inspection_tokens is not None else 15
        token = self.tokens.get_access_token()
        headers = {"Authorization": "Bearer " + token}
        if order_post:
            self._prepare_order_post(headers)
        request_failed = False
        try:
            request_options = {
                "headers": headers,
                "params": params,
                "json": json_body,
                "timeout": timeout,
            }
            if inspection_tokens is not None:
                request_options.update(
                    allow_redirects=False,
                    proxies={},
                    stream=True,
                    _disable_environment_proxies=True,
                )
            response = self.transport.request(
                method,
                url,
                **request_options,
            )
        except Exception:
            request_failed = True
        if request_failed:
            if order_post:
                raise SaxoOrderError("Saxo order POST outcome unknown; inspect SIM account") from None
            raise SaxoAuthError("Saxo SIM request failed") from None
        if inspection_tokens is not None:
            try:
                response_status = _response_status(response)
            except Exception:
                try:
                    _close_response(response)
                except Exception:
                    pass
                raise SaxoAuthError("Saxo SIM response status is invalid") from None
            if response_status in {401, 403}:
                inspection_tokens.mark_rejected()
                try:
                    _close_response(response)
                except Exception:
                    pass
                raise SaxoAuthError("Saxo SIM rejected the inspection credential")
        status, body = _response(
            response,
            max_body_bytes=_MAX_INSPECTION_BODY_BYTES if inspection_tokens is not None else None,
            deadline_check=inspection_tokens.check_response_progress if inspection_tokens is not None else None,
        )
        if 300 <= status < 400:
            raise SaxoAuthError("Saxo SIM request redirected; refusing to follow it")
        if status in {401, 403} and inspection_tokens is not None:
            inspection_tokens.mark_rejected()
            raise SaxoAuthError("Saxo SIM rejected the inspection credential")
        if status == 401:
            if isinstance(self.tokens, DemoTokenManager):
                self.tokens.mark_rejected()
                raise SaxoAuthError("Saxo SIM rejected the 24-hour token; refresh it in 1Password and retry")
            self.tokens.access_expires_at = 0
            token = self.tokens.get_access_token()
            headers["Authorization"] = "Bearer " + token
            if order_post:
                self._prepare_order_post(headers)
            retry_failed = False
            try:
                status, body = _response(self.transport.request(method, url, headers=headers, params=params, json=json_body, timeout=15))
            except Exception:
                retry_failed = True
            if retry_failed:
                if order_post:
                    raise SaxoOrderError("Saxo order POST outcome unknown; inspect SIM account") from None
                raise SaxoAuthError("Saxo SIM request failed after token refresh") from None
            if 300 <= status < 400:
                raise SaxoAuthError("Saxo SIM request redirected; refusing to follow it")
            if status == 401:
                raise SaxoAuthError("Saxo rejected refreshed authorization; run interactive Saxo login")
        return status, body

    def check_connection(self) -> None:
        status, user = self.request("GET", "/port/v1/users/me")
        client_key = user.get("ClientKey") if isinstance(user, dict) else None
        if status != 200 or not isinstance(client_key, str) or not client_key:
            raise SaxoAuthError("Saxo SIM connection check failed; verify the 24-hour token and SIM access")
        if isinstance(self.tokens, LeaseBackedDemoTokenManager) and (len(client_key) > 128 or not re.fullmatch(r"[A-Za-z0-9._-]+", client_key)):
            raise SaxoAuthError("Saxo SIM connection response is invalid")
        self.client_key = client_key

    def account_candidates(self) -> list[SaxoAccountCandidate]:
        if self.client_key is None:
            self.check_connection()
        if isinstance(self.tokens, LeaseBackedDemoTokenManager):
            data = self._inspection_collection_rows("/port/v1/accounts/me", {}, "accounts")
        else:
            status, accounts = self.request("GET", "/port/v1/accounts/me")
            data = accounts.get("Data", []) if isinstance(accounts, dict) else []
            if status != 200 or not isinstance(data, list):
                raise SaxoReconcileError("Saxo SIM account discovery failed")
        candidates = []
        account_keys = set()
        currencies = set()
        for row in data:
            if not isinstance(row, dict):
                raise SaxoReconcileError("Saxo SIM account response has an invalid row")
            account_key = row.get("AccountKey")
            currency = row.get("Currency")
            active = row.get("Active")
            legal_asset_types = row.get("LegalAssetTypes")
            if not isinstance(account_key, str) or not account_key or account_key.strip() != account_key:
                raise SaxoReconcileError("Saxo SIM account response has incomplete identity or eligibility data")
            if isinstance(self.tokens, LeaseBackedDemoTokenManager) and (len(account_key) > 128 or not re.fullmatch(r"[A-Za-z0-9._-]+", account_key)):
                raise SaxoReconcileError("Saxo SIM account response has invalid identity data")
            if not isinstance(currency, str) or not currency or currency.strip() != currency:
                raise SaxoReconcileError("Saxo SIM account response has incomplete identity or eligibility data")
            if isinstance(self.tokens, LeaseBackedDemoTokenManager) and not re.fullmatch(r"[A-Za-z]{3}", currency):
                raise SaxoReconcileError("Saxo SIM account response has invalid currency data")
            if not isinstance(active, bool) or not isinstance(legal_asset_types, list):
                raise SaxoReconcileError("Saxo SIM account response has incomplete identity or eligibility data")
            if isinstance(self.tokens, LeaseBackedDemoTokenManager) and len(legal_asset_types) > 50:
                raise SaxoReconcileError("Saxo SIM account response exceeds its type limit")
            if any(not isinstance(asset_type, str) for asset_type in legal_asset_types):
                raise SaxoReconcileError("Saxo SIM account response has incomplete identity or eligibility data")
            if account_key in account_keys:
                raise SaxoReconcileError("Saxo SIM account response contains a duplicate account identifier")
            account_keys.add(account_key)
            normalized_currency = currency.upper()
            currencies.add(normalized_currency)
            if active and normalized_currency == self.base_currency and "Stock" in legal_asset_types:
                candidates.append(SaxoAccountCandidate(account_key, normalized_currency))
        if not candidates:
            available = ", ".join(sorted(currencies)) or "none"
            raise SaxoReconcileError(f"no active Saxo SIM stock account matches fund currency {self.base_currency}; available: {available}")
        return candidates

    def inspect_accounts(self, account_key: str | None = None) -> list[SaxoAccountSummary]:
        candidates = self.account_candidates()
        if account_key is not None:
            if not isinstance(account_key, str) or not account_key or account_key.strip() != account_key:
                raise SaxoReconcileError("Saxo SIM account identifier is invalid")
            candidates = [candidate for candidate in candidates if candidate.account_key == account_key]
            if not candidates:
                raise SaxoReconcileError("Saxo SIM account identifier is not an eligible account")
        return [self._inspect_account(candidate) for candidate in candidates]

    def _inspect_account(self, candidate: SaxoAccountCandidate) -> SaxoAccountSummary:
        params = {"ClientKey": self.client_key, "AccountKey": candidate.account_key}
        status, balance = self.request("GET", "/port/v1/balances", params=params)
        if status != 200 or not isinstance(balance, dict):
            raise SaxoReconcileError("cannot read Saxo SIM account balance")
        currency = balance.get("Currency")
        if not isinstance(currency, str) or currency.upper() != candidate.currency:
            raise SaxoReconcileError("Saxo SIM account balance currency does not match the account")
        cash_balance = _finite_number(balance.get("CashBalance"), "accounting cash balance", SaxoReconcileError)
        positions = []
        skip = 0
        page_count = 0
        row_count = 0
        while True:
            position_params: dict[str, str | int | None] = {"ClientKey": self.client_key, "AccountKey": candidate.account_key}
            if isinstance(self.tokens, LeaseBackedDemoTokenManager):
                position_params["$top"] = _MAX_INSPECTION_PAGE_ROWS
            if skip:
                position_params["$skip"] = skip
            status, result = self.request("GET", "/port/v1/positions", params=position_params)
            if status != 200:
                raise SaxoReconcileError("cannot read Saxo SIM account positions")
            rows = result.get("Data") if isinstance(result, dict) else None
            if not isinstance(rows, list):
                raise SaxoReconcileError("Saxo SIM positions response has an invalid shape")
            if isinstance(self.tokens, LeaseBackedDemoTokenManager):
                self.tokens.record_page("positions", len(rows))
                page_count += 1
                row_count += len(rows)
                if page_count > _MAX_INSPECTION_PAGES or row_count > _MAX_INSPECTION_ROWS:
                    raise SaxoReconcileError("Saxo SIM positions exceed the inspection limit")
            for row in rows:
                base = row.get("PositionBase") if isinstance(row, dict) else None
                uic = base.get("Uic") if isinstance(base, dict) else None
                if isinstance(uic, bool) or not isinstance(uic, int) or uic <= 0:
                    raise SaxoReconcileError("Saxo SIM position response has an invalid instrument identifier")
                if not isinstance(base, dict):
                    raise SaxoReconcileError("Saxo SIM position response has an invalid position")
                amount = _finite_number(base.get("Amount"), "position amount", SaxoReconcileError)
                if amount:
                    positions.append(SaxoPositionSummary(uic=uic, amount=amount))
            next_skip = (
                _inspection_page_skip(
                    result.get("__next"),
                    path="/port/v1/positions",
                    current_skip=skip,
                    params=position_params,
                )
                if isinstance(self.tokens, LeaseBackedDemoTokenManager)
                else _next_page_skip(result.get("__next"), skip, SaxoReconcileError, "positions")
            )
            if next_skip is None:
                break
            skip = next_skip
        return SaxoAccountSummary(candidate.account_key, candidate.currency, cash_balance, tuple(positions))

    def _inspection_collection_rows(self, path: str, params: dict[str, str | int | None], collection: str) -> list:
        rows: list = []
        skip = 0
        while True:
            page_params = {**params, "$top": _MAX_INSPECTION_PAGE_ROWS}
            if skip:
                page_params["$skip"] = skip
            status, result = self.request("GET", path, params=page_params)
            if status != 200 or not isinstance(result, dict) or not isinstance(result.get("Data"), list):
                raise SaxoReconcileError("Saxo SIM account discovery failed")
            page = result["Data"]
            if len(page) > _MAX_INSPECTION_PAGE_ROWS:
                raise SaxoReconcileError("Saxo SIM account discovery exceeds the page limit")
            self.tokens.record_page(collection, len(page))
            rows.extend(page)
            if len(rows) > _MAX_INSPECTION_ROWS:
                raise SaxoReconcileError("Saxo SIM account discovery exceeds the collection limit")
            next_skip = _inspection_page_skip(
                result.get("__next"),
                path=path,
                current_skip=skip,
                params=page_params,
            )
            if next_skip is None:
                return rows
            skip = next_skip

    def discover_account(self, account_key: str | None = None) -> None:
        if account_key is not None and (not isinstance(account_key, str) or not account_key or account_key.strip() != account_key):
            raise SaxoReconcileError("explicit Saxo SIM account identifier is required")
        if account_key is None and getattr(self.tokens, "auth_mode", "oauth") == "demo-token":
            raise SaxoReconcileError("explicit Saxo SIM account identifier is required")
        candidates = self.account_candidates()
        if account_key is None:
            self.account_key = candidates[0].account_key
            return
        if not any(candidate.account_key == account_key for candidate in candidates):
            raise SaxoReconcileError("Saxo SIM account identifier is not an eligible account")
        self.account_key = account_key

    def positions(self) -> dict[str, Position]:
        self._require_account()
        totals: dict[str, float] = {}
        skip = 0
        while True:
            params: dict[str, str | int | None] = {"ClientKey": self.client_key, "AccountKey": self.account_key}
            if skip:
                params["$skip"] = skip
            status, result = self.request("GET", "/port/v1/positions", params=params)
            if status != 200:
                raise SaxoReconcileError("cannot read Saxo SIM positions")
            rows = result.get("Data") if isinstance(result, dict) else None
            if not isinstance(rows, list):
                raise SaxoReconcileError("Saxo positions response has an invalid shape")
            for row in rows:
                if not isinstance(row, dict):
                    raise SaxoReconcileError("Saxo position response has an invalid row")
                base = row.get("PositionBase", {})
                if not isinstance(base, dict):
                    raise SaxoReconcileError("Saxo position response has an invalid position")
                ticker = next((name for name, uic in self._ticker_uic.items() if uic == base.get("Uic")), None)
                if ticker is None or not row.get("NetPositionId"):
                    raise SaxoReconcileError("Saxo position cannot be mapped to a fund ticker")
                amount = _finite_number(base.get("Amount"), "position amount", SaxoReconcileError)
                totals[ticker] = totals.get(ticker, 0.0) + amount
            next_skip = _next_page_skip(result.get("__next"), skip, SaxoReconcileError, "positions")
            if next_skip is None:
                break
            skip = next_skip
        return {ticker: Position(ticker=ticker, shares=shares) for ticker, shares in totals.items() if shares != 0}

    def balances(self) -> dict:
        self._require_account()
        status, result = self.request(
            "GET",
            "/port/v1/balances",
            params={"ClientKey": self.client_key, "AccountKey": self.account_key},
        )
        if status != 200 or not isinstance(result, dict):
            raise SaxoReconcileError("cannot read Saxo SIM balances")
        currency = result.get("Currency")
        if not isinstance(currency, str) or currency.upper() != self.base_currency:
            raise SaxoReconcileError(f"Saxo balance currency {currency} does not match fund currency {self.base_currency}")
        _finite_number(result.get("CashBalance"), "accounting cash balance", SaxoReconcileError)
        return result

    def search_instrument(self, ticker: str) -> tuple[int, str]:
        status, result = self.request(
            "GET",
            "/ref/v1/instruments",
            params={"Keywords": ticker, "AssetTypes": "Stock"},
        )
        if status != 200:
            raise SaxoReconcileError(f"Saxo instrument search failed for {ticker}")
        rows = result.get("Data", []) if isinstance(result, dict) else []
        candidates = [row for row in rows if isinstance(row, dict) and str(row.get("Symbol", "")).split(":")[0].upper() == ticker.upper() and row.get("Identifier") is not None and str(row.get("ExchangeId", "")).upper() in _US_EXCHANGES]
        if not candidates:
            raise SaxoReconcileError(f"Saxo instrument not found for {ticker}")
        exchange_order = {exchange: index for index, exchange in enumerate(_US_EXCHANGES)}
        candidates.sort(
            key=lambda row: (
                0 if str(row.get("PrimaryListing", "")) == str(row["Identifier"]) else 1,
                exchange_order[str(row["ExchangeId"]).upper()],
                str(row["Identifier"]),
            )
        )
        try:
            uic = int(candidates[0]["Identifier"])
        except (TypeError, ValueError):
            raise SaxoReconcileError(f"Saxo instrument identifier is invalid for {ticker}") from None
        if uic <= 0:
            raise SaxoReconcileError(f"Saxo instrument identifier is invalid for {ticker}")
        return uic, "Stock"

    def instrument_details(self, uic: int, asset_type: str = "Stock") -> dict:
        status, details = self.request("GET", f"/ref/v1/instruments/details/{int(uic)}/{asset_type}")
        if status != 200 or not isinstance(details, dict):
            raise SaxoReconcileError(f"Saxo instrument details unavailable for UIC {uic}")
        return details

    def place_order(self, payload: dict) -> tuple[str | None, str | None]:
        status, body = self.request("POST", "/trade/v2/orders", json_body=payload, order_post=True)
        code = _error_code(body)
        if code:
            if status == 409:
                order_id = body.get("OrderId") if isinstance(body, dict) else None
                if order_id:
                    return str(order_id), None
                raise SaxoOrderError(f"Saxo order state unknown after conflict ({code}); inspect SIM account", code)
            raise SaxoOrderError(f"Saxo rejected order ({code})", code)
        if status < 200 or status >= 300 or not isinstance(body, dict) or not body.get("OrderId"):
            raise SaxoOrderError("Saxo order response did not confirm an OrderId")
        return str(body["OrderId"]), None

    def wait_for_order(self, order_id: str, *, deadline: float | None = None) -> None:
        self._require_account()
        deadline = deadline if deadline is not None else self.clock.monotonic() + self.execution_timeout_s
        while self.clock.monotonic() < deadline:
            status, body = self.request("GET", f"/port/v1/orders/{self.client_key}/{order_id}")
            if status in (404, 410) or (status == 200 and isinstance(body, dict) and (body.get("IsOpen") is False or body == {} or body.get("Data") == [])):
                return
            self.clock.sleep(min(self.poll_interval_s, max(0.0, deadline - self.clock.monotonic())))
        raise SaxoOrderError(f"Saxo order {order_id} did not complete before deadline; inspect SIM account")

    def order_fill(
        self,
        order_id: str,
        requested_quantity: float,
        *,
        uic: int,
        deadline: float | None = None,
    ) -> tuple[float, float]:
        self._require_account()
        if not isinstance(order_id, str) or not order_id:
            raise SaxoOrderError("Saxo order identifier is invalid")
        if isinstance(requested_quantity, bool) or not isinstance(requested_quantity, (int, float)) or not math.isfinite(requested_quantity) or requested_quantity <= 0:
            raise SaxoOrderError(f"Saxo requested quantity is invalid for order {order_id}")
        if isinstance(uic, bool) or not isinstance(uic, int) or uic <= 0:
            raise SaxoOrderError(f"Saxo instrument identifier is invalid for order {order_id}")
        deadline = deadline if deadline is not None else self.clock.monotonic() + self.execution_timeout_s
        observed_quantity = 0.0
        moment = self.clock.utcnow().date()
        base_params = {
            "AccountKeys": self.account_key,
            "ClientKey": self.client_key,
            "FromDate": (moment - timedelta(days=1)).isoformat(),
            "ToDate": moment.isoformat(),
            "TransactionType": "Trade",
            "Uics": str(uic),
            "$top": 100,
        }
        while self.clock.monotonic() < deadline:
            quantity = 0.0
            notional = 0.0
            skip = 0
            while True:
                if self.clock.monotonic() >= deadline:
                    break
                status, result = self.request(
                    "GET",
                    "/hist/v1/transactions",
                    params={**base_params, "$skip": skip},
                )
                if status != 200:
                    raise SaxoOrderError(f"Saxo execution lookup failed for order {order_id}")
                if not isinstance(result, dict):
                    raise SaxoOrderError(f"Saxo execution response has invalid shape for order {order_id}")
                rows = result.get("Data")
                if not isinstance(rows, list):
                    raise SaxoOrderError(f"Saxo execution response has invalid shape for order {order_id}")
                for transaction in rows:
                    if not isinstance(transaction, dict):
                        raise SaxoOrderError(f"Saxo execution response has invalid row for order {order_id}")
                    trades = transaction.get("Trades", [])
                    if not isinstance(trades, list):
                        raise SaxoOrderError(f"Saxo execution response has invalid trades for order {order_id}")
                    for trade in trades:
                        if not isinstance(trade, dict) or str(trade.get("OrderId", "")) != order_id:
                            continue
                        if trade.get("TradedQuantity") is None or trade.get("Price") is None:
                            raise SaxoOrderError(f"Saxo execution record is incomplete for order {order_id}")
                        amount = abs(_finite_number(trade["TradedQuantity"], "execution quantity", SaxoOrderError))
                        price = _finite_number(trade["Price"], "execution price", SaxoOrderError)
                        if amount <= 0 or price <= 0:
                            raise SaxoOrderError(f"Saxo execution record is invalid for order {order_id}")
                        quantity += amount
                        notional += amount * price
                observed_quantity = quantity
                if abs(quantity - requested_quantity) <= max(1e-8, requested_quantity * 1e-8):
                    return quantity, notional / quantity
                if quantity > requested_quantity:
                    raise SaxoOrderError(f"Saxo execution exceeds requested quantity for order {order_id}")
                next_skip = _next_page_skip(result.get("__next"), skip, SaxoOrderError, f"execution for order {order_id}")
                if next_skip is None:
                    break
                skip = next_skip
            self.clock.sleep(min(self.poll_interval_s, max(0.0, deadline - self.clock.monotonic())))
        if observed_quantity:
            raise SaxoOrderError(f"Saxo order {order_id} only partially filled; inspect SIM account")
        raise SaxoOrderError(f"Saxo execution record missing for order {order_id}; inspect SIM account")

    def _require_account(self) -> None:
        if self.account_key is None or self.client_key is None:
            raise SaxoReconcileError("Saxo account discovery has not completed")


class SaxoBroker:
    def __init__(self, client: SaxoClient, universe: list[str], *, cache_ttl_s: float = 3600):
        if not isinstance(universe, list) or not universe or any(not isinstance(ticker, str) or not ticker.strip() for ticker in universe) or not math.isfinite(cache_ttl_s) or cache_ttl_s <= 0:
            raise ValueError("Saxo broker requires a non-empty universe and positive cache TTL")
        self.client = client
        self.universe = [ticker.strip().upper() for ticker in universe]
        self.cache_ttl_s = cache_ttl_s
        self._cache: dict[str, tuple[float, int, str, dict]] = {}
        if self.client.account_key is None:
            raise SaxoReconcileError("Saxo broker requires an explicitly selected account identifier")

    def __repr__(self) -> str:
        return f"SaxoBroker(universe={self.universe!r}, credentials=[redacted])"

    def validate_universe(self) -> None:
        now = self.client.clock.monotonic()
        for ticker in self.universe:
            cached = self._cache.get(ticker)
            if cached is None or now - cached[0] >= self.cache_ttl_s:
                uic, asset_type = self.client.search_instrument(ticker)
                details = self.client.instrument_details(uic, asset_type)
                if details.get("IsTradable") is not True:
                    raise SaxoReconcileError(f"Saxo instrument is not tradable: {ticker}")
                exchange = details.get("Exchange")
                currency = details.get("CurrencyCode")
                if not isinstance(exchange, dict) or exchange.get("CountryCode") != "US" or not isinstance(currency, str) or currency.upper() != self.client.base_currency:
                    raise SaxoReconcileError(f"Saxo instrument is not a US listing in {self.client.base_currency}: {ticker}")
                supported = details.get("SupportedOrderTypes", details.get("SupportedOrderTypeSettings", []))
                if isinstance(supported, dict):
                    supported = supported.get("SupportedOrderTypes", [])
                if not isinstance(supported, list) or not any(item == "Market" or (isinstance(item, dict) and item.get("OrderType") == "Market") for item in supported):
                    raise SaxoReconcileError(f"Saxo instrument does not support market orders: {ticker}")
                self._cache[ticker] = (now, uic, asset_type, details)
                self.client._ticker_uic[ticker] = uic

    def positions(self) -> dict[str, Position]:
        self.validate_universe()
        return self.client.positions()

    def filter_orders(self, orders: list[Order]) -> list[Order]:
        if not isinstance(orders, list) or any(not isinstance(order, Order) for order in orders):
            raise TypeError("SaxoBroker.filter_orders requires a list of Orders")
        self.validate_universe()
        filtered = []
        for order in orders:
            cached = self._cache.get(order.ticker.upper())
            if cached is None:
                raise SaxoReconcileError(f"{order.ticker.upper()} is outside the deployed Saxo universe")
            lot_size = _instrument_lot_size(cached[3])
            quantity = _tradable_quantity(order.quantity, lot_size)
            if quantity > 0:
                filtered.append(order.model_copy(update={"quantity": quantity}))
        return filtered

    def cash(self) -> float:
        return _finite_number(self.client.balances().get("CashBalance"), "accounting cash balance", SaxoReconcileError)

    def order_submission_window(self, cutoff: datetime, *, now: Callable[[], datetime]) -> AbstractContextManager[None]:
        return self.client.order_submission_window(cutoff, now=now)

    def _buying_power(self) -> float:
        return _finite_number(self.client.balances().get("CashAvailableForTrading"), "available trading cash", SaxoOrderError)

    def place_order(self, order: Order) -> Fill:
        if not isinstance(order, Order):
            raise TypeError("SaxoBroker.place_order requires an Order")
        if not math.isfinite(order.price) or order.price <= 0:
            raise SaxoOrderError("Saxo order reference price must be finite and positive")
        self.validate_universe()
        ticker = order.ticker.upper()
        if ticker not in self._cache:
            raise SaxoReconcileError(f"{ticker} is outside the deployed Saxo universe")
        _, uic, asset_type, details = self._cache[ticker]
        lot_size = _instrument_lot_size(details)
        quantity = _tradable_quantity(order.quantity, lot_size)
        if quantity <= 0:
            raise SaxoOrderError(f"{ticker}: quantity is below the instrument lot size")
        if order.side == "buy" and quantity * order.price > self._buying_power():
            raise SaxoOrderError("Saxo buying power is insufficient", "InsufficientCash")
        if self.client.account_key is None:
            raise SaxoReconcileError("Saxo account discovery has not completed")
        payload = {
            "AccountKey": self.client.account_key,
            "Uic": uic,
            "AssetType": asset_type,
            "Amount": quantity,
            "BuySell": "Buy" if order.side == "buy" else "Sell",
            "OrderType": "Market",
            "OrderDuration": {"DurationType": "DayOrder"},
            "ManualOrder": False,
        }
        order_id, _ = self.client.place_order(payload)
        deadline = self.client.clock.monotonic() + self.client.execution_timeout_s
        self.client.wait_for_order(order_id, deadline=deadline)
        filled_quantity, price = self.client.order_fill(order_id, quantity, uic=uic, deadline=deadline)
        return Fill(ticker=ticker, side=order.side, quantity=filled_quantity, price=price)


def _tradable_quantity(quantity: float, lot_size) -> float:
    try:
        amount = Decimal(str(quantity))
        lot = Decimal(str(lot_size))
        if amount <= 0 or lot <= 0:
            raise ValueError
        units = (amount / lot).to_integral_value(rounding=ROUND_DOWN)
        return float(units * lot)
    except Exception:
        raise SaxoOrderError("Saxo instrument reported invalid quantity precision") from None


def _instrument_lot_size(details: dict) -> float:
    lot_size = details.get("LotSize")
    return 1 if lot_size is None else lot_size


def _finite_number(value, label: str, error_type) -> float:
    if isinstance(value, bool):
        raise error_type(f"Saxo {label} is invalid")
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise error_type(f"Saxo {label} is invalid") from None
    if not math.isfinite(number):
        raise error_type(f"Saxo {label} is invalid")
    return number


def _next_page_skip(link: object, skip: int, error_type: type[Exception], context: str) -> int | None:
    if link is None:
        return None
    if not isinstance(link, str) or not link:
        raise error_type(f"Saxo {context} pagination is invalid")
    values = parse_qs(urlparse(link).query, keep_blank_values=True).get("$skip", [])
    try:
        next_skip = int(values[0]) if len(values) == 1 else skip
    except ValueError:
        raise error_type(f"Saxo {context} pagination is invalid") from None
    if next_skip <= skip:
        raise error_type(f"Saxo {context} pagination did not advance")
    return next_skip


def _inspection_page_skip(
    link: object,
    *,
    path: str,
    current_skip: int,
    params: dict[str, str | int | None],
) -> int | None:
    if link is None:
        return None
    if not isinstance(link, str) or not link or len(link) > 4096:
        raise SaxoReconcileError("Saxo SIM pagination is invalid")
    parsed = urlparse(link)
    if parsed.scheme or parsed.netloc:
        if parsed.scheme != "https" or parsed.hostname != "gateway.saxobank.com" or parsed.port not in (None, 443) or parsed.username is not None or parsed.password is not None or parsed.path not in {path, f"/sim/openapi{path}"}:
            raise SaxoReconcileError("Saxo SIM pagination origin is invalid")
    elif parsed.path not in {path, f"/sim/openapi{path}"} or link.startswith("//"):
        raise SaxoReconcileError("Saxo SIM pagination path is invalid")
    if parsed.fragment:
        raise SaxoReconcileError("Saxo SIM pagination is invalid")
    try:
        query = parse_qs(parsed.query, keep_blank_values=True, strict_parsing=True)
    except ValueError:
        raise SaxoReconcileError("Saxo SIM pagination is invalid") from None
    expected_params = {key: value for key, value in params.items() if key != "$skip" and value is not None}
    if any(len(values) != 1 for values in query.values()) or set(query) != set(expected_params) | {"$skip"}:
        raise SaxoReconcileError("Saxo SIM pagination parameters are invalid")
    for key, value in expected_params.items():
        if query.get(key) != [str(value)]:
            raise SaxoReconcileError("Saxo SIM pagination parameters changed")
    try:
        skip_value = query["$skip"][0]
        if not re.fullmatch(r"(?:0|[1-9][0-9]*)", skip_value):
            raise ValueError
        next_skip = int(skip_value)
    except (KeyError, ValueError):
        raise SaxoReconcileError("Saxo SIM pagination is invalid") from None
    if next_skip <= current_skip or next_skip > _MAX_INSPECTION_ROWS:
        raise SaxoReconcileError("Saxo SIM pagination did not advance within its bound")
    return next_skip


def _error_code(body) -> str | None:
    if not isinstance(body, dict):
        return None
    info = body.get("ErrorInfo")
    if isinstance(info, dict):
        return str(info.get("ErrorCode") or info.get("Message") or "ErrorInfo")
    return None


def _response(
    response,
    *,
    max_body_bytes: int | None = None,
    deadline_check: Callable[[], float] | None = None,
) -> tuple[int, object]:
    if isinstance(response, tuple) and len(response) == 2:
        if deadline_check is not None:
            deadline_check()
        if max_body_bytes is not None:
            try:
                body_size = len(json.dumps(response[1], separators=(",", ":"), ensure_ascii=False).encode("utf-8"))
            except (TypeError, ValueError, UnicodeEncodeError):
                raise SaxoReconcileError("Saxo SIM response could not be bounded") from None
            if body_size > max_body_bytes:
                raise SaxoReconcileError("Saxo SIM response exceeds the inspection size limit")
        if deadline_check is not None:
            deadline_check()
        return int(response[0]), response[1]
    status = int(getattr(response, "status_code", 0))
    if max_body_bytes is not None:
        try:
            content = _bounded_response_content(response, max_body_bytes, deadline_check)
            body = json.loads(content.decode("utf-8")) if content else {}
            if deadline_check is not None:
                deadline_check()
        except (SaxoAuthError, SaxoReconcileError):
            raise
        except Exception:
            body = {}
        finally:
            _close_response(response)
        return status, body
    try:
        body = response.json()
    except Exception:
        body = {}
    return status, body


def _response_status(response) -> int:
    if isinstance(response, tuple) and len(response) == 2:
        return int(response[0])
    return int(getattr(response, "status_code", 0))


def _close_response(response) -> None:
    close = getattr(response, "close", None)
    try:
        if callable(close):
            close()
    finally:
        session = getattr(response, "_aihf_session", None)
        if session is not None:
            session.close()


def _bounded_response_content(
    response,
    max_body_bytes: int,
    deadline_check: Callable[[], float] | None = None,
) -> bytes:
    iterator = getattr(response, "iter_content", None)
    if callable(iterator):
        chunks = []
        size = 0
        for chunk in iterator(chunk_size=64 * 1024):
            if deadline_check is not None:
                deadline_check()
            if not chunk:
                continue
            if not isinstance(chunk, bytes):
                raise SaxoReconcileError("Saxo SIM response could not be bounded")
            size += len(chunk)
            if size > max_body_bytes:
                raise SaxoReconcileError("Saxo SIM response exceeds the inspection size limit")
            chunks.append(chunk)
        if deadline_check is not None:
            deadline_check()
        return b"".join(chunks)
    content = getattr(response, "content", None)
    if deadline_check is not None:
        deadline_check()
    if not isinstance(content, bytes):
        raise SaxoReconcileError("Saxo SIM response could not be bounded")
    if len(content) > max_body_bytes:
        raise SaxoReconcileError("Saxo SIM response exceeds the inspection size limit")
    return content


@contextmanager
def _refresh_lock(reference: str, lock_dir: str | Path | None = None, *, timeout_s: float = 90.0):
    if not math.isfinite(timeout_s) or timeout_s <= 0:
        raise ValueError("refresh lock timeout must be positive")
    key = hashlib.sha256(reference.encode("utf-8")).hexdigest()
    with _THREAD_REFRESH_LOCKS_GUARD:
        thread_lock = _THREAD_REFRESH_LOCKS.setdefault(key, threading.Lock())
    deadline = time.monotonic() + timeout_s
    thread_acquired = thread_lock.acquire(timeout=timeout_s)
    if not thread_acquired:
        raise _RefreshLockTimeout(f"Saxo refresh lock contention timed out after {timeout_s:g}s; owner=another thread in this process; retry")
    try:
        configured = lock_dir or os.environ.get("SAXO_REFRESH_LOCK_DIR")
        directory = Path(configured) if configured else Path(tempfile.gettempdir()) / "hedge-fund-saxo-locks"
        from hedge_fund.paths import _enrolled_root_ancestor

        if _enrolled_root_ancestor(directory / "probe") is not None:
            raise ValueError("Saxo refresh lock directory must be outside an enrolled engine root")
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{key}.lockdir"
        acquired = False
        try:
            while not acquired:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise _RefreshLockTimeout(f"Saxo refresh lock contention timed out after {timeout_s:g}s; owner={_refresh_lock_owner(path)}; retry") from None
                try:
                    path.mkdir()
                    acquired = True
                except FileExistsError:
                    time.sleep(min(0.05, remaining))
            (path / "owner").write_text(f"{socket.gethostname()}:{os.getpid()}", encoding="utf-8")
            yield
        finally:
            if acquired:
                owner = _refresh_lock_owner(path)
                try:
                    (path / "owner").unlink(missing_ok=True)
                    path.rmdir()
                except OSError as exc:
                    _LOG.error(
                        "Saxo refresh lock cleanup failed; lock=%s owner=%s error=%s; verify holder is inactive before removal",
                        path,
                        owner,
                        type(exc).__name__,
                    )
    finally:
        thread_lock.release()


class _RefreshLockTimeout(SaxoAuthError):
    """Refresh lock stayed held; owner context supports safe manual recovery."""


def _refresh_lock_owner(path: Path) -> str:
    try:
        value = (path / "owner").read_text(encoding="utf-8").strip()
    except OSError:
        return "unknown (owner file unavailable)"
    host, separator, pid = value.rpartition(":")
    if separator and re.fullmatch(r"[A-Za-z0-9._-]{1,128}", host) and pid.isdigit():
        return f"{host}:{pid}"
    return "unknown (owner file invalid)"
