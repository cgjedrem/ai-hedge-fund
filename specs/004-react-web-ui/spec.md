# Feature Specification: Local React Trading Desk

**Feature Branch**: `cgjedrem-fictional-winner` (app-managed worktree; branch creation skipped, numbering applied)
**Created**: 2026-10-30
**Status**: Ready for design
**Input**: "let's spawn a child session to go away from tui and into react ui same ui but with react use shadcn component pls spawn a child session with coordinator agent with speckit and devloop. do that autonomously, my goal is to see the result without you asking. I am off to a concert"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Inspect the trading desk (Priority: P1)

The operator opens a local browser instead of a terminal and inspects mandates, deployed paper funds, next-run forecasts, recorded performance, holdings, sessions, orders, reports and scorecards.

**Why this priority**: Safe visibility is the primary useful outcome without touching running funds.
**Independent Test**: Navigate a seeded offline fund with multiple sessions; compare displayed quantities and report sections with domain records.
**Acceptance Scenarios**:
1. **Given** a deployed fund, **When** its detail opens, **Then** NAV, cash, positions, cadence, next-run forecast, session history and chart are visible.
2. **Given** a session with executed and proposed decisions, **When** its report opens, **Then** orders/fills/costs and targets-only proposals remain distinct.
3. **Given** existing live funds, **When** browsing in read-only mode, **Then** no ledger, configuration, mailbox, process or external provider is changed.

### User Story 2 - Deliberately operate an isolated paper fund (Priority: P1)

The operator approves or rejects the displayed pending decision, halts/resumes, and explicitly starts/stops a runner or requests a run.

**Why this priority**: The browser must preserve existing trading safety rather than invent a parallel engine.
**Independent Test**: Exercise fake-backed fund operations in a temporary data root and inspect the existing ledger/mailbox.
**Acceptance Scenarios**:
1. **Given** a pending decision, **When** an approval is submitted, **Then** its displayed timestamp and source hash must still match and the existing mailbox receives the verdict without immediate execution.
2. **Given** an expired/replaced decision, **When** a stale verdict is submitted, **Then** it is rejected visibly without rebinding to the new decision.
3. **Given** read-only mode, **When** a mutation is requested, **Then** it is denied before any domain side effect.
4. **Given** explicit write capability and an isolated fund, **When** runner or halt controls are used, **Then** the correct existing adapter is invoked and errors are shown.

### User Story 3 - Build and research funds (Priority: P2)

The operator creates a mandate, configures strategies/agents/capital/cadence/window/approval/broker/universe, deploys deliberately, and runs an explicitly requested backtest with progress and reports.

**Why this priority**: Creation and research complete the existing operator workflow.
**Independent Test**: Create and deploy to a temporary root, run an offline fake-backed backtest, reopen its persisted report.
**Acceptance Scenarios**:
1. **Given** a builder draft, **When** cadence changes away from minute, **Then** minute-only fields are omitted and canonical validation is applied.
2. **Given** an existing name, **When** saving a new fund, **Then** history is not overwritten implicitly.
3. **Given** a backtest request, **When** execution starts, **Then** progress, failure or completion is visible and the result can be reopened.

### User Story 4 - Configure and navigate (Priority: P2)

The operator switches models, enters provider credentials without exposing stored secrets, and navigates through a keyboard command palette.

**Why this priority**: Preserve familiar terminal efficiency and provider choice.
**Independent Test**: Navigate with keyboard, submit a write-only test credential, verify no response or log contains it.
**Acceptance Scenarios**:
1. **Given** settings, **When** credentials are displayed, **Then** only configured/missing status is returned.
2. **Given** a text field, **When** typing shortcut letters, **Then** navigation does not steal focus.
3. **Given** a narrow browser, **When** navigating any screen, **Then** controls and error messages remain usable.

### Edge Cases

- Empty, invalid or corrupt mandates, research results and ledgers remain visible as errors, not success-shaped empty data.
- Missing quotes are not recorded NAV; live estimates are separately timestamped and never persisted as history.
- Duplicate/stale actions, running jobs, external runner ownership and in-flight work must not silently retry trading operations.
- Invalid names, traversal, symlinks, unexpected origins and secret-bearing errors must not cross the local safety boundary.
- Minute backtests retain the existing daily-grid interpretation.
- Browser reload/deep links must not resubmit mutations.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Provide home, mandate list/detail, builder, paper list/detail, backtest, session report, research report, scorecard, settings and command palette.
- **FR-002**: Preserve dark terminal-like styling and keyboard navigation using the requested component family.
- **FR-003**: Reuse canonical Python trading, validation, scheduling, metric, scorecard and ledger logic; do not calculate trading decisions in the browser.
- **FR-004**: Display next-run forecasts, recorded equity/benchmark curves, positions, sessions, fills/costs and distinctly labeled live-value estimates.
- **FR-005**: Preserve source-hash-bound, expiring approval semantics through the existing ledger mailbox.
- **FR-006**: Require explicit capability and user action for all mutations; support approval/rejection, halt/resume, runner start/stop, builder deployment and backtests.
- **FR-007**: Keep model switching and write-only, allowlisted provider credential configuration available without returning/logging keys.
- **FR-008**: Run locally with a single documented command and provide a Compose service consistent with Linux overrides.
- **FR-009**: Preserve the TUI and its entry points; do not delete or silently replace it.
- **FR-010**: Default browser access to local-only, read-only operation; reject remote access and unintended cross-origin mutations.
- **FR-011**: All automated execution uses temporary roots and fakes, with no paid-provider/LLM calls, real orders, live loops or protected-runner operations.
- **FR-012**: Protected funds `watchtower`, `watchtower-weekly` and `umbrella` are read-only during development and evidence collection.
- **FR-013**: Provide explicit loading, empty, stale, permission-denied and failure states; retain useful domain errors without leaking secrets.
- **FR-014**: Record a TUI parity checklist and honestly label deferred/unsupported actions before any retirement decision.

### Key Entities

- **Mandate**: Canonically validated fund configuration and strategy selection.
- **Deployment**: Fund snapshot, universe, broker, ledger and runner ownership.
- **Session**: Immutable hash-chained recorded valuation, execution and decision.
- **Pending approval**: Decision timestamp and source-record hash, verdict and expiry.
- **Research job/result**: Explicitly requested work, progress, failure/completion and saved report.
- **Capabilities/settings**: Local operating mode, allowed actions, model selection and secret-presence flags.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: All eleven named screen groups in FR-001 are reachable in the browser and covered by the parity checklist.
- **SC-002**: A seeded fund can be inspected from list through session report and scorecard with matching recorded amounts and zero external requests.
- **SC-003**: Stale approvals, forbidden mutations and invalid names have negative tests; no protected fund state changes during acceptance.
- **SC-004**: Creation, approval/rejection and backtest workflows complete using isolated fake-backed scenarios.
- **SC-005**: The production interface builds, starts from one command, serves deep links and has captured browser screenshots.
- **SC-006**: Existing tests retain their baseline behavior; new backend/frontend tests pass and changed Python files satisfy existing style gates.

## Assumptions

- The user's express autonomous authorization replaces interactive design/plan approvals, not red-team analysis, review or final merge approval. The PR will not be merged.
- Additive migration is intended: the TUI remains available until the user evaluates parity.
- Single-user localhost deployment is sufficient; remote/cloud access and accounts are out of scope.
- Read-only real-fund browsing is the default. Network activity and writes require explicit user-enabled capability; autonomous verification never grants that capability on real funds.
- The protected names remain guarded even when general writes are enabled; any future relaxation requires deliberate configuration and is not exercised here.
- Destructive deletion/replacement and redo may be deferred with visible parity gaps rather than risk existing history.
- Existing Python domain functions are authoritative; UI presentation may adapt terminal layouts to a responsive sidebar and cards.
- Fixture/demo mode uses synthetic data and fake execution, clearly labeled; it must not pretend to show actual market data.
- Provider setup may show configured status without revealing key values. Free yfinance remains usable without credentials when the user explicitly requests network work.
- Linux/Windows runtime differences and unavailable browser/container capabilities will be documented as blocked, not claimed as tested.
