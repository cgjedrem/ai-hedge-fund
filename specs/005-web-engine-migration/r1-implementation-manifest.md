# Spec005 Release 1 implementation manifest

## Latest authorized lifecycle continuation (2026-11-07)

- Source/docs commit `2b4cbed2a20c6f9877cbbc762e6df378c960d3f8`, parent
  `66bc100`; committed diff 29,256 bytes, SHA-256
  `42cff85f38eb517236539f88dd184841ec42577ed42a28e4090e269901c868c4`.
  Package-source SHA-256:
  `3f1922909961798b36353a9309c4de9ddc6651b031f2ac7c0dd1ff529550cbd5`.
- Implementation commit files:
  `README.md`, `docker-compose.linux.yml`, `docker-compose.yml`,
  `docs/governance/web-migration-contract.md`,
  `hedge_fund/web/supervisor.py`, `hedge_fund/web/test_supervisor.py`,
  `specs/005-web-engine-migration/contracts/headless-and-deployment.md`.
- Follow-up evidence-only files:
  `specs/005-web-engine-migration/implementation-evidence.md`,
  `implementation-progress.md`, this manifest, `spec.md`, `tasks.md`, and
  `memory.md`.
- Build artifact: Linux/amd64 image tag
  `aihf-web:2b4cbed2a20c6f9877cbbc762e6df378c960d3f8-3f1922909961798b36353a9309c4de9ddc6651b031f2ac7c0dd1ff529550cbd5`,
  ID `sha256:ededc795ef56179fc923a28043a3e00d424558b5f06bc20d0f2e43f0716c430e`.
- Runtime artifacts in ignored `outputs/spec005-supervisor-lifecycle-20261107-102921/`:
  `progress.log`, `compose.lifecycle.yml`, `prepare_migration_root.py`,
  `runtime_lifecycle_scenarios.py`, and `orphan_reap_probe.py`.
- Synthetic A was read-only, but helper-to-service enrollment failed because
  immutable root `host` identity differed. No trust, rebind, writable A, B or C
  ran. Container and exact owner-labeled ext4 volume were removed; image retained.
  Overall acceptance **INCONCLUSIVE / not accepted**, RB-5 unchecked. Full
  evidence is in `implementation-evidence.md`; no independent QA claim.

## Latest trust-lifecycle continuation (2026-11-07)

- Source correction: `1846c970acd88d836a84ae03a9699966c31154df`
  (`fix: require explicit trust for web writes`), parent
  `c77163e3862410813af5497a82f0ad6a0badda59`.
- Changed source: `hedge_fund/web/supervisor.py`,
  `hedge_fund/web/test_supervisor.py`. The supervisor now requires exact
  `operator-trusted-single-writer`, not generic `protocol-native` write authority.
- Targeted final-source regressions: supervisor **20 passed**, runtime authority
  **41 passed**, web authority **3 passed**; Black/isort/Flake8/diff check passed.
- Final build: clean revision `1846c970acd88d836a84ae03a9699966c31154df`,
  selected-package SHA-256
  `415e28b31527c2a10c295ef92d2729c8a60e8d39604d3df26d1dd0fac8ec5cab`,
  image ID `sha256:a834e17d6b4d627ea4132a3ed223c38c0bf219eb659e41b3ff2faa7af6283713`,
  Linux/amd64. Final `web-operator` Compose config passed **9/9** assertions; no
  container started from this image. Full provenance is in `implementation-evidence.md`.
- The prior `c77163e` artifact's no-trust SIGHUP **FAIL** exposed writes/network after
  fresh synthetic enrollment classified `protocol-native`. No valid mutation ran; the
  container stopped before a writable replacement. The corrected image was not started
  after fail-stop. Final runtime acceptance remains **INCONCLUSIVE / not accepted**;
  A/B/C runtime checks remain not run and RB-5 remains unchecked.
- Changed evidence/docs: `specs/005-web-engine-migration/implementation-evidence.md`,
  `implementation-progress.md`, `change-manifest.md`, `spec.md`, `tasks.md`,
  `contracts/headless-and-deployment.md`, this manifest, `docs/governance/web-migration-contract.md`,
  and `memory.md`. Ignored session progress: `outputs/spec005-g5-runtime-c77163e-20261107-0940/progress.log`.
- No cutover, real-fund writes, provider/LLM/broker calls, public exposure, or Docker
  prune. Independent QA remains coordinator-owned.

## Latest runtime evidence and documentation continuation (2026-11-05)

- Source/artifact: clean source revision `7ec7aaa970a1805478940691a948f1b0dbed4649`,
  package digest `152aa83b71b6cab8569aaf270ee7215208444335713bc4887cd17544c9bad263`,
  Compose tag `aihf-web:7ec7aaa970a1805478940691a948f1b0dbed4649-152aa83b71b6cab8569aaf270ee7215208444335713bc4887cd17544c9bad263`,
  image ID `sha256:b998cd64d5d28c5853ee36fe88381b3ff4a5b4ea7cabb0f1c7d239d5ba7fd977`,
  Linux/amd64. Exact build/runtime provenance is in `implementation-evidence.md`.
- Runtime: Linux Compose host-network profile and synthetic ext4 named volume exercised.
  Fresh-root, API-security, protected-root, synthetic paper, same-fund exclusion,
  stale-recovery and sequential CLI-TUI checks passed. **Replacement identity gate FAIL:**
  replacement retained the enrolled PID/mount namespace identity and readiness remained
  `enrolled`; probe stopped before capability/write-denial checks. No write-enabled
  replacement or reenrollment ran. Overall acceptance remains **INCONCLUSIVE / not
  accepted**; RB-5 stays unchecked.
- Revision label is operator-supplied and format-checked, not Git-verified. Package digest
  is verified for selected `hedge_fund` files; it excludes generated identity, web static
  assets, frontend, Dockerfile, lockfiles, base image and OS layers. `tui-web`/ttyd was not
  started and remains unapproved. No real roots, funds, cutover, external provider calls or
  broker calls.
- Targeted `test_build_identity.py` and `test_session_build_identity.py`: **13 passed**;
  Black, configured isort and Flake8 (`--max-line-length=420`) passed on four relevant
  Python files.
- Exact task-owned cleanup: five stopped containers and the synthetic ext4 volume removed;
  final image retained. `runtime-cleanup.log` records IDs, commands and timestamps;
  `final-resource-state.log` confirms no project containers, networks, volume or `probe2`.
- Evidence/docs changed in this continuation: `docs/governance/web-migration-contract.md`,
  `memory.md`, `specs/005-web-engine-migration/contracts/headless-and-deployment.md`,
  `implementation-evidence.md`, `implementation-progress.md`, `plan.md`,
  `r1-implementation-manifest.md`, `spec.md`, and `tasks.md`. Structured blocker recorded
  at `C:\Users\ChristianGjedrem\.copilot\session-state\67b35421-22ab-450f-9b9c-b1d67e6c4e5e\files\spec005-r1-replacement-identity-blocker.json`.

## Earlier continuation summary — cad96a artifact (superseded)

- Worktree/branch: `cgjedrem-super-fiesta`; continuation base `3498ef8a7a1751917b16936c9219dda70dd7fa74`. Commits: `81959b6fa70b25d6a6d40a27d20ec809264efbaa`, `672d69379dc3558f498fd0a2992f9a5c82adc50d`, `cad96a05875efe13d229a8a079d2348ed6d0cf95`, `4ed878775c00ef47fcd3fd82bf8ac99f37eb4c7f` and `7ec7aaa970a1805478940691a948f1b0dbed4649`. Prior required commits remain in ancestry.
- Scope result: exact report-download bytes are preserved; report-selection regression uses keyboard input. Docker now has read-only inspection, explicit writable operator mode, Linux host-network overlay and build-baked source identity. No admission guard was weakened. Real roots, operator cutover and actual funds remain untouched.
- Historical image record: `aihf-web-spec005-r1-cad96a0-8875cf1`, ID `sha256:21582eeedfa316925b6656f4eedcb4dfd0b999062af3d3aa72f84ceaaa9597b6`, Linux/amd64. The prior record listed a direct `docker build` command without the Dockerfile's required identity args; no prior build log remains. Treat exact build provenance as **INCONCLUSIVE**. It is not the current image.
- Historical runtime status: bounded synthetic ext4 checks were reported, but exact runtime provenance was missing and the old replacement-success claim is not current evidence. See the historical section in `implementation-evidence.md`; the current `7ec7aaa` replacement identity gate failed.
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
