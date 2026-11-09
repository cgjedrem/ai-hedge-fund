# Data Model: Saxo Demo Account Connection

## Demo credential reference

- **Purpose**: Identifies a local secrets-vault field containing the short-lived Saxo SIM token.
- **Fields**:
  - Vault reference: required `op://` locator; not itself an authentication secret.
  - Token value: resolved only at request time, held in memory, and never serialized to fund or ledger data.
  - Credential mode: explicitly `demo-token` or existing SIM-only `oauth`; the modes cannot be combined or inferred from partial configuration.
- **Validation**:
  - Demo token reference must be a non-empty vault reference.
  - Missing, invalid, expired, or rejected credentials fail closed.
  - No refresh-token write-back or OAuth fallback occurs in demo-token mode.

## Demo account binding

- **Purpose**: Fixes a dedicated Saxo SIM fund to the account an operator verified.
- **Fields**:
  - Environment: SIM only.
  - Account identity: explicit identifier selected after read-only inspection.
  - Currency: must match the fund's supported base currency.
  - Starting cash: broker-reported accounting cash.
  - Starting positions: broker-reported position set.
- **Validation**:
  - Multiple candidate accounts require explicit selection.
  - Incomplete, contradictory, unreadable, unsupported, or changed account state blocks preparation or execution.
  - A fresh fund requires no starting positions and cash within $0.01 of mandate capital.

## Dedicated demo fund

- **Purpose**: Holds one fund mandate and ledger without sharing writable state with existing funds.
- **Fields**:
  - Fund identity and mandate.
  - Explicit isolated root.
  - Broker selection: Saxo SIM.
  - Bound demo account identity.
  - Approval-required setting: enabled for initial testing.
- **Validation**:
  - Root writes must pass the existing runtime write-admission policy.
  - Saxo SIM mutation also requires verified exclusive account ownership; the current implementation reports `ownership-unknown`.
  - No existing ledger, mandate, or position import/reset is performed to resolve a mismatch.
  - Failure of either gate blocks deployment rather than granting an exception.

## Bounded demo run

- **Purpose**: Represents an operator-initiated test run against the bound SIM account.
- **Fields**:
  - Verified account and fund settings.
  - Operator approval state.
  - Separate first-order authorization state.
  - Explicit stop boundary for the requested run.
- **State transitions**: `prepared` -> `approved` -> `authorized-for-first-order` -> `running` -> `stopped`; any credential, root-admission, account-ownership, reconciliation, or interruption failure transitions to a stopped/blocked state.
- **Validation**:
  - No transition to `running` until account, fund, approval, and first-order authorization checks pass.
  - No automatic restart or retry of an uncertain order after interruption.
