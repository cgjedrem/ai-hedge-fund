# Tasks: Saxo OpenAPI Broker Adapter (SIM)

**Feature**: 003-saxo-broker-adapter | **Input**: spec.md, plan.md, research.md, data-model.md, contracts/saxo-adapter.md, quickstart.md
**Tests requested**: yes (constitution III — test-first, co-located, network-free)

## Phase 1: Setup

- [ ] T001 Create `hedge_fund/brokers/saxo.py` module skeleton with SIM-only constants (`BASE_URL = "https://gateway.saxobank.com/sim/openapi"`, `AUTH_URL = "https://sim.logonvalidation.net"`) and error taxonomy classes `SaxoAuthError`, `SaxoOrderError`, `SaxoReconcileError` in hedge_fund/brokers/saxo.py
- [ ] T002 [P] Add fake transport + fake clock test doubles in hedge_fund/brokers/test_saxo_doubles.py (Transport protocol recording calls, scripted responses; FakeClock for pacer/token manager)

## Phase 2: Foundational (blocking)

- [ ] T003 Test-first: token manager refresh + rotation write-back tests in hedge_fund/brokers/test_saxo_tokens.py (proactive refresh at <120 s margin, single-use rotating refresh token persisted to 1Password BEFORE new access token used, refresh failure → SaxoAuthError with re-auth guidance, no retry loop)
- [ ] T004 Implement `TokenManager` in hedge_fund/brokers/saxo.py (POST {AUTH_URL}/token with grant_type=refresh_token, Basic app auth, 1Password write-back via secrets provider, state machine UNAUTHENTICATED→AUTHORIZED→REAUTH_REQUIRED)
- [ ] T005 [P] Test-first: pacer tests in hedge_fund/brokers/test_saxo_pacer.py (orders class ≥1.0 s spacing under FakeClock, other classes unpaced)
- [ ] T006 Implement `Pacer` in hedge_fund/brokers/saxo.py (per-endpoint-class min interval, fake-clock friendly wait)
- [ ] T007 Test-first: redaction tests in hedge_fund/brokers/test_saxo_redaction.py (no app secret/access/refresh token material in client logs, exception messages, or repr under any failure path)
- [ ] T008 Extend `hedge_fund/secrets/provider.py` with write-back capability (`op item edit` for the rotating refresh token; failure raises, never continues with unpersisted rotation) in hedge_fund/secrets/provider.py

## Phase 3: US1 — Connect fund to Saxo SIM book (P1)

**Goal**: A deployed `saxo` fund reads SIM positions/cash and reconciles before trading.
**Independent test**: with a scripted transport, `SaxoBroker.positions()`/`cash()` return values mapped from fixture payloads; reconciliation refuses on mismatch.

- [ ] T009 [P] [US1] Test-first: client book-read tests in hedge_fund/brokers/test_saxo_client.py (users/me → ClientKey, accounts/me → AccountKey, positions/me grouped by NetPositionId with signed Amount + OpenPrice, balances/me → CashAvailableForTrading)
- [ ] T010 [US1] Implement `SaxoClient` book reads + startup discovery in hedge_fund/brokers/saxo.py (bearer auth on every call, one 401→refresh→retry then SaxoAuthError)
- [ ] T011 [P] [US1] Test-first: instrument resolution tests in hedge_fund/brokers/test_saxo_universe.py (Keywords search → Uic/AssetType cache ~1 h TTL, untradable/missing ticker → SaxoReconcileError before any order)
- [ ] T012 [US1] Implement universe validation + UIC cache in hedge_fund/brokers/saxo.py (FR-006: validate full fund universe before first order of a session)
- [ ] T013 [US1] Wire reconciliation to SaxoBroker book in hedge_fund/paper/tick.py (external book authoritative; mismatch refuses session — reuse existing reconcile path)

## Phase 4: US2 — Order execution with actual SIM fills (P2)

**Goal**: Session orders place market orders and record Saxo's actual simulated fills.
**Independent test**: scripted transport: POST → OrderId, open-order poll → gone, positions/transactions → fill; Fill matches fixture; ErrorInfo/409/deadline paths raise.

- [ ] T014 [US2] Test-first: order placement tests in hedge_fund/brokers/test_saxo_orders.py (payload shape: Uic/AssetType Stock/Amount shares/BuySell/OrderType Market/DayOrder/ManualOrder false; unique x-request-id per attempt; HTTP 200 with ErrorInfo → SaxoOrderError carrying Saxo ErrorCode; 409 → inspect state, never re-POST; poll-until-gone with 120 s deadline → SaxoOrderError; fill read from position OpenPrice/Amount or transactions; fill-completely-or-raise)
- [ ] T015 [US2] Implement `SaxoBroker.place_order` + fill detection in hedge_fund/brokers/saxo.py (pacer wait before POST, body inspection not status-only, poll open order until gone, bounded deadline, Fill construction with Saxo's simulated price)
- [ ] T016 [US2] Test-first: quantity precision tests in hedge_fund/brokers/test_saxo_precision.py (LotSize rounding from instrument details; fractional rejection → refuse, never round up exposure — FR-012)
- [ ] T017 [US2] Implement quantity precision handling in hedge_fund/brokers/saxo.py (round to tradable precision; refuse when rounding would change exposure direction/size materially)

## Phase 5: US3 — Secrets via 1Password, token safety (P2)

**Goal**: No secret ever in plaintext/logs/ledger; rotating refresh token survives restarts.
**Independent test**: with fake `op` runner, references resolve at startup; missing ref errors name the variable; write-back called after every refresh; grep-style redaction tests pass.

- [ ] T018 [US3] Test-first: startup secret resolution tests in hedge_fund/secrets/test_saxo_secrets.py (SAXO_APP_KEY_REF/SAXO_APP_SECRET_REF/SAXO_REFRESH_TOKEN_REF resolved via op://; missing → error naming variable, never value; redirect URI from non-secret env)
- [ ] T019 [US3] Implement Saxo credential wiring in hedge_fund/brokers/saxo.py + factory (resolve at construction; interactive auth-code+PKCE helper module `hedge_fund/brokers/saxo_auth.py` for first login storing refresh token to 1Password)

## Phase 6: US4 — Broker selection per fund mandate (P3)

**Goal**: `broker: paper|saxo` in the mandate; existing funds byte-identical; TUI shows broker.
**Independent test**: FundSpec round-trip golden test (paper fund yaml byte-identical); factory builds SaxoBroker for saxo funds; redo refuses saxo.

- [ ] T020 [US4] Test-first: FundSpec broker field tests in hedge_fund/fund/test_spec_broker.py (Literal validation, popped-on-default serialization byte-compat golden file, immutable after deploy) + implement in hedge_fund/fund/spec.py
- [ ] T021 [US4] Wire broker factory `"saxo"` branch in hedge_fund/paper/deployed.py (build SaxoBroker with resolved secrets; missing secrets fail before trading) and redo guard for non-paper brokers in hedge_fund/paper/tick.py; surface broker name in TUI/status display

## Phase 7: Polish

- [ ] T022 [P] Update quickstart smoke-test steps in specs/003-saxo-broker-adapter/quickstart.md to match implemented CLI (`saxo_auth` module name, env var names) — doc-only
- [ ] T023 Run style gate (black/isort/flake8) and chunked full pytest (`hedge_fund/brokers`, `hedge_fund/secrets`, `hedge_fund/fund`, then full suite) — expect green except the 6 documented Windows baseline failures

## Dependencies

- T001 → T002..T008 (foundational) → US1 (T009–T013) → US2 (T014–T017) → US3 (T018–T019) → US4 (T020–T021) → Polish (T022–T023)
- US1 blocks US2 (orders need universe validation + book reads)
- US3 depends on T004/T008 (token write-back); US4 depends on all prior (factory wiring)
- Parallel: T002, T005, T007, T009, T011, T016, T018, T020, T022 are test-first or doc tasks on separate files

## Implementation Strategy

- MVP = US1 (book reads + reconciliation) — a saxo fund can deploy, read its SIM book, and refuse safely.
- US2 adds trading; US3 hardens secrets; US4 completes configuration UX.
- Every implementation task is preceded by its failing test (constitution III); all tests network-free via the fake transport/clock (constitution II/IV).