# Tasks: RB-3 Safe Halt → Reconciliation → Resume Completion

**Input**: Design documents from `/specs/006-rb3-halt-recovery/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/recovery-semantics.md

**Tests**: Included — constitution Principle III requires co-located pytest coverage; write tests FIRST (red), then implement (green).

**Organization**: Tasks grouped by user story; each story independently testable with synthetic fixtures.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Different files, no dependencies on incomplete tasks
- **[Story]**: US1/US2/US3 map to spec.md user stories
- Paths relative to repo root

**Execution constraint**: specialists run sequentially (one at a time); [P] marks file-independence only.

---

## Phase 1: Setup

**Purpose**: Baseline verification before any change

- [ ] T001 Verify baseline: `git merge-base --is-ancestor b6aefe5cf04753265168ec32bcb02976932a9588 HEAD` and clean tree; record pre-change targeted test results (`poetry run pytest hedge_fund/paper/test_ledger.py hedge_fund/runtime/test_reconciliation.py -q`) as the red/green baseline in specs/006-rb3-halt-recovery/implementation-evidence.md

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Shared primitives all stories depend on

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [ ] T002 Add outstanding-intent query helper (scan journal for execution intents with no recorded outcome, and unresolved Resume intents) in hedge_fund/paper/ledger.py near the existing intent guard (`:784-841`); additive, no change to existing record serialization
- [ ] T003 Regression test: replay of a pre-feature ledger fixture remains byte-identical with the new helper present in hedge_fund/paper/test_ledger.py

**Checkpoint**: helper exists, old records replay identically

---

## Phase 3: User Story 1 — Every interrupted operation visibly requires reconciliation (Priority: P1) 🎯 MVP

**Goal**: Outstanding execution intents and halt-interrupted executions surface as reconciliation-required and block new work regardless of request ID

**Independent Test**: Simulate crash-after-intent and halt-after-first-fill; preview shows both; new work with a fresh request ID is denied (quickstart.md Scenarios 1–2)

### Tests for User Story 1 (write FIRST, must FAIL before implementation) ⚠️

- [ ] T004 [P] [US1] Test: crash-after-intent (intent, no outcome) appears in reconciliation preview with identity/head/book/fill digests in hedge_fund/runtime/test_reconciliation.py
- [ ] T005 [P] [US1] Test: outstanding intent denies new work for a *different* request ID via require_ready_for_work in hedge_fund/paper/test_ledger.py
- [ ] T006 [P] [US1] Test: halt-interrupted execution after ≥1 transmitted fill journals a reconciliation-required record bound to the fill identities; zero-effect halt stays clean (extend existing partial-fill case) in hedge_fund/paper/test_tick.py
- [ ] T007 [P] [US1] Test: web preview renders outstanding-intent entries and resume_allowed=false in hedge_fund/web/test_recovery.py

### Implementation for User Story 1

- [ ] T008 [US1] Enumerate outstanding execution intents in the preview builder alongside tick_failed events in hedge_fund/runtime/reconciliation.py (`:185-225`)
- [ ] T009 [US1] Extend Ledger.require_ready_for_work() to deny on outstanding execution intents (any request ID) using the T002 helper in hedge_fund/paper/ledger.py (`:307-317`)
- [ ] T010 [US1] Journal a reconciliation-required record at the halt re-raise boundary when ≥1 effect was transmitted in hedge_fund/paper/tick.py (`:804-819`); add WRITER_MAP entry citing T006 if a new raw write is introduced (hedge_fund/runtime/test_writer_map.py)
- [ ] T011 [US1] Include outstanding intents in resume_allowed and denial reasons in hedge_fund/web/services.py (`:775-793`)

**Checkpoint**: US1 green on targeted runs; no silent uncertain operation possible

---

## Phase 4: User Story 2 — Resume gating accounts for all unresolved state (Priority: P2)

**Goal**: Resume permission and readiness consider outstanding execution intents and unresolved Resume intents; retries never duplicate fills

**Independent Test**: Ledgers with each unresolved state deny Resume until reviewed confirmation bound to current head/book/fill digest; retried requests return recorded outcomes (quickstart.md Scenario 4)

### Tests for User Story 2 (write FIRST, must FAIL where behavior is new) ⚠️

- [ ] T012 [P] [US2] Test: unresolved Resume intent blocks require_ready_for_work and resume_allowed in hedge_fund/paper/test_ledger.py
- [ ] T013 [P] [US2] Test: restart/retry after crash-after-intent returns recorded outcome or is denied — fill count exactly one — across the retry matrix in hedge_fund/paper/test_tick.py
- [ ] T014 [P] [US2] Test: reviewed Resume after intent reconciliation clears Halt and admits new executions in hedge_fund/web/test_recovery.py

### Implementation for User Story 2

- [ ] T015 [US2] Route Resume-permission evaluation through the unresolved-state set (failures + outstanding intents + unresolved Resume intent) in hedge_fund/paper/ledger.py resume path (`:945-1010`) and hedge_fund/web/services.py (`:783-793`, `:3653-3738`)
- [ ] T016 [US2] Verify retry/idempotency guards cover the intent-only interruption path (same-ID deny + cross-ID readiness deny) in hedge_fund/paper/ledger.py (`:784-841`); extend only if T013 shows a hole

**Checkpoint**: US1 AND US2 green; Resume cannot reopen an ambiguous fund

---

## Phase 5: User Story 3 — Recovery confirmations expire with state change (Priority: P3)

**Goal**: Receipts carry a recorded-clock validity bound; expired or legacy (field-less) receipts never authorize Resume (completes spec005 T140)

**Independent Test**: Issue receipt, mutate bound state or advance recorded clock past validity, or present legacy receipt → Resume denied with re-review reason (quickstart.md Scenario 3)

### Tests for User Story 3 (write FIRST, must FAIL before implementation) ⚠️

- [ ] T017 [P] [US3] Test: expired receipt (recorded clock past valid_until) denied in hedge_fund/runtime/test_reconciliation.py
- [ ] T018 [P] [US3] Test: legacy receipt without expiry fields denied fail-closed; fresh bound receipt still authorizes in hedge_fund/runtime/test_reconciliation.py
- [ ] T019 [P] [US3] Test: bound-state change after issuance denies Resume with re-review reason via web flow in hedge_fund/web/test_recovery.py

### Implementation for User Story 3

- [ ] T020 [US3] Add issued_at/valid_until (recorded clock) to receipt issuance and fields in hedge_fund/runtime/reconciliation.py (`:104-136`); choose bounded validity window (single review session scale) and record the value in specs/006-rb3-halt-recovery/implementation-evidence.md
- [ ] T021 [US3] Reject expired and field-less receipts in verification in hedge_fund/runtime/reconciliation.py (`:310-330`), keeping the existing digest rebinding

**Checkpoint**: all three stories green; T140 semantics satisfied

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Invariants, regression breadth, evidence

- [ ] T022 [P] Run daily/weekly/minute cadence regression subset (`pytest hedge_fund/paper/test_tick.py -q -k "weekly or daily or session"`) — all pre-existing tests pass unmodified (FR-009)
- [ ] T023 [P] Run full targeted slice green: `poetry run pytest hedge_fund/paper/test_ledger.py hedge_fund/paper/test_tick.py hedge_fund/runtime/test_reconciliation.py hedge_fund/web/test_recovery.py hedge_fund/runtime/test_writer_map.py -q`
- [ ] T024 Style gate: black --check, isort --check, flake8 on changed files (line-length 420 preserved)
- [ ] T025 Update specs/006-rb3-halt-recovery/implementation-evidence.md with per-task results, exact commands, durations, platform, and fixture provenance (evidence contract)
- [ ] T026 Full isolated suite `poetry run pytest hedge_fund -q` (~40 min, run alone); record any failure against pre-change baseline per constitution Principle III; BLOCKED/INCONCLUSIVE is not PASS

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (T001)**: no dependencies
- **Foundational (T002–T003)**: depends on T001 — BLOCKS all stories
- **US1 (Phase 3)**: after Foundational; no dependency on US2/US3
- **US2 (Phase 4)**: after Foundational; integrates with US1 readiness helper (T002) — run after US1 for simplicity (sequential specialists)
- **US3 (Phase 5)**: after Foundational; independent of US1/US2 files except reconciliation.py ordering — run after US1
- **Polish (Phase 6)**: after all stories

### Parallel Opportunities

- Within each story: test tasks T004–T007 / T012–T014 / T017–T019 are [P] (different files) — but executed sequentially by the single specialist; [P] marks file independence
- T022 and T023 [P] (different concerns), run sequentially

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. T001 → T002–T003 → Phase 3 (T004–T011)
2. **STOP and VALIDATE**: quickstart Scenarios 1–2 green — the core safety hole (silent uncertain operations) is closed

### Incremental Delivery

1. MVP (US1) → targeted tests green → commit
2. US2 → green → commit
3. US3 → green → commit
4. Polish: style, evidence, isolated full suite

### Notes

- Synthetic fixtures only; no production roots, broker calls, paid data, or Docker changes
- Any new raw write must gain a WRITER_MAP entry (hedge_fund/runtime/test_writer_map.py) citing test nodes
- No PR without explicit user instruction
