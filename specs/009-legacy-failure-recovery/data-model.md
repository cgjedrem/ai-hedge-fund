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
- `classification`: `verified` | `attestable` | `not_resolvable`.
- `checks`: replay, corruption, book, stream continuity, and post-effect-field evidence.
- `effect_evidence`: pending decision at expected head, post-advance failure shape, and effect-field presence.
- `reason`: structural gap for `not_resolvable`; missing no-effect proof for `attestable`.
- `verified`: structural checks pass; replay at `expected_head` has no pending decision; no effect marker contradicts proof.
- `attestable`: structural checks pass, but no-effect proof is unavailable; operator attests this digest.
- `not_resolvable`: at least one structural check fails; blocks the entire set.
- Validation rules: preview and confirm share classification logic (FR-012); exception text never proves no effect. Error shape may only downgrade a failure to `attestable`.
- Continuity invariant: failure event index precedes a successful `tick` event that matches a verified successor record chained from `expected_head`. Session-label ordering alone is insufficient. Intraday timestamps retain full `HH:MM:SS`.

### Reconciliation decision record (new, append-only audit record)

Durable record appended through the anchored audit boundary on confirm.

- `kind`: new audit event kind for the decision (e.g., `legacy_failure_reconciliation` — exact name fixed in tasks).
- `schema_version`: v2 for new decisions; v1 global-attestation records remain replayable.
- `decision_id`: derived from decision content for replay deduplication.
- `failure_digests`: ordered list of resolved failure digests; MUST equal the previewed set.
- `ledger_head`: head digest at preview time; confirm MUST re-verify equality.
- `book_digest`: broker-book digest at preview time; confirm MUST re-verify equality.
- `audit_history_digest`: SHA-256 of exact `events.jsonl` bytes at preview time and before append.
- `audit_history_length`: byte count for exact retry recognition of the decision's own append.
- `operator`: operator identity string (existing audit `by` convention).
- `recorded_time`: recorded clock value (constitution Principle IV).
- `attested_failure_digests`: exact subset classified `attestable`; verified failures need no attestation.
- Validation rules: every digest in `failure_digests` must currently be unresolved and structurally resolvable; `attested_failure_digests` MUST equal the attestable subset. Unknown, already-resolved, not-resolvable, missing, or extra digests reject the whole record with zero writes.

## State transitions

```text
unresolved failures (N >= 1)
  -> preview: classify each; bind audit digest (computed only, zero writes)
  -> confirm (no not_resolvable, exact attestations, head/book/audit/set unchanged,
              control + audit lanes held):
       append decision record -> failures in set become "resolved by decision"
  -> confirm (any drift or not_resolvable): refused, zero writes

resolved by decision:
  readiness treats bound digests as resolved; all other gates (halt, intent,
  corruption, mismatch) unchanged. Irreversible by this feature (no un-resolve).
```

## Relationships

- Decision record 1—N historical failure events (by digest binding).
- Decision record binds one ledger head, book digest, and exact audit-history revision.
- Any audit append, including Halt, invalidates the preview.
- Classification derives from event-stream position, verified replay, and broker-book comparison. New persisted inputs are decision record fields only.
