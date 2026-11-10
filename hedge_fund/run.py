"""Run the AI hedge fund.

Two modes, one engine. A backtest replays a mandate over history; a paper
fund is that same mandate deployed against a universe and advanced one
completed session at a time, keeping a ledger. Both call `advance`; only
the clock, the broker, and where the state lives differ.

Usage::

    aihf --root /path/to/hedge-fund-data
        No arguments: the interactive app (a Textual TUI). Backtest a
        mandate, deploy and advance a paper fund, or build a new mandate.
        TUI provider dispatch is disabled; use a guarded CLI action or web desk.

    aihf --root /path/to/hedge-fund-data --enable-network backtest mandates/example.yaml --universe AAPL,MSFT
        One bounded backtest. Free data and approved local models by default.
        Paid dispatch needs explicit provider, call/cost caps and deadline.

    aihf --root /path/to/hedge-fund-data paper create alpha --mandate mandates/example.yaml --universe AAPL,MSFT
        Deploy a paper fund: snapshot the mandate, fix the universe, open an
        empty ledger and a book with the mandate's capital.

    aihf --root /path/to/hedge-fund-data paper status alpha --head
        Print the exact head required by a reviewed headless mutation.

    aihf --root /path/to/hedge-fund-data --enable-network paper tick alpha --expected-head none --request-id RUN-001
        Advance the fund by exactly one session and append it to the ledger:
        the oldest unrecorded completed close for a daily fund, the current
        bar at prints taken now for a minute fund. Network authority is
        invocation-bound. Scheduled ticks require free data and local models.

    aihf --root /path/to/hedge-fund-data paper run|stop alpha
        Disabled. The web desk owns finite local-only scheduled runs.

    aihf --root /path/to/hedge-fund-data paper status alpha
    aihf --root /path/to/hedge-fund-data paper list
    aihf --root /path/to/hedge-fund-data paper halt alpha --reason "..." --request-id HALT-001
    aihf --root /path/to/hedge-fund-data paper resume alpha
    aihf --root /path/to/hedge-fund-data paper approve alpha --expected-head SHA256 --request-id APPROVE-001

    aihf --root /path/to/hedge-fund-data paper scorecard alpha
        Grade every analyst (hit rate, slugging, IC) and every strategy
        (P&L between executions) on the fund's ledger. JSON on stdout.

    aihf --root ROOT lifecycle preview --action archive --kind template --identity alpha
    aihf --root ROOT lifecycle archive template alpha --expected-head SHA256 --request-id ID
    aihf --root ROOT lifecycle restore|recover ARCHIVE_ID --expected-head SHA256 --request-id ID
    aihf --root ROOT lifecycle list|inspect [ARCHIVE_ID]
        Offline, separately scoped reversible archive and explicit journal recovery.
        Preview the exact identity and references first; mutation requires its head.

A mandate is the desk — strategies, staff, risk, capital, cadence — and
never names tickers; the universe is fixed when a fund is deployed (paper)
or given per study (backtest).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import sys
from contextlib import contextmanager
from datetime import date as _date
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Iterator
from uuid import uuid4

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


class PaperWriterDenied(RuntimeError):
    """Enrolled-root paper writer could not acquire verified admission."""


def main(argv: list[str] | None = None) -> None:
    # Persona/LLM text is arbitrary unicode; a Windows console defaults to
    # cp1252 and would crash on it. Force UTF-8 (with replacement) on both
    # streams before anything prints.
    for stream in (sys.stdout, sys.stderr):
        if stream is not None and hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    parser = _parser()
    args = parser.parse_args(argv)
    if args.command == "saxo":
        _saxo_inspect(args, parser)
        return
    if args.root is None:
        parser.error("--root is required for this command")
    try:
        context = RootContext.open(args.root)
    except RootPathError as exc:
        parser.error(str(exc))

    try:
        with paths.bound_root(context):
            if args.command == "lifecycle":
                if args.load_dotenv or args.model or args.enable_network:
                    parser.error("offline lifecycle does not accept dotenv, model, or network settings")
                _lifecycle(args, parser, context)
                return
            if args.command == "handover":
                if args.load_dotenv or args.model or args.enable_network:
                    parser.error("offline handover does not accept dotenv or model settings")
                _handover(args, parser, context)
                return
            try:
                paths.load_root_dotenv(context, enabled=args.load_dotenv)
            except (RootPathError, UnicodeError, ValueError) as exc:
                parser.error(str(exc))
            _load_runtime()
            from hedge_fund.runtime.policy import AuthorizationDenied

            if not (args.command == "paper" and args.action == "halt"):
                try:
                    ensure_mandates_dir()
                except RootPathError as exc:
                    parser.error(str(exc))

            if args.command is None:
                if args.enable_network:
                    parser.error("the TUI has no operation-bound provider consent; use the web desk or guarded CLI actions")
                if args.model:
                    os.environ["HEDGE_FUND_LLM_MODEL"] = args.model
                from hedge_fund.tui.app import HedgeFundApp

                HedgeFundApp().run()
                return

            console = Console(stderr=True)
            try:
                if args.command == "backtest":
                    _backtest(args, parser, console, context)
                else:
                    _paper(args, parser, console, context)
            except (FundHalted, NothingDue, LedgerError) as exc:
                console.print(f"[red]{exc}[/]")
                sys.exit(1)
            except PaperWriterDenied as exc:
                console.print(f"[red]{exc}[/]")
                sys.exit(1)
            except AuthorizationDenied:
                console.print("[red]Provider operation denied by its captured authorization.[/]")
                sys.exit(1)
    finally:
        context.close()


def _saxo_inspect(args, parser: argparse.ArgumentParser) -> None:
    if not args.enable_network and not args.saxo_enable_network:
        parser.error("Saxo SIM inspection requires explicit --enable-network consent")
    from hedge_fund.brokers.factory import build_saxo_demo_client
    from hedge_fund.brokers.saxo import SaxoAuthError, SaxoReconcileError

    try:
        client = build_saxo_demo_client()
        client.check_connection()
        accounts = client.inspect_accounts(args.account_key)
    except (SaxoAuthError, SaxoReconcileError, ValueError) as exc:
        parser.error(str(exc))
    except Exception:
        parser.error("Saxo SIM inspection failed; no order was submitted")

    summaries = []
    for account in accounts:
        summaries.append(
            {
                "account_key": account.account_key,
                "currency": account.currency,
                "cash_balance": account.cash_balance,
                "position_count": len(account.positions),
                "positions": [{"uic": position.uic, "amount": position.amount} for position in account.positions],
            }
        )
    print(
        json.dumps(
            {
                "environment": "SIM",
                "status": "connected",
                "accounts": summaries,
                "selected_account_key": args.account_key,
                "selection_required": args.account_key is None,
            }
        )
    )


def _load_runtime() -> None:
    global backtest_fund, save_result, format_shares, CachedDataClient
    global make_data_client, is_intraday, completed_through, Cadence, Fund
    global FundSpec, load_spec, normalize_universe, deploy, is_running
    global Ledger, LedgerError, list_deployed, load_deployed, NothingDue
    global redo, tick, validate_fund_name
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


def _expected_head_argument(value: str) -> str | None:
    if value == "none":
        return None
    if len(value) == 64 and all(character in "0123456789abcdef" for character in value):
        return value
    raise argparse.ArgumentTypeError("expected head must be a lowercase SHA-256 hash or 'none'")


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
        default=None,
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
    parser.add_argument(
        "--enable-network",
        action="store_true",
        help="enable bounded provider requests for this invocation; no paid call is implied",
    )
    commands = parser.add_subparsers(dest="command")

    saxo = commands.add_parser("saxo", help="read-only Saxo SIM inspection")
    saxo_actions = saxo.add_subparsers(dest="saxo_action", required=True)
    inspect = saxo_actions.add_parser("inspect", help="check the demo-token connection and inspect accounts")
    inspect.add_argument("--account-key", help="inspect and explicitly verify one eligible SIM account")
    inspect.add_argument(
        "--enable-network",
        dest="saxo_enable_network",
        action="store_true",
        help="authorize this bounded read-only Saxo SIM request",
    )

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
    backtest.add_argument(
        "--authorize-paid-provider",
        metavar="PROVIDER",
        help="explicitly authorize one paid provider by its captured identity",
    )
    backtest.add_argument(
        "--confirm-fd-self-service-pricing",
        action="store_true",
        help="confirm public self-service pricing; custom Financial Datasets Enterprise pricing is unsupported",
    )
    backtest.add_argument("--paid-max-calls", type=int, help="maximum paid transport calls")
    backtest.add_argument("--paid-max-cost-usd", help="total worst-case reservation cap, at most 100")
    backtest.add_argument("--paid-max-attempt-cost-usd", help="worst-case reservation per attempt, at most 10")
    backtest.add_argument("--deadline-minutes", type=int, default=60, help="one-shot authorization lifetime, 1–1440 minutes")

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
    advance.add_argument("--expected-head", type=_expected_head_argument, required=True, help="reviewed ledger head from `paper status --head`; use 'none' for an empty ledger")
    advance.add_argument("--request-id", required=True, help="stable request identity reused only for an exact retry")
    advance.add_argument("--deadline-minutes", type=int, default=60, help="one-shot authorization lifetime, 1–1440 minutes")
    advance.add_argument("--authorize-paid-provider", metavar="PROVIDER")
    advance.add_argument(
        "--confirm-fd-self-service-pricing",
        action="store_true",
        help="confirm public self-service pricing; custom Financial Datasets Enterprise pricing is unsupported",
    )
    advance.add_argument("--paid-max-calls", type=int)
    advance.add_argument("--paid-max-cost-usd")
    advance.add_argument("--paid-max-attempt-cost-usd")

    runner = actions.add_parser("run", help="stay up and advance the fund whenever a session is due")
    runner.add_argument("name")

    stopper = actions.add_parser("stop", help="stop a fund's runner after the session in flight")
    stopper.add_argument("name")

    status = actions.add_parser("status", help="NAV, last session, pending decision, halt state")
    status.add_argument("name")
    status.add_argument("--head", action="store_true", help="print current ledger head, or 'none' for an empty ledger")

    actions.add_parser("list", help="every deployed paper fund")

    scorecard = actions.add_parser("scorecard", help="grade every analyst and strategy on the ledger")
    scorecard.add_argument("name")

    halt = actions.add_parser("halt", help="set the kill switch: ticks refuse to trade")
    halt.add_argument("name")
    halt.add_argument("--reason", required=True)
    halt.add_argument("--request-id", required=True, help="stable request identity reused only for an exact retry")

    resume = actions.add_parser("resume", help="resume only after verified reconciliation")
    resume.add_argument("name")

    reconcile_tick = actions.add_parser("reconcile-tick-request", help="review or resolve an orphaned paper tick intent")
    reconcile_tick.add_argument("name")
    reconcile_tick.add_argument("--intent-request-id")
    reconcile_tick.add_argument("--request-id")
    reconcile_tick.add_argument("--intent-digest")
    reconcile_tick.add_argument("--preview-digest")
    reconcile_tick.add_argument("--confirm", action="store_true")

    approve = actions.add_parser("approve", help="approve a pending decision")
    approve.add_argument("name")
    approve.add_argument("--now", action="store_true", help="run a session now when one is due")
    approve.add_argument("--expected-head", type=_expected_head_argument, required=True, help="reviewed source record hash for the pending decision")
    approve.add_argument("--request-id", required=True, help="stable verdict request identity reused only for an exact retry")
    approve.add_argument("--tick-request-id", help="separate stable request identity required with --now")
    approve.add_argument("--deadline-minutes", type=int, default=60, help="one-shot authorization lifetime, 1–1440 minutes")
    approve.add_argument("--authorize-paid-provider", metavar="PROVIDER")
    approve.add_argument(
        "--confirm-fd-self-service-pricing",
        action="store_true",
        help="confirm public self-service pricing; custom Financial Datasets Enterprise pricing is unsupported",
    )
    approve.add_argument("--paid-max-calls", type=int)
    approve.add_argument("--paid-max-cost-usd")
    approve.add_argument("--paid-max-attempt-cost-usd")

    reject = actions.add_parser("reject", help="reject a pending decision")
    reject.add_argument("name")
    reject.add_argument("--expected-head", type=_expected_head_argument, required=True, help="reviewed source record hash for the pending decision")
    reject.add_argument("--request-id", required=True, help="stable verdict request identity reused only for an exact retry")

    handover = commands.add_parser(
        "handover",
        help="inspect or explicitly enroll this root offline",
    )
    handover_actions = handover.add_subparsers(
        dest="handover_action",
        required=True,
    )
    handover_actions.add_parser(
        "inspect",
        help="show root identity, paper head inventory and any required trust acknowledgement",
    )
    handover_actions.add_parser(
        "enroll-fresh",
        help="enroll only a genuinely empty root",
    )
    handover_actions.add_parser(
        "inspect-source",
        help="read-only: show the relocation content digest of this legacy root without writing to it",
    )
    relocation = handover_actions.add_parser(
        "relocate-from",
        help="copy a quiescent legacy root into this empty target; target stays read-only until trusted",
    )
    relocation.add_argument("source", help="absolute path of the legacy root to copy (never written)")
    relocation.add_argument(
        "--content-digest",
        required=True,
        help="exact content_digest printed by `aihf --root SOURCE handover inspect-source`",
    )
    migration = handover_actions.add_parser(
        "migrate-existing",
        help="record an existing root; migration stays read-only until separately trusted",
    )
    migration.add_argument("--inventory-digest", required=True)
    migration.add_argument(
        "--operator-attestation",
        required=True,
        help="exact statement printed by `aihf --root ROOT handover inspect`",
    )
    trust = handover_actions.add_parser(
        "trust-single-writer",
        help="deliberately enable operator-trusted single-writer mode for this root",
    )
    trust.add_argument("--inventory-digest", required=True, help="exact current digest printed by handover inspect")
    trust.add_argument(
        "--operator-acknowledgement",
        required=True,
        help="exact root-specific responsibility statement printed by handover inspect",
    )
    handover_actions.add_parser(
        "revoke-single-writer",
        help="revoke protocol write authority after participating writers are quiescent",
    )
    lifecycle = commands.add_parser("lifecycle", help="review and reversibly archive exact objects offline")
    lifecycle_actions = lifecycle.add_subparsers(dest="lifecycle_action", required=True)
    lifecycle_actions.add_parser("list", help="list archive journal identities")
    inspection = lifecycle_actions.add_parser("inspect", help="inspect an exact archive journal")
    inspection.add_argument("archive_id")
    preview = lifecycle_actions.add_parser("preview", help="review an exact lifecycle transition")
    preview.add_argument("--action", choices=("archive", "restore", "recover"), required=True)
    preview.add_argument("--kind", choices=("template", "deployment", "research"))
    preview.add_argument("--identity")
    preview.add_argument("--archive-id")
    archival = lifecycle_actions.add_parser("archive", help="archive one reviewed object; never permanently delete")
    archival.add_argument("kind", choices=("template", "deployment", "research"))
    archival.add_argument("identity")
    for action, command in (
        ("archive", archival),
        ("restore", lifecycle_actions.add_parser("restore", help="restore one reviewed archive without starting work")),
        ("recover", lifecycle_actions.add_parser("recover", help="explicitly reconcile a reviewed interrupted archive journal")),
    ):
        if action != "archive":
            command.add_argument("archive_id")
        command.add_argument("--expected-head", required=True, help="exact expected_head from lifecycle preview")
        command.add_argument("--request-id", required=True, help="durable invocation identity")
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
        parser.error(f"no paper fund named {name!r} under {PAPER_DIR} (see `aihf --root <root> paper list`)")
    return directory


def _lifecycle(args, parser: argparse.ArgumentParser, root: RootContext) -> None:
    from hedge_fund.runtime.admission import AdmissionError
    from hedge_fund.runtime.operations import OperationError
    from hedge_fund.web.schemas import LifecycleAcceptRequest, LifecyclePreviewRequest
    from hedge_fund.web.services import DeskService, ServiceError

    action = args.action if args.lifecycle_action == "preview" else args.lifecycle_action
    service = DeskService(root.path, root_context=root, allow_writes=action not in {"list", "inspect"})
    session = f"headless-lifecycle-{hashlib.sha256(str(root.path).encode('utf-8')).hexdigest()}"
    try:
        if action == "list":
            result = service.list_lifecycle_archives()
        elif action == "inspect":
            result = service.get_lifecycle_archive(args.archive_id)
        else:
            request = LifecyclePreviewRequest(
                action=action,
                kind=getattr(args, "kind", None),
                identity=getattr(args, "identity", None),
                archive_id=getattr(args, "archive_id", None),
            )
            if args.lifecycle_action != "preview":
                # The root-owned headless caller may observe an existing result, but never
                # starts a second transition for the same invocation identity.
                if service._operation_store is None:
                    raise ServiceError(409, "Durable operation storage is unavailable.")
                existing = service._operation_store.get_by_request(args.request_id)
                if existing is not None:
                    stored = existing.public_view()["payload"]
                    matching = existing.action == f"lifecycle-{action}" and stored.get("action") == action and service._lifecycle_head(stored) == args.expected_head and ((action == "archive" and stored.get("kind") == request.kind and stored.get("identity") == request.identity) or (action != "archive" and stored.get("archive_id") == request.archive_id))
                    if not matching:
                        raise ServiceError(409, "Lifecycle invocation conflicts with durable state.")
                    print(json.dumps(service.get_operation(existing.operation_id), sort_keys=True))
                    return
            preview = service.create_lifecycle_preview(
                request,
                operator_session=session,
                offline_recovery=action == "recover",
            )
            if args.lifecycle_action == "preview":
                result = preview
            else:
                if preview["expected_head"] != args.expected_head:
                    raise ServiceError(409, "Lifecycle head or references changed; preview again.")
                acceptance = LifecycleAcceptRequest(
                    **request.model_dump(),
                    request_id=args.request_id,
                    preview_id=preview["preview_id"],
                    preview_digest=preview["preview_digest"],
                    confirmation_token=preview["confirmation_token"],
                    expected_head=args.expected_head,
                )
                result = service.accept_lifecycle(
                    acceptance,
                    operator_session=session,
                    offline_recovery=action == "recover",
                )
        print(json.dumps(result, sort_keys=True))
    except (ServiceError, AdmissionError, OperationError, RootPathError, ValueError) as exc:
        refusal = exc.refusal if isinstance(exc, ServiceError) else None
        detail = json.dumps(refusal, sort_keys=True) if refusal is not None else str(exc)
        parser.error(f"offline lifecycle denied ({type(exc).__name__}): {detail}")
    finally:
        service.close()


def _handover(args, parser: argparse.ArgumentParser, root: RootContext) -> None:
    from hedge_fund.runtime.admission import RootMigrationLease
    from hedge_fund.runtime.handover import (
        build_head_inventory,
        enroll_fresh,
        enrollment_status,
        HANDOVER_PATH,
        HandoverError,
        inspect_relocation_source,
        inventory_digest,
        migrate_existing,
        OPERATOR_ATTESTATION,
        prepare_single_writer_acknowledgement,
        relocate_existing,
        revoke_single_writer,
        SINGLE_WRITER_RESPONSIBILITY_WARNING,
        trust_single_writer,
        write_authority,
    )

    try:
        if args.handover_action == "inspect-source":
            print(json.dumps(inspect_relocation_source(root), sort_keys=True, indent=2))
            return
        if args.handover_action == "inspect":
            status = enrollment_status(root, verify_inventory=True)
            orphaned_admission = status["state"] == "invalid" and status["reason"] == "admission-state-without-handover"
            inspectable = status["state"] in {"unenrolled", "enrolled"} or orphaned_admission
            if not inspectable:
                raise HandoverError("root enrollment or ledger inventory is unavailable")
            acknowledgement = None
            acknowledgement_expires_at = None
            runtime_scope = None
            if status["state"] == "enrolled":
                review = prepare_single_writer_acknowledgement(root)
                heads = review["heads"]
                authority = {
                    "authority": review["write_authority"],
                    "reason": review["reason"],
                }
                acknowledgement = review["operator_acknowledgement"]
                acknowledgement_expires_at = review["review_expires_at"]
                runtime_scope = review["runtime_scope"]
            elif any(root.path.iterdir()):
                if not root.verify_private_storage():
                    root.prepare_private_storage()
                with RootMigrationLease.acquire(root, timeout=0):
                    heads = build_head_inventory(root)
                    try:
                        root.file_info(HANDOVER_PATH)
                    except FileNotFoundError:
                        if status["state"] == "enrolled":
                            raise HandoverError("root enrollment changed during inspection")
                    else:
                        status = enrollment_status(root, verify_inventory=True)
                        if status["state"] != "enrolled":
                            raise HandoverError("root enrollment or ledger inventory changed")
            else:
                heads = build_head_inventory(root)
            if status["state"] != "enrolled":
                authority = {"authority": "unavailable", "reason": status["reason"]}
            print(
                json.dumps(
                    {
                        "state": status["state"],
                        "write_authority": authority,
                        "heads": heads,
                        "inventory_digest": inventory_digest(heads),
                        "operator_attestation": OPERATOR_ATTESTATION,
                        "operator_acknowledgement": acknowledgement,
                        "operator_acknowledgement_expires_at": acknowledgement_expires_at,
                        "runtime_scope": runtime_scope,
                        "operator_responsibility": SINGLE_WRITER_RESPONSIBILITY_WARNING,
                    },
                    sort_keys=True,
                    indent=2,
                )
            )
            return

        if args.handover_action == "enroll-fresh":
            record = enroll_fresh(root)
        elif args.handover_action == "relocate-from":
            with RootContext.open(args.source) as source:
                record = relocate_existing(root, source=source, expected_content_digest=args.content_digest)
        elif args.handover_action == "trust-single-writer":
            authority = trust_single_writer(
                root,
                expected_inventory_digest=args.inventory_digest,
                operator_acknowledgement=args.operator_acknowledgement,
            )
            print(json.dumps({"state": "trusted", "write_authority": authority}, sort_keys=True))
            return
        elif args.handover_action == "revoke-single-writer":
            authority = revoke_single_writer(root)
            print(json.dumps({"state": "revoked", "write_authority": authority}, sort_keys=True))
            return
        else:
            record = migrate_existing(
                root,
                expected_inventory_digest=args.inventory_digest,
                operator_attestation=args.operator_attestation,
            )
    except Exception as exc:
        parser.error(f"offline handover failed ({type(exc).__name__}): {exc}")
    print(
        json.dumps(
            {
                "state": "enrolled",
                "mode": record["mode"],
                "inventory_digest": record["inventory_digest"],
                "write_authority": write_authority(root)["authority"],
            },
            sort_keys=True,
        )
    )


@contextmanager
def _paper_writer_admission(*, verify_inventory: bool = True) -> Iterator[tuple[RootContext, object] | None]:
    from hedge_fund.runtime.admission import (
        AdmissionCoordinator,
        AdmissionError,
        RootOwnerLease,
    )
    from hedge_fund.runtime.handover import (
        enrollment_status,
        HandoverError,
        has_write_authority,
        verify_root_inventory,
        write_authority,
    )

    root = paths.root_context()
    status = enrollment_status(root, verify_inventory=verify_inventory)
    if status["state"] == "unenrolled":
        raise PaperWriterDenied("Paper writes are blocked until explicit offline enrollment.")
    if status["state"] != "enrolled":
        raise PaperWriterDenied("Paper writes are blocked by root enrollment or ledger drift.")
    authority = write_authority(root)
    if not has_write_authority(authority):
        reason = authority["reason"]
        if reason in {
            "operator-single-writer-acknowledgement-required",
            "operator-single-writer-acknowledgement-invalid",
            "operator-single-writer-runtime-scope-changed",
            "attested-migration-read-only",
        }:
            remedy = "run offline handover inspect and use its fresh exact inventory and acknowledgement for this runtime"
        elif reason == "operator-single-writer-runtime-scope-unavailable":
            remedy = "runtime scope cannot be verified; trusted mode stays disabled"
        else:
            remedy = "resolve the reported root or participant issue before retrying"
        raise PaperWriterDenied(f"Paper writes are blocked: root write authority is {authority['authority']} ({authority['reason']}); {remedy}.")

    owner = None
    try:
        owner = RootOwnerLease.acquire(root, timeout=0)
        admission = AdmissionCoordinator(root, owner_lease=owner)
        if verify_inventory:
            verify_root_inventory(root)
    except (AdmissionError, HandoverError, OSError, RootPathError, ValueError) as exc:
        if owner is not None:
            owner.close()
        raise PaperWriterDenied("Paper writes are blocked because root admission is unavailable.") from exc
    try:
        yield root, admission
    finally:
        owner.close()


@contextmanager
def _paper_lane(participant, name: str, lane: str) -> Iterator[None]:
    if participant is None:
        yield
        return
    if lane not in {"deployment_lock", "manual_session", "control_lane", "halt_lane"}:
        raise ValueError("paper admission lane is invalid")
    from hedge_fund.runtime.admission import AdmissionError
    from hedge_fund.runtime.handover import HandoverError, LedgerHeadPublicationError

    _root, admission = participant
    try:
        with getattr(admission, lane)(name, timeout=0):
            yield
    except LedgerHeadPublicationError as exc:
        raise PaperWriterDenied("Paper mutation was recorded; root head inventory requires offline review.") from exc
    except HandoverError as exc:
        raise PaperWriterDenied("Paper writes are blocked by root enrollment or ledger drift.") from exc
    except AdmissionError as exc:
        raise PaperWriterDenied(f"Paper {lane.replace('_', ' ')} is busy or unavailable.") from exc


def _verify_enrolled_inventory(participant) -> None:
    if participant is None:
        return
    from hedge_fund.runtime.handover import HandoverError, verify_root_inventory

    root, _admission = participant
    try:
        verify_root_inventory(root)
    except HandoverError as exc:
        raise PaperWriterDenied("Paper writes are blocked by ledger inventory drift.") from exc


def _verify_enrolled_head(participant, name: str) -> None:
    if participant is None:
        return
    from hedge_fund.runtime.handover import HandoverError, verify_ledger_head

    root, _admission = participant
    try:
        verify_ledger_head(root, name)
    except HandoverError as exc:
        raise PaperWriterDenied("Paper writes are blocked by ledger head drift.") from exc


def _cli_settings(root: RootContext, args, parser: argparse.ArgumentParser):
    from hedge_fund.runtime.admission import AdmissionCoordinator, AdmissionError
    from hedge_fund.runtime.configuration import ConfigurationError, resolve_settings

    admission = AdmissionCoordinator(root)
    launch = {"model": args.model} if args.model else None
    try:
        settings = resolve_settings(
            root,
            admission=admission,
            launch=launch,
        )
    except (AdmissionError, ConfigurationError, OSError, ValueError):
        parser.error("captured runtime settings are unavailable")
    return settings, admission


def _authorize_cli_operation(
    root: RootContext,
    args,
    parser: argparse.ArgumentParser,
    *,
    settings,
    admission,
    spec,
    universe: list[str],
    operation: str,
    operation_inputs: dict[str, object],
    expected_head: str | None,
    model_call_bound: int,
    llm_call_bound: int,
    spec_path: Path | None = None,
    directory: Path | None = None,
    participant=None,
    resolver=None,
):
    from hedge_fund.llm.client import validate_llm_transport
    from hedge_fund.pipeline.session import code_version, mandate_hash
    from hedge_fund.pipeline.session import SessionRecord as CapturedSessionRecord
    from hedge_fund.runtime.capture import freeze_capture
    from hedge_fund.runtime.configuration import ConfigurationError, resolve_settings
    from hedge_fund.runtime.costs import (
        cost_model_description,
        cost_model_identity,
        COST_MODEL_VERSION,
        has_verified_cost_model,
        minimum_attempt_cost,
    )
    from hedge_fund.runtime.credentials import CredentialStore, CredentialStoreError
    from hedge_fund.runtime.dispatch import make_one_shot_dispatch
    from hedge_fund.runtime.handover import (
        HandoverError,
        verify_ledger_head,
        verify_root_inventory,
    )
    from hedge_fund.runtime.policy import (
        AuthorizationDenied,
        classify_provider,
        KEN_FRENCH_BREAKPOINTS_TARGET,
        ProviderClass,
        ProviderTarget,
    )

    if not args.enable_network:
        parser.error("provider access requires explicit --enable-network")
    if not isinstance(operation_inputs, dict) or any(not isinstance(key, str) or not key for key in operation_inputs):
        parser.error("operation inputs are invalid")
    try:
        operation_inputs_json = json.dumps(
            operation_inputs,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError):
        parser.error("operation inputs are invalid")
    if len(operation_inputs_json.encode("utf-8")) > 4096:
        parser.error("operation inputs exceed their bound")
    redo_source = None
    if operation == "paper-redo":
        if directory is None:
            parser.error("paper redo source is unavailable")
        try:
            redo_source = Ledger(directory).latest()
        except (LedgerError, OSError, ValueError):
            parser.error("paper redo source is unavailable")
        if redo_source is None or redo_source.hash != expected_head or redo_source.hash != redo_source.compute_hash() or operation_inputs.get("redo_source_session") != redo_source.session or operation_inputs.get("redo_previous_head") != redo_source.prev_hash:
            parser.error("paper redo head changed before authorization")
    if type(model_call_bound) is not int or not 1 <= model_call_bound <= 1000 or type(llm_call_bound) is not int or not 0 <= llm_call_bound <= model_call_bound:
        parser.error("model-call estimate is invalid")
    deadline_minutes = getattr(args, "deadline_minutes", 60)
    if type(deadline_minutes) is not int or not 1 <= deadline_minutes <= 1440:
        parser.error("one-shot deadline must be between 1 and 1440 minutes")
    if spec.broker != "paper":
        parser.error("guarded provider actions currently require a local-paper mandate")

    data_target = ProviderTarget(kind="data", provider=settings.data_provider)
    breakpoints_target = KEN_FRENCH_BREAKPOINTS_TARGET
    llm_target = ProviderTarget(
        kind="llm",
        provider=settings.llm_provider,
        model=settings.model,
        endpoint=settings.endpoint,
    )
    targets = [data_target, breakpoints_target]
    try:
        data_class = classify_provider(data_target)
        llm_class = None
        if llm_call_bound:
            validate_llm_transport(llm_target)
            llm_class = classify_provider(
                llm_target,
                approved_local_models={settings.model},
            )
            targets.append(llm_target)
        if classify_provider(breakpoints_target) is not ProviderClass.FREE_DATA:
            parser.error("breakpoints provider is not approved free data")
    except AuthorizationDenied:
        parser.error("captured provider has no guarded production transport")
    paid_targets = [
        (target, provider_class)
        for target, provider_class in (
            (data_target, data_class),
            (llm_target, llm_class),
        )
        if provider_class is ProviderClass.PAID_CLOUD
    ]
    if len(paid_targets) > 1:
        parser.error("only one paid provider may be authorized per operation")
    paid_cost_model = None
    if paid_targets:
        paid_target = paid_targets[0][0]
        if not has_verified_cost_model(paid_target):
            parser.error("paid provider has no verified upper-bound cost model")
        paid_cost_model = cost_model_identity(paid_target)

    fd_pricing_confirmation = getattr(args, "confirm_fd_self_service_pricing", False)
    if type(fd_pricing_confirmation) is not bool:
        parser.error("Financial Datasets pricing confirmation is invalid")
    authorized_provider = getattr(args, "authorize_paid_provider", None)
    paid_max_calls = getattr(args, "paid_max_calls", None)
    paid_total_text = getattr(args, "paid_max_cost_usd", None)
    paid_attempt_text = getattr(args, "paid_max_attempt_cost_usd", None)
    paid_budget = None
    if operation in {"backtest", "paper-tick", "paper-redo", "stock-check"} and paid_targets:
        paid_provider = paid_targets[0][0].provider
        if not isinstance(authorized_provider, str) or authorized_provider.casefold() != paid_provider:
            parser.error(f"paid dispatch requires --authorize-paid-provider {paid_provider}")
        if paid_provider == "fd" and not fd_pricing_confirmation:
            parser.error("paid FD dispatch requires --confirm-fd-self-service-pricing")
        if paid_provider != "fd" and fd_pricing_confirmation:
            parser.error("Financial Datasets pricing confirmation does not match the paid provider")
        if type(paid_max_calls) is not int or not 1 <= paid_max_calls <= 10000:
            parser.error("paid call bound must be between 1 and 10000")
        try:
            paid_total = Decimal(paid_total_text)
            paid_attempt = Decimal(paid_attempt_text)
        except (InvalidOperation, TypeError):
            parser.error("paid total and per-attempt cost bounds are required")
        if not paid_total.is_finite() or not paid_attempt.is_finite() or paid_total <= 0 or paid_total > Decimal("100") or paid_attempt <= 0 or paid_attempt > Decimal("10") or paid_attempt > paid_total:
            parser.error("paid cost bounds exceed the allowed finite range")
        paid_budget = (paid_max_calls, paid_total, paid_attempt)
        minimum_cost = minimum_attempt_cost(paid_targets[0][0])
        if minimum_cost is None or paid_attempt < minimum_cost:
            parser.error("per-attempt cost bound is below the provider's verified maximum")
    elif paid_targets:
        parser.error("paid provider is unsupported for this headless operation")
    elif fd_pricing_confirmation or any(value is not None for value in (authorized_provider, paid_max_calls, paid_total_text, paid_attempt_text)):
        parser.error("paid authorization does not match the captured providers")

    transport_model_call_bound = model_call_bound
    transport_llm_call_bound = llm_call_bound
    if llm_class is ProviderClass.LOCAL:
        transport_model_call_bound += llm_call_bound
        transport_llm_call_bound *= 2
    data_calls = min(10000, max(100, model_call_bound * 10))
    provider_call_bounds = {
        data_target.identity: data_calls,
        breakpoints_target.identity: 1,
    }
    if llm_call_bound:
        provider_call_bounds[llm_target.identity] = transport_llm_call_bound
    if paid_targets:
        paid_target = paid_targets[0][0]
        call_limit = provider_call_bounds[paid_target.identity]
        if paid_budget[0] > call_limit:
            parser.error("paid call bound exceeds the operation estimate")
        provider_call_bounds[paid_target.identity] = paid_budget[0]

    credential_versions = {}
    data_key = None
    llm_key = None
    if paid_targets:
        target = paid_targets[0][0]
        provider_id = target.provider.casefold()
        try:
            credentials = CredentialStore(root, admission)
            version, configured = credentials.version(provider_id)
            if not configured or version <= 0:
                parser.error("paid provider credential is not saved under this root")
            credential = credentials.read_version(provider_id, version)
        except CredentialStoreError:
            parser.error("paid provider credential is unavailable")
        if not isinstance(credential, str) or not credential:
            parser.error("paid provider credential is unavailable")
        credential_versions[provider_id] = version
        if target.kind == "data":
            data_key = credential
        else:
            llm_key = credential

    try:
        capture = freeze_capture(
            root=root,
            subject_id=spec.name,
            mandate_digest=mandate_hash(spec),
            universe=tuple(universe),
            broker=spec.broker,
            settings=settings,
            credential_versions=credential_versions,
            code_version=code_version(),
            mandate_snapshot=spec.model_dump(mode="json"),
        )
    except (ConfigurationError, OSError, ValueError):
        parser.error("operation capture could not be frozen")

    expires_at = datetime.now(timezone.utc) + timedelta(minutes=deadline_minutes)
    operation_id = uuid4().hex
    digest_payload = {
        "operation": operation,
        "operation_id": operation_id,
        "operation_inputs": operation_inputs,
        "estimated_model_calls": model_call_bound,
        "estimated_llm_calls": llm_call_bound,
        "transport_model_call_bound": transport_model_call_bound,
        "transport_llm_call_bound": transport_llm_call_bound,
        "fd_self_service_pricing_confirmed": fd_pricing_confirmation,
        "cost_model_version": COST_MODEL_VERSION,
        "paid_cost_model": paid_cost_model,
        "capture_digest": capture.digest,
        "expected_head": expected_head,
        "provider_ids": sorted(target.identity for target in targets),
        "transport_call_bounds": {identity: calls for identity, calls in sorted(provider_call_bounds.items())},
        "universe": universe,
        "deadline": expires_at.isoformat(),
        "paid_bounds": None
        if paid_budget is None
        else {
            "calls": paid_budget[0],
            "total": str(paid_budget[1]),
            "attempt": str(paid_budget[2]),
        },
    }
    operation_digest = hashlib.sha256(
        json.dumps(
            digest_payload,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()

    active_head = expected_head
    redo_advanced = False

    def boundary_check() -> None:
        try:
            root.revalidate()
            current_settings = resolve_settings(
                root,
                admission=admission,
                launch={"model": args.model} if args.model else None,
            )
        except (ConfigurationError, OSError, RootPathError, ValueError):
            raise AuthorizationDenied("captured runtime settings are unavailable") from None
        if current_settings.version != capture.settings_version or current_settings.to_mapping() != settings.to_mapping():
            raise AuthorizationDenied("captured runtime settings changed")
        if credential_versions:
            credentials = CredentialStore(root, admission)
            for provider_id, version in credential_versions.items():
                try:
                    current_version, configured = credentials.version(provider_id)
                except CredentialStoreError:
                    raise AuthorizationDenied("captured provider credential is unavailable") from None
                if current_version != version or not configured:
                    raise AuthorizationDenied("captured provider credential changed")
        if operation == "stock-check":
            try:
                verify_root_inventory(root)
            except HandoverError:
                raise AuthorizationDenied("paper ledger inventory is unavailable") from None
        if spec_path is not None:
            try:
                current_spec = _override_rebalance(
                    load_spec(spec_path),
                    getattr(args, "rebalance", None),
                )
            except (OSError, ValueError):
                raise AuthorizationDenied("captured mandate is unavailable") from None
            if mandate_hash(current_spec) != capture.mandate_digest:
                raise AuthorizationDenied("captured mandate changed")
        if directory is not None:
            if participant is not None:
                try:
                    verify_ledger_head(root, directory.name)
                except HandoverError:
                    raise AuthorizationDenied("paper ledger head is unavailable") from None
            try:
                current_deployed = load_deployed(directory)
                current_state = Ledger(directory).replay(
                    current_deployed.spec.capital,
                    full=True,
                )
            except (LedgerError, OSError, ValueError):
                raise AuthorizationDenied("paper ledger is unavailable") from None
            current_head = current_state.prev_hash
            if current_head != active_head or current_state.halted is not None or mandate_hash(current_deployed.spec) != capture.mandate_digest or tuple(current_deployed.universe) != capture.universe:
                raise AuthorizationDenied("paper operation fence changed")

    def advance_redo_fence(superseded: CapturedSessionRecord) -> None:
        nonlocal active_head, redo_advanced
        if operation != "paper-redo" or directory is None or redo_source is None or redo_advanced or not isinstance(superseded, CapturedSessionRecord) or superseded.hash != redo_source.hash or superseded.hash != superseded.compute_hash() or superseded.session != redo_source.session or superseded.prev_hash != redo_source.prev_hash:
            raise AuthorizationDenied("paper redo transition does not match its capture")
        try:
            if participant is not None:
                verify_ledger_head(root, directory.name)
            current_deployed = load_deployed(directory)
            current_state = Ledger(directory).replay(current_deployed.spec.capital, full=True)
        except (HandoverError, LedgerError, OSError, ValueError):
            raise AuthorizationDenied("paper redo transition is unavailable") from None
        if current_state.prev_hash != redo_source.prev_hash or current_state.halted is not None or mandate_hash(current_deployed.spec) != capture.mandate_digest or tuple(current_deployed.universe) != capture.universe:
            raise AuthorizationDenied("paper redo transition does not match its capture")
        active_head = redo_source.prev_hash
        redo_advanced = True

    total_paid_cost = paid_budget[1] if paid_budget is not None else Decimal("0")
    attempt_cost = paid_budget[2] if paid_budget is not None else Decimal("0")
    bounds = {}
    costs = {}
    for target in targets:
        calls = provider_call_bounds[target.identity]
        cost_cap = total_paid_cost if paid_targets and target.identity == paid_targets[0][0].identity else Decimal("0")
        bounds[target.identity] = (calls, cost_cap, calls)
        costs[target.identity] = attempt_cost if cost_cap else Decimal("0")
    max_calls = sum(item[0] for item in bounds.values())
    if max_calls > 20000:
        parser.error("operation transport-call estimate exceeds its bound")
    try:
        dispatch = make_one_shot_dispatch(
            root_id=capture.root_id,
            subject_id=capture.subject_id,
            capture_digest=capture.digest,
            operation_id=operation_id,
            operation_digest=operation_digest,
            expires_at=expires_at,
            targets=tuple(targets),
            max_calls=max_calls,
            max_cost=total_paid_cost,
            max_resources=sum(item[2] for item in bounds.values()),
            upper_bound_costs=costs,
            per_target_bounds=bounds,
            approved_local_models={settings.model},
            clock=lambda: datetime.now(timezone.utc),
            boundary_check=boundary_check,
            resolver=resolver,
        )
    except AuthorizationDenied:
        parser.error("operation provider authorization could not be established")
    return {
        "dispatch": dispatch,
        "capture": capture,
        "data_key": data_key,
        "llm_key": llm_key,
        "settings": settings,
        "admission": admission,
        "expires_at": expires_at,
        "paid_provider": paid_targets[0][0].provider if paid_targets else None,
        "paid_cost_model": (cost_model_description(paid_targets[0][0]) if paid_targets else None),
        "paid_budget": paid_budget,
        "fd_self_service_pricing_confirmed": fd_pricing_confirmation,
        "advance_redo_fence": advance_redo_fence if operation == "paper-redo" else None,
    }


def _cli_llm_factory(settings, dispatch, api_key):
    from hedge_fund.llm import make_llm

    def llm_factory(_model_spec):
        return make_llm(
            model=settings.model,
            timeout=settings.timeout_seconds,
            max_tokens=int(settings.parameters.get("max_tokens", 4096)),
            temperature=settings.parameters.get("temperature"),
            top_p=settings.parameters.get("top_p"),
            context_size=(int(settings.parameters.get("context_size", 8192)) if settings.llm_provider == "Ollama" else None),
            api_key=api_key,
            endpoint=settings.endpoint,
            use_environment=False,
            dispatch=dispatch,
        )

    return llm_factory


def _cli_fund(spec, settings, dispatch, api_key):
    return Fund(
        spec,
        blind=True,
        llm_factory=_cli_llm_factory(settings, dispatch, api_key),
        breakpoints_dispatch=dispatch,
    )


def _require_cli_sim_account_ownership(broker: str, parser: argparse.ArgumentParser) -> None:
    if broker == "saxo":
        from hedge_fund.brokers.account_binding import (
            require_sim_account_ownership,
            SIMOwnershipUnknown,
        )

        try:
            require_sim_account_ownership()
        except SIMOwnershipUnknown as exc:
            parser.error(str(exc))


def _run_cli_tick(
    directory: Path,
    name: str,
    deployed,
    console: Console,
    *,
    session: str | None,
    again: bool,
    participant,
    root: RootContext,
    parser: argparse.ArgumentParser,
    args,
    request_id: str,
    expected_head: str | None,
    authorization=None,
):
    from hedge_fund.paper.ledger import UnresolvedTickIntentRefusal
    from hedge_fund.runtime.operations import DuplicateLogicalOperationRefusal

    _require_cli_sim_account_ownership(deployed.broker, parser)

    def execute():
        from hedge_fund.paper.ledger import PaperReconciliationRequired, PaperTickNoWork
        from hedge_fund.runtime.admission import paper_control_transition
        from hedge_fund.runtime.operations import OperationStore

        _verify_enrolled_head(participant, name)
        ledger = Ledger(directory)
        try:
            if again:
                if expected_head is None:
                    raise LedgerError("paper ledger head changed before the redo request")
                prior = ledger.redo_request_result(request_id, expected_head)
            else:
                prior = ledger.tick_request_result(
                    request_id,
                    expected_head=expected_head,
                    session=session,
                )
        except PaperTickNoWork as exc:
            raise NothingDue(str(exc)) from exc
        except PaperReconciliationRequired:
            ledger.halt("approval journal requires reconciliation")
            raise
        if prior is not None:
            return prior
        state = ledger.replay(
            deployed.spec.capital,
            full=True,
        )
        if state.prev_hash != expected_head:
            raise LedgerError(f"paper ledger head changed before the tick request " f"(expected {expected_head or 'none'}, found {state.prev_hash or 'none'})")
        if state.halted is not None:
            raise FundHalted(f"{name} is halted: {state.halted}")
        try:
            with paper_control_transition(directory, name):
                halted = ledger.halted()
                if halted is not None:
                    raise FundHalted(f"{name} is halted: {halted}")
                if again:
                    ledger.require_ready_for_work(state, approval_required=deployed.spec.approval_required)
                else:
                    ledger.require_ready_for_tick(state, approval_required=deployed.spec.approval_required)
        except PaperReconciliationRequired:
            ledger.halt("approval journal requires reconciliation")
            raise
        redo_source = ledger.latest() if again else None
        if again and redo_source is None:
            raise NothingDue(f"{name}: no session recorded yet, nothing to run again")
        provider_authority = authorization
        if provider_authority is None:
            settings, admission = _cli_settings(root, args, parser)
            from hedge_fund.fund import model_call_bounds

            model_calls_per_tick, llm_calls_per_tick = model_call_bounds(
                deployed.spec,
            )
            model_calls = len(deployed.universe) * model_calls_per_tick * 2
            llm_calls = len(deployed.universe) * llm_calls_per_tick * 2
            if not 1 <= model_calls <= 1000:
                parser.error("paper model-call estimate exceeds the 1000-call bound")
            provider_authority = _authorize_cli_operation(
                root,
                args,
                parser,
                settings=settings,
                admission=admission,
                spec=deployed.spec,
                universe=list(deployed.universe),
                operation="paper-redo" if again else "paper-tick",
                operation_inputs={
                    "session": session,
                    "redo": again,
                    **(
                        {
                            "redo_source_session": redo_source.session,
                            "redo_previous_head": redo_source.prev_hash,
                        }
                        if redo_source is not None
                        else {}
                    ),
                },
                expected_head=state.prev_hash,
                model_call_bound=model_calls,
                llm_call_bound=llm_calls,
                directory=directory,
                participant=participant,
            )
        settings = provider_authority["settings"]

        def build_fund(selected):
            return _cli_fund(
                selected,
                settings,
                provider_authority["dispatch"],
                provider_authority["llm_key"],
            )

        with make_data_client(
            provider=settings.data_provider,
            dispatch=provider_authority["dispatch"],
            api_key=provider_authority["data_key"],
        ) as raw:
            data = CachedDataClient(raw, live=deployed.spec.is_intraday)
            verb = "running the latest session again" if again else "advancing one session"
            with console.status(
                f"[cyan]{deployed.name}: {verb} over {', '.join(deployed.universe)}…",
                spinner="dots",
            ):
                if again:
                    from hedge_fund.runtime.policy import AuthorizationDenied

                    on_rewind = provider_authority.get("advance_redo_fence")
                    if not callable(on_rewind):
                        raise AuthorizationDenied("paper redo transition was not captured")
                    return redo(
                        directory,
                        data,
                        build_fund=build_fund,
                        on_rewind=on_rewind,
                        request_id=request_id,
                        expected_head=expected_head,
                    )
                return tick(
                    directory,
                    data,
                    session=session,
                    expected_head=expected_head,
                    build_fund=build_fund,
                    request_id=request_id,
                    operation_store=OperationStore(participant[0], admission=participant[1]),
                )

    try:
        if participant is None:
            return execute()
        with _paper_lane(participant, name, "manual_session"):
            return execute()
    except UnresolvedTickIntentRefusal as exc:
        parser.error(f"{exc.reason}: {json.dumps(exc.fields, sort_keys=True)}")
    except DuplicateLogicalOperationRefusal as exc:
        parser.error(f"{exc.reason}: {json.dumps(exc.fields, sort_keys=True)}")


# ---------------------------------------------------------------------------
# backtest
# ---------------------------------------------------------------------------


def _backtest(
    args,
    parser: argparse.ArgumentParser,
    console: Console,
    root: RootContext,
) -> None:
    universe = _universe(args.universe, parser)
    try:
        spec_path = paths.resolve_user_path(args.mandate)
        spec = load_spec(spec_path)
    except ValueError as exc:
        parser.error(str(exc))
    spec = _override_rebalance(spec, args.rebalance)
    end = args.end or completed_through()
    from hedge_fund.runtime.defaults import backtest_start_date

    start = args.start or backtest_start_date(_date.fromisoformat(end)).isoformat()
    try:
        start_day = _date.fromisoformat(start)
        end_day = _date.fromisoformat(end)
    except ValueError:
        parser.error("backtest dates must be valid ISO dates")
    if end_day < start_day or (end_day - start_day).days > 730:
        parser.error("backtest date range must be chronological and at most 730 days")
    from hedge_fund.fund import model_call_bounds

    model_calls_per_session, llm_calls_per_session = model_call_bounds(spec)
    weekdays = sum(1 for offset in range((end_day - start_day).days + 1) if (start_day + timedelta(days=offset)).weekday() < 5)
    model_calls = weekdays * len(universe) * model_calls_per_session
    llm_calls = weekdays * len(universe) * llm_calls_per_session
    if not 1 <= model_calls <= 1000:
        parser.error("estimated backtest model calls exceed the 1000-call bound")
    settings, admission = _cli_settings(root, args, parser)
    provider_authority = _authorize_cli_operation(
        root,
        args,
        parser,
        settings=settings,
        admission=admission,
        spec=spec,
        universe=universe,
        operation="backtest",
        operation_inputs={
            "start": start,
            "end": end,
            "rebalance": spec.rebalance,
        },
        expected_head=None,
        model_call_bound=model_calls,
        llm_call_bound=llm_calls,
        spec_path=spec_path,
    )
    # A backtest blinds the investor agents' prompts (no ticker, industry or
    # calendar dates): the LLM may have been trained on what those companies
    # did over the window, and that memory would otherwise score as skill.
    fund = _cli_fund(
        spec,
        settings,
        provider_authority["dispatch"],
        provider_authority["llm_key"],
    )

    if provider_authority["paid_provider"] is not None:
        calls, total, attempt = provider_authority["paid_budget"]
        console.print("[yellow]Paid dispatch authorized:[/] " f"{provider_authority['paid_provider']} · up to {calls} calls · " f"${attempt} per attempt · ${total} total · " f"expires {provider_authority['expires_at'].isoformat()} · " f"{provider_authority['paid_cost_model']}")
    with make_data_client(
        provider=settings.data_provider,
        dispatch=provider_authority["dispatch"],
        api_key=provider_authority["data_key"],
    ) as raw:
        fd = CachedDataClient(raw)
        with console.status(
            f"[cyan]{spec.name}: backtesting {start} → {end} " f"({spec.rebalance} rebalance vs {spec.benchmark}) " f"over {', '.join(universe)}…",
            spinner="dots",
        ):
            result = backtest_fund(fund, start, end, fd, universe)

    payload = result.model_dump_json(indent=2)
    print(payload)
    from hedge_fund.runtime.admission import AdmissionCoordinator, RootOwnerLease

    owner = RootOwnerLease.acquire(root, timeout=0)
    research_admission = AdmissionCoordinator(root, owner_lease=owner)
    try:
        saved = save_result(result, admission=research_admission)
    finally:
        owner.close()
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


def _paper(
    args,
    parser: argparse.ArgumentParser,
    console: Console,
    root: RootContext,
) -> None:
    if args.action == "create":
        universe = _universe(args.universe, parser)
        try:
            validate_fund_name(args.name)
            spec = load_spec(paths.resolve_user_path(args.mandate))
        except ValueError as exc:
            parser.error(str(exc))
        spec = _override_rebalance(spec, args.rebalance)
        _require_cli_sim_account_ownership(spec.broker, parser)
        if args.approval:
            spec = spec.model_copy(update={"approval_required": True})
        try:
            with _paper_writer_admission() as participant:
                if participant is None:
                    directory = deploy(args.name, spec, universe, root=PAPER_DIR)
                else:
                    with _paper_lane(participant, args.name, "deployment_lock"):
                        _verify_enrolled_inventory(participant)
                        directory = deploy(args.name, spec, universe, root=PAPER_DIR)
        except FileExistsError as exc:
            parser.error(str(exc))
        cadence = f"{spec.cadence_label}, {spec.window.label}" if spec.is_intraday else spec.cadence_label
        approval_note = "  ·  approval required" if spec.approval_required else ""
        console.print(f"[bold]{args.name}[/] deployed at {directory}  ·  mandate {spec.name}  ·  " f"{', '.join(universe)}  ·  ${spec.capital:,.0f}  ·  broker {spec.broker}  ·  {cadence}{approval_note}")
        root_argument = "--root <selected-root>"
        console.print(f"[dim]next: `aihf {root_argument} paper status {args.name} --head` for the reviewed head, " f"then `aihf {root_argument} --enable-network paper tick {args.name} --expected-head <head|none> " f"--request-id <unique-id>` for one bounded session. Headless scheduled runners are disabled.[/]")
        return

    if args.action == "list":
        for directory in list_deployed(PAPER_DIR):
            print(_status_line(directory))
        return

    if args.action in {"run", "stop"}:
        parser.error("Legacy unattended paper runner controls are disabled.")

    directory = _fund_dir(args.name, parser)

    if args.action == "reconcile-tick-request":
        confirmation_values = (args.request_id, args.intent_digest, args.preview_digest)
        if args.confirm:
            if args.request_id is None or args.preview_digest is None:
                parser.error("--confirm requires --request-id and --preview-digest")
            if args.intent_request_id is not None and args.intent_digest is None:
                parser.error("--intent-request-id requires --intent-digest")
        elif any(value is not None for value in confirmation_values):
            parser.error("confirmation fields require --confirm")
        with _paper_writer_admission() as participant:
            with _paper_lane(participant, args.name, "control_lane"):
                _verify_enrolled_head(participant, args.name)
                from hedge_fund.runtime.reconciliation import (
                    build_tick_intent_reconciliation_snapshot,
                    TickIntentReconciliationConfirmation,
                )

                deployed = load_deployed(directory)
                ledger = Ledger(directory)
                state = ledger.replay(deployed.spec.capital, full=True)
                latest = ledger.latest()
                snapshot = build_tick_intent_reconciliation_snapshot(
                    directory,
                    deployed,
                    ledger,
                    state,
                    latest,
                    intent_request_id=args.intent_request_id,
                )
                if not args.confirm:
                    print(
                        json.dumps(
                            {
                                "name": args.name,
                                "preview": snapshot.preview.model_dump(mode="json"),
                            },
                            indent=2,
                            sort_keys=True,
                        )
                    )
                    return
                if not snapshot.preview.required or not snapshot.preview.recoverable:
                    parser.error(f"Tick intent is not recoverable: {snapshot.preview.reason}")
                try:
                    confirmation = TickIntentReconciliationConfirmation(
                        request_id=args.request_id,
                        intent_request_id=args.intent_request_id,
                        intent_digest=args.intent_digest,
                        preview_digest=args.preview_digest,
                    )
                    receipt_id = ledger.reconcile_tick_intent(
                        deployed.spec.capital,
                        confirmation=confirmation,
                        operator="cli",
                    )
                except (TypeError, ValueError, LedgerError) as exc:
                    parser.error(f"Tick-intent reconciliation failed: {type(exc).__name__}")
                print(
                    json.dumps(
                        {
                            "name": args.name,
                            "intent_request_id": args.intent_request_id,
                            "reconciliation_id": receipt_id,
                        },
                        indent=2,
                        sort_keys=True,
                    )
                )
        return

    if args.action == "tick":
        if not args.enable_network:
            parser.error("paper tick requires explicit --enable-network")
        if args.again and args.session is not None:
            parser.error("paper tick --session cannot be combined with --again")
        deployed = load_deployed(directory)
        _require_cli_sim_account_ownership(deployed.broker, parser)
        with _paper_writer_admission() as participant:
            record = _run_cli_tick(
                directory,
                args.name,
                deployed,
                console,
                session=args.session,
                again=args.again,
                participant=participant,
                root=root,
                parser=parser,
                args=args,
                request_id=args.request_id,
                expected_head=args.expected_head,
            )
        print(record.model_dump_json(indent=2))
        console.print(_tick_summary(deployed.name, record))
        return

    if args.action == "status":
        if args.head:
            deployed = load_deployed(directory)
            ledger = Ledger(directory)
            state = ledger.replay(deployed.spec.capital, full=True)
            latest = ledger.latest()
            if state.prev_hash != (latest.hash if latest is not None else None):
                raise LedgerError("paper ledger head changed during status")
            print(latest.hash if latest is not None else "none")
            return
        line, deployed, latest, approval, approval_error = _status_view(directory)
        print(line)
        if deployed is not None and latest is not None and latest.decision is not None:
            when = "bar" if deployed.spec.is_intraday else "close"
            if approval_error is not None:
                print(f"  pending decision, {approval_error}:")
            elif deployed.spec.approval_required:
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
        if args.action == "approve" and args.now and not args.enable_network:
            parser.error("approve --now requires explicit --enable-network before the ledger verdict")
        if args.action == "approve" and args.now and not args.tick_request_id:
            parser.error("approve --now requires a separate --tick-request-id")
        deployed = load_deployed(directory)
        if args.action == "approve" and args.now:
            _require_cli_sim_account_ownership(deployed.broker, parser)
        ledger = Ledger(directory)

        def run_approved_tick(participant, authorization):
            try:
                record = _run_cli_tick(
                    directory,
                    args.name,
                    deployed,
                    console,
                    session=None,
                    again=False,
                    participant=participant,
                    root=root,
                    parser=parser,
                    args=args,
                    request_id=args.tick_request_id,
                    expected_head=args.expected_head,
                    authorization=authorization,
                )
            except NothingDue:
                console.print(f"{args.name}: will execute at the next close")
                return
            print(record.model_dump_json(indent=2))
            console.print(_tick_summary(deployed.name, record))

        with _paper_writer_admission() as participant:
            provider_authority = None
            _verify_enrolled_head(participant, args.name)
            prior = ledger.approval_command_result(args.request_id, args.action, "cli", args.expected_head)
            if prior is not None:
                if args.action == "approve":
                    console.print(f"[green]{args.name}[/] approved decision from {prior['decision_as_of']}")
                else:
                    console.print(f"[yellow]{args.name}[/] rejected decision from {prior['decision_as_of']}")
                if args.action == "approve" and args.now:
                    run_approved_tick(participant, provider_authority)
                return
            state = ledger.replay(deployed.spec.capital)
            if state.halted is not None:
                raise FundHalted(f"{args.name} is halted: {state.halted}")
            if state.prev_hash != args.expected_head:
                raise LedgerError(f"paper ledger head changed before the verdict request " f"(expected {args.expected_head or 'none'}, found {state.prev_hash or 'none'})")
            if not deployed.spec.approval_required:
                parser.error(f"approval gate is not enabled for '{args.name}'")
            if state.pending is None:
                parser.error(f"nothing is awaiting approval for '{args.name}'")
            if state.prev_hash is None:
                parser.error(f"pending decision for '{args.name}' has no source record hash")
            if args.action == "approve" and args.now:
                settings, admission = _cli_settings(root, args, parser)
                from hedge_fund.fund import model_call_bounds

                model_calls_per_tick, llm_calls_per_tick = model_call_bounds(deployed.spec)
                model_calls = len(deployed.universe) * model_calls_per_tick * 2
                llm_calls = len(deployed.universe) * llm_calls_per_tick * 2
                if not 1 <= model_calls <= 1000:
                    parser.error("paper model-call estimate exceeds the 1000-call bound")
                provider_authority = _authorize_cli_operation(
                    root,
                    args,
                    parser,
                    settings=settings,
                    admission=admission,
                    spec=deployed.spec,
                    universe=list(deployed.universe),
                    operation="paper-tick",
                    operation_inputs={
                        "pending_session": state.pending.as_of,
                        "run_now": True,
                    },
                    expected_head=state.prev_hash,
                    model_call_bound=model_calls,
                    llm_call_bound=llm_calls,
                    directory=directory,
                    participant=participant,
                )
            if participant is None:
                ledger.set_approval(
                    args.action,
                    state.pending.as_of,
                    state.prev_hash,
                    "cli",
                    request_id=args.request_id,
                )
            else:
                from hedge_fund.runtime.admission import (
                    AdmissionError,
                    paper_approval_transition,
                )
                from hedge_fund.runtime.handover import HandoverError

                try:
                    with paper_approval_transition(participant[1], args.name) as proof:
                        ledger.set_approval(
                            args.action,
                            state.pending.as_of,
                            state.prev_hash,
                            "cli",
                            request_id=args.request_id,
                            admission=proof,
                        )
                except (AdmissionError, HandoverError) as exc:
                    raise PaperWriterDenied("Paper verdict admission is unavailable.") from exc
            if args.action == "approve":
                console.print(f"[green]{args.name}[/] approved decision from {state.pending.as_of}")
            else:
                console.print(f"[yellow]{args.name}[/] rejected decision from {state.pending.as_of}")
            if args.action == "approve" and args.now:
                run_approved_tick(participant, provider_authority)
        return

    ledger = Ledger(directory)
    if args.action == "halt":

        def directory_identity():
            try:
                info = directory.stat(follow_symlinks=False)
            except OSError:
                parser.error(f"paper fund {args.name!r} is no longer available")
            if not stat.S_ISDIR(info.st_mode):
                parser.error(f"paper fund {args.name!r} is no longer available")
            return info.st_dev, info.st_ino

        expected_identity = directory_identity()
    with _paper_writer_admission(verify_inventory=args.action != "halt") as participant:
        if args.action == "halt":
            with _paper_lane(participant, args.name, "halt_lane"):
                if directory_identity() != expected_identity:
                    parser.error(f"paper fund {args.name!r} changed before halt admission")
                ledger.halt(args.reason, request_id=args.request_id)
                console.print(f"[red]{args.name} halted:[/] {args.reason}")
        elif args.action == "resume":
            with _paper_lane(participant, args.name, "control_lane"):
                raise PaperWriterDenied("Resume requires a verified reconciliation receipt; automatic resume is disabled.")


def _status_line(directory: Path) -> str:
    return _status_view(directory)[0]


def _status_view(directory: Path):
    from hedge_fund.paper.ledger import PaperReconciliationRequired

    try:
        deployed = load_deployed(directory)
    except ValueError as exc:
        return f"{directory.name:<18} unavailable: {exc}", None, None, None, None
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
    approval = None
    approval_error = None
    try:
        replayed = ledger.replay(deployed.spec.capital)
        if replayed.prev_hash != (latest.hash if latest is not None else None):
            raise PaperReconciliationRequired("ledger head changed during observation")
        approval = ledger.observe_approval_for_display(replayed, approval_required=deployed.spec.approval_required)
    except PaperReconciliationRequired:
        approval_error = "in progress or requires reconciliation"
    except (LedgerError, OSError, ValueError):
        approval_error = "approval history unavailable"
    if approval_error is not None:
        approval_state = f"  ·  {approval_error}"
    elif deployed.spec.approval_required and latest is not None and latest.decision is not None:
        if approval is not None:
            approval_state = f"  ·  {approval['verdict']} recorded"
        else:
            approval_state = "  ·  awaiting approval"
    line = f"{deployed.name:<18} {deployed.spec.name}  ·  {' '.join(deployed.universe)}  ·  " f"broker {deployed.broker}  ·  {deployed.spec.cadence_label}{running}  ·  {state}{flag}{approval_state}"
    return line, deployed, latest, approval, approval_error


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
