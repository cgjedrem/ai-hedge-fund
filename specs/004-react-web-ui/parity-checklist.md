# TUI parity checklist

React desk supplements the Textual TUI. TUI entry points and screens remain intact.
This checklist records web availability, not a retirement decision.

| Workflow | Web status | Boundary / gap |
|---|---|---|
| Workspace overview and local capability status | Available | Recorded local totals; no live quotes |
| Mandate list and canonical detail | Available | Corrupt files remain visible as errors |
| Mandate builder | Available | Preserves server-catalog strategy IDs, weights, params and blend policy; canonical FundSpec validation |
| Paper-fund list and detail | Available | Ledger replay; positions and marks are recorded values |
| Next-run forecast and NAV/benchmark curve | Available | Schedule forecast only; no runner status probe |
| Holdings and session history | Available | Reads verified records; session reports keep executed and proposed data separate |
| Order/fill and cost report | Available | Explicit cost DTO fields; horizontally scrollable, keyboard-accessible tables |
| Strategy and analyst scorecard | Available | Uses canonical scorecard output |
| Research reports and bounded backtests | Available | Confirmation shows provider/model/agent count/tickers/range; separate startup write and network capabilities; cancellation is cooperative at valuation boundaries |
| Approval / rejection | Available | Only approval-required, non-halted funds accept verdicts; exact displayed `decision_as_of` and source hash sent to existing mailbox; stale requests conflict |
| Halt / resume | Available | Halt validates contained deployment identity without replaying corrupt events; resume still requires valid ledger replay; no runner process control |
| Model selection and provider credentials | Available | Model selection is process-only and frozen per job; credential entry is write-only; settings reveal presence only |
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
- Fund names reject Windows trailing-dot/space aliases and reserved device names.
- Missing `/assets/*` returns 404; SPA routes fall back to `index.html`; unknown API routes stay JSON errors.
- Packaged wheels include the production static bundle; source builds require Node.js and npm.
- Per-fund API locks are process-local; they do not coordinate with an external TUI or runner.
- The React desk does not replace the TUI or authorize real-money trading.
