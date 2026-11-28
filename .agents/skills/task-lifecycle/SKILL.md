---
name: task-lifecycle
description: Interactive skill for task creation, maintenance, and lifecycle management. Covers creating tasks from ideas, assigning tasks to epics, creating epics from ideas, creating projects/areas from ideas, capture routing, and file organization. THEK decides, Tasker proposes and executes. Use when THEK says "create task", "new task", "add task", "create epic", "new project", "new area", "organize vault", "route capture", or has an idea that needs action. Do not use for task board scanning (use task-board-scan), retrospectives (use task-retro), or cycle planning.
---

# Task Lifecycle Skill

Also triggered when:
- A capture item (email, Discord message) needs routing
- An inbox item needs classification
- An idea needs to become a task, epic, or project

## Prerequisites
- Mission Control API running (localhost:3000)
- Vault structure (PARA folders)
- Current cycle file exists

## Flows

### Flow 1: Task Creation

THEK has an idea or action item → Tasker creates a task.

1. **Gather context** — What's the task about? Which project/area? Any deadline?
2. **Propose epic assignment** — Based on scope and content, suggest which epic this belongs to. If no fit, propose creating a new epic (Flow 3).
3. **THEK approves/rejects** — Confirm epic assignment or choose a different one.
4. **Create task** — Use `task-creation` ENSO skill for frontmatter format and file structure. Create via Mission Control API (`POST /api/tasks`) with:
   - title
   - summary (1-2 sentences)
   - body (full description)
   - assignee (default: "user")
   - folderPath (scope + `Next_Action/02_Active/E00X-<epic-slug>/` — the epic's folder, NOT a status folder)
   - `epic_ref: E00X` in frontmatter (must match the folder)
   - `status: backlog` in frontmatter (initial; status lives in YAML, not folders)
5. **Confirm** — Show created task details. Update MANIFEST via `manifest-maintenance` skill.

**Quick mode:** If THEK says "create task: <title>", create immediately in Backlog with minimal info, flag for later review.

### Flow 2: Task Maintenance

Update, move, or modify existing tasks.

**Status transitions** (frontmatter only — no folder moves for status):
- `backlog` → `in_progress` (start working)
- `in_progress` → `review` (done, needs review)
- `review` → `done` (confirmed complete)
- `review` → `in_progress` (needs more work)
- `in_progress` → `backlog` (deprioritize)
- Any → `archived` (removed from board, kept in `03_Archive/<cycle>/`)

**Epic reassignment:**
- Move a task from one epic folder to another (e.g. `E001-.../task.md` → `E003-.../task.md`)
- Update frontmatter `epic_ref` to match the new folder — they MUST agree
- An orphan task (`_orphan/`) gets assigned by moving it into the target epic folder and setting `epic_ref`

**Task splitting:**
- THEK: "split task X into Y and Z"
- Tasker creates two new tasks, marks original as done or archive
- Each child gets its own epic assignment

**Procedure:**
1. THEK specifies the change (status, epic, assignee)
2. Tasker calls Mission Control API to update
3. Tasker confirms change and updates MANIFEST

### Flow 3: Epic Creation from Ideas

THEK has an idea that's bigger than a task → Tasker proposes an epic.

1. **Check existing epics** — Does this fit an existing epic? If yes, suggest adding as a task under it.
2. **If no fit:** Propose a new epic with:
   - Title
   - Completion condition (ask THEK: hard, soft, or mixed?)
   - Goal alignment (which objective in Life-Goals.md does this serve?)
   - Project/area assignment
3. **THEK approves/rejects/modifies** — Confirm epic details.
4. **Create epic file** at `<scope>/Next_Action/02_Active/E00X-<epic-slug>/epic.md` (per-epic subfolder pattern, NOT a top-level `Epics/` folder)
5. **Update Epic-Dependency-Map.md** if the epic has dependencies
6. **Update Life-Goals.md** goal → epic mapping
7. **Propose task breakdown** — Ask THEK: "Want to break this into tasks now?" Tasks created in this cycle go in the same folder as `epic.md`.

### Flow 4: Project/Area Creation from Ideas

THEK has an idea that needs a whole new scope → Tasker proposes project/area creation.

1. **Classify** — Is this a project (has an end date) or an area (ongoing responsibility)?
2. **Propose structure:**
   - PARA folder structure (Inbox, Calendar, Next_Action, Reference)
   - MANIFEST.md with Identity, Purpose, Structure sections
   - `Next_Action/02_Active/` with per-epic subfolders as epics are created
   - Initial epic (if applicable)
   - Goal alignment
3. **THEK approves/rejects/modifies**
4. **Create folders and MANIFEST.md** — use `para-structure-guard` ENSO skill for folder creation and `manifest-maintenance` skill for MANIFEST
5. **If epic was proposed:** Create epic file, update dependency map, update Life-Goals
6. **Confirm** — Show created scope, deliver summary

### Flow 5: Capture Routing

Incoming item (email, Discord message, Scribe output) needs routing.

1. **Read the capture item** — understand content and origin
2. **Classify using `inbox-processing` ENSO skill decision tree:**
   - **Task** → Create task (Flow 1) with epic proposal
   - **Add to existing epic** → Link to existing task or create sub-task
   - **Someday** → Park in `04_Actions/Someday/` or scope-level Someday
   - **Reference** → File in `Reference/02_Active/` or `05_Zettelkasten/`
   - **Calendar event** → Add to calendar via gws-calendar-insert
3. **THEK approves routing** — Confirm or modify
4. **Execute routing** — Use `inbox-processing` and `task-creation` ENSO skills for file operations
5. **Mark capture item as processed**

### Flow 6: Vault Organization

Periodic vault cleanup — moves misplaced files, repairs frontmatter, routes inbox items.

Uses `vault-organizer` skill for scan/move/repair operations.
Uses `manifest-maintenance` ENSO skill for MANIFEST updates after moves.
Uses `para-structure-guard` ENSO skill for folder structure repairs.
Uses `inbox-processing` ENSO skill for inbox routing logic.
Uses `task-creation` and `task-processing` ENSO skills for task frontmatter operations.

## ENSO Skills Called (Not Recreated)

Tasker calls these existing ENSO skills instead of reimplementing:

- **`task-creation`** — canonical task frontmatter format and creation protocol
- **`task-processing`** — standardized task lifecycle operations (create, move, archive, status transitions)
- **`inbox-processing`** — routes inbox items to Calendar, Reference, or Next_Action
- **`manifest-maintenance`** — rewrite MANIFEST.md files after structural changes
- **`para-structure-guard`** — create/repair PARA folder structure for new scopes
- **`obsidian-vault-maintainer`** — Obsidian wiki vault maintenance

## Rules
- THEK decides everything. Tasker proposes, adapts, executes.
- Quick mode: "create task: <title>" creates with `status: backlog` in the target epic folder (or `_orphan/` if epic unclear).
- Never create an epic without THEK approving the completion condition.
- Never create a project/area without THEK approving the classification.
- Always run manifest-maintenance after structural changes.
- Capture routing: always propose, don't auto-route without approval.
- If Mission Control API is down, fall back to file-based task creation using task-creation ENSO skill.
- Use task-processing ENSO skill for all status transitions and task moves.
- Use inbox-processing ENSO skill for all inbox routing decisions.