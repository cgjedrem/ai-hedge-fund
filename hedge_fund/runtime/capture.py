"""Immutable root-bound runtime capture metadata."""

from __future__ import annotations

import hashlib
import json
import os
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from types import MappingProxyType
from uuid import uuid4

from hedge_fund.runtime.configuration import ConfigurationError, RuntimeSettings
from hedge_fund.runtime.root import (
    ensure_unique_resource_name,
    RootContext,
    RootPathError,
)

_TICKER = re.compile(r"[A-Z0-9.^=-]{1,15}")
_PROVIDER_ID = re.compile(r"[a-z][a-z0-9._-]{0,63}")
_SHA256 = re.compile(r"[a-fA-F0-9]{64}")
_MAX_MANDATE_SNAPSHOT_BYTES = 1024 * 1024


def is_capture_ticker(value: object) -> bool:
    """Return whether a ticker is valid in a frozen operation capture."""
    return isinstance(value, str) and _TICKER.fullmatch(value) is not None


@dataclass(frozen=True, slots=True)
class CredentialHandle:
    """Root/provider/version reference; contains no credential material."""

    root_id: str = field(repr=False)
    provider_id: str
    version: int

    def __post_init__(self) -> None:
        if not isinstance(self.root_id, str) or not _SHA256.fullmatch(self.root_id):
            raise ConfigurationError("credential reference is invalid")
        if not isinstance(self.provider_id, str) or not _PROVIDER_ID.fullmatch(self.provider_id.casefold()):
            raise ConfigurationError("credential reference is invalid")
        if type(self.version) is not int or self.version < 0:
            raise ConfigurationError("credential reference is invalid")
        object.__setattr__(self, "root_id", self.root_id.casefold())
        object.__setattr__(self, "provider_id", self.provider_id.casefold())


@dataclass(frozen=True, slots=True)
class FrozenCapture:
    """Immutable execution inputs; public view omits private identities."""

    capture_id: str
    digest: str
    root_id: str = field(repr=False)
    subject_id: str
    mandate_digest: str = field(repr=False)
    universe: tuple[str, ...]
    broker: str
    settings_version: int
    data_provider: str
    llm_provider: str
    model: str
    endpoint: str | None
    timeout_seconds: float
    parameters: Mapping[str, int | float] = field(repr=False)
    provenance: Mapping[str, str] = field(repr=False)
    credential_versions: Mapping[str, int] = field(repr=False)
    credential_handles: Mapping[str, CredentialHandle] = field(repr=False)
    code_version: str = field(repr=False)
    mandate_snapshot: bytes | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.capture_id, str) or not re.fullmatch(r"[a-fA-F0-9]{32}", self.capture_id):
            raise ConfigurationError("capture identity is invalid")
        if not isinstance(self.digest, str) or not _SHA256.fullmatch(self.digest):
            raise ConfigurationError("capture digest is invalid")
        if not isinstance(self.root_id, str) or not _SHA256.fullmatch(self.root_id):
            raise ConfigurationError("capture root identity is invalid")
        if not isinstance(self.subject_id, str):
            raise ConfigurationError("capture subject is invalid")
        try:
            subject_id = ensure_unique_resource_name(self.subject_id, [])
        except RootPathError:
            raise ConfigurationError("capture subject is invalid") from None
        if not isinstance(self.mandate_digest, str) or not _SHA256.fullmatch(self.mandate_digest):
            raise ConfigurationError("mandate digest is invalid")
        if not isinstance(self.universe, tuple):
            raise ConfigurationError("capture universe is invalid")
        if not self.universe or any(not is_capture_ticker(ticker) for ticker in self.universe) or len(set(self.universe)) != len(self.universe):
            raise ConfigurationError("capture universe is invalid")
        if not isinstance(self.broker, str) or self.broker != "paper":
            raise ConfigurationError("only local-paper captures are supported")
        if not isinstance(self.parameters, Mapping) or not isinstance(self.provenance, Mapping):
            raise ConfigurationError("capture settings are invalid")
        if not isinstance(self.credential_versions, Mapping) or not isinstance(self.credential_handles, Mapping):
            raise ConfigurationError("capture credential references are invalid")
        if not isinstance(self.code_version, str) or not self.code_version or self.code_version != self.code_version.strip() or len(self.code_version) > 256 or any(ord(char) < 32 or ord(char) == 127 for char in self.code_version):
            raise ConfigurationError("code version is invalid")

        root_id = self.root_id.casefold()
        mandate_digest = self.mandate_digest.casefold()
        settings = RuntimeSettings(
            data_provider=self.data_provider,
            llm_provider=self.llm_provider,
            model=self.model,
            endpoint=self.endpoint,
            timeout_seconds=self.timeout_seconds,
            parameters=self.parameters,
            version=self.settings_version,
            provenance=self.provenance,
        )
        versions: dict[str, int] = {}
        for provider, version in self.credential_versions.items():
            if not isinstance(provider, str) or not _PROVIDER_ID.fullmatch(provider.casefold()) or type(version) is not int or version < 0:
                raise ConfigurationError("credential references are invalid")
            provider_id = provider.casefold()
            if provider_id in versions:
                raise ConfigurationError("credential references are invalid")
            versions[provider_id] = version

        handles: dict[str, CredentialHandle] = {}
        for provider, handle in self.credential_handles.items():
            if not isinstance(provider, str) or not _PROVIDER_ID.fullmatch(provider.casefold()) or not isinstance(handle, CredentialHandle):
                raise ConfigurationError("credential references are invalid")
            provider_id = provider.casefold()
            if provider_id in handles or handle.provider_id != provider_id or handle.root_id != root_id:
                raise ConfigurationError("credential references are invalid")
            handles[provider_id] = handle
        if handles.keys() != versions.keys() or any(handles[key].version != version for key, version in versions.items()):
            raise ConfigurationError("credential references are invalid")

        mandate_snapshot, mandate_snapshot_bytes = _validated_mandate_snapshot(
            self.mandate_snapshot,
            subject_id=subject_id,
            mandate_digest=mandate_digest,
        )
        payload = {
            "schema": 2 if mandate_snapshot is not None else 1,
            "root_id": root_id,
            "subject_id": subject_id,
            "mandate_digest": mandate_digest,
            "universe": list(self.universe),
            "broker": self.broker,
            "settings_version": settings.version,
            "settings": settings.to_mapping(),
            "provenance": dict(settings.provenance),
            "credential_versions": versions,
            "code_version": self.code_version,
        }
        if mandate_snapshot is not None:
            payload["mandate_snapshot"] = mandate_snapshot
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        expected_digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        if self.digest.casefold() != expected_digest:
            raise ConfigurationError("capture digest does not match contents")

        object.__setattr__(self, "capture_id", self.capture_id.casefold())
        object.__setattr__(self, "digest", expected_digest)
        object.__setattr__(self, "root_id", root_id)
        object.__setattr__(self, "subject_id", subject_id)
        object.__setattr__(self, "mandate_digest", mandate_digest)
        object.__setattr__(self, "parameters", MappingProxyType(dict(settings.parameters)))
        object.__setattr__(self, "provenance", settings.provenance)
        object.__setattr__(self, "credential_versions", MappingProxyType(versions))
        object.__setattr__(self, "credential_handles", MappingProxyType(handles))
        object.__setattr__(self, "data_provider", settings.data_provider)
        object.__setattr__(self, "llm_provider", settings.llm_provider)
        object.__setattr__(self, "model", settings.model)
        object.__setattr__(self, "endpoint", settings.endpoint)
        object.__setattr__(self, "timeout_seconds", settings.timeout_seconds)
        object.__setattr__(self, "universe", tuple(self.universe))
        object.__setattr__(self, "mandate_snapshot", mandate_snapshot_bytes)

    def public_view(self, *, current_settings_version: int | None = None) -> dict[str, object]:
        if current_settings_version is not None and (type(current_settings_version) is not int or current_settings_version < 0):
            raise ConfigurationError("current settings version is invalid")
        restart_needed = None if current_settings_version is None else current_settings_version != self.settings_version
        return {
            "capture_id": self.capture_id,
            "digest": self.digest,
            "subject_id": self.subject_id,
            "universe": list(self.universe),
            "broker": self.broker,
            "settings_version": self.settings_version,
            "data_provider": self.data_provider,
            "llm_provider": self.llm_provider,
            "model": self.model,
            "endpoint": self.endpoint,
            "timeout_seconds": self.timeout_seconds,
            "parameters": dict(self.parameters),
            "provenance": dict(self.provenance),
            "restart_needed": restart_needed,
        }

    def private_bytes(self) -> bytes:
        """Serialize frozen inputs and version handles; no credential values."""
        record = {
            "schema": 2 if self.mandate_snapshot is not None else 1,
            "capture_id": self.capture_id,
            "digest": self.digest,
            "root_id": self.root_id,
            "subject_id": self.subject_id,
            "mandate_digest": self.mandate_digest,
            "universe": list(self.universe),
            "broker": self.broker,
            "settings_version": self.settings_version,
            "settings": {
                "data_provider": self.data_provider,
                "llm_provider": self.llm_provider,
                "model": self.model,
                "endpoint": self.endpoint,
                "timeout_seconds": self.timeout_seconds,
                "parameters": dict(self.parameters),
                "provenance": dict(self.provenance),
            },
            "credential_handles": [
                {
                    "provider_id": handle.provider_id,
                    "version": handle.version,
                }
                for _, handle in sorted(self.credential_handles.items())
            ],
            "code_version": self.code_version,
        }
        if self.mandate_snapshot is not None:
            record["mandate_snapshot"] = json.loads(self.mandate_snapshot)
        return json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")

    @classmethod
    def from_private_bytes(cls, root: RootContext, data: bytes) -> FrozenCapture:
        """Restore a bounded capture from root-private bytes."""
        if not isinstance(root, RootContext) or not isinstance(data, bytes):
            raise ConfigurationError("capture input is invalid")
        if len(data) > 1024 * 1024:
            raise ConfigurationError("capture exceeds its bound")
        root.revalidate()
        try:
            record = json.loads(data.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise ConfigurationError("capture is malformed") from None
        fields = {
            "schema",
            "capture_id",
            "digest",
            "root_id",
            "subject_id",
            "mandate_digest",
            "universe",
            "broker",
            "settings_version",
            "settings",
            "credential_handles",
            "code_version",
        }
        if not isinstance(record, dict) or frozenset(record) not in {
            frozenset(fields),
            frozenset(fields | {"mandate_snapshot"}),
        }:
            raise ConfigurationError("capture fields are invalid")
        if type(record["schema"]) is not int or record["schema"] not in {1, 2}:
            raise ConfigurationError("capture schema is invalid")
        settings_record = record["settings"]
        if not isinstance(settings_record, dict) or set(settings_record) != {
            "data_provider",
            "llm_provider",
            "model",
            "endpoint",
            "timeout_seconds",
            "parameters",
            "provenance",
        }:
            raise ConfigurationError("capture settings are invalid")
        try:
            settings = RuntimeSettings(
                **settings_record,
                version=record["settings_version"],
            )
            root_id = _root_id(root)
            if record["root_id"] != root_id:
                raise ConfigurationError("capture root identity does not match")
            handles_record = record["credential_handles"]
            if not isinstance(handles_record, list):
                raise ConfigurationError("capture credential handles are invalid")
            handles = {}
            versions = {}
            for entry in handles_record:
                if not isinstance(entry, dict) or set(entry) != {"provider_id", "version"}:
                    raise ConfigurationError("capture credential handles are invalid")
                provider = entry["provider_id"]
                version = entry["version"]
                if not isinstance(provider, str) or provider.casefold() in handles:
                    raise ConfigurationError("capture credential handles are invalid")
                handle = CredentialHandle(root_id, provider, version)
                handles[handle.provider_id] = handle
                versions[handle.provider_id] = handle.version
            snapshot = None
            if "mandate_snapshot" in record:
                snapshot = json.dumps(
                    record["mandate_snapshot"],
                    sort_keys=True,
                    separators=(",", ":"),
                    ensure_ascii=False,
                ).encode("utf-8")
            capture = cls(
                capture_id=record["capture_id"],
                digest=record["digest"],
                root_id=root_id,
                subject_id=record["subject_id"],
                mandate_digest=record["mandate_digest"],
                universe=tuple(record["universe"]),
                broker=record["broker"],
                settings_version=settings.version,
                data_provider=settings.data_provider,
                llm_provider=settings.llm_provider,
                model=settings.model,
                endpoint=settings.endpoint,
                timeout_seconds=settings.timeout_seconds,
                parameters=settings.parameters,
                provenance=settings.provenance,
                credential_versions=versions,
                credential_handles=handles,
                code_version=record["code_version"],
                mandate_snapshot=snapshot,
            )
        except (ConfigurationError, TypeError, ValueError, KeyError):
            raise ConfigurationError("capture is invalid") from None
        root.revalidate()
        return capture


def freeze_capture(
    *,
    root: RootContext,
    subject_id: str,
    mandate_digest: str,
    universe: Sequence[str],
    broker: str,
    settings: RuntimeSettings,
    credential_versions: Mapping[str, int],
    code_version: str,
    mandate_snapshot: Mapping[str, object] | None = None,
) -> FrozenCapture:
    """Freeze validated execution metadata and root-scoped version handles."""
    if not isinstance(root, RootContext):
        raise ConfigurationError("an explicit root context is required")
    root.revalidate()
    if not isinstance(settings, RuntimeSettings):
        raise ConfigurationError("runtime settings are required")
    try:
        canonical_subject = ensure_unique_resource_name(subject_id, [])
    except RootPathError:
        raise ConfigurationError("capture subject is invalid") from None
    if not isinstance(mandate_digest, str) or not _SHA256.fullmatch(mandate_digest):
        raise ConfigurationError("mandate digest is invalid")
    if isinstance(universe, (str, bytes)) or not isinstance(universe, Sequence) or not universe:
        raise ConfigurationError("capture universe is invalid")
    universe_values = tuple(universe)
    if any(not is_capture_ticker(ticker) for ticker in universe_values):
        raise ConfigurationError("capture universe is invalid")
    if len(set(universe_values)) != len(universe_values):
        raise ConfigurationError("capture universe is invalid")
    if not isinstance(broker, str) or broker != "paper":
        raise ConfigurationError("only local-paper captures are supported")
    if not isinstance(credential_versions, Mapping):
        raise ConfigurationError("credential references are invalid")
    raw_versions = dict(credential_versions)
    if any(not isinstance(provider, str) or not _PROVIDER_ID.fullmatch(provider.casefold()) or type(version) is not int or version < 0 for provider, version in raw_versions.items()):
        raise ConfigurationError("credential references are invalid")
    provider_ids = [provider.casefold() for provider in raw_versions]
    if len(set(provider_ids)) != len(provider_ids):
        raise ConfigurationError("credential references are invalid")
    if not isinstance(code_version, str) or not code_version or len(code_version) > 256:
        raise ConfigurationError("code version is invalid")
    if any(ord(char) < 32 or ord(char) == 127 for char in code_version):
        raise ConfigurationError("code version is invalid")

    root_id = _root_id(root)
    snapshot_record, snapshot_bytes = _validated_mandate_snapshot(
        mandate_snapshot,
        subject_id=canonical_subject,
        mandate_digest=mandate_digest.lower(),
    )
    versions = {provider.casefold(): version for provider, version in credential_versions.items()}
    handles = {
        provider: CredentialHandle(
            root_id=root_id,
            provider_id=provider,
            version=version,
        )
        for provider, version in versions.items()
    }
    payload = {
        "schema": 2 if snapshot_record is not None else 1,
        "root_id": root_id,
        "subject_id": canonical_subject,
        "mandate_digest": mandate_digest.lower(),
        "universe": list(universe_values),
        "broker": broker,
        "settings_version": settings.version,
        "settings": settings.to_mapping(),
        "provenance": dict(settings.provenance),
        "credential_versions": versions,
        "code_version": code_version,
    }
    if snapshot_record is not None:
        payload["mandate_snapshot"] = snapshot_record
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    capture_id = uuid4().hex
    capture = FrozenCapture(
        capture_id=capture_id,
        digest=hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        root_id=root_id,
        subject_id=canonical_subject,
        mandate_digest=mandate_digest.lower(),
        universe=universe_values,
        broker=broker,
        settings_version=settings.version,
        data_provider=settings.data_provider,
        llm_provider=settings.llm_provider,
        model=settings.model,
        endpoint=settings.endpoint,
        timeout_seconds=settings.timeout_seconds,
        parameters=settings.parameters,
        provenance=settings.provenance,
        credential_versions=versions,
        credential_handles=handles,
        code_version=code_version,
        mandate_snapshot=snapshot_bytes,
    )
    root.revalidate()
    return capture


def _root_id(root: RootContext) -> str:
    identity = {
        "path": os.path.normcase(os.fspath(root.path)),
        "filesystem": root.filesystem.filesystem,
        "local": root.filesystem.local,
        "cloud_synced": root.filesystem.cloud_synced,
        "device": root.device_identity,
        "object": list(root._root_identity),
        "host": root.host_identity,
    }
    canonical = json.dumps(identity, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _validated_mandate_snapshot(
    value: bytes | Mapping[str, object] | None,
    *,
    subject_id: str,
    mandate_digest: str,
) -> tuple[dict[str, object] | None, bytes | None]:
    if value is None:
        return None, None
    try:
        if isinstance(value, bytes):
            if len(value) > _MAX_MANDATE_SNAPSHOT_BYTES:
                raise ConfigurationError("capture mandate snapshot exceeds its bound")
            raw = json.loads(value.decode("utf-8"))
        elif isinstance(value, Mapping):
            encoded = json.dumps(
                dict(value),
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
                allow_nan=False,
            ).encode("utf-8")
            if len(encoded) > _MAX_MANDATE_SNAPSHOT_BYTES:
                raise ConfigurationError("capture mandate snapshot exceeds its bound")
            raw = json.loads(encoded.decode("utf-8"))
        else:
            raise ConfigurationError("capture mandate snapshot is invalid")
        if not isinstance(raw, dict):
            raise ConfigurationError("capture mandate snapshot is invalid")
        from hedge_fund.fund import FundSpec
        from hedge_fund.pipeline.session import mandate_hash

        spec = FundSpec.model_validate(raw)
        if spec.name != subject_id or mandate_hash(spec) != mandate_digest:
            raise ConfigurationError("capture mandate snapshot does not match identity")
        record = spec.model_dump(mode="json")
        canonical = json.dumps(
            record,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
        if len(canonical) > _MAX_MANDATE_SNAPSHOT_BYTES:
            raise ConfigurationError("capture mandate snapshot exceeds its bound")
        return record, canonical
    except ConfigurationError:
        raise
    except (TypeError, ValueError, UnicodeDecodeError):
        raise ConfigurationError("capture mandate snapshot is invalid") from None
