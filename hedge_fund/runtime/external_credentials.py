"""Process-local external credential leases."""

from __future__ import annotations

import re
import threading
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Callable, Mapping, TypeVar

from hedge_fund.data.registry import DATA_PROVIDER_ENV_VARS
from hedge_fund.llm.registry import (
    KEYLESS_PROVIDERS,
    PROVIDER_ENV_VARS,
    SUPPORTED_PROVIDERS,
)

_ROOT_ID = re.compile(r"[a-fA-F0-9]{64}")
_INSTANCE_ID = re.compile(r"[A-Za-z0-9._:-]{1,128}")
_PROVIDER_ID = re.compile(r"[a-z][a-z0-9._-]{0,63}")
_DELIVERY_ID = re.compile(r"[A-Za-z0-9._:-]{1,128}")
_MAX_VALUE_BYTES = 16 * 1024
_MAX_DELIVERIES = 4096
_MAX_GENERATION = 2**31 - 1
APPLICATION_PROVIDER_IDS = frozenset(provider.casefold() for provider in (SUPPORTED_PROVIDERS.intersection(PROVIDER_ENV_VARS) - KEYLESS_PROVIDERS) | DATA_PROVIDER_ENV_VARS.keys())
INSPECTION_CAPABILITY_DESTINATIONS = {"saxo-demo-token": "saxo-sim-readonly"}
_INSPECTION_PURPOSE = "saxo-sim-readonly"
_Publication = TypeVar("_Publication")


class ExternalCredentialError(RuntimeError):
    """External credential delivery or lease validation failed."""


def runtime_provider_destinations(configured: str | None) -> dict[str, str]:
    """Parse explicit provider IDs; unset input grants no destination."""
    if configured is None or configured == "":
        return {}
    if not isinstance(configured, str) or len(configured) > 2048:
        raise ExternalCredentialError("provider allowlist is invalid")
    providers = configured.split(",")
    if not providers or len(providers) > len(APPLICATION_PROVIDER_IDS):
        raise ExternalCredentialError("provider allowlist is invalid")
    result: dict[str, str] = {}
    for raw_provider in providers:
        provider = raw_provider.casefold()
        if not _PROVIDER_ID.fullmatch(provider) or provider not in APPLICATION_PROVIDER_IDS or provider in result:
            raise ExternalCredentialError("provider allowlist is invalid")
        result[provider] = provider
    return result


def runtime_inspection_capability_destinations(configured: str | None) -> dict[str, str]:
    """Parse the separate, opt-in Saxo inspection capability namespace."""
    if configured is None or configured == "":
        return {}
    if not isinstance(configured, str) or configured.casefold() != "saxo-demo-token":
        raise ExternalCredentialError("capability allowlist is invalid")
    return dict(INSPECTION_CAPABILITY_DESTINATIONS)


@dataclass(frozen=True, slots=True)
class RuntimeCredentialHandle:
    """Opaque generation identity; no credential value."""

    root_id: str = field(repr=False)
    instance_id: str = field(repr=False)
    provider_id: str
    generation: int
    destination: str = field(repr=False)
    purpose: str = field(default="application", repr=False)


@dataclass(slots=True)
class _Lease:
    value: str = field(repr=False)
    handle: RuntimeCredentialHandle
    captures: int = 0
    expires_at: datetime | None = None
    invalidated: bool = False


class RuntimeCredentialLeaseStore:
    """Hold external credential generations in backend memory only."""

    def __init__(
        self,
        *,
        root_id: str,
        instance_id: str,
        allowed_destinations: Mapping[str, str] | None = None,
        allowed_capabilities: Mapping[str, str] | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if not isinstance(root_id, str) or not _ROOT_ID.fullmatch(root_id):
            raise ExternalCredentialError("runtime root identity is invalid")
        if not isinstance(instance_id, str) or not _INSTANCE_ID.fullmatch(instance_id):
            raise ExternalCredentialError("runtime instance identity is invalid")
        if allowed_destinations is None:
            allowed_destinations = {}
        if not isinstance(allowed_destinations, Mapping):
            raise ExternalCredentialError("provider allowlist is invalid")
        destinations: dict[str, str] = {}
        for provider, destination in allowed_destinations.items():
            if not isinstance(provider, str) or not _PROVIDER_ID.fullmatch(provider.casefold()):
                raise ExternalCredentialError("provider allowlist is invalid")
            provider_id = provider.casefold()
            if provider_id not in APPLICATION_PROVIDER_IDS or provider_id in destinations:
                raise ExternalCredentialError("provider is not an allowed application provider")
            if not isinstance(destination, str) or not _PROVIDER_ID.fullmatch(destination.casefold()):
                raise ExternalCredentialError("provider destination is invalid")
            destinations[provider_id] = destination.casefold()
        if allowed_capabilities is None:
            allowed_capabilities = {}
        if not isinstance(allowed_capabilities, Mapping):
            raise ExternalCredentialError("capability allowlist is invalid")
        capabilities: dict[str, str] = {}
        for provider, destination in allowed_capabilities.items():
            if provider != "saxo-demo-token" or provider in capabilities:
                raise ExternalCredentialError("capability is not allowed")
            if not isinstance(destination, str) or destination.casefold() != _INSPECTION_PURPOSE:
                raise ExternalCredentialError("capability purpose is invalid")
            if provider in destinations:
                raise ExternalCredentialError("capability cannot be an application provider")
            capabilities[provider] = destination.casefold()
        if clock is not None and not callable(clock):
            raise ExternalCredentialError("credential clock is invalid")

        self._root_id = root_id.casefold()
        self._instance_id = instance_id
        self._allowed_destinations = destinations
        self._allowed_capabilities = capabilities
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._leases: dict[tuple[str, int], _Lease] = {}
        self._generations: dict[str, int] = {}
        self._revoked: set[str] = set()
        self._deliveries: set[str] = set()
        self._capability_leases: dict[tuple[str, int], _Lease] = {}
        self._capability_generations: dict[str, int] = {}
        self._capability_revoked: set[str] = set()
        self._capability_deliveries: set[str] = set()
        self._closed = False
        self._lock = threading.RLock()

    def publish(
        self,
        provider: str,
        value: str,
        *,
        expected_generation: int,
        delivery_id: str,
        root_id: str,
        instance_id: str,
        destination: str,
    ) -> RuntimeCredentialHandle:
        provider_id = self._provider(provider)
        with self._lock:
            self._ensure_open()
            expected_destination = self._allowed_destinations.get(provider_id)
        if expected_destination is None:
            raise ExternalCredentialError("provider is not allowed")
        if not isinstance(destination, str) or destination.casefold() != expected_destination:
            raise ExternalCredentialError("provider destination is not allowed")
        if not isinstance(value, str) or not value or not value.strip() or any(unicodedata.category(char) in {"Cc", "Cf"} for char in value):
            raise ExternalCredentialError("credential value is invalid")
        try:
            value_size = len(value.encode("utf-8"))
        except UnicodeEncodeError:
            raise ExternalCredentialError("credential value is invalid") from None
        if value_size > _MAX_VALUE_BYTES:
            raise ExternalCredentialError("credential value is invalid")
        if type(expected_generation) is not int or expected_generation < 0:
            raise ExternalCredentialError("credential generation is invalid")
        if not isinstance(delivery_id, str) or not _DELIVERY_ID.fullmatch(delivery_id):
            raise ExternalCredentialError("delivery identity is invalid")
        self._check_target(root_id, instance_id)

        with self._lock:
            self._ensure_open()
            if delivery_id in self._deliveries:
                raise ExternalCredentialError("delivery was already used")
            if len(self._deliveries) >= _MAX_DELIVERIES:
                raise ExternalCredentialError("delivery capacity is unavailable")
            current_generation = self._generations.get(provider_id, 0)
            if current_generation != expected_generation:
                raise ExternalCredentialError("credential generation changed")
            generation = current_generation + 1
            if generation > _MAX_GENERATION:
                raise ExternalCredentialError("credential generation exceeds its bound")
            handle = RuntimeCredentialHandle(
                root_id=self._root_id,
                instance_id=self._instance_id,
                provider_id=provider_id,
                generation=generation,
                destination=expected_destination,
            )
            lease = _Lease(value=value, handle=handle)
            self._leases[(provider_id, generation)] = lease
            self._generations[provider_id] = generation
            self._revoked.discard(provider_id)
            self._deliveries.add(delivery_id)
            old_generation = current_generation
            if old_generation:
                self._discard_if_unreferenced(provider_id, old_generation)
            return handle

    def publish_capability(
        self,
        provider: str,
        value: str,
        *,
        expected_generation: int,
        delivery_id: str,
        root_id: str,
        instance_id: str,
        destination: str,
        expires_at: str,
        purpose: str = _INSPECTION_PURPOSE,
    ) -> RuntimeCredentialHandle:
        provider_id = self._provider(provider)
        with self._lock:
            self._ensure_open()
            expected_destination = self._allowed_capabilities.get(provider_id)
        if expected_destination is None:
            raise ExternalCredentialError("provider is not allowed")
        if purpose != _INSPECTION_PURPOSE or purpose != expected_destination:
            raise ExternalCredentialError("purpose is not allowed")
        if not isinstance(destination, str) or destination.casefold() != expected_destination:
            raise ExternalCredentialError("provider destination is not allowed")
        expiration = _parse_capability_expiry(expires_at, self._now())
        _validate_value(value)
        if type(expected_generation) is not int or expected_generation < 0:
            raise ExternalCredentialError("credential generation is invalid")
        if not isinstance(delivery_id, str) or not _DELIVERY_ID.fullmatch(delivery_id):
            raise ExternalCredentialError("delivery identity is invalid")
        self._check_target(root_id, instance_id)
        with self._lock:
            self._ensure_open()
            if delivery_id in self._capability_deliveries:
                raise ExternalCredentialError("delivery was already used")
            if len(self._capability_deliveries) >= _MAX_DELIVERIES:
                raise ExternalCredentialError("delivery capacity is unavailable")
            current_generation = self._capability_generations.get(provider_id, 0)
            if current_generation != expected_generation:
                raise ExternalCredentialError("credential generation changed")
            generation = current_generation + 1
            if generation > _MAX_GENERATION:
                raise ExternalCredentialError("credential generation exceeds its bound")
            handle = RuntimeCredentialHandle(
                root_id=self._root_id,
                instance_id=self._instance_id,
                provider_id=provider_id,
                generation=generation,
                destination=expected_destination,
                purpose=_INSPECTION_PURPOSE,
            )
            self._capability_leases[(provider_id, generation)] = _Lease(
                value=value,
                handle=handle,
                expires_at=expiration,
            )
            self._capability_generations[provider_id] = generation
            self._capability_revoked.discard(provider_id)
            self._capability_deliveries.add(delivery_id)
            old_generation = current_generation
            if old_generation:
                self._discard_capability_if_unreferenced(provider_id, old_generation)
            return handle

    def capability_status(self, provider: str, *, destination: str, purpose: str = _INSPECTION_PURPOSE) -> dict[str, int | str | None]:
        provider_id = self._provider(provider)
        with self._lock:
            self._ensure_open()
            expected_destination = self._allowed_capabilities.get(provider_id)
            if expected_destination is None:
                raise ExternalCredentialError("provider is not allowed")
            if purpose != _INSPECTION_PURPOSE or purpose != expected_destination:
                raise ExternalCredentialError("purpose is not allowed")
            if not isinstance(destination, str) or destination.casefold() != expected_destination:
                raise ExternalCredentialError("provider destination is not allowed")
            generation = self._capability_generations.get(provider_id, 0)
            lease = self._capability_leases.get((provider_id, generation))
            state = "revoked" if provider_id in self._capability_revoked else "expired" if lease is not None and self._expired(lease) else "available" if lease is not None and not lease.invalidated else "requires-auth"
            return {
                "provider_id": provider_id,
                "destination": expected_destination,
                "root_id": self._root_id,
                "instance_id": self._instance_id,
                "purpose": _INSPECTION_PURPOSE,
                "state": state,
                "generation": generation,
                "expires_at": lease.expires_at.isoformat().replace("+00:00", "Z") if lease and lease.expires_at else None,
            }

    def current_capability_handle(self, provider: str, *, destination: str, purpose: str = _INSPECTION_PURPOSE) -> RuntimeCredentialHandle:
        status = self.capability_status(provider, destination=destination, purpose=purpose)
        provider_id = status["provider_id"]
        with self._lock:
            lease = self._capability_leases.get((provider_id, status["generation"]))
            if status["state"] != "available" or lease is None:
                raise ExternalCredentialError("credential is unavailable")
            return lease.handle

    def capture_capability(self, provider: str, *, destination: str, purpose: str = _INSPECTION_PURPOSE) -> RuntimeCredentialHandle:
        handle = self.current_capability_handle(provider, destination=destination, purpose=purpose)
        with self._lock:
            lease = self._capability_leases.get((handle.provider_id, handle.generation))
            if lease is None or lease.invalidated or self._expired(lease):
                raise ExternalCredentialError("credential is unavailable")
            lease.captures += 1
            return handle

    def assert_capability_dispatch_allowed(self, handle: RuntimeCredentialHandle, *, destination: str, purpose: str = _INSPECTION_PURPOSE) -> None:
        if not isinstance(handle, RuntimeCredentialHandle) or handle.purpose != _INSPECTION_PURPOSE or purpose != _INSPECTION_PURPOSE:
            raise ExternalCredentialError("purpose is not allowed")
        if handle.root_id != self._root_id or handle.instance_id != self._instance_id:
            raise ExternalCredentialError("runtime instance changed")
        if not isinstance(destination, str) or destination.casefold() != handle.destination:
            raise ExternalCredentialError("provider destination changed")
        with self._lock:
            self._ensure_open()
            if handle.provider_id in self._capability_revoked:
                raise ExternalCredentialError("credential is revoked")
            lease = self._capability_leases.get((handle.provider_id, handle.generation))
            if lease is None or lease.handle != handle or lease.captures < 1 or lease.invalidated:
                raise ExternalCredentialError("credential handle is unavailable")
            if self._expired(lease):
                raise ExternalCredentialError("credential is expired")

    def capability_value_for_dispatch(self, handle: RuntimeCredentialHandle, *, destination: str, purpose: str = _INSPECTION_PURPOSE) -> str:
        self.assert_capability_dispatch_allowed(handle, destination=destination, purpose=purpose)
        with self._lock:
            lease = self._capability_leases[(handle.provider_id, handle.generation)]
            return lease.value

    def invalidate_capability(self, handle: RuntimeCredentialHandle) -> None:
        if not isinstance(handle, RuntimeCredentialHandle) or handle.purpose != _INSPECTION_PURPOSE:
            raise ExternalCredentialError("purpose is not allowed")
        with self._lock:
            self._ensure_open()
            lease = self._capability_leases.get((handle.provider_id, handle.generation))
            if lease is None or lease.handle != handle:
                return
            lease.invalidated = True
            lease.value = ""
            self._discard_capability_if_unreferenced(handle.provider_id, handle.generation)

    def commit_capability_publication(
        self,
        handle: RuntimeCredentialHandle,
        commit: Callable[[], _Publication],
        *,
        destination: str,
        purpose: str = _INSPECTION_PURPOSE,
    ) -> _Publication:
        """Serialize a local publication commit with revoke, invalidation and close.

        The callback must only hand off an already prepared result: no I/O,
        blocking work or acquisition of other locks. Captured A may finish after
        rotation to B, but revoking either current generation invalidates all pins.
        """
        with self._lock:
            self.assert_capability_dispatch_allowed(handle, destination=destination, purpose=purpose)
            return commit()

    def revoke_capability(self, provider: str, *, expected_generation: int | None = None, purpose: str = _INSPECTION_PURPOSE) -> int:
        provider_id = self._provider(provider)
        if purpose != _INSPECTION_PURPOSE:
            raise ExternalCredentialError("purpose is not allowed")
        if expected_generation is not None and (type(expected_generation) is not int or expected_generation < 0):
            raise ExternalCredentialError("credential generation is invalid")
        with self._lock:
            self._ensure_open()
            if provider_id not in self._allowed_capabilities:
                raise ExternalCredentialError("provider is not allowed")
            generation = self._capability_generations.get(provider_id, 0)
            if expected_generation is not None and generation != expected_generation:
                raise ExternalCredentialError("credential generation changed")
            if generation >= _MAX_GENERATION:
                raise ExternalCredentialError("credential generation exceeds its bound")
            generation += 1
            self._capability_generations[provider_id] = generation
            self._capability_revoked.add(provider_id)
            for key in [key for key in self._capability_leases if key[0] == provider_id]:
                self._capability_leases.pop(key, None)
            return generation

    def delivery_status(self, provider: str, *, destination: str) -> dict[str, int | str]:
        provider_id = self._provider(provider)
        with self._lock:
            self._ensure_open()
            expected_destination = self._allowed_destinations.get(provider_id)
            if expected_destination is None:
                raise ExternalCredentialError("provider is not allowed")
            if not isinstance(destination, str) or destination.casefold() != expected_destination:
                raise ExternalCredentialError("provider destination is not allowed")
            generation = self._generations.get(provider_id, 0)
            state = "revoked" if provider_id in self._revoked else "available" if generation else "requires-auth"
            return {
                "provider_id": provider_id,
                "destination": expected_destination,
                "root_id": self._root_id,
                "instance_id": self._instance_id,
                "state": state,
                "generation": generation,
            }

    def is_configured(self, provider: str) -> bool:
        provider_id = self._provider(provider)
        with self._lock:
            self._ensure_open()
            return provider_id in self._allowed_destinations

    def current_handle(self, provider: str, *, destination: str) -> RuntimeCredentialHandle:
        """Return active identity without pinning its value."""
        provider_id = self._provider(provider)
        with self._lock:
            self._ensure_open()
            expected_destination = self._allowed_destinations.get(provider_id)
            if expected_destination is None:
                raise ExternalCredentialError("provider is not allowed")
            if not isinstance(destination, str) or destination.casefold() != expected_destination:
                raise ExternalCredentialError("provider destination is not allowed")
            if provider_id in self._revoked:
                raise ExternalCredentialError("credential is unavailable")
            generation = self._generations.get(provider_id, 0)
            lease = self._leases.get((provider_id, generation))
            if lease is None:
                raise ExternalCredentialError("credential is unavailable")
            return lease.handle

    def acquire(self, handle: RuntimeCredentialHandle) -> None:
        """Pin the reviewed current generation for admitted work."""
        if not isinstance(handle, RuntimeCredentialHandle):
            raise ExternalCredentialError("credential handle is invalid")
        if handle.purpose != "application":
            raise ExternalCredentialError("purpose is not allowed")
        with self._lock:
            self._ensure_open()
            if handle.root_id != self._root_id or handle.instance_id != self._instance_id:
                raise ExternalCredentialError("runtime instance changed")
            if handle.provider_id not in self._allowed_destinations:
                raise ExternalCredentialError("provider is not allowed")
            if handle.destination != self._allowed_destinations[handle.provider_id]:
                raise ExternalCredentialError("provider destination is not allowed")
            if handle.provider_id in self._revoked:
                raise ExternalCredentialError("credential is revoked")
            if self._generations.get(handle.provider_id, 0) != handle.generation:
                raise ExternalCredentialError("credential generation changed")
            lease = self._leases.get((handle.provider_id, handle.generation))
            if lease is None or lease.handle != handle:
                raise ExternalCredentialError("credential handle is unavailable")
            lease.captures += 1

    def is_current(self, handle: RuntimeCredentialHandle, *, destination: str) -> bool:
        if not isinstance(handle, RuntimeCredentialHandle) or handle.purpose != "application" or handle.root_id != self._root_id or handle.instance_id != self._instance_id:
            return False
        if not isinstance(destination, str) or destination.casefold() != handle.destination:
            return False
        with self._lock:
            if self._closed:
                return False
            return handle.provider_id not in self._revoked and self._generations.get(handle.provider_id, 0) == handle.generation and (handle.provider_id, handle.generation) in self._leases

    def assert_dispatch_allowed(self, handle: RuntimeCredentialHandle, *, destination: str) -> None:
        if not isinstance(handle, RuntimeCredentialHandle):
            raise ExternalCredentialError("credential handle is invalid")
        if handle.purpose != "application":
            raise ExternalCredentialError("purpose is not allowed")
        if handle.root_id != self._root_id or handle.instance_id != self._instance_id:
            raise ExternalCredentialError("runtime instance changed")
        if not isinstance(destination, str) or destination.casefold() != handle.destination:
            raise ExternalCredentialError("provider destination changed")
        with self._lock:
            self._ensure_open()
            if handle.provider_id in self._revoked:
                raise ExternalCredentialError("credential is revoked")
            lease = self._leases.get((handle.provider_id, handle.generation))
            if lease is None or lease.handle != handle or lease.captures < 1:
                raise ExternalCredentialError("credential handle is unavailable")

    def capture(self, provider: str, *, destination: str) -> RuntimeCredentialHandle:
        provider_id = self._provider(provider)
        with self._lock:
            self._ensure_open()
            if provider_id not in self._allowed_destinations:
                raise ExternalCredentialError("provider is not allowed")
            if provider_id in self._revoked:
                raise ExternalCredentialError("credential is unavailable")
            expected_destination = self._allowed_destinations[provider_id]
            if not isinstance(destination, str) or destination.casefold() != expected_destination:
                raise ExternalCredentialError("provider destination is not allowed")
            generation = self._generations.get(provider_id, 0)
            lease = self._leases.get((provider_id, generation))
            if lease is None:
                raise ExternalCredentialError("credential is unavailable")
            lease.captures += 1
            return lease.handle

    def value_for_dispatch(
        self,
        handle: RuntimeCredentialHandle,
        *,
        destination: str,
    ) -> str:
        if not isinstance(handle, RuntimeCredentialHandle):
            raise ExternalCredentialError("credential handle is invalid")
        if handle.purpose != "application":
            raise ExternalCredentialError("purpose is not allowed")
        if handle.root_id != self._root_id or handle.instance_id != self._instance_id:
            raise ExternalCredentialError("runtime instance changed")
        if not isinstance(destination, str) or destination.casefold() != handle.destination:
            raise ExternalCredentialError("provider destination changed")
        with self._lock:
            self._ensure_open()
            if handle.provider_id in self._revoked:
                raise ExternalCredentialError("credential is revoked")
            lease = self._leases.get((handle.provider_id, handle.generation))
            if lease is None or lease.handle != handle or lease.captures < 1:
                raise ExternalCredentialError("credential handle is unavailable")
            return lease.value

    def release(self, handle: RuntimeCredentialHandle) -> None:
        if not isinstance(handle, RuntimeCredentialHandle):
            raise ExternalCredentialError("credential handle is invalid")
        with self._lock:
            if self._closed:
                return
            if handle.purpose == _INSPECTION_PURPOSE:
                lease = self._capability_leases.get((handle.provider_id, handle.generation))
                if lease is None or lease.handle != handle or lease.captures < 1:
                    return
                lease.captures -= 1
                if handle.generation != self._capability_generations.get(handle.provider_id) or lease.invalidated or self._expired(lease):
                    self._discard_capability_if_unreferenced(handle.provider_id, handle.generation)
                return
            if handle.purpose != "application":
                return
            lease = self._leases.get((handle.provider_id, handle.generation))
            if lease is None or lease.handle != handle or lease.captures < 1:
                return
            lease.captures -= 1
            if handle.generation != self._generations.get(handle.provider_id):
                self._discard_if_unreferenced(handle.provider_id, handle.generation)

    def revoke(self, provider: str, *, expected_generation: int | None = None) -> int:
        provider_id = self._provider(provider)
        if expected_generation is not None and (type(expected_generation) is not int or expected_generation < 0):
            raise ExternalCredentialError("credential generation is invalid")
        with self._lock:
            self._ensure_open()
            if provider_id not in self._allowed_destinations:
                raise ExternalCredentialError("provider is not allowed")
            generation = self._generations.get(provider_id, 0)
            if expected_generation is not None and generation != expected_generation:
                raise ExternalCredentialError("credential generation changed")
            if generation >= _MAX_GENERATION:
                raise ExternalCredentialError("credential generation exceeds its bound")
            generation += 1
            self._generations[provider_id] = generation
            self._revoked.add(provider_id)
            for key in [key for key in self._leases if key[0] == provider_id]:
                self._leases.pop(key, None)
            return generation

    def status(self) -> dict[str, dict[str, int | str]]:
        with self._lock:
            self._ensure_open()
            result = {}
            for provider in sorted(self._allowed_destinations):
                generation = self._generations.get(provider, 0)
                state = "revoked" if provider in self._revoked else "available" if generation else "requires-auth"
                result[provider] = {"state": state, "generation": generation}
            return result

    def close(self) -> None:
        """Drop all values and reject later lease operations."""
        with self._lock:
            self._leases.clear()
            self._generations.clear()
            self._revoked.clear()
            self._deliveries.clear()
            self._capability_leases.clear()
            self._capability_generations.clear()
            self._capability_revoked.clear()
            self._capability_deliveries.clear()
            self._allowed_destinations.clear()
            self._allowed_capabilities.clear()
            self._closed = True

    def _provider(self, provider: str) -> str:
        if not isinstance(provider, str) or not _PROVIDER_ID.fullmatch(provider.casefold()):
            raise ExternalCredentialError("provider identity is invalid")
        return provider.casefold()

    def _check_target(self, root_id: str, instance_id: str) -> None:
        if root_id != self._root_id or instance_id != self._instance_id:
            raise ExternalCredentialError("runtime target changed")

    def _ensure_open(self) -> None:
        if self._closed:
            raise ExternalCredentialError("runtime credential store is closed")

    def _discard_if_unreferenced(self, provider: str, generation: int) -> None:
        lease = self._leases.get((provider, generation))
        if lease is not None and lease.captures == 0:
            self._leases.pop((provider, generation), None)

    def _discard_capability_if_unreferenced(self, provider: str, generation: int) -> None:
        lease = self._capability_leases.get((provider, generation))
        if lease is not None and lease.captures == 0:
            self._capability_leases.pop((provider, generation), None)

    def _now(self) -> datetime:
        value = self._clock()
        if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() != timedelta(0):
            raise ExternalCredentialError("credential clock is invalid")
        return value.astimezone(timezone.utc)

    def _expired(self, lease: _Lease) -> bool:
        expired = lease.expires_at is not None and self._now() >= lease.expires_at
        if expired:
            lease.invalidated = True
            lease.value = ""
        return expired


def _validate_value(value: object) -> None:
    if not isinstance(value, str) or not value or not value.strip() or any(unicodedata.category(char) in {"Cc", "Cf"} for char in value):
        raise ExternalCredentialError("credential value is invalid")
    try:
        value_size = len(value.encode("utf-8"))
    except UnicodeEncodeError:
        raise ExternalCredentialError("credential value is invalid") from None
    if value_size > _MAX_VALUE_BYTES:
        raise ExternalCredentialError("credential value is invalid")


def _parse_capability_expiry(value: object, now: datetime) -> datetime:
    if not isinstance(value, str) or len(value) > 32:
        raise ExternalCredentialError("credential expiry is invalid")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00" if value.endswith("Z") else value)
    except (TypeError, ValueError):
        raise ExternalCredentialError("credential expiry is invalid") from None
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise ExternalCredentialError("credential expiry is invalid")
    parsed = parsed.astimezone(timezone.utc)
    if parsed <= now or parsed > now + timedelta(hours=24):
        raise ExternalCredentialError("credential expiry is invalid")
    return parsed
