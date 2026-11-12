# Quickstart Validation: Paper Writer Safety

**Prerequisites**: Poetry env installed (`poetry install`), Windows or Linux. All scenarios use owned synthetic enrolled test roots (`hedge_fund/runtime/test_bootstrap.py` support) and fake market data. **Never** point these at a real fund directory; `watchtower`/`watchtower-weekly` remain protected and untouched.

**Test naming convention (required)**: new fence tests must contain `intent` in the test ID and new dedup tests must contain `logical` or `duplicate`, so the `-k` filters below cannot silently select zero tests; each scenario run must report a non-zero collected count and the evidence note must record it.

## Scenario A — Unresolved-intent fence (US1 / FR-001..004)

1. Focused test run (after implementation):
   ```powershell
   poetry run pytest hedge_fund/paper/test_ledger.py hedge_fund/paper/test_tick.py -q -k "intent"
   ```
2. Expected:
   - Synthetic crash-after-intent fixture → new-identity tick refused with reason `unresolved-tick-intent`, fields populated per [contracts/refusal-contract.md](contracts/refusal-contract.md).
   - Same-identity retry reaches existing replay/reconciliation (no fence interference).
   - Reconciled intent → new sessions admitted.
   - No-intent baseline → admission path unchanged (existing tick tests green).

## Scenario B — Logical-operation dedup (US2 / FR-005..008)

1. Focused test run:
   ```powershell
   poetry run pytest hedge_fund/runtime/test_operations.py hedge_fund/runtime/test_writer_races.py -q -k "logical or duplicate"
   ```
2. Expected:
   - Same logical action, two independent request IDs → exactly one execution; second refused `duplicate-logical-operation` referencing the first operation ID.
   - Different session/action → both independent.
   - Terminal-failed prior operation → resubmission admitted.
   - Restart between submissions (fresh store handle) → dedup still holds (durability).
   - Cross-entry-point race (CLI child vs web admission, owned child vs CLI) → one recorded fake fill, matching book.

## Scenario C — Regression + governance evidence

1. Focused writer-map guard:
   ```powershell
   poetry run pytest hedge_fund/runtime/test_writer_map.py -q
   ```
2. Style on changed scopes:
   ```powershell
   poetry run black --check <changed files>; poetry run isort --check-only <changed files>; poetry run flake8 <changed files>
   ```
3. Full suite, run alone (≈40 min; concurrent pytest runs cause runner timeouts — repository memory):
   ```powershell
   poetry run pytest hedge_fund -q
   ```
   Any failure must be individually evidenced as unchanged baseline per Constitution III, or the feature is not done.

## Out of bounds (must NOT happen during validation)

- No creation/modification/access of real or protected fund roots.
- No paid-provider calls, no Docker daemon operations, no brokerage requests.
- No edits to existing ledger serialization; old fixture ledgers must replay byte-identically (existing replay tests cover this).
