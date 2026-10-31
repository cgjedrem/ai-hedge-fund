"""Fixed defaults and schedule labels outside TUI imports."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime, time, timedelta, tzinfo
from math import isfinite
from numbers import Real

from hedge_fund.data.bars import bars_per_day
from hedge_fund.data.sessions import NEW_YORK
from hedge_fund.fund import format_interval, MIN_INTERVAL_SECONDS, TradingWindow

DEFAULT_RISK: dict[str, float] = {"max_position_pct": 0.25, "max_gross_exposure": 1.0}
DEFAULT_CAPITAL = 100_000.0
BACKTEST_WEEKS = 78
BOARD_REFRESH = 1 / 12
WARM_CHUNK = 10
_FAST_SECONDS = 10
_INTERVAL_ERROR = "Enter the interval in minutes: 1, 5, or 0.5 for every 30 seconds."


def backtest_start_date(end: date) -> date:
    if not isinstance(end, date) or isinstance(end, datetime):
        raise TypeError("end must be a date")
    return end - timedelta(weeks=BACKTEST_WEEKS)


def warm_tasks(universe: Sequence[str], dates: Sequence[str]) -> list[tuple[str, list[str]]]:
    if isinstance(universe, (str, bytes)) or not isinstance(universe, Sequence):
        raise TypeError("universe must be a sequence of ticker strings")
    if isinstance(dates, (str, bytes)) or not isinstance(dates, Sequence):
        raise TypeError("dates must be a sequence of session strings")
    if any(not isinstance(ticker, str) or not ticker for ticker in universe):
        raise ValueError("universe entries must be non-empty strings")
    if any(not isinstance(session, str) or not session for session in dates):
        raise ValueError("date entries must be non-empty strings")
    return [(ticker, list(dates[offset : offset + WARM_CHUNK])) for ticker in universe for offset in range(0, len(dates), WARM_CHUNK)]


def parse_interval(text: str) -> float:
    if not isinstance(text, str):
        raise ValueError(_INTERVAL_ERROR)
    try:
        minutes = float(text.strip())
    except ValueError:
        raise ValueError(_INTERVAL_ERROR) from None
    if not isfinite(minutes) or minutes <= 0:
        raise ValueError(_INTERVAL_ERROR)
    if round(minutes * 60) < MIN_INTERVAL_SECONDS:
        raise ValueError(f"The shortest interval is {MIN_INTERVAL_SECONDS}s: sessions are stamped to the second. " "Enter 0.0167 for every second.")
    return minutes


def interval_line(minutes: float, window: TradingWindow) -> str:
    if not isinstance(window, TradingWindow):
        raise TypeError("a trading window is required")
    seconds = _interval_seconds(minutes)
    return f"every {format_interval(seconds)} · {window.label} · {bars_per_day(seconds, window):,} sessions a day"


def fast_caveat(minutes: float) -> str | None:
    seconds = _interval_seconds(minutes)
    if seconds >= _FAST_SECONDS:
        return None
    return f"Under {_FAST_SECONDS}s a bar may not fit its price requests (about a second per ticker); " "bars the fund cannot reach in time are skipped and logged as gaps."


def window_lines(
    window: TradingWindow,
    minutes: float = 1.0,
    *,
    today: datetime | None = None,
    local_zone: tzinfo | None = None,
) -> list[str]:
    if not isinstance(window, TradingWindow):
        raise TypeError("a trading window is required")
    if today is not None and not isinstance(today, datetime):
        raise TypeError("today must be a datetime")
    if local_zone is not None and not isinstance(local_zone, tzinfo):
        raise TypeError("local_zone must be a timezone")
    lines = [interval_line(minutes, window)]
    today = today if today is not None else datetime.now(NEW_YORK)
    local = local_zone if local_zone is not None else datetime.now().astimezone().tzinfo
    start_ny = datetime.combine(today.date(), time(*map(int, window.start.split(":"))), tzinfo=NEW_YORK)
    end_ny = datetime.combine(today.date(), time(*map(int, window.end.split(":"))), tzinfo=NEW_YORK)
    start_local, end_local = start_ny.astimezone(local), end_ny.astimezone(local)
    if (start_local.hour, start_local.minute) != (start_ny.hour, start_ny.minute) or (end_local.hour, end_local.minute) != (end_ny.hour, end_ny.minute):
        day_shift = (end_local.date() - end_ny.date()).days
        suffix = {1: " (the next day)", -1: " (the day before)"}.get(day_shift, "")
        lines.append(f"that is {start_local:%H:%M}–{end_local:%H:%M} {start_local:%Z} where you are{suffix}")
    return lines


def _interval_seconds(minutes: float) -> int:
    if isinstance(minutes, bool) or not isinstance(minutes, Real) or not isfinite(minutes) or minutes <= 0:
        raise ValueError(_INTERVAL_ERROR)
    seconds = int(round(minutes * 60))
    if seconds < MIN_INTERVAL_SECONDS:
        raise ValueError(f"The shortest interval is {MIN_INTERVAL_SECONDS}s: sessions are stamped to the second. " "Enter 0.0167 for every second.")
    return seconds
