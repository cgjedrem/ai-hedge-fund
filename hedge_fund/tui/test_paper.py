"""The paper screens: approval step, kill switch, history, live prints, runner start/stop."""

import asyncio
import os
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock

import pytest
import yaml
from textual.widgets import ContentSwitcher, Input, OptionList, Static

from hedge_fund import paths
from hedge_fund.data.sessions import NEW_YORK
from hedge_fund.paper import deploy, Ledger, load_deployed
from hedge_fund.tui import backtest, funds, paper, paper_view, report
from hedge_fund.tui.app import HedgeFundApp
from hedge_fund.tui.fixtures import (
    executed_and_decided,
    make_minute_spec,
    make_pending,
    make_quote,
    make_session,
    make_spec,
    render,
)


@pytest.mark.parametrize("mode", ["long_only", "long_short", "dollar_neutral"])
@pytest.mark.parametrize("size", [(120, 45), (80, 24)])
def test_all_modes_can_be_backtested_and_paper_traded(mode, size):
    spec = make_spec()
    spec.strategies[0].blend.mode = mode

    async def scenario():
        app = HedgeFundApp()
        async with app.run_test(size=size) as pilot:
            await app.push_screen(backtest.BacktestScreen(spec))
            assert app.screen.query_one("#bt-panes", ContentSwitcher).current == "bt-dates"
            assert not app.screen.query_one("#bt-tickers", Input).disabled
            await pilot.press("escape")
            directory = deploy("test", spec, ["TEST"], root=paths.PAPER_DIR)
            await app.push_screen(paper.PaperScreen())
            menu = app.screen.query_one("#paper-menu", OptionList)
            assert menu.highlighted == menu.get_option_index("paper:0")
            assert app.screen.check_action("halt", ()) and app.screen.check_action("sessions", ())
            detail = render(app.screen.query_one("#detail-body", Static).content)
            assert "● new" in detail and "NEXT RUN" in detail
            assert load_deployed(directory).spec == spec

    asyncio.run(scenario())


def test_enrolled_root_displays_tui_write_denial_and_blocks_paper_controls(monkeypatch):
    from hedge_fund.paper import runner as legacy_runner
    from hedge_fund.runtime.admission import AdmissionCoordinator, RootOwnerLease
    from hedge_fund.runtime.handover import enroll_fresh, record_ledger_head
    from hedge_fund.runtime.root import RootContext

    root = Path(os.environ["HEDGE_FUND_TEST_ROOT"]) / "tui-enrolled"
    root.mkdir()
    spec = make_spec(["pead"], "alpha").model_copy(update={"approval_required": True})
    forbidden_client = Mock(side_effect=AssertionError("TUI reached provider setup"))
    forbidden_action = Mock(side_effect=AssertionError("TUI reached a paper writer"))
    monkeypatch.setattr(paper, "make_data_client", forbidden_client)
    monkeypatch.setattr(paper, "tick", forbidden_action)
    monkeypatch.setattr(paper, "redo", forbidden_action)
    monkeypatch.setattr(legacy_runner, "spawn_runner", forbidden_action)
    monkeypatch.setattr(legacy_runner, "stop_runner", forbidden_action)

    with RootContext.open(root) as context, paths.bound_root(context):
        enroll_fresh(context)
        owner = RootOwnerLease.acquire(context, timeout=0)
        admission = AdmissionCoordinator(context, owner_lease=owner)
        try:
            with admission.deployment_lock("alpha", timeout=0):
                directory = deploy("alpha", spec, ["TEST"], root=paths.PAPER_DIR)
            ledger = Ledger(directory)
            pending = make_pending("2025-01-20")
            with admission.manual_session("alpha", timeout=0):
                ledger.append(make_session("2025-01-20", decision=pending))
            record_ledger_head(context, "alpha", admission=admission)
            before_files = {path.relative_to(root).as_posix(): path.read_bytes() for path in root.rglob("*") if path.is_file() and "runtime/private" not in path.relative_to(root).as_posix()}

            async def scenario():
                app = HedgeFundApp()
                async with app.run_test(size=(140, 50)) as pilot:
                    await app.push_screen(paper.PaperScreen(select="alpha"))
                    screen = app.screen
                    detail = render(screen.query_one("#detail-body", Static).content)
                    assert "WRITE UNAVAILABLE" in detail
                    assert "enrolled roots" in detail

                    screen.action_run()
                    assert app.screen is screen
                    screen.action_runner()
                    assert app.screen is screen
                    screen.action_halt()
                    screen.action_resume()
                    screen.action_approve()
                    screen.action_reject()
                    screen.action_delete()
                    screen._finish_delete("alpha", True)
                    assert app.screen is screen

                    await app.push_screen(paper.RunSessionScreen(directory))
                    for _ in range(20):
                        await pilot.pause(0.05)
                        if app.screen._phase == "failed":
                            break
                    assert app.screen._phase == "failed"
                    assert "TUI paper writes are disabled on enrolled roots" in render(app.screen.query_one("#run-phase", Static).content)

                    await app.push_screen(paper.BuilderScreen(mode="paper"))
                    app.screen._finish_build()

            asyncio.run(scenario())
            with pytest.raises(RuntimeError, match="TUI paper writes are disabled"):
                funds.wipe_fund("alpha")

            after_files = {path.relative_to(root).as_posix(): path.read_bytes() for path in root.rglob("*") if path.is_file() and "runtime/private" not in path.relative_to(root).as_posix()}
            assert after_files == before_files
            assert not (root / "mandates").exists()
            forbidden_client.assert_not_called()
            forbidden_action.assert_not_called()
        finally:
            owner.close()


def test_tui_delete_denies_orphaned_admission_state_without_side_effects(tmp_path):
    from hedge_fund.runtime.handover import enroll_fresh, HANDOVER_PATH
    from hedge_fund.runtime.root import RootContext

    root = tmp_path / "tui-orphan"
    root.mkdir()
    with RootContext.open(root) as context:
        enroll_fresh(context)
        mandate = root / "mandates" / "alpha.yaml"
        mandate.parent.mkdir()
        mandate.write_text("synthetic: true\n", encoding="utf-8")
        paper_record = root / "paper" / "alpha" / "ledger" / "record.json"
        paper_record.parent.mkdir(parents=True)
        paper_record.write_text("synthetic-ledger\n", encoding="utf-8")
        (root / HANDOVER_PATH).unlink()

        with paths.bound_root(context):
            with pytest.raises(
                RuntimeError,
                match="root enrollment or ledger inventory is unavailable",
            ):
                funds.wipe_fund("alpha")

        assert mandate.read_text(encoding="utf-8") == "synthetic: true\n"
        assert paper_record.read_text(encoding="utf-8") == "synthetic-ledger\n"


def test_paper_screen_records_approval_verdicts_from_y_and_n():
    spec = make_spec(["pead"], "alpha").model_copy(update={"approval_required": True})
    directory = deploy("alpha", spec, ["TEST"], root=paths.PAPER_DIR)
    ledger = Ledger(directory)
    pending = make_pending("2025-01-20")
    ledger.append(make_session("2025-01-20", decision=pending))
    state = ledger.replay(spec.capital)

    async def scenario():
        app = HedgeFundApp()
        async with app.run_test(size=(140, 50)) as pilot:
            await app.push_screen(paper.PaperScreen())
            screen = app.screen
            assert screen.check_action("approve", ()) and screen.check_action("reject", ())
            detail = render(screen.query_one("#detail-body", Static).content)
            assert "awaiting approval — y approve · n reject" in detail

            await pilot.press("y")
            await pilot.pause()
            approval = ledger.approval()
            assert approval is not None
            assert approval["verdict"] == "approve" and approval["by"] == "tui"
            assert approval["decision_as_of"] == pending.as_of
            assert approval["decision_hash"] == state.prev_hash
            assert [event["kind"] for event in ledger.events()] == ["approve"]
            detail = render(screen.query_one("#detail-body", Static).content)
            assert "approved for execution" in detail

            await pilot.press("n")
            await pilot.pause()
            rejection = ledger.approval()
            assert rejection is not None
            assert rejection["verdict"] == "reject" and rejection["by"] == "tui"
            assert [event["kind"] for event in ledger.events()] == ["approve", "reject"]
            assert "rejected; decision will lapse" in render(screen.query_one("#detail-body", Static).content)

    asyncio.run(scenario())


def test_run_session_board_reports_a_gated_skip(monkeypatch):
    spec = make_spec(["pead"], "alpha").model_copy(update={"approval_required": True})
    directory = deploy("alpha", spec, ["TEST"], root=paths.PAPER_DIR)
    ledger = Ledger(directory)
    pending = make_pending("2025-01-20")
    ledger.append(make_session("2025-01-20", decision=pending))
    pending_hash = ledger.latest().hash
    deployed = load_deployed(directory)
    monkeypatch.setattr(paper.RunSessionScreen, "_run", lambda self: None)

    async def scenario():
        app = HedgeFundApp()
        async with app.run_test(size=(140, 50)):
            screen = paper.RunSessionScreen(directory)
            await app.push_screen(screen)
            screen._begin_board(deployed, "2025-01-21", [], pending, pending_hash)
            phase = render(screen.query_one("#run-phase", Static).content)
            assert "skipping execution of the 2025-01-20 decision; it lapses" in phase

            approval = ledger.set_approval("approve", pending.as_of, pending_hash, "tui")
            screen._begin_board(deployed, "2025-01-21", [], pending, pending_hash, approval)
            phase = render(screen.query_one("#run-phase", Static).content)
            assert "executing the 2025-01-20 decision" in phase

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "gate,pending,halted",
    [(False, True, False), (True, False, False), (True, True, True)],
)
def test_paper_screen_disables_approval_actions_outside_the_gate(gate, pending, halted):
    spec = make_spec(["pead"], "alpha").model_copy(update={"approval_required": gate})
    directory = deploy("alpha", spec, ["TEST"], root=paths.PAPER_DIR)
    ledger = Ledger(directory)
    if pending:
        ledger.append(make_session("2025-01-20", decision=make_pending("2025-01-20")))
    if halted:
        ledger.halt("operator review")

    async def scenario():
        app = HedgeFundApp()
        async with app.run_test(size=(140, 50)) as pilot:
            await app.push_screen(paper.PaperScreen())
            screen = app.screen
            assert not screen.check_action("approve", ())
            assert not screen.check_action("reject", ())
            await pilot.press("y", "n")
            assert ledger.approval() is None

    asyncio.run(scenario())


def test_paper_screen_shows_live_prints_when_they_arrive(monkeypatch):
    spec = make_spec(["pead"], "alpha")
    directory = deploy("alpha", spec, ["TEST"], root=paths.PAPER_DIR)
    record, _ = executed_and_decided()
    Ledger(directory).append(make_session("2025-01-20", executed=record, nav=101000, positions={"TEST": 10}, marks={"TEST": 100}))
    asked: list = []

    def fetch(tickers):
        asked.append(tickers)
        return {"TEST": make_quote("TEST", 120, datetime.now(NEW_YORK).isoformat())}

    monkeypatch.setattr(paper, "fetch_snapshots", fetch)

    async def scenario():
        app = HedgeFundApp()
        async with app.run_test(size=(140, 50)) as pilot:
            await app.push_screen(paper.PaperScreen())
            for _ in range(50):  # the prints arrive off-thread
                await pilot.pause(0.05)
                detail = render(app.screen.query_one("#detail-body", Static).content)
                if "Live" in detail:
                    break
            assert asked and asked[-1] == ["TEST"] and "$101,200" in detail

    asyncio.run(scenario())


def test_paper_screen_execution_denies_before_provider_or_ledger_effects(monkeypatch):
    spec = make_spec(["pead"], "alpha")
    directory = deploy("alpha", spec, ["TEST"], root=paths.PAPER_DIR)
    ledger = Ledger(directory)
    before_records = ledger.records()
    before_events = ledger.events()
    forbidden_client = Mock(side_effect=AssertionError("TUI execution reached provider setup"))
    monkeypatch.setattr(paper, "make_data_client", forbidden_client)

    async def scenario():
        app = HedgeFundApp()
        async with app.run_test(size=(140, 50)) as pilot:
            await app.push_screen(paper.PaperScreen())
            screen = app.screen
            notified = []
            monkeypatch.setattr(screen, "notify", lambda message, **_kwargs: notified.append(message))
            await pilot.press("enter")
            await pilot.pause()
            assert app.screen is screen
            assert notified == ["TUI paper execution lacks operation-bound authorization. Use the explicit-root CLI or web desk."]
            run_screen = paper.RunSessionScreen(directory)
            await app.push_screen(run_screen)
            for _ in range(20):
                await pilot.pause(0.05)
                if run_screen._phase == "failed":
                    break
            assert run_screen._phase == "failed"
            assert "lacks operation-bound authorization" in render(run_screen.query_one("#run-phase", Static).content)
            await pilot.pause()

    asyncio.run(scenario())
    forbidden_client.assert_not_called()
    assert ledger.records() == before_records
    assert ledger.events() == before_events


@pytest.mark.parametrize("size", [(120, 45), (80, 24)])
@pytest.mark.parametrize("what", ["executed", "decided", "both", "neither"])
def test_session_report_separates_the_executed_cycle_from_the_new_decision(size, what):
    record, decided = executed_and_decided()
    session = make_session("2025-01-20", executed=record if what in ("executed", "both") else None, decision=decided if what in ("decided", "both") else None)

    async def scenario():
        app = HedgeFundApp()
        async with app.run_test(size=size) as pilot:
            await app.push_screen(paper.SessionReportScreen("alpha", session))
            screen = app.screen
            await pilot.pause()
            head = render(screen.query_one("#report-head", Static).content)
            footer = render(screen.query_one("#report-foot", Static).content)
            menu = screen.query_one("#report-nav", OptionList)
            ids = [menu.get_option_at_index(i).id for i in range(menu.option_count)]
            assert "alpha" in head and "session 2025-01-20" in head
            assert "NAV $100,000.00" in footer
            if what in ("executed", "both"):
                assert "executed the 2025-01-15 decision (refreshed 2025-01-19)" in head
                assert "x:sec:orders" in ids and "x:sec:portfolio" in ids
                menu.highlighted = menu.get_option_index("x:sec:portfolio")
                await pilot.pause()
                assert "Target net" in render(screen.query_one("#detail-pane", Static).content)
            if what in ("decided", "both"):
                assert "executes next session" in head
                assert "d:sec:portfolio" in ids and "d:sec:orders" not in ids
                menu.highlighted = menu.get_option_index("d:sec:portfolio")
                await pilot.pause()
                detail = render(screen.query_one("#detail-pane", Static).content)
                assert "PROPOSED ALLOCATIONS" in detail and "TEST: +25.00%" in detail
            if what == "neither":
                assert "valuation only" in head
                assert ids == [None, "book"]
                menu.highlighted = menu.get_option_index("book")
                await pilot.pause()
                assert "flat — no positions" in render(screen.query_one("#detail-pane", Static).content)

    asyncio.run(scenario())


def test_paper_screen_works_the_kill_switch_and_sessions_reads_the_ledger(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(paper, "fetch_snapshots", lambda _tickers: {})
    spec = make_spec(["pead"], "alpha")
    directory = deploy("alpha", spec, ["TEST"], root=paths.PAPER_DIR)
    ledger = Ledger(directory)

    async def scenario():
        app = HedgeFundApp()
        async with app.run_test(size=(140, 50)) as pilot:
            await app.push_screen(paper.PaperScreen())
            screen = app.screen
            menu = screen.query_one("#paper-menu", OptionList)
            assert [menu.get_option_at_index(i).id for i in range(menu.option_count)] == ["paper:0", "build"]
            assert "alpha" in render(menu.get_option("paper:0").prompt)
            detail = render(screen.query_one("#detail-body", Static).content)
            assert "● new" in detail and "mark the book at the latest completed close" in detail
            assert screen.check_action("halt", ()) and not screen.check_action("resume", ())

            await pilot.press("h")  # no prompt: halts at once
            await pilot.pause()
            assert app.screen is screen
            assert ledger.halted() == paper_view.APP_HALT
            assert menu.highlighted == menu.get_option_index("paper:0")  # re-highlighted after the reload
            detail = render(screen.query_one("#detail-body", Static).content)
            assert "■ halted" in detail and "r to resume" in detail and paper_view.APP_HALT not in detail
            assert not screen.check_action("halt", ()) and screen.check_action("resume", ())
            await pilot.press("enter")  # halted funds do not run
            await pilot.pause()
            assert app.screen is screen
            await pilot.press("r")
            await pilot.pause()
            assert ledger.halted() is None
            assert [e["kind"] for e in ledger.events()] == ["halt", "resume"]

            # Two sessions land in the ledger behind the screen's back; coming
            # back to the screen re-reads them.
            record, decided = executed_and_decided()
            first = make_session("2025-01-17", decision=decided, nav=100000)
            second = make_session("2025-01-20", executed=record, nav=101000, positions={"TEST": 10}, marks={"TEST": 100}, prev_hash=first.hash)
            ledger.append(first)
            ledger.append(second)
            await app.push_screen(paper.SessionReportScreen("alpha", first))
            await pilot.press("escape")
            await pilot.pause()
            detail = render(screen.query_one("#detail-body", Static).content)
            assert "○ idle" in detail and "mark the book" in detail and "2025-01-17 · 2 sessions" in detail
            assert "SESSIONS" in detail and "2025-01-20" in detail and "1 fill" in detail
            assert "+1.0%" in render(menu.get_option("paper:0").prompt)

            await pilot.press("s")
            sessions_screen = app.screen
            assert isinstance(sessions_screen, paper.SessionsScreen)
            assert "last session 2025-01-20" in render(sessions_screen.query_one("#pf-status", Static).content)
            assert "+1.00%" in render(sessions_screen.query_one("#stat-return", Static).content)
            sessions = sessions_screen.query_one("#pf-sessions", OptionList)
            rows = [render(sessions.get_option_at_index(i).prompt) for i in range(sessions.option_count)]
            assert rows[0].startswith(" 2025-01-20") and "1 fill" in rows[0]
            assert rows[1].startswith(" 2025-01-17") and "decided" in rows[1]
            overview = render(sessions_screen.query_one("#detail-pane", Static).content)
            assert "EXECUTED" in overview and "decision from 2025-01-15" in overview
            await pilot.press("enter")
            assert isinstance(app.screen, paper.SessionReportScreen)
            assert "executed the 2025-01-15 decision" in render(app.screen.query_one("#report-head", Static).content)
            await pilot.press("escape")
            await pilot.press("escape")
            assert app.screen is screen

            # d deletes the fund — ledger, book, definition and backtests — after a yes.
            (paths.MANDATES_DIR / "alpha.yaml").write_text(yaml.safe_dump(spec.model_dump()))
            await pilot.press("d")
            modal = app.screen
            assert isinstance(modal, funds.ConfirmWipeScreen)
            manifest = render(modal.query_one("#confirm-files", Static).content)
            assert "2 sessions of ledger" in manifest and "alpha.yaml" in manifest and "name is free again" in manifest
            await pilot.press("escape")  # no
            assert app.screen is screen and directory.exists()
            await pilot.press("d")
            await pilot.press("enter")  # yes
            await pilot.pause()
            assert app.screen is screen
            assert not directory.exists() and not (paths.MANDATES_DIR / "alpha.yaml").exists()
            assert [menu.get_option_at_index(i).id for i in range(menu.option_count)] == ["build"]
            assert not screen.check_action("delete", ()) and not screen.check_action("halt", ())

    asyncio.run(scenario())


def test_paper_screen_enter_on_a_minute_fund_opens_the_same_approval_step(monkeypatch):
    """Enter means one thing at every cadence: run the next session, through
    the modal, onto the board. For a minute fund the session is the current
    bar, named by its clock time."""
    directory = deploy("fast", make_minute_spec(), ["TEST"], root=paths.PAPER_DIR)
    for variable in ("FINANCIAL_DATASETS_API_KEY", "TYPESAFE_API_KEY"):
        monkeypatch.setenv(variable, "x")
    monkeypatch.setenv("HEDGE_FUND_LLM_MODEL", "jev-1.13.0")
    monkeypatch.setattr(paper, "make_data_client", lambda: Mock(__enter__=lambda s: s, __exit__=lambda s, *a: None))
    monkeypatch.setattr(paper, "next_session", lambda data, spec, last, **kw: "2025-01-21T13:05:00")
    started: list = []
    monkeypatch.setattr(paper.RunSessionScreen, "_run", lambda self: started.append(self._directory))

    async def scenario():
        app = HedgeFundApp()
        async with app.run_test(size=(140, 50)) as pilot:
            await app.push_screen(paper.PaperScreen())
            screen = app.screen
            await pilot.press("enter")
            await pilot.pause()
            modal = app.screen
            assert isinstance(modal, paper.RunConfirmScreen) and modal.check_action("confirm", ())
            assert "through 2025-01-21 13:05:00 ET?" in render(modal.query_one("#run-q", Static).content)
            body = render(modal.query_one("#run-body", Static).content)
            assert "Mark the book at the 2025-01-21 13:05:00 ET print, taken now" in body
            assert "first decision" in body
            await pilot.press("enter")
            await pilot.pause()
            assert isinstance(app.screen, paper.RunSessionScreen) and started == [directory]
            app.screen._phase = "done"
            await pilot.press("escape")
            assert app.screen is screen

    asyncio.run(scenario())


@pytest.mark.parametrize("cadence", ["daily", "minute"])
def test_paper_screen_space_reports_runner_controls_disabled(monkeypatch, cadence):
    from hedge_fund.paper import runner as legacy_runner

    spec = make_minute_spec() if cadence == "minute" else make_spec(["pead"], "alpha")
    directory = deploy(spec.name, spec, ["TEST"], root=paths.PAPER_DIR)
    assert directory.is_dir()
    effects = []

    def forbidden(*_args, **_kwargs):
        effects.append(True)
        pytest.fail("disabled TUI runner reached process control")

    async def scenario():
        app = HedgeFundApp()
        async with app.run_test(size=(140, 50)) as pilot:
            await app.push_screen(paper.PaperScreen())
            screen = app.screen
            monkeypatch.setattr(legacy_runner, "spawn_runner", forbidden)
            monkeypatch.setattr(legacy_runner, "stop_runner", forbidden)
            monkeypatch.setattr(paper_view, "is_running", forbidden)
            notified = []
            monkeypatch.setattr(screen, "notify", lambda message, **_kwargs: notified.append(message))
            await pilot.press("space")
            await pilot.pause()
            assert app.screen is screen
            assert notified == ["Unattended paper runners are disabled. Use the explicit-root CLI or web desk for one authorized session."]

    asyncio.run(scenario())
    assert effects == []


def test_sessions_screen_groups_a_minute_funds_bars_by_day():
    directory = deploy("fast", make_minute_spec(), ["TEST"], root=paths.PAPER_DIR)
    ledger = Ledger(directory)
    record, decided = executed_and_decided()
    chain = [make_session("2025-01-21T13:00:00", decision=decided, nav=100000)]
    chain.append(make_session("2025-01-21T13:05:00", executed=record, nav=101000, positions={"TEST": 10}, marks={"TEST": 100}, prev_hash=chain[-1].hash))
    chain.append(make_session("2025-01-22T13:00:00", nav=102000, positions={"TEST": 10}, marks={"TEST": 200}, prev_hash=chain[-1].hash))
    for r in chain:
        ledger.append(r)

    async def scenario():
        app = HedgeFundApp()
        async with app.run_test(size=(140, 50)) as pilot:
            await app.push_screen(paper.SessionsScreen(directory))
            screen = app.screen
            await pilot.pause()
            assert "every 5m · 13:00–13:10 ET" in render(screen.query_one("#pf-head", Static).content)
            sessions = screen.query_one("#pf-sessions", OptionList)
            rows = [(sessions.get_option_at_index(i).id, render(sessions.get_option_at_index(i).prompt).strip()) for i in range(sessions.option_count)]
            assert rows[0][0] is None and rows[0][1].startswith("2025-01-22  +0.99%  1 bar")
            assert rows[1] == ("s:0", "13:00:00  +0.99%")
            assert rows[2][0] is None and rows[2][1].startswith("2025-01-21  +1.00%  2 bars")
            assert rows[3][0] == "s:1" and rows[3][1].startswith("13:05:00  +1.00%  1 fill")
            assert rows[4][0] == "s:2" and rows[4][1].startswith("13:00:00  +0.00%  decided")
            assert sessions.highlighted == 1  # the newest bar, not its heading
            assert "next bar's close" in render(report.session_overview(chain[0]))

    asyncio.run(scenario())
