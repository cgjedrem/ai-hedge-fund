---
name: task-retro
description: Interactive skill for retroactively assigning existing tasks to epics. Used when tasks exist before the epic system was set up, or when capture creates orphan tasks. Triggered by "retro tasks" or during cycle planning. Do not use for creating new tasks (use task-creation), cycle planning (use cycle-planning), or daily reviews.
---

# Task Retro Skill

## Trigger
THEK says "retro tasks", "assign tasks to epics", or during cycle planning when orphan tasks are found.

## Prerequisites
- At least one epic exists
- Orphan tasks exist (tasks without `epic` field in frontmatter)

## Steps

### 1. Find Orphan Tasks
- Call Mission Control API `GET /api/tasks`
- Filter: tasks where `epic` field is missing or empty
- Group by scope (area, project)

### 2. Present Orphans
- List each orphan: title, scope, scopeName, status
- Group by project/area for context

### 3. Assign to Epics
- For each orphan, propose an epic assignment based on:
  - Scope/area matches epic's project
  - Title/body keywords match epic title
  - Goal alignment
- Ask THEK: "Proposed assignments — approve, modify, or reject each"
- THEK can also say "skip" to leave as orphan temporarily

### 4. Create New Epics
- If an orphan doesn't fit any existing epic:
  - Propose creating a new epic for it
  - Ask THEK for epic title and completion condition
  - Create epic file in appropriate project/area
  - Assign task to new epic

### 5. Move to Someday
- If an orphan is not relevant to current cycle:
  - Ask THEK: "Move to Someday?"
  - If yes, move task to appropriate Someday folder

### 6. Write Updates
- Update task frontmatter via Mission Control API — add `epic: E001` field
- Update `Epic-Dependency-Map.md` if new epics were created
- Deliver summary to Discord #tasker channel

## Rules
- Tasker proposes assignments. THEK approves, modifies, or rejects.
- Tasker adapts — if THEK wants to batch-assign or skip sections, follow their lead.
- Never auto-assign without approval.