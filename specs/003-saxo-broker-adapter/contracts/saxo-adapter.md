# Contract: Saxo OpenAPI Adapter

**Feature**: 003-saxo-broker-adapter | **Date**: 2026-10-30

Three surfaces: (A) the in-process `Broker` protocol the adapter must satisfy, (B) the Saxo SIM REST endpoints it calls, (C) the secrets/token interface.

## A. Broker protocol (in-process, unchanged)

```python
class Broker(Protocol):
    def positions(self) -> dict[str, Position]: ...
    def cash(self) -> float: ...
    def place_order(self, order: Order) -> Fill: ...
```

`SaxoBroker` implements this structurally (no `SimBroker` inheritance). Models `Order`/`Fill`/`Position` from `hedge_fund/brokers/models.py` are reused unchanged.

**Semantics**:
- `positions()` → net positions keyed by engine ticker; `Position.amount` signed (long +), `avg_cost` = Saxo `PositionBase.OpenPrice`.
- `cash()` → `CashAvailableForTrading` (buying power) in account currency.
- `place_order(order)` → **fill-completely-or-raise**. Returns `Fill(price=<Saxo simulated fill>, quantity=<filled shares>, ts=<execution time>)`. Raises `SaxoOrderError` (carrying Saxo's `ErrorCode`, e.g. `MarketClosed`, `InsufficientCash`, `OrderValueToSmall`), `SaxoAuthError` (re-auth required), or `SaxoReconcileError` (universe/validation failure). Never returns a partial fill; never silently drops.

## B. Saxo SIM REST surface (outbound)

Base: `https://gateway.saxobank.com/sim/openapi` · Auth: `https://sim.logonvalidation.net`

| Purpose | Call | Notes |
|---|---|---|
| Token exchange/refresh | `POST {auth}/token` | `grant_type=authorization_code` (with PKCE verifier) or `refresh_token`; Basic auth with app credentials; **refresh tokens are single-use and rotate** |
| Who am I | `GET /port/v1/users/me` | → `ClientKey` |
| Accounts | `GET /port/v1/accounts/me` | → `AccountKey` (first trading account) |
| Positions | `GET /port/v1/positions/me` | `Data[]`: `PositionBase{Amount (signed), OpenPrice, Uic, AssetType, ExecutionTimeOpen}`, `PositionView{CurrentPrice, ProfitLossOnTrade}`, `NetPositionId` (consume net, not raw fills) |
| Balances | `GET /port/v1/balances/me` | `CashBalance`, **`CashAvailableForTrading`**, `Currency`, `CurrencyDecimals` |
| Instrument search | `GET /ref/v1/instruments?Keywords={TICKER}&AssetTypes=Stock` | → `Uic`, `ExchangeId`, `IsTradable`, `LotSize`, `SupportedOrderTypes`; symbol format `TICKER:exchange` (e.g. `KO:xnys`; `AAPL:xnas` to verify on SIM) |
| Place order | `POST /trade/v2/orders` | body `{"AccountKey","Uic","AssetType":"Stock","Amount":<shares>,"BuySell":"Buy"\|"Sell","OrderType":"Market","OrderDuration":{"DurationType":"DayOrder"},"ManualOrder":false}`; header `x-request-id` unique per attempt; **HTTP 200 may carry `ErrorInfo` instead of `OrderId` — inspect the body** |
| Open order poll | `GET /port/v1/orders/{ClientKey}/{OrderId}` | poll until 404/gone (market orders fill near-instantly when open); deadline 120 s |
| Transactions | `GET /hist/v1/transactions` | fallback/confirmation source for fill price/time |

**Client obligations**: Bearer access token on every call; proactive refresh at <120 s remaining; pacer ≥1.0 s between order POSTs; unique `x-request-id`; on 409 (15 s duplicate window) inspect state, never re-POST; on 401 attempt exactly one refresh then re-auth error; SIM-only URLs (live gateway/auth never configured).

## C. Secrets & tokens (1Password)

Item `Saxo OpenAPI SIM` with fields `app-key`, `app-secret`, `refresh-token` (rotating). Env config (non-secret): `SAXO_APP_KEY_REF`, `SAXO_APP_SECRET_REF`, `SAXO_REFRESH_TOKEN_REF` hold `op://` references; `SAXO_REDIRECT_URI` holds the redirect URI.

- **Resolve** at startup via `op read` (existing provider). Missing reference ⇒ error naming the variable, never the value.
- **Rotate**: after every successful token refresh, `op item edit` writes the new refresh token back **before** the new access token is used. Write-back failure ⇒ raise (do not continue with an unpersisted rotation).
- **Redact**: all client logging/exception paths replace token/secret material with `[redacted]`; ledger and events never contain credentials (tested).

## Error taxonomy

| Error | Raised when | Recovery |
|---|---|---|
| `SaxoAuthError` | refresh failed / 401 after one refresh / interactive re-auth needed | user re-authenticates (auth-code + PKCE in browser) |
| `SaxoOrderError` | order rejected (ErrorInfo, 409 unresolved, deadline exceeded) | session halts with Saxo's ErrorCode in the message |
| `SaxoReconcileError` | universe validation failed / book mismatch | session refuses before trading |