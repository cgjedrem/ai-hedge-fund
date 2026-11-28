---
name: pr-preflight
description: Pre-PR checklist for branch hygiene and verified "done" claims. Use before opening or updating any PR, or when asked to verify alert/issue resolution. Do not use for post-merge verification of CI runs.
---

# PR Preflight

Run every item before opening or updating a PR. Fix failures before proceeding; do not open the PR and promise to fix later.

## 1. Intended commits only

Resolve the PR's intended base first. When updating an existing PR, use its current base:

```powershell
gh pr view <number> --json baseRefName --jq .baseRefName
```

When opening a new PR, use the base the author chose — default `main`, but stacked PRs (e.g. speckit-implement code PRs) target their parent spec/plan branch.

```powershell
git fetch origin
git log --oneline origin/<base>..HEAD
```

The list must contain only the commits intended for this PR: a stacked PR shows only its own commits on top of the parent branch; a main-targeted PR shows only its own. Stray commits (merge noise, leftover experiments, another feature's work) mean the branch is contaminated relative to that base. Cleanup means removing the unintended commits relative to the intended base — rebase onto `origin/<base>` or rebuild the branch with cherry-picks. Never rebase a stacked PR onto `main`; that discards the parent ancestry the implementation gate requires.

## 2. No other open PR on this branch

```powershell
gh pr list --head <branch> --state open
```

If a PR is already open for this branch, do not push unrelated work to it — the list may contain only the PR you are updating. Create a fresh branch for the new work instead of leaking commits into an existing PR.

## 3. Verify "done" claims against the API — never from memory

Before claiming alerts or issues are resolved, verify their actual state:

```powershell
gh api "repos/<owner>/<repo>/code-scanning/alerts?state=open" --paginate
gh api "repos/<owner>/<repo>/dependabot/alerts?state=open" --paginate
gh issue view <number> --json state
```

- Never assert resolution from memory or from PR merges alone.
- Code-scanning alerts close only after the next scan runs on the **default branch** — a merged fix PR does not close the alert immediately. Until the post-merge scan confirms closure, the correct claim is "fix merged, closure pending next scan", not "alert closed".

## 4. PR body is self-contained

The PR body must stand alone: motivation, what changed, how it was verified, and linked issues. A reviewer must not need chat history or sibling PRs to understand it.

## 5. PR body hygiene — no template artifacts or dead open loops

- Check the body for generator/template artifacts: wrong attribution footers (e.g. a tool name that did not author the change), boilerplate from another repo's template, placeholder checkboxes.
- Any issue flagged during review of the PR (body or comments) must be **resolved or explicitly declined by the user before merge** — a flagged item left unanswered is a dead open loop; merged PRs do not get re-read.
- Fix the body in place: `gh pr edit <number> --body-file -` (or `--body`), never by appending a correction comment nobody will read.

## Docs-only changes: light local boundary check

For prose/documentation-only changes, the DocFX publication boundary check can run locally without a full site build:

```powershell
py -3 scripts/check-docfx-publication-boundary.py --no-site
```

This skips the assertions that read from the built `_site` directory and keeps all source-tree assertions. CI always runs the full check (with site build) — `--no-site` is a local convenience only.
