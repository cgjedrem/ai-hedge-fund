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
- `positions()` → net positions keyed by engine ticker from `/port/v1/positions` scoped by `ClientKey` and `AccountKey`, mapped to `Position(ticker, shares=PositionBase.Amount)`.
- `cash()` → **accounting cash balance** (`CashBalance` from `/port/v1/balances` scoped by `ClientKey` and `AccountKey`). Require USD currency. Buying power (`CashAvailableForTrading`) is separate and used only for affordability.
- `filter_orders(orders)` → copy orders with quantity rounded down to lot multiples; `LotSize: null` or missing uses 1. Remove results below one lot. Cycle ledger records the adjusted order copies. `place_order(order)` → **fill-completely-or-raise** for every submitted order. Never returns a partial fill.
- Post-filter position/gross-limit breaches are rejected when filtered exposure worsens the corresponding current-book metric. Risk-reducing trades may continue while an existing breach remains.
- Saxo minute mandates start at or after 09:30 ET and end by 15:59 ET. An omitted Saxo window defaults to 09:30–15:59; paper window defaults stay unchanged.
- The unattended runner does not execute a pending Saxo bar once 16:00 ET has passed, even if the bar is still within the generic lateness window; it resumes at the next valid bar.
- Universe validation selects a deterministic US-exchange listing and requires instrument details `Exchange.CountryCode=US`, `CurrencyCode=USD`, and market-order support. Reused broker instances revalidate on each session and refresh expired entries after 3600 seconds.
- Saxo account currency is fixed USD by the app's mandate convention; there is no deploy-time remote account check. Broker construction checks `Active`, `LegalAssetTypes` including `Stock`, account `Currency`, and scoped balance `Currency` before session trading.

## B. Saxo SIM REST surface (outbound)

Base: `https://gateway.saxobank.com/sim/openapi` · Auth: `https://sim.logonvalidation.net`

| Purpose | Call | Notes |
|---|---|---|
| Token exchange/refresh | `POST {auth}/token` | `grant_type=authorization_code` (with PKCE verifier) or `refresh_token`; Basic auth with app credentials; **refresh tokens are single-use and rotate**; interactive exchange+write-back and refresh are serialized (lock keyed by secret reference); latest refresh token is re-read from 1Password before every refresh attempt |
| Who am I | `GET /port/v1/users/me` | → `ClientKey` |
| Accounts | `GET /port/v1/accounts/me` | Select active USD account with `LegalAssetTypes` including `Stock`; otherwise startup refusal |
| Positions | `GET /port/v1/positions` | Include both `ClientKey` and `AccountKey`; `Data[]` net positions with signed `PositionBase.Amount` and `NetPositionId` |
| Balances | `GET /port/v1/balances` | Include both `ClientKey` and `AccountKey`; require `Currency=USD`; `CashBalance` → `cash()`, `CashAvailableForTrading` → affordability only |
| Instrument search | `GET /ref/v1/instruments?Keywords={TICKER}&AssetTypes=Stock` | → candidates with `Identifier` (mapped to `Uic`), `ExchangeId`; symbol format `TICKER:exchange` (e.g. `KO:xnys`; `AAPL:xnas` to verify on SIM). **Does not carry tradability fields** |
| Instrument details | `GET /ref/v1/instruments/details/{Uic}/{AssetType}` | **second, distinct call** (per Saxo's stock-order sample): → `IsTradable`, `LotSize`, `MinimumOrderValue/Size`, `SupportedOrderTypeSettings`/`SupportedOrderTypes`, `TickSize`. Both response shapes are fixture-tested separately |
| Place order | `POST /trade/v2/orders` | body `{"AccountKey","Uic","AssetType":"Stock","Amount":<shares>,"BuySell":"Buy"\|"Sell","OrderType":"Market","OrderDuration":{"DurationType":"DayOrder"},"ManualOrder":false}`; header `x-request-id` unique per attempt; **HTTP 200 may carry `ErrorInfo` instead of `OrderId` — inspect the body** |
| Open order poll | `GET /port/v1/orders/{ClientKey}/{OrderId}` | poll until 404/gone (market orders fill near-instantly when open); disappearance **triggers inspection, not fill establishment**; deadline 120 s |
| Transactions | `GET /hist/v1/transactions` | Filter with `AccountKeys`, `ClientKey`, `FromDate`, `ToDate`, `TransactionType=Trade`, `Uics`; paginate using `__next`/`$skip`; match `Data[].Trades[].OrderId`; aggregate `TradedQuantity` and weighted `Price`. `OrderId` is not a supported query filter |

**Client obligations**: Bearer access token on every call; proactive refresh at <120 s remaining; pacer ≥1.0 s between order POSTs; unique `x-request-id`; on 409 (15 s duplicate window) inspect state, never re-POST; on 401 attempt exactly one refresh then re-auth error; SIM-only URLs (live gateway/auth never configured).

## C. Secrets & tokens (1Password)

Item `Saxo OpenAPI SIM` with fields `app-key`, `app-secret`, `refresh-token` (rotating). Env config (non-secret): `SAXO_APP_KEY_REF`, `SAXO_APP_SECRET_REF`, `SAXO_REFRESH_TOKEN_REF` hold `op://` references; `SAXO_REDIRECT_URI` holds the redirect URI; `SAXO_REFRESH_LOCK_DIR` selects a shared lock directory.

The provider resolves `op://` references via `op read` and sanitizes failures. For write-back it reads the item with `op item get --format=json --reveal`, updates the referenced field in memory, then pipes JSON to `op item edit`; token never appears in argv.

- **Resolve** app credentials at startup via the provider. Read the refresh token under its lock on first authorization and each refresh. Missing reference ⇒ error naming the variable, never the value.
- **Rotate**: under a reference-keyed atomic lock directory, re-read the latest refresh token, refresh, then persist before using the access token. Acquisition times out after 90 seconds and reports sanitized owner context; contention is retryable, not terminal re-authentication. Never steal locks automatically. Default temp path coordinates same-host processes only. Host/container coordination requires both to use the same mounted path via `SAXO_REFRESH_LOCK_DIR`; atomic directory creation is required. A process crash can leave a stale lock, which requires operator verification and cleanup.
- Interactive authorization holds the same reference-keyed lock across authorization-code exchange and token write-back. Lock cleanup errors after successful persistence are logged with recovery context; the saved token remains authorized.
- Interactive re-auth updates persisted refresh credentials but does not replace an already-running process's terminal `REAUTH_REQUIRED` token manager; restart that runner after login.
- **Redact**: all client logging/exception paths replace token/secret material with `[redacted]`; ledger and events never contain credentials (tested).

## D. Mandate costs

When Saxo `costs` is omitted, `FundSpec` defaults spread and commission to zero. Explicit values are honored, including values equal to paper defaults. Paper default costs and serialized output remain unchanged.

## Error taxonomy

| Error | Raised when | Recovery |
|---|---|---|
| `SaxoAuthError` | refresh failed / 401 after one refresh / interactive re-auth needed | user re-authenticates (auth-code + PKCE in browser) |
| `SaxoOrderError` | order rejected (ErrorInfo, 409 unresolved, deadline exceeded) | session halts with Saxo's ErrorCode in the message |
| `SaxoReconcileError` | universe validation failed / book mismatch | session refuses before trading |