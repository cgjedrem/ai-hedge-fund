# Data Model: Paper Writer Safety

**Date**: 2026-11-10 · Derived from [spec.md](spec.md) Key Entities and the discovery-verified current records.

## Entity 1: Session intent (existing record, new consumer)

A durable ledger event recorded by the tick path **before** session effects. Existing fields include the tick request identity and requested session; outcome events (`tick_failed`, session completion, redo supersession) reference the same identity.

**New derived view** — `UnresolvedIntent`:

| Field | Source | Notes |
|---|---|---|
| `request_id` | intent event | identity the fence reports back to the operator |
| `session` | intent event | target session of the interrupted attempt |
| `recorded_at` | intent event | ordering/diagnostics |
| `metadata_complete` | derived | false when surrounding records are torn → fence still fails closed |

**Amended lifecycle (post-QA)**: resolution events now also include `tick_aborted` (pre-effect exit, `no_effects=True`) and `tick_intent_resolved` (explicit operator reconciliation verdict, receipt bound to intent request identity + digests, requires local book to match verified ledger state). Corrupt/torn intents are fail-closed and resolvable only via the explicit verdict. An incomplete (legacy-shaped) intent with a matching outcome counts as resolved. `BookMismatch` remains fail-and-halt even pre-effect.

**Lifecycle / state transitions (original)**:

```text
(none) --tick admission--> RECORDED(intent)
RECORDED --completion event--> RESOLVED
RECORDED --tick_failed event--> RESOLVED
RECORDED --redo supersession--> RESOLVED
RECORDED --(none of the above)--> UNRESOLVED  ← blocks new-identity session requests
RECORDED(torn metadata) ------> UNRESOLVED (fail closed)
```

**Validation rules**:
- An intent with any matching outcome event for the same request identity is resolved; order of appearance does not matter (crash between intent and outcome is the norm being fenced).
- Multiple unresolved intents: fence reports the unresolved state (oldest first for diagnostics); it never auto-resolves or picks a winner.
- The fence is evaluated only after same-request-identity replay lookup, so a retry of the interrupting request reaches the existing replay/reconciliation path (FR-003).

## Entity 2: Logical-operation identity (new field on existing record)

Added to the durable operation record in `runtime/operations.py` as an **optional** field; pre-feature records lack it and never match.

| Field | Type | Derivation |
|---|---|---|
| `logical_key` | string digest, optional | canonical digest over `(fund identity, action type, target session or due set, reviewed payload digest)` — inputs already bound at acceptance |

**Validation rules**:
- Computed once at acceptance from already-reviewed inputs; never recomputed from mutable state.
- Canonical serialization of inputs (sorted keys, explicit separators) so all entry points derive identical keys for the same logical action.
- Redo (`tick --again`) carries a distinct action type and is never an accidental-duplicate match.

**State transitions (dedup relevance)**:

```text
operation status:  pending/accepted/running/interrupted  → BLOCKS same logical_key (refuse: duplicate-logical-operation)
                   terminal-failed                        → FREE (deliberate resubmission admitted as new attempt)
                   terminal-succeeded                     → FREE (downstream head/session conflict governs, as today)
```

## Entity 3: Operation record (existing, unchanged except optional field)

Existing identity layers are preserved: preview ID, caller request ID (replay key), operation ID (random UUID), index + sidecar projections. This feature adds no new identity layer; it reuses the operation record as the carrier for `logical_key` and the ledger event stream as the carrier for intents.

## Relationships

- `UnresolvedIntent` is a read-model over ledger events; the dedup key is a write-time field on operation records. The two mechanisms are independent: the fence protects sessions, dedup protects all mutating paper actions (including non-session actions like approve/halt where a logical key is derivable).
