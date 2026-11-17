# Feature Specification: Legacy Failure Recovery

**Feature Branch**: `009-legacy-failure-recovery` (authored on worktree branch `cgjedrem-effective-winner`; branch-creation hook skipped per session worktree contract)

**Created**: 2026-11-17

**Status**: Draft

**Input**: User description: "Supported recovery for historical failures that block otherwise consistent existing paper funds. Six historical failed events (2026-10-27 … 2026-11-10) across two funds lack request IDs; ledger full replay and broker-book comparison PASS; corrupt audit event count 0; historical resume events lack reconciliation IDs and no reconciliation receipts exist; preview reports 'multiple-unreconciled-failures' recoverable=false and execution is guarded with 423 reconciliation-required. Distinguish actual unresolved effects from already superseded historical no-effect errors with trustworthy evidence; operator-mediated audited reconciliation may be needed. Never ignore exceptions wholesale, clear audit history, fabricate receipts, mark no_effects by exception type alone, relabel corruption/healthy prematurely, weaken the gate for genuine post-effect ambiguity, or use latest mutable bytes as sole proof. Preserve old ledger hashes and audit history."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Resolve multiple historical no-effect failures (Priority: P1)

The operator has a paper fund that is blocked from scheduled work solely because of multiple historical failed events. Full ledger replay verifies, the broker book matches replay, and no audit event is corrupt. Some or all failures predate request-ID journaling (unkeyed). The operator opens the recovery preview, reviews each unresolved failure together with the supporting evidence the system computed for it, confirms that every listed failure is resolved by durable evidence, and performs one explicit, audited reconciliation operation. Afterwards the fund's recovery state is ready, the ledger readiness check passes, and scheduled work is admitted again — with every historical event, hash, and audit line preserved byte-identically.

**Why this priority**: This is the blocking production situation (two funds, six events) and the entire value of the feature: restoring schedulability of otherwise-consistent funds without rewriting history.

**Independent Test**: On a synthetic root with a hash-chained ledger containing multiple unkeyed historical failed events followed by verified later sessions and a matching broker book, an operator completes the reconciliation preview and confirm flow; the fund becomes work-admissible and the pre-existing ledger bytes and audit history are unchanged.

**Acceptance Scenarios**:

1. **Given** a fund with multiple unresolved historical failures (including unkeyed events), verified replay, matching broker book, and zero corrupt audit events, **When** the operator opens the recovery preview, **Then** the preview lists every unresolved failure with its identity (digest), recorded time, error summary, and the system's evidence classification, and offers a confirm action only when every failure carries sufficient no-effect evidence.
2. **Given** such a preview, **When** the operator confirms, **Then** the system durably records an audited reconciliation decision binding each failure digest, the current ledger head, the broker-book digest, the operator identity, and the recorded time, and the fund's recovery state becomes ready and work admission succeeds.
3. **Given** a completed reconciliation, **When** the ledger and audit history are replayed byte-for-byte, **Then** all pre-existing session records, checkpoints, and event bytes are identical to before the operation (append-only change).
4. **Given** a reconciled fund, **When** the operator or scheduler retries the same reconciliation or a crash occurs mid-operation and the operation is retried, **Then** the outcome is idempotent: no duplicate resolution effect, no double resolution of the same failure digest, and the durable record remains consistent.

---

### User Story 2 - Genuine ambiguity stays blocked (Priority: P2)

The operator attempts recovery on a fund where the evidence does not establish that a failure had no effects: a failure that may have occurred after an effect boundary (e.g., after broker orders or approval consumption), a corrupt audit event, a broker book that does not match replay, a ledger head that changed since the preview, or an interleaving writer. In every such case the system refuses resolution, keeps the recovery gate closed, tells the operator exactly which failure and which evidence check failed, and leaves all state unchanged.

**Why this priority**: The gate exists to prevent resuming over genuinely ambiguous post-effect failures. Weakening it — even accidentally, via this new path — would undermine the ledger-integrity principle. This story is the negative space that makes P1 safe.

**Independent Test**: Synthetic fixtures for each refusal class (post-effect-ambiguous failure, corrupt audit event, book mismatch, stale preview head, concurrent writer contention) each independently demonstrate refusal with unchanged state and a specific operator-visible reason.

**Acceptance Scenarios**:

1. **Given** a fund with at least one failure whose effects cannot be excluded by durable evidence, **When** the operator opens the preview, **Then** that failure is marked not-resolvable with its specific evidence gap, and no confirm action is offered for a set containing it.
2. **Given** a fund whose replay fails verification or whose audit chain contains a corrupt event, **When** any recovery action is attempted, **Then** it is refused as corrupt (distinct from reconciliation-required) and nothing is written.
3. **Given** a fund whose current broker book does not match the verified replay, **When** any recovery action is attempted, **Then** it is refused with a book-mismatch reason and nothing is written.
4. **Given** a preview computed at one ledger head, **When** the ledger head changes before the operator confirms, **Then** the confirm is refused as stale and the operator must re-preview.
5. **Given** another writer holds or contends the fund's control/audit lanes, **When** reconciliation is attempted, **Then** it is refused or serialized through the existing admission lanes and never appends concurrently.

---

### User Story 3 - Evidence transparency for the operator (Priority: P3)

Before deciding, the operator can see, per unresolved historical failure: what the system could establish (event identity, position relative to later verified sessions, replay and book status) and what it could not. The display distinguishes "resolved by durable evidence" from "not resolvable — operator judgment or external evidence required", without presenting exception type alone as proof of no effects.

**Why this priority**: The operator cannot make a trustworthy attestation without seeing the evidence basis; but the flow is usable (P1/P2 testable) with a minimal evidence presentation.

**Independent Test**: Preview rendering for a mixed fixture (resolvable + non-resolvable failures) shows per-failure classifications and reasons, verified against the same computation the confirm path uses.

**Acceptance Scenarios**:

1. **Given** a fund with mixed-evidence failures, **When** the operator views the preview, **Then** each failure shows its classification and the specific evidence or gap behind it, and the set-level confirm availability matches the per-failure classifications.

---

### Edge Cases

- **Multiple legacy failures missing request IDs**: unkeyed events are first-class; identity is the event digest, not a request ID. Resolution must not require inventing IDs for historical events.
- **Actual post-effect unresolved failure**: a failure whose position or recorded metadata cannot exclude broker/approval/ledger effects is never auto-classified as no-effect; it remains blocking regardless of how old it is or which exception type it carries.
- **Corrupt audit event or failed replay**: handled as corruption, not reconciliation; no recovery write path is available.
- **Ledger/book mismatch at confirm time**: refusal; the operator must resolve the divergence through existing means first.
- **Stale preview / changed head**: confirm binds the previewed head; any append (successful session, halt, other event) invalidates the preview.
- **Retry / crash / idempotency**: durable decision record is written so that a crashed operation can be observed and safely retried without double effect; a second confirm of the same failure set is a no-op or explicit already-resolved refusal.
- **Interleaving writer**: all reads and the decision write pass through the existing root/admission/audit lanes; no out-of-band writes.
- **Legacy receipts and legacy resume events**: pre-existing legacy receipts keep their current event-only replay semantics; this feature neither upgrades nor invalidates them.
- **Funds with an active Halt or unresolved tick intent**: those conditions keep their own gates; this feature resolves failure events only and does not clear halts or intents.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST provide an operator-mediated recovery preview for a fund with one or more unresolved historical tick failures, including failures with no request ID, listing every unresolved failure with its durable identity and evidence classification.
- **FR-002**: The system MUST compute, per failure, an evidence classification with at least two outcomes: "resolvable — no effects established by durable evidence" and "not resolvable — evidence insufficient". Exception type or error message text alone MUST NOT constitute no-effect evidence.
- **FR-003**: The system MUST offer a confirm action only when every unresolved failure for the fund is classified resolvable; a set containing any non-resolvable failure MUST NOT be confirmable as a whole or piecemeal through this path.
- **FR-004**: On confirm, the system MUST durably record an audited reconciliation decision that binds: each resolved failure's digest, the ledger head at preview time, the broker-book digest at preview time, the operator identity, and the recorded time — without modifying, deleting, or re-serializing any pre-existing event, session record, checkpoint, or hash chain.
- **FR-005**: After a valid decision is recorded, replay-based readiness MUST treat the bound failures as resolved, so the fund's recovery state becomes ready and work admission succeeds, provided no other gate (halt, unresolved intent, corruption, mismatch) applies.
- **FR-006**: The confirm MUST be refused as stale if the ledger head, broker-book digest, or unresolved-failure set changed between preview and confirm; the refusal MUST NOT write anything.
- **FR-007**: The operation MUST be idempotent across retry and crash: the durable decision record MUST make a retried or repeated confirm safe (no duplicate resolution, no conflicting records for the same failure digest).
- **FR-008**: All reads and writes of the recovery flow MUST pass through the existing enrolled-root read boundaries and admission/audit lanes; the flow MUST NOT introduce any out-of-band or unanchored write.
- **FR-009**: The flow MUST preserve the existing distinctions among corrupt replay, reconciliation-required, halted, and ready states; it MUST NOT relabel corruption as healthy or reconciliation-required, nor weaken any existing gate for post-effect-ambiguous current failures.
- **FR-010**: The feature MUST NOT perform fee, cash, position, or session-record rewrites of any kind; resolution changes only how historical failure events are treated by readiness.
- **FR-011**: Existing single-failure receipt semantics, legacy receipt event-only replay, intent reconciliation, halt, and resume behavior MUST remain unchanged for all cases they already cover.
- **FR-012**: The preview's per-failure classifications MUST be computed by the same logic that gates the confirm, so the operator's display can never be more permissive than the write path.

### Key Entities *(include if feature involves data)*

- **Historical failure event**: An existing audit event of a failed tick attempt. Identity is the digest of its canonical content; it may lack a request ID (legacy/unkeyed) and may lack effect-boundary metadata (predates effect classification).
- **Evidence classification**: The system's per-failure determination, derived from durable records (event content, position in the verified event stream, replay result, broker-book comparison), of whether absence of effects is established.
- **Reconciliation decision record**: A new durable, audited, append-only record binding operator, recorded time, previewed ledger head, broker-book digest, and the set of resolved failure digests. It authorizes readiness to treat exactly those failures as resolved; it is not a rewrite of any prior record.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: An operator can take a fund blocked solely by multiple historical no-effect failures from preview to restored schedulability in a single reviewed operation, with zero bytes of pre-existing ledger or audit history altered (verified by byte-identical replay).
- **SC-002**: 100% of fixtures containing at least one genuinely ambiguous (post-effect-possible) failure remain blocked after any attempted recovery through this path.
- **SC-003**: 100% of refusal classes (corrupt replay, corrupt audit event, book mismatch, stale preview, writer contention) refuse with a distinct operator-visible reason and zero writes.
- **SC-004**: A crashed or retried reconciliation leaves the fund in exactly one consistent state; repeating the confirm never produces duplicate or conflicting resolution records.
- **SC-005**: Acceptance evidence is produced on synthetic fixtures first; any attended production reconciliation of real funds is a separately approved operator action outside this feature's scope.

## Assumptions

- Single-operator personal deployment; "the operator" is the sole user, acting through the supported web surface consistent with spec007's reviewed-recovery contract.
- The durable evidence available in existing records is sufficient to classify the six known production events; any event the evidence cannot classify stays blocked rather than forcing a resolution path.
- This feature adds a resolution path for failure events only; halt clearing, tick-intent reconciliation, and approval-journal effects remain governed by their existing mechanisms.
- No new fund creation, no scheduler behavior changes, and no provider/data changes are in scope.
- Synthetic fixtures (anonymized) are the required test substrate; real-fund data is inspected read-only only if essential, and never mutated by this feature's development.
