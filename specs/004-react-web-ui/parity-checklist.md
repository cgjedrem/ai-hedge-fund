# TUI parity checklist

React desk supplements the Textual TUI. TUI entry points and screens remain intact.
This checklist records web availability, not a retirement decision.

| Workflow | Web status | Boundary / gap |
|---|---|---|
| Workspace overview and local capability status | Available | Recorded local totals; no live quotes |
| Mandate list and canonical detail | Available | Corrupt files remain visible as errors |
| Mandate builder | Available | Uses registered strategies/analysts and canonical FundSpec validation |
| Paper-fund list and detail | Available | Ledger replay; positions and marks are recorded values |
| Next-run forecast and NAV/benchmark curve | Available | Schedule forecast only; no runner status probe |
| Holdings and session history | Available | Reads verified records; session reports keep executed and proposed data separate |
| Order/fill and cost report | Available | Shows persisted execution fields only |
| Strategy and analyst scorecard | Available | Uses canonical scorecard output |
| Research reports and bounded backtests | Available | Backtests need explicit startup write and network capabilities |
| Approval / rejection | Available | Exact displayed `decision_as_of` and source hash sent to existing mailbox; stale requests conflict |
| Halt / resume | Available | Ledger state only; does not control a runner process |
| Model selection and provider credentials | Available | Write-only credential entry; settings reveal presence only |
| Command palette and keyboard navigation | Available | Ctrl/Command+K; editable fields retain focus |
| Runner start / stop | Deferred | Ownership cannot be proven; controls stay disabled |
| Manual fund run | Deferred | Web process does not own the runner lifecycle |
| Delete fund/report | Deferred | Destructive history mutation is not exposed |
| Ledger redo | Deferred | Replay/redo is not exposed in the browser |
| Live valuation | Deferred | Web process does not fetch live market data; value remains explicitly unavailable |

## Safety posture

- Default server is loopback-only, read-only, and network-off.
- Demo launcher uses synthetic data in a temporary directory.
- Protected fund names remain read-only when general writes are enabled.
- Per-fund API locks are process-local; they do not coordinate with an external TUI or runner.
- The React desk does not replace the TUI or authorize real-money trading.
