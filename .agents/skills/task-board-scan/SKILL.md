---
name: task-board-scan
description: Autonomous skill for daily task board scanning. Runs on cron at 09:00. Detects orphans, drift, and stale tasks. Sends brief summary to Discord if flags found. Silent if clean. Use when running daily board scan via cron, or when asked to check task board health. Do not use for task creation, task lifecycle changes, or cycle planning.
---

# Task Board Scan Skill

## Trigger
Daily cron at 09:00 (after morning brief).

## Layout (locked 2026-08-08)

```
Next_Action/
├── 02_Active/
│   ├── E001-<epic-slug>/
│   │   ├── epic.md          ← has goal_ref, no epic_ref
│   │   └── *.md             ← tasks, all with epic_ref: E001
│   ├── E00X-.../
│   │   └── ...
│   └── _orphan/             ← tasks with epic_ref: null or unknown
└── 03_Archive/
    └── (cycle-organized)
```

**Rule:** the folder an epic lives in MUST match the `epic_ref` of its tasks. Tasks in `_orphan/` are flagged. Top-level `Epics/` and `Backlog/` (under Next_Action/) folders do NOT exist — everything is under `02_Active/`.

## Steps

### 1. Fetch Tasks
- For each epic folder in `02_Active/` (matching `E00*`):
  - Read `epic.md` → parse epic (id, title, goal_ref, status, updated_at)
  - Read every other `*.md` → parse task (id, title, epic_ref, status, updated_at, scope)
- Read `02_Active/_orphan/*.md` → these are orphan tasks

### 2. Orphan Detection
Two orphan classes — both flagged:
- **Folder orphans:** any task in `02_Active/_orphan/`
- **Mismatched-orphan:** any task whose folder does NOT match its `epic_ref`
  - e.g. task in `E001-.../` with `epic_ref: E003` = mismatch
  - the folder is the source of truth, the `epic_ref` field should agree

Report each orphan with: title, current folder, declared `epic_ref`, status.

### 3. Drift Detection
- For each `epic.md` in `02_Active/E00*/`:
  - Flag if `goal_ref` is missing or empty
  - Flag if `status: backlog` and the folder contains no in-progress tasks (stale epic)
- Compare with previous scan (`state/last_scan.json`) — new epics or removed epics are noted

### 4. Staleness Detection
- Filter: tasks in `in_progress` or `review` status with `updated_at` older than 16 weeks
- Collect list of stale tasks with: title, epic, status, last updated date, days since update

### 5. Status Change Summary
- Compare with previous scan (`state/last_scan.json`)
- Report tasks that changed status since last scan
- Highlight tasks that moved to `done` (accomplishments)
- Highlight epics where ALL tasks reached `done` (candidates for cycle-archive review)

### 6. Report
- If any flags found (orphans, drift, stale):
  - Compose brief summary
  - Send to Discord #tasker channel
- If no flags and no notable status changes:
  - Silent — no message
- Always write `state/last_scan.json` with current scan results

## Fallbacks
- Mission Control API down → fall back to filesystem scan of `02_Active/`
- No task files found → silent (empty board is valid after cleanup)
- Previous scan file missing → treat as first scan, no comparison
- Epics folder missing from an active epic → flag as structural drift, do not crash

## Migration Notes
- 2026-08-08: layout changed. Epics moved from `Backlog/` and `Epics/02_Active/` into per-epic subfolders under `02_Active/`. Tasks grouped by `epic_ref`. `_orphan/` holds unknown-epic tasks for triage.
- The `epic_ref` field on each task should still match the folder name — filesystem layout and frontmatter MUST agree.
