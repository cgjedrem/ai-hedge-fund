# Feature Specification: RB-3 Safe Halt → Reconciliation → Resume Completion

**Feature Branch**: `cgjedrem-musical-eureka`

**Created**: 2026-11-12

**Status**: Draft

**Input**: User description: "Fix the next issue: safe Halt → reconciliation → Resume for the single-user local paper trading desk (RB-3). Halt stops admission of new executions (not undo already transmitted effects); uncertain/interrupted operations visibly require reconciliation; Resume only after verified head-bound recovery; restart/retry cannot duplicate fills. Preserve original daily/weekly funds."

**Prior art**: This feature completes the partially delivered RB-3 scope from `specs/005-web-engine-migration` (PR8, commit `b6aefe5`). Discovery on 2026-11-12 verified which RB-3 mechanics already exist and identified the remaining gaps this feature closes. This spec supersedes stale backlog claims in `specs/005-web-engine-migration/tasks.md` (e.g. the RB-3 row stating `Ledger.resume()` always raises and web Resume always returns 423 — both are now implemented).

## Background: Verified Current State

Already implemented and tested in the baseline (not restated as work here):

- Halt blocks admission of new executions on all user-facing execution paths (CLI, web, owned runner, canonical tick), with a per-order fence immediately before order submission.
- The web desk provides reviewed recovery: reconciliation preview (failed-operation identity, ledger head, broker-book digest, fill digests), explicit operator confirmation, and head-bound Resume.
- Resume records a durable effect intent before clearing Halt and records completion afterward; a same-ID completed tick returns its recorded result and a same-ID failed or intent-only tick denies repetition.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Every interrupted operation visibly requires reconciliation (Priority: P1)

The operator runs a local paper trading desk. A paper tick is interrupted in an ambiguous window — after an effect intent was recorded but before its outcome was journaled (process kill, crash, power loss), or the fund is halted mid-execution after at least one fill was already transmitted. When the operator next opens the desk, the interrupted operation is presented as requiring reconciliation, with the same failure identity, ledger head, book digest and fill digest evidence as a recorded failure, and the fund refuses new work until it is reconciled.

**Why this priority**: An uncertain operation the operator cannot see is the core RB-3 safety hole. Today a crash that leaves only an effect intent produces no failure event, so the recovery preview is empty and new work is not globally blocked; a halt during execution likewise records no failure event. Silent uncertainty defeats the entire Halt → reconciliation → Resume contract.

**Independent Test**: Can be fully tested with synthetic fixtures by (a) killing a tick after intent recording with no completion, and (b) halting a fund mid-execution after a transmitted fill, then opening the recovery preview and attempting new work. Delivers value alone: every ambiguous interruption becomes operator-visible and blocks admission until reconciled.

**Acceptance Scenarios**:

1. **Given** a fund with a recorded tick intent and no matching outcome (simulated crash), **When** the operator requests the reconciliation preview or any new execution, **Then** the outstanding intent is surfaced as requiring reconciliation and new work is denied until it is resolved.
2. **Given** a fund halted mid-execution after at least one transmitted fill, **When** the operator opens the desk, **Then** the interrupted execution appears in the reconciliation-required view with failure identity, ledger head, broker-book digest and fill digest.
3. **Given** an outstanding unresolved intent, **When** the operator attempts any ledger-mutating control or execution action, **Then** the action is refused with a reconciliation-required reason, regardless of which request ID is supplied.

---

### User Story 2 - Resume gating accounts for all unresolved state (Priority: P2)

The operator reviews a reconciliation preview and confirms recovery. The decision of whether Resume is permitted considers every form of unresolved state: recorded failures, outstanding effect intents, and an incomplete prior Resume intent. Resume clears Halt only after verified head-bound recovery, and retry of the same or a new request can never duplicate fills.

**Why this priority**: Resume is the moment safety is enforced; if readiness checks ignore an unresolved intent, Resume can reopen a fund whose last operation is still ambiguous.

**Independent Test**: Can be fully tested with synthetic fixtures by constructing ledgers with each unresolved state and asserting Resume is denied until reviewed confirmation bound to the current head/book/fill digest succeeds; and that retried requests return the recorded outcome instead of re-executing.

**Acceptance Scenarios**:

1. **Given** a fund with an unresolved Resume intent from an interrupted prior Resume, **When** work readiness or Resume permission is evaluated, **Then** the unresolved intent blocks admission and is visible in the recovery decision.
2. **Given** reviewed confirmation bound to the current failure, head, book and fill digest, **When** the operator resumes, **Then** Halt clears and subsequent new executions are admitted.
3. **Given** any retried or restarted request for an already-completed or already-intended operation, **When** it is submitted, **Then** the recorded outcome is returned or the retry is denied — no fill is duplicated.

---

### User Story 3 - Recovery confirmations expire with state change (Priority: P3)

A reconciliation confirmation (receipt) is valid only for the exact state it reviewed. If the ledger head, broker book, or failure identity changes after the receipt was issued — or the receipt is older than a bounded validity window — the receipt no longer authorizes Resume and the operator must re-review. This completes unchecked task T140 from the prior spec.

**Why this priority**: A stale receipt reused after new activity would resume against unreviewed state. Lower priority because receipts are already bound to failure/head/book/fill digests; expiry closes the remaining time-and-change window.

**Independent Test**: Can be fully tested by issuing a receipt, mutating the ledger (or advancing the recorded clock past the validity window), and asserting Resume with that receipt is denied and demands fresh review.

**Acceptance Scenarios**:

1. **Given** a valid reviewed receipt, **When** any ledger state it binds to changes before Resume, **Then** Resume with that receipt is denied with a re-review reason.
2. **Given** a receipt older than its validity window, **When** Resume is attempted, **Then** it is denied as expired.

---

### Edge Cases

- Multiple outstanding intents across different funds: each fund's readiness is evaluated independently; one fund's unresolved state never blocks another fund.
- Intent recorded for a request ID, then a *different* request ID is submitted: admission is still denied until the outstanding intent is reconciled (no request-ID bypass).
- A halt occurs with zero transmitted effects (clean interruption): reconciliation confirms nothing was transmitted and Resume proceeds after replay without book comparison ambiguity.
- Daily/weekly/monthly funds (date-keyed sessions) and minute funds (timestamped bars) behave identically under Halt/reconciliation/Resume; cadence handling is unchanged.
- Operator never reconciles: the fund stays halted indefinitely; nothing auto-resolves or auto-expires the requirement.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST treat an outstanding execution effect intent with no recorded outcome as a reconciliation-required condition, equal in standing to a recorded execution failure.
- **FR-002**: The reconciliation preview MUST enumerate outstanding intents (not only recorded failures), presenting operation identity, ledger head, broker-book digest and fill digest evidence for each.
- **FR-003**: Work-readiness evaluation MUST deny new ledger-mutating work while any outstanding intent or unresolved Resume intent exists for the fund, regardless of the incoming request ID.
- **FR-004**: An execution interrupted by Halt after at least one transmitted effect MUST produce a reconciliation-required record bound to the transmitted effects; an interruption with zero transmitted effects MUST NOT require book-ambiguity review.
- **FR-005**: Resume permission evaluation MUST consider outstanding execution intents and unresolved Resume intents in addition to Halt state and recorded failures.
- **FR-006**: Recovery receipts MUST expire: a receipt MUST NOT authorize Resume after any bound state (failure identity, ledger head, broker book, fill digest) changes, or after a bounded validity window has elapsed.
- **FR-007**: Resume after verified recovery MUST continue to record its effect intent before clearing Halt and completion afterward (existing invariant, preserved).
- **FR-008**: Restart or retry of an interrupted operation MUST return the recorded outcome or be denied; it MUST NEVER duplicate a fill (existing invariant, extended to intent-only interruptions).
- **FR-009**: Daily, weekly and monthly funds (date-keyed sessions) MUST behave identically to today under all of the above; no cadence or session-key change is permitted.
- **FR-010**: Halt MUST continue to stop only admission of new executions; already-transmitted effects are never undone.
- **FR-011**: TUI and CLI surfaces MUST retain their current behavior (CLI Resume denied; TUI Halt/Resume under existing write-admission rules); reviewed recovery is delivered through the core ledger/runtime semantics and the existing web desk surface. Wiring reviewed recovery into TUI/CLI is explicitly deferred to a follow-up feature. *(Clarified 2026-11-12: user selected option A — core + web only.)*

### Key Entities

- **Effect intent**: Durable record written before an operation's effects are attempted; unresolved until its outcome is recorded. Attributes: operation identity (request ID), fund, operation kind, recorded clock time.
- **Reconciliation preview**: Operator-facing summary of everything requiring review for a fund: recorded failures, outstanding intents, ledger head, broker-book digest, fill digests.
- **Recovery receipt**: Operator's reviewed confirmation bound to a specific failure/intent identity, ledger head, book digest and fill digest; single-use and expiring.
- **Resume intent**: Durable record that Resume was attempted; blocks further control writes until completion is recorded.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of simulated ambiguous interruptions (crash-after-intent, halt-mid-execution) appear in the reconciliation-required view; zero silent uncertain operations.
- **SC-002**: 100% of admission attempts made while any unresolved intent exists are denied with a reconciliation-required reason, across all execution entry points.
- **SC-003**: In retry/restart scenarios, the number of fills recorded for one logical operation is always exactly one — zero duplicates across the test matrix.
- **SC-004**: 100% of Resume attempts using a receipt whose bound state changed or whose validity window elapsed are denied.
- **SC-005**: All pre-existing daily/weekly paper fund tests pass unchanged, demonstrating no regression to original funds.

## Assumptions

- The single operator uses the web desk for reviewed recovery (confirmed 2026-11-12); core semantics live in the ledger/runtime layer and are surface-agnostic.
- Receipt validity window has a reasonable bounded default (see plan); receipts are already bound to state digests, so expiry is additive.
- Reconciliation evidence uses the recorded clock and existing hash-chained replay; no new external services, brokers, or paid data are involved.
- All validation uses synthetic fixtures (synthetic writable test roots); no production roots, live funds, or broker requests are touched.
- Spec005's unchecked RB-3 tasks (T063–T073 partial, T140) are completed by this feature only insofar as the gaps above; full spec005 acceptance (native control, e2e) remains out of scope.
