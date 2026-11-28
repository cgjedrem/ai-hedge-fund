---
name: task-creation
description: Task creation protocol for projects and areas. Defines frontmatter format, status transitions, file paths, and task lifecycle management. Use when creating new tasks, defining task scope, or setting up task frontmatter. Do not use for task board scanning (use task-board-scan), retroactive epic assignment (use task-retro), or cycle planning.
---

# Task Creation Skill

## Purpose

This skill defines the canonical protocol for creating and managing tasks in projects (`03_Projects/<name>/Next_Action/`) and areas (`02_Areas/<name>/Next_Action/`). Tasks are markdown files with YAML frontmatter that drive the project/area workflow.

## Task Frontmatter Format (Required)

Every task file MUST contain this frontmatter:

```yaml
---
id: "<uuid>"
title: "<task title>"
summary: "<optional summary>"
status: backlog | in_progress | review | done
assignee: user | agent:<name>
created_at: "<ISO datetime>"
updated_at: "<ISO datetime>"
activity_log:
  - action: created | status_change | moved | archived
    actor: user | agent:<name>
    timestamp: "<ISO datetime>"
---
```

### Field Definitions

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `id` | string (UUID) | Yes | Unique identifier, generated on creation. Use `crypto.randomUUID()` or equivalent. |
| `title` | string | Yes | Task name, max 100 characters. |
| `summary` | string | No | Optional brief context or acceptance criteria. |
| `status` | enum | Yes | One of: `backlog`, `in_progress`, `review`, `done`. No other values. |
| `assignee` | string | Yes | Either `user` or `agent:<name>` (e.g. `agent:scribe`). |
| `created_at` | ISO datetime | Yes | When task was created. Format: `2026-04-25T14:30:00Z`. |
| `updated_at` | ISO datetime | Yes | Last modification time. Update on every change. |
| `activity_log` | array | Yes | List of state changes. Always append, never delete. |

## File Path Structure (locked 2026-08-08)

Per-epic folder model. Status lives in frontmatter — folder placement is by epic, NOT by status.

### Project Tasks

```
03_Projects/<project>/Next_Action/02_Active/E00X-<epic-slug>/<slug>-<uuid>.md
```

### Area Tasks

```
02_Areas/<area>/Next_Action/02_Active/E00X-<epic-slug>/<slug>-<uuid>.md
```

### Action Queue Tasks

```
04_Actions/Next_Actions/02_Active/E00X-<epic-slug>/<slug>-<uuid>.md
```

### Orphan Tasks (no epic assigned yet)

```
<scope>/Next_Action/02_Active/_orphan/<slug>-<uuid>.md
```

### Archive (cycle-organized)

```
<scope>/Next_Action/03_Archive/<cycle-folder>/<slug>-<uuid>.md
# e.g. .../03_Archive/cycle-002/<slug>-<uuid>.md
```

### Status Folder Mapping

**None.** Status is in the `status:` frontmatter field only. The file stays in its epic folder through `backlog → in_progress → review → done`. Only on `archived` does the file move to `03_Archive/<cycle>/`.

## Creating a Task

### Step 1: Prepare the Task

```javascript
const task = {
  id: crypto.randomUUID(),  // e.g. "a1b2c3d4-e5f6-4g7h-8i9j-0k1l2m3n4o5p"
  title: "Implement task routing logic",
  summary: "Route inbox items to Reference/Calendar/Next_Action based on content type",
  status: "backlog",
  assignee: "user",
  created_at: new Date().toISOString(),  // e.g. "2026-04-25T14:30:00Z"
  updated_at: new Date().toISOString(),
};
```

### Step 2: Create Activity Log Entry

```javascript
const entry = {
  action: "created",
  actor: "user",  // or "agent:scribe"
  timestamp: new Date().toISOString(),
};

task.activity_log = [entry];
```

### Step 3: Determine Scope, Epic & Folder

```
// Example: Task in Alpha project, status backlog, epic E001
Scope:   project
Project: Alpha
Epic:    E001
Path:    03_Projects/Alpha/Next_Action/02_Active/E001-<epic-slug>/implement-task-routing-a1b2c3d4.md
// If epic is unknown, use _orphan/:
Path:    03_Projects/Alpha/Next_Action/02_Active/_orphan/implement-task-routing-a1b2c3d4.md
```

The `epic_ref:` field in frontmatter MUST match the parent folder.

### Step 4: Write File

```markdown
---
id: "a1b2c3d4-e5f6-4g7h-8i9j-0k1l2m3n4o5p"
title: "Implement task routing logic"
summary: "Route inbox items to Reference/Calendar/Next_Action based on content type"
status: backlog
assignee: user
created_at: "2026-04-25T14:30:00Z"
updated_at: "2026-04-25T14:30:00Z"
activity_log:
  - action: created
    actor: user
    timestamp: "2026-04-25T14:30:00Z"
---

## Context

The scribe sync loop needs to intelligently route inbox items to the right destination folder based on file content.

## Acceptance Criteria

- [ ] Route calendar items (dates, events) to Calendar/
- [ ] Route action items (tasks, next steps) to `Next_Action/02_Active/<E00X-epic-slug>/` (or `_orphan/` if epic unclear)
- [ ] Route reference items (docs, notes) to Reference/
- [ ] Handle ambiguous cases by prompting THEK

## Resources

- [Scribe Sync Loop](../../../scribe/SOUL.md)
- [Inbox Processing Skill](../../../skills/inbox-processing/SKILL.md)
```

## Updating a Task

### Status Change

When moving a task from one status to another:

1. Validate the transition (see Status Transitions below)
2. Update the `status` field
3. Update the `updated_at` timestamp
4. Append a new entry to `activity_log`:
   ```yaml
   - action: status_change
     actor: agent:scribe
     timestamp: "2026-04-25T15:45:00Z"
   ```
5. **Do NOT move the file.** Status changes update the frontmatter `status:` field only. The task stays in its epic folder through the entire lifecycle.

### Assignee Change

1. Update the `assignee` field
2. Update `updated_at`
3. Append to `activity_log`:
   ```yaml
   - action: assignee_change
     old_assignee: user
     new_assignee: agent:scribe
     actor: user
     timestamp: "..."
   ```

### Body Updates

When editing the task body (context, acceptance criteria, resources):
1. Update the markdown content (after frontmatter)
2. Update `updated_at`
3. Append to `activity_log`:
   ```yaml
   - action: body_update
     actor: user
     timestamp: "..."
   ```

## Status Transitions

### Valid Forward Transitions

```
backlog → in_progress → review → done
```

### Valid Reverse Transitions

```
done ← review (move back to review, e.g. regressions)
review ← in_progress (move back if blocked)
in_progress ← backlog (move back if deprioritized)
```

### Invalid Transitions

These are blocked:
- `backlog` → `review` (must go through `in_progress` first)
- `backlog` → `done` (must go through `in_progress` and `review` first)
- `in_progress` → `done` (must go through `review` first)
- `review` → `backlog` (move to `in_progress` instead)
- `done` → `in_progress` (move to `review` instead)

### Archiving

Move a task from any status to `03_Archive/<cycle>/`. The `status:` field becomes `archived`:
- From: `<epic-folder>/<slug>-<uuid>.md` → To: `03_Archive/<cycle-folder>/<slug>-<uuid>.md`
- Set `status: archived`
- Append to `activity_log`:
  ```yaml
  - action: archived
    reason: "Not prioritized"
    actor: user
    timestamp: "..."
  ```

## Workflow Examples

### Example 1: Create a Task for an Agent

```
Scope:    project
Project:  Learning Pipeline Optimization
Title:    Extract handwriting from ReMarkable PDF
Assignee: agent:scribe
Status:   backlog
```

**File:** `03_Projects/Learning Pipeline Optimization/Next_Action/02_Active/E001-Learning-Pipeline/epic.md` (or `_orphan/` if epic unclear)
**Task file:** `03_Projects/Learning Pipeline Optimization/Next_Action/02_Active/E001-Learning-Pipeline/extract-handwriting-abc123.md`

```markdown
---
id: "abc123de-f456-7890-ghij-k1l2m3n4o5p6"
title: "Extract handwriting from ReMarkable PDF"
summary: "Integrate OCR extraction into Phase 2 automation"
status: backlog
assignee: agent:scribe
created_at: "2026-04-25T10:00:00Z"
updated_at: "2026-04-25T10:00:00Z"
activity_log:
  - action: created
    actor: user
    timestamp: "2026-04-25T10:00:00Z"
---

## Context

THEK takes handwritten notes on iPad via ReMarkable. Phase 2 (Articulate) needs to extract this text from the PDF and save it to Zettelkasten/Inbox.

## Acceptance Criteria

- [ ] OCR extraction script can handle ReMarkable PDF format
- [ ] Text accuracy is >95% for English text
- [ ] Output is saved as raw text (no paraphrasing)
- [ ] Crossed-out words are excluded automatically

## Resources

- [Scribe Phase 2 Workflow](../../SOUL.md#phase-2---articulate)
- [OCR Tool Docs](../Reference/ocr-tools.md)
```

### Example 2: Transition a Task to In Progress

**No file move.** Status change updates frontmatter only — task stays in its epic folder.

**Frontmatter update:**

```yaml
status: in_progress
updated_at: "2026-04-26T09:30:00Z"
activity_log:
  - action: created
    actor: user
    timestamp: "2026-04-25T10:00:00Z"
  - action: status_change
    actor: agent:scribe
    timestamp: "2026-04-26T09:30:00Z"
```

### Example 3: Archive a Completed Task

**File move:** `...Next_Action/02_Active/E001-Learning-Pipeline/extract-handwriting-abc123.md` → `...Next_Action/03_Archive/cycle-002/extract-handwriting-abc123.md`

**Frontmatter update:**

```yaml
status: archived
updated_at: "2026-04-30T16:00:00Z"
activity_log:
  - ... [previous entries]
  - action: archived
    reason: "Completed successfully"
    actor: user
    timestamp: "2026-04-30T16:00:00Z"
```

## Safety Rules

- **Always generate a UUID** for every new task; don't reuse IDs
- **Never invent status values** outside: `backlog`, `in_progress`, `review`, `done`
- **Always update `updated_at`** on every change
- **Always append to `activity_log`**; never delete or replace entries
- **Validate transitions** — but do NOT move the file when status changes; only the frontmatter updates
- **Ask THEK before assigning to agents** — ensure the agent can handle it
- **Preserve task body on status changes** — only update frontmatter
- **Folder ↔ epic_ref must agree** — if you move a task to a different epic folder, also update its `epic_ref` field (or vice versa)
