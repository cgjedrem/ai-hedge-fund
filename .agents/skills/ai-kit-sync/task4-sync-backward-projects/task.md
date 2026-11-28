# Task: sync-backward-projects

## Task Purpose
INTERACTIVE STOP 2 (LAST STEP). Compare merged ENSO canonical against each project and, only for explicitly approved items, open ONE PR per affected project so improvements flow back out. Ends the run and records state.

## Inputs
- ENSO default branch, merged state only — the open task3 PR must NOT be included
- Default branch of each repo in `{project_repos}` (remote read per the Remote-Read Rule)
- `{sync_branch}` (default `chore/ai-kit-sync-YYYY-MM-DD`); `{sync_marker}` (default `ai-kit-sync:`)

## Steps
1. Scope the comparison to what is NEW: read the previous run's `timestamp` from `state/last_ai_kit_sync.json` (merged ENSO default branch), then restrict candidates to canonical artifacts created or changed on the ENSO default branch since that timestamp:
   ```bash
   gh api "repos/enso-dev-beep/enso-skills-and-scripts/commits?path=<path>&since=<timestamp>" --jq '.[].sha'
   ```
   If no prior timestamp exists (first run), state that explicitly and fall back to the full delta — with a warning that the list will be large. In the step-3 decision list, always offer an explicit `full-resync` option that re-runs this comparison against the complete canonical tree for one or all projects.
2. Build per-project candidates by comparing each in-scope canonical artifact (from step 1) against its target in the project's default branch, using the deterministic canonical→project mappings below:

   | ENSO canonical | Project target | Key |
   |---|---|---|
   | `packages/_base/.apm/agents/<file>` | `.packages/_base/.apm/agents/<file>` AND EVERY preset under `.specify/presets/*/agents/<file>` that already contains that agent file; if no preset contains it, `.packages/_base/.apm/agents/<file>` only | file name |
   | `skills/<category>/<name>/` | `.github/skills/<name>/` | `<name>` — collision rule: if two canonical skills share `<name>` across categories, do NOT map either; emit a conflict item in the step-3 decision list and let {requesting_user} decide |
   | `workflows/<category>/<name>/` | `.specify/workflows/<name>/` (shape per task1: YAML packs → `workflow.yml` + `overlays/<name>/*.yml`; markdown → `workflow.md` tree) | `<name>` — if the project lacks `.specify/workflows/`, offer `apply-with-adaptation` and record the chosen target path |

   Never sync the task1 exclusions: preset `.cache/`/`.registry/`, extension registries, `workflow-registry.json`, `memory/`, `templates/`, `scripts/`, `assessments/`, `bugs/`, `integrations/`, and `.specify/` root config files.

   The output is a per-project decision list: which agent definitions, skills, and workflows are new or improved in ENSO that the project lacks (e.g. improvements the user merged from another PC).
3. Present the list to {requesting_user}, grouped by project. Per item: what is new/improved, concrete options (`apply` / `skip` / `apply-with-adaptation` — noting what must change for that project), and a recommendation with reasoning.
4. Wait for explicit selection. Write NOTHING before it.
5. For approved items, per affected project repo:
   - Create branch `{sync_branch}` from a freshly fetched project default branch
   - Apply the ENSO-canonical versions per the mapping table: each agent definition is written byte-identically to `.packages/_base/.apm/agents/<file>` and to EVERY preset under `.specify/presets/*/agents/<file>` that already contains that file (never create the file under new presets). This preserves preset dedupe by construction — every preset that contains the agent file stays byte-identical to `.packages/_base/.apm/agents/`.
   - Target-side validation BEFORE committing: every touched `*.agent.md` parses as markdown with valid YAML frontmatter; every touched `SKILL.md` follows skill-creator conventions; every touched workflow file parses as valid YAML
   - Verify the diff touches only approved paths: compare the branch's changed file list against the approved path set for that project
   - On validation or scope failure: abort THAT project's PR (delete its branch, do not open the PR), report which project failed and why, and continue with the remaining projects' PRs
   - On success: commit with the trailer `Co-authored-by: Copilot App <223556219+Copilot@users.noreply.github.com>` and open ONE PR per project: title `{sync_marker} <date>`, against that project's default branch, body listing the approved items for that project
6. Surface every PR link to {requesting_user} for review. Never auto-merge, never push to a default branch directly.
7. If nothing is approved: end cleanly — no branches, no PRs — and keep the presented list in the state file.
8. Complete the state record AFTER all backward work settles (see State Persistence in workflow.md):
   - If the forward PR is still open: push a follow-up commit to `{sync_branch}` updating `backward_items_presented`, `backward_items_approved`, and `project_pr_urls` in `state/last_ai_kit_sync.json` — the forward PR now carries the complete run record.
   - If the forward PR was already merged or closed: open a tiny PR titled `ai-kit-sync-state: <date>` (no `{sync_marker}` prefix, so the task0 startswith gate does not trip on it) containing ONLY the `state/last_ai_kit_sync.json` update.

## Success Criteria
- Comparison used merged ENSO default-branch state only
- No project repo written except via its own PR after explicit approval
- Exactly one PR per affected project; all links surfaced to {requesting_user}
- State file fully updated even when zero items were approved

## Outputs
`state/last_ai_kit_sync.json`:
```json
{
  "timestamp": "ISO-8601",
  "forward_items_found": [],
  "forward_items_approved": [],
  "forward_items_applied": [],
  "forward_pr_url": "https://github.com/enso-dev-beep/enso-skills-and-scripts/pull/N",
  "backward_items_presented": [],
  "backward_items_approved": [],
  "project_pr_urls": {
    "owner/repo": "https://github.com/owner/repo/pull/M"
  }
}
```
