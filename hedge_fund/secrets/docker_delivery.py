"""Attended host-side delivery to one checked Docker operator."""

from __future__ import annotations

import argparse
import io
import json
import math
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Mapping, TextIO
from urllib.parse import unquote, urlsplit
from uuid import uuid4

from hedge_fund.data.registry import DATA_PROVIDER_ENV_VARS
from hedge_fund.llm.registry import PROVIDER_ENV_VARS
from hedge_fund.runtime.credential_delivery import (
    DeliveryEnvelope,
    DeliveryProtocolError,
    DeliveryReply,
    encode_delivery_frame,
    read_delivery_reply,
)
from hedge_fund.runtime.external_credentials import (
    APPLICATION_PROVIDER_IDS,
    ExternalCredentialError,
    runtime_provider_destinations,
)

_CONTAINER_ID = re.compile(r"[a-fA-F0-9]{64}")
_IMAGE_ID = re.compile(r"sha256:[a-fA-F0-9]{64}")
_REVISION = re.compile(r"(?:[a-fA-F0-9]{40}|[a-fA-F0-9]{64})")
_SOURCE_SHA256 = re.compile(r"[a-fA-F0-9]{64}")
_CONTEXT_NAME = re.compile(r"[A-Za-z0-9._-]{1,64}")
_IDENTIFIER = re.compile(r"[a-z][a-z0-9._-]{0,63}")
_AUTH_VARIABLES = frozenset(
    {
        "OP_SERVICE_ACCOUNT_TOKEN",
        "OP_CONNECT_HOST",
        "OP_CONNECT_TOKEN",
        "OP_CONNECT_TOKEN_FILE",
    }
)
_DOCKER_OVERRIDE_VARIABLES = frozenset({"DOCKER_HOST", "DOCKER_CONTEXT", "DOCKER_TLS_VERIFY", "DOCKER_CERT_PATH"})
_SECRET_VARIABLES = frozenset(PROVIDER_ENV_VARS.values()) | frozenset(DATA_PROVIDER_ENV_VARS.values()) | _AUTH_VARIABLES
_SECRET_ENV_MARKERS = (
    "API_KEY",
    "KEY_REF",
    "TOKEN",
    "SECRET",
    "PASSWORD",
    "CREDENTIAL",
    "AUTHORIZATION",
    "SAXO",
)
_MAPPING_CONFIG_FIELDS = frozenset({"schema", "mappings"})
_MAPPING_FIELDS = frozenset(
    {
        "provider_id",
        "reference",
        "destination",
        "root_id",
        "container_id",
        "image_id",
        "revision",
        "source_sha256",
        "volume_name",
    }
)
_MAX_MAPPING_CONFIG_BYTES = 1024 * 1024
_MAX_MAPPING_COUNT = 64


class DockerCredentialDeliveryError(RuntimeError):
    """Sanitized host delivery failure."""

    def __init__(
        self,
        reason_code: str,
        *,
        reconciliation_state: str | None = None,
        reconciliation_generation: int | None = None,
    ) -> None:
        self.reason_code = reason_code
        self.reconciliation_state = reconciliation_state
        self.reconciliation_generation = reconciliation_generation
        super().__init__(reason_code)


@dataclass(frozen=True, slots=True)
class SourceMapping:
    """One explicit, non-secret 1Password reference mapping."""

    provider_id: str
    reference: str = field(repr=False)
    destination: str
    root_id: str = field(repr=False)
    container_id: str
    image_id: str
    revision: str
    source_sha256: str
    volume_name: str

    def __post_init__(self) -> None:
        if not isinstance(self.provider_id, str) or not _IDENTIFIER.fullmatch(self.provider_id.casefold()):
            raise DockerCredentialDeliveryError("mapping-invalid")
        provider_id = self.provider_id.casefold()
        if provider_id not in APPLICATION_PROVIDER_IDS:
            raise DockerCredentialDeliveryError("provider-not-allowed")
        if not isinstance(self.destination, str) or self.destination.casefold() != provider_id:
            raise DockerCredentialDeliveryError("destination-not-allowed")
        if not isinstance(self.root_id, str) or not re.fullmatch(r"[a-fA-F0-9]{64}", self.root_id):
            raise DockerCredentialDeliveryError("mapping-invalid")
        if not isinstance(self.container_id, str) or not _CONTAINER_ID.fullmatch(self.container_id):
            raise DockerCredentialDeliveryError("mapping-invalid")
        if not isinstance(self.image_id, str) or not _IMAGE_ID.fullmatch(self.image_id):
            raise DockerCredentialDeliveryError("mapping-invalid")
        if not isinstance(self.revision, str) or not _REVISION.fullmatch(self.revision):
            raise DockerCredentialDeliveryError("mapping-invalid")
        if not isinstance(self.source_sha256, str) or not _SOURCE_SHA256.fullmatch(self.source_sha256):
            raise DockerCredentialDeliveryError("mapping-invalid")
        if not isinstance(self.volume_name, str) or not re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", self.volume_name):
            raise DockerCredentialDeliveryError("mapping-invalid")
        _validate_reference(self.reference)
        object.__setattr__(self, "provider_id", provider_id)
        object.__setattr__(self, "destination", provider_id)
        object.__setattr__(self, "root_id", self.root_id.casefold())
        object.__setattr__(self, "container_id", self.container_id.casefold())
        object.__setattr__(self, "image_id", self.image_id.casefold())
        object.__setattr__(self, "revision", self.revision.casefold())
        object.__setattr__(self, "source_sha256", self.source_sha256.casefold())


@dataclass(frozen=True, slots=True)
class DockerCredentialDeliveryResult:
    """Value-free delivery result."""

    provider_id: str
    state: str
    generation: int
    duration_seconds: float
    reason_code: str | None = None


@dataclass(frozen=True, slots=True)
class _TargetIdentity:
    container_id: str
    image_id: str
    revision: str
    source_sha256: str
    volume_name: str
    volume_created_at: str
    started_at: str


class DockerCredentialDelivery:
    """Resolve and deliver one mapped credential through private stdin."""

    def __init__(
        self,
        *,
        runner: Callable | None = None,
        resolver: Callable[[str, float], str] | None = None,
        source_mappings: Mapping[str, SourceMapping] | None = None,
        environment: Mapping[str, str] | None = None,
        timeout_seconds: float = 60.0,
        clock: Callable[[], float] | None = None,
    ) -> None:
        if isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, (int, float)) or not math.isfinite(timeout_seconds) or not 0 < timeout_seconds <= 60:
            raise DockerCredentialDeliveryError("timeout-invalid")
        if runner is not None and not callable(runner):
            raise DockerCredentialDeliveryError("runner-invalid")
        if resolver is not None and not callable(resolver):
            raise DockerCredentialDeliveryError("resolver-invalid")
        if clock is not None and not callable(clock):
            raise DockerCredentialDeliveryError("clock-invalid")
        if source_mappings is None:
            source_mappings = {}
        if not isinstance(source_mappings, Mapping):
            raise DockerCredentialDeliveryError("mapping-invalid")
        normalized: dict[str, SourceMapping] = {}
        for provider, mapping in source_mappings.items():
            if not isinstance(provider, str) or not isinstance(mapping, SourceMapping):
                raise DockerCredentialDeliveryError("mapping-invalid")
            provider_id = provider.casefold()
            if provider_id in normalized or mapping.provider_id != provider_id:
                raise DockerCredentialDeliveryError("mapping-invalid")
            normalized[provider_id] = mapping
        if environment is not None and (not isinstance(environment, Mapping) or any(not isinstance(key, str) or not isinstance(value, str) for key, value in environment.items())):
            raise DockerCredentialDeliveryError("environment-invalid")
        self._runner = runner or subprocess.run
        self._resolver = resolver
        self._source_mappings = normalized
        self._environment = os.environ if environment is None else environment
        self._timeout_seconds = float(timeout_seconds)
        self._clock = clock or time.monotonic

    def deliver(self, container_id: str, provider: str) -> DockerCredentialDeliveryResult:
        started = self._now()
        deadline = started + self._timeout_seconds
        provider_id = _provider_id(provider)
        mapping = self._source_mappings.get(provider_id)
        if mapping is None:
            raise DockerCredentialDeliveryError("provider-not-allowed")
        if mapping.container_id != container_id.casefold():
            raise DockerCredentialDeliveryError("target-not-allowed")
        if any(_is_auth_variable(name) for name in self._environment):
            raise DockerCredentialDeliveryError("ambiguous-authentication")
        if any(isinstance(name, str) and name.upper() in _DOCKER_OVERRIDE_VARIABLES for name in self._environment):
            raise DockerCredentialDeliveryError("ambiguous-docker-configuration")
        if not isinstance(container_id, str) or not _CONTAINER_ID.fullmatch(container_id):
            raise DockerCredentialDeliveryError("target-invalid")
        try:
            before = self._check_target(container_id, deadline)
            if before.image_id != mapping.image_id or before.revision.casefold() != mapping.revision or before.source_sha256 != mapping.source_sha256 or before.volume_name != mapping.volume_name:
                raise DockerCredentialDeliveryError("target-not-allowed")
            preflight = self._exchange(
                container_id,
                DeliveryEnvelope(
                    action="status",
                    provider_id=provider_id,
                    destination=mapping.destination,
                ),
                deadline,
                publish=False,
            )
            if preflight.provider_id != provider_id or preflight.destination != mapping.destination or preflight.root_id != mapping.root_id:
                raise DockerCredentialDeliveryError("target-status-invalid")
            if preflight.state == "denied":
                raise DockerCredentialDeliveryError(preflight.reason_code or "delivery-denied")
            if preflight.state not in {"requires-auth", "available", "revoked"} or preflight.root_id is None or preflight.instance_id is None:
                raise DockerCredentialDeliveryError("target-status-invalid")

            secret = self._resolve(mapping.reference, deadline)
            request = DeliveryEnvelope(
                action="publish",
                provider_id=provider_id,
                destination=mapping.destination,
                root_id=preflight.root_id,
                instance_id=preflight.instance_id,
                expected_generation=preflight.generation,
                delivery_id=uuid4().hex,
                value=secret,
            )
            self._check_local_context(deadline)
            after = self._inspect_target(container_id, deadline)
            if after != before:
                raise DockerCredentialDeliveryError("target-changed")
            try:
                reply = self._exchange(
                    container_id,
                    request,
                    deadline,
                    publish=True,
                )
            except DockerCredentialDeliveryError as exc:
                if exc.reason_code in {"delivery-outcome-unknown", "timeout"}:
                    reconciled = self._reconcile(
                        container_id,
                        provider_id,
                        mapping.destination,
                        deadline,
                    )
                    raise DockerCredentialDeliveryError(
                        "delivery-outcome-unknown",
                        reconciliation_state=reconciled.state if reconciled else None,
                        reconciliation_generation=reconciled.generation if reconciled else None,
                    ) from None
                raise
            if reply.state != "available" or reply.generation != preflight.generation + 1:
                raise DockerCredentialDeliveryError(reply.reason_code or "delivery-denied")
            if reply.root_id != preflight.root_id or reply.instance_id != preflight.instance_id:
                raise DockerCredentialDeliveryError("target-changed")
            return DockerCredentialDeliveryResult(
                provider_id=provider_id,
                state="available",
                generation=reply.generation,
                duration_seconds=max(0.0, self._now() - started),
            )
        except DockerCredentialDeliveryError:
            raise

    def _resolve(self, reference: str, deadline: float) -> str:
        remaining = self._remaining(deadline)
        try:
            if self._resolver is None:
                value = _resolve_op_reference(
                    reference,
                    remaining,
                    environment=_safe_child_environment(self._environment),
                )
            else:
                value = self._resolver(reference, remaining)
        except subprocess.TimeoutExpired:
            raise DockerCredentialDeliveryError("authentication-timeout") from None
        except DockerCredentialDeliveryError:
            raise
        except Exception:
            raise DockerCredentialDeliveryError("credential-resolution-failed") from None
        try:
            DeliveryEnvelope(
                action="publish",
                provider_id="openai",
                destination="openai",
                root_id="a" * 64,
                instance_id="validation",
                expected_generation=0,
                delivery_id="validation",
                value=value,
            )
        except DeliveryProtocolError:
            raise DockerCredentialDeliveryError("invalid-value") from None
        return value

    def _reconcile(
        self,
        container_id: str,
        provider_id: str,
        destination: str,
        deadline: float,
    ) -> DeliveryReply | None:
        try:
            return self._exchange(
                container_id,
                DeliveryEnvelope(
                    action="status",
                    provider_id=provider_id,
                    destination=destination,
                ),
                deadline,
                publish=False,
            )
        except DockerCredentialDeliveryError:
            return None

    def _check_target(self, container_id: str, deadline: float) -> _TargetIdentity:
        self._check_local_context(deadline)
        info = self._run(
            ["docker", "info", "--format", "{{.OSType}}"],
            deadline,
            error_code="docker-unavailable",
        )
        if _text(info.stdout).strip().casefold() != "linux":
            raise DockerCredentialDeliveryError("linux-container-engine-required")
        return self._inspect_target(container_id, deadline)

    def _check_local_context(self, deadline: float) -> None:
        result = self._run(
            ["docker", "context", "show"],
            deadline,
            error_code="docker-context-unavailable",
        )
        context_name = _text(result.stdout).strip()
        if not _CONTEXT_NAME.fullmatch(context_name):
            raise DockerCredentialDeliveryError("docker-context-invalid")
        if os.name == "nt" and context_name.casefold() != "desktop-linux":
            raise DockerCredentialDeliveryError("local-docker-context-required")
        inspected = self._run(
            ["docker", "context", "inspect", context_name],
            deadline,
            error_code="docker-context-unavailable",
        )
        try:
            contexts = json.loads(_text(inspected.stdout))
            endpoint = contexts[0]["Endpoints"]["docker"]["Host"]
        except (ValueError, KeyError, IndexError, TypeError, AttributeError):
            raise DockerCredentialDeliveryError("docker-context-invalid") from None
        if os.name == "nt":
            local_endpoint = isinstance(endpoint, str) and endpoint.casefold() == "npipe:////./pipe/dockerdesktoplinuxengine"
        else:
            local_endpoint = isinstance(endpoint, str) and endpoint.casefold().startswith("unix://")
        if not local_endpoint:
            raise DockerCredentialDeliveryError("remote-docker-context-denied")

    def _inspect_target(self, container_id: str, deadline: float) -> _TargetIdentity:
        result = self._run(
            ["docker", "inspect", "--type", "container", container_id],
            deadline,
            error_code="target-unavailable",
        )
        try:
            containers = json.loads(_text(result.stdout))
            if not isinstance(containers, list) or len(containers) != 1:
                raise ValueError
            container = containers[0]
            config = container["Config"]
            state = container["State"]
            host_config = container["HostConfig"]
            labels = config["Labels"]
            mounts = container["Mounts"]
            env = config["Env"]
            container_identity = container["Id"]
            image_id = container["Image"]
            revision = labels["org.opencontainers.image.revision"]
            source_hash = labels["org.opencontainers.image.source-sha256"]
            started_at = state["StartedAt"]
            volume = self._validate_operator_container(
                config=config,
                state=state,
                host_config=host_config,
                labels=labels,
                mounts=mounts,
                env=env,
                container_identity=container_identity,
            )
        except (KeyError, TypeError, ValueError, AttributeError):
            raise DockerCredentialDeliveryError("target-invalid") from None
        if not isinstance(container_identity, str) or container_identity.casefold() != container_id.casefold() or not isinstance(image_id, str) or not _IMAGE_ID.fullmatch(image_id) or not isinstance(revision, str) or not _REVISION.fullmatch(revision) or not isinstance(source_hash, str) or not _SOURCE_SHA256.fullmatch(source_hash) or not isinstance(started_at, str) or not started_at:
            raise DockerCredentialDeliveryError("target-invalid")
        volume_created_at = self._inspect_volume(volume, deadline)
        return _TargetIdentity(
            container_id=container_identity.casefold(),
            image_id=image_id.casefold(),
            revision=revision,
            source_sha256=source_hash.casefold(),
            volume_name=volume,
            volume_created_at=volume_created_at,
            started_at=started_at,
        )

    def _inspect_volume(self, volume_name: str, deadline: float) -> str:
        result = self._run(
            ["docker", "volume", "inspect", volume_name],
            deadline,
            error_code="target-volume-invalid",
        )
        try:
            volumes = json.loads(_text(result.stdout))
            if not isinstance(volumes, list) or len(volumes) != 1:
                raise ValueError
            volume = volumes[0]
            if volume.get("Name") != volume_name or volume.get("Driver") != "local" or volume.get("Scope") != "local" or not isinstance(volume.get("CreatedAt"), str) or not volume["CreatedAt"]:
                raise ValueError
            return volume["CreatedAt"]
        except (ValueError, KeyError, TypeError, AttributeError):
            raise DockerCredentialDeliveryError("target-volume-invalid") from None

    @staticmethod
    def _validate_operator_container(*, config, state, host_config, labels, mounts, env, container_identity) -> str:
        if not isinstance(container_identity, str) or not _CONTAINER_ID.fullmatch(container_identity):
            raise ValueError
        if state.get("Status") != "running":
            raise ValueError
        if labels.get("com.docker.compose.service") != "web-operator":
            raise ValueError
        entrypoint = config.get("Entrypoint")
        if not isinstance(entrypoint, list) or len(entrypoint) < 3 or Path(entrypoint[0]).name != "aihf-web-supervisor" or entrypoint[1:3] != ["--root", "/data"]:
            raise ValueError
        if config.get("User", "") not in {"", "0", "root"}:
            raise ValueError
        if not isinstance(host_config.get("Tmpfs"), dict) or "/tmp" not in host_config["Tmpfs"]:
            raise ValueError
        if not isinstance(env, list) or any(not isinstance(entry, str) for entry in env):
            raise ValueError
        if any(_is_secret_environment_key(entry.split("=", 1)[0]) for entry in env):
            raise ValueError
        if "HEDGE_FUND_RUNTIME_ROLE=web-operator" not in env:
            raise ValueError
        provider_allowlist = [entry.split("=", 1)[1] for entry in env if entry.split("=", 1)[0] == "HEDGE_FUND_RUNTIME_PROVIDERS" and "=" in entry]
        if len(provider_allowlist) != 1:
            raise ValueError
        try:
            runtime_provider_destinations(provider_allowlist[0])
        except ExternalCredentialError:
            raise ValueError from None
        if not isinstance(mounts, list) or len(mounts) != 1:
            raise ValueError
        root_mount = mounts[0]
        if not isinstance(root_mount, dict) or root_mount.get("Type") != "volume" or root_mount.get("Destination") != "/data" or root_mount.get("RW") is not True or not isinstance(root_mount.get("Name"), str) or not re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", root_mount["Name"]):
            raise ValueError
        return root_mount["Name"]

    def _exchange(
        self,
        container_id: str,
        request: DeliveryEnvelope,
        deadline: float,
        *,
        publish: bool,
    ) -> DeliveryReply:
        frame = encode_delivery_frame(request)
        try:
            result = self._run(
                [
                    "docker",
                    "exec",
                    "--interactive",
                    container_id,
                    "python",
                    "-m",
                    "hedge_fund.runtime.credential_delivery",
                    "--receive",
                ],
                deadline,
                input_data=frame,
                error_code="delivery-outcome-unknown" if publish else "delivery-transport-unavailable",
            )
        except DockerCredentialDeliveryError:
            raise
        try:
            reply = read_delivery_reply(io.BytesIO(_bytes(result.stdout)))
        except DeliveryProtocolError:
            if publish:
                raise DockerCredentialDeliveryError("delivery-outcome-unknown") from None
            raise DockerCredentialDeliveryError("delivery-transport-unavailable") from None
        if result.returncode not in {0, 2} or ((result.returncode == 2) != (reply.state == "denied")):
            if publish:
                raise DockerCredentialDeliveryError("delivery-outcome-unknown")
            raise DockerCredentialDeliveryError("delivery-transport-unavailable")
        return reply

    def _run(self, args: list[str], deadline: float, *, input_data: bytes | None = None, error_code: str):
        timeout = self._remaining(deadline)
        kwargs: dict[str, object] = {
            "capture_output": True,
            "timeout": timeout,
            "check": False,
            "env": _safe_child_environment(self._environment),
        }
        if input_data is not None:
            kwargs["input"] = input_data
        try:
            result = self._runner(args, **kwargs)
        except subprocess.TimeoutExpired:
            raise DockerCredentialDeliveryError("timeout" if error_code not in {"delivery-outcome-unknown"} else error_code) from None
        except Exception:
            raise DockerCredentialDeliveryError(error_code) from None
        if not isinstance(result, subprocess.CompletedProcess):
            raise DockerCredentialDeliveryError(error_code)
        if result.returncode != 0 and not (args[:2] == ["docker", "exec"] and result.returncode == 2):
            raise DockerCredentialDeliveryError(error_code)
        return result

    def _remaining(self, deadline: float) -> float:
        remaining = deadline - self._now()
        if remaining <= 0:
            raise DockerCredentialDeliveryError("timeout")
        return remaining

    def _now(self) -> float:
        value = self._clock()
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise DockerCredentialDeliveryError("clock-invalid")
        return float(value)


def default_mapping_config_path() -> Path:
    """Return user-local non-secret mapping metadata path."""
    return Path.home() / ".hedge-fund" / "op-runtime-mappings.json"


def load_source_mappings(path: Path | str | None = None) -> dict[str, SourceMapping]:
    """Load bounded non-secret mappings; missing file means disabled."""
    try:
        selected_path = default_mapping_config_path() if path is None else Path(path)
        if not selected_path.is_file():
            if not selected_path.exists():
                return {}
            raise DockerCredentialDeliveryError("mapping-config-unavailable")
        with selected_path.open("rb") as stream:
            payload = stream.read(_MAX_MAPPING_CONFIG_BYTES + 1)
    except FileNotFoundError:
        return {}
    except (OSError, TypeError, ValueError):
        raise DockerCredentialDeliveryError("mapping-config-unavailable") from None
    if len(payload) > _MAX_MAPPING_CONFIG_BYTES:
        raise DockerCredentialDeliveryError("mapping-config-invalid")
    try:
        record = json.loads(payload.decode("utf-8"), object_pairs_hook=_unique_json_object)
        if not isinstance(record, dict) or set(record) != _MAPPING_CONFIG_FIELDS or type(record["schema"]) is not int or record["schema"] != 1:
            raise ValueError
        rows = record["mappings"]
        if not isinstance(rows, list) or len(rows) > _MAX_MAPPING_COUNT:
            raise ValueError
        mappings: dict[str, SourceMapping] = {}
        for row in rows:
            if not isinstance(row, dict) or set(row) != _MAPPING_FIELDS:
                raise ValueError
            mapping = SourceMapping(**row)
            if mapping.provider_id in mappings:
                raise ValueError
            mappings[mapping.provider_id] = mapping
        return mappings
    except (DockerCredentialDeliveryError, RecursionError, TypeError, ValueError, UnicodeDecodeError, json.JSONDecodeError):
        raise DockerCredentialDeliveryError("mapping-config-invalid") from None


def _unique_json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError
        result[key] = value
    return result


def _provider_id(value: str) -> str:
    if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value.casefold()):
        raise DockerCredentialDeliveryError("provider-invalid")
    provider = value.casefold()
    if provider not in APPLICATION_PROVIDER_IDS:
        raise DockerCredentialDeliveryError("provider-not-allowed")
    return provider


def _is_auth_variable(name: object) -> bool:
    if not isinstance(name, str):
        return False
    normalized = name.upper()
    return normalized in _AUTH_VARIABLES or normalized.startswith("OP_SESSION_")


def _is_secret_environment_key(name: str) -> bool:
    normalized = name.upper()
    return normalized in _SECRET_VARIABLES or normalized.startswith("OP_SESSION_") or any(marker in normalized for marker in _SECRET_ENV_MARKERS)


def _safe_child_environment(environment: Mapping[str, str]) -> dict[str, str]:
    return {key: value for key, value in environment.items() if not _is_secret_environment_key(key)}


def _validate_reference(value: str) -> None:
    if not isinstance(value, str) or any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise DockerCredentialDeliveryError("reference-invalid")
    try:
        parsed = urlsplit(value)
    except ValueError:
        raise DockerCredentialDeliveryError("reference-invalid") from None
    segments = [unquote(segment) for segment in parsed.path.strip("/").split("/") if segment]
    if parsed.scheme != "op" or not parsed.netloc or "@" in parsed.netloc or ":" in parsed.netloc or parsed.query or parsed.fragment or len(segments) != 2:
        raise DockerCredentialDeliveryError("reference-invalid")
    if any(not segment or any(ord(char) < 32 or ord(char) == 127 or char in "/\\" for char in segment) for segment in [parsed.netloc, *segments]):
        raise DockerCredentialDeliveryError("reference-invalid")


def _resolve_op_reference(
    reference: str,
    timeout: float,
    *,
    environment: Mapping[str, str],
) -> str:
    executable = shutil.which("op")
    if executable is None:
        raise DockerCredentialDeliveryError("cli-missing")
    try:
        result = subprocess.run(
            [executable, "read", "--no-newline", reference],
            capture_output=True,
            timeout=timeout,
            check=False,
            shell=False,
            env=_safe_child_environment(environment),
        )
    except subprocess.TimeoutExpired:
        raise
    except (OSError, subprocess.SubprocessError):
        raise DockerCredentialDeliveryError("credential-resolution-failed") from None
    if result.returncode != 0:
        raise DockerCredentialDeliveryError("credential-resolution-failed")
    if not isinstance(result.stdout, bytes) or len(result.stdout) > 16 * 1024:
        raise DockerCredentialDeliveryError("invalid-value")
    try:
        return result.stdout.decode("utf-8")
    except (AttributeError, UnicodeDecodeError):
        raise DockerCredentialDeliveryError("invalid-value") from None


def _bytes(value: bytes | str) -> bytes:
    if isinstance(value, bytes):
        return value
    if isinstance(value, str):
        return value.encode("utf-8")
    return b""


def _text(value: bytes | str) -> str:
    try:
        return _bytes(value).decode("utf-8")
    except UnicodeDecodeError:
        raise DockerCredentialDeliveryError("docker-response-invalid") from None


def main(
    argv: list[str] | None = None,
    *,
    runner: Callable | None = None,
    resolver: Callable[[str, float], str] | None = None,
    environment: Mapping[str, str] | None = None,
    stdout: TextIO | None = None,
) -> int:
    parser = argparse.ArgumentParser(prog="aihf-op-deliver")
    parser.add_argument("--config", type=Path, default=None)
    parser.add_argument("--provider", required=True)
    arguments = parser.parse_args(argv)
    output = sys.stdout if stdout is None else stdout
    try:
        provider_id = _provider_id(arguments.provider)
        mappings = load_source_mappings(arguments.config)
        mapping = mappings.get(provider_id)
        if mapping is None:
            raise DockerCredentialDeliveryError("provider-not-allowed")
        result = DockerCredentialDelivery(
            runner=runner,
            resolver=resolver,
            source_mappings=mappings,
            environment=environment,
        ).deliver(
            mapping.container_id,
            provider_id,
        )
    except DockerCredentialDeliveryError as exc:
        output.write(f"delivery=denied reason={exc.reason_code}\n")
        return 2
    output.write(f"delivery=available provider={result.provider_id} generation={result.generation}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
