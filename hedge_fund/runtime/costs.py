"""Published request-cost bounds for supported paid providers."""

from __future__ import annotations

import json
from decimal import Decimal, ROUND_CEILING
from urllib.parse import urlsplit

from hedge_fund.runtime.policy import AuthorizationDenied, ProviderTarget

COST_MODEL_VERSION = "2026-11-01-v2"
FD_PRICING_SOURCE = "https://www.financialdatasets.ai/pricing.md"
TYPESAFE_PRICING_SOURCE = "https://typesafe.ai/blog/introducing-system-one-models-and-jev"
MAX_LLM_OUTPUT_TOKENS = 131_072

_FD_MAX_SELF_SERVICE_REQUEST_COST = Decimal("0.16")
_TYPESAFE_INPUT_TOKEN_COST = Decimal("0.000000042")
_TYPESAFE_MAX_REQUEST_BYTES = 1_048_576
_TYPESAFE_MAX_CONTEXT_TOKENS = Decimal("64000")
_TYPESAFE_MAX_ATTEMPT_COST = (_TYPESAFE_MAX_CONTEXT_TOKENS * _TYPESAFE_INPUT_TOKEN_COST).quantize(Decimal("0.000001"), rounding=ROUND_CEILING)

# Operator-declared: Ollama model page, 2026-11-18.
# Rates per 1M input/cached-input/output: $2.00/$0.20/$10.00; context 1M.
_OLLAMA_KIMI_K3_1_PRO_MODEL = "kimi-k3.1-pro:cloud"
_OLLAMA_LOOPBACK_ENDPOINT = ("127.0.0.1", 11434, "http")
_OLLAMA_KIMI_K3_1_PRO_INPUT_PER_MILLION = Decimal("2.00")
_OLLAMA_KIMI_K3_1_PRO_CACHED_INPUT_PER_MILLION = Decimal("0.20")
_OLLAMA_KIMI_K3_1_PRO_OUTPUT_PER_MILLION = Decimal("10.00")
_OLLAMA_KIMI_K3_1_PRO_CONTEXT_TOKENS = Decimal("1000000")
_OLLAMA_PRICE_PER_MILLION = Decimal("1000000")
_OLLAMA_KIMI_K3_1_PRO_MAX_ATTEMPT_COST = (_OLLAMA_KIMI_K3_1_PRO_CONTEXT_TOKENS * _OLLAMA_KIMI_K3_1_PRO_INPUT_PER_MILLION + Decimal(MAX_LLM_OUTPUT_TOKENS) * _OLLAMA_KIMI_K3_1_PRO_OUTPUT_PER_MILLION) / _OLLAMA_PRICE_PER_MILLION
_OLLAMA_KIMI_K3_1_PRO_MAX_ATTEMPT_COST = _OLLAMA_KIMI_K3_1_PRO_MAX_ATTEMPT_COST.quantize(Decimal("0.000001"), rounding=ROUND_CEILING)


def _normalized_ollama_endpoint(target: ProviderTarget) -> tuple[str, int, str] | None:
    from hedge_fund.runtime.endpoints import _validate_configured_endpoint

    try:
        return _validate_configured_endpoint(target)
    except AuthorizationDenied:
        return None


def has_verified_cost_model(target: ProviderTarget) -> bool:
    """Whether target has a published finite tariff bound."""
    if not isinstance(target, ProviderTarget):
        return False
    if target.kind == "data":
        return target.endpoint is None and target.provider == "fd"
    if target.kind != "llm":
        return False
    if target.provider == "ollama":
        return target.model == _OLLAMA_KIMI_K3_1_PRO_MODEL and _normalized_ollama_endpoint(target) == _OLLAMA_LOOPBACK_ENDPOINT
    return target.endpoint is None and target.provider == "typesafe" and target.model == "jev-1.13.0"


def minimum_attempt_cost(target: ProviderTarget) -> Decimal | None:
    """Maximum supported request charge for target's verified cost model."""
    if not has_verified_cost_model(target):
        return None
    if target.kind == "data":
        return _FD_MAX_SELF_SERVICE_REQUEST_COST
    if target.provider == "ollama":
        return _OLLAMA_KIMI_K3_1_PRO_MAX_ATTEMPT_COST
    return _TYPESAFE_MAX_ATTEMPT_COST


def cost_model_identity(target: ProviderTarget) -> str | None:
    """Stable cost schedule identity for operation binding."""
    if not has_verified_cost_model(target):
        return None
    if target.kind == "data":
        return "fd-self-service-max-8x-v1"
    if target.provider == "ollama":
        return "ollama-kimi-k3.1-pro-1m-context-v1"
    return "typesafe-jev-1.13.0-64k-context-v1"


def cost_model_description(target: ProviderTarget) -> str | None:
    """Short operator-facing cost-model scope."""
    identity = cost_model_identity(target)
    if identity == "fd-self-service-max-8x-v1":
        return "Financial Datasets self-service rates, maximum premium multiplier 8×; custom Enterprise pricing unsupported."
    if identity == "typesafe-jev-1.13.0-64k-context-v1":
        return "TypeSafe Jev 1.13.0 published input-token rate; 64K context ceiling; output tokens free; 1 MiB local request cap."
    if identity == "ollama-kimi-k3.1-pro-1m-context-v1":
        return "Ollama model page, operator-declared 2026-11-18: " f"${_OLLAMA_KIMI_K3_1_PRO_INPUT_PER_MILLION}/1M input " f"(${_OLLAMA_KIMI_K3_1_PRO_CACHED_INPUT_PER_MILLION} cached), " f"${_OLLAMA_KIMI_K3_1_PRO_OUTPUT_PER_MILLION}/1M output; 1M-token context."
    return None


def request_cost_upper_bound(
    target: ProviderTarget,
    *,
    url: str,
    method: str,
    body: bytes | None,
) -> Decimal | None:
    """Return conservative USD cost bound; None means cost is unknown."""
    if not has_verified_cost_model(target) or not isinstance(url, str):
        return None
    if not isinstance(method, str) or method.upper() not in {"GET", "POST"}:
        return None
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError:
        return None
    host = parts.hostname.casefold() if parts.hostname else ""
    if target.kind == "llm" and target.provider == "ollama":
        if target.model != _OLLAMA_KIMI_K3_1_PRO_MODEL or parts.scheme.casefold() != "http" or host != "127.0.0.1" or port not in (None, 11434) or parts.path != "/api/chat" or parts.username is not None or parts.password is not None or parts.query or parts.fragment or method.upper() != "POST" or not isinstance(body, bytes):
            return None
        try:
            request = json.loads(body)
        except (UnicodeDecodeError, ValueError):
            return None
        if not isinstance(request, dict) or request.get("model") != target.model:
            return None
        options = request.get("options")
        if not isinstance(options, dict):
            return None
        context_tokens = options.get("num_ctx")
        output_tokens = options.get("num_predict")
        if type(context_tokens) is not int or not 1 <= context_tokens <= int(_OLLAMA_KIMI_K3_1_PRO_CONTEXT_TOKENS):
            return None
        if type(output_tokens) is not int or not 1 <= output_tokens <= MAX_LLM_OUTPUT_TOKENS:
            return None
        return ((_OLLAMA_KIMI_K3_1_PRO_CONTEXT_TOKENS * _OLLAMA_KIMI_K3_1_PRO_INPUT_PER_MILLION + Decimal(output_tokens) * _OLLAMA_KIMI_K3_1_PRO_OUTPUT_PER_MILLION) / _OLLAMA_PRICE_PER_MILLION).quantize(Decimal("0.000001"), rounding=ROUND_CEILING)
    if parts.scheme.casefold() != "https" or port not in (None, 443):
        return None
    if target.kind == "data":
        if host != "api.financialdatasets.ai" or method.upper() != "GET":
            return None
        return _FD_MAX_SELF_SERVICE_REQUEST_COST
    if target.model != "jev-1.13.0" or host != "api.typesafe.ai" or parts.path != "/v1/systemone" or method.upper() != "POST" or not isinstance(body, bytes) or not 1 <= len(body) <= _TYPESAFE_MAX_REQUEST_BYTES:
        return None
    try:
        request = json.loads(body)
    except (UnicodeDecodeError, ValueError):
        return None
    if not isinstance(request, dict) or request.get("model") != target.model:
        return None
    return _TYPESAFE_MAX_ATTEMPT_COST
