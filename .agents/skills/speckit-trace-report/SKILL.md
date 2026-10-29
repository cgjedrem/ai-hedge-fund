---
name: speckit-trace-report
description: Generate a compact, CI-friendly compliance report combining matrix, gaps,
  and orphans
compatibility: Requires spec-kit project structure with .specify/ directory
metadata:
  author: github-spec-kit
  source: extension:trace
---

# Trace Report Skill

# Trace Report

Produce a single one-page report that summarises traceability health: coverage percentage, gaps by severity, orphan count, and a short delta from the previous report (if any).

## User Input

```text
$ARGUMENTS
```

You **MUST** consider the user input before proceeding (if not empty). The user may specify:
- Output format (e.g., "markdown", "json", "junit")
- A threshold to fail at (e.g., "fail under 80% coverage")
- A baseline ref to compare against (e.g., "compare to main")

## Prerequisites

1. Run the scan logic from `/speckit.trace.build` to assemble matrix, gaps, and orphans.
2. If a baseline ref is given, run the same scan on that ref using `git show <ref>:.specify/spec.md` and compare.

## Delegation

Canonical pattern: `.specify/docs/subsession-delegation.md`. Adaptation for this skill:

1. **Recursion guard**: if the current input contains the exact token `DELEGATED_WORKER`, skip this section and run inline.
2. **Resolve mode** (default `subagent`; degrade to `inline` when no subagent capability exists; invalid/missing config falls back silently). `inline` → skip the rest of this section.
3. **Delegate** the entire Outline (read-only scan + report) to a subagent. Kickoff contains ONLY: the `DELEGATED_WORKER` token, this skill's name, the repo root, the spec path and test directory, the user's `$ARGUMENTS` (format / threshold / baseline ref), and an instruction to read `.agents/skills/speckit-trace-report/SKILL.md` and execute the Outline. No conversation history.
4. **Orchestrator** relays the report and the three `TRACE-*:` lines unchanged and in order (CI greps for them).

## Outline

1. **Header**: One-line health badge.

   ```markdown
   # Trace Report — 2026-05-12

   **Coverage: 87% (13 / 15)** — 2 gaps, 1 orphan, baseline `main` (was 80%)
   ```

2. **Coverage Block**:

   ```markdown
   ## Coverage

   | Metric | Now | Baseline | Delta |
   |--------|-----|----------|-------|
   | Requirements | 15 | 13 | +2 |
   | Covered | 13 | 11 | +2 |
   | Coverage | 87% | 85% | +2pp |
   ```

3. **Gaps Block** (link to `/speckit.trace.gaps` output):

   ```markdown
   ## Gaps (2)

   - REQ-007 — Audit log retention is 90 days (High)
   - REQ-012 — Footer shows copyright year (Low)
   ```

4. **Orphans Block** (link to `/speckit.trace.orphans` output):

   ```markdown
   ## Orphans (1)

   - test_old_signup_flow → REQ-LEGACY-001 (not in spec)
   ```

5. **CI Exit Block**: Always print three grep-ready lines so pipelines can parse without a JSON output flag.

   ```text
   TRACE-COVERAGE: 87
   TRACE-GAPS: 2 (1 high, 0 medium, 1 low)
   TRACE-ORPHANS: 1
   ```

6. **Optional JSON**: If the user requested `--format=json`, emit a second block with the same data structured as JSON for tooling consumption.

## Rules

- **Read-only** — never modify spec, tests, or `.specify/trace.md` from this command (use `/speckit.trace.build` to refresh the matrix).
- **One report, one page** — keep the markdown body under ~80 lines; long detail belongs in the matrix file.
- **Threshold is advisory** — if `--fail-under=N` is given, append a `TRACE-FAIL: coverage X% < threshold N%` line; do not exit non-zero (the host CI decides).
- **Stable lines** — the three `TRACE-*:` lines must always print in the same order with the same prefixes.
- **Honest deltas** — only compare to a baseline that was actually scanned; never invent a "previous" value.
