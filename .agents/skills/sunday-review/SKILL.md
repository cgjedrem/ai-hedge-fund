---
name: sunday-review
description: Interactive skill for weekly review. Tasker surfaces the week's accomplishments, stalled items, and next week adjustments. THEK decides what changes. Triggered by THEK saying "sunday review" or similar.
---

# Sunday Review Skill

## Trigger
THEK says "sunday review", "weekly review", "review the week", or similar.

## Prerequisites
- Current cycle file exists
- At least one active epic

## Steps

### 1. Cycle Context
- Read current cycle file
- Report: which cycle, which week, focus or planning phase
- Report: remaining weeks in cycle

### 2. Accomplishments
- Call Mission Control API `GET /api/tasks` — filter tasks with status change this week
- List tasks moved to `done` or `review` this week
- Ask THEK: "Does this match what you actually accomplished? Anything to add or correct?"

### 3. Epic Progress
- Read all active epics for current cycle focus
- For each: status, completion condition, progress estimate
- Flag hard completion conditions that appear met → auto-surface for THEK confirmation
- Ask THEK: "Any epics to mark as done or move to backlog?"

### 4. Stalled Items
- List tasks in `in_progress` with no activity_log update in 7+ days
- List tasks in `review` status for 7+ days
- Ask THEK: "Which stalled items should we unblock, defer, or archive?"

### 5. Orphans and Drift
- List tasks without `epic` field (orphans)
- List epics without `goal_ref` (drift)
- Ask THEK: "Assign orphans to epics, or defer to Someday?"

### 6. Next Week Adjustments
- Ask THEK: "Any adjustments to next week's MITs?"
- Update cycle file if changes made

### 7. Extended Review (Planning Weeks Only)
- If current week is in planning phase or last week of cycle:
  - Ask THEK: "Ready to plan the next cycle?"
  - If yes → trigger `cycle-planning` skill
- If not a planning week, skip this step

### 8. Write Updates
- Update cycle file, epic frontmatter, task statuses as directed by THEK
- Deliver summary to Discord #tasker channel
- Write memory entry

## Rules
- Tasker surfaces data and flags. THEK decides.
- Tasker adapts — if THEK wants to skip sections, skip them.
- Don't be rigid about the order. Follow THEK's flow.