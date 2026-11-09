"""Construct deployed-fund brokers from their persisted broker selection."""

from __future__ import annotations

import os
from pathlib import Path

from hedge_fund.brokers.account_binding import require_sim_account_ownership
from hedge_fund.brokers.paper import PaperBroker
from hedge_fund.brokers.saxo import (
    DemoTokenManager,
    Pacer,
    SaxoBroker,
    SaxoClient,
    TokenManager,
)
from hedge_fund.secrets.provider import SecretProvider, SecretProviderError

_OAUTH_REF_NAMES = ("SAXO_APP_KEY_REF", "SAXO_APP_SECRET_REF", "SAXO_REFRESH_TOKEN_REF")
_DEMO_REF_NAME = "SAXO_DEMO_ACCESS_TOKEN_REF"


def demo_token_mode_configured(environ: dict[str, str] | None = None) -> bool:
    env = os.environ if environ is None else environ
    return _DEMO_REF_NAME in env


def build_broker(
    deployed,
    *,
    directory: str | Path,
    secrets_provider: SecretProvider | None = None,
    transport=None,
    clock=None,
    environ: dict[str, str] | None = None,
):
    if deployed.broker != deployed.spec.broker:
        raise ValueError("deployed broker does not match the mandate snapshot")
    if deployed.broker == "paper":
        return PaperBroker(Path(directory) / "broker.json", deployed.spec.costs)
    if deployed.broker != "saxo":
        raise ValueError(f"unsupported broker: {deployed.broker}")

    require_sim_account_ownership()
    env = os.environ if environ is None else environ
    _validate_base_currency(env)
    mode, refs = _credential_mode(env)
    account_key = getattr(deployed.spec, "saxo_account_key", None)
    if mode == "demo-token" and (not isinstance(account_key, str) or not account_key or account_key.strip() != account_key):
        raise ValueError("Saxo demo-token mandate requires an explicit account identifier")
    provider = secrets_provider or SecretProvider()
    tokens = _build_tokens(mode, refs, provider, transport=transport, clock=clock, environ=env)
    client = SaxoClient(
        tokens=tokens,
        transport=transport,
        pacer=Pacer(clock=clock),
        clock=clock,
        base_currency="USD",
    )
    client.discover_account(account_key)
    return SaxoBroker(client, deployed.universe)


def build_saxo_demo_client(
    *,
    secrets_provider: SecretProvider | None = None,
    transport=None,
    clock=None,
    environ: dict[str, str] | None = None,
) -> SaxoClient:
    env = os.environ if environ is None else environ
    _validate_base_currency(env)
    mode, refs = _credential_mode(env)
    if mode != "demo-token":
        raise ValueError(f"{_DEMO_REF_NAME}: required for read-only Saxo SIM inspection")
    provider = secrets_provider or SecretProvider()
    tokens = DemoTokenManager(access_token_ref=refs[_DEMO_REF_NAME], secrets_provider=provider)
    return SaxoClient(
        tokens=tokens,
        transport=transport,
        pacer=Pacer(clock=clock),
        clock=clock,
        base_currency="USD",
    )


def _validate_base_currency(environ: dict[str, str]) -> None:
    requested_currency = environ.get("SAXO_BASE_CURRENCY", "USD")
    if not isinstance(requested_currency, str) or requested_currency.upper() != "USD":
        raise ValueError("the fund mandate base currency is USD; Saxo base currency cannot be overridden")


def _credential_mode(environ: dict[str, str]) -> tuple[str, dict[str, str]]:
    demo_present = _DEMO_REF_NAME in environ
    oauth_present = any(name in environ for name in _OAUTH_REF_NAMES)
    if demo_present and oauth_present:
        raise ValueError(f"{_DEMO_REF_NAME} cannot be combined with Saxo OAuth credential references")
    if demo_present:
        reference = environ[_DEMO_REF_NAME]
        if not isinstance(reference, str) or not reference.startswith("op://"):
            raise ValueError(f"{_DEMO_REF_NAME}: requires an op:// reference")
        return "demo-token", {_DEMO_REF_NAME: reference}
    refs = {name: environ.get(name, "") for name in _OAUTH_REF_NAMES}
    for name in _OAUTH_REF_NAMES:
        if not isinstance(refs[name], str) or not refs[name].startswith("op://"):
            raise ValueError(f"{name}: requires an op:// reference for Saxo broker")
    return "oauth", refs


def _build_tokens(mode, refs, provider, *, transport, clock, environ):
    if mode == "demo-token":
        return DemoTokenManager(access_token_ref=refs[_DEMO_REF_NAME], secrets_provider=provider)
    try:
        credentials = {name: provider.resolve(name, refs[name]) for name in _OAUTH_REF_NAMES[:2]}
    except SecretProviderError:
        raise
    return TokenManager(
        app_key=credentials["SAXO_APP_KEY_REF"],
        app_secret=credentials["SAXO_APP_SECRET_REF"],
        refresh_token_ref=refs["SAXO_REFRESH_TOKEN_REF"],
        secrets_provider=provider,
        transport=transport,
        clock=clock,
        lock_dir=environ.get("SAXO_REFRESH_LOCK_DIR"),
    )
