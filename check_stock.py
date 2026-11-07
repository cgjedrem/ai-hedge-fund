"""Check a single stock the way the fund's analysts would.

Usage (from the repo root):
    poetry run python check_stock.py NVDA --root <root> --enable-network
    poetry run python check_stock.py XOM --root <root> --enable-network --agents burry,damodaran
    poetry run python check_stock.py AAPL --root <root> --enable-network --date 2026-10-23

What it does:
  1. Builds the same fundamentals snapshot the fund builds each session
     (yfinance data, trailing-twelve-month metrics, newest first).
  2. Prints the numbers the investor personas will look at.
  3. Asks each persona agent for a verdict via your Ollama model
     (same prompts, same cache, as a live session).
  4. Also runs the PEAD quant model (earnings-surprise drift).

The default Yahoo data and local Ollama model use no provider credentials.
Paid providers require explicit bounded consent and a root-private credential.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Sequence

from hedge_fund.data.protocol import DataClient
from hedge_fund.features.snapshot import build_snapshot, InsufficientData
from hedge_fund.runtime.policy import AuthorizationDenied
from hedge_fund.signals import ALPHA_MODEL_REGISTRY
from hedge_fund.signals.base import AlphaModel

DEFAULT_PANEL = ["burry", "pabrai", "damodaran", "ackman", "pead"]


def latest_session_date() -> str:
    """Most recent completed NYSE session (rough: skip weekends)."""
    d = datetime.now(timezone.utc).date()
    while d.weekday() >= 5:
        d = d.fromordinal(d.toordinal() - 1)
    return d.isoformat()


def show_snapshot(ticker: str, as_of: str, data_client: DataClient) -> None:
    snapshot = build_snapshot(ticker, as_of, data_client)
    print(f"\n=== {ticker} fundamentals as of {as_of} "
          f"({snapshot.sector or '?'}) — {len(snapshot.periods)} ttm periods ===")
    print(f"{'period':<12}{'rev gr':>8}{'gross':>8}{'oper':>8}{'net':>8}"
          f"{'ROE':>8}{'D/E':>7}{'curr':>7}{'P/E':>8}{'FCF/sh':>9}")
    for p in snapshot.periods[:8]:
        def pct(v):
            return f"{v * 100:.1f}%" if v is not None else "-"

        def num(v, w):
            return f"{v:.2f}".rjust(w) if v is not None else "-".rjust(w)
        print(f"{p.report_period:<12}"
              f"{pct(p.revenue_growth):>8}{pct(p.gross_margin):>8}"
              f"{pct(p.operating_margin):>8}{pct(p.net_margin):>8}"
              f"{pct(p.return_on_equity):>8}"
              f"{num(p.debt_to_equity, 7)}{num(p.current_ratio, 7)}"
              f"{num(p.price_to_earnings_ratio, 8)}{num(p.free_cash_flow_per_share, 9)}")
    print(f"derived: ROE avg {snapshot.roe_avg}, net margin avg {snapshot.net_margin_avg}, "
          f"EPS YoY {snapshot.eps_growth_yoy}, BVPS CAGR {snapshot.bvps_cagr}")


def ask_agents(
    ticker: str,
    as_of: str,
    data_client: DataClient,
    agents: Sequence[AlphaModel],
) -> None:
    print(f"\n=== analyst verdicts on {ticker} @ {as_of} ===")
    for agent in agents:
        try:
            signal = agent.predict(ticker, as_of, data_client)
        except AuthorizationDenied:
            raise
        except (ValueError, RuntimeError) as exc:
            if type(exc) not in {ValueError, RuntimeError}:
                raise
            print(f"  {agent.name:<11} ERROR: {type(exc).__name__} (analyst failed)")
            continue
        name = agent.name
        meta = signal.metadata or {}
        conf = meta.get("confidence", "-")
        cached = " (cached)" if meta.get("cached") else ""
        print(f"  {name:<11} {signal.value:+.2f}  confidence {conf}{cached}")
        if signal.reasoning:
            for line in signal.reasoning.strip().splitlines():
                print(f"      {line}")


def main(argv: list[str] | None = None) -> None:
    for stream in (sys.stdout, sys.stderr):
        if stream is not None and hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("ticker")
    ap.add_argument("--root", type=Path, required=True, help="existing enrolled absolute data root")
    ap.add_argument("--enable-network", action="store_true", help="authorize bounded provider requests for this invocation")
    ap.add_argument("--load-dotenv", action="store_true", help="load safe non-secret settings from this root's .env")
    ap.add_argument("--model", help="override the captured LLM model")
    ap.add_argument("--date", default=None, help="as-of date YYYY-MM-DD (default: latest session)")
    ap.add_argument("--agents", default=",".join(DEFAULT_PANEL),
                    help="comma-separated from: " + ", ".join(ALPHA_MODEL_REGISTRY))
    ap.add_argument("--authorize-paid-provider", metavar="PROVIDER")
    ap.add_argument("--confirm-fd-self-service-pricing", action="store_true")
    ap.add_argument("--paid-max-calls", type=int)
    ap.add_argument("--paid-max-cost-usd")
    ap.add_argument("--paid-max-attempt-cost-usd")
    ap.add_argument("--deadline-minutes", type=int, default=60)
    args = ap.parse_args(argv)

    from hedge_fund import paths
    from hedge_fund.data import CachedDataClient, make_data_client
    from hedge_fund.fund import custom_strategy, Fund, FundSpec, model_call_bounds
    from hedge_fund.llm import LLMCallError, PromptCache
    from hedge_fund.paper.ledger import LedgerError
    from hedge_fund.run import _authorize_cli_operation, _cli_llm_factory, _cli_settings
    from hedge_fund.runtime.capture import is_capture_ticker
    from hedge_fund.runtime.handover import HandoverError, verify_root_inventory
    from hedge_fund.runtime.root import RootContext, RootPathError

    ticker = args.ticker.strip().upper()
    if not is_capture_ticker(ticker):
        ap.error("ticker is invalid")
    as_of = args.date or latest_session_date()
    try:
        if date.fromisoformat(as_of).isoformat() != as_of:
            raise ValueError("noncanonical date")
    except ValueError:
        ap.error("date must be a valid YYYY-MM-DD")
    names = [name.strip() for name in args.agents.split(",")]
    if any(not name for name in names):
        ap.error("analyst selection is invalid")
    try:
        strategy = custom_strategy(names)
        spec = FundSpec.model_validate(
            {
                "schema_version": 2,
                "name": "stock-check",
                "strategies": [strategy],
                "risk": {"max_position_pct": 1, "max_gross_exposure": 1},
                "rebalance": "daily",
            }
        )
        model_calls, llm_calls = model_call_bounds(spec)
    except ValueError:
        ap.error("analyst selection is invalid")
    if not args.enable_network:
        ap.error("provider access requires explicit --enable-network")

    try:
        root = RootContext.open(args.root)
    except (OSError, RootPathError):
        ap.error("data root is invalid")
    try:
        with paths.bound_root(root):
            try:
                verify_root_inventory(root)
                paths.load_root_dotenv(root, enabled=args.load_dotenv)
            except (HandoverError, LedgerError, OSError, RootPathError, UnicodeError, ValueError):
                ap.error("offline root enrollment, inventory, or settings are unavailable")
            settings, admission = _cli_settings(root, args, ap)
            authority = _authorize_cli_operation(
                root,
                args,
                ap,
                settings=settings,
                admission=admission,
                spec=spec,
                universe=[ticker],
                operation="stock-check",
                operation_inputs={"ticker": ticker, "date": as_of, "agents": [model.name for model in strategy.models]},
                expected_head=None,
                model_call_bound=model_calls,
                llm_call_bound=llm_calls,
            )
            try:
                with make_data_client(
                    provider=settings.data_provider,
                    dispatch=authority["dispatch"],
                    api_key=authority["data_key"],
                ) as raw:
                    data_client = CachedDataClient(raw, cache_dir=root.path / "cache" / "data", live=True)
                    try:
                        show_snapshot(ticker, as_of, data_client)
                    except InsufficientData as exc:
                        print(f"snapshot: {exc}")
                        print("(the fund's personas would ABSTAIN on this ticker)")
                        return
                    fund = Fund(
                        spec,
                        cache=PromptCache(root.path / "cache" / "llm"),
                        llm_factory=_cli_llm_factory(settings, authority["dispatch"], authority["llm_key"]),
                        breakpoints_dispatch=authority["dispatch"],
                        fail_on_llm_error=True,
                    )
                    ask_agents(ticker, as_of, data_client, fund.strategies[0][1])
            except AuthorizationDenied:
                ap.exit(1, "provider operation denied by its captured authorization\n")
            except LLMCallError:
                ap.exit(1, "provider request failed; operation stopped\n")
    finally:
        root.close()


if __name__ == "__main__":
    main()
