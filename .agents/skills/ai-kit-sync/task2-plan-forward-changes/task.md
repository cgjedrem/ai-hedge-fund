# Task: plan-forward-changes

## Task Purpose
INTERACTIVE STOP 1. Convert the scan items into a decision list and get {requesting_user}'s explicit approval before anything is written. This gate is never skipped — not even for "small" changes.

## Inputs
- Diff items from task1 (including `preset-divergence` items and proposed categories)

## Steps
1. Present the decision list to {requesting_user}. Per item:
   - What changed and where it came from (source repo + path)
   - Concrete options, as applicable:
     - `promote` — copy into ENSO canonical (`packages/_base/.apm/agents/`, `skills/{category}/`, `workflows/{category}/`)
     - `skip` — leave ENSO as-is
     - `rename-category` — promote, but under a different `{category}` than proposed
     - `resolve-conflict-which-way` — for `action: conflict` and `preset-divergence` items, pick which side wins (project A / project B / ENSO canonical / keep both with rename)
   - A recommendation per item with reasoning ("my judgement: ...")
2. Wait for an explicit approval that lists exactly which items to apply and with which option. If {requesting_user} edits the list, the edited list IS the approval.
3. Record the approved list verbatim — it becomes the task3 PR body.
4. Write NOTHING before approval — no branches, no files, no PRs.

## Success Criteria
- Every scan item has a decided option (approved or skipped explicitly)
- Approval is explicit and enumerates the items to apply
- Gate never skipped — task3 must refuse to run without this record

## Outputs
```json
{
  "approved": [
    {
      "item_ref": "<scan item index or path>",
      "decision": "promote | rename-category | resolve-conflict-which-way",
      "category": "development",
      "conflict_resolution": "project-version-wins",
      "notes": "optional per-item note"
    }
  ],
  "skipped": [
    {"item_ref": "<scan item index or path>", "reason": "why skipped"}
  ],
  "approved_by": "{requesting_user}",
  "approved_at": "ISO-8601"
}
```
