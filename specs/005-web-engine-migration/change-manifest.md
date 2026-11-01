# Change Manifest — python-dev

## Created

- `hedge_fund/test_acceptance_isolation.py` — isolation boundary and process-cleanup regressions.
- `hedge_fund/test_support/__init__.py` — test-support package marker.
- `hedge_fund/test_support/network_guard.py` — isolated environment, dotenv, socket, child-process, and safe cleanup helpers.
- `hedge_fund/test_support/sitecustomize.py` — installs test isolation in Python children.
- `hedge_fund/runtime/__init__.py` — runtime package marker.
- `hedge_fund/runtime/root.py` — explicit root identity, filesystem policy, handle-relative access, atomic writes and lock-file handles.
- `hedge_fund/runtime/test_root.py` — fixed-root, alias, filesystem, reparse, race, I/O and lock-handle contract tests.
- `hedge_fund/runtime/test_bootstrap.py` — explicit-root bootstrap, dotenv and root-scoped cache regressions.
- `hedge_fund/runtime/test_defaults.py` — T008 expected-red tests for neutral defaults, minute schedule labels, warm progress chunking and import closure.
- `hedge_fund/reporting/__init__.py` — neutral reporting package marker.
- `hedge_fund/reporting/palette.py` — canonical Rich palette outside TUI imports.
- `hedge_fund/reporting/names.py` — shared analyst display-name maps.
- `hedge_fund/reporting/console.py` — headless report, scorecard and cost renderables.
- `hedge_fund/reporting/test_console.py` — T008 expected-red console cost, scorecard order/precision, fixed-version serialization and import-closure tests.
- `hedge_fund/runtime/defaults.py` — neutral backtest defaults, warm-task chunking and schedule labels.
- `hedge_fund/runtime/credentials.py` — neutral credential save, mask and missing-key helpers.
- `hedge_fund/runtime/test_credentials.py` — credential boundary and no-TUI import-closure tests.
- `hedge_fund/runtime/admission.py` — versioned root/deployment OS locks, manual admission and bounded control lane.
- `hedge_fund/runtime/test_admission.py` — T009 cross-process lock, ownership-fail-closed and bounded-control tests.
- `hedge_fund/runtime/configuration.py` — non-secret settings resolution, persistence, provider/model validation and isolated child environment.
- `hedge_fund/runtime/capture.py` — immutable digest-checked captures and root-scoped credential-version handles.
- `hedge_fund/runtime/policy.py` — provider classification, one-shot paid authorization and finite scheduled dispatch budgets.
- `hedge_fund/runtime/operations.py` — root-private preview/token consumption, durable operation sidecars, request idempotency, state fencing and snapshot-consistent reads.
- `hedge_fund/runtime/test_capture.py` — T010 expected-red design plus T016 settings, capture, import-closure and environment regressions.
- `hedge_fund/runtime/test_policy.py` — T010 expected-red design plus T017 provider-classification, budget and finite-runner regressions.
- `hedge_fund/runtime/test_operations.py` — T011 expected-red and green regressions for canonical confirmation, idempotent request acceptance, stale preview denial, cancellation boundaries, snapshot consistency and interrupted-worker fencing.
- `frontend/e2e/run-owned.mjs` — owns browser test root, environment, port, static output, exact child lifecycle, and production artifact fingerprint.
- `frontend/scripts/run-owned.test.mjs` — ownership, port/static output, network-boundary, and artifact fingerprint tests.
- `frontend/src/test/setup.test.ts` — browser-unit-test global isolation checks.
- `specs/005-web-engine-migration/acceptance-matrix.md` — individual capability and cross-cutting acceptance inventory.
- `specs/005-web-engine-migration/retired-assertions.md` — TUI and external import-closure assertion inventory.
- `specs/005-web-engine-migration/environment-evidence.md` — verified Windows/tool inventory and Linux/ext4 blockers.
- `specs/005-web-engine-migration/implementation-evidence.md` — revision-bound harness test evidence.
- `specs/005-web-engine-migration/implementation-progress.md` — task checkpoints and next stop.
- `specs/005-web-engine-migration/change-manifest.md` — implementation file inventory.
- `specs/005-web-engine-migration/spec005-final-evidence.md` — consolidated final bounded-QA evidence and artifact identities.
- `specs/005-web-engine-migration/qa-final-disposition.md` — partial readiness, remaining blockers and safe preview boundary.
- `specs/005-web-engine-migration/screenshots/desktop-backtests.png` — synthetic browser screenshot.
- `specs/005-web-engine-migration/screenshots/desktop-builder.png` — synthetic browser screenshot.
- `specs/005-web-engine-migration/screenshots/desktop-mandate-detail.png` — synthetic browser screenshot.
- `specs/005-web-engine-migration/screenshots/desktop-mandates.png` — synthetic browser screenshot.
- `specs/005-web-engine-migration/screenshots/desktop-overview.png` — synthetic browser screenshot.
- `specs/005-web-engine-migration/screenshots/desktop-paper-detail.png` — synthetic browser screenshot.
- `specs/005-web-engine-migration/screenshots/desktop-paper-list.png` — synthetic browser screenshot.
- `specs/005-web-engine-migration/screenshots/desktop-research-list.png` — synthetic browser screenshot.
- `specs/005-web-engine-migration/screenshots/desktop-research-report.png` — synthetic browser screenshot.
- `specs/005-web-engine-migration/screenshots/desktop-scorecard.png` — synthetic browser screenshot.
- `specs/005-web-engine-migration/screenshots/desktop-session-report.png` — synthetic browser screenshot.
- `specs/005-web-engine-migration/screenshots/desktop-settings.png` — synthetic browser screenshot.
- `specs/005-web-engine-migration/screenshots/mobile-overview.png` — synthetic browser screenshot.
- `specs/005-web-engine-migration/screenshots/mobile-paper-detail.png` — synthetic browser screenshot.
- `specs/005-web-engine-migration/screenshots/mobile-research-report.png` — synthetic browser screenshot.
- `specs/005-web-engine-migration/screenshots/mobile-session-report.png` — synthetic browser screenshot.
- `specs/005-web-engine-migration/screenshots/mobile-settings.png` — synthetic browser screenshot.

## Modified

- `hedge_fund/conftest.py` — establish isolated test state before application imports; reap exact owned child.
- `hedge_fund/web/conftest.py` — retain offline web fixtures under the shared harness.
- `frontend/e2e/desk.spec.ts` — isolate expected origin and browser screenshot destination.
- `frontend/package.json` — route E2E command through owned runner.
- `frontend/playwright.config.ts` — validate owned root/port/output and deny external requests.
- `frontend/src/test/setup.ts` — install fake-network guards and test cleanup.
- `frontend/vite.config.ts` — loopback API target and fixture-owned test build output.
- `hedge_fund/web/__main__.py` — root-first web startup, isolated static root and non-conflicting default port.
- `hedge_fund/web/demo.py` — validate fixture-owned demo/static paths.
- `hedge_fund/web/test_launcher.py` — launcher root/port regression coverage.
- `hedge_fund/web/test_main.py` — default port, demo/static path and escape-denial coverage.
- `hedge_fund/test_paths.py` — fixed-root identity revalidation regression.
- `hedge_fund/paths.py` — explicit root binding, exact-root opted-in dotenv and root-relative I/O helpers.
- `hedge_fund/run.py` — pre-import explicit-root CLI bootstrap, root-relative paths and neutral report helpers after root binding.
- `hedge_fund/test_run.py` — CLI relative-mandate root regression and removal of the obsolete credential-loader patch.
- `check_stock.py` — remove TUI credential-loader dependency; require provider credentials in the process environment.
- `hedge_fund/tui/palette.py` — compatibility exports from neutral report palette.
- `hedge_fund/tui/shared.py` — compatibility exports from neutral names/default helpers.
- `hedge_fund/tui/scorecard_view.py` — compatibility exports from neutral scorecard renderers.
- `hedge_fund/tui/report.py` — use neutral session headline and cost renderers.
- `hedge_fund/tui/builder.py` — use neutral interval/schedule helpers.
- `hedge_fund/tui/backtest.py` — use neutral backtest defaults and warm-task chunking.
- `hedge_fund/tui/paper.py` — use neutral board refresh default.
- `hedge_fund/tui/keys.py` — compatibility exports from neutral credential helpers; legacy dotenv loader remains.
- `hedge_fund/tui/test_keys.py` — patch the neutral credential writer.
- `hedge_fund/tui/test_home.py` — isolate dotenv-precedence tests and avoid treating Windows mode bits as ACL proof.
- `hedge_fund/fund/spec.py` — root-bound YAML reads.
- `hedge_fund/fund/test_spec.py` — handle-bound YAML read regression.
- `hedge_fund/data/cached.py` — root-scoped data cache reads/writes.
- `hedge_fund/features/breakpoints.py` — root-scoped breakpoint cache reads/writes.
- `hedge_fund/llm/cache.py` — root-scoped prompt cache reads/writes.
- `hedge_fund/llm/test_client.py` — explicit root CLI invocation, UTF-8 output reads and no-TUI credential helper import.
- `hedge_fund/web/app.py` — pass the fixed root context into the web service.
- `hedge_fund/web/services.py` — bind service file access to the configured root context; verify mandate inventory under the registry lock; count uncapped research totals; gate backtests on local/free provider policy.
- `hedge_fund/web/test_actions.py` — root-bound web action regressions and classifier-denial HTTP mapping.
- `hedge_fund/web/test_app.py` — fixed-root app coverage.
- `hedge_fund/web/test_jobs.py` — durable operation worker progress, cancellation, restart and fencing tests; bounded wait timeouts.
- `hedge_fund/web/test_services.py` — root-bound service regressions; mandate drift, clone admission, rename/write retry, local/free backtest and uncapped research-count coverage.
- `hedge_fund/web/test_settings.py` — root-bound settings file coverage.
- `memory.md` — append verified root-guard, pagination, retry-limit, policy-mapping and style-baseline facts.
- `specs/005-web-engine-migration/tasks.md` — task status and platform/integration limits.
- `specs/005-web-engine-migration/implementation-evidence.md` — revision-bound test, browser, package and limitation evidence.
- `specs/005-web-engine-migration/implementation-progress.md` — T001–T018 checkpoints, final verification and blockers.
- `specs/005-web-engine-migration/change-manifest.md` — cumulative source/test/document inventory.
- `specs/004-react-web-ui/parity-checklist.md` — retained-TUI and final migration blockers.

## Deleted

- None.

## Final bounded QA closure — 2026-11-01

- Service guard regressions deny both in-place mandate updates and physical renames after root-inventory drift; research home count uses the uncapped `total`; clone storage-admission failure maps to 409; paid/unknown backtest policy denies before operation persistence.
- The rename-then-write path is not transactional. Fault injection confirms a failed write leaves original bytes at the renamed path; retry with the original logical identity succeeds. No crash-atomicity claim.
- Final browser run refreshed the synthetic screenshot set. Seventeen files: 2,749,128 bytes; sorted relative filename + NUL + full bytes + NUL SHA-256 `18b4f94915483066e59286ab82626ab26b514e8c01c61729d7d6dafa44629039`.
- Final artifact/test source identity covers every modified tracked `.py`, `.ts`, `.tsx`, `.mjs` and `.png` path, not a narrow four-file selection: at `2026-11-01T11:45:32.6822468+01:00` → `11:45:32.8695038+01:00`, 41 paths / 2,308,066 bytes / SHA-256 `875ade896c3869ffe4213cba47e7440edceb35d6ed4ce20da91ec25fe9b3e62b`. Algorithm: sorted UTF-8 repository-relative path + NUL + full worktree bytes + NUL. Base revision: `9694f619207e14fb5e55de1bef96deb79df7a360`.
- Production static bundle and wheel-embedded static files match the owned Playwright artifact: 3 files / 973,294 bytes / SHA-256 `309b88c7a472685221fee0cb89f207d9d72e8f36d9f38a2a9a2301c82df7897a`. Wheel: `dist/aihf-2.6.1-py3-none-any.whl`, 653,276 bytes / SHA-256 `db57b12627fcb5bf86b2587c1842cf7e6a5a9be7de01768d1721f50b68cc19e0`; build passed, wheel install/runtime smoke not run.
- Full tracked-diff identity is recorded in the ignored session artifact and PR #8 handoff after commit. Untracked `pip/` and `pypa/` remain untouched and excluded.

## Acceptance boundary

- T011 test-design task is complete; operation-store tests pass on synthetic Windows/NTFS, with one earlier unrooted sidecar-write failure retained as INCONCLUSIVE.
- T018 implementation/test criteria are complete only on synthetic Windows/NTFS. Durable operation storage is not wired into the production API/DeskService mutation paths; owned-child lifecycle, ACL/private-storage proof and controlled legacy-writer handover are not established.
- T015/T021 remain partial. T137/T138/T140/T142–T145/T147/T148 remain open; T139/T141/T146 have bounded partial evidence but stay unchecked. Full migration and TUI retirement remain BLOCKED.
- Full Python suite remains INCONCLUSIVE after prior stalls at 149 passed / 2 skipped of 1,207 collected. Native Linux/ext4 and actual NTFS ACL evidence remain BLOCKED. The final wheel built, but installed-wheel runtime smoke remains INCONCLUSIVE.
- React desk remains an additive subset. TUI/Textual and operator recovery paths remain retained. Do not enable production writes, paid/headless dispatch or container execution from this partial candidate.
- Untracked `pip/` and `pypa/` are preserved, untouched and excluded from this manifest and implementation staging.
- `outputs/spec005-test-final-closure-20261101-01/session-artifacts/progress.md` contains the exact final command checkpoints; ignored artifact, not staged or included in the PR.
