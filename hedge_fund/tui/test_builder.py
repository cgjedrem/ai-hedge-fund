"""The fund wizard in both modes, including the minute cadence sub-steps."""

import asyncio
import json
from datetime import datetime
from unittest.mock import Mock
from zoneinfo import ZoneInfo

import pytest
import yaml
from textual.widgets import ContentSwitcher, Input, OptionList, SelectionList, Static

from hedge_fund import paths
from hedge_fund.data.sessions import NEW_YORK
from hedge_fund.fund import FundSpec, load_spec, TradingWindow
from hedge_fund.paper import deploy, Ledger, load_deployed
from hedge_fund.signals import ALPHA_MODEL_REGISTRY
from hedge_fund.tui import builder, paper
from hedge_fund.tui.app import HedgeFundApp
from hedge_fund.tui.fixtures import make_session, make_spec, render
from hedge_fund.tui.shared import cadence_identity, MODE_LABELS, strategy_description


def test_mixed_description_identifies_short_analysts():
    description = strategy_description(make_spec().strategies[0])
    assert "Short ideas must be supported by Druckenmiller." in description
    assert "Long-only analysts contribute ownership views." in description
    assert "Long-only" in builder.BuilderScreen._agent_prompt("buffett", ALPHA_MODEL_REGISTRY["buffett"]).plain


@pytest.mark.parametrize(
    "names,mode",
    [
        (["buffett"], "long_only"),
        (["buffett", "druckenmiller"], "long_short"),
        (["druckenmiller"], "long_short"),
    ],
)
@pytest.mark.parametrize("size", [(120, 45), (80, 24)])
def test_builder_derives_rules_and_back_navigation_does_not_duplicate(names, mode, size):
    async def scenario():
        app = HedgeFundApp()
        async with app.run_test(size=size) as pilot:
            await app.push_screen(builder.BuilderScreen())
            screen = app.screen
            screen.query_one("#name-input", Input).value = "new-fund"
            await pilot.press("enter")
            screen.query_one("#strategy-list", SelectionList).select(builder.CUSTOM)
            await pilot.press("enter")
            agents = screen.query_one("#agent-list", SelectionList)
            for name in names:
                agents.select(name)
            await pilot.press("enter")
            assert screen.query_one("#panes", ContentSwitcher).current == "step-capital"
            await pilot.press("escape")
            assert screen.query_one("#panes", ContentSwitcher).current == "step-agents"
            assert set(agents.selected) == set(names)
            await pilot.press("enter")
            await pilot.press("enter", "enter")
            assert screen.query_one("#panes", ContentSwitcher).current == "step-done"
            saved = load_spec(paths.MANDATES_DIR / "new-fund.yaml")
            assert saved.schema_version == 2
            assert len(saved.strategies) == 1
            assert saved.strategies[0].blend.mode == mode
            menu = screen.query_one("#done-menu", OptionList)
            assert [menu.get_option_at_index(i).id for i in range(menu.option_count)] == ["go-backtest", "go-back"]
            await pilot.wait_for_scheduled_animations()
            await pilot.pause()
            assert screen.query_one("#done-menu", OptionList).region.intersection(screen.region).height > 0
            text = render(screen.query_one("#done-summary", Static).content)
            assert MODE_LABELS[mode] in text

    asyncio.run(scenario())


def test_builder_existing_name_and_save_race_never_overwrite():
    original = "name: old-user-fund\n"
    path = paths.MANDATES_DIR / "existing.yaml"
    path.write_text(original)

    async def scenario():
        app = HedgeFundApp()
        async with app.run_test(size=(120, 45)) as pilot:
            await app.push_screen(builder.BuilderScreen())
            screen = app.screen
            screen.query_one("#name-input", Input).value = "existing"
            await pilot.press("enter")
            # Taken: replacing would wipe it, which the TUI cannot admit, so no
            # wipe modal is offered and the name step stays put.
            assert app.screen is screen
            assert screen.query_one("#panes", ContentSwitcher).current == "step-name"
            assert path.read_text() == original
            screen.query_one("#name-input", Input).value = "save-race"
            await pilot.press("enter")
            screen.query_one("#strategy-list", SelectionList).select(builder.CUSTOM)
            await pilot.press("enter")
            screen.query_one("#agent-list", SelectionList).select("pead")
            await pilot.press("enter", "enter")
            assert screen.query_one("#panes", ContentSwitcher).current == "step-cadence"
            # Simulate another process saving the chosen name after validation.
            competing_path = paths.MANDATES_DIR / "save-race.yaml"
            competing_path.write_text(original)
            await pilot.press("enter")
            assert screen.query_one("#panes", ContentSwitcher).current == "step-name"
            assert competing_path.read_text() == original

    asyncio.run(scenario())


def _capture_notices(monkeypatch, screen) -> list[str]:
    notices: list[str] = []
    monkeypatch.setattr(screen, "notify", lambda message, **_kwargs: notices.append(message))
    return notices


def _tree(directory) -> dict[str, bytes]:
    return {p.relative_to(directory).as_posix(): p.read_bytes() for p in directory.rglob("*") if p.is_file()} if directory.exists() else {}


def test_builder_paper_mode_denies_the_build_and_refuses_taken_names(monkeypatch):
    """Paper builds need deployment admission the TUI never holds: the + row
    and the final step both deny, and nothing is written. The wizard steps,
    taken-name refusal and ticker prefill still behave as before."""
    deploy("taken", make_spec(["pead"], "taken"), ["NVDA", "AMD"], root=paths.PAPER_DIR)
    (paths.MANDATES_DIR / "saved.yaml").write_text(yaml.safe_dump(make_spec(["pead"], "saved").model_dump()))
    before_paper, before_mandates = _tree(paths.PAPER_DIR), _tree(paths.MANDATES_DIR)

    async def scenario():
        app = HedgeFundApp()
        async with app.run_test(size=(120, 45)) as pilot:
            await app.push_screen(paper.PaperScreen())
            fund_list = app.screen
            list_notices = _capture_notices(monkeypatch, fund_list)
            await pilot.press("end", "enter")  # the + row
            await pilot.pause()
            assert app.screen is fund_list
            assert list_notices == ["TUI paper writes are disabled on enrolled roots; use the web desk."]
            await app.push_screen(builder.BuilderScreen(mode="paper"))
            screen = app.screen
            notices = _capture_notices(monkeypatch, screen)
            assert screen.STEP_TITLES == ["Name", "Strategies", "Capital", "Cadence", "Approval", "Broker", "Saxo account", "Tickers"]
            for taken in ("taken", "saved"):  # paper funds and saved definitions both count
                screen.query_one("#name-input", Input).value = taken
                await pilot.press("enter")
                assert app.screen is screen
                assert screen.query_one("#panes", ContentSwitcher).current == "step-name"
            assert len(notices) == 2 and all("cannot be replaced here" in n for n in notices)
            screen.query_one("#name-input", Input).value = "alpha"
            await pilot.press("enter")
            screen.query_one("#strategy-list", SelectionList).select(builder.CUSTOM)
            await pilot.press("enter")
            screen.query_one("#agent-list", SelectionList).select("pead")
            await pilot.press("enter", "enter", "enter")
            await pilot.press("enter")
            assert screen.query_one("#panes", ContentSwitcher).current == "step-broker"
            await pilot.press("enter")
            assert screen.query_one("#panes", ContentSwitcher).current == "step-tickers"
            tickers = screen.query_one("#tickers-input", Input)
            assert tickers.value == "NVDA, AMD"  # prefilled from the newest paper fund
            tickers.value = "test, msft"
            await pilot.press("enter")
            await pilot.pause()
            assert screen.query_one("#panes", ContentSwitcher).current == "step-tickers"
            assert notices[-1] == "TUI paper writes are disabled on enrolled roots; use the web desk."
            assert screen._built is None

    asyncio.run(scenario())
    assert _tree(paths.PAPER_DIR) == before_paper
    assert _tree(paths.MANDATES_DIR) == before_mandates


def test_saxo_builder_requires_account_key_then_blocks_shared_root_deployment(monkeypatch):
    monkeypatch.setenv("SAXO_DEMO_ACCESS_TOKEN_REF", "op://vault/item/demo-token")

    async def scenario():
        app = HedgeFundApp()
        async with app.run_test(size=(120, 45)) as pilot:
            await app.push_screen(builder.BuilderScreen(mode="paper"))
            screen = app.screen
            screen.query_one("#name-input", Input).value = "saxo-blocked"
            await pilot.press("enter")
            screen.query_one("#strategy-list", SelectionList).select(builder.CUSTOM)
            await pilot.press("enter")
            screen.query_one("#agent-list", SelectionList).select("pead")
            await pilot.press("enter", "enter")
            screen.query_one("#cadence-list", OptionList).highlighted = 0
            await pilot.press("enter")
            await pilot.press("enter", "enter")
            screen.query_one("#window-end-input", Input).value = "15:59"
            await pilot.press("enter")
            await pilot.press("enter")
            await pilot.press("down", "enter")
            assert screen.query_one("#panes", ContentSwitcher).current == "step-saxo-account"

            await pilot.press("enter")
            assert screen.query_one("#panes", ContentSwitcher).current == "step-saxo-account"
            account = screen.query_one("#saxo-account-input", Input)
            account.value = "sim-account-1"
            await pilot.press("enter")
            assert screen.query_one("#panes", ContentSwitcher).current == "step-tickers"
            screen.query_one("#tickers-input", Input).value = "AAPL"
            await pilot.press("enter")
            await pilot.pause()

            assert screen.query_one("#panes", ContentSwitcher).current == "step-tickers"
            assert screen._state["saxo_account_key"] == "sim-account-1"
            assert not (paths.MANDATES_DIR / "saxo-blocked.yaml").exists()
            assert not (paths.PAPER_DIR / "saxo-blocked").exists()

    asyncio.run(scenario())


@pytest.mark.parametrize("approval_required", [False, True])
def test_builder_paper_mode_records_approval_choice_then_denies_the_build(monkeypatch, approval_required):
    name = "approval-on" if approval_required else "approval-off"

    async def scenario():
        app = HedgeFundApp()
        async with app.run_test(size=(120, 45)) as pilot:
            await app.push_screen(builder.BuilderScreen(mode="paper"))
            screen = app.screen
            notices = _capture_notices(monkeypatch, screen)
            screen.query_one("#name-input", Input).value = name
            await pilot.press("enter")
            screen.query_one("#strategy-list", SelectionList).select(builder.CUSTOM)
            await pilot.press("enter")
            screen.query_one("#agent-list", SelectionList).select("pead")
            await pilot.press("enter", "enter")
            await pilot.press("enter")
            assert screen.query_one("#panes", ContentSwitcher).current == "step-approval"
            choices = screen.query_one("#approval-list", OptionList)
            choices.highlighted = int(approval_required)
            await pilot.press("enter")
            assert screen.query_one("#panes", ContentSwitcher).current == "step-broker"
            assert screen._state["approval_required"] is approval_required
            await pilot.press("enter")
            assert screen.query_one("#panes", ContentSwitcher).current == "step-tickers"
            screen.query_one("#tickers-input", Input).value = "TEST"
            await pilot.press("enter")
            await pilot.pause()
            assert notices == ["TUI paper writes are disabled on enrolled roots; use the web desk."]

    asyncio.run(scenario())
    assert not (paths.PAPER_DIR / name).exists()
    assert not (paths.MANDATES_DIR / f"{name}.yaml").exists()


def test_builder_minute_path_sets_interval_and_window_then_denies_the_build(monkeypatch):
    async def scenario():
        app = HedgeFundApp()
        async with app.run_test(size=(120, 45)) as pilot:
            await app.push_screen(builder.BuilderScreen(mode="paper"))
            screen = app.screen
            screen.query_one("#name-input", Input).value = "fast"
            await pilot.press("enter")
            screen.query_one("#strategy-list", SelectionList).select(builder.CUSTOM)
            await pilot.press("enter")
            screen.query_one("#agent-list", SelectionList).select("pead")
            await pilot.press("enter", "enter")
            cadences = screen.query_one("#cadence-list", OptionList)
            assert cadences.highlighted == builder.BuilderScreen.CADENCES.index("weekly")  # the default, still
            prompts = [render(cadences.get_option_at_index(i).prompt) for i in range(cadences.option_count)]
            assert prompts[0].startswith("minute") and "set the interval and trading window" in prompts[0]
            assert "one decision at each close" in prompts[1] and "news-speed" not in "".join(prompts)
            cadences.highlighted = 0
            await pilot.press("enter")
            assert screen.query_one("#panes", ContentSwitcher).current == "step-interval"
            assert "every 1m · 09:30–16:00 ET · 391 sessions a day" in render(screen.query_one("#interval-line", Static).content)

            interval = screen.query_one("#interval-input", Input)
            interval.value = "0.005"
            await pilot.pause()
            line = render(screen.query_one("#interval-line", Static).content)
            assert "shortest interval is 1s" in line and "stamped to the second" in line
            await pilot.press("enter")  # refused; still here
            assert screen.query_one("#panes", ContentSwitcher).current == "step-interval"
            interval.value = "0.0167"  # every second: allowed, with a caveat about keeping up
            await pilot.pause()
            line = render(screen.query_one("#interval-line", Static).content)
            assert "every 1s · 09:30–16:00 ET · 23,401 sessions a day" in line and "logged as gaps" in line
            interval.value = "0.5"
            await pilot.pause()
            line = render(screen.query_one("#interval-line", Static).content)
            assert "every 30s · 09:30–16:00 ET · 781 sessions a day" in line and "gaps" not in line
            await pilot.press("enter")
            assert screen.query_one("#panes", ContentSwitcher).current == "step-window"
            assert "Cadence" in render(screen.query_one("#rail-3", Static).content)

            start, end = screen.query_one("#window-start-input", Input), screen.query_one("#window-end-input", Input)
            end.value = "21:00"
            await pilot.pause()
            assert "outside US extended hours" in render(screen.query_one("#window-line", Static).content)
            await pilot.press("enter")  # start's enter moves to end
            await pilot.press("enter")  # end's enter: refused
            assert screen.query_one("#panes", ContentSwitcher).current == "step-window"
            start.value, end.value = "09:00", "12:00"
            await pilot.pause()
            assert "every 30s · 09:00–12:00 ET · 361 sessions a day" in render(screen.query_one("#window-line", Static).content)
            end.focus()
            await pilot.press("enter")
            assert screen.query_one("#panes", ContentSwitcher).current == "step-approval"
            await pilot.press("enter")
            assert screen.query_one("#panes", ContentSwitcher).current == "step-broker"
            await pilot.press("enter")
            assert screen.query_one("#panes", ContentSwitcher).current == "step-tickers"
            rail = render(screen.query_one("#rail-3", Static).content)
            assert "every 30s" in rail and "09:00–12:00 ET" in rail
            await pilot.press("escape")
            assert screen.query_one("#panes", ContentSwitcher).current == "step-broker"
            await pilot.press("escape")
            assert screen.query_one("#panes", ContentSwitcher).current == "step-approval"
            await pilot.press("escape", "escape", "escape")
            assert screen.query_one("#panes", ContentSwitcher).current == "step-cadence"
            assert cadences.highlighted == 0
            await pilot.press("enter", "enter")  # interval and window remembered
            end.focus()
            await pilot.press("enter")
            await pilot.press("enter")
            await pilot.press("enter")  # broker
            assert screen.query_one("#panes", ContentSwitcher).current == "step-tickers"
            screen.query_one("#tickers-input", Input).value = "TEST"
            notices = _capture_notices(monkeypatch, screen)
            await pilot.press("enter")
            await pilot.pause()
            assert screen.query_one("#panes", ContentSwitcher).current == "step-tickers"
            assert notices == ["TUI paper writes are disabled on enrolled roots; use the web desk."]
            assert screen._state["rebalance"] == "minute" and screen._state["interval"] == 0.5
            assert screen._state["window"] == TradingWindow(start="09:00", end="12:00")
            assert not (paths.MANDATES_DIR / "fast.yaml").exists()
            assert not (paths.PAPER_DIR / "fast").exists()

    asyncio.run(scenario())


def test_builder_minute_helpers_are_pure():
    window = TradingWindow(start="09:30", end="16:00")
    assert builder.interval_line(1, window) == "every 1m · 09:30–16:00 ET · 391 sessions a day"
    assert builder.interval_line(90, window) == "every 1h30m · 09:30–16:00 ET · 6 sessions a day"
    with pytest.raises(ValueError, match="in minutes"):
        builder.parse_interval("soon")
    with pytest.raises(ValueError, match="1s"):
        builder.parse_interval("0.005")
    assert builder.parse_interval("0.01") == 0.01  # 0.6s rounds to the 1s floor, as the spec counts it
    assert builder.fast_caveat(0.1) and builder.fast_caveat(1 / 6) is None  # 6s warns, 10s does not

    today = datetime(2025, 7, 1, tzinfo=NEW_YORK)  # summer: ET is UTC-4
    assert builder.window_lines(window, 1, today=today, local_zone=NEW_YORK) == ["every 1m · 09:30–16:00 ET · 391 sessions a day"]
    assert builder.window_lines(window, 1, today=today, local_zone=ZoneInfo("America/Los_Angeles"))[1] == "that is 06:30–13:00 PDT where you are"
    assert builder.window_lines(window, 1, today=today, local_zone=ZoneInfo("Asia/Tokyo"))[1] == "that is 22:30–05:00 JST where you are (the next day)"
    assert cadence_identity(FundSpec(**{**make_spec().model_dump(), "rebalance": "minute", "interval": 5})) == "every 5m · 09:30–16:00 ET"
    assert cadence_identity(make_spec()) == "weekly"


def test_builder_refuses_to_replace_a_taken_name_and_wipes_nothing(monkeypatch):
    """Replacing a fund wipes its definition, backtests and ledger, which the
    TUI cannot admit: a taken name is refused at the name step, every file
    stays, and a fresh name still walks the wizard to the denied build."""
    old = make_spec(["buffett"], "alpha")
    old.rebalance = "monthly"
    (paths.MANDATES_DIR / "alpha.yaml").write_text(yaml.safe_dump(old.model_dump()))
    receipt = paths.RESEARCH_DIR / "alpha-backtest-2025-01-01.json"
    receipt.write_text(json.dumps({"fund": "alpha", "universe": ["NVDA"], "metrics": {"total_return_pct": 0.1, "annualized_return_pct": 0.1, "sharpe_ratio": 1, "max_drawdown_pct": -0.1, "benchmark_return_pct": 0, "excess_return_pct": 0.1, "n_cycles": 1}}))
    directory = deploy("alpha", old, ["NVDA"], root=paths.PAPER_DIR)
    ledger = Ledger(directory)
    ledger.append(make_session("2025-01-17", nav=100000))
    untouched = deploy("beta", old, ["AMD"], root=paths.PAPER_DIR)
    before = (_tree(paths.MANDATES_DIR), _tree(paths.RESEARCH_DIR), _tree(paths.PAPER_DIR))

    async def scenario():
        app = HedgeFundApp()
        async with app.run_test(size=(120, 45)) as pilot:
            await app.push_screen(builder.BuilderScreen(mode="paper"))
            screen = app.screen
            notices = _capture_notices(monkeypatch, screen)
            screen.query_one("#name-input", Input).value = "alpha"
            await pilot.press("enter")
            assert app.screen is screen
            assert screen.query_one("#panes", ContentSwitcher).current == "step-name"
            assert screen._state.get("replace") is None
            assert notices and "cannot be replaced here" in notices[-1]
            screen.query_one("#name-input", Input).value = "gamma"
            await pilot.press("enter")
            assert screen.query_one("#panes", ContentSwitcher).current == "step-strategies"
            assert screen._state["replace"] is None
            screen.query_one("#strategy-list", SelectionList).select(builder.CUSTOM)
            await pilot.press("enter")
            screen.query_one("#agent-list", SelectionList).select("pead")
            await pilot.press("enter", "enter", "enter")
            await pilot.press("enter")
            await pilot.press("enter")  # choose the default paper broker
            screen.query_one("#tickers-input", Input).value = "TEST"
            await pilot.press("enter")
            await pilot.pause()
            assert screen.query_one("#panes", ContentSwitcher).current == "step-tickers"
            assert notices[-1] == "TUI paper writes are disabled on enrolled roots; use the web desk."

    asyncio.run(scenario())
    assert (_tree(paths.MANDATES_DIR), _tree(paths.RESEARCH_DIR), _tree(paths.PAPER_DIR)) == before
    assert receipt.exists() and len(ledger.records()) == 1
    assert load_deployed(untouched).universe == ["AMD"]


def test_builder_first_session_is_unreachable_from_the_tui(monkeypatch):
    forbidden_client = Mock(side_effect=AssertionError("TUI reached provider setup"))
    monkeypatch.setattr(paper, "make_data_client", forbidden_client)

    async def scenario():
        app = HedgeFundApp()
        async with app.run_test(size=(120, 45)) as pilot:
            await app.push_screen(paper.PaperScreen())
            fund_list = app.screen
            notices = _capture_notices(monkeypatch, fund_list)
            await pilot.press("enter")  # the + row of an empty list
            await pilot.pause()
            assert app.screen is fund_list
            assert notices == ["TUI paper writes are disabled on enrolled roots; use the web desk."]

    asyncio.run(scenario())
    forbidden_client.assert_not_called()
    assert not paths.PAPER_DIR.exists() or not any(paths.PAPER_DIR.iterdir())
