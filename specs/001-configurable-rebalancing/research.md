# Research: Configurable Rebalancing Cadence

**Feature**: specs/001-configurable-rebalancing | **Date**: 2026-10-29

All unknowns were resolved during discovery (code-explorer recon + direct source verification at `d2f30c2`). No NEEDS CLARIFICATION items remain.

## R1: Is the cadence core actually already implemented?

- **Decision**: Treat mandate field, spec validation, scheduler rule, and TUI picker as already-built; pin them with tests rather than rebuild.
- **Rationale**: Verified directly in source: `Cadence` literal with four values and default `weekly` (`fund/spec.py:25,158-161`), cross-field validator for minute-only settings (`spec.py:189-205`), backward-compat serializer (`spec.py:206-219`), `is_rebalance_session` handling all four cadences plus first-session and unknown-value edge cases (`pipeline/session.py:231-248`), TUI picker with minute sub-steps (`tui/builder.py:98-103,380-387,466-477`). Existing tests already cover the default path (`fund/test_spec.py:41-48`), cadence validation (`test_spec.py:50-53`), and the period rule including holiday-Monday and ISO-year boundary (`pipeline/test_session.py:60-75`).
- **Alternatives considered**: Rebuilding the surfaces "to be sure" — rejected: violates minimal-change discipline and risks ledger-integrity regressions for zero user value.

## R2: How should the CLI override construct a valid overridden spec?

- **Decision**: After `load_spec`, build the overridden spec by round-tripping through the model: dump the loaded spec (the existing wrap serializer already omits `interval`/`window` from day-grid funds and default `costs`), drop `interval`/`window` when the target cadence is not `minute`, set `rebalance`, and re-validate via the model. Apply in `_backtest` and `paper create` only, before backtest execution / `deploy()`.
- **Rationale**: The cross-field validator rejects `interval`/`window` on non-minute funds *when explicitly set*; a naive `model_copy(update={"rebalance": ...})` on a minute mandate overridden to daily would leave those fields set and raise a confusing error. The dump→mutate→validate round-trip reuses the model's own validation (FR-015) and guarantees the result serializes canonically (FR-006, FR-010). Overriding to `minute` on a day-grid mandate needs no special handling: absent `interval`/`window` keys fall back to the standard defaults, exactly matching a mandate that says only `rebalance: minute` (FR-011).
- **Alternatives considered**: `model_copy(update=...)` — rejected (cannot unset fields; leaks minute-only settings into day-grid specs); raw dataclass-style reconstruction — rejected (duplicates validation the model already owns).

## R3: How is an invalid override value rejected before engine work?

- **Decision**: Constrain the flag with argparse `choices` on the two subparsers; argparse then rejects unknown values with a usage error naming the value and the allowed set, before `load_spec` or any engine call.
- **Rationale**: Matches the existing CLI style (plain argparse, `parser.error` for domain errors, pure-JSON stdout); satisfies FR-002/FR-015 at the CLI surface with zero new code paths.
- **Alternatives considered**: Post-load validation with `parser.error` — redundant given `choices`, kept only if implementation finds a case `choices` misses.

## R4: Where must the override NOT exist?

- **Decision**: No cadence override on `paper tick/run/stop/status/list/scorecard/halt/resume`. Deployed funds are frozen: `fund.yaml` is snapshotted at `deploy()` and `execute_decision` refuses cross-spec execution; every ledger record stamps the mandate hash.
- **Rationale**: Ledger integrity (constitution I). A post-deploy cadence change would fork the configuration a live fund trades under.
- **Alternatives considered**: An explicit `--force` escape hatch — rejected as out of scope and dangerous.

## R5: Should `--rebalance minute` be allowed from the CLI?

- **Decision**: Yes. Semantics identical to writing `rebalance: minute` alone in a mandate: standard interval (1 minute) and trading window (09:30–16:00 ET) defaults apply unless the mandate already provides them.
- **Rationale**: Keeps flag semantics == mandate semantics; no special-casing; the model validator already guarantees validity.
- **Alternatives considered**: Rejecting `minute` via flag to force mandate editing — rejected: inconsistent with mandate behavior, adds a special case, and the defaults are documented.

## R6: Documentation placement?

- **Decision**: Root `README.md` gains a short mandate-field reference (cadence: values, default, meaning; minute-only interval/window; the CLI override). `hedge_fund/fund/example.yaml` cadence comment lists all four values. `hedge_fund/README.md` gets the override flag mentioned where the minute fund is introduced.
- **Rationale**: Discovery found the root README never documents mandate fields; example.yaml's comment omits `minute` (stale). Both are the exact gaps the brief calls out.
- **Alternatives considered**: A new docs/ page — rejected: repo convention keeps docs in READMEs.

## R7: Test strategy for the delta?

- **Decision**: Extend `hedge_fund/test_run.py` (offline fixture, JSON-stdout assertions) with: backtest override changes the result's cadence label/cycle count; `paper create` override lands in the deployed `fund.yaml`; invalid value → argparse usage error; no-flag mandate-without-rebalance → weekly (CLI default path); minute→daily override succeeds without minute-only leakage; daily→minute override yields valid defaults; tick/run parsers expose no such flag. Existing suite must stay green except the six documented Windows baseline failures.
- **Rationale**: The CLI is the only behavior change; TUI/scheduler/spec behavior is already pinned by existing tests and must not regress.
- **Alternatives considered**: New test module — rejected: co-location and existing fixtures make `test_run.py` the natural home.