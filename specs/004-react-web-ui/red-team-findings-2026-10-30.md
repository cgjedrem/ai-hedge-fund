# Red-Team Findings: Local React Trading Desk

Session: RT-004-react-web-ui-2026-10-30. Target: spec.md.
Selection: --yes under express autonomous authorization; three catalog lenses sequentially in one QA reviewer context (sequential-specialist rule).
Catalog was absent and scaffolded before review. Constitution has no trigger section: bootstrap categories apply.
Triggers covered: money_path, immutability_audit, contracts, multi_party, ai_llm; regulatory_path reviewed voluntarily (weak keyword evidence).
Review: independent qa-reviewer, 2026-10-30. No source/runtime execution performed.

## Session Summary

Reviewer initially blocked plan entry pending mechanism-level constraints. Constraints are recorded in plan.md before implementation. This report preserves the working spec without rewriting it. No finding authorizes changing existing engine semantics.

## Findings and Resolutions

| ID | Lens | Severity | Location | Finding | Resolution/status |
|----|------|----------|----------|---------|-------------------|
| L1 | ledger-and-money | CRITICAL | FR-005 | Approval identity source/expiry comparison unspecified | spec-fix design constraint: server supplies and compares timestamp+source hash and uses existing expiry; plan Safety |
| L2 | ledger-and-money | CRITICAL | US2 | No external single-writer guarantee | accepted-risk bounded: API locks are local only; unsafe engine/process actions deferred unless shared guarantee proven |
| L3 | ledger-and-money | HIGH | FR-004 | Live value may contaminate recorded series | design constraint: separate fields/timestamps; recorded-only curves |
| L4 | ledger-and-money | HIGH | US3 | Explicit replacement and normalized name collisions | design constraint: reject existing/casefold/protected names; no replacement |
| L5 | ledger-and-money | LOW | SC-002 | Precision/chain verification visibility unspecified | design constraint: preserve domain numeric precision, format only for display; expose record errors/time/version |
| B1 | local-boundary | CRITICAL | FR-010 | Loopback alone insufficient; Compose publication | design constraint: Host/Origin/token, loopback publication, production CSP |
| B2 | local-boundary | CRITICAL | FR-006 | Browser could grant capabilities | design constraint: immutable startup capabilities, protected guard server-side |
| B3 | local-boundary | HIGH | FR-007 | Credential injection/leaks | design constraint: allowlist/control-character rejection/atomic persistence/no echoes |
| B4 | local-boundary | HIGH | Edge cases | Path containment and SPA fallback | design constraint: resolved-root/symlink guard and API/static separation |
| B5 | local-boundary | HIGH | FR-011 | Attribution/schema/local assets unspecified | design constraint: web attribution, typed schemas, locally bundled assets |
| H1 | human-and-model-control | CRITICAL | US2 | Duplicate/conflicting verdicts | accepted-risk: preserve canonical mailbox replacement semantics, stale identity checks and no repeated execution; do not impose incompatible global first-wins policy |
| H2 | human-and-model-control | CRITICAL | FR-011 | Explicit jobs could spend unexpectedly | design constraint: separate network capability, confirmation, bounded jobs, no retries |
| H3 | human-and-model-control | HIGH | Reports | Untrusted model text in privileged origin | design constraint: escaped text, no raw HTML, CSP |
| H4 | human-and-model-control | HIGH | Runner actions | PID reuse/ownership and manual-run races | design constraint: ownership verification or explicit deferral |
| H5 | human-and-model-control | HIGH | SC-003 | Fakes alone do not enforce isolation | design constraint: guards tested with fakes below boundary, external calls blocked |

## Resolution Log

Autonomous resolution owner: coordinator, based on explicit user instruction. L2/H1 accepted risks are limited by disabled unsafe capabilities and unchanged authoritative engine behavior, not a claim that external races are fixed. All design constraints require implementation evidence and independent final QA. Missing runtime evidence remains BLOCKED.

## Metadata

```yaml
session_id: RT-004-react-web-ui-2026-10-30
selection_method: auto
execution: sequential-single-reviewer
lenses: [ledger-and-money, local-boundary, human-and-model-control]
finding_count: 15
unresolved_design: 0
runtime_status: pending
```
