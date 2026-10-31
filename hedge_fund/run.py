"""Run the AI hedge fund.

Two modes, one engine. A backtest replays a mandate over history; a paper
fund is that same mandate deployed against a universe and advanced one
completed session at a time, keeping a ledger. Both call `advance`; only
the clock, the broker, and where the state lives differ.

Usage::

    aihf --root /path/to/hedge-fund-data
        No arguments: the interactive app (a Textual TUI). Backtest a
        mandate, deploy and advance a paper fund, or build a new mandate.

    aihf --root /path/to/hedge-fund-data backtest mandates/example.yaml --universe AAPL,MSFT
        Replay the mandate over history (default: the last 18 months up to
        the latest completed session). Full result JSON on stdout; a copy
        lands in research/. --start/--end/--out/--model.

    aihf --root /path/to/hedge-fund-data paper create alpha --mandate mandates/example.yaml --universe AAPL,MSFT
        Deploy a paper fund: snapshot the mandate, fix the universe, open an
        empty ledger and a book with the mandate's capital.

    aihf paper tick alpha
        Advance the fund by exactly one session and append it to the ledger:
        the oldest unrecorded completed close for a daily fund, the current
        bar at prints taken now for a minute fund. Idempotent; what a
        scheduler calls after each close:

            30 18 * * 1-5  aihf --root /path/to/hedge-fund-data paper tick alpha

        A missed day is never skipped — the next tick advances the oldest
        unrecorded session. --session names it explicitly.

    aihf paper run alpha
        Stay up and do what tick does whenever a session is due: after each
        midnight for a daily fund, at every bar inside the window for a
        minute fund. One process per fund, found by its runner.pid; Ctrl-C,
        SIGTERM or `aihf paper stop alpha` stop it after the session in
        flight. A minute fund's time down is logged as a gap, never back-filled.

    aihf paper status alpha | list | halt alpha --reason "..." | resume alpha

    aihf paper scorecard alpha
        Grade every analyst (hit rate, slugging, IC) and every strategy
        (P&L between executions) on the fund's ledger. JSON on stdout.

A mandate is the desk — strategies, staff, risk, capital, cadence — and
never names tickers; the universe is fixed when a fund is deployed (paper)
or given per study (backtest).
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import date as _date
from pathlib import Path

from rich.console import Console

from hedge_fund import paths
from hedge_fund.runtime.root import RootContext, RootPathError

backtest_fund = None
save_result = None
format_shares = None
CachedDataClient = None
make_data_client = None
is_intraday = None
completed_through = None
Cadence = None
Fund = None
FundSpec = None
load_spec = None
normalize_universe = None
deploy = None
is_running = None
Ledger = None
LedgerError = None
list_deployed = None
load_deployed = None
NothingDue = None
redo = None
serve = None
stop_runner = None
tick = None
validate_fund_name = None
ensure_mandates_dir = None
PAPER_DIR = None
FundHalted = None
SessionRecord = None
score = None
cost_line = None
analyst_table = None
strategy_table = None
_CONFIGURED_PAPER_DIR: Path | None = None


def main(argv: list[str] | None = None) -> None:
    # Persona/LLM text is arbitrary unicode; a Windows console defaults to
    # cp1252 and would crash on it. Force UTF-8 (with replacement) on both
    # streams before anything prints.
    for stream in (sys.stdout, sys.stderr):
        if stream is not None and hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        context = RootContext.open(args.root)
    except RootPathError as exc:
        parser.error(str(exc))

    try:
        with paths.bound_root(context):
            try:
                paths.load_root_dotenv(context, enabled=args.load_dotenv)
            except (RootPathError, UnicodeError, ValueError) as exc:
                parser.error(str(exc))
            _load_runtime()
            if args.model:
                os.environ["HEDGE_FUND_LLM_MODEL"] = args.model
            ensure_mandates_dir()

            if args.command is None:
                from hedge_fund.tui.app import HedgeFundApp

                HedgeFundApp().run()
                return

            console = Console(stderr=True)
            try:
                if args.command == "backtest":
                    _backtest(args, parser, console)
                else:
                    _paper(args, parser, console)
            except (FundHalted, NothingDue, LedgerError) as exc:
                console.print(f"[red]{exc}[/]")
                sys.exit(1)
    finally:
        context.close()


def _load_runtime() -> None:
    global backtest_fund, save_result, format_shares, CachedDataClient
    global make_data_client, is_intraday, completed_through, Cadence, Fund
    global FundSpec, load_spec, normalize_universe, deploy, is_running
    global Ledger, LedgerError, list_deployed, load_deployed, NothingDue
    global redo, serve, stop_runner, tick, validate_fund_name
    global ensure_mandates_dir, PAPER_DIR, FundHalted, SessionRecord
    global score, cost_line, analyst_table, strategy_table
    global _CONFIGURED_PAPER_DIR

    from hedge_fund.backtesting import backtest_fund as engine_backtest_fund
    from hedge_fund.backtesting import save_result as engine_save_result
    from hedge_fund.brokers.models import format_shares as engine_format_shares
    from hedge_fund.data import CachedDataClient as EngineCachedDataClient
    from hedge_fund.data import make_data_client as engine_make_data_client
    from hedge_fund.data.bars import is_intraday as engine_is_intraday
    from hedge_fund.data.sessions import completed_through as engine_completed_through
    from hedge_fund.fund import Cadence as EngineCadence
    from hedge_fund.fund import Fund as EngineFund
    from hedge_fund.fund import FundSpec as EngineFundSpec
    from hedge_fund.fund import load_spec as engine_load_spec
    from hedge_fund.fund import normalize_universe as engine_normalize_universe
    from hedge_fund.paper import deploy as engine_deploy
    from hedge_fund.paper import is_running as engine_is_running
    from hedge_fund.paper import Ledger as EngineLedger
    from hedge_fund.paper import LedgerError as EngineLedgerError
    from hedge_fund.paper import list_deployed as engine_list_deployed
    from hedge_fund.paper import load_deployed as engine_load_deployed
    from hedge_fund.paper import NothingDue as EngineNothingDue
    from hedge_fund.paper import redo as engine_redo
    from hedge_fund.paper import serve as engine_serve
    from hedge_fund.paper import stop_runner as engine_stop_runner
    from hedge_fund.paper import tick as engine_tick
    from hedge_fund.paper import validate_fund_name as engine_validate_fund_name
    from hedge_fund.pipeline import FundHalted as EngineFundHalted
    from hedge_fund.pipeline import SessionRecord as EngineSessionRecord
    from hedge_fund.reporting.console import analyst_table, cost_line, strategy_table
    from hedge_fund.scorecard import score as engine_score

    bindings = {
        "backtest_fund": engine_backtest_fund,
        "save_result": engine_save_result,
        "format_shares": engine_format_shares,
        "CachedDataClient": EngineCachedDataClient,
        "make_data_client": engine_make_data_client,
        "is_intraday": engine_is_intraday,
        "completed_through": engine_completed_through,
        "Cadence": EngineCadence,
        "Fund": EngineFund,
        "FundSpec": EngineFundSpec,
        "load_spec": engine_load_spec,
        "normalize_universe": engine_normalize_universe,
        "deploy": engine_deploy,
        "is_running": engine_is_running,
        "Ledger": EngineLedger,
        "LedgerError": EngineLedgerError,
        "list_deployed": engine_list_deployed,
        "load_deployed": engine_load_deployed,
        "NothingDue": EngineNothingDue,
        "redo": engine_redo,
        "serve": engine_serve,
        "stop_runner": engine_stop_runner,
        "tick": engine_tick,
        "validate_fund_name": engine_validate_fund_name,
        "ensure_mandates_dir": paths.ensure_mandates_dir,
        "FundHalted": EngineFundHalted,
        "SessionRecord": EngineSessionRecord,
        "score": engine_score,
        "cost_line": cost_line,
        "analyst_table": analyst_table,
        "strategy_table": strategy_table,
    }
    for name, value in bindings.items():
        if globals()[name] is None:
            globals()[name] = value
    if PAPER_DIR is None or PAPER_DIR == _CONFIGURED_PAPER_DIR:
        PAPER_DIR = paths.PAPER_DIR
    _CONFIGURED_PAPER_DIR = paths.PAPER_DIR


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="aihf",
        description="Run the AI hedge fund under an explicit data root.",
    )
    parser.add_argument(
        "--root",
        type=Path,
        required=True,
        help="existing absolute NTFS or ext4 data root",
    )
    parser.add_argument(
        "--load-dotenv",
        action="store_true",
        help="load safe non-secret settings from this root's .env",
    )
    parser.add_argument(
        "--model",
        help="LLM the investor agents reason with, e.g. claude-opus-5-5 " "(default: HEDGE_FUND_LLM_MODEL env, else the built-in default); quant " "models ignore it",
    )
    commands = parser.add_subparsers(dest="command")

    backtest = commands.add_parser(
        "backtest",
        help="replay a mandate over history",
        description="Replay a mandate over history: every benchmark session from " "--start to --end, decisions at a rebalance session's close executed at " "the next close. Full result JSON on stdout, a copy in research/.",
    )
    backtest.add_argument(
        "mandate",
        help="path to a mandate YAML; relative paths resolve under --root",
    )
    backtest.add_argument("--universe", required=True, help=_UNIVERSE_HELP)
    backtest.add_argument("--start", help="first session YYYY-MM-DD (default: 78 weeks before --end)")
    backtest.add_argument("--end", help="last session YYYY-MM-DD (default: the latest completed session)")
    backtest.add_argument(
        "--out",
        help="also write the result JSON to this file; relative paths resolve under --root",
    )
    backtest.add_argument("--rebalance", choices=("minute", "daily", "weekly", "monthly"), help="override the mandate cadence for this backtest")

    paper = commands.add_parser("paper", help="deploy and advance a paper fund")
    actions = paper.add_subparsers(dest="action", required=True)

    create = actions.add_parser("create", help="deploy a mandate as a paper fund")
    create.add_argument("name", help="fund name; becomes paper/<name>/ under --root")
    create.add_argument(
        "--mandate",
        required=True,
        help="path to a mandate YAML; relative paths resolve under --root",
    )
    create.add_argument("--universe", required=True, help=_UNIVERSE_HELP)
    create.add_argument("--rebalance", choices=("minute", "daily", "weekly", "monthly"), help="override the mandate cadence before deployment")
    create.add_argument("--approval", action="store_true", help="require approval before executing pending decisions")

    advance = actions.add_parser("tick", help="advance the fund by one session")
    advance.add_argument("name")
    advance.add_argument("--session", help="the session to record (YYYY-MM-DD, or a bar's YYYY-MM-DDTHH:MM:SS); " "must be the next unrecorded one")
    advance.add_argument("--again", action="store_true", help="run the latest recorded session again and replace its record")

    runner = actions.add_parser("run", help="stay up and advance the fund whenever a session is due")
    runner.add_argument("name")

    stopper = actions.add_parser("stop", help="stop a fund's runner after the session in flight")
    stopper.add_argument("name")

    status = actions.add_parser("status", help="NAV, last session, pending decision, halt state")
    status.add_argument("name")

    actions.add_parser("list", help="every deployed paper fund")

    scorecard = actions.add_parser("scorecard", help="grade every analyst and strategy on the ledger")
    scorecard.add_argument("name")

    halt = actions.add_parser("halt", help="set the kill switch: ticks refuse to trade")
    halt.add_argument("name")
    halt.add_argument("--reason", required=True)

    resume = actions.add_parser("resume", help="clear the kill switch")
    resume.add_argument("name")

    approve = actions.add_parser("approve", help="approve a pending decision")
    approve.add_argument("name")
    approve.add_argument("--now", action="store_true", help="run a session now when one is due")

    reject = actions.add_parser("reject", help="reject a pending decision")
    reject.add_argument("name")
    return parser


_UNIVERSE_HELP = "tickers to trade, comma or space separated, e.g. AAPL,MSFT,NVDA"


def _universe(text: str, parser: argparse.ArgumentParser) -> list[str]:
    try:
        return normalize_universe(text.replace(",", " ").split())
    except ValueError as exc:
        parser.error(str(exc))


def _override_rebalance(spec: FundSpec, cadence: Cadence | None) -> FundSpec:
    if cadence is None:
        return spec
    data = spec.model_dump()
    if cadence != "minute":
        data.pop("interval", None)
        data.pop("window", None)
    data["rebalance"] = cadence
    return FundSpec.model_validate(data)


def _fund_dir(name: str, parser: argparse.ArgumentParser) -> Path:
    try:
        validate_fund_name(name)
    except ValueError as exc:
        parser.error(str(exc))
    directory = PAPER_DIR / name
    if not directory.is_dir():
        parser.error(f"no paper fund named {name!r} under {PAPER_DIR} (see `aihf paper list`)")
    return directory


# ---------------------------------------------------------------------------
# backtest
# ---------------------------------------------------------------------------


def _backtest(args, parser: argparse.ArgumentParser, console: Console) -> None:
    universe = _universe(args.universe, parser)
    try:
        spec = load_spec(paths.resolve_user_path(args.mandate))
    except ValueError as exc:
        parser.error(str(exc))
    spec = _override_rebalance(spec, args.rebalance)
    end = args.end or completed_through()
    from hedge_fund.runtime.defaults import backtest_start_date

    start = args.start or backtest_start_date(_date.fromisoformat(end)).isoformat()
    # A backtest blinds the investor agents' prompts (no ticker, industry or
    # calendar dates): the LLM may have been trained on what those companies
    # did over the window, and that memory would otherwise score as skill.
    fund = Fund(spec, blind=True)

    with make_data_client() as raw:
        fd = CachedDataClient(raw)
        with console.status(
            f"[cyan]{spec.name}: backtesting {start} → {end} " f"({spec.rebalance} rebalance vs {spec.benchmark}) " f"over {', '.join(universe)}…",
            spinner="dots",
        ):
            result = backtest_fund(fund, start, end, fd, universe)

    payload = result.model_dump_json(indent=2)
    print(payload)
    saved = save_result(result)
    if args.out:
        try:
            paths.write_text(paths.resolve_user_path(args.out), payload)
        except (OSError, ValueError) as exc:
            parser.error(f"result could not be written ({type(exc).__name__}).")
    m = result.metrics
    console.print(f"[bold]{spec.name}[/] {result.start} → {result.end}  ·  " f"{len(result.dates)} sessions  ·  {m.n_cycles} rebalances  ·  {m.n_orders} orders  ·  " f"{cost_line(m.trading_cost, m.traded_notional)}  ·  " f"return {m.total_return_pct:+.1%} vs {spec.benchmark} {m.benchmark_return_pct:+.1%}  ·  " f"sharpe {m.sharpe_ratio:.2f}  ·  max drawdown {m.max_drawdown_pct:.1%}")
    card = score(result.records)
    console.print(analyst_table(card))
    console.print(strategy_table(card))
    console.print(f"[dim]saved to {saved}[/]")


# ---------------------------------------------------------------------------
# paper
# ---------------------------------------------------------------------------


def _paper(args, parser: argparse.ArgumentParser, console: Console) -> None:
    if args.action == "create":
        universe = _universe(args.universe, parser)
        try:
            validate_fund_name(args.name)
            spec = load_spec(paths.resolve_user_path(args.mandate))
        except ValueError as exc:
            parser.error(str(exc))
        spec = _override_rebalance(spec, args.rebalance)
        if args.approval:
            spec = spec.model_copy(update={"approval_required": True})
        try:
            directory = deploy(args.name, spec, universe, root=PAPER_DIR)
        except FileExistsError as exc:
            parser.error(str(exc))
        cadence = f"{spec.cadence_label}, {spec.window.label}" if spec.is_intraday else spec.cadence_label
        approval_note = "  ·  approval required" if spec.approval_required else ""
        console.print(f"[bold]{args.name}[/] deployed at {directory}  ·  mandate {spec.name}  ·  " f"{', '.join(universe)}  ·  ${spec.capital:,.0f}  ·  broker {spec.broker}  ·  {cadence}{approval_note}")
        console.print(f"[dim]next: `aihf paper tick {args.name}` to run one session, `aihf paper run " f"{args.name}` to leave it running, `aihf paper status {args.name}` any time[/]")
        return

    if args.action == "list":
        for directory in list_deployed(PAPER_DIR):
            print(_status_line(directory))
        return

    directory = _fund_dir(args.name, parser)

    if args.action == "tick":
        deployed = load_deployed(directory)
        with make_data_client() as raw:
            fd = CachedDataClient(raw, live=deployed.spec.is_intraday)
            verb = "running the latest session again" if args.again else "advancing one session"
            with console.status(
                f"[cyan]{deployed.name}: {verb} over {', '.join(deployed.universe)}…",
                spinner="dots",
            ):
                record = redo(directory, fd, build_fund=None) if args.again else tick(directory, fd, session=args.session)
        print(record.model_dump_json(indent=2))
        console.print(_tick_summary(deployed.name, record))
        return

    if args.action == "run":
        deployed = load_deployed(directory)
        spec = deployed.spec
        cadence = f"{spec.cadence_label}, {spec.window.label}" if spec.is_intraday else spec.rebalance
        console.print(f"[bold]{deployed.name}[/] running {cadence}  ·  " f"broker {deployed.broker}  ·  {', '.join(deployed.universe)}  ·  Ctrl-C or `aihf paper stop {deployed.name}` to stop")

        def _event(kind: str, fields: dict) -> None:
            detail = fields.get("reason") or (f"{fields.get('bars_skipped')} bars skipped" if "bars_skipped" in fields else "")
            console.print(f"[yellow]{kind}[/] {fields.get('from') or 'start'} → {fields.get('to')}  {detail}".rstrip())

        with make_data_client() as raw:
            try:
                serve(directory, CachedDataClient(raw, live=spec.is_intraday), on_record=lambda record: console.print(_tick_summary(deployed.name, record)), on_event=_event)
            except RuntimeError as exc:  # already running
                console.print(f"[red]{exc}[/]")
                sys.exit(1)
        console.print(f"[dim]{deployed.name} stopped[/]")
        return

    if args.action == "stop":
        if stop_runner(directory):
            console.print(f"[green]{args.name}[/] asked to stop; it finishes the session in flight first")
        else:
            console.print(f"[dim]{args.name} is not running[/]")
        return

    if args.action == "status":
        print(_status_line(directory))
        ledger = Ledger(directory)
        latest = ledger.latest()
        if latest is not None and latest.decision is not None:
            deployed = load_deployed(directory)
            when = "bar" if deployed.spec.is_intraday else "close"
            if deployed.spec.approval_required:
                approval, _ = ledger.resolve_approval(latest.decision.as_of, latest.hash)
                if approval is not None:
                    state = "approved for execution" if approval["verdict"] == "approve" else "rejected; execution will be skipped"
                    print(f"  pending decision, {state} at the next {when}:")
                else:
                    print(f"  pending decision, awaiting approval before the next {when}:")
            else:
                print(f"  pending decision, to execute at the next {when}:")
            for ticker, weight in sorted(latest.decision.final_weights.items()):
                print(f"    {ticker}: {weight:+.2%}")
        if latest is not None and latest.positions:
            print("  book:")
            for ticker, shares in sorted(latest.positions.items()):
                print(f"    {ticker}: {format_shares(shares, signed=True)} @ {latest.marks[ticker]:,.2f}")
        return

    if args.action == "scorecard":
        records = Ledger(directory).records()
        if not records:
            console.print(f"[dim]{args.name} has no sessions recorded yet[/]")
            return
        card = score(records)
        print(card.model_dump_json(indent=2))
        console.print(analyst_table(card))
        console.print(strategy_table(card))
        return

    if args.action in {"approve", "reject"}:
        deployed = load_deployed(directory)
        ledger = Ledger(directory)
        state = ledger.replay(deployed.spec.capital)
        if state.halted is not None:
            raise FundHalted(f"{args.name} is halted: {state.halted}")
        if not deployed.spec.approval_required:
            parser.error(f"approval gate is not enabled for '{args.name}'")
        if state.pending is None:
            parser.error(f"nothing is awaiting approval for '{args.name}'")
        if state.prev_hash is None:
            parser.error(f"pending decision for '{args.name}' has no source record hash")
        ledger.set_approval(args.action, state.pending.as_of, state.prev_hash, "cli")
        if args.action == "approve":
            console.print(f"[green]{args.name}[/] approved decision from {state.pending.as_of}")
        else:
            console.print(f"[yellow]{args.name}[/] rejected decision from {state.pending.as_of}")
        if args.action == "approve" and args.now:
            try:
                with make_data_client() as raw:
                    fd = CachedDataClient(raw, live=deployed.spec.is_intraday)
                    with console.status(f"[cyan]{deployed.name}: advancing one session…", spinner="dots"):
                        record = tick(directory, fd)
            except NothingDue:
                console.print(f"{args.name}: will execute at the next close")
                return
            print(record.model_dump_json(indent=2))
            console.print(_tick_summary(deployed.name, record))
        return

    ledger = Ledger(directory)
    if args.action == "halt":
        ledger.halt(args.reason)
        console.print(f"[red]{args.name} halted:[/] {args.reason}")
    elif args.action == "resume":
        ledger.resume()
        console.print(f"[green]{args.name} resumed[/]")


def _status_line(directory: Path) -> str:
    try:
        deployed = load_deployed(directory)
    except ValueError as exc:
        return f"{directory.name:<18} unavailable: {exc}"
    ledger = Ledger(directory)
    latest = ledger.latest()
    halted = ledger.halted()
    if latest is None:
        state = f"not started  ·  ${deployed.spec.capital:,.0f}"
    else:
        ret = latest.nav / deployed.spec.capital - 1
        state = f"{len(ledger.sessions())} sessions  ·  last {latest.session}  ·  " f"NAV ${latest.nav:,.2f} ({ret:+.2%})"
    flag = f"  ·  HALTED: {halted}" if halted else ""
    running = "  ·  running" if is_running(directory) else ""
    approval_state = ""
    if deployed.spec.approval_required and latest is not None and latest.decision is not None:
        approval, _ = ledger.resolve_approval(latest.decision.as_of, latest.hash)
        if approval is not None:
            approval_state = f"  ·  {approval['verdict']} recorded"
        else:
            approval_state = "  ·  awaiting approval"
    return f"{deployed.name:<18} {deployed.spec.name}  ·  {' '.join(deployed.universe)}  ·  " f"broker {deployed.broker}  ·  {deployed.spec.cadence_label}{running}  ·  {state}{flag}{approval_state}"


def _tick_summary(name: str, record: SessionRecord) -> str:
    parts = [f"[bold]{name}[/] · session {record.session} · NAV ${record.nav:,.2f}"]
    if record.executed is not None:
        costs = f", costs ${record.executed.trading_cost:,.2f}" if record.executed.trading_cost else ""
        parts.append(f"executed {len(record.executed.orders)} orders from {record.executed.as_of}{costs}")
    if record.decision is not None:
        n_signals = sum(len(sr.signals) for sr in record.decision.strategies)
        when = "bar" if is_intraday(record.session) else "close"
        parts.append(f"decided on {n_signals} signals, {len(record.decision.clamps)} clamps; executes next {when}")
    if record.executed is None and record.decision is None:
        parts.append("marked the book; no rebalance due")
    return "  ·  ".join(parts)


if __name__ == "__main__":
    main()
