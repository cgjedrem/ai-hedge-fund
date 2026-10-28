"""Execution — turn target weights into delta orders.

Targets are the complete statement of the desired book: any held name absent
from the targets has an implicit target of zero, so close orders fall out of
the same arithmetic as everything else. Pure function; the broker does the
filling.

Later: Almgren-Chriss optimal execution, market impact, fill probability.
"""

from __future__ import annotations

import math

from hedge_fund.brokers.models import Order, Position


def build_orders(
    target_weights: dict[str, float],
    positions: dict[str, Position],
    marks: dict[str, float],
    equity: float,
) -> list[Order]:
    """Diff the target book against the broker's current book.

    Sizing: target_shares = weight * equity / mark, truncated toward zero at
    4 decimal places — never overshoot the target, so the cost of a buy never
    exceeds its allocation (and a short never grows past its target in
    magnitude); sub-4dp dust stays in cash and is re-evaluated next cycle.
    Orders below the 4dp precision (|quantity| < 0.0001) are not emitted.

    Ordering: all sells first, then buys, alphabetical within each group —
    deterministic, and sells free the cash that buys consume within the
    same cycle.

    A KeyError on marks here means a pipeline bug upstream (execute_decision
    prices every tradeable and held name before calling this) — let it raise.
    """
    sells: list[Order] = []
    buys: list[Order] = []

    for ticker in sorted(set(target_weights) | set(positions)):
        mark = marks[ticker]
        value = target_weights.get(ticker, 0.0) * equity / mark
        target_shares = math.trunc(value * 10**4) / 10**4
        current_shares = positions[ticker].shares if ticker in positions else 0
        # Snap held shares to the 4dp grid too: incremental fills can leave
        # them an ulp off a clean multiple.
        delta = round(target_shares - round(current_shares, 4), 4)
        if delta == 0:
            continue
        order = Order(
            ticker=ticker,
            side="buy" if delta > 0 else "sell",
            quantity=abs(delta),
            price=mark,
        )
        (buys if delta > 0 else sells).append(order)

    return sells + buys
