# Saxo SIM Connection Contract

## Purpose

Define the user-facing behavior for connecting with the vault-held 24-hour demo token and inspecting a Saxo SIM account. This flow is read-only and is not an order-placement or fund-deployment authorization.

## Configuration contract

- The user provides a vault reference to the Saxo SIM token using a dedicated demo credential setting.
- The token value is never accepted from command-line arguments, written to application config, printed, or included in errors.
- The existing SIM-only OAuth references remain separate; configuring both credential modes is an error.
- The demo mode can only address the SIM service.
- Neither credential mode supports live-account endpoints.
- Demo-token clients reject non-GET requests before token resolution or transport.

## Inspection behavior

1. Resolve the token from the local vault only when an inspection starts.
2. Read eligible account identity, currency, cash, and positions using broker read operations.
3. If no eligible account is found, report a safe actionable error.
4. If exactly one candidate is found, show enough sanitized attributes for operator verification.
5. If several candidates are found, require an explicit account choice; do not use first-match selection.
6. Never submit, modify, or cancel an order during inspection.
7. On missing/rejected/expired token or incomplete broker response, stop and report failure without exposing the token or raw secret-bearing response.

## Fund and execution boundary

- Inspection alone does not create or alter a fund.
- Fund preparation requires an explicitly selected SIM account, a root accepted by normal write admission, verified exclusive SIM account ownership, and successful initial-book reconciliation.
- A first demo order requires the approval gate and separate explicit operator confirmation after reviewing the target account and fund settings.
- Execution is manually started and bounded; no live account, schedule, or unattended run is allowed by this contract.
- If either normal root admission or the SIM account-ownership gate denies an operation, deployment is blocked. No alternate write path is permitted.
