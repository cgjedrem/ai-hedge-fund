# Task: gate-open-sync-prs

## Task Purpose
HARD STOP gate: refuse to start a sync run while a previous sync PR is still open in ANY repo — ENSO forward PRs AND project backward PRs (`ai-kit-sync: <date>`) alike. Serializes sync runs so leftover project PRs never cause this week's scan to re-propose identical items.

## Inputs
- `{sync_marker}` — PR title prefix (default: `ai-kit-sync:`)
- `{state_marker}` — state-only PR title prefix (default: `ai-kit-sync-state:`) — non-blocking
- `{project_repos}` — in-scope project repos (required, from workflow Parameters); the gate covers `enso-dev-beep/enso-skills-and-scripts` plus every repo in `{project_repos}`

## Steps
1. Build the blocking gate list per repo, dedupe by repo+number:
   - **Title prefix (canonical, all participating repos — ENSO + `{project_repos}`):**
     ```bash
     gh pr list --repo <owner>/<repo> --state open --limit 100 \
       --json number,title,url \
       --jq '[.[] | select(.title | startswith("{sync_marker}") and (startswith("{state_marker}") | not))]'
     ```
     The explicit `{state_marker}` exclusion keeps the prefixes disjoint; never rely on `--search "... in:title"` alone, which is a substring match.
   - **Label (auxiliary, ENSO repo only):** if an `ai-kit-sync` label exists in the ENSO repo, union its matches into the ENSO result. Project repos are matched on title prefix only — the label may not exist there.
   A PR blocks the run when it matches in ANY participating repo (title prefix, or label for ENSO). Requiring multiple criteria would miss legacy PRs lacking the label or freshly created PRs lacking the prefix.
2. Separately, list open `{state_marker}` PRs (startswith filter, any repo — in practice they only exist in the ENSO repo). These are NOT blockers: they are surfaced to {requesting_user} as non-blocking warnings ("state-pr cleanup pending — merge or close when convenient") so they never pile up unnoticed.
3. If the blocking gate list is non-empty in ANY repo:
   - Surface every blocking PR link to {requesting_user} with the message: "review these first — merge or close them before the next sync run"
   - STOP the workflow immediately. Do NOT scan, do NOT write anything, do NOT create branches.
4. If the blocking gate list is empty everywhere: report any state-PR warnings, then proceed to task1.

## Success Criteria
- Gate outcome is exactly one of: hard stop with blocking links surfaced, or explicit confirmation that zero blocking PRs are open across ENSO and all `{project_repos}` repos
- Open `{state_marker}` PRs surfaced as non-blocking warnings regardless of gate outcome
- No repository reads beyond the PR lists, no writes of any kind

## Outputs
```json
{
  "blocking_sync_prs": [],
  "state_prs_warning": [],
  "proceed": true
}
```
