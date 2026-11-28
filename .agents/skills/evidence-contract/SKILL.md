---
name: evidence-contract
description: 'Acceptance evidence contract: what every acceptance row must record (identity, time, environment, scenario, provenance, result) and PASS/FAIL/BLOCKED/INCONCLUSIVE rules.'
---

# Acceptance evidence contract

## Evidence records

For every acceptance row, record:

| Field | Required content |
| --- | --- |
| Identity | Source revision AND dirty-diff digest (or immutable source snapshot); built/installed artifact ID or hash, with the source-to-artifact mapping |
| Time | Observation timestamp with timezone; start/end or measured duration when relevant |
| Environment | OS/platform version, device/emulator/browser, app/configuration, permissions and relevant external services |
| Scenario | Initial state, exact reproduction actions/events, expected results, negative and adjacent-state cases |
| Provenance | Observer/execution owner, evidence type, exact command and exit code or user report, and retained log/screenshot/trace reference |
| Result | Expected versus actual, exact measurements and units, PASS / FAIL / BLOCKED / INCONCLUSIVE |

Do not replace a measurement or quotation with a stronger claim. For example, a
reported "20 seconds" is not "a minute" or "stable indefinitely". Quote the exact
duration, count, latency, threshold and observation scope; unknown values stay unknown.

Evidence types are distinct: static review, build identity/build success, automated
unit/fake tests, runtime observation, and user report. A build proves compilation,
not installation or behavior. Static review and passing unit tests do not satisfy a
device interruption row. A user report remains attributed to that user; do not claim
it was independently reproduced. Screenshots establish only the states they show.

PASS means the row's expected result was observed with the required evidence type
and matching identity/environment. FAIL means an observed mismatch. BLOCKED means
the required execution capability, environment, access or artifact is unavailable;
name the owner and unblock action. INCONCLUSIVE means evidence is missing, stale,
ambiguous or insufficient to decide. Neither BLOCKED nor INCONCLUSIVE is a pass.
An excluded scenario needs an explicit applicability rationale, not a fabricated pass.

## Invalidation and final gate

After any behavior-changing implementation or review edit, mark affected acceptance
rows INCONCLUSIVE (stale), retain the historical observations, and assign a fresh run
on the final artifact. Record the changed behavior and affected rows; justify any
unaffected evidence carried forward. If impact is uncertain, reopen the wider set.
Rebuilding without exercising affected scenarios does not restore acceptance.

Keep the pre-implementation review gate. After implementation and the last review
edit, require current static review AND current evidence for every required runtime
row before acceptance/release-ready claims. Reopen this gate after any later
behavior change. A human may choose to proceed with a documented risk, but that
decision does not turn missing evidence into PASS. Commit, PR and release approval
remain separate authorizations.

## Platform integration matrix

Assessment defines expected outputs before fixing; implementation tests the changed
decision logic using pure/fake-driven native tests; verification executes the platform
matrix on a supported device/emulator. A fake proves the reaction to an event, not
that the OS emits it for every call, alarm or external app.

For any platform integration cover success, denial/unavailable capability, interruption,
retry/recovery, cancellation/release, stale pending work and adjacent lifecycle states.
For mobile audio focus, record expected loop, timer, focus requests, warnings and
recovery for each row:

- Permanent media loss with other playback active, paused and stopped.
- Transient loss with no music stream active; no requests until the allowed restore.
- Duck and gain.
- Request denial, retry, recovery and warning cleanup.
- Phase transition, retry button, pause/resume, mute/unmute and release while blocked.
- Pending poll followed by transient loss, silence or release.

Do not infer platform behavior from another platform or from absence of an error.
Escalate unsupported assumptions with a smallest runnable falsification experiment.

## Execution ownership and repair

Assign build, native test, device/emulator and other runtime work to an execution-
capable agent with the needed tools and environment. Backend includes explicitly
delegated native integration and device verification. QA stays read-only: deliver
useful static findings, audit provided evidence, and label unexecuted runtime work
BLOCKED/routed with its execution owner. Never discard static work merely because
the runtime portion is blocked.

Before a second patch for the same symptom, obtain new evidence that distinguishes
the current hypothesis from an alternative. Repeated failed repairs require a
root-cause reassessment, not another speculative variation. Stop on unsupported
platform assumptions or stalled repair; request missing capability, user input or
a risk-appropriate capability-tier escalation. Respect the workflow's rework limit.

A gate that stays BLOCKED after one discriminating experiment is not a reason to
keep the session running. Write a structured blocked-handoff (symptom, evidence,
blocker, owner, unblock action) into session artifacts, notify the user, and stop.
A blocked-handoff is a terminal state for that session, not a queue for further
attempts; resuming requires the named unblock action, not more churn.

Choose capability tiers by uncertainty, platform complexity and cost of error;
routine bounded work can use a standard tier, while cross-layer/OS behavior and
repeated failed repairs call for stronger reasoning or relevant execution capability.
No fixed model/provider or forced effort is prescribed. Honor explicit user settings;
propose conflicting changes for approval rather than silently replacing them.

Every handoff includes symptom, reproduction and artifact identity, failed attempts,
exact evidence, current hypothesis, unknowns and the smallest falsification experiment.
A receiving model reassesses those facts independently and does not inherit prior
success claims. Configuration, registry names and copied prompts do not prove an
active session loaded them; verify loading separately without forcing a reload.

Progress updates name current task, execution owner, check mode (automatic/manual/
read-only), latest observed result, blocker, and next stop condition. Report at
meaningful boundaries; no unsupported ETA, idle polling or notification loops.

## Source and installed copies

Map each source to its generated/installed consumer before editing. Preserve command
placeholders and local customizations. Compare governed sections separately from
whole-file identity; propagate only intended changes. A real directory is not an
automatic sync. Do not rerun setup or copy a catalog blindly. Validate the supported
workflow/schema format, source/generated parity and final evidence gate after review.

### Installation and loading acceptance

For changes to agents, workflow-wrapped skills or their dependencies, keep four
identities separate: canonical source revision plus dirty-diff digest; repository
consumer; installed/discovery copy; and effective definition loaded by a session.
Use package `sync.yml` ownership and `workflow_skill_sources` mappings when present.
Record exact paths, hashes or governed-section digests and observation times for
each layer; a matching name, copied file or passing source test proves no later layer.

Before any authorized installation, compare all mapped layers and dependencies,
including referenced governance docs, helper scripts, skills and hooks. Preserve
local customization, repo-only blocks and repo-owned frontmatter. Check hook paths,
shells, event schemas, permissions and portability for the target harness; never
copy a repo-specific hook into another package merely because its agent is shared.
Missing dependencies block acceptance; do not silently omit a contract or hook.

Verify installation with format/frontmatter checks and governed-section parity,
separately from whole-file differences. Verify loading separately using available
effective-prompt/source diagnostics tied to a session and timestamp, including
applicable instruction/hook sources and precedence. Persona self-identification alone
is not proof. In an explicitly authorized isolated test context, smoke-test each
applicable hook's trigger and expected result, retaining redacted evidence. Mark an
inapplicable hook N/A only with a rationale. If diagnostics or a safe execution
context are unavailable, record BLOCKED; ambiguous/stale loading evidence is
INCONCLUSIVE. Neither is delivered acceptance.

Approval to edit sources or open a sync PR does not authorize user-level installation,
live hook execution, a restart or reload. Never overwrite `~/.copilot` or require an
active session to reload to satisfy this gate. Report source work as ready separately
from blocked/unverified installation or loading; arrange a user-approved later check.

## Windows PowerShell 5.1

Use the editor/patch tool for authored files. `Set-Content -Encoding UTF8` in Windows
PowerShell 5.1 adds a BOM; it is NOT a BOM-free writer. For script serialization:

```powershell
$utf8 = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText($queryPath, $query, $utf8)
gh api graphql -F "query=@$queryPath"
$code = $LASTEXITCODE
if ($code -ne 0) { exit $code }
```

Use `-F` (file expansion), not `-f`, for a GraphQL query file. Use `author` for
GraphQL review-comment identity. Prefer explicit variables/arguments to nested
quoting. Capture `$LASTEXITCODE` immediately after EVERY native command; gate each
dependent step and propagate failure from scripts. A log tail, pipeline success or
`$?` after another command is not the native exit code. Retain full logs as evidence
and display concise tails separately. Do not infer success from empty output.
