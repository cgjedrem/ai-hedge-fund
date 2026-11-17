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
  "classification": "resolvable | not_resolvable",
  "checks": {
    "replay_verified": true,
    "corrupt_events_zero": true,
    "book_matches_replay": true,
    "chain_continuity_across_failure": true,
    "no_post_effect_fields": true
  },
  "reason": null
}
```

Plus set-level fields: `preview_head`, `preview_book_digest`, `confirm_offered` (true only when every failure is `resolvable`), `set_reason` when not offered.

Error/state distinctions preserved: corrupt replay and corrupt audit events report the existing corrupt state (no failures array, no confirm); halted reports halted; this path never relabels them.

## Confirm (new)

POST confirm with body: `{ "preview_head", "preview_book_digest", "failure_digests": [...], "operator", "attestation": true }`.

Outcomes:

| Condition | Result | Writes |
|---|---|---|
| All digests unresolved + resolvable; head/book unchanged; lanes acquired | 200, decision record appended, recovery state becomes ready (other gates permitting) | decision record only |
| Head/book/failure-set drift | 409 stale-preview, operator must re-preview | none |
| Any digest unknown, already resolved, or not_resolvable | 422 with per-digest reasons | none |
| Corrupt replay / corrupt audit event | existing corrupt response | none |
| Book mismatch | existing mismatch refusal | none |
| Lane contention | existing contention response | none |
| Repeat confirm of identical resolved set | 200 already-resolved (idempotent) | none |

## Invariants

- Confirm performs zero writes on every refusal path.
- The decision record is the only new audit kind; all pre-existing bytes replay byte-identically (constitution Principle I).
- `ledger.ok=false` continues to mean "readiness denied", not "corrupt" (`web/services.py:4126-4167`); this contract adds no new meaning to it.
- The work-admission guard (`423 reconciliation-required`, `web/services.py:4246-4275`) is unchanged; it simply stops firing once readiness passes.
