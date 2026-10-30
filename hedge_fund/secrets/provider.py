"""1Password CLI-backed secret resolution and rotation."""

from __future__ import annotations

import json
import math
import subprocess
from typing import Callable
from urllib.parse import unquote, urlparse


class SecretProviderError(RuntimeError):
    """Secret lookup or persistence failed."""


class SecretProvider:
    def __init__(
        self,
        *,
        runner: Callable | None = None,
        timeout: float = 15.0,
    ) -> None:
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("timeout must be positive")
        self._runner = runner or subprocess.run
        self._timeout = timeout

    def resolve(self, variable: str, reference: str) -> str:
        if not variable or not isinstance(reference, str) or not reference.startswith("op://"):
            raise SecretProviderError(f"{variable or 'secret'}: expected an op:// reference")
        try:
            result = self._runner(
                ["op", "read", reference],
                capture_output=True,
                text=True,
                check=True,
                timeout=self._timeout,
            )
            value = result if isinstance(result, str) else result.stdout
        except Exception:
            raise SecretProviderError(f"{variable}: cannot resolve 1Password reference") from None
        value = value.strip()
        if not value:
            raise SecretProviderError(f"{variable}: 1Password reference is empty or missing")
        return value

    def write_back(self, variable: str, reference: str, value: str) -> None:
        vault, item, field = _reference_parts(variable, reference)
        if not isinstance(value, str) or not value:
            raise SecretProviderError(f"{variable}: refusing to persist an empty secret")
        try:
            result = self._runner(
                ["op", "item", "get", item, "--format=json", "--reveal", "--vault", vault],
                capture_output=True,
                text=True,
                check=True,
                timeout=self._timeout,
            )
            raw_item = result if isinstance(result, str) else result.stdout
            template = json.loads(raw_item)
            field_data = _find_field(template, field)
            field_data["value"] = value
            self._runner(
                ["op", "item", "edit", item, "--vault", vault],
                input=json.dumps(template),
                capture_output=True,
                text=True,
                check=True,
                timeout=self._timeout,
            )
        except Exception:
            raise SecretProviderError(f"{variable}: cannot persist rotated 1Password secret") from None


def _find_field(item: object, field: str) -> dict:
    matches: list[dict] = []

    def visit(value: object) -> None:
        if isinstance(value, dict):
            identifiers = (value.get("id"), value.get("label"), value.get("name"))
            if field in identifiers and "value" in value:
                matches.append(value)
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(item)
    if len(matches) != 1:
        raise ValueError("1Password item field is missing or ambiguous")
    return matches[0]


def _reference_parts(variable: str, reference: str) -> tuple[str, str, str]:
    if not isinstance(reference, str):
        raise SecretProviderError(f"{variable}: expected an op:// reference")
    parsed = urlparse(reference)
    parts = [unquote(part) for part in parsed.path.strip("/").split("/") if part]
    if parsed.scheme != "op" or not parsed.netloc or len(parts) < 2:
        raise SecretProviderError(f"{variable}: expected an op://vault/item/field reference")
    return unquote(parsed.netloc), parts[0], parts[-1]
