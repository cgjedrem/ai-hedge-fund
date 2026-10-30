from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import datetime
from importlib import import_module

import pytest
from textual.widgets import ContentSwitcher, Input, OptionList, SelectionList

from hedge_fund import paths
from hedge_fund.brokers.factory import build_broker
from hedge_fund.brokers.protocol import OrderSubmissionDeferred
from hedge_fund.brokers.saxo import SaxoBroker
from hedge_fund.brokers.sim import SimBroker
from hedge_fund.data.models import Price
from hedge_fund.data.sessions import NEW_YORK
from hedge_fund.fund import Fund, FundSpec
from hedge_fund.models import Signal
from hedge_fund.paper.deployed import deploy, load_deployed
from hedge_fund.paper.ledger import Ledger
from hedge_fund.paper.tick import _run
from hedge_fund.pipeline.clock import Marked
from hedge_fund.pipeline.session import advance, BookMismatch, FundState
from hedge_fund.tui import builder
from hedge_fund.tui.app import HedgeFundApp

tick_module = import_module("hedge_fund.paper.tick")


class SharedSecrets:
    def __init__(self):
        self.refresh = "refresh-initial"

    def resolve(self, variable, reference):
        if variable == "SAXO_REFRESH_TOKEN_REF":
            return self.refresh
        return f"credential-{variable}"

    def write_back(self, variable, reference, value):
        self.refresh = value


class SaxoSimTransport:
    def __init__(self):
        self.calls = []
        self.positions = 0.0
        self.cash = 100_000.0
        self.order_id = 0
        self.executions = []
        self.refresh_id = 0

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        if url.endswith("/token"):
            self.refresh_id += 1
            return 200, {
                "access_token": f"access-{self.refresh_id}",
                "refresh_token": f"refresh-{self.refresh_id}",
                "expires_in": 900,
            }
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
            rows = []
            if self.positions:
                rows.append(
                    {
                        "NetPositionId": "net-aapl",
                        "PositionBase": {"Uic": 44, "Amount": self.positions, "OpenPrice": 100},
                    }
                )
            return 200, {"Data": rows}
        if url.endswith("/port/v1/balances"):
            return 200, {
                "Currency": "USD",
                "CashBalance": self.cash,
                "CashAvailableForTrading": self.cash,
            }
        if url.endswith("/trade/v2/orders"):
            self.order_id += 1
            order_id = f"order-{self.order_id}"
            payload = kwargs["json"]
            amount = float(payload["Amount"])
            signed = amount if payload["BuySell"] == "Buy" else -amount
            self.positions += signed
            self.cash -= signed * 100.0
            self.executions.append(
                {
                    "Trades": [
                        {
                            "OrderId": order_id,
                            "TradedQuantity": amount,
                            "Price": 100.0,
                        }
                    ],
                }
            )
            return 200, {"OrderId": order_id}
        if "/port/v1/orders/" in url:
            return 404, {}
        if url.endswith("/hist/v1/transactions"):
            return 200, {"Data": list(self.executions)}
        raise AssertionError(f"unexpected fake request: {method} {url}")


class FakeData:
    def get_prices(self, ticker, start_date, end_date, **kwargs):
        if ticker not in ("AAPL", "SPY") or not start_date <= "2026-10-29" <= end_date:
            return []
        return [Price(open=100, close=100, high=100, low=100, volume=1000, time="2026-10-29T20:00:00Z")]


class FakeClock:
    def __init__(self):
        self.mark = 100.0

    def is_complete(self, session):
        return True

    def previous(self, session):
        return "2026-10-29T09:30:00" if session.endswith("09:31:00") else "2026-10-29T09:31:00"

    def session_date(self, session):
        return session[:10]

    def marks(self, tickers, session):
        return Marked(prices={ticker: self.mark for ticker in tickers})


class LongAnalyst:
    name = "pead"

    def predict(self, ticker, date, data_client):
        return Signal(model_name=self.name, ticker=ticker, date=date, value=1.0)


def _fund(spec):
    return Fund(spec, models={spec.strategies[0].name: [LongAnalyst()]})


def _cutoff_setup(tmp_path, *, approval_required=False):
    spec = FundSpec(
        schema_version=2,
        name="cutoff",
        broker="saxo",
        rebalance="minute",
        interval=1,
        window={"start": "09:30", "end": "15:59"},
        capital=100_000,
        costs={"spread_bps": 0, "commission_per_share": 0},
        strategies=[{"name": "solo", "models": [{"name": "pead"}], "blend": {"mode": "long_short"}}],
        risk={"max_position_pct": 1, "max_gross_exposure": 1},
        approval_required=approval_required,
    )
    directory = deploy("cutoff", spec, ["AAPL", "MSFT"], root=tmp_path)

    class TwoTickerData(FakeData):
        def get_prices(self, ticker, start_date, end_date, **kwargs):
            return super().get_prices("AAPL" if ticker == "MSFT" else ticker, start_date, end_date, **kwargs)

    class CutoffClock(FakeClock):
        def previous(self, session):
            if session.endswith("15:59:00"):
                return "2026-10-29T15:58:00"
            if session.endswith("09:31:00"):
                return "2026-10-30T09:30:00"
            return "2026-10-29T15:59:00"

        def marks(self, tickers, session):
            return Marked(prices={ticker: 200.0 if ticker == "MSFT" and session.startswith("2026-10-30") else 100.0 for ticker in tickers})

    return directory, load_deployed(directory), Ledger(directory), _fund(spec), TwoTickerData(), CutoffClock()


@pytest.mark.parametrize("fills_before_cutoff", [0, 1])
def test_cutoff_records_completed_fills_and_re_evaluates_unsubmitted_orders_next_bar(tmp_path, fills_before_cutoff):
    directory, deployed, ledger, fund, data, clock = _cutoff_setup(tmp_path)

    class CutoffBroker(SimBroker):
        remaining = fills_before_cutoff

        def place_order(self, order):
            if self.remaining == 0:
                raise OrderSubmissionDeferred("market close reached before order submission")
            if self.remaining is not None:
                self.remaining -= 1
            return super().place_order(order)

    broker = CutoffBroker(100_000)
    first = _run(directory, deployed, ledger, ledger.replay(100_000), "2026-10-29T15:58:00", data, None, clock=clock, fund=fund, broker=broker)
    assert first.decision is not None
    closing = _run(directory, deployed, ledger, ledger.replay(100_000), "2026-10-29T15:59:00", data, None, clock=clock, fund=fund, broker=broker)

    assert len(closing.executed.orders) == len(closing.executed.fills) == fills_before_cutoff
    assert len(closing.executed.deferred_orders) == 2 - fills_before_cutoff
    assert "market close" in closing.executed.deferral_reason
    assert closing.executed.deferred_orders[-1].ticker == "MSFT"
    assert closing.executed.deferred_orders[-1].quantity == 500
    assert closing.positions == ({"AAPL": 500} if fills_before_cutoff else {})
    assert ledger.replay(100_000, full=True).positions == closing.positions
    assert len([event for event in ledger.events() if event["kind"] == "broker_fill"]) == fills_before_cutoff

    broker.remaining = None
    resumed = _run(directory, deployed, ledger, ledger.replay(100_000), "2026-10-30T09:30:00", data, None, clock=clock, fund=fund, broker=broker)
    assert resumed.positions == {"AAPL": 500, "MSFT": 250}
    assert len(resumed.executed.orders) == 2 - fills_before_cutoff
    assert next(order for order in resumed.executed.orders if order.ticker == "MSFT").quantity == 250
    assert resumed.executed.deferred_orders == []
    assert "deferred_orders" not in resumed.executed.model_dump()
    assert "deferral_reason" not in resumed.executed.model_dump()
    legacy_payload = resumed.model_dump(mode="json", exclude={"hash", "snapshot_times"})
    assert not {"deferred_orders", "deferral_reason"} & legacy_payload["executed"].keys()
    assert hashlib.sha256(json.dumps(legacy_payload, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest() == resumed.hash
    assert ledger.replay(100_000, full=True).positions == resumed.positions


def test_cutoff_re_evaluation_requires_a_new_approval(tmp_path):
    directory, deployed, ledger, fund, data, clock = _cutoff_setup(tmp_path, approval_required=True)

    class CutoffBroker(SimBroker):
        remaining = 1

        def place_order(self, order):
            if self.remaining == 0:
                raise OrderSubmissionDeferred("market close reached before order submission")
            if self.remaining is not None:
                self.remaining -= 1
            return super().place_order(order)

    broker = CutoffBroker(100_000)
    first = _run(directory, deployed, ledger, ledger.replay(100_000), "2026-10-29T15:58:00", data, None, clock=clock, fund=fund, broker=broker)
    ledger.set_approval("approve", first.decision.as_of, first.hash, "cli")
    closing = _run(directory, deployed, ledger, ledger.replay(100_000), "2026-10-29T15:59:00", data, None, clock=clock, fund=fund, broker=broker)
    assert closing.positions == {"AAPL": 500}
    assert len(closing.executed.deferred_orders) == 1
    assert ledger.approval() is None

    broker.remaining = None
    unapproved = _run(directory, deployed, ledger, ledger.replay(100_000), "2026-10-30T09:30:00", data, None, clock=clock, fund=fund, broker=broker)
    assert unapproved.executed is None
    assert unapproved.positions == closing.positions
    ledger.set_approval("approve", unapproved.decision.as_of, unapproved.hash, "cli")
    approved = _run(directory, deployed, ledger, ledger.replay(100_000), "2026-10-30T09:31:00", data, None, clock=clock, fund=fund, broker=broker)
    assert approved.positions == {"AAPL": 500, "MSFT": 250}
    assert [(order.ticker, order.quantity) for order in approved.executed.orders] == [("MSFT", 250)]
    assert ledger.replay(100_000, full=True).positions == approved.positions


def test_confirmed_external_fill_is_journaled_if_later_order_fails(tmp_path):
    directory, deployed, ledger, fund, data, clock = _cutoff_setup(tmp_path)

    class FailingBroker(SimBroker):
        def place_order(self, order):
            if self.positions():
                raise RuntimeError("later order failed")
            return super().place_order(order)

    broker = FailingBroker(100_000)
    _run(directory, deployed, ledger, ledger.replay(100_000), "2026-10-29T15:58:00", data, None, clock=clock, fund=fund, broker=broker)
    with pytest.raises(RuntimeError, match="later order failed"):
        _run(directory, deployed, ledger, ledger.replay(100_000), "2026-10-29T15:59:00", data, None, clock=clock, fund=fund, broker=broker)

    fills = [event for event in ledger.events() if event["kind"] == "broker_fill"]
    assert len(fills) == 1
    assert fills[0]["fill"]["ticker"] == "AAPL"
    assert fills[0]["order"]["quantity"] == fills[0]["fill"]["quantity"] == 500
    assert ledger.halted() is not None
    assert ledger.latest().session == "2026-10-29T15:58:00"


def test_confirmed_fills_are_journaled_if_later_assessment_fails(tmp_path):
    directory, deployed, ledger, fund, data, clock = _cutoff_setup(tmp_path)
    broker = SimBroker(100_000)
    analyst = fund.strategies[0][1][0]
    original_predict = analyst.predict

    def fail_at_close(ticker, date, data_client):
        if date.endswith("15:59:00"):
            raise RuntimeError("assessment failed")
        return original_predict(ticker, date, data_client)

    analyst.predict = fail_at_close
    _run(directory, deployed, ledger, ledger.replay(100_000), "2026-10-29T15:58:00", data, None, clock=clock, fund=fund, broker=broker)
    with pytest.raises(RuntimeError, match="assessment failed"):
        _run(directory, deployed, ledger, ledger.replay(100_000), "2026-10-29T15:59:00", data, None, clock=clock, fund=fund, broker=broker)

    assert {event["fill"]["ticker"] for event in ledger.events() if event["kind"] == "broker_fill"} == {"AAPL", "MSFT"}
    assert ledger.halted() is not None
    assert ledger.latest().session == "2026-10-29T15:58:00"


def test_fill_journal_failure_still_halts_after_an_external_fill(tmp_path, monkeypatch):
    directory, deployed, ledger, fund, data, clock = _cutoff_setup(tmp_path)
    broker = SimBroker(100_000)
    _run(directory, deployed, ledger, ledger.replay(100_000), "2026-10-29T15:58:00", data, None, clock=clock, fund=fund, broker=broker)

    def fail_log(*args, **kwargs):
        raise OSError("event journal unavailable")

    monkeypatch.setattr(ledger, "log_event", fail_log)
    with pytest.raises(OSError, match="event journal unavailable"):
        _run(directory, deployed, ledger, ledger.replay(100_000), "2026-10-29T15:59:00", data, None, clock=clock, fund=fund, broker=broker)

    assert ledger.halted() is not None
    assert set(broker.positions()) == {"AAPL"}
    assert ledger.latest().session == "2026-10-29T15:58:00"


def test_real_saxo_client_deferral_reaches_the_session_ledger(tmp_path):
    class ClosingClock(FakeClock):
        def previous(self, session):
            return "2026-10-29T15:58:00"

    spec = FundSpec(
        schema_version=2,
        name="cutoff-client",
        broker="saxo",
        rebalance="minute",
        interval=1,
        window={"start": "09:30", "end": "15:59"},
        capital=100_000,
        strategies=[{"name": "solo", "models": [{"name": "pead"}], "blend": {"mode": "long_short"}}],
        risk={"max_position_pct": 1, "max_gross_exposure": 1},
    )
    directory = deploy("cutoff-client", spec, ["AAPL"], root=tmp_path)
    deployed = load_deployed(directory)
    transport = SaxoSimTransport()
    broker = build_broker(
        deployed,
        directory=directory,
        secrets_provider=SharedSecrets(),
        transport=transport,
        environ={
            "SAXO_APP_KEY_REF": "op://vault/item/key",
            "SAXO_APP_SECRET_REF": "op://vault/item/secret",
            "SAXO_REFRESH_TOKEN_REF": "op://vault/item/token",
            "SAXO_REFRESH_LOCK_DIR": str(tmp_path / "locks"),
        },
    )
    ledger = Ledger(directory)
    clock = ClosingClock()
    data = FakeData()
    first = _run(directory, deployed, ledger, ledger.replay(100_000), "2026-10-29T15:58:00", data, None, clock=clock, fund=_fund(spec), broker=broker)

    cutoff = datetime(2026, 10, 29, 16, tzinfo=NEW_YORK)
    with broker.order_submission_window(cutoff, now=lambda: cutoff):
        closing = _run(directory, deployed, ledger, ledger.replay(100_000), "2026-10-29T15:59:00", data, None, clock=clock, fund=_fund(spec), broker=broker)

    assert first.decision is not None
    assert closing.executed.orders == closing.executed.fills == []
    assert [order.ticker for order in closing.executed.deferred_orders] == ["AAPL"]
    assert "market close" in closing.executed.deferral_reason
    assert not any(method == "POST" and url.endswith("/trade/v2/orders") for method, url, _ in transport.calls)
    assert ledger.replay(100_000, full=True).positions == {}
    assert ledger.halted() is None


def test_saxo_external_adapter_records_order_fill_in_ledger(tmp_path, monkeypatch):
    mandate_dir = tmp_path / "mandates"
    mandate_dir.mkdir()
    monkeypatch.setattr(paths, "PAPER_DIR", tmp_path)
    monkeypatch.setattr(paths, "MANDATES_DIR", mandate_dir)

    async def build_through_tui():
        app = HedgeFundApp()
        async with app.run_test(size=(120, 45)) as pilot:
            await app.push_screen(builder.BuilderScreen(mode="paper"))
            screen = app.screen
            screen.query_one("#name-input", Input).value = "external"
            await pilot.press("enter")
            screen.query_one("#strategy-list", SelectionList).select(builder.CUSTOM)
            await pilot.press("enter")
            screen.query_one("#agent-list", SelectionList).select("pead")
            await pilot.press("enter", "enter")
            screen.query_one("#cadence-list", OptionList).highlighted = 0
            await pilot.press("enter", "enter")
            screen.query_one("#window-end-input", Input).value = "15:59"
            await pilot.press("enter", "enter", "enter")
            screen.query_one("#broker-list", OptionList).highlighted = 1
            await pilot.press("enter")
            screen.query_one("#tickers-input", Input).value = "AAPL"
            await pilot.press("enter")
            assert screen.query_one("#panes", ContentSwitcher).current == "step-done"

    asyncio.run(build_through_tui())
    directory = tmp_path / "external"
    deployed = load_deployed(directory)
    spec = deployed.spec
    secrets = SharedSecrets()
    transport = SaxoSimTransport()
    filter_inputs = []
    original_filter_orders = SaxoBroker.filter_orders

    def capture_filter_inputs(broker, orders):
        filter_inputs.extend(orders)
        return original_filter_orders(broker, orders)

    monkeypatch.setattr(SaxoBroker, "filter_orders", capture_filter_inputs)
    environ = {
        "SAXO_APP_KEY_REF": "op://vault/item/key",
        "SAXO_APP_SECRET_REF": "op://vault/item/secret",
        "SAXO_REFRESH_TOKEN_REF": "op://vault/item/token",
    }
    monkeypatch.setattr(
        tick_module,
        "build_broker",
        lambda value, *, directory: build_broker(
            value,
            directory=directory,
            secrets_provider=secrets,
            transport=transport,
            environ=environ,
        ),
    )
    data = FakeData()
    clock = FakeClock()
    ledger = Ledger(directory)
    broker = build_broker(
        deployed,
        directory=directory,
        secrets_provider=secrets,
        transport=transport,
        environ=environ,
    )
    with pytest.raises(BookMismatch, match="cash"):
        advance(
            _fund(spec),
            FundState.initial(spec.capital).model_copy(update={"cash": spec.capital - 1}),
            "2026-10-29T09:30:00",
            broker,
            data,
            deployed.universe,
            clock,
        )

    first = _run(
        directory,
        deployed,
        ledger,
        FundState.initial(spec.capital),
        "2026-10-29T09:30:00",
        data,
        _fund,
        clock=clock,
    )
    second = _run(
        directory,
        deployed,
        ledger,
        FundState(
            cash=first.cash,
            positions=first.positions,
            last_session=first.session,
            pending=first.decision,
            prev_hash=first.hash,
        ),
        "2026-10-29T09:31:00",
        data,
        _fund,
        clock=clock,
    )
    third_state = FundState(
        cash=second.cash,
        positions=second.positions,
        last_session=second.session,
        pending=second.decision,
        prev_hash=second.hash,
    )
    clock.mark = 18_750 / 191.33
    third = _run(
        directory,
        deployed,
        ledger,
        third_state,
        "2026-10-29T09:32:00",
        data,
        _fund,
        clock=clock,
    )
    fourth_state = FundState(
        cash=third.cash,
        positions=third.positions,
        last_session=third.session,
        pending=third.decision,
        prev_hash=third.hash,
    )
    fourth = _run(
        directory,
        deployed,
        ledger,
        fourth_state,
        "2026-10-29T09:33:00",
        data,
        _fund,
        clock=clock,
    )

    recorded = ledger.read(second.session)
    assert recorded.executed is not None
    assert recorded.executed.fills[0].ticker == "AAPL"
    assert recorded.executed.fills[0].quantity == 250
    assert recorded.executed.fills[0].price == 100
    assert recorded.positions == {"AAPL": 250}
    assert sum(method == "POST" and url.endswith("/trade/v2/orders") for method, url, _ in transport.calls) == 2
    rounded_record = ledger.read(third.session)
    assert filter_inputs[1].quantity == pytest.approx(3.83, abs=0.001)
    assert rounded_record.executed is not None
    assert rounded_record.executed.orders[0].quantity == 3
    assert rounded_record.executed.fills[0].quantity == 3
    assert rounded_record.positions == {"AAPL": 253}
    assert sum(method == "POST" and url.endswith("/trade/v2/orders") for method, url, _ in transport.calls) == 2
    continued_record = ledger.read(fourth.session)
    assert continued_record.executed is not None
    assert continued_record.executed.orders == []
    assert continued_record.executed.fills == []
    assert continued_record.positions == {"AAPL": 253}
    assert fourth.session == "2026-10-29T09:33:00"
    assert sum(method == "POST" and url.endswith("/trade/v2/orders") for method, url, _ in transport.calls) == 2
    assert not (directory / "broker.json").exists()
