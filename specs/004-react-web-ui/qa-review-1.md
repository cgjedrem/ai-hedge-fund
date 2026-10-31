# Independent QA 1

Reviewer: qa-reviewer, read-only. Source: b183ac7 / c552029. Date: 2026-10-30.
Verdict: **FAIL**. Static review is not runtime acceptance.

| ID | Priority | Finding | Required response |
|----|----------|---------|-------------------|
| Q1 | Important | Windows trailing-dot protected-name alias may bypass string guard | Temporary-root probe, reject ambiguous names/canonical aliases before adapter calls |
| Q2 | Important | Approval endpoint and card ignore gate/halted state | Match CLI/TUI preconditions, explicit negative tests |
| Q3 | Important | CycleRecord properties omitted from DTO; cost cards blank | Explicit canonical property fields and API/UI assertions |
| Q4 | Important | Builder overwrites library model weights/params/blend | Preserve canonical strategy semantics, regression test |
| Q5 | Important | SPA fallback rejects report `.json` and dotted-fund deep links | Asset-prefix-only 404, direct navigation/reload test |
| Q6 | Important | Web model selection persists into shared `.env` unlike TUI | Process-only selection, protect future runner configuration |
| Q7 | Important | Halt blocked by corrupt ledger replay | Validated deployment/name then existing halt adapter, corrupt-state test |
| Q8 | Important | Paid backtest lacks confirmation/cancellation | Explicit provider/model/range confirmation and safe cooperative cancellation/shutdown |
| Q9 | Important | Optional web extras break default pytest collection | Dev dependency or properly scoped import skips, minimal-install evidence |
| Q10 | Important | Chart screenshots capture no line paths | Disable chart animation, assert paths, recapture |
| Q11 | Important | Fresh-checkout one-command launcher not demonstrated on Windows | Practical documented native build/run command and verification |
| Q12 | Minor | Data client not closed, host node_modules copied into image | Context-managed lifecycle; Docker ignore hygiene |
| Q13 | Minor | Default read-only volume writable in Compose | Read-only mount consistent with default capability |
| Q14 | Minor | Request size check relies solely on Content-Length | Enforce actual streamed byte bound |
| Q15 | Minor | Report table clipped at desktop width | Visible columns or usable explicit horizontal scrolling |

## Evidence Gate

- Focused API/frontend checks were observed by implementer, not reviewer.
- Final screenshots must show chart lines and cost fields and cover direct deep links.
- Existing suite remains INCONCLUSIVE until final revision-bound results or exact blockers.
- Docker runtime and real-fund read-only browser checks remain unverified.
- Do not repeat protected-root hashing or secret/PID inspection. Do not modify real funds or control real runners.

Rework cycle 1 approved autonomously under the user's express instruction. Fix findings, then independent QA; no merge.
