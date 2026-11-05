# Spec005 Release 1 implementation manifest

## Current continuation (2026-11-05)

- Worktree/branch: `cgjedrem-super-fiesta`; base `3498ef8a7a1751917b16936c9219dda70dd7fa74`. Prior implementation commits are unchanged.
- Scope result: report downloads now return exact ledger bytes captured during verified replay; the TUI report-selection regression uses actual keyboard input. The Docker target is selected but **BLOCKED** on the current Windows Docker Desktop bind filesystem (`9p`) and unverified container-identity lifecycle. No Docker application/compose guard was bypassed, and no operator cutover occurred.
- Final source/test snapshot: six changed runtime/test files, 375,729 bytes, SHA-256 `ee1441d6e50a58093b1c5ce06ffc114734feaf2ee9eb2c5ecd5f92d3f0506c15`. The full non-TUI runs used prior hash `90cb132f20f18aa5131f866d87e22af33d3af3f63fca496b0a0979b077e6dda5`; only a `Ledger.replay` docstring clarification differs. Final-source TUI/report rerun: **40 passed**. See exact evidence in `implementation-progress.md`.
- Test status: second full non-TUI suite **2,414 passed, 51 skipped** on the prior docstring wording; final-source TUI/report group **40 passed**; frontend Vitest **223 passed**, owned-browser harness **9 passed**, TypeScript/static checks pass. An earlier full backend run had one synthetic-root WinError 5 during relocation setup; focused rerun and second full run passed, but cause remains unattributed. See exact evidence in `implementation-progress.md`.
- Current source/test files: `frontend/e2e/reports.spec.ts`, `frontend/e2e/run-owned.mjs`, `hedge_fund/paper/ledger.py`, `hedge_fund/tui/test_paper.py`, `hedge_fund/web/services.py`, `hedge_fund/web/test_reports.py`.
- Current specification/deployment/evidence changes: `README.md`, `docs/governance/web-migration-contract.md`, `memory.md`, `specs/005-web-engine-migration/contracts/headless-and-deployment.md`, `specs/005-web-engine-migration/contracts/runtime-api.md`, `specs/005-web-engine-migration/implementation-evidence.md`, `specs/005-web-engine-migration/implementation-progress.md`, `specs/005-web-engine-migration/plan.md`, `specs/005-web-engine-migration/r1-implementation-manifest.md`, `specs/005-web-engine-migration/report-parity-evidence.md`, `specs/005-web-engine-migration/spec.md`, and `specs/005-web-engine-migration/tasks.md`.
- Docker source files remain unchanged. README-inclusive final QA image tag `aihf-web-spec005-r1-20261105-1720-ee1441d6e50`, image ID `sha256:4c78a55ad7ff0e55df9dde3ff5527946163adb5491734037f6d7b2948c9df1e8`, `linux/amd64`. Build passed. Its configured entrypoint exits 2 because `--container-bind` is rejected; overriding that flag reaches `/data` and exits 2 because the Windows bind is `9p` rather than local NTFS/ext4. Final synthetic root digest stayed unchanged and both exact probe containers were removed. Linux/ext4, writable action/exclusion, local-Ollama and container replacement remain unverified. No release-ready claim.

## Prior implementation scope and identity

- Branch: `cgjedrem-shiny-tribble`.
- Base revision: `8660cc5f93c0fb81a7d1273abfd42b2fddd85f68`.
- Implementation commits: `9c1f5b8e6c5b69b648a68de49cb7164f638a9b2e` (`feat: implement Spec005 Release 1 paper desk flows`); `9c847d8fade403c18916f6b266cf4d38922d6a62` (`fix: record TUI Resume actor`).
- Source/test snapshot: 38 files, 1,638,124 bytes, SHA-256 `8bd944b98a805c15ea44b5b01d6a1b5b077a628e7ec781b6531be310a34aa7bc`.
- Snapshot covers sorted UTF-8 repository-relative path + NUL + full file bytes + NUL; excludes evidence documents, `memory.md`, and root `node_modules/`.
- Implementation preserves the published engine and React UI. No Docker or deployment topology changes.
- RB-5 was open at this earlier implementation checkpoint. The user later selected a writable single-writer Docker desk; current implementation remains blocked by the filesystem and container-identity evidence above.
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
- `hedge_fund/tui/paper.py` — retained TUI Resume path passes the TUI audit identity and uses the same effect-intent fence.
- `hedge_fund/tui/test_admission_regressions.py` — synthetic simple-Halt Resume identity and enrolled-root admission-denial regressions.

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
- RB-5: choice is selected but implementation/acceptance is blocked; do not mark complete until supported filesystem, final image, writer exclusion and identity lifecycle have current evidence.
- Test boundary: synthetic roots and fakes only. No live provider/broker calls, production-root activation, or real-fund writes.
