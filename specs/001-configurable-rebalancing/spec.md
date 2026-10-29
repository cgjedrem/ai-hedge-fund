# Feature Specification: Configurable Rebalancing Cadence

**Feature Branch**: `cgjedrem-redesigned-invention`

**Created**: 2026-10-29

**Status**: Draft

**Input**: User description: "Make rebalance cadence a first-class, user-configurable setting across every surface: mandate YAML, fund spec validation, scheduler, TUI fund builder, CLI, and docs. Backward compatibility: existing fund mandates without an explicit rebalance setting must keep behaving exactly as today."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Set the cadence in the fund mandate (Priority: P1)

A fund owner writing a mandate file states how often the fund decides — every bar (minute), every session (daily), the first session of each ISO week (weekly), or the first session of each calendar month (monthly). The engine accepts the four values, rejects anything else with an error that names the offending value, and the scheduler rebalances exactly on the stated cadence — including when the first session of a period falls on an unusual day (a holiday Monday makes Tuesday the week's first session; a year boundary does not split an ISO week).

**Why this priority**: This is the core promise of the feature — the owner controls the fund's decision rhythm from the mandate. Without it, no other surface means anything.

**Independent Test**: Load a mandate that sets each of the four cadence values in turn and confirm the engine rebalances on the stated rhythm; load a mandate with a misspelled cadence and confirm a clear rejection naming the value.

**Acceptance Scenarios**:

1. **Given** a mandate with `rebalance: monthly`, **When** the engine runs across a month boundary, **Then** the first session of each calendar month is a rebalance session and no other session is.
2. **Given** a mandate with `rebalance: weekly`, **When** the first trading day of an ISO week is a holiday, **When** the engine runs, **Then** the next observed session (e.g. Tuesday) is that week's rebalance session.
3. **Given** a mandate with `rebalance: minute`, **When** the engine runs, **Then** every bar within the trading window is a rebalance session.
4. **Given** a mandate with an unknown cadence value (e.g. `hourly`), **When** the mandate is loaded, **Then** it is rejected with an error naming the value and the allowed values.
5. **Given** the example mandate shipped with the project, **When** a user reads the cadence line, **Then** the comment lists all four supported values.

---

### User Story 2 - Existing mandates keep behaving exactly as today (Priority: P1)

A fund owner with an existing mandate that says nothing about rebalance continues to get today's behavior: the fund decides weekly, its stored configuration serializes exactly as it did before, and previously recorded ledgers remain verifiable byte-for-byte. Nothing about this feature may change what an old mandate means or how it is written to disk.

**Why this priority**: Ledger integrity is the project's first principle. A configuration feature that silently changes the meaning or serialization of existing funds is a corruption bug, not a feature.

**Independent Test**: Load a mandate with no rebalance setting and confirm the fund decides weekly; confirm the stored configuration of such a fund is byte-identical to what the current system writes; confirm a previously recorded session ledger still verifies.

**Acceptance Scenarios**:

1. **Given** a mandate with no `rebalance` key, **When** the fund is loaded and run, **Then** the fund decides on the weekly cadence (the current default).
2. **Given** a mandate with no `rebalance` key, **When** the fund's configuration is saved, **Then** the serialized output is byte-identical to the output the current system produces for the same mandate.
3. **Given** a ledger recorded by the current system, **When** it is verified after this feature ships, **Then** verification succeeds unchanged.

---

### User Story 3 - Override the cadence from the command line (Priority: P2)

A user running a backtest, or creating a paper fund from the command line, can override the mandate's cadence with a command-line option instead of editing the file. The override accepts the same four values and rejects anything else with a clear usage error. A paper fund created with an override bakes the overridden cadence into its frozen configuration at creation time; the cadence of an already-deployed fund can never be changed from the command line. Overriding a minute fund to a day-grid cadence must not leave minute-only settings behind, and overriding a day-grid fund to minute must yield a valid minute fund using the standard defaults.

**Why this priority**: The command line is the primary automation surface; without the override, trying a different cadence means hand-editing a file per experiment. It ranks below the mandate itself because the mandate remains the source of truth.

**Independent Test**: Run a backtest with a cadence override and confirm the result reflects the overridden cadence; create a paper fund with an override and confirm the frozen configuration carries it; attempt an invalid value and confirm a clear rejection; attempt to change a deployed fund's cadence and confirm there is no such path.

**Acceptance Scenarios**:

1. **Given** a weekly mandate, **When** a backtest runs with the cadence overridden to monthly, **Then** the backtest result reflects monthly rebalancing (fewer decision cycles than the same run without the override).
2. **Given** a weekly mandate, **When** a paper fund is created with the cadence overridden to daily, **Then** the created fund's frozen configuration records the daily cadence and the confirmation output states it.
3. **Given** any mandate, **When** a backtest or paper-fund creation is attempted with an unknown cadence value, **Then** the command fails with a usage error naming the value and the allowed values, before any engine work starts.
4. **Given** a minute mandate (with interval and trading window set), **When** a backtest runs with the cadence overridden to daily, **Then** the run succeeds as a daily fund and the minute-only settings are not applied.
5. **Given** a daily mandate, **When** a paper fund is created with the cadence overridden to minute, **Then** the created fund is a valid minute fund using the standard interval and trading window defaults.
6. **Given** a deployed paper fund, **When** the user inspects the command-line interface, **Then** there is no option to change the deployed fund's cadence.

---

### User Story 4 - Pick the cadence in the fund builder (Priority: P2)

A user creating a fund in the terminal UI chooses the cadence from an explicit list of the four supported values, with a plain-language description of each. Choosing the minute cadence reveals the interval and trading-window steps; choosing a day-grid cadence does not. The chosen cadence is shown in the builder's summary and saved with the fund.

**Why this priority**: The builder is the primary interactive surface for fund creation; cadence must be a first-class choice there, not a hidden default. The capability exists today — this story pins it so it is protected and verified alongside the rest of the feature.

**Independent Test**: Walk the fund builder, select each cadence in turn, and confirm the summary and saved fund record the selection; select minute and confirm the interval/window steps appear.

**Acceptance Scenarios**:

1. **Given** the fund builder, **When** the user reaches the cadence step, **Then** all four cadence values are offered with descriptions.
2. **Given** the user selects `minute`, **When** they continue, **Then** the builder asks for the interval and trading window before finishing.
3. **Given** the user selects `weekly`, **When** they finish, **Then** the saved fund records the weekly cadence and the summary shows it.

---

### User Story 5 - Documentation states where cadence is set and what it means (Priority: P3)

A new user reading the project's top-level documentation can find what the rebalance cadence is, that it is set in the mandate, which values are allowed, and how to override it from the command line. The documentation matches the actual behavior — no value is documented that the engine rejects, and no accepted value is missing from the docs.

**Why this priority**: A configurable setting that isn't discoverable might as well not exist. Documentation is cheap but only matters once the behavior is right, hence the lowest priority.

**Independent Test**: Read the top-level documentation cold and, using only what it says, set a cadence in a mandate and override one from the command line successfully.

**Acceptance Scenarios**:

1. **Given** the top-level project documentation, **When** the user looks up fund configuration, **Then** the rebalance cadence field is documented with its allowed values, its default, and its meaning.
2. **Given** the documentation, **When** the user wants to override the cadence for a single backtest or paper-fund creation, **Then** the command-line option is documented.

---

### Edge Cases

- What happens when the first session of a period is a market holiday? The next observed session becomes that period's rebalance session (the rule compares consecutive observed sessions, never calendar dates).
- What happens at an ISO week / year boundary (e.g. Dec 30 → Jan 2 in the same ISO week)? They are one week; no rebalance between them.
- What happens when a fund runs its very first session? It is always a rebalance session, regardless of cadence.
- What happens when an unknown cadence value reaches the engine (not just the loader)? The engine rejects it with an error naming the value.
- What happens when a minute fund's cadence is overridden to a day-grid cadence? The minute-only settings (interval, trading window) must be dropped, not carried along — a day-grid fund cannot have them.
- What happens when a day-grid fund is overridden to minute? The standard interval and trading-window defaults apply; the result must be a valid minute fund.
- What happens when a mandate file contains a byte-order mark? Loading fails with an error naming the file (fail-loud; no silent stripping).
- What happens when a user tries to change the cadence of an already-deployed paper fund? There is no such option; deployed configurations are frozen at creation.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST accept exactly four rebalance cadence values — minute, daily, weekly, monthly — wherever a cadence is set (mandate, command-line override).
- **FR-002**: The system MUST reject any other cadence value with an error that names the offending value and the allowed values.
- **FR-003**: The system MUST default the cadence to weekly when a mandate does not state one.
- **FR-004**: The system MUST rebalance on the first session of each period for daily/weekly/monthly cadences and on every bar for the minute cadence, comparing only consecutive observed sessions (no look-ahead).
- **FR-005**: The system MUST treat a fund's first session as a rebalance session regardless of cadence.
- **FR-006**: The system MUST keep the serialization of mandates without an explicit cadence byte-identical to the current system's output, so existing ledgers remain verifiable.
- **FR-007**: The system MUST offer a command-line option to override the cadence when running a backtest and when creating a paper fund.
- **FR-008**: The system MUST apply a command-line cadence override before a paper fund's configuration is frozen, so the created fund carries the overridden cadence.
- **FR-009**: The system MUST NOT provide any way to change the cadence of an already-deployed paper fund from the command line.
- **FR-010**: The system MUST reject a command-line override to a day-grid cadence on a minute mandate in a way that leaves no minute-only settings on the resulting fund.
- **FR-011**: The system MUST accept a command-line override to minute on a day-grid mandate, producing a valid minute fund with standard interval and trading-window defaults.
- **FR-012**: The fund builder MUST offer all four cadence values as an explicit choice with plain-language descriptions, and MUST reveal interval/trading-window steps only for the minute cadence.
- **FR-013**: The example mandate shipped with the project MUST list all four supported cadence values in its cadence comment.
- **FR-014**: The top-level documentation MUST document the cadence field: allowed values, default, meaning, and the command-line override.
- **FR-015**: The system MUST validate the cadence wherever it enters the engine (mandate load, command-line override) before any trading logic runs.

### Key Entities *(include if feature involves data)*

- **Fund mandate**: The user-authored configuration of a fund. Key attributes: strategies, staff, risk limits, capital, costs, and the rebalance cadence (this feature), plus minute-only settings (interval, trading window) that belong only to minute-cadence funds.
- **Frozen fund configuration**: The snapshot of a mandate taken when a paper fund is deployed. It carries the cadence at creation time and must never drift under a live fund.
- **Session record**: The per-session ledger entry. It records whether the session was a rebalance session and a hash of the configuration in force, chaining to previous records.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A user can set each of the four cadence values in a mandate and observe the engine rebalance on exactly that rhythm in a backtest, with zero configuration outside the mandate file.
- **SC-002**: A mandate with no cadence setting produces byte-identical stored configuration and identical rebalance behavior to the current system (verified by test).
- **SC-003**: A user can override the cadence for a backtest or paper-fund creation with a single command-line option, and an invalid value is rejected before any engine work begins.
- **SC-004**: All four cadences are selectable in the fund builder, and a fund created through the builder trades on the selected cadence.
- **SC-005**: A reader of the top-level documentation can set and override the cadence using only the documentation, on the first attempt.
- **SC-006**: The full test suite passes with no new failures beyond the six documented Windows baseline failures.

## Assumptions

- **Already-built core.** Discovery verified the mandate field, spec validation, scheduler rule, and TUI picker already exist and behave as this spec requires. The delta work is: the command-line override (US3), the example-mandate comment fix (US1 scenario 5), and documentation (US5). The spec is written as end-state requirements so existing behavior is pinned by the same acceptance criteria as new behavior.
- **Drift-threshold trigger is out of scope.** The brief offered it as an optional stretch "only if it lands cleanly." It does not: it is a new engine concept (persistent target-weight state compared every session) that interacts with the decision-executes-next-session rule and the per-record configuration hash, and it would require serialization changes that risk ledger integrity. Excluded deliberately; can be specced separately later.
- **No new cadence values.** Quarterly or other cadences are out of scope; the four existing values cover the brief's examples (daily/weekly/monthly/minute-level).
- **Command-line override scope.** The override applies to `backtest` and paper-fund creation only. Ticking, running, or inspecting a deployed fund offers no cadence override — deployed configurations are frozen by design (ledger hash chain).
- **Minute via command line is allowed.** Overriding to minute on a day-grid mandate yields a valid minute fund with the standard interval and trading-window defaults — the same result as writing `rebalance: minute` alone in a mandate. This keeps flag semantics identical to mandate semantics.
- **No configuration-format version bump.** No stored serialization changes, so the existing format version stays as is.
- **Windows environment.** Tests run on Windows; the six documented baseline failures are pre-existing and out of scope.