# Spec005 Release 1 implementation manifest

## Current continuation (2026-11-05)

- Worktree/branch: `cgjedrem-super-fiesta`; continuation base `3498ef8a7a1751917b16936c9219dda70dd7fa74`. Commits: `81959b6fa70b25d6a6d40a27d20ec809264efbaa`, `672d69379dc3558f498fd0a2992f9a5c82adc50d` and `cad96a05875efe13d229a8a079d2348ed6d0cf95`. Prior required commits remain in ancestry.
- Scope result: exact report-download bytes are preserved; report-selection regression uses keyboard input. Docker now has read-only inspection, explicit writable operator mode, Linux host-network overlay and build-baked source identity. No admission guard was weakened. Real roots, operator cutover and actual funds remain untouched.
- Final image: `aihf-web-spec005-r1-cad96a0-8875cf1`, ID `sha256:21582eeedfa316925b6656f4eedcb4dfd0b999062af3d3aa72f84ceaaa9597b6`, Linux/amd64, created `2026-11-05T18:24:31.448453995Z` UTC. Baked revision `cad96a05875efe13d229a8a079d2348ed6d0cf95`; baked package SHA-256 `8875cf13798d0b6f8468bba97ab3e7f4a21eb48ccd1f61f951b30cd94026d815`. Build ran **44.5122 s** from `2026-11-05T19:24:08.3366748+01:00` to `19:24:52.8510996+01:00`.
- Runtime status: bounded synthetic ext4 checks observed startup, trust, same-container restart, API denials, synthetic create/deploy, same-fund exclusion, stale-container denial, secret non-disclosure and sequential TUI rendering. The exact runtime observation timestamp and full invocation were not retained in the current evidence record; formal runtime status is **INCONCLUSIVE**, not PASS. Linux host-network/browser/Ollama, Windows bridge/browser/Ollama, target-fund operation, NTFS relocation and recreation/rebind remain unverified or blocked. See `implementation-evidence.md`.
- Test status: timestamped Python selection **302 passed in 293.92 s** (process elapsed **296.6548349 s**, exit 0) across ten backend/runtime/API/TUI modules; immutable package/test tree `36ad8b23874224ca3883bd6f6b05686d7c5ef145`. Black, repository-configured isort and Flake8 passed on all 13 changed Python files. Exact commands and times: `implementation-evidence.md`. This is not a full-suite result. Frontend Vitest **223 passed**, TypeScript exit 0, owned-browser safety **9 passed**, report browser **2 passed**, and desk lifecycle browser **15 passed** predate only an import-formatting change; they were not rerun after `cad96a0`. The earlier full-suite WinError 5 and historical 14-failure discrepancy remain unattributed. Independent QA remains pending; no release-ready claim.
- Compose merge: exact final-source configuration check passed **13 assertions** at `2026-11-05T19:52:45.5403224+01:00`–`19:52:46.0710415+01:00` in **0.528331 s**. This is configuration evidence only, not browser or host-network runtime evidence.
- Changed source/test files: `Dockerfile.web`, `docker-compose.yml`, `docker-compose.linux.yml`, `frontend/e2e/reports.spec.ts`, `frontend/e2e/run-owned.mjs`, `hedge_fund/paper/ledger.py`, `hedge_fund/pipeline/session.py`, `hedge_fund/pipeline/test_session_build_identity.py`, `hedge_fund/runtime/build_identity.py`, `hedge_fund/runtime/test_build_identity.py`, `hedge_fund/test_run.py`, `hedge_fund/tui/test_paper.py`, `hedge_fund/web/__main__.py`, `hedge_fund/web/app.py`, `hedge_fund/web/services.py`, `hedge_fund/web/test_app.py`, `hedge_fund/web/test_main.py`, and `hedge_fund/web/test_reports.py`.
- Changed specification/evidence/docs files: `README.md`, `docs/governance/web-migration-contract.md`, `memory.md`, `specs/005-web-engine-migration/contracts/headless-and-deployment.md`, `specs/005-web-engine-migration/contracts/runtime-api.md`, `specs/005-web-engine-migration/implementation-evidence.md`, `specs/005-web-engine-migration/implementation-progress.md`, `specs/005-web-engine-migration/plan.md`, `specs/005-web-engine-migration/r1-implementation-manifest.md`, `specs/005-web-engine-migration/report-parity-evidence.md`, `specs/005-web-engine-migration/spec.md`, and `specs/005-web-engine-migration/tasks.md`.

## Prior implementation scope and identity

- Branch: `cgjedrem-shiny-tribble`.
- Base revision: `8660cc5f93c0fb81a7d1273abfd42b2fddd85f68`.
- Implementation commits: `9c1f5b8e6c5b69b648a68de49cb7164f638a9b2e` (`feat: implement Spec005 Release 1 paper desk flows`); `9c847d8fade403c18916f6b266cf4d38922d6a62` (`fix: record TUI Resume actor`).
- Source/test snapshot: 38 files, 1,638,124 bytes, SHA-256 `8bd944b98a805c15ea44b5b01d6a1b5b077a628e7ec781b6531be310a34aa7bc`.
- Snapshot covers sorted UTF-8 repository-relative path + NUL + full file bytes + NUL; excludes evidence documents, `memory.md`, and root `node_modules/`.
- Implementation preserves the published engine and React UI. No Docker or deployment topology changes.
- At this earlier implementation checkpoint RB-5 was open and Docker source was unchanged. The later continuation added operator wiring and final-image synthetic ext4 observations; formal runtime evidence remains INCONCLUSIVE and existing-fund blockers remain.
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
- RB-5: inspect final-image synthetic-root observations and evidence limits. Keep unchecked until formal timestamped runtime provenance and supported existing-fund filesystem, protected-name and identity-lifecycle decisions are resolved.
- Test boundary: synthetic roots and fakes only. No live provider/broker calls, production-root activation, or real-fund writes.
