# Tasks: Saxo OpenAPI Broker Adapter (SIM)

**Feature**: 003-saxo-broker-adapter | **Input**: spec.md, plan.md, research.md, data-model.md, contracts/saxo-adapter.md, quickstart.md
**Tests requested**: yes (constitution III - test-first, co-located, network-free)

## Phase 1: Setup

- [x] T001 Create `hedge_fund/brokers/saxo.py` module skeleton with SIM-only constants (`BASE_URL = "https://gateway.saxobank.com/sim/openapi"`, `AUTH_URL = "https://sim.logonvalidation.net"`) and error taxonomy classes `SaxoAuthError`, `SaxoOrderError`, `SaxoReconcileError` in hedge_fund/brokers/saxo.py
- [x] T002 [P] Add fake transport + fake clock test doubles in hedge_fund/brokers/test_saxo_doubles.py (Transport protocol recording calls, scripted responses; FakeClock for pacer/token manager)

## Phase 2: Foundational (blocking)

- [x] T003 Test-first: secrets provider tests in hedge_fund/secrets/test_provider.py: `op://` reference resolution via `op read`, missing reference -> error naming the variable never the value, sanitized failure messages, sensitive write-back via JSON template on stdin with no token in argv, persistent fake item and re-read verification
- [x] T004 Implement `hedge_fund/secrets/provider.py` (resolve + write-back per T003) in hedge_fund/secrets/provider.py
- [x] T005 Test-first: token manager refresh + rotation + coordination tests in hedge_fund/brokers/test_saxo_tokens.py (proactive refresh at <120 s margin; rotated token persisted before access token use; reference-keyed atomic lock and latest-token re-read; same-host manager race; shared mount configured via `SAXO_REFRESH_LOCK_DIR`; bounded lock timeout with owner context and no stale-lock stealing; refresh failure -> SaxoAuthError)
- [x] T006 Implement `TokenManager` in hedge_fund/brokers/saxo.py (POST {AUTH_URL}/token with grant_type=refresh_token, Basic app auth, lock + re-read + 1Password write-back via secrets provider, state machine UNAUTHENTICATED->AUTHORIZED->REAUTH_REQUIRED)
- [x] T007 [P] Test-first: pacer tests in hedge_fund/brokers/test_saxo_pacer.py (orders class >=1.0 s spacing under FakeClock, other classes unpaced)
- [x] T008 Implement `Pacer` in hedge_fund/brokers/saxo.py (per-endpoint-class min interval, fake-clock friendly wait)
- [x] T009 [P] Test-first: redaction tests in hedge_fund/brokers/test_saxo_redaction.py (no app secret/access/refresh token material in client logs, exception messages, or repr under any failure path)
- [x] T010 [P] Test-first: instrument resolution tests in hedge_fund/brokers/test_saxo_universe.py (search `Identifier`/`ExchangeId`; deterministic supported US exchange selection; details require tradable, `Exchange.CountryCode=US`, `CurrencyCode=USD`, and Market order support; cache ~1 h with later-session expiry revalidation; missing/non-US listing refuses)

## Phase 3: US1 - Connect fund to Saxo SIM book (P1)

**Goal**: A deployed `saxo` fund reads SIM positions/cash and reconciles before trading.
**Independent test**: with a scripted transport, `SaxoBroker.positions()`/`cash()` return values mapped from fixture payloads; currency mismatch refuses at startup; reconciliation refuses on mismatch.

- [x] T011 [P] [US1] Test-first: client book-read tests in hedge_fund/brokers/test_saxo_client.py (accounts/me -> first `Active` USD account with `LegalAssetTypes` including Stock; positions and balances use scoped endpoints with ClientKey+AccountKey; `CashBalance` for `cash()`, `CashAvailableForTrading` only for affordability)
- [x] T012 [US1] Implement `SaxoClient` book reads + startup discovery with currency validation in hedge_fund/brokers/saxo.py (bearer auth on every call, one 401->refresh->retry then SaxoAuthError)
- [x] T013 [US1] Implement universe validation + UIC cache in hedge_fund/brokers/saxo.py (FR-006: two-call resolution per T010, validate full universe each session and refresh expired entries)
- [x] T014 [US1] Wire reconciliation to SaxoBroker book in hedge_fund/paper/tick.py (external book authoritative; `cash()` = accounting CashBalance so ledger comparison is apples-to-apples; mismatch refuses session - reuse existing reconcile path)

## Phase 4: US2 - Order execution with actual SIM fills (P2)

**Goal**: Session orders place market orders and record Saxo actual simulated fills.
**Independent test**: scripted transport: POST -> OrderId, open-order poll -> gone, transactions -> order-correlated fill; Fill matches fixture for increase, reduction, and full-exit scenarios; ErrorInfo/409/deadline paths raise.

- [x] T015 [US2] Test-first: order placement tests in hedge_fund/brokers/test_saxo_orders.py (order payload/request id/errors/deadline; transactions filtered by account/client/date/UIC, paginated, nested `Trades[].OrderId` correlated; increases/reductions/full exits; complete-fill-or-raise; buying power checked before placement)
- [x] T016 [US2] Implement `SaxoBroker.place_order` + order-correlated fill detection in hedge_fund/brokers/saxo.py (pacer wait before POST, body inspection not status-only, poll open order until gone, read executed quantity/price from transactions tied to the OrderId, bounded deadline, `Fill(ticker, side, quantity, price)` construction)
- [x] T017 [US2] Test-first: quantity precision tests in hedge_fund/brokers/test_saxo_precision.py (LotSize rounding down in copied orders; missing/null LotSize fallback; suppress untradable sub-lot rebalance dust; submitted order remains complete-fill-or-raise; multi-session e2e verifies 3.83→3 fill and continued fund operation; de-risking rounded sells proceed; filters that worsen position/gross exposure refuse before submission)
- [x] T018 [US2] Implement quantity precision handling in hedge_fund/brokers/saxo.py and post-filter projected-risk validation in hedge_fund/pipeline/stages.py (copy orders rounded down to tradable lot multiples; missing/null `LotSize` defaults to one; omit below-lot dust; record adjusted order in ledger; permit post-filter breaches only when filtered risk does not worsen current-book risk)

## Phase 5: US3 - Secrets via 1Password, token safety (P2)

**Goal**: No secret ever in plaintext/logs/ledger; rotating refresh token survives restarts and concurrent fund runners.
**Independent test**: with fake `op` runner, references resolve at startup; missing ref errors name the variable; write-back called after every refresh under the coordination lock; grep-style redaction tests pass.

- [x] T019 [US3] Test-first: startup-secret and interactive-auth lock tests in hedge_fund/secrets/test_saxo_secrets.py and hedge_fund/brokers/test_saxo_auth.py (all env references required; refresh token read under lock on first authenticated request; auth-code exchange and token write-back share the reference lock; missing references are sanitized)
- [x] T020 [US3] Implement Saxo credential wiring in hedge_fund/brokers/saxo.py + interactive auth helper `hedge_fund/brokers/saxo_auth.py` (auth-code + PKCE exchange and write-back under the refresh-reference lock; cleanup failure after successful persistence is logged and recoverable)

## Phase 6: US4 - Broker selection, deployment, and routing (P3)

**Goal**: `broker: paper|saxo` end to end: mandate -> deploy -> factory-routed tick/runner -> TUI; existing funds byte-identical.
**Independent test**: FundSpec/DeployedFund round-trip golden test (paper fund yaml byte-identical); factory builds SaxoBroker for saxo funds; saxo deployment creates no paper book; redo refuses saxo; e2e: selecting Saxo deploys and runs a session through the external adapter.

- [x] T021 [US4] Test-first: FundSpec broker field + cadence/window validation tests in hedge_fund/fund/test_spec_broker.py (paper defaults/serialization byte-compatible; Saxo omitted costs default zero, explicit costs honored; non-minute cadence and windows outside 09:30–15:59 refused; omitted Saxo window defaults to 09:30–15:59; immutable after deploy)
- [x] T022 [US4] Test-first: deployment + factory routing tests in hedge_fund/paper/test_deployed_broker.py (`DeployedFund.broker` matches FundSpec; Saxo deploy skips local broker book; factory routes paper/Saxo; fixed USD policy rejects currency override; broker startup validates actual account; continuous runner reuses Saxo broker/token manager; redo refuses external broker)
- [x] T023 [US4] Test-first: TUI broker selector tests in hedge_fund/tui/test_builder_broker.py (fund setup option, summary, cadence guard, Saxo regular-hours window validation); rail includes Broker and Tickers steps
- [x] T024 [US4] End-to-end test: builder deploys Saxo and runs fake SIM book/order/fill/ledger path; multi-session 3.83-share drift rounds down to 3, fills completely, remains ledger-consistent, and fund continues

> T023–T024 runtime validation passes in the designated non-Ollama validation venv.

## Phase 7: Polish

- [x] T025 [P] Update quickstart smoke-test steps in specs/003-saxo-broker-adapter/quickstart.md to match implemented CLI (`saxo_auth` module name, env var names, cadence guidance) - doc-only
- [ ] T026 Run style gate (black/isort/flake8) and chunked full pytest (`hedge_fund/brokers`, `hedge_fund/secrets`, `hedge_fund/fund`, `hedge_fund/paper`, then full suite) - expect green except the 6 documented Windows baseline failures

> T026 partial (2026-10-30): changed Python files pass Black, isort, and Flake8; the 41-test affected regression set passed. Latest broker/secrets suites: 74 passed; fund suite: 85 passed. The paper suite reported 66 passed and 3 known Windows failures; the latest runner-module run reported 9 passed and 2 known Windows failures, while the two Saxo runner regressions passed. Other completed chunks reported data/pipeline 185 passed and 36 skipped, portfolio/risk/scorecard/signals/strategies/validation 132 passed, and non-Ollama LLM tests 147 passed. An aggregate non-Ollama run was interrupted at 88% (782 passed, 36 skipped; known Windows failures included), and the TUI runner-control test was interrupted before producing a result. T026 remains open because the aggregate validation did not complete.

## Dependencies

- T001 -> T002 -> T003-T010 (foundational; secrets provider T003/T004 before token manager T005/T006) -> US1 (T011-T014) -> US2 (T015-T018) -> US3 (T019-T020) -> US4 (T021-T024) -> Polish (T025-T026)
- US1 blocks US2 (orders need universe validation + book reads)
- US3 depends on T004/T006 (provider + token write-back); US4 depends on all prior (factory wiring, e2e)
- Parallel: T002, T007, T009, T010, T011, T017, T019, T021, T025 are test-first or doc tasks on separate files

## Implementation Strategy

- MVP = US1 (book reads + reconciliation) - a saxo fund can deploy, read its SIM book, and refuse safely.
- US2 adds trading; US3 hardens secrets; US4 completes configuration, deployment, and routing end to end.
- Every implementation task is preceded by its failing test (constitution III); all tests network-free via the fake transport/clock/op runner (constitution II/IV).
