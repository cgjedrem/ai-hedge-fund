# Contract: Shared Refusal Reasons (CLI / Web / Runner)

**Date**: 2026-11-10 · Both new refusals are surfaced through one shared reason vocabulary so all entry points agree (Constitution V). No new endpoints; existing error channels carry these reasons.

## Reason: `unresolved-tick-intent`

Raised when FR-001's fence refuses a new-identity session request.

| Field | Presence | Meaning |
|---|---|---|
| `reason` | always | literal `unresolved-tick-intent` |
| `fund` | always | fund identity whose ledger holds the intent |
| `intent_request_id` | always | request identity of the unresolved intent |
| `intent_session` | always | target session of the interrupted attempt |
| `recovery` | always | pointer to the existing reconciliation path (the CLI/web wording differs; the reason code and fields do not) |

- CLI: non-zero exit, reason + fields on stderr; no partial session effects.
- Web: existing operation-refusal error shape with this reason code; no worker is dispatched.
- Runner child: session skipped as blocked, durable runner state records the refusal reason; no retry loop escalation (retrying would re-hit the fence).

## Reason: `duplicate-logical-operation`

Raised when FR-006 refuses a request whose `logical_key` matches a non-terminal operation.

| Field | Presence | Meaning |
|---|---|---|
| `reason` | always | literal `duplicate-logical-operation` |
| `existing_operation_id` | always | the operation that owns the in-flight logical action |
| `logical_key` | always | the derived key that matched |

- CLI/web: same surfacing split as above. The existing operation's status/result remains queryable by its own identity.
- Same-request-ID replay and changed-payload conflict behavior (`operations.py:442-516`) are evaluated first and are unchanged.

## Stability

Reason codes are additive. Downstream surfaces must match on the code, not message text; message wording is free to improve without a contract change.
