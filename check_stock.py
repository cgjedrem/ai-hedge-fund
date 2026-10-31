"""Check a single stock the way the fund's analysts would.

Usage (from the repo root):
    python -m poetry run python check_stock.py NVDA
    python -m poetry run python check_stock.py XOM --agents burry,damodaran
    python -m poetry run python check_stock.py AAPL --date 2026-10-23

What it does:
  1. Builds the same fundamentals snapshot the fund builds each session
     (yfinance data, trailing-twelve-month metrics, newest first).
  2. Prints the numbers the investor personas will look at.
  3. Asks each persona agent for a verdict via your Ollama model
     (same prompts, same cache, as a live session).
  4. Also runs the PEAD quant model (earnings-surprise drift).

Costs nothing but time: data comes from Yahoo, opinions from your Ollama.
Provider credentials must already be present in the process environment.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from hedge_fund.data import make_data_client
from hedge_fund.features.snapshot import build_snapshot, InsufficientData
from hedge_fund.signals import ALPHA_MODEL_REGISTRY

DEFAULT_PANEL = ["burry", "pabrai", "damodaran", "ackman", "pead"]


def latest_session_date() -> str:
    """Most recent completed NYSE session (rough: skip weekends)."""
    d = datetime.now(timezone.utc).date()
    while d.weekday() >= 5:
        d = d.fromordinal(d.toordinal() - 1)
    return d.isoformat()


def show_snapshot(ticker: str, as_of: str, data_client) -> None:
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


def ask_agents(ticker: str, as_of: str, data_client, names: list[str]) -> None:
    print(f"\n=== analyst verdicts on {ticker} @ {as_of} ===")
    for name in names:
        agent = ALPHA_MODEL_REGISTRY[name]()
        try:
            signal = agent.predict(ticker, as_of, data_client)
        except Exception as exc:
            print(f"  {name:<11} ERROR: {exc}")
            continue
        meta = signal.metadata or {}
        conf = meta.get("confidence", "-")
        cached = " (cached)" if meta.get("cached") else ""
        print(f"  {name:<11} {signal.value:+.2f}  confidence {conf}{cached}")
        if signal.reasoning:
            for line in signal.reasoning.strip().splitlines():
                print(f"      {line}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("ticker")
    ap.add_argument("--date", default=None, help="as-of date YYYY-MM-DD (default: latest session)")
    ap.add_argument("--agents", default=",".join(DEFAULT_PANEL),
                    help="comma-separated from: " + ", ".join(ALPHA_MODEL_REGISTRY))
    args = ap.parse_args()

    as_of = args.date or latest_session_date()
    data_client = make_data_client()
    ticker = args.ticker.upper()

    try:
        show_snapshot(ticker, as_of, data_client)
    except InsufficientData as exc:
        print(f"snapshot: {exc}")
        print("(the fund's personas would ABSTAIN on this ticker)")
        return
    ask_agents(ticker, as_of, data_client, [a.strip() for a in args.agents.split(",")])


if __name__ == "__main__":
    main()