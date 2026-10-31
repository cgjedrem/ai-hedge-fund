"""Prompt cache — one JSON file per LLM decision.

This is deliberately three things at once (a locked design decision):
1. a cache: a backtest re-running an agent over an unchanged snapshot costs $0;
2. the persistence record: the EXACT prompt + response behind every Signal,
   for replay and audit;
3. the debug trail: failed parses keep the raw response on disk.

Files live under the configured root's cache/llm/, keyed by a hash of
(agent, model, prompt).
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from hedge_fund import paths
from hedge_fund.runtime.root import RootConfigurationError


def _default_cache_dir() -> Path:
    if paths.CACHE_DIR is None:
        raise RootConfigurationError("an explicit root must be configured first")
    return paths.CACHE_DIR / "llm"


DEFAULT_CACHE_DIR = _default_cache_dir() if paths.CACHE_DIR is not None else None


def prompt_key(agent: str, model: str, system: str, user: str, salt: str = "") -> str:
    """Cache key for one (agent, model, prompt) combination.

    `salt` namespaces keys that differ in request semantics the prompts
    don't carry — an ensemble sample index or a sampling temperature. An
    empty salt (the default) yields the legacy key, so existing cache
    files stay valid.
    """
    payload = f"{agent}|{model}|{system}|{user}"
    if salt:
        payload = f"{payload}|{salt}"
    return hashlib.sha256(payload.encode()).hexdigest()[:24]


def salted_key(base: str, salt: str) -> str:
    """Namespace an existing cache key (e.g. a provider's own cache_key)
    with request semantics the prompts don't carry — an ensemble sample
    index or a sampling temperature."""
    return hashlib.sha256(f"{base}|{salt}".encode()).hexdigest()[:24]


class PromptCache:
    def __init__(self, cache_dir: Path | str | None = None) -> None:
        self._dir = Path(cache_dir) if cache_dir is not None else _default_cache_dir()

    def get(self, key: str) -> dict | None:
        path = self._dir / f"{key}.json"
        if paths.file_mtime(path) is None:
            return None
        try:
            return json.loads(paths.read_text(path))
        except (json.JSONDecodeError, OSError):
            return None  # corrupt cache entry -> treat as miss, will be rewritten

    def put(self, key: str, record: dict) -> None:
        record = {**record, "created_at": datetime.now(timezone.utc).isoformat()}
        path = self._dir / f"{key}.json"
        paths.write_text(path, json.dumps(record, indent=2))
