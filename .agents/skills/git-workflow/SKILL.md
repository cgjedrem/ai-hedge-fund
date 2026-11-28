---
name: git-workflow
description: 'Git conventions covering branch naming, commit messages, PR templates, rebase vs merge strategy, and change manifest format. Use when creating branches, making commits, or submitting PRs on any git project. Do not use for GitHub API operations (use github skill), local git troubleshooting, or git LFS workflows.'
---

# Git Workflow

## Branch Naming

All branches use a project prefix followed by the type and short description. Replace `<project>` with the actual project or team name:

```
<project>/feature/<short-description>
<project>/bugfix/<short-description>
<project>/hotfix/<short-description>
<project>/chore/<short-description>
```

Examples (using `acme` as a sample project prefix):
- `acme/feature/user-registration`
- `acme/bugfix/login-crash-empty-email`
- `acme/hotfix/auth-token-expiry`
- `acme/chore/add-staging-pipeline`

If the project has no prefix convention, use the type directly: `feature/user-registration`.

## Commit Messages

Format:
```
<type>(<scope>): <description>

[optional body]
[optional footer]
```

Types:
- `feat`: New feature
- `fix`: Bug fix
- `refactor`: Code restructure without behavior change
- `test`: Adding or updating tests
- `docs`: Documentation only
- `chore`: DevOps, CI, tooling
- `style`: Formatting only (no logic change)

Examples:
```
feat(auth): add JWT token refresh endpoint
fix(login): handle empty email field without crash
test(users): add happy path and error tests for registration
chore(ci): add staging pipeline configuration
```

## Rebase vs Merge

- **Always rebase** on the target branch before submitting a PR
- **Never merge** the target branch into your feature branch
- Squash commits if the PR has more than 3 commits
- One logical change per commit — don't mix refactor and feature in one commit

## Pull Request Format

```markdown
## What
[1-2 sentences describing the change]

## Why
[Context from the change request / issue / ticket]

## Changes
- [file1]: [what changed and why]
- [file2]: [what changed and why]

## Testing
- [How this was tested]
- [Test commands to run]

## Checklist
- [ ] All tests pass
- [ ] No out-of-scope changes
- [ ] Change scope matches actual diff
- [ ] Security checklist reviewed (for backend/auth changes)
```

## Change Manifest Format

When working in a multi-agent or multi-step pipeline, each contributor produces a `change-manifest.md` listing files they touched:

```markdown
# Change Manifest — <contributor-id>

## Created
- `path/to/new/file.ts` — Brief description of what this file does

## Modified
- `path/to/existing/file.ts` — Brief description of what changed

## Deleted
- `path/to/removed/file.ts` — Brief description of why it was removed
```

## Aggregated PR Submission (Multi-Contributor)

When multiple contributors are involved, the aggregator compiles manifests into a single PR with:

```markdown
## What
[Feature/bugfix description from the original request]

## Contributors
- Discovery: [who]
- Planning: [who]
- Execution: [who]
- Review: [who] — [pass | pass-with-caveats | fail]

## Changes

### [Contributor 1]
[Their change manifest entries]

### [Contributor 2]
[Their change manifest entries]

## Review Summary
[Critical and important findings only]

## Testing
[Aggregated test commands from all contributors]
```

## Merge Rules

- PRs require the repository owner's approval
- No direct commits to main/master
- No force-push to shared branches
- Delete feature branches after merge