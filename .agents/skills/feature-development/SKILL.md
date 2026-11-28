---
name: feature-development
description: 'Orchestrate the 5-phase feature development pipeline: Discovery, Planning, Execution, Review, Summary. Use when asked to build or implement a feature with the structured pipeline.'
---

# Workflow: feature-development

## Trigger
- "build feature", "implement feature", "add feature"
- Coordinator receives a feature request from {requesting_user}
- {requesting_user} asks to build a new feature for a project

## Purpose
Orchestrate the 5-phase feature development pipeline: Discovery → Planning → Execution → Review → Summary.

## Preflight (run before task1)

- **Worktree freshness.** If the project integrates via a long-lived branch (e.g. `origin/dev`), run `git merge-base --is-ancestor origin/<base> HEAD`; if false, surface "worktree is N commits behind <base>" and rebase BEFORE Discovery. Code exploration against a stale tree produces wrong file/line references and plans that reference missing machinery.
- **Machinery sanity.** After Discovery, grep-verify that every function/class the plan references exists at the current HEAD. One-line check per symbol; report misses before presenting the plan.

## Prerequisites
- Check active work for shared-file, branch, service, data-volume, or spec-allocation conflicts; independent worktrees may proceed concurrently
- One writer per checkout at a time: specialists editing the same checkout run strictly sequentially; concurrent work requires independent worktrees/branches
- If a long pipeline session shows context churn (repeated compaction, degraded single-command relaying), split remaining phases into a fresh child session with a self-contained kickoff
- {requesting_user} has provided a feature description or request
- Coordinator agent is configured in the agent harness config
- Specialist agents available for the relevant domains (e.g. code exploration, frontend, backend, devops, QA)
- Shared work directory exists or can be created
- `iteration_log.py` script available at `scripts/iteration_log.py`

## Hard-gate deviations
If a repo hard gate blocks the pipeline (e.g. a plan-review gate requiring merged spec/plan before task generation) and {requesting_user} explicitly directs proceeding anyway, proceed only on that explicit instruction and record the deviation in the generated artifact's preamble: gate name, who directed it, date. Never report the gate as passed; never claim the deviation is routine.

## Parameters

- `{requesting_user}` — user requesting the feature (default: inferred from session)
- `{project_dir}` — target project directory (default: current working directory)

## Steps

### Evidence contract (applies to every step)

Read `docs/governance/evidence-contract.md` in ENSO, or the installed
`~/.agents/docs/governance/evidence-contract.md`. Acceptance rows bind revision plus
dirty-diff, built/installed artifact, timestamp, environment, scenario and provenance.
Quote exact measurements/durations; distinguish static review, build identity,
unit/fake tests, runtime and attributed user reports. Use PASS / FAIL / BLOCKED /
INCONCLUSIVE per row, not as replacements for the existing pipeline log statuses.
Plan negative and adjacent-state cases for platform integrations, including denial,
interruption, retry/recovery, release and stale pending work. Assign runtime/native/
device execution to a capable specialist; backend includes explicitly delegated native
work. QA remains read-only and retains useful static findings when runtime is blocked.
QA returns execution or repair requests to the coordinator; it must not delegate
them to nested specialists as a workaround for its scope.
Before a second patch require new discriminating evidence; repeated failures require
root-cause reassessment. Stop/escalate unsupported platform assumptions or stalled
repair. Select capability tiers by risk, without fixed models/providers or forced effort.
Handoff symptom, reproduction/artifact, failed attempts, exact evidence, hypothesis,
unknowns and smallest falsification experiment; new models reassess, not inherit success.
Progress updates name task, owner, check mode, observed result, blocker and stop condition.

### Handoff envelope and report interface

Every delegated kickoff or repair carries the following envelope, without expanding
the user's scope. Use direct tools for simple one-shot work when appropriate; this
interface does not require background spawning. Harness instructions take precedence.

| Field | Required content |
|---|---|
| Deliverable | Exact requested outcome, artifact location and acceptance criteria |
| Mutation scope | Permitted files/workspace and actions; prohibited actions, including commit, push, PR, merge, deployment, installation or reload when not authorized |
| Approval | Verbatim inherited user approval quote, its source and exact scope; distinguish confirmed requirements from suggestions; agent instructions are not new user authorization |
| Checks | Expected automatic CI and its trigger/status, required local checks, and any extra manual/cloud check with authorization, execution owner and stop condition |
| Context | Current source/artifact identity, relevant decisions and evidence; for repairs use the packet below |
| Budget | Slice limit (earlier of ~25 minutes or ~150 tool calls, or a tighter harness limit) and the phase/tasks it covers |
| Checkpoint | Required before the limit: revision and dirty-diff identity, done/remaining work, evidence, blockers, next owner/check |
| Return | Verdict/status, deliverable and blockers first, then changed files, evidence and next authorized action |

Use `ready`, `blocked` or `needs-approval` for handoff state, alongside the existing
pipeline log status and acceptance-row verdicts, not instead of them. `ready` is
qualified by layer (for example source-ready, loading BLOCKED), never a blanket pass.
Do not treat expected automatic CI as an instruction to start an additional cloud
session or manual run. Report unobserved checks as pending/unverified.

Record each delegated handle's exact value, kind, originating tool/provider and
owning run. A task/background `agent_id` stays in that provider's agent tools; an
app session ID stays in that provider's session tools. Never interchange IDs or
guess/convert a handle. Follow harness wait/notification rules. On an expired or
missing handle, use at most one supported same-provider lookup/recovery, verify its
identity and retained result, then report blocked if unresolved. Never respawn or
repeat mutations blindly to recover a missing result.

### task0-delivery-authority-and-execution-preflight
- **Purpose:** Establish a feasible, authorized completion path before implementation or fan-out.
- **Action:** Record task/spec identity; base, feature branch and workspace; hard workflow gates and any exact authorized override; acceptance evidence; runtime executor; and authority for edits, tests, branch creation, commit, push, PR, merge, deployment, migration and live/private data access.
- **Rules:** Autopilot is not additional authority. An implementation request does not imply publication, deployment or data import. Do not treat continuation prompts as a gate override. If an existing gate cannot be satisfied under the authorized actions, stop before crossing it and report the blocker. Assign an integration owner and identify resource conflicts before spawning children.
- **Output:** `delivery-contract.md` in the session/shared work artifacts; keep it free of credentials and private financial details.
- **Success:** The assigned work, required evidence and authorized terminal state are explicit. Local completion, commit, publication, merge and deployment are separate states.

### task1-discover-architecture
- **Purpose:** Analyze the codebase to understand architecture and identify key files relevant to the feature
- **Action:** Spawn code exploration agent (or run code exploration tool)
- **Input:** Task brief with feature description + request context
- **Output:** `architecture-summary.md` and `key-files.md` in shared work directory
- **Success:** Both files exist and contain non-empty architecture findings

### task2-plan-implementation
- **Purpose:** Coordinator synthesizes architecture summary into an implementation plan
- **Action:** Coordinator reads explorer output and drafts:
  - Frontend changes needed
  - Backend changes needed
  - DevOps changes needed
  - Test strategy
- **Adversarial pass (before Gate 1):** Coordinator stress-tests the drafted plan once — hunt for failure paths the plan does not classify (e.g. which layer converts/swallows error signals, what happens to run status when each dependency rejects), not style. One focused pass; findings get plan amendments, not a separate review phase. Cheap at plan time, expensive at PR time.
- **Output:** `approved-plan.md` in shared work directory
- **Success:** Plan covers all relevant change areas and is approved by {requesting_user} at Gate 1
- For user-facing work, the plan names the user decision, the happy/empty/warning/error states, and what action each warning supports. Show a synthetic state sketch at Gate 1 when UI behavior is material.
- For each open decision, explain in plain language what changes for the user under each option. Recommend a default and say why; mark it unapproved until the user decides. Leave dependent work on hold.
- **Gate 1:** Present plan to {requesting_user}. Wait for approval before proceeding.
  - If {requesting_user} approves → task3
  - If {requesting_user} requests changes → Revise plan and re-present
  - If {requesting_user} rejects → End pipeline, document reason

### task3-execute-plan
- **Purpose:** Implement the approved plan
- **Action:** Select implementers by the affected surfaces, project technology and actual role remits. Split mixed work by dependency; reserve a qualified non-author for consumer/integration review. Report a missing capability rather than routing by a fixed role order.
- **Input for each:** Approved plan + architecture context + shared work directory + handoff envelope
- **Output:** Each agent writes changes and `file-manifest.md`
- **Success:** Each spawned agent either completes without error or returns a checkpointed slice, and file-manifest.md exists for each

Run sequential synchronous work one bounded slice at a time (execution, review
and rework). Stop at the earlier of ~25 minutes or ~150 tool calls; a tighter
harness limit wins. Before the limit, hand off revision and dirty-diff identity,
completed and remaining work, evidence, blockers and next owner/check. Resume
the same phase and cumulative cycle count, not a new unbounded attempt. If a
sync spawn returns past its budget without a checkpoint, rebuild one from `git status`/
`git diff` plus its manifest/transcript, then resume in one new bounded slice or
escalate; the coordinator does not take over the work. If a slice ends with no
measurable progress (no new diff, evidence row or resolved decision), do not start
another slice; escalate to {requesting_user}.

For coding steps, after the first missing-path or patch expected-lines failure,
resolve the actual path inside the authorized workspace and reread the narrow
current context before retrying. Reconcile stale text/line numbers and local edits;
stop on ambiguity or conflicting ownership rather than guessing paths or replaying
the same patch. Retry only against newly observed context.

### task4-review-changes
- **Purpose:** QA review of all changes
- **Action:** Obtain the independent consumer review of affected contracts/behavior by a non-author, and the read-only QA review. Both reviews complete before findings are batched for rework; when executed via agent-iteration-loop, follow its order (QA, then consumer review).
- **Input:** All change files + approved plan
- **Output:** `review-report.md` with findings by severity and code-review status, distinct from the runtime verdict below
- **Success:** Review-report.md exists with status field set
- **Gate 2:** Coordinator reads review status:
  - `pass` → final evidence gate below, then task5 only if accepted; publication still requires explicit authority
  - `fail` or any required runtime row FAIL → Rework loop (see Rollback)
  - `pass-with-caveats` → final evidence gate below, then present to {requesting_user} for decision

#### Final evidence gate (after review and every behavior-changing review edit)

- Preserve Gate 1. This is an additional gate within the existing Markdown review step.
- Mark affected acceptance rows INCONCLUSIVE (stale) after implementation/review fixes;
  retain historical evidence and rerun on the final built/installed artifact.
- An execution-capable specialist returns `acceptance-evidence.md`; QA audits it
  read-only. Static review and build success do not replace platform runtime rows.
- Report the runtime verdict separately from the code-review status. Keep each
  required runtime row, including negative and adjacent states: PASS for a matching
  observation, FAIL for an observed mismatch, BLOCKED if the check could not run,
  INCONCLUSIVE if evidence is missing, stale, ambiguous or insufficient. Give the
  evidence and next owner/action per non-PASS row; one blocked check does not erase
  another's failure. Route FAIL to rework. If review passes but any required row is
  BLOCKED or INCONCLUSIVE, report it to {requesting_user} as not accepted, with owner
  and next stop condition; make no acceptance/release-ready claim. Acceptance/release
  readiness requires current passing review and fresh
  PASS evidence for every required row; a clean review cannot cancel any non-PASS.
- For UI changes, include evidence for required loading/empty/error/warning states
  and distinguish automated accessibility checks from human usability observations.
- A later behavior edit reopens affected rows and this gate. Any user risk acceptance
  remains explicit and does not relabel missing evidence PASS.
- Preserve the existing `review` log phase. For BLOCKED/INCONCLUSIVE acceptance,
  log pipeline status `blocked` and the row status/reason; do not invent schema values.

### task5-compile-summary
- **Purpose:** Compile deliverables and perform only the authorized delivery action
- **Action:** Coordinator compiles:
  - All deliverables and file changes
  - Code-review status and findings, alongside the separate runtime verdict and per-row results
  - Next steps and follow-up tasks
- **Output:** `summary.md` in shared work directory
- **Success:** Requested deliverable is retained and reported verdict-first. Submit a
  PR only if explicitly authorized; otherwise leave changes uncommitted or at the
  authorized stopping point. A pipeline approval is not implicit commit/push/PR,
  merge, deployment or extra manual cloud-check approval.

#### Memory Write-Back
After compiling the summary, append only durable, verified, non-sensitive repository
facts to agent memory. Keep transient pipeline IDs, statuses, branch tips, commits,
and per-phase reports in the session summary/artifact instead of persistent memory.
Never put credentials, private financial data, or sensitive personal information
in agent memory.

#### Mandatory: Iteration Log
After each significant pipeline event, coordinator MUST call the helper bundled with the installed skill (`.agents/skills/feature-development/scripts/iteration_log.py` in consuming repos; canonical authoring home: this repo's `workflows/development/feature-development/scripts/`). On Windows use `py -3` instead of `python3`:
```bash
python3 .agents/skills/feature-development/scripts/iteration_log.py \
  --project {slug} --version {N} --status {status} --phase {phase} \
  --reason "{reason}" --changes "{what changed}" \
  --session {transcript_path} --tokens {token_count} --runtime {seconds} \
  --files "{comma-separated file paths}"
```
Trigger points: explorer done, gate approved/rejected, each dev agent done, QA done, rework start, rework limit hit, pipeline complete.
Statuses: `in-progress`, `approved`, `rejected`, `rework`, `blocked`.
Phases: `discovery`, `planning`, `execution`, `review`, `summary`.

## Skills/Tools Used
- **[iteration-work](~/ENSO Skills and Scripts/skills/agent-architecture/iteration-work/SKILL.md)** — iteration logging protocol
- Sub-agent spawning tool — for spawning specialist agents (harness-specific)
- Messaging tool — for gate notifications to {requesting_user} (harness-specific)

## Outputs
- `architecture-summary.md` + `key-files.md` (discovery)
- `approved-plan.md` (planning)
- `file-manifest.md` per agent (execution)
- `review-report.md` (review)
- `acceptance-evidence.md` (final-artifact evidence, separate from static review)
- `summary.md` (summary)
- `delivery-contract.md` (authority and execution preflight)
- Iteration log entries in vault
- Agent memory write-back
- State file: `state/last_feature_dev.json` — tracks current pipeline run ID, project slug, phase, status, agent spawn count, cumulative rework cycle count, scope/decision changes with user approval references, timestamps

## Rollback
- Gate rejection: coordinator routes feedback, ends or revises pipeline
- Spawn failure: reconcile the returned handle/status with the originating provider
  before at most one retry; if work may already exist, recover it or report blocked,
  never create a duplicate blindly
- Timeout: alert {requesting_user} with partial output
- Rework loop max 3 cycles, then stop for {requesting_user}'s human intervention;
  additional cycles require explicit approval with the new limit recorded
- On failure at any task: write current state to `state/last_feature_dev.json`, notify {requesting_user}

## Rework Loop
1. QA status=fail or a required runtime row FAIL → coordinator reads review report and evidence
2. Coordinator identifies which agent(s) need to fix issues
3. Coordinator categorizes findings: **bugs to fix** vs **design decisions to preserve**
4. Coordinator routes the repair packet below to the relevant dev agent(s), with
   the original plan and explicit skip list; use retained context where supported
5. Dev agent(s) fix ONLY the bugs, skip the design decisions. A second patch for the
   same symptom requires new discriminating evidence; repeated failure triggers
   root-cause reassessment and escalation, not another speculative patch.
6. Before QA re-check, sweep the entire touched artifact and dependent normative
   statements (spec, plan, tasks, contracts, examples and tests as applicable) for
   contradictions. Reconcile all affected statements within approved scope, or
   report the exact conflict as blocked/needs-approval. Return the sweep evidence
   and revised identity to task4; do not add blanket extra review rounds.
7. **Max 3 cycles.** Initial QA is cycle 1/3; each new QA review increments the
   cumulative count and includes its resulting repairs. Recovering a truncated
   report or lost handle is not a new review. Switching agents, rephrasing a task
   or updating the plan does not reset the cap. Record user-approved scope changes with
   old/new scope and approval quote; never auto-reset the cycle count. After 3,
   stop: "Changes need human intervention". Continue only under a recorded explicit
   user-approved extension, including its limit.

## QA Fix Task Brief Template
When spawning a dev agent to fix QA findings, include:
```
### Handoff envelope
[Deliverable, mutation boundaries, inherited approval quote/scope and check ownership]

### Current source and decisions
[Revision + dirty-diff or snapshot; actual paths; exact relevant current source text]
[Confirmed/open/superseded decisions and constraints with source references]

### Findings to fix
[Exact current finding text, evidence and file:line; expected result; prior failed attempts]

### Hard boundaries (do NOT change these)
[List each design decision with reason it's preserved]

### Consistency sweep before rereview
[Entire touched artifact and dependent normative statements; resolved contradictions,
remaining blockers, affected checks and final artifact identity]

### Cycle accounting
[Run ID, cumulative same-scope cycle, cap/approved extension and scope-change approvals]
```
This prevents the apply-then-revert pattern where agents fix everything then undo design decisions.

## Failure Handling
- If specialist spawn fails: apply the bounded provider/handle recovery in Rollback;
  alert {requesting_user} if unresolved, without duplicate work
- If specialist times out: coordinator alerts {requesting_user} with partial output
- If {requesting_user} rejects at any gate: coordinator routes feedback, ends or revises pipeline
