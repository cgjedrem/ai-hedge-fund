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

## Prerequisites
- No active pipeline run for the same project
- {requesting_user} has provided a feature description or request
- Coordinator agent is configured in the agent harness config
- Specialist agents available for the relevant domains (e.g. code exploration, frontend, backend, devops, QA)
- Shared work directory exists or can be created
- `iteration_log.py` script available at `scripts/iteration_log.py`

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
Before a second patch require new discriminating evidence; repeated failures require
root-cause reassessment. Stop/escalate unsupported platform assumptions or stalled
repair. Select capability tiers by risk, without fixed models/providers or forced effort.
Handoff symptom, reproduction/artifact, failed attempts, exact evidence, hypothesis,
unknowns and smallest falsification experiment; new models reassess, not inherit success.
Progress updates name task, owner, check mode, observed result, blocker and stop condition.

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
- **Output:** `approved-plan.md` in shared work directory
- **Success:** Plan covers all relevant change areas and is approved by {requesting_user} at Gate 1
- **Gate 1:** Present plan to {requesting_user}. Wait for approval before proceeding.
  - If {requesting_user} approves → task3
  - If {requesting_user} requests changes → Revise plan and re-present
  - If {requesting_user} rejects → End pipeline, document reason

### task3-execute-plan
- **Purpose:** Implement the approved plan
- **Action:** Spawn specialist agents sequentially, one at a time, per the plan's domain split (e.g. frontend → backend → devops)
- **Input for each:** Approved plan + architecture context + shared work directory
- **Output:** Each agent writes changes and `file-manifest.md`
- **Success:** All spawned agents complete without error and file-manifest.md exists for each

### task4-review-changes
- **Purpose:** QA review of all changes
- **Action:** Spawn QA agent (or run QA review tool)
- **Input:** All change files + approved plan
- **Output:** `review-report.md` with findings by severity and overall status
- **Success:** Review-report.md exists with status field set
- **Gate 2:** Coordinator reads review status:
  - `pass` → final evidence gate below, then task5 only if accepted
  - `fail` → Rework loop (see Rollback)
  - `pass-with-caveats` → Present to {requesting_user} for decision

#### Final evidence gate (after review and every behavior-changing review edit)

- Preserve Gate 1. This is an additional gate within the existing Markdown review step.
- Mark affected acceptance rows INCONCLUSIVE (stale) after implementation/review fixes;
  retain historical evidence and rerun on the final built/installed artifact.
- An execution-capable specialist returns `acceptance-evidence.md`; QA audits it
  read-only. Static review and build success do not replace platform runtime rows.
- PASS requires current static review and fresh matching evidence for every required
  acceptance row, including negative and adjacent states. BLOCKED or INCONCLUSIVE
  pauses acceptance, with execution owner/unblock action; do not label it release-ready.
- A later behavior edit reopens affected rows and this gate. Any user risk acceptance
  remains explicit and does not relabel missing evidence PASS.
- Preserve the existing `review` log phase. For BLOCKED/INCONCLUSIVE acceptance,
  log pipeline status `blocked` and the row status/reason; do not invent schema values.

### task5-compile-summary
- **Purpose:** Compile deliverables and submit PR
- **Action:** Coordinator compiles:
  - All deliverables and file changes
  - Known issues from QA review
  - Next steps and follow-up tasks
- **Output:** `summary.md` in shared work directory
- **Success:** Summary submitted as PR for {requesting_user}'s final approval

#### Mandatory: Memory Write-Back
After compiling summary, coordinator MUST update agent memory with:
  - Pipeline run ID, status, branch, key commits
  - What was done (per-phase summary)
  - Known issues / next steps
  - Any backlog item updates
This ensures institutional memory survives session compaction.

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
- Iteration log entries in vault
- Agent memory write-back
- State file: `state/last_feature_dev.json` — tracks current pipeline run ID, project slug, phase, status, agent spawn count, rework cycle count, timestamps

## Rollback
- Gate rejection: coordinator routes feedback, ends or revises pipeline
- Spawn failure: retry once, then alert {requesting_user}
- Timeout: alert {requesting_user} with partial output
- Rework loop max 3 cycles, then alert {requesting_user} for human intervention
- On failure at any task: write current state to `state/last_feature_dev.json`, notify {requesting_user}

## Rework Loop
1. QA status=fail → coordinator reads review report
2. Coordinator identifies which agent(s) need to fix issues
3. Coordinator categorizes findings: **bugs to fix** vs **design decisions to preserve**
4. Coordinator re-spawns relevant dev agent(s) with review report + original plan + **explicit skip list**
5. Dev agent(s) fix ONLY the bugs, skip the design decisions. A second patch for the
   same symptom requires new discriminating evidence; repeated failure triggers
   root-cause reassessment and escalation, not another speculative patch.
6. Back to task4-review-changes (QA re-check)
7. **Max 3 cycles.** After 3, coordinator alerts {requesting_user}: "Changes need human intervention"

## QA Fix Task Brief Template
When spawning a dev agent to fix QA findings, include:
```
### Findings to fix
[List each bug with file:line — problem — fix]

### Hard boundaries (do NOT change these)
[List each design decision with reason it's preserved]
```
This prevents the apply-then-revert pattern where agents fix everything then undo design decisions.

## Failure Handling
- If specialist spawn fails: coordinator retries once, then alerts {requesting_user}
- If specialist times out: coordinator alerts {requesting_user} with partial output
- If {requesting_user} rejects at any gate: coordinator routes feedback, ends or revises pipeline