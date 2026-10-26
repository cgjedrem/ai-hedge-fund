"""YFinanceClient contract tests — mocked yfinance, no network.

Mirrors test_client_contract.py for the FD client: the protocol's
fail-loud semantics, field mapping onto the shared models, and the
HEDGE_FUND_DATA_PROVIDER switch. yfinance is faked by monkeypatching
the module-level ``yf`` in yfinance_client, so these tests run with or
without the optional dependency installed.
"""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pandas as pd
import pytest
import requests

from hedge_fund.data import (
    DataClient,
    DataClientError,
    FDClient,
    data_provider,
    make_data_client,
)
from hedge_fund.data import yfinance_client
from hedge_fund.data.yfinance_client import YFinanceClient


# ---------------------------------------------------------------------------
# A fake yfinance module
# ---------------------------------------------------------------------------

class _YFError(Exception):
    """Base for the fake yfinance exception taxonomy."""


class YFRateLimitError(_YFError):
    pass


class YFDataException(_YFError):
    pass


class YFTickerMissingError(_YFError):
    pass


class YFTzMissingError(_YFError):
    pass


class YFPricesMissingError(_YFError):
    pass


class YFEarningsDateMissing(_YFError):
    pass


class FakeTicker:
    """Stands in for yf.Ticker. Attributes come from **attrs; a value that
    is an exception instance is raised when the attribute is used."""

    def __init__(self, symbol: str, **attrs) -> None:
        self.symbol = symbol
        self._attrs = attrs
        self.history_calls: list[dict] = []

    def __getattr__(self, name: str):
        try:
            value = self._attrs[name]
        except KeyError:
            raise AttributeError(name) from None
        if isinstance(value, Exception):
            raise value
        return value

    def history(self, **kwargs):
        self.history_calls.append(kwargs)
        result = self._attrs.get("history")
        if isinstance(result, Exception):
            raise result
        return result

    def get_news(self, count: int, tab: str):
        result = self._attrs.get("news", [])
        if isinstance(result, Exception):
            raise result
        return result[:count]

    def get_earnings_dates(self, limit: int):
        result = self._attrs.get("earnings_dates")
        if isinstance(result, Exception):
            raise result
        return result


def _install(monkeypatch: pytest.MonkeyPatch, ticker: FakeTicker | None = None) -> SimpleNamespace:
    """Point yfinance_client.yf at a fake module serving *ticker*."""
    fake = SimpleNamespace(
        exceptions=SimpleNamespace(
            YFException=_YFError,
            YFRateLimitError=YFRateLimitError,
            YFDataException=YFDataException,
            YFTickerMissingError=YFTickerMissingError,
            YFTzMissingError=YFTzMissingError,
            YFPricesMissingError=YFPricesMissingError,
            YFEarningsDateMissing=YFEarningsDateMissing,
        ),
        config=SimpleNamespace(debug=SimpleNamespace(hide_exceptions=True)),
        Ticker=lambda symbol: ticker if ticker is not None else FakeTicker(symbol),
    )
    monkeypatch.setattr(yfinance_client, "yf", fake)
    return fake


def _client(monkeypatch: pytest.MonkeyPatch, ticker: FakeTicker | None = None) -> YFinanceClient:
    _install(monkeypatch, ticker)
    return YFinanceClient()


# ---------------------------------------------------------------------------
# Fake data builders
# ---------------------------------------------------------------------------

def _prices_df(rows: list[tuple]) -> pd.DataFrame:
    """rows: (timestamp, open, high, low, close, volume)."""
    return pd.DataFrame(
        {
            "Open": [r[1] for r in rows],
            "High": [r[2] for r in rows],
            "Low": [r[3] for r in rows],
            "Close": [r[4] for r in rows],
            "Volume": [r[5] for r in rows],
        },
        index=pd.DatetimeIndex([pd.Timestamp(r[0]) for r in rows]),
    )


def _frame(columns: list[str], rows: dict[str, list]) -> pd.DataFrame:
    """A statement frame: index = row labels, columns = period ends
    (newest first), as yfinance serves them."""
    return pd.DataFrame(rows, index=pd.DatetimeIndex([pd.Timestamp(c) for c in columns])).T


QUARTERS = ["2025-03-31", "2024-12-31", "2024-09-30", "2024-06-30", "2024-03-31"]


def _quarterly_statements() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    income = _frame(QUARTERS, {
        "Total Revenue": [100.0, 100.0, 100.0, 100.0, 90.0],
        "Gross Profit": [40.0, 40.0, 40.0, 40.0, 36.0],
        "Operating Income": [30.0, 30.0, 30.0, 30.0, 27.0],
        "Net Income": [20.0, 20.0, 20.0, 20.0, 18.0],
        "Diluted EPS": [1.0, 1.0, 1.0, 1.0, 0.9],
        "Basic Average Shares": [10.0, 10.0, 10.0, 10.0, 10.0],
    })
    balance = _frame(QUARTERS, {
        "Stockholders Equity": [200.0] * 5,
        "Total Assets": [400.0] * 5,
        "Total Liabilities Net Minority Interest": [200.0] * 5,
        "Total Debt": [50.0] * 5,
        "Cash And Cash Equivalents": [25.0] * 5,
        "Current Assets": [150.0] * 5,
        "Current Liabilities": [75.0] * 5,
        "Ordinary Shares Number": [10.0] * 5,
    })
    cashflow = _frame(QUARTERS, {
        "Operating Cash Flow": [35.0] * 5,
        "Capital Expenditure": [-5.0] * 5,
        "Investing Cash Flow": [-6.0] * 5,
        "Financing Cash Flow": [-2.0] * 5,
        "Changes In Cash": [27.0] * 5,
    })
    return income, balance, cashflow


def _fundamentals_ticker(symbol: str = "TEST", **overrides) -> FakeTicker:
    income, balance, cashflow = _quarterly_statements()
    attrs = {
        "quarterly_financials": income,
        "quarterly_balance_sheet": balance,
        "quarterly_cashflow": cashflow,
        "financials": income,
        "balance_sheet": balance,
        "cashflow": cashflow,
        "fast_info": SimpleNamespace(last_price=10.0, previous_close=9.0,
                                     market_cap=100.0, currency="USD"),
        "earnings_dates": None,
    }
    attrs.update(overrides)
    return FakeTicker(symbol, **attrs)


def _earnings_dates(rows: list[tuple]) -> pd.DataFrame:
    """rows: (announcement timestamp, eps estimate, reported eps)."""
    return pd.DataFrame(
        {
            "EPS Estimate": [r[1] for r in rows],
            "Reported EPS": [r[2] for r in rows],
            "Surprise(%)": [None] * len(rows),
        },
        index=pd.DatetimeIndex([pd.Timestamp(r[0]) for r in rows]),
    )


# ---------------------------------------------------------------------------
# Construction & protocol conformity
# ---------------------------------------------------------------------------

def test_satisfies_the_data_client_protocol(monkeypatch):
    client = _client(monkeypatch)
    assert isinstance(client, DataClient)


def test_constructor_raises_import_error_without_the_extra(monkeypatch):
    monkeypatch.setattr(yfinance_client, "yf", None)
    with pytest.raises(ImportError, match="poetry install -E yfinance"):
        YFinanceClient()


def test_context_manager_parity_with_fdclient(monkeypatch):
    _install(monkeypatch)
    with YFinanceClient() as client:
        assert isinstance(client, YFinanceClient)
    client.close()  # a no-op that must not raise


def test_constructor_disables_exception_hiding(monkeypatch):
    """yfinance's default logs and returns empty on failure, which the
    protocol forbids — the client must flip it into raising."""
    fake = _install(monkeypatch)
    YFinanceClient()
    assert fake.config.debug.hide_exceptions is False


def test_a_fresh_ticker_per_call(monkeypatch):
    """yfinance memoizes fast_info/news per Ticker; caching handles would
    freeze quotes at their first fetch. Each call must build a new one."""
    built = []

    def factory(symbol):
        built.append(symbol)
        return FakeTicker(symbol, fast_info=SimpleNamespace(last_price=10.0, previous_close=9.0))

    fake = _install(monkeypatch)
    fake.Ticker = factory
    client = YFinanceClient()
    client.get_snapshot("TEST")
    client.get_snapshot("TEST")
    assert built == ["TEST", "TEST"]


# ---------------------------------------------------------------------------
# get_prices
# ---------------------------------------------------------------------------

def test_prices_map_daily_bars_and_widen_the_end_date(monkeypatch):
    ticker = FakeTicker("TEST", history=_prices_df([
        ("2025-01-06", 99.0, 102.0, 98.0, 101.0, 1_000_000),
        ("2025-01-07", 101.0, 103.0, 100.0, 102.0, 1_100_000),
    ]))
    client = _client(monkeypatch, ticker)
    prices = client.get_prices("TEST", "2025-01-06", "2025-01-07")
    assert [p.time for p in prices] == ["2025-01-06", "2025-01-07"]
    assert prices[0].open == 99.0 and prices[0].close == 101.0
    assert prices[0].high == 102.0 and prices[0].low == 98.0
    assert prices[0].volume == 1_000_000
    call = ticker.history_calls[0]
    assert call["start"] == "2025-01-06"
    assert call["end"] == "2025-01-08"  # FD's inclusive end → Yahoo's exclusive
    assert call["interval"] == "1d"
    assert call["auto_adjust"] is False


def test_prices_intraday_bars_keep_the_full_timestamp(monkeypatch):
    ticker = FakeTicker("TEST", history=_prices_df([
        ("2025-01-07 09:30:00-05:00", 100.0, 101.0, 99.0, 100.5, 5000),
    ]))
    client = _client(monkeypatch, ticker)
    prices = client.get_prices("TEST", "2025-01-07", "2025-01-07",
                               interval="minute", interval_multiplier=5)
    assert ticker.history_calls[0]["interval"] == "5m"
    assert prices[0].time.startswith("2025-01-07T09:30:00")


def test_prices_reject_an_interval_yahoo_cannot_serve(monkeypatch):
    client = _client(monkeypatch)
    with pytest.raises(ValueError, match="interval"):
        client.get_prices("TEST", "2025-01-06", "2025-01-07",
                          interval="minute", interval_multiplier=7)


def test_prices_empty_frame_means_no_data(monkeypatch):
    ticker = FakeTicker("TEST", history=_prices_df([]))
    client = _client(monkeypatch, ticker)
    assert client.get_prices("TEST", "2025-01-06", "2025-01-07") == []


def test_prices_skip_rows_without_a_close(monkeypatch):
    ticker = FakeTicker("TEST", history=_prices_df([
        ("2025-01-06", 99.0, 102.0, 98.0, 101.0, 1_000_000),
        ("2025-01-07", float("nan"), float("nan"), float("nan"), float("nan"), 0),
    ]))
    client = _client(monkeypatch, ticker)
    assert [p.time for p in client.get_prices("TEST", "2025-01-06", "2025-01-07")] == ["2025-01-06"]


# ---------------------------------------------------------------------------
# get_snapshot
# ---------------------------------------------------------------------------

def test_snapshot_maps_fast_info(monkeypatch):
    ticker = FakeTicker("TEST", fast_info=SimpleNamespace(last_price=152.0, previous_close=150.0))
    client = _client(monkeypatch, ticker)
    snap = client.get_snapshot("TEST")
    assert snap is not None
    assert snap.ticker == "TEST" and snap.price == 152.0
    assert snap.day_change == pytest.approx(2.0)
    assert snap.day_change_percent == pytest.approx(2.0 / 150.0 * 100)


def test_snapshot_is_none_when_yahoo_has_no_price(monkeypatch):
    ticker = FakeTicker("TEST", fast_info=SimpleNamespace(last_price=None, previous_close=None))
    client = _client(monkeypatch, ticker)
    assert client.get_snapshot("TEST") is None


# ---------------------------------------------------------------------------
# get_financial_metrics
# ---------------------------------------------------------------------------

def test_ttm_metrics_sum_four_quarters(monkeypatch):
    client = _client(monkeypatch, _fundamentals_ticker())
    rows = client.get_financial_metrics("TEST", "2025-04-30", period="ttm", limit=10)
    # Five quarters on file → ttm computable at i=0 and i=1 only; the annual
    # backfill (here the same frames) tops the history up to five periods.
    assert [r.report_period for r in rows] == [
        "2025-03-31", "2024-12-31", "2024-09-30", "2024-06-30", "2024-03-31",
    ]
    latest = rows[0]
    assert latest.period == "ttm"
    assert latest.filing_date is None  # the not-point-in-time marker
    assert latest.gross_margin == pytest.approx(0.4)   # 160 / 400
    assert latest.net_margin == pytest.approx(0.2)     # 80 / 400
    assert latest.earnings_per_share == pytest.approx(4.0)
    assert latest.return_on_equity == pytest.approx(80.0 / 200.0)
    assert latest.current_ratio == pytest.approx(2.0)
    assert latest.debt_to_equity == pytest.approx(0.25)
    assert latest.free_cash_flow_per_share == pytest.approx(12.0)  # (35-5)*4 / 10


def test_ttm_history_backfills_with_annual_periods(monkeypatch):
    """Four quarters on file give one ttm window; annual statements (each a
    trailing-twelve-month flow window) fill the history up to the four
    periods the snapshot gate needs, newest first, without duplicating a
    period the quarterly windows already cover."""
    quarters = QUARTERS[:4]
    income_q = _frame(quarters, {
        "Total Revenue": [100.0, 100.0, 100.0, 100.0],
        "Gross Profit": [40.0, 40.0, 40.0, 40.0],
        "Operating Income": [30.0, 30.0, 30.0, 30.0],
        "Net Income": [20.0, 20.0, 20.0, 20.0],
        "Diluted EPS": [1.0, 1.0, 1.0, 1.0],
        "Basic Average Shares": [10.0, 10.0, 10.0, 10.0],
    })
    balance_q = _frame(quarters, {"Stockholders Equity": [200.0] * 4,
                                  "Total Assets": [400.0] * 4,
                                  "Total Debt": [50.0] * 4,
                                  "Current Assets": [150.0] * 4,
                                  "Current Liabilities": [75.0] * 4,
                                  "Ordinary Shares Number": [10.0] * 4})
    cashflow_q = _frame(quarters, {"Operating Cash Flow": [35.0] * 4,
                                   "Capital Expenditure": [-5.0] * 4})
    years = ["2023-12-31", "2022-12-31", "2021-12-31"]
    income_a = _frame(years, {"Total Revenue": [400.0, 380.0, 350.0],
                              "Net Income": [80.0, 76.0, 70.0],
                              "Diluted EPS": [4.0, 3.8, 3.5],
                              "Basic Average Shares": [10.0, 10.0, 10.0]})
    balance_a = _frame(years, {"Stockholders Equity": [200.0, 190.0, 180.0],
                               "Total Assets": [400.0, 380.0, 360.0],
                               "Total Debt": [50.0, 50.0, 50.0],
                               "Current Assets": [150.0, 140.0, 130.0],
                               "Current Liabilities": [75.0, 70.0, 65.0],
                               "Ordinary Shares Number": [10.0, 10.0, 10.0]})
    cashflow_a = _frame(years, {"Operating Cash Flow": [140.0, 130.0, 120.0],
                                "Capital Expenditure": [-20.0, -18.0, -16.0]})
    ticker = _fundamentals_ticker(
        quarterly_financials=income_q, quarterly_balance_sheet=balance_q,
        quarterly_cashflow=cashflow_q,
        financials=income_a, balance_sheet=balance_a, cashflow=cashflow_a,
    )
    client = _client(monkeypatch, ticker)
    rows = client.get_financial_metrics("TEST", "2025-04-30", period="ttm", limit=10)
    assert [r.report_period for r in rows] == [
        "2025-03-31", "2023-12-31", "2022-12-31", "2021-12-31",
    ]
    assert rows[0].period == "ttm"
    assert all(r.period == "annual" for r in rows[1:])
    # Annual rows grow against the prior fiscal year, so the backfilled
    # history carries growth figures the short quarterly window cannot.
    assert rows[1].revenue_growth == pytest.approx(400.0 / 380.0 - 1)
    assert rows[2].revenue_growth == pytest.approx(380.0 / 350.0 - 1)
    assert rows[3].revenue_growth is None  # no fourth year on file


def test_ttm_backfill_skipped_when_quarterly_history_is_long(monkeypatch):
    """A ticker with enough quarters needs no annual rows — the response
    stays pure quarterly-window ttm."""
    client = _client(monkeypatch, _fundamentals_ticker())
    rows = client.get_financial_metrics("TEST", "2025-04-30", period="ttm", limit=2)
    assert [r.report_period for r in rows] == ["2025-03-31", "2024-12-31"]
    assert all(r.period == "ttm" for r in rows)


def test_metrics_respect_the_end_date_cutoff(monkeypatch):
    client = _client(monkeypatch, _fundamentals_ticker())
    rows = client.get_financial_metrics("TEST", "2025-02-01", period="quarterly")
    assert "2025-03-31" not in [r.report_period for r in rows]
    assert rows[0].report_period == "2024-12-31"


def test_quarterly_metrics_carry_year_ago_growth(monkeypatch):
    client = _client(monkeypatch, _fundamentals_ticker())
    rows = client.get_financial_metrics("TEST", "2025-04-30", period="quarterly")
    latest = rows[0]
    assert latest.report_period == "2025-03-31"
    assert latest.revenue_growth == pytest.approx(100.0 / 90.0 - 1)
    assert latest.earnings_growth == pytest.approx(20.0 / 18.0 - 1)
    # i=1 has no fifth quarter behind it in Yahoo's ~4-5 quarter window.
    assert rows[1].revenue_growth is None


def test_annual_metrics_carry_year_ago_growth(monkeypatch):
    """Annual periods grow against the prior year (one column back), not
    four — Yahoo serves ~4 annual periods, so growth is computable."""
    years = ["2024-12-31", "2023-12-31"]
    income = _frame(years, {"Total Revenue": [110.0, 100.0], "Net Income": [22.0, 20.0]})
    balance = _frame(years, {"Stockholders Equity": [200.0, 200.0]})
    cashflow = _frame(years, {"Operating Cash Flow": [35.0, 30.0]})
    ticker = _fundamentals_ticker(financials=income, balance_sheet=balance, cashflow=cashflow)
    client = _client(monkeypatch, ticker)
    rows = client.get_financial_metrics("TEST", "2025-04-30", period="annual")
    assert rows[0].report_period == "2024-12-31"
    assert rows[0].revenue_growth == pytest.approx(0.1)
    assert rows[0].earnings_growth == pytest.approx(0.1)
    assert rows[1].revenue_growth is None  # no third year on file


def test_metrics_tolerate_mismatched_statement_columns(monkeypatch):
    """Yahoo sometimes serves the balance sheet with a different period set
    than the income statement; missing columns must yield None, not a
    KeyError escaping the client."""
    income, balance, cashflow = _quarterly_statements()
    balance = balance.drop(columns=[balance.columns[0]])  # newest quarter missing
    ticker = _fundamentals_ticker(quarterly_balance_sheet=balance)
    client = _client(monkeypatch, ticker)
    rows = client.get_financial_metrics("TEST", "2025-04-30", period="quarterly")
    assert rows[0].report_period == "2025-03-31"
    assert rows[0].return_on_equity is None  # balance-sheet fields absent, not raised


def test_metrics_empty_statements_mean_no_data(monkeypatch):
    empty = pd.DataFrame()
    ticker = FakeTicker("TEST", quarterly_financials=empty,
                        quarterly_balance_sheet=empty, quarterly_cashflow=empty)
    client = _client(monkeypatch, ticker)
    assert client.get_financial_metrics("TEST", "2025-04-30") == []


def test_metrics_reject_an_unknown_period(monkeypatch):
    client = _client(monkeypatch, _fundamentals_ticker())
    with pytest.raises(ValueError, match="period"):
        client.get_financial_metrics("TEST", "2025-04-30", period="monthly")


# ---------------------------------------------------------------------------
# get_news
# ---------------------------------------------------------------------------

NESTED_NEWS = {
    "id": "1",
    "content": {
        "title": "Nested headline",
        "provider": {"displayName": "Reuters"},
        "canonicalUrl": {"url": "https://example.com/nested"},
        "pubDate": "2025-01-10T15:00:00Z",
    },
}
FLAT_NEWS = {
    "title": "Flat headline",
    "publisher": "Bloomberg",
    "link": "https://example.com/flat",
    "providerPublishTime": 1736442000,  # 2025-01-09T17:00:00Z
}


def test_news_maps_both_yahoo_shapes(monkeypatch):
    ticker = FakeTicker("TEST", news=[NESTED_NEWS, FLAT_NEWS])
    client = _client(monkeypatch, ticker)
    news = client.get_news("TEST", "2025-01-11")
    assert [n.title for n in news] == ["Nested headline", "Flat headline"]
    nested, flat = news
    assert nested.source == "Reuters" and nested.url == "https://example.com/nested"
    assert nested.date == "2025-01-10T15:00:00Z"
    assert flat.source == "Bloomberg" and flat.url == "https://example.com/flat"
    assert flat.date == "2025-01-09T17:00:00+00:00"


def test_news_filters_to_the_window(monkeypatch):
    old = {"title": "Old", "publisher": "X", "link": "u", "providerPublishTime": 1733504400}
    undated = {"title": "Undated", "publisher": "X", "link": "u"}
    ticker = FakeTicker("TEST", news=[NESTED_NEWS, FLAT_NEWS, old, undated])
    client = _client(monkeypatch, ticker)
    news = client.get_news("TEST", "2025-01-11", start_date="2025-01-09")
    assert [n.title for n in news] == ["Nested headline", "Flat headline"]  # old + undated excluded
    news = client.get_news("TEST", "2025-01-09")
    assert [n.title for n in news] == ["Flat headline", "Old", "Undated"]  # nested after end


def test_news_empty_means_no_news(monkeypatch):
    client = _client(monkeypatch, FakeTicker("TEST", news=[]))
    assert client.get_news("TEST", "2025-01-11") == []


# ---------------------------------------------------------------------------
# get_insider_trades
# ---------------------------------------------------------------------------

def _insider_df() -> pd.DataFrame:
    return pd.DataFrame({
        "Start Date": [pd.Timestamp("2025-01-15"), pd.Timestamp("2024-06-01")],
        "Insider": ["Jane Doe", "John Smith"],
        "Position": ["CEO", "Director"],
        "Transaction": ["Sale", "Purchase"],
        "Text": ["Sale at price 150.00 per share", "Purchase at price 100.00 per share"],
        "Shares": [1000.0, 500.0],
        "Value": [150000.0, 50000.0],
        "Ownership": ["D", "D"],
    })


def test_insider_trades_map_and_filter(monkeypatch):
    client = _client(monkeypatch, FakeTicker("TEST", insider_transactions=_insider_df()))
    trades = client.get_insider_trades("TEST", "2025-02-01", start_date="2025-01-01")
    assert len(trades) == 1
    trade = trades[0]
    assert trade.name == "Jane Doe" and trade.title == "CEO"
    assert trade.filing_date == "2025-01-15"  # transaction date, documented approximation
    assert trade.transaction_date == "2025-01-15"
    assert trade.transaction_shares == 1000.0
    assert trade.transaction_price_per_share == pytest.approx(150.0)
    assert trade.is_board_director is False


def test_insider_trades_flag_directors(monkeypatch):
    client = _client(monkeypatch, FakeTicker("TEST", insider_transactions=_insider_df()))
    trades = client.get_insider_trades("TEST", "2025-02-01")
    assert trades[1].is_board_director is True


def test_insider_trades_empty_frame_means_no_data(monkeypatch):
    client = _client(monkeypatch, FakeTicker("TEST", insider_transactions=pd.DataFrame()))
    assert client.get_insider_trades("TEST", "2025-02-01") == []


def test_insider_trades_nan_fields_become_none_not_the_string_nan(monkeypatch):
    df = pd.DataFrame({
        "Start Date": [pd.Timestamp("2025-01-15")],
        "Insider": [float("nan")],
        "Position": [float("nan")],
        "Transaction": [float("nan")],
        "Text": [float("nan")],
        "Shares": [1000.0],
        "Value": [150000.0],
    })
    client = _client(monkeypatch, FakeTicker("TEST", insider_transactions=df))
    (trade,) = client.get_insider_trades("TEST", "2025-02-01")
    assert trade.name == "unknown"
    assert trade.title is None
    assert trade.transaction_type is None
    assert trade.is_board_director is False


# ---------------------------------------------------------------------------
# get_company_facts / get_market_cap
# ---------------------------------------------------------------------------

def test_company_facts_map_info(monkeypatch):
    info = {
        "longName": "Test Corp", "sector": "Technology", "industry": "Software",
        "fullExchangeName": "NasdaqGS", "city": "Cupertino", "country": "United States",
    }
    client = _client(monkeypatch, FakeTicker("TEST", info=info))
    facts = client.get_company_facts("TEST")
    assert facts is not None
    assert facts.name == "Test Corp" and facts.sector == "Technology"
    assert facts.exchange == "NasdaqGS" and facts.location == "Cupertino, United States"
    assert facts.is_active is True


def test_company_facts_none_for_an_unknown_ticker(monkeypatch):
    client = _client(monkeypatch, FakeTicker("TEST", info={}))
    assert client.get_company_facts("TEST") is None


def test_market_cap_comes_from_fast_info(monkeypatch):
    ticker = FakeTicker("TEST", fast_info=SimpleNamespace(market_cap=3_000_000_000_000.0))
    client = _client(monkeypatch, ticker)
    assert client.get_market_cap("TEST", "2025-01-01") == 3_000_000_000_000.0


def test_market_cap_none_when_unknown(monkeypatch):
    ticker = FakeTicker("TEST", fast_info=SimpleNamespace(market_cap=None))
    client = _client(monkeypatch, ticker)
    assert client.get_market_cap("TEST", "2025-01-01") is None


# ---------------------------------------------------------------------------
# get_earnings / get_earnings_history
# ---------------------------------------------------------------------------

def test_earnings_returns_latest_quarter_and_year(monkeypatch):
    client = _client(monkeypatch, _fundamentals_ticker())
    earnings = client.get_earnings("TEST")
    assert earnings is not None
    assert earnings.report_period == "2025-03-31"
    assert earnings.currency == "USD"
    assert earnings.quarterly is not None and earnings.quarterly.revenue == 100.0
    assert earnings.quarterly.net_income == 20.0
    assert earnings.quarterly.free_cash_flow == pytest.approx(30.0)  # 35 ocf + (-5) capex
    assert earnings.quarterly.shareholders_equity == 200.0
    assert earnings.annual is not None and earnings.annual.revenue == 100.0


def test_earnings_none_without_statements(monkeypatch):
    empty = pd.DataFrame()
    ticker = FakeTicker("TEST", quarterly_financials=empty,
                        quarterly_balance_sheet=empty, quarterly_cashflow=empty)
    client = _client(monkeypatch, ticker)
    assert client.get_earnings("TEST") is None


def test_earnings_history_matches_announcements_to_quarters(monkeypatch):
    events = _earnings_dates([
        ("2025-04-24 16:00", 0.95, 1.0),   # Q1 2025 (ended 2025-03-31): BEAT
        ("2025-01-23 16:00", 1.05, 1.0),   # Q4 2024 (ended 2024-12-31): MISS
    ])
    client = _client(monkeypatch, _fundamentals_ticker(earnings_dates=events))
    history = client.get_earnings_history("TEST", limit=5)
    assert [r.report_period for r in history] == QUARTERS
    q1, q4 = history[0], history[1]
    # Matched to an announcement → the 8-K the market reacted to.
    assert q1.source_type == "8-K"
    assert q1.filing_date == "2025-04-24"
    assert q1.quarterly.eps_surprise == "BEAT"
    assert q1.quarterly.estimated_earnings_per_share == 0.95
    assert q4.source_type == "8-K"
    assert q4.filing_date == "2025-01-23"
    assert q4.quarterly.eps_surprise == "MISS"
    # No announcement in window → plain 10-Q, no filing date to trade on.
    assert history[2].source_type == "10-Q"
    assert history[2].filing_date is None
    assert history[2].quarterly.eps_surprise is None


def test_earnings_history_ignores_future_announcements(monkeypatch):
    events = _earnings_dates([("2026-04-24 16:00", 1.0, None)])  # not yet reported
    client = _client(monkeypatch, _fundamentals_ticker(earnings_dates=events))
    history = client.get_earnings_history("TEST", limit=2)
    assert all(r.source_type == "10-Q" for r in history)


def test_earnings_history_empty_without_statements(monkeypatch):
    empty = pd.DataFrame()
    ticker = FakeTicker("TEST", quarterly_financials=empty,
                        quarterly_balance_sheet=empty, quarterly_cashflow=empty)
    client = _client(monkeypatch, ticker)
    assert client.get_earnings_history("TEST") == []


# ---------------------------------------------------------------------------
# Failure semantics: raise on infrastructure, empty only on genuine no-data
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("call", [
    lambda c: c.get_prices("TEST", "2025-01-06", "2025-01-07"),
    lambda c: c.get_snapshot("TEST"),
    lambda c: c.get_financial_metrics("TEST", "2025-04-30"),
    lambda c: c.get_news("TEST", "2025-01-11"),
    lambda c: c.get_insider_trades("TEST", "2025-02-01"),
    lambda c: c.get_company_facts("TEST"),
    lambda c: c.get_earnings("TEST"),
    lambda c: c.get_earnings_history("TEST"),
    lambda c: c.get_market_cap("TEST", "2025-01-01"),
])
def test_rate_limit_raises_data_client_error(monkeypatch, call):
    ticker = FakeTicker(
        "TEST",
        history=YFRateLimitError("rate limited"),
        fast_info=YFRateLimitError("rate limited"),
        quarterly_financials=YFRateLimitError("rate limited"),
        quarterly_balance_sheet=YFRateLimitError("rate limited"),
        quarterly_cashflow=YFRateLimitError("rate limited"),
        news=YFRateLimitError("rate limited"),
        insider_transactions=YFRateLimitError("rate limited"),
        info=YFRateLimitError("rate limited"),
        earnings_dates=YFRateLimitError("rate limited"),
    )
    client = _client(monkeypatch, ticker)
    with pytest.raises(DataClientError):
        call(client)


@pytest.mark.parametrize("call", [
    lambda c: c.get_prices("TEST", "2025-01-06", "2025-01-07"),
    lambda c: c.get_snapshot("TEST"),
    lambda c: c.get_news("TEST", "2025-01-11"),
    lambda c: c.get_company_facts("TEST"),
    lambda c: c.get_market_cap("TEST", "2025-01-01"),
])
def test_network_failure_raises_data_client_error(monkeypatch, call):
    boom = requests.ConnectionError("connection reset")
    ticker = FakeTicker("TEST", history=boom, fast_info=boom, news=boom, info=boom)
    client = _client(monkeypatch, ticker)
    with pytest.raises(DataClientError):
        call(client)


def test_yahoo_data_error_raises(monkeypatch):
    ticker = FakeTicker("TEST", history=YFDataException("malformed response"))
    client = _client(monkeypatch, ticker)
    with pytest.raises(DataClientError, match="data error"):
        client.get_prices("TEST", "2025-01-06", "2025-01-07")


@pytest.mark.parametrize("exc", [
    YFTickerMissingError("no ticker"), YFTzMissingError("no tz"),
    YFPricesMissingError("no prices"), YFEarningsDateMissing("no dates"),
])
def test_explicit_no_data_signals_return_empty(monkeypatch, exc):
    ticker = FakeTicker("TEST", history=exc)
    client = _client(monkeypatch, ticker)
    assert client.get_prices("TEST", "2025-01-06", "2025-01-07") == []


def test_unexpected_errors_propagate(monkeypatch):
    ticker = FakeTicker("TEST", history=RuntimeError("a bug, not a failure mode"))
    client = _client(monkeypatch, ticker)
    with pytest.raises(RuntimeError):
        client.get_prices("TEST", "2025-01-06", "2025-01-07")


def _http_error(status: int) -> requests.exceptions.HTTPError:
    exc = requests.exceptions.HTTPError(f"HTTP Error {status}")
    exc.response = SimpleNamespace(status_code=status)
    return exc


def test_http_404_means_no_such_data(monkeypatch):
    """Yahoo answers an unknown ticker (or an ETF's insider roster) with a
    404 — that is genuine no-data, not an infrastructure failure."""
    ticker = FakeTicker("TEST", history=_http_error(404))
    client = _client(monkeypatch, ticker)
    assert client.get_prices("TEST", "2025-01-06", "2025-01-07") == []


def test_http_500_raises_data_client_error(monkeypatch):
    ticker = FakeTicker("TEST", history=_http_error(500))
    client = _client(monkeypatch, ticker)
    with pytest.raises(DataClientError, match="HTTP error"):
        client.get_prices("TEST", "2025-01-06", "2025-01-07")


def test_generic_yfinance_error_raises(monkeypatch):
    ticker = FakeTicker("TEST", history=_YFError("something else entirely"))
    client = _client(monkeypatch, ticker)
    with pytest.raises(DataClientError, match="yfinance error"):
        client.get_prices("TEST", "2025-01-06", "2025-01-07")


def test_empty_result_message_means_no_data(monkeypatch):
    """Some yfinance versions raise YFException('Empty fundamentals-timeseries
    result') for a real ticker with no statements on file."""
    ticker = FakeTicker("TEST", history=_YFError("Empty fundamentals-timeseries result"))
    client = _client(monkeypatch, ticker)
    assert client.get_prices("TEST", "2025-01-06", "2025-01-07") == []


def test_malformed_json_raises_data_client_error(monkeypatch):
    import json as _json
    ticker = FakeTicker("TEST", history=_json.JSONDecodeError("expecting value", "doc", 0))
    client = _client(monkeypatch, ticker)
    with pytest.raises(DataClientError, match="malformed response"):
        client.get_prices("TEST", "2025-01-06", "2025-01-07")


def test_transport_failure_raises_through_the_real_scraper(monkeypatch):
    """End-to-end through real yfinance internals: a broken transport must
    surface as DataClientError, not as a silently empty frame. This is the
    regression test for yfinance's log-and-return-empty default."""
    real_yf = pytest.importorskip("yfinance")
    pytest.importorskip("curl_cffi")
    from curl_cffi.requests.exceptions import RequestException
    import yfinance.data as ydata

    monkeypatch.setattr(yfinance_client, "yf", real_yf)
    client = YFinanceClient()

    def broken_get(self, *args, **kwargs):
        raise RequestException("simulated outage")

    monkeypatch.setattr(ydata.YfData, "get", broken_get)
    with pytest.raises(DataClientError):
        client.get_financial_metrics("AAPL", "2025-04-30")
    with pytest.raises(DataClientError):
        client.get_earnings_history("AAPL")


# ---------------------------------------------------------------------------
# The provider switch
# ---------------------------------------------------------------------------

def test_provider_defaults_to_fd(monkeypatch):
    monkeypatch.delenv("HEDGE_FUND_DATA_PROVIDER", raising=False)
    assert data_provider() == "fd"
    assert isinstance(make_data_client(), FDClient)


def test_provider_switch_selects_yfinance(monkeypatch):
    _install(monkeypatch)
    monkeypatch.setenv("HEDGE_FUND_DATA_PROVIDER", "yfinance")
    assert data_provider() == "yfinance"
    assert isinstance(make_data_client(), YFinanceClient)


def test_provider_switch_rejects_unknown_values(monkeypatch):
    monkeypatch.setenv("HEDGE_FUND_DATA_PROVIDER", "bloomberg")
    with pytest.raises(ValueError, match="HEDGE_FUND_DATA_PROVIDER"):
        make_data_client()


def test_provider_switch_surfaces_a_missing_extra(monkeypatch):
    monkeypatch.setattr(yfinance_client, "yf", None)
    monkeypatch.setenv("HEDGE_FUND_DATA_PROVIDER", "yfinance")
    with pytest.raises(ImportError, match="poetry install -E yfinance"):
        make_data_client()
