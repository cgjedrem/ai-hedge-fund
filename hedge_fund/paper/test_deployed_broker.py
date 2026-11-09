from __future__ import annotations

import pytest

from hedge_fund.brokers.factory import build_broker
from hedge_fund.brokers.paper import PaperBroker
from hedge_fund.brokers.test_saxo_doubles import (
    fake_saxo_broker,
    write_fake_sim_deployment,
)
from hedge_fund.fund.spec import Fund, FundSpec
from hedge_fund.paper.deployed import deploy, load_deployed
from hedge_fund.pipeline.session import advance, BookMismatch, FundState, reconcile
from hedge_fund.runtime.admission import OwnershipUnknown


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


def _spec(broker="paper", rebalance="weekly", account_key="account"):
    data = {
        "schema_version": 2,
        "name": "adapter-test",
        "strategies": [{"name": "event", "models": [{"name": "pead"}], "blend": {"mode": "long_short"}}],
        "risk": {"max_position_pct": 0.25, "max_gross_exposure": 1.0},
        "broker": broker,
        "rebalance": rebalance,
    }
    if broker == "saxo" and account_key is not None:
        data["saxo_account_key"] = account_key
    return FundSpec(**data)


def test_saxo_deploy_denies_unverified_account_without_local_broker_book(tmp_path):
    spec = _spec("saxo", "minute")
    with pytest.raises(OwnershipUnknown, match="ownership-unknown"):
        deploy("external", spec, ["AAPL"], root=tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_paper_deployment_keeps_default_broker_in_deployment_yaml(tmp_path):
    directory = deploy("paper", _spec(), ["AAPL"], root=tmp_path)

    assert "\nbroker: paper\n" in (directory / "fund.yaml").read_text()
    assert load_deployed(directory).broker == "paper"


def test_factory_routes_paper_and_denies_saxo_before_resolving_credentials(tmp_path):
    paper_dir = deploy("paper", _spec(), ["AAPL"], root=tmp_path)
    paper_fund = load_deployed(paper_dir)
    assert isinstance(build_broker(paper_fund, directory=paper_dir), PaperBroker)

    saxo_dir = write_fake_sim_deployment("saxo", _spec("saxo", "minute"), ["AAPL"], root=tmp_path)
    saxo_fund = load_deployed(saxo_dir)
    secrets = FakeSecrets()
    transport = FakeTransport()
    with pytest.raises(OwnershipUnknown, match="ownership-unknown"):
        build_broker(
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
    assert secrets.calls == transport.calls == []


def test_factory_rejects_unknown_account_before_missing_saxo_secret_reference(tmp_path):
    directory = write_fake_sim_deployment("saxo", _spec("saxo", "minute"), ["AAPL"], root=tmp_path)
    with pytest.raises(OwnershipUnknown, match="ownership-unknown"):
        build_broker(load_deployed(directory), directory=directory, environ={})


def test_factory_rejects_unknown_account_before_currency_override_or_secret_resolution(tmp_path):
    directory = write_fake_sim_deployment("saxo", _spec("saxo", "minute"), ["AAPL"], root=tmp_path)
    secrets = FakeSecrets()
    with pytest.raises(OwnershipUnknown, match="ownership-unknown"):
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
    directory = write_fake_sim_deployment("saxo", _spec("saxo", "minute"), ["AAPL"], root=tmp_path)
    deployed = load_deployed(directory)
    broker = fake_saxo_broker(
        deployed.universe,
        secrets_provider=FakeSecrets(),
        transport=FakeTransport(),
        lock_dir=tmp_path,
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

    directory = write_fake_sim_deployment("saxo", _spec("saxo", "minute"), ["AAPL"], root=tmp_path)
    with pytest.raises(ValueError, match="redo is only supported for paper"):
        redo(directory, None)
    assert not (directory / "broker.json").exists()


def test_tick_refuses_unknown_sim_account_before_ledger_or_provider_access(tmp_path, monkeypatch):
    from importlib import import_module

    from hedge_fund.runtime.admission import paper_execution_transition

    tick_module = import_module("hedge_fund.paper.tick")
    directory = write_fake_sim_deployment("saxo", _spec("saxo", "minute"), ["AAPL"], root=tmp_path)
    with paper_execution_transition(directory, directory.name):
        pass
    before = {str(entry.relative_to(directory)): entry.read_bytes() for entry in directory.rglob("*") if entry.is_file()}

    def forbidden(*_args, **_kwargs):
        pytest.fail("unknown SIM ownership reached ledger or provider work")

    monkeypatch.setattr(tick_module, "Ledger", forbidden)
    with pytest.raises(OwnershipUnknown, match="ownership-unknown"):
        tick_module.tick(directory, None, build_fund=forbidden)
    assert {str(entry.relative_to(directory)): entry.read_bytes() for entry in directory.rglob("*") if entry.is_file()} == before
