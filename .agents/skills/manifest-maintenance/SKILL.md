---
name: manifest-maintenance
description: 'Read, rewrite, and maintain accurate MANIFEST.md files for all PARA Areas and Projects. Use when (1) a file is added/removed/moved within an Area or Project, (2) asked to "sync", "update", or "rewrite" a manifest, (3) Scribe Sync Loop triggers a manifest update, (4) "manifest workflow" is mentioned, (5) retroactive manifest sync is needed across the vault. Do not use for initial PARA setup (use manifest-rollout), non-MANIFEST file editing, or vault-wide structural audits.'
---

# Manifest Maintenance Skill

## When to Rewrite a Manifest

Rewrite `MANIFEST.md` when:
- A file is added, removed, or moved within this Area or Project
- Counts are stale or out of sync with disk
- Asked to perform a retroactive sync

## Rewrite Procedure

1. **Read the current MANIFEST.md** — understand its structure
2. **Read manifest-sop.md** — ensure rewrite follows the standard
3. **Read manifest-template.md** — use as formatting reference
4. **Scan all subfolders** — count files and find last-modified timestamp per folder
5. **Rewrite MANIFEST.md** — apply template structure with accurate counts and timestamps
6. **Write back** — preserve all original sections (Status, Projects, Agent Instructions) while updating counts

## MANIFEST.md Format

Every MANIFEST.md must contain these required sections:

```markdown
# MANIFEST — <Scope Name>

## Identity
- Type: project | area
- Owner: <agent or THEK>
- Status: active | paused | archived
- Created: <ISO date>
- Updated: <ISO date>

## Purpose
<One paragraph: what this project/area is for and what done looks like>

## Structure
- Inbox/         — intake
- Calendar/      — scheduled events
- Next_Action/   — tasks (Backlog / Progress / Done / Archive)
- Reference/     — knowledge store (01_Core / 02_Active / 03_Archive)

## Active Items
<Summary of current state: active tasks, open items, recent changes>

## Backlinks
<WikiLinks to related projects, areas, or Zettels>
```

## Core Protocol Rules

### Read-Before-Change Rule

Before any structural operation in a project or area scope:
- Create a subfolder
- Move a file
- Create a new task
- Archive content

**Action:** Read the target scope's `MANIFEST.md` first.

**Why:** MANIFEST tells you the current structure, ownership, and active state. It prevents accidental writes to archived scopes or conflicts with ongoing work.

### Update-After-Change Rule

After any structural change to a project or area:
1. Refresh the `Updated` date to today's ISO date
2. Update the `Active Items` section to reflect current state
3. Add or remove backlinks if scope relationships changed
4. Save the updated MANIFEST.md

### Stale Detection

If a MANIFEST.md hasn't been updated in 14+ days and the scope shows recent file activity:
1. Flag the MANIFEST as stale
2. Prompt THEK to review and refresh it
3. Do not proceed with major operations until THEK confirms

### Missing MANIFEST

If a project or area folder exists without a `MANIFEST.md`:
1. Create a new MANIFEST.md using the template above
2. Fill in Identity section (ask THEK if Owner/Status unclear)
3. Write a brief Purpose statement based on folder name/contents
4. Fill in the Basic Structure section
5. Proceed only after creation succeeds

### Backlink Rules

**When Filing a Note:**
- If a note references another project or area, add a WikiLink in both MANIFEST files
- Example: Note in Project A references Project B → add `[Project B](../../../03_Projects/Project B/MANIFEST.md)` in Project A's Backlinks, and reciprocal link in Project B

**When Archiving a Scope:**
- Move backlinks to an `## Archive References` section instead of deleting
- This preserves the link graph for historical research

**Zettelkasten Exception:**
- `05_Zettelkasten/` root does NOT require a MANIFEST.md
- Individual Zettels maintain bidirectional WikiLinks instead
- No archive section needed for Zettelkasten

## Typical Workflows

### Adding a New Task to a Project

1. Read the project's MANIFEST.md
2. Confirm the project Status is `active`
3. Check `Active Items` for related tasks
4. Create the task in `Next_Action/Backlog/`
5. Update MANIFEST.md: add new task to `Active Items`, refresh `Updated` date
6. Save

### Moving a Project to Archive

1. Read the project's MANIFEST.md
2. Confirm all active tasks are marked `done` or moved to Done folder
3. Update MANIFEST.md: change Status to `archived`, move `Active Items` to `## Archive Summary`, update `Updated` date
4. Move the entire project folder to `07_Archive/`
5. Update any backlinks pointing to this project: add to referrer's `Archive References` section, remove from `Backlinks`

### Updating Active Items

1. Read MANIFEST.md
2. Update `Active Items` with current tasks, recent changes, or open questions
3. Keep it brief and factual — status snapshot, not a log
4. Refresh `Updated` date
5. Save

## Safety Constraints

- **Never delete a MANIFEST.md** — archive its parent scope instead
- **Always ask THEK before changing Owner** — ownership defines access and authority
- **Never move a scope without updating backlinks** — preserves the link graph
- **If MANIFEST is missing and you cannot create it** (e.g. read-only context) — escalate to THEK

## Bundled Resources

- [manifest-sop.md](references/manifest-sop.md) — SOP defining what a manifest must contain
- [manifest-template.md](references/manifest-template.md) — template for formatting reference
- [rewrite-guide.md](references/rewrite-guide.md) — step-by-step rewrite instructions for LLMs