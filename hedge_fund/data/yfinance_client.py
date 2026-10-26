"""yfinance-backed DataClient — the free data provider.

Selected with ``HEDGE_FUND_DATA_PROVIDER=yfinance`` (see
``hedge_fund.data.make_data_client``). Uses Yahoo Finance via the optional
``yfinance`` package (``poetry install -E yfinance``): no API key, no
credits.

.. warning::

   **Not point-in-time — do not validate backtests with this client.**
   Yahoo serves fundamentals *as reported now*: ``get_financial_metrics``
   filters statement periods by ``end_date``, but a quarter's numbers only
   become public weeks after the period ends, and Yahoo folds restatements
   into history. A backtest on this data leaks the future into the past.
   Use this client for day-to-day paper trading and iteration; run final
   backtest validation against the paid Financial Datasets provider
   (``HEDGE_FUND_DATA_PROVIDER=fd``), which filters on SEC filing dates.

Failure semantics follow the DataClient protocol: rate-limit, network and
server failures RAISE ``DataClientError``; empty is returned only when the
data genuinely doesn't exist. yfinance's own default is to log and return
empty on failure — indistinguishable from "no data" — so the constructor
disables that hiding (``yf.config.debug.hide_exceptions = False``) and
every call goes through :meth:`_guarded`, which maps yfinance's exception
taxonomy onto the protocol contract.
"""

from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta, timezone
from math import isfinite
from typing import Callable, TypeVar

import requests

from hedge_fund.data.models import (
    CompanyFacts,
    CompanyNews,
    Earnings,
    EarningsData,
    EarningsRecord,
    FinancialMetrics,
    InsiderTrade,
    Price,
    PriceSnapshot,
)
from hedge_fund.data.protocol import DataClientError

try:
    import yfinance as yf
except ImportError:  # optional dependency — see pyproject [tool.poetry.extras]
    yf = None

try:  # yfinance 1.x transports over curl_cffi; its errors are not requests'
    from curl_cffi.requests.exceptions import (
        HTTPError as _CurlHTTPError,
        RequestException as _CurlRequestException,
    )
except ImportError:
    _CurlHTTPError = None
    _CurlRequestException = None

logger = logging.getLogger(__name__)

T = TypeVar("T")

_NETWORK_ERRORS: tuple = (requests.RequestException,) + (
    (_CurlRequestException,) if _CurlRequestException is not None else ()
)

# HTTPError subclasses RequestException in both libraries, so _guarded must
# test these first: a 404 is Yahoo's "no such ticker / no such data" (an
# empty answer), while a 429 or 5xx is an infrastructure failure (a raise).
_HTTP_ERRORS: tuple = (requests.exceptions.HTTPError,) + (
    (_CurlHTTPError,) if _CurlHTTPError is not None else ()
)

# Intervals Yahoo serves. Anything else is a caller bug, not a data failure.
_YF_INTERVALS = {
    "1m", "2m", "5m", "15m", "30m", "60m", "90m",
    "1h", "1d", "5d", "1wk", "1mo", "3mo",
}

# An earnings announcement lands at most ~10 weeks after its quarter ends;
# the earliest announcement in that window is the quarter's event.
_ANNOUNCEMENT_WINDOW_DAYS = 75


class YFinanceClient:
    """DataClient over Yahoo Finance. See module docstring for the
    point-in-time warning — this client is NOT safe for rigorous backtest
    validation.

    Usage::

        with YFinanceClient() as yf:
            prices = yf.get_prices("AAPL", "2024-01-01", "2024-12-31")
    """

    def __init__(self, timeout: float = 30.0) -> None:
        if yf is None:
            raise ImportError(
                "HEDGE_FUND_DATA_PROVIDER=yfinance needs the optional "
                "dependency: `poetry install -E yfinance` or `pip install yfinance`"
            )
        self._timeout = timeout
        # yfinance's default is to log exceptions and return empty frames,
        # which the protocol forbids (empty must mean "no data exists").
        # This flips yfinance into raising. The config is process-global —
        # acceptable here because a process runs exactly one data provider.
        config = getattr(yf, "config", None)
        if config is not None:
            config.debug.hide_exceptions = False

    # ------------------------------------------------------------------
    # Context manager (parity with FDClient)
    # ------------------------------------------------------------------

    def __enter__(self) -> YFinanceClient:
        return self

    def __exit__(self, *args) -> None:
        self.close()

    def close(self) -> None:
        """No resources to release — yfinance owns its own HTTP session."""

    # ------------------------------------------------------------------
    # Prices
    # ------------------------------------------------------------------

    def get_prices(
        self,
        ticker: str,
        start_date: str,
        end_date: str,
        interval: str = "day",
        interval_multiplier: int = 1,
    ) -> list[Price]:
        """Fetch OHLC price bars, ascending by time.

        FD's *end_date* is inclusive; Yahoo's ``end`` is exclusive, so the
        request runs through the day after *end_date*. Bars are Yahoo's
        split-adjusted raw OHLC (``auto_adjust=False``), matching FD's
        split-adjusted bars. An empty frame — or yfinance's explicit
        no-such-data error — means genuinely no data and returns [].
        """
        yf_interval = _map_interval(interval, interval_multiplier)
        end_exclusive = (date.fromisoformat(end_date) + timedelta(days=1)).isoformat()
        daily = yf_interval.endswith(("d", "wk", "mo"))

        def fetch():
            return self._ticker(ticker).history(
                start=start_date, end=end_exclusive, interval=yf_interval,
                auto_adjust=False, actions=False, timeout=self._timeout,
            )

        df = self._guarded(f"{ticker} prices", fetch, empty=None)
        if df is None or df.empty:
            return []
        prices = []
        for stamp, row in df.iterrows():
            close = _num(row.get("Close"))
            if close is None:
                continue  # yfinance pads some ranges with all-NaN rows
            stamp_iso = (stamp.date().isoformat() if daily and hasattr(stamp, "date")
                         else _iso(stamp))
            prices.append(Price(
                open=_num(row.get("Open")) or close,
                high=_num(row.get("High")) or close,
                low=_num(row.get("Low")) or close,
                close=close,
                volume=int(_num(row.get("Volume")) or 0),
                time=stamp_iso,
            ))
        return prices

    def get_snapshot(self, ticker: str) -> PriceSnapshot | None:
        """Fetch the latest quote. None when Yahoo has no price for the
        ticker (unknown or inactive). The timestamp is the observation
        time — Yahoo's fast_info carries no trade timestamp of its own."""
        def fetch():
            info = self._ticker(ticker).fast_info
            return _num(info.last_price), _num(info.previous_close)

        price, previous = self._guarded(f"{ticker} snapshot", fetch, empty=(None, None))
        if price is None or price <= 0:
            return None
        change = price - previous if previous else None
        return PriceSnapshot(
            ticker=ticker,
            price=price,
            time=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            day_change=change,
            day_change_percent=(change / previous * 100) if previous else None,
        )

    # ------------------------------------------------------------------
    # Financial Metrics
    # ------------------------------------------------------------------

    def get_financial_metrics(
        self,
        ticker: str,
        end_date: str,
        period: str = "ttm",
        limit: int = 10,
    ) -> list[FinancialMetrics]:
        """Fetch statement-derived metrics for periods ended on or before
        *end_date*, newest first.

        NOT point-in-time: the filter is the fiscal period end, because
        Yahoo exposes no filing dates. A period ended shortly before
        *end_date* was not yet public then — see the module docstring.
        ``filing_date`` is left None on every row as a marker of that.

        *period* is "ttm" (flows summed over the trailing four quarters,
        stocks from the latest), "quarterly", or "annual". Yahoo serves
        only ~4-5 quarters of statements, so few four-quarter windows
        exist; the ttm history is backfilled with annual-statement rows
        (each fiscal year is a trailing-twelve-month flow window) so a
        ticker can still reach the four periods the snapshot gate needs.
        Uncomputable fields stay None rather than being invented.
        """
        if period not in ("ttm", "quarterly", "annual"):
            raise ValueError(f"period must be ttm|quarterly|annual, not {period!r}")
        income, balance, cashflow = self._statements(ticker, annual=(period == "annual"))
        if income is None or income.empty:
            return []
        cutoff = date.fromisoformat(end_date)
        cols = [c for c in income.columns if _col_date(c) is not None and _col_date(c) <= cutoff]
        if period == "ttm":
            rows = [m for m in
                    (self._ttm_metrics(ticker, income, balance, cashflow, cols, i)
                     for i in range(len(cols)))
                    if m is not None]
            if len(rows) < limit:
                rows += self._annual_rows(ticker, cutoff, limit - len(rows),
                                          seen={m.report_period for m in rows})
            rows.sort(key=lambda m: m.report_period, reverse=True)
            return rows[:limit]
        return [self._period_metrics(ticker, income, balance, cashflow, cols, i, period)
                for i in range(min(limit, len(cols)))]

    def _period_metrics(
        self, ticker, income, balance, cashflow, cols, i, period,
    ) -> FinancialMetrics:
        col = cols[i]
        f = self._flows(income, balance, cashflow, col)
        s = self._stocks(balance, col)
        offset = 4 if period == "quarterly" else 1  # a year ago in this period's columns
        year_ago = cols[i + offset] if i + offset < len(cols) else None
        prior = self._flows(income, balance, cashflow, year_ago) if year_ago is not None else {}
        return FinancialMetrics(
            ticker=ticker,
            report_period=_col_date(col).isoformat(),
            period=period,
            filing_date=None,  # unknown from Yahoo — see module docstring
            gross_margin=_div(f.get("gross_profit"), f.get("revenue")),
            operating_margin=_div(f.get("operating_income"), f.get("revenue")),
            net_margin=_div(f.get("net_income"), f.get("revenue")),
            return_on_equity=_div(f.get("net_income"), s.get("equity")),
            return_on_assets=_div(f.get("net_income"), s.get("assets")),
            current_ratio=_div(s.get("current_assets"), s.get("current_liabilities")),
            debt_to_equity=_div(s.get("debt"), s.get("equity")),
            debt_to_assets=_div(s.get("debt"), s.get("assets")),
            revenue_growth=_growth(f.get("revenue"), prior.get("revenue")),
            earnings_growth=_growth(f.get("net_income"), prior.get("net_income")),
            earnings_per_share=f.get("eps"),
            book_value_per_share=_div(s.get("equity"), s.get("shares")),
            free_cash_flow_per_share=_div(f.get("fcf"), s.get("shares")),
        )

    def _ttm_metrics(self, ticker, income, balance, cashflow, cols, i) -> FinancialMetrics | None:
        window = cols[i:i + 4]
        if len(window) < 4:
            return None  # fewer than four quarters on file is not a ttm
        flows = [self._flows(income, balance, cashflow, c) for c in window]
        f = {key: _sum(f.get(key) for f in flows)
             for key in ("revenue", "gross_profit", "operating_income", "net_income", "fcf")}
        eps = _sum(f.get("eps") for f in flows)
        s = self._stocks(balance, window[0])
        return FinancialMetrics(
            ticker=ticker,
            report_period=_col_date(window[0]).isoformat(),
            period="ttm",
            filing_date=None,
            gross_margin=_div(f["gross_profit"], f["revenue"]),
            operating_margin=_div(f["operating_income"], f["revenue"]),
            net_margin=_div(f["net_income"], f["revenue"]),
            return_on_equity=_div(f["net_income"], s.get("equity")),
            return_on_assets=_div(f["net_income"], s.get("assets")),
            current_ratio=_div(s.get("current_assets"), s.get("current_liabilities")),
            debt_to_equity=_div(s.get("debt"), s.get("equity")),
            debt_to_assets=_div(s.get("debt"), s.get("assets")),
            earnings_per_share=eps,
            book_value_per_share=_div(s.get("equity"), s.get("shares")),
            free_cash_flow_per_share=_div(f["fcf"], s.get("shares")),
        )

    def _annual_rows(self, ticker, cutoff, limit, seen) -> list[FinancialMetrics]:
        """Annual-statement rows to backfill a short ttm history: one
        trailing-twelve-month flow window per fiscal year on file, skipping
        periods a quarterly window already covers."""
        if limit <= 0:
            return []
        income, balance, cashflow = self._statements(ticker, annual=True)
        if income is None or income.empty:
            return []
        cols = [c for c in income.columns if _col_date(c) is not None and _col_date(c) <= cutoff]
        rows = [self._period_metrics(ticker, income, balance, cashflow, cols, i, "annual")
                for i in range(len(cols))]
        return [m for m in rows if m.report_period not in seen][:limit]

    # ------------------------------------------------------------------
    # News
    # ------------------------------------------------------------------

    def get_news(
        self,
        ticker: str,
        end_date: str,
        start_date: str | None = None,
        limit: int = 1000,
    ) -> list[CompanyNews]:
        """Fetch company news, newest first. Yahoo serves ~100 recent items
        with no historical window, so the date filters only narrow what
        Yahoo returned — old news is simply absent."""
        items = self._guarded(
            f"{ticker} news",
            lambda: self._ticker(ticker).get_news(count=min(limit, 100), tab="all"),
            empty=[],
        )
        news = []
        for item in items or []:
            mapped = _map_news_item(ticker, item)
            if mapped is None:
                continue
            day = mapped.date[:10] if mapped.date else None
            if day is not None and day > end_date:
                continue
            if start_date is not None and (day is None or day < start_date):
                continue  # undated items can't be proven inside the window
            news.append(mapped)
        news.sort(key=lambda n: n.date or "", reverse=True)
        return news[:limit]

    # ------------------------------------------------------------------
    # Insider Trades
    # ------------------------------------------------------------------

    def get_insider_trades(
        self,
        ticker: str,
        end_date: str,
        start_date: str | None = None,
        limit: int = 1000,
    ) -> list[InsiderTrade]:
        """Fetch insider transactions. Yahoo exposes the *transaction* date,
        not the Form 4 filing date; ``filing_date`` is filled with the
        transaction date as a documented approximation."""
        df = self._guarded(
            f"{ticker} insider trades",
            lambda: self._ticker(ticker).insider_transactions,
            empty=None,
        )
        if df is None or df.empty:
            return []
        trades = []
        for _, row in df.iterrows():
            day = _day(row.get("Start Date"))
            if day is None or day > end_date or (start_date is not None and day < start_date):
                continue
            shares = _num(row.get("Shares"))
            value = _num(row.get("Value"))
            position = _text(row.get("Position"))
            trades.append(InsiderTrade(
                ticker=ticker,
                name=_text(row.get("Insider")) or "unknown",
                filing_date=day,
                transaction_date=day,
                title=position,
                is_board_director=bool(position) and "director" in position.lower(),
                transaction_type=_text(row.get("Text")) or _text(row.get("Transaction")),
                transaction_shares=shares,
                transaction_value=value,
                transaction_price_per_share=_div(value, shares),
            ))
        return trades[:limit]

    # ------------------------------------------------------------------
    # Company Facts
    # ------------------------------------------------------------------

    def get_company_facts(self, ticker: str) -> CompanyFacts | None:
        """Fetch company metadata. None when Yahoo doesn't know the ticker."""
        info = self._guarded(f"{ticker} company facts", lambda: self._ticker(ticker).info, empty=None)
        if not info:
            return None
        location = ", ".join(p for p in (info.get("city"), info.get("country")) if p)
        return CompanyFacts(
            ticker=ticker,
            is_active=True,
            name=info.get("longName") or info.get("shortName"),
            sector=info.get("sector"),
            industry=info.get("industry"),
            exchange=info.get("fullExchangeName") or info.get("exchange"),
            location=location or None,
        )

    # ------------------------------------------------------------------
    # Earnings
    # ------------------------------------------------------------------

    def get_earnings(self, ticker: str) -> Earnings | None:
        """Fetch the latest quarter's (and year's) earnings. None when
        Yahoo has no statements for the ticker."""
        income, balance, cashflow = self._statements(ticker)
        if income is None or income.empty:
            return None
        col = income.columns[0]
        quarterly = self._earnings_data(income, balance, cashflow, col)
        event = _match_event(self._earnings_events(ticker, 12), _col_date(col))
        if event is not None:
            quarterly = quarterly.model_copy(update={
                "estimated_earnings_per_share": event["estimated"],
                "eps_surprise": event["surprise"],
            })
        annual = None
        income_a, balance_a, cashflow_a = self._statements(ticker, annual=True)
        if income_a is not None and not income_a.empty:
            annual = self._earnings_data(income_a, balance_a, cashflow_a, income_a.columns[0])
        currency = self._guarded(
            f"{ticker} currency", lambda: self._ticker(ticker).fast_info.currency, empty=None,
        )
        return Earnings(
            ticker=ticker,
            report_period=_col_date(col).isoformat(),
            currency=currency if isinstance(currency, str) else None,
            quarterly=quarterly,
            annual=annual,
        )

    def get_earnings_history(
        self,
        ticker: str,
        limit: int = 12,
    ) -> list[EarningsRecord]:
        """Fetch one record per quarterly statement period, newest first.

        Yahoo's earnings calendar gives the *announcement* date and EPS
        estimate/actual per quarter; a record matched to an announcement
        is marked source_type "8-K" with the announcement as filing_date
        (the date the surprise became public — what PEAD trades on).
        Unmatched records are "10-Q" with filing_date None, since Yahoo
        exposes no actual SEC filing dates.
        """
        income, balance, cashflow = self._statements(ticker)
        if income is None or income.empty:
            return []
        events = self._earnings_events(ticker, limit)
        records = []
        for col in list(income.columns)[:limit]:
            period_end = _col_date(col)
            if period_end is None:
                continue
            data = self._earnings_data(income, balance, cashflow, col)
            event = _match_event(events, period_end)
            if event is not None:
                data = data.model_copy(update={
                    "estimated_earnings_per_share": event["estimated"],
                    "eps_surprise": event["surprise"],
                })
            records.append(EarningsRecord(
                ticker=ticker,
                report_period=period_end.isoformat(),
                source_type="8-K" if event is not None else "10-Q",
                filing_date=event["day"] if event is not None else None,
                filing_datetime=event["stamp"] if event is not None else None,
                quarterly=data,
            ))
        return records

    # ------------------------------------------------------------------
    # Convenience
    # ------------------------------------------------------------------

    def get_market_cap(self, ticker: str, end_date: str) -> float | None:
        """Return the CURRENT market cap. Yahoo keeps no market-cap history,
        so *end_date* is ignored — another reason this client must not be
        used for backtest validation."""
        return self._guarded(
            f"{ticker} market cap",
            lambda: _num(self._ticker(ticker).fast_info.market_cap),
            empty=None,
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _ticker(self, symbol: str):
        # A fresh Ticker every call: construction does no I/O, and yfinance
        # memoizes fast_info/news/earnings per Ticker — caching handles here
        # would freeze quotes at their first fetch for the client's lifetime.
        return yf.Ticker(symbol)

    def _guarded(self, what: str, fn: Callable[[], T], empty: T) -> T:
        """Run a yfinance call under the protocol's failure semantics.

        With exception-hiding disabled (see __init__), yfinance raises on
        failure; this maps its taxonomy onto the contract. Rate-limit,
        server and network errors RAISE DataClientError; only the explicit
        no-such-ticker/no-such-data signals (the missing-data exceptions,
        an HTTP 404, an "empty result" message) return *empty*. Anything
        else (a caller bug, a yfinance bug) propagates.
        """
        try:
            return fn()
        except yf.exceptions.YFRateLimitError as exc:
            raise DataClientError(f"yfinance rate limited on {what}") from exc
        except yf.exceptions.YFDataException as exc:
            raise DataClientError(f"yfinance data error on {what}: {exc}") from exc
        except (
            yf.exceptions.YFTickerMissingError,
            yf.exceptions.YFTzMissingError,
            yf.exceptions.YFPricesMissingError,
            yf.exceptions.YFEarningsDateMissing,
        ):
            return empty
        except _HTTP_ERRORS as exc:  # before _NETWORK_ERRORS — it subclasses them
            if _http_status(exc) == 404:
                return empty
            raise DataClientError(f"yfinance HTTP error on {what}: {exc}") from exc
        except _NETWORK_ERRORS as exc:
            raise DataClientError(f"yfinance network error on {what}: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise DataClientError(f"yfinance got a malformed response on {what}: {exc}") from exc
        except yf.exceptions.YFException as exc:
            if "empty" in str(exc).lower() or "no data found" in str(exc).lower():
                return empty  # yfinance's explicit no-data-on-file signal
            raise DataClientError(f"yfinance error on {what}: {exc}") from exc

    def _statements(self, ticker: str, annual: bool = False):
        """(income, balance sheet, cash flow) frames, columns = period ends
        (newest first). None/empty income means no data on file."""
        t = self._ticker(ticker)
        if annual:
            return (
                self._guarded(f"{ticker} annual financials", lambda: t.financials, empty=None),
                self._guarded(f"{ticker} annual balance sheet", lambda: t.balance_sheet, empty=None),
                self._guarded(f"{ticker} annual cash flow", lambda: t.cashflow, empty=None),
            )
        return (
            self._guarded(f"{ticker} quarterly financials", lambda: t.quarterly_financials, empty=None),
            self._guarded(f"{ticker} quarterly balance sheet", lambda: t.quarterly_balance_sheet, empty=None),
            self._guarded(f"{ticker} quarterly cash flow", lambda: t.quarterly_cashflow, empty=None),
        )

    def _earnings_events(self, ticker: str, limit: int) -> list[dict]:
        """Yahoo's earnings calendar: announcement date, EPS estimate and
        actual per quarter. Future entries (no actual yet) are dropped."""
        df = self._guarded(
            f"{ticker} earnings dates",
            lambda: self._ticker(ticker).get_earnings_dates(limit=min(max(limit, 12), 100)),
            empty=None,
        )
        if df is None or df.empty:
            return []
        events = []
        for stamp, row in df.iterrows():
            reported = _num(row.get("Reported EPS"))
            if reported is None:
                continue  # a future date, not an event
            estimated = _num(row.get("EPS Estimate"))
            surprise = None
            if estimated is not None:
                surprise = "BEAT" if reported > estimated else "MISS" if reported < estimated else "MEET"
            events.append({
                "when": stamp,
                "day": _day(stamp),
                "stamp": _iso(stamp),
                "estimated": estimated,
                "reported": reported,
                "surprise": surprise,
            })
        return events

    def _earnings_data(self, income, balance, cashflow, col) -> EarningsData:
        f = self._flows(income, balance, cashflow, col)
        s = self._stocks(balance, col)
        return EarningsData(
            revenue=f.get("revenue"),
            earnings_per_share=f.get("eps"),
            net_income=f.get("net_income"),
            gross_profit=f.get("gross_profit"),
            operating_income=f.get("operating_income"),
            weighted_average_shares=_cell(income, ("Basic Average Shares",), col),
            weighted_average_shares_diluted=_cell(income, ("Diluted Average Shares",), col),
            free_cash_flow=f.get("fcf"),
            cash_and_equivalents=s.get("cash"),
            total_debt=s.get("debt"),
            total_assets=s.get("assets"),
            total_liabilities=s.get("liabilities"),
            shareholders_equity=s.get("equity"),
            net_cash_flow_from_operations=f.get("ocf"),
            capital_expenditure=f.get("capex"),
            net_cash_flow_from_investing=_cell(cashflow, ("Investing Cash Flow", "Cash Flow From Continuing Investing Activities"), col),
            net_cash_flow_from_financing=_cell(cashflow, ("Financing Cash Flow", "Cash Flow From Continuing Financing Activities"), col),
            change_in_cash_and_equivalents=_cell(cashflow, ("Changes In Cash", "Change In Cash Supplemental As Reported"), col),
        )

    @staticmethod
    def _flows(income, balance, cashflow, col) -> dict:
        """Flow (per-period) figures for one statement column."""
        if col is None:
            return {}
        ocf = _cell(cashflow, ("Operating Cash Flow", "Cash Flow From Continuing Operating Activities"), col)
        capex = _cell(cashflow, ("Capital Expenditure", "Capital Expenditures"), col)
        fcf = _cell(cashflow, ("Free Cash Flow",), col)
        if fcf is None and ocf is not None and capex is not None:
            fcf = ocf + capex  # capex is negative in Yahoo's presentation
        return {
            "revenue": _cell(income, ("Total Revenue", "Operating Revenue"), col),
            "gross_profit": _cell(income, ("Gross Profit",), col),
            "operating_income": _cell(income, ("Operating Income", "EBIT"), col),
            "net_income": _cell(income, ("Net Income", "Net Income Common Stockholders"), col),
            "eps": _cell(income, ("Diluted EPS", "Basic EPS"), col),
            "ocf": ocf,
            "capex": capex,
            "fcf": fcf,
        }

    @staticmethod
    def _stocks(balance, col) -> dict:
        """Stock (point-in-time) figures for one balance-sheet column."""
        if balance is None or balance.empty or col is None:
            return {}
        return {
            "equity": _cell(balance, ("Stockholders Equity", "Total Equity Gross Minority Interest"), col),
            "assets": _cell(balance, ("Total Assets",), col),
            "liabilities": _cell(balance, ("Total Liabilities Net Minority Interest", "Total Liabilities"), col),
            "debt": _cell(balance, ("Total Debt",), col),
            "cash": _cell(balance, ("Cash And Cash Equivalents", "Cash Cash Equivalents And Short Term Investments"), col),
            "current_assets": _cell(balance, ("Current Assets", "Total Current Assets"), col),
            "current_liabilities": _cell(balance, ("Current Liabilities", "Total Current Liabilities"), col),
            "shares": _cell(balance, ("Ordinary Shares Number", "Share Issued"), col),
        }


# ---------------------------------------------------------------------------
# Module-level mapping helpers (duck-typed — no pandas import, so this module
# loads fine when yfinance is not installed)
# ---------------------------------------------------------------------------

def _map_interval(interval: str, multiplier: int) -> str:
    if multiplier < 1:
        raise ValueError(f"interval_multiplier must be >= 1, not {multiplier}")
    suffix = {"day": "d", "minute": "m", "hour": "h", "week": "wk", "month": "mo"}.get(interval)
    if suffix is None:
        raise ValueError(f"unsupported interval {interval!r}")
    candidate = f"{multiplier}{suffix}"
    if candidate not in _YF_INTERVALS:
        raise ValueError(f"yfinance has no {candidate!r} interval (valid: {sorted(_YF_INTERVALS)})")
    return candidate


def _map_news_item(ticker: str, item: dict) -> CompanyNews | None:
    """Map one Yahoo news article. Tolerates both shapes: the current
    nested one (content.title / content.provider.displayName /
    content.canonicalUrl.url / content.pubDate) and the retired flat one
    (title / publisher / link / providerPublishTime)."""
    if not isinstance(item, dict):
        return None
    content = item.get("content") if isinstance(item.get("content"), dict) else item
    title = content.get("title")
    if not title:
        return None
    provider = content.get("provider")
    if isinstance(provider, dict):
        source = provider.get("displayName")
    else:
        source = content.get("publisher")
    url = content.get("link")
    for key in ("canonicalUrl", "clickThroughUrl"):
        if isinstance(content.get(key), dict) and content[key].get("url"):
            url = content[key]["url"]
            break
    stamp = content.get("pubDate") or content.get("displayTime")
    if stamp is None and content.get("providerPublishTime"):
        stamp = datetime.fromtimestamp(content["providerPublishTime"], tz=timezone.utc).isoformat()
    return CompanyNews(
        ticker=ticker,
        title=str(title),
        source=str(source) if source else "unknown",
        date=_iso(stamp) if stamp is not None else None,
        url=url,
    )


def _match_event(events: list[dict], period_end: date | None) -> dict | None:
    """The earliest announcement inside a quarter's announcement window —
    that is the event at which the quarter's surprise became public."""
    if period_end is None:
        return None
    candidates = [
        e for e in events
        if e["day"] is not None
        and period_end < date.fromisoformat(e["day"]) <= period_end + timedelta(days=_ANNOUNCEMENT_WINDOW_DAYS)
    ]
    return min(candidates, key=lambda e: e["day"], default=None)


def _cell(df, names: tuple[str, ...], col) -> float | None:
    """First matching row label's value in *col*, as a finite float."""
    if df is None or df.empty or col is None or col not in df.columns:
        return None  # Yahoo sometimes serves the three statements with different period sets
    for name in names:
        if name in df.index:
            return _num(df.loc[name, col])
    return None


def _col_date(col) -> date | None:
    day = _day(col)
    return date.fromisoformat(day) if day is not None else None


def _day(stamp) -> str | None:
    """A timestamp-like value as an ISO date string."""
    if stamp is None:
        return None
    if hasattr(stamp, "date") and callable(stamp.date):
        try:
            return stamp.date().isoformat()
        except (ValueError, AttributeError):
            return None
    text = str(stamp)
    return text[:10] if len(text) >= 10 else None


def _iso(stamp) -> str:
    """A timestamp-like value as an ISO 8601 string."""
    if hasattr(stamp, "isoformat"):
        return stamp.isoformat()
    return str(stamp)


def _num(value) -> float | None:
    if value is None:
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return f if isfinite(f) else None


def _text(value) -> str | None:
    """A string field, or None when Yahoo left it empty. NaN is not equal
    to itself, which catches pandas' missing-string marker without
    importing pandas."""
    if value is None or value != value:
        return None
    text = str(value).strip()
    return text or None


def _http_status(exc: BaseException) -> int | None:
    response = getattr(exc, "response", None)
    return getattr(response, "status_code", None)


def _div(a: float | None, b: float | None) -> float | None:
    if a is None or b is None or b == 0:
        return None
    return a / b


def _growth(now: float | None, then: float | None) -> float | None:
    if now is None or then is None or then <= 0:
        return None
    return now / then - 1


def _sum(values) -> float | None:
    vals = [v for v in values if v is not None]
    return sum(vals) if vals else None
