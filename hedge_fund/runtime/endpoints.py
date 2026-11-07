"""Provider endpoint allowlists and DNS destination checks."""

from __future__ import annotations

import socket
from dataclasses import dataclass
from ipaddress import ip_address
from urllib.parse import parse_qsl, urlsplit

from hedge_fund.runtime.policy import (
    APPROVED_LOCAL_MODELS,
    AuthorizationDenied,
    ProviderTarget,
)

_REMOTE_HOSTS = {
    ("data", "fd"): frozenset({"api.financialdatasets.ai"}),
    ("data", "ken-french-breakpoints"): frozenset({"mba.tuck.dartmouth.edu"}),
    ("data", "yfinance"): frozenset(
        {
            "consent.yahoo.com",
            "fc.yahoo.com",
            "finance.yahoo.com",
            "guce.yahoo.com",
            "query1.finance.yahoo.com",
            "query2.finance.yahoo.com",
        }
    ),
    ("data", "yf"): frozenset(
        {
            "consent.yahoo.com",
            "fc.yahoo.com",
            "finance.yahoo.com",
            "guce.yahoo.com",
            "query1.finance.yahoo.com",
            "query2.finance.yahoo.com",
        }
    ),
    ("data", "yahoo"): frozenset(
        {
            "consent.yahoo.com",
            "fc.yahoo.com",
            "finance.yahoo.com",
            "guce.yahoo.com",
            "query1.finance.yahoo.com",
            "query2.finance.yahoo.com",
        }
    ),
    ("llm", "anthropic"): frozenset({"api.anthropic.com"}),
    ("llm", "deepseek"): frozenset({"api.deepseek.com"}),
    ("llm", "kimi"): frozenset({"api.moonshot.ai"}),
    ("llm", "openai"): frozenset({"api.openai.com"}),
    ("llm", "typesafe"): frozenset({"api.typesafe.ai"}),
    ("llm", "xai"): frozenset({"api.x.ai"}),
}
_SECRET_QUERY_NAMES = frozenset(
    {
        "apikey",
        "apitoken",
        "accesskey",
        "awsaccesskeyid",
        "accesstoken",
        "auth",
        "authkey",
        "authorization",
        "authtoken",
        "bearertoken",
        "clientid",
        "clientsecret",
        "credential",
        "key",
        "password",
        "refreshtoken",
        "secret",
        "secretkey",
        "sig",
        "signature",
        "token",
        "xamzcredential",
        "xamzsecuritytoken",
        "xamzsignature",
        "xapikey",
    }
)
_DEFAULT_ENDPOINTS = {
    ("llm", "anthropic"): "https://api.anthropic.com",
    ("llm", "deepseek"): "https://api.deepseek.com",
    ("llm", "kimi"): "https://api.moonshot.ai/v1",
    ("llm", "ollama"): "http://127.0.0.1:11434",
    ("llm", "openai"): "https://api.openai.com/v1",
    ("llm", "typesafe"): "https://api.typesafe.ai",
    ("llm", "xai"): "https://api.x.ai/v1",
}
_OLLAMA_HOST = "127.0.0.1"
_OLLAMA_PORT = 11434


@dataclass(frozen=True, slots=True)
class PinnedAddress:
    host: str
    port: int
    address: str
    local: bool


def provider_base_url(target: ProviderTarget) -> str:
    """Return canonical default or validated configured endpoint."""
    validate_provider_target(target)
    if target.endpoint is not None:
        return target.endpoint
    try:
        return _DEFAULT_ENDPOINTS[(target.kind, target.provider)]
    except KeyError:
        raise AuthorizationDenied("provider transport is unsupported") from None


def validate_request_url(target: ProviderTarget, url: str) -> tuple[str, int, bool]:
    """Return approved host, port, locality; reject origin or credential drift."""
    if not isinstance(target, ProviderTarget) or not isinstance(url, str):
        raise AuthorizationDenied("provider destination is invalid")
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError:
        raise AuthorizationDenied("provider destination is invalid") from None
    host = parts.hostname.casefold() if parts.hostname else ""
    if not host or parts.username is not None or parts.password is not None or parts.fragment:
        raise AuthorizationDenied("provider destination is invalid")
    if any("".join(char for char in name.casefold() if char.isalnum()) in _SECRET_QUERY_NAMES for name, _ in parse_qsl(parts.query, keep_blank_values=True)):
        raise AuthorizationDenied("provider URL cannot carry credentials")
    endpoint = _validate_configured_endpoint(target)
    if target.kind == "llm" and target.provider == "ollama":
        if target.model not in APPROVED_LOCAL_MODELS or endpoint != (_OLLAMA_HOST, _OLLAMA_PORT, "http") or host != _OLLAMA_HOST or parts.scheme.casefold() != "http" or port not in (None, _OLLAMA_PORT):
            raise AuthorizationDenied("Ollama destination is not the approved loopback endpoint")
        return host, _OLLAMA_PORT, True
    allowed_hosts = _REMOTE_HOSTS.get((target.kind, target.provider))
    if not allowed_hosts:
        raise AuthorizationDenied("provider transport is unsupported")
    if parts.scheme.casefold() != "https" or port not in (None, 443) or host not in allowed_hosts:
        raise AuthorizationDenied("provider destination does not match its identity")
    return host, 443, False


def validate_provider_target(target: ProviderTarget) -> None:
    """Reject unsupported provider transports and configured origins."""
    if not isinstance(target, ProviderTarget):
        raise AuthorizationDenied("provider target is invalid")
    endpoint = _validate_configured_endpoint(target)
    if target.kind == "llm" and target.provider == "ollama":
        if target.model not in APPROVED_LOCAL_MODELS or endpoint != (_OLLAMA_HOST, _OLLAMA_PORT, "http"):
            raise AuthorizationDenied("Ollama destination is not the approved loopback endpoint")
        return
    if (target.kind, target.provider) not in _REMOTE_HOSTS:
        raise AuthorizationDenied("provider transport is unsupported")


def resolve_destination(
    host: str,
    port: int,
    *,
    local: bool,
    resolver=None,
) -> PinnedAddress:
    """Resolve once; pin one address only after every answer passes policy."""
    if local:
        try:
            address = ip_address(host)
        except ValueError:
            raise AuthorizationDenied("local destination must be a literal IP") from None
        if address != ip_address(_OLLAMA_HOST) or port != _OLLAMA_PORT:
            raise AuthorizationDenied("local destination is not approved")
        return PinnedAddress(host, port, address.compressed, True)
    if not isinstance(host, str) or not host or type(port) is not int or port != 443:
        raise AuthorizationDenied("remote destination is invalid")
    lookup = resolver or _resolve_system
    try:
        answers = tuple(lookup(host, port))
    except Exception:
        raise AuthorizationDenied("provider destination could not be resolved") from None
    addresses = tuple(_address_text(answer) for answer in answers)
    if not addresses:
        raise AuthorizationDenied("provider destination has no addresses")
    parsed = []
    for value in addresses:
        try:
            address = ip_address(value)
        except ValueError:
            raise AuthorizationDenied("provider destination returned an invalid address") from None
        if getattr(address, "ipv4_mapped", None) is not None or not address.is_global:
            raise AuthorizationDenied("provider destination resolved to a forbidden address")
        parsed.append(address)
    return PinnedAddress(host, port, parsed[0].compressed, False)


def _validate_configured_endpoint(target: ProviderTarget) -> tuple[str, int, str] | None:
    endpoint = target.endpoint
    if target.kind == "llm" and target.provider == "ollama":
        if endpoint is None:
            return _OLLAMA_HOST, _OLLAMA_PORT, "http"
        try:
            parts = urlsplit(endpoint)
            port = parts.port
        except ValueError:
            raise AuthorizationDenied("configured provider endpoint is invalid") from None
        host = parts.hostname.casefold() if parts.hostname else ""
        if parts.scheme.casefold() != "http" or host != _OLLAMA_HOST or port not in (None, _OLLAMA_PORT) or parts.path not in ("", "/") or parts.query or parts.fragment:
            raise AuthorizationDenied("configured Ollama endpoint is not approved")
        return host, _OLLAMA_PORT, "http"
    if endpoint is None:
        return None
    try:
        parts = urlsplit(endpoint)
        port = parts.port
    except ValueError:
        raise AuthorizationDenied("configured provider endpoint is invalid") from None
    host = parts.hostname.casefold() if parts.hostname else ""
    allowed_hosts = _REMOTE_HOSTS.get((target.kind, target.provider))
    if not allowed_hosts or parts.scheme.casefold() != "https" or host not in allowed_hosts or port not in (None, 443) or parts.query or parts.fragment:
        raise AuthorizationDenied("configured provider endpoint is not approved")
    return host, 443, "https"


def _resolve_system(host: str, port: int):
    return [entry[4][0] for entry in socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)]


def _address_text(answer) -> str:
    if isinstance(answer, str):
        return answer
    if isinstance(answer, tuple) and len(answer) >= 5 and isinstance(answer[4], tuple) and answer[4]:
        value = answer[4][0]
        if isinstance(value, str):
            return value
    raise AuthorizationDenied("provider resolver returned an invalid address")
