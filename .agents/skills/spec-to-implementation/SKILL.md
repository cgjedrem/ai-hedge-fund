---
name: spec-to-implementation
description: Implement a spec or ticket test-first with the red-green TDD loop in vertical slices plus two-axis review. Use when asked to implement an approved spec/plan/ticket.
---

# Workflow: spec-to-implementation

## Trigger
- "implement this spec", "pick up ticket #N", "build this test-first"
- A spec or ticket exists (e.g. from `issue-investigation-to-plan` or `conversation-to-spec`) and is ready for implementation
- {requesting_user} asks to implement an approved plan

## Purpose
Implement a spec or ticket test-first: agree seams up front, run the red→green TDD loop in vertical slices, diagnose failures systematically instead of guess-patching, and finish with a two-axis review before commit.

## Prerequisites
- A spec, ticket, or approved plan with acceptance criteria exists
- Repository builds and test suite runs locally
- Clean working tree on a feature branch (create one if needed)

**Parameters:**
- `{requesting_user}` — user who confirms seams and receives gate decisions (required)
- `{spec_ref}` — spec file path, issue number, or ticket URL (required)
- `{branch}` — feature branch (default: derived from ticket slug)
- `{ENSO_ROOT}` — absolute path to the ENSO skills-and-scripts repository (required when resolving linked skill paths)
- `{reserved_spec_number}`, `{reservation_ref}`, `{reservation_oid}`, `{allocation_remote}` — confirmed allocation receipt for a new numbered spec; pass unchanged to every child working on that spec

## Steps

### task0-reserve-spec-numbers-before-spawning
- **Purpose:** Prevent independent sessions/worktrees from assigning the same number to different specs. Existing numbered specs retain their identity; verify their spec reference instead of allocating again. Unnumbered tickets that do not create a numbered spec need no allocation.
- **Authority:** Use the target repository's actual numbering tooling, not ENSO's own spec catalog. With Spec Kit, use `.specify/extensions/git/scripts/powershell/create-new-feature-branch.ps1 -Json -DryRun -ShortName "<slug>" "<description>"` (or its Bash equivalent). It scans specs, branches, live remote heads and merged specs. A dry run is only a candidate, NOT a reservation. Do not use offline mode, `GIT_BRANCH_NAME` overrides or hand-calculated `max + 1` for concurrent allocation.
- **Allocation:** Before launching ANY children that create specs, the parent allocates all new specs one at a time. Independent parents must use the same writable authoritative remote and the same reservation-ref convention. For sequential Spec Kit numbering, take `FEATURE_NUM` and the namespace from the returned `BRANCH_NAME`, replacing only its final `<number>-<slug>` segment with `<number>-spec-reservation`. Thus `jdoe/app/042-new-api` claims `refs/heads/jdoe/app/042-spec-reservation`; unprefixed `042-new-api` claims `refs/heads/042-spec-reservation`. Never put the slug or session ID in the reservation name: contenders for a number must collide on the SAME ref. Existing branch-template scope determines the numbering scope.
- **Atomic claim:** Resolve a safe, already-published base commit OID on that remote (not an unpublished local HEAD). Create a unique reservation commit with `git commit-tree <base-oid>^{tree} -p <base-oid> -m "Spec reservation: <spec-ref>; owner=<session-id>; nonce=<fresh-UUID>"`, capturing its OID. This reuses the published tree, changes no checkout and includes no unpublished code; the fresh nonce is mandatory so contenders never push identical OIDs (Git can treat an identical OID as already up to date without checking the lease). Validate the ref with `git check-ref-format`. Then execute `git push --force-with-lease=<reservation-ref>: <allocation-remote> <reservation-oid>:<reservation-ref>`. The empty expected value after `:` means "create only if absent"; Git's remote ref transaction admits only one contender with a unique OID. This is a real persistent numbered branch visible to the existing numbering scanner, not a fictional local lock. Never use plain push, unconditional force, or a nonempty lease to take someone else's claim. This step needs explicit remote-write authorization; if the run forbids pushes, allocation is BLOCKED rather than silently local-only.
- **Receipt and handoff:** After success, verify the exact remote ref/OID with `git ls-remote --heads <allocation-remote> <reservation-ref>`. Record spec reference/slug, number, ref, OID, remote and owning session in the parent's allocation ledger before spawning. Every child kickoff includes this receipt plus its fixed `SPECIFY_FEATURE_DIRECTORY` (`specs/<number>-<slug>`, respecting project layout). Pass `-Number <reserved_spec_number>` / `--number` to core `create-new-feature`, or set the explicit spec directory as supported by that installation. Children MUST NOT auto-allocate or renumber independently. Multiple children on the same spec share its receipt; different specs receive distinct receipts. Keep the app-managed worktree branch unchanged.
- **Conflict/failure:** On a rejected claim, refresh the remote heads and rerun the real resolver, then attempt the next candidate (maximum 5 attempts). A remote/auth/network failure, unverifiable receipt, unsupported allocator or exhausted retries blocks spawns: report the exact failed step without guessing a number. An already-existing spec directory for a different feature also blocks that child and returns allocation to the parent. Never treat another session's reservation as your own. Retain successful reservation refs even on cancellation/failure so numbers are not recycled; do not delete them during ordinary branch cleanup. A retry may reuse only its recorded, verified receipt.
- **Limit:** This guarantees uniqueness only among allocators following this protocol against the same authoritative remote and numbering scope. Legacy allocators must adopt the claim step before running concurrently; merely scanning remote heads cannot close a race. If the target has a stronger centralized allocator, use its atomic claim/receipt API instead and pass that receipt to children.
- **Success:** Every new numbered spec has a verified, durable allocation before any parallel child launch. This does not authorize parallel specialists where the coordinator requires sequential execution, nor bypass seam/approval gates.

### task1-load-spec-and-context
- **Purpose:** Understand what to build and the vocabulary to build it in
- **Action:** Read the full spec/ticket body and comments. Read `CONTEXT.md` and nearby ADRs if present so names match the project's domain language. Maintain a decision register in the working notes with each decision marked `confirmed`, `open`, or `superseded`, including its source. The latest explicit user direction supersedes older notes when they conflict. When a correction changes a settled decision, propagate it through the relevant spec, plan, tasks, contracts, and tests before implementation.
- **Output:** Working notes: in-scope behavior, exclusions, acceptance criteria, and current decision register
- **Success:** Acceptance criteria restated; open ambiguities surfaced to {requesting_user} before code; superseded decisions are not treated as active requirements

### task2-agree-seams
- **Purpose:** Fix where tests will live before writing any
- **Action:** Apply `tdd` seam rules — identify the public boundaries under test, preferring existing seams, at the highest level possible
- **Gate:** Present the proposed seams and ask one focused confirmation question per turn. Do not bundle unrelated design choices or include a recommended answer unless {requesting_user} asks for one. No test is written at an unconfirmed seam.
- **Success:** Seam list confirmed; testing effort targeted at critical paths, not every edge case

### task3-tdd-loop
- **Purpose:** Implement in vertical slices, red before green
- **Action:** Apply `tdd` loop per slice:
  1. Write one failing test at a confirmed seam (red)
  2. Write only enough code to pass it (green)
  3. Repeat — one seam, one test, one minimal implementation per cycle
- **Discipline:** No horizontal slicing (all tests first), no tautological assertions, no implementation-coupled tests. Run typechecking regularly and single test files per cycle
- **Output:** Passing tests + implementation, slice by slice
- **Success:** All acceptance criteria covered by at least one test that failed first

### task4-diagnose-failures
- **Purpose:** Handle stuck failures systematically, not by guess-patching
- **Action:** When a test fails unexpectedly or behavior regresses, apply `diagnosing-bugs` — form a hypothesis, find the smallest reproduction, verify the cause before fixing
- **Trigger:** Any failure that survives one obvious fix attempt
- **Success:** Root cause identified and stated before the fix lands; no "changed things until it passed" commits

### task5-review-and-commit
- **Purpose:** Verify the work before it lands
- **Action:** Run the full test suite once. Then apply `code-review` two-axis review of the branch diff against its merge-base — Standards axis (repo standards + smell baseline) and Spec axis (does the diff implement `{spec_ref}`)
- **Handoff:** In the completion summary, explain non-obvious implementation and data-model choices, citing relevant repository precedent where available. Separate verified facts from assumptions and identify any deployment or environment checks that were not performed.
- **Gate:** 
  - Clean or judgement-call-only findings → commit to `{branch}` with messages referencing the ticket
  - Hard violations or spec gaps → fix, re-run affected tests, re-review
- **Success:** Full suite green, review findings addressed, work committed

## Skills/Tools Used
- **[tdd]({ENSO_ROOT}/skills/mattpocock/tdd/SKILL.md)** — seams, red→green loop, test anti-patterns
- **[implement]({ENSO_ROOT}/skills/mattpocock/implement/SKILL.md)** — overall implementation contract
- **[diagnosing-bugs]({ENSO_ROOT}/skills/mattpocock/diagnosing-bugs/SKILL.md)** — hypothesis-driven failure diagnosis
- **[code-review]({ENSO_ROOT}/skills/mattpocock/code-review/SKILL.md)** — pre-commit two-axis review
- **git** — branch, commit; test runner and typechecker (project-specific)

## Outputs
- Tests at confirmed seams (failed first, now green)
- Implementation committed to `{branch}`
- Review findings resolved or explicitly accepted by {requesting_user}

## Rollback
- Wrong seam discovered mid-loop: stop, re-confirm seams with {requesting_user}, migrate or delete affected tests — do not test around a bad seam
- Slice went wrong: `git reset` to last green slice; slices are the checkpoint unit
- Review reveals spec misunderstanding: return to task1 with the correction; keep green tests that remain valid
