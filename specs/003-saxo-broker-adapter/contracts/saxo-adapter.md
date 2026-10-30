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

`SaxoBroker` implements this structurally (no `SimBroker` inheritance). The shared models are reused **unchanged and as-is**: `Position(ticker, shares)` and `Fill(ticker, side, quantity, price)` from `hedge_fund/brokers/models.py` — there are no `amount`/`avg_cost`/`ts` fields on them. Saxo-specific data (net-position id, acquisition price `OpenPrice`, current price, execution time) stays internal to the adapter (logs/events only), never forced into the shared models.

**Semantics**:
- `positions()` → net positions keyed by engine ticker, mapped to `Position(ticker, shares=PositionBase.Amount)` (signed, long +). `OpenPrice` (acquisition cost) and `PositionView.CurrentPrice` are internal metadata only.
- `cash()` → **accounting cash balance** (`CashBalance` from `/port/v1/balances/me`), in the account currency. This is the number the pipeline adds to equity/NAV (`pipeline/stages.py`) and reconciles against ledger cash (`pipeline/session.py`), so it must be the accounting balance — **not** `CashAvailableForTrading`, which fluctuates with reserved funds and would misstate equity or cause false reconciliation mismatches. Buying power (`CashAvailableForTrading`) is read separately, internal to the adapter, and consulted for order affordability before placement.
- `place_order(order)` → **fill-completely-or-raise**. Returns `Fill(ticker, side, quantity, price)` where `price` is Saxo's simulated execution price for *this* order and `quantity` the executed shares. Raises `SaxoOrderError` (carrying Saxo's `ErrorCode`, e.g. `MarketClosed`, `InsufficientCash`, `OrderValueToSmall`), `SaxoAuthError` (re-auth required), or `SaxoReconcileError` (universe/validation failure). Never returns a partial fill; never silently drops.

## B. Saxo SIM REST surface (outbound)

Base: `https://gateway.saxobank.com/sim/openapi` · Auth: `https://sim.logonvalidation.net`

| Purpose | Call | Notes |
|---|---|---|
| Token exchange/refresh | `POST {auth}/token` | `grant_type=authorization_code` (with PKCE verifier) or `refresh_token`; Basic auth with app credentials; **refresh tokens are single-use and rotate**; refresh is serialized cross-process (lock keyed by secret reference) and the latest refresh token is re-read from 1Password before every attempt |
| Who am I | `GET /port/v1/users/me` | → `ClientKey` |
| Accounts | `GET /port/v1/accounts/me` | → `AccountKey`: **first trading account whose `Currency` matches the fund's base currency**; none compatible ⇒ startup refusal (no FX conversion) |
| Positions | `GET /port/v1/positions/me` | `Data[]`: `PositionBase{Amount (signed), OpenPrice, Uic, AssetType, ExecutionTimeOpen}`, `PositionView{CurrentPrice, ProfitLossOnTrade}`, `NetPositionId` (consume net, not raw fills). Mapped to shared `Position(ticker, shares)`; `OpenPrice`/`CurrentPrice` stay internal |
| Balances | `GET /port/v1/balances/me` | **`CashBalance`** → returned by `cash()` (accounting cash for NAV/reconciliation); **`CashAvailableForTrading`** → internal affordability checks only; also `Currency`, `CurrencyDecimals` |
| Instrument search | `GET /ref/v1/instruments?Keywords={TICKER}&AssetTypes=Stock` | → candidates with `Identifier` (mapped to `Uic`), `ExchangeId`; symbol format `TICKER:exchange` (e.g. `KO:xnys`; `AAPL:xnas` to verify on SIM). **Does not carry tradability fields** |
| Instrument details | `GET /ref/v1/instruments/details/{Uic}/{AssetType}` | **second, distinct call** (per Saxo's stock-order sample): → `IsTradable`, `LotSize`, `MinimumOrderValue/Size`, `SupportedOrderTypeSettings`/`SupportedOrderTypes`, `TickSize`. Both response shapes are fixture-tested separately |
| Place order | `POST /trade/v2/orders` | body `{"AccountKey","Uic","AssetType":"Stock","Amount":<shares>,"BuySell":"Buy"\|"Sell","OrderType":"Market","OrderDuration":{"DurationType":"DayOrder"},"ManualOrder":false}`; header `x-request-id` unique per attempt; **HTTP 200 may carry `ErrorInfo` instead of `OrderId` — inspect the body** |
| Open order poll | `GET /port/v1/orders/{ClientKey}/{OrderId}` | poll until 404/gone (market orders fill near-instantly when open); disappearance **triggers inspection, not fill establishment**; deadline 120 s |
| Transactions | `GET /hist/v1/transactions` | **fill source**: order-correlated executed quantity/price tied to the OrderId — required because `OpenPrice`/`Amount` describe the holding (reductions keep the old acquisition cost; full exits leave no position row), not this execution |

**Client obligations**: Bearer access token on every call; proactive refresh at <120 s remaining; pacer ≥1.0 s between order POSTs; unique `x-request-id`; on 409 (15 s duplicate window) inspect state, never re-POST; on 401 attempt exactly one refresh then re-auth error; SIM-only URLs (live gateway/auth never configured).

## C. Secrets & tokens (1Password)

Item `Saxo OpenAPI SIM` with fields `app-key`, `app-secret`, `refresh-token` (rotating). Env config (non-secret): `SAXO_APP_KEY_REF`, `SAXO_APP_SECRET_REF`, `SAXO_REFRESH_TOKEN_REF` hold `op://` references; `SAXO_REDIRECT_URI` holds the redirect URI.

**The `hedge_fund/secrets/` package does not exist in this checkout** — this feature creates it (test-first): a provider that resolves `op://` references via `op read`, sanitizes failures (error names the variable, never the value), and supports write-back via `op item edit` for the rotating refresh token.

- **Resolve** at startup via the provider. Missing reference ⇒ error naming the variable, never the value.
- **Rotate**: under a cross-process lock keyed by the secret reference, re-read the latest refresh token, refresh, then `op item edit` writes the new refresh token back **before** the new access token is used. Write-back failure ⇒ raise (do not continue with an unpersisted rotation). The re-read makes two fund runners sharing one item safe: the loser of a rotation race picks up the winner's token.
- **Redact**: all client logging/exception paths replace token/secret material with `[redacted]`; ledger and events never contain credentials (tested).

## Error taxonomy

| Error | Raised when | Recovery |
|---|---|---|
| `SaxoAuthError` | refresh failed / 401 after one refresh / interactive re-auth needed | user re-authenticates (auth-code + PKCE in browser) |
| `SaxoOrderError` | order rejected (ErrorInfo, 409 unresolved, deadline exceeded) | session halts with Saxo's ErrorCode in the message |
| `SaxoReconcileError` | universe validation failed / book mismatch | session refuses before trading |