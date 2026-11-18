# Contract: Legacy Failure Recovery (web surface)

**Date**: 2026-11-17 | **Spec**: [../spec.md](../spec.md)

Extends the spec007 recovery-semantics contract (`specs/007-rb3-halt-recovery/contracts/recovery-semantics.md`) and the spec005 runtime API contract (`specs/005-web-engine-migration/contracts/runtime-api.md`). Reviewed recovery remains web-only.

## Preview (extended)

Existing recovery preview response gains, per fund, an ordered `failures` array:

```json
{
  "failure_digest": "sha256:...",
  "time": "2026-11-03T05:05:03Z",
  "error_summary": "DataClientError: ...",
  "has_request_id": false,
  "classification": "verified | attestable | not_resolvable",
  "checks": {
    "replay_verified": true,
    "corrupt_events_zero": true,
    "book_matches_replay": true,
    "chain_continuity_across_failure": true,
    "no_post_effect_fields": true
  },
  "effect_evidence": {
    "pending_decision_at_head": false,
    "post_advance_failure_shape": false,
    "post_effect_fields_present": false
  },
  "reason": null
}
```

Three-way classification:

- `verified`: structural checks pass and replay at `expected_head` has no pending decision. System-proven no-effect; no attestation required.
- `attestable`: structural checks pass, but no-effect proof is unavailable (pending decision at head, post-effect metadata, or post-advance failure shape). Requires explicit per-failure attestation.
- `not_resolvable`: at least one structural check fails. Blocks the complete set.

Continuity anchors on the failure's index in the verified event stream. A later successful `tick` event must match a verified successor record chained from the expected head. Session labels alone do not prove ordering; minute-fund timestamps retain seconds.

Plus set-level fields: `preview_head`, `preview_book_digest`, `preview_audit_digest` (SHA-256 of exact `events.jsonl` bytes), `confirm_offered` (true only when no failure is `not_resolvable`), `set_reason` when not offered.

Error/state distinctions preserved: corrupt replay and corrupt audit events report the existing corrupt state (no failures array, no confirm); halted reports halted; this path never relabels them.

## Confirm (new)

POST confirm with body:

```json
{
  "preview_head": "sha256:...",
  "preview_book_digest": "sha256:...",
  "preview_audit_digest": "sha256:...",
  "failure_digests": ["sha256:..."],
  "operator": "operator identity",
  "attested_failure_digests": ["sha256:..."]
}
```

`attested_failure_digests` MUST equal exactly the request members classified `attestable`; `verified` members require no attestation. Any `not_resolvable` member, missing attestation, or extra attestation refuses the whole request with zero writes.

Outcomes:

| Condition | Result | Writes |
|---|---|---|
| All digests unresolved + verified/attestable; exact attestations; head/book/audit digest unchanged; lanes acquired | 200, decision record appended, recovery state becomes ready (other gates permitting) | decision record only |
| Head/book/audit-history/failure-set drift | 409 stale-preview, operator must re-preview | none |
| Any digest unknown, already resolved, or not_resolvable; attestation set differs from attestable subset | 422 with per-digest reasons | none |
| Corrupt replay / corrupt audit event | existing corrupt response | none |
| Book mismatch | existing mismatch refusal | none |
| Control or audit lane contention | existing contention response | none |
| Repeat confirm of identical resolved set with no append beyond its own decision | 200 already-resolved (idempotent) | none |

## Invariants

- Confirm performs zero writes on every refusal path.
- Confirm holds the audit lane through exact-byte digest recheck and append. Any audit append, including Halt, invalidates the preview.
- The decision record is the only new audit kind; all pre-existing bytes replay byte-identically (constitution Principle I).
- New decisions use schema v2 with the preview audit digest/length and exact attestable digest set; schema-v1 global-attestation decisions remain replayable.
- `ledger.ok=false` continues to mean "readiness denied", not "corrupt" (`web/services.py:4126-4167`); this contract adds no new meaning to it.
- The work-admission guard (`423 reconciliation-required`, `web/services.py:4246-4275`) is unchanged; it simply stops firing once readiness passes.
