---

description: "Task list for Discovery Snapshot Contract implementation"
---

# Tasks: Discovery Snapshot Contract

**Input**: Design documents from `specs/010-discovery-snapshot-contract/`

**Prerequisites**: [plan.md](plan.md), [spec.md](spec.md), [research.md](research.md), [data-model.md](data-model.md), [contracts/discovery-snapshot-v1.md](contracts/discovery-snapshot-v1.md), [quickstart.md](quickstart.md)

**Tests**: Included because FR-012–FR-015 explicitly require deterministic fixtures and exact outcome validation. Write each story's tests before its implementation and confirm the new tests fail for the intended reason.

**Organization**: Tasks are grouped by user story. The public validator evolves incrementally, so the stories are delivered in priority order even though each has separate fixtures and acceptance scenarios.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Different files and no dependency on another incomplete task
- **[Story]**: US1, US2, or US3 for story-phase tasks
- All paths are repository-relative; implementation remains offline and headless

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Establish the planned package without adding dependencies or behavior

- [ ] T001 Create the `hedge_fund/discovery/` package with initially empty `hedge_fund/discovery/__init__.py`, `hedge_fund/discovery/models.py`, `hedge_fund/discovery/snapshot.py`, `hedge_fund/discovery/fixtures.py`, and `hedge_fund/discovery/test_snapshot.py`; do not add dependencies, providers, persistence, CLI, API, UI, or ranking modules

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Supply shared normalization, baseline data, strict result primitives, exact timestamps, and stable issue mechanics required by every story

**⚠️ CRITICAL**: No user story implementation can begin until this phase is complete

- [ ] T002 [P] Define a named, fully synthetic version-1 valid raw snapshot and its complete expected canonical dictionary in `hedge_fund/discovery/fixtures.py`, including two instruments, offset/lowercase RFC 3339 inputs, mixed integer/float values, and all seven optional output fields
- [ ] T003 [P] Add failing regression coverage in `hedge_fund/fund/test_spec.py` for a directly importable `normalize_ticker`, proving `aapl` → `AAPL`, ` MSFT ` → `MSFT`, `BRK.B` preservation, and unchanged `normalize_universe` order, deduplication, and empty-universe behavior
- [ ] T004 [P] Add failing foundational tests in `hedge_fund/discovery/test_snapshot.py` for immutable `SnapshotValidationResult`/`ValidationIssue` records, RFC 3339 acceptance/rejection, lossless UTC/fraction canonicalization, exact `Fraction` conversion, unambiguous escaped-key location rendering, and numeric issue ordering where index 2 precedes index 10
- [ ] T005 Extract `normalize_ticker` from the existing loop in `hedge_fund/fund/spec.py`, reuse it inside `normalize_universe`, and export it from `hedge_fund/fund/__init__.py` without changing existing universe behavior (depends on T003)
- [ ] T006 [P] Implement the shared strict Pydantic base with `extra="forbid"`, `strict=True`, and `allow_inf_nan=False`, plus frozen `SnapshotValidationResult` and `ValidationIssue` records with the exact public attributes from `data-model.md` in `hedge_fund/discovery/models.py` (depends on T004)
- [ ] T007 [P] Implement internal full-match RFC 3339 parsing, representable-calendar checks, UTC canonicalization preserving fraction digits verbatim, and exact standard-library `Fraction` conversion in `hedge_fund/discovery/snapshot.py`, rejecting leap seconds, year 0000, and out-of-range UTC conversions without reading a clock (depends on T004)
- [ ] T008 Implement internal Pydantic/raw-error adaptation in `hedge_fund/discovery/snapshot.py`: structured locations with dotted safe keys and bracketed JSON-escaped unsafe keys, the eleven stable reasons including all schema-version classifications, deterministic readable messages, related duplicate locations, deduplication, and structured sorting with numeric array indices before rendering; never expose Pydantic messages, URLs, or raw locations as public compatibility guarantees (depends on T004, T006)

**Checkpoint**: Foundational tests pass; shared normalization and timestamp behavior are deterministic and ready for the public validator

---

## Phase 3: User Story 1 - Reject unreliable candidate data (Priority: P1) 🎯 MVP

**Goal**: Accept complete valid snapshots with canonical content and reject malformed or ambiguous snapshots without returning partial output

**Independent Test**: Run `poetry run pytest hedge_fund/discovery/test_snapshot.py hedge_fund/fund/test_spec.py -q`; valid fixtures must match complete canonical output and every malformed fixture must match all declared issue locations/reasons without any external service

### Tests for User Story 1

- [ ] T009 [US1] Extend `hedge_fund/discovery/fixtures.py` with named valid and malformed inputs plus exact expected snapshots/issues for absent and null optionals, blank industry, lowercase/padded tickers, empty and all-suspended universes, missing/null required fields, unknown fields at all levels, the colliding top-level key `source.extra` and key `extra` inside `source`, keys requiring JSON escaping, duplicate canonical codes, invalid optional pairs, wrong types, non-finite values, numeric bounds, preserved finite extremes, format-valid `ZZZ` and invalid lowercase/non-ASCII currencies, and missing/boolean/float/string/unsupported schema versions
- [ ] T010 [US1] Add failing contract tests in `hedge_fund/discovery/test_snapshot.py` that deep-copy each US1 fixture, call the public `validate_snapshot`, compare complete field content and ordered issues, distinguish `$["source.extra"]` from `source.extra`, verify both duplicate locations/related locations, assert exact missing/malformed/unsupported version reasons, reject any supplied freshness argument with `invalid_value` at each supplied argument until US2, assert `snapshot=None` on every failure, and replay results for determinism (depends on T009)

### Implementation for User Story 1

- [ ] T011 [US1] Implement strict snapshot, source, and instrument models in `hedge_fund/discovery/models.py` with exactly the declared fields, required/null distinction, optional null defaults, strict strings/lists/integers, `StrictInt` plus an explicit `== 1` schema-version validator rather than `Literal[1]`, custom built-in int/float guards that reject booleans and preserve numeric type/value, field bounds, nonblank text checks, and format-only uppercase three-letter ASCII currency validation without ISO 4217 membership (depends on T006, T010)
- [ ] T012 [US1] Implement `validate_snapshot(raw, *, reference_time=None, max_age_seconds=None)` internally in `hedge_fund/discovery/snapshot.py`: prewalk exact JSON-compatible types, aggregate model issues including the version gate, independently check canonical duplicates, optional-pair consistency and timestamp order, canonicalize only declared fields, emit explicit optional nulls, preserve instrument order, and return all-or-nothing results (depends on T005, T007, T008, T011)
- [ ] T013 [US1] Export `validate_snapshot`, `SnapshotValidationResult`, and `ValidationIssue` from `hedge_fund/discovery/__init__.py`, keeping internal helpers and Pydantic models private; at the US1 checkpoint, reject every non-None freshness argument with `invalid_value` at each supplied argument in `hedge_fund/discovery/snapshot.py`, without evaluating age/future behavior or silently accepting an enabled policy (depends on T012)

**Checkpoint**: User Story 1 is fully functional; malformed candidate data cannot yield a partial canonical snapshot

---

## Phase 4: User Story 2 - Replay historical snapshots safely (Priority: P2)

**Goal**: Preserve provenance and support deterministic historical validation, timestamp ordering, and explicit-reference freshness

**Independent Test**: Run `poetry run pytest hedge_fund/discovery/test_snapshot.py -q`; historical data must pass without policy, exact age equality must pass, over-age/future cases must return their declared issues, and repeated identical calls must match without clock/network access

### Tests for User Story 2

- [ ] T014 [US2] Add named historical, exact-boundary, fractionally-over-boundary, future, equal observation/retrieval, earlier-retrieval, and incomplete/invalid-policy fixtures with explicit reference inputs and expected issue locations/reasons to `hedge_fund/discovery/fixtures.py`
- [ ] T015 [US2] Add failing replay and freshness tests in `hedge_fund/discovery/test_snapshot.py`, including no-policy historical acceptance, arbitrary-precision boundary arithmetic, future-not-stale behavior, invalid-policy suppression of freshness claims, timestamp grammar cases, and repeated canonical/issue equality (depends on T014)

### Implementation for User Story 2

- [ ] T016 [US2] Replace the interim US1 freshness rejection with complete explicit freshness handling in `hedge_fund/discovery/snapshot.py`: require both keyword arguments, classify policy argument failures as `missing_field`/`invalid_type`/`invalid_value`, use exact `Fraction` arithmetic for timestamp order/future/stale checks, accept exact age equality, and never call the wall clock or emit dependent freshness issues from invalid prerequisites (depends on T013, T015)

**Checkpoint**: User Story 2 is independently replayable; all freshness decisions are explicit, exact, and deterministic

---

## Phase 5: User Story 3 - Evolve the contract without silent breakage (Priority: P3)

**Goal**: Retain an executable version-1 compatibility baseline for future changes, building on the strict version gate already delivered in US1

**Independent Test**: Run `poetry run pytest hedge_fund/discovery/test_snapshot.py -q`; the version-1 baseline must pass, the US1 missing/malformed/unsupported version checks must remain green, and a simulated rename must produce missing/unknown-field issues rather than silent acceptance or migration

### Compatibility tests for User Story 3

- [ ] T017 [US3] Preserve the named version-1 valid fixture as the compatibility baseline and add simulated field-rename, removal, unit-change, and meaning-change cases in `hedge_fund/discovery/fixtures.py`, with exact missing/unknown-field or semantic-review expectations and no version-2 implementation
- [ ] T018 [US3] Add failing compatibility tests in `hedge_fund/discovery/test_snapshot.py` that validate the preserved baseline, retain the US1 `missing_field`/`invalid_type`/`unsupported_schema_version` coverage, reject silent migration, and prove a field rename/removal/unit-or-meaning change requires review under the documented policy (depends on T017)

**Checkpoint**: All three stories pass independently; the version-1 baseline remains intact for later provider and ranking features

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Verify style, every documented scenario, and repository-wide regressions

- [ ] T019 Run `poetry run pytest hedge_fund/discovery/test_snapshot.py hedge_fund/fund/test_spec.py -q` and confirm every fixture's complete canonical output or exact ordered issues
- [ ] T020 [P] Run `poetry run black --check hedge_fund/discovery hedge_fund/fund/spec.py hedge_fund/fund/__init__.py hedge_fund/fund/test_spec.py` with the repository's deliberate 420-character configuration
- [ ] T021 [P] Run `poetry run isort --check-only hedge_fund/discovery hedge_fund/fund/spec.py hedge_fund/fund/__init__.py hedge_fund/fund/test_spec.py` with the existing black profile
- [ ] T022 [P] Run `poetry run flake8 hedge_fund/discovery hedge_fund/fund/spec.py hedge_fund/fund/__init__.py hedge_fund/fund/test_spec.py` and resolve only feature-related findings
- [ ] T023 Execute every V1–V8 scenario in `specs/010-discovery-snapshot-contract/quickstart.md` against `hedge_fund/discovery/test_snapshot.py`, confirming offline isolation, no credentials, no wall-clock reads, no partial snapshots, and no ranking behavior
- [ ] T024 Run the constitution-required full suite with `poetry run pytest hedge_fund -q` across `hedge_fund/`; acceptance requires a complete passing run or individually evidenced unchanged baseline failures, never an interrupted or narrowed final suite

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: Starts immediately; adds no behavior
- **Foundational (Phase 2)**: Depends on T001 and blocks every story
- **US1 (Phase 3)**: Depends on Foundational; establishes the public validator, strict version-1 gate, fail-closed interim freshness behavior, and canonical all-or-nothing result
- **US2 (Phase 4)**: Depends on US1's public entry point; replaces the interim freshness rejection with explicit policy behavior without changing canonical snapshot fields
- **US3 (Phase 5)**: Depends on US1/US2 validator flow; adds executable compatibility-evolution checks while preserving all prior fixtures
- **Polish (Phase 6)**: Depends on all three stories

### User Story Dependencies

- **US1 (P1)**: No dependency on another story; this is the MVP
- **US2 (P2)**: Uses US1's public validator but has independent historical/freshness fixtures and assertions
- **US3 (P3)**: Uses the assembled validator but has independent version/compatibility fixtures and assertions

### Within Each User Story

- Fixture expectations and tests precede implementation; confirm new tests fail before writing behavior
- Shared models and timestamp/issue primitives precede the public pipeline
- Complete each story checkpoint before advancing to the next priority
- Do not add provider, persistence, ranking, API, UI, migration, or trading work

### Parallel Opportunities

- **T002, T003, T004** can be authored concurrently in separate files after T001
- **T006 and T007** can proceed concurrently after T004; T008 follows T006
- **T020, T021, T022** are read-only style checks and can run concurrently after implementation
- Story implementation is intentionally sequential because each story extends the same public validator and `snapshot.py`

---

## Parallel Examples by User Story

### User Story 1

No implementation tasks are marked parallel: `fixtures.py` expectations feed `test_snapshot.py`, strict models feed `snapshot.py`, and the public export follows the assembled validator. The safe parallel work is foundational T002/T003/T004 before this story begins.

### User Story 2

No implementation tasks are marked parallel: T014 defines the exact inputs consumed by T015, and T016 implements the resulting contract in the same `snapshot.py` used by US1. Keep this story sequential to avoid freshness/fixture drift.

### User Story 3

No tasks are marked parallel: T017 defines the compatibility baseline consumed by T018, while strict version rejection is already covered by US1. Do not create a version-2 fixture or migration path.

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Setup and Foundational phases
2. Deliver US1's strict validation, schema-version gate, canonical output, issue aggregation, duplicate rejection, and explicit rejection of any supplied freshness arguments
3. Stop at the US1 checkpoint and run its independent test command, including the interim freshness regression
4. Review the usable offline contract before replacing the interim freshness rejection with full policy behavior or adding compatibility-evolution checks

### Incremental Delivery

1. Setup + Foundational → shared primitives and baseline ready
2. US1 → trustworthy all-or-nothing snapshot validation (MVP)
3. US2 → deterministic historical replay and explicit freshness
4. US3 → executable version-1 compatibility boundary
5. Polish → focused style checks, quickstart scenarios, and full-suite evidence

---

## Notes

- All fixture content is synthetic and in-memory; tests must not access providers, credentials, network, files, persistence, models, or wall clocks
- Canonical snapshots compare JSON-compatible field content, not serialized bytes, key order, or insignificant whitespace
- Numeric values retain their built-in type and value; unavailable optionals become explicit nulls, never zero
- Duplicate snapshot rows are errors even though existing universe-list normalization deduplicates
- Feature 011 will consume this contract; ranking and eligibility are not implementation tasks here
