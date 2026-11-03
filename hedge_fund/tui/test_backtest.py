"""The backtest board's running numbers against the engine's final metrics."""

import asyncio
from unittest.mock import Mock

import pytest
from textual.widgets import ContentSwitcher, Input, OptionList, Static

from hedge_fund.backtesting import (
    DailyValuation,
    FundBacktestResult,
    performance_metrics,
)
from hedge_fund.brokers.models import Fill
from hedge_fund.tui import backtest, home
from hedge_fund.tui.app import HedgeFundApp
from hedge_fund.tui.fixtures import make_cycle, make_session, make_signal, render


@pytest.mark.parametrize("start_action", ["submit", "direct"])
def test_legacy_backtest_refuses_before_key_prompt_worker_provider_or_success(monkeypatch, start_action):
    keys = Mock(return_value=True)
    provider = Mock(side_effect=AssertionError("No provider construction is authorized"))
    save = Mock(side_effect=AssertionError("No result may be saved"))
    monkeypatch.setattr(home, "demand_run_keys", keys)
    monkeypatch.setattr(backtest, "make_data_client", provider)
    monkeypatch.setattr(backtest, "_save_admitted", save)
    spec = make_cycle(make_signal()).spec

    async def scenario():
        app = HedgeFundApp()
        async with app.run_test(size=(120, 45)) as pilot:
            await app.push_screen(backtest.BacktestScreen(spec))
            screen = app.screen
            worker = Mock()
            monkeypatch.setattr(screen, "_run", worker)
            notifications = Mock(wraps=screen.notify)
            monkeypatch.setattr(screen, "notify", notifications)
            screen.query_one("#bt-tickers", Input).value = "TEST"
            screen.query_one("#start-input", Input).value = "2025-01-01"
            screen.query_one("#end-input", Input).value = "2025-02-01"
            screen.query_one("#end-input", Input).focus()

            if start_action == "submit":
                await pilot.press("enter")
            else:
                screen._begin("2025-01-01", "2025-02-01", ["TEST"])
            await pilot.pause()

            keys.assert_not_called()
            worker.assert_not_called()
            provider.assert_not_called()
            save.assert_not_called()
            message = notifications.call_args.args[0]
            assert "disabled" in message.lower()
            assert "aihf backtest" in message
            assert "web desk" in message
            assert render(screen.query_one("#bt-disabled", Static).content).strip() == message
            assert notifications.call_args.kwargs["severity"] == "warning"
            assert screen.query_one("#bt-panes", ContentSwitcher).current == "bt-dates"
            assert screen.query_one("#bt-done-menu", OptionList).has_class("hidden")
            assert screen.check_action("back", ())
            await pilot.press("escape")
            await pilot.pause()
            assert not isinstance(app.screen, backtest.BacktestScreen)

    asyncio.run(scenario())


def test_legacy_worker_entry_refuses_synchronously_before_starting_work(monkeypatch):
    provider = Mock(side_effect=AssertionError("No provider construction is authorized"))
    monkeypatch.setattr(backtest, "make_data_client", provider)
    spec = make_cycle(make_signal()).spec

    async def scenario():
        app = HedgeFundApp()
        async with app.run_test(size=(120, 45)) as pilot:
            await app.push_screen(backtest.BacktestScreen(spec))
            screen = app.screen
            notifications = Mock(wraps=screen.notify)
            monkeypatch.setattr(screen, "notify", notifications)

            started = screen._run(spec, "2025-01-01", "2025-02-01", ["TEST"])
            await app.workers.wait_for_complete()
            await pilot.pause()

            assert started is None
            provider.assert_not_called()
            assert "disabled" in notifications.call_args.args[0].lower()
            assert notifications.call_args.kwargs["severity"] == "warning"
            assert screen.query_one("#bt-panes", ContentSwitcher).current == "bt-dates"
            assert screen.query_one("#bt-done-menu", OptionList).has_class("hidden")

    asyncio.run(scenario())


@pytest.mark.parametrize("size", [(120, 45), (80, 24)])
def test_backtest_daily_board_matches_final_metrics_and_uses_fill_dates(size, tmp_path):
    record = make_cycle(make_signal())
    record.execution_as_of = "2025-01-16"
    record.fills = [Fill(ticker="TEST", side="buy", quantity=1, price=100)]
    dates = ["2025-01-15", "2025-01-16", "2025-01-17"]
    nav = [100000, 100000, 90000]
    benchmark_nav = [100000, 101000, 102000]
    metrics = performance_metrics(100000, dates, nav, benchmark_nav, [record])
    sessions = [make_session(dates[0]), make_session(dates[1], executed=record), make_session(dates[2], nav=90000)]
    result = FundBacktestResult(fund=record.fund, start=dates[0], end=dates[-1], rebalance="weekly",
                                benchmark="SPY", universe=["TEST"], capital=100000, dates=dates,
                                nav=nav, benchmark_nav=benchmark_nav, records=sessions, metrics=metrics)
    async def scenario():
        app = HedgeFundApp()
        async with app.run_test(size=size) as pilot:
            await app.push_screen(backtest.BacktestScreen(record.spec))
            screen = app.screen
            screen.query_one("#bt-panes", ContentSwitcher).current = "bt-run"
            screen._begin_replay(record.spec, dict(zip(dates, [100, 101, 102])), 3)
            screen._board_valuation(DailyValuation(as_of=dates[0], nav=nav[0], benchmark_nav=benchmark_nav[0]))
            screen._board_tick(record)
            for i in (1, 2):
                screen._board_valuation(DailyValuation(as_of=dates[i], nav=nav[i], benchmark_nav=benchmark_nav[i]))
            await pilot.pause()
            before = {name: render(screen.query_one(f"#stat-{name}", Static).content)
                      for name in ("nav", "return", "sharpe", "dd")}
            assert screen._tape[0][0] == "2025-01-16"
            assert "session 3/3" in render(screen.query_one("#cycle-line", Static).content)
            screen._finish(result, tmp_path / "backtest.json")
            after = {name: render(screen.query_one(f"#stat-{name}", Static).content) for name in before}
            assert before == after
            phase = render(screen.query_one("#phase-line", Static).content)
            assert "1 executed cycles" in phase and "pending" not in phase
    asyncio.run(scenario())
