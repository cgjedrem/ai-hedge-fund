# CLI Contract: `--rebalance` override

**Feature**: specs/001-configurable-rebalancing | **Date**: 2026-10-29

The command-line interface gains one optional option on exactly two subcommands. Everything else about the CLI is unchanged.

## Surface

```text
aihf backtest  MANDATE --universe UNIVERSE [--start DATE] [--end DATE] [--out PATH]
               [--rebalance {minute,daily,weekly,monthly}]          # NEW

aihf paper create NAME --mandate MANDATE --universe UNIVERSE
               [--rebalance {minute,daily,weekly,monthly}]          # NEW
```

No other subcommand (`paper tick/run/stop/status/list/scorecard/halt/resume`) accepts `--rebalance` — deployed funds are frozen at creation.

## Semantics

| Case | Behavior |
|------|----------|
| flag absent | mandate cadence used as today; mandate without `rebalance` ⇒ `weekly` (unchanged default path) |
| flag value == mandate cadence | no observable difference from absent flag |
| day-grid mandate + `--rebalance <day-grid value>` | fund runs/deploys on the overridden cadence |
| minute mandate + `--rebalance <day-grid value>` | valid day-grid fund; minute-only settings (interval, window) are dropped, never leaked |
| day-grid mandate + `--rebalance minute` | valid minute fund with standard defaults (interval 1 minute, window 09:30–16:00 ET) — same as writing `rebalance: minute` alone in the mandate |
| minute mandate + `--rebalance minute` | mandate's own interval/window preserved |
| unknown value (e.g. `hourly`) | usage error naming the value and the allowed choices; exit before mandate load or any engine work |

## Output contracts

- **stdout stays pure JSON** (existing house rule). `backtest` result and `paper create` confirmation already carry cadence-derived fields (`rebalance` label / `cadence_label`); they reflect the override with no format change.
- **stderr** carries the rich console output, including the usage error for invalid values (argparse convention: message names the invalid choice and lists allowed values).

## Error contract

| Error | Where | Message shape |
|-------|-------|---------------|
| invalid choice | argument parse | `argument --rebalance: invalid choice: 'hourly' (choose from 'minute', 'daily', 'weekly', 'monthly')` |
| mandate invalid | mandate load | existing behavior — names file path and model error (unchanged) |
| minute-only fields after a malformed override | model validation | must never occur: the override transform drops them by construction; if it ever does, it is a bug |

## Compatibility

- Existing invocations without `--rebalance` behave byte-for-byte as before (same stdout JSON, same exit codes).
- The source mandate file is never modified by the override.
- Deployed-fund commands gain nothing and lose nothing.