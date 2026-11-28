---
name: epic-review
description: Interactive skill for reviewing epics at cycle end or on demand. The planning agent surfaces completion status, flags hard conditions that appear met, and the user decides which epics to close. Triggered by "review epics" or at cycle end. Do not use for task board scanning (use task-board-scan), retrospectives (use task-retro), or daily reviews.
---

# Epic Review Skill

## Trigger
User says "review epics", "epic review", or it's the end of a cycle.

## Prerequisites
- At least one epic exists

## Steps

### 1. Epic Status Report
- Walk `02_Active/E00X-*/epic.md` across all scopes (`02_Areas/*`, `03_Projects/*`)
- For each: title, status, completion_type, completion_condition, goal_ref
- Group by: active this cycle, backlog, done
- Read associated tasks in the same folder to gauge actual progress

### 2. Hard Completion Check
- For epics with `completion_type: hard`:
  - Check if completion condition is objectively met
  - Surface met conditions for user confirmation
  - Ask user: "This epic's condition appears met. Confirm done?"

### 3. Soft/Mixed Completion Check
- For epics with `completion_type: soft` or `mixed`:
  - Present progress summary
  - Ask user: "Is this good enough to mark done, or keep going?"

### 4. Backlog Review
- List epics in backlog
- Ask user: "Any backlog epics to activate for next cycle?"

### 5. Drift Check
- Flag epics without `goal_ref`
- Ask user: "Assign these to a goal, or keep them unlinked?"

### 6. Archive Done Epics
- For confirmed-done epics:
  - Move `epic.md` to `Next_Action/03_Archive/<cycle>/<epic-id>-epic.md`
  - Move associated tasks (still inside the epic folder) to `03_Archive/<cycle>/` — they keep their `epic_ref` for traceability
  - Update epic frontmatter: `status: done`
  - Update `Epic-Dependency-Map.md` — remove completed epics, unblock dependents
- Ask user: "Archive tasks for done epics?"

### 7. Write Updates
- Update epic frontmatter as directed
- Update dependency map
- Deliver summary to the planning agent's notification channel (e.g. Discord #tasker in the ENSO implementation)
