import asyncio

from textual.widgets import ContentSwitcher, Input, OptionList, SelectionList, Static

from hedge_fund import paths
from hedge_fund.paper import load_deployed
from hedge_fund.tui import builder
from hedge_fund.tui.app import HedgeFundApp
from hedge_fund.tui.fixtures import render


def test_builder_blocks_daily_saxo_and_deploys_minute_saxo():
    async def scenario():
        app = HedgeFundApp()
        async with app.run_test(size=(120, 45)) as pilot:
            await app.push_screen(builder.BuilderScreen(mode="paper"))
            screen = app.screen
            screen.query_one("#name-input", Input).value = "saxo-choice"
            await pilot.press("enter")
            screen.query_one("#strategy-list", SelectionList).select(builder.CUSTOM)
            await pilot.press("enter")
            screen.query_one("#agent-list", SelectionList).select("pead")
            await pilot.press("enter", "enter", "enter", "enter")
            assert screen.query_one("#panes", ContentSwitcher).current == "step-broker"
            broker_options = screen.query_one("#broker-list", OptionList)
            broker_options.highlighted = 1
            await pilot.press("enter")
            assert screen.query_one("#panes", ContentSwitcher).current == "step-broker"
            assert screen._state["broker"] == "paper"
            assert broker_options.highlighted == 0

            await pilot.press("escape", "escape")
            assert screen.query_one("#panes", ContentSwitcher).current == "step-cadence"
            screen.query_one("#cadence-list", OptionList).highlighted = 0
            await pilot.press("enter", "enter", "enter", "enter", "enter")
            assert screen.query_one("#panes", ContentSwitcher).current == "step-broker"
            broker_options = screen.query_one("#broker-list", OptionList)
            broker_options.highlighted = 1
            await pilot.press("enter")
            assert screen.query_one("#panes", ContentSwitcher).current == "step-broker"
            assert screen._state["broker"] == "paper"

            await pilot.press("escape", "escape")
            assert screen.query_one("#panes", ContentSwitcher).current == "step-window"
            screen.query_one("#window-end-input", Input).value = "15:59"
            await pilot.press("enter", "enter", "enter")
            assert screen.query_one("#panes", ContentSwitcher).current == "step-broker"
            broker_options = screen.query_one("#broker-list", OptionList)
            broker_options.highlighted = 1
            await pilot.press("enter")
            assert screen.query_one("#panes", ContentSwitcher).current == "step-tickers"
            screen.query_one("#tickers-input", Input).value = "AAPL"
            await pilot.press("enter")
            deployed = load_deployed(paths.PAPER_DIR / "saxo-choice")
            assert deployed.broker == "saxo" and deployed.spec.broker == "saxo"
            assert not (paths.PAPER_DIR / "saxo-choice" / "broker.json").exists()
            assert "broker: saxo" in render(screen.query_one("#done-summary", Static).content)

    asyncio.run(scenario())
