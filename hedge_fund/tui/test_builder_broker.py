import asyncio

from textual.widgets import ContentSwitcher, Input, OptionList, SelectionList

from hedge_fund import paths
from hedge_fund.tui import builder, paper
from hedge_fund.tui.app import HedgeFundApp


def test_builder_blocks_daily_saxo_and_denies_the_minute_saxo_build(monkeypatch):
    """Daily Saxo is refused at the broker step; minute Saxo is accepted there,
    but the TUI holds no deployment admission, so the final step is denied and
    nothing is written."""
    notices: list[str] = []
    write_denial = paper.paper_write_denial()
    assert write_denial is not None

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
            assert screen.query_one("#panes", ContentSwitcher).current == "step-saxo-account"
            screen.query_one("#saxo-account-input", Input).value = "sim-account-1"
            await pilot.press("enter")
            assert screen.query_one("#panes", ContentSwitcher).current == "step-tickers"
            assert screen._state["broker"] == "saxo"
            screen.query_one("#tickers-input", Input).value = "AAPL"
            monkeypatch.setattr(screen, "notify", lambda message, **_kwargs: notices.append(message))
            await pilot.press("enter")
            await pilot.pause()
            assert screen.query_one("#panes", ContentSwitcher).current == "step-tickers"
            assert notices == [write_denial]
            assert not (paths.PAPER_DIR / "saxo-choice").exists()
            assert not (paths.MANDATES_DIR / "saxo-choice.yaml").exists()

    asyncio.run(scenario())
