"""Saxo OpenAPI SIM broker adapter."""

from __future__ import annotations

import hashlib
import logging
import math
import os
import re
import socket
import tempfile
import threading
import time
import uuid
from contextlib import AbstractContextManager, contextmanager
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_DOWN
from enum import Enum
from pathlib import Path
from typing import Callable, Iterator, Protocol
from urllib.parse import parse_qs, urlparse

import requests

from hedge_fund.brokers.models import Fill, Order, Position
from hedge_fund.brokers.protocol import OrderSubmissionDeferred
from hedge_fund.secrets.provider import SecretProvider

BASE_URL = "https://gateway.saxobank.com/sim/openapi"
AUTH_URL = "https://sim.logonvalidation.net"
_LOG = logging.getLogger(__name__)
_THREAD_REFRESH_LOCKS: dict[str, threading.Lock] = {}
_THREAD_REFRESH_LOCKS_GUARD = threading.Lock()
_US_EXCHANGES = ("NASDAQ", "NYSE", "NYSEARCA", "NYSEAMERICAN", "BATS", "CBOE")


class Transport(Protocol):
    def request(self, method: str, url: str, **kwargs):
        ...


class SaxoAuthError(RuntimeError):
    """Authentication failed; interactive login may be required."""


class SaxoOrderError(RuntimeError):
    """Saxo rejected an order or execution could not be confirmed."""

    def __init__(self, message: str, error_code: str | None = None):
        super().__init__(message)
        self.error_code = error_code


class SaxoReconcileError(RuntimeError):
    """Saxo book or instrument data cannot be reconciled safely."""


class TokenState(str, Enum):
    UNAUTHENTICATED = "UNAUTHENTICATED"
    AUTHORIZED = "AUTHORIZED"
    REAUTH_REQUIRED = "REAUTH_REQUIRED"


class TokenManager:
    def __init__(
        self,
        *,
        app_key: str,
        app_secret: str,
        refresh_token_ref: str,
        secrets_provider: SecretProvider,
        transport: Transport | None = None,
        clock=None,
        refresh_margin_s: float = 120.0,
        lock_dir: str | Path | None = None,
        lock_timeout_s: float = 90.0,
    ):
        if not isinstance(app_key, str) or not app_key or not isinstance(app_secret, str) or not app_secret or not isinstance(refresh_token_ref, str) or not refresh_token_ref.startswith("op://"):
            raise ValueError("Saxo credentials must include app key, app secret, and an op:// refresh reference")
        if not math.isfinite(refresh_margin_s) or refresh_margin_s < 0:
            raise ValueError("refresh margin cannot be negative")
        if not math.isfinite(lock_timeout_s) or lock_timeout_s <= 0:
            raise ValueError("refresh lock timeout must be positive")
        if lock_dir is not None and (not isinstance(lock_dir, (str, Path)) or not str(lock_dir).strip() or not Path(lock_dir).is_absolute()):
            raise ValueError("refresh lock directory must be an absolute path")
        self.app_key = app_key
        self.app_secret = app_secret
        self.refresh_token_ref = refresh_token_ref
        self.secrets_provider = secrets_provider
        self.transport = transport or RequestsTransport()
        self.clock = clock or SystemClock()
        self.refresh_margin_s = refresh_margin_s
        self.lock_timeout_s = lock_timeout_s
        self.lock_dir = Path(lock_dir) if lock_dir is not None else None
        self.access_token: str | None = None
        self.access_expires_at = 0.0
        self.state = TokenState.UNAUTHENTICATED

    def __repr__(self) -> str:
        return "TokenManager(state={!r}, access_token=[redacted], refresh_token_ref=[redacted])".format(self.state.value)

    def get_access_token(self) -> str:
        if self.state == TokenState.REAUTH_REQUIRED:
            raise SaxoAuthError("Saxo authorization expired; run interactive Saxo login")
        if self.access_token and self.access_expires_at - self.clock.monotonic() >= self.refresh_margin_s:
            return self.access_token
        self._refresh()
        if not self.access_token:
            raise SaxoAuthError("Saxo authorization unavailable; run interactive Saxo login")
        return self.access_token

    def _refresh(self) -> None:
        try:
            with _refresh_lock(self.refresh_token_ref, self.lock_dir, timeout_s=self.lock_timeout_s):
                refresh_token = self.secrets_provider.resolve("SAXO_REFRESH_TOKEN_REF", self.refresh_token_ref)
                response = self.transport.request(
                    "POST",
                    f"{AUTH_URL}/token",
                    auth=(self.app_key, self.app_secret),
                    data={"grant_type": "refresh_token", "refresh_token": refresh_token},
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                    timeout=15,
                )
                status, body = _response(response)
                if status < 200 or status >= 300 or not isinstance(body, dict):
                    raise ValueError("token endpoint rejected refresh")
                access_token = body.get("access_token")
                rotated = body.get("refresh_token")
                expires_in = body.get("expires_in")
                if not isinstance(access_token, str) or not access_token or not isinstance(rotated, str) or not rotated:
                    raise ValueError("token response incomplete")
                lifetime = float(expires_in)
                if lifetime <= 0:
                    raise ValueError("token lifetime invalid")
                self.secrets_provider.write_back("SAXO_REFRESH_TOKEN_REF", self.refresh_token_ref, rotated)
        except _RefreshLockTimeout as exc:
            _LOG.warning("Saxo refresh lock contention; verify owner and retry")
            raise SaxoAuthError(str(exc)) from None
        except Exception:
            self.access_token = None
            self.access_expires_at = 0.0
            self.state = TokenState.REAUTH_REQUIRED
            _LOG.warning("Saxo token refresh failed; interactive login required")
            raise SaxoAuthError("Saxo token refresh failed; run interactive Saxo login") from None
        self.access_token = access_token
        self.access_expires_at = self.clock.monotonic() + lifetime
        self.state = TokenState.AUTHORIZED


class SystemClock:
    def monotonic(self) -> float:
        return time.monotonic()

    def sleep(self, seconds: float) -> None:
        time.sleep(seconds)

    def utcnow(self) -> datetime:
        return datetime.now(timezone.utc)


class RequestsTransport:
    def request(self, method: str, url: str, **kwargs):
        return requests.request(method, url, **kwargs)


class Pacer:
    def __init__(self, *, min_interval_s: dict[str, float] | None = None, clock=None):
        self.min_interval_s = dict(min_interval_s or {"orders": 1.0})
        if any(not key or not math.isfinite(value) or value < 0 for key, value in self.min_interval_s.items()):
            raise ValueError("pacer intervals must be non-negative")
        self.clock = clock or SystemClock()
        self.last_call_at: dict[str, float] = {}

    def wait_for(self, endpoint_class: str) -> None:
        if endpoint_class not in self.min_interval_s:
            return
        now = self.clock.monotonic()
        previous = self.last_call_at.get(endpoint_class)
        interval = self.min_interval_s[endpoint_class]
        if previous is not None and now - previous < interval:
            self.clock.sleep(interval - (now - previous))
        self.last_call_at[endpoint_class] = self.clock.monotonic()


class SaxoClient:
    def __init__(
        self,
        *,
        tokens: TokenManager,
        transport: Transport | None = None,
        pacer: Pacer | None = None,
        base_currency: str = "USD",
        execution_timeout_s: float = 120.0,
        clock=None,
        poll_interval_s: float = 1.0,
    ):
        if not isinstance(base_currency, str) or not base_currency or not math.isfinite(execution_timeout_s) or execution_timeout_s <= 0 or not math.isfinite(poll_interval_s) or poll_interval_s <= 0:
            raise ValueError("currency and positive order polling bounds are required")
        self.tokens = tokens
        self.transport = transport or tokens.transport
        self.pacer = pacer or Pacer(clock=clock)
        self.clock = clock or SystemClock()
        self.base_currency = base_currency.upper()
        self.execution_timeout_s = execution_timeout_s
        self.poll_interval_s = poll_interval_s
        self.client_key: str | None = None
        self.account_key: str | None = None
        self._ticker_uic: dict[str, int] = {}
        self._order_submission_cutoff: tuple[datetime, Callable[[], datetime]] | None = None

    @contextmanager
    def order_submission_window(self, cutoff: datetime, *, now: Callable[[], datetime]) -> Iterator[None]:
        if cutoff.tzinfo is None or cutoff.utcoffset() is None:
            raise ValueError("Saxo order cutoff must be timezone-aware")
        previous = self._order_submission_cutoff
        self._order_submission_cutoff = (cutoff, now)
        try:
            yield
        finally:
            self._order_submission_cutoff = previous

    def _prepare_order_post(self, headers: dict[str, str]) -> None:
        self.pacer.wait_for("orders")
        headers["x-request-id"] = str(uuid.uuid4())
        if self._order_submission_cutoff is not None:
            cutoff, now = self._order_submission_cutoff
            moment = now()
            if moment.tzinfo is None or moment.utcoffset() is None:
                raise ValueError("Saxo order clock must be timezone-aware")
            if moment >= cutoff:
                raise OrderSubmissionDeferred("market close reached before order submission")

    def request(self, method: str, path: str, *, params=None, json_body=None, order_post=False):
        url = f"{BASE_URL}{path}"
        token = self.tokens.get_access_token()
        headers = {"Authorization": "Bearer " + token}
        if order_post:
            self._prepare_order_post(headers)
        try:
            response = self.transport.request(
                method,
                url,
                headers=headers,
                params=params,
                json=json_body,
                timeout=15,
            )
        except Exception:
            if order_post:
                raise SaxoOrderError("Saxo order POST outcome unknown; inspect SIM account") from None
            raise SaxoAuthError("Saxo SIM request failed") from None
        status, body = _response(response)
        if status == 401:
            self.tokens.access_expires_at = 0
            token = self.tokens.get_access_token()
            headers["Authorization"] = "Bearer " + token
            if order_post:
                self._prepare_order_post(headers)
            try:
                status, body = _response(self.transport.request(method, url, headers=headers, params=params, json=json_body, timeout=15))
            except Exception:
                if order_post:
                    raise SaxoOrderError("Saxo order POST outcome unknown; inspect SIM account") from None
                raise SaxoAuthError("Saxo SIM request failed after token refresh") from None
            if status == 401:
                raise SaxoAuthError("Saxo rejected refreshed authorization; run interactive Saxo login")
        return status, body

    def discover_account(self) -> None:
        status, user = self.request("GET", "/port/v1/users/me")
        if status != 200 or not isinstance(user, dict) or not user.get("ClientKey"):
            raise SaxoReconcileError("Saxo SIM user discovery failed")
        self.client_key = str(user["ClientKey"])
        status, accounts = self.request("GET", "/port/v1/accounts/me")
        data = accounts.get("Data", []) if isinstance(accounts, dict) else []
        if status != 200 or not isinstance(data, list):
            raise SaxoReconcileError("Saxo SIM account discovery failed")
        compatible = [row for row in data if isinstance(row, dict) and isinstance(row.get("Currency"), str) and row["Currency"].upper() == self.base_currency and row.get("AccountKey") and row.get("Active") is True and isinstance(row.get("LegalAssetTypes"), list) and "Stock" in row["LegalAssetTypes"]]
        if not compatible:
            currencies = sorted({str(row.get("Currency", "")) for row in data if isinstance(row, dict)})
            raise SaxoReconcileError(f"no Saxo trading account matches fund currency {self.base_currency}; available: {', '.join(currencies) or 'none'}")
        self.account_key = str(compatible[0]["AccountKey"])

    def positions(self) -> dict[str, Position]:
        self._require_account()
        totals: dict[str, float] = {}
        skip = 0
        while True:
            params: dict[str, str | int | None] = {"ClientKey": self.client_key, "AccountKey": self.account_key}
            if skip:
                params["$skip"] = skip
            status, result = self.request("GET", "/port/v1/positions", params=params)
            if status != 200:
                raise SaxoReconcileError("cannot read Saxo SIM positions")
            rows = result.get("Data") if isinstance(result, dict) else None
            if not isinstance(rows, list):
                raise SaxoReconcileError("Saxo positions response has an invalid shape")
            for row in rows:
                if not isinstance(row, dict):
                    raise SaxoReconcileError("Saxo position response has an invalid row")
                base = row.get("PositionBase", {})
                if not isinstance(base, dict):
                    raise SaxoReconcileError("Saxo position response has an invalid position")
                ticker = next((name for name, uic in self._ticker_uic.items() if uic == base.get("Uic")), None)
                if ticker is None or not row.get("NetPositionId"):
                    raise SaxoReconcileError("Saxo position cannot be mapped to a fund ticker")
                amount = _finite_number(base.get("Amount"), "position amount", SaxoReconcileError)
                totals[ticker] = totals.get(ticker, 0.0) + amount
            next_skip = _next_page_skip(result.get("__next"), skip, SaxoReconcileError, "positions")
            if next_skip is None:
                break
            skip = next_skip
        return {ticker: Position(ticker=ticker, shares=shares) for ticker, shares in totals.items() if shares != 0}

    def balances(self) -> dict:
        self._require_account()
        status, result = self.request(
            "GET",
            "/port/v1/balances",
            params={"ClientKey": self.client_key, "AccountKey": self.account_key},
        )
        if status != 200 or not isinstance(result, dict):
            raise SaxoReconcileError("cannot read Saxo SIM balances")
        currency = result.get("Currency")
        if not isinstance(currency, str) or currency.upper() != self.base_currency:
            raise SaxoReconcileError(f"Saxo balance currency {currency} does not match fund currency {self.base_currency}")
        _finite_number(result.get("CashBalance"), "accounting cash balance", SaxoReconcileError)
        return result

    def search_instrument(self, ticker: str) -> tuple[int, str]:
        status, result = self.request(
            "GET",
            "/ref/v1/instruments",
            params={"Keywords": ticker, "AssetTypes": "Stock"},
        )
        if status != 200:
            raise SaxoReconcileError(f"Saxo instrument search failed for {ticker}")
        rows = result.get("Data", []) if isinstance(result, dict) else []
        candidates = [row for row in rows if isinstance(row, dict) and str(row.get("Symbol", "")).split(":")[0].upper() == ticker.upper() and row.get("Identifier") is not None and str(row.get("ExchangeId", "")).upper() in _US_EXCHANGES]
        if not candidates:
            raise SaxoReconcileError(f"Saxo instrument not found for {ticker}")
        exchange_order = {exchange: index for index, exchange in enumerate(_US_EXCHANGES)}
        candidates.sort(
            key=lambda row: (
                0 if str(row.get("PrimaryListing", "")) == str(row["Identifier"]) else 1,
                exchange_order[str(row["ExchangeId"]).upper()],
                str(row["Identifier"]),
            )
        )
        try:
            uic = int(candidates[0]["Identifier"])
        except (TypeError, ValueError):
            raise SaxoReconcileError(f"Saxo instrument identifier is invalid for {ticker}") from None
        if uic <= 0:
            raise SaxoReconcileError(f"Saxo instrument identifier is invalid for {ticker}")
        return uic, "Stock"

    def instrument_details(self, uic: int, asset_type: str = "Stock") -> dict:
        status, details = self.request("GET", f"/ref/v1/instruments/details/{int(uic)}/{asset_type}")
        if status != 200 or not isinstance(details, dict):
            raise SaxoReconcileError(f"Saxo instrument details unavailable for UIC {uic}")
        return details

    def place_order(self, payload: dict) -> tuple[str | None, str | None]:
        status, body = self.request("POST", "/trade/v2/orders", json_body=payload, order_post=True)
        code = _error_code(body)
        if code:
            if status == 409:
                order_id = body.get("OrderId") if isinstance(body, dict) else None
                if order_id:
                    return str(order_id), None
                raise SaxoOrderError(f"Saxo order state unknown after conflict ({code}); inspect SIM account", code)
            raise SaxoOrderError(f"Saxo rejected order ({code})", code)
        if status < 200 or status >= 300 or not isinstance(body, dict) or not body.get("OrderId"):
            raise SaxoOrderError("Saxo order response did not confirm an OrderId")
        return str(body["OrderId"]), None

    def wait_for_order(self, order_id: str, *, deadline: float | None = None) -> None:
        self._require_account()
        deadline = deadline if deadline is not None else self.clock.monotonic() + self.execution_timeout_s
        while self.clock.monotonic() < deadline:
            status, body = self.request("GET", f"/port/v1/orders/{self.client_key}/{order_id}")
            if status in (404, 410) or (status == 200 and isinstance(body, dict) and (body.get("IsOpen") is False or body == {} or body.get("Data") == [])):
                return
            self.clock.sleep(min(self.poll_interval_s, max(0.0, deadline - self.clock.monotonic())))
        raise SaxoOrderError(f"Saxo order {order_id} did not complete before deadline; inspect SIM account")

    def order_fill(
        self,
        order_id: str,
        requested_quantity: float,
        *,
        uic: int,
        deadline: float | None = None,
    ) -> tuple[float, float]:
        self._require_account()
        if not isinstance(order_id, str) or not order_id:
            raise SaxoOrderError("Saxo order identifier is invalid")
        if isinstance(requested_quantity, bool) or not isinstance(requested_quantity, (int, float)) or not math.isfinite(requested_quantity) or requested_quantity <= 0:
            raise SaxoOrderError(f"Saxo requested quantity is invalid for order {order_id}")
        if isinstance(uic, bool) or not isinstance(uic, int) or uic <= 0:
            raise SaxoOrderError(f"Saxo instrument identifier is invalid for order {order_id}")
        deadline = deadline if deadline is not None else self.clock.monotonic() + self.execution_timeout_s
        observed_quantity = 0.0
        moment = self.clock.utcnow().date()
        base_params = {
            "AccountKeys": self.account_key,
            "ClientKey": self.client_key,
            "FromDate": (moment - timedelta(days=1)).isoformat(),
            "ToDate": moment.isoformat(),
            "TransactionType": "Trade",
            "Uics": str(uic),
            "$top": 100,
        }
        while self.clock.monotonic() < deadline:
            quantity = 0.0
            notional = 0.0
            skip = 0
            while True:
                if self.clock.monotonic() >= deadline:
                    break
                status, result = self.request(
                    "GET",
                    "/hist/v1/transactions",
                    params={**base_params, "$skip": skip},
                )
                if status != 200:
                    raise SaxoOrderError(f"Saxo execution lookup failed for order {order_id}")
                if not isinstance(result, dict):
                    raise SaxoOrderError(f"Saxo execution response has invalid shape for order {order_id}")
                rows = result.get("Data")
                if not isinstance(rows, list):
                    raise SaxoOrderError(f"Saxo execution response has invalid shape for order {order_id}")
                for transaction in rows:
                    if not isinstance(transaction, dict):
                        raise SaxoOrderError(f"Saxo execution response has invalid row for order {order_id}")
                    trades = transaction.get("Trades", [])
                    if not isinstance(trades, list):
                        raise SaxoOrderError(f"Saxo execution response has invalid trades for order {order_id}")
                    for trade in trades:
                        if not isinstance(trade, dict) or str(trade.get("OrderId", "")) != order_id:
                            continue
                        if trade.get("TradedQuantity") is None or trade.get("Price") is None:
                            raise SaxoOrderError(f"Saxo execution record is incomplete for order {order_id}")
                        amount = abs(_finite_number(trade["TradedQuantity"], "execution quantity", SaxoOrderError))
                        price = _finite_number(trade["Price"], "execution price", SaxoOrderError)
                        if amount <= 0 or price <= 0:
                            raise SaxoOrderError(f"Saxo execution record is invalid for order {order_id}")
                        quantity += amount
                        notional += amount * price
                observed_quantity = quantity
                if abs(quantity - requested_quantity) <= max(1e-8, requested_quantity * 1e-8):
                    return quantity, notional / quantity
                if quantity > requested_quantity:
                    raise SaxoOrderError(f"Saxo execution exceeds requested quantity for order {order_id}")
                next_skip = _next_page_skip(result.get("__next"), skip, SaxoOrderError, f"execution for order {order_id}")
                if next_skip is None:
                    break
                skip = next_skip
            self.clock.sleep(min(self.poll_interval_s, max(0.0, deadline - self.clock.monotonic())))
        if observed_quantity:
            raise SaxoOrderError(f"Saxo order {order_id} only partially filled; inspect SIM account")
        raise SaxoOrderError(f"Saxo execution record missing for order {order_id}; inspect SIM account")

    def _require_account(self) -> None:
        if self.account_key is None or self.client_key is None:
            raise SaxoReconcileError("Saxo account discovery has not completed")


class SaxoBroker:
    def __init__(self, client: SaxoClient, universe: list[str], *, cache_ttl_s: float = 3600):
        if not isinstance(universe, list) or not universe or any(not isinstance(ticker, str) or not ticker.strip() for ticker in universe) or not math.isfinite(cache_ttl_s) or cache_ttl_s <= 0:
            raise ValueError("Saxo broker requires a non-empty universe and positive cache TTL")
        self.client = client
        self.universe = [ticker.strip().upper() for ticker in universe]
        self.cache_ttl_s = cache_ttl_s
        self._cache: dict[str, tuple[float, int, str, dict]] = {}
        if self.client.account_key is None:
            self.client.discover_account()

    def __repr__(self) -> str:
        return f"SaxoBroker(universe={self.universe!r}, credentials=[redacted])"

    def validate_universe(self) -> None:
        now = self.client.clock.monotonic()
        for ticker in self.universe:
            cached = self._cache.get(ticker)
            if cached is None or now - cached[0] >= self.cache_ttl_s:
                uic, asset_type = self.client.search_instrument(ticker)
                details = self.client.instrument_details(uic, asset_type)
                if details.get("IsTradable") is not True:
                    raise SaxoReconcileError(f"Saxo instrument is not tradable: {ticker}")
                exchange = details.get("Exchange")
                currency = details.get("CurrencyCode")
                if not isinstance(exchange, dict) or exchange.get("CountryCode") != "US" or not isinstance(currency, str) or currency.upper() != self.client.base_currency:
                    raise SaxoReconcileError(f"Saxo instrument is not a US listing in {self.client.base_currency}: {ticker}")
                supported = details.get("SupportedOrderTypes", details.get("SupportedOrderTypeSettings", []))
                if isinstance(supported, dict):
                    supported = supported.get("SupportedOrderTypes", [])
                if not isinstance(supported, list) or not any(item == "Market" or (isinstance(item, dict) and item.get("OrderType") == "Market") for item in supported):
                    raise SaxoReconcileError(f"Saxo instrument does not support market orders: {ticker}")
                self._cache[ticker] = (now, uic, asset_type, details)
                self.client._ticker_uic[ticker] = uic

    def positions(self) -> dict[str, Position]:
        self.validate_universe()
        return self.client.positions()

    def filter_orders(self, orders: list[Order]) -> list[Order]:
        if not isinstance(orders, list) or any(not isinstance(order, Order) for order in orders):
            raise TypeError("SaxoBroker.filter_orders requires a list of Orders")
        self.validate_universe()
        filtered = []
        for order in orders:
            cached = self._cache.get(order.ticker.upper())
            if cached is None:
                raise SaxoReconcileError(f"{order.ticker.upper()} is outside the deployed Saxo universe")
            lot_size = _instrument_lot_size(cached[3])
            quantity = _tradable_quantity(order.quantity, lot_size)
            if quantity > 0:
                filtered.append(order.model_copy(update={"quantity": quantity}))
        return filtered

    def cash(self) -> float:
        return _finite_number(self.client.balances().get("CashBalance"), "accounting cash balance", SaxoReconcileError)

    def order_submission_window(self, cutoff: datetime, *, now: Callable[[], datetime]) -> AbstractContextManager[None]:
        return self.client.order_submission_window(cutoff, now=now)

    def _buying_power(self) -> float:
        return _finite_number(self.client.balances().get("CashAvailableForTrading"), "available trading cash", SaxoOrderError)

    def place_order(self, order: Order) -> Fill:
        if not isinstance(order, Order):
            raise TypeError("SaxoBroker.place_order requires an Order")
        if not math.isfinite(order.price) or order.price <= 0:
            raise SaxoOrderError("Saxo order reference price must be finite and positive")
        self.validate_universe()
        ticker = order.ticker.upper()
        if ticker not in self._cache:
            raise SaxoReconcileError(f"{ticker} is outside the deployed Saxo universe")
        _, uic, asset_type, details = self._cache[ticker]
        lot_size = _instrument_lot_size(details)
        quantity = _tradable_quantity(order.quantity, lot_size)
        if quantity <= 0:
            raise SaxoOrderError(f"{ticker}: quantity is below the instrument lot size")
        if order.side == "buy" and quantity * order.price > self._buying_power():
            raise SaxoOrderError("Saxo buying power is insufficient", "InsufficientCash")
        if self.client.account_key is None:
            raise SaxoReconcileError("Saxo account discovery has not completed")
        payload = {
            "AccountKey": self.client.account_key,
            "Uic": uic,
            "AssetType": asset_type,
            "Amount": quantity,
            "BuySell": "Buy" if order.side == "buy" else "Sell",
            "OrderType": "Market",
            "OrderDuration": {"DurationType": "DayOrder"},
            "ManualOrder": False,
        }
        order_id, _ = self.client.place_order(payload)
        deadline = self.client.clock.monotonic() + self.client.execution_timeout_s
        self.client.wait_for_order(order_id, deadline=deadline)
        filled_quantity, price = self.client.order_fill(order_id, quantity, uic=uic, deadline=deadline)
        return Fill(ticker=ticker, side=order.side, quantity=filled_quantity, price=price)


def _tradable_quantity(quantity: float, lot_size) -> float:
    try:
        amount = Decimal(str(quantity))
        lot = Decimal(str(lot_size))
        if amount <= 0 or lot <= 0:
            raise ValueError
        units = (amount / lot).to_integral_value(rounding=ROUND_DOWN)
        return float(units * lot)
    except Exception:
        raise SaxoOrderError("Saxo instrument reported invalid quantity precision") from None


def _instrument_lot_size(details: dict) -> float:
    lot_size = details.get("LotSize")
    return 1 if lot_size is None else lot_size


def _finite_number(value, label: str, error_type) -> float:
    if isinstance(value, bool):
        raise error_type(f"Saxo {label} is invalid")
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise error_type(f"Saxo {label} is invalid") from None
    if not math.isfinite(number):
        raise error_type(f"Saxo {label} is invalid")
    return number


def _next_page_skip(link: object, skip: int, error_type: type[Exception], context: str) -> int | None:
    if link is None:
        return None
    if not isinstance(link, str) or not link:
        raise error_type(f"Saxo {context} pagination is invalid")
    values = parse_qs(urlparse(link).query, keep_blank_values=True).get("$skip", [])
    try:
        next_skip = int(values[0]) if len(values) == 1 else skip
    except ValueError:
        raise error_type(f"Saxo {context} pagination is invalid") from None
    if next_skip <= skip:
        raise error_type(f"Saxo {context} pagination did not advance")
    return next_skip


def _error_code(body) -> str | None:
    if not isinstance(body, dict):
        return None
    info = body.get("ErrorInfo")
    if isinstance(info, dict):
        return str(info.get("ErrorCode") or info.get("Message") or "ErrorInfo")
    return None


def _response(response) -> tuple[int, object]:
    if isinstance(response, tuple) and len(response) == 2:
        return int(response[0]), response[1]
    status = int(getattr(response, "status_code", 0))
    try:
        body = response.json()
    except Exception:
        body = {}
    return status, body


@contextmanager
def _refresh_lock(reference: str, lock_dir: str | Path | None = None, *, timeout_s: float = 90.0):
    if not math.isfinite(timeout_s) or timeout_s <= 0:
        raise ValueError("refresh lock timeout must be positive")
    key = hashlib.sha256(reference.encode("utf-8")).hexdigest()
    with _THREAD_REFRESH_LOCKS_GUARD:
        thread_lock = _THREAD_REFRESH_LOCKS.setdefault(key, threading.Lock())
    deadline = time.monotonic() + timeout_s
    thread_acquired = thread_lock.acquire(timeout=timeout_s)
    if not thread_acquired:
        raise _RefreshLockTimeout(f"Saxo refresh lock contention timed out after {timeout_s:g}s; owner=another thread in this process; retry")
    try:
        configured = lock_dir or os.environ.get("SAXO_REFRESH_LOCK_DIR")
        directory = Path(configured) if configured else Path(tempfile.gettempdir()) / "hedge-fund-saxo-locks"
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{key}.lockdir"
        acquired = False
        try:
            while not acquired:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise _RefreshLockTimeout(f"Saxo refresh lock contention timed out after {timeout_s:g}s; owner={_refresh_lock_owner(path)}; retry") from None
                try:
                    path.mkdir()
                    acquired = True
                except FileExistsError:
                    time.sleep(min(0.05, remaining))
            (path / "owner").write_text(f"{socket.gethostname()}:{os.getpid()}", encoding="utf-8")
            yield
        finally:
            if acquired:
                owner = _refresh_lock_owner(path)
                try:
                    (path / "owner").unlink(missing_ok=True)
                    path.rmdir()
                except OSError as exc:
                    _LOG.error(
                        "Saxo refresh lock cleanup failed; lock=%s owner=%s error=%s; verify holder is inactive before removal",
                        path,
                        owner,
                        type(exc).__name__,
                    )
    finally:
        thread_lock.release()


class _RefreshLockTimeout(SaxoAuthError):
    """Refresh lock stayed held; owner context supports safe manual recovery."""


def _refresh_lock_owner(path: Path) -> str:
    try:
        value = (path / "owner").read_text(encoding="utf-8").strip()
    except OSError:
        return "unknown (owner file unavailable)"
    host, separator, pid = value.rpartition(":")
    if separator and re.fullmatch(r"[A-Za-z0-9._-]{1,128}", host) and pid.isdigit():
        return f"{host}:{pid}"
    return "unknown (owner file invalid)"
