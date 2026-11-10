# Feature Specification: Paper Writer Safety — Intent Fencing and Operation Deduplication

**Feature Branch**: `cgjedrem-didactic-meme`

**Created**: 2026-11-10

**Status**: Draft

**Input**: User description: "Writer fencing and duplicate-operation/idempotency safety for a single-user local paper-trading application. Scope is the two paper funds watchtower and watchtower-weekly, with web/CLI/headless-runner overlap despite one human. Bounded feature-by-feature progress."

## Context and Scope

A single operator drives one local paper-trading installation through three entry points that can overlap in time: the web desk, the command line, and the headless scheduled runner. Discovery (2026-11-10, baseline `b6aefe5`) established that cooperating entry points already share per-fund execution lanes and that retrying the *same* request identity is replay-safe. Two concrete gaps remain **missing functionality**:

1. A process that dies after declaring intent to run a trading session, but before recording failure or completion, leaves an unresolved intent that later session requests with a *new* identity never check. The operator can unknowingly run a second session on top of an unresolved one.
2. The same logical action (same fund, same action type, same target session) submitted twice with independently generated request identities is not recognized as a duplicate at acceptance; only incidental lane, head, or session-ordering conflicts catch some cases.

**In scope**: closing those two gaps for all admitted paper funds, validated exclusively on owned synthetic fixtures.

**Out of scope**: Saxo/brokerage integration, secret delivery, TUI retirement, Docker platform work, enterprise/multi-user isolation, and OS-enforced exclusion of unaware or out-of-band programs (cooperative-participant boundary remains). The protected production fund identities `watchtower` and `watchtower-weekly` remain blocked exactly as today; this feature does not unblock them and never operates on real fund roots.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Crashed session blocks silent re-run (Priority: P1)

The operator's machine loses power (or the process is killed) in the middle of a trading session for a paper fund, after the session's intent was recorded but before any outcome was. Later — from any entry point — the operator asks for another session on that fund. The system refuses to start the new session, tells the operator an earlier session intent is unresolved, and directs them to the existing reconciliation path. Once reconciliation resolves the earlier intent (recorded failure, verified completion, or operator-approved resolution), new sessions proceed normally.

**Why this priority**: A silent duplicate session can double-fill the paper broker book and corrupt the hash-chained ledger the operator relies on for decisions. This is the only gap where a crash plus an innocent retry produces an *undetected* wrong state.

**Independent Test**: Using a synthetic fund, simulate a crash after intent recording (no outcome event), then request a new session with a fresh request identity; verify refusal with a clear reason, verify reconciliation unblocks, and verify normal sessions are unaffected when no intent is unresolved.

**Acceptance Scenarios**:

1. **Given** a synthetic fund with an unresolved session intent (no failure or completion recorded), **When** any entry point requests a new session for that fund under a new request identity, **Then** the request is refused with a reason identifying the unresolved intent and no session effects occur.
2. **Given** a synthetic fund with an unresolved session intent, **When** the operator completes the existing reconciliation path for that intent, **Then** subsequent new session requests are admitted normally.
3. **Given** a synthetic fund with no unresolved intent, **When** a new session is requested, **Then** admission behaves exactly as before this feature (no new friction).
4. **Given** an unresolved session intent exists, **When** the operator retries with the *same* request identity as the interrupted request, **Then** the existing replay/reconciliation behavior for that identity is preserved (the fence does not break same-identity retry).

---

### User Story 2 - Double-submitted action is recognized as one operation (Priority: P2)

The operator triggers the same logical action twice in quick succession from different entry points (or a UI retry that regenerates its request identity) — for example two "run today's session" requests for the same fund and session. The system recognizes the second submission as the same logical operation and either returns the first operation's outcome or refuses it as a duplicate with a clear reason. It never executes the logical action twice.

**Why this priority**: Double submissions are common in single-user multi-surface workflows (double-click plus CLI retry). Today they are caught only incidentally; making the guarantee explicit removes dependence on timing.

**Independent Test**: Using a synthetic fund, submit the same logical operation (same fund, action type, target session, and payload) under two independently generated request identities; verify exactly one execution occurs and the second submission is deterministically linked to or rejected against the first.

**Acceptance Scenarios**:

1. **Given** an accepted or in-flight operation for a logical action on a synthetic fund, **When** a second request for the same logical action arrives under a different request identity, **Then** the second request is deduplicated against the first (returns the first operation's status/outcome or a clear duplicate refusal) and no second execution occurs.
2. **Given** two requests for the same fund but genuinely different logical actions (different action type or different target session), **When** both are submitted, **Then** each is treated as an independent operation under the existing lane rules.
3. **Given** a prior logical operation reached a terminal failed state, **When** the operator deliberately resubmits the same logical action, **Then** the resubmission is admitted as a new attempt (deduplication never permanently blocks retry after a known failure).

---

### Edge Cases

- Multiple distinct unresolved intents from repeated crashes: the fence reports the unresolved state and requires reconciliation; it must not pick winners or auto-resolve.
- An unresolved intent whose records are partially torn (intent event present, surrounding metadata damaged): the system fails closed toward reconciliation, never toward silently proceeding.
- Duplicate detection must survive process restart: recognition is based on durable records, not in-memory maps.
- A duplicate submission arriving while the first operation is still queued (not yet executing) deduplicates without violating existing lane exclusion.
- Deliberate redo (`tick --again`) remains a distinct, explicitly authorized path and is not misclassified as an accidental duplicate.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Before admitting any new trading-session request for a fund that was not already resolved by same-request-identity replay, the system MUST check durable records for any unresolved session intent on that fund and MUST refuse the request when one exists, whatever new identity the request carries.
- **FR-002**: The refusal in FR-001 MUST surface a reason that identifies the unresolved intent and directs the operator to the existing reconciliation path.
- **FR-003**: The unresolved-intent fence MUST NOT alter the existing same-request-identity replay and reconciliation behavior.
- **FR-004**: The unresolved-intent fence MUST apply uniformly across all supported entry points (web desk, command line, headless runner).
- **FR-005**: The system MUST derive a stable logical-operation identity from the fund, action type, target session, and reviewed payload of each mutating paper request, and MUST persist that identity durably with the operation record.
- **FR-006**: When a newly submitted request's logical-operation identity matches an existing non-terminal operation, the system MUST NOT execute the action a second time; it MUST either return the existing operation's status/outcome or refuse with an explicit duplicate reason.
- **FR-007**: Logical-operation deduplication MUST treat a prior terminal failure as closed, admitting a deliberate resubmission as a new attempt.
- **FR-008**: Both mechanisms MUST be based on durable state so they survive process restart and machine reboot.
- **FR-009**: All validation MUST use owned synthetic fund fixtures; the feature MUST NOT create, modify, or access any real or protected fund root.
- **FR-010**: Existing ledger invariants (hash chaining, no history rewrite outside the explicit redo path, replayability of old records) MUST be preserved unchanged.

### Key Entities

- **Session intent**: The durable declaration, recorded before a trading session executes, that a session attempt has begun; unresolved until a failure or completion outcome is recorded.
- **Logical-operation identity**: A deterministic identity derived from fund, action type, target session, and reviewed payload, distinguishing "the same action asked twice" from "two different actions".
- **Operation record**: The existing durable record of an accepted mutating request, carrying its request identity, status, and (new) logical-operation identity.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: In synthetic crash-injection tests covering every recorded crash window between intent declaration and outcome recording, 100% of subsequent new-identity session requests are refused until reconciliation.
- **SC-002**: In synthetic duplicate-submission tests across all pairwise entry-point combinations (web–CLI, web–runner, CLI–runner), exactly one execution occurs per logical operation in 100% of cases.
- **SC-003**: Zero regressions in the existing test suite: every previously passing test still passes, with any exception individually evidenced as unchanged baseline per project governance.
- **SC-004**: No interaction with real or protected fund roots occurs during development or validation (verifiable from test fixtures and code review).
- **SC-005**: Same-identity retry behavior and the deliberate redo path behave byte-for-byte as before for previously recorded scenarios.

## Assumptions

- The installation remains single-user and single-account; all writers participate in the existing cooperative admission protocol. Exclusion of unaware or malicious programs writing the same files remains the operator's acknowledged responsibility (unchanged from Spec005).
- The protected production fund identities `watchtower` and `watchtower-weekly` stay blocked; the user did not request unblocking them, and Gate 1 approval proceeded on that basis. Any future unblocking is a separate explicit decision.
- The existing reconciliation path (recorded-failure selection and operator-approved resolution) is the designated way to clear an unresolved intent; this feature adds the fence, not a new resolution workflow.
- "Entry points" means the web desk, the CLI, and the headless owned runner; browser-level coordination (Web Locks, pending-operation storage) remains a convenience, not part of the safety guarantee.
