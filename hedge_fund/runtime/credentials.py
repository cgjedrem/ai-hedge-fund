"""Credential helpers shared by headless and web entry points."""

from __future__ import annotations

import json
import os
import re
import stat
import unicodedata
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from hedge_fund import paths
from hedge_fund.llm import PROVIDER_ENV_VARS, env_var_for
from hedge_fund.runtime.admission import LOCK_DIRECTORY, AdmissionCoordinator, AdmissionError
from hedge_fund.runtime.root import PRIVATE_ROOT, RootContext

write_atomic = paths.write_atomic
_CREDENTIAL_ROOT = f"{PRIVATE_ROOT}/credentials"
_CREDENTIAL_INDEX = f"{_CREDENTIAL_ROOT}/index.json"
_MAX_CREDENTIAL_BYTES = 8192
_MAX_CREDENTIAL_VERSION = 2**31 - 1


class CredentialStoreError(RuntimeError):
    """Credential storage or validation failed."""


class CredentialVersionConflict(CredentialStoreError):
    """Credential version changed."""


class CredentialStore:
    """Persist immutable secret versions under verified private storage."""

    def __init__(self, root: RootContext, admission: AdmissionCoordinator) -> None:
        if not isinstance(root, RootContext) or not isinstance(admission, AdmissionCoordinator):
            raise CredentialStoreError("root and admission contexts are required")
        if admission.root is not root or not root.verify_private_storage():
            raise CredentialStoreError("private credential storage is unverified")
        self._root = root
        self._admission = admission

    def status(self) -> dict[str, dict[str, int | bool]]:
        with self._snapshot() as index:
            return {
                provider: {
                    "version": index["providers"].get(
                        provider.casefold(),
                        {"version": 0, "configured": False},
                    )["version"],
                    "configured": index["providers"].get(
                        provider.casefold(),
                        {"version": 0, "configured": False},
                    )["configured"],
                }
                for provider in sorted(PROVIDER_ENV_VARS, key=str.casefold)
            }

    def version(self, provider: str) -> tuple[int, bool]:
        provider_id = _provider_id(provider)
        with self._snapshot() as index:
            record = index["providers"].get(
                provider_id,
                {"version": 0, "configured": False},
            )
            return record["version"], record["configured"]

    def save(self, provider: str, value: str, *, expected_version: int) -> int:
        provider_id = _provider_id(provider)
        secret = _validate_credential(value)
        if type(expected_version) is not int or expected_version < 0:
            raise CredentialStoreError("expected credential version is invalid")
        payload = _credential_bytes(provider_id, 1, secret)
        if len(payload) > _MAX_CREDENTIAL_BYTES:
            raise CredentialStoreError("credential exceeds its bound")
        try:
            with self._admission.registry_lock(timeout=5.0):
                index = self._read_index()
                current = index["providers"].get(
                    provider_id,
                    {"version": 0, "configured": False},
                )
                if current["version"] != expected_version:
                    raise CredentialVersionConflict("credential version changed")
                version = current["version"] + 1
                if version > _MAX_CREDENTIAL_VERSION:
                    raise CredentialStoreError("credential version exceeds its bound")
                payload = _credential_bytes(provider_id, version, secret)
                relative = _credential_path(provider_id, version)
                while self._exists(relative):
                    version += 1
                    if version > _MAX_CREDENTIAL_VERSION:
                        raise CredentialStoreError("credential version exceeds its bound")
                    payload = _credential_bytes(provider_id, version, secret)
                    relative = _credential_path(provider_id, version)
                self._write_bytes(relative, payload)
                index["providers"][provider_id] = {
                    "version": version,
                    "configured": True,
                }
                self._write_index(index)
                return version
        except AdmissionError as exc:
            raise CredentialStoreError("credential writer admission is unavailable") from exc

    def delete(self, provider: str, *, expected_version: int) -> int:
        provider_id = _provider_id(provider)
        if type(expected_version) is not int or expected_version < 0:
            raise CredentialStoreError("expected credential version is invalid")
        try:
            with self._admission.registry_lock(timeout=5.0):
                index = self._read_index()
                current = index["providers"].get(
                    provider_id,
                    {"version": 0, "configured": False},
                )
                if current["version"] != expected_version:
                    raise CredentialVersionConflict("credential version changed")
                version = current["version"] + 1
                if version > _MAX_CREDENTIAL_VERSION:
                    raise CredentialStoreError("credential version exceeds its bound")
                index["providers"][provider_id] = {
                    "version": version,
                    "configured": False,
                }
                self._write_index(index)
                return version
        except AdmissionError as exc:
            raise CredentialStoreError("credential writer admission is unavailable") from exc

    def read_version(self, provider: str, version: int) -> str | None:
        provider_id = _provider_id(provider)
        if type(version) is not int or not 0 <= version <= _MAX_CREDENTIAL_VERSION:
            raise CredentialStoreError("credential version is invalid")
        if version == 0:
            return None
        if not self._root.verify_private_storage():
            raise CredentialStoreError("private credential storage is unverified")
        relative = _credential_path(provider_id, version)
        try:
            if self._root.file_info(relative).size > _MAX_CREDENTIAL_BYTES:
                raise CredentialStoreError("credential storage exceeds its bound")
            raw = self._root.read_bytes(relative)
            record = json.loads(raw.decode("utf-8"))
        except CredentialStoreError:
            raise
        except (OSError, UnicodeError, ValueError) as exc:
            raise CredentialStoreError("credential version is unavailable") from exc
        if (
            not isinstance(record, dict)
            or set(record) != {"schema", "provider", "version", "value"}
            or type(record.get("schema")) is not int
            or record["schema"] != 1
            or record.get("provider") != provider_id
            or record.get("version") != version
        ):
            raise CredentialStoreError("credential version is invalid")
        return _validate_credential(record["value"])

    @contextmanager
    def _snapshot(self) -> Iterator[dict]:
        self._root.revalidate()
        if not self._root.verify_private_storage():
            raise CredentialStoreError("private credential storage is unverified")
        try:
            self._root.file_info(_CREDENTIAL_INDEX)
        except FileNotFoundError:
            try:
                self._root.file_info(f"{LOCK_DIRECTORY}/registry.lock")
            except FileNotFoundError:
                yield {"schema": 1, "providers": {}}
                return
        try:
            with self._admission.registry_read_lock(timeout=5.0):
                yield self._read_index()
        except AdmissionError as exc:
            raise CredentialStoreError("credential admission lock is unavailable") from exc

    def _read_index(self) -> dict:
        try:
            if self._root.file_info(_CREDENTIAL_INDEX).size > _MAX_CREDENTIAL_BYTES:
                raise CredentialStoreError("credential index exceeds its bound")
            raw = self._root.read_bytes(_CREDENTIAL_INDEX)
        except FileNotFoundError:
            return {"schema": 1, "providers": {}}
        except CredentialStoreError:
            raise
        except OSError as exc:
            raise CredentialStoreError("credential index is unavailable") from exc
        try:
            index = json.loads(raw.decode("utf-8"))
        except (UnicodeError, ValueError) as exc:
            raise CredentialStoreError("credential index is invalid") from exc
        if not isinstance(index, dict) or set(index) != {"schema", "providers"}:
            raise CredentialStoreError("credential index is invalid")
        if type(index.get("schema")) is not int or index["schema"] != 1:
            raise CredentialStoreError("credential index is invalid")
        providers = index.get("providers")
        if not isinstance(providers, dict) or set(providers) - {
            provider.casefold() for provider in PROVIDER_ENV_VARS
        }:
            raise CredentialStoreError("credential index is invalid")
        for provider, record in providers.items():
            if (
                not isinstance(record, dict)
                or set(record) != {"version", "configured"}
                or type(record.get("version")) is not int
                or not 0 <= record["version"] <= _MAX_CREDENTIAL_VERSION
                or type(record.get("configured")) is not bool
                or (record["configured"] and record["version"] == 0)
            ):
                raise CredentialStoreError("credential index is invalid")
        return index

    def _write_index(self, index: dict) -> None:
        payload = json.dumps(index, sort_keys=True, separators=(",", ":")).encode("utf-8")
        if len(payload) > _MAX_CREDENTIAL_BYTES:
            raise CredentialStoreError("credential index exceeds its bound")
        self._write_bytes(_CREDENTIAL_INDEX, payload)

    def _write_bytes(self, relative: str, payload: bytes) -> None:
        parent = relative.rsplit("/", 1)[0]
        self._root.mkdir(parent, parents=True, mode=0o700)
        try:
            self._root.write_bytes(relative, payload, mode=stat.S_IRUSR | stat.S_IWUSR)
        except OSError as exc:
            raise CredentialStoreError("credential storage write failed") from exc

    def _exists(self, relative: str) -> bool:
        try:
            self._root.file_info(relative)
        except FileNotFoundError:
            return False
        except OSError as exc:
            raise CredentialStoreError("credential path is unavailable") from exc
        return True


def _provider_id(provider: str) -> str:
    if not isinstance(provider, str):
        raise CredentialStoreError("credential provider is invalid")
    provider_id = provider.casefold()
    if provider_id not in {name.casefold() for name in PROVIDER_ENV_VARS}:
        raise CredentialStoreError("credential provider is invalid")
    return provider_id


def _validate_credential(value: str) -> str:
    if not isinstance(value, str) or not value or not value.strip():
        raise CredentialStoreError("credential value is invalid")
    if any(unicodedata.category(char) in {"Cc", "Cf"} for char in value):
        raise CredentialStoreError("credential value is invalid")
    if len(value.encode("utf-8")) > 4096:
        raise CredentialStoreError("credential value exceeds its bound")
    return value


def _credential_bytes(provider: str, version: int, value: str) -> bytes:
    return json.dumps(
        {
            "schema": 1,
            "provider": provider,
            "version": version,
            "value": value,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def _credential_path(provider: str, version: int) -> str:
    return f"{_CREDENTIAL_ROOT}/{provider}/{version}.json"


def save_credential(env_var: str, value: str, *, path: str | Path | None = None) -> Path:
    if not isinstance(env_var, str) or not re.fullmatch(r"[A-Z][A-Z0-9_]*", env_var):
        raise ValueError("environment variable name is invalid")
    if not isinstance(value, str) or any(unicodedata.category(char) in {"Cc", "Cf"} for char in value):
        raise ValueError("credential value contains control characters")
    if path is None:
        if paths.ENV_PATH is None:
            raise ValueError("an explicit credential root is required")
        candidate = Path(paths.ENV_PATH)
    else:
        candidate = Path(path)
    line = f"{env_var}={_quote(value)}"
    if candidate.exists():
        original = candidate.read_text(encoding="utf-8")
        pattern = re.compile(rf"^[ \t]*#?[ \t]*(?:export[ \t]+)?{re.escape(env_var)}[ \t]*=.*$", re.MULTILINE)
        updated, count = pattern.subn(lambda _: line, original, count=1)
        if count == 0:
            separator = "" if not original or original.endswith("\n") else "\n"
            updated = f"{original}{separator}{line}\n"
    else:
        updated = f"{line}\n"
    candidate.parent.mkdir(parents=True, exist_ok=True)
    write_atomic(candidate, updated, mode=stat.S_IRUSR | stat.S_IWUSR)
    os.environ[env_var] = value
    return candidate


def missing_key(provider: str) -> str | None:
    if not isinstance(provider, str):
        raise TypeError("provider must be text")
    name = env_var_for(provider)
    if name is None or os.environ.get(name):
        return None
    return name


def masked(value: str) -> str:
    if not isinstance(value, str):
        raise TypeError("credential value must be text")
    if len(value) <= 12:
        return "•" * len(value)
    return f"{value[:6]}{'•' * 8}{value[-4:]}"


def _quote(value: str) -> str:
    if value and not re.search(r"[\s#'\"\\]", value):
        return value
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'
