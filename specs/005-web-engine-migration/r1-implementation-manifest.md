# Spec005 Release 1 implementation manifest

## Scope and identity

- Branch: `cgjedrem-shiny-tribble`.
- Base revision: `8660cc5f93c0fb81a7d1273abfd42b2fddd85f68`.
- Implementation commit: `9c1f5b8e6c5b69b648a68de49cb7164f638a9b2e` (`feat: implement Spec005 Release 1 paper desk flows`).
- Source/test snapshot: 37 files, 1,629,986 bytes, SHA-256 `b80e55df9dc3c2493d41bdb98f511c7b1120aa96ff86eb90d901cd2e302de79a`.
- Snapshot covers sorted UTF-8 repository-relative path + NUL + full file bytes + NUL; excludes evidence documents, `memory.md`, and root `node_modules/`.
- Implementation preserves the published engine and React UI. No Docker or deployment topology changes.
- RB-5 remains blocked pending the operator choice between a writable single-writer desk container and a host-run desk with no container writer. The choice changes writer/root topology, validation, and deployment documentation.
- Evidence and test outcomes are implementation-owner observations, not independent QA sign-off. See `implementation-progress.md` for timestamped observations, exact commands, results, and remaining limits.

## Python implementation

- `hedge_fund/paper/ledger.py` — request-bound control/tick idempotency, Halt/Resume fencing, and ambiguity checks.
- `hedge_fund/paper/tick.py` — request-bound tick outcome and pre-effect audit-contention classification.
- `hedge_fund/paper/test_ledger.py` — ledger control, request identity, and Resume regressions.
- `hedge_fund/paper/test_tick.py` — tick request, no-work, and effect-boundary regressions.
- `hedge_fund/paths.py` — Halt-control write validation for request identity.
- `hedge_fund/test_paths.py` — root/write-path contract regressions.
- `hedge_fund/pipeline/session.py` — bounded monotonic session progress reporting.
- `hedge_fund/pipeline/stages.py` — progress callbacks across assessment/execution stages.
- `hedge_fund/pipeline/test_stages.py` — stage progress and input-validation coverage.
- `hedge_fund/run.py` — CLI request identity, paper control, verdict, and recovery paths.
- `hedge_fund/test_run.py` — CLI behavior and compatibility regressions.
- `hedge_fund/runtime/owned_runner_child.py` — request-bound runner tick and safe pre-effect contention retry.
- `hedge_fund/runtime/test_owned_runner_child.py` — runner retry and request-bound effect regressions.
- `hedge_fund/runtime/test_inventory_cache_race.py` — inventory/cache race regressions.
- `hedge_fund/runtime/test_writer_races.py` — participating writer and control-lane interleavings.
- `hedge_fund/runtime/test_writer_race_matrix.py` — cross-platform synthetic reparse-point writer regressions.
- `hedge_fund/runtime/reconciliation.py` — hash-bound local-paper failure reconciliation.
- `hedge_fund/runtime/test_reconciliation.py` — reconciliation identity, mismatch, and fail-closed regressions.
- `hedge_fund/tui/paper.py` — retained TUI Resume path uses the same effect-intent fence.

## Web implementation

- `hedge_fund/web/app.py` — request/response wiring for desk paper operations.
- `hedge_fund/web/schemas.py` — validated paper-operation request/response shapes.
- `hedge_fund/web/services.py` — manual-run review, progress/outcomes, control fencing, and recovery service behavior.
- `hedge_fund/web/test_actions.py` — CLI/web provider and action denial regressions.
- `hedge_fund/web/test_app.py` — route and application response regressions.
- `hedge_fund/web/test_jobs.py` — operation progress, completion, and error-state regressions.
- `hedge_fund/web/test_paper_operations.py` — manual paper-run and control operation regressions.
- `hedge_fund/web/test_write_authority.py` — participating writer-authority regressions.
- `hedge_fund/web/test_recovery.py` — hash-bound recovery service regressions.

## React UI and browser tests

- `frontend/src/pages/paper.tsx` — manual-run review, operation progress/outcomes, Halt/Resume, and recovery UI.
- `frontend/src/pages/paper.test.tsx` — paper page state and action regressions.
- `frontend/src/components/operation-status.tsx` — operation progress and terminal-state display.
- `frontend/src/lib/types.ts` — paper operation and recovery API types.
- `frontend/src/App.test.tsx` — application-level paper control/recovery regressions.
- `frontend/e2e/desk.spec.ts` — synthetic-root browser flows for manual run, verdict, Halt/Resume, reconciliation, and stale-head rejection.
- `frontend/e2e/run-owned.mjs` — owned browser lifecycle support.
- `frontend/scripts/run-owned.test.mjs` — browser-runner safety regressions.
- `frontend/playwright.config.ts` — browser configuration for owned test runs.

## Evidence and handoff

- `specs/005-web-engine-migration/implementation-progress.md` — scope decision and append-only execution/test evidence.
- `memory.md` — dated durable implementation facts.
- `specs/005-web-engine-migration/r1-implementation-manifest.md` — this R1-specific file inventory and QA map.

## Independent QA map

- RB-1: inspect ledger and runner request fencing; verify writer inventory, ownership races, and pre-effect retry tests.
- RB-2: inspect reviewed manual-run acceptance, explicit no-work outcomes, progress, and structured operation errors.
- RB-3: inspect hash-bound reconciliation receipt checks, Halt/Resume transitions, stale-head rejection, and no retry of ambiguous effects.
- RB-4: inspect provider defaults, secret handling, and CLI/web SIM denial tests.
- RB-6: inspect targeted regression tests and the synthetic-root browser lifecycle flow.
- RB-5: do not mark complete or alter deployment topology until the operator chooses a writer/root model.
- Test boundary: synthetic roots and fakes only. No live provider/broker calls, production-root activation, or real-fund writes.
