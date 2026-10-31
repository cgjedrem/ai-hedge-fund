"""Provider classification and bounded dispatch authorization."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from ipaddress import ip_address
from threading import Lock
from urllib.parse import urlsplit, urlunsplit


class AuthorizationDenied(RuntimeError):
    """Provider action lacks matching authority."""


class BudgetDenied(AuthorizationDenied):
    """Call, cost or resource bound would be exceeded."""


class ProviderClass(str, Enum):
    FREE_DATA = "free-data"
    LOCAL = "local"
    PAID_CLOUD = "paid-cloud"


class OperationScope(str, Enum):
    MANUAL_ONE_SHOT = "manual-one-shot"
    SCHEDULED = "scheduled"


@dataclass(frozen=True, slots=True)
class ProviderTarget:
    kind: str
    provider: str
    model: str | None = None
    endpoint: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.kind, str) or self.kind.casefold() not in {"data", "llm"}:
            raise ValueError("provider kind is invalid")
        if not isinstance(self.provider, str) or not _SAFE_NAME.fullmatch(self.provider):
            raise ValueError("provider name is invalid")
        if self.model is not None and (not isinstance(self.model, str) or not _safe_text(self.model, maximum=256)):
            raise ValueError("model name is invalid")
        if self.endpoint is not None:
            object.__setattr__(self, "endpoint", _normalize_endpoint(self.endpoint))
        object.__setattr__(self, "kind", self.kind.casefold())
        object.__setattr__(self, "provider", self.provider.casefold())

    @property
    def identity(self) -> str:
        payload = {
            "kind": self.kind,
            "provider": self.provider,
            "model": self.model,
            "endpoint": self.endpoint,
        }
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class BudgetReservation:
    call_number: int
    cost: Decimal
    resources: int


@dataclass(slots=True)
class _BudgetState:
    calls_reserved: int = 0
    cost_reserved: Decimal = Decimal("0")
    resources_reserved: int = 0
    lock: Lock = field(default_factory=Lock, repr=False)


@dataclass(frozen=True, slots=True)
class DispatchBudget:
    max_calls: int
    max_cost: Decimal
    max_resources: int
    _state: _BudgetState = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        if type(self.max_calls) is not int or self.max_calls <= 0 or type(self.max_resources) is not int or self.max_resources <= 0 or not isinstance(self.max_cost, Decimal) or not self.max_cost.is_finite() or self.max_cost < 0:
            raise ValueError("dispatch budget bounds are invalid")
        object.__setattr__(self, "_state", _BudgetState())

    @property
    def calls_reserved(self) -> int:
        return self._state.calls_reserved

    @property
    def cost_reserved(self) -> Decimal:
        return self._state.cost_reserved

    @property
    def resources_reserved(self) -> int:
        return self._state.resources_reserved

    def reserve(
        self,
        *,
        upper_bound_cost: Decimal | None,
        resource_units: int = 1,
    ) -> BudgetReservation:
        cost = _validate_cost(upper_bound_cost)
        if type(resource_units) is not int or resource_units <= 0:
            raise BudgetDenied("resource bound is invalid")
        state = self._state
        with state.lock:
            next_calls = state.calls_reserved + 1
            next_cost = state.cost_reserved + cost
            next_resources = state.resources_reserved + resource_units
            if next_calls > self.max_calls or next_cost > self.max_cost or next_resources > self.max_resources:
                raise BudgetDenied("dispatch bound would be exceeded")
            state.calls_reserved = next_calls
            state.cost_reserved = next_cost
            state.resources_reserved = next_resources
            return BudgetReservation(next_calls, cost, resource_units)


@dataclass(frozen=True, slots=True)
class OneShotAuthorization:
    root_id: str
    subject_id: str
    capture_digest: str
    provider_id: str
    expires_at: datetime
    max_calls: int
    max_cost: Decimal
    max_resources: int = 10000
    _budget: DispatchBudget = field(init=False, repr=False)

    def __post_init__(self) -> None:
        _validate_identity(self.root_id)
        _validate_identity(self.subject_id)
        _validate_identity(self.capture_digest)
        _validate_identity(self.provider_id)
        _validate_expiry_value(self.expires_at)
        if type(self.max_calls) is not int or self.max_calls <= 0:
            raise ValueError("one-shot bounds are invalid")
        if type(self.max_resources) is not int or self.max_resources <= 0:
            raise ValueError("one-shot bounds are invalid")
        if not isinstance(self.max_cost, Decimal) or not self.max_cost.is_finite() or self.max_cost <= 0:
            raise ValueError("one-shot bounds are invalid")
        object.__setattr__(
            self,
            "_budget",
            DispatchBudget(
                max_calls=self.max_calls,
                max_cost=self.max_cost,
                max_resources=self.max_resources,
            ),
        )

    @property
    def calls_reserved(self) -> int:
        return self._budget.calls_reserved

    @property
    def cost_reserved(self) -> Decimal:
        return self._budget.cost_reserved

    @property
    def resources_reserved(self) -> int:
        return self._budget.resources_reserved


@dataclass(slots=True)
class _RunnerState:
    budget: DispatchBudget
    sessions_started: int = 0
    session_lock: Lock = field(default_factory=Lock, repr=False)


@dataclass(frozen=True, slots=True)
class RunnerAuthorization:
    root_id: str
    deployment_id: str
    capture_digest: str
    provider_ids: tuple[str, ...]
    expires_at: datetime
    max_sessions: int
    max_calls: int
    max_resources: int
    initial_due_set: tuple[str, ...] = ()
    _state: _RunnerState = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        _validate_identity(self.root_id)
        _validate_identity(self.deployment_id)
        _validate_identity(self.capture_digest)
        _validate_expiry_value(self.expires_at)
        if not isinstance(self.provider_ids, tuple) or not self.provider_ids or any(not isinstance(value, str) or not value for value in self.provider_ids) or len(set(self.provider_ids)) != len(self.provider_ids):
            raise ValueError("runner providers are invalid")
        if not isinstance(self.initial_due_set, tuple) or not self.initial_due_set or any(not isinstance(value, str) or not _safe_text(value, maximum=256) for value in self.initial_due_set) or len(set(self.initial_due_set)) != len(self.initial_due_set):
            raise ValueError("runner due-set is invalid")
        if type(self.max_sessions) is not int or self.max_sessions <= 0 or type(self.max_calls) is not int or self.max_calls <= 0 or type(self.max_resources) is not int or self.max_resources <= 0:
            raise ValueError("runner bounds are invalid")
        object.__setattr__(
            self,
            "_state",
            _RunnerState(
                budget=DispatchBudget(
                    max_calls=self.max_calls,
                    max_cost=Decimal("0"),
                    max_resources=self.max_resources,
                )
            ),
        )

    @property
    def sessions_started(self) -> int:
        return self._state.sessions_started

    @property
    def calls_reserved(self) -> int:
        return self._state.budget.calls_reserved

    @property
    def resources_reserved(self) -> int:
        return self._state.budget.resources_reserved


def classify_provider(
    target: ProviderTarget,
    *,
    approved_local_models: set[str] | frozenset[str] = frozenset(),
) -> ProviderClass:
    """Classify provider from identity and literal endpoint, never key absence."""
    if not isinstance(target, ProviderTarget):
        raise AuthorizationDenied("provider target is invalid")
    if not isinstance(approved_local_models, (set, frozenset)) or any(not isinstance(model, str) or not _safe_text(model, maximum=256) for model in approved_local_models):
        raise AuthorizationDenied("local model allowlist is invalid")
    if target.kind == "data":
        if target.provider in {"yfinance", "yf", "yahoo"}:
            return ProviderClass.FREE_DATA
        if target.provider in {"fd", "financialdatasets", "financial-datasets"}:
            return ProviderClass.PAID_CLOUD
        raise AuthorizationDenied("data provider is unknown")
    if target.kind != "llm":
        raise AuthorizationDenied("provider kind is unknown")
    if target.provider == "ollama":
        if target.model in approved_local_models and not _cloud_labelled(target.model or "") and _literal_local_ollama_endpoint(target.endpoint):
            return ProviderClass.LOCAL
        return ProviderClass.PAID_CLOUD
    if target.provider in {
        "anthropic",
        "deepseek",
        "google",
        "kimi",
        "openai",
        "typesafe",
        "xai",
    }:
        return ProviderClass.PAID_CLOUD
    raise AuthorizationDenied("LLM provider is unknown")


def authorize_session(
    authorization: RunnerAuthorization,
    *,
    root_id: str,
    deployment_id: str,
    capture_digest: str,
    due_set: tuple[str, ...],
    now: datetime,
) -> int:
    """Reserve finite sessions; first due-set must match reviewed identity."""
    if not isinstance(authorization, RunnerAuthorization):
        raise AuthorizationDenied("runner authorization is required")
    _validate_runner_identity(
        authorization,
        root_id=root_id,
        deployment_id=deployment_id,
        capture_digest=capture_digest,
        now=now,
    )
    if not isinstance(due_set, tuple) or not due_set or any(not isinstance(value, str) or not _safe_text(value, maximum=256) for value in due_set) or len(set(due_set)) != len(due_set):
        raise AuthorizationDenied("runner due-set is invalid")
    state = authorization._state
    with state.session_lock:
        next_session = authorization.sessions_started + 1
        if next_session == 1 and due_set != authorization.initial_due_set:
            raise AuthorizationDenied("reviewed due-set changed")
        if next_session > authorization.max_sessions:
            raise AuthorizationDenied("runner session bound exhausted")
        state.sessions_started = next_session
        return next_session


def authorize_dispatch(
    target: ProviderTarget,
    *,
    scope: OperationScope,
    root_id: str,
    subject_id: str,
    capture_digest: str,
    now: datetime,
    one_shot: OneShotAuthorization | None = None,
    runner: RunnerAuthorization | None = None,
    upper_bound_cost: Decimal | None = None,
    resource_units: int = 1,
    network_authorized: bool = False,
    attempt: int = 1,
    approved_local_models: set[str] | frozenset[str] = frozenset(),
) -> ProviderClass:
    """Reserve finite authority before any provider dispatch."""
    if not isinstance(scope, OperationScope):
        raise AuthorizationDenied("operation scope is invalid")
    _validate_identity(root_id)
    _validate_identity(subject_id)
    _validate_identity(capture_digest)
    _validate_now(now)
    if type(network_authorized) is not bool:
        raise AuthorizationDenied("network authorization is invalid")
    if type(attempt) is not int or attempt <= 0:
        raise AuthorizationDenied("attempt number is invalid")
    provider_class = classify_provider(
        target,
        approved_local_models=approved_local_models,
    )
    if scope is OperationScope.MANUAL_ONE_SHOT:
        if runner is not None:
            raise AuthorizationDenied("runner authority cannot authorize manual work")
        if provider_class is ProviderClass.PAID_CLOUD:
            if not network_authorized or not isinstance(one_shot, OneShotAuthorization):
                raise AuthorizationDenied("paid provider requires one-shot authorization")
            _validate_one_shot_identity(
                one_shot,
                target=target,
                root_id=root_id,
                subject_id=subject_id,
                capture_digest=capture_digest,
                now=now,
            )
            if attempt != 1:
                raise AuthorizationDenied("paid retries are disabled")
            one_shot._budget.reserve(
                upper_bound_cost=upper_bound_cost,
                resource_units=resource_units,
            )
            return provider_class
        if provider_class is ProviderClass.FREE_DATA and not network_authorized:
            raise AuthorizationDenied("network authorization is required")
        return provider_class

    if one_shot is not None or not isinstance(runner, RunnerAuthorization):
        raise AuthorizationDenied("finite runner authorization is required")
    if provider_class is ProviderClass.PAID_CLOUD:
        raise AuthorizationDenied("scheduled paid providers are prohibited")
    _validate_runner_identity(
        runner,
        root_id=root_id,
        deployment_id=subject_id,
        capture_digest=capture_digest,
        now=now,
    )
    if runner.sessions_started <= 0 or target.identity not in runner.provider_ids:
        raise AuthorizationDenied("runner provider is not authorized")
    runner._state.budget.reserve(
        upper_bound_cost=Decimal("0"),
        resource_units=resource_units,
    )
    return provider_class


_SAFE_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")


def _validate_cost(value: Decimal | None) -> Decimal:
    if value is None:
        raise BudgetDenied("paid upper-bound cost is unknown")
    if not isinstance(value, Decimal) or not value.is_finite() or value < 0:
        raise BudgetDenied("upper-bound cost is invalid")
    return value


def _validate_identity(value: str) -> None:
    if not isinstance(value, str) or not _safe_text(value, maximum=512):
        raise AuthorizationDenied("authorization identity is invalid")


def _validate_expiry_value(value: datetime) -> None:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("authorization expiry must be timezone-aware")


def _validate_now(value: datetime) -> None:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise AuthorizationDenied("authorization clock must be timezone-aware")


def _validate_one_shot_identity(
    authorization: OneShotAuthorization,
    *,
    target: ProviderTarget,
    root_id: str,
    subject_id: str,
    capture_digest: str,
    now: datetime,
) -> None:
    if authorization.root_id != root_id or authorization.subject_id != subject_id or authorization.capture_digest != capture_digest or authorization.provider_id != target.identity or authorization.expires_at <= now:
        raise AuthorizationDenied("one-shot authorization does not match")


def _validate_runner_identity(
    authorization: RunnerAuthorization,
    *,
    root_id: str,
    deployment_id: str,
    capture_digest: str,
    now: datetime,
) -> None:
    if authorization.root_id != root_id or authorization.deployment_id != deployment_id or authorization.capture_digest != capture_digest or authorization.expires_at <= now:
        raise AuthorizationDenied("runner authorization does not match")


def _normalize_endpoint(value: str) -> str:
    if not isinstance(value, str) or not _safe_text(value, maximum=2048):
        raise ValueError("provider endpoint is invalid")
    try:
        parts = urlsplit(value)
        port = parts.port
    except ValueError:
        raise ValueError("provider endpoint is invalid") from None
    if parts.scheme.casefold() not in {"http", "https"} or not parts.hostname or parts.username is not None or parts.password is not None or parts.query or parts.fragment or (port is not None and not 1 <= port <= 65535):
        raise ValueError("provider endpoint is invalid")
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path, "", ""))


def _literal_local_ollama_endpoint(endpoint: str | None) -> bool:
    if endpoint is None:
        return False
    try:
        parts = urlsplit(endpoint)
        port = parts.port
        address = ip_address(parts.hostname or "")
    except ValueError:
        return False
    return parts.scheme == "http" and address.is_loopback and port == 11434 and parts.username is None and parts.password is None and not parts.query and not parts.fragment


def _cloud_labelled(model: str) -> bool:
    labels = set(re.split(r"[/:\s_-]+", model.casefold()))
    return bool(labels.intersection({"cloud", "hosted", "remote"}))


def _safe_text(value: str, *, maximum: int) -> bool:
    return bool(value) and len(value) <= maximum and value == value.strip() and not any(ord(char) < 32 or ord(char) == 127 for char in value)
