---
description: "Task list for configurable rebalancing cadence"
---

# Tasks: Configurable Rebalancing Cadence

**Input**: Design documents from `/specs/001-configurable-rebalancing/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/cli.md, quickstart.md

**Tests**: Included — the brief explicitly requests default-path tests, and US3 is test-first (red-green).

**Organization**: By user story. US1/US2/US4 are pinning stories (behavior already exists — verified in discovery at `d2f30c2`); their tasks verify and pin rather than build. US3 is the only new behavior. US5 is documentation.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: User story from spec.md (US1–US5)
- Exact file paths in every description

## Path Conventions

Single package: `hedge_fund/` at repo root; tests co-located next to code (constitution III).

---

## Phase 1: Setup

**Purpose**: Establish the baseline so regressions are attributable.

- [X] T001 Record baseline test state: run `python -m poetry run pytest hedge_fund/test_run.py hedge_fund/fund -q`, then `hedge_fund/pipeline -q`, `hedge_fund/tui -q`, `hedge_fund/backtesting -q`, `hedge_fund/paper -q` as separate short chunks; note pass/fail counts per chunk and confirm the only failures are the six documented Windows baseline failures (features intraday `%-d`, 2× paper redo `os.rename`, paper sigterm `os.kill`, tui home file-mode, tui paper_view `%-d`).
  - **Evidence (final; fresh run at HEAD `9bb0ca0`)**: CLI+fund 94 passed (process exit 1 after the summary with 0 failures — pre-existing Windows anomaly, pytest summary is authoritative); pipeline 74 passed; TUI run per-file to avoid the full-dir hang (see T009); backtesting 26 passed; paper 34 passed, 3 documented failures; features 36 passed, 1 documented failure. Every observed failure matches the six documented Windows baseline failures; nothing else fails.

**Checkpoint**: Baseline recorded; any pre-existing failure beyond the six is investigated before feature work.

---

## Phase 2: Foundational (Blocking Prerequisites)

None required. No shared infrastructure changes: FundSpec, the scheduler, and the TUI builder are already complete (discovery-verified); the feature adds no new models, storage, or serialization. User story phases can begin immediately.

---

## Phase 3: User Story 1 — Set the cadence in the fund mandate (Priority: P1) 🎯

**Goal**: The mandate cadence surface is accurate and pinned: example mandate lists all four values; existing validation/scheduler tests stay green.

**Independent Test**: `example.yaml` cadence comment shows `minute | daily | weekly | monthly`; `pytest hedge_fund/fund hedge_fund/pipeline hedge_fund/backtesting -q` green (minus baseline failures).

### Implementation for User Story 1

- [X] T002 [P] [US1] Update the cadence comment on the `rebalance` line in hedge_fund/fund/example.yaml to list all four supported values (`minute | daily | weekly | monthly`) and note that `interval`/`window` apply only to minute funds (FR-013). Preserve the file's existing comment style and UTF-8 no-BOM encoding.
- [X] T003 [US1] Verify mandate-cadence coverage is green with no code changes: run `python -m poetry run pytest hedge_fund/fund hedge_fund/pipeline hedge_fund/backtesting -q`; if anything beyond the six baseline failures fails, stop and investigate before continuing (FR-001/002/004/005 pinned by fund/test_spec.py, pipeline/test_session.py, backtesting/test_fund.py). **Evidence**: 174 passed.

**Checkpoint**: Mandate surface accurate and pinned.

---

## Phase 4: User Story 2 — Existing mandates keep behaving exactly as today (Priority: P1)

**Goal**: The backward-compat default path is pinned at the CLI surface (it is already pinned at the model surface).

**Independent Test**: A mandate without `rebalance` and no flag runs as weekly through the CLI; serializer tests stay green.

### Implementation for User Story 2

- [X] T004 [US2] Add a pinning test to hedge_fund/test_run.py: a mandate with no `rebalance` key, invoked with no `--rebalance` flag, produces a weekly-cadence backtest result (and, if the existing offline paper fixtures allow it cheaply, a `paper create` whose deployed spec is weekly). This test must pass immediately — it pins the default path, it does not change behavior (FR-003, FR-006; spec US2 scenario 1). **Evidence**: 1 passed against initial-revision source snapshot; stdout SHA-256 `8dbc24919e7ae535220364a45f9f9c8b04863f6afa4ad07c1db1872275f38623` with revision stamp fixed to `2.6.1+cd662f4`.
- [X] T005 [US2] Verify serialization invariants hold: run `python -m poetry run pytest hedge_fund/fund/test_spec.py -q` and confirm the default-applied and serializer-exclusion tests pass unchanged (day-grid mandates serialize without `interval`/`window`; default costs omit the `costs` block) — no code changes in this task (FR-006; spec US2 scenarios 2–3). **Evidence**: 71 passed; no spec changes.

**Checkpoint**: Default path proven at both model and CLI surfaces.

---

## Phase 5: User Story 3 — Override the cadence from the command line (Priority: P2)

**Goal**: `--rebalance {minute,daily,weekly,monthly}` on `backtest` and `paper create`, applied after mandate load and before engine work / deploy freeze, with correct minute↔day-grid field handling. No override on deployed-fund subcommands.

**Independent Test**: The T006 test set passes: override changes backtest cadence; `paper create` freeze carries the override; invalid value is a usage error; minute↔day-grid transitions are valid; tick/run expose no such flag.

### Tests for User Story 3 (write FIRST — must FAIL before T007)

- [X] T006 [P] [US3] Add failing tests to hedge_fund/test_run.py (offline fixtures, JSON-stdout assertions, following the file's existing patterns): (a) `backtest --rebalance monthly` on a weekly mandate yields a monthly-cadence result with fewer decision cycles than the unoverridden run; (b) `paper create --rebalance daily` writes a deployed `fund.yaml` whose spec records the daily cadence and the confirmation output states it; (c) `--rebalance hourly` exits with a usage error naming `hourly` and the allowed choices, before any engine work; (d) minute mandate + `--rebalance daily` succeeds as a daily fund with no `interval`/`window` on the resulting spec; (e) daily mandate + `--rebalance minute` yields a valid minute fund with the standard interval/window defaults; (f) `paper tick` and `paper run` parsers have no `--rebalance` option (FR-007–FR-011; contracts/cli.md).
  - **Evidence**: Red: 6 failed, 2 passed, 12 deselected before T007. Green: all six scenarios covered by 8 passed, 12 deselected; source mandate byte-preservation assertions included.

### Implementation for User Story 3

- [X] T007 [US3] Implement the override in hedge_fund/run.py: add `--rebalance` with `choices=("minute", "daily", "weekly", "monthly")` to the `backtest` and `paper create` subparsers in `_parser()`; after `load_spec`, build the overridden spec by dumping the loaded spec, dropping `interval`/`window` when the target cadence is a day-grid value, setting `rebalance`, and re-validating through the model (research.md R2); apply before backtest execution and before `deploy()`; do not touch any other subcommand (FR-007–FR-011, FR-015).
  - **Evidence**: Choices limited to the four supported cadences. Override applied after load and before backtest/deploy; day-grid targets omit minute-only fields and model validation rebuilds the spec.
- [X] T008 [US3] Make the T006 tests pass and confirm compatibility: all T006 assertions green; a flag-absent invocation produces byte-identical stdout JSON to the pre-change baseline (T001); the source mandate file is never modified (contracts/cli.md compatibility section).
  - **Evidence**: T004 + T006 targeted run: 9 passed, 11 deselected. Flag-absent JSON SHA-256 `8dbc24919e7ae535220364a45f9f9c8b04863f6afa4ad07c1db1872275f38623` matched the test run against clean initial-revision source snapshot `cd662f4`; `code_version` held at `2.6.1+cd662f4`. Mandate source-byte checks pass for backtest and paper-create overrides.

**Checkpoint**: CLI override complete; US1–US3 all independently functional.

---

## Phase 6: User Story 4 — Pick the cadence in the fund builder (Priority: P2)

**Goal**: The TUI picker stays pinned — no code change expected.

**Independent Test**: `pytest hedge_fund/tui -q` green (minus the two documented tui baseline failures).

- [X] T009 [US4] Verify the builder's cadence-picker coverage is green with no code changes: run `python -m poetry run pytest hedge_fund/tui -q`; the existing tests already drive the real screen through all four cadences including the minute sub-steps (FR-012 pinned by tui/test_builder.py). Only the tui home file-mode and tui paper_view `%-d` baseline failures are tolerated.
  - **Evidence (final; fresh run at HEAD `9bb0ca0`, TUI split per file because the full-dir run hangs post-summary)**: test_backtest 2 passed; test_builder 13 passed; test_funds+test_home 12 passed, 1 known failure (home file-mode); test_paper 18 passed — including the two previously blocked runner parameter cases, which pass in a per-file chunk — followed by a `KeyboardInterrupt` during interpreter cleanup after all 18 completed and passed; test_paper_view 3 passed, 1 known failure (`%-d`); test_report+test_scorecard_view 14 passed. TUI total: 62 passed, 2 documented Windows failures, 0 deselected, 0 blocked. No TUI code changed.

**Checkpoint**: All four surfaces (mandate, spec, scheduler, TUI) verified consistent.

---

## Phase 7: User Story 5 — Documentation (Priority: P3)

**Goal**: A cold reader can set and override the cadence from the top-level docs alone.

**Independent Test**: Read README.md's mandate section cold; the cadence field, its values/default/meaning, and the CLI override are all documented and match actual behavior.

- [X] T010 [P] [US5] Add a short mandate-field reference to README.md (near the existing TUI/fund blurb): the `rebalance` field with its four values, default `weekly`, meaning (first session of each period / every bar), minute-only `interval`/`window`, and one-line `--rebalance` override examples for `backtest` and `paper create` (FR-014).
  - **Evidence**: README lists four values, `weekly` default, period/bar semantics, minute-only fields, and backtest/paper-create override commands.
- [X] T011 [P] [US5] Mention the `--rebalance` override in hedge_fund/README.md where cadence/minute funds are introduced (near the `paper run fast` example), keeping the existing doc voice (FR-014).
  - **Evidence**: Added a `paper create --rebalance minute` deployment example immediately before the `paper run fast` command; run command remains override-free.

**Checkpoint**: Documentation matches behavior on all surfaces.

---

## Phase 8: Polish & Cross-Cutting Concerns

- [X] T012 Run the full suite in directory chunks (`test_run.py`+`fund`, `pipeline`, `tui`, `backtesting`, `paper`, `features`, remaining dirs) and sum results: only the six documented Windows baseline failures tolerated (SC-006).
  - **Evidence (final; fresh complete run at HEAD `9bb0ca0`, clean worktree, every test file run exactly once)**: CLI+fund 94 passed; pipeline 74 passed; TUI per-file 62 passed, 2 known failures (see T009); backtesting 26 passed; paper 34 passed, 3 known failures; features 36 passed, 1 known failure; data 108 passed, 37 skipped; brokers 28 passed; llm 291 passed; portfolio+risk 59 passed; scorecard+signals 73 passed; root test_paths 2 passed; strategies and validation contain no tests (pytest exit 5). **Sum: 887 passed, 37 skipped, 6 failed — exactly the six documented Windows baseline failures — 0 deselected.** (The earlier partial record summed 888 from overlapping interrupted TUI attempts; this per-file run supersedes it.)
- [X] T013 Style gate on touched files: `black --check --line-length 420`, `isort --check-only` (black profile), `flake8` (constitution VI).
  - **Evidence (final; verified against the true pre-feature baseline `cd662f4`, not `dd4c7c7` which already contains the first test commit)**: black --check --line-length 420 fails on both touched files — and fails identically on their `cd662f4` versions; every black hunk rewrites pre-existing implicit string-concat regions, and no hunk touches feature-added lines (the `--rebalance` argument and cadence tests appear only as unchanged context). isort flags `test_run.py` for the `import importlib` placement inside the `offline` fixture — present verbatim at `cd662f4`; the feature's import edits are correctly sorted (`import hashlib` placed correctly; the fund import line even fixed a pre-existing module-level order violation). flake8 default-79 E501s are noise against the project's 420 standard (no flake8 config file exists); E306 count is 6 before and 6 after — the same findings at shifted line numbers, none new. **Verdict: the feature introduces zero new style violations; the residual failures are pre-existing at baseline. No reformat of pre-existing regions applied (out of feature scope).**
- [X] T014 Verify no UTF-8 BOM in touched YAML/spec files and run the quickstart.md validation scenarios; clean up any temp artifacts.
  - **Evidence**: No BOM in `hedge_fund/fund/example.yaml` or this task file. Quickstart smoke copied the example mandate to a temporary directory, used synthetic offline prices, and confirmed monthly output (2 cycles), unchanged source bytes, and `hourly` usage error before engine work. Temporary directory removed on exit; no live provider or `~/.hedge-fund` access.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (T001)**: first — baseline attribution.
- **US1 (T002–T003)**, **US2 (T004–T005)**, **US4 (T009)**: independent of each other; all depend only on T001.
- **US3 (T006–T008)**: T006 before T007 (red-green); T004 shares the test file, so run after T004 to avoid churn.
- **US5 (T010–T011)**: after US3 (docs document the implemented flag).
- **Polish (T012–T014)**: last.

### Parallel Opportunities

- T002, T006 (different files) can run together after T001.
- T010, T011 (different files) can run together.
- Single-implementer reality (this pipeline): sequential order T001 → T002 → T003 → T004 → T005 → T006 → T007 → T008 → T009 → T010 → T011 → T012 → T013 → T014.

## Implementation Strategy

- **MVP**: US1 + US2 + US3 — the user-visible delta (accurate example, pinned default path, CLI override) is complete and shippable at T008.
- **Pinning discipline**: US1/US2/US4 tasks are verification-first; any failure there means a discovery assumption broke — stop and reassess, do not patch silently.
- **Red-green**: T006 must fail before T007 lands; T008 turns it green.
- Commit after each story checkpoint with conventional messages.