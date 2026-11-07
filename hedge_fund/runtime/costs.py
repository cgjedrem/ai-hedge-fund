"""Published request-cost bounds for supported paid providers."""

from __future__ import annotations

import json
from decimal import Decimal, ROUND_CEILING
from urllib.parse import urlsplit

from hedge_fund.runtime.policy import ProviderTarget

COST_MODEL_VERSION = "2026-11-01-v2"
FD_PRICING_SOURCE = "https://www.financialdatasets.ai/pricing.md"
TYPESAFE_PRICING_SOURCE = "https://typesafe.ai/blog/introducing-system-one-models-and-jev"

_FD_MAX_SELF_SERVICE_REQUEST_COST = Decimal("0.16")
_TYPESAFE_INPUT_TOKEN_COST = Decimal("0.000000042")
_TYPESAFE_MAX_REQUEST_BYTES = 1_048_576
_TYPESAFE_MAX_CONTEXT_TOKENS = Decimal("64000")
_TYPESAFE_MAX_ATTEMPT_COST = (_TYPESAFE_MAX_CONTEXT_TOKENS * _TYPESAFE_INPUT_TOKEN_COST).quantize(Decimal("0.000001"), rounding=ROUND_CEILING)


def has_verified_cost_model(target: ProviderTarget) -> bool:
    """Whether target has a published finite tariff bound."""
    if not isinstance(target, ProviderTarget) or target.endpoint is not None:
        return False
    if target.kind == "data":
        return target.provider == "fd"
    return target.kind == "llm" and target.provider == "typesafe" and target.model == "jev-1.13.0"


def minimum_attempt_cost(target: ProviderTarget) -> Decimal | None:
    """Maximum supported request charge for target's verified cost model."""
    if not has_verified_cost_model(target):
        return None
    if target.kind == "data":
        return _FD_MAX_SELF_SERVICE_REQUEST_COST
    return _TYPESAFE_MAX_ATTEMPT_COST


def cost_model_identity(target: ProviderTarget) -> str | None:
    """Stable cost schedule identity for operation binding."""
    if not has_verified_cost_model(target):
        return None
    if target.kind == "data":
        return "fd-self-service-max-8x-v1"
    return "typesafe-jev-1.13.0-64k-context-v1"


def cost_model_description(target: ProviderTarget) -> str | None:
    """Short operator-facing cost-model scope."""
    identity = cost_model_identity(target)
    if identity == "fd-self-service-max-8x-v1":
        return "Financial Datasets self-service rates, maximum premium multiplier 8×; custom Enterprise pricing unsupported."
    if identity == "typesafe-jev-1.13.0-64k-context-v1":
        return "TypeSafe Jev 1.13.0 published input-token rate; 64K context ceiling; output tokens free; 1 MiB local request cap."
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
