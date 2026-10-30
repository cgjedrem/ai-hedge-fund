"""Construct deployed-fund brokers from their persisted broker selection."""

from __future__ import annotations

import os
from pathlib import Path

from hedge_fund.brokers.paper import PaperBroker
from hedge_fund.brokers.saxo import Pacer, SaxoBroker, SaxoClient, TokenManager
from hedge_fund.secrets.provider import SecretProvider, SecretProviderError


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

    env = os.environ if environ is None else environ
    requested_currency = env.get("SAXO_BASE_CURRENCY", "USD")
    if not isinstance(requested_currency, str) or requested_currency.upper() != "USD":
        raise ValueError("the fund mandate base currency is USD; Saxo base currency cannot be overridden")
    names = ("SAXO_APP_KEY_REF", "SAXO_APP_SECRET_REF", "SAXO_REFRESH_TOKEN_REF")
    refs = {name: env.get(name, "") for name in names}
    for name in names:
        if not isinstance(refs[name], str) or not refs[name].startswith("op://"):
            raise ValueError(f"{name}: requires an op:// reference for Saxo broker")
    provider = secrets_provider or SecretProvider()
    try:
        credentials = {name: provider.resolve(name, refs[name]) for name in names[:2]}
    except SecretProviderError:
        raise
    tokens = TokenManager(
        app_key=credentials["SAXO_APP_KEY_REF"],
        app_secret=credentials["SAXO_APP_SECRET_REF"],
        refresh_token_ref=refs["SAXO_REFRESH_TOKEN_REF"],
        secrets_provider=provider,
        transport=transport,
        clock=clock,
        lock_dir=env.get("SAXO_REFRESH_LOCK_DIR"),
    )
    client = SaxoClient(
        tokens=tokens,
        transport=transport,
        pacer=Pacer(clock=clock),
        clock=clock,
        base_currency="USD",
    )
    return SaxoBroker(client, deployed.universe)
