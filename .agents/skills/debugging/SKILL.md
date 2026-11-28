---
name: debugging
description: 'Root cause isolation and fix methodology for the bugfix pipeline. Covers reproduction, isolation, diagnosis, fix, and verification. Referenced by frontend and backend agents during bugfix tasks. Use when fixing a bug, investigating a crash, or resolving an error reported through the bugfix pipeline. Do not use for feature development, refactoring, or architectural changes.'
---

# Debugging Methodology

## Overview

This skill defines a structured approach to debugging. Every bugfix follows the same 5-step process: Reproduce → Isolate → Diagnose → Fix → Verify.

## Step 1: Reproduce

Before fixing anything, reproduce the bug reliably.

- **Read the root cause analysis** from the code explorer (if available)
- **Identify the exact conditions** that trigger the bug
- **Create a minimal reproduction** — smallest possible input/steps that trigger it
- **Document the reproduction steps** in the shared work directory as `reproduction.md`

Format:
```markdown
# Bug Reproduction

## Bug Description
[From THEK's report]

## Root Cause Analysis
[From code explorer, if available]

## Reproduction Steps
1. [Step 1]
2. [Step 2]
3. [Expected behavior]
4. [Actual behavior]

## Environment
- Browser/Runtime: [version]
- OS: [version]
- Relevant config: [any relevant settings]
```

If the bug cannot be reproduced:
- Document what you tried
- Flag as `needs-more-info` in the shared work directory
- The coordinator will ask THEK for more context

## Step 2: Isolate

Narrow down where the bug lives.

- **Start from the symptom** — where does the incorrect behavior manifest?
- **Trace backwards** — follow the execution path from symptom to source
- **Use binary search** — comment out half the code, see if the bug persists, narrow down
- **Check recent changes** — `git log` and `git diff` for recent modifications to the affected area
- **Check dependencies** — was a dependency updated? Is there a version mismatch?

Output: Write `isolation.md` in the shared work directory:
```markdown
# Bug Isolation

## Affected Component
[Frontend / Backend / Infrastructure]

## Affected Files
- `path/to/file.ts` — [what this file does and why it's relevant]

## Root Cause Location
- File: [path]
- Line: [line number]
- Function/Component: [name]
- Explanation: [why this causes the bug]
```

## Step 3: Diagnose

Understand *why* the bug happens.

- **Classify the bug type:**
  - Logic error (wrong condition, wrong calculation)
  - Off-by-one error (boundary conditions)
  - Null/undefined access (missing null check)
  - Race condition (async timing)
  - Type mismatch (wrong data shape)
  - Integration mismatch (API contract difference)
  - Configuration error (wrong env var, wrong path)
  - State management error (stale state, missing update)

- **Check for similar patterns** — grep the codebase for similar patterns that might have the same bug
- **Check for cascading effects** — does fixing this break anything else?

Output: Update `isolation.md` with the diagnosis section:
```markdown
## Diagnosis
- Bug type: [classification]
- Root cause: [explanation of why]
- Similar patterns found: [yes/no, list files if yes]
- Cascading effects: [list any dependent code that might be affected]
```

### Systemic pattern protocol (mandatory when the root cause is a shared mechanism)

When the root cause lives in a **shared mutation, mapper, extension, or helper** (not a single call site), the bug is a *class*, not an instance. Before proposing a fix:

1. **Enumerate every consumer of the shared mechanism** — persistence writers, API/PATCH DTO builders, comparison/equality gates, retry/status logic, log writers. Make it a checklist with file:line each.
2. **Classify each consumer's contract** — what does null/empty/sentinel mean *there*? (e.g. null = "omit field" in a PATCH DTO vs null = constraint violation in a non-nullable DB column vs sentinel = equality participant in a comparer.)
3. **Trace round-trips** — persist → reload → re-send. A value that is safe in memory can change meaning after a round-trip (null coalesced to `""`, sentinel persisted as data).
4. **Name latent twins** — other paths that share the mechanism but did not crash *this time* (initial-load vs batch, create vs update). They are in scope for the fix plan even if dormant.
5. The fix plan must state, per consumer, whether it is fixed, deliberately unchanged (with reason), or deferred (with follow-up vehicle).

Skipping this protocol converts one fix into N serial QA discoveries.

## Step 4: Fix

Apply the minimal fix.

- **Fix only the bug.** Do not refactor, optimize, or change unrelated code.
- **If the fix requires refactoring to be safe**, note it as a follow-up, not part of this fix.
- **Add a test that reproduces the bug first**, then fix it. This prevents regression.
- **Keep the fix minimal.** The smaller the diff, the easier to review.

Fix checklist:
- [ ] Test written that reproduces the bug (test fails before fix, passes after)
- [ ] Minimal fix applied
- [ ] No unrelated changes in the diff
- [ ] Similar patterns checked — no other instances of same bug
- [ ] Fix doesn't break existing tests
- [ ] File manifest updated

## Step 5: Verify

Confirm the fix works and nothing else broke.

- **Run the reproduction test** — it should now pass
- **Run the full test suite** — no regressions
- **Verify through the serving layer** — if the app serves cached materialized artifacts (snapshot files, generated reports, built bundles), builder-side fixes are invisible until artifacts are rebuilt. Find the rebuild path (prefer disk-only, no external API calls), rebuild, then re-check the endpoint/UI the user actually sees.
- **Check edge cases** — related boundary conditions
- **Verify the fix matches the approved plan** — no scope creep

Output: Update `file-manifest.md` with:
```markdown
## Fix Verification
- Reproduction test: [pass/fail]
- Full test suite: [pass/fail]
- Edge cases checked: [list]
- Scope matches plan: [yes/no]
```

## Common Pitfalls

1. **Don't fix symptoms.** Fix the root cause.
2. **Don't add defensive code without fixing the root cause.** A null check that hides the real bug is not a fix.
3. **Don't refactor while fixing.** Refactoring and bugfixing in the same PR makes review harder.
4. **Don't skip the reproduction step.** If reproduction fails, the fix cannot be verified.
5. **Don't assume single cause.** Some bugs have multiple contributing factors. Check for them.
6. **Don't stop at green tests.** The user's symptom lives in what the serving layer delivers. A green builder test + a stale cached artifact = still broken in the UI. Reproduce the user-visible value end-to-end after the fix.
7. **Don't fix only the crashing instance.** If the root cause is a shared mechanism, run the systemic pattern protocol (Step 3) — guarding one call site leaves the bug class alive.
