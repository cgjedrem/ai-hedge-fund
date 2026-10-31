# Research: Complete web-only engine migration

**Date:** 2026-10-31. **Basis:** supplied discovery at main `6443490`, static repository
inspection at `24fbf1f`, three sequential QA lens reports. No external research/provider
calls, runtime tests, funds or credentials accessed. No timing/acceptance evidence inferred.
The [forward contract](../../docs/governance/web-migration-contract.md) is normative.

## Decisions, rationale and alternatives

| Decision | Rationale / evidence | Alternatives considered |
| --- | --- | --- |
| Canonical Python engine with thin FastAPI/React adapters | Discovery `paper\tick`, `pipeline\session`, ledger/fund/backtesting are authority; existing React presentation remains | Browser scheduling/trading logic duplicates invariants; reject. |
| Neutral runtime/reporting helpers before TUI retirement | Discovery lists CLI/web/check_stock/test imports from TUI; manifest still requires Textual | Delete TUI first breaks headless imports/assertions; retaining hidden Textual dependency fails retirement. |
| Explicit launch-fixed root + exact dotenv + child allowlist | LB1 confirms CWD/global-path propagation gap | CWD/env root precedence or upward dotenv search may access real state; reject. |
| OS locks plus durable root/deployment journals | LM1 confirms PID check/write and "participating" loophole | In-process locks or expiring JSON lease alone cannot prevent duplicate execution. Use kernel lock release, but require financial recovery after crash. |
| Root registry / runner reservation / session lease / control lane | Short scoped locks keep unrelated funds, verdict and Halt responsive | Whole-runner global lock monopolizes lifecycle/research/control; per-web lock excludes headless. |
| Offline legacy handover, unknown ownership denies all mutations | Old binaries ignore new protocol; markers cannot fence them | Auto-adopt PID or silently upgrade/restart creates unfenced owners; reject. |
| Host writable driver; container observer only | LM2/LB2: shared host/container mount with separate PID namespaces; compose autorestart/TUI/ttyd still shipped | Cross-namespace signals or shared writable root unsupported; no container proxy added. |
| Detached verified owner/control channels per OS | HM4: POSIX-oriented PID stop lacks Windows evidence | Raw PID kill risks unrelated process; emulate Windows success via Linux tests is invalid. |
| Durable request/token/config/reconciliation sidecars | HM4/HM5: reload/restart and post-fill loss cannot depend on browser/memory status | Change old SessionRecord schema or auto-retry risks replay/duplicate effects; reject. |
| Replay plus explicit post-fill reconciliation | LM3: fills may precede failed append | Valid chain does not prove absence of unrecorded effects; replay-only Resume unsafe. |
| Expiring single-use digest, exact head/due-set and finite backlog | LM4/HM5: review can become stale; restored runner may catch up indefinitely | Confirmation of name alone silently changes submitted work; reject. |
| Frozen settings and private credential versions, surgical deletion | LB4: active work must retain private capture; Windows mode analogy not proof | Hot swap/credential echo/global dotenv breaks reproducibility and privacy. |
| Free default; cloud class explicit; finite free/local runner; per-call paid caps | HM1–3: old factory defaults paid, keyless cloud is not local; old constitution conflicts | Key/env implied authorization or paid scheduled loops prohibited. Free yfinance dependency must be available for supported free default during implementation. |
| Web local-paper only; exclusive SIM account binding and headless exception | LM5: account control differs from deployment ledger ownership | Pretend SIM readiness grants web control or duplicate across roots unsupported. Restrict authority until exclusive account handover verified. |
| HTTPS host-bound remote credentials; literal-loopback local model | LB3: endpoints can redirect secrets or reach metadata/private resources | URL regex alone cannot stop DNS/redirect escapes; authorized dispatch must pin/recheck addresses/TLS. |
| Local NTFS/ext4 only | LB5: locks/rename/identity need actual filesystem guarantees | UNC/SMB/NFS/cloud-synced unknown roots denied, not covered by "same path". |
| Reversible scoped archive and distinct replacement | FR-041–043 retain history/immutable snapshots | Broad wipe/overwrite excluded. |
| Existing frontend Vitest/Playwright/build, existing pytest/lint | `frontend\package.json` declares test/e2e/build; pyproject pytest/black/isort/flake8 | No new testing framework planned. Declaration is not availability/pass evidence. |
| User-directed doc-only governance amendment now | HM1 and express user authority; historical spec requires proposal but now superseded forward | Blanket baseline waiver or false suite pass forbidden; runtime gate unchanged. |

## Evidence authority and open implementation risks

Static reviewed seams are identified in discovery, supplemented by QA readings of runner/
tick/ledger/provider/credential/compose source, and direct Makefile/package/catalog/setup
inspection. Line references belong to those revisions, not promises about future source.
Main fetched to `6443490` with no commits missing from this branch at inspection.

Design unknowns are settled above; no unresolved clarification marker remains. Implementation
feasibility still needs actual OS locks/incarnation/ACL/stop evidence, DNS dispatch enforcement,
cost upper-bound accuracy, append-failure reconciliation, package assets and browser behavior.
If a required primitive/platform is unavailable, deny capability and keep acceptance blocked.
Discovery's historical Linux/PR7 counts and baseline failure list are not fresh evidence.
No claim that Linux runtime is available was made or tested here.

## Scope trace strategy

Use FR-001–062 explicitly (trace tooling defaults to REQ, so do not silently lose IDs).
Each discovery A01–F13 row maps to requirement, replacement assertion, actual source/
fixture/platform result and pass/fail/blocked status. Keep SIM browser exemption separate
from local-paper acceptance; retain headless console/stdout/output-file and daily-grid
intraday research exceptions. Docker ttyd/TUI/compose/Make/helper import closure supplements
the 74 product rows. Retirement requires all mandatory non-exempt rows and platform results.

## Planning validation receipt

Observed on Windows at `2026-10-31T15:01:40.9607240+01:00`, source base `24fbf1f`
plus the nine planning artifacts (before commit):

- UTF-8/no BOM, all local Markdown links, no unresolved placeholders/tasks and all 15
  finding IDs: PASS by a read-only inline validator.
- Historical spec/discovery/checklist Git blob hashes unchanged: PASS using Git's checkout
  filters. Initial raw worktree-versus-blob byte comparison failed because checkout newline
  representation differs; it was not evidence of a historical edit. The corrected hash
  check and clean historical diff establish repository-content preservation.
- Initial tracked `git diff --check`: PASS. Staging subsequently exposed Markdown hard-break
  trailing spaces in two new files; those were removed and the complete staged check rerun
  before commit. Existing/new PR lookup for this head returned no PR; no PR
  template was found under tracked repository paths.
- Origin main fetched as `6443490db64056742fbbe6a18abf92c903c10861`, ancestor of HEAD
  with zero missing main commits. Final publication rechecks this.

This receipt is documentation validation only. No runtime suite/build/browser/Linux/Docker/
provider/fund/credential test result is claimed.
