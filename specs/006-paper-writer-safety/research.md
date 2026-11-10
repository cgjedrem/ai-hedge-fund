# Phase 0 Research: Paper Writer Safety

**Date**: 2026-11-10 · **Baseline**: `b6aefe5` (post PR #8) · **Method**: code-explorer discovery report on current code + coordinator verification of cited lines.

All Technical Context items were known; no NEEDS CLARIFICATION remained. The design choices below resolve the open implementation questions.

## Decision 1: Fence source of truth — ledger event stream, not a new marker file

- **Decision**: The unresolved-intent fence derives state from the existing durable ledger event stream: a `tick_intent` event is unresolved when no outcome event (`tick_failed` / recorded completion / redo supersession) with the same request identity exists.
- **Rationale**: The intent event is already written before effects (`paper/tick.py`), already survives crashes, and is already the record reconciliation consults. A parallel marker file would add a second writer, a new WRITER_MAP surface, and a new torn-write window — the exact failure class this feature removes.
- **Alternatives considered**: (a) dedicated `pending-intent.json` marker (rejected: extra write, double-source drift); (b) in-memory tracking (rejected: violates FR-008 durability).

## Decision 2: Fence placement — shared admission guard in `paper/ledger.py`, invoked at every tick entry

- **Decision**: Add an unresolved-intent query on `Ledger` plus a guard invoked from the tick admission path (`paper/tick.py`) so CLI, web worker, and owned-runner child all pass through it (all three already converge on the same tick machinery — verified in discovery §1).
- **Rationale**: One enforcement point covers all entry points (FR-004) because entry-point diversity lives above the shared tick layer. Same-identity replay is resolved earlier by request-ID lookup (`paper/ledger.py:760-842`), so the fence only sees genuinely new identities and cannot break replay (FR-003).
- **Alternatives considered**: (a) per-entry-point guards in `web/services.py`, `run.py`, `owned_runner_child.py` (rejected: three copies, drift risk, and discovery showed convergence); (b) extending `require_ready_for_work` in place (accepted in substance — the fence composes with it; naming decided at implementation).

## Decision 3: Fail closed on torn intent metadata

- **Decision**: If an intent event exists but surrounding metadata is unreadable or inconsistent, the fence treats the intent as unresolved and directs to reconciliation.
- **Rationale**: Spec edge case; a false refusal is operator-recoverable, a false pass can double-fill the book. Matches the existing reconciliation-first posture (`runtime/reconciliation.py`).

## Decision 4: Logical-operation identity — deterministic digest stored as optional field

- **Decision**: `logical_key = digest(fund identity, action type, target session/due set, reviewed payload digest)` computed at acceptance in `runtime/operations.py`, persisted as a new **optional** field on the durable operation record. Records written before this feature simply lack the field and are never dedup matches.
- **Rationale**: The reviewed payload digest already exists at acceptance (preview digest binds action, subject, head, due set, payload). Reusing its inputs keeps the key stable across entry points for the same logical action while distinguishing different sessions/actions. Optional-field additivity preserves Constitution I byte-compatibility.
- **Alternatives considered**: (a) recompute-and-scan without persisting (rejected: old operations carry no derivation inputs; fragile); (b) deterministic operation IDs replacing UUIDs (rejected: operation ID is referenced by sidecars/journals/worker fencing — too invasive for this slice).

## Decision 5: Dedup semantics — match non-terminal only, refuse-and-link

- **Decision**: At acceptance, if an operation with the same `logical_key` exists in a non-terminal state (pending/accepted/running/interrupted-awaiting-recovery), the new request is refused as `duplicate-logical-operation` and the refusal references the existing operation ID. Terminal-failed or terminal-succeeded operations do not block: a deliberate resubmission after failure is a new attempt (FR-007); a resubmission after success conflicts downstream on head/session as today.
- **Rationale**: "At most once in flight" is the guarantee the operator needs; permanent dedup would forbid legitimate retries (FR-007). Interrupted operations still block because their effects are unresolved — consistent with the P1 fence philosophy.
- **Alternatives considered**: (a) silently return the existing operation as if accepted (rejected: confuses request-ID replay semantics; refusal-with-reference is explicit); (b) include terminal-succeeded in blocking (rejected: would wedge funds after one successful session).

## Evidence posture

Historical Spec005 claims were discriminated during discovery: "no durable rewind intent" (T021-era) is **stale** — redo now writes durable pending state (`paper/ledger.py:219-246`). The gaps this feature addresses were classified **MISSING FUNCTIONALITY** at current HEAD, not missing evidence. All validation is synthetic-fixture only; full-suite completion evidence follows Constitution III.
