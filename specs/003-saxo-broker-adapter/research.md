# Research: Trading 212 Broker Adapter

**Feature**: 003-t212-broker-adapter | **Date**: 2026-10-30

All NEEDS CLARIFICATION items from the plan's Technical Context were resolved before planning via two research rounds (broker landscape + T212 API deep dive). Findings below are the design inputs.

## R1. HTTP client library

**Decision**: Use `requests` (already a project dependency, ^2.32.0). No new packages.

**Rationale**: The adapter needs Basic auth, JSON bodies, timeout control, and header inspection (`x-ratelimit-*`). `requests` does all of this and is already installed; adding `httpx` or the community `t212-sdk` would add a dependency for no capability gain.

**Alternatives considered**:
- `t212-sdk` (community, Fern-generated): full endpoint coverage, but pins its own HTTP stack, adds surface we don't need (CFD endpoints, pies), and the adapter must stay demo-only and auditable — a thin ~200-line client over `requests` is easier to review and test.
- `urllib` stdlib: workable but clunkier (auth headers, sessions, retries by hand) for zero benefit.

## R2. Environment: demo only

**Decision**: The client hardcodes `https://demo.trading212.com/api/v0`. The live URL never appears in code or config.

**Rationale**: FR-002 (constitution II: paper only). A configurable base URL would make a live call one typo away. Demo and live use **separate API keys**, so even a misconfigured key cannot cross environments — a demo key returns 401 on live.

**Alternatives considered**: env-var-selectable base URL — rejected as an unnecessary live-risk footgun.

## R3. Authentication and secrets

**Decision**: HTTP Basic auth (API key = username, secret = password). Credentials come from two env vars — `HEDGE_FUND_T212_API_KEY` and `HEDGE_FUND_T212_API_SECRET` — whose values may be either plaintext or a 1Password `op://` reference. `op://` values are resolved at broker construction via the 1Password CLI (`op read`), never at import time.

**Rationale**: FR-007/FR-009. Resolution-at-construction keeps secrets out of long-lived process env dumps; the `op` CLI works both interactively (desktop-app unlock on the host) and unattended (service-account token `OP_SERVICE_ACCOUNT_TOKEN` in Docker).

**Alternatives considered**: SDK keyrings / direct 1Password Connect API — rejected (extra infra for one user); reading secrets from fund.yaml — rejected (FR-009: secrets never in persisted files).

## R4. Order placement semantics

**Decision**: Market orders only (`POST /equity/orders/market`), body `{"ticker": "<SYM>_US_EQ", "quantity": <signed float>, "extendedHours": false}`. Quantity sign encodes side (positive buy, negative sell) — T212 has no `side` field. Quantities are rounded to **4 decimals**; sell quantities round **down** (toward zero) to avoid `SellingEquityNotOwned`.

**Rationale**: The engine's sessions rebalance at close with reference prices; market orders at the next open/close match the paper semantics. 4dp is T212's placement precision (positions may hold 8dp). Rounding sells down prevents ordering more shares than `quantityAvailableForTrading`.

**Alternatives considered**: limit orders — deferred (spec P2 scope is market orders; the API supports them if needed later).

## R5. Fill completion: poll, never blind-retry

**Decision**: `place_order` POSTs once, then polls `GET /equity/orders/{id}` (limit 1 req/s) until a terminal status: `FILLED` → return `Fill` with the historical fill's actual price/quantity; `REJECTED`/`CANCELLED` → raise. A bounded overall timeout (default 120s) raises. **A timed-out or ambiguous POST is never retried blindly** — the beta API is non-idempotent and a blind retry can duplicate the order; the caller must inspect pending orders first.

**Rationale**: The Broker contract is fill-completely-or-raise; partial states must not be returned as fills. Non-idempotency makes retry-on-timeout the single most dangerous operation in the adapter.

**Alternatives considered**: WebSocket — T212 has none; polling is the only option.

## R6. Rate limiting

**Decision**: A tiny per-endpoint pacer (minimum interval between calls of the same kind) plus 429 handling that sleeps until `x-ratelimit-reset` (Unix seconds) and retries the **read** once. Order POSTs are never auto-retried (R5).

**Rationale**: Known limits: market orders 50/min, order status 1/s, positions 1/s, account summary 1/5s, instruments 1/50s, pending orders 1/5s. A daily 9-ticker session cannot hit these with pacing, but the pacer makes the adapter safe under bursts and testable with a fake clock.

## R7. Ticker mapping and universe validation

**Decision**: Engine tickers map to T212 tickers as `{SYMBOL}_US_EQ` (US equities). Before the first order of a session, the adapter validates the fund's universe against `GET /equity/metadata/instruments` (cached ~1h; ~5MB response) and refuses to trade any ticker that is missing or not tradable.

**Rationale**: FR-006/FR-011. The instruments list is the only authoritative source of tradable tickers; validating up front turns a mid-session surprise into a pre-session refusal.

## R8. Book authority and reconciliation

**Decision**: The external broker's `positions()`/`cash()` (from `GET /equity/positions` and `GET /equity/account/summary`) are authoritative. The existing pre-session reconciliation (ledger book vs broker book) runs unchanged; an unexplained mismatch refuses the session. Sells are sized against `quantityAvailableForTrading`, not raw `quantity` (pies/pending orders lock shares).

**Rationale**: FR-005. This is exactly the two-books design PaperBroker already implements — T212Broker just sources its book from the API instead of broker.json.

## R9. Redo path with an external broker

**Decision**: `redo` on a fund whose broker is not `paper` is refused with a clear error. Restoring broker.json to a pre-session state is meaningless when the book lives at the broker; undoing real demo fills is out of scope.

**Rationale**: Ledger integrity (constitution I) — a redo that cannot restore the broker book would desync the two books by design.

## R10. Costs model for T212 funds

**Decision**: T212 fills carry the broker's actual price, so the mandate's cost model defaults to zero spread/commission for `broker: t212` funds (double-counting real fills with a simulated spread would corrupt NAV). A mandate may still override costs explicitly.

**Rationale**: `TradingCosts` exists to simulate friction SimBroker can't know; with a real broker the friction is already in the fill price.

## R11. Testing strategy

**Decision**: All adapter tests run against a fake `requests` transport (pre-scripted responses/fixture files) and a fake clock for the pacer/poller. Recorded real response shapes (from research) become fixtures. No test touches the network; the final smoke test against the user's demo account is a manual quickstart step, not a test.

**Rationale**: Constitution II (no unattended live risk) and III (green suite); determinism (IV).

## R12. Fund configuration and byte-compat

**Decision**: `FundSpec` gains `broker: Literal["paper", "t212"] = "paper"`. When serializing, the key is popped when it equals the default (same pattern as `approval_required`), so existing deployed `fund.yaml` files remain byte-identical and old funds keep working unchanged.

**Rationale**: FR-010 (per-fund broker selection) + constitution I (deployed funds immutable; byte-identical replay).

## Open items (empirical, demo-account smoke test)

- Minimum order size/value: not documented; observe on first demo orders.
- Explicit error codes for market-closed and unknown ticker: bodies vary; the adapter branches on HTTP status and surfaces the body verbatim in errors (never logging secrets).
- Whether `extendedHours: true` is needed for the fund's cadence: default false; revisit if fills lag sessions.