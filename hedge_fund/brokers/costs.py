"""Trading costs — what a fill costs beyond the price on the tape.

A real shop splits the cost of a trade into three parts: the commission
per share, half the bid-ask spread paid on every side, and market impact
that grows with order size against the name's daily volume. This model
carries the first two. Impact needs average daily volume at every session
and is a later addition.

The commission is whatever the broker charges: a per-share rate, a
percentage of the order's notional value, or both — with an optional
per-order minimum, which is how percentage-commission shops (Saxo) price
small orders. Defaults are a liquid US large/mid cap traded by a small
fund: 5 bps of half-spread per side and $0.005 a share (Interactive
Brokers' fixed rate), no minimum. Zero on all of it means free fills.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class TradingCosts(BaseModel):
    """The cost model a mandate names in its `costs:` block."""

    model_config = ConfigDict(extra="forbid")

    spread_bps: float = Field(
        default=5.0, ge=0, description="half the bid-ask spread, in basis points, paid on every side"
    )
    commission_per_share: float = Field(
        default=0.005, ge=0, description="broker commission per share, in dollars"
    )
    commission_bps: float = Field(
        default=0.0,
        ge=0,
        description="broker commission as a share of the order's notional value, in basis points, paid on every side",
    )
    min_commission_per_order: float = Field(
        default=0.0, ge=0, description="smallest commission charged per order, in dollars"
    )

    def fill_price(self, side: Literal["buy", "sell"], mark: float) -> float:
        """A buy pays the half-spread above *mark*; a sell receives it below.
        A short is a sell and a cover is a buy, so the same two lines hold."""
        spread = mark * self.spread_bps / 10_000
        return mark + spread if side == "buy" else mark - spread

    def commission(self, quantity: float, price: float) -> float:
        """What one order costs in commission: the per-share and notional
        rates on the shares traded, but never less than the per-order
        minimum — a percentage shop charges it on every small order."""
        shares = abs(quantity)
        fee = shares * self.commission_per_share + shares * price * self.commission_bps / 10_000
        return max(fee, self.min_commission_per_order)
