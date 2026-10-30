"""The pipeline's two stages: assess views, then execute them at a later close.

`assess_fund` runs the analysts as of a completed session and turns their
views into validated target weights (a DecisionRecord — no orders, no
broker). `execute_decision` sizes that decision against the broker's book at
a subsequent session's exact closing prices and returns the CycleRecord.
`hedge_fund.pipeline.session.advance` sequences the two across sessions;
nothing here knows about the clock.
"""

from __future__ import annotations

from datetime import date as _date
from datetime import timedelta
from math import isfinite
from typing import Callable

from hedge_fund.brokers.models import Fill, Order, Position
from hedge_fund.brokers.protocol import Broker, OrderSubmissionDeferred
from hedge_fund.data.protocol import DataClient
from hedge_fund.fund import Fund, normalize_universe
from hedge_fund.models import Signal
from hedge_fund.pipeline.clock import Clock, clock_for, execution_policy, PinnedQuotes
from hedge_fund.pipeline.execution import build_orders
from hedge_fund.pipeline.models import (
    CycleRecord,
    DecisionRecord,
    StrategyRecord,
    TickerSkip,
)
from hedge_fund.portfolio.construction import blend_signals, WEIGHT_TOLERANCE
from hedge_fund.portfolio.validation import validate_targets
from hedge_fund.risk.limits import apply_limits
from hedge_fund.signals import get_investment_approach

# How far back to look for the most recent close: covers weekends, holiday
# clusters, and short trading halts without reaching into stale history.
_MARK_LOOKBACK_DAYS = 7


def assess_fund(
    fund: Fund,
    as_of: str,
    data_client: DataClient,
    universe: list[str],
    clock: Clock | None = None,
) -> DecisionRecord:
    """Construct validated target weights using only the assessment cutoff."""
    clock = clock or clock_for(fund.spec, data_client)
    if not clock.is_complete(as_of):
        raise ValueError(f"assessment {as_of} requires incomplete data")
    spec = fund.spec.model_copy(deep=True)
    universe = normalize_universe(universe)
    marks, skipped = _mark_prices(universe, clock.session_date(as_of), data_client)

    tradeable = [t for t in universe if t in marks]
    # Analysts read the session's print, not the wire: the same price the
    # engine marks and executes with, and nothing from after the session.
    view = PinnedQuotes(data_client, clock, as_of)

    # Each strategy runs its own analysts and blends its own sleeve; the fund
    # nets the sleeves by capital slice. A persona staffed into two strategies
    # is asked twice, but the second ask is a prompt-cache hit, not spend.
    total_slice = sum(s.weight for s, _ in fund.strategies)
    strategy_records: list[StrategyRecord] = []
    netted: dict[str, float] = {t: 0.0 for t in tradeable}
    for strategy, staff in fund.strategies:
        signals: list[Signal] = []
        for ticker in tradeable:
            for model in staff:
                signals.append(model.predict(ticker, as_of, view))
        blend = blend_signals(
            signals,
            strategy.model_weights,
            strategy.blend.gross_target,
            mode=strategy.blend.mode,
            investment_approaches={m.name: get_investment_approach(m.name) for m in strategy.models},
        )
        slice_ = strategy.weight / total_slice
        for ticker, weight in blend.weights.items():
            netted[ticker] += slice_ * weight
        strategy_records.append(
            StrategyRecord(
                name=strategy.name,
                slice=slice_,
                signals=signals,
                convictions=blend.convictions,
                weights=blend.weights,
                eligible_scores=blend.eligible_scores,
                flat_reason=blend.flat_reason,
            )
        )

    preserve_proportions = any(s.blend.mode == "dollar_neutral" for s in spec.strategies)
    risk = apply_limits(netted, spec.risk, preserve_proportions=preserve_proportions)
    if risk.scale_factor is not None:
        multipliers = dict.fromkeys(netted, risk.scale_factor)
    else:
        # Exactly offset contributions stay visible even though no net trade remains.
        multipliers = {ticker: risk.weights[ticker] / weight if weight != 0 else 1.0 for ticker, weight in netted.items()}
    for record in strategy_records:
        record.final_contribution = {ticker: record.slice * weight * multipliers[ticker] for ticker, weight in record.weights.items()}
    validate_targets(spec, strategy_records, risk.weights)

    return DecisionRecord(
        fund=spec.name,
        as_of=as_of,
        spec=spec,
        universe=universe,
        marks=marks,
        skipped=skipped,
        strategies=strategy_records,
        target_weights=netted,
        clamps=risk.clamps,
        risk_scale_factor=risk.scale_factor,
        final_weights=risk.weights,
    )


def execute_decision(
    fund: Fund,
    original: DecisionRecord,
    session: str,
    broker: Broker,
    data_client: DataClient,
    clock: Clock | None = None,
    *,
    on_fill: Callable[[Order, Fill], None] | None = None,
) -> CycleRecord:
    """Refresh views before sizing a complete rebalance at exact session prices."""
    clock = clock or clock_for(fund.spec, data_client)
    if session <= original.as_of or not clock.is_complete(session):
        raise ValueError(f"execution session {session} must follow {original.as_of} and be complete")
    if fund.spec != original.spec:
        raise ValueError("fund mandate changed after assessment; create a new assessment")
    cutoff = clock.previous(session)
    effective = (
        original
        if cutoff == original.as_of
        else assess_fund(
            fund,
            cutoff,
            data_client,
            original.universe,
            clock,
        )
    )
    spec = effective.spec
    validate_targets(spec, effective.strategies, effective.final_weights)
    held = broker.positions()
    targets = {t: w for t, w in effective.final_weights.items() if w != 0}
    marks = clock.marks(list(set(held) | set(targets)), session).prices
    cash_before = broker.cash()
    equity_before = cash_before + sum(p.shares * marks[t] for t, p in held.items())
    if not isfinite(equity_before) or equity_before <= 0:
        raise ValueError(f"{spec.name}: equity on {session} must be finite and positive")
    orders = build_orders(targets, held, marks, equity_before, min_order_pct=spec.min_order_pct_of_equity)
    current_weights = {t: p.shares * marks[t] / equity_before for t, p in held.items()}
    current_gross = sum(abs(weight) for weight in current_weights.values())

    def violates_limit(projected: float, current: float, limit: float) -> bool:
        return projected > limit + WEIGHT_TOLERANCE and (current <= limit + WEIGHT_TOLERANCE or projected > current + WEIGHT_TOLERANCE)

    def validate_projected_orders(candidate_orders, *, filtered: bool = False) -> None:
        projected = {t: p.shares for t, p in held.items()}
        for candidate in candidate_orders:
            projected[candidate.ticker] = projected.get(candidate.ticker, 0) + (candidate.quantity if candidate.side == "buy" else -candidate.quantity)
        weights = {t: shares * marks[t] / equity_before for t, shares in projected.items()}
        suffix = " after broker order filtering" if filtered else ""
        for ticker, weight in weights.items():
            if not isfinite(weight) or violates_limit(abs(weight), abs(current_weights.get(ticker, 0)), spec.risk.max_position_pct):
                raise ValueError(f"{ticker}: projected position violates max_position_pct{suffix}")
        projected_gross = sum(abs(weight) for weight in weights.values())
        if not isfinite(projected_gross) or violates_limit(projected_gross, current_gross, spec.risk.max_gross_exposure):
            raise ValueError(f"projected portfolio violates max_gross_exposure{suffix}")

    try:
        validate_projected_orders(orders)
    except ValueError:
        if not spec.min_order_pct_of_equity:
            raise
        # The cost gate may have skipped trims the risk limits rely on. Put
        # back every skipped order that shrinks a position — each can only
        # lower exposure, so this is never less safe than the ungated basket.
        kept = {order.ticker for order in orders}
        orders = [order for order in build_orders(targets, held, marks, equity_before) if order.ticker in kept or _shrinks(order, held)]
        validate_projected_orders(orders)
    filter_orders = getattr(broker, "filter_orders", None)
    if callable(filter_orders):
        orders = filter_orders(orders)
        validate_projected_orders(orders, filtered=True)
    if spec.broker == "saxo" and len(orders) > 1:
        pending = list(orders)
        ordered: list[Order] = []
        projected = dict(current_weights)
        gross = current_gross
        while pending:
            for index, order in enumerate(pending):
                old_weight = projected.get(order.ticker, 0.0)
                delta = order.quantity if order.side == "buy" else -order.quantity
                new_weight = old_weight + delta * marks[order.ticker] / equity_before
                next_gross = gross - abs(old_weight) + abs(new_weight)
                if not isfinite(new_weight) or not isfinite(next_gross) or violates_limit(abs(new_weight), abs(current_weights.get(order.ticker, 0)), spec.risk.max_position_pct) or violates_limit(next_gross, current_gross, spec.risk.max_gross_exposure):
                    continue
                ordered.append(pending.pop(index))
                projected[order.ticker] = new_weight
                gross = next_gross
                break
            else:
                raise ValueError("Saxo order basket has no safe execution sequence under projected risk limits")
        orders = ordered
    submitted: list[Order] = []
    fills: list[Fill] = []
    deferred: list[Order] = []
    deferral_reason = None
    for index, order in enumerate(orders):
        try:
            fill = broker.place_order(order)
        except OrderSubmissionDeferred as exc:
            deferred = orders[index:]
            deferral_reason = str(exc) or "order submission deferred"
            break
        submitted.append(order)
        fills.append(fill)
        if on_fill is not None:
            on_fill(order, fill)
    positions = {t: p.shares for t, p in broker.positions().items()}
    cash = broker.cash()
    fields = effective.model_dump(exclude={"as_of", "marks"})
    return CycleRecord(
        **fields,
        as_of=original.as_of,
        marks=marks,
        equity_before=equity_before,
        cash_before=cash_before,
        orders=submitted,
        fills=fills,
        deferred_orders=deferred,
        deferral_reason=deferral_reason,
        positions=positions,
        cash=cash,
        nav=cash + sum(shares * marks[t] for t, shares in positions.items()),
        original_assessment=original.model_copy(deep=True),
        refreshed_assessment=effective.model_copy(deep=True),
        execution_as_of=session,
        execution_policy=execution_policy(session),
    )


def mark_lookback_start(as_of: str) -> str:
    """The first date a mark for *as_of* may come from: a week back, enough
    to cover weekends, holiday clusters and short halts without reaching into
    stale history. The backtest warm fetches exactly this window."""
    return (_date.fromisoformat(as_of) - timedelta(days=_MARK_LOOKBACK_DAYS)).isoformat()


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _shrinks(order: Order, held: dict[str, Position]) -> bool:
    """Does *order* move its position closer to flat?"""
    current = held[order.ticker].shares if order.ticker in held else 0
    delta = order.quantity if order.side == "buy" else -order.quantity
    return abs(current + delta) < abs(current)


def _mark_prices(
    tickers: list[str],
    as_of: str,
    data_client: DataClient,
) -> tuple[dict[str, float], list[TickerSkip]]:
    """Analytical lookback marks; names without data are excluded from assessment."""
    start = mark_lookback_start(as_of)
    marks: dict[str, float] = {}
    skipped: list[TickerSkip] = []

    for ticker in tickers:
        prices = data_client.get_prices(ticker, start, as_of)
        bars = [p for p in prices if start <= p.time[:10] <= as_of]
        if bars:
            marks[ticker] = max(bars, key=lambda p: p.time).close
            if not isfinite(marks[ticker]) or marks[ticker] <= 0:
                raise ValueError(f"{ticker}: analytical close on {as_of} must be finite and positive")
        else:
            skipped.append(
                TickerSkip(
                    ticker=ticker,
                    reason=f"no close within {_MARK_LOOKBACK_DAYS} days of {as_of}",
                )
            )

    return marks, skipped
