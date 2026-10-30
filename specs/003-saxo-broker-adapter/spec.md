# Spec: Saxo OpenAPI Broker Adapter (SIM)

**Feature Branch**: `003-saxo-broker-adapter` (app-managed worktree; branch creation skipped, numbering applied)
**Created**: 2026-10-30
**Status**: Draft (re-targeted from Trading 212 — see Context)

## Context: why Saxo and not Trading 212

The original target, Trading 212, prohibits in its API terms: *"You are expressly prohibited from using our API for Algorithmic Trading purposes..."* — which covers this engine's automated order placement even with per-decision human approval. Saxo Bank's OpenAPI is built for programmatic trading: order payloads carry a `ManualOrder` flag distinguishing bot-placed from manual orders, trading endpoints require a `Personal: Write` app permission, and Saxo documents a self-service credential path for direct retail clients. Personal algorithmic trading on one's own account is an anticipated, supported use case.

## User Stories

### US1 — Connect a fund to its Saxo SIM book (P1)

As a fund owner, I deploy a paper fund whose broker is Saxo SIM, and the engine reads my actual SIM positions and cash from OpenAPI, so the pre-session reconciliation compares the ledger against the broker's authoritative book and refuses to trade on any unexplained mismatch.

**Acceptance**: positions and balances come from `GET /port/v1/positions` and `GET /port/v1/balances`, scoped by `ClientKey` and `AccountKey`; tickers map to Saxo UICs via instrument search and must be US-listed USD stocks; a ticker missing from the SIM instrument universe refuses the session before any order; account currency mismatch refuses broker startup before trading.

### US2 — Execute session orders with actual SIM fills (P2)

As a fund owner, when a session decides to trade, the adapter places market orders on the SIM environment and records fills with Saxo's actual simulated fill prices, so the ledger reflects what really happened on the broker.

**Acceptance**: `place_order` places a market order (`POST /trade/v2/orders`, `OrderType: Market`, `DayOrder`, `ManualOrder: false`), treats HTTP 200 with a populated `ErrorInfo` as failure, detects the fill via order-correlated execution records (order leaves open orders → executed quantity/price read from the transaction/execution data tied to that OrderId, correct for increases, reductions, and full exits), returns a complete `Fill` or raises, and never blind-retries an order POST (Saxo rejects identical duplicates within 15 s with 409 anyway).

### US3 — Credentials via 1Password, tokens handled safely (P2)

As a fund owner, my OpenAPI app secret and OAuth refresh token are referenced through 1Password `op://` secrets, so no secret is stored in plaintext files, logged, or written to ledgers — and the rotating refresh token is written back to 1Password after each refresh so restarts survive.

**Acceptance**: app credentials resolve via the 1Password CLI at broker startup; the refresh-token reference is read under the refresh lock on initial authorization and each refresh; missing references fail with an error naming the variable, never the value; each rotated token is persisted before its access token is exposed; no secret material appears in logs, errors, events, or the ledger.

### US4 — Broker selection per fund mandate (P3)

As a fund owner, I choose `broker: paper | saxo` in the fund mandate at deploy time, existing funds stay byte-identical, and the TUI/status show which broker a fund uses.

**Acceptance**: `FundSpec` validates the literal; the key is popped from serialization when it equals the default `paper`; deployed funds are immutable; `redo` refuses non-paper brokers.

## Functional Requirements

- **FR-001** The adapter implements the existing `Broker` protocol (`positions()`, `cash()`, `place_order()`) structurally, reusing `Order`/`Fill`/`Position` unchanged.
- **FR-002** The adapter targets the SIM environment only: REST base `https://gateway.saxobank.com/sim/openapi`, auth server `https://sim.logonvalidation.net`. The live gateway/auth URLs must not appear in code or configuration.
- **FR-003** Every submitted `place_order` fills completely and returns a `Fill` with the broker's actual price, or raises. Untradable sub-lot rebalance dust is filtered before submission; submitted orders are never silently dropped or partially returned.
- **FR-004** OAuth2 access tokens (~20 min) are refreshed proactively; refresh tokens are single-use and rotate on every refresh, so the latest refresh token must be persisted (to 1Password) immediately after each refresh. Refreshes and interactive authorization-code exchange/write-back are serialized by a lock keyed by the secret reference; refresh re-reads the latest token before each attempt. Lock acquisition times out after 90 seconds with owner context; contention remains retryable and does not require interactive login. Locks are never stolen automatically. Host/container coordination requires `SAXO_REFRESH_LOCK_DIR` to point to the same mounted filesystem path in both environments; without it, the default lock coordinates only processes sharing that host temp directory. A process crash can leave a lock directory; remove it only after confirming its owner is no longer refreshing. Cleanup failure after successful persistence is logged for verified recovery and does not discard the newly authorized access token. If re-authentication is required for another refresh failure, the adapter raises a clear error instructing the interactive login rather than retrying; running fund processes must restart after interactive re-authentication.
- **FR-005** The external broker's book is authoritative; the existing pre-session reconciliation runs unchanged and refuses the session on unexplained mismatch. Every positions page must contain an explicit list-valued `Data`; all pages are read with the same account/client scope or the entire snapshot fails. `cash()` reports the **accounting cash balance** (`CashBalance`) so equity/NAV and ledger reconciliation stay correct; buying power (`CashAvailableForTrading`) is consulted separately for order affordability. Sells are sized against positions as reported by the broker.
- **FR-005a** The app's mandate convention is USD. Saxo startup requires an active account with Stock legal asset access and USD currency; scoped balances must also report USD. Mismatches refuse before any order; no FX conversion is attempted.
- **FR-006** The fund's universe is validated against `GET /ref/v1/instruments` and instrument details (UIC + AssetType resolution, cached for at most 3600 seconds) before each session; reused broker instances revalidate whenever a cached entry expires. Only deterministic US exchange listings whose details report `CountryCode: US` and `CurrencyCode: USD` are accepted. Untradable or missing tickers refuse the session.
- **FR-007** Secrets (app secret, refresh token) are referenced as 1Password `op://` items; app credentials resolve via the 1Password CLI at startup, while the refresh token resolves under its lock when first needed and before each refresh. Refresh-token write-back honors both `op://vault/item/field` and section-qualified `op://vault/item/section/field` references. Plaintext env values remain supported for non-secret config only.
- **FR-008** Order placement respects Saxo's limits: at most 1 order placement per second, with pacing after token acquisition; a unique `x-request-id` per attempt; and no automatic re-POST of a possibly-received order.
- **FR-009** Secrets never appear in logs, exception messages, the ledger, events, or any persisted file outside 1Password.
- **FR-010** Broker selection is per-fund in the mandate, fixed at deploy time; serialization stays byte-compatible with existing funds.
- **FR-011** Fill detection: after placing, poll the open-order endpoint until the order leaves it — disappearance triggers **inspection, not fill establishment**. The returned `Fill` must carry order-correlated executed quantity and price read from the execution/transaction records tied to that OrderId (covering increases, reductions, and full exits — a reducing sale keeps the position's acquisition cost, and a full exit leaves no position to read from). The execution deadline is checked before each transaction page and raises with guidance when it expires.
- **FR-012** Orders are copied with quantity rounded down to the instrument's tradable lot multiple; missing/null `LotSize` defaults to one share; orders below one lot are filtered. After broker filtering, projected position and gross exposure are checked before submission. A post-filter limit breach is rejected if the candidate worsens that exposure versus the current book; an already-over-limit exposure may proceed only when it does not worsen. Saxo orders retain the original sell-first order where safe, but are reordered as needed so each projected intermediate book, at the sizing marks, satisfies the same limits; if no safe sequence exists the basket is refused before submission. Actual fills and prices may differ from projections. The adapter never rounds order quantity up, and every submitted order must fill completely or raise. Ledger orders record the adjusted submitted quantity.
- **FR-013** yfinance remains the market-data path; OpenAPI price endpoints are not used (SIM provides no live stock prices anyway).
- **FR-014** Saxo mandates require minute cadence within regular US market hours. The daily cadence's 00:05 New York turn is outside market hours, so non-minute Saxo mandates are refused. Saxo minute windows start no earlier than 09:30 ET and end no later than 15:59 ET, before the 16:00 close; omitted Saxo windows default to 09:30–15:59 ET. The unattended runner checks the 16:00 ET cutoff immediately before every order POST attempt, including an authorized retry. Completed fills are recorded and unsent orders are identified as deferred; the next valid bar recomputes from the broker book rather than replaying stale quantities, and a new decision still requires approval when configured. Confirmed Saxo fills are journaled before the next order, and other failures halt the fund. Explicit out-of-window Saxo mandates are refused by validation and the TUI; paper defaults remain unchanged.
- **FR-015** When `broker: saxo` omits `costs`, spread and commission default to zero because SIM fills already carry simulated execution prices; explicitly supplied costs remain unchanged. Paper defaults and serialization remain byte-compatible.

## Edge Cases

- **Token expires mid-session** → proactive refresh every ~15 min; on refresh failure raise a re-auth error; never loop on 401.
- **Two funds share the 1Password item** → refresh is serialized by a secret-reference-keyed lock when both processes share the same lock directory; each refresh re-reads the latest token first. Stale lock directories require operator cleanup after process-state verification.
- **SIM account reset** (Saxo allows self-service resets) → reconciliation reports the mismatch and refuses; the fund owner decides.
- **Market closed** → Saxo rejects synchronously (`MarketClosed` error code expected; verify on SIM); the session halts with the broker's message. FR-014 restricts configured Saxo minute windows to 09:30–15:59 ET; this only surfaces on manual/off-schedule runs.
- **Instrument not tradable / not found** → universe validation refuses before ordering.
- **Duplicate-order window** → identical POSTs within 15 s get 409; the adapter never re-POSTs, it inspects state instead.
- **Session capability collision** → the adapter stays at the default `OrdersOnly`/`Standard` session level so it never demotes the user's SaxoTraderGO session.

## Assumptions

- The user creates a Saxo SIM account (self-service, no funding) and registers an OpenAPI app on the Developer Portal (SIM environment, `Personal: Write` trading permission).
- Periodic interactive re-authentication (practically ~weekly) is acceptable for a paper fund; fully unattended month-long operation is explicitly out of scope.
- Live (real-money) trading is out of scope; the live gateway is unreachable by construction.
- 1Password CLI is available in both host and Docker contexts (desktop unlock / service-account token).
- Host/container refresh coordination is enabled only when both use the same mounted filesystem path through `SAXO_REFRESH_LOCK_DIR`; that filesystem must provide atomic directory creation.

## Success Criteria

- **SC-1**: A deployed `saxo` fund reads its SIM positions/cash and reconciles against the ledger before trading.
- **SC-2**: A session's orders appear in the SIM account with matching instruments/quantities, and the ledger records Saxo's actual simulated fill prices.
- **SC-3**: No secret material is ever found in logs, errors, or persisted files (tested).
- **SC-4**: Existing paper funds run byte-identically (no behavior or file changes).
- **SC-5**: The full test suite stays green apart from the 6 documented Windows baseline failures, with all adapter tests network-free.