---
description: "Task list for per-fund approval gate (yay/nay mode)"
---

# Tasks: Per-Fund Approval Gate

**Input**: Design documents from `/specs/002-approval-gate/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/cli.md, quickstart.md

**Tests**: Included — US2/US3/US5 are test-first (red-green); US1 serialization parity is a mandatory pinning test.

**Organization**: By user story. Foundational phase carries the FundSpec field + mailbox (shared by all stories).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: User story from spec.md (US1–US6)
- Exact file paths in every description

## Path Conventions

Single package: `hedge_fund/` at repo root; tests co-located next to code (constitution III).

---

## Phase 1: Setup

**Purpose**: Establish the baseline so regressions are attributable.

- [x] T001 Record baseline test state at the pre-feature HEAD: run `python -m poetry run pytest hedge_fund/test_run.py hedge_fund/fund -q`, then `hedge_fund/pipeline -q`, `hedge_fund/paper -q`, `hedge_fund/backtesting -q`, and `hedge_fund/tui` **per-file** as separate short chunks; note pass/fail counts per chunk and confirm the only failures are the six documented Windows baseline failures (features intraday `%-d`, 2× paper redo `os.rename`, paper sigterm `os.kill`, tui home file-mode, tui paper_view `%-d`). Trust the pytest summary line, not the process exit code (pre-existing Windows anomaly).
  - **Evidence**: At `5b93aa3` on Windows/Python 3.13.7, using cached Poetry env `aihf-emaEr9cn-py3.13` after the branch-specific Poetry env was created empty: `test_run.py + fund` 94 passed (pytest summary; process exit 1), pipeline 74 passed, paper 34 passed/3 baseline failed, backtesting 26 passed, features 36 passed/1 baseline failed. TUI per-file: scorecard_view 3 passed; report 11; paper_view 3 passed/1 baseline failed; paper 18 passed (KeyboardInterrupt during post-summary cleanup); home 8 passed/1 baseline failed; funds 4; builder 13; backtest 2. Total: 320 passed, 6 baseline failures, 0 skipped. The six failures are exactly the documented two paper redo `os.rename`, paper runner `os.kill`, features intraday `%-d`, TUI home file mode, and TUI paper_view `%-d`; no other test failures.

**Checkpoint**: Baseline recorded; any pre-existing failure beyond the six is investigated before feature work.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The FundSpec field and the verdict mailbox — every story builds on these.

- [x] T002 [US1] Add `approval_required: bool` (default `False`) to `FundSpec` in hedge_fund/fund/spec.py, and extend the wrap model_serializer `_serialize` to pop it when `False` (same pattern as `costs` at default) so approval-OFF serialization is byte-identical to the pre-feature output (FR-001/002/004). Do not reformat pre-existing regions.
  - **Evidence**: `python -m poetry run pytest hedge_fund/fund/test_spec.py -q` — 77 passed after field/serializer implementation; strict `bool` rejects integer/string coercions and the default JSON matches the exact pre-feature literal.
- [x] T003 [US1] Add the byte-parity and validation tests to hedge_fund/fund/test_spec.py (pattern: `test_costs_default_..._serialize_only_when_changed` at :114): (a) default-False fund's `model_dump_json()` is byte-identical to the pre-feature serialization (assert the exact expected JSON string); (b) `approval_required=True` serializes the field; (c) a mandate YAML without the key loads unchanged; (d) a non-boolean value (`approval_required: yes-please`) is rejected with a clear error; (e) an unknown near-miss key is still rejected by `extra="forbid"`. Tests (a)/(c)/(d)/(e) must pass against the pre-field model where meaningful — write them first, confirm red for (b)-dependent behavior only after T002 lands (FR-003/004).
  - **Evidence**: Pre-field run `pytest hedge_fund/fund/test_spec.py -q -k approval` — 4 passed, 1 expected failure (`approval_required` was forbidden), 71 deselected. Post-field `pytest hedge_fund/fund/test_spec.py -q` — 77 passed, including exact JSON parity, true serialization, absent YAML setting, strict non-bool rejection, and near-miss rejection.
- [x] T004 [US2] Add the verdict mailbox to hedge_fund/paper/ledger.py beside the kill-switch code: `APPROVAL_FILE = "pending-approval.json"`; `approval()` reader returning `None` on missing/corrupt/unparseable file (fail-safe — never a yay; FR-015); `set_approval(verdict, decision_as_of, by)` writing `{"verdict", "decision_as_of", "decided_at", "by"}` via `paths.write_atomic` + `log_event("approve"/"reject", decision_as_of=..., by=...)` (FR-005/012); `clear_approval()` removing the file if present. Add tests to hedge_fund/paper/test_ledger.py: write/read round-trip, missing ⇒ None, corrupt JSON ⇒ None, wrong verdict value ⇒ None, clear removes, events appended with the right kinds (FR-012).
  - **Evidence**: `python -m poetry run pytest hedge_fund/paper/test_ledger.py -q` — 18 passed. Covers approve/reject round trips + events, missing/corrupt/wrong-verdict/unreadable mailbox, clear, newer-verdict preservation, and writer input validation.
- [x] T005 [US2] Implement the gate in `_run()` in hedge_fund/paper/tick.py (the single choke point shared by tick/redo/runner): when the deployed spec has `approval_required` and `state.pending` is not None — resolve the verdict via `Ledger.approval()`: `approve` with matching `decision_as_of` ⇒ proceed to normal execution and clear the verdict after `ledger.append` succeeds; `reject` with matching key ⇒ `log_event("reject", ...)` consumption note, clear, pass `state.model_copy(update={"pending": None})` to `advance` (book marked, no orders); no verdict or stale key ⇒ `log_event("expire", decision_as_of=..., reason=...)`, clear a stale file, same skip path. Gate OFF ⇒ code path identical to today (no mailbox read). The gate never reads/writes `control.json` (FR-006/007/008/014/015).
  - **Evidence**: `pytest hedge_fund/paper/test_tick.py -q -k "gate or verdict_written"` — 7 passed. Gate-off path asserts no mailbox read; halted path asserts no mailbox read and unchanged `control.json`.

**Checkpoint**: `pytest hedge_fund/fund hedge_fund/paper -q` green (minus baseline failures); gate-OFF behavior untouched.

---

## Phase 3: User Story 2 — A pending decision waits (Priority: P1) 🎯

**Goal**: The gate holds unapproved decisions; the fund keeps running.

**Independent Test**: quickstart Scenario 2 — gated fund skips execution, records the session, continues its cadence.

- [x] T006 [US2] Write the gate behavior tests FIRST in hedge_fund/paper/test_tick.py (fixtures only; `deploy(..., root=tmp_path)` pattern): (a) gate ON + no verdict ⇒ next session executes nothing, book unchanged, session recorded, `expire` event, fund not halted, and the following session makes a fresh decision (FR-007/008, US2.1–2.2); (b) gate ON + approve verdict keyed to the pending decision ⇒ next session executes it, verdict file cleared after append (FR-010 first half); (c) gate ON + reject verdict ⇒ next session skips, book unchanged, verdict consumed (FR-011); (d) stale verdict (key ≠ pending `as_of`) ⇒ ignored, expire path, stale file cleared (FR-006); (e) gate OFF regression ⇒ pending auto-executes exactly as today, no mailbox read (FR-002, US2.3); (f) gated + halted ⇒ existing `FundHalted` behavior unchanged (FR-014, US5.4). Confirm (a)–(d) fail before T005's gate exists if run in that order; all pass after.
  - **Evidence**: Before T005, `pytest hedge_fund/paper/test_tick.py -q -k gate` — 4 expected failures in no-verdict/approve/reject/stale paths; gate-off and halted tests passed (2 passed, 18 deselected). After T005 plus the mid-session write case, `pytest hedge_fund/paper/test_tick.py -q -k "gate or verdict_written"` — 7 passed, 18 deselected.
- [x] T007 [US2] Run `python -m poetry run pytest hedge_fund/paper hedge_fund/fund hedge_fund/pipeline -q` and confirm green minus baseline failures.
  - **Evidence**: `python -m poetry run pytest hedge_fund/paper hedge_fund/fund hedge_fund/pipeline -q` — 203 passed, 3 failed. Failures are the baseline paper redo `os.rename` ×2 and runner `os.kill`; no new failures.

**Checkpoint**: Core gate behavior proven at the paper layer.

---

## Phase 4: User Story 3 — CLI approve/reject (Priority: P1)

**Goal**: `aihf paper approve|reject <name>` per contracts/cli.md.

**Independent Test**: quickstart Scenarios 3–5.

- [x] T008 [US3] Write CLI tests FIRST in hedge_fund/test_run.py via the `offline` fixture (do not reformat pre-existing regions): (a) approve on gated fund with pending decision writes the verdict + `approve` event and prints confirmation; (b) `--now` with a due session executes immediately; (c) `--now` with nothing due reports next-close execution, exit 0; (d) reject writes `verdict=reject` + event; (e) approve/reject on gate-OFF fund fails naming the fund; (f) approve/reject with nothing pending fails with "nothing awaiting approval"; (g) `paper create --approval` deploys a fund whose spec has `approval_required=True` and the confirmation states it (FR-009/010, US1.3).
  - **Evidence**: Before T009, 8 focused CLI approval tests failed because `--approval` and approve/reject commands were not registered. After implementation, `pytest hedge_fund/test_run.py -q -k "paper_create_approval or paper_approve_now or paper_reject_records or paper_approval_commands"` — 10 passed, 20 deselected. Tests use the `offline` fixture and temp fund dirs.
- [x] T009 [US3] Implement in hedge_fund/run.py: `approve`/`reject` subparsers beside `halt`/`resume` (name + `--now` on approve); dispatch in the `_paper` tail following the halt/resume pattern — validate gate ON (replay the ledger, check deployed spec) and pending exists, then `ledger.set_approval(...)`; catch `NothingDue` on `--now` and report next-close; `--approval` store-true on `paper create` applied with the other create-time spec overrides; `status` prints an `awaiting approval` line when gated+pending; `_status_line` carries an awaiting-approval marker (FR-009/010/013).
  - **Evidence**: `python -m poetry run pytest hedge_fund/test_run.py -q` — 30 passed in 1.57s; pytest summary is clean, process exit code 1 matches the recorded Windows pytest anomaly.
- [x] T010 [US3] Run `python -m poetry run pytest hedge_fund/test_run.py hedge_fund/paper -q`; confirm green minus baseline failures. **Evidence**: Combined command reached 48 passed, then Windows `KeyboardInterrupt` in the paper runner signal-test chunk before a summary. Independent chunks: `test_run.py -q` — 30 passed; `paper -q` — 49 passed, 3 failed. The three failures are exactly the baseline two redo `os.rename` errors and runner stale-PID `os.kill` error; no new failures. Combined run not cleanly completed because of the known Windows signal behavior; constituent chunks completed.

**Checkpoint**: CLI yay/nay operable and refused correctly.

---

## Phase 4: User Story 4 — TUI surface (Priority: P2)

**Goal**: Fund screen shows awaiting-approval state with working y/n; builder step sets the flag.

**Independent Test**: quickstart Scenario 6 (TUI tests run per-file on Windows).

- [x] T011 [P] [US1] [US4] Add the approval step to the TUI fund builder in hedge_fund/tui/builder.py (paper mode, after cadence — `STEP_IDS`/`STEP_TITLES` pattern) with a plain-language description, and wire the choice through `_finish_build` into the `FundSpec` (FR-001). Add a test to hedge_fund/tui/test_builder.py that the step produces `approval_required=True` in the deployed spec when toggled and `False`/absent when not (pattern: existing builder tests).
  - **Evidence**: New test red run: 2 expected failures because the approval pane was absent. Green `python -m poetry run pytest hedge_fund/tui/test_builder.py -q` — 15 passed in 18.60s, including off/on serialization, daily/minute navigation, and backtest regression.
- [x] T012 [US4] Add the TUI fund-screen surface: in hedge_fund/tui/paper_view.py add `gate`/`approval` snapshot properties, rewrite the next-run row for gated+pending to "awaiting approval — y approve · n reject" (expiry wording: decision lapsed), and make `run_plan` say the run will mark the book and skip execution; in hedge_fund/tui/paper.py add `y`/`n` bindings, gate `check_action` on `gate ∧ pending ∧ ¬halted`, and implement `action_approve`/`action_reject` calling `snap.ledger.set_approval(...)` with notify + `_populate()` (FR-013). Add tests to hedge_fund/tui/test_paper.py: y/n enabled/disabled per state, verdict file + event written on each action, detail copy shows awaiting approval (run this file alone).
  - **Evidence**: Focused UI tests: `test_paper_view.py -k "approval_snapshot_rows or next_run_names"` — 2 passed; `test_paper.py -k "approval_verdicts or disables_approval_actions"` — 4 passed; `test_paper.py -k run_session_board_reports_a_gated_skip` — 1 passed. Coverage includes matching/stale verdict copy, lapsed decision copy, run-plan/board skip text, y/n mailbox/audit writes, and disabled gate/pending/halt states.
- [x] T013 [US4] Run `python -m poetry run pytest hedge_fund/tui/test_paper.py hedge_fund/tui/test_builder.py -q` (per-file if the pair hangs); confirm green minus baseline failures. **Evidence**: `test_builder.py -q` — 15 passed; `test_paper_view.py -q` — 5 passed, 1 baseline `%-d` failure. Full `test_paper.py -q` — 23 passed before Windows `KeyboardInterrupt`; excluding the two runner cases — 24 passed, 2 deselected. Session-screen case passes in the 24-test selection. **Runner cases blocked (environmental, not a code defect)**: `test_paper_screen_space_starts_and_stops_a_runner_at_any_cadence[daily]` and `[minute]` were each run twice in isolation (single test ID, once with `-p no:cacheprovider`) — all four attempts externally killed with exit 1 and zero-byte output before pytest wrote a summary. The daily case reproduces on pre-feature commit `d25de7b` (KeyboardInterrupt after 4.18s, 20 deselected, no assertion summary), so the kill predates the feature. Same blocked pattern as the rebalancing feature's commit `1ad5b0d`. Everything else in the task is green, so the box is checked with the blocked evidence recorded.

**Checkpoint**: TUI mirror of the CLI contract complete.

---

## Phase 5: User Story 1/6 — Example mandate + documentation (Priority: P3)

**Goal**: Discoverability and the shipped example stay truthful.

- [x] T014 [P] [US1] Add a commented `approval_required` documentation line to hedge_fund/fund/example.yaml (parsed content unchanged — the shipped example's behavior must not change; UTF-8 no BOM; preserve comment style) (FR-001).
  - **Evidence**: `example.yaml` decodes as UTF-8 without BOM; `yaml.safe_load` output equals `HEAD:hedge_fund/fund/example.yaml`.
- [x] T015 [P] [US6] Document approval mode in README.md (and hedge_fund/README.md if it carries the fund-settings reference): default off, the three creation surfaces, `approve`/`reject` commands with `--now`, expiry-skip-not-halt semantics, and kill-switch orthogonality (FR-016).
  - **Evidence**: README.md and hedge_fund/README.md document default-off, mandate/TUI/CLI creation, approve/reject/`--now`, expiry skip without halt, and kill-switch independence; the package README also documents the mailbox and audit events.
- [x] T016 [US6] Verify docs match behavior: every documented key/command/flag exists and behaves as documented (spot-check against the implemented CLI help output); no documented value the engine rejects. **Evidence**: `aihf paper create --help` exposes `--approval`; `aihf paper approve --help` exposes `--now`; `aihf paper reject --help` accepts the name and exposes no unsupported flag. Approval CLI tests: 10 passed, 20 deselected; YAML example parses unchanged.

**Checkpoint**: Surfaces consistent (constitution V).

---

## Phase 6: Final Validation & Polish

- [x] T017 Run the full suite in chunks and record final counts: `python -m poetry run pytest hedge_fund/test_run.py hedge_fund/fund -q`, `hedge_fund/pipeline -q`, `hedge_fund/paper -q`, `hedge_fund/backtesting -q`, `hedge_fund/features -q`, `hedge_fund/tui` per-file; only the six documented baseline failures tolerated (SC-006). **Evidence**: `test_run.py hedge_fund/fund` — 110 passed in 2.63s (pytest summary had no failures; process exit 1 matches the recorded Windows anomaly); pipeline — 74 passed; paper — 51 passed, 3 documented baseline failures; backtesting — 26 passed; features — 36 passed, 1 documented baseline failure. TUI per-file: scorecard view 3 passed; report 11 passed; paper view 5 passed, 1 documented baseline failure; paper file 23 passed before `KeyboardInterrupt`, and 24 passed with the two runner cases deselected; home 8 passed, 1 documented baseline failure; funds 4 passed; builder 15 passed; backtest 2 passed. Daily and minute runner cases each interrupt independently in this branch; daily also interrupted at pre-feature `d25de7b` (4.18s, 20 deselected, no assertion summary), while minute was not compared at baseline. **Consolidated unique totals**: 369 passed, 6 documented baseline assertion failures, 0 skipped; 2 TUI runner cases blocked (environmental Windows external kill, evidence under T013). **Post-reformat re-verification** (after commit `d23c93f`, all 12 reformatted files' test files re-run in chunks): fund 80 passed; run+fund 110 passed; paper 51 passed + the same 3 baseline failures; paper view 5 passed + 1 baseline; builder 15 passed; paper 24 passed (runner cases deselected). No new failures introduced by reformatting.
- [x] T018 Style gate: `black --check` (line-length 420), `isort --check-only` (black profile), `flake8` on all touched files; no reformatting of pre-existing flaky regions in run.py/test_run.py; no BOM in any YAML/spec file (constitution VI). **Evidence**: Initial state — black would reformat 14 touched files, isort 7, flake8 `--max-line-length=420` 16 non-E501 findings all attributed by `git blame` to earlier commits. **Fix applied** (commit `d23c93f`): black `--line-length 420` + isort `--profile black` applied to the 12 touched files (spec.py, test_spec.py, ledger.py, test_ledger.py, tick.py, test_tick.py, builder.py, paper.py, paper_view.py, test_builder.py, test_paper.py, test_paper_view.py); run.py/test_run.py deliberately excluded — their black/isort hunks verified to be the documented pre-existing flaky regions (string-concat joins, importlib placement in offline fixture), untouched by the feature diff. Post-fix verification: black — 12 files left unchanged; isort — exit 0; flake8 `--max-line-length=420` on all 14 touched files — only 6 E306 findings, all in test_run.py at lines 30/32/50/366/373/398, verified outside the feature diff hunks (feature hunks: line 6 import, lines 413+ tests). Affected test chunks re-run green after reformatting (see T017 post-reformat evidence). BOM scan — 22 specification/YAML files checked, none.
- [x] T019 Ledger-integrity spot check: a ledger written by the pre-feature code (fixture committed in the test) verifies under `replay(full=True)` after the change; approval-OFF deployed `fund.yaml` byte-identical to pre-feature output (FR-004, SC-002). **Evidence**: focused `test_ledger.py` + `test_tick.py` — 2 passed, 43 deselected in 0.49s. Committed legacy-record fixture replays with its pending decision and full hash verification; default-off deployment bytes match the fixed legacy YAML fixture with platform-native newlines.

**Checkpoint**: Feature done when all boxes tick with evidence and the suite is green minus baseline.

---

## Phase 7: QA Rework (Iteration 4)

- [x] T020 [US2] Bind approval verdicts to both `decision_as_of` and source-record `decision_hash`; invalidate a source-session verdict on redo; replay consumed approvals when redoing the execution session; preserve verdict on failed gated advance; make mailbox clearing unlink-safe and atomic temp names unique; document fail-safe mailbox versus fail-loud kill-switch behavior; test explicit YAML `approval_required: false` parity. Update `plan.md`, `spec.md`, `research.md`, `data-model.md`, `quickstart.md`, and `contracts/cli.md` with the identity/replay semantics and deferred findings.
  - **Evidence — PASS for requested changes; automated unit/fake tests only**: Windows 11 `10.0.26200`, Python 3.13.7 x64, Poetry env `aihf-emaEr9cn-py3.13`; imported `hedge_fund` from this worktree. Test source revision `d23c93f2c56017fa19a688860ccb89310b5365c0`; code/test dirty-diff SHA-256 `3c772810d49c1a61769e72b738b0c3643cb53cfc23db83b4cc73df0149607eb6`, captured 2026-10-29 23:57:19 +01:00 after final tests. Documentation-only spec/plan/research/data-model/quickstart/CLI/tasks/memory updates followed; no code or test changes. No separate wheel/build artifact. Exact final chunks:
    | Command target | Pytest summary | Process exit |
    |---|---:|---:|
    | `hedge_fund/test_run.py hedge_fund/fund` | 111 passed in 2.08s | 1; known Windows pytest exit anomaly, no test failures |
    | `hedge_fund/pipeline` | 74 passed in 0.80s | 0 |
    | `hedge_fund/paper` | 57 passed, 3 failed in 3.28s | 1 |
    | `hedge_fund/backtesting` | 26 passed in 0.74s | 0 |
    | `hedge_fund/features` | 36 passed, 1 failed in 0.86s | 1 |
    | `tui/test_scorecard_view.py` | 3 passed in 0.75s | 0 |
    | `tui/test_report.py` | 11 passed in 0.95s | 0 |
    | `tui/test_paper_view.py` | 5 passed, 1 failed in 1.38s | 1 |
    | `tui/test_paper.py -k "not test_paper_screen_space_starts_and_stops_a_runner_at_any_cadence"` | 24 passed, 2 deselected in 12.05s | 0 |
    | `tui/test_home.py` | 8 passed, 1 failed in 4.11s | 1 |
    | `tui/test_funds.py` | 4 passed in 1.69s | 0 |
    | `tui/test_builder.py` | 15 passed in 18.05s | 0 |
    | `tui/test_backtest.py` | 2 passed in 1.53s | 0 |
    | `hedge_fund/test_paths.py` | 3 passed in 0.03s | 0 |
    The six failures are the documented baselines only: paper redo `os.rename` ×2, paper runner stale-PID `os.kill`, features intraday `%-d`, TUI paper-view `%-d`, TUI home file mode. Total: 379 passed, 6 baseline failures, 2 TUI runner cases deselected, 0 skipped. The two runner cases were not run per this QA cycle's constraint.
  - **Focused regression evidence**: C1/I1 regressions were red against old behavior; M1 unlink and M2 temp-name tests were red before their fixes. Corrected I2 gated failed-advance test passed against the old retry behavior. Focused runs: identity/stale/late-vote/replay/retry — 5 passed, 24 deselected; source-redo with unlink failure — 1 passed, 29 deselected; I1 tick-history identity assertion — 1 passed, 29 deselected; ledger approval/unlink tests — 9 passed, 12 deselected; explicit-false YAML tests — 7 passed, 71 deselected. Full final chunks above include these regressions.
  - **Style and static checks**: isort (`--profile black`) — pass on 12 changed Python files; flake8 (`--max-line-length=420`) — pass on 12; Black (`--line-length 420`) — 11 files unchanged, `run.py` alone reports pre-existing string-concatenation/spacing regions. Black excluding `run.py` passes. `black --diff` shows no diff in the approval CLI hunks; no pre-existing region reformatted. BOM scan — 17 YAML/spec files, none; `git diff --check` — pass.

### Deferred QA findings

| Finding | Disposition |
|---|---|
| M3: separate consume event kind | Deferred; consumed approval identity/verdict stored on existing `tick` event. |
| M4: `--now` concurrency guard against runner | Deferred; same pre-existing `paper tick` concurrency risk; runner-wide lock is separate scope. |
| M5: skip LLM refresh on gated skip | Deferred; spend optimization, not a gate correctness requirement. |
| `NothingDue` wording | Deferred; message polish, next-close behavior remains tested. |
| Expire session field | Deferred; identity and reason audit the expiry; session field is enrichment. |
| Docstrings | Deferred; documentation polish, no repaired-path contract ambiguity. |
| Rejected-weekly lapsed text | Deferred; UI copy polish, execution/rejection behavior unchanged. |
| Second-guard test coverage | Deferred; direct-call coverage for the TUI action guard is outside the identity/replay changes; enabled-action tests remain. |
| FR-014 wording | Deferred; kill-switch behavior and tests remain untouched. |

**Coordinator independent verification (2026-10-29, post-commit `e3d0a78`, clean tree, Poetry env `aihf-0Qkf8biM-py3.13`)**: re-ran affected chunks — paper+fund 138 passed + 3 documented baseline failures; tui paper_view 5 passed + 1 baseline; tui builder 15 passed; tui paper 24 passed, 2 runner cases deselected (blocked, see T013); test_paths+test_run 33 passed. Style on the 11 non-run.py hardening files: black clean, isort clean, flake8 `--max-line-length=420` zero findings; run.py black-diff hunks verified to be the pre-existing string-concat flaky regions (the `return (...)` join predates the feature at `d25de7b`; the feature only appended `{approval_state}` inside it).

**Final QA (iteration 5) verdict: pass-with-caveats** — C1, I1, I2, M1, M2, M6, M7 all fixed and verified against `e3d0a78`; no new Critical/Important findings. Three new Minors recorded as deferred follow-ups: (a) `paths.py:47-49` temp file left behind if `os.replace` fails (unique names now accumulate instead of reuse); (b) `ledger.py:325-331` consumed-verdict replay scans all of `events.jsonl` on every gated tick/TUI snapshot/status line — cost grows with log size; (c) `events.jsonl` now feeds gate decisions but is not hash-chained and appends are not atomic — a damaged line fails safe (gate skips) and should be documented or tolerated per-line. Nitpick test gaps: consumed-reject replay, expire-last-event redo, damaged-line + matching verdict file.