# Rewrite Guide — MANIFEST.md

## When to Rewrite

Rewrite the manifest when:
- A file is added, removed, or moved within this Area or Project
- Counts are stale (manual edits, direct file operations, or Sync Loop changes)
- Requested by a human or agent

## Step-by-Step Rewrite Procedure

### 1. Scan the Folder Structure

List all immediate subfolders in the Area/Project root:
- `Inbox/`
- `Reference/` and its children: `01_Core/`, `02_Active/`, `03_Archive/`
- `Calendar/`
- `Next Action/`
- Any other sibling folders

For each folder, record:
- **File count**: number of `.md` files (recursive depth: scan immediate children only, not deeply nested)
- **Last modified**: most recent file modification timestamp in that folder

### 2. Read Current Manifest

Open the existing `MANIFEST.md` and note:
- Area/Project name and status
- Related projects links
- Agent instructions (preserve these verbatim)
- Existing sections to retain

### 3. Apply Template Structure

Use the format defined in `manifest-template.md`. Required sections:

**Section 1 — Quick Status**
- Area/Project status
- Total file count across all folders
- Last sync timestamp (current datetime)

**Section 2 — FILE INDEX** (replace any stale table)
- One row per immediate subfolder
- Columns: `Folder | File Count | Last Modified`
- Sort by folder name alphabetically

**Section 3 — Related Projects** (preserve existing links)

**Section 4 — Agent Instructions** (preserve verbatim)

### 4. Count Rules

- Only count `.md` files
- Count immediate children only (do not recurse into deeply nested subfolders beyond 03_Archive semantic clusters)
- Ignore hidden files and system files
- If a folder is empty, show count = 0

### 5. Timestamp Format

Use: `YYYY-MM-DD HH:MM` (24-hour, vault timezone)

### 6. Write the Updated Manifest

- Preserve all content that should remain unchanged (Projects, Agent Instructions)
- Replace only the sections that are machine-generated (FILE INDEX, counts, timestamps)
- Do not add new sections not in the template
- Keep formatting consistent (markdown tables)

## Output

Return a brief summary: which folders had their counts/timestamps updated, and confirm MANIFEST.md was rewritten.
