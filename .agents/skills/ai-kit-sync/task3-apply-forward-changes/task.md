# Task: apply-forward-changes

## Task Purpose
Apply exactly the approved forward items into ENSO canonical on a fresh branch, validate, and open the forward PR. Nothing outside the approved list may change.

## Inputs
- Approved decision list from task2 (required — refuse to run without it)
- ENSO default branch name; `{sync_branch}` (default `chore/ai-kit-sync-YYYY-MM-DD`); `{sync_marker}` (default `ai-kit-sync:`)

## Steps
1. Create branch `{sync_branch}` from a freshly fetched ENSO default branch — never reuse a stale local base.
2. Apply only the approved items:
   - Agent definitions → `packages/_base/.apm/agents/*.agent.md`
   - Skills → `skills/{category}/<name>/` (category per approval)
   - Workflows → `workflows/{category}/<name>/` — and register **markdown-shape** workflows (dirs with `workflow.md`) in `workflows/workflowindex.md`; YAML packs (`workflow.yml` + overlays) are not indexed (see step 3 validation)
   - Preset-divergence resolutions → update the canonical agent definition only; `.specify/` presets do not exist ENSO-side
3. Validate before committing, scoped by artifact shape:
   - Every `*.agent.md` parses as markdown with valid YAML frontmatter
   - Every promoted `SKILL.md` follows skill-creator conventions (required sections, referenced paths exist)
   - **Markdown-shape workflows** (promoted dir contains `workflow.md`): its `workflow.md` must satisfy the workflow-builder checklist — required sections present (Trigger, Purpose, Prerequisites, Steps with per-task Purpose/Input/Output/Success, Skills/Tools Used, Outputs, Rollback), valid front matter if any — and its path must resolve from `workflows/workflowindex.md` to the on-disk `workflows/{category}/<name>/workflow.md` created by this apply
   - **YAML-pack workflows** (promoted dir contains `workflow.yml` + overlays, no `workflow.md`): every touched `.yml` file must parse as valid YAML instead; the workflow-builder checklist and workflowindex.md resolution do NOT apply — the index documents markdown workflows only (YAML packs are project-side speckit workflows, not ENSO workflowindex-registered workflows)
   - Removed/renamed artifacts leave no dangling references
   - Fail the PR on any broken check: fix on the branch and re-validate; on unrecoverable failure, discard the branch and report — do not open a broken PR
4. Commit in logical groups (per artifact or per artifact type) with clear messages. Every commit carries the trailer:
   `Co-authored-by: Copilot App <223556219+Copilot@users.noreply.github.com>`
5. Push the branch and open the ENSO PR: title `{sync_marker} <date>` (e.g. `ai-kit-sync: 2026-10-02`), against the default branch.
6. PR body: the full task2 decision list (every item — approved and skipped — with chosen options) plus validation results.
7. Record the forward state ON the branch: update `workflows/agent-architecture/ai-kit-sync/state/last_ai_kit_sync.json` with `timestamp`, `forward_items_found`, `forward_items_approved`, `forward_items_applied`, and `forward_pr_url`, then commit and push it as a follow-up commit on `{sync_branch}` so the forward PR itself carries the state update. Leave the backward fields empty — task4 completes them (see State Persistence in workflow.md).
8. Surface the PR link to {requesting_user}.

## Success Criteria
- PR contains exactly the approved items — no more, no less
- All validations pass; co-author trailer present on every commit
- PR link delivered to {requesting_user}
- Rollback stays trivial: close the PR and delete `{sync_branch}` (documented in workflow.md instead of file backups, because apply happens on a fresh branch)

## Outputs
```json
{
  "forward_pr_url": "https://github.com/enso-dev-beep/enso-skills-and-scripts/pull/N",
  "branch": "chore/ai-kit-sync-YYYY-MM-DD",
  "items_applied": ["<item_ref>"],
  "validation": "passed"
}
```
