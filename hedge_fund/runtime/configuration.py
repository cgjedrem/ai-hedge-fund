"""Root-bound non-secret runtime settings."""

from __future__ import annotations

import json
import math
import os
import stat
from collections.abc import Mapping
from dataclasses import dataclass, field
from ipaddress import ip_address
from types import MappingProxyType
from urllib.parse import urlsplit, urlunsplit

from hedge_fund.runtime.root import ensure_unique_resource_name, RootContext, RootPathError

SETTINGS_PATH = "runtime/settings.json"
DEFAULT_DATA_PROVIDER = "yfinance"
DEFAULT_MODEL = "claude-opus-5-5"
DEFAULT_TIMEOUT_SECONDS = 60.0
# Mirrors LLM registry; parity asserted by tests.
_PROVIDERS = {provider.casefold(): provider for provider in ("Anthropic", "OpenAI", "xAI", "DeepSeek", "Google", "Kimi", "TypeSafe", "Ollama")}
_MODEL_PROVIDERS = {
    "claude-opus-5-5": "Anthropic",
    "claude-fable-5-1": "Anthropic",
    "gpt-6-sol": "OpenAI",
    "gpt-6-astra": "OpenAI",
    "jev-1.13.0": "TypeSafe",
    "grok-4.7": "xAI",
    "deepseek-flash": "DeepSeek",
    "kimi-k3": "Kimi",
    "gemini-3.8-flash": "Google",
    "gemma3:4b": "Ollama",
    "glm-5.3-flash:cloud": "Ollama",
    "glm-5.3:cloud": "Ollama",
    "minimax-m3:cloud": "Ollama",
    "kimi-k3:cloud": "Ollama",
}
_DEFAULT_LLM_PROVIDER = "Anthropic"
_DATA_PROVIDERS = {
    "fd": "fd",
    "financialdatasets": "fd",
    "financial-datasets": "fd",
    "yahoo": "yfinance",
    "yf": "yfinance",
    "yfinance": "yfinance",
}
_SETTING_FIELDS = (
    "data_provider",
    "llm_provider",
    "model",
    "endpoint",
    "timeout_seconds",
    "parameters",
)
_ENVIRONMENT_FIELDS = {
    "HEDGE_FUND_DATA_PROVIDER": "data_provider",
    "HEDGE_FUND_LLM_PROVIDER": "llm_provider",
    "HEDGE_FUND_LLM_MODEL": "model",
    "HEDGE_FUND_LLM_ENDPOINT": "endpoint",
    "HEDGE_FUND_LLM_TIMEOUT_SECONDS": "timeout_seconds",
}
_PARAMETER_FIELDS = frozenset({"max_tokens", "temperature", "top_p"})
_PROVENANCE_VALUES = frozenset({"default", "persisted", "environment", "launch"})


class ConfigurationError(ValueError):
    """Settings input or persisted data is invalid."""


class SettingsConflict(RuntimeError):
    """Persisted settings version changed."""


@dataclass(frozen=True, slots=True)
class RuntimeSettings:
    """Immutable non-secret configuration snapshot."""

    data_provider: str = DEFAULT_DATA_PROVIDER
    llm_provider: str = _DEFAULT_LLM_PROVIDER
    model: str = DEFAULT_MODEL
    endpoint: str | None = None
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
    parameters: Mapping[str, int | float] = field(default_factory=dict, repr=False)
    version: int = 0
    provenance: Mapping[str, str] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        normalized = _normalize_settings(
            {
                "data_provider": self.data_provider,
                "llm_provider": self.llm_provider,
                "model": self.model,
                "endpoint": self.endpoint,
                "timeout_seconds": self.timeout_seconds,
                "parameters": self.parameters,
            }
        )
        for name, value in normalized.items():
            object.__setattr__(self, name, value)
        if type(self.version) is not int or self.version < 0:
            raise ConfigurationError("settings version is invalid")
        if not isinstance(self.provenance, Mapping):
            raise ConfigurationError("settings provenance is invalid")
        provenance = dict(self.provenance)
        if any(name not in _SETTING_FIELDS for name in provenance):
            raise ConfigurationError("settings provenance is invalid")
        if any(not isinstance(value, str) or value not in _PROVENANCE_VALUES for value in provenance.values()):
            raise ConfigurationError("settings provenance is invalid")
        for name in _SETTING_FIELDS:
            provenance.setdefault(name, "default")
        object.__setattr__(self, "parameters", MappingProxyType(dict(self.parameters)))
        object.__setattr__(self, "provenance", MappingProxyType(provenance))

    def to_mapping(self) -> dict[str, object]:
        return {
            "data_provider": self.data_provider,
            "llm_provider": self.llm_provider,
            "model": self.model,
            "endpoint": self.endpoint,
            "timeout_seconds": self.timeout_seconds,
            "parameters": dict(self.parameters),
        }

    def public_view(self) -> dict[str, object]:
        return {
            **self.to_mapping(),
            "version": self.version,
            "provenance": dict(self.provenance),
        }


def environment_settings(
    environment: Mapping[str, str] | None = None,
) -> dict[str, object]:
    """Read allowlisted non-secret setting variables only."""
    source = os.environ if environment is None else environment
    if not isinstance(source, Mapping):
        raise ConfigurationError("environment settings are invalid")
    values: dict[str, object] = {}
    for variable, field_name in _ENVIRONMENT_FIELDS.items():
        if variable not in source:
            continue
        value = source[variable]
        if not isinstance(value, str):
            raise ConfigurationError("environment setting is invalid")
        if field_name == "timeout_seconds":
            try:
                values[field_name] = float(value)
            except ValueError:
                raise ConfigurationError("environment setting is invalid") from None
        else:
            values[field_name] = value
    return values


def resolve_settings(
    root: RootContext,
    *,
    launch: Mapping[str, object] | None = None,
    environment: Mapping[str, object] | None = None,
    persisted: Mapping[str, object] | RuntimeSettings | None = None,
) -> RuntimeSettings:
    """Resolve launch > environment > persisted > safe defaults."""
    _require_root(root)
    stored = load_settings(root) if persisted is None else _parse_persisted(persisted)
    values: dict[str, object] = {
        "data_provider": DEFAULT_DATA_PROVIDER,
        "llm_provider": _DEFAULT_LLM_PROVIDER,
        "model": DEFAULT_MODEL,
        "endpoint": None,
        "timeout_seconds": DEFAULT_TIMEOUT_SECONDS,
        "parameters": {},
    }
    provenance = {name: "default" for name in _SETTING_FIELDS}
    for name in _SETTING_FIELDS:
        if stored.provenance[name] == "persisted":
            values[name] = getattr(stored, name)
            provenance[name] = "persisted"
    environment_overrides = environment_settings() if environment is None else environment
    for source_name, source in (
        ("environment", environment_overrides),
        ("launch", launch),
    ):
        overrides = _validate_overrides(source)
        _derive_model_provider(overrides)
        for name, value in overrides.items():
            values[name] = value
            provenance[name] = source_name
    return RuntimeSettings(
        **values,
        version=stored.version,
        provenance=provenance,
    )


def load_settings(root: RootContext) -> RuntimeSettings:
    """Load persisted non-secret settings; missing file means safe defaults."""
    _require_root(root)
    try:
        raw = root.read_bytes(SETTINGS_PATH)
    except FileNotFoundError:
        return RuntimeSettings()
    try:
        record = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ConfigurationError("persisted settings are invalid") from None
    if not isinstance(record, dict) or set(record) - {*_SETTING_FIELDS, "version"}:
        raise ConfigurationError("persisted settings are invalid")
    version = record.get("version")
    if type(version) is not int or version < 1:
        raise ConfigurationError("persisted settings are invalid")
    values = {name: record[name] for name in _SETTING_FIELDS if name in record}
    _derive_model_provider(values)
    merged = {**RuntimeSettings().to_mapping(), **values}
    normalized = _normalize_settings(merged)
    return RuntimeSettings(
        **normalized,
        version=version,
        provenance={name: "persisted" for name in _SETTING_FIELDS},
    )


def save_settings(
    root: RootContext,
    values: Mapping[str, object],
    *,
    expected_version: int,
) -> RuntimeSettings:
    """Persist non-secret settings with compare-and-swap versioning."""
    _require_root(root)
    if type(expected_version) is not int or expected_version < 0:
        raise ConfigurationError("expected settings version is invalid")
    overrides = _validate_overrides(values)
    current = load_settings(root)
    if current.version != expected_version:
        raise SettingsConflict("settings version changed")
    _derive_model_provider(overrides)
    merged = current.to_mapping()
    merged.update(overrides)
    version = current.version + 1
    settings = RuntimeSettings(
        **_normalize_settings(merged),
        version=version,
        provenance={name: "persisted" for name in _SETTING_FIELDS},
    )
    root.mkdir("runtime", parents=True, mode=0o700)
    record = {**settings.to_mapping(), "version": settings.version}
    payload = json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    root.write_bytes(SETTINGS_PATH, payload, mode=stat.S_IRUSR | stat.S_IWUSR)
    return settings


def child_root_arguments(root: RootContext) -> tuple[str, str]:
    """Return fixed root argv pair; never encode root in environment."""
    _require_root(root)
    return ("--root", os.fspath(root.path))


def build_child_environment(
    root: RootContext,
    *,
    child_id: str,
    settings: RuntimeSettings,
    inherited_environment: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Build allowlisted child environment with root-scoped home and temp."""
    _require_root(root)
    if not isinstance(settings, RuntimeSettings):
        raise ConfigurationError("runtime settings are required")
    try:
        identity = ensure_unique_resource_name(child_id, [])
    except RootPathError:
        raise ConfigurationError("child identity is invalid") from None
    base = f"runtime/children/{identity}"
    home_relative = f"{base}/home"
    temp_relative = f"{base}/tmp"
    root.mkdir(home_relative, parents=True, mode=0o700)
    root.mkdir(temp_relative, parents=True, mode=0o700)
    home = os.fspath(root.resolve(home_relative))
    temp = os.fspath(root.resolve(temp_relative))

    source = os.environ if inherited_environment is None else inherited_environment
    if not isinstance(source, Mapping):
        raise ConfigurationError("child environment is invalid")
    allowed = ("PATH", "SystemRoot", "WINDIR", "COMSPEC", "PATHEXT") if os.name == "nt" else ("PATH", "LANG", "LC_ALL", "TZ")
    child: dict[str, str] = {}
    for name in allowed:
        value = _environment_value(source, name)
        if value is not None:
            child[name] = value

    child.update(
        {
            "HOME": home,
            "USERPROFILE": home,
            "TEMP": temp,
            "TMP": temp,
            "PYTHON_DOTENV_DISABLED": "1",
            "PYTHONNOUSERSITE": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
            "HEDGE_FUND_DATA_PROVIDER": settings.data_provider,
            "HEDGE_FUND_LLM_PROVIDER": settings.llm_provider,
            "HEDGE_FUND_LLM_MODEL": settings.model,
            "HEDGE_FUND_LLM_TIMEOUT_SECONDS": str(settings.timeout_seconds),
        }
    )
    if settings.endpoint is not None:
        child["HEDGE_FUND_LLM_ENDPOINT"] = settings.endpoint

    if os.name == "nt":
        appdata_relative = f"{base}/home/AppData/Roaming"
        local_relative = f"{base}/home/AppData/Local"
        root.mkdir(appdata_relative, parents=True, mode=0o700)
        root.mkdir(local_relative, parents=True, mode=0o700)
        child["APPDATA"] = os.fspath(root.resolve(appdata_relative))
        child["LOCALAPPDATA"] = os.fspath(root.resolve(local_relative))
    else:
        for name, relative in (
            ("XDG_CACHE_HOME", f"{base}/home/.cache"),
            ("XDG_CONFIG_HOME", f"{base}/home/.config"),
            ("XDG_DATA_HOME", f"{base}/home/.local/share"),
        ):
            root.mkdir(relative, parents=True, mode=0o700)
            child[name] = os.fspath(root.resolve(relative))
    root.revalidate()
    return child


def _require_root(root: RootContext) -> None:
    if not isinstance(root, RootContext):
        raise ConfigurationError("an explicit root context is required")
    root.revalidate()


def _validate_overrides(values: Mapping[str, object] | None) -> dict[str, object]:
    if values is None:
        return {}
    if not isinstance(values, Mapping):
        raise ConfigurationError("settings overrides are invalid")
    if any(not isinstance(name, str) or name not in _SETTING_FIELDS for name in values):
        raise ConfigurationError("settings contain unsupported fields")
    return dict(values)


def _derive_model_provider(overrides: dict[str, object]) -> None:
    if "model" not in overrides or "llm_provider" in overrides:
        return
    model = overrides["model"]
    if isinstance(model, str) and model in _MODEL_PROVIDERS:
        overrides["llm_provider"] = _MODEL_PROVIDERS[model]


def _parse_persisted(
    persisted: Mapping[str, object] | RuntimeSettings,
) -> RuntimeSettings:
    if isinstance(persisted, RuntimeSettings):
        return persisted
    if not isinstance(persisted, Mapping):
        raise ConfigurationError("persisted settings are invalid")
    if any(not isinstance(name, str) or name not in {*_SETTING_FIELDS, "version"} for name in persisted):
        raise ConfigurationError("persisted settings are invalid")
    version = persisted.get("version", 0)
    if type(version) is not int or version < 0:
        raise ConfigurationError("persisted settings are invalid")
    values = {name: persisted[name] for name in _SETTING_FIELDS if name in persisted}
    _derive_model_provider(values)
    merged = {**RuntimeSettings().to_mapping(), **values}
    return RuntimeSettings(
        **_normalize_settings(merged),
        version=version,
        provenance={name: "persisted" for name in values},
    )


def _normalize_settings(values: Mapping[str, object]) -> dict[str, object]:
    if not isinstance(values, Mapping) or set(values) != set(_SETTING_FIELDS):
        raise ConfigurationError("settings values are invalid")
    data_provider = values["data_provider"]
    if not isinstance(data_provider, str) or data_provider.casefold() not in _DATA_PROVIDERS:
        raise ConfigurationError("data provider is unsupported")
    llm_provider = values["llm_provider"]
    if not isinstance(llm_provider, str) or llm_provider.casefold() not in _PROVIDERS:
        raise ConfigurationError("LLM provider is unsupported")
    normalized_provider = _PROVIDERS[llm_provider.casefold()]
    model = _validate_text(values["model"], maximum=256, message="model is invalid")
    registered_provider = _MODEL_PROVIDERS.get(model)
    if registered_provider is not None and registered_provider != normalized_provider:
        raise ConfigurationError("model and provider do not match")
    endpoint = _normalize_endpoint(values["endpoint"])
    timeout = values["timeout_seconds"]
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or timeout <= 0 or timeout > 300:
        raise ConfigurationError("timeout is invalid")
    return {
        "data_provider": _DATA_PROVIDERS[data_provider.casefold()],
        "llm_provider": normalized_provider,
        "model": model,
        "endpoint": endpoint,
        "timeout_seconds": float(timeout),
        "parameters": _normalize_parameters(values["parameters"]),
    }


def _normalize_parameters(value: object) -> Mapping[str, int | float]:
    if not isinstance(value, Mapping) or any(not isinstance(name, str) or name not in _PARAMETER_FIELDS for name in value):
        raise ConfigurationError("model parameters are invalid")
    result: dict[str, int | float] = {}
    for name, item in value.items():
        if name == "max_tokens":
            if type(item) is not int or not 1 <= item <= 131072:
                raise ConfigurationError("model parameters are invalid")
            result[name] = item
        else:
            if isinstance(item, bool) or not isinstance(item, (int, float)) or not math.isfinite(item):
                raise ConfigurationError("model parameters are invalid")
            upper = 2 if name == "temperature" else 1
            if item < 0 or item > upper:
                raise ConfigurationError("model parameters are invalid")
            result[name] = float(item)
    return MappingProxyType(result)


def _normalize_endpoint(value: object) -> str | None:
    if value is None:
        return None
    text = _validate_text(value, maximum=2048, message="endpoint is invalid")
    try:
        parts = urlsplit(text)
        port = parts.port
    except ValueError:
        raise ConfigurationError("endpoint is invalid") from None
    if parts.scheme.casefold() not in {"http", "https"} or not parts.hostname or any(char.isspace() for char in parts.hostname) or parts.username is not None or parts.password is not None or parts.query or parts.fragment:
        raise ConfigurationError("endpoint is invalid")
    if port is not None and not 1 <= port <= 65535:
        raise ConfigurationError("endpoint is invalid")
    if parts.scheme.casefold() == "http":
        try:
            if not ip_address(parts.hostname).is_loopback:
                raise ConfigurationError("endpoint is invalid")
        except ValueError:
            raise ConfigurationError("endpoint is invalid") from None
    netloc = parts.netloc.lower()
    return urlunsplit((parts.scheme.lower(), netloc, parts.path, "", ""))


def _validate_text(value: object, *, maximum: int, message: str) -> str:
    if not isinstance(value, str) or not value or len(value) > maximum or value != value.strip() or any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise ConfigurationError(message)
    return value


def _environment_value(source: Mapping[str, str], name: str) -> str | None:
    matches = [key for key in source if isinstance(key, str) and key.casefold() == name.casefold()]
    if len(matches) > 1:
        raise ConfigurationError("child environment is ambiguous")
    if not matches:
        return None
    value = source[matches[0]]
    if not isinstance(value, str) or "\x00" in value:
        raise ConfigurationError("child environment is invalid")
    return value
