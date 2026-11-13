# Tasks: RB-3 Safe Halt → Reconciliation → Resume Completion

**Input**: Design documents from `/specs/007-rb3-halt-recovery/` (revised post-rebase onto `448056f` / PR #11)

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/recovery-semantics.md

**Tests**: Included — constitution Principle III; tests FIRST (red), then implementation (green).

**Organization**: by user story; each independently testable with synthetic fixtures. Sequential specialist execution; [P] marks file-independence only.

**Baseline note**: PR #11 already delivered intent enumeration/fencing/resolution, safe pre-effect aborts, post-effect failure journaling for request-identified ticks, receipt replay, and logical-operation dedup. Tasks below cover ONLY the four re-verified remaining gaps.

## Format: `[ID] [P?] [Story] Description`

---

## Phase 1: Setup

- [x] T001 Verify baseline `448056f` ancestor + clean tree; record pre-change targeted results (`poetry run pytest hedge_fund/paper/test_ledger.py hedge_fund/runtime/test_reconciliation.py hedge_fund/web/test_recovery.py -q`) as red/green baseline in specs/007-rb3-halt-recovery/implementation-evidence.md. `poetry` CLI unavailable; cached Poetry environment used directly.

---

## Phase 2: Foundational (Blocking Prerequisites)

**⚠️ CRITICAL**: blocks all user stories

- [x] T002 Add a single fund-level unresolved-state query in hedge_fund/paper/ledger.py covering: recorded failures pending review, outstanding tick intents (reuse PR #11 orphan scan `:371-432`), unresolved Resume intents, and unmatched approval-consumption entries; additive helper near the readiness guard (`:359-369`)
- [x] T003 Regression test: pre-feature ledger fixtures replay byte-identically with the helper present in hedge_fund/paper/test_ledger.py

**Checkpoint**: helper exists; old records replay identically

---

## Phase 3: User Story 1 — Recovery always reachable (Priority: P1) 🎯 MVP

**Goal**: Reconciliation-required state never hides the recovery surface; unmatched approval consumption is resolvable

**Independent Test**: quickstart Scenarios 1–2 — readiness-denied fund still shows recovery; unmatched approval-consumption entry enumerated and resolved through the reviewed path

### Tests for User Story 1 (write FIRST, must FAIL before implementation) ⚠️

- [x] T004 [P] [US1] Test: readiness denial surfaces as reconciliation_required (distinct from corrupt replay) and snapshot still exposes recovery state in hedge_fund/web/test_recovery.py
- [x] T005 [P] [US1] Test: unmatched approval-consumption entry appears in the recovery preview and resolves through the reviewed path (extend regression anchor around hedge_fund/paper/test_tick.py:627-655) in hedge_fund/paper/test_tick.py
- [x] T006 [P] [US1] Test: genuine corrupt replay still reports corruption (no regression to corruption visibility) in hedge_fund/web/test_recovery.py

### Implementation for User Story 1

- [x] T007 [US1] Distinguish valid-but-not-ready (reconciliation_required) from corrupt replay in the snapshot/report path in hedge_fund/web/services.py (`:4082-4089` region) and keep recovery fetch/display available in that state (frontend/src/pages/paper.tsx:157-159,690-693 — service-level fix preferred; touch frontend only if required)
- [x] T008 [US1] Extend the orphaned-intent resolution path to enumerate and resolve unmatched approval-consumption entries with the same audited digest-bound review in hedge_fund/paper/ledger.py (`:1025-1104`) and hedge_fund/runtime/reconciliation.py preview (`:497-535`); add WRITER_MAP entry citing T005 if a new raw write is introduced (hedge_fund/runtime/test_writer_map.py)

**Checkpoint**: US1 green; no dead-end halted fund

---

## Phase 4: User Story 2 — One consistent Resume gate (Priority: P2)

**Goal**: readiness, web resume_allowed, and Ledger.resume() evaluate the same unresolved-state set; recovery operations are not blocked by the gate they serve

**Independent Test**: quickstart Scenario 3 — fixtures per unresolved-state category; all three evaluation points agree

### Tests for User Story 2 (write FIRST, must FAIL where behavior is new) ⚠️

- [x] T009 [P] [US2] Test: unresolved Resume intent denies require_ready_for_work and resume_allowed in hedge_fund/paper/test_ledger.py and hedge_fund/web/test_recovery.py
- [x] T010 [P] [US2] Test: backend Resume denied while orphaned tick intent exists (parity with desk) in hedge_fund/paper/test_ledger.py
- [x] T011 [P] [US2] Test: recovery operations (intent resolution, confirmed Resume) remain admissible while the gate denies ordinary work in hedge_fund/paper/test_ledger.py

### Implementation for User Story 2

- [x] T012 [US2] Route require_ready_for_work (`hedge_fund/paper/ledger.py:359-369`), web resume_allowed (`hedge_fund/web/services.py:824-846`), and the Ledger.resume() pre-check (`:1207-1216`) through the T002 unresolved-state query; preserve PR #11's separate require_ready_for_tick fence and recovery-path admission unchanged

**Checkpoint**: US1+US2 green; gates agree

---

## Phase 5: User Story 3 — Legacy no-ID post-fill Halt journaling (Priority: P2)

**Goal**: no-request-ID ticks interrupted post-fill journal a reviewable tick_failed bound to transmitted fills; zero-effect interruptions stay clean aborts

**Independent Test**: quickstart Scenario 4 — no-ID tick halted after first fill produces reviewable record; zero-fill halt stays clean

### Tests for User Story 3 (write FIRST, must FAIL before implementation) ⚠️

- [x] T013 [P] [US3] Test: no-request-ID tick halted after ≥1 transmitted fill journals tick_failed bound to fill identities and appears in recovery in hedge_fund/paper/test_tick.py
- [x] T014 [P] [US3] Test: no-request-ID zero-effect halt keeps clean-abort semantics (no book-ambiguity review) in hedge_fund/paper/test_tick.py

### Implementation for User Story 3

- [x] T015 [US3] Journal post-effect tick_failed for the no-request-ID path when interrupted by Halt with no outcome, mirroring the request-identified handler in hedge_fund/paper/tick.py (`:212-216`, `:474-500`, cf. `:931-934`); WRITER_MAP entry citing T013 if a new raw write appears

**Checkpoint**: all execution paths journal reviewable post-fill interruptions

---

## Phase 6: User Story 4 — Recovery receipts expire (Priority: P3)

**Goal**: both receipt types carry recorded-clock validity; expired/legacy receipts deny fail-closed; state rebinding preserved (spec005 T140)

**Independent Test**: quickstart Scenario 5 — expired and legacy receipts denied; fresh bound receipt succeeds

### Tests for User Story 4 (write FIRST, must FAIL before implementation) ⚠️

- [x] T016 [P] [US4] Test: expired receipt denied (recorded clock past valid_until) for failure-bound and intent-bound receipts in hedge_fund/runtime/test_reconciliation.py
- [x] T017 [P] [US4] Test: legacy receipt without expiry fields denied fail-closed; fresh bound receipt still authorizes in hedge_fund/runtime/test_reconciliation.py
- [x] T018 [P] [US4] Test: bound-state change after issuance still denied (rebind regression) via web flow in hedge_fund/web/test_recovery.py

### Implementation for User Story 4

- [x] T019 [US4] Add issued_at/valid_until (recorded clock) at issuance for both receipt types in hedge_fund/runtime/reconciliation.py (`:104-136`, `:268-307`); choose bounded validity window (single review-session scale); record value in implementation-evidence.md — 30 minutes.
- [x] T020 [US4] Reject expired and field-less receipts in verification in hedge_fund/runtime/reconciliation.py (`:678-699` and the intent-receipt verifier), preserving digest rebinding

**Checkpoint**: all four stories green; T140 semantics satisfied

---

## Phase 7: Polish & Cross-Cutting Concerns

- [x] T021 [P] Cadence regression subset (`pytest hedge_fund/paper/test_tick.py -q -k "weekly or daily or session"`) — 16 passed, 113 deselected (FR-007)
- [x] T022 [P] PR #11 writer-safety regression subset (`pytest hedge_fund/paper/test_ledger.py hedge_fund/paper/test_tick.py -q`) — 216 passed. T012's default work gate initially blocked existing redo supersession; redo now admits outstanding tick intents while retaining the other recovery blockers.
- [ ] T023 Full targeted slice green: `poetry run pytest hedge_fund/paper/test_ledger.py hedge_fund/paper/test_tick.py hedge_fund/runtime/test_reconciliation.py hedge_fund/runtime/test_writer_map.py hedge_fund/web/test_recovery.py -q` (+ frontend jest if paper.tsx touched) — FAIL: writer-map scan found five callsites in unchanged modules; verified pre-existing baseline failure on `448056f` (files and test unchanged on branch; reproduced on base). Disposition: individually-evidenced baseline defect per Principle III, handoff recorded; not repaired by this branch (out of scope).
- [x] T024 Style gate: black --check, isort --check, flake8 on changed files (line-length 420) — PASS with E203 compatibility ignore; bare flake8 reports two unchanged E203 lines.
- [x] T025 Complete specs/007-rb3-halt-recovery/implementation-evidence.md: per-task results, exact commands, durations, platform, fixture provenance (evidence contract)
- [x] T026 Isolated full suite `poetry run pytest hedge_fund -q` (~40 min, alone); record any failure vs pre-change baseline per Principle III; BLOCKED/INCONCLUSIVE is not PASS — final run on `8d81ace`: 2856 passed / 108 failed / 66 skipped in 2617s; 108/108 failures ID-identical to baseline `448056f` reproduction (zero branch-attributable failures); details in implementation-evidence.md.

---

## Dependencies & Execution Order

- **Setup (T001)** → **Foundational (T002–T003)** → stories.
- **US1 (T004–T008)**: after Foundational; independent.
- **US2 (T009–T012)**: after Foundational; reuses T002 helper — run after US1 (sequential).
- **US3 (T013–T015)**: after Foundational; independent files (tick.py) — run after US2.
- **US4 (T016–T020)**: after Foundational; touches reconciliation.py after US1's preview change — run after US1.
- **Polish (T021–T026)**: after all stories.

### Parallel Opportunities

- Test tasks within each story are [P] (different files) — executed sequentially by the single specialist.
- T021/T022 [P] — run sequentially.

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. T001 → T002–T003 → Phase 3 (T004–T008)
2. **STOP and VALIDATE**: quickstart Scenarios 1–2 green — no dead-end halted fund

### Incremental Delivery

US1 → commit → US2 → commit → US3 → commit → US4 → commit → Polish/evidence.

### Notes

- Synthetic fixtures only; no production roots, broker calls, paid data, Docker changes.
- New raw writes require WRITER_MAP entries (hedge_fund/runtime/test_writer_map.py) citing test nodes.
- PR #11 behaviors (safe aborts, dedup, tick fence, intent resolution, receipt replay) must not regress — T022 guards this.
- No PR-scope change without user instruction; PR #12 already open for these spec docs.
- Execution deviation: `poetry` CLI was unavailable, so cached Poetry-venv Python ran pytest directly; frontend uses Vitest. Both are recorded in implementation-evidence.md.
- US1 required the frontend recovery-fetch/display condition: `ledger.ok` remains false to keep normal work fenced while `recovery_state` exposes the recovery surface.
