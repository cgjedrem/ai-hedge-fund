# Tasks: Legacy Failure Recovery

**Input**: Design documents from `/specs/009-legacy-failure-recovery/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/legacy-failure-recovery.md, quickstart.md

**Tests**: Included — constitution Principle III and spec acceptance scenarios require failing-first focused tests plus full-suite evidence.

**Organization**: Tasks grouped by user story for independent implementation and testing.

## Format: `[ID] [P?] [Story] Description`

## Path Conventions

- Python package + co-located tests: `hedge_fund/`
- React desk: `frontend/src/`

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Fixture and evidence scaffolding shared by all stories

- [x] T001 Create synthetic fixture helpers for legacy failure recovery in hedge_fund/runtime/test_reconciliation.py: builder for an enrolled synthetic root (`hedge_fund/runtime/test_bootstrap.py` pattern) whose events file contains N legacy `tick_failed` events without `request_id` and without post-effect fields, anchored at an expected head with no pending decision for the verified variant, followed by later verified session records, with a broker book matching replay
- [x] T002 [P] Add fixture variant helpers in the same test module: failure event carrying transmitted-fill/post-effect fields; corrupt audit event injection; perturbed broker-book digest; head-advancing append helper (for stale-preview tests)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Decision record + replay treatment that ALL stories depend on

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [x] T003 Define the reconciliation decision record: new append-only audit event kind (e.g. `legacy_failure_reconciliation`) with fields per data-model.md (`decision_id`, `failure_digests`, `ledger_head`, `book_digest`, exact `audit_history_digest` + length, operator, recorded time, and exact `attested_failure_digests`) in hedge_fund/paper/ledger.py; new records use schema v2 while schema-v1 records remain replayable; append only through the anchored audit boundary (`ledger.py:2200-2254`); add WRITER_MAP entry if any new raw write appears
- [x] T004 Extend replay in hedge_fund/runtime/reconciliation.py: failures whose digest is bound by a valid decision record (matching set, head context, dedup by decision_id) count as resolved in the unresolved-failure computation (`reconciliation.py:365-405,446-501`); identical repeated decision records dedup; records referencing unknown or already-resolved digests are invalid and resolve nothing
- [x] T005 Failing-first tests for T003/T004 in hedge_fund/runtime/test_reconciliation.py: decision record resolves bound digests; byte-identical pre-existing bytes after append; duplicate decision record replays as one; invalid digest set resolves nothing; legacy receipts and intent semantics unchanged (FR-011 regression fixtures reusing `test_legacy_failure_receipt_replay_preserves_resolution` patterns)

**Checkpoint**: Replay-level resolution works headlessly; US1/US2/US3 can proceed

---

## Phase 3: User Story 1 — Resolve multiple historical no-effect failures (Priority: P1) 🎯 MVP

**Goal**: Operator previews, reviews per-failure evidence, and confirms one audited reconciliation that restores schedulability with history preserved

**Independent Test**: quickstart.md Scenario A — synthetic fund with 3 unkeyed failures and no pending decision at each expected head: preview lists all `verified`, confirm appends exactly one decision record with an empty attested subset, recovery state ready, 423 guard stops firing, pre-existing bytes hash-identical

### Tests for User Story 1 ⚠️ (write FIRST, ensure FAIL)

- [x] T006 [P] [US1] Preview classification tests in hedge_fund/web/test_services.py: unkeyed no-pending fixture yields per-failure `verified` entries with all structural checks true; ambiguous but structurally sound failures are `attestable`; structural gaps are `not_resolvable`; preview binds head/book/audit digests and offers confirm only without `not_resolvable`
- [x] T007 [P] [US1] Confirm happy-path test in hedge_fund/web/test_recovery.py: confirm with matching preview binds appends exactly one decision record, recovery state becomes ready, work admission no longer returns 423 (`web/services.py:4246-4275`)
- [x] T008 [P] [US1] Byte-identity + idempotency tests in hedge_fund/web/test_recovery.py: pre-existing ledger/event bytes hash-identical before/after confirm; repeated identical confirm returns already-resolved with no second record

### Implementation for User Story 1

- [x] T009 [US1] Implement the evidence classification function in hedge_fund/runtime/reconciliation.py (research.md Decision 2): pure computation over verified replay + events + book evidence producing per-failure `verified`/`attestable`/`not_resolvable`; `verified` requires no pending decision at `expected_head`; structurally sound uncertainty requires explicit attestation; any structural failure blocks; error text alone never proves no effect (FR-002, FR-012)
- [x] T010 [US1] Extend recovery preview in hedge_fund/web/services.py with the `failures` array, `preview_head`, `preview_book_digest`, `preview_audit_digest`, `confirm_offered`, and `set_reason` per contract; classification comes only from T009
- [x] T011 [US1] Implement confirm orchestration in hedge_fund/web/services.py: take fund lock + control/audit lanes, hold audit lane through digest recheck and append, re-verify head/book/audit/failure-set equality, require attestations equal exactly the `attestable` subset, append decision record via T003; zero writes on any refusal (FR-006, FR-007, FR-008)
- [x] T012 [US1] Add confirm route in hedge_fund/web/app.py beside existing recovery routes (:315-329, :421-427) with the contract's outcome matrix (200 / 409 stale / 422 per-digest / contention / idempotent already-resolved)

**Checkpoint**: US1 fully functional headlessly (API + replay), MVP demo-able

---

## Phase 4: User Story 2 — Genuine ambiguity stays blocked (Priority: P2)

**Goal**: Every refusal class refuses with a distinct operator-visible reason and zero writes

**Independent Test**: quickstart.md Scenario B — each refusal fixture independently demonstrates refusal + unchanged state

### Tests for User Story 2 ⚠️ (write FIRST, ensure FAIL)

- [x] T013 [P] [US2] Post-effect-ambiguous failure test in hedge_fund/web/test_services.py: fixture with transmitted-fill/post-effect fields remains non-`verified`; if structural checks pass it classifies `attestable` and requires its digest in the operator attestation set (SC-002)
- [x] T014 [P] [US2] Corrupt replay / corrupt audit event tests in hedge_fund/web/test_recovery.py: recovery attempt refuses via existing corrupt state, zero writes, distinct from reconciliation-required (FR-009)
- [x] T015 [P] [US2] Book-mismatch refusal test in hedge_fund/web/test_recovery.py: perturbed book digest → mismatch refusal, zero writes
- [x] T016 [P] [US2] Stale-preview tests in hedge_fund/web/test_recovery.py: head/failure-set changes or any audit append (including Halt) between preview and confirm → 409 stale-preview, zero writes
- [x] T017 [P] [US2] Lane-contention test in hedge_fund/web/test_recovery.py: second writer holding fund lane → contention response, no concurrent append (FR-008)
- [x] T018 [US2] Crash/retry idempotency test in hedge_fund/web/test_recovery.py (quickstart Scenario C): fault injection between intent and completion; retry yields exactly one durable decision and consistent replay

### Implementation for User Story 2

- [x] T019 [US2] Close any gaps the failing tests expose in hedge_fund/runtime/reconciliation.py and hedge_fund/web/services.py refusal paths (expected small if T009–T012 are exact); each refusal MUST carry its distinct operator-visible reason per contract — verified: T013–T018 passed on first run; no production gap found

**Checkpoint**: US1 + US2 both green; negative space fully evidenced

---

## Phase 5: User Story 3 — Evidence transparency for the operator (Priority: P3)

**Goal**: Desk recovery panel shows per-failure classification, checks, and reasons; confirm affordance only when offered

**Independent Test**: frontend unit tests render mixed `verified`/`attestable`/`not_resolvable` evidence and confirm gating matches `confirm_offered`; each `attestable` digest needs its own acknowledgment (quickstart: P3 acceptance scenario 1)

### Tests for User Story 3 ⚠️ (write FIRST, ensure FAIL)

- [x] T020 [P] [US3] Display tests in frontend/src/pages/paper.test.tsx: per-failure list renders digest, time, error summary, classification, per-check detail and reason; confirm button enabled iff `confirm_offered=true`; not_resolvable failures show their evidence gap

### Implementation for User Story 3

- [x] T021 [US3] Extend frontend/src/pages/paper.tsx recovery panel (:710-745, :761-773 area) with the per-failure evidence list and gated confirm action wired to the T012 route, displaying 409/422 refusal reasons verbatim

**Checkpoint**: All three stories functional

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Evidence, invariants, and suite-level proof

- [ ] T022 Run quickstart.md Scenarios A–D and record exact commands, outputs, test IDs, platform, and recorded times in specs/009-legacy-failure-recovery/implementation-evidence.md (Scenarios A–C are INCONCLUSIVE on findings 1–4 source pending final reruns; Scenario D BLOCKED pending coordinator-managed T024)
- [x] T023 [P] Verify writer-map scan passes (hedge_fund/runtime/test_writer_map.py) and black/isort/flake8 are clean on touched files (line-length 420; do not reformat unrelated code) — writer map, Black, isort, and Black-compatible flake8 pass; default flake8 reports only four E203 findings reproduced on baseline
- [ ] T024 Run full suite `poetry run pytest hedge_fund -q` alone in this worktree (memory: concurrent pytest runs cause runner timeouts); every failure individually evidenced against baseline `e6f04d2` reproduction or fixed; record in implementation-evidence.md — **BLOCKED**: the prior `9914ef4` run ended `28 failed, 3029 passed, 62 skipped` but became inconclusive after overlap; coordinator owns the final full-suite run
- [x] T025 Update specs/007-rb3-halt-recovery/contracts/recovery-semantics.md with a one-paragraph pointer to the new decision-record condition (spec007 calls for entries for every reconciliation condition); Spec005's 423 row remains unchanged because denial-until-ready semantics still hold after a valid decision

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: none — start immediately
- **Phase 2 (Foundational)**: depends on T001/T002 fixtures — BLOCKS all stories
- **Phase 3 (US1)**: depends on Phase 2 — MVP
- **Phase 4 (US2)**: depends on Phase 3 implementation existing to refuse correctly (tests can be authored in parallel with Phase 3 tests, same files)
- **Phase 5 (US3)**: depends on T010/T012 contract shape being stable
- **Phase 6 (Polish)**: depends on all stories

### User Story Dependencies

- **US1 (P1)**: after Foundational; no dependency on other stories
- **US2 (P2)**: after US1 implementation (refusals guard the confirm path); independently testable per refusal class
- **US3 (P3)**: after US1 contract shape; independently testable via frontend unit tests

### Parallel Opportunities

- T002 parallel with T001 (same file, sequential edits fine if one assignee)
- T006/T007/T008 parallel-authored (different files for T006 vs T007/T008)
- T013–T018 parallel-authored within test files (one assignee, sequential commits)
- T023 parallel with T024 prep

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Phase 1 + Phase 2 → replay-level resolution proven headlessly
2. Phase 3 → preview + confirm API green on synthetic fixtures
3. **STOP and VALIDATE**: quickstart Scenario A end-to-end

### Incremental Delivery

1. MVP (US1) → demo-able recovery on synthetic root
2. US2 → negative-space evidence complete (SC-002/003/004)
3. US3 → operator-facing evidence display (SC-001 UX)
4. Phase 6 → Principle III evidence pack; production reconciliation remains a separately approved attended operator action (SC-005)

---

## Notes

- Single specialist (python-dev) executes sequentially per coordinator policy; [P] marks authoring independence, not concurrent agents
- No provider/LLM calls, no paid credits, no production data mutation anywhere in these tasks
- Production reconciliation of the two real funds is OUT OF SCOPE for implementation; requires separate attended operator approval (quickstart Scenario E)
