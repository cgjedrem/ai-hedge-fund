"""The mandate library: saved fund definitions, their backtest history, deletion."""

from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from rich.console import Group
from rich.table import Table
from rich.text import Text
from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen, Screen
from textual.widgets import Footer, OptionList, Static
from textual.widgets.option_list import Option

from hedge_fund import paths
from hedge_fund.backtesting.research import last_score, receipts, summarize
from hedge_fund.fund import discover_funds, FundSpec
from hedge_fund.paper import (
    DeployedFund,
    Ledger,
    LedgerError,
    list_deployed,
    load_deployed,
)
from hedge_fund.runtime.admission import (
    AdmissionCoordinator,
    AdmissionError,
    RootOwnerLease,
    WriterConflict,
)
from hedge_fund.runtime.root import RootContext
from hedge_fund.tui.backtest import BacktestScreen
from hedge_fund.tui.palette import BRIGHT, CYAN, GREEN, MUTED, RED, TEXT
from hedge_fund.tui.shared import cadence_identity, MODE_LABELS, strategy_description


def paper_write_denial() -> str | None:
    from hedge_fund.runtime.handover import (
        enrollment_status,
        has_write_authority,
        write_authority,
    )

    try:
        root = paths.root_context(required=False)
        if root is None:
            return "TUI paper writes require an explicit root; resolve with `aihf --root ROOT handover inspect`."
        configured_paper = Path(paths.PAPER_DIR) if paths.PAPER_DIR is not None else None
        expected_paper = root.path / "paper"
        if configured_paper is None or _absolute_key(configured_paper) != _absolute_key(expected_paper):
            return "TUI paper writes require `paper/` inside the configured root; resolve with `aihf --root ROOT handover inspect`."
        status = enrollment_status(root, verify_inventory=True)
    except Exception:
        return "TUI paper writes are blocked because root enrollment or inventory cannot be verified; run `aihf --root ROOT handover inspect`."
    if status["state"] == "unenrolled":
        return "TUI paper writes require offline root enrollment; resolve with `aihf --root ROOT handover inspect`."
    if status["state"] != "enrolled":
        return f"TUI paper writes are blocked by root enrollment or ledger inventory ({status['reason']}); run `aihf --root ROOT handover inspect`."
    authority = write_authority(root)
    if has_write_authority(authority):
        return None
    reason = authority["reason"] or "write-authority-unavailable"
    if reason == "operator-single-writer-runtime-scope-unavailable":
        return "TUI paper writes are blocked because runtime scope cannot be verified; trusted mode stays disabled. Restore runtime identity, then run `aihf --root ROOT handover inspect`."
    if reason.startswith("operator-single-writer-") or reason == "attested-migration-read-only":
        return f"TUI paper writes require current trusted-single-writer authority ({reason}); run `aihf --root ROOT handover inspect`, review its fresh challenge, then `aihf --root ROOT handover trust-single-writer --inventory-digest DIGEST --operator-acknowledgement EXACT`."
    return f"TUI paper writes are blocked by root write authority ({reason}); run `aihf --root ROOT handover inspect`."


def paper_creation_denial() -> str:
    """Keep TUI creation outside existing-fund admission."""
    return "TUI paper-fund creation is not admitted by the existing-fund workflow; use `aihf --root ROOT paper deploy`."


@contextmanager
def tui_paper_admission(
    identity: str,
    directory: Path | None = None,
) -> Iterator[tuple[RootContext, AdmissionCoordinator]]:
    """Hold root participation; caller owns fund-lane scope."""
    from hedge_fund.paper.deployed import validate_fund_name
    from hedge_fund.runtime.handover import verify_ledger_head, verify_root_inventory

    denial = paper_write_denial()
    if denial is not None:
        raise AdmissionError(denial)
    root = paths.root_context(required=False)
    if root is None:
        raise AdmissionError("TUI paper admission requires an explicit root.")
    try:
        validate_fund_name(identity)
    except (TypeError, ValueError):
        raise AdmissionError("TUI paper admission requires a canonical fund name.") from None
    expected = root.path / "paper" / identity
    candidate = expected if directory is None else Path(directory)
    if _absolute_key(candidate) != _absolute_key(expected):
        raise AdmissionError("TUI paper admission requires the fund directory under the configured root.")
    owner = None
    try:
        try:
            if directory is not None:
                root.resolve(f"paper/{identity}")
            owner = RootOwnerLease.acquire(root, timeout=0)
            admission = AdmissionCoordinator(root, owner_lease=owner)
            verify_root_inventory(root)
            if directory is not None:
                verify_ledger_head(root, identity)
            admission.require_root_owner()
        except WriterConflict as exc:
            raise AdmissionError(f"TUI paper admission denied: another participating writer holds the required root or fund lane ({exc}).") from None
        except AdmissionError:
            raise
        except Exception as exc:
            raise AdmissionError(f"TUI paper admission is unavailable ({type(exc).__name__}); run `aihf --root ROOT handover inspect`.") from None

        yield root, admission
    except WriterConflict as exc:
        raise AdmissionError(f"TUI paper admission denied: another participating writer holds the required root or fund lane ({exc}).") from None
    finally:
        if owner is not None:
            owner.close()


def _absolute_key(path: Path) -> str:
    return os.path.normcase(os.path.abspath(os.fspath(path)))


def mandate_delete_denial() -> str:
    """Mandate deletion has no root-admitted write path."""
    return "Mandate deletion is unavailable: the TUI cannot delete under root admission. Mandates and backtests were kept."


class FundSelectScreen(Screen):
    """'Backtest a mandate', master-detail: mandate slots on the left, the
    highlighted mandate's latest backtest stats and its backtest history
    (newest first) on the right. Enter opens the backtest window picker.
    Refreshes on resume.
    """

    BINDINGS = [
        Binding("escape", "back", "back"),
        Binding("d", "delete", "delete mandate"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._summaries: dict[tuple[str, float], dict | None] = {}

    def compose(self) -> ComposeResult:
        with Horizontal(id="select"):
            with Vertical(id="select-rail"):
                yield Static(Text("YOUR MANDATES", style=MUTED), classes="rail-title")
                yield OptionList(id="select-menu")
            with VerticalScroll(id="select-detail"):
                yield Static("", id="detail-body")
        yield Footer()

    def on_mount(self) -> None:
        self._populate()

    def on_screen_resume(self) -> None:
        self._populate()

    def action_back(self) -> None:
        self.app.pop_screen()

    def _populate(self) -> None:
        # Slots carry the mandate's path, not just its name: a file's stem and
        # the fund's name need not match (example.yaml holds "example-fund"),
        # and delete has to remove the right file.
        self._slots = discover_funds(paths.MANDATES_DIR)
        menu = self.query_one("#select-menu", OptionList)
        menu.clear_options()
        if not self._slots:
            self.query_one("#detail-body", Static).update(Text("No funds yet — build one under Paper trading and it shows up here too.", style=MUTED))
            return
        for i, entry in enumerate(self._slots):
            if entry.spec is None:
                menu.add_option(Option(Text(f"{entry.path.name} — Unavailable\n{entry.error}", style=MUTED), id=f"unavailable:{i}", disabled=True))
            else:
                menu.add_option(Option(_slot_card(i, entry.spec, last_score(entry.spec.name)), id=f"fund:{i}"))
        # Options added after mount leave `highlighted` unset — pin it so the
        # detail pane fills in and Enter works without an arrow press first.
        first = next((i for i, entry in enumerate(self._slots) if entry.spec is not None), None)
        menu.highlighted = first
        menu.focus()
        if first is not None:
            self._show_detail(first)
        else:
            self.query_one("#detail-body", Static).update(Text("Saved mandates are unavailable. Recreate them in the builder or update their configurations.", style=MUTED))

    @on(OptionList.OptionHighlighted, "#select-menu")
    def _hover(self, event: OptionList.OptionHighlighted) -> None:
        oid = (event.option.id or "") if event.option else ""
        if oid.startswith("fund:"):
            self._show_detail(int(oid.split(":")[1]))

    @on(OptionList.OptionSelected, "#select-menu")
    def _choose(self, event: OptionList.OptionSelected) -> None:
        oid = event.option.id or ""
        if oid.startswith("fund:"):
            spec = self._slots[int(oid.split(":")[1])].spec
            if spec is None:
                return
            self.app.push_screen(BacktestScreen(spec))

    def action_delete(self) -> None:
        menu = self.query_one("#select-menu", OptionList)
        if not self._slots or menu.highlighted is None:
            return
        self.notify(mandate_delete_denial(), severity="warning")

    def _finish_delete(self, scope: str | None) -> None:
        """Callback from the confirm screen: None cancelled, otherwise the
        blast radius the user picked."""
        if scope is None:
            return
        # Stale confirm callbacks stay denied.
        self.notify(mandate_delete_denial(), severity="warning")

    def _show_detail(self, i: int) -> None:
        spec = self._slots[i].spec
        if spec is None:
            return
        self.query_one("#detail-body", Static).update(_fund_detail(spec, self._history(spec.name)))

    def _history(self, name: str) -> list[dict]:
        """Every backtest of this mandate, newest first, as light summaries.
        Cached by (path, mtime) so arrowing the list stays instant."""
        out: list[dict] = []
        for p in receipts(name):
            mtime = p.stat().st_mtime
            key = (str(p), mtime)
            if key not in self._summaries:
                self._summaries[key] = summarize(p, mtime)
            summ = self._summaries[key]
            if summ is not None:
                out.append(summ)
        out.sort(key=lambda s: s["mtime"], reverse=True)
        return out


class ConfirmWipeScreen(ModalScreen[bool]):
    """Everything with a name is about to go — because the user pressed `d`
    on the fund, or gave the builder a name that already belongs to one.
    The irreversible things in this app all look the same: what goes, named
    exactly, and one key to say yes.
    """

    BINDINGS = [
        Binding("escape", "cancel", "keep it"),
        Binding("enter", "confirm", "yes", priority=True),
    ]

    def __init__(self, name: str, *, replacing: bool = False) -> None:
        super().__init__()
        self._name = name
        self._replacing = replacing

    def compose(self) -> ComposeResult:
        verb = "Replace" if self._replacing else "Delete"
        then = "The new fund takes the name." if self._replacing else "The name is free again."
        yes = "replace it — the new fund starts from nothing" if self._replacing else "delete it"
        no = "keep it and pick another name" if self._replacing else "keep it"
        with Vertical(id="confirm"):
            yield Static(Text.assemble((f"{verb} ", f"bold {BRIGHT}"), (self._name, f"bold {RED}"), ("?", f"bold {BRIGHT}")), id="confirm-q")
            yield Static(_wipe_manifest(self._name, then), id="confirm-files")
            yield Static(Text.assemble(("enter", f"bold {RED}"), (f"  {yes}\n", MUTED), ("esc", f"bold {BRIGHT}"), (f"    {no}", MUTED)), id="confirm-keys")
        yield Footer()

    def action_cancel(self) -> None:
        self.dismiss(False)

    def action_confirm(self) -> None:
        self.dismiss(True)


class ConfirmDeleteScreen(ModalScreen[str | None]):
    """Deleting is the only irreversible thing this app does, so it gets a
    screen of its own: the exact files at stake, and two keys for the two
    blast radii — the mandate alone, or the mandate and its history.
    """

    BINDINGS = [
        Binding("escape", "cancel", "cancel"),
        Binding("enter", "delete_mandate", "delete the mandate", priority=True),
        Binding("ctrl+d", "delete_all", "delete mandate + history", priority=True),
    ]

    def __init__(self, path: Path, spec: FundSpec, history: list[dict]) -> None:
        super().__init__()
        self._path = path
        self._spec = spec
        self._backtests = sum(1 for h in history if h["kind"] == "backtest")

    def compose(self) -> ComposeResult:
        with Vertical(id="confirm"):
            yield Static(Text.assemble(("Delete ", f"bold {BRIGHT}"), (self._spec.name, f"bold {RED}"), ("?", f"bold {BRIGHT}")), id="confirm-q")
            yield Static(self._manifest(), id="confirm-files")
            yield Static(Text.assemble(("enter", f"bold {GREEN}"), ("   delete the mandate\n", MUTED), ("ctrl+d", f"bold {RED}"), ("  delete the mandate and its history\n", MUTED), ("esc", f"bold {BRIGHT}"), ("     cancel", MUTED)), id="confirm-keys")
        yield Footer()

    def _manifest(self) -> Text:
        """What is on the table, named exactly — a count is easy to misread
        when the thing being counted cannot be recovered."""
        lines = Text()
        lines.append(f"{self._path.name}\n", style=TEXT)
        lines.append("  the mandate — strategies, staff, risk, capital\n\n", style=MUTED)
        if self._backtests:
            lines.append(f"{self._backtests} " f"{'backtest' if self._backtests == 1 else 'backtests'}\n", style=CYAN)
            lines.append("  saved results — kept unless you press ctrl+d", style=MUTED)
        else:
            lines.append("No saved backtests.", style=MUTED)
        lines.append("\n\nPaper funds deployed from this mandate keep their own copy.", style=MUTED)
        return lines

    def action_cancel(self) -> None:
        self.dismiss(None)

    def action_delete_mandate(self) -> None:
        self.dismiss("mandate")

    def action_delete_all(self) -> None:
        self.dismiss("all")


def fund_name_taken(name: str) -> bool:
    """A name is taken if a saved definition or a paper fund already owns it;
    the builder refuses both so one name means one fund everywhere."""
    return (paths.MANDATES_DIR / f"{name}.yaml").exists() or (paths.PAPER_DIR / name).exists()


def newest_paper_universe() -> list[str] | None:
    """The tickers of the most recently created paper fund — the builder's
    ticker step prefills from it, so a returning user just presses enter."""
    newest: DeployedFund | None = None
    for directory in list_deployed(paths.PAPER_DIR):
        try:
            deployed = load_deployed(directory)
        except ValueError:
            continue
        if newest is None or deployed.created > newest.created:
            newest = deployed
    return newest.universe if newest else None


def wipe_fund(name: str) -> None:
    """Reject TUI deletion; preserve mandate, receipts, and paper history."""
    denial = paper_write_denial()
    if denial is not None:
        raise RuntimeError(denial)
    raise RuntimeError(mandate_delete_denial())


def short_tickers(universe: list[str], limit: int = 2) -> str:
    """A run's tickers, short enough for a one-line log row: the first few,
    then a count of the rest. The full list is on the run's own report."""
    if not universe:
        return "—"
    if len(universe) <= limit:
        return " ".join(universe)
    return f"{' '.join(universe[:limit])} +{len(universe) - limit}"


def _wipe_manifest(name: str, then: str) -> Text:
    """What wiping *name* destroys, named exactly, and what *then* follows."""
    lines = Text()
    if (paths.MANDATES_DIR / f"{name}.yaml").exists():
        lines.append(f"{name}.yaml\n", style=TEXT)
        lines.append("  the saved definition — strategies, staff, risk, capital\n", style=MUTED)
    backtests = len(receipts(name))
    if backtests:
        lines.append(f"{backtests} {'backtest' if backtests == 1 else 'backtests'}\n", style=CYAN)
        lines.append("  saved results\n", style=MUTED)
    directory = paths.PAPER_DIR / name
    if directory.exists():
        try:
            sessions = len(Ledger(directory).records())
            what = f"{sessions} {'session' if sessions == 1 else 'sessions'} of ledger"
        except (LedgerError, OSError, ValueError):
            what = "its ledger"
        lines.append("paper fund\n", style=RED)
        lines.append(f"  {what}, the book, and every event — the track record\n", style=MUTED)
    lines.append(f"\n{then} None of this can be recovered.", style=MUTED)
    return lines


def _slot_card(index: int, spec: FundSpec, score: tuple | None) -> Text:
    """One slot in the left rail: number + name + last-score arrow on top, a
    short mandate line beneath. Spare on purpose — the detail pane carries the
    full stats."""
    n = len(spec.strategies)
    card = Text()
    card.append(f" {index + 1:02d}  ", style=f"bold {CYAN}")
    # Bold but uncoloured on purpose: the name inherits the option list's
    # colour, so the highlighted row can turn it green (see app.tcss).
    card.append(spec.name, style="bold")
    if score is not None:
        total, _, _ = score
        up = total >= 0
        card.append(f"   {'▲' if up else '▼'} {total:+.1%}", style=f"bold {GREEN if up else RED}")
    card.append(f"\n     {n} {'strategy' if n == 1 else 'strategies'}" f"  ·  {cadence_identity(spec)}", style=MUTED)
    card.append("\n     " + ", ".join(MODE_LABELS[s.blend.mode] for s in spec.strategies), style=MUTED)
    return card


def _fund_detail(spec: FundSpec, history: list[dict]) -> Group:
    """The right pane: the mandate's identity, its latest backtest stats, then
    every backtest, newest first, each with the tickers it was run over."""
    staff = ", ".join(s.title for s in spec.strategies)
    parts: list = [
        Text(spec.name, style=f"bold {BRIGHT}"),
        Text(f"{staff}  ·  {cadence_identity(spec)}  ·  ${spec.capital:,.0f}", style=MUTED),
    ]
    parts.extend(Text(f"{s.title}: {strategy_description(s)}", style=MUTED) for s in spec.strategies)

    if not history:
        parts.append(Text("\nNo backtests yet.", style=MUTED))
        parts.append(Text("\nEnter to backtest this mandate over history", style=MUTED))
        return Group(*parts)

    latest = history[0]
    facts = [f"{latest['start']} → {latest['end']}", f"{latest['n_cycles']} cycles"]
    if latest["universe"]:
        facts.append(" ".join(latest["universe"]))
    parts.append(Text("\nLATEST BACKTEST", style=f"bold {BRIGHT}"))
    parts.append(Text("  ·  ".join(facts), style=MUTED))
    parts.append(_stat_list(latest))

    parts.append(Text("\nBACKTESTS", style=f"bold {BRIGHT}"))
    # Three columns, not four. The kind and the number are pinned with no_wrap
    # so a narrow pane can never drop the result — the tickers ride along in
    # the middle column and are the only thing allowed to ellipsize.
    log = Table(box=None, show_header=False, padding=(0, 1), pad_edge=False, expand=True)
    log.add_column(no_wrap=True)  # kind
    log.add_column(overflow="ellipsis", no_wrap=True)  # when · tickers
    log.add_column(justify="right", no_wrap=True)  # headline number
    for h in history[:12]:
        up = h["total"] >= 0
        when = Text(f"{h['start']} → {h['end']}", style=MUTED)
        if h["universe"]:
            when.append(f"  {short_tickers(h['universe'])}", style=CYAN)
        log.add_row(
            Text("backtest", style=MUTED),
            when,
            Text(f"{h['total']:+.1%}", style=GREEN if up else RED),
        )
    parts.append(log)
    return Group(*parts)


def _stat_list(bt: dict) -> Table:
    """The headline backtest numbers as a label/value list.

    These used to be a six-column table, which truncated its own headers
    ("Ann…", "Shar…") in the detail pane. Reading down instead of across
    keeps every label a whole word at any terminal width.
    """
    table = Table(box=None, show_header=False, padding=(0, 1), pad_edge=False)
    table.add_column(style=MUTED, width=14)
    table.add_column(justify="right", min_width=8)
    table.add_row("Total return", Text(f"{bt['total']:+.1%}", style=f"bold {GREEN if bt['total'] >= 0 else RED}"))
    table.add_row("Annualized", Text(f"{bt['annualized']:+.1%}", style=TEXT))
    table.add_row("Sharpe", Text(f"{bt['sharpe']:.2f}", style=(GREEN if bt["sharpe"] > 1 else "yellow" if bt["sharpe"] > 0 else RED)))
    table.add_row("Max drawdown", Text(f"{bt['maxdd']:.1%}", style=RED))
    table.add_row(bt["benchmark"], Text(f"{bt['benchret']:+.1%}", style=TEXT))
    table.add_row("Excess", Text(f"{bt['excess']:+.1%}", style=f"bold {GREEN if bt['excess'] >= 0 else RED}"))
    return table
