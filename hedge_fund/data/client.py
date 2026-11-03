"""Financial Datasets API client."""

from __future__ import annotations

from math import isfinite
from urllib.parse import urlsplit

import httpx

from hedge_fund.data.models import (
    CompanyFacts,
    CompanyNews,
    Earnings,
    EarningsRecord,
    FinancialMetrics,
    InsiderTrade,
    Price,
    PriceSnapshot,
)
from hedge_fund.data.protocol import DataClientError
from hedge_fund.runtime.dispatch import blocked_httpx_client, ProviderDispatch
from hedge_fund.runtime.policy import AuthorizationDenied, ProviderTarget

NEWS_PAGE = 10  # the most /news/ returns per request


class FDClientError(DataClientError):
    """An API request failed for infrastructure reasons (auth, rate limit,
    server error, network). Distinct from "no data exists" — that returns
    empty. A backtest must crash on this, not treat it as no-data.
    """

    def __init__(self, message: str, *, status_code: int | None = None, path: str | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.path = path


class FDClient:
    """Financial Datasets API client.

    Usage::

        with FDClient(
            api_key=captured_credential,
            dispatch=operation_dispatch,
        ) as fd:
            prices = fd.get_prices("AAPL", "2024-01-01", "2024-12-31")

    Direct construction without dispatch has no I/O authority.
    """

    BASE_URL = "https://api.financialdatasets.ai"

    def __init__(
        self,
        api_key: str | None = None,
        timeout: float = 30.0,
        *,
        dispatch: ProviderDispatch | None = None,
        inner_transport: httpx.BaseTransport | None = None,
    ) -> None:
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not isfinite(timeout) or timeout <= 0:
            raise ValueError("timeout must be a positive finite number")
        if dispatch is not None and not isinstance(dispatch, ProviderDispatch):
            raise ValueError("provider dispatch is invalid")
        if inner_transport is not None and not isinstance(inner_transport, httpx.BaseTransport):
            raise ValueError("inner HTTP transport is invalid")
        target = ProviderTarget(kind="data", provider="fd")
        self._api_key = api_key if api_key is not None else ""
        if not isinstance(self._api_key, str) or any(ord(char) < 32 or ord(char) == 127 for char in self._api_key):
            raise ValueError("Financial Datasets credential is invalid")
        if dispatch is not None and not self._api_key.strip():
            raise AuthorizationDenied("captured Financial Datasets credential is required")
        self._timeout = timeout
        if dispatch is None:
            self._session = blocked_httpx_client(timeout=timeout)
        else:
            self._session = dispatch.httpx_client(
                target,
                timeout=timeout,
                inner_transport=inner_transport,
            )
        self._session.headers["X-API-Key"] = self._api_key

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------

    def __enter__(self) -> FDClient:
        return self

    def __exit__(self, *args) -> None:
        self.close()

    def close(self) -> None:
        """Close the HTTP session."""
        self._session.close()

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
        """Fetch OHLC price bars."""
        data = self._get("/prices/", {
            "ticker": ticker,
            "interval": interval,
            "interval_multiplier": interval_multiplier,
            "start_date": start_date,
            "end_date": end_date,
        }, response_key="prices")
        return [Price(**row) for row in data] if data else []

    def get_snapshot(self, ticker: str) -> PriceSnapshot | None:
        """Fetch the real-time quote. None if the ticker is unknown."""
        resp = self._request("GET", "/prices/snapshot/", params={"ticker": ticker})
        if resp is None:
            return None
        row = resp.json().get("snapshot")
        return PriceSnapshot(**row) if row else None

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
        """Fetch financial metrics that were PUBLIC as of *end_date*.

        Point-in-time: filters on ``filing_date`` (when the SEC filing was
        accepted, ET) — not ``report_period`` (the fiscal period end, which
        precedes public availability by 3-6 weeks and would leak the future
        into a backtest). Rows without a known filing_date are excluded
        server-side, so everything returned was provably knowable on
        *end_date*.
        """
        data = self._get("/financial-metrics/", {
            "ticker": ticker,
            "filing_date_lte": end_date,
            "period": period,
            "limit": limit,
        }, response_key="financial_metrics")
        return [FinancialMetrics(**row) for row in data] if data else []

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
        """Fetch company news: the newest items first, at most *limit*.
        /news/ serves no more than NEWS_PAGE per request and rejects a
        larger ask, so the request is clamped to what it can answer."""
        params: dict = {"ticker": ticker, "end_date": end_date, "limit": min(limit, NEWS_PAGE)}
        if start_date is not None:
            params["start_date"] = start_date
        data = self._get("/news/", params, response_key="news")
        return [CompanyNews(**row) for row in data] if data else []

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
        """Fetch insider trades."""
        params: dict = {"ticker": ticker, "filing_date_lte": end_date, "limit": limit}
        if start_date is not None:
            params["filing_date_gte"] = start_date
        data = self._get("/insider-trades/", params, response_key="insider_trades")
        return [InsiderTrade(**row) for row in data] if data else []

    # ------------------------------------------------------------------
    # Company Facts
    # ------------------------------------------------------------------

    def get_company_facts(self, ticker: str) -> CompanyFacts | None:
        """Fetch company metadata (single record)."""
        resp = self._request("GET", "/company/facts/", params={"ticker": ticker})
        if resp is None:
            return None
        facts_data = resp.json().get("company_facts")
        return CompanyFacts(**facts_data) if facts_data else None

    # ------------------------------------------------------------------
    # Earnings
    # ------------------------------------------------------------------

    def get_earnings(self, ticker: str) -> Earnings | None:
        """Fetch latest earnings for a single ticker.

        limit=1 (one report period) — only [0] is used, and without a limit
        the pagination loop in _get would walk the ticker's entire feed.
        """
        data = self._get("/earnings/", {"ticker": ticker, "limit": 1}, response_key="earnings")
        if not data:
            return None
        row = data[0] if isinstance(data, list) else data
        return Earnings(**row)

    def get_earnings_history(
        self,
        ticker: str,
        limit: int = 12,
    ) -> list[EarningsRecord]:
        """Fetch historical earnings filings as a flat list.

        Returns one record per SEC filing (8-K, 10-Q, 10-K, 20-F).
        The same ``report_period`` may appear multiple times with
        different ``source_type`` values.
        """
        data = self._get("/earnings/", {
            "ticker": ticker,
            "limit": limit,
        }, response_key="earnings")
        return [EarningsRecord(**row) for row in data] if data else []

    # ------------------------------------------------------------------
    # Convenience
    # ------------------------------------------------------------------

    def get_market_cap(self, ticker: str, end_date: str) -> float | None:
        """Return market cap from company facts or financial metrics."""
        facts = self.get_company_facts(ticker)
        if facts is not None and facts.market_cap is not None:
            return facts.market_cap
        metrics = self.get_financial_metrics(ticker, end_date, limit=1)
        if metrics and metrics[0].market_cap is not None:
            return metrics[0].market_cap
        return None

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _get(
        self,
        path: str,
        params: dict,
        response_key: str,
    ) -> list[dict] | None:
        """GET and extract *response_key*, following pagination to the end.

        The API caps every list response at a fixed page size and links the
        remainder via ``next_page_url`` (absolute, self-contained — request
        it verbatim, no params). This loop reassembles the full result the
        caller asked for, so everything above it — including the disk cache,
        which memoizes the *merged* list — never sees a truncated page.

        A mid-walk 404 ends the stream and keeps the rows accumulated so
        far; any other failure raises via _request's fail-loud contract.
        """
        resp = self._request("GET", path, params=params)
        if resp is None:
            return None
        body = resp.json()
        rows = body.get(response_key)
        next_page_url = body.get("next_page_url")
        while next_page_url and isinstance(rows, list):
            resp = self._request("GET", next_page_url)
            if resp is None:
                break
            body = resp.json()
            rows.extend(body.get(response_key) or [])
            next_page_url = body.get("next_page_url")
        return rows

    def _request(
        self,
        method: str,
        path: str,
        **kwargs,
    ) -> httpx.Response | None:
        """One HTTP attempt. Return None only for 404."""
        url = path if path.startswith("http") else self.BASE_URL + path
        try:
            resp = self._session.request(
                method,
                url,
                timeout=self._timeout,
                **kwargs,
            )
        except httpx.RequestError as exc:
            safe_path = _safe_path(path)
            raise FDClientError(
                f"{method} {safe_path} failed ({type(exc).__name__})",
                path=safe_path,
            ) from None

        if resp.status_code == 404:
            return None

        if resp.status_code >= 400:
            safe_path = _safe_path(path)
            body = (resp.text.replace(self._api_key, "[REDACTED]") if self._api_key else resp.text)[:200]
            raise FDClientError(
                f"{method} {safe_path} returned {resp.status_code}: {body}",
                status_code=resp.status_code,
                path=safe_path,
            )

        return resp


def _safe_path(value: str) -> str:
    try:
        parts = urlsplit(value)
    except ValueError:
        return "/"
    return parts.path or "/"
