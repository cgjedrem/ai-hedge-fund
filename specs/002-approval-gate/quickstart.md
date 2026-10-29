# Quickstart: Per-Fund Approval Gate — Validation Scenarios

**Date**: 2026-10-29 | **Spec**: [spec.md](./spec.md)

All scenarios run against fixture funds in a scratch home (tests) — never `~/.hedge-fund`, never Docker, never network. The commands below are the human-readable form of what the test suite exercises.

## Scenario 1 — Default OFF is today's behavior (US1.4, US2.3, SC-002)

1. Create a paper fund from a mandate with no `approval_required` key.
2. Run a session that produces a decision; run the next session.
3. **Expect**: the pending decision auto-executes at the next close exactly as today; the deployed `fund.yaml` is byte-identical to the pre-feature serialization; a pre-feature ledger verifies.

## Scenario 2 — Gate ON holds the decision (US2.1–2.2, FR-007/008)

1. Create a paper fund with approval mode on (mandate key, builder step, or `--approval`).
2. Run a session that produces a decision; run the next session.
3. **Expect**: no orders placed, book unchanged by the skipped decision, session recorded, `expire` audit event, fund NOT halted; the following decision cycle produces a fresh decision normally.

## Scenario 3 — Approve (yay) (US3.1–3.2, SC-003)

1. Gated fund with a pending decision → `aihf paper approve <name>`.
2. **Expect**: verdict file written (`verdict=approve`, keyed to the pending `as_of`), `approve` audit event; the next session executes the decision.
3. With a session due → `aihf paper approve <name> --now` executes immediately.
4. With no session due → `--now` reports "will execute at the next close", exit 0.

## Scenario 4 — Reject keeps the book unchanged (US3.3, SC-004)

1. Gated fund with a fresh pending decision → `aihf paper reject <name>`.
2. Run the next session.
3. **Expect**: no orders, book unchanged, session recorded, verdict consumed.

## Scenario 5 — Refusals (US3.4–3.5, FR-009)

1. `approve`/`reject` on a gate-OFF fund → refusal naming the fund.
2. `approve`/`reject` on a gated fund with nothing pending → "nothing awaiting approval".

## Scenario 6 — TUI (US4, FR-013)

1. Gated fund with pending decision on the fund screen → awaiting-approval state shown, `y`/`n` enabled.
2. `y` → verdict + audit event, screen refreshes. `n` on a fresh decision → same for reject.
3. Gate OFF / nothing pending / halted → `y`/`n` disabled.
4. Next-run description says the run will skip execution.

## Scenario 7 — Expiry and staleness (US5, FR-006/015)

1. Gated fund, no verdict → next session skips + `expire` event, fund continues (not halted).
2. Stale verdict (key ≠ current pending `as_of`, e.g. after redo) → ignored, skip path, stale file cleared.
3. Corrupt verdict file → treated as no verdict; never a yay.
4. Gated + halted fund → existing halt behavior unchanged; gate adds nothing.

## Full-suite gate (SC-006)

`python -m poetry run pytest hedge_fund -q` in directory chunks (Windows): the only failures allowed are the six documented baseline failures (features intraday `%-d`, 2× paper redo `os.rename`, paper sigterm `os.kill`, tui home file-mode, tui paper_view `%-d`). TUI tests run per-file. Trust the pytest summary line, not the process exit code.