# Phase 1 Data Model: Legacy Failure Recovery

**Date**: 2026-11-17 | **Spec**: [spec.md](spec.md) | **Research**: [research.md](research.md)

## Entities

### Historical failure event (existing, unchanged)

Audit event of kind `tick_failed` (or legacy equivalent) in the fund's events file.

- Identity: SHA-256 digest of canonical JSON of the whole event (existing rule, `hedge_fund/runtime/reconciliation.py:365-405`).
- Fields relevant here: `time`, `kind`, error summary; optional `request_id`, `expected_head`, attempt identity, transmitted-fill metadata. Legacy events may lack all optional fields.
- **Invariant**: never modified, re-serialized, or deleted by this feature.

### Evidence classification (computed, not persisted)

Per-failure result produced at preview time by the classification rule (research.md Decision 2):

- `failure_digest`: the event identity.
- `outcome`: `resolvable` | `not_resolvable`.
- `checks`: per-check pass/fail detail (replay verified, zero corrupt events, book digest matches, chain continuity across failure, no post-effect fields present).
- `reason`: operator-visible specific gap when `not_resolvable`.
- Validation rules: identical computation used by preview display and confirm gate (FR-012); exception type/message text is never a check input (FR-002).

### Reconciliation decision record (new, append-only audit record)

Durable record appended through the anchored audit boundary on confirm.

- `kind`: new audit event kind for the decision (e.g., `legacy_failure_reconciliation` — exact name fixed in tasks).
- `decision_id`: derived from content (failure-set digest + head + book digest + recorded time) for idempotent replay dedup.
- `failure_digests`: ordered list of resolved failure digests; MUST equal the previewed set.
- `ledger_head`: head digest at preview time; confirm MUST re-verify equality.
- `book_digest`: broker-book digest at preview time; confirm MUST re-verify equality.
- `operator`: operator identity string (existing audit `by` convention).
- `recorded_time`: recorded clock value (constitution Principle IV).
- `attestation`: explicit operator acknowledgment that residual uncertainty (research.md Decision 2, check 4) is accepted.
- Validation rules: every digest in `failure_digests` must currently be unresolved and classified resolvable; unknown or already-resolved digests reject the whole record (atomic set semantics).

## State transitions

```text
unresolved failures (N >= 1)
  -> preview: classify each (computed only, zero writes)
  -> confirm (all resolvable, head/book/set unchanged, lanes held):
       append decision record -> failures in set become "resolved by decision"
  -> confirm (any drift or any not_resolvable): refused, zero writes

resolved by decision:
  readiness treats bound digests as resolved; all other gates (halt, intent,
  corruption, mismatch) unchanged. Irreversible by this feature (no un-resolve).
```

## Relationships

- Decision record 1—N historical failure events (by digest binding).
- Decision record binds one ledger head and one book digest (staleness anchor).
- Classification derives from: event stream (existing), verified replay result (existing), broker-book comparison (existing). No new persisted inputs beyond the decision record itself.
