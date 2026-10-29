---
description: "Create a feature branch with sequential or timestamp numbering"
---

# Create Feature Branch

Create and switch to a new git feature branch for the given specification. This command handles **branch creation only** — the spec directory and files are created by the core `__SPECKIT_COMMAND_SPECIFY__` workflow.

## User Input

```text
$ARGUMENTS
```

You **MUST** consider the user input before proceeding (if not empty).

## Environment Variable Override

If the user explicitly provided `GIT_BRANCH_NAME` (e.g., via environment variable, argument, or in their request), pass it through to the script by setting the `GIT_BRANCH_NAME` environment variable before invoking the script. When `GIT_BRANCH_NAME` is set:
- The script uses the exact value as the branch name, bypassing all prefix/suffix generation
- `--short-name`, `--number`, and `--timestamp` flags are ignored
- `FEATURE_NUM` is extracted when the final path segment starts with a numeric or timestamp feature marker (for example `042-name`, `feat/042-name`, or `jdoe/app/042-name`), otherwise set to the full branch name

## Prerequisites

- Verify Git is available by running `git rev-parse --is-inside-work-tree 2>/dev/null`
- If Git is not available, warn the user and skip branch creation

## Branch Numbering Mode

Determine the branch numbering strategy by checking configuration in this order:

1. Check `.specify/extensions/git/git-config.yml` for `branch_numbering` value
2. Check `.specify/init-options.json` for `feature_numbering` value (inherit from core)
3. Check `.specify/init-options.json` for `branch_numbering` value (deprecated, backward compatibility — will be removed in a future release)
4. Default to `sequential` if none of the above exist

## Branch Name Template

Check `.specify/extensions/git/git-config.yml` for an optional `branch_template` value. If it is empty or missing, use the default branch shape `{number}-{slug}`. If it is set, `{slug}` must not appear before `{number}`, its final path segment must start with `{number}-`, and the script expands these tokens:

- `{author}`: sanitized Git config author (`user.name`, falling back to the email local part)
- `{app}`: sanitized Spec Kit init directory name
- `{number}`: sequential number or timestamp
- `{slug}`: generated short branch slug

For monorepos, a template such as `{author}/{app}/{number}-{slug}` creates names like `jdoe/web/008-guided-tour` while preserving per-project feature numbering.

The script also accepts `branch_prefix` as a shorthand for simple namespaces; it expands to `<branch_prefix>/{number}-{slug}`.

## Execution

Generate a concise short name (2-4 words) for the branch:
- Analyze the feature description and extract the most meaningful keywords
- Use action-noun format when possible (e.g., "add-user-auth", "fix-payment-bug")
- Preserve technical terms and acronyms (OAuth2, API, JWT, etc.)

Run the appropriate script based on your platform:

- **Bash**: `.specify/extensions/git/scripts/bash/create-new-feature-branch.sh --json --short-name "<short-name>" "<feature description>"`
- **Bash (timestamp)**: `.specify/extensions/git/scripts/bash/create-new-feature-branch.sh --json --timestamp --short-name "<short-name>" "<feature description>"`
- **PowerShell**: `.specify/extensions/git/scripts/powershell/create-new-feature-branch.ps1 -Json -ShortName "<short-name>" "<feature description>"`
- **PowerShell (timestamp)**: `.specify/extensions/git/scripts/powershell/create-new-feature-branch.ps1 -Json -Timestamp -ShortName "<short-name>" "<feature description>"`

**IMPORTANT**:
- NEVER hand-derive the feature number by scanning local `specs/` directories — always let the script resolve it. The script checks local specs, local and remote branches, live remote heads, and spec directories merged into the remote default branch; a local-only scan misses numbers claimed elsewhere, and parallel sessions then collide on the same number.
- Do NOT pass `--number` when creating a branch — the script determines the correct next number automatically.
- If branch creation must be skipped (for example in an agent worktree/session that commits to its own session branch), still resolve the number with this script: run it with `--dry-run`/`-DryRun` (numbering only — creates no branch), parse `FEATURE_NUM` from the JSON output, and pass that number explicitly to the core spec workflow (`--number`/`-Number` on `create-new-feature`, or as the `NNN` prefix of `SPECIFY_FEATURE_DIRECTORY`).
- The resolved number is a best-effort claim at resolution time — a parallel session can take the same number before you commit. If the spec directory or branch already exists when you try to create it, re-run the resolution and take the next number; do not force-reuse a taken number.
- Always include the JSON flag (`--json` for Bash, `-Json` for PowerShell) so the output can be parsed reliably
- Run this script only once per feature for branch creation; a `--dry-run` numbering re-check after a conflict is the allowed exception

**App-managed worktrees**: when the session context indicates an app-managed worktree or session branch (e.g. a Copilot workspace with a dedicated branch already assigned), the harness owns the branch lifecycle — never create or switch branches.
- **PowerShell**: add `-NoBranch`, e.g. `.specify/extensions/git/scripts/powershell/create-new-feature-branch.ps1 -Json -NoBranch -ShortName "<short-name>" "<feature description>"`. Computes `BRANCH_NAME`/`FEATURE_NUM` only (numbering stays remote-aware); the JSON adds `"DRY_RUN": true` — expected.
- **Bash**: the twin has **no** `--no-branch` flag, and unknown flags are not rejected — they join the feature description and the branch is still created. Use `--dry-run` instead (same no-checkout result).
- Record the deviation in the spec's `**Feature Branch**` header: session branch name plus `(app-managed worktree; branch creation skipped, numbering applied)`.
- The JSON output will contain `BRANCH_NAME` and `FEATURE_NUM`
- Do not manually expand `branch_template`; the script reads the git extension config and applies it consistently

## Graceful Degradation

If Git is not installed or the current directory is not a Git repository:
- Branch creation is skipped with a warning: `[specify] Warning: Git repository not detected; skipped branch creation`
- The script still outputs `BRANCH_NAME` and `FEATURE_NUM` so the caller can reference them

## Output

The script outputs JSON with:
- `BRANCH_NAME`: The branch name (e.g., `003-user-auth`, `20260319-143022-user-auth`, or `jdoe/web/003-user-auth`)
- `FEATURE_NUM`: The numeric or timestamp prefix used
