"""Paper trading: the fund list, the approval step, one run, and a fund's history."""

from __future__ import annotations

import hashlib
import json
import os
from concurrent.futures import as_completed, ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from rich.console import Group
from rich.text import Text
from textual import on, work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen, Screen
from textual.timer import Timer
from textual.widgets import ContentSwitcher, Footer, OptionList, Static
from textual.widgets.option_list import Option

from hedge_fund import paths
from hedge_fund.brokers.factory import demo_token_mode_configured
from hedge_fund.data import CachedDataClient, make_data_client, PriceSnapshot
from hedge_fund.data.bars import is_intraday
from hedge_fund.fund import Fund, FundSpec
from hedge_fund.llm import make_llm
from hedge_fund.llm.client import validate_llm_transport
from hedge_fund.paper import assessment_dates, DeployedFund, is_running, Ledger, LedgerError, list_deployed, load_deployed, next_session, NothingDue, redo, tick
from hedge_fund.pipeline import DecisionRecord, FundState, SessionRecord
from hedge_fund.pipeline.session import code_version, mandate_hash
from hedge_fund.runtime.admission import AdmissionError
from hedge_fund.runtime.capture import freeze_capture, FrozenCapture
from hedge_fund.runtime.configuration import resolve_settings, RuntimeSettings
from hedge_fund.runtime.defaults import BOARD_REFRESH
from hedge_fund.runtime.dispatch import make_one_shot_dispatch
from hedge_fund.runtime.policy import APPROVED_LOCAL_MODELS, AuthorizationDenied, classify_provider, KEN_FRENCH_BREAKPOINTS_TARGET, ProviderClass, ProviderTarget
from hedge_fund.runtime.root import RootConfigurationError
from hedge_fund.scorecard import score
from hedge_fund.signals import ALPHA_MODEL_REGISTRY, LLMAgent
from hedge_fund.tui.funds import mandate_delete_denial, paper_creation_denial, paper_write_denial, tui_paper_admission
from hedge_fund.tui.palette import BRIGHT, CYAN, GREEN, MUTED, RED, TEXT
from hedge_fund.tui.paper_view import APP_HALT, day_heading, fetch_snapshots, LIVE_REFRESH, paper_detail, paper_slot, PaperSnapshot, run_plan
from hedge_fund.tui.report import book_summary, Desk, desk_table, session_detail, session_headline, session_nav, session_overview, session_row
from hedge_fund.tui.scorecard_view import analyst_table, strategy_table
from hedge_fund.tui.shared import agent_names, cadence_identity, DISPLAY_NAMES, render_area_chart, session_label
from hedge_fund.tui.widgets import first_selectable, StatTiles


class PaperScreen(Screen):
    """Paper trading. The fund list is the home of the fund: every deployed
    fund on the left, the highlighted one's state and its next run on the
    right. Enter runs its next session; `y`/`n` approve or reject gated
    decisions. `space` reports disabled runner control; `s` opens history;
    `h`/`r` work the kill switch. TUI creation and deletion stay disabled.
    """

    BINDINGS = [
        Binding("escape", "back", "back"),
        Binding("enter", "run", "run next session", priority=True),
        Binding("space", "runner", "runner control disabled"),
        Binding("s", "sessions", "sessions"),
        Binding("y", "approve", "approve"),
        Binding("n", "reject", "reject"),
        Binding("h", "halt", "halt"),
        Binding("r", "resume", "resume"),
        Binding("d", "delete", "delete"),
    ]

    def __init__(self, select: str | None = None, run: bool = False) -> None:
        super().__init__()
        self._snaps: list[PaperSnapshot | None] = []
        self._select = select  # highlight this fund on first paint
        self._run_on_mount = run  # ...and open its approval step right away
        self._quotes: dict[str, dict[str, PriceSnapshot]] = {}  # fund name -> latest prints
        self._quote_timer: Timer | None = None
        self._write_denial: str | None = None

    def compose(self) -> ComposeResult:
        with Horizontal(id="select"):
            with Vertical(id="select-rail"):
                yield Static(Text("PAPER TRADING", style=MUTED), classes="rail-title")
                yield OptionList(id="paper-menu")
            with VerticalScroll(id="select-detail"):
                yield Static("", id="detail-body")
        yield Footer()

    def on_mount(self) -> None:
        self._populate(self._select)
        self._quote_timer = self.set_interval(LIVE_REFRESH, self._poll_quotes)
        if self._run_on_mount:
            self._run_on_mount = False
            self.call_after_refresh(self.action_run)

    def on_screen_suspend(self) -> None:
        if self._quote_timer is not None:
            self._quote_timer.pause()

    def on_screen_resume(self) -> None:
        current = self._current()
        self._populate(current.deployed.name if current else None)
        if self._quote_timer is not None:
            self._quote_timer.resume()

    # ---- the list ---------------------------------------------------------

    def _populate(self, select: str | None) -> None:
        self._write_denial = paper_write_denial()
        menu = self.query_one("#paper-menu", OptionList)
        menu.clear_options()
        self._snaps = []
        for i, directory in enumerate(list_deployed(paths.PAPER_DIR)):
            try:
                snap = PaperSnapshot(directory)
            except ValueError as exc:
                self._snaps.append(None)
                menu.add_option(Option(Text(f" {directory.name} — Unavailable\n     {exc}", style=MUTED), disabled=True))
                continue
            self._snaps.append(snap)
            menu.add_option(Option(paper_slot(i, snap), id=f"paper:{i}"))
        if self._snaps:
            menu.add_option(None)
        menu.add_option(Option(Text.assemble(("  +  ", GREEN), ("Build a new fund", TEXT)), id="build"))
        # Options added after mount leave `highlighted` unset — pin it to the
        # asked-for fund, else the first readable one, else the build row.
        wanted = next((f"paper:{i}" for i, s in enumerate(self._snaps) if s is not None and s.deployed.name == select), None)
        first = wanted or next((f"paper:{i}" for i, s in enumerate(self._snaps) if s is not None), "build")
        menu.highlighted = menu.get_option_index(first)
        menu.focus()
        self._show_detail(first)
        self.refresh_bindings()

    def _current(self) -> PaperSnapshot | None:
        menu = self.query_one("#paper-menu", OptionList)
        if menu.highlighted is None:
            return None
        oid = menu.get_option_at_index(menu.highlighted).id or ""
        if not oid.startswith("paper:"):
            return None
        return self._snaps[int(oid.split(":")[1])]

    @on(OptionList.OptionHighlighted, "#paper-menu")
    def _highlight(self, event: OptionList.OptionHighlighted) -> None:
        oid = (event.option.id or "") if event.option else ""
        if oid:
            self._show_detail(oid)
        self.refresh_bindings()

    def _show_detail(self, oid: str) -> None:
        detail = self.query_one("#detail-body", Static)
        if oid.startswith("paper:"):
            snap = self._snaps[int(oid.split(":")[1])]
            if snap is not None:
                width = detail.content_size.width or 60
                body = paper_detail(
                    snap,
                    min(width, 100),
                    self._quotes.get(snap.deployed.name),
                )
                if self._write_denial is not None:
                    detail.update(
                        Group(
                            body,
                            Text(f"WRITE UNAVAILABLE — {self._write_denial}", style=f"bold {RED}"),
                        )
                    )
                else:
                    detail.update(body)
                self._poll_quotes()
        elif oid == "build":
            blurb = Text()
            blurb.append(
                paper_creation_denial(),
                style=MUTED,
            )
            if self._write_denial is not None:
                blurb.append(f"\n\n{self._write_denial}", style=f"bold {RED}")
            detail.update(blurb)

    # ---- live quotes ------------------------------------------------------

    def _poll_quotes(self) -> None:
        """Ask for the highlighted fund's prints, off-thread. Only a fund with
        positions has anything live to show; cash is cash. Re-read the ledger
        when a legacy process or another authorized writer records a session."""
        snap = self._current()
        if snap is None:
            return
        if snap.error is None and (is_running(snap.directory) != snap.running or (snap.ledger.sessions() or [None])[-1] != snap.last_session):
            self._populate(snap.deployed.name)
            return
        if snap.state is not None and snap.state.positions:
            self._fetch_quotes(snap.deployed.name, sorted(snap.state.positions))

    @work(thread=True, group="quotes", exclusive=True)
    def _fetch_quotes(self, name: str, tickers: list[str]) -> None:
        quotes = fetch_snapshots(tickers)
        if quotes:
            self.app.call_from_thread(self._quotes_arrived, name, quotes)

    def _quotes_arrived(self, name: str, quotes: dict[str, PriceSnapshot]) -> None:
        self._quotes[name] = quotes
        snap = self._current()
        if snap is not None and snap.deployed.name == name:
            detail = self.query_one("#detail-body", Static)
            width = detail.content_size.width or 60
            detail.update(paper_detail(snap, min(width, 100), quotes))

    # ---- actions ----------------------------------------------------------

    def _deny_paper_write(self) -> bool:
        denial = paper_write_denial()
        if denial is None:
            return False
        self.notify(denial, severity="warning")
        return True

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool:
        if action in ("back", "run"):
            return True  # run also handles the build row
        snap = self._current()
        if snap is None:
            return False
        if action == "delete":
            return True  # a fund with a broken ledger can still be deleted
        if snap.error:
            return False
        if action == "halt":
            return snap.halted is None
        if action == "resume":
            return snap.halted is not None
        if action in ("approve", "reject"):
            blocked_demo = snap.deployed.broker == "saxo" and demo_token_mode_configured()
            return not blocked_demo and snap.gate and snap.pending is not None and snap.halted is None
        if action == "runner":
            blocked_demo = snap.deployed.broker == "saxo" and demo_token_mode_configured()
            return snap.running or (not blocked_demo and snap.halted is None)
        return True

    def action_back(self) -> None:
        self.app.pop_screen()

    def action_run(self) -> None:
        menu = self.query_one("#paper-menu", OptionList)
        if menu.highlighted is not None and (menu.get_option_at_index(menu.highlighted).id or "") == "build":
            if self._deny_paper_write():
                return
            self.notify(paper_creation_denial(), severity="warning")
            return
        if self._deny_paper_write():
            return
        snap = self._current()
        if snap is not None:
            self.app.push_screen(RunConfirmScreen(snap.directory), self._after_confirm)

    def action_runner(self) -> None:
        """Space reports disabled legacy unattended runner control."""
        self.notify(
            "Unattended paper runners are disabled. Use the explicit-root CLI or web desk for one authorized session.",
            severity="warning",
        )

    def _after_confirm(self, plan: _TUIRunPlan | None) -> None:
        if plan is not None:
            self.app.push_screen(RunSessionScreen(plan.directory, plan=plan))

    def action_sessions(self) -> None:
        snap = self._current()
        if snap is not None:
            self.app.push_screen(SessionsScreen(snap.directory))

    def action_halt(self) -> None:
        if self._deny_paper_write():
            return
        snap = self._current()
        if snap is None:
            return
        try:
            with tui_paper_admission(snap.deployed.name, snap.directory) as (_root, admission):
                with admission.halt_lane(snap.deployed.name, timeout=0):
                    snap.ledger.halt(APP_HALT, request_id=uuid4().hex)
        except (LedgerError, RootConfigurationError, AdmissionError) as exc:
            self.notify(f"{snap.deployed.name} was not halted: {exc}", severity="error")
            return
        self.notify(f"{snap.deployed.name} halted · r to resume", severity="warning")
        self._populate(snap.deployed.name)

    def action_resume(self) -> None:
        if self._deny_paper_write():
            return
        snap = self._current()
        if snap is None:
            return
        try:
            with tui_paper_admission(snap.deployed.name, snap.directory) as (_root, admission):
                with admission.control_lane(snap.deployed.name, timeout=0):
                    snap.ledger.resume(
                        snap.deployed.spec.capital,
                        approval_required=snap.deployed.spec.approval_required,
                        request_id=uuid4().hex,
                        operator="tui",
                    )
        except (LedgerError, RootConfigurationError, AdmissionError) as exc:
            self.notify(f"{snap.deployed.name} stays halted: {exc}", severity="warning")
            return
        self.notify(f"{snap.deployed.name} resumed")
        self._populate(snap.deployed.name)

    def action_approve(self) -> None:
        self._record_approval("approve")

    def action_reject(self) -> None:
        self._record_approval("reject")

    def _record_approval(self, verdict: str) -> None:
        if self._deny_paper_write():
            return
        snap = self._current()
        if snap is None or snap.error or not snap.gate or snap.pending is None or snap.halted is not None or snap.state is None or snap.state.prev_hash is None:
            return
        name = snap.deployed.name
        try:
            with tui_paper_admission(name, snap.directory) as (_root, admission):
                from hedge_fund.runtime.admission import paper_approval_transition

                with paper_approval_transition(admission, name) as proof:
                    snap.ledger.set_approval(
                        verdict,
                        snap.pending.as_of,
                        snap.state.prev_hash,
                        "tui",
                        request_id=uuid4().hex,
                        admission=proof,
                    )
        except (LedgerError, RootConfigurationError, AdmissionError) as exc:
            self.notify(f"{name} verdict was not recorded: {exc}", severity="error")
            return
        action = "approved" if verdict == "approve" else "rejected"
        self.notify(f"{name} decision {action} from {snap.pending.as_of}")
        self._populate(name)

    def action_delete(self) -> None:
        if self._current() is not None:
            self.notify(mandate_delete_denial(), severity="warning")

    def _finish_delete(self, name: str, yes: bool | None) -> None:
        if not yes:
            return
        self.notify(mandate_delete_denial(), severity="warning")


@dataclass(frozen=True, slots=True)
class _TUIRunPlan:
    directory: Path
    deployed: DeployedFund
    state: FundState
    expected_head: str | None
    due: str | None
    action: str | None
    capture: FrozenCapture
    operation_id: str
    request_id: str
    operation_digest: str


class RunConfirmScreen(ModalScreen[_TUIRunPlan | None]):
    """The approval step. Enter on a fund is "run", so before anything trades
    the user sees exactly what this run will do — the decision about to be
    executed, its targets, whether a new decision follows — and says yes.
    Nothing has touched the ledger or the broker until they do.

    Dismisses with a captured plan after explicit confirmation.
    """

    BINDINGS = [
        Binding("escape", "cancel", "cancel"),
        Binding("enter", "confirm", "run", priority=True),
    ]

    def __init__(self, directory: Path) -> None:
        super().__init__()
        self._directory = directory
        self._plan: _TUIRunPlan | None = None
        self._ready = False

    def compose(self) -> ComposeResult:
        with Vertical(id="run-confirm"):
            yield Static("", id="run-q")
            yield Static(Text("finding the next session…", style=MUTED), id="run-body")
            yield Static("", id="run-keys")

    def on_mount(self) -> None:
        self.query_one("#run-q", Static).update(Text.assemble(("Run ", f"bold {BRIGHT}"), (self._directory.name, f"bold {GREEN}"), ("?", f"bold {BRIGHT}")))
        self.query_one("#run-keys", Static).update(Text("esc  cancel", style=MUTED))
        self._resolve()

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool:
        if action == "confirm":
            return self._ready and self._plan is not None and self._plan.action is not None
        return True

    def action_cancel(self) -> None:
        self.dismiss(None)

    def action_confirm(self) -> None:
        if self._plan is not None and self._plan.action is not None:
            self.dismiss(self._plan)

    @work(thread=True, exclusive=True)
    def _resolve(self) -> None:
        app = self.app
        try:
            plan = _resolve_tui_run_plan(self._directory)
        except Exception as exc:
            app.call_from_thread(self._show_error, exc)
            return
        app.call_from_thread(self._show, plan)

    def _show(self, plan: _TUIRunPlan) -> None:
        deployed, state, due = plan.deployed, plan.state, plan.due
        self._plan = plan
        self._ready = True
        self.query_one("#run-q", Static).update(Text.assemble(("Run ", f"bold {BRIGHT}"), (deployed.name, f"bold {GREEN}"), (f" through {session_label(due)}?" if due else f" again through {session_label(state.last_session)}?" if plan.action == "redo" else "?", f"bold {BRIGHT}")))
        approval = None
        if deployed.spec.approval_required and state.pending is not None:
            approval, _ = Ledger(self._directory).resolve_approval(state.pending.as_of, state.prev_hash)
        self.query_one("#run-body", Static).update(run_plan(deployed.name, state, due, deployed.spec, approval=approval))
        keys = Text()
        if plan.action is not None:
            keys.append("enter", style=f"bold {GREEN}")
            keys.append("  run   " if plan.action == "run" else "  run again   ", style=MUTED)
        keys.append("esc", style=f"bold {BRIGHT}")
        keys.append("  cancel", style=MUTED)
        self.query_one("#run-keys", Static).update(keys)
        self.refresh_bindings()

    def _show_error(self, exc: Exception) -> None:
        self._ready = True
        self.query_one("#run-body", Static).update(Text.assemble(("✗ ", f"bold {RED}"), (f"{type(exc).__name__}: {exc}", RED)))
        self.refresh_bindings()


class RunSessionScreen(Screen):
    """Run a paper fund through its next session, with the analysts' live
    board while they think, then the session's report. Reached only through
    the approval step, which has already checked the fund is runnable and
    that a session is due.

    The board is a best-effort warm: each analyst streams its thesis for the
    dates the run will assess, filling the caches `tick` reads a moment
    later. `tick` is the source of truth; it writes the ledger.
    """

    BINDINGS = [Binding("escape", "back", "back")]

    def __init__(
        self,
        directory: Path,
        *,
        plan: _TUIRunPlan | None = None,
        redo: bool = False,
    ) -> None:
        super().__init__()
        self._directory = directory
        self._plan = plan
        self._redo = plan.action == "redo" if plan is not None else redo
        self._phase = "running"
        self._record: SessionRecord | None = None
        self._desks: list[Desk] = []
        self._painter: Timer | None = None

    def compose(self) -> ComposeResult:
        with ContentSwitcher(initial="run-live", id="run-panes"):
            with VerticalScroll(id="run-live", classes="pane"):
                yield Static("", id="run-phase")
                yield Static("", id="run-roster")
            with Vertical(id="run-report"):
                yield Static("", id="report-head")
                with Horizontal(id="report-panes"):
                    with Vertical(id="report-rail"):
                        yield OptionList(id="report-nav")
                    with VerticalScroll(id="report-detail"):
                        yield Static("", id="detail-pane")
                yield Static("", id="report-foot")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#run-phase", Static).update(Text(f"Starting {self._directory.name}…", style=MUTED))
        self._run()

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool:
        # No leaving mid-run: the worker is writing the ledger.
        return not (action == "back" and self._phase == "running")

    def action_back(self) -> None:
        self.app.pop_screen()

    @on(OptionList.OptionHighlighted, "#report-nav")
    def _browse(self, event: OptionList.OptionHighlighted) -> None:
        assert self._record is not None
        oid = (event.option.id or "") if event.option else ""
        detail = session_detail(self._record, oid)
        if detail is not None:
            self.query_one("#detail-pane", Static).update(detail)
            self.query_one("#report-detail", VerticalScroll).scroll_home(animate=False)

    @work(thread=True, exclusive=True)
    def _run(self) -> None:
        app = self.app
        directory = self._directory
        plan = self._plan
        if not isinstance(plan, _TUIRunPlan) or plan.action not in {"run", "redo"}:
            denial = paper_write_denial() or "TUI paper execution requires an operation-bound confirmation; reopen the fund's run action."
            app.call_from_thread(self._fail, AdmissionError(denial))
            return
        try:
            with tui_paper_admission(plan.deployed.name, directory) as (root, admission):
                with admission.manual_session(plan.deployed.name, timeout=0):
                    deployed, state = _verify_tui_run_plan(root, admission, plan)
                    spec = deployed.spec
                    dispatch = _make_tui_run_dispatch(
                        plan.capture,
                        admission,
                        operation_id=plan.operation_id,
                        operation_digest=plan.operation_digest,
                        include_llm=True,
                    )
                    with make_data_client(plan.capture.data_provider, dispatch=dispatch) as raw:
                        data = CachedDataClient(raw, live=spec.is_intraday)
                        if plan.action == "run":
                            due = next_session(data, spec, state.last_session)
                            if due != plan.due:
                                raise AdmissionError("The reviewed paper session changed; reopen the run confirmation.")
                        else:
                            due = state.last_session
                            if due is None:
                                raise NothingDue("no session recorded yet, nothing to run again")
                            state = Ledger(directory).replay(spec.capital, before=due)
                        if due is None:
                            raise NothingDue(f"nothing due after {state.last_session}")
                        dates = assessment_dates(state, due, spec)
                        approval = None
                        if spec.approval_required and state.pending is not None:
                            approval, _ = Ledger(directory).resolve_approval(state.pending.as_of, state.prev_hash)
                        app.call_from_thread(self._begin_board, deployed, due, dates, state.pending, state.prev_hash, approval)
                        if dates:
                            self._warm(spec, deployed.universe, dates, plan.capture, dispatch)
                        build_fund = _tui_fund_factory(plan.capture, dispatch)
                        if plan.action == "redo":
                            record = redo(
                                directory,
                                data,
                                build_fund=build_fund,
                                request_id=plan.request_id,
                                expected_head=plan.expected_head,
                            )
                        else:
                            record = tick(
                                directory,
                                data,
                                session=due,
                                build_fund=build_fund,
                                expected_head=plan.expected_head,
                                operation_id=plan.operation_id,
                                request_id=plan.request_id,
                                capture_id=plan.capture.capture_id,
                                capture_digest=plan.capture.digest,
                            )
            app.call_from_thread(self._show_report, deployed, record)
        except Exception as exc:  # fail loud, in the UI
            app.call_from_thread(self._fail, exc)

    def _warm(
        self,
        spec: FundSpec,
        universe: list[str],
        dates: list[str],
        capture: FrozenCapture,
        dispatch,
    ) -> None:
        desks = dict(zip(agent_names(spec), self._desks, strict=True))
        # A warm prompt must match the tick prompt or the warm calls never hit
        # the cache the tick reads — so the mandate's model params (e.g.
        # news=True) flow through here exactly as Fund.__init__ passes them.
        params = {m.name: m.params for s in spec.strategies for m in s.models}

        def warm(agent_name: str) -> None:
            desk = desks[agent_name]
            cls = ALPHA_MODEL_REGISTRY[agent_name]  # own instance per thread
            kwargs = params.get(agent_name, {})
            # Only LLM agents have anything to stream; a quant model carries
            # no client and simply runs. The injected client must carry the
            # same temperature the agent was built with — the agent salts its
            # cache keys with it, so a mismatched client would still key
            # correctly but sample at the wrong creativity.
            model = (
                cls(
                    llm=_tui_llm_factory(capture, dispatch, on_token=desk.feed, temperature=kwargs.get("temperature")),
                    breakpoints_dispatch=dispatch,
                    **kwargs,
                )
                if issubclass(cls, LLMAgent)
                else cls(**kwargs)
            )
            with make_data_client(capture.data_provider, dispatch=dispatch) as raw:
                fd = CachedDataClient(raw)
                for as_of in dates:
                    for ticker in universe:
                        desk.begin(ticker)
                        try:
                            desk.settle(model.predict(ticker, as_of, fd))
                        except Exception:
                            pass  # best-effort warm; tick is the source of truth
            desk.finish()

        names = list(desks)
        with ThreadPoolExecutor(max_workers=min(8, len(names))) as pool:
            for future in as_completed([pool.submit(warm, n) for n in names]):
                future.result()

    # ---- UI-thread updates ------------------------------------------------

    def _begin_board(
        self,
        deployed: DeployedFund,
        due: str,
        dates: list[str],
        pending: DecisionRecord | None,
        pending_hash: str | None,
        approval: dict[str, str] | None = None,
    ) -> None:
        doing = []
        if pending is not None:
            matching_approval = approval is not None and approval.get("decision_as_of") == pending.as_of and approval.get("decision_hash") == pending_hash
            if not deployed.spec.approval_required or (matching_approval and approval.get("verdict") == "approve"):
                doing.append(f"executing the {pending.as_of} decision")
            elif matching_approval and approval.get("verdict") == "reject":
                doing.append(f"skipping the rejected {pending.as_of} decision; it lapses")
            else:
                doing.append(f"skipping execution of the {pending.as_of} decision; it lapses")
        if due in dates:
            doing.append("assessing the next decision")
        if not doing:
            doing.append("marking the book")
        self.query_one("#run-phase", Static).update(
            Text.assemble(
                (f"Running {deployed.name} {'again through' if self._redo else 'through'} ", f"bold {BRIGHT}"),
                (session_label(due), f"bold {RED}"),
                ("  ·  " + " · ".join(doing), MUTED),
            )
        )
        if not dates:
            return
        self._desks = [Desk(DISPLAY_NAMES.get(n, n)) for n in agent_names(deployed.spec)]
        self._paint_board()
        # The worker threads mutate their own desk; this redraws all of them on
        # one clock, so token rate never sets frame rate.
        self._painter = self.set_interval(BOARD_REFRESH, self._paint_board)

    def _paint_board(self) -> None:
        self.query_one("#run-roster", Static).update(desk_table(self._desks))

    def _stop_painting(self) -> None:
        if self._painter is not None:
            self._painter.stop()
            self._painter = None
        if self._desks:
            self._paint_board()

    def _show_report(self, deployed: DeployedFund, record: SessionRecord) -> None:
        self._stop_painting()
        self._phase = "done"
        self._record = record
        self.query_one("#report-head", Static).update(session_headline(deployed.name, record))
        self.query_one("#report-foot", Static).update(
            Group(
                book_summary(record),
                Text.assemble(("✓ ", f"bold {GREEN}"), ("Recorded ", MUTED), (str(Ledger(self._directory).path(record.session)), MUTED)),
            )
        )
        self.refresh_bindings()  # phase changed: esc is offered again
        nav = self.query_one("#report-nav", OptionList)
        nav.clear_options()
        nav.add_options(session_nav(record))
        self.query_one("#run-panes", ContentSwitcher).current = "run-report"
        nav.highlighted = first_selectable(nav)
        nav.focus()

    def _fail(self, exc: Exception) -> None:
        self._stop_painting()
        self._phase = "failed"
        phase = self.query_one("#run-phase", Static)
        if isinstance(exc, NothingDue):
            phase.update(Text.assemble(("Nothing due  ", f"bold {BRIGHT}"), (f"{exc}", MUTED), ("\n\nThe fund is up to date. Run it again when the next session is in. esc to go back.", MUTED)))
        else:
            phase.update(Text.assemble(("✗ ", f"bold {RED}"), (f"{type(exc).__name__}: {exc}", RED), ("\n\nesc to go back", MUTED)))
            self.notify(str(exc), title="Run failed", severity="error")
        self.refresh_bindings()


class SessionsScreen(Screen):
    """One fund's history: the running numbers, the equity curve, and every
    session it has recorded. Enter on a session opens its full report.
    Running and the kill switch live on the fund list, not here.
    """

    BINDINGS = [Binding("escape", "back", "back")]

    def __init__(self, directory: Path) -> None:
        super().__init__()
        self._directory = directory
        self._snap: PaperSnapshot | None = None
        self._shown: list[SessionRecord] = []  # newest first, as listed

    def compose(self) -> ComposeResult:
        with Vertical(id="pf"):
            yield Static("", id="pf-head")
            yield Static("", id="pf-status")
            yield StatTiles(id="stats")
            with Vertical(id="curve-box"):
                yield Static("", id="curve")
            yield Static("", id="scorecard")
            with Horizontal(id="pf-panes"):
                with Vertical(id="report-rail"):
                    yield Static(Text("SESSIONS", style=MUTED), classes="rail-title")
                    yield OptionList(id="pf-sessions")
                with VerticalScroll(id="report-detail"):
                    yield Static("", id="detail-pane")
        yield Footer()

    def on_mount(self) -> None:
        self._load()

    def on_screen_resume(self) -> None:
        self._load()

    def action_back(self) -> None:
        self.app.pop_screen()

    def _load(self) -> None:
        try:
            snap = PaperSnapshot(self._directory)
        except ValueError as exc:
            self._snap = None
            self.query_one("#pf-head", Static).update(Text(str(self._directory), style=f"bold {BRIGHT}"))
            self.query_one("#pf-status", Static).update(Text.assemble(("✗ ", f"bold {RED}"), (str(exc), RED)))
            return
        self._snap = snap
        spec = snap.spec
        staff = ", ".join(s.title for s in spec.strategies)
        self.query_one("#pf-head", Static).update(
            Group(
                Text.assemble((snap.deployed.name, f"bold {BRIGHT}"), (f"  ·  {snap.deployed.broker}", MUTED)),
                Text(f"{staff}  ·  {cadence_identity(spec)}  ·  ${spec.capital:,.0f}" f"  ·  {' '.join(snap.deployed.universe)}", style=MUTED),
            )
        )
        self.query_one("#pf-status", Static).update(snap.status())
        self._render_numbers(snap)
        self._render_sessions(snap)

    def _render_numbers(self, snap: PaperSnapshot) -> None:
        curve_box = self.query_one("#curve-box", Vertical)
        curve_box.border_title = "equity curve"
        curve_box.border_subtitle = f"[{GREEN}]██[/] fund   [{CYAN}]──[/] {snap.spec.benchmark}"
        if not snap.records:
            self.query_one("#stats", StatTiles).add_class("hidden")
            self.query_one("#scorecard", Static).add_class("hidden")
            self.query_one("#curve", Static).update(Text("The curve starts with the first session.", style=MUTED))
            return
        self.query_one("#stats", StatTiles).remove_class("hidden")
        m = snap.metrics()
        self.query_one("#stats", StatTiles).update(snap.spec.benchmark, snap.nav, m.total_return_pct, m.benchmark_return_pct, m.excess_return_pct, m.sharpe_ratio, m.max_drawdown_pct)
        _, nav, bench = snap.curves()
        curve_widget = self.query_one("#curve", Static)
        width = curve_widget.content_size.width or 80
        curve_widget.update(Group(*render_area_chart(nav, bench, snap.spec.capital, min(width, 100))))
        card = score(snap.records)
        scorecard = self.query_one("#scorecard", Static)
        scorecard.update(Group(analyst_table(card), strategy_table(card)))
        scorecard.remove_class("hidden")

    def _render_sessions(self, snap: PaperSnapshot) -> None:
        menu = self.query_one("#pf-sessions", OptionList)
        menu.clear_options()
        self._shown = list(reversed(snap.records))
        if not self._shown:
            self.query_one("#detail-pane", Static).update(Text("No sessions recorded yet.\n\nThe first run values the book at the most " "recent completed close and makes the first decision; the run after " "executes it.", style=MUTED))
            return
        navs = [snap.spec.capital, *(r.nav for r in snap.records)]
        day: str | None = None
        for i, record in enumerate(self._shown):
            index = len(snap.records) - 1 - i
            grouped = is_intraday(record.session)
            if grouped and record.session[:10] != day:  # a minute fund's bars, under their day
                day = record.session[:10]
                menu.add_option(Option(day_heading(day, snap.records, navs), disabled=True))
            menu.add_option(Option(session_row(record, navs[index], time_only=grouped), id=f"s:{i}"))
        menu.highlighted = menu.get_option_index("s:0")
        menu.focus()

    @on(OptionList.OptionHighlighted, "#pf-sessions")
    def _highlight(self, event: OptionList.OptionHighlighted) -> None:
        oid = (event.option.id or "") if event.option else ""
        if oid.startswith("s:"):
            record = self._shown[int(oid.split(":")[1])]
            self.query_one("#detail-pane", Static).update(session_overview(record))
            self.query_one("#report-detail", VerticalScroll).scroll_home(animate=False)

    @on(OptionList.OptionSelected, "#pf-sessions")
    def _open(self, event: OptionList.OptionSelected) -> None:
        oid = event.option.id or ""
        if oid.startswith("s:") and self._snap is not None:
            record = self._shown[int(oid.split(":")[1])]
            self.app.push_screen(SessionReportScreen(self._snap.deployed.name, record))


class SessionReportScreen(Screen):
    """One recorded session, browsable: every signal on the rail, the full
    thesis on the right. The same browser the tick lands on."""

    BINDINGS = [Binding("escape", "back", "back")]

    def __init__(self, name: str, record: SessionRecord) -> None:
        super().__init__()
        self._name = name
        self._record = record

    def compose(self) -> ComposeResult:
        with Vertical(id="run-report"):
            yield Static("", id="report-head")
            with Horizontal(id="report-panes"):
                with Vertical(id="report-rail"):
                    yield OptionList(id="report-nav")
                with VerticalScroll(id="report-detail"):
                    yield Static("", id="detail-pane")
            yield Static("", id="report-foot")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#report-head", Static).update(session_headline(self._name, self._record))
        self.query_one("#report-foot", Static).update(book_summary(self._record))
        nav = self.query_one("#report-nav", OptionList)
        nav.add_options(session_nav(self._record))
        nav.highlighted = first_selectable(nav)
        nav.focus()

    def action_back(self) -> None:
        self.app.pop_screen()

    @on(OptionList.OptionHighlighted, "#report-nav")
    def _browse(self, event: OptionList.OptionHighlighted) -> None:
        oid = (event.option.id or "") if event.option else ""
        detail = session_detail(self._record, oid)
        if detail is not None:
            self.query_one("#detail-pane", Static).update(detail)
            self.query_one("#report-detail", VerticalScroll).scroll_home(animate=False)


def _resolve_tui_run_plan(directory: Path) -> _TUIRunPlan:
    if not isinstance(directory, (str, os.PathLike)):
        raise AdmissionError("TUI paper run path is invalid.")
    candidate = Path(directory)
    with tui_paper_admission(candidate.name, candidate) as (root, admission):
        deployed = load_deployed(candidate)
        if deployed.broker != "paper":
            raise AdmissionError("The native TUI admits local paper funds only.")
        ledger = Ledger(candidate)
        state = ledger.replay(deployed.spec.capital)
        if state.halted is not None:
            raise AdmissionError("The paper fund is halted; press r to resume before running.")
        settings = resolve_settings(root, admission=admission)
        capture = _tui_capture(root, deployed, settings)
        operation_id = uuid4().hex
        request_id = uuid4().hex
        preview_id = uuid4().hex
        preview_digest = _operation_digest(
            {
                "action": "preview",
                "capture_digest": capture.digest,
                "expected_head": state.prev_hash,
                "operation_id": preview_id,
                "request_id": request_id,
            }
        )
        dispatch = _make_tui_run_dispatch(
            capture,
            admission,
            operation_id=preview_id,
            operation_digest=preview_digest,
            include_llm=False,
        )
        with make_data_client(capture.data_provider, dispatch=dispatch) as raw:
            due = next_session(
                CachedDataClient(raw, live=deployed.spec.is_intraday),
                deployed.spec,
                state.last_session,
            )
        action = "run" if due is not None else "redo" if state.last_session else None
        if action == "run":
            operation_digest = ledger.tick_request_digest(
                request_id,
                expected_head=state.prev_hash,
                session=due,
                operation_id=operation_id,
                capture_id=capture.capture_id,
                capture_digest=capture.digest,
            )
        elif action == "redo":
            operation_digest = ledger.redo_request_digest(request_id, state.prev_hash)
        else:
            operation_digest = ""
        return _TUIRunPlan(
            directory=candidate,
            deployed=deployed,
            state=state,
            expected_head=state.prev_hash,
            due=due,
            action=action,
            capture=capture,
            operation_id=operation_id,
            request_id=request_id,
            operation_digest=operation_digest,
        )


def _tui_capture(root, deployed: DeployedFund, settings: RuntimeSettings) -> FrozenCapture:
    _require_tui_providers(settings)
    return freeze_capture(
        root=root,
        subject_id=deployed.name,
        mandate_digest=mandate_hash(deployed.spec),
        universe=deployed.universe,
        broker=deployed.broker,
        settings=settings,
        credential_versions={},
        code_version=code_version(),
        mandate_snapshot=deployed.spec.model_dump(mode="json"),
    )


def _require_tui_providers(settings: RuntimeSettings) -> None:
    if not isinstance(settings, RuntimeSettings):
        raise AdmissionError("Captured paper settings are unavailable.")
    if settings.data_provider != "yfinance" or settings.llm_provider != "Ollama" or settings.model not in APPROVED_LOCAL_MODELS:
        raise AuthorizationDenied("TUI paper runs require free yfinance and an approved local Ollama model.")
    data_target = ProviderTarget(kind="data", provider=settings.data_provider)
    llm_target = ProviderTarget(
        kind="llm",
        provider=settings.llm_provider,
        model=settings.model,
        endpoint=settings.endpoint,
    )
    try:
        validate_llm_transport(llm_target)
        data_class = classify_provider(data_target)
        llm_class = classify_provider(
            llm_target,
            approved_local_models=APPROVED_LOCAL_MODELS,
        )
    except AuthorizationDenied:
        raise AuthorizationDenied("TUI paper runs require free yfinance and an approved local Ollama model.") from None
    if data_class is not ProviderClass.FREE_DATA or llm_class is not ProviderClass.LOCAL:
        raise AuthorizationDenied("TUI paper runs require free yfinance and an approved local Ollama model.")


def _make_tui_run_dispatch(
    capture: FrozenCapture,
    admission,
    *,
    operation_id: str,
    operation_digest: str,
    include_llm: bool,
):
    if not isinstance(capture, FrozenCapture) or type(include_llm) is not bool:
        raise AuthorizationDenied("TUI provider capture is invalid.")
    _require_tui_providers(
        RuntimeSettings(
            data_provider=capture.data_provider,
            llm_provider=capture.llm_provider,
            model=capture.model,
            endpoint=capture.endpoint,
            timeout_seconds=capture.timeout_seconds,
            parameters=capture.parameters,
            version=capture.settings_version,
            provenance=capture.provenance,
        )
    )
    targets = [ProviderTarget(kind="data", provider=capture.data_provider)]
    approved_models = frozenset()
    if include_llm:
        llm_target = ProviderTarget(
            kind="llm",
            provider=capture.llm_provider,
            model=capture.model,
            endpoint=capture.endpoint,
        )
        if classify_provider(llm_target, approved_local_models=APPROVED_LOCAL_MODELS) is not ProviderClass.LOCAL:
            raise AuthorizationDenied("TUI local-model authorization is unavailable.")
        if classify_provider(KEN_FRENCH_BREAKPOINTS_TARGET) is not ProviderClass.FREE_DATA:
            raise AuthorizationDenied("TUI free-data authorization is unavailable.")
        targets.extend((llm_target, KEN_FRENCH_BREAKPOINTS_TARGET))
        approved_models = APPROVED_LOCAL_MODELS
    bounds = {target.identity: (10000, Decimal("0"), 10000) for target in targets}
    return make_one_shot_dispatch(
        root_id=capture.root_id,
        subject_id=capture.subject_id,
        capture_digest=capture.digest,
        operation_id=operation_id,
        operation_digest=operation_digest,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=15),
        targets=tuple(targets),
        max_calls=sum(value[0] for value in bounds.values()),
        max_cost=Decimal("0"),
        max_resources=sum(value[2] for value in bounds.values()),
        upper_bound_costs={target.identity: Decimal("0") for target in targets},
        per_target_bounds=bounds,
        approved_local_models=approved_models,
        boundary_check=admission.require_root_owner,
    )


def _verify_tui_run_plan(root, admission, plan: _TUIRunPlan) -> tuple[DeployedFund, FundState]:
    if not isinstance(plan, _TUIRunPlan):
        raise AdmissionError("TUI paper run confirmation is invalid.")
    admission.require_root_owner()
    root.revalidate()
    if plan.directory.name != plan.deployed.name:
        raise AdmissionError("Paper deployment identity changed after confirmation; review the fund again.")
    deployed = load_deployed(plan.directory)
    capture = plan.capture
    if deployed.name != capture.subject_id or deployed.name != plan.directory.name or deployed.broker != capture.broker or mandate_hash(deployed.spec) != capture.mandate_digest or tuple(deployed.universe) != capture.universe or capture.code_version != code_version():
        raise AdmissionError("Paper deployment changed after confirmation; review the fund again.")
    settings = resolve_settings(root, admission=admission)
    _require_tui_providers(settings)
    current_capture = _tui_capture(root, deployed, settings)
    if current_capture.digest != capture.digest or current_capture.root_id != capture.root_id:
        raise AdmissionError("Paper provider settings changed after confirmation; review the fund again.")
    state = Ledger(plan.directory).replay(deployed.spec.capital)
    if state.prev_hash != plan.expected_head:
        raise AdmissionError("Paper ledger head changed after confirmation; review the fund again.")
    if state.halted is not None:
        raise AdmissionError("The paper fund is halted; press r to resume before running.")
    return deployed, state


def _tui_fund_factory(capture: FrozenCapture, dispatch):
    def build(spec: FundSpec) -> Fund:
        if not isinstance(spec, FundSpec) or spec.name != capture.subject_id or mandate_hash(spec) != capture.mandate_digest:
            raise AuthorizationDenied("TUI paper mandate does not match its operation capture.")
        return Fund(
            spec,
            blind=True,
            llm_factory=lambda model_spec: _tui_llm_factory(
                capture,
                dispatch,
                temperature=model_spec.params.get("temperature"),
            ),
            breakpoints_dispatch=dispatch,
        )

    return build


def _tui_llm_factory(
    capture: FrozenCapture,
    dispatch,
    *,
    on_token=None,
    temperature: float | None = None,
):
    return make_llm(
        model=capture.model,
        timeout=capture.timeout_seconds,
        max_tokens=int(capture.parameters.get("max_tokens", 4096)),
        on_token=on_token,
        temperature=temperature if temperature is not None else capture.parameters.get("temperature"),
        top_p=capture.parameters.get("top_p"),
        context_size=int(capture.parameters.get("context_size", 8192)),
        api_key=None,
        endpoint=capture.endpoint,
        use_environment=False,
        dispatch=dispatch,
    )


def _operation_digest(payload: dict[str, object]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()
