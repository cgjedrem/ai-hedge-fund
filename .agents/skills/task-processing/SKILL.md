---
name: task-processing
description: Standardize PARA task operations for `Next_Action/` scopes. Use when creating, moving, or archiving tasks so status values, folder mapping, and activity log updates stay consistent with the per-epic folder model. Do not use for task creation from scratch (use task-creation), task board scanning (use task-board-scan), or non-PARA task systems.
---

# task-processing Skill

## Purpose
Handle task lifecycle operations in PARA scopes (`02_Areas/*` and `03_Projects/*`) using the per-epic folder structure under `Next_Action/02_Active/`.

## Canonical Rules (locked 2026-08-08)

### Layout
```
<scope>/Next_Action/
├── 02_Active/
│   ├── E00X-<epic-slug>/
│   │   ├── epic.md          ← has goal_ref, no epic_ref
│   │   └── *.md             ← tasks with epic_ref: E00X
│   ├── E00Y-<epic-slug>/
│   │   └── ...
│   └── _orphan/             ← tasks with epic_ref: null or unknown
└── 03_Archive/
    └── <cycle-folder>/      ← cycle-organized: pre-cycle, cycle-NNN, post-cycle-NNN
```

### Status values (frontmatter only — NO folder moves for status)
- `backlog` (initial)
- `in_progress`
- `review`
- `done`
- `archived` (move to `03_Archive/<cycle>/` AND set status)

### Folder rules
- Task file's parent folder MUST match its `epic_ref` frontmatter
- Tasks without an epic go in `_orphan/`
- Epics live as `epic.md` inside their own folder — NO top-level `Epics/` folder

### Activity log
- Always update `updated_at` and append to `activity_log` on every write
- Required actions: `created`, `status_change`, `moved`, `archived`

## Required Frontmatter
```yaml
---
id: "<uuid>"
title: "<task title>"
summary: "<optional summary>"
status: backlog | in_progress | review | done
assignee: user | agent:<name>
epic_ref: E00X | null         # MUST match parent folder
created_at: "<ISO datetime>"
updated_at: "<ISO datetime>"
activity_log:
  - action: created | status_change | moved | archived
    actor: user | agent:<name>
    timestamp: "<ISO datetime>"
---
```

## Procedure
1. Resolve target scope (`02_Areas/<name>` or `03_Projects/<name>`).
2. Resolve target epic (folder `02_Active/E00X-<slug>/` or `_orphan/` for unknown).
3. On create: write task file to the epic folder with `status: backlog`.
4. On status transition: update `status` field only — file stays put unless moving to archive.
5. On epic reassignment: move file to the new epic's folder AND update `epic_ref`. They MUST agree.
6. On archive: move to `03_Archive/<cycle>/` and append `archived` action.
7. If MANIFEST exists for scope, refresh its active-items summary.

## Safety
- Never invent status values.
- Never keep file path and `epic_ref` out of sync.
- Prefer move/archive over delete.
- If scope or epic is ambiguous, stop and ask.

## Migration Notes
- Pre-2026-08-08 layout used `Backlog/`, `Progress/`, `Done/`, `Archive/` subfolders of `Next_Action/`. Those are gone — status is in frontmatter now.
- Top-level `Epics/` folder and `Backlog/` folder (under `Next_Action/`) are also gone. Everything is under `02_Active/`.
