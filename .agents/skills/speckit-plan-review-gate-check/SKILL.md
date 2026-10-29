---
name: speckit-plan-review-gate-check
description: Check that spec.md and plan.md are committed, pushed, and under an open PR before allowing task generation
compatibility: Requires spec-kit project structure with .specify/ directory
metadata:
  author: github-spec-kit
  source: extension:plan-review-gate
---

# Plan Review Gate Check Skill

# Plan Review Gate — Pre-Tasks Check

This is a mandatory `before_tasks` gate. It blocks `/speckit.tasks` unless the spec and plan artifacts are committed, pushed, and under an open PR for review. Merge is NOT required at this gate — spec-kit features ship as a PR stack that is human-reviewed in dependency order before any merge (see `.specify/memory/constitution.md`, Development Workflow).

## Delegation

Canonical pattern: `.specify/docs/subsession-delegation.md`. Adaptation for this skill:

1. **Recursion guard**: if the current input contains the exact token `DELEGATED_WORKER`, skip this section and run inline.
2. **Default `inline`** — this gate is a deterministic git-state check; delegating costs more than it saves. Only delegate when `.specify/extensions/delegation.yml` explicitly overrides this skill to `subagent` and a subagent capability exists; invalid/missing config falls back silently to `inline`.
3. **When delegated**: Steps 1–4 run in a read-only subagent whose kickoff contains ONLY the `DELEGATED_WORKER` token, this skill's name, the repo root, and an instruction to read `.agents/skills/speckit-plan-review-gate-check/SKILL.md` and execute Steps 1–4. The orchestrator emits the gate decision (Step 5) and performs any waiver bookkeeping (Step 3, writes `gate-waivers.md`) itself.

## Steps

### 1. Locate Feature Artifacts

Run `.specify/scripts/bash/check-prerequisites.sh --json` from the repo root and parse the output to determine the FEATURE_DIR. If the script is not available, search for the most recent `specs/*/plan.md` relative to the repo root.

Verify that both `spec.md` and `plan.md` exist in FEATURE_DIR. If either is missing, ERROR and stop:

```
BLOCKED: spec.md and plan.md must both exist before running /speckit.tasks.
Run /speckit.specify and /speckit.plan first.
```

### 2. Resolve Review Target Branch

Start with `.specify/extensions/plan-review-gate/plan-review-gate-config.yml`. This repository-shared file selects the branch the spec-artifacts PR is expected to target; it is not an authorization to skip review, merge, or task generation.

1. If the file is absent, or its `target_branch` value is blank, preserve the existing review-target fallback: resolve `origin/HEAD` with:

   ```bash
   git symbolic-ref refs/remotes/origin/HEAD 2>/dev/null | sed 's@^refs/remotes/origin/@@'
   ```

   If that fails, fall back to `main`, then `master`.

2. If the file exists, parse it with an installed YAML parser. In this repository, use `py -3` with PyYAML; do not infer the value with line-oriented text parsing. Safely load a YAML mapping, read only `target_branch`, treat YAML null or the exact empty string as blank, and BLOCK if the document cannot be parsed, is not a mapping, or has a non-string non-null value. Do not silently use the fallback after a malformed configuration.

3. For a non-empty configured value, require a remote branch name without the `origin/` prefix. Validate the exact scalar with Git before using it as the expected PR base:

   ```bash
   case "$configured_target_branch" in
     origin/*) echo "BLOCKED: .specify/extensions/plan-review-gate/plan-review-gate-config.yml target_branch must not include origin/."; exit 1 ;;
   esac
   validated_target_branch="$(git check-ref-format --branch "$configured_target_branch" 2>/dev/null)" ||
     { echo "BLOCKED: .specify/extensions/plan-review-gate/plan-review-gate-config.yml has an invalid target_branch."; exit 1; }
   test "$validated_target_branch" = "$configured_target_branch" ||
     { echo "BLOCKED: .specify/extensions/plan-review-gate/plan-review-gate-config.yml target_branch must be an unexpanded remote branch name."; exit 1; }
   ```

   If the value includes `origin/`, is invalid, or Git normalizes it, BLOCK and name the invalid configured value. Do not concatenate an unvalidated value into a remote ref and do not fall back to `origin/HEAD`, `main`, or `master`.

4. For a valid non-empty configured target, verify that it exists on `origin`:

   ```bash
   git ls-remote --heads origin "refs/heads/{target_branch}"
   ```

   If `git ls-remote` succeeds with no matching head, BLOCK: `Configured review target origin/{target_branch} does not exist on origin.` If it cannot query `origin`, BLOCK with that exact connectivity/authentication failure. Do not fall back after any configured-target failure. No fetch of the remote-tracking ref is required: the gate no longer reads artifact contents from `origin/{target_branch}` — the PR check in §4 uses the live forge API.

Set `{target_branch}` to the validated configured target or to the existing fallback result.

### 3. Waivers and Overrides

**Waiver (audited, works with configured targets).** If the user explicitly supplies `--waiver "<reason>"` in `/speckit.tasks` arguments via `$ARGUMENTS`, the gate may pass despite artifacts not under open PR review, provided it first appends a record to `{FEATURE_DIR}/gate-waivers.md` (create the file if absent):

```markdown
## Plan-review gate waiver — YYYY-MM-DD

- **Reason**: <user-supplied reason>
- **Branch state**: <current branch>, artifacts not under open PR review targeting origin/{target_branch}
- **Direction**: explicit user direction in session
```

Then print:

```
Plan review gate: WAIVED (audited)
Waiver recorded in {FEATURE_DIR}/gate-waivers.md. Artifacts still require review and merge of the PR stack before implementation merges.
```

The waiver keeps the audit trail the gate exists for while unblocking single-maintainer flows. It never bypasses the clean-worktree requirement for the artifacts (drift detection still applies), and it does not authorize skipping review of the eventual PR stack.

**Generic override (fallback workflows only).** For an unconfigured fallback workflow only, retain the extension's existing generic behavior: if the user explicitly supplies `--skip-review` in `/speckit.tasks` arguments via `$ARGUMENTS`, the gate may skip its Git artifact checks and print:

```
Plan review gate: SKIPPED (explicit generic --skip-review)
Warning: proceeding without an open plan-review PR. This fallback-only legacy override is not a configured review-target remedy.
```

Never offer the generic override in a blocked result. The waiver MAY be offered in a blocked result when the user is present and the flow is single-maintainer.

### 4. Check Artifacts Are Committed, Pushed, and Under Review

For each artifact (`spec.md` and `plan.md`), run three checks:

1. **Clean worktree** — no uncommitted changes:

   ```bash
   git status --porcelain -- {FEATURE_DIR}/spec.md {FEATURE_DIR}/plan.md
   ```

   Non-empty output means uncommitted changes — BLOCKED.

2. **Pushed** — the current branch has an upstream and no unpushed commits touch the artifacts:

   ```bash
   git rev-parse --abbrev-ref --symbolic-full-name @{u}
   git log --oneline @{u}..HEAD -- {FEATURE_DIR}/spec.md {FEATURE_DIR}/plan.md
   ```

   No upstream means the branch was never pushed — BLOCKED. Non-empty `git log` output means commits touching the artifacts are not on the remote — BLOCKED.

3. **Open PR** — an open pull request exists whose head is the current branch:

   ```bash
   gh pr list --head {current_branch} --state open --json number,baseRefName,url
   ```

   - If `gh` is unavailable or authentication fails, WARN and degrade this check to "committed + pushed" only; record the degraded check in the gate output. Do not BLOCK solely because the forge CLI is missing.
   - No open PR for the branch — BLOCKED.
   - When `{target_branch}` came from a non-empty configured value, the PR's `baseRefName` MUST equal `{target_branch}`; a mismatch is BLOCKED naming the actual base. Under the unconfigured fallback, accept any base and note it in the output.

### 5. Gate Decision

**If BOTH artifacts are committed, clean, pushed, and covered by an open PR (with matching base when configured):**

```
Plan review gate: PASSED
spec.md and plan.md are committed, pushed, and under open PR review: {pr_url} (base: {base_ref}) — proceeding to task generation.
```

Allow `/speckit.tasks` to continue.

**If ANY check in §4 fails:**

Report exactly which checks failed and stop execution. Do NOT allow task generation to proceed.

```
BLOCKED: spec.md and plan.md must be committed, pushed, and under an open PR for review before running /speckit.tasks.

Review target branch: origin/{target_branch}
The following checks failed:
- {list each failed check with its reason: uncommitted changes / branch not pushed / unpushed artifact commits / no open PR / PR targets wrong base}

To unblock:
1. Commit the spec artifacts: git add {FEATURE_DIR}/ && git commit -m "Add spec and plan"
2. Push the branch: git push -u origin {current_branch}
3. Open a PR for review (draft is fine): gh pr create --draft --base {target_branch}
4. Re-run /speckit.tasks

Merge is NOT required at this gate — the PR stack is human-reviewed in dependency order before any merge.

Single-maintainer alternative: re-run /speckit.tasks with --waiver "<reason>" to record an audited waiver (see Waivers and Overrides).

This gate ensures implementation plans are under review before task generation begins.
```

**IMPORTANT**: When blocked, you MUST stop execution entirely. Do NOT continue with task generation. The open-PR requirement is a mandatory reviewed-artifact check, not a bypass.

## Key Rules

- This is a hard gate by default — it blocks task generation unless spec.md and plan.md are committed, clean, pushed, and under an open PR
- Merge to the review target is NOT required at this gate; the stack is human-reviewed in dependency order before merging
- `target_branch` selects the branch the spec-artifacts PR must target; it never authorizes review, merge, or task generation
- A non-empty configured target is Git-validated and verified on `origin`; invalid or missing targets block without fallback
- With no configured target, preserve the `origin/HEAD`, `main`, then `master` fallback, and accept any PR base
- The audited `--waiver` mechanism (549 retro) records to `gate-waivers.md` and never bypasses the clean-worktree requirement
- The existing explicit generic `--skip-review` override applies only to unconfigured fallback workflows; it is not available for a configured target and is never suggested when blocked
- The check is based on Git and forge state, not user confirmation
- Only spec.md and plan.md are checked (other artifacts like research.md are not required)