"""Which models exist, who serves them, and what key each one needs.

Sourced from ``api_models.json`` next to this module — one list, so the
picker and the clients cannot drift apart.

This lives in ``hedge_fund/llm`` and not ``hedge_fund/tui`` because it states facts about
providers, not about presentation — the TUI imports it, never the reverse.
(It also has to: ``hedge_fund.signals`` needs a client, and routing that through the
TUI package would close an import cycle.)
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

API_MODELS_PATH = Path(__file__).resolve().parent / "api_models.json"
_CAPABILITIES = frozenset({"chat", "embedding", "ocr"})
_COST_CLASSES = frozenset({"local", "paid-cloud"})

# Provider names are the strings used in api_models.json.
PROVIDER_ENV_VARS = {
    "Anthropic": "ANTHROPIC_API_KEY",
    "OpenAI": "OPENAI_API_KEY",
    "xAI": "XAI_API_KEY",
    "DeepSeek": "DEEPSEEK_API_KEY",
    "Google": "GOOGLE_API_KEY",
    "Kimi": "KIMI_API_KEY",
    "TypeSafe": "TYPESAFE_API_KEY",
}

# Providers that need no API key — local or self-hosted runtimes.
KEYLESS_PROVIDERS = frozenset({"Ollama"})

# Providers with a production transport guarded at the HTTP boundary.
SUPPORTED_PROVIDERS = frozenset(
    {
        "OpenAI",
        "xAI",
        "DeepSeek",
        "Kimi",
        "TypeSafe",
        "Ollama",
    }
)

_FALLBACK = ("Gemma 3 4B", "gemma3:4b", "Ollama")


@dataclass(frozen=True, slots=True)
class ModelCatalogEntry:
    display_name: str
    model_name: str
    provider: str
    capability: str | None = None
    cost_class: str | None = None


def _validated_entries(value: object) -> list[ModelCatalogEntry]:
    if not isinstance(value, list):
        raise ValueError("model catalog is invalid")
    entries = []
    seen = set()
    for item in value:
        if not isinstance(item, dict):
            raise ValueError("model catalog is invalid")
        display_name = item.get("display_name")
        model_name = item.get("model_name")
        provider = item.get("provider")
        capability = item.get("capability")
        cost_class = item.get("cost_class")
        if any(not isinstance(text, str) or not text or text != text.strip() for text in (display_name, model_name, provider)):
            raise ValueError("model catalog is invalid")
        if model_name in seen:
            raise ValueError("model catalog is invalid")
        if provider == "Ollama" and (capability not in _CAPABILITIES or cost_class not in _COST_CLASSES):
            raise ValueError("model catalog is invalid")
        if capability is not None and capability not in _CAPABILITIES:
            raise ValueError("model catalog is invalid")
        if cost_class is not None and cost_class not in _COST_CLASSES:
            raise ValueError("model catalog is invalid")
        seen.add(model_name)
        entries.append(ModelCatalogEntry(display_name, model_name, provider, capability, cost_class))
    return entries


_FALLBACK_ENTRY = ModelCatalogEntry(*_FALLBACK, capability="chat", cost_class="local")


def load_api_model_entries() -> list[ModelCatalogEntry]:
    """The validated catalog, including capability and cost classifiers."""
    try:
        entries = _validated_entries(json.loads(API_MODELS_PATH.read_text(encoding="utf-8")))
    except (OSError, ValueError, TypeError, KeyError):
        return [_FALLBACK_ENTRY]
    return entries or [_FALLBACK_ENTRY]


def load_api_models() -> list[tuple[str, str, str]]:
    """The registry as (display name, model id, provider), file order kept.

    Falls back to the built-in default alone if the file is missing or
    malformed — a broken registry should cost you the picker, not the app.
    """
    return [(entry.display_name, entry.model_name, entry.provider) for entry in load_api_model_entries()]


def catalog_entry_for(model_id: str) -> ModelCatalogEntry | None:
    """Return exact catalog metadata. Unknown/non-string id → None."""
    if not isinstance(model_id, str) or not model_id:
        return None
    return next(
        (entry for entry in load_api_model_entries() if entry.model_name == model_id),
        None,
    )


def provider_for(model_id: str) -> str | None:
    """Which provider serves a model id. None if it is not in the registry —
    a hand-exported HEDGE_FUND_LLM_MODEL should not be second-guessed."""
    entry = catalog_entry_for(model_id)
    return None if entry is None else entry.provider


def env_var_for(provider: str) -> str | None:
    """The environment variable a provider's key is read from."""
    return PROVIDER_ENV_VARS.get(provider)


def is_supported(provider: str) -> bool:
    """Can v2 actually talk to this provider?"""
    return provider in SUPPORTED_PROVIDERS
