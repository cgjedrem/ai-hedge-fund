# Research: Saxo Demo Account Connection

## R1 - Demo credential mode

**Decision**: Add a separate reference to the user's Saxo-issued 24-hour SIM token. Treat it as an opaque bearer credential for demo-only requests; do not refresh it, exchange it, or fall back to the existing OAuth flow. Preserve the existing OAuth implementation for its existing SIM-only route; no live-account support is present or implied.

**Rationale**: The user confirmed the vault field contains a token valid for the Saxo demo account and distinguished that from the existing SIM OAuth path. The current broker factory requires app-key, app-secret, and refresh-token references, while the token manager expects a rotating OAuth refresh response. A distinct credential mode avoids misinterpreting the demo token or changing existing SIM OAuth behavior. The user-reported token type and lifetime are not independently verified; implementation must fail closed if Saxo rejects it.

**Alternatives considered**:
- Continue requiring SIM OAuth for the demo-token workflow: rejected because it does not support the user's stated demo credential flow.
- Reuse the existing SIM OAuth refresh-token field for the 24-hour token: rejected because the broker posts it as an OAuth refresh token and writes back rotated values.
- Automatically fall back from one mode to another: rejected because it can obscure which account and credential mode are in use.

## R2 - Read-only connection and account inspection

**Decision**: Expose a read-only demo connection/account inspection flow that reports enough sanitized information for an operator to identify an eligible account, verify currency, cash, and positions, and choose one explicitly. Ambiguous account results must require a selection.

**Rationale**: Existing Saxo account discovery selects the first eligible active USD Stock account, which is not sufficient for a supervised connection to an explicitly chosen demo account. Preserve that selection only for legacy SIM OAuth mandates; the new demo-token mode requires explicit account binding. Existing SIM OAuth broker reads can refresh OAuth as a side effect; the new demo mode must not mutate orders or account state. Authentication failure and ambiguous or incomplete broker responses must remain visible and fail closed.

**Alternatives considered**:
- Silently use the first eligible account: rejected because multiple SIM accounts may exist.
- Use an order submission as a connectivity test: rejected because a connection check must be read-only.

## R3 - Dedicated fund root and write admission

**Decision**: Keep demo fund files in an explicitly selected root and route every write through existing root-admission controls. Do not alter `HOME`, use the shared default root as a shortcut, or bypass admission. Root admission is separate from Saxo SIM account ownership; the target's `require_sim_account_ownership()` currently fails closed with `ownership-unknown`. Stop before any fund mutation unless both controls authorize it.

**Rationale**: PR #8 provides explicit root selection and normal root admission. Existing fund state and other running services must not be changed by this demo setup. Local file authority does not prove exclusive control of the remote SIM account.

**Alternatives considered**:
- Deploy in the shared default root: rejected because it could overlap existing funds or active services.
- Change process `HOME` or directly call internal deployment APIs: rejected because it circumvents the supported application/admission path.
- Treat root admission as proof of exclusive SIM custody: rejected because independent processes may mutate the same broker account.

## R4 - Supervised demo execution

**Decision**: Require a verified SIM account, a fresh empty fund ledger with cash matching the account within $0.01, an approval gate, separate operator confirmation before the first order, and a manually initiated bounded run. No schedule or unattended loop is part of this feature.

**Rationale**: The user wants to evaluate automated-trading capability on demo, not authorize real-money or unattended operation. Broker reconciliation is authoritative and must not silently import or reset positions/cash.

**Alternatives considered**:
- Automatically adopt broker positions or adjust mandate capital: rejected because it hides the starting book and changes the fund's mandate.
- Start an unattended runner after setup: rejected because execution needs bounded operator supervision.

## R5 - Verification

**Decision**: Validate credential resolution, redaction, account selection, read-only behavior, admission, and bounded execution with fake transports and synthetic roots. Do not make network calls, read the user's vault token, invoke paid data/model services, or place a demo order in development tests.

**Rationale**: These checks are deterministic and avoid exposing credentials or mutating broker state. A later user-authorized read-only SIM inspection is separate runtime evidence; unit tests do not establish that the user's token is valid.

**Alternatives considered**:
- Use the user's token in a development smoke test: rejected because no credentialed request is authorized and tests must not disclose secrets.
- Treat fake-transport tests as proof of actual Saxo connectivity: rejected because they cannot validate token provenance or account state.
