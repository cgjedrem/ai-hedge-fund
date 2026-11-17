# Quickstart Validation: Legacy Failure Recovery

**Date**: 2026-11-17 | **Spec**: [spec.md](spec.md)

All validation runs on synthetic enrolled test roots (`hedge_fund/runtime/test_bootstrap.py` pattern; `enroll_synthetic_root`). No production data, no providers, no LLM calls.

## Prerequisite

```powershell
poetry install
```

## Scenario A — P1 happy path (multiple unkeyed failures resolved)

1. Fixture: synthetic fund whose events file contains 3 legacy `tick_failed` events (no `request_id`, no post-effect fields), followed by later verified session records; broker book matches replay.
2. Run the focused tests (exact IDs assigned in tasks.md), e.g.:
   ```powershell
   poetry run pytest hedge_fund/runtime/test_reconciliation.py hedge_fund/web/test_recovery.py -q -k legacy
   ```
3. Expected: preview lists 3 failures, all `resolvable`, `confirm_offered=true`; confirm appends exactly one decision record; recovery state ready; work admission no longer returns 423; pre-existing events/ledger bytes hash-identical before/after.

## Scenario B — P2 refusals (each independent)

| Fixture | Expected |
|---|---|
| One failure carrying transmitted-fill/post-effect fields | that failure `not_resolvable`, no confirm offered |
| Corrupt audit event injected | corrupt state, zero writes |
| Book digest perturbed | book-mismatch refusal, zero writes |
| Append an event between preview and confirm | 409 stale-preview, zero writes |
| Second writer holds fund lane | contention response, zero writes |
| Confirm repeated after success | idempotent already-resolved, no second record |

## Scenario C — crash/retry

Interrupt confirm between decision-record intent and completion (fault-injection pattern from spec006/007 tests); retry. Expected: exactly one durable decision, consistent replay, no duplicate resolution.

## Scenario D — regression guard

```powershell
poetry run pytest hedge_fund -q
```

Expected: full suite green, or every failure individually evidenced as unchanged baseline per constitution Principle III (exact test ID, expected/observed, source/build, platform, recorded time, fixture provenance, reproduction on `e6f04d2`).

## Scenario E — production (separate approval, NOT part of this feature's acceptance)

Attended operator reconciliation of the two real funds requires: this feature merged, synthetic acceptance complete, and a fresh explicit operator approval naming funds, expected failure digests, and rollback evidence (verified backup). It is executed interactively by the operator, never by an agent session.
