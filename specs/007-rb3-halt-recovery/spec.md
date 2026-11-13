# Feature Specification: RB-3 Safe Halt → Reconciliation → Resume Completion

**Feature Branch**: `cgjedrem-musical-eureka`

**Created**: 2026-11-12 (revised same day after rebase onto `448056f` / PR #11)

**Status**: Draft

**Input**: User description: "Fix the next issue: safe Halt → reconciliation → Resume for the single-user local paper trading desk (RB-3). Halt stops admission of new executions (not undo already transmitted effects); uncertain/interrupted operations visibly require reconciliation; Resume only after verified head-bound recovery; restart/retry cannot duplicate fills. Preserve original daily/weekly funds."

**Prior art**: This feature completes the RB-3 scope left over after `specs/005-web-engine-migration` (PR8) and `specs/006-paper-writer-safety` (PR #11, merged into main @ `448056f`). Originally drafted as spec 006 against baseline `b6aefe5`; renumbered to 007 and rescoped after re-verification against the new main.

## Background: Verified Current State (post-PR #11, verified 2026-11-12)

Already implemented and tested on current main (NOT restated as work here):

- Halt blocks admission of new executions on all user-facing execution paths, with a per-order fence immediately before order submission; transmitted effects are never undone.
- Orphaned tick intents (crash-after-intent) ARE enumerated in a digest-bound intent recovery preview, fenced for new-identity ticks, and resolvable through an audited intent-resolution path (`hedge_fund/paper/ledger.py:371-432`, `:1025-1104`; `hedge_fund/runtime/reconciliation.py:497-535`).
- Request-identified ticks record durable outcomes: pre-effect interruptions become `tick_aborted` with `no_effects=true` (recognized as safe by the intent query), post-effect failures become `tick_failed` (`hedge_fund/paper/tick.py:430-500`).
- The web desk provides reviewed recovery: failure preview, explicit confirmation, head/book/fill-digest-bound Resume; reconciliation confirmations are replayed before preview; CLI replays confirmations.
- `resume_allowed` already denies unresolved tick intents (`hedge_fund/web/services.py:824-846`); `Ledger.resume()` rejects unfinished Resume effect intents (`hedge_fund/paper/ledger.py:1209-1216`).
- Durable logical-operation deduplication prevents repeated effects for repeated operations.

## Remaining verified gaps (this feature's scope)

1. **Resume gating inconsistency**: general work readiness (`ledger.py:359-369`) checks neither unresolved Resume intents nor outstanding tick intents; web `resume_allowed` checks tick intents but not Resume intents; backend Resume uses the general guard and can diverge from desk permission on orphaned tick intents.
2. **Recovery can be unreachable**: when approval-readiness denial marks `ledger.ok=false`, the desk suppresses the recovery fetch/card (`web/services.py:4082-4089`; `frontend/src/pages/paper.tsx:157-159,690-693`), and unmatched approval-consumption journal entries are unrecoverable through the intent preview (`hedge_fund/paper/test_tick.py:627-655`).
3. **Legacy no-request-ID ticks**: the post-effect Halt failure journaling added by PR #11 covers request-identified ticks; the legacy path (e.g. TUI's `tick()` call without ID) only journals with `attempt_context` (`tick.py:212-216`, `:474-500`), so a post-fill Halt there can lack the reviewable failure record.
4. **Receipt expiry absent (spec005 T140)**: both receipt types carry `recorded_at` but no validity bound; verification checks state rebinding only (`runtime/reconciliation.py:268-307`, `:678-699`).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Recovery is always reachable when reconciliation is required (Priority: P1)

The operator's desk must never hide recovery controls when the fund needs reconciliation. When readiness denial (e.g. unresolved approval consumption) currently marks the ledger snapshot "not ok", the desk must still distinguish "valid but not ready — reconciliation required" from genuinely corrupt replay, and still surface the recovery preview and resolution actions. Approval-consumption journal entries that match no intent must be resolvable through the same reviewed path instead of wedging the fund.

**Why this priority**: A fund that needs reconciliation but shows no recovery UI is a dead-end halt — the worst RB-3 outcome. This is the only gap that can make recovery *unreachable* rather than merely inconsistent.

**Independent Test**: Synthetic fixture with unmatched approval consumption (and/or readiness denial): the desk still fetches and displays the recovery surface with a reconciliation-required reason, and the unmatched entry can be resolved through the reviewed path. Verifiable without US2–US4.

**Acceptance Scenarios**:

1. **Given** a fund whose readiness check denies work due to unresolved state, **When** the operator opens the desk, **Then** the recovery surface is still fetched and shown with the reconciliation-required reason, clearly distinct from a corrupt-replay error.
2. **Given** an approval-consumption journal entry matching no intent, **When** the operator opens the recovery preview, **Then** the unmatched entry is presented and resolvable through the reviewed path.
3. **Given** genuinely corrupt replay (link/hash failure), **When** the desk loads, **Then** it shows the corruption state as today — no regression to corruption visibility.

---

### User Story 2 - One consistent Resume gate (Priority: P2)

Resume permission is evaluated identically everywhere: general work readiness, web `resume_allowed`, and `Ledger.resume()` all consider the same unresolved-state set — recorded failures, outstanding tick intents, and unresolved Resume intents. Backend Resume can never clear a Halt that the desk would forbid, and vice versa.

**Why this priority**: Divergent gates let one surface reopen a fund another surface considers unsafe; convergence removes the ambiguity without changing the underlying recovery mechanics PR #11 delivered.

**Independent Test**: Fixtures with each unresolved-state category; assert all three evaluation points agree (deny until resolved, permit after reviewed recovery). Verifiable without US1/US3/US4.

**Acceptance Scenarios**:

1. **Given** an unresolved Resume intent, **When** work readiness or `resume_allowed` is evaluated, **Then** it denies with a reconciliation-required reason (today only `Ledger.resume()` rejects it).
2. **Given** an orphaned tick intent, **When** backend Resume is attempted, **Then** it is denied until the intent is resolved — matching desk behavior.
3. **Given** all unresolved state reviewed and resolved, **When** Resume completes, **Then** Halt clears exactly once and new executions are admitted.

---

### User Story 3 - Post-fill Halt journaling for legacy ticks (Priority: P2)

A paper tick invoked without a request ID (legacy/TUI path) that is interrupted by Halt after at least one transmitted fill produces the same durable, reviewable `tick_failed` record that request-identified ticks get — bound to the transmitted fill identities. Pre-effect interruptions on this path remain clean aborts.

**Why this priority**: Closes the last execution path where a post-fill interruption could lack a reviewable record; lower than US1/US2 because the legacy path is not the primary desk flow.

**Independent Test**: Synthetic no-request-ID tick halted after a first fill: failure record exists, drives preview/Resume review; zero-fill halt journals a clean abort or nothing per existing no-effect rules. Verifiable independently.

**Acceptance Scenarios**:

1. **Given** a no-request-ID tick halted after ≥1 transmitted fill, **When** the ledger is inspected, **Then** a `tick_failed` record bound to the fill identities exists and appears in recovery.
2. **Given** a no-request-ID tick halted before any effect, **When** the ledger is inspected, **Then** no book-ambiguity review is required (clean abort semantics preserved).

---

### User Story 4 - Recovery receipts expire (Priority: P3)

Recovery receipts (both failure-bound and intent-bound) carry a recorded-clock validity window. Expired receipts, and legacy receipts without expiry fields, never authorize Resume or intent resolution; state rebinding continues to apply (spec005 T140).

**Why this priority**: Receipts are already bound to failure/head/book/fill digests, so stale-receipt risk is limited to quiet periods; additive hardening.

**Independent Test**: Issue a receipt, advance the recorded clock past validity (or present a legacy receipt), attempt Resume → denied with re-review reason; fresh receipt still works.

**Acceptance Scenarios**:

1. **Given** a receipt older than its validity window, **When** Resume/intent-resolution is attempted, **Then** it is denied as expired.
2. **Given** a legacy receipt without expiry fields, **When** presented, **Then** it is denied fail-closed.
3. **Given** a fresh receipt whose bound state changed, **When** presented, **Then** it is denied by the existing rebind check (regression).

---

### Edge Cases

- Multiple funds: unresolved state in one fund never blocks another.
- Zero-effect interruptions (any path): no book-ambiguity review required; safe-abort semantics from PR #11 preserved.
- Operator never reconciles: fund stays halted indefinitely; nothing auto-resolves or auto-expires the reconciliation *requirement* (only receipts expire).
- Daily/weekly/monthly (date-keyed) and minute (timestamped) funds behave identically under all of the above; cadence and session keys unchanged.
- Retried/restarted operations add zero additional fills; completed operations return their recorded outcome (PR #11 dedup preserved).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The desk MUST distinguish "valid replay, not ready — reconciliation required" from corrupt replay, and MUST fetch and display the recovery surface in the former state, including when readiness denial would otherwise mark the snapshot not-ok.
- **FR-002**: Approval-consumption journal entries matching no intent MUST be enumerable and resolvable through the reviewed recovery path.
- **FR-003**: Work readiness, web Resume permission, and `Ledger.resume()` MUST evaluate the same unresolved-state set: recorded failures, outstanding tick intents, and unresolved Resume intents.
- **FR-004**: Backend Resume MUST NOT clear Halt while an orphaned tick intent or unresolved Resume intent exists.
- **FR-005**: No-request-ID ticks interrupted by Halt after ≥1 transmitted effect MUST journal a reviewable `tick_failed` record bound to the transmitted fill identities; zero-effect interruptions MUST NOT require book-ambiguity review.
- **FR-006**: Recovery receipts MUST carry `issued_at`/`valid_until` on the recorded clock; expired receipts and receipts lacking expiry fields MUST be denied (fail-closed); existing state rebinding MUST be preserved.
- **FR-007**: Existing invariants MUST be preserved: Resume intent-before-clear with completion after; retries add zero additional fills; no-effect abort semantics; daily/weekly session keys; Halt stops admission only, never undoes transmitted effects.
- **FR-008**: Receipt expiry MUST NOT expire the reconciliation requirement itself — only the authorization; an expired receipt demands fresh review of current state.
- **FR-009**: TUI and CLI surfaces retain current behavior; reviewed recovery remains a web-desk surface. Wiring reviewed recovery into TUI/CLI is deferred to a follow-up feature. *(User decision 2026-11-12, option A.)*

### Key Entities

- **Tick intent / orphaned intent**: durable pre-effect record; unresolved until outcome. PR #11 added digest-bound enumeration, fencing, and audited resolution. This feature extends the same treatment to unmatched approval-consumption entries and to permission consistency.
- **Resume intent**: durable record of an attempted Resume; unresolved Resume intents join the common unresolved-state set. *(Amended 2026-11-13 after Copilot review finding C3: a reviewed failure counts as resolved only once a uniquely matching `resume_effect_intent` exists — a bare `resume` event without its effect intent is an incomplete transition that remains reviewable, and a fresh head/book-bound review may authorize completing it even after the original receipt expired. Receipt expiry still denies the expired authorization itself.)*
- **Recovery receipt** (failure-bound and intent-bound): reviewed confirmation bound to identity + ledger head + book digest + fill digest; gains `issued_at`/`valid_until`; single-use; expiring; fail-closed for legacy receipts.
- **Recovery surface state**: desk distinguishes corrupt replay / valid-not-ready-reconciliation-required / ready.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: In 100% of synthetic fixtures where reconciliation is required, the desk displays the recovery surface — zero dead-end halts from readiness denial.
- **SC-002**: Across readiness, web permission, and `Ledger.resume()`, 100% of fixture evaluations agree (deny/permit) for every unresolved-state category.
- **SC-003**: In retry/restart scenarios, retries add zero additional fills for one logical operation, and completed operations return their recorded outcome in 100% of cases.
- **SC-004**: 100% of Resume/resolution attempts with expired or legacy receipts are denied; 100% with fresh bound receipts succeed.
- **SC-005**: All pre-existing daily/weekly paper fund and PR #11 writer-safety tests pass unchanged.

## Assumptions

- PR #11's intent recovery machinery (enumeration, fencing, audited resolution) is the foundation; this feature extends it rather than replacing it.
- Receipt validity window is short and bounded (single review-session scale); final value fixed during implementation and recorded in evidence.
- All validation uses synthetic writable test roots; no production roots, broker calls, or paid data.
- Spec005 full acceptance (native control, e2e) and spec006 task-checkbox/evidence bookkeeping remain out of scope except where directly affected by these changes.
