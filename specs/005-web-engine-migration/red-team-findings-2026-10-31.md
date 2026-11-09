# Red-team findings — complete web engine migration

**Session:** RT-005-web-engine-migration-2026-10-31

**Target:** [spec.md](spec.md), historical record at `24fbf1ff3eda4b92e0097859ec2279ef6ba49a79`

**Date:** 2026-10-31 (user-supplied planning date; not a runtime observation time)

**Maintainer:** operator, with expressly delegated autonomous resolution

**Supporting context:** discovery, constitution, catalog and narrowly inspected repository source

**Selection:** auto, all three catalog lenses, evaluated sequentially by `qa-reviewer` as requested

**Wall-clock:** per-lens start/end clocks were not recorded; duration unavailable, not inferred.

## 1. Session summary

The user supplied 15 static findings. Three separate sequential `qa-reviewer` invocations
evaluated and confirmed the gaps against the historical spec, with targeted source inspection.
These are not 15 newly discovered runtime vulnerabilities. Five CRITICAL, eight HIGH and
two MEDIUM findings; five retained per lens, none dropped, no failed lens.

No tests/builds/servers/provider calls/fund operations ran. Protected names and port 8765
were read only as repository text, never accessed as resources. Reviewer prose claiming
"no commands" is interpreted as no runtime validation: reviewers did use read/search tools.
No clock, platform pass, exploit or financial effect is fabricated.

The constitution lacks a red-team trigger section, so bootstrap uses all six categories.
Money/valuation, LLM, immutable/hash-chained records, approvals and interface/schema keywords
match; `regulatory_path` is added by judgment because credential/broker/local capability and
audit boundaries bear the concern, not because a statutory compliance claim was established.
Keyword-matched categories were not removed.

| Catalog lens | Trigger coverage | Weight | Bound | Actual reviewer order |
| --- | --- | --- | --- | --- |
| ledger-and-money | money_path, immutability_audit | 10 | 5 | 1 |
| local-boundary | contracts, regulatory_path | 9 | 5 | 2 |
| human-and-model-control | multi_party, ai_llm | 10 | 5 | 3 |

All findings are resolved as forward **spec-fix** design commitments under user-directed
autonomy, not runtime-closed fixes. HM1 uses the expressly authorized governance-amendment
path. No accepted-risk or out-of-scope classification hides a missing safety requirement.
Existing spec/discovery/checklists were not edited during resolution.

## 2. Findings

Downstream references below point to normative clauses in the forward
[web migration contract](../../docs/governance/web-migration-contract.md), not to edits in
historical records. The new plan consumes those resolutions only after this resolution phase.

| ID | Lens | Severity | Historical location | Static gap / suggested resolution | Status / downstream clause |
| --- | --- | --- | --- | --- | --- |
| LM1 | ledger-and-money | CRITICAL | FR-007/008/013/062, SC-003 | "Participating" admission excludes legacy writers; lease scope/recovery undefined. All writers share locks/journals, unknown legacy denies mutation; verified handover/recovery. | spec-fix: A1–A5 |
| LM2 | ledger-and-money | CRITICAL | FR-005/008/012/044, A02/A07 | Shared host/container root and PID-only ownership cannot fence namespaces; compose auto-restarts protected-name runners and ships TUI/ttyd. Host writer/read-only observer only; retire legacy services, no auto-start/restart. | spec-fix: R4/R5, A4 |
| LM3 | ledger-and-money | HIGH | FR-036/037/039, US3 AS3/5 | Replay can pass after unrecorded fills; halt alone does not reconcile them. Require explicit reconciliation provenance before Resume. | spec-fix: O4/O5 |
| LM4 | ledger-and-money | HIGH | FR-010/014/042, US1/4 | Manual/start review lacks exact head/due-set identity; restored backlog can be unbounded. Digest/revalidate due-set and bounded catch-up; restore stays stopped. | spec-fix: O1/O2, G3 |
| LM5 | ledger-and-money | HIGH | FR-027/038/042/043, US6 AS5 | SIM account may bind multiple deployments; full web SIM control unsafe. Exclusive account binding and explicit local-paper-only web exemption. | spec-fix: G4 |
| LB1 | local-boundary | CRITICAL | FR-006/022, Assumption 5 | Root can derive from CWD/environment/dotenv and leak into children. Explicit fixed launch root; exact dotenv and allowlisted child environment; configuration precedence grants no capability. | spec-fix: R1/R2 |
| LB2 | local-boundary | HIGH | FR-005/053 | Container read-only versus writable role and internal non-loopback bind carveout unspecified. Read-only observer only, exclusively host-loopback mapped bind. | spec-fix: R4/R5 |
| LB3 | local-boundary | HIGH | FR-020/025/054 | URL checks omit credential destination and metadata/private address controls. HTTPS host-bound remote credentials; literal-loopback local models; dispatch DNS/TLS/redirect guards. | spec-fix: R6/G2 |
| LB4 | local-boundary | MEDIUM | FR-021/023/059 | Key deletion/captured versions/status and Windows ACL evidence undefined. Surgical delete, active capture semantics, private modes/ACLs; unsupported evidence blocked. | spec-fix: C1 |
| LB5 | local-boundary | MEDIUM | FR-006/007/040 | Network filesystem locking/identity guarantees unspecified. Tested local NTFS/ext4 only; network/unknown filesystems unsupported. | spec-fix: R3 |
| HM1 | human-and-model-control | CRITICAL | FR-026/061/062, Constitution II/III/V/Governance | Amendment requires green suite while conflicting TUI/unattended requirements block migration; baseline list too broad. User-directed doc amendment now, free/local bounded exception, individual baseline proof, platform gates preserved. | spec-fix: G1/G3, amended constitution |
| HM2 | human-and-model-control | CRITICAL | FR-004/019/022/024/025 | Old paid default plus environment/key presence may imply authorization; keyless/cloud models misclassified. Intentional free-default incompatibility, explicit per-invocation paid policy, all cloud LLMs paid class. | spec-fix: G2 |
| HM3 | human-and-model-control | HIGH | FR-025/026/047 | Continuing runner authorization/backtest spend lacks finite scope and cap. Free/local scheduled bounds; advisory estimate and enforced per-call budget. | spec-fix: G3 |
| HM4 | human-and-model-control | HIGH | FR-008/011/012/016/017 | PID stop/process lifetime platform ambiguity and memory-only request deduplication. Verified detached groups/control channel, durable request states interrupted after restart, no auto-resume. | spec-fix: A4/O5 |
| HM5 | human-and-model-control | HIGH | FR-007/017/035/036/041/055 | Confirmation replay/expiry/digest unspecified; active approval may execute later; manual conflict and provenance unclear. Single-use digest, active-runner warning, deny manual, sidecar provenance. | spec-fix: A2/O1/O3/O5 |

## 3. Resolutions log

Each resolution was chosen by the executing planner under the user's express autonomy;
reviewers assessed gaps before the forward contract existed and did not re-review implementation.

| ID | Category | Forward reference | Resolution authority / verification |
| --- | --- | --- | --- |
| LM1 | spec-fix | contract §3 A1–A5 | User required all-writer admission; static clause presence checked; runtime pending. |
| LM2 | spec-fix | contract §2 R4/R5; §3 A4 | User chose host writer/read-only container; compose/source changes deferred. |
| LM3 | spec-fix | contract §4 O4/O5 | User required reconciliation beyond replay; runtime pending. |
| LM4 | spec-fix | contract §4 O1/O2; §1 G3 | User required exact review/bounded backlog; runtime pending. |
| LM5 | spec-fix | contract §1 G4 | User explicitly changed SIM browser scope; no web parity claimed. |
| LB1 | spec-fix | contract §2 R1/R2 | User fixed root/capability precedence; runtime pending. |
| LB2 | spec-fix | contract §2 R4/R5 | Explicit observer/bind exception, no cross-namespace authority. |
| LB3 | spec-fix | contract §2 R6; §1 G2 | Host-bound HTTPS/local-loopback rules, runtime DNS proof pending. |
| LB4 | spec-fix | contract §5 C1 | Deletion/version/ACL denial and blocked evidence preserved. |
| LB5 | spec-fix | contract §2 R3 | Only tested local filesystems; network unsupported. |
| HM1 | spec-fix (governance amendment) | constitution Governance; contract §1 G1/G3 | User authorized amendment now; no fabricated suite pass. |
| HM2 | spec-fix | contract §1 G2 | Explicit compatibility break and cloud class. |
| HM3 | spec-fix | contract §1 G3 | Scoped expiry/session/resource limits and pre-call cost cap. |
| HM4 | spec-fix | contract §3 A4; §4 O5 | Detached verified control and durable interruption. |
| HM5 | spec-fix | contract §3 A2; §4 O1/O3/O5 | Preview/dedup/approval warning and old-ledger-safe sidecars. |

No recent analyze report is present in the feature inputs; no overlap substitution was made.
This is not designated a dogfood protocol-codification session, so no dogfood decision is invented.

## 4. Session metadata

```yaml
session_id: RT-005-web-engine-migration-2026-10-31
target: specs/005-web-engine-migration/spec.md
source_revision: 24fbf1ff3eda4b92e0097859ec2279ef6ba49a79
date_basis: user-supplied
maintainer: operator-delegated-autonomy
selection_method: auto
execution_mode: sequential-qa-reviewer-user-directed
bootstrap: true
matched_triggers: [money_path, regulatory_path, ai_llm, immutability_audit, multi_party, contracts]
selected_lenses: [ledger-and-money, local-boundary, human-and-model-control]
lens_timings:
  ledger-and-money: {start: null, end: null}
  local-boundary: {start: null, end: null}
  human-and-model-control: {start: null, end: null}
timing_note: Not recorded; no duration claim.
finding_origin: supplied-static-findings-confirmed-by-review
counts: {critical: 5, high: 8, medium: 2, low: 0}
resolution_counts: {spec-fix: 15, new-OQ: 0, accepted-risk: 0, out-of-scope: 0}
dropped: 0
lens_failures: []
unresolved_design: 0
runtime_resolution: pending-implementation-and-evidence
gate: proceed-to-plan-review-only
```
