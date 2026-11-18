# Phase 0 Research: Legacy Failure Recovery

**Date**: 2026-11-17 | **Spec**: [spec.md](spec.md)

All findings below trace to the discovery-phase read-only code analysis at baseline `e6f04d2` (== origin/main). No NEEDS CLARIFICATION items remain; each candidate was resolved by code evidence or an explicit conservative default.

## Decision 1: Resolution mechanism — one audited decision record per failure set

- **Decision**: A single durable, append-only **reconciliation decision record** binds the ordered set of resolved failure digests + previewed ledger head + broker-book digest + operator identity + recorded time. Replay treats exactly those failure digests as resolved.
- **Rationale**: The existing single-failure reviewed-Resume path cannot process multi-failure state (`hedge_fund/runtime/reconciliation.py:466-470` selects the last unresolved failure; >1 yields `multiple-unreconciled-failures`, `recoverable=false`; `hedge_fund/paper/ledger.py:1432-1441` Resume independently rejects multiple unresolved failures). Looping single receipts cannot start because the gate blocks the first one. A set-binding record is one atomic audit line, trivially idempotent (content-addressed), and leaves per-failure receipt semantics untouched.
- **Alternatives considered**: (a) Sequential single-failure receipts — rejected: dead-ended by the multi-failure gate and by Resume's rejection. (b) Auto-resolution on preview when evidence looks clean — rejected: violates the operator-mediated requirement and the never-ignore directive. (c) Rewriting/annotating historical events — rejected: violates constitution Principle I (byte-identical replay).

## Decision 2: Evidence classification standard (the core safety rule)

- **Decision**: Use a three-way per-failure classification:
  - **`verified`**: every structural check passes; replay at `expected_head` shows no pending decision; no post-effect fields or post-advance failure shape contradict no-effect proof. No operator attestation required.
  - **`attestable`**: every structural check passes, but positive no-effect proof is unavailable. Examples: a pending decision existed at `expected_head`, effect metadata exists, or the failure has a session-already-recorded append shape. Confirm requires explicit attestation for this digest.
  - **`not_resolvable`**: any structural check fails (full replay, corruption, book match, or stream continuity). A set containing one is refused with zero writes.
- **Verified code facts**: Session records rebuild `FundState` through replay (`paper/ledger.py:4-5`). Orders execute only when `state.pending is not None`; assessment follows execution (`pipeline/session.py:198-206`). Therefore a verified expected head with no pending decision proves no orders could execute. Conversely, `LedgerError` for "session already recorded" occurs at append after `advance()` returned (`paper/ledger.py:599`), so that failure shape is attestable, never verified. Legacy `tick_failed` events persist session/error/expected-head and optional operation context, not in-memory `effect_state` (`paper/tick.py:983-1008`).
- **Continuity rule**: Anchor the failure at its index in the verified audit-event stream. Require a later successful `tick` event after that index to match a verified successor record in the expected-head chain. Session labels alone do not prove ordering. Preserve complete naive session keys: minute `YYYY-MM-DDTHH:MM:SS`, other cadences `YYYY-MM-DD` (`pipeline/session.py:154-156`).
- **Rationale**: Error text alone cannot prove no effects: execution may precede assessment (`pipeline/session.py:198-240`), while a session-already-recorded append error is post-advance. The no-pending discriminator provides positive proof only at the expected head; legacy post-advance uncertainty requires an explicit per-failure operator decision.
- **Alternatives considered**: (a) Exception-type allowlist (DataClientError = no effects) — rejected explicitly by the user directive and by the discovery trace. (b) Require positive pre-effect metadata — rejected as sole rule: legacy events predate effect classification (`9c1f5b8`, merged `b6aefe5` 2026-11-09), so nothing would ever be resolvable and the feature would be dead on arrival. (c) Latest-mutable-bytes-as-proof — rejected per user directive; the verified hash chain, not mutable bytes, is the evidence.

## Decision 3: Preview/confirm binding and staleness

- **Decision**: Preview returns SHA-256 of exact `events.jsonl` bytes alongside the head, book digest, and classifications. Confirm presents that digest and rechecks it while holding control and audit lanes through the append. Any audit append, including Halt, invalidates the preview; drift → 409 stale-preview, zero writes. Decision schema v2 stores the preview digest and byte length.
- **Rationale**: Control lane alone does not exclude Halt audit writes. The audit lane closes the preview-confirm-append race; an exact byte digest covers any appended audit event, not only session or failure events.

## Decision 4: Idempotency and crash safety

- **Decision**: The decision record is written through the existing anchored audit append boundary (`ledger.py:2200-2254`, `runtime/root.py:1984-2027`) with identity derived from the failure set, head, book, pre-append audit digest/length, operator, attestations, and recorded time. Replay keeps schema-v1 decisions valid and applies schema-v2 records. An identical retry is already-resolved only when the matching decision is the sole append since its bound preview revision.
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
