# Tasks: Saxo OpenAPI Broker Adapter (SIM)

**Feature**: 003-saxo-broker-adapter | **Input**: spec.md, plan.md, research.md, data-model.md, contracts/saxo-adapter.md, quickstart.md
**Tests requested**: yes (constitution III - test-first, co-located, network-free)

## Phase 1: Setup

- [ ] T001 Create `hedge_fund/brokers/saxo.py` module skeleton with SIM-only constants (`BASE_URL = "https://gateway.saxobank.com/sim/openapi"`, `AUTH_URL = "https://sim.logonvalidation.net"`) and error taxonomy classes `SaxoAuthError`, `SaxoOrderError`, `SaxoReconcileError` in hedge_fund/brokers/saxo.py
- [ ] T002 [P] Add fake transport + fake clock + fake `op` runner test doubles in hedge_fund/brokers/test_saxo_doubles.py (Transport protocol recording calls, scripted responses; FakeClock for pacer/token manager; FakeOp for secrets provider)

## Phase 2: Foundational (blocking)

- [ ] T003 Test-first: secrets provider tests in hedge_fund/secrets/test_provider.py (**the `hedge_fund/secrets/` package does not exist yet - create it**): `op://` reference resolution via `op read`, missing reference -> error naming the variable never the value, sanitized failure messages, write-back via `op item edit` for rotating tokens, write-back failure raises
- [ ] T004 Implement `hedge_fund/secrets/provider.py` (resolve + write-back per T003) in hedge_fund/secrets/provider.py
- [ ] T005 Test-first: token manager refresh + rotation + coordination tests in hedge_fund/brokers/test_saxo_tokens.py (proactive refresh at <120 s margin; single-use rotating refresh token persisted to 1Password BEFORE new access token used; **cross-process lock keyed by secret reference + re-read latest token before every refresh attempt; two managers sharing one item - loser of rotation race re-reads winner token and succeeds**; refresh failure -> SaxoAuthError with re-auth guidance, no retry loop)
- [ ] T006 Implement `TokenManager` in hedge_fund/brokers/saxo.py (POST {AUTH_URL}/token with grant_type=refresh_token, Basic app auth, lock + re-read + 1Password write-back via secrets provider, state machine UNAUTHENTICATED->AUTHORIZED->REAUTH_REQUIRED)
- [ ] T007 [P] Test-first: pacer tests in hedge_fund/brokers/test_saxo_pacer.py (orders class >=1.0 s spacing under FakeClock, other classes unpaced)
- [ ] T008 Implement `Pacer` in hedge_fund/brokers/saxo.py (per-endpoint-class min interval, fake-clock friendly wait)
- [ ] T009 [P] Test-first: redaction tests in hedge_fund/brokers/test_saxo_redaction.py (no app secret/access/refresh token material in client logs, exception messages, or repr under any failure path)
- [ ] T010 [P] Test-first: instrument resolution tests in hedge_fund/brokers/test_saxo_universe.py (**two distinct calls with distinct response shapes**: search `GET /ref/v1/instruments?Keywords=...` -> Identifier/Uic + ExchangeId; details `GET /ref/v1/instruments/details/{Uic}/{AssetType}` -> IsTradable/LotSize/SupportedOrderTypes; cache ~1 h TTL; untradable/missing ticker -> SaxoReconcileError before any order; search response lacking tradability fields must not be treated as validation data)

## Phase 3: US1 - Connect fund to Saxo SIM book (P1)

**Goal**: A deployed `saxo` fund reads SIM positions/cash and reconciles before trading.
**Independent test**: with a scripted transport, `SaxoBroker.positions()`/`cash()` return values mapped from fixture payloads; currency mismatch refuses at startup; reconciliation refuses on mismatch.

- [ ] T011 [P] [US1] Test-first: client book-read tests in hedge_fund/brokers/test_saxo_client.py (users/me -> ClientKey; accounts/me -> **first trading account whose Currency matches the fund base currency, mismatch/none-compatible -> startup refusal**; positions/me grouped by NetPositionId mapped to shared `Position(ticker, shares)` with signed Amount; balances/me -> **`CashBalance` for `cash()`**, `CashAvailableForTrading` exposed separately for affordability only)
- [ ] T012 [US1] Implement `SaxoClient` book reads + startup discovery with currency validation in hedge_fund/brokers/saxo.py (bearer auth on every call, one 401->refresh->retry then SaxoAuthError)
- [ ] T013 [US1] Implement universe validation + UIC cache in hedge_fund/brokers/saxo.py (FR-006: two-call resolution per T010, validate full fund universe before first order of a session)
- [ ] T014 [US1] Wire reconciliation to SaxoBroker book in hedge_fund/paper/tick.py (external book authoritative; `cash()` = accounting CashBalance so ledger comparison is apples-to-apples; mismatch refuses session - reuse existing reconcile path)

## Phase 4: US2 - Order execution with actual SIM fills (P2)

**Goal**: Session orders place market orders and record Saxo actual simulated fills.
**Independent test**: scripted transport: POST -> OrderId, open-order poll -> gone, transactions -> order-correlated fill; Fill matches fixture for increase, reduction, and full-exit scenarios; ErrorInfo/409/deadline paths raise.

- [ ] T015 [US2] Test-first: order placement tests in hedge_fund/brokers/test_saxo_orders.py (payload shape: Uic/AssetType Stock/Amount shares/BuySell/OrderType Market/DayOrder/ManualOrder false; unique x-request-id per attempt; HTTP 200 with ErrorInfo -> SaxoOrderError carrying Saxo ErrorCode; 409 -> inspect state, never re-POST; poll-until-gone with 120 s deadline -> SaxoOrderError; **fill read from order-correlated transaction/execution records tied to the OrderId - fixtures cover an increase (position grows), a reduction (position shrinks but OpenPrice unchanged), and a full exit (no position row remains); position state alone never establishes a fill**; fill-completely-or-raise; affordability checked against CashAvailableForTrading before placement)
- [ ] T016 [US2] Implement `SaxoBroker.place_order` + order-correlated fill detection in hedge_fund/brokers/saxo.py (pacer wait before POST, body inspection not status-only, poll open order until gone, read executed quantity/price from transactions tied to the OrderId, bounded deadline, `Fill(ticker, side, quantity, price)` construction)
- [ ] T017 [US2] Test-first: quantity precision tests in hedge_fund/brokers/test_saxo_precision.py (LotSize rounding from instrument **details** response; fractional rejection -> refuse, never round up exposure - FR-012)
- [ ] T018 [US2] Implement quantity precision handling in hedge_fund/brokers/saxo.py (round to tradable precision; refuse when rounding would change exposure direction/size materially)

## Phase 5: US3 - Secrets via 1Password, token safety (P2)

**Goal**: No secret ever in plaintext/logs/ledger; rotating refresh token survives restarts and concurrent fund runners.
**Independent test**: with fake `op` runner, references resolve at startup; missing ref errors name the variable; write-back called after every refresh under the coordination lock; grep-style redaction tests pass.

- [ ] T019 [US3] Test-first: startup secret resolution tests in hedge_fund/secrets/test_saxo_secrets.py (SAXO_APP_KEY_REF/SAXO_APP_SECRET_REF/SAXO_REFRESH_TOKEN_REF resolved via provider; missing -> error naming variable, never value; redirect URI from non-secret env)
- [ ] T020 [US3] Implement Saxo credential wiring in hedge_fund/brokers/saxo.py + interactive auth helper `hedge_fund/brokers/saxo_auth.py` (auth-code + PKCE in browser for first login, stores refresh token into the 1Password item)

## Phase 6: US4 - Broker selection, deployment, and routing (P3)

**Goal**: `broker: paper|saxo` end to end: mandate -> deploy -> factory-routed tick/runner -> TUI; existing funds byte-identical.
**Independent test**: FundSpec/DeployedFund round-trip golden test (paper fund yaml byte-identical); factory builds SaxoBroker for saxo funds; saxo deployment creates no paper book; redo refuses saxo; e2e: selecting Saxo deploys and runs a session through the external adapter.

- [ ] T021 [US4] Test-first: FundSpec broker field + cadence validation tests in hedge_fund/fund/test_spec_broker.py (Literal validation; popped-on-default serialization byte-compat golden file; **saxo + daily cadence refused at validation with in-market-cadence guidance** - FR-014; immutable after deploy) + implement in hedge_fund/fund/spec.py
- [ ] T022 [US4] Test-first: deployment + factory routing tests in hedge_fund/paper/test_deployed_broker.py (**`DeployedFund.broker` widened to Literal["paper","saxo"] consistently with FundSpec; saxo deployment skips `PaperBroker.create` - no local broker.json book; `hedge_fund/brokers/factory.py` `build_broker(deployed)` routes paper->PaperBroker, saxo->SaxoBroker with resolved secrets; `paper/tick.py` line ~283 and the runner construct brokers only via the factory; redo refuses non-paper brokers; missing secrets fail before trading**) + implement in hedge_fund/paper/deployed.py, hedge_fund/brokers/factory.py, hedge_fund/paper/tick.py
- [ ] T023 [US4] Test-first: TUI broker selector tests in hedge_fund/tui/test_builder_broker.py (fund-setup broker option paper|saxo alongside approval gate at hedge_fund/tui/builder.py ~line 471; summary line shows choice; saxo+daily cadence blocked in UI) + implement in hedge_fund/tui/builder.py
- [ ] T024 [US4] End-to-end test: selecting Saxo in the builder deploys a saxo fund and runs a session through the external adapter (fake transport) in hedge_fund/paper/test_saxo_e2e.py - proves mandate -> deploy -> factory routing -> book read -> order -> fill -> ledger recording

## Phase 7: Polish

- [ ] T025 [P] Update quickstart smoke-test steps in specs/003-saxo-broker-adapter/quickstart.md to match implemented CLI (`saxo_auth` module name, env var names, cadence guidance) - doc-only
- [ ] T026 Run style gate (black/isort/flake8) and chunked full pytest (`hedge_fund/brokers`, `hedge_fund/secrets`, `hedge_fund/fund`, `hedge_fund/paper`, then full suite) - expect green except the 6 documented Windows baseline failures

## Dependencies

- T001 -> T002 -> T003-T010 (foundational; secrets provider T003/T004 before token manager T005/T006) -> US1 (T011-T014) -> US2 (T015-T018) -> US3 (T019-T020) -> US4 (T021-T024) -> Polish (T025-T026)
- US1 blocks US2 (orders need universe validation + book reads)
- US3 depends on T004/T006 (provider + token write-back); US4 depends on all prior (factory wiring, e2e)
- Parallel: T002, T007, T009, T010, T011, T017, T019, T021, T025 are test-first or doc tasks on separate files

## Implementation Strategy

- MVP = US1 (book reads + reconciliation) - a saxo fund can deploy, read its SIM book, and refuse safely.
- US2 adds trading; US3 hardens secrets; US4 completes configuration, deployment, and routing end to end.
- Every implementation task is preceded by its failing test (constitution III); all tests network-free via the fake transport/clock/op runner (constitution II/IV).
