---

description: "Task list for curated financial news aggregation"
---

# Tasks: Curated Financial News Aggregation

**Input**: Design documents from `specs/010-curated-news-aggregation/`

**Prerequisites**: `plan.md`, `spec.md`, `research.md`, `data-model.md`, `contracts/`, and `quickstart.md`

**Tests**: Required. Execute one failing public-seam test followed by its minimal implementation; do not write all tests horizontally. All tests use committed fixtures, controlled clocks/DNS, and temporary synthetic roots without real network, sleeps, paid calls, or real desk roots.

**Organization**: Tasks are grouped by user story. Foundational contracts are completed before story integration.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Independent files and no incomplete dependency; TDD slices still run sequentially.
- **[Story]**: US1 analyst news, US2 filings/macro, US3 safe operator refresh.
- Every implementation task follows its corresponding red test.

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Establish reproducible dependencies and the isolated feature package.

- [x] T001 Add exact `feedparser==6.0.14` and `edgartools==6.4.0` dependencies plus packaged news data configuration in `pyproject.toml` and regenerate `poetry.lock` without unrelated upgrades.
- [x] T002 Create the narrowly exporting feature package and empty synthetic fixture directory in `hedge_fund/news/__init__.py` and `hedge_fund/news/fixtures/`.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Build and verify catalog, normalization, parsing, persistence, guarded transport, and finite refresh contracts before analyst or CLI integration.

**Critical**: No user story work begins until these contracts pass independently.

- [x] T003 Add failing catalog loading/semantic-validation tests for provenance, approved hosts, exclusions, source bindings, and stricter-only limits in `hedge_fund/news/test_catalog.py`.
- [x] T004 Implement immutable catalog/source/limit/curation models and strict Pydantic loading in `hedge_fund/news/models.py` and `hedge_fund/news/catalog.py` to satisfy T003.
- [x] T005 [P] Add the reviewed registry provenance and enabled Fed/BLS/BEA/SEC feed definitions, with unselected company candidates disabled, in `hedge_fund/news/catalog.json` and validate against `specs/010-curated-news-aggregation/contracts/catalog-v1.schema.json`.
- [x] T006 Add failing URL/title/timestamp normalization and conservative identity-key tests in `hedge_fund/news/test_normalize.py`.
- [x] T007 Implement semantics-preserving normalization, inert text handling, timestamp precision, and deterministic identity keys in `hedge_fund/news/normalize.py` to satisfy T006.
- [x] T008 Add failing bytes-only RSS/Atom parsing, malformed-feed, entry-bound, and no-secondary-fetch tests in `hedge_fund/news/test_parsing.py`.
- [x] T009 Implement bounded feedparser response-bytes parsing and inert attribution mapping in `hedge_fund/news/parsing.py` to satisfy T008.
- [x] T010 Add failing restart, missing/corrupt-state, atomic revision/run-id, alias, conservative merge, attribution, and health transaction tests in `hedge_fund/news/test_store.py`.
- [x] T011 Implement immutable news/health/run state models and root-admitted atomic JSON `NewsStore` behavior in `hedge_fund/news/models.py` and `hedge_fund/news/store.py` to satisfy T010.
- [x] T012 Add failing exact-origin authorization, SEC identity, redirect, DNS-pinning, byte-limit, and sanitized-failure contract tests in `hedge_fund/news/test_transport.py`, `hedge_fund/runtime/test_endpoints.py`, and `hedge_fund/runtime/test_policy.py`.
- [x] T013 Implement the `curated-news` free-data target/policy validation and per-origin authority in `hedge_fund/runtime/endpoints.py` and `hedge_fund/runtime/policy.py` to satisfy the T012 policy cases.
- [x] T014 Implement manual per-hop guarded streaming transport using existing dispatch/DNS pinning in `hedge_fund/news/transport.py` to satisfy the remaining T012 cases.
- [x] T015 Add failing finite scheduler tests for source isolation, shared host cadence, deterministic ordering, deadline gates, and no real sleeping in `hedge_fund/news/test_refresh.py`.
- [x] T016 Implement bounded refresh coordination, per-source outcomes, and atomic partial commits in `hedge_fund/news/refresh.py` to satisfy T015.

**Checkpoint**: Catalog, parsing, storage, transport, and refresh protocols are independently verified.

---

## Phase 3: User Story 1 - Analysts receive curated company and market news (Priority: P1) MVP

**Goal**: Persist approved company/general news and expose it through the existing analyst `get_news` workflow with stable deduplication and provenance.

**Independent Test**: Refresh general and official IR fixtures, reconstruct the store/client, and verify relevant deduplicated `CompanyNews`, timestamps, attributions, retained history, and unchanged non-news delegation without network access.

- [x] T017 [US1] Add a failing representative refresh/restart/100-repeat analyst-retrieval test using general and company sources in `hedge_fund/news/test_integration.py`.
- [x] T018 [P] [US1] Create independent synthetic general-news and official IR RSS/Atom fixtures, including equivalent URLs and cross-source attribution cases, in `hedge_fund/news/fixtures/general.xml` and `hedge_fund/news/fixtures/ir.xml`.
- [x] T019 [US1] Add failing additive `CompanyNews` projection, rich query/health, deterministic ordering, and non-news delegation tests in `hedge_fund/news/test_client.py`.
- [x] T020 [US1] Implement optional news metadata fields and the outer `CuratedNewsDataClient` adapter in `hedge_fund/data/models.py` and `hedge_fund/news/client.py` to satisfy T019.
- [x] T021 [US1] Add failing production-composition tests proving CLI, owned runner, and web use the local outer adapter while injected factories retain existing behavior in `hedge_fund/news/test_composition.py`.
- [x] T022 [US1] Wire production local-news composition without scheduled network refresh in `hedge_fund/run.py`, `hedge_fund/runtime/owned_runner_child.py`, and `hedge_fund/web/services.py` to satisfy T021.
- [x] T023 [US1] Add failing offline status/manual refresh CLI contract tests for selectors, JSON output, no-op, and network authorization in `hedge_fund/news/test_cli.py`.
- [x] T024 [US1] Implement `news refresh` and strictly offline `news status` using the shared catalog/service/store in `hedge_fund/run.py` to satisfy T023.

**Checkpoint**: User Story 1 is independently functional through existing analyst retrieval and explicit CLI refresh.

---

## Phase 4: User Story 2 - Analysts receive filings and macro releases alongside news (Priority: P2)

**Goal**: Normalize SEC filings/8-K metadata and official Fed/SEC/BLS/BEA releases into the same durable analyst experience.

**Independent Test**: Retrieve bounded SEC submissions through fake guarded transport, parse them with the isolated pinned EDGAR worker, refresh official macro fixtures, and verify classifications, dates, canonical links, and accession deduplication after restart.

- [x] T025 [US2] Add failing EDGAR 6.4.0 worker tests for offline `filings.recent` parsing, audit denial, root-confined import effects, typed output, forbidden document APIs, and fail-closed mismatches in `hedge_fund/news/test_edgar_worker.py`.
- [x] T026 [US2] Implement the isolated audited `python -I -B` EDGAR parser worker and bounded typed IPC in `hedge_fund/news/edgar_worker.py` to satisfy T025.
- [x] T027 [US2] Add failing guarded SEC submissions retrieval, configured-form filtering, date-only fallback, no-pagination, and filing-index-link tests in `hedge_fund/news/test_filings.py`.
- [x] T028 [US2] Implement the parent-owned SEC retrieval and offline `FilingRecord` adapter in `hedge_fund/news/filings.py` to satisfy T027.
- [x] T029 [US2] Add a failing filing/8-K/macro end-to-end analyst retrieval and restart test in `hedge_fund/news/test_integration.py`.
- [x] T030 [P] [US2] Add synthetic SEC submissions/8-K and Fed/SEC/BLS/BEA fixtures and enable their reviewed official catalog entries in `hedge_fund/news/fixtures/submissions.json`, `hedge_fund/news/fixtures/macro.xml`, and `hedge_fund/news/catalog.json`.
- [x] T031 [US2] Add failing SEC accession identity, ambiguous acceptance-time, legacy-items, and conflicting-filing dedup tests in `hedge_fund/news/test_store.py`.
- [x] T032 [US2] Implement any required accession/date/metadata merge corrections in `hedge_fund/news/normalize.py`, `hedge_fund/news/models.py`, and `hedge_fund/news/store.py` to satisfy T031 without regressing prior slices.

**Checkpoint**: User Stories 1 and 2 both pass independently and together using the same store and analyst adapter.

---

## Phase 5: User Story 3 - Operators refresh sources safely and can diagnose health (Priority: P3)

**Goal**: Prove hostile destinations, bounded execution, partial failure, content-rights limits, and operator diagnostics remain fail-closed and deterministic.

**Independent Test**: Run adversarial transport fixtures, 50-source recorded-clock scheduling, interrupted/failed persistence, and CLI failure scenarios without real network or sleeps; verify prior items and truthful health survive.

- [x] T033 [US3] Add failing SSRF/redirect/DNS-rebinding denial-matrix cases covering every hop and mixed/non-public answers in `hedge_fund/news/test_transport.py`.
- [x] T034 [US3] Correct guarded destination and per-hop transport enforcement in `hedge_fund/news/transport.py` and `hedge_fund/runtime/endpoints.py` to satisfy T033.
- [x] T035 [US3] Add the failing 50-source global/per-host concurrency, cadence, request/resource, deadline, and no-late-start recorded-event test in `hedge_fund/news/test_refresh.py`.
- [x] T036 [US3] Correct shared scheduling, budgets, and worker cleanup in `hedge_fund/news/refresh.py` to satisfy T035 without real sleeps.
- [x] T037 [US3] Add failing partial-failure, healthy-empty/degraded/failed/stale, older-run fence, retry-idempotency, and pre/post-replace interruption tests in `hedge_fund/news/test_store.py` and `hedge_fund/news/test_refresh.py`.
- [x] T038 [US3] Correct atomic commit/health/outcome behavior in `hedge_fund/news/store.py` and `hedge_fund/news/refresh.py` to satisfy T037.
- [x] T039 [US3] Add failing hostile feed/content-rights cases for active markup, embedded resources, oversize/decompression bombs, excess entries, false empty feeds, and summary policy in `hedge_fund/news/test_parsing.py` and `hedge_fund/news/test_transport.py`.
- [x] T040 [US3] Correct parser/transport bounds and inert metadata handling in `hedge_fund/news/parsing.py` and `hedge_fund/news/transport.py` to satisfy T039.
- [x] T041 [US3] Add failing CLI tests for SEC-plan identity preflight, corrupt store, partial exit status, unknown/disabled selectors, and sanitized output in `hedge_fund/news/test_cli.py`.
- [x] T042 [US3] Correct CLI validation/error/reporting behavior in `hedge_fund/run.py` and `hedge_fund/news/refresh.py` to satisfy T041.

**Checkpoint**: All three stories satisfy the offline acceptance scenarios and fail closed without affecting unrelated providers or ledger/broker behavior.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Document operator use and establish full regression, style, and two-axis review evidence.

- [x] T043 [P] Document catalog review, synthetic-root offline validation, manual refresh/status, SEC identity, rights limits, and the absence of automatic scheduling in `README.md` and `specs/010-curated-news-aggregation/quickstart.md`.
- [x] T044 Run focused news/analyst/runtime regression commands and resolve all new failures recorded in `specs/010-curated-news-aggregation/tasks.md`.
- [x] T045 Run the full `poetry run pytest hedge_fund -q` suite and record exact results or individually reproduced pre-change baseline failures in `specs/010-curated-news-aggregation/acceptance-evidence.md`.
- [x] T046 Run Black line-length-420, isort Black-profile, and flake8 checks on every changed Python path and record results in `specs/010-curated-news-aggregation/acceptance-evidence.md`.
- [x] T047 Perform Standards-axis and Spec-axis review of the merge-base diff and resolve hard findings in `hedge_fund/news/`, `hedge_fund/run.py`, `hedge_fund/runtime/`, `hedge_fund/data/models.py`, and `hedge_fund/web/services.py` before delivery.
- [x] T048 Record verified acceptance scenarios, unperformed live/deployment checks, and final artifact/test references in `specs/010-curated-news-aggregation/acceptance-evidence.md`.
- [ ] T049 Record the approved implementation outcome, verification evidence, remaining limitations, and no-PR delivery state in `memory.md` and inspect the final diff for `specs/010-curated-news-aggregation/`.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup**: Starts immediately after Gate 1 approval; no other-phase dependency.
- **Foundational**: Depends on Setup and blocks all user stories.
- **US1**: Depends on Foundational; is the MVP.
- **US2**: Depends on Foundational and the shared US1 store/client composition; filing-specific code can be reviewed independently after T014.
- **US3**: Hardens all prior slices and depends on their initial green states.
- **Polish**: Depends on all three stories.

### Within Each Slice

1. Confirm the public seam and write exactly one behavior-focused failing test.
2. Run that test and preserve the red result.
3. Write only enough implementation to pass it; rerun the containing file.
4. Continue to the next behavior without batching tests or speculative features.

### Parallel Opportunities

- T005 catalog data can be prepared independently once T004 defines validation.
- T018 fixture preparation is file-independent from the client implementation after its preceding red/green slices.
- T030 fixture data is file-independent from EDGAR adapter implementation after T026/T028 contracts are understood.
- T043 documentation can be prepared independently once behavior is stable.
- Parallel markers do not authorize multiple simultaneous red tests or unreviewed parallel edits to shared files.

## Parallel Example: User Story 1

```text
After the preceding slices are green:
Task T018: Prepare independent general/IR fixture files.
Task T021: Prepare the separate production-composition contract test.
Execute actual TDD red/green slices sequentially when integrating either result.
```

## Parallel Example: User Story 2

```text
After T026/T028 establish their contracts:
Task T030: Prepare independent submissions/macro fixtures and catalog data.
Task T031: Prepare the separate accession/date dedup test.
Run and integrate each test slice sequentially.
```

## Parallel Example: User Story 3

```text
No hostile-test tasks are marked parallel: each security regression is driven red-to-green independently to avoid masking failures.
```

## Implementation Strategy

### MVP First

1. Complete Setup and Foundational contracts.
2. Complete US1 and independently validate refresh, restart, dedup, analyst retrieval, and CLI behavior.
3. Preserve that green checkpoint before adding US2.

### Incremental Delivery

1. Add US2 offline EDGAR parsing and official macro normalization; rerun all prior news tests.
2. Add US3 adversarial, scheduling, health, and CLI hardening; rerun all affected tests.
3. Complete focused and full-suite validation, style checks, two-axis review, durable evidence, and final branch commit. Do not create a PR.
