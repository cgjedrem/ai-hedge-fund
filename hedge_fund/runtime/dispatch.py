"""Operation-bound authorization at provider transport boundaries."""

from __future__ import annotations

import contextvars
from collections.abc import Callable, Mapping, Sequence
from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal
from types import MappingProxyType
from typing import Iterator

import httpcore
import httpx
from httpcore._backends.sync import SyncBackend

from hedge_fund.runtime.costs import request_cost_upper_bound
from hedge_fund.runtime.endpoints import (
    PinnedAddress,
    resolve_destination,
    validate_provider_target,
    validate_request_url,
)
from hedge_fund.runtime.policy import (
    AuthorizationDenied,
    authorize_dispatch,
    BudgetDenied,
    classify_provider,
    DispatchBudget,
    OneShotAuthorization,
    OperationScope,
    ProviderTarget,
    RunnerAuthorization,
)


class ProviderDispatch:
    """Reserve each HTTP attempt against frozen operation authority."""

    __slots__ = (
        "scope",
        "root_id",
        "subject_id",
        "capture_digest",
        "operation_id",
        "operation_digest",
        "network_authorized",
        "approved_local_models",
        "_clock",
        "_boundary_check",
        "_resolver",
        "_targets",
        "_one_shot",
        "_runner",
        "_attempts",
        "_sealed",
    )

    def __setattr__(self, name, value) -> None:
        if getattr(self, "_sealed", False):
            raise AttributeError("provider dispatch authority is immutable")
        object.__setattr__(self, name, value)

    def __delattr__(self, name) -> None:
        if getattr(self, "_sealed", False):
            raise AttributeError("provider dispatch authority is immutable")
        object.__delattr__(self, name)

    def __init__(
        self,
        *,
        scope: OperationScope,
        root_id: str,
        subject_id: str,
        capture_digest: str,
        operation_id: str,
        operation_digest: str,
        targets: Sequence[ProviderTarget],
        network_authorized: bool,
        one_shot: Mapping[str, OneShotAuthorization] | None = None,
        runner: RunnerAuthorization | None = None,
        approved_local_models: set[str] | frozenset[str] = frozenset(),
        clock: Callable[[], datetime] | None = None,
        boundary_check: Callable[[], None] | None = None,
        resolver=None,
    ) -> None:
        if not isinstance(scope, OperationScope):
            raise AuthorizationDenied("operation scope is invalid")
        if type(network_authorized) is not bool or not network_authorized:
            raise AuthorizationDenied("network authorization is required")
        if not isinstance(targets, Sequence) or isinstance(targets, (str, bytes)) or not targets:
            raise AuthorizationDenied("provider targets are invalid")
        if clock is not None and not callable(clock):
            raise AuthorizationDenied("authorization clock is invalid")
        if boundary_check is not None and not callable(boundary_check):
            raise AuthorizationDenied("dispatch fence is invalid")
        if resolver is not None and not callable(resolver):
            raise AuthorizationDenied("provider resolver is invalid")
        self.scope = scope
        self.root_id = root_id
        self.subject_id = subject_id
        self.capture_digest = capture_digest
        self.operation_id = operation_id
        self.operation_digest = operation_digest
        self.network_authorized = network_authorized
        self.approved_local_models = frozenset(approved_local_models)
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._boundary_check = boundary_check
        self._resolver = resolver
        self._targets: dict[str, ProviderTarget] = {}
        self._one_shot = dict(one_shot or {})
        self._runner = runner
        self._attempts: contextvars.ContextVar[dict[str, int]] = contextvars.ContextVar(
            f"provider_attempts_{id(self)}",
            default={},
        )
        for target in targets:
            if not isinstance(target, ProviderTarget) or target.identity in self._targets:
                raise AuthorizationDenied("provider targets are invalid")
            validate_provider_target(target)
            provider_class = classify_provider(
                target,
                approved_local_models=self.approved_local_models,
            )
            if scope is OperationScope.MANUAL_ONE_SHOT:
                authorization = self._one_shot.get(target.identity)
                if not isinstance(authorization, OneShotAuthorization):
                    raise AuthorizationDenied("operation-bound provider authorization is required")
                if authorization.provider_id != target.identity or authorization.operation_id != operation_id or authorization.operation_digest != operation_digest:
                    raise AuthorizationDenied("provider authorization scope does not match")
                if authorization.root_id != root_id or authorization.subject_id != subject_id or authorization.capture_digest != capture_digest:
                    raise AuthorizationDenied("provider authorization inputs do not match")
                if provider_class.value == "paid-cloud" and authorization.upper_bound_cost <= 0:
                    raise AuthorizationDenied("paid upper-bound cost is unknown")
                if provider_class.value != "paid-cloud" and authorization.upper_bound_cost != 0:
                    raise AuthorizationDenied("free/local provider cost bound must be zero")
            elif scope is OperationScope.SCHEDULED:
                if runner is None or target.identity not in runner.provider_ids or provider_class.value == "paid-cloud":
                    raise AuthorizationDenied("scheduled provider is not authorized")
            self._targets[target.identity] = target
        if scope is OperationScope.MANUAL_ONE_SHOT and set(self._one_shot) != set(self._targets):
            raise AuthorizationDenied("operation provider set does not match authorization")
        if scope is OperationScope.SCHEDULED and (one_shot is not None or runner is None):
            raise AuthorizationDenied("finite runner authorization is required")
        object.__setattr__(self, "_targets", MappingProxyType(self._targets))
        object.__setattr__(self, "_one_shot", MappingProxyType(self._one_shot))
        object.__setattr__(self, "_sealed", True)

    @contextmanager
    def invocation(self, target: ProviderTarget) -> Iterator[None]:
        """Track retries within one model invocation."""
        self._require_target(target)
        current = dict(self._attempts.get())
        current[target.identity] = 0
        token = self._attempts.set(current)
        try:
            yield
        finally:
            self._attempts.reset(token)

    def authorize_transport(
        self,
        target: ProviderTarget,
        *,
        url: str,
        method: str,
        host_header: str | None = None,
        request_body: bytes | None = None,
    ) -> PinnedAddress:
        """Reserve authority, fence operation, then pin approved destination."""
        self._require_target(target)
        if not isinstance(method, str) or not method or not method.isascii():
            raise AuthorizationDenied("provider method is invalid")
        host, port, local = validate_request_url(target, url)
        if host_header is not None and not _host_header_matches(host_header, host, port):
            raise AuthorizationDenied("provider host header does not match destination")
        one_shot = self._one_shot.get(target.identity)
        cost = one_shot.upper_bound_cost if one_shot is not None else Decimal("0")
        provider_class = classify_provider(
            target,
            approved_local_models=self.approved_local_models,
        )
        if provider_class.value == "paid-cloud":
            required_cost = request_cost_upper_bound(
                target,
                url=url,
                method=method,
                body=request_body,
            )
            if required_cost is None:
                raise AuthorizationDenied("provider upper-bound cost is unknown")
            if cost < required_cost:
                raise BudgetDenied("provider request cost exceeds authorization")
        if self._boundary_check is not None:
            self._boundary_check()
        attempt = self._next_attempt(target)
        authorize_dispatch(
            target,
            scope=self.scope,
            root_id=self.root_id,
            subject_id=self.subject_id,
            capture_digest=self.capture_digest,
            operation_id=self.operation_id,
            operation_digest=self.operation_digest,
            now=self._clock(),
            one_shot=one_shot,
            runner=self._runner,
            upper_bound_cost=cost,
            resource_units=1,
            network_authorized=self.network_authorized,
            attempt=attempt,
            approved_local_models=self.approved_local_models,
        )
        return resolve_destination(
            host,
            port,
            local=local,
            resolver=self._resolver,
        )

    def recheck_transport_fence(self, target: ProviderTarget) -> None:
        """Recheck expiry and operation fence immediately before I/O."""
        self._require_target(target)
        if self._boundary_check is not None:
            self._boundary_check()
        now = self._clock()
        if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
            raise AuthorizationDenied("authorization clock must be timezone-aware")
        if self.scope is OperationScope.MANUAL_ONE_SHOT:
            authorization = self._one_shot.get(target.identity)
            if authorization is None or authorization.root_id != self.root_id or authorization.subject_id != self.subject_id or authorization.capture_digest != self.capture_digest or authorization.provider_id != target.identity or authorization.operation_id != self.operation_id or authorization.operation_digest != self.operation_digest or authorization.expires_at <= now:
                raise AuthorizationDenied("one-shot authorization does not match")
            return
        runner = self._runner
        if runner is None or runner.root_id != self.root_id or runner.deployment_id != self.subject_id or runner.capture_digest != self.capture_digest or runner.operation_id != self.operation_id or runner.operation_digest != self.operation_digest or runner.expires_at <= now:
            raise AuthorizationDenied("runner authorization does not match")

    def httpx_transport(
        self,
        target: ProviderTarget,
        *,
        inner_transport: httpx.BaseTransport | None = None,
    ) -> httpx.BaseTransport:
        """Create guarded transport; optional inner transport stays below guard."""
        self._require_target(target)
        return AuthorizedHTTPTransport(self, target, inner_transport=inner_transport)

    def validate_target(self, target: ProviderTarget) -> None:
        self._require_target(target)

    def httpx_client(
        self,
        target: ProviderTarget,
        *,
        timeout: float = 60.0,
        inner_transport: httpx.BaseTransport | None = None,
    ) -> httpx.Client:
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or timeout <= 0:
            raise AuthorizationDenied("provider timeout is invalid")
        return httpx.Client(
            transport=self.httpx_transport(
                target,
                inner_transport=inner_transport,
            ),
            timeout=float(timeout),
            trust_env=False,
            follow_redirects=False,
        )

    def _require_target(self, target: ProviderTarget) -> None:
        if not isinstance(target, ProviderTarget) or self._targets.get(target.identity) != target:
            raise AuthorizationDenied("provider target is outside operation scope")

    def _next_attempt(self, target: ProviderTarget) -> int:
        current = self._attempts.get()
        if target.identity not in current:
            return 1
        attempt = current[target.identity] + 1
        self._attempts.set({**current, target.identity: attempt})
        return attempt


class AuthorizedHTTPTransport(httpx.BaseTransport):
    """Guard each request before an HTTP transport can perform I/O."""

    def __init__(
        self,
        dispatch: ProviderDispatch,
        target: ProviderTarget,
        *,
        inner_transport: httpx.BaseTransport | None = None,
    ) -> None:
        if not isinstance(dispatch, ProviderDispatch) or not isinstance(target, ProviderTarget):
            raise AuthorizationDenied("guarded HTTP transport is invalid")
        self._dispatch = dispatch
        self._target = target
        self._backend = None
        if inner_transport is None:
            self._backend = _PinnedSyncBackend()
            self._inner = _PinnedHTTPTransport(self._backend)
        elif isinstance(inner_transport, httpx.BaseTransport):
            self._inner = inner_transport
        else:
            raise AuthorizationDenied("inner HTTP transport is invalid")

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        try:
            request_body = request.content
        except httpx.RequestNotRead:
            request_body = None
        pin = self._dispatch.authorize_transport(
            self._target,
            url=str(request.url),
            method=request.method,
            host_header=request.headers.get("host"),
            request_body=request_body,
        )
        self._dispatch.recheck_transport_fence(self._target)
        token = self._backend.pin(pin) if self._backend is not None else None
        try:
            response = self._inner.handle_request(request)
        finally:
            if self._backend is not None:
                self._backend.unpin(token)
        if 300 <= response.status_code < 400:
            response.close()
            raise AuthorizationDenied("provider redirects are disabled")
        return response

    def close(self) -> None:
        self._inner.close()


class DenyingHTTPTransport(httpx.BaseTransport):
    """Reject provider I/O when operation authority is absent."""

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        raise AuthorizationDenied("provider operation authorization is required")


class _PinnedHTTPTransport(httpx.HTTPTransport):
    def __init__(self, backend: _PinnedSyncBackend) -> None:
        super().__init__(
            verify=True,
            http2=False,
            trust_env=False,
            retries=0,
            limits=httpx.Limits(max_connections=10, max_keepalive_connections=0),
        )
        ssl_context = self._pool._ssl_context
        self._pool = httpcore.ConnectionPool(
            ssl_context=ssl_context,
            max_connections=10,
            max_keepalive_connections=0,
            keepalive_expiry=0,
            http1=True,
            http2=False,
            retries=0,
            network_backend=backend,
        )


class _PinnedSyncBackend(SyncBackend):
    def __init__(self) -> None:
        self._pin_context: contextvars.ContextVar[PinnedAddress | None] = contextvars.ContextVar(
            f"provider_pin_{id(self)}",
            default=None,
        )

    def pin(self, address: PinnedAddress):
        return self._pin_context.set(address)

    def unpin(self, token) -> None:
        self._pin_context.reset(token)

    def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options=None,
    ):
        pin = self._pin_context.get()
        normalized_host = host.decode("ascii").casefold() if isinstance(host, bytes) else host.casefold() if isinstance(host, str) else ""
        if pin is None or normalized_host != pin.host or port != pin.port:
            raise AuthorizationDenied("HTTP connection escaped pinned destination")
        return super().connect_tcp(
            pin.address,
            port,
            timeout=timeout,
            local_address=local_address,
            socket_options=socket_options,
        )


def blocked_httpx_client(*, timeout: float = 60.0) -> httpx.Client:
    """Build inert client; provider requests fail before socket access."""
    return httpx.Client(
        transport=DenyingHTTPTransport(),
        timeout=timeout,
        trust_env=False,
        follow_redirects=False,
    )


def blocked_async_httpx_client(*, timeout: float = 60.0) -> httpx.AsyncClient:
    """Build inert async client; provider requests fail before socket access."""
    return httpx.AsyncClient(
        transport=DenyingAsyncHTTPTransport(),
        timeout=timeout,
        trust_env=False,
        follow_redirects=False,
    )


def make_one_shot_dispatch(
    *,
    root_id: str,
    subject_id: str,
    capture_digest: str,
    operation_id: str,
    operation_digest: str,
    expires_at: datetime,
    targets: Sequence[ProviderTarget],
    max_calls: int,
    max_cost: Decimal,
    max_resources: int,
    upper_bound_costs: Mapping[str, Decimal],
    per_target_bounds: Mapping[str, tuple[int, Decimal, int]] | None = None,
    approved_local_models: set[str] | frozenset[str] = frozenset(),
    clock: Callable[[], datetime] | None = None,
    boundary_check: Callable[[], None] | None = None,
    resolver=None,
) -> ProviderDispatch:
    """Bind one finite budget to frozen providers and operation inputs."""
    if not isinstance(targets, Sequence) or isinstance(targets, (str, bytes)) or not targets:
        raise AuthorizationDenied("provider targets are invalid")
    target_ids = {target.identity for target in targets if isinstance(target, ProviderTarget)}
    if len(target_ids) != len(targets):
        raise AuthorizationDenied("provider targets are invalid")
    if not isinstance(upper_bound_costs, Mapping) or set(upper_bound_costs) != target_ids:
        raise AuthorizationDenied("provider cost bounds are invalid")
    if per_target_bounds is not None and (not isinstance(per_target_bounds, Mapping) or set(per_target_bounds) != target_ids):
        raise AuthorizationDenied("provider bounds are invalid")
    if type(max_calls) is not int or max_calls <= 0 or type(max_resources) is not int or max_resources <= 0:
        raise AuthorizationDenied("provider bounds are invalid")
    if not isinstance(max_cost, Decimal) or not max_cost.is_finite() or max_cost < 0:
        raise AuthorizationDenied("provider cost bound is invalid")
    if per_target_bounds is not None:
        aggregate_calls = 0
        aggregate_cost = Decimal("0")
        aggregate_resources = 0
        for bounds in per_target_bounds.values():
            if not isinstance(bounds, tuple) or len(bounds) != 3 or type(bounds[0]) is not int or bounds[0] <= 0 or not isinstance(bounds[1], Decimal) or not bounds[1].is_finite() or bounds[1] < 0 or type(bounds[2]) is not int or bounds[2] <= 0:
                raise AuthorizationDenied("provider bounds are invalid")
            aggregate_calls += bounds[0]
            aggregate_cost += bounds[1]
            aggregate_resources += bounds[2]
        if aggregate_calls > max_calls or aggregate_cost > max_cost or aggregate_resources > max_resources:
            raise AuthorizationDenied("per-target bounds exceed aggregate authorization")
    shared_budget = None
    if per_target_bounds is None:
        shared_budget = DispatchBudget(
            max_calls=max_calls,
            max_cost=max_cost,
            max_resources=max_resources,
        )
    authorizations = {}
    for target in targets:
        if per_target_bounds is None:
            calls, cost, resources = max_calls, max_cost, max_resources
        else:
            bounds = per_target_bounds[target.identity]
            if not isinstance(bounds, tuple) or len(bounds) != 3 or type(bounds[0]) is not int or type(bounds[2]) is not int or not isinstance(bounds[1], Decimal):
                raise AuthorizationDenied("provider bounds are invalid")
            calls, cost, resources = bounds
        authorizations[target.identity] = OneShotAuthorization(
            root_id=root_id,
            subject_id=subject_id,
            capture_digest=capture_digest,
            provider_id=target.identity,
            operation_id=operation_id,
            operation_digest=operation_digest,
            expires_at=expires_at,
            max_calls=calls,
            max_cost=cost,
            max_resources=resources,
            upper_bound_cost=upper_bound_costs[target.identity],
            shared_budget=shared_budget,
        )
    return ProviderDispatch(
        scope=OperationScope.MANUAL_ONE_SHOT,
        root_id=root_id,
        subject_id=subject_id,
        capture_digest=capture_digest,
        operation_id=operation_id,
        operation_digest=operation_digest,
        targets=targets,
        network_authorized=True,
        one_shot=authorizations,
        approved_local_models=approved_local_models,
        clock=clock,
        boundary_check=boundary_check,
        resolver=resolver,
    )


class DenyingAsyncHTTPTransport(httpx.AsyncBaseTransport):
    """Reject async provider I/O when operation authority is absent."""

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        raise AuthorizationDenied("provider operation authorization is required")

    async def aclose(self) -> None:
        return None


def _host_header_matches(value: str, host: str, port: int) -> bool:
    if not isinstance(value, str) or not value:
        return False
    normalized = value.casefold()
    return normalized in {host, f"{host}:{port}"}
