"""Process-local external credential leases."""

from __future__ import annotations

import re
import threading
import unicodedata
from dataclasses import dataclass, field
from typing import Mapping

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


@dataclass(frozen=True, slots=True)
class RuntimeCredentialHandle:
    """Opaque generation identity; no credential value."""

    root_id: str = field(repr=False)
    instance_id: str = field(repr=False)
    provider_id: str
    generation: int
    destination: str = field(repr=False)


@dataclass(slots=True)
class _Lease:
    value: str = field(repr=False)
    handle: RuntimeCredentialHandle
    captures: int = 0


class RuntimeCredentialLeaseStore:
    """Hold external credential generations in backend memory only."""

    def __init__(
        self,
        *,
        root_id: str,
        instance_id: str,
        allowed_destinations: Mapping[str, str] | None = None,
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

        self._root_id = root_id.casefold()
        self._instance_id = instance_id
        self._allowed_destinations = destinations
        self._leases: dict[tuple[str, int], _Lease] = {}
        self._generations: dict[str, int] = {}
        self._revoked: set[str] = set()
        self._deliveries: set[str] = set()
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

    def delivery_status(self, provider: str, *, destination: str) -> dict[str, int | str]:
        provider_id = self._provider(provider)
        expected_destination = self._allowed_destinations.get(provider_id)
        if expected_destination is None:
            raise ExternalCredentialError("provider is not allowed")
        if not isinstance(destination, str) or destination.casefold() != expected_destination:
            raise ExternalCredentialError("provider destination is not allowed")
        with self._lock:
            self._ensure_open()
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
        if not isinstance(handle, RuntimeCredentialHandle) or handle.root_id != self._root_id or handle.instance_id != self._instance_id:
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
            self._allowed_destinations.clear()
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
