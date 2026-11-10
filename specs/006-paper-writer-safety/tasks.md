# Tasks: Paper Writer Safety — Intent Fencing and Operation Deduplication

**Input**: Design documents from `/specs/006-paper-writer-safety/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/refusal-contract.md, quickstart.md

**Tests**: Included — Constitution III requires co-located green tests and the spec's acceptance scenarios are test-defined. Write failing tests before implementation within each story.

**Organization**: Tasks grouped by user story for independent implementation and testing.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: US1 = unresolved tick-intent fence (P1), US2 = logical-operation dedup (P2)

## Phase 1: Setup

**Purpose**: Baseline verification before any change

- [ ] T001 Confirm clean baseline at HEAD `e061e9c`: `git status --porcelain` empty and record the exact HEAD in the implementation evidence note
- [ ] T002 [P] Run focused baseline suites and record results as pre-change evidence: `poetry run pytest hedge_fund/paper/test_ledger.py hedge_fund/paper/test_tick.py hedge_fund/runtime/test_operations.py -q`
- [ ] T003 [P] Verify synthetic test-root bootstrap path works (`hedge_fund/runtime/test_bootstrap.py` usage in existing tests) so all new tests use owned synthetic fixtures only

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Shared refusal reason vocabulary both stories and all entry points consume

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [ ] T004 Add shared refusal reason constants `unresolved-tick-intent` and `duplicate-logical-operation` plus their structured field carriers, placed with the existing refusal/error definitions used by `hedge_fund/paper/ledger.py` and `hedge_fund/runtime/operations.py`, matching `specs/006-paper-writer-safety/contracts/refusal-contract.md`
- [ ] T005 [P] Add failing contract-shape tests for both refusal reasons (fields present per contract) in `hedge_fund/paper/test_ledger.py` and `hedge_fund/runtime/test_operations.py`

**Checkpoint**: Reason vocabulary exists and is importable by ledger, operations, CLI, and web layers

---

## Phase 3: User Story 1 — Crashed session blocks silent re-run (Priority: P1) 🎯 MVP

**Goal**: Any new-identity session request is refused while an unresolved tick intent exists on the fund, uniformly across CLI, web worker, and owned-runner child; reconciliation unblocks; same-identity retry is unaffected.

**Independent Test**: Synthetic crash-after-intent fixture → new-identity tick refused with `unresolved-tick-intent`; same-identity retry reaches existing replay path; after reconciliation new sessions admitted; no-intent baseline unchanged.

### Tests for User Story 1 — write FIRST, ensure they FAIL

- [ ] T006 [P] [US1] Add failing fence tests in `hedge_fund/paper/test_ledger.py`: unresolved intent blocks new-identity request; outcome events (completion, `tick_failed`, redo supersession) resolve it; torn intent metadata fails closed; multiple unresolved intents reported oldest-first without auto-resolution; historical pre-feature intent events in old fixture ledgers parse and classify correctly
- [ ] T007 [P] [US1] Add failing admission-path tests in `hedge_fund/paper/test_tick.py`: manual/CLI tick refused with reason fields populated; no partial session effects written; same-request-ID retry bypasses the fence into the existing replay/reconciliation path (`paper/ledger.py:760-842` behavior preserved); deliberate redo (`tick --again`) not misclassified
- [ ] T008 [P] [US1] Add failing cross-entry-point test in `hedge_fund/runtime/test_writer_races.py`: owned-runner child session request against a synthetic fund with an unresolved intent is skipped as blocked and the refusal reason is durably recorded (no retry escalation)

### Implementation for User Story 1

- [ ] T009 [US1] Implement unresolved-intent read model on `Ledger` in `hedge_fund/paper/ledger.py`: derive unresolved intents from the existing event stream (intent without matching outcome for the same request identity), fail closed on torn metadata, oldest-first reporting; reads only — no new write kind
- [ ] T010 [US1] Implement the admission guard composing with `require_ready_for_work` in `hedge_fund/paper/ledger.py`, raising/carrying the `unresolved-tick-intent` refusal with contract fields (T004, T009)
- [ ] T011 [US1] Wire the guard into tick admission in `hedge_fund/paper/tick.py` so CLI, web worker, and owned-runner child (all converging on this path per discovery §1) are fenced; verify placement is after same-request-ID replay lookup (FR-003)
- [ ] T012 [US1] Surface the refusal in `hedge_fund/run.py` (CLI: non-zero exit, reason + fields on stderr), `hedge_fund/web/services.py` (existing operation-refusal error shape, no worker dispatch), and `hedge_fund/runtime/owned_runner_child.py` (session skipped as blocked, refusal reason recorded via the existing durable runner-state write path, no retry escalation)
- [ ] T013 [US1] If T009–T012 introduced any new raw write, add the `WRITER_MAP` entry in `hedge_fund/runtime/test_writer_map.py` citing the covering tests; otherwise assert no entry needed
- [ ] T014 [US1] Run `poetry run pytest hedge_fund/paper hedge_fund/runtime/test_writer_races.py hedge_fund/web -q` and confirm green including all US1 tests

**Checkpoint**: US1 independently functional — crash-after-intent can never silently produce a second session

---

## Phase 4: User Story 2 — Double-submitted action recognized as one operation (Priority: P2)

**Goal**: The same logical action (fund, action type, target session, reviewed payload) submitted under two independently generated request IDs executes at most once while non-terminal; terminal-failed frees the key for deliberate retry.

**Independent Test**: Synthetic fund; duplicate logical action under fresh request IDs → exactly one execution, second refused `duplicate-logical-operation` referencing the first operation ID; different session/action → independent; terminal-failed prior → resubmission admitted; store restart between submissions → dedup holds.

### Tests for User Story 2 — write FIRST, ensure they FAIL

- [ ] T015 [P] [US2] Add failing derivation tests in `hedge_fund/runtime/test_operations.py`: identical logical actions across entry-point input shapes derive identical keys; different session/action/payload derive different keys; canonical serialization is order-stable
- [ ] T016 [P] [US2] Add failing acceptance dedup tests in `hedge_fund/runtime/test_operations.py`: non-terminal match refuses with contract fields; terminal-failed frees the key; terminal-succeeded frees the key (downstream head/session conflict governs); same-request-ID replay and changed-payload conflict paths (`operations.py:442-516`) unchanged; pre-feature records without the field never match
- [ ] T017 [P] [US2] Add failing durability and race tests in `hedge_fund/runtime/test_writer_races.py`: fresh store handle after simulated restart still dedups; concurrent duplicate submissions across CLI child vs web admission produce exactly one execution and one recorded fake fill with matching book

### Implementation for User Story 2

- [ ] T018 [US2] Implement `logical_key` derivation (canonical digest over fund identity, action type, target session/due set, reviewed payload digest) at acceptance in `hedge_fund/runtime/operations.py` (research Decision 4)
- [ ] T019 [US2] Persist `logical_key` as a new optional field on the durable operation record via the existing operation-store write paths in `hedge_fund/runtime/operations.py`; confirm old records remain byte-identical and replayable (Constitution I)
- [ ] T020 [US2] Implement acceptance-time dedup lookup in `hedge_fund/runtime/operations.py` under the existing registry lock: non-terminal same-key match refuses `duplicate-logical-operation` referencing the existing operation ID; lookup runs after same-request-ID replay/conflict resolution
- [ ] T021 [US2] Surface the refusal in `hedge_fund/run.py` and `hedge_fund/web/services.py` per contract (mirror T012 pattern)
- [ ] T022 [US2] If T018–T021 introduced any new raw write, add the `WRITER_MAP` entry in `hedge_fund/runtime/test_writer_map.py`; otherwise assert no entry needed
- [ ] T023 [US2] Run `poetry run pytest hedge_fund/runtime hedge_fund/web -q` and confirm green including all US2 tests

**Checkpoint**: US1 AND US2 both independently functional

---

## Phase 5: Polish & Cross-Cutting Concerns

**Purpose**: Governance evidence and validation closure

- [ ] T024 [P] Run style checks on changed scopes: `poetry run black --check`, `isort --check-only`, `flake8` on changed files (line-length 420 preserved, no reformatting of untouched code)
- [ ] T025 [P] Verify no UTF-8 BOM in any touched YAML/spec file and no protected/real fund root was accessed (review test fixtures and `git diff`)
- [ ] T026 Execute all quickstart.md scenarios (A, B) and record exact commands, results, durations, platform, and HEAD in `specs/006-paper-writer-safety/implementation-evidence.md`
- [ ] T027 Run the full suite alone (≈40 min, no concurrent pytest): `poetry run pytest hedge_fund -q`; any failure individually evidenced as unchanged baseline per Constitution III in `specs/006-paper-writer-safety/implementation-evidence.md` with exact test ID, expected/observed, source/build, platform, recorded time, fixture provenance, and pre-change reproduction
- [ ] T028 Update `specs/006-paper-writer-safety/checklists/requirements.md` and spec status to reflect delivered state; append durable facts to `memory.md`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: none — start immediately
- **Foundational (Phase 2)**: depends on Phase 1 — BLOCKS both stories
- **US1 (Phase 3)**: depends on Phase 2 — MVP, deliver first
- **US2 (Phase 4)**: depends on Phase 2 — independent of US1 (different files: operations.py vs ledger/tick), sequential after US1 under single-specialist execution
- **Polish (Phase 5)**: depends on US1 + US2

### Within Each Story

- Tests (T006–T008, T015–T017) MUST fail before implementation begins
- Read model/derivation (T009, T018) before guards/lookups (T010, T020) before surfacing (T012, T021)
- Writer-map assertion (T013, T022) before the story's green-run gate (T014, T023)

### Parallel Opportunities

- T002 ∥ T003; T005 pair internally; T006 ∥ T007 ∥ T008; T015 ∥ T016 ∥ T017; T024 ∥ T025
- US1 and US2 are file-disjoint and could parallelize, but this pipeline runs one specialist sequentially (P1 → P2)

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Phases 1–2 → foundation
2. Phase 3 (US1) → validate independently per quickstart Scenario A → shippable safety increment
3. Phase 4 (US2) → validate per quickstart Scenario B
4. Phase 5 → governance evidence closes the feature

### Incremental Delivery

Each story is a complete, independently testable safety guarantee; either alone is mergeable value. No PR is opened by this pipeline (not requested); delivery is commits on `cgjedrem-didactic-meme` plus evidence artifacts.
