# TUI parity checklist

**NOT full parity. Do not retire the TUI.** React desk remains an additive, safety-bounded subset; TUI entry points and screens stay intact.

| Workflow | Web status | Boundary / gap |
|---|---|---|
| Workspace overview and local capability status | Available | Recorded local totals; no live quotes |
| Mandate list and canonical detail | Available | Corrupt files remain visible as errors |
| Mandate builder and revision editor | Partial | Simple builder creates canonical mandates; full JSON create/edit/clone supports revision-bound validated fields and canonical rename. Deployment snapshots remain immutable. Complete browser, Linux/ext4 and migration acceptance remain open under T141. |
| Paper-fund list and detail | Available | Ledger replay; positions and marks are recorded values |
| Next-run forecast and NAV/benchmark curve | Available | Schedule forecast only; no runner status probe |
| Holdings and session history | Available with boundaries | Reads verified records; session history now has bounded stable cursor/search pages over the full ledger. Session reports keep executed and proposed data separate. |
| Order/fill and cost report | Available | Explicit cost DTO fields; horizontally scrollable, keyboard-accessible tables |
| Strategy and analyst scorecard | Available | Uses canonical scorecard output |
| Research reports and bounded backtests | Available with boundaries | Saved research and verified paper-session histories use bounded stable cursor/search pages. Backtest confirmation shows provider/model/agent count/tickers/range/mandate hash; cancellation cannot interrupt in-flight provider/session work. Report drilldown/export parity and full migration acceptance remain open under T146. |
| Approval / rejection | Available with stricter web guard | Hash-bound mailbox; stale, consumed and expired verdict targets reject with 409. Extra fail-closed check is intentionally stricter than the TUI's direct snapshot-to-mailbox action. |
| Halt / resume | Available | Halt validates contained deployment identity without replaying corrupt events; resume still requires valid ledger replay; no runner process control |
| Model selection and provider credentials | Available | Model selection is process-only and frozen per job; credential entry is write-only; settings reveal presence only |
| Command palette and keyboard navigation | Available | Ctrl/Command+K; editable fields retain focus |
| Runner start / stop | Deferred | Ownership cannot be proven; controls stay disabled |
| Manual fund run | Deferred | Web process does not own the runner lifecycle |
| Delete / replace fund or report | Deferred | No browser delete or replace route; destructive history mutation is not exposed |
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

## Final blocker status — 2026-11-01

- **PARTIAL; NOT READY TO MERGE.** This React desk remains additive; no TUI assertion, dependency or entry point was retired.
- T015/T021 handover and unaware-writer integration remain partial. T137/T138/T140/T142–T145/T147/T148 remain open; T139/T141/T146 have bounded partial evidence but stay unchecked.
- Full Python suite is **INCONCLUSIVE** after prior stalls at 149/1,207 collected. Native Linux/ext4 and actual NTFS ACL acceptance are **BLOCKED**. Wheel build passed; installed-wheel runtime smoke remains **INCONCLUSIVE**.
- No production-write, paid/headless provider, broker-execution or container surface is enabled by this closure. Local/free policy checks do not establish full migration acceptance.
