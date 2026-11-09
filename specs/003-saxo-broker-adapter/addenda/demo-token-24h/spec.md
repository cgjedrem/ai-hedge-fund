# Addendum: Saxo SIM 24-Hour Token Connection

**Created**: 2026-11-08

**Status**: Read-only connection/inspection implemented; fund writes remain blocked by SIM ownership policy.

**Input**: User description: "connect a demo account on saxo bank to a fund" and "use github speckit to develop this feature - connecting demo to our existing app". The Saxo demo uses a vault-held token valid for 24 hours; both this token mode and the existing OAuth mode are SIM-only.

> **Spec lineage**: This is a non-numbered addendum to `specs/003-saxo-broker-adapter`. Keep `003` as the parent integration; do not create or select another numbered feature. `.specify/feature.json` continues to track the active web-engine migration. Both the existing OAuth credential path and this token path target Saxo SIM only; no live-account support is present or implied.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Connect to Saxo SIM safely (Priority: P1)

As a fund owner, I can use my Saxo demo credentials already held in the local secrets vault to connect the app to Saxo SIM, so I can verify demo connectivity without exposing credentials or involving a live account.

**Why this priority**: Without a safe demo connection, the fund cannot be tested against Saxo.

**Independent Test**: With a fake Saxo service and synthetic vault provider, verify success with a valid demo token, safe failure with a missing or expired token, and absence of token material in all visible output.

**Acceptance Scenarios**:

1. **Given** a valid demo token is available in the local vault, **When** the user runs the connection check, **Then** the app reports a successful Saxo SIM connection without displaying or persisting the token.
2. **Given** the demo token is missing, invalid, or expired, **When** the user checks the connection, **Then** the app reports that local re-authentication is required and submits no orders.
3. **Given** live-account credentials or a non-SIM endpoint are selected, **When** the user attempts this demo connection, **Then** the app refuses to continue.

### User Story 2 - Select and verify the target demo account (Priority: P1)

As a fund owner, I can identify the intended demo account and inspect its currency, cash, and positions before connecting a fund, so account ambiguity or an unexpected book cannot lead to an unsafe trade.

**Why this priority**: Account identity and the starting broker book must be known before any fund is linked or run.

**Independent Test**: Fake account responses cover one eligible account, multiple eligible accounts, no eligible account, a non-USD account, an account with positions, and an unavailable account service; inspection is proven read-only.

**Acceptance Scenarios**:

1. **Given** exactly one eligible demo account is available, **When** the user inspects accounts, **Then** the app presents enough information to verify its identity, currency, cash, and positions without placing an order.
2. **Given** multiple eligible demo accounts are available, **When** the user inspects accounts, **Then** the app requires an explicit account choice and does not silently select one.
3. **Given** the selected account has unsupported currency, existing positions, or unreadable balances, **When** the user attempts to prepare a fund, **Then** preparation is blocked until the mismatch is resolved.

### User Story 3 - Prepare a dedicated supervised demo fund (Priority: P2)

As a fund owner, I can connect one dedicated fund to the verified demo account and run a bounded, manually initiated test with an approval gate, while keeping existing funds and live accounts untouched.

**Why this priority**: The user's goal is to exercise the fund's automated-trading capability on a demo account, but only after connection and account checks succeed.

**Independent Test**: Using a synthetic fund root and fake broker/data services, verify account binding, initial-book reconciliation, approval-required behavior, explicit first-order authorization, bounded execution, and unchanged existing fund state.

**Acceptance Scenarios**:

1. **Given** a verified, empty demo account and a dedicated isolated fund root, **When** the user prepares the fund, **Then** the fund is bound to the explicitly selected SIM account and existing fund data remains unchanged.
2. **Given** a fresh fund ledger and verified demo account, **When** their starting cash differs by more than one cent, **Then** the app refuses to run and does not import, reset, or overwrite either book.
3. **Given** the fund is prepared, **When** an operator starts a bounded run, **Then** the run requires the configured approval and separate explicit authorization before its first demo order, and stops after the requested run.
4. **Given** a live-account endpoint, unattended schedule, or unbounded loop is requested, **When** the demo workflow is started, **Then** the request is refused.

### Edge Cases

- The 24-hour token expires during connection or account inspection; the operation fails closed and asks for local re-authentication.
- Account inspection returns duplicate, incomplete, or contradictory account data; no account is selected and no fund is prepared.
- The selected account is reset or changed after preparation; reconciliation refuses to trade.
- The demo account has positions, non-USD cash, or cash that does not match the new fund's starting capital; the fund remains blocked.
- The secrets vault is locked, unavailable, or lacks permission to read the token; no token value is requested in chat or written to local files.
- The app is interrupted during a bounded run; it does not automatically resume or resubmit an uncertain order.
- Existing paper funds share local storage; the demo fund must use a supported isolated location and must not alter their mandate, ledger, cache, or runner state.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The demo-token connection MUST communicate only with Saxo SIM and MUST refuse any live-account configuration. The existing OAuth route is also SIM-only; no live-account mode is supported.
- **FR-002**: The user MUST be able to reference the Saxo demo's 24-hour token from the local secrets vault without placing its value in chat, source code, logs, fund files, or ledger records.
- **FR-003**: Demo-token authentication MUST remain distinct from the existing SIM OAuth flow; conflicting or ambiguous credential modes MUST fail closed.
- **FR-004**: A missing, rejected, or expired demo token MUST produce a safe re-authentication error and MUST NOT result in an order attempt.
- **FR-005**: The user MUST be able to inspect eligible demo accounts and verify the selected account before a fund is connected.
- **FR-006**: When more than one eligible demo account exists, the app MUST require an explicit account selection rather than silently choosing the first match.
- **FR-007**: Account inspection MUST be read-only and MUST NOT submit, modify, or cancel orders.
- **FR-008**: Before a demo fund can run, the selected account MUST be confirmed as the intended demo account and its supported currency, cash, and positions MUST be reconciled.
- **FR-009**: Any new demo fund MUST use the application's explicit root and pass its normal root write-admission policy; it MUST NOT share writable fund state with existing funds or services. Root admission alone MUST NOT be treated as proof of exclusive control over a Saxo SIM account.
- **FR-010**: A fresh demo fund MUST start with no positions, and its configured starting cash MUST match the selected account's cash within $0.01; the app MUST refuse mismatches without importing, resetting, or overwriting either book.
- **FR-011**: The initial demo fund MUST require an approval gate, and the first demo order MUST require separate explicit operator authorization after account and fund settings are verified.
- **FR-012**: Demo execution MUST be manually initiated and bounded to the requested run; unattended schedules and unbounded trading loops are out of scope.
- **FR-013**: Existing paper funds and their persisted records MUST remain unchanged by demo connection, inspection, setup, and execution.
- **FR-014**: Connection and inspection failures MUST be visible to the operator, while secrets and sensitive authentication material remain redacted.

### Key Entities *(include if feature involves data)*

- **Demo credential reference**: A local vault reference to the short-lived token required for Saxo's demo environment; the token value is secret and is never part of fund state.
- **Demo account**: A Saxo SIM account identified explicitly by the operator and characterized by currency, cash, and positions.
- **Dedicated demo fund**: A fund configuration and ledger isolated from other funds and bound to one verified demo account.
- **Bounded demo run**: A manually initiated execution attempt with an approval gate, a separate first-order authorization, and a defined stopping point.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A user can verify a successful or failed demo connection without any token value appearing in output, logs, or persisted fund records.
- **SC-002**: Every successful or failed account inspection leaves the broker's orders unchanged.
- **SC-003**: When multiple eligible accounts are returned, 100% of attempts require an explicit selection before fund preparation.
- **SC-004**: Any unsupported account, book mismatch greater than $0.01, or unverified account identity blocks execution before the first order.
- **SC-005**: Demo setup and bounded runs affect only the selected SIM account and dedicated demo fund; existing funds and live accounts remain untouched.
- **SC-006**: The user can authorize the first demo order only after reviewing the verified account and fund settings.

## Assumptions

- The user has a Saxo SIM account and has placed its 24-hour demo token in a local secrets-vault field; the value is never pasted into chat.
- The runtime 1Password delivery work does not itself grant Saxo account ownership. Saxo mutation remains fail-closed while exclusive SIM account control is unverifiable.
- The existing Saxo broker adapter and fund application are reused where safe; demo token handling does not replace the existing SIM-only OAuth path.
- The demo account is dedicated to this test and has no positions or concurrent manual/fund activity at initial reconciliation.
- The fund uses supported US/USD instruments and the app's existing market-data and minute-cadence constraints.
- No real-money trading, paid-data calls, unattended live-data loops, or automatic schedule is needed to validate this feature.
- If root admission or the separate SIM account-ownership gate denies a demo fund operation, deployment and execution remain blocked; neither control is bypassed.
