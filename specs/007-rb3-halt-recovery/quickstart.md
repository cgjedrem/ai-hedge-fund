# Quickstart: Validating RB-3 Halt Recovery Completion

**Date**: 2026-11-12 (revised post-rebase onto `448056f`) | **Plan**: [plan.md](plan.md) | **Contract**: [contracts/recovery-semantics.md](contracts/recovery-semantics.md)

All validation uses synthetic writable test roots (pytest fixtures). No production roots, broker calls, or paid data.

## Prerequisites

- Python 3.11 + Poetry env synced (`poetry install`), repo on the feature branch at/after `448056f`.

## Scenario 1 — Recovery reachable under readiness denial (FR-001)

1. Fixture: fund whose readiness check denies work (e.g. unresolved approval consumption) while replay is valid.
2. Run: `poetry run pytest hedge_fund/web/test_recovery.py -q -k reconciliation`
3. Expect: snapshot reports `reconciliation_required` (distinct from corrupt); recovery preview is still served and displayable; corrupt-replay fixtures still report corruption.

## Scenario 2 — Unmatched approval consumption resolvable (FR-002)

1. Fixture: approval-consumption journal entry matching no intent (anchor: `hedge_fund/paper/test_tick.py:627-655`).
2. Run: `poetry run pytest hedge_fund/paper/test_tick.py -q -k approval`
3. Expect: entry enumerated in the recovery preview; resolves through the reviewed path; fund becomes resumable.

## Scenario 3 — One Resume gate (FR-003/004)

1. Fixtures: one per unresolved-state category (recorded failure, orphaned tick intent, unresolved Resume intent, unmatched approval consumption).
2. Run: `poetry run pytest hedge_fund/paper/test_ledger.py hedge_fund/web/test_recovery.py -q -k "resume or readiness"`
3. Expect: readiness, `resume_allowed`, and `Ledger.resume()` agree (deny until resolved, permit after reviewed recovery); recovery operations themselves remain admissible; PR #11 tick fence unchanged.

## Scenario 4 — Legacy no-ID post-fill Halt (FR-005)

- Run: `poetry run pytest hedge_fund/paper/test_tick.py -q -k "halt"`
- Expect: no-request-ID tick halted after ≥1 fill journals `tick_failed` bound to fill identities and appears in recovery; zero-effect halt keeps clean-abort semantics.

## Scenario 5 — Receipt expiry (FR-006/008)

- Run: `poetry run pytest hedge_fund/runtime/test_reconciliation.py hedge_fund/web/test_recovery.py -q -k "receipt or expiry"`
- Expect: expired receipts denied; legacy field-less receipts denied fail-closed; fresh bound receipts succeed; bound-state change still denied.

## Regression guards

- Cadence: `poetry run pytest hedge_fund/paper/test_tick.py -q -k "weekly or daily or session"` (unchanged).
- PR #11 writer safety: `poetry run pytest hedge_fund/paper/test_ledger.py hedge_fund/paper/test_tick.py -q` (dedup/safe-abort/intent-fence unchanged).

## Full-suite evidence (constitution Principle III)

- `poetry run pytest hedge_fund -q` — isolated (~40 min; concurrent runs cause runner timeouts). Record any failure against the pre-change baseline with exact test ID, expected/observed, platform, time, fixture provenance. Targeted slices green first. BLOCKED/INCONCLUSIVE is not PASS.
