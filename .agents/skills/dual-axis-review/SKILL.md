---
name: dual-axis-review
description: 'Review changes since a fixed point on two axes (Standards and Spec) and triage findings into fix now, file as issue, or accept. Use when asked to review a branch or PR before merge.'
---

# Workflow: dual-axis-review

## Trigger
- "review this branch", "review the PR", "review since main", "review since <ref>"
- A feature branch or PR is ready for review before merge
- Called as the review phase of `spec-to-implementation` or `feature-development`

## Purpose
Review the changes since a fixed point along two independent axes — Standards (repo conventions + smell baseline) and Spec (does the diff implement what was asked) — then triage findings into actionable outcomes: fix now, file as issue, or accept.

## Prerequisites
- Inside a git repository; the fixed point resolves (`git rev-parse <ref>`)
- Diff between fixed point and `HEAD` is non-empty
- Spec source locatable (issue reference in commits, spec file, or {requesting_user} supplies it)

## Parameters

- `{requesting_user}` — user who supplies the fixed point and decides on findings
- `{fixed_point}` — commit/branch/tag to diff against (ask if not given)
- `{spec_ref}` — originating issue/spec (auto-detected from commit messages when possible)

## Steps

### task1-pin-diff-and-spec
- **Purpose:** Establish exactly what is being reviewed against what
- **Action:** Apply `code-review` §1–2 — capture `git diff {fixed_point}...HEAD` (three-dot) and the commit list; locate the spec via commit issue references, a supplied path, or `docs/`/`specs/` matching the branch
- **Success:** Fixed point resolves, diff non-empty, spec found or explicitly declared absent
- **Fail here, not later:** bad ref or empty diff stops the workflow before sub-agents spawn

### task2-run-both-axes
- **Purpose:** Review Standards and Spec independently so findings don't contaminate each other
- **Action:** Apply `code-review` §3–4 — spawn two parallel sub-agents:
  - **Standards:** documented repo standards + the full Fowler smell baseline; repo standards override the baseline; skip anything tooling enforces
  - **Spec:** does the diff faithfully implement `{spec_ref}`; missing behavior, extra unrequested behavior, contract drift
- **Output:** Two findings reports, each under 400 words, hard violations distinguished from judgement calls
- **Success:** Both sub-agents return; findings cite file/hunk and the standard or spec line they trace to

### task3-aggregate-and-triage
- **Purpose:** Turn findings into decisions, not a wall of comments
- **Action:** Merge both reports side by side. Classify each finding:
  - **fix-now** — hard violation or spec gap; fix on this branch before merge
  - **file** — real but out of scope; apply `triage` to write it as an agent-ready issue with category and verification note
  - **accept** — judgement call {requesting_user} consciously overrides; record the reason
- **Gate:** Present the classified list to {requesting_user} for confirmation before acting
- **Success:** Every finding has exactly one classification confirmed by {requesting_user}

### task4-act-and-verify
- **Purpose:** Close the loop on each classification
- **Action:**
  - fix-now items: fix, re-run affected tests, re-diff to confirm resolved
  - file items: create tracker issues per `triage` brief format; link them in the PR/branch description
  - accept items: record in the review summary with rationale
- **Output:** Review summary — findings by axis, classification, and resolution
- **Success:** No unresolved fix-now items; filed issues have live URLs; summary delivered to {requesting_user}

## Skills/Tools Used
- **[code-review]({ENSO_ROOT}/skills/mattpocock/code-review/SKILL.md)** — two-axis parallel review + smell baseline
- **[triage]({ENSO_ROOT}/skills/mattpocock/triage/SKILL.md)** — filing out-of-scope findings as agent-ready issues
- Sub-agent spawning tool (harness-specific) — parallel Standards/Spec reviewers
- **git**, **gh** — diff, log, issue creation

## Outputs
- Review summary: findings by axis with classification and resolution
- Fixed commits on the branch (fix-now items)
- Filed tracker issues (file items) with links
- Recorded accepted judgement calls with rationale

## Rollback
- Sub-agent failure: retry once with the same prompt; on second failure run that axis inline
- Fix-now change breaks tests: `diagnosing-bugs` loop or revert the fix and reclassify as file with {requesting_user} approval
- Wrong issue filed: close with a comment; do not delete
