# Tasks: Trading 212 Broker Adapter

**Input**: Design documents from `/specs/003-t212-broker-adapter/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/t212-adapter.md, quickstart.md

**Tests**: Included — constitution Principle III requires a co-located, green suite; every story ships with tests over fake transports/fixtures (no network).

**Organization**: Tasks are grouped by user story. US3 (secrets) is implemented early because US1/US2 construction depends on it, but its wiring task stays in the US3 phase.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1–US4)
- Include exact file paths in descriptions

## Path Conventions

Single-package Python app: all paths under `hedge_fund/`; tests co-located next to the code they test.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Test scaffolding and module skeletons before any behavior exists.

- [ ] T001 [P] Create `hedge_fund/secrets/` package: `__init__.py` with `SecretResolutionError(RuntimeError)` and a `resolve_secret(raw: str) -> str` stub raising NotImplementedError; empty `hedge_fund/secrets/test_secrets.py`
- [ ] T002 [P] Create `hedge_fund/brokers/test_t212.py` with test scaffolding: `FakeTransport` (pre-scripted method→response list, records calls), `FakeClock` (controllable sleep/monotonic), and a `hedge_fund/brokers/fixtures/t212/` directory with recorded-shape JSON fixtures (order object, positions list, account summary, instruments excerpt, historical order with fill) per contracts/t212-adapter.md

**Checkpoint**: Scaffolding exists; suite still green.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The HTTP client and secret resolver everything else sits on.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [ ] T003 [P] Implement `resolve_secret` in `hedge_fund/secrets/__init__.py`: values starting with `op://` resolved via `op read` subprocess (stdout captured, stderr suppressed, timeout); other values pass through unchanged; failures raise `SecretResolutionError` whose message contains no secret material; tests in `hedge_fund/secrets/test_secrets.py` (stubbed subprocess): op:// success, op:// failure, plaintext passthrough, no-secret-in-message assertions
- [ ] T004 [P] Implement `T212Client` in `hedge_fund/brokers/t212.py`: demo-only base URL constant `https://demo.trading212.com/api/v0` (module-level, asserted by test), HTTP Basic auth from passed credentials, per-request timeout, per-endpoint minimum-interval pacer driven by an injectable clock (market orders 1.2s, order status 1.05s, positions 1.05s, account summary 5.05s, instruments 50s), 429 handling that sleeps until `x-ratelimit-reset` and retries reads once (never order POSTs), and `T212Error` normalization branching on HTTP status with status + response body verbatim in the message and no credentials/Authorization headers ever in messages; tests in `hedge_fund/brokers/test_t212.py` over FakeTransport/FakeClock

**Checkpoint**: Client + secrets layer done and green — user stories can proceed.

---

## Phase 3: User Story 1 — Connect fund to T212 demo book (Priority: P1) 🎯 MVP

**Goal**: A fund can read its authoritative book (positions + cash) from the T212 demo account, so the existing pre-session reconciliation works against the real demo account.

**Independent Test**: Construct `T212Broker` with FakeTransport fixtures → `positions()` returns engine-ticker `Position` dict, `cash()` returns available-to-trade; untradable universe tickers are refused; `isinstance(broker, Broker)` holds.

### Implementation for User Story 1

- [ ] T005 [US1] Implement `T212Broker.positions()` in `hedge_fund/brokers/t212.py`: `GET /equity/positions` → `dict[str, Position]` keyed by engine ticker (`AAPL_US_EQ` → `AAPL`), shares from `quantity`, negative shares raise (no shorts on Invest)
- [ ] T006 [US1] Implement `T212Broker.cash()` in `hedge_fund/brokers/t212.py`: `GET /equity/account/summary` → `cash.availableToTrade` as float; currency mismatch with the fund's expected currency raises
- [ ] T007 [US1] Implement instruments fetch + ~1h in-memory cache + universe validation in `hedge_fund/brokers/t212.py`: `GET /equity/metadata/instruments`, engine ticker ⇄ `{SYMBOL}_US_EQ` mapping helpers, `validate_universe()` refusing missing/untradable tickers before any order
- [ ] T008 [US1] Tests in `hedge_fund/brokers/test_t212.py`: positions mapping + negative-shares raise; cash + currency mismatch; universe validation (missing ticker, untradable, cache reuse across calls); structural `isinstance(T212Broker(...), Broker)` protocol check

**Checkpoint**: US1 independently functional — the adapter reports the demo book and reconciliation can refuse on mismatch.

---

## Phase 4: User Story 2 — Execute orders with actual fills (Priority: P2)

**Goal**: `place_order` places a demo market order, polls to a terminal state, and returns a complete `Fill` with the broker's actual price — or raises. Fail-safe: no blind retries, sell sizing against available quantity, redo refused.

**Independent Test**: Fixture-driven scenario: POST → pending → FILLED → `Fill(actual price, actual qty)` recorded; rejection and timeout raise; a sell larger than `quantityAvailableForTrading` is refused locally; `redo` on a t212 fund raises.

### Implementation for User Story 2

- [ ] T009 [US2] Implement market-order placement in `hedge_fund/brokers/t212.py`: `POST /equity/orders/market` with `{"ticker", "quantity", "extendedHours": false}`; signed quantity (positive buy / negative sell); round to 4 decimals with sells rounding down (toward zero); refuse zero/negative effective quantity; refuse sells exceeding `quantityAvailableForTrading` locally before any HTTP call; single-POST rule (429-with-reset retry is the only re-POST)
- [ ] T010 [US2] Implement fill polling in `hedge_fund/brokers/t212.py`: poll `GET /equity/orders/{id}` no faster than 1 req/s with a 120s injectable-clock deadline; terminal `FILLED` → fetch actual price/quantity from `GET /equity/history/orders` → return `Fill`; `REJECTED`/`CANCELLED` → raise `T212Error` with body verbatim; deadline exceeded → raise with "inspect pending orders before retrying" guidance
- [ ] T011 [US2] Wire the broker into the session path: `build_broker(deployed)` factory in `hedge_fund/paper/deployed.py` (paper → `PaperBroker` unchanged; t212 → `T212Broker` with resolved credentials + universe + costs), `hedge_fund/paper/tick.py` uses the factory for sessions, and the redo path in `hedge_fund/paper/tick.py` refuses any broker other than `paper` with a clear error
- [ ] T012 [US2] Tests in `hedge_fund/brokers/test_t212.py` + `hedge_fund/paper/test_tick.py`: full place→poll→fill fixture scenario; REJECTED and timeout paths; 429-on-POST single-retry; quantity rounding (4dp, sell-down, zero-refusal); sell-size local refusal; redo refusal for t212 funds; paper funds' behavior unchanged (existing tests still pass)

**Checkpoint**: US2 independently functional — a t212 fund can trade a session end-to-end against fixtures.

---

## Phase 5: User Story 3 — 1Password credentials via op:// references (Priority: P2)

**Goal**: Credentials resolve from 1Password at broker construction; plaintext env values still work; secrets never appear in logs, errors, or persisted files.

**Independent Test**: With `HEDGE_FUND_T212_API_KEY=op://vault/T212/api_key` and a stubbed `op`, broker construction resolves the secret; without variables, construction raises naming the variable; no secret material in any error message or log output.

### Implementation for User Story 3

- [ ] T013 [US3] Wire credential resolution into `T212Broker` construction in `hedge_fund/brokers/t212.py`: read `HEDGE_FUND_T212_API_KEY` / `HEDGE_FUND_T212_API_SECRET`, resolve each via `hedge_fund.secrets.resolve_secret`, missing/empty → `SecretResolutionError` naming the variable (never the value); `op` invoked only at construction
- [ ] T014 [US3] Tests in `hedge_fund/brokers/test_t212.py` + `hedge_fund/secrets/test_secrets.py`: end-to-end op:// construction with stubbed `op`; plaintext env path; missing-variable error; assertions that exception messages, log output, and any written files contain no secret material

**Checkpoint**: US3 independently functional — credentials flow from 1Password to the adapter with no plaintext leakage.

---

## Phase 6: User Story 4 — Broker selection per fund mandate (Priority: P3)

**Goal**: `broker: paper | t212` is a validated, per-fund mandate setting that is byte-compatible with existing deployed funds and visible in the UI/status.

**Independent Test**: A fund.yaml with `broker: t212` loads and builds a T212Broker; a fund.yaml without the key loads byte-identically to before; an invalid value fails FundSpec validation; TUI detail and CLI status show the broker name.

### Implementation for User Story 4

- [ ] T015 [US4] Add `broker: Literal["paper", "t212"] = "paper"` to `FundSpec` in `hedge_fund/fund/spec.py`, popping the key on serialization when it equals the default (same pattern as `approval_required`) so existing deployed fund.yaml files stay byte-identical
- [ ] T016 [US4] Show the broker name in `hedge_fund/tui/paper_view.py` (fund detail) and `hedge_fund/run.py` (status output)
- [ ] T017 [US4] Tests in `hedge_fund/fund/test_spec.py` (or co-located spec tests) + `hedge_fund/tui/test_builder.py`: Literal validation rejects unknown values; serialization pops the default (byte-compat); t212 value round-trips; broker name appears in TUI detail and status output

**Checkpoint**: All four user stories independently functional.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Exports, docs, and the full quality gate.

- [ ] T018 Export `T212Broker` (and `T212Error`) from `hedge_fund/brokers/__init__.py`
- [ ] T019 [P] Documentation pass: module docstrings in `hedge_fund/brokers/t212.py` and `hedge_fund/secrets/__init__.py` carrying the key contract rules (demo-only, fill-complete-or-raise, no blind retries, secrets never persisted); cross-check `specs/003-t212-broker-adapter/quickstart.md` commands still accurate
- [ ] T020 Run the full quality gate: `poetry run pytest hedge_fund -q` green apart from the 6 documented Windows baseline failures; `poetry run black --check hedge_fund`, `poetry run isort --check-only hedge_fund`, `poetry run flake8 hedge_fund` clean; no BOM in any touched file
- [ ] T021 Run quickstart.md Layer A validation end-to-end and record the result

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: no dependencies — start immediately
- **Foundational (Phase 2)**: depends on Phase 1 — BLOCKS all user stories
- **US1 (Phase 3)**: depends on Phase 2
- **US2 (Phase 4)**: depends on US1 (place_order needs positions/cash for sizing and reconciliation)
- **US3 (Phase 5)**: T003 lands in Phase 2; the wiring task T013 depends on T009's constructor shape — do after US2
- **US4 (Phase 6)**: depends on US2 (the factory must exist to be configured); TUI/status tasks are independent of each other
- **Polish (Phase 7)**: depends on all stories complete

### User Story Dependencies

- **US1**: foundational only — no cross-story dependencies
- **US2**: needs US1's book reads (sell sizing, reconciliation)
- **US3**: resolver exists from Phase 2; wiring follows US2's constructor
- **US4**: config surface over the completed factory

### Parallel Opportunities

- T001 + T002 (Phase 1) in parallel
- T003 + T004 (Phase 2) in parallel
- T005 + T006 (US1) in parallel; T007 after T005 (shares ticker mapping)
- T015 + T016 (US4) in parallel
- T019 parallel with T018

---

## Parallel Example: User Story 1

```bash
# Together (different methods, same module — coordinate edits):
Task: "T005 [US1] Implement T212Broker.positions() in hedge_fund/brokers/t212.py"
Task: "T006 [US1] Implement T212Broker.cash() in hedge_fund/brokers/t212.py"
# Then:
Task: "T007 [US1] Instruments cache + universe validation in hedge_fund/brokers/t212.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Phase 1 → Phase 2 (foundation)
2. Phase 3 (US1): the adapter can report the demo book; reconciliation refuses on mismatch
3. **STOP and VALIDATE** against fixtures

### Incremental Delivery

1. Foundation → US1 (book reads) → US2 (order execution) → US3 (secrets wiring) → US4 (mandate config) → Polish
2. Each story adds value without breaking the previous ones; paper funds are untouched throughout (existing tests must stay green)

### Notes

- Commit after each task or logical group
- Long test runs: chunk them (`poetry run pytest hedge_fund/brokers -q` then the rest) — full-suite runs have been externally killed before
- The 6 known Windows baseline failures are pre-existing and unrelated; do not fix them here