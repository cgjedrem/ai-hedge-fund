from __future__ import annotations

import pytest

from hedge_fund.brokers.factory import build_broker
from hedge_fund.brokers.paper import PaperBroker
from hedge_fund.fund.spec import Fund, FundSpec
from hedge_fund.paper.deployed import deploy, load_deployed
from hedge_fund.pipeline.session import advance, BookMismatch, FundState, reconcile


class FakeSecrets:
    def __init__(self):
        self.calls = []

    def resolve(self, variable, reference):
        self.calls.append((variable, reference))
        return f"resolved-{variable}"

    def write_back(self, variable, reference, value):
        self.calls.append((f"write:{variable}", reference, value))


class FakeTransport:
    def __init__(self):
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        if url.endswith("/token"):
            return 200, {"access_token": "access", "refresh_token": "rotated", "expires_in": 900}
        if url.endswith("/port/v1/users/me"):
            return 200, {"ClientKey": "client"}
        if url.endswith("/port/v1/accounts/me"):
            return 200, {
                "Data": [
                    {
                        "AccountKey": "account",
                        "Currency": "USD",
                        "Active": True,
                        "LegalAssetTypes": ["Stock"],
                    }
                ]
            }
        if url.endswith("/ref/v1/instruments"):
            return 200, {"Data": [{"Identifier": 44, "Symbol": "AAPL:xnas", "ExchangeId": "NASDAQ"}]}
        if url.endswith("/ref/v1/instruments/details/44/Stock"):
            return 200, {
                "IsTradable": True,
                "LotSize": 1,
                "SupportedOrderTypes": ["Market"],
                "CurrencyCode": "USD",
                "Exchange": {"CountryCode": "US", "ExchangeId": "NASDAQ"},
            }
        if url.endswith("/port/v1/positions"):
            return 200, {"Data": []}
        if url.endswith("/port/v1/balances"):
            return 200, {"Currency": "USD", "CashBalance": 100_000, "CashAvailableForTrading": 10}
        return 200, {"Data": []}


def _spec(broker="paper", rebalance="weekly"):
    return FundSpec(
        schema_version=2,
        name="adapter-test",
        strategies=[{"name": "event", "models": [{"name": "pead"}], "blend": {"mode": "long_short"}}],
        risk={"max_position_pct": 0.25, "max_gross_exposure": 1.0},
        broker=broker,
        rebalance=rebalance,
    )


def test_saxo_deploy_skips_local_broker_book(tmp_path):
    spec = _spec("saxo", "minute")
    directory = deploy("external", spec, ["AAPL"], root=tmp_path)

    assert load_deployed(directory).broker == "saxo"
    assert not (directory / "broker.json").exists()


def test_paper_deployment_keeps_default_broker_in_deployment_yaml(tmp_path):
    directory = deploy("paper", _spec(), ["AAPL"], root=tmp_path)

    assert "\nbroker: paper\n" in (directory / "fund.yaml").read_text()
    assert load_deployed(directory).broker == "paper"


def test_factory_routes_paper_and_saxo_and_resolves_credentials(tmp_path):
    paper_dir = deploy("paper", _spec(), ["AAPL"], root=tmp_path)
    paper_fund = load_deployed(paper_dir)
    assert isinstance(build_broker(paper_fund, directory=paper_dir), PaperBroker)

    saxo_dir = deploy("saxo", _spec("saxo", "minute"), ["AAPL"], root=tmp_path)
    saxo_fund = load_deployed(saxo_dir)
    secrets = FakeSecrets()
    transport = FakeTransport()
    broker = build_broker(
        saxo_fund,
        directory=saxo_dir,
        secrets_provider=secrets,
        transport=transport,
        environ={
            "SAXO_APP_KEY_REF": "op://vault/item/key",
            "SAXO_APP_SECRET_REF": "op://vault/item/secret",
            "SAXO_REFRESH_TOKEN_REF": "op://vault/item/token",
        },
    )
    assert broker.client.account_key == "account"
    assert [call[0] for call in secrets.calls] == [
        "SAXO_APP_KEY_REF",
        "SAXO_APP_SECRET_REF",
        "SAXO_REFRESH_TOKEN_REF",
        "write:SAXO_REFRESH_TOKEN_REF",
    ]


def test_factory_rejects_missing_saxo_secret_reference_before_trading(tmp_path):
    directory = deploy("saxo", _spec("saxo", "minute"), ["AAPL"], root=tmp_path)
    with pytest.raises(ValueError, match="SAXO_APP_KEY_REF"):
        build_broker(load_deployed(directory), directory=directory, environ={})


def test_factory_rejects_non_usd_base_currency_override_before_secret_resolution(tmp_path):
    directory = deploy("saxo", _spec("saxo", "minute"), ["AAPL"], root=tmp_path)
    secrets = FakeSecrets()
    with pytest.raises(ValueError, match="base currency is USD"):
        build_broker(
            load_deployed(directory),
            directory=directory,
            secrets_provider=secrets,
            environ={
                "SAXO_APP_KEY_REF": "op://vault/item/key",
                "SAXO_APP_SECRET_REF": "op://vault/item/secret",
                "SAXO_REFRESH_TOKEN_REF": "op://vault/item/token",
                "SAXO_BASE_CURRENCY": "EUR",
            },
        )
    assert secrets.calls == []


def test_saxo_reconciliation_uses_accounting_cash_and_refuses_mismatch(tmp_path):
    directory = deploy("saxo", _spec("saxo", "minute"), ["AAPL"], root=tmp_path)
    deployed = load_deployed(directory)
    broker = build_broker(
        deployed,
        directory=directory,
        secrets_provider=FakeSecrets(),
        transport=FakeTransport(),
        environ={
            "SAXO_APP_KEY_REF": "op://vault/item/key",
            "SAXO_APP_SECRET_REF": "op://vault/item/secret",
            "SAXO_REFRESH_TOKEN_REF": "op://vault/item/token",
        },
    )

    reconcile(FundState.initial(100_000), broker, "saxo")

    class CompleteClock:
        def is_complete(self, session):
            return True

    with pytest.raises(BookMismatch, match="cash"):
        advance(
            Fund(deployed.spec, models={"event": [object()]}),
            FundState.initial(99_999),
            "2026-10-29T09:30:00",
            broker,
            None,
            deployed.universe,
            CompleteClock(),
        )


def test_redo_refuses_saxo_before_rewinding_ledger(tmp_path):
    from hedge_fund.paper.tick import redo

    directory = deploy("saxo", _spec("saxo", "minute"), ["AAPL"], root=tmp_path)
    with pytest.raises(ValueError, match="redo is only supported for paper"):
        redo(directory, None)
    assert not (directory / "broker.json").exists()
