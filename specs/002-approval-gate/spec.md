# Feature Specification: Per-Fund Approval Gate (Yay/Nay Mode)

**Feature Branch**: `cgjedrem-super-telegram`

**Created**: 2026-10-29

**Status**: Draft

**Input**: User description: "Per-fund approval gate ('yay/nay' mode). When enabled for a fund, a pending decision produced by a session is NOT auto-executed at the next close; instead it waits for explicit user approval. Fund-level setting (mandate YAML + spec validation + TUI fund builder toggle + CLI), default OFF = current auto-execute behavior. Approval state lives in the fund dir so the runner container and TUI container both see it. CLI: `aihf paper approve <name>` / `aihf paper reject <name>`. TUI surface: show pending decision + approve/reject action on the fund screen. Ledger: audit event for approve/reject/expire; if no approval by the next session, skip execution and record the skip (not a halt — the fund keeps running). The existing kill switch stays as-is; the gate is orthogonal."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Turn approval mode on for a fund (Priority: P1)

A fund owner decides a fund should not trade without a human yay. They enable approval mode where they create funds: in the mandate file, in the terminal fund builder, or with a command-line flag at creation. A fund created without any of these keeps today's behavior exactly — decisions auto-execute at the next close, and nothing about the fund's stored configuration or ledgers changes.

**Why this priority**: Without the setting there is no feature. Default-off backward compatibility is the constitution's ledger-integrity principle applied to configuration: an existing fund must be byte-for-byte unchanged by this feature's existence.

**Independent Test**: Create a fund with approval mode on via each surface (mandate, builder, CLI flag) and confirm the deployed fund records it; create a fund without it and confirm the deployed configuration is byte-identical to today's output and a pre-feature ledger still verifies.

**Acceptance Scenarios**:

1. **Given** a mandate with approval mode enabled, **When** a paper fund is created from it, **Then** the deployed fund records approval mode as on and the confirmation output states it.
2. **Given** the fund builder, **When** the user reaches the approval step, **Then** they can toggle approval mode with a plain-language description, and the saved fund records the choice.
3. **Given** a paper fund created with the command-line approval flag, **When** the deployment is inspected, **Then** approval mode is recorded on the deployed fund.
4. **Given** a mandate with no approval setting, **When** a fund is created from it, **Then** the deployed configuration is byte-identical to what the current system writes and previously recorded ledgers still verify.
5. **Given** a mandate with an approval setting that is not a boolean, **When** the mandate is loaded, **Then** it is rejected with a clear error.

---

### User Story 2 - A pending decision waits for approval instead of auto-executing (Priority: P1)

A fund with approval mode on completes a session and produces a decision. At the next close the engine does NOT execute it. The fund still marks its book, still computes its value, and still makes a fresh decision on its normal cadence — it just does not trade on the unapproved decision. The pending decision and its approval status are visible to the owner.

**Why this priority**: This is the core behavior the feature exists for. It ranks with US1 because the setting is meaningless without the wait behavior.

**Independent Test**: Run a gated fund through a decision cycle and confirm the next session executes nothing, the book is unchanged by the skipped decision, the session is still recorded, and the following decision cycle proceeds normally.

**Acceptance Scenarios**:

1. **Given** a gated fund with a pending decision, **When** the next session runs, **Then** no orders are placed, the book is unchanged by the skipped decision, and the session is recorded as usual.
2. **Given** a gated fund whose decision was skipped, **When** the next decision cycle arrives, **Then** a fresh decision is produced and the fund continues operating normally (no halt).
3. **Given** a fund with approval mode off, **When** a session runs with a pending decision, **Then** the decision auto-executes exactly as today (existing behavior pinned, unchanged).
4. **Given** a gated fund, **When** the owner inspects its status (CLI or TUI), **Then** the pending decision and the fact that it awaits approval are visible.

---

### User Story 3 - Approve or reject from the command line (Priority: P1)

The owner runs `aihf paper approve <name>` to yay the pending decision — it executes at the next close (or immediately when the owner asks for immediate execution and a session is due) — or `aihf paper reject <name>` to nay it — the decision is discarded and the book is untouched. Both commands record an audit event. The commands fail with clear messages when there is nothing to decide (approval mode off, or no pending decision).

**Why this priority**: The command line is the automation surface; without it, approval cannot be scripted or given from outside the TUI.

**Independent Test**: On a gated fund with a pending decision, run approve and confirm the decision executes at the next close with an audit event; run reject on a fresh pending decision and confirm the next session skips it with an audit event and the book is unchanged; run both against a gate-off fund and a fund with nothing pending and confirm clear refusals.

**Acceptance Scenarios**:

1. **Given** a gated fund with a pending decision, **When** the owner runs approve, **Then** an approval verdict is recorded, an audit event is written, and the decision executes at the next session close.
2. **Given** a gated fund with a pending decision and a due session, **When** the owner runs approve with the immediate option, **Then** the decision executes right away.
3. **Given** a gated fund with a pending decision, **When** the owner runs reject, **Then** a rejection verdict is recorded, an audit event is written, and the next session skips execution leaving the book unchanged.
4. **Given** a fund with approval mode off, **When** approve or reject is attempted, **Then** the command fails with a message naming the fund and the reason.
5. **Given** a gated fund with no pending decision, **When** approve or reject is attempted, **Then** the command fails with a message saying there is nothing awaiting approval.
6. **Given** an approve on a gated fund with a pending decision but no session currently due, **When** the immediate option is used, **Then** the command reports that the decision will execute at the next close rather than failing.

---

### User Story 4 - Approve or reject from the terminal UI (Priority: P2)

The owner opens the fund screen in the terminal UI and sees that a decision awaits approval, with the decision's target weights. Two actions are offered — approve and reject — enabled only when the fund is gated, has a pending decision, and is not halted. Taking an action records the verdict and audit event and refreshes the screen.

**Why this priority**: The TUI is the primary interactive surface; the gate must be operable where the owner watches the fund. It follows the CLI because the CLI is the automation contract the TUI mirrors.

**Independent Test**: Open a gated fund with a pending decision in the TUI, confirm the awaiting-approval state is displayed, take approve and reject in turn on fresh decisions, and confirm the verdict file and audit events result and the actions are disabled when they should be.

**Acceptance Scenarios**:

1. **Given** a gated fund with a pending decision on the fund screen, **When** the owner views the fund, **Then** the screen shows the decision awaits approval and offers approve/reject actions.
2. **Given** the approve action is taken, **When** the screen refreshes, **Then** the verdict is recorded and an audit event exists.
3. **Given** the reject action is taken, **When** the screen refreshes, **Then** the verdict is recorded and an audit event exists.
4. **Given** a fund that is not gated, or has no pending decision, or is halted, **When** the owner looks at the actions, **Then** approve/reject are disabled.
5. **Given** the fund screen's next-run description, **When** a gated fund has an unapproved pending decision, **Then** it says the run will skip execution rather than trade.

---

### User Story 5 - An unapproved decision expires gracefully (Priority: P2)

A gated fund's decision sits unapproved when the next session arrives. The engine skips execution, records the skip as an audit event, and carries on: the session is recorded, the book is marked, the next decision cycle proceeds. The fund is NOT halted. A verdict left over from an earlier decision (after a redo replaced the deciding session) is never honored — it is ignored as stale.

**Why this priority**: Expiry is the safety net that makes the gate non-blocking; without it a forgotten fund would silently stop trading. It depends on US2's skip path, so it follows.

**Independent Test**: Run a gated fund past a decision with no verdict given and confirm the skip event, the unchanged book, the recorded session, and the normal continuation; plant a stale verdict keyed to a replaced decision and confirm it is ignored.

**Acceptance Scenarios**:

1. **Given** a gated fund with an unapproved pending decision, **When** the next session runs, **Then** an expiry/skip audit event is recorded and no orders are placed.
2. **Given** the same session, **When** it completes, **Then** the session record exists, the book is marked, and the fund is not halted.
3. **Given** a stale approval verdict left from a decision that no longer exists (redo replaced it), **When** the next session runs, **Then** the stale verdict is ignored and the skip path applies.
4. **Given** a gated fund that is also halted, **When** a session is attempted, **Then** the existing halt behavior applies unchanged and the approval gate adds nothing to it.

---

### User Story 6 - Documentation states how the gate works (Priority: P3)

A reader of the top-level documentation can find what approval mode is, that it is set at fund creation (mandate, builder, or CLI flag), that approve/reject are the yay/nay commands, and that an unapproved decision is skipped — not a halt. The documentation matches actual behavior.

**Why this priority**: Discoverability matters but only once the behavior is right.

**Independent Test**: Read the documentation cold and, using only what it says, enable the gate, approve a decision, and reject one.

**Acceptance Scenarios**:

1. **Given** the top-level documentation, **When** the user looks up fund settings, **Then** approval mode is documented with its default (off) and how to enable it on each creation surface.
2. **Given** the documentation, **When** the user wants to yay or nay a pending decision, **Then** the approve/reject commands and the expiry behavior are documented.

---

### Edge Cases

- What happens when a verdict is written while a session is mid-run? It applies at the next session; the current session is unaffected.
- What happens when the deciding session is redone (`paper tick --again`) while a verdict is pending? The verdict is keyed to the decision it approved; a replaced decision makes the verdict stale and it is ignored, never honored.
- What happens when approval mode is toggled on a deployed fund while a decision is pending? There is no live-edit path for deployed funds; the CLI and TUI refuse to change approval-adjacent state while a decision is pending, and the deployed configuration is frozen at creation by design.
- What happens when approve is requested with the immediate option but no session is due? The command reports the decision will execute at the next close instead of failing.
- What happens when a gated fund is also halted? The kill switch wins exactly as today; the gate neither adds nor removes halt behavior, and never writes the kill-switch file.
- What happens when a gated weekly/monthly fund's decision is skipped mid-period? The fund stays mark-only until the next period's decision; the UI copy says the decision lapsed rather than silently vanishing.
- What happens when the verdict file is corrupt or unreadable? It is treated as absent (fail-safe for a mailbox), never as a yay.
- What happens when two surfaces (runner container and TUI container) touch the verdict at once? Writes are atomic file replacements; last writer wins at human decision speed; a verdict written mid-session applies next session.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST support a per-fund approval-mode setting that is settable in the mandate YAML, selectable in the TUI fund builder, and settable via a command-line flag at paper-fund creation.
- **FR-002**: The system MUST default approval mode to off, which preserves the current auto-execute behavior exactly.
- **FR-003**: The system MUST reject a non-boolean approval setting in the mandate with a clear validation error.
- **FR-004**: The system MUST keep the stored configuration of funds without approval mode byte-identical to the current system's output, so existing ledgers remain verifiable.
- **FR-005**: The system MUST store the approval verdict as a file in the fund directory, readable and writable by both the runner and TUI containers sharing the fund volume.
- **FR-006**: The system MUST key the verdict to the decision it refers to, and MUST ignore (never honor) a verdict that does not match the currently pending decision.
- **FR-007**: The system MUST NOT auto-execute a pending decision at the next close for a gated fund; the session proceeds (book marked, value computed, session recorded) without executing the unapproved decision.
- **FR-008**: The system MUST continue operating a gated fund after a skipped decision: the next decision cycle proceeds normally and the fund is not halted.
- **FR-009**: The system MUST provide `aihf paper approve <name>` and `aihf paper reject <name>` commands that record the verdict and an audit event, refusing with clear messages when approval mode is off or nothing is pending.
- **FR-010**: The system MUST execute an approved decision at the next session close, and MUST execute it immediately when the owner requests immediate execution and a session is due; when none is due it MUST report the next-close execution instead of failing.
- **FR-011**: The system MUST leave the book unchanged by a rejected decision: the next session skips execution and no orders are placed.
- **FR-012**: The system MUST record an audit event for approval, rejection, and expiry/skip of a pending decision.
- **FR-013**: The system MUST show the pending decision and its awaiting-approval status in both the CLI status output and the TUI fund screen, and MUST offer approve/reject actions on the TUI fund screen, enabled only when the fund is gated, has a pending decision, and is not halted.
- **FR-014**: The system MUST leave the existing kill switch (`paper halt`/`resume`) behavior unchanged, and the approval gate MUST NOT write or read the kill-switch control file.
- **FR-015**: The system MUST treat a corrupt or unreadable verdict file as no verdict (fail-safe), never as an approval.
- **FR-016**: The top-level documentation MUST document approval mode: default, how to enable it on each creation surface, the approve/reject commands, and the expiry behavior.

### Key Entities *(include if feature involves data)*

- **Approval mode**: A per-fund setting, fixed at fund creation, recorded in the fund's frozen configuration. Default off.
- **Approval verdict**: The owner's yay/nay for one specific pending decision, stored in the fund directory, carrying which decision it refers to, when it was decided, and by which surface. Consumed exactly once.
- **Pending decision**: The fund's most recent assessed decision awaiting execution — already lives in the session ledger; this feature adds no second copy of it.
- **Audit events**: The fund's append-only event log, extended with approval, rejection, and expiry/skip kinds.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A user can enable approval mode on each creation surface (mandate, builder, CLI flag) and observe a pending decision wait instead of auto-executing, with zero configuration outside the chosen surface.
- **SC-002**: A fund created without approval mode produces byte-identical stored configuration and identical behavior to the current system (verified by test), and a pre-feature ledger still verifies.
- **SC-003**: A user can yay a pending decision from the CLI or TUI and observe it execute at the next close (or immediately when due and requested), with an audit event recorded.
- **SC-004**: A user can nay a pending decision from the CLI or TUI and observe the book unchanged after the next session, with an audit event recorded.
- **SC-005**: A gated fund left unattended through a decision boundary skips execution, records the skip, and continues its normal cadence — verified by test that no halt occurs.
- **SC-006**: The full test suite passes with no new failures beyond the six documented Windows baseline failures.

## Assumptions

- **Decision stays in the ledger.** The pending decision already lives in the hash-chained session ledger; this feature adds only the verdict as new on-disk state. No decision duplication, no chain changes.
- **Verdict consumed once.** An approve verdict is consumed by the session that executes the decision; a reject verdict by the session that skips it. The verdict file is cleared after consumption.
- **Setting fixed at creation.** Deployed fund configurations are frozen by design (mandate-hash guard); approval mode is set on the creation surfaces and not live-toggled on a deployed fund. Approval-adjacent operations refuse while a decision is pending.
- **Expiry is per-session, not time-based.** "No approval by the next session" is the expiry rule; there is no separate timeout clock.
- **Gate lives in the paper layer.** Backtests are unaffected: approval mode has no meaning for backtesting, and the engine's shared session path is not altered.
- **Windows environment.** Tests run on Windows; the six documented baseline failures are pre-existing and out of scope. Verdict writes use the existing atomic file-replacement helper (UTF-8, no BOM).
- **No new cadence or scheduling concepts.** The gate intercepts execution only; session discovery, cadence, and the runner loops are untouched.