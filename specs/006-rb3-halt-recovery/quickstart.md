# Quickstart: Validating RB-3 Halt Recovery Completion

**Date**: 2026-11-12 | **Plan**: [plan.md](plan.md) | **Contract**: [contracts/recovery-semantics.md](contracts/recovery-semantics.md)

All validation uses synthetic writable test roots (pytest fixtures). No production roots, broker calls, or paid data.

## Prerequisites

- Python 3.11 + Poetry env synced (`poetry install`), repo at the feature branch.

## Scenario 1 — Outstanding intent is visible and blocks work (FR-001/002/003)

1. Fixture: execute a tick that records its effect intent, then simulate interruption before outcome journaling.
2. Run: `poetry run pytest hedge_fund/paper/test_ledger.py hedge_fund/runtime/test_reconciliation.py -q -k intent`
3. Expect: preview enumerates the outstanding intent with identity/head/book/fill digests; a *different* request ID is denied with `reconciliation_required`; `resume_allowed` is false until reviewed.

## Scenario 2 — Halt mid-execution after a transmitted fill (FR-004)

1. Fixture: fund halted after the first fill of a multi-order execution (extends `test_tick.py:1476-1505`).
2. Run: `poetry run pytest hedge_fund/paper/test_tick.py -q -k halt`
3. Expect: a reconciliation-required record bound to the transmitted fill exists; the web preview shows it; Resume requires reviewed confirmation; zero-effect halts stay clean.

## Scenario 3 — Receipt expiry (FR-006)

1. Fixture: issue a receipt, then (a) mutate bound state, (b) advance the recorded clock past `valid_until`, (c) present a legacy receipt without expiry fields.
2. Run: `poetry run pytest hedge_fund/runtime/test_reconciliation.py hedge_fund/web/test_recovery.py -q -k receipt`
3. Expect: all three denied with re-review/expired reasons; a fresh bound receipt still authorizes Resume.

## Scenario 4 — No duplicate fills on restart/retry (FR-008)

- Run: `poetry run pytest hedge_fund/paper/test_tick.py hedge_fund/paper/test_ledger.py -q -k "retry or intent"`
- Expect: retried completed/intended operations return the recorded outcome or are denied; fill count per logical operation is exactly one.

## Scenario 5 — Daily/weekly funds unchanged (FR-009)

- Run: `poetry run pytest hedge_fund/paper/test_tick.py -q -k "weekly or daily or session"`
- Expect: all pre-existing cadence tests pass unmodified.

## Full-suite evidence (constitution Principle III)

- `poetry run pytest hedge_fund -q` — run **isolated** (~40 min; concurrent runs cause runner timeouts). Record exact failures-if-any against the pre-change baseline per the evidence contract. Targeted slices above must be green before the full run.
