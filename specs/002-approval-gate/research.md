# Research: Per-Fund Approval Gate

**Date**: 2026-10-29 | **Input**: spec.md + code-explorer discovery report (verified at `9d4db75`)

## R1. Where the gate intercepts

**Decision**: Gate in `paper/tick.py::_run()` (line ~243), NOT in `pipeline/session.py::advance()`.

**Evidence**: `_run` is the single choke point shared by `aihf paper tick`, `redo`, and both runner loops (`_run_days`, `_run_bars`) — one change covers CLI, TUI, cron, and runner. The engine's `advance()` is shared with backtesting, where approval mode is meaningless. On skip, `_run` passes `state.model_copy(update={"pending": None})` to `advance`, which then marks the book and (on a rebalance session) makes a fresh decision; `next_state` naturally drops the expired decision. Zero engine/schema/hash changes.

**Alternatives rejected**: gating inside `execute_decision` (engine layer — would affect backtests and duplicate policy); gating in the runner loops only (misses manual `tick`).

## R2. What new state goes on disk

**Decision**: A verdict mailbox only — `pending-approval.json` in the fund dir. The decision itself stays in the ledger chain.

**Evidence**: `SessionRecord.decision` folds into `FundState.pending` via `next_state` and is replayed from disk on every tick; the module docstring states "nothing about a decision lives anywhere else" (`pipeline/models.py:47-49`). Duplicating the decision into a side file creates drift risk against the chain. The verdict is the only new state: `{"verdict": "approve"|"reject", "decision_as_of": "<pending.as_of>", "decided_at": iso, "by": "cli"|"tui"}`.

**Keying**: `decision_as_of` matches `state.pending.as_of`. After `redo` replaces the deciding session, the old verdict's key no longer matches the current pending → ignored, never honored (spec FR-006, edge case).

**Fail-safe semantics**: missing or corrupt file ⇒ no verdict (spec FR-015). This is deliberately opposite to the kill switch's fail-loud `LedgerError` on corrupt `control.json` — a mailbox must never be interpreted as a yay, and a corrupt nay must not wedge the fund.

## R3. FundSpec field and hash parity

**Decision**: `approval_required: bool = False` on `FundSpec`; `_serialize` (wrap mode, `fund/spec.py:206`) pops it when `False`, exactly like `costs` at default.

**Evidence**: `replay()` re-serializes every parsed record and compares hashes (`paper/ledger.py:170-172`); each record embeds a serialized FundSpec. If the field appeared in serialization when `False`, every existing ledger would fail verification on first replay after upgrade. The pop-when-default pattern is already proven by `interval`/`window`/`costs`. `extra="forbid"` on FundSpec means the field must be declared, and old YAML without it parses unchanged.

**Mandatory test**: byte-parity assertion — an approval-OFF `FundSpec.model_dump_json()` equals the pre-feature serialization; a ledger written before the field verifies under `replay(full=True)` (mirror `test_ledger.py:151-168` integer-shares compat tests).

## R4. Verdict lifecycle

**Decision**: Write on approve/reject (CLI or TUI) → read+resolve at gate time in `_run` → consume (clear file) after the session's `ledger.append` succeeds.

**Evidence**: `ledger.append` refuses duplicates/out-of-order/broken chains; clearing only after a successful append means a failed tick leaves the verdict intact for retry. `write_atomic` (`paths.py:43`, sibling temp + `os.replace`) is crash-safe and Windows-safe; both containers mount the same volume (`docker-compose.yml:33,47`), so the file is the cross-container mailbox. Last-writer-wins is fine at human decision speed; a verdict written mid-session applies next session.

**Event kinds**: `approve`, `reject` (written at verdict time with `by` + `decision_as_of`), `expire` (written at skip time when no/stale verdict). `events.jsonl` is append-only and NOT hash-chained (`ledger.py:247-253`) — new kinds need no chain changes. The skip itself is additionally visible in the session record (no execution).

## R5. Skip semantics (expiry)

**Decision**: No/stale verdict at gate time ⇒ skip execution: `log_event("expire", ...)`, clear a stale verdict file, pass `pending=None` into `advance`. Fund continues; NOT a halt.

**Evidence**: `next_state` (`session.py:202-210`) sets `pending = record.decision`; a mark-only session with a fresh decision replaces the pending naturally. Weekly/monthly funds stay mark-only until the next period's decision — UI copy must say the decision lapsed (spec edge case). The auto-halt path (`tick.py:255-259`) is reserved for exceptions; a skip is a normal, expected outcome and must not trigger it.

## R6. CLI surface

**Decision**: `aihf paper approve <name> [--now]` and `aihf paper reject <name>`, registered beside `halt`/`resume` (`run.py:188-193` pattern, dispatch tail `run.py:377-385`). `aihf paper create --approval` sets the flag at creation (pattern: `_override_rebalance`, `run.py:296`).

**Refusals**: gate OFF ⇒ error naming the fund; nothing pending ⇒ "nothing awaiting approval". `--now` with nothing due: `tick` raises `NothingDue` (`tick.py:180-186`) — catch it and report "will execute at the next close" (exit 0). Approve/reject refuse while... (no toggle path exists for deployed funds; the create-time flag is the only setting surface, so no pending-state race on the setting itself).

**Status**: `paper status` (`run.py:349-367`) already prints pending target weights — add the awaiting-approval line there and in `_status_line` (`run.py:387`).

## R7. TUI surface

**Decision**: Bindings `y` = approve, `n` = reject on `PaperScreen` (pattern: `h`/`r` halt/resume, `paper.py:91-99`, `:319-332`); `check_action` (`:236`) enables them iff `snap.gate and snap.pending and not snap.halted`. `PaperSnapshot` (`paper_view.py:48`) gains `gate`/`approval` properties; `next_run_rows` (`:169`) rewrites the "First: execute the <date> decision" row to "awaiting approval — y approve · n reject" when gated+pending; `run_plan` (`:321`) says the run will mark the book and skip execution.

**Builder**: approval step in paper mode after cadence (`STEP_IDS`/`STEP_TITLES`, `builder.py:117-122` — precedent: `step-tickers`); `_finish_build` (`:466`) passes `approval_required` into the FundSpec.

## R8. Kill-switch orthogonality

**Decision**: The gate never reads or writes `control.json`; halt/resume never touch `pending-approval.json`.

**Evidence**: A gated fund is not halted — it keeps running sessions (mark, decide, record) and only skips executing unapproved decisions. Halt enforcement stays three-layer (engine `session.py:150`, entry checks `tick.py:172`/`runner.py:101,133`, TUI `check_action`). A halted gated fund behaves exactly as a halted ungated fund (spec US5 scenario 4).

## R9. Test strategy

**Decision**: Co-located pytest, fixtures only. `deploy(..., root=tmp_path)` pattern (`test_tick.py:71`); `offline` fixture for CLI (`test_run.py:26`); TUI autouse `isolated_configuration` (`tui/conftest.py:9`); `FakeAnalyst`/`FakeDataClient`/`SERIES` from `backtesting/test_fund.py`; `registered_fakes` autouse fixture.

**Windows discipline** (memory.md): TUI tests per-file (full-dir run hangs post-summary); trust the pytest summary line, not the process exit code; do not reformat pre-existing black/isort-flaky regions in `run.py`/`test_run.py`; no BOM in YAML.

## R10. Documentation

**Decision**: Top-level README fund-settings section gains approval mode (default off, three creation surfaces, approve/reject commands, expiry-not-halt). `hedge_fund/README.md` gains the same at package level if it carries a fund-settings reference. `example.yaml` gains a commented `approval_required` line (parsed content unchanged — the shipped example's behavior must not change).