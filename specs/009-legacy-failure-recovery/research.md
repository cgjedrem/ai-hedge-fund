# Phase 0 Research: Legacy Failure Recovery

**Date**: 2026-11-17 | **Spec**: [spec.md](spec.md)

All findings below trace to the discovery-phase read-only code analysis at baseline `e6f04d2` (== origin/main). No NEEDS CLARIFICATION items remain; each candidate was resolved by code evidence or an explicit conservative default.

## Decision 1: Resolution mechanism — one audited decision record per failure set

- **Decision**: A single durable, append-only **reconciliation decision record** binds the ordered set of resolved failure digests + previewed ledger head + broker-book digest + operator identity + recorded time. Replay treats exactly those failure digests as resolved.
- **Rationale**: The existing single-failure reviewed-Resume path cannot process multi-failure state (`hedge_fund/runtime/reconciliation.py:466-470` selects the last unresolved failure; >1 yields `multiple-unreconciled-failures`, `recoverable=false`; `hedge_fund/paper/ledger.py:1432-1441` Resume independently rejects multiple unresolved failures). Looping single receipts cannot start because the gate blocks the first one. A set-binding record is one atomic audit line, trivially idempotent (content-addressed), and leaves per-failure receipt semantics untouched.
- **Alternatives considered**: (a) Sequential single-failure receipts — rejected: dead-ended by the multi-failure gate and by Resume's rejection. (b) Auto-resolution on preview when evidence looks clean — rejected: violates the operator-mediated requirement and the never-ignore directive. (c) Rewriting/annotating historical events — rejected: violates constitution Principle I (byte-identical replay).

## Decision 2: Evidence classification standard (the core safety rule)

- **Decision**: A failure is classified **resolvable** only when ALL hold at preview time:
  1. Full replay verifies; zero corrupt audit events; broker-book digest matches replay (`web/services.py:4126-4167` already computes these).
  2. The failure's position in the event stream is an ancestor of the current verified head, and at least one later session for the fund verified in the same replay (chain continuity across the failure).
  3. The event carries no fields indicating post-effect state (no transmitted fills, no post-effect metadata; cf. `tick.py:525-543` fields when present).
  4. The operator records an explicit attestation in the decision, accepting the residual uncertainty the durable record cannot exclude.
  Otherwise: **not resolvable**, with the specific failing check reported.
- **Rationale**: Discovery established that legacy error text alone cannot prove no effects: a news `DataClientError` proves the ledger append did not complete *at that point* but not that no broker order or approval consumption preceded it (`pipeline/session.py:197-240` executes orders before assessment; `tick.py:810-855,983-1008` approval consumption can cross the effect boundary before `advance()`; `ledger.py:586-605` "session already recorded" is raised after `advance()`). Checks 1–3 are the strongest durable-evidence screen the existing records support; check 4 makes the unavoidable residual an explicit, audited operator decision rather than a silent system assumption.
- **Alternatives considered**: (a) Exception-type allowlist (DataClientError = no effects) — rejected explicitly by the user directive and by the discovery trace. (b) Require positive pre-effect metadata — rejected as sole rule: legacy events predate effect classification (`9c1f5b8`, merged `b6aefe5` 2026-11-09), so nothing would ever be resolvable and the feature would be dead on arrival. (c) Latest-mutable-bytes-as-proof — rejected per user directive; the verified hash chain, not mutable bytes, is the evidence.

## Decision 3: Preview/confirm binding and staleness

- **Decision**: Preview computes and returns the classification set plus the ledger head and book digest it was computed against; confirm must present the same head + digest + failure set and re-verify before writing. Any drift → stale refusal, zero writes (FR-006).
- **Rationale**: Receipts already bind failure digest + head + book + operator (`reconciliation.py:109-185,371-405`); the decision record extends the same binding discipline to the set case. Preview-then-confirm against a moved head is the classic TOCTOU hole.

## Decision 4: Idempotency and crash safety

- **Decision**: The decision record is written through the existing anchored audit append boundary (`ledger.py:2200-2254`, `runtime/root.py:1984-2027`) with the decision's identity derived from its content (failure-set digest + head + book + recorded time). Replay dedups identical decisions; a second confirm over an already-resolved set is an explicit already-resolved refusal, not a second effect.
- **Rationale**: Matches existing receipt/replay dedup philosophy (`reconciliation.py:365-405` whole-event digest identity collapses duplicates) and the anchored-append discipline.

## Decision 5: Surface and lanes

- **Decision**: Web-surface only (consistent with spec007's reviewed-recovery contract): extend `web/services.py` preview computation and add a confirm route beside the existing recovery routes (`web/app.py:315-329,421-427`); confirm takes the fund lock + control/audit lanes exactly as web Resume does (`web/services.py:3861-3869,4046-4076`). Frontend evidence display in `frontend/src/pages/paper.tsx` recovery panel. TUI unchanged (documented headless exception per constitution Principle V).
- **Rationale**: Reviewed recovery is already web-only; duplicating a TUI path widens scope and review surface for zero operator demand.

## Decision 6: Scope exclusions enforced by design

- No halt clearing, no tick-intent reconciliation, no approval-journal mutation, no fee/cash/position/session rewrite (FR-010), no change to single-failure receipts, legacy receipt replay, or resume semantics (FR-011).
- **Rationale**: Each is governed by spec006/007 machinery with its own gates; overlapping them risks superseding recorded decisions (routes to user per coordinator policy).

## Resolved clarification candidates

| Candidate question | Resolution |
|---|---|
| Can unkeyed failures ever be resolved? | Yes — receipt matching already treats missing request ID as matchable (`failed_request_id` optional; `reconciliation.py:113-118,142-185`); the blocker is multiplic​ity, not keylessness. |
| Is `ledger.ok=false` evidence of corruption? | No — readiness denial sets `reconciliation_required` + `ledger.ok=false` after successful replay (`web/services.py:4126-4167`); corrupt replay is a distinct state. |
| Do historical resume events without reconciliation IDs resolve anything? | No (`reconciliation.py:388-405`) — they remain inert history; preserved, not upgraded. |
| Production repair during development? | Out of scope — synthetic fixtures only; attended production reconciliation is a separate operator approval (SC-005). |
