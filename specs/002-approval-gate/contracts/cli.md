# CLI Surface Contract: Per-Fund Approval Gate

**Date**: 2026-10-29 | **Spec**: [spec.md](./spec.md)

All commands under the existing `aihf paper` subcommand group. Refusals exit non-zero with a message naming the fund and the reason. Successes print a confirmation line and record the corresponding audit event.

## New subcommands

### `aihf paper approve <name> [--now]`

Yay the fund's pending decision.

| Precondition | Failure behavior |
|---|---|
| fund exists | unknown name ⇒ existing fund-dir error |
| gate ON (`approval_required` in deployed spec) | `approval gate is not enabled for '<name>'` |
| a decision is pending | `nothing is awaiting approval for '<name>'` |
| not halted | halted ⇒ existing halt refusal path (gate adds nothing) |

- Writes the verdict mailbox (`verdict=approve`, keyed to the pending decision's `as_of` and source-record hash, `by="cli"`) + `approve` audit event.
- Default: the decision executes at the next session close.
- `--now`: chains one `tick()` immediately; if a session is due the decision executes right away; if none is due (`NothingDue`) the command reports the decision will execute at the next close and exits 0.

### `aihf paper reject <name>`

Nay the fund's pending decision. Same preconditions/refusals as approve (no `--now`).

- Writes the verdict mailbox (`verdict=reject`, keyed to the pending decision identity, `by="cli"`) + `reject` audit event.
- The next session skips execution; the book is unchanged; the verdict is consumed.

## Changed subcommands

### `aihf paper create <mandate> <name> [--approval]`

- New store-true flag `--approval`; applied to the spec before the deploy freeze (pattern: `--rebalance` override).
- Confirmation output states approval mode when on.

### `aihf paper status <name>` and the fund list line

- When gate ON and a decision is pending: status shows the pending weights (existing) plus an `awaiting approval` line; the one-line fund summary carries an awaiting-approval marker.
- When a decision was skipped/expired, status reflects the ledger as recorded (no special state).

## Non-changes (pinned)

- `halt`/`resume` untouched; the gate never reads/writes `control.json`.
- No new commands for toggling approval mode on a deployed fund (frozen at creation by design).
- `tick`, `run`, `redo`, `stop`, `list`, `scorecard` behavior unchanged for gate-OFF funds.

## TUI surface (contract mirror)

- Fund screen bindings: `y` approve, `n` reject — enabled iff gate ON ∧ pending ∧ not halted; disabled otherwise.
- Fund screen shows the awaiting-approval state and the pending decision's target weights.
- Next-run description for gated+pending: says the run will skip execution (decision lapsed wording on expiry), not "execute the decision".
- Builder (paper mode): approval step after cadence with plain-language description; choice saved into the deployed spec.