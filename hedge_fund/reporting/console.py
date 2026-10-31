"""Rich report helpers for headless and web entry points."""

from __future__ import annotations

import math
from numbers import Real

from rich import box
from rich.table import Table
from rich.text import Text

from hedge_fund.pipeline import SessionRecord
from hedge_fund.reporting.names import SHORT_NAMES
from hedge_fund.reporting.palette import BRIGHT, GREEN, MUTED, RED, TEXT
from hedge_fund.scorecard import Scorecard

_NONE = Text("–", style=MUTED)


def session_headline(name: str, record: SessionRecord) -> Text:
    """Report one recorded session."""
    if not isinstance(name, str) or not isinstance(record, SessionRecord):
        raise TypeError("name and session record are required")
    facts = [f"session {record.session}"]
    if record.executed is not None:
        executed = record.executed
        refreshed = executed.refreshed_assessment.as_of if executed.refreshed_assessment else executed.as_of
        facts.append(f"executed the {executed.as_of} decision (refreshed {refreshed})")
    if record.decision is not None:
        signals = sum(len(strategy.signals) for strategy in record.decision.strategies)
        facts.append(f"decided · {signals} signals · executes next session")
    if record.executed is None and record.decision is None:
        facts.append("valuation only")
    return Text.assemble((name, f"bold {BRIGHT}"), ("  ·  " + "  ·  ".join(facts), MUTED))


def cost_line(trading_cost: float, traded_notional: float) -> str:
    """Show cost as basis points of traded notional."""
    if any(isinstance(value, bool) or not isinstance(value, Real) or not math.isfinite(value) for value in (trading_cost, traded_notional)):
        raise ValueError("cost and notional must be finite numbers")
    if traded_notional == 0:
        return "no trades"
    bps = trading_cost / traded_notional * 10_000
    return f"costs ${trading_cost:,.0f} · {bps:.1f} bps of ${traded_notional:,.0f} traded"


def analyst_table(card: Scorecard) -> Table:
    """Render analyst grades with sample counts."""
    if not isinstance(card, Scorecard):
        raise TypeError("a scorecard is required")
    judged = f"judged over one {card.horizon} period" if card.horizon else "no decisions yet"
    table = _table(f"ANALYSTS  ·  {judged}")
    table.add_column("analyst", style=f"bold {TEXT}")
    table.add_column("views", justify="right")
    table.add_column("abstained", justify="right")
    table.add_column("hit rate", justify="right")
    table.add_column("slugging", justify="right")
    table.add_column("IC", justify="right")
    table.add_column("IC t", justify="right")
    table.add_column("dates", justify="right")
    if not card.analysts:
        table.caption = "nothing to grade yet: a view is scored once the next decision is made"
        table.caption_style = MUTED
        table.caption_justify = "left"
        return table
    for analyst in card.analysts:
        table.add_row(
            SHORT_NAMES.get(analyst.name, analyst.name),
            str(analyst.n_views),
            Text(str(analyst.n_abstained), style=MUTED if analyst.n_abstained == 0 else TEXT),
            _rate(analyst.hit_rate, analyst.n_directional),
            _NONE if analyst.slugging is None else Text(f"{analyst.slugging:.2f}×", style=TEXT),
            _NONE if analyst.ic_mean is None else Text(f"{analyst.ic_mean:+.3f}", style=_signed(analyst.ic_mean)),
            _NONE if analyst.ic_t_stat is None else Text(f"{analyst.ic_t_stat:+.1f}", style=_significance(analyst.ic_t_stat)),
            str(analyst.n_dates),
        )
    return table


def strategy_table(card: Scorecard) -> Table:
    """Render sleeve P&L and unattributed fund return."""
    if not isinstance(card, Scorecard):
        raise TypeError("a scorecard is required")
    table = _table("STRATEGIES  ·  P&L between executions")
    table.add_column("strategy", style=f"bold {TEXT}")
    table.add_column("periods", justify="right")
    table.add_column("P&L", justify="right")
    table.add_column("return", justify="right")
    table.add_column("win rate", justify="right")
    table.add_column("max DD", justify="right")
    table.add_column("share", justify="right")
    if not card.strategies:
        table.caption = "nothing to attribute yet: a sleeve is scored between two executions"
        table.caption_style = MUTED
        table.caption_justify = "left"
        return table
    for strategy in card.strategies:
        table.add_row(
            strategy.name,
            str(strategy.n_periods),
            Text(f"{strategy.pnl:+,.0f}", style=_signed(strategy.pnl)),
            Text(f"{strategy.return_pct:+.2%}", style=_signed(strategy.return_pct)),
            _rate(strategy.win_rate, strategy.n_periods),
            Text(f"{strategy.max_drawdown_pct:.1%}", style=RED if strategy.max_drawdown_pct > 0 else MUTED),
            _NONE if strategy.share_of_pnl is None else Text(f"{strategy.share_of_pnl:+.0%}", style=TEXT),
        )
    table.caption = f"fund P&L {card.fund_pnl:+,.0f}  ·  unattributed {card.unattributed:+,.0f}  ·  " f"of which trading costs {-card.trading_cost:+,.0f}"
    table.caption_style = MUTED
    table.caption_justify = "left"
    return table


def _table(title: str) -> Table:
    return Table(box=box.SQUARE, header_style="bold", border_style="#1f2b25", title=Text(title, style=f"bold {BRIGHT}"), title_justify="left")


def _rate(value: float | None, count: int) -> Text:
    if value is None:
        return _NONE
    return Text.assemble((f"{value:.0%}", _signed(value - 0.5)), (f" of {count}", MUTED))


def _signed(value: float) -> str:
    if value > 0:
        return GREEN
    if value < 0:
        return RED
    return MUTED


def _significance(t_stat: float) -> str:
    if t_stat >= 2:
        return GREEN
    if t_stat <= -2:
        return RED
    return MUTED
