---
name: inbox-processing
description: 'Inbox processing protocol for project and area agents. Routes inbox items to Reference, Calendar, and Next_Action folders based on content type and context. Use when processing incoming documents, notes, or files in a PARA inbox folder. Do not use for outgoing items, archive maintenance, or non-PARA folder structures.'
---

# Inbox Processing Skill

## Purpose

Every project and area in the vault has an `Inbox/` folder for capturing raw input. This skill defines the protocol for agents to process inbox items and route them to the appropriate destination folder (Reference, Calendar, or Next_Action) based on content type and intent.

**Key principle:** Inbox processing is atomic — items move from Inbox to a final destination, never stay in Inbox.

## Supported Operating Models

This skill applies to agents with these PARA models:
- `project` — agents that own project folders
- `area` — agents that own area folders
- `cross_para` — agents that operate across multiple project/area scopes

**Not applicable to:**
- `zettelkasten` — Zettelkasten has its own Phase 1-3 flow (see scribe's SOUL.md)
- `extractor_pipeline` — Extractor routes from `01_Master_Inbox` to `04_Actions/`
- `calendar` — Calendar agents have specialized calendar routing (see para-scope snippet)

## Inbox Structure

```
<project_or_area>/Inbox/
├── raw-notes.md
├── meeting-summary.md
├── decision-doc.md
└── screenshot.png
```

Inbox items are typically:
- Raw notes or brainstorms
- Meeting summaries
- Captured ideas
- PDFs or images (flagged for processing)

## Routing Decision Tree

When processing an inbox item, classify it and route accordingly:

```
Item in Inbox/
  ├─ Is it a scheduled event or time-bound task?
  │  └─ YES → Route to Calendar/
  │
  ├─ Is it a decision, reference material, or long-term knowledge?
  │  └─ YES → Route to Reference/
  │
  └─ Is it an action item, next step, or task?
     └─ YES → Route to Next_Action/02_Active/<E00X-epic-slug>/ or _orphan/ if epic unclear
```

### Ambiguous Cases

If an item could fit multiple categories:
1. Ask THEK for clarification (do not guess)
2. Leave in Inbox and flag for review
3. Add a note in the item explaining the ambiguity

## Destination Folder Rules

### → Calendar/

**When to route to Calendar:**
- Scheduled events (meetings, appointments, deadlines)
- Time-bound tasks (delivery dates, review milestones)
- Recurring events or regular commitments
- Travel, availability blocks

**File format:**
```markdown
---
date: 2026-05-10
title: "Project Kickoff Meeting"
duration: 60  # in minutes
location: "Zoom link or physical location"
---

Agenda:
- Introductions
- Scope review
- Timeline discussion
```

**Result:** Item moves from `Inbox/project-kickoff-meeting.md` → `Calendar/project-kickoff-meeting.md`

### → Reference/

**When to route to Reference:**
- Documentation, guides, best practices
- Decision records and rationale
- Baseline data, historical context
- Long-term knowledge that doesn't expire

**Subfolder structure within Reference:**
- `Reference/01_Core/` — foundational knowledge (rarely changes)
- `Reference/02_Active/` — current working material
- `Reference/03_Archive/` — old but kept for history

**File naming:**
```markdown
# Reference files should be titled as nouns (not verbs)
- ✅ Budget Allocation Methodology
- ✅ API Design Patterns for This Project
- ❌ How to calculate budget
- ❌ Do this API design
```

**Result:** Item moves from `Inbox/budget-methodology.md` → `Reference/02_Active/budget-methodology.md` (or `01_Core/` if foundational)

### → Next_Action/02_Active/

**When to route to Next_Action:**
- Action items, tasks, to-dos
- Implementation tasks, bug fixes, feature requests
- Next steps that require work

**File format:** See task-creation skill for full frontmatter requirements. Add `epic_ref: E00X` field — must match parent folder.

```markdown
---
id: "<uuid>"
title: "Design homepage mockup"
summary: "Create Figma mockups for homepage redesign"
status: backlog
assignee: user | agent:<name>
epic_ref: E00X
created_at: "<ISO datetime>"
updated_at: "<ISO datetime>"
activity_log:
  - action: created
    actor: user
    timestamp: "<ISO datetime>"
---

## Context
Homepage needs redesign to match new brand guidelines.

## Acceptance Criteria
- [ ] Mobile, tablet, desktop mockups
- [ ] Design follows brand guidelines
- [ ] Ready for developer handoff
```

**Result:** Item moves from `Inbox/homepage-mockup.md` → `Next_Action/02_Active/E00X-<epic-slug>/homepage-mockup-<uuid>.md` (or `_orphan/` if epic unclear)

## Processing Workflow

### Step 1: Read the Item

1. Open the inbox item
2. Understand its intent and content
3. Identify any metadata (dates, urgency, assignee hints)

### Step 2: Classify

Using the decision tree above, determine the destination:
- Calendar → time-bound or scheduled
- Reference → knowledge or documentation
- Next_Action → actionable task
- Ambiguous → ask THEK

### Step 3: Prepare for Destination

**If Calendar:**
- Ensure date field is ISO format (YYYY-MM-DD)
- Add duration and location if available

**If Reference:**
- Decide on subfolder (01_Core, 02_Active, or 03_Archive)
- Ensure title is a noun phrase, not an action verb
- Clean up formatting (headers, links, etc.)

**If Next_Action:**
- Generate a UUID for the task ID
- Fill in all frontmatter fields
- Write clear acceptance criteria
- Set assignee (default to `user` if unclear)
- Initial status is always `backlog`
- Set `epic_ref` to match parent folder (use `null` if going to `_orphan/`)

### Step 4: Move the File

```bash
# Example 1: Inbox → Calendar
mv Inbox/project-kickoff.md Calendar/project-kickoff.md

# Example 2: Inbox → Reference/02_Active/
mv Inbox/budget-methodology.md Reference/02_Active/budget-methodology.md

# Example 3: Inbox → Next_Action/02_Active/_orphan/ (or <E00X-epic-slug>/ if epic known)
mv Inbox/homepage-mockup.md Next_Action/02_Active/_orphan/homepage-mockup-abc123.md
```

### Step 5: Update MANIFEST.md

After processing inbox items:
1. Read the scope's MANIFEST.md
2. Update the `Active Items` section with new tasks or changes
3. Refresh the `Updated` date
4. Save

## Special Cases

### Case 1: Item References Another Scope

If an inbox item mentions or relates to another project/area:
1. Route it normally to this scope's destination
2. Add a WikiLink to the related scope in the file body
3. Update both scope's MANIFEST.md Backlinks sections

Example:
```markdown
# In Project A's Next_Action task
Related: [Project B Calendar](../../../03_Projects/Project B/Calendar/timeline.md)
```

### Case 2: Multi-Part Item

If an inbox item contains multiple ideas or tasks:
1. Split it into separate files (one per idea)
2. Route each separately
3. Add a comment in the parent item linking to all splits

### Case 3: Item with External Media

If the inbox item references a PDF, image, or external file:
1. Download or copy the file to the destination folder
2. Update the markdown link to the new location
3. Move the markdown to the destination
4. Example:
   ```
   Inbox/project-proposal.md (contains ![proposal.pdf])
   → Reference/02_Active/project-proposal.md
   → Reference/02_Active/proposal.pdf (file copy)
   ```

### Case 4: Ambiguous Deadline

Item has both reference value AND a deadline:
- Route to Calendar (deadline takes priority)
- Add a link from Calendar item to Reference folder
- Optionally create a task in Next_Action to "Review [reference doc]" before the deadline

## Health Agent Exception

The `health-agent` and `health-agent-rasma` agents have specialized inbox processing:

**Health Agent Inbox Model:**
```
02_Areas/Health Agent/Inbox/ → routes to:
- Calendar/    (medical appointments, scheduled tests)
- Reference/   (baseline updates, dashboards, finalized summaries)
- Next_Action/ (health interventions, protocols, action items)
```

**Atomic Protocol:**
Files move from `/Inbox/` to `/Reference/` after processing. Baseline data is always preserved in Reference for historical tracking.

See `health-agent/SOUL.md` and `health-agent-rasma/SOUL.md` for the specialized health data model.

## Scribe Exception

The scribe agent has a **different Inbox protocol** documented in scribe/SOUL.md:

- **Scribe Sync Loop:** Scans Areas/Projects Inboxes → routes to Reference/Calendar/Next_Action (standard model)
- **Scribe Master Loop:** Processes `04_Actions/Learning_Queue/` via Phase 1-3 pipeline → outputs to Zettelkasten

This skill applies to the **Scribe Sync Loop** only. The Master Loop uses Zettelkasten-specific phases.

## Safety Rules

- **Never delete inbox items** — always move to a destination or archive
- **Always ask THEK before routing ambiguous items** — don't guess
- **Preserve original content** — edit for clarity, but don't change intent
- **Update MANIFEST.md after processing** — keeps metadata current
- **Atomic move only** — don't copy. File should not exist in two places
- **Alert on missing destination folder** — if Reference/ or Calendar/ doesn't exist, create it before moving

## Monitoring & Cleanup

### Weekly Cleanup

Check each Inbox/ folder for:
- Unprocessed items (older than 3 days) — ask THEK why they're still in Inbox
- Duplicates — merge or delete with THEK confirmation
- Corrupted files — repair or ask THEK for clarification

### Stale Items

If an item stays in Inbox for 7+ days:
1. Ping THEK: "This item is still in Inbox — ready to process?"
2. If THEK says "archive" → move to Archive folder
3. If THEK says "keep" → note the reason (often means "waiting for someone")

## Examples

### Example 1: Meeting Notes → Calendar

**Original:** `Inbox/2026-04-25-kickoff-notes.md`

```markdown
# Project Kickoff Meeting

May 10, 2026, 2 PM - 3 PM
Zoom: https://zoom.us/j/123456789

Attendees:
- THEK
- Design lead
- Dev lead

Topics covered:
- Scope and timeline
- Team roles
- Next steps
```

**Routed to:** `Calendar/2026-05-10-kickoff-meeting.md`

```markdown
---
date: 2026-05-10
title: "Project Kickoff Meeting"
duration: 60
location: "Zoom: https://zoom.us/j/123456789"
---

## Attendees
- THEK
- Design lead
- Dev lead

## Topics
- Scope and timeline
- Team roles
- Next steps

## Notes
See [Kickoff Notes](../Reference/02_Active/kickoff-notes.md) for detailed discussion.
```

### Example 2: Design Guide → Reference

**Original:** `Inbox/brand-guidelines-2026.md`

```markdown
# Brand Guidelines 2026

Typography: Helvetica Neue
Colors: Primary #1F2937, Secondary #60A5FA
Spacing: 8px base unit
...
```

**Routed to:** `Reference/01_Core/brand-guidelines.md`

```markdown
# Brand Guidelines 2026

Typography: Helvetica Neue
Colors: Primary #1F2937, Secondary #60A5FA
Spacing: 8px base unit
...

**Last Updated:** 2026-04-25
**Authority:** Design team
```

### Example 3: Bug Report → Next_Action

**Original:** `Inbox/bug-search-not-working.md`

```markdown
# Search is broken on mobile

When I tap search on iOS, nothing happens. Works fine on desktop.
Priority: High
```

**Routed to:** `Next_Action/02_Active/_orphan/fix-mobile-search-abc123.md` (epic unclear at inbox time)

```markdown
---
id: "abc123de-f456-7890-ghij-k1l2m3n4o5p6"
title: "Fix mobile search functionality"
summary: "Search not working on iOS; works on desktop"
status: backlog
assignee: user
epic_ref: null
created_at: "2026-04-25T14:30:00Z"
updated_at: "2026-04-25T14:30:00Z"
activity_log:
  - action: created
    actor: user
    timestamp: "2026-04-25T14:30:00Z"
---

## Context
Mobile search is broken on iOS. Desktop works fine.

## Acceptance Criteria
- [ ] Search input responds to tap on iOS
- [ ] Results display correctly
- [ ] Performance is <2s on 3G

## Platform Notes
- iOS version: latest
- Device: iPhone 13
```
