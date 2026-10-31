# Independent QA 2

Reviewer: qa-reviewer, read-only current-source review of 1639720. Date: 2026-10-30.
Verdict: **FAIL** pending the concrete residual defects below. Most first-review findings are fixed in source.

| ID | Priority | Discriminating evidence | Required response |
|----|----------|-------------------------|-------------------|
| R1 | Important | Cost cards call money() defaulting to zero decimals; fractional example 0.5/4.5 renders inconsistent totals | Two-decimal cost display and explicit fractional assertions |
| R2 | Important | Library analyst roster can be subsetted while retaining canonical library name/blend | Whole library strategies or canonical named custom sleeve; server-side validation and tests |
| R3 | Important | session_report uses Ledger.read without chain verification; parity text says verified records | Verify ledger before single-session report, corrupt/tampered negative test |
| R4 | Important | Parity doc lacks explicit NOT full parity declaration and builder/custom limitations | Accurate checklist and retirement guidance |
| R5 | Evidence | Runtime repair rows name a421497+dirty hash, not source commit 1639720 | Final-commit-bound rerun or independently demonstrated content identity |
| R6 | Evidence | Earlier npm critical audit report unattributed; reviewer metadata checks inconclusive | Actual production/full npm audit with advisory IDs, targeted remediation when applicable |

## Adjacent Issues

- Backtest confirmation only binds analyst count; bind full mandate hash to avoid same-count changes.
- Corrupt-ledger snapshot should still read independent halted control state.
- Web's stricter consumed/expired verdict rejection must be documented relative to CLI/TUI.
- Cooperative cancellation may wait for an ongoing provider/session step; document latency and shutdown policy.

## Rework Authorization and Stop Conditions

Cycle 2 repair is based on new discriminating source evidence, not repeated speculative patching. Fix R1-R4 and applicable boundary issues, then capture current-source runtime evidence and independent final QA. Do not claim npm advisories from guesses. Do not mutate real funds or inspect secret/PID contents. Real-fund browser reads and live preview remain execution-specialist responsibilities.
