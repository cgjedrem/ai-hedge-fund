"""Pure helpers for signed, non-authoritative paper valuations."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

from hedge_fund.data.models import PriceSnapshot

MAX_VALUATION_POSITIONS = 25
MAX_OBSERVATION_AGE_SECONDS = 900
_MAX_FUTURE_SECONDS = 60


def estimate_valuation(
    *,
    cash: float,
    positions: Mapping[str, float],
    quotes: Mapping[str, PriceSnapshot | None],
    errors: Mapping[str, str],
    as_of: datetime,
    expected_head: str | None,
    recorded_nav: float | None,
) -> dict[str, object]:
    """Return display-only estimate; incomplete coverage never yields NAV."""
    if not isinstance(positions, Mapping) or len(positions) > MAX_VALUATION_POSITIONS:
        raise ValueError("valuation positions exceed the supported bound")
    if not isinstance(quotes, Mapping) or not isinstance(errors, Mapping):
        raise ValueError("valuation quote collections are invalid")
    if not isinstance(as_of, datetime) or as_of.tzinfo is None:
        raise ValueError("valuation timestamp must be timezone-aware")
    if expected_head is not None and (not isinstance(expected_head, str) or len(expected_head) != 64 or any(char not in "0123456789abcdef" for char in expected_head)):
        raise ValueError("valuation head is invalid")

    cash_value = _decimal(cash, "cash")
    total = cash_value
    valid_total = cash_value
    rows: list[dict[str, object]] = []
    counts = {"quoted": 0, "usable": 0, "missing": 0, "stale": 0, "errors": 0}
    seen: set[str] = set()
    now = as_of.astimezone(timezone.utc)

    for ticker, raw_shares in sorted(positions.items()):
        if not isinstance(ticker, str) or not ticker or len(ticker) > 16 or not ticker.isascii() or ticker != ticker.strip() or ticker != ticker.upper() or ticker in seen:
            raise ValueError("valuation ticker is invalid")
        seen.add(ticker)
        shares = _decimal(raw_shares, "shares")
        row: dict[str, object] = {
            "ticker": ticker,
            "shares": _text(shares),
            "price": None,
            "quote_time": None,
            "observation_age_seconds": None,
            "status": "error",
            "freshness": "unknown",
            "reason": None,
        }
        error = errors.get(ticker)
        quote = quotes.get(ticker)
        if error is not None:
            row["reason"] = _safe_error_code(error)
            counts["errors"] += 1
        elif quote is None:
            row["status"] = "missing"
            row["reason"] = "Provider returned no quote."
            counts["missing"] += 1
        elif not isinstance(quote, PriceSnapshot) or quote.ticker.upper() != ticker:
            row["reason"] = "Quote identity is invalid."
            counts["errors"] += 1
        else:
            try:
                price = _decimal(quote.price, "price")
                if price <= 0:
                    raise ValueError("quote price is invalid")
                observed_at = _parse_time(quote.time)
                age = (now - observed_at.astimezone(timezone.utc)).total_seconds()
                if age < -_MAX_FUTURE_SECONDS:
                    raise ValueError("quote observation is in the future")
            except (InvalidOperation, TypeError, ValueError):
                row["reason"] = "Quote price or observation time is invalid."
                counts["errors"] += 1
            else:
                counts["quoted"] += 1
                row["price"] = _text(price)
                row["quote_time"] = quote.time
                row["observation_age_seconds"] = max(0, int(age))
                if age > MAX_OBSERVATION_AGE_SECONDS:
                    row["status"] = "stale"
                    row["reason"] = "Provider observation exceeds the 15-minute limit."
                    counts["stale"] += 1
                else:
                    row["status"] = "quoted"
                    counts["usable"] += 1
                    valid_total += shares * price
                    total += shares * price
                    row["reason"] = "Observation time is not an exchange print time; freshness is unverified."
        rows.append(row)

    complete = counts["missing"] == 0 and counts["stale"] == 0 and counts["errors"] == 0
    result: dict[str, object] = {
        "status": "estimated" if complete else ("stale" if counts["stale"] else "partial"),
        "value": _text(total) if complete else None,
        "partial_estimate": None if complete else _text(valid_total),
        "as_of": _time_text(now),
        "provenance": "yfinance" if positions else "verified-ledger-cash",
        "expected_head": expected_head,
        "recorded_nav": _text(_decimal(recorded_nav, "recorded NAV")) if recorded_nav is not None else None,
        "coverage": {"total": len(positions), **counts},
        "quotes": rows,
        "reason": ("No open positions; estimate contains verified ledger cash only." if not positions else "Complete symbol coverage; provider print freshness is unverified." if complete else "Coverage is partial or stale; complete estimate withheld."),
    }
    return result


def _decimal(value: object, field: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError(f"{field} is invalid") from None
    if not result.is_finite():
        raise ValueError(f"{field} is invalid")
    return result


def _parse_time(value: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise ValueError("quote observation time is invalid")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("quote observation time must include a timezone")
    return parsed


def _text(value: Decimal) -> str:
    return format(value, "f")


def _time_text(value: datetime) -> str:
    return value.isoformat(timespec="seconds").replace("+00:00", "Z")


def _safe_error_code(value: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 80:
        return "ProviderError"
    if any(not (char.isascii() and (char.isalnum() or char == "_")) for char in value):
        return "ProviderError"
    return f"Provider error ({value})."
