# Data Model: RB-3 Halt Recovery Completion

**Date**: 2026-11-12 | **Plan**: [plan.md](plan.md)

All entities are extensions of existing ledger/reconciliation artifacts. New fields are additive; pre-feature records remain replayable byte-identically.

## Entities

### Effect Intent (existing, extended in standing)

Durable journal record written before an operation's effects are attempted.

- **Fields**: operation identity (request ID), fund, operation kind (execution / resume), recorded-clock timestamp, outcome reference (absent while unresolved).
- **New standing rule**: an execution intent with no outcome is a *reconciliation-required condition* with the same standing as a recorded failure (FR-001).
- **Validation**: at most one unresolved Resume intent per fund; an unresolved intent of any kind blocks fund work readiness (FR-003).

### Recovery Receipt (existing, extended)

Operator's reviewed confirmation authorizing one Resume.

- **Existing fields**: failure/operation identity, ledger head hash, broker-book digest, fill digest, reviewer, decision.
- **New fields**: `issued_at` (recorded clock), `valid_until` (recorded clock, bounded window).
- **Validation rules**:
  - Single-use; bound-state change (identity/head/book/fill digest) invalidates (existing rebind check).
  - `recorded_now > valid_until` → expired, Resume denied with re-review reason (FR-006).
  - Receipt missing the new fields → treated as expired (fail-closed; no grandfathering).

### Reconciliation Preview (existing, extended)

Operator-facing summary of everything requiring review for a fund.

- **Entries**: recorded execution failures (existing) **+** outstanding execution intents (new, FR-002).
- **Each entry**: operation identity, ledger head, broker-book digest, fill digest, reason.
- **Derived flag**: `resume_allowed` = Halt active AND no unreviewed failures AND no outstanding intents AND no unresolved Resume intent (extended per FR-005).

### Resume Intent (existing, semantics unchanged)

Durable record that Resume was attempted; completion recorded afterward. Unresolved Resume intent blocks further control writes (existing) and now also blocks general work readiness and `resume_allowed` (FR-003/FR-005).

## State Transitions

```text
Execution:  INTENT_RECORDED → OUTCOME_RECORDED (ok | failed)
                | (interruption with no outcome)
                +→ OUTSTANDING → requires reconciliation → OUTCOME_RECORDED via recovery

Fund:       RUNNING → HALTED (manual or on failure)
            HALTED → RECONCILIATION_REQUIRED (failure or outstanding intent present)
            RECONCILIATION_REQUIRED → RESUMABLE (reviewed receipt, fresh & bound)
            RESUMABLE → RUNNING (Resume: intent → clear Halt → completion)

Receipt:    ISSUED → (bound-state change | expiry) → INVALID → requires fresh review
```

## Relationships

- Preview aggregates failures and intents **for one fund**; cross-fund isolation is absolute.
- Receipt binds to exactly one failure/intent identity and one ledger head; Resume consumes at most one receipt.
- Session keys (daily/weekly date keys, minute timestamps) are untouched; no cadence-related fields change (FR-009).
