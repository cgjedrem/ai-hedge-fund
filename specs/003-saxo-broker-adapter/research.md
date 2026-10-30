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

**Rationale**: Saxo provides no unattended retail login — Certificate-Based Authentication is institutional-partner-only (retail logins must show MiFID II disclaimers interactively). The practical pattern for a personal bot is a long-lived process refreshing its own token, plus periodic (~weekly) interactive re-auth. The rotating-refresh-token rule makes "persist after every refresh" mandatory, or the next restart fails.

**Implication for the watchtower**: fully unattended month-long operation is out of scope by design; the fund owner re-authenticates interactively when prompted.

**Sources**: developer.saxo/openapi/learn/oauth-authorization-code-grant, developer.saxo/openapi/learn/oauth-authorization-code-grant-pkce, openapi.help.saxo/hc/en-us (token lifetime, CBA availability)

## R4. Secrets storage

**Decision**: 1Password via `op://` references, resolved at startup through the 1Password CLI (same mechanism as the original design). The refresh token is special: it **rotates**, so the adapter writes the new value back to the 1Password item after each refresh (`op item edit`). Plaintext env values remain supported for non-secret configuration only.

**Rationale**: FR-007/FR-009. A rotating credential cannot sit only in process memory across restarts; 1Password is the one sanctioned secret store (never plaintext files, never the ledger).

**Alternatives considered**: OS keychain directly — rejected (Docker context has no keychain); encrypted local file — rejected (constitution: secrets never in persisted files outside the secret store).

## R5. Order placement semantics

**Decision**: Market orders only: `POST /trade/v2/orders` with `{"AccountKey": ..., "Uic": <int>, "AssetType": "Stock", "Amount": <shares>, "BuySell": "Buy"|"Sell", "OrderType": "Market", "OrderDuration": {"DurationType": "DayOrder"}, "ManualOrder": false}`. Side is an explicit enum (unlike T212's signed quantity). Cash-amount sizing (`AmountType: CurrencyAmount`) is MutualFunds-only — not usable for stocks. Each POST carries a unique `x-request-id` header.

**Rationale**: Matches the engine's session semantics (rebalance at close, reference prices). `ManualOrder: false` truthfully declares bot placement. DayOrder is the natural duration for market orders that fill immediately when open.

**Critical response rule**: a **200 OK can still be a logical failure** — the body may carry `ErrorInfo` and no `OrderId`. The adapter inspects the body, never just the HTTP status.

**Sources**: developer.saxo/openapi/referencedocs/trade/v2/orders/post__trade, developer.saxo/openapi/learn/order-placement

## R6. Fill detection (no dedicated fills endpoint)

**Decision**: After a successful POST, poll `GET /port/v1/orders/{ClientKey}/{OrderId}` until the order **leaves the open-orders list** (404/empty — market orders fill near-instantly when the market is open), then read the authoritative fill from the resulting position (`PositionBase.OpenPrice`, `PositionBase.Amount`, `ExecutionTimeOpen`) or `GET /hist/v1/transactions`. Bounded deadline (default 120 s) raises with guidance. `trade/v1|v2/trades` endpoints are deal-capture/back-office only — not used.

**Rationale**: Saxo's retail API has no single "get my fill" endpoint; this synthesized pattern uses only documented endpoints. The position's `OpenPrice` is Saxo's own simulated fill price — exactly what the ledger must record.

**Sources**: developer.saxo/openapi/referencedocs/port/v1/orders/get__port__clientkey_orderid, developer.saxo/openapi/referencedocs/port/v1/positions/get__port__me, developer.saxo/openapi/referencedocs/hist/v1/transactions

## R7. Rate limiting and duplicate protection

**Decision**: Per-endpoint pacer (order placement ≥1/s; reads modestly paced) plus a unique `x-request-id` per attempt. **No automatic re-POST** of an order whose outcome is unknown. Saxo rejects identical repeated order POSTs within a 15-second window with 409 unless `x-request-id` differs — the adapter treats 409 as "inspect state, never resend".

**Rationale**: Documented limits: ~10,000,000 requests/day per app, 120 req/min per session per service group, 1 order placement/s per session. A daily 9-ticker session cannot hit these, but the pacer + unique request ids make the adapter safe and testable with a fake clock.

**Source**: developer.saxo/openapi/learn/rate-limiting

## R8. Ticker mapping and universe validation

**Decision**: Engine tickers resolve to Saxo `(Uic, AssetType=Stock)` via `GET /ref/v1/instruments?Keywords=<TICKER>&AssetTypes=Stock` (symbol format `AAPL:xnas` inferred from documented examples like `KO:xnys` — verify on SIM). Resolutions are cached in memory (~1h). Before the first order of a session, every universe ticker must resolve to a tradable instrument (`IsTradable`, `SupportedOrderTypes` includes Market); otherwise the session refuses.

**Rationale**: FR-006. Saxo identifies instruments by numeric UIC + AssetType, not ticker — the mapping is a hard prerequisite for ordering.

## R9. Book authority and reconciliation

**Decision**: The external broker's book is authoritative: positions from `GET /port/v1/positions/me` (consume via `NetPositionId` grouping; `PositionBase.Amount` signed, `OpenPrice` acquisition price), cash from `GET /port/v1/balances/me` (`CashAvailableForTrading`, `Currency`). The existing pre-session reconciliation runs unchanged; unexplained mismatch refuses the session. ClientKey/AccountKey are discovered via `GET /port/v1/users/me` / `GET /port/v1/accounts/me` at startup.

**Rationale**: FR-005 — the same two-books design PaperBroker implements, sourced from the API.

## R10. Costs model for Saxo funds

**Decision**: Same as the T212 design: fills carry the broker's actual (simulated) price, so the mandate's cost model defaults to zero spread/commission for `broker: saxo` funds; a mandate may override explicitly.

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