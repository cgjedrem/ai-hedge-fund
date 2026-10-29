---
name: speckit-trace-orphans
description: List tests that reference a requirement ID that no longer exists in spec.md
compatibility: Requires spec-kit project structure with .specify/ directory
metadata:
  author: github-spec-kit
  source: extension:trace
---

# Trace Orphans Skill

# Trace Orphans

Find tests that annotate a `REQ-XXX` identifier which is missing from the current `.specify/spec.md`. Orphan tests usually mean a requirement was renamed, split, merged, or dropped — and the test was never updated.

## User Input

```text
$ARGUMENTS
```

You **MUST** consider the user input before proceeding (if not empty). The user may specify:
- Test directory override
- A rename hint (e.g., "REQ-010 was renamed to REQ-AUTH-001")
- An ignore list for known dropped requirements

## Prerequisites

1. Run the scan from `/speckit.trace.build`.
2. Build two sets:
   - `spec_ids` — every `REQ-XXX` present in `.specify/spec.md`.
   - `test_ids` — every `REQ-XXX` referenced anywhere in the test suite.

## Delegation

Canonical pattern: `.specify/docs/subsession-delegation.md`. Adaptation for this skill:

1. **Recursion guard**: if the current input contains the exact token `DELEGATED_WORKER`, skip this section and run inline.
2. **Resolve mode** (default `subagent`; degrade to `inline` when no subagent capability exists; invalid/missing config falls back silently). `inline` → skip the rest of this section.
3. **Delegate** the entire Outline (read-only scan + report) to a subagent. Kickoff contains ONLY: the `DELEGATED_WORKER` token, this skill's name, the repo root, the spec path and test directory, the user's `$ARGUMENTS` (rename hints / ignore list), and an instruction to read `.agents/skills/speckit-trace-orphans/SKILL.md` and execute the Outline. No conversation history.
4. **Orchestrator** relays the report and the final `TRACE-ORPHANS:` line unchanged (CI greps for it).

## Outline

1. **Compute Orphans**: `orphans = test_ids - spec_ids`.

   ```markdown
   ## Orphan Tests

   | Test | File:Line | References | Reason |
   |------|-----------|------------|--------|
   | test_old_signup_flow | tests/test_auth.py:120 | REQ-LEGACY-001 | Not in spec |
   | test_admin_delete | tests/test_admin.py:55 | REQ-010 | Not in spec |
   ```

2. **Rename Detection**: If the user provided a rename hint, surface it. Otherwise, suggest likely renames using a name-similarity heuristic on the requirement descriptions in git history.

   ```markdown
   ## Likely Renames

   | Orphan | Best Match | Confidence |
   |--------|------------|------------|
   | REQ-010 | REQ-AUTH-001 | High (description match) |
   | REQ-LEGACY-001 | — | None — likely dropped |
   ```

3. **Action Recommendation**: For each orphan, recommend one of: rename annotation, delete test, or move test to a legacy suite.

   ```markdown
   ## Recommended Actions

   - test_admin_delete → update annotation to REQ-AUTH-001
   - test_old_signup_flow → delete or move to tests/legacy/
   ```

4. **Exit Signal**: Print a final CI-grep line.

   ```text
   TRACE-ORPHANS: 2 orphan test(s)
   ```

## Rules

- **Read-only** — never modify tests or spec files; recommendations are reported, not applied.
- **No silent deletes** — never suggest deleting a test without flagging it for human review.
- **Confidence required for rename** — only suggest a rename when the description match is strong; otherwise mark "dropped".
- **Preserve test history** — recommend moving to `tests/legacy/` over deletion when the behavior may still ship.
- **CI-friendly summary** — final `TRACE-ORPHANS:` line must always print so pipelines can grep for it.
