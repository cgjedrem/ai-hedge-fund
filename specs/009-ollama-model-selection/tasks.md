# Tasks: Ollama Model Selection

**Input**: Design documents from `specs/009-ollama-model-selection/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/contracts.md, quickstart.md

**Tests**: INCLUDED — the spec's acceptance scenarios and quickstart V1-V8 mandate mocked-metadata tests; Constitution III requires the full suite green.

**Organization**: Tasks grouped by user story (US1 P1 configure-anywhere, US2 P2 picker visibility, US3 P3 cloud governance).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, US3)
- Paths are repo-relative; tests are co-located under `hedge_fund/`

---

## Phase 1: Setup

**Purpose**: Baseline verification before any change

- [ ] T001 Run `poetry run pytest hedge_fund -q` on the clean feature-branch baseline and record the green/baseline result for later comparison (Principle III)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Single-source the model catalog with capability/cost-class metadata; all stories depend on it

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [ ] T002 Extend the Ollama section of `hedge_fund/llm/api_models.json` with `kimi-k3:cloud` and add `capability` (`chat`/`embedding`/`ocr`) and `cost_class` (`local`/`paid-cloud`) fields to Ollama entries; classify `kimi-k3:cloud` as chat + paid-cloud per data-model.md
- [ ] T003 Expose the new `capability` and `cost_class` classifiers through `hedge_fund/llm/registry.py` without changing provider resolution semantics for non-Ollama providers (FR-011)
- [ ] T004 [P] Write failing registry/catalog tests in `hedge_fund/llm/test_client.py` (or the existing registry test module) covering: new entry present with correct classifiers, non-Ollama entries byte-identical in meaning
- [ ] T005 Rework the model whitelist in `hedge_fund/runtime/configuration.py` (around lines 29-37, 526-541) to derive from the catalog instead of a parallel literal list, rejecting unknown tags with an explicit per-tag reason and rejecting non-chat capabilities for analysis use (FR-001, FR-002, FR-006)
- [ ] T006 [P] Write failing configuration tests in `hedge_fund/runtime/test_capture.py` covering: `kimi-k3:cloud` accepted, unknown tag rejected with explicit reason, embedding/OCR tag rejected with capability reason, precedence launch > env > persisted > default unchanged (V1, V6)

**Checkpoint**: Catalog is single-sourced; validation accepts `kimi-k3:cloud` and rejects invalid tags explicitly — user story implementation can now begin

---

## Phase 3: User Story 1 - Configure a daemon-available Ollama model (Priority: P1) 🎯 MVP

**Goal**: Any approved chat-capable Ollama tag is accepted identically via CLI flag, environment, persisted settings, and web settings write — with explicit rejection and zero silent substitution

**Independent Test**: quickstart V1 and V2 — same accept/reject outcome on every surface; invalid persisted preset produces an explicit TUI notice, not a silent default

### Tests for User Story 1

- [ ] T007 [P] [US1] Write failing CLI surfacing tests covering `--model kimi-k3:cloud` acceptance and unknown-tag fast failure with the catalog reason (not masked as `captured runtime settings are unavailable`) in the existing `hedge_fund/` CLI test module for `run.py`
- [ ] T008 [P] [US1] Write failing TUI test in `hedge_fund/tui/` covering: unknown persisted preset yields an explicit notice and NO silent substitution with a catalog default (V2)

### Implementation for User Story 1

- [ ] T009 [US1] Fix model-validation error surfacing in `hedge_fund/run.py` (around lines 967-980) so model-validation failures propagate their explicit reason while genuine settings-capture failures keep the existing mask (contract C4)
- [ ] T010 [US1] Replace the silent preset fallback in `hedge_fund/tui/home.py` (lines 58-70) with an explicit notice and unchanged effective selection (contract C5, FR-003); update the outdated comment

**Checkpoint**: US1 independently testable — V1/V2 scenarios pass

---

## Phase 4: User Story 2 - See what is actually selectable (Priority: P2)

**Goal**: Web settings picker shows selectable Ollama models with capability/cost-class state; paid-cloud entries visibly dispatch-gated, never presented as free local

**Independent Test**: quickstart V5 — `GET /api/settings` and `GET /api/catalog` carry classifier fields; settings page renders `kimi-k3:cloud` with a paid/cloud indicator

### Tests for User Story 2

- [ ] T011 [P] [US2] Write failing web tests in `hedge_fund/web/test_settings.py` covering: models array entries include `capability` and `cost_class`; rejection responses match contract C2 message shapes and contain no credential material (V5, V7)

### Implementation for User Story 2

- [ ] T012 [US2] Extend the settings/catalog model serialization in `hedge_fund/web/services.py` (around lines 2287-2319, 572-573) to include `capability` and `cost_class` per contract C1/C3, and specific rejection reasons per contract C2 (lines 2430-2451)
- [ ] T013 [P] [US2] Update the settings picker in `frontend/src/pages/settings.tsx` (around lines 27, 246-250) to render capability and a paid/cloud dispatch-gated indicator per contract C1

**Checkpoint**: US2 independently testable — V5 scenario passes

---

## Phase 5: User Story 3 - Cloud-labelled Ollama tags under explicit policy (Priority: P3)

**Goal**: `kimi-k3:cloud` classified paid/cloud: scheduled/unattended refusal, one-shot only with explicit per-operation authorization + enforced budget + verified cost model

**Independent Test**: quickstart V4 — scheduled path refuses regardless of env credentials; unauthorized one-shot refuses naming the requirement; missing cost model refuses with that exact reason

### Tests for User Story 3

- [ ] T014 [P] [US3] Write failing policy tests in `hedge_fund/runtime/test_policy.py` covering: `:cloud`-suffixed tags classified paid/cloud via `cost_class` metadata, scheduled/unattended refusal independent of credentials, one-shot refusal without explicit authorization (V4)
- [ ] T015 [P] [US3] Write failing dispatch tests in `hedge_fund/runtime/test_dispatch.py` covering: gated one-shot dispatch of a paid-cloud tag refused without verified cost model with that exact reason; loopback transport guardrails unchanged (V4, V7)

### Implementation for User Story 3

- [ ] T016 [US3] Key the paid/cloud classification in `hedge_fund/runtime/policy.py` (around lines 36, 270-273, 500-502) on the catalog `cost_class` metadata instead of hardcoded literals, preserving all existing classifications
- [ ] T017 [US3] Add the Ollama cloud cost-model entry in `hedge_fund/runtime/costs.py` (around lines 22-28) using operator-supplied pricing, recorded as operator-declared per research D7; if pricing is unavailable at implementation time, dispatch MUST refuse with the explicit "no verified cost model" reason — never substitute or infer pricing

**Checkpoint**: US3 independently testable — V4 scenario passes

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Regression safety and governance compliance across all stories

- [ ] T018 Verify the writer-map AST scan `hedge_fund/runtime/test_writer_map.py` still passes; add WRITER_MAP entries for any new raw writes introduced (repo memory: new write_text/write_bytes/rename/mkdir/os.open need entries)
- [ ] T019 [P] Run black (line-length 420), isort (black profile), and flake8 on all changed files (Principle VI)
- [ ] T020 Run the full suite `poetry run pytest hedge_fund -q` and confirm green with no new failures versus the T001 baseline (Principle III, SC-005)
- [ ] T021 Execute quickstart.md scenarios V1-V8 as the acceptance walk and record results in the spec directory

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies
- **Foundational (Phase 2)**: Depends on T001 — BLOCKS all user stories
- **US1 (Phase 3)**: Depends on Foundational
- **US2 (Phase 4)**: Depends on Foundational; integrates with US1 validation but independently testable
- **US3 (Phase 5)**: Depends on Foundational; policy gating composes with US1 acceptance
- **Polish (Phase 6)**: Depends on all stories complete

### User Story Dependencies

- **US1 (P1)**: No dependencies on other stories
- **US2 (P2)**: Consumes the catalog classifiers from Foundational; no US1 dependency
- **US3 (P3)**: Consumes `cost_class` from Foundational; gates dispatch of models US1 made selectable

### Within Each User Story

- Tests written first and confirmed failing before implementation
- Backend serialization before frontend rendering (US2)
- Classification before cost-model gating (US3)

### Parallel Opportunities

- T003/T004 (registry + its tests) parallel with T005/T006 (configuration + its tests) — different files
- Within stories: test tasks marked [P] are parallel; T013 (frontend) parallel with backend work once contract C1 fields exist

---

## Parallel Example: Foundational Phase

```bash
# After T002 (catalog data) lands:
Task: "Expose classifiers through hedge_fund/llm/registry.py (T003)"
Task: "Derive configuration whitelist from catalog in hedge_fund/runtime/configuration.py (T005)"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1-2 (baseline + single-sourced catalog)
2. Complete Phase 3 (US1) — operator can configure `kimi-k3:cloud` everywhere with explicit rejections
3. **STOP and VALIDATE**: V1/V2 quickstart scenarios

### Incremental Delivery

1. Foundational → catalog with classifiers
2. US1 → consistent configuration acceptance (MVP)
3. US2 → picker visibility
4. US3 → paid/cloud governance (required before any real `kimi-k3:cloud` dispatch)
5. Polish → full-suite green + quickstart acceptance walk

**Note**: US3 is P3 in user value but is a constitutional precondition for any live cloud-model use; the feature is not operator-usable for actual `kimi-k3:cloud` inference until US3 and the D7 cost-model input land.
