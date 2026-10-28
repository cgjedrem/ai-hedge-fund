"""Broker data models — positions, orders, fills.

Two order verbs, not four: positions are signed share counts, so "short" is
just selling past zero and "cover" is buying back toward it. Long/short
labeling is a display concern, not an execution one.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field, PlainSerializer


def as_json_shares(v: float) -> float | int:
    """Serialize a share count as an int when it is whole, so ledgers and
    books written before fractional shares re-verify byte-identically."""
    return int(v) if float(v).is_integer() else v


# Share quantities are floats (fractional shares), but whole values serialize
# as ints in JSON so old integer-share records hash identically.
Shares = Annotated[float, PlainSerializer(as_json_shares, return_type=float | int, when_used="json")]


def format_shares(shares: float, *, signed: bool = False) -> str:
    """Format a share quantity: whole numbers as ints, fractional with 4
    decimals; sub-4dp dust (e.g. 5.5e-17 float residue) renders as zero."""
    if round(shares, 4) == 0:
        return "+0" if signed else "0"
    if float(shares).is_integer():
        return f"{int(shares):+d}" if signed else f"{int(shares):,}"
    return f"{shares:+,.4f}" if signed else f"{shares:,.4f}"


class Position(BaseModel):
    """Signed share count in one ticker. Negative = short."""

    ticker: str
    shares: Shares


class Order(BaseModel):
    """An instruction to trade. `price` is the reference price the caller
    computed (the as-of close): SimBroker fills exactly there, a live broker
    fills at its own quote — the Fill always carries the truth."""

    ticker: str
    side: Literal["buy", "sell"]
    quantity: Shares = Field(gt=0)
    price: float


class Fill(BaseModel):
    """An executed order at its actual fill price."""

    ticker: str
    side: Literal["buy", "sell"]
    quantity: Shares
    price: float
