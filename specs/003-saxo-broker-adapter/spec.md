# Spec: Saxo OpenAPI Broker Adapter (SIM)

**Feature Branch**: `003-saxo-broker-adapter` (app-managed worktree; branch creation skipped, numbering applied)
**Created**: 2026-10-30
**Status**: Draft (re-targeted from Trading 212 — see Context)

## Context: why Saxo and not Trading 212

The original target, Trading 212, prohibits in its API terms: *"You are expressly prohibited from using our API for Algorithmic Trading purposes..."* — which covers this engine's automated order placement even with per-decision human approval. Saxo Bank's OpenAPI is built for programmatic trading: order payloads carry a `ManualOrder` flag distinguishing bot-placed from manual orders, trading endpoints require a `Personal: Write` app permission, and Saxo documents a self-service credential path for direct retail clients. Personal algorithmic trading on one's own account is an anticipated, supported use case.

## User Stories

### US1 — Connect a fund to its Saxo SIM book (P1)

As a fund owner, I deploy a paper fund whose broker is Saxo SIM, and the engine reads my actual SIM positions and cash from OpenAPI, so the pre-session reconciliation compares the ledger against the broker's authoritative book and refuses to trade on any unexplained mismatch.

**Acceptance**: positions and available cash come from `GET /port/v1/positions` and `GET /port/v1/balances`; tickers map to Saxo UICs via the instruments search; a ticker missing from the SIM instrument universe refuses the session before any order; the account's currency must match the fund's base currency or deployment is refused.

### US2 — Execute session orders with actual SIM fills (P2)

As a fund owner, when a session decides to trade, the adapter places market orders on the SIM environment and records fills with Saxo's actual simulated fill prices, so the ledger reflects what really happened on the broker.

**Acceptance**: `place_order` places a market order (`POST /trade/v2/orders`, `OrderType: Market`, `DayOrder`, `ManualOrder: false`), treats HTTP 200 with a populated `ErrorInfo` as failure, detects the fill via order-correlated execution records (order leaves open orders → executed quantity/price read from the transaction/execution data tied to that OrderId, correct for increases, reductions, and full exits), returns a complete `Fill` or raises, and never blind-retries an order POST (Saxo rejects identical duplicates within 15 s with 409 anyway).

### US3 — Credentials via 1Password, tokens handled safely (P2)

As a fund owner, my OpenAPI app secret and OAuth refresh token are referenced through 1Password `op://` secrets and resolved at startup, so no secret is ever stored in plaintext files, logged, or written to ledgers — and the rotating refresh token is written back to 1Password after each refresh so restarts survive.

**Acceptance**: `op://` references resolve via the 1Password CLI; missing credentials fail with an error naming the variable, never the value; after every token refresh the new refresh token is persisted back to the 1Password item; no secret material appears in logs, errors, events, or the ledger.

### US4 — Broker selection per fund mandate (P3)

As a fund owner, I choose `broker: paper | saxo` in the fund mandate at deploy time, existing funds stay byte-identical, and the TUI/status show which broker a fund uses.

**Acceptance**: `FundSpec` validates the literal; the key is popped from serialization when it equals the default `paper`; deployed funds are immutable; `redo` refuses non-paper brokers.

## Functional Requirements

- **FR-001** The adapter implements the existing `Broker` protocol (`positions()`, `cash()`, `place_order()`) structurally, reusing `Order`/`Fill`/`Position` unchanged.
- **FR-002** The adapter targets the SIM environment only: REST base `https://gateway.saxobank.com/sim/openapi`, auth server `https://sim.logonvalidation.net`. The live gateway/auth URLs must not appear in code or configuration.
- **FR-003** `place_order` fills completely and returns a `Fill` with the broker's actual price, or raises. No partial fills returned, no silent drops.
- **FR-004** OAuth2 access tokens (~20 min) are refreshed proactively; refresh tokens are single-use and rotate on every refresh, so the latest refresh token must be persisted (to 1Password) immediately after each refresh. Because fund runners are separate processes that may share the same 1Password item, refresh is coordinated cross-process (lock keyed by the secret reference) and the latest refresh token is re-read from 1Password immediately before every refresh attempt, so a process that loses the race picks up the winner's rotated token instead of a spent one. If re-authentication is required, the adapter raises a clear error instructing the interactive login rather than retrying.
- **FR-005** The external broker's book is authoritative; the existing pre-session reconciliation runs unchanged and refuses the session on unexplained mismatch. `cash()` reports the **accounting cash balance** (`CashBalance`) so equity/NAV and ledger reconciliation stay correct; buying power (`CashAvailableForTrading`) is consulted separately for order affordability. Sells are sized against positions as reported by the broker.
- **FR-005a** At startup the adapter validates that the discovered trading account's currency is compatible with the fund's base currency (the currency the mandate's capital is denominated in); a mismatch (e.g. EUR account, USD-denominated mandate) refuses deployment — no silent FX conversion is attempted in this feature.
- **FR-006** The fund's universe is validated against `GET /ref/v1/instruments` (UIC + AssetType resolution, cached) before the first order of a session; untradable or missing tickers refuse the session.
- **FR-007** Secrets (app secret, refresh token) are referenced as 1Password `op://` items resolved via the 1Password CLI at startup; plaintext env values remain supported for non-secret config only.
- **FR-008** Order placement respects Saxo's limits: at most 1 order placement per second, a unique `x-request-id` per attempt, and no automatic re-POST of a possibly-received order.
- **FR-009** Secrets never appear in logs, exception messages, the ledger, events, or any persisted file outside 1Password.
- **FR-010** Broker selection is per-fund in the mandate, fixed at deploy time; serialization stays byte-compatible with existing funds.
- **FR-011** Fill detection: after placing, poll the open-order endpoint until the order leaves it — disappearance triggers **inspection, not fill establishment**. The returned `Fill` must carry order-correlated executed quantity and price read from the execution/transaction records tied to that OrderId (covering increases, reductions, and full exits — a reducing sale keeps the position's acquisition cost, and a full exit leaves no position to read from). A bounded deadline raises with guidance.
- **FR-012** Quantities are rounded to the instrument's tradable precision (LotSize when available); fractional-share support for US stocks on SIM is verified empirically during the smoke test — if rejected, the adapter refuses rather than silently rounding up exposure.
- **FR-013** yfinance remains the market-data path; OpenAPI price endpoints are not used (SIM provides no live stock prices anyway).
- **FR-014** Saxo mandates must use a cadence that fires while the relevant market is open: the daily cadence's 00:05 New York turn (when daily funds look for yesterday's close) is outside market hours, so `saxo` funds with a daily cadence are refused at deploy/validation time with guidance to pick an in-market intraday cadence.

## Edge Cases

- **Token expires mid-session** → proactive refresh every ~15 min; on refresh failure raise a re-auth error; never loop on 401.
- **Two funds share the 1Password item** → refresh is serialized by a cross-process lock keyed on the secret reference; each refresh re-reads the latest refresh token first, so the loser of a rotation race re-reads the winner's token instead of failing on a spent one.
- **SIM account reset** (Saxo allows self-service resets) → reconciliation reports the mismatch and refuses; the fund owner decides.
- **Market closed** → Saxo rejects synchronously (`MarketClosed` error code expected; verify on SIM); the session halts with the broker's message. Deploy-time validation (FR-014) keeps normal cadences in-market so this only surfaces on manual/off-schedule runs.
- **Instrument not tradable / not found** → universe validation refuses before ordering.
- **Duplicate-order window** → identical POSTs within 15 s get 409; the adapter never re-POSTs, it inspects state instead.
- **Session capability collision** → the adapter stays at the default `OrdersOnly`/`Standard` session level so it never demotes the user's SaxoTraderGO session.

## Assumptions

- The user creates a Saxo SIM account (self-service, no funding) and registers an OpenAPI app on the Developer Portal (SIM environment, `Personal: Write` trading permission).
- Periodic interactive re-authentication (practically ~weekly) is acceptable for a paper fund; fully unattended month-long operation is explicitly out of scope.
- Live (real-money) trading is out of scope; the live gateway is unreachable by construction.
- 1Password CLI is available in both host and Docker contexts (desktop unlock / service-account token).

## Success Criteria

- **SC-1**: A deployed `saxo` fund reads its SIM positions/cash and reconciles against the ledger before trading.
- **SC-2**: A session's orders appear in the SIM account with matching instruments/quantities, and the ledger records Saxo's actual simulated fill prices.
- **SC-3**: No secret material is ever found in logs, errors, or persisted files (tested).
- **SC-4**: Existing paper funds run byte-identically (no behavior or file changes).
- **SC-5**: The full test suite stays green apart from the 6 documented Windows baseline failures, with all adapter tests network-free.