"""Fixed schedule and progress defaults, independent of the terminal app."""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from hedge_fund.data.sessions import NEW_YORK
from hedge_fund.fund import TradingWindow
from hedge_fund.runtime.defaults import backtest_start_date, BACKTEST_WEEKS, BOARD_REFRESH, DEFAULT_CAPITAL, DEFAULT_RISK, fast_caveat, interval_line, parse_interval, WARM_CHUNK, warm_tasks, window_lines


def test_backtest_defaults_preserve_window_and_capital_values():
    assert BACKTEST_WEEKS == 78
    assert DEFAULT_CAPITAL == 100_000.0
    assert DEFAULT_RISK == {"max_position_pct": 0.25, "max_gross_exposure": 1.0}
    assert backtest_start_date(date(2025, 1, 1)) == date(2023, 7, 5)


def test_warm_progress_defaults_keep_order_and_bound_chunks():
    universe = ["AAA", "BBB"]
    dates = [f"2025-01-{day:02d}" for day in range(1, 22)]
    tasks = warm_tasks(universe, dates)

    assert BOARD_REFRESH == pytest.approx(1 / 12)
    assert WARM_CHUNK == 10
    assert tasks == [
        ("AAA", dates[:10]),
        ("AAA", dates[10:20]),
        ("AAA", dates[20:]),
        ("BBB", dates[:10]),
        ("BBB", dates[10:20]),
        ("BBB", dates[20:]),
    ]
    assert sum(len(chunk) for _, chunk in tasks) == len(universe) * len(dates)


def test_minute_schedule_labels_keep_interval_and_timezone_output():
    window = TradingWindow(start="09:30", end="16:00")
    assert interval_line(1, window) == "every 1m · 09:30–16:00 ET · 391 sessions a day"
    assert interval_line(90, window) == "every 1h30m · 09:30–16:00 ET · 6 sessions a day"
    assert parse_interval("0.01") == 0.01
    with pytest.raises(ValueError, match="in minutes"):
        parse_interval("soon")
    with pytest.raises(ValueError, match="1s"):
        parse_interval("0.005")
    assert fast_caveat(0.1)
    assert fast_caveat(1 / 6) is None

    today = datetime(2025, 7, 1, tzinfo=NEW_YORK)
    assert window_lines(window, 1, today=today, local_zone=NEW_YORK) == ["every 1m · 09:30–16:00 ET · 391 sessions a day"]
    assert window_lines(window, 1, today=today, local_zone=ZoneInfo("America/Los_Angeles"))[1] == ("that is 06:30–13:00 PDT where you are")
    assert window_lines(window, 1, today=today, local_zone=ZoneInfo("Asia/Tokyo"))[1] == ("that is 22:30–05:00 JST where you are (the next day)")


def test_default_helpers_validate_boundary_types_and_ranges():
    window = TradingWindow(start="09:30", end="16:00")
    with pytest.raises(TypeError, match="date"):
        backtest_start_date(datetime(2025, 1, 1))
    with pytest.raises(TypeError, match="universe"):
        warm_tasks("AAA", [])
    with pytest.raises(ValueError, match="non-empty"):
        warm_tasks([""], [])
    with pytest.raises(ValueError, match="interval"):
        parse_interval(None)
    with pytest.raises(ValueError, match="interval"):
        interval_line(float("nan"), window)
    with pytest.raises(ValueError, match="interval"):
        fast_caveat(0.001)
    with pytest.raises(TypeError, match="timezone"):
        window_lines(window, local_zone=object())


def test_defaults_import_without_tui_or_textual(owned_test_process):
    process = owned_test_process("import sys; import hedge_fund.runtime.defaults; " "assert not any(name == 'hedge_fund.tui' or name.startswith('hedge_fund.tui.') " "or name == 'textual' or name.startswith('textual.') for name in sys.modules)")
    assert process.wait(timeout=10) == 0
