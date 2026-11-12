# Data Model: RB-3 Halt Recovery Completion

**Date**: 2026-11-12 (revised post-rebase onto `448056f`) | **Plan**: [plan.md](plan.md)

All entities extend PR #11 artifacts. New fields are additive; pre-feature records replay byte-identically.

## Entities

### Tick Intent / Orphaned Intent (PR #11, extended)

Durable pre-effect record; unresolved until outcome (`tick_failed` / `tick_aborted` / completion).

- **PR #11 standing**: enumerated in a digest-bound recovery preview, fenced for new-identity ticks, resolvable via audited intent resolution (`ledger.py:371-432`, `:1025-1104`).
- **This feature**: joins the common unresolved-state set used by all three gate call sites (FR-003/004).

### Approval-Consumption Entry (existing, newly resolvable)

Journal record of approval consumption. PR #11 resolves entries matching an intent; entries matching no intent currently wedge the fund.

- **This feature**: unmatched entries are enumerated in the recovery preview and resolvable through the same reviewed, audited path (FR-002).

### Resume Intent (existing, extended standing)

Durable record of an attempted Resume; completion recorded afterward.

- **This feature**: unresolved Resume intents join the common unresolved-state set — they already block `Ledger.resume()` (`ledger.py:1209-1216`); they now also block general work readiness and web `resume_allowed` (FR-003).

### Recovery Receipt — failure-bound and intent-bound (PR #11, extended)

Reviewed confirmation authorizing one Resume or one intent resolution.

- **Existing fields**: bound identity, ledger head hash, broker-book digest, fill digest, reviewer, decision, `recorded_at`.
- **New fields**: `issued_at`, `valid_until` (recorded clock, bounded window) (FR-006).
- **Validation**: single-use; bound-state change invalidates (existing rebind); `recorded_now > valid_until` → expired, denied with re-review reason; missing expiry fields → expired (fail-closed). Expiry invalidates the *authorization only*, never the reconciliation requirement (FR-008).

### Recovery Surface State (desk-facing, refined)

- `corrupt`: replay/link verification failed (existing, unchanged visibility).
- `reconciliation_required` (refined): replay valid, fund not ready — unresolved-state set non-empty. Recovery surface MUST be fetched and displayed in this state, even when readiness denial would previously have collapsed to not-ok (FR-001).
- `ready`: no unresolved state.

## State Transitions

```text
Execution:  INTENT → OUTCOME (completed | tick_failed | tick_aborted[no_effects])
                | (crash before outcome) → ORPHANED → reviewed resolution → resolved

Approval:   CONSUMPTION → (matches intent) resolved via intent path
                       → (matches none) enumerated → reviewed resolution → resolved   [new]

Fund:       RUNNING → HALTED → RECONCILIATION_REQUIRED (unresolved-state set non-empty)
            RECONCILIATION_REQUIRED → RESUMABLE (all entries reviewed/resolved, fresh receipt)
            RESUMABLE → RUNNING (Resume: intent → clear Halt → completion)

Receipt:    ISSUED → (bound-state change | recorded clock past valid_until | legacy fields) → INVALID
```

## Relationships

- The unresolved-state query is the single source for readiness, `resume_allowed`, and the Resume pre-check — per fund, cross-fund isolation absolute.
- Receipts bind exactly one failure or intent identity plus current head/book/fill digests; one receipt authorizes one operation.
- Session keys (daily/weekly date keys, minute timestamps) untouched (FR-007).
