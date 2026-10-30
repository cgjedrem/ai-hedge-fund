# Research: Saxo OpenAPI Broker Adapter

**Feature**: 003-saxo-broker-adapter | **Date**: 2026-10-30

All design inputs verified against official Saxo sources (developer.saxo, openapi.help.saxo) by a dedicated research pass. Each section states the decision, rationale, and alternatives.

## R0. Why Saxo (re-target from Trading 212)

**Decision**: Build the broker adapter against Saxo Bank OpenAPI, SIM environment.

**Rationale**: Trading 212's API terms expressly prohibit using their API for Algorithmic Trading purposes — which covers this engine's automated order placement even with per-decision human approval. Saxo's OpenAPI anticipates programmatic trading: the order payload has a `ManualOrder` boolean ("Indicator for whether order is placed automatically or manually"), trading endpoints require a `Personal: Write` app permission, and Saxo documents a self-service credential request path for direct retail clients. No prohibition against personal algo trading was found anywhere in Saxo's docs.

**Sources**: developer.saxo/openapi/learn/order-placement, developer.saxo/openapi/referencedocs/trade/v2/orders/post__trade, developer.saxo/openapi/learn/direct-clients-request-for-openapi-application-credentials-for-the-live-environ

## R1. HTTP client library

**Decision**: Use `requests` (already a project dependency, ^2.32.0). No new packages, no SDK.

**Rationale**: The adapter needs OAuth token calls, Basic-auth token exchange, JSON bodies, header control (`x-request-id`), and timeouts. Saxo's first-party samples are JavaScript-only; community Python SDKs are unverified. A thin client over `requests` stays auditable and testable.

**Alternatives considered**: `saxo_apy` (community, existence/maintenance unverified) — rejected; `openapi-samples-python` patterns — consulted conceptually only.

## R2. Environment: SIM only

**Decision**: Hardcode SIM endpoints: REST base `https://gateway.saxobank.com/sim/openapi`, auth server `https://sim.logonvalidation.net`. Live URLs (`gateway.saxobank.com/openapi`, `live.logonvalidation.net`) never appear in code or config.

**Rationale**: Constitution II (paper only). SIM and LIVE use **separate app registrations** (environment-specific AppKey/AppSecret), so SIM credentials cannot reach the live gateway even by misconfiguration. SIM access is self-service: register at developer.saxo, create an app against the SIM environment — no funded account, no approval queue.

**Sources**: developer.saxo/openapi/learn/environments, developer.saxo/accounts/sim/signup

## R3. Authentication and token lifecycle

**Decision**: OAuth2 Authorization Code Grant (+PKCE for the native/desktop case). The adapter holds an access token (~20 min lifetime) and refreshes **proactively** (~every 15 min). Refresh tokens are **single-use and rotate on every refresh** — the adapter persists the newest refresh token to 1Password immediately after each successful refresh. If a refresh fails (revoked, expired, logged out via SaxoTraderGO "Application Access"), the adapter raises a clear re-auth error instead of retrying.

**Lock scope**: refresh is serialized by an atomic lock directory keyed by the secret reference. Acquisition is bounded to 90 seconds; timeout reports sanitized owner context, remains retryable, and never steals the lock. The default temp directory coordinates processes on that host only. Host/container coordination requires both environments to set `SAXO_REFRESH_LOCK_DIR` to the same mounted filesystem path with atomic directory creation. A process crash can leave a stale lock; operator verifies the recorded PID is no longer active before removing it. Each refresh re-reads the latest refresh token while holding the lock. Interactive re-authentication requires restart of running processes whose token managers entered `REAUTH_REQUIRED`.

**Rationale**: Saxo provides no unattended retail login — Certificate-Based Authentication is institutional-partner-only (retail logins must show MiFID II disclaimers interactively). The practical pattern for a personal bot is a long-lived process refreshing its own token, plus periodic (~weekly) interactive re-auth. The rotating-refresh-token rule makes "persist after every refresh" mandatory, or the next restart fails.

**Implication for the watchtower**: fully unattended month-long operation is out of scope by design; the fund owner re-authenticates interactively when prompted.

**Sources**: developer.saxo/openapi/learn/oauth-authorization-code-grant, developer.saxo/openapi/learn/oauth-authorization-code-grant-pkce, openapi.help.saxo/hc/en-us (token lifetime, CBA availability)

## R4. Secrets storage

**Decision**: 1Password via `op://` references; app credentials resolve at startup, while the rotating refresh token is read under the refresh lock on initial authorization and each refresh. For rotation, `op item get <item> --format=json --reveal --vault <vault>` supplies the current item template; the provider changes only the referenced field and pipes the full JSON to `op item edit <item> --vault <vault>`. The new token never appears in CLI arguments. Plaintext env values remain supported for non-secret configuration only.

**Rationale**: FR-007/FR-009. 1Password documents JSON templates for sensitive edits and warns that assignment values can be visible in command history/process lists. A rotating credential cannot sit only in process memory across restarts.

**Alternatives considered**: OS keychain directly — rejected (Docker context has no keychain); encrypted local file — rejected (constitution: secrets never in persisted files outside the secret store).

**Source**: `https://developer.1password.com/docs/cli/item-edit/`

## R5. Order placement semantics

**Decision**: Market orders only: `POST /trade/v2/orders` with `{"AccountKey": ..., "Uic": <int>, "AssetType": "Stock", "Amount": <shares>, "BuySell": "Buy"|"Sell", "OrderType": "Market", "OrderDuration": {"DurationType": "DayOrder"}, "ManualOrder": false}`. Side is an explicit enum (unlike T212's signed quantity). Cash-amount sizing (`AmountType: CurrencyAmount`) is MutualFunds-only — not usable for stocks. Each POST carries a unique `x-request-id` header.

**Rationale**: Matches the engine's session semantics (rebalance at close, reference prices). `ManualOrder: false` truthfully declares bot placement. DayOrder is the natural duration for market orders that fill immediately when open.

**Critical response rule**: a **200 OK can still be a logical failure** — the body may carry `ErrorInfo` and no `OrderId`. The adapter inspects the body, never just the HTTP status.

**Sources**: developer.saxo/openapi/referencedocs/trade/v2/orders/post__trade, developer.saxo/openapi/learn/order-placement

## R6. Fill detection (no dedicated fills endpoint)

**Decision**: After a successful POST, poll `GET /port/v1/orders/{ClientKey}/{OrderId}` until the order leaves the open-orders list. Disappearance triggers inspection, not fill establishment. Query `GET /hist/v1/transactions` with `AccountKeys`, `ClientKey`, `FromDate`, `ToDate`, `TransactionType=Trade`, and `Uics`; do not send unsupported `OrderId`. Paginate using `__next`/`$skip`. Match `Data[].Trades[].OrderId`, then aggregate `TradedQuantity` and weighted `Price`; this covers increases, reductions, and full exits. A bounded deadline raises with guidance.

**Rationale**: Saxo's retail API has no single "get my fill" endpoint; this synthesized pattern uses only documented endpoints and never infers a fill from position state alone.

**Sources**: developer.saxo/openapi/referencedocs/port/v1/orders/get__port__clientkey_orderid, developer.saxo/openapi/referencedocs/hist/v1/transactions

## R7. Rate limiting and duplicate protection

**Decision**: Per-endpoint pacer (order placement ≥1/s; reads modestly paced) plus a unique `x-request-id` per attempt. **No automatic re-POST** of an order whose outcome is unknown. Saxo rejects identical repeated order POSTs within a 15-second window with 409 unless `x-request-id` differs — the adapter treats 409 as "inspect state, never resend".

**Rationale**: Documented limits: ~10,000,000 requests/day per app, 120 req/min per session per service group, 1 order placement/s per session. A daily 9-ticker session cannot hit these, but the pacer + unique request ids make the adapter safe and testable with a fake clock.

**Source**: developer.saxo/openapi/learn/rate-limiting

## R8. Ticker mapping and universe validation

**Decision**: Search `GET /ref/v1/instruments?Keywords=<TICKER>&AssetTypes=Stock`, require an exact ticker prefix and a supported US exchange ID, and choose deterministically (primary listing, exchange priority, identifier). Then request `/ref/v1/instruments/details/{Uic}/Stock`; require `IsTradable`, `Exchange.CountryCode=US`, `CurrencyCode=USD`, and Market order support. Search and details have different response shapes. Resolutions are cached in memory (~1 h).

**Rationale**: FR-006. Saxo identifies instruments by numeric UIC + AssetType, not ticker; expecting tradability fields directly from search would make validation fail against real responses.

## R9. Book authority, cash semantics, and currency

**Decision**: The external book is authoritative. Read `/port/v1/positions` and `/port/v1/balances` with both discovered `ClientKey` and `AccountKey`; `/me` variants are client-wide and do not provide account scope. Select the first active account with `LegalAssetTypes` including `Stock` and `Currency=USD`. The app mandate convention is fixed USD; startup refuses other account currencies. `cash()` returns `CashBalance`; `CashAvailableForTrading` is used only for affordability.

**Rationale**: FR-005/FR-005a — the pipeline treats `cash()` as same-currency money. Offline deploy validates the fixed USD mandate convention; live account currency is checked when the broker starts, before trading.

## R10. Costs model for Saxo funds

**Decision**: When `broker: saxo` omits `costs`, default spread and commission to zero because Saxo SIM `Fill.price` already carries simulated execution pricing. Explicit cost values remain honored. Paper default costs and serialized output remain unchanged.

**Rationale**: Double-counting simulated friction on top of real simulated fills would corrupt NAV.

## R11. Market data on SIM

**Decision**: Do not use OpenAPI price endpoints. SIM supplies **no live prices for stocks** (only FxSpot) — Saxo's own samples fall back to fictive prices. Fill-price sanity checks compare Saxo's simulated fill (`OpenPrice`) against the yfinance price at trade time.

**Rationale**: yfinance is already the data path (FR-013); SIM quotes would be `NoAccess` anyway.

**Source**: SaxoBank/openapi-samples-js orders/stocks/demo.js (NoAccess fallback)

## R12. Session capabilities

**Decision**: The adapter stays at the default session level (`TradeLevel: OrdersOnly`, `DataLevel: Standard`) — it never requests `FullTradingAndChat`/`Premium`.

**Rationale**: Only one session per user may hold the upgraded level; a bot requesting it would forcibly demote/log off the user's own SaxoTraderGO session. The adapter needs no real-time data, so the default level costs nothing.

**Source**: developer.saxo/openapi/learn/session-capabilities

## R13. Testing strategy

**Decision**: All adapter tests run against a fake `requests` transport (pre-scripted responses/fixture files) and a fake clock for the pacer/token refresher. Recorded real response shapes (from research) become fixtures. No test touches the network; the SIM smoke test is a manual quickstart step.

**Rationale**: Constitution II and III; determinism (IV).

## R14. Fund configuration and byte-compat

**Decision**: `FundSpec` gains `broker: Literal["paper", "saxo"] = "paper"`, popped from serialization when equal to the default (same pattern as `approval_required`) — existing deployed fund.yaml files stay byte-identical.

**Rationale**: FR-010 + constitution I.

## Open items (empirical, SIM smoke test)

- `AAPL:xnas` symbol resolution and UIC for the fund's universe (search endpoint).
- Whether SIM accepts **fractional** `Amount` for US stocks (place a 0.5-share order; FR-012).
- Market-closed behavior: confirm synchronous `MarketClosed` rejection (inferred from the error-code enum).
- Real refresh-token lifetime for the user's app registration (docs example shows 2400 s — illustrative, not contractual).
- Whether `/hist/v1/transactions` populates promptly after a SIM trade (vs batch/EOD).
- Exact `/ref/v1/exchanges/{ExchangeId}` schedule schema (not needed if using position-level `IsMarketOpen`).