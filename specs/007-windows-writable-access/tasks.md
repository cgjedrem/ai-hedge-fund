# Tasks: Native Single-User Writable Access for Existing Funds

**Input**: Design documents from `/specs/007-windows-writable-access/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/handover-cli.md, quickstart.md

**Tests**: Included — Constitution III mandates co-located green tests; all new behavior is exercised on synthetic test-owned roots only (`enroll_synthetic_root`, TEST_MODE, `outputs/spec005-test-*` + `.test-owned`). No task touches the real root `C:\Users\ChristianGjedrem\.hedge-fund`.

**Organization**: Tasks grouped by user story (US1 writable access P1, US2 auditable trust grant P2, US3 protected funds/markers P3).

## Format: `[ID] [P?] [Story] Description`

## Phase 1: Setup (Shared Infrastructure)

- [X] T001 Confirm baseline: `poetry run pytest hedge_fund/runtime hedge_fund/tui -q` on the branch head; record any pre-existing failures with exact test IDs as baseline evidence (Constitution III)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Attestation model, Windows scope identity, and relocation split that all stories build on.

- [X] T002 Add destination-bound attestation artifact schema + storage helpers (kinds `stale-marker-retirement`, `protected-fund-inclusion`; fields per data-model.md incl. `source_evidence_digest`, destination `root_binding`) in hedge_fund/runtime/handover.py; add WRITER_MAP entries citing tests in hedge_fund/runtime/test_writer_map.py
- [X] T003 [P] Add Windows runtime-scope identity (machine + account SID + root volume) to `_runtime_scope_identity` in hedge_fund/runtime/handover.py:202-235, keeping non-Windows behavior unchanged
- [X] T004 Extend `inspect-source` in hedge_fund/runtime/handover.py + hedge_fund/run.py with `--evidence-out PATH`: write the source evidence bundle OUTSIDE the source tree; verify zero source-tree writes (snapshot test)
- [X] T005 Split relocation into `relocate-copy` (hash-verified copy incl. `runtime/private/v1/settings.json`; no target inventory validation, no enrollment) and `relocate-finalize` (attestation-aware inventory validation + enrollment) in hedge_fund/runtime/handover.py:971-1149 + hedge_fund/run.py; keep `relocate-from` behavior intact or route it through the two stages without semantic change
- [X] T006 Tests: attestation schema round-trip + wrong-root binding refusal in hedge_fund/runtime/test_handover.py; Windows scope grant/scope-mismatch denial in hedge_fund/runtime/test_write_authority.py; relocate-copy settings transfer + digest-mismatch + interrupted-copy in hedge_fund/runtime/test_handover.py

**Checkpoint**: Foundation ready — attestation artifacts recordable at synthetic destinations; Windows scope identity exists; two-stage relocation works on synthetic roots.

---

## Phase 3: User Story 1 - Writable access to all existing funds (Priority: P1) 🎯 MVP

**Goal**: Operator can open the native TUI on the trusted destination root and perform writes; history replays byte-identically.

**Independent Test**: Quickstart Scenario B steps 5-8 on a synthetic two-fund fixture (no protected names): relocate-finalize → inspect → trust-single-writer → TUI write succeeds; prior records hash-identical.

### Tests for User Story 1

- [X] T007 [P] [US1] trust-single-writer accepts valid Windows scope and denies tampered scope / stale challenge / inventory mismatch in hedge_fund/runtime/test_write_authority.py
- [X] T008 [P] [US1] TUI admitted-write tests: enrolled+trusted root write succeeds with held owner/lane and operation-bound authorization; unenrolled or untrusted root still denied in hedge_fund/tui/test_admission_regressions.py (extend)

### Implementation for User Story 1

- [X] T009 [US1] Accept the Windows runtime scope in `trust-single-writer` ceremony (challenge, 15-min expiry, exclusive admission, inventory recheck) in hedge_fund/runtime/handover.py:431-565,641-686
- [X] T010 [US1] Convert the enrolled-root blanket rejections into admission checks (held owner/lane + valid trust required; operation-bound authorization) in hedge_fund/tui/funds.py:34-45 and hedge_fund/tui/paper.py:511-516 — no bypass path
- [X] T011 [US1] Second-participating-writer denial test: concurrent TUI/CLI write attempt on a trusted root denied or serialized in hedge_fund/tui/test_admission_regressions.py

**Checkpoint**: Synthetic two-fund root end-to-end writable through the TUI; all denial paths green.

---

## Phase 4: User Story 2 - Explicit, auditable trust grant (Priority: P2)

**Goal**: Every grant/attestation is a durable, inspectable artifact; denials are clear and create no partial state.

**Independent Test**: After synthetic enablement, artifacts alone reconstruct who/what/when/which-inventory; write attempted before grant is denied with the resolving command printed.

### Tests for User Story 2

- [X] T012 [P] [US2] Denial-path matrix (unenrolled, untrusted, scope mismatch, inventory mismatch, second writer) prints failed precondition + resolving command and writes no partial state in hedge_fund/runtime/test_write_authority.py and hedge_fund/runtime/test_handover.py

### Implementation for User Story 2

- [X] T013 [US2] Extend `handover inspect` output to list recorded attestation artifacts and remaining blockers with the exact resolving subcommand each in hedge_fund/runtime/handover.py + hedge_fund/run.py
- [X] T014 [US2] Error-contract pass: exit code 2 family preserved for unenabled roots; every new denial follows the contract in specs/007-windows-writable-access/contracts/handover-cli.md §Error contract

**Checkpoint**: Trust grant fully reconstructible from on-disk artifacts (SC-005).

---

## Phase 5: User Story 3 - Safe resolution of protected funds and stale markers (Priority: P3)

**Goal**: Attestation-based inclusion of `umbrella`/`watchtower`/`watchtower-weekly` under original names and retirement of the two stale `runner.pid` markers — at the destination only.

**Independent Test**: Quickstart Scenario B steps 1-5 on a synthetic fixture with 3 protected funds + 2 stale markers: source snapshot unchanged; destination attested and enrolled; unattested variants still refuse.

### Tests for User Story 3

- [ ] T015 [P] [US3] attest-stale-marker: success, live-process refusal (real dummy process), missing marker, evidence-digest mismatch, idempotent repeat in hedge_fund/runtime/test_handover.py
- [ ] T016 [P] [US3] attest-protected-fund: success under original name, unknown/unprotected name refusal, rename-evasion impossibility in hedge_fund/runtime/test_handover.py
- [ ] T017 [P] [US3] Root-layer authz: attested protected fund writable; unattested protected name denied; alias/evasion paths denied in hedge_fund/runtime/test_root.py
- [ ] T018 [P] [US3] Source-immutability test: full procedure leaves source tree hash-identical in hedge_fund/runtime/test_handover.py

### Implementation for User Story 3

- [ ] T019 [US3] `handover attest-stale-marker --marker RELPATH --source-evidence DIGEST --operator-statement TEXT` (destination-bound; liveness check; marker retired into destination root-private attestation area) in hedge_fund/runtime/handover.py + hedge_fund/run.py
- [ ] T020 [US3] `handover attest-protected-fund --fund NAME --source-evidence DIGEST --operator-statement TEXT` (destination-bound) in hedge_fund/runtime/handover.py + hedge_fund/run.py
- [ ] T021 [US3] Attestation-aware protected-name authorization preserving default denial + alias checks in hedge_fund/runtime/root.py:217-270,489-511 and hedge_fund/runtime/admission.py:956-962
- [ ] T022 [US3] Wire attestation awareness into `build_head_inventory` (hedge_fund/runtime/handover.py:1159-1218) and `relocate-finalize` validation: attested blockers appear as attestation-referenced entries; unattested still refuse

**Checkpoint**: Full synthetic rehearsal (Quickstart Scenario B) passes end-to-end.

---

## Phase 6: Polish & Cross-Cutting Concerns

- [ ] T023 Run Quickstart Scenario A: `poetry run pytest hedge_fund/runtime -q` then full `poetry run pytest hedge_fund -q`; record per-failure baseline evidence per Constitution III
- [ ] T024 Interruption drill (Quickstart B step 10): kill mid-relocate-copy; source untouched; destination marked incomplete; rerun succeeds — automated test
- [ ] T025 [P] black/isort/flake8 clean on changed files; WRITER_MAP audit passes (`poetry run pytest hedge_fund/runtime/test_writer_map.py -q`)
- [ ] T026 [P] Update README/docs handover section references for the two-stage relocation + attestation subcommands (docs only)
- [ ] T027 Produce the real-cutover runbook artifact (Quickstart Scenario C detail) for separate operator authorization — document only, no execution

---

## Dependencies & Execution Order

- Phase 1 → Phase 2 → stories. US1 (P1) first — MVP. US2/US3 follow; US3 depends on T002/T005 artifacts but not on US1's TUI work.
- Sequential execution (single developer pipeline): T001 → T006 → T007-T011 → T012-T014 → T015-T022 → T023-T027.

### Parallel Opportunities

- T002+T003, T007+T008, T015-T018, T025+T026 marked [P] touch disjoint code regions.

---

## Implementation Strategy

MVP = Phases 1-3 (synthetic writable TUI). US3 then unlocks the real root's protected funds. Full-suite evidence (T023) gates QA review. Real cutover (T027 runbook) requires separate explicit operator authorization and is NOT part of implementation.