---
name: agent-iteration-loop
description: >
  5-iteration agent loop for implementing a task with multi-perspective review before any git commit.
  Route implementation by affected surface, get read-only QA and independent consumer review,
  return findings to the affected surface owner, then run final QA and verify runtime evidence.
  Then present diff + commit message to the HUMAN for approval — never commit without it.
  Use when user says "run the agent loop", "iteration loop", "BE FE QA loop", or invokes the loop for a task.
  Do not use for single-agent edits, trivial changes, or tasks with no code output.
---

# Agent Iteration Loop

## Overview

A 5-iteration multi-agent loop that implements a task with layered review. The human is the **final gate** before any git commit. Agents implement and review; the coordinator orchestrates and presents; the human approves and commits (or tells the coordinator to commit after approval).

## Hard Rules

1. **No git commit without explicit human approval.** The coordinator MUST NOT run `git add` / `git commit` until the user says "commit" or explicitly approves the exact proposed commit. A bare "go" is approval only when it directly answers a presented commit proposal. Present the file list and proposed message, then WAIT.
2. **Sequential only.** Run one bounded synchronous slice at a time. Stop by the earlier of ~25 minutes or ~150 tool calls, or sooner for a tighter harness limit. Before the limit, checkpoint the revision and dirty diff, completed and remaining work, evidence, blockers and next owner/check. Resume from that checkpoint without resetting the iteration or rework count. If a slice ends with no measurable progress (no new diff, evidence row or resolved decision), do not start another slice; escalate to the human.
3. **Coordinator does not write code.** The coordinator orchestrates, summarizes, presents, and (after human approval) commits. Implementation and review are specialist responsibilities.
4. **Five iterations, no shortcuts.** Each iteration has a defined agent and purpose. Skipping an iteration requires explicit human override.
5. **Open decisions are not approvals.** Explain each choice and its practical effect in plain language. Recommend a default with a reason, label it unapproved, and wait for the human before implementing work that depends on it.

## The 5 Iterations

### Evidence and repair contract (all iterations)

Read `docs/governance/evidence-contract.md` in ENSO, or
`~/.agents/docs/governance/evidence-contract.md` when installed.
Record revision plus dirty-diff, built/installed artifact, timestamp, environment,
scenario, provenance and exact measurements/durations per acceptance row.
Separate static review, build, unit/fake tests, runtime and attributed user reports.
Use PASS / FAIL / BLOCKED / INCONCLUSIVE; missing or stale evidence cannot pass.
Define negative and adjacent-state platform cases before implementation. Runtime,
native and device checks go to an execution-capable specialist (backend-dev includes
explicitly delegated native work); QA audits evidence and returns useful static
findings while unexecuted checks remain BLOCKED/routed with owner. QA does not
write fixes, run commands, or spawn or ask another agent to run commands, write fixes or audit for it;
the coordinator routes that work separately within the approved scope.
Before a second patch for the same symptom require new discriminating evidence.
Repeated failed repair requires root-cause reassessment; stop/escalate unsupported
platform assumptions or stalled repair rather than consume all three rework cycles.
Use risk-based capability tiers, not fixed model/provider names or forced effort.
Handoff symptom, reproduction/artifact, failed attempts, exact evidence, hypothesis,
unknowns and smallest falsification experiment; a new model reassesses independently.
Progress updates include task, owner, check mode, latest result, blocker and stop condition.

### Iteration 1 — Implement (surface owner)

- Inspect the changed surface and project stack, then select a specialist whose remit fits (e.g. client UI vs service/API). For mixed changes, split by ownership and dependency order. Name an independent consumer reviewer before starting; if no suitable owner or reviewer is available, report the gap rather than assigning by title alone.
- The specialist reads the task spec (Level 5 doc) and the current source files, then implements.
- Verify no syntax errors after implementation.
- Output: file manifest + change summary.

### Iteration 2 — QA Review (qa-reviewer)

- Spawn qa-reviewer with the changed files + the task spec.
- Review for: contract compliance, security (OWASP), correctness, backward compatibility, defense-in-depth, edge cases.
- Report findings by severity (Critical / Important / Minor / Nitpick).
- Output: review report with file:line references.

### Iteration 3 — Consumer Review (independent reviewer)

- Assign a specialist who understands the consuming side and did not author the changes under review. If both client and service owners implemented, use a separate qualified reviewer; do not have either sign off on their own work.
- Frontend reviews backend changes: response shape, field presence, plain-object safety, client compatibility.
- Backend reviews frontend changes: API contract alignment, state shape, request payload correctness.
- Report findings by severity.
- Output: consumer-perspective review.

### Iteration 4 — Fix Findings

- The coordinator collects all findings from iterations 2 and 3.
- Return approved fixes to the specialist(s) owning the affected surface (default: that surface's original implementer).
- Classify findings: fix-now (Critical/Important), defer-with-reason (Minor if out of task scope), nitpick (document, don't fix).
- Verify no syntax errors after fixes.
- Output: fix summary (what was fixed, what was deferred + why).

### Iteration 5 — Final QA Review (qa-reviewer)

- Spawn qa-reviewer for a final pass on the post-fix state.
- Verify all prior Critical/Important findings are fixed.
- Re-run the contract compliance checklist.
- Output: code-review verdict — `pass` / `fail` / `pass-with-caveats`; report runtime separately at the evidence gate.

### Final evidence gate (after iteration 5, before the human gate)

- Keep the pre-implementation approval/review gate; this gate does not replace it.
- Every behavior-changing fix in iteration 4 or later invalidates affected rows.
  Retain history, mark stale rows INCONCLUSIVE and rerun against the final artifact.
- The execution-capable specialist runs required checks; QA stays read-only and
  audits the returned evidence. A static `pass` alone does not satisfy this gate.
- Report the code-review verdict alongside a separate runtime verdict listing each
  required scenario (including negative and adjacent states), its evidence and result:
  PASS (observed as expected), FAIL (observed mismatch), BLOCKED (could not run) or
  INCONCLUSIVE (missing, stale, ambiguous or insufficient evidence). Preserve mixed
  results and give a next action/owner for each non-PASS. No acceptance/release-ready
  claim unless review passes and every required row is PASS.
- If review passes but any required row is BLOCKED or INCONCLUSIVE, report it to the
  human as not accepted, with owner and next stop condition; make no
  acceptance/release-ready claim.
- Any later human-requested behavior edit reopens affected rows and this gate.

Passing review and required evidence completes the local implementation; it does not
require a commit. Report local completion, commit status, publication and deployment
as separate states. A local handoff may remain uncommitted when no commit was
authorized.

## After the Loop — Publication Authorization

If iteration 5 returns `pass` or `pass-with-caveats` AND the final evidence gate passes:

1. Present to the human:
   - Files changed (file manifest)
   - Commit message (Conventional Commits format)
   - Summary of what was implemented + reviewed
   - Any caveats (deferred findings)
2. Do not commit, push, create a PR, merge, or deploy unless that specific action was authorized.
3. If a commit is requested, present the exact files and message and wait for approval of that commit.
4. The human says one of:
   - "commit" or explicitly approves the presented commit → coordinator runs `git add <files>` + `git commit -m "<message>"`
   - "change X" → coordinator routes the change request back to the implementer (mini-iteration)
   - "hold" → do not publish; report the local implementation state

If iteration 5 returns `fail` or a required runtime check returns FAIL:

- Rework loop: spawn the specialist(s) owning the affected surface (default: that surface's original implementer) with the failure findings (max 3 rework cycles).
- After each rework, re-run the affected runtime rows as well as qa-reviewer (iteration 5 pattern).
- After 3 failed rework cycles, alert the human and stop.

If review passes but a required runtime row is BLOCKED or INCONCLUSIVE (none FAIL):

- Report it to the human as not accepted, with owner and next stop condition; make no acceptance/release-ready claim.

## Coordinator Responsibilities

- Track the tasks in the approved scope and the current iteration of each.
- Mark the current task in-progress; mark implementation complete after final review and required evidence, even when it remains uncommitted.
- Update the task doc's Status line to "✅ Implemented, reviewed, and approved — committed <hash>" after the commit lands.
- Present the iteration results concisely (table format) — do not dump full agent outputs.
- Record the commit hash in the task doc + todo list.

## Task Doc Status Lifecycle

1. `Level 1 — awaiting alignment` (initial)
2. `Level 5 — design complete — implementation awaiting approval` (after design loop)
3. `Implementation in progress — iteration N/5` (during the agent loop)
4. `Implementation complete locally — reviewed and verified; commit pending/unauthorized` (after the final evidence gate)
5. `✅ Implemented, reviewed, and approved — committed <hash>` (only after the explicitly authorized commit)

## When to Use

- Multi-file tasks with backend + frontend surface
- Tasks where contract compliance + security + consumer compatibility all matter
- Tasks in a sequential pipeline where each task depends on the prior

## When NOT to Use

- Single-file trivial edits
- Doc-only changes
- Tasks with no code output
- When the human explicitly says "just do it" (single-agent direct implementation)