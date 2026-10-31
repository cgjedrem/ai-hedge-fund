"""Credential helpers shared by headless and web entry points."""

from __future__ import annotations

import os
import re
import stat
import unicodedata
from pathlib import Path

from hedge_fund import paths
from hedge_fund.llm import env_var_for

write_atomic = paths.write_atomic


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
