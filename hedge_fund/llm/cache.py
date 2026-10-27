"""Prompt cache — one JSON file per LLM decision.

This is deliberately three things at once (a locked design decision):
1. a cache: a backtest re-running an agent over an unchanged snapshot costs $0;
2. the persistence record: the EXACT prompt + response behind every Signal,
   for replay and audit;
3. the debug trail: failed parses keep the raw response on disk.

Files live under ~/.hedge-fund/cache/llm/, keyed by a hash of
(agent, model, prompt).
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from hedge_fund.paths import CACHE_DIR

DEFAULT_CACHE_DIR = CACHE_DIR / "llm"


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
    def __init__(self, cache_dir: Path | str = DEFAULT_CACHE_DIR) -> None:
        self._dir = Path(cache_dir)

    def get(self, key: str) -> dict | None:
        path = self._dir / f"{key}.json"
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            return None  # corrupt cache entry -> treat as miss, will be rewritten

    def put(self, key: str, record: dict) -> None:
        self._dir.mkdir(parents=True, exist_ok=True)
        record = {**record, "created_at": datetime.now(timezone.utc).isoformat()}
        path = self._dir / f"{key}.json"
        path.write_text(json.dumps(record, indent=2))
