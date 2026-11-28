---
name: copilot-review-triage
description: Fetch, classify, and adjudicate GitHub Copilot (copilot-pull-request-reviewer) PR comments against your own review findings, producing a decision-tracking table with per-item status. Use when Copilot has left review comments on PRs, when preparing a stack for human team review, or when the user says "check copilot comments", "triage bot review". Do not use for human reviewer comments (treat those as authoritative discussion) or as a substitute for your own review.
---

# Copilot Review Triage

Bot reviews are high-signal but noisy: real defects sit next to doc-nits and false positives. Never apply bot comments wholesale — triage each one.

## Fetch

```powershell
gh pr view <n> --json headRefOid,reviews,comments                   # head, summaries + conversation
gh api --paginate repos/<owner>/<repo>/pulls/<n>/comments           # all inline comments with IDs
```

Note: Copilot embeds additional "suppressed" findings inside the review summary body — read those too; they are often the sharper findings.

## Classify each finding

| Class | Meaning | Default action |
|---|---|---|
| 🔴 defect | breaks behavior / contract | verify against code, then fix |
| 🟡 hardening | invariant unenforced, future-caller risk | cheap guards: accept |
| 🟡 needs-decision | touches design intent or ops impact | escalate to design owner, do not self-decide |
| 🔵 nit | test coverage gap, wording | accept if cheap |
| ❌ false positive | claim contradicted by code | reject with evidence recorded |

## Convergence check (do this — it's the valuable part)

Cross-reference bot findings against your own independent review findings:

- **Bot + you found the same thing independently** → high confidence real; prioritize.
- **Bot found something your review missed** → check if it's in a blind spot class (e.g. generated-code return types, API response semantics).
- **Bot contradicts your review** → re-verify with direct code reads; record which was wrong and why.

## Verify before accepting

Copilot claims are [Unverified] until checked: read the actual code at the cited line, check the generated client/API contract it references, trace the claimed execution path. Real example: a claimed "nullable bool discarded" was confirmed by reading the generated client's method signature; a claimed "missing field" was refuted because the field existed in a sibling file.

## Track decisions in a table

Keep the decision table in a persistent session artifact so a handoff or retry cannot widen the batch. Record repository, PR number, full approved head SHA, exact approved inline comment database IDs, allowed actions and approval reference. One row per finding: ID, PR, location, claim, judgment/evidence and status (`open / accepted-fix / rejected / deferred / answered`). Record summary-only findings separately; they have no inline thread to resolve. Counts and classes summarize the batch; neither defines approval.

## Fix placement on stacked PRs

**Fix on the same branch the review was left on** — the PR the bot reviewed is where the fix belongs; reviewers re-check the PR they commented on, and reply threads resolve against new commits in that PR. Do NOT open a stacked "review-fixes" PR on top unless the user explicitly asks for that.

When the fix spans stack layers (contract changed at PR N, emission lives in PR N+1, consumer in PR N+2):

1. Place the approved change in the lowest affected branch; split by layer when necessary. Commit or push only if that action was authorized.
2. After a parent update, check all descendants parent-first using the `stacked-pr-stack-manager` procedure. Stop for WIP, ownership conflicts, or missing rewrite/push approval; another worktree is not permission to move a shared ref.
3. Account for each push and each authorized thread action using the post-fix loop below.

When the user's checkout has unrelated WIP, do authorized branch surgery in a temporary worktree — never switch, stash or rebase someone else's checkout.

## Post-fix loop (before declaring a round done)

1. On resume, after **each push** and before thread actions, re-fetch the live PR head, comments and threads. For GraphQL, page `reviewThreads` to exhaustion and page each thread's `comments` connection independently (`pageInfo.hasNextPage` / `endCursor`). Recheck the head after paging; a partial or inconsistent snapshot is not a target list.
2. Compare with the saved batch. Record old → new head only for a verified, specifically authorized push from that batch; retain the original approval and revalidate fixes at the new tip. Stop for fresh approval on any unexpected head. List new comment IDs separately as pending approval, even when they share a file, class or thread with an approved ID. Never resolve a thread over a new, unapproved concern.
3. For each approved action, match the **exact** approved `comments.nodes[].databaseId` to precisely one live thread `id` on that PR. Save both, its root comment database ID, fix SHA/evidence, existing replies and `isResolved`. Do not match by path, line, body or list position. Missing/ambiguous IDs, permissions or incomplete pages block the action.
4. Reply only if authorized, using the verified root comment ID for the reply endpoint. If an equivalent reply already exists, record its ID and skip posting. Resolve only if authorized and still unresolved, using the verified thread node ID. After an uncertain write, re-read before any retry; if the outcome cannot be established, stop rather than duplicate the reply or mutate another thread.
5. Re-fetch and record final head and final `isResolved` for **every** approved ID/thread, including already-resolved ones. Report reply ID, disposition and any blocker per row. A resolve request is not completion until that exact thread reads `isResolved: true`; leave intentionally reply-only work labeled as such. Report new pending comments separately. Propose any title/body edit separately; triage does not authorize it.

**Raw gh recipe** (no harness tool may exist). Writes apply only to the authorized, verified IDs from steps 3 and 4:

```powershell
# Reply (in_reply_to = the root review comment's database id, not a thread id):
gh api repos/<owner>/<repo>/pulls/<n>/comments -X POST --input body.json
#   body.json: {"body": "Fixed in <sha>: ...", "in_reply_to": <root-comment-database-id>}
#   body.json must be UTF-8 without BOM (PowerShell 5.1 Out-File/Set-Content -Encoding UTF8 add one).

# Map comment databaseId -> thread node id. Write the query to an ASCII file first —
# inline -f query="..." gets mangled (see windows-powershell-traps).
# -f passes owner/name as strings; -F passes number as an Int. --paginate prints one JSON
# document per page: add --slurp (gh 2.48+) for one array, or --jq per page, before parsing.
gh api graphql --paginate --slurp -f owner=<o> -f name=<r> -F number=<n> -F query=@threads.graphql
#   threads.graphql:
#   query($owner: String!, $name: String!, $number: Int!, $endCursor: String) {
#     repository(owner: $owner, name: $name) { pullRequest(number: $number) {
#       # Keep the outer pageInfo on reviewThreads: gh --paginate follows only that cursor.
#       reviewThreads(first: 100, after: $endCursor) { pageInfo { hasNextPage endCursor }
#         nodes { id isResolved comments(first: 100) {
#           pageInfo { hasNextPage endCursor }
#           nodes { databaseId replyTo { databaseId } author { login } body } } } } } } }

# Page one thread's comments when its comments.pageInfo.hasNextPage is true:
gh api graphql --paginate --slurp -f id=<PRRT_...> -F query=@thread-comments.graphql
#   thread-comments.graphql:
#   query($id: ID!, $endCursor: String) {
#     node(id: $id) { ... on PullRequestReviewThread {
#       comments(first: 100, after: $endCursor) { pageInfo { hasNextPage endCursor }
#         nodes { databaseId replyTo { databaseId } author { login } body } } } } }

# Resolve (only an authorized, verified thread ID):
gh api graphql -F query=@resolve.graphql
#   resolve.graphql: mutation { resolveReviewThread(input: {threadId: "PRRT_..."}) {
#     thread { isResolved } } }
```

A thread whose `comments.pageInfo.hasNextPage` is true needs its comments paged separately before matching; `comments(first: 1)` exposes only the root comment, so a reply's comment ID matches nothing.

## Boundaries

- Present the table before mutation. A request to triage is read-only; approval applies only to the recorded PR head, named comment IDs and specified actions, not future comments or external actions generally.
- Bot review state is COMMENTED, never authoritative approval — human review still required.
- If the bot never reviewed a PR (check before assuming), note it; requesting the bot review via API requires it to be a repo collaborator — otherwise web UI only.
