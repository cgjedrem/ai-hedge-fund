"""v2 data pipeline — data provider protocol, FD client, and response models."""

import os

import httpx

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
from hedge_fund.runtime.dispatch import ProviderDispatch

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


def data_provider(provider: str | None = None) -> str:
    """Configured provider: HEDGE_FUND_DATA_PROVIDER, default yfinance."""
    value = (
        os.environ.get("HEDGE_FUND_DATA_PROVIDER", "yfinance")
        if provider is None
        else provider
    )
    if not isinstance(value, str):
        raise ValueError("data provider must be text")
    if provider is not None and value != value.strip():
        raise ValueError("data provider is invalid")
    normalized = value.strip().lower()
    if normalized in ("fd", "financialdatasets", "financial-datasets"):
        return "fd"
    if normalized in ("yfinance", "yf", "yahoo"):
        return "yfinance"
    source = "HEDGE_FUND_DATA_PROVIDER" if provider is None else "provider"
    raise ValueError(f"unsupported {source}")


def make_data_client(
    provider: str | None = None,
    *,
    dispatch: ProviderDispatch | None = None,
    api_key: str | None = None,
    inner_transport: httpx.BaseTransport | None = None,
) -> DataClient:
    """Construct configured provider.

    yfinance is free and not point-in-time. fd is paid and filing-date filtered.
    Provider I/O requires operation-bound dispatch; no-dispatch clients are inert.
    """
    if dispatch is not None and not isinstance(dispatch, ProviderDispatch):
        raise ValueError("provider dispatch is invalid")
    if inner_transport is not None and not isinstance(inner_transport, httpx.BaseTransport):
        raise ValueError("inner HTTP transport is invalid")
    selected = data_provider(provider)
    if selected == "fd":
        return FDClient(
            api_key=api_key,
            dispatch=dispatch,
            inner_transport=inner_transport,
        )
    if selected == "yfinance":
        if inner_transport is not None:
            raise ValueError("the selected provider does not support an HTTP transport")
        if api_key is not None:
            raise ValueError("the selected data provider does not use a credential")
        return YFinanceClient(dispatch=dispatch)
    raise AssertionError("normalized data provider is unsupported")
