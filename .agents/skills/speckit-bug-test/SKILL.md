---
name: speckit-bug-test
description: Validate that a previously fixed bug is resolved and record the verification
  report
compatibility: Requires spec-kit project structure with .specify/ directory
metadata:
  author: github-spec-kit
  source: preset:agent-team
---

# Speckit Bug Test Skill

# Test Bug Fix

Validate that the fix recorded by `/speckit-bug-fix` actually resolves the bug described by `/speckit-bug-assess`. The output is a verification report at `.specify/bugs/<slug>/test.md`.

## User Input

```text
$ARGUMENTS
```

The user input should identify the bug to validate. Accept any of:

- `slug=<bug-slug>` or `--slug <bug-slug>` or a bare slug-like token.
- A path that contains the slug (e.g. `.specify/bugs/login-timeout/`).
- **Nothing** — fall back to context (see below).

## Slug Resolution

Resolve `BUG_SLUG` in this order, stopping at the first match:

1. **Explicit user input** — a slug passed in `$ARGUMENTS` (any of the forms above).
2. **Conversation context** — if the current session has just run `/speckit-bug-assess` or `/speckit-bug-fix`, the slug it reported is the working slug. Reuse it without re-prompting. Confirm it by checking that `.specify/bugs/<slug>/fix.md` exists; if it does not, fall through.
3. **Single candidate on disk** — list `.specify/bugs/*/fix.md`. If exactly one bug has a `fix.md`, use it.
4. **Disambiguate**:
   - **Interactive mode**: ask the user which bug to validate and list the candidates.
   - **Automated mode**: stop with an error listing the candidates. Do not guess.

Once resolved, set `BUG_SLUG` and `BUG_DIR = .specify/bugs/<BUG_SLUG>`, and briefly state in your reply which resolution path was used (explicit / from context / single candidate / asked).

## Prerequisites

- `BUG_DIR/assessment.md` MUST exist.
- `BUG_DIR/fix.md` MUST exist. If not, stop and instruct the user to run `/speckit-bug-fix` first.
- If `BUG_DIR/test.md` already exists, ask the user whether to overwrite it (interactive mode) or refuse (automated mode).
- Read both `assessment.md` and `fix.md` in full so you know:
  - The original symptom and reproduction steps (from `assessment.md`).
  - The actual code changes and tests added (from `fix.md`).

## Execution

1. **Plan the validation**
   - Assign each acceptance criterion an ID. Bind every result to revision plus
     local changes (diff identity), or build ID/digest; environment, scenario,
     timestamp and provenance (executor/reporter and log/artifact reference).
     Keep static, build, runtime and user report evidence distinct. A user
     report is attributed and quoted, not relabeled as agent execution.
   - Behavior-affecting changes, including review fixes, invalidate affected
     rows and final approval pending rerun; mark them `INCONCLUSIVE` and retain
     superseded evidence. Evidence from an earlier revision cannot pass the
     changed behavior. Explicitly justify any unaffected rows retained.
   - Use the assessment's adjacent-state and negative-path integration matrix:
     denial/failure, recovery, cancellation/release and pending work as well as
     the happy path. Define expected thresholds and observation durations
     before running; record actual values and measured durations.
   - Decide which checks prove the bug is gone:
     - Re-run the reproduction steps from the assessment (or their automated equivalent).
     - Run the tests added or updated in the fix.
     - Run any broader regression suite that touches the changed files.
   - Decide which checks prove nothing was broken:
     - Existing test suites for the changed modules.
     - Lint / type-check if the project uses them.

2. **Run the checks**
   - Execute each planned check. Capture command, exit status, and a short excerpt of relevant output (last few lines, or the failing assertion).
   - Assign execution to a runtime owner with the required capability and
     environment. A read-only QA reviewer may inspect supplied evidence and
     deliver static findings, but must label runtime work `BLOCKED` and route
     it rather than claim execution. Missing device/tooling/permission is
     `BLOCKED`; ambiguous, stale or insufficient observations are `INCONCLUSIVE`.
   - If a check is destructive, network-dependent, or expensive, record it as
     `BLOCKED` pending explicit user consent; do not run it without consent.
   - Mocks establish reaction to injected events, not that an OS emits them.
     For mobile focus, separate fake-driven native decision tests from actual
     device/emulator call, alarm and playback event checks. Unit/build success
     cannot satisfy an Android call-interruption criterion.
   - Quote relevant output and retain full logs by reference. Capture native
     process exit status immediately; a log tail is not an exit status.

3. **Judge the outcome**
   - Mark the fix as:
     - **verified** — every required criterion has current adequate evidence and the original symptom no longer reproduces in the required scenario/environment.
     - **partial** — the original symptom is gone but unrelated regressions appeared, or some checks are inconclusive.
     - **failed** — the symptom still reproduces or the regression suite is broken by the fix.
     - **BLOCKED** — a required check cannot run due to access, tooling or permission.
     - **INCONCLUSIVE** — required evidence is stale, ambiguous or insufficient.
   - A known failure takes precedence; otherwise any required BLOCKED or
     INCONCLUSIVE row prevents verified. Partial never means acceptance.
   - Do not over-claim. If reproduction was not actually performed (e.g., the bug required a production environment), say so explicitly.

4. **Write the verification report**

   Write to `BUG_DIR/test.md` using this structure:

   ```markdown
   # Bug Verification: <short title>

   - **Slug**: <BUG_SLUG>
   - **Tested**: <ISO 8601 date>
   - **Assessment**: ./assessment.md
   - **Fix**: ./fix.md
   - **Result**: verified | partial | failed | BLOCKED | INCONCLUSIVE

   ## Summary

   <One or two sentences: does the bug reproduce, did the fix hold, were any regressions found.>

   ## Checks Performed

   | Criterion / check | Revision + local changes / build identity | Environment / scenario | Type / provenance / timestamp | Command / action / exit status | Expected threshold / duration | Observed values / measured duration | Result |
   |-------------------|-------------------------------------------|------------------------|-------------------------------|--------------------------------|-------------------------------|-------------------------------------|--------|
   | <ID; reproduction, new tests, regression or static check> | <commit + diff identity OR build ID/digest> | <exact context> | <static/build/runtime/user report; executor or reporter + artifact; time> | <exact invocation or steps; code if applicable> | <bound + required window> | <measurement, not inferred> | <PASS/FAIL/BLOCKED/INCONCLUSIVE> |

   ## Integration Regression Matrix

   | Criterion | Initial state / event | Expected state / side effects / forbidden behavior | Runtime owner / check mode | Evidence reference / result |
   |-----------|-----------------------|----------------------------------------------------|----------------------------|-----------------------------|
   | <ID> | <adjacent state or negative path> | <loop, timer, requests, warnings, recovery where relevant> | <executor; automatic/manual> | <current row / status> |

   ## Invalidated Evidence

   <Affected IDs, behavior change, superseded evidence identity and rerun result;
   justify retained unaffected evidence.>

   ## Output Excerpts

   <Short snippets of relevant output (e.g., final summary line of a test run, the failing assertion). Keep it tight — no full logs.>

   ## Residual Risks

   - <known limitation, environment not covered, etc.>

   ## Recommendation

   <One paragraph. Examples:>
   - "Close the bug — verified end-to-end."
   - "Hold — reproduction inconclusive; needs verification in staging."
   - "Reopen — symptom still reproduces; rerun `/speckit-bug-assess`."
   ```

5. **Report back** with:
   - The slug and `BUG_DIR/test.md` path.
   - The result (`verified`, `partial`, `failed`, `BLOCKED`, `INCONCLUSIVE`).
   - If the result is `failed`, recommend re-running `/speckit-bug-assess` with the new evidence captured in `test.md`.
   - Name the task, owner, automatic/manual check, observed result, blocker and
     next stop condition; do not invent ETAs or poll idle workers.
   - Before a model/owner switch, hand off symptom/repro, revision/environment,
     failed attempts, quoted evidence, hypothesis, unknowns and the smallest
     falsification check. Route by capability/risk, not a hardcoded model.
     Require new evidence before a second patch; after two failed attempts
     stop and reassess root cause rather than propose another speculative fix.

## Guardrails

- This command MUST NOT modify source code. It only runs checks and writes inside `.specify/bugs/<slug>/`.
- Never overwrite an existing `test.md` without confirmation.
- Never mark a fix as `verified` when the required reproduction was not exercised:
  use `BLOCKED` or `INCONCLUSIVE` with the reason and runtime owner.
- Final QA evidence approval is read-only review, not automatic runtime proof
  or commit, publish, or release consent. Later behavior changes reopen affected
  rows and approval even after a workflow run has completed.
