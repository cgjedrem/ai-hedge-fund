# Data Model: Configurable Rebalancing Cadence

**Feature**: specs/001-configurable-rebalancing | **Date**: 2026-10-29

No persisted schema changes. This document records the entities the feature touches and the validation rules that govern them, so implementers and reviewers share one reference.

## Entities

### Cadence (value object, existing — pinned)

- **Values**: `minute` | `daily` | `weekly` | `monthly` — exactly four, everywhere.
- **Default**: `weekly` (applies whenever a mandate omits the field).
- **Meaning**: how often the fund decides — every bar (minute), or the first session of each day/ISO-week/calendar-month (day-grid cadences).
- **Validation**: unknown values rejected at mandate load (model-level, error names the value) and at the engine boundary (`is_rebalance_session` raises naming the value); rejected at the CLI by argument-choice checking before any engine work.

### Fund mandate (existing — unchanged shape)

- **Cadence field**: optional; absent ⇒ `weekly`.
- **Minute-only fields**: `interval` (bar spacing in minutes, floor 1 second) and `window` (trading window inside 04:00–20:00 ET). Belong ONLY to minute funds; their presence on a day-grid fund is a validation error.
- **Serialization invariant**: a day-grid mandate serializes without `interval`/`window`; a mandate at default costs serializes without a `costs` block. This keeps pre-existing ledgers verifiable byte-identically. **This feature must not alter any serialized output.**

### Overridden spec (new transient concept — never persisted as a new shape)

- **What**: an in-memory fund configuration derived from a loaded mandate by replacing the cadence, produced only when the CLI override flag is present.
- **Construction rule**: dump the loaded spec (the existing serializer omits minute-only fields from day-grid funds), remove `interval`/`window` when the target cadence is a day-grid value, set the target cadence, re-validate through the model.
- **Validity rules inherited from the model**: minute funds must have interval ≥ 1 second and interval no longer than the trading window; day-grid funds must not carry interval/window.
- **Lifecycle**: exists from the override point until the command finishes; for `paper create` it is frozen into the deployed snapshot at creation; never written back to the source mandate.

### Frozen fund configuration (existing — unchanged)

- **Snapshot**: taken at paper-fund creation; carries the (possibly overridden) cadence from that moment on.
- **Immutability**: no CLI path may alter the cadence of a deployed fund; every ledger record stamps the hash of the configuration in force.

### Session record (existing — untouched)

- **Rebalance flag**: whether the session was a rebalance session (first session of period / every bar).
- **Mandate hash**: hash of the serialized configuration in force, chaining records. Unchanged by this feature.

## State transitions

```text
mandate YAML ──load──▶ spec ──(no flag)──────────────▶ engine (backtest | deploy)
                    └──(with --rebalance X)─▶ overridden spec ──▶ engine (backtest | deploy)
deploy: spec ──freeze──▶ deployed fund.yaml  (cadence fixed from here on)
```

## Validation rules summary (where errors surface)

| Input | Bad value | Surface | Error style |
|-------|-----------|---------|-------------|
| mandate `rebalance` | e.g. `hourly` | mandate load | names value + allowed values, includes file path |
| CLI `--rebalance` | e.g. `hourly` | argument parsing | usage error naming value + allowed choices, before engine work |
| minute-only fields on day-grid fund (incl. after override) | any | model validation | field-prefixed, lowercase, en-dash house style |
| interval/window out of range on minute fund | any | model validation | field-prefixed message with the floor/bound |