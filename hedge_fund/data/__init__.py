"""v2 data pipeline — data provider protocol, FD client, and response models."""

import os

from hedge_fund.data.cached import CachedDataClient
from hedge_fund.data.client import FDClient, FDClientError
from hedge_fund.data.models import (
    CompanyFacts,
    CompanyNews,
    Earnings,
    EarningsData,
    EarningsRecord,
    Filing,
    FinancialMetrics,
    InsiderTrade,
    Price,
    PriceSnapshot,
)
from hedge_fund.data.protocol import DataClient, DataClientError
from hedge_fund.data.yfinance_client import YFinanceClient

__all__ = [
    "CachedDataClient",
    "CompanyFacts",
    "CompanyNews",
    "DataClient",
    "DataClientError",
    "data_provider",
    "Earnings",
    "EarningsData",
    "EarningsRecord",
    "FDClient",
    "FDClientError",
    "Filing",
    "FinancialMetrics",
    "InsiderTrade",
    "make_data_client",
    "Price",
    "PriceSnapshot",
    "YFinanceClient",
]


def data_provider() -> str:
    """The configured market-data provider: HEDGE_FUND_DATA_PROVIDER,
    default "fd" (Financial Datasets)."""
    return os.environ.get("HEDGE_FUND_DATA_PROVIDER", "fd").strip().lower()


def make_data_client() -> DataClient:
    """Construct the raw data provider selected by HEDGE_FUND_DATA_PROVIDER.

    "fd" (default) is the paid Financial Datasets client — point-in-time,
    safe for backtest validation. "yfinance" is the free Yahoo Finance
    client — no key or credits, but NOT point-in-time (see
    YFinanceClient's docstring); use it for day-to-day paper trading and
    iteration. Wrap either in CachedDataClient as before.
    """
    provider = data_provider()
    if provider in ("fd", "financialdatasets", "financial-datasets"):
        return FDClient()
    if provider in ("yfinance", "yf", "yahoo"):
        return YFinanceClient()
    raise ValueError(
        f"unknown HEDGE_FUND_DATA_PROVIDER {provider!r}: expected 'fd' or 'yfinance'"
    )
