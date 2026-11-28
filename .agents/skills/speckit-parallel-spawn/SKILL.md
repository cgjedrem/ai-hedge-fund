---
name: speckit-parallel-spawn
description: Run multiple Spec Kit pipelines in parallel isolated worktree coordinator sessions without collisions. Owned by architect for multi-spec fan-out (1 worktree = 1 coordinator), covering spec-number reservation, seam ownership, provider selection (Copilot vs Ollama), A2A-Compact pointer-only kickoffs, and merge-stack safety. Do not use for a single speckit run.
---

# Parallel Spec Kit Spawns

Learned 2026-10-27 (session: 4 parallel speckit children, specs 504-507) and upgraded for the two-stage `architect` -> `coordinator` worktree architecture.
Parallelism is owned exclusively by `architect` (`create_session` with `agent: "coordinator"`); `coordinator` executes strictly one spec inside its assigned worktree (`1 worktree = 1 coordinator`).

## Failure modes this prevents

| Failure | Cause | Prevention |
|---|---|---|
| N children grab the same spec number (observed: 3x `504-*`) | Each computes "next number" from the same base | Reserve numbers at spawn time (below) |
| Duplicate seam implementations (twin predicate written twice) | Two specs need the same contract | One child OWNS each shared interface; others reference-only |
| Parent/child write race on a branch | Parent merges/resolves while child pushes | Child branch = child-owned until FINAL report |
| Cross-spec corrections never arrive | Parent lacked outbound session channel | Parent needs `send_session_message`; kickoffs list sibling session IDs |
| Blocked children loop forever | Re-ask into a void without a scoped decision | Use documented defaults only within approved scope; escalate authorization/acceptance questions |
| Child dies silently mid-run — no branch, no FINAL report | Spawn construction failure or session crash | Check child session liveness (`get_session` / `get_sessions_status`: `active_session_id`, `activity`, `last_error`) and local worktree state (`git worktree list`, `git status --porcelain`, `specs/<n>/progress/`) first; check `git ls-remote origin <expected-branch>` only when remote push was authorized. Respawn ONLY after confirming the child session has stopped/failed, preserving any partial worktree changes |
| Every child merge conflicts on `tasks.md` checkboxes (observed 2026-11-19, spec 513: 5+ union resolutions, replayed again at every rebase) | All children check boxes in the same shared file | **Scoped to children sharing ONE feature's task list**: such children NEVER edit that tasks.md; each writes `specs/<n>/progress/<child-slug>.md` listing completed task IDs. Parent checks the boxes once at integration. Children running independent pipelines (own spec dir, own tasks.md) keep the normal lifecycle — they create and update their own tasks.md |
| Parent can't reach a running child mid-flight (observed 2026-11-19, spec 513: write_agent "No agent found") | `read_agent`/`write_agent` take task-agent handles; app session IDs from `create_session` are a different ID space | Kickoffs state "parent will not message mid-flight; report blockers in your FINAL report". Corrections go via the session messaging tool only; if unavailable, relay through the user |
| Runaway credit burn across N parallel children | Unpinned models inheriting parent Opus or pasting 5KB specs into kickoffs | Pin provider/model routing explicitly when requested (`--provider copilot|ollama`) and enforce `A2A-Compact` pointer-only kickoffs (`<=250` words) |

## Provider selection at spawn time (`--provider copilot | ollama`)

- **Default (no explicit provider override):** Omit `kickoff.model` and `kickoff.reasoning_effort` so the child `coordinator` uses its `.agent.md` `model:` priority array (`gpt-6.1-terra` primary with Ollama Cloud fallback, or Ollama primary if the workspace was switched via `switch-model-profile.ps1 -Provider ollama`).
- **Explicit `--provider ollama` for a batch/child:** Pass `kickoff.model: "73192633-e8b9-4870-90db-123a98a64cc1/glm-5.3-flash:cloud"` (or the discovered `<ollama_uuid>/glm-5.3-flash:cloud` ID from `switch-provider`) and state `Active provider: ollama` in `Routing:` so the child knows Ollama Cloud is active for the session.
- **Explicit `--provider copilot` or user-named model:** Pass `kickoff.model: "gpt-6.1-terra"` (or the user's exact named model + effort verbatim). Never silently substitute a user-named model; if rejected, report the exact error and ask the user.
- **Claude Code fallback (`Frivillig-vite`, `Ungfritid-vite`, or CLI without `create_session`):** Emit ready-to-run `claude --worktree <spec-slug> --agent coordinator` commands per spec with the same pointer-only kickoff file written under `specs/<n>/kickoff.md`.

## Spawn-time checklist (`architect` parent)

1. **Reserve spec numbers.** Before kicking off, compute the free range from
   BOTH local `specs/` AND remote in-flight branches:
   `git ls-remote origin | grep -i speckit` plus `gh pr list --state open`.
   Assign each child an explicit number (`spec 505`, `spec 506`, ...) in its
   kickoff. Never let parallel children self-compute.
2. **Pin seams.** For every shared contract between pieces, name the owner
   child in ALL kickoffs ("child B owns `ITwinLookup`; child C consumes via
   reference, do not implement a default").
3. **List siblings.** Put every sibling's session id + one-line scope in each
   kickoff so children can coordinate directly when contracts drift.
4. **Kickoff contract (`A2A-Compact`, `<=250` words).** Invoke `create_session`
   with `workspace_type: "worktree"`, `notify_on_idle: "once"`,
   `coordinate_with_creator: true`, and `kickoff.agent: "coordinator"`. Use the
   `Child-session kickoff template` in `.github/agents/coordinator.agent.md`
   (pointer-only: cite `specs/<n>/spec.md`, `plan.md`, `tasks.md` paths instead
   of pasting artifact bodies); fill the verbatim request separately from parent
   instructions, exact deliverable, authorized mutations, prohibitions,
   validation/automatic-CI expectations, one Gate 1 status, user-named routing,
   parent session ID and provider, and report fallback. Do not add a commit,
   issue, PR or push unless requested. Documented defaults cannot expand
   authority or bypass required acceptance. The final-report line ends the turn
   without follow-up questions; finish cleanup before reporting. Put state
   (READY/BLOCKED/NEEDS_APPROVAL), verdict, deliverable and blockers first after
   the existing FINAL header so truncation does not hide them. A blocked pipeline
   uses the same header and channel. Append spec reservation, seam ownership, and
   sibling IDs.
   Also pin in every kickoff whose child shares the parent's task list
   (shared-feature fan-out): "Do NOT edit specs/<n>/tasks.md — write your
   completed task IDs to specs/<n>/progress/<your-slug>.md instead; the parent
   integrates checkboxes. This applies recursively: if you delegate to workers
   (speckit-implement DELEGATED_WORKER or otherwise), forbid them from editing
   the shared tasks.md too — they report completed task IDs in their FINAL
   report, and you validate via your progress file, not task checkboxes."
   Children owning an independent spec (own tasks.md) get no such restriction.
   Every kickoff also states: "The parent will not message you mid-flight;
   report blockers in your FINAL report." (Observed 2026-11-19 spec 513:
   tasks.md checkbox edits conflicted on every merge and rebase replay, and
   write_agent rejects app session IDs.)
5. **Handle and attachment provenance.** Record app session IDs with their
   provider and creation result; never send them to `read_agent`/`write_agent`,
   which require task-agent handles. Validate that forwarded attachments still
   belong to the creator's staged upload area before fan-out. A stale attachment
   failure pauses the affected fan-out until the input is corrected; do not
   silently drop required evidence or retry it for every sibling.
6. **Verify child liveness and worktree state before respawning.** A missing
   FINAL report proves nothing, and an authorized local-only child will never
   push a remote branch. Check `get_session` / `get_sessions_status`
   (`active_session_id`, `activity`, `last_error`) and inspect the child's local
   worktree (`git worktree list`, `git status --porcelain`, `git log -1`,
   `specs/<n>/progress/`) first; check `git ls-remote origin <expected-branch>`
   only when remote push was explicitly authorized. Never respawn while a child
   session is still active or busy — respawn ONLY after confirming the child has
   stopped or failed, and preserve any surviving local worktree changes rather
   than launching a duplicate writer. Cross-session nudges need the
   session-messaging tool with an app session ID; `read_agent`/`write_agent`
   take task-agent handles only. When the session-messaging tool is unavailable,
   inspect the local worktree and git refs directly.

Automatic CI from an authorized PR is not an extra manual cloud validation
command. Respect explicit CI restrictions too; ask about genuine conflicts rather
than withholding a requested deliverable or assuming broader permission.

## Merge-time rules

- Stack PRs base->head in dependency order; merge bottom-up promptly. A stale
  base under a stack cascades conflicts downward.
- Parent never edits a child-owned branch without first checking
  `git ls-remote origin <branch>` for fresh commits and coordinating with the
  owner session.
- Renumber collisions at merge time by repo precedent (renumber-after-rebase),
  preferring the next free number across BOTH merged and open spec PRs.
- After any multi-branch rebase cascade, diff the file inventory of each
  branch tip against its pre-rebase tip (`git diff --stat <old-tip> <new-tip>`);
  a missing test/source file means a silently dropped commit — restore it
  before pushing. (Observed 2026-11-18: US2's test commit vanished mid-cascade,
  caught only by a tip build failure.)

## Stacked-PR stale merge ref

After rebasing a stacked PR's base, GitHub may keep testing the OLD merge ref
and report DIRTY/CONFLICTING forever, even when `git merge-tree` is clean and
GraphQL stack protection blocks base edits. Recovery: try a real head-touch
push first (a new commit on the head forces re-evaluation); if that fails,
close-and-recreate the PR — branch and commits survive; reference the old PR
in the new body.

## Verify after kickoff

- Each child's first turn should acknowledge its assigned spec number and seam
  ownership. A child planning with the wrong number = kickoff failure; correct
  immediately via `send_session_message`.
