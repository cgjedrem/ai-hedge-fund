# Implementation evidence

## T001–T002 test isolation

| Field | Evidence |
|---|---|
| Status | PASS — source/unit and fake regression tests only |
| Base revision | `19bbf49864d060b496bbd32b80944b15fd1de8ba` |
| Branch | `cgjedrem-vigilant-robot` |
| Source/test identity | SHA-256 over sorted relative paths, NUL separators, and full file bytes: `a9075a070b511f8442a68f1a2e92d48ff72187196491e60be0f03a91f54f6b20` |
| Files in identity | `hedge_fund/conftest.py`, `hedge_fund/web/conftest.py`, `hedge_fund/test_acceptance_isolation.py`, `hedge_fund/test_support/__init__.py`, `hedge_fund/test_support/network_guard.py`, `hedge_fund/test_support/sitecustomize.py` |
| Artifact | Source-run; no wheel, container, or production build |
| Environment | Windows 10 Enterprise build 26200; NTFS worktree; Python 3.13.7; Poetry 2.5.1; locked `python-dotenv` 1.0.0 |
| Isolation | Test HOME/USERPROFILE/TEMP/TMP and pytest roots under checkout `outputs`; `PYTHON_DOTENV_DISABLED=1`; provider, model, root, key-reference, and proxy variables cleared; Python sockets reject non-loopback targets |
| Dotenv boundary | `load_dotenv` and implicit `find_dotenv` disabled in parent and Python children; explicit `dotenv_values` accepted only for paths inside the marked session root |
| Scenario | Synthetic roots and sentinels only; fake/offline web regression tests; no provider credentials, paid calls, real data roots, or outbound traffic; non-loopback socket requests rejected before I/O |
| Provenance | Test output captured from commands executed in this worktree; no user-reported or inherited pass counted |

### Measurements

- `2026-10-31T15:57:46.2286105+01:00` → `2026-10-31T15:57:49.9115310+01:00`: `outputs\web-migration-acceptance-20261031-152200\venvs\aihf-Tbl0PwyA-py3.13\Scripts\python.exe -m pytest hedge_fund\test_acceptance_isolation.py -p no:cacheprovider -q --durations=10`; **19 passed in 1.70 s**, process elapsed **3.6829205 s**, exit 0.
- `2026-10-31T15:57:46.2266887+01:00` → `2026-10-31T15:57:51.5134333+01:00`: `outputs\web-migration-acceptance-20261031-152200\venvs\aihf-Tbl0PwyA-py3.13\Scripts\python.exe -m pytest hedge_fund\web -p no:cacheprovider -q --durations=10`; **71 passed in 3.00 s**, process elapsed **5.2867446 s**, exit 0.
- `2026-10-31T15:58:35.1439813+01:00` → `2026-10-31T15:58:37.1118855+01:00`: changed-scope Black, isort, flake8, and `git diff --check`; all exit 0, process elapsed **1.9679042 s**.
- Final identity includes an assertion that every `hedge_fund.llm.PROVIDER_ENV_VARS` value is present in the cleared-variable list. All marked `spec005-test-*` roots were absent after the final test runs.
- No frontend or live-runtime check represented by these rows.
- Test session roots used `.test-owned` markers and were removed. A negative cleanup test confirmed an external-to-root synthetic sentinel survived directory-symlink removal.

### Failed attempts and repairs

- `2026-10-31T15:48:25.9734617+01:00` → `2026-10-31T15:48:29.5125360+01:00`: expected-red child-isolation probes; **2 failed, 15 deselected in 0.42 s**, test process exit 1. The child helper accepted HOME/PYTHONPATH overrides, and a spawned child could not import the project from its isolated working directory. The wrapper returned 0 only to allow this expected-red phase to continue.
- Child environment now rejects path/import overrides and admits only string-valued synthetic provider/proxy/test variables. Child `PYTHONPATH` exposes the test shim and checkout; the child validates HOME/TEMP/AppData/XDG/dotenv paths before app import. Final child-import probe passed.
- First full web run after global dotenv suppression: **70 passed, 1 failed**. The test guard also blocked `DeskService` reading its explicit synthetic root `.env`. Guard now permits explicit paths only inside the marked test root; ambient loading remains disabled. The rerun above passed.
- First default-basetemp runs completed tests but session cleanup failed because pytest and synthetic storage fixtures create reparse entries. Cleanup now unlinks reparse entries without traversing targets; the sentinel-preservation test and subsequent session cleanup passed.
- Initial formatting checks failed. Changed-scope Black, isort, and flake8 passed after formatting.
- Final review formatting checks flagged import grouping and E501 line length in the provider-registry parity assertion. The test was reformatted; final isolation, web, and style runs above passed against the final source/test identity.

### Limits

- Static review and local fake/unit observations only. No live network, browser production artifact, Linux filesystem, container, paid provider, real user root, or real process runtime was exercised.
- Cleanup rejects and unlinks observed reparse entries without traversal. Concurrent path replacement during recursive cleanup was not tested; session roots are unique and marker-owned.
- No retirement or cross-platform parity claim follows from these rows.

## T003 test-owned browser acceptance harness

| Field | Evidence |
|---|---|
| Status | **PASS — T003 harness acceptance only.** Production build and six guarded browser tests passed. No engine-parity or retirement claim follows. |
| Base revision | `5860036d6a247d5858b5a34204bda3cb4c82816b` |
| Source/test identity | SHA-256 over 12 sorted T003 code/test paths, path/content NUL separators: `3660bf4c708bb54cf0ce1666b55ae56b3c7df2c538c12d22e22f71f00431d9b5`. |
| Artifact | Vite output SHA-256 `58a6fb074175e08905a77a214741a92cef02c965317e35f279136e8629c7f434`; 3 files, 944,284 bytes. Built from the source/test identity above into the marked E2E root and hashed before cleanup. No wheel/install artifact. |
| Environment | Windows 11 Enterprise 10.0.26200; NTFS `C:`; Python 3.13.7; Poetry 2.5.1; Node 22.13.1; npm 10.9.2; TypeScript 5.9.3; Vite 6.4.5; Playwright 1.64.1; Edge 156.0.4314.50. |
| Isolation | E2E and Python test roots under checkout `outputs`; HOME/USERPROFILE/TEMP/XDG isolated; dotenv disabled; credential/provider/proxy/Node overrides cleared; provider fakes; loopback-only browser API. Vite output, Playwright results, browser cache and npm cache target the marked E2E root, not `hedge_fund/web/static`. |
| Scenario | Explicit port `8876`; no server reuse; demo root and static output are fixture-owned; external browser requests denied. Desktop/narrow routes, builder submission, backtest review/cancel, deep links, disabled decisions and reload recovery exercised. |
| Provenance | Direct commands in this worktree; execution owner python-dev. No PR7 totals or user report used. T003 does not exercise real data, real runner ownership, paid providers or migration parity. |

### Measurements

- `2026-10-31T17:35:51.3659567+01:00` → `2026-10-31T17:35:56.3933682+01:00`: isolated `python -m pytest hedge_fund/web -p no:cacheprovider -q --durations=10`; **76 passed in 3.20 s**, process elapsed **5.0274115 s**, exit 0.
- `2026-10-31T17:35:51.2799550+01:00` → `2026-10-31T17:35:52.4955909+01:00`: isolated `node --check frontend/e2e/run-owned.mjs` and `node --test frontend/scripts/run-owned.test.mjs`; **6 Node tests passed**, Node test duration **688.395 ms**, combined process elapsed **1.2156359 s**, exit 0.
- `2026-10-31T17:35:51.3659567+01:00` → `2026-10-31T17:37:47.9819881+01:00`: from `frontend/`, `node e2e/run-owned.mjs` with `AIHF_E2E_PYTHON` set to the absolute isolated venv interpreter; TypeScript check passed; Vite transformed **2,307 modules**, built in **36.77 s**, emitted 3 files / **944,284 bytes**, artifact hash above. Playwright: **6 passed in 13.8 s**, process elapsed **116.6160314 s**, exit 0. Vite emitted a non-fatal 919.58 kB minified-chunk warning.
- Same browser run: **17 screenshots / 2,830,416 bytes** under `specs/005-web-engine-migration/screenshots/`; all use synthetic demo data. The test's external-request assertion passed. Exclusive port-bind probe exited 0 after the run; E2E root `spec005-test-e2e-49624-1bb7f233` was absent; exact server PID `49664` was absent.
- Vitest reported start `17:43:25` local on `2026-10-31`; from `frontend/`, `node node_modules/vitest/vitest.mjs run src --reporter=verbose`; **2 files / 11 tests passed**, Vitest duration **75.49 s**, process elapsed **78.571 s**, exit 0. Recharts logged zero-sized chart warnings in jsdom; tests passed.
- `2026-10-31T17:45:48.7326900+01:00` → `2026-10-31T17:45:50.9569265+01:00`: Black `--check`, isort `--check-only`, flake8 with `--extend-ignore=E501`, and `git diff --check` over the four changed Python files; all exit 0.
- `2026-10-31T17:46:03.6542462+01:00` → `2026-10-31T17:46:06.4572560+01:00`: baseline-relative flake8 comparison against `HEAD` for the same four Python files; **38 baseline / 36 current E501 findings, 0 added, 2 removed**, exit 0. Plain flake8 still reports inherited E501 findings; changed lines add none.
- `2026-10-31T17:45:48.7837110+01:00` → `2026-10-31T17:45:49.9502743+01:00`: isolated `node --check frontend/e2e/run-owned.mjs` and `node --test frontend/scripts/run-owned.test.mjs`; **6 passed**, Node test duration **642.164 ms**, exit 0.
- T003 code/test paths: `frontend/e2e/desk.spec.ts`, `frontend/e2e/run-owned.mjs`, `frontend/package.json`, `frontend/playwright.config.ts`, `frontend/scripts/run-owned.test.mjs`, `frontend/src/test/setup.ts`, `frontend/src/test/setup.test.ts`, `frontend/vite.config.ts`, `hedge_fund/web/__main__.py`, `hedge_fund/web/demo.py`, `hedge_fund/web/test_launcher.py`, `hedge_fund/web/test_main.py`.

### Expected-red and repair record

- Fixture-owned static-output tests first failed as intended: Python launcher left `app.state.static_root` unset; Node harness did not configure the build output under its owned root.
- The runner now supplies `outputs/<owned-root>/web-static`; Vite uses the override only in test mode and validates its location; the Python launcher validates marked-root containment/reparse points and passes the existing `create_app(static_dir=...)` option.
- Two subsequent test-only failures exposed a root-prefix assumption and reuse of a demo directory. Tests now accept the shared `spec005-test-*` marker prefix and use unique roots. Black/isort checks exposed formatting/import grouping issues; the changed scope was corrected and rechecked.
- An earlier offline `npm ci` failed `ENOTCACHED` for `yallist-3.1.1.tgz`. A later authorized locked install completed **311 packages in 52 s**; its timestamp was not retained. The final browser run used those installed dependencies with child npm offline mode.
- The runner now reports the sorted-path/content SHA-256 of its fixture-owned production bundle before cleanup; the six Node safety tests include deterministic-path/content fingerprint coverage.

### Blockers and limits

- The build warning remains non-fatal. jsdom reports zero-sized Recharts containers; frontend unit tests pass, but screenshot visual completeness is not established by that warning or these tests.
- Manual visual screenshot spot-check showed a large empty panel below the overview hero. No current assertion verifies that panel's content; visual completeness is **INCONCLUSIVE**, not a harness failure or a migration pass.
- The full Python suite remains **INCONCLUSIVE**: 1,207 collected; four observed attempts stopped after 149 passed / 2 skipped at `test_two_managers_reread_rotated_token_under_shared_reference_lock`. A full-trace run showed the main thread waiting in `Thread.start()` while the fake worker had reached its bounded transport wait; plugin autoload was disabled. The test file passes alone (8 passed in 0.31 s). Root cause is unresolved; no test/code patch is justified by this evidence.
- Linux/ext4 lifecycle remains **BLOCKED**. WSL exposed only `docker-desktop`; Docker 29.9.2 metadata reported `linux/amd64`, but no container or compose service was inspected or run. No ext4 filesystem behavior is proven.
- No paid provider/LLM calls, real data roots, protected runners, existing compose services, or port `8765` were accessed. T003 proves harness behavior only, not TUI parity or engine safety.

## T006 environment inventory

- Status: **PASS — environment inventory only**. Linux/ext4 and container lifecycle remain **BLOCKED**.
- Observation window: `2026-10-31T17:32:11.7590288+01:00` → `2026-10-31T17:32:19.1487375+01:00`; Docker client/server metadata: `2026-10-31T17:39:36.0287862+01:00` → `2026-10-31T17:39:36.3830616+01:00`.
- Observed: Windows 11 Enterprise build `26200`, NTFS `C:`, Python `3.13.7`, Poetry `2.5.1`, Node `22.13.1`, npm `10.9.2`, Edge `156.0.4314.50`, Docker `29.9.2` server `linux/amd64`, and WSL distribution list containing only `docker-desktop`.
- No container or compose service was queried or operated. Docker metadata does not prove ext4; no native Linux/ext4 or container acceptance row passes. Full inventory and dependency-install limits are in `environment-evidence.md`.

## T007 fixed-root and path contract tests

| Field | Evidence |
|---|---|
| Status | **PASS — test contract and Windows/NTFS local synthetic root only.** Linux/ext4 runtime remains **BLOCKED**. |
| Base revision | `5860036d6a247d5858b5a34204bda3cb4c82816b` |
| Source/test identity | SHA-256 over sorted relative paths, NUL separators and full bytes: `5e4fcb0e932f6dd3820962838a1f1ade1b89b877406fe84c7ea5589309a663c8`. |
| Files | `hedge_fund/runtime/__init__.py`, `hedge_fund/runtime/root.py`, `hedge_fund/runtime/test_root.py`, `hedge_fund/test_paths.py`. |
| Artifact | Source-run; no package, wheel, container or production artifact. |
| Environment | Windows 11 Enterprise build `26200`, local NTFS `C:`, Python `3.13.7`; synthetic pytest roots under checkout `outputs`. |
| Isolation | Test HOME/USERPROFILE/TEMP under isolated checkout roots; dotenv disabled; credential/provider/proxy/root variables cleared; fake cloud-status cases; no provider, broker or external calls. |
| Scenario | Missing/relative root, decoy HOME/CWD/root and `.env`, case/YAML aliases, traversal/reserved/trailing-dot-space/UNC paths, protected synthetic identities before path probes, local/remote/cloud/unknown filesystem policy, real NTFS handle-relative read/write, reparse denial and root-rename exclusion/revalidation. |
| Provenance | Direct isolated pytest/style commands in this worktree; no real user data root or protected runner touched. |

### Measurements

- Expected-red observation `2026-10-31T17:49:06.4054522+01:00` → `2026-10-31T17:49:07.7762991+01:00`: pytest collection failed with two `ModuleNotFoundError: hedge_fund.runtime.root` errors; expected before implementation.
- First implementation run `2026-10-31T17:55:24.6797184+01:00` → `2026-10-31T17:55:26.4514781+01:00`: reparse-denial test left a child handle open; pytest session cleanup observed `WinError 32`. The rejection path now closes the handle before returning.
- Second implementation run `2026-10-31T17:56:05.9445650+01:00` → `2026-10-31T17:56:07.6049180+01:00`: **32 passed / 2 skipped / 1 failed**; native file open returned `WinError 87`. An isolated access-mask probe showed `GENERIC_READ` and missing `SYNCHRONIZE` failed; explicit read-data/read-attributes/synchronize opened the synthetic file.
- Final tests `2026-10-31T17:59:41.5094394+01:00` → `2026-10-31T17:59:43.6311852+01:00`: `python -m pytest hedge_fund/runtime/test_root.py hedge_fund/test_paths.py -p no:cacheprovider -q --durations=10`; **35 passed, 2 skipped in 0.60 s**, process elapsed **2.1217458 s**, exit 0. Skips are existing POSIX-only file-mode tests.
- Final style `2026-10-31T17:59:41.5611458+01:00` → `2026-10-31T17:59:43.7349227+01:00`: Black 420, isort Black profile, flake8 `--max-line-length=420 --extend-ignore=E203`, and `git diff --check`; all exit 0.
- Windows cloud-files probe on a synthetic checkout root returned HRESULT `0x80070186`; `FormatError(390)` identified “The operation is only supported on files under a cloud sync root.” Unknown API statuses fail closed; NTFS/root access tests passed.

### Limits

- Root support is not wired into `paths.py`, CLI bootstrap or web startup yet; T012 remains open.
- Linux/ext4 implementation and actual runtime primitives were not exercised. Cloud-sync exclusion on Linux is not verified.
- No complete engine, admission, child-runner, ledger or UI parity claim follows from this test task.

## T004 acceptance matrix inventory

- Status: **PASS — documentation/static inventory only**; all runtime capability and contract rows remain `PENDING`.
- Validation observed `2026-10-31T16:44:58.2885007+01:00` → `2026-10-31T16:44:58.4439457+01:00`; process elapsed **0.155445 s**, exit 0.
- The inline validator found **74** matrix rows; all IDs exactly matched discovery A01–F13; all 74 were `PENDING`. G4 SIM exceptions are in a separate disposition register. Helper, entrypoint, compose, filesystem, platform, and LM/LB/HM obligations are listed without any runtime pass inference.

## T005 retired-assertion inventory

- Status: **PASS — inventory/static AST count only**; no assertion, test, TUI module, or dependency was removed.
- Same validator window as T004 above; process elapsed **0.155445 s**, exit 0.
- The AST-to-Markdown validator matched **48 TUI tests / 385 direct `assert` nodes** and **28 external TUI-importing tests / 179 direct `assert` nodes**, total **76 tests / 564 direct `assert` nodes**. `pytest.raises` and mock/helper checks are not included in the AST count.
- Source/test SHA-256 over 13 test files: `c6ab8b3dbee6bcf1ed0c2de8ee455b561d77c1dacf7ea1d4d89fc61a900a1f89`.
- External coverage includes the 20 `hedge_fund/test_run.py` tests, the LLM client replay test, and seven fake Saxo tests. Web tests that reach `tui.keys` through `web.services` are listed separately as import-closure tests; their web assertions stay in place and must pass without importing `hedge_fund.tui`.

## T008 neutral report/default test design

| Field | Evidence |
|---|---|
| Status | **PASS — test-design/red-gate only.** Neutral helper implementations and acceptance remain **PENDING** under T013. |
| Base revision | `5860036d6a247d5858b5a34204bda3cb4c82816b` |
| Test identity | SHA-256 over sorted relative paths, NUL separators and full bytes: `e57d0e072afb91e5fdc18a2bc66d737c96c79f62555c98fc321af8e7f6bacaa0`. |
| Files | `hedge_fund/reporting/__init__.py`, `hedge_fund/reporting/test_console.py`, `hedge_fund/runtime/test_defaults.py`. |
| Artifact | Source test files; no package, wheel, container or production artifact. |
| Environment | Windows 11 Enterprise build `26200`; NTFS worktree; Python `3.13.7`; Poetry `2.5.1`; locked dev environment created under checkout `outputs/spec005-poetry-envs`, cache/home under checkout `outputs`; project `.venv` and real user data roots unused. |
| Isolation | `HOME`/`USERPROFILE` point to marked checkout-owned `outputs/spec005-tool-home`; `PYTHON_DOTENV_DISABLED=1`; provider, model, credential, root and proxy variables cleared before test invocation. Tests use synthetic records and do not call providers, brokers or network. |
| Scenario | Existing TUI report/scorecard and schedule assertions run before additions; neutral tests pin cost formatting, scorecard header/row ordering, signed/fractional precision, fixed `SessionRecord.code_version`, backtest window/progress defaults and minute schedule labels. Test-only child probes assert neutral imports do not load TUI/Textual. |
| Provenance | Direct Poetry/pytest/style commands in this worktree; execution owner python-dev. No inherited PR output or user report used. |

### Measurements

- Baseline command `python -m poetry run pytest hedge_fund/tui/test_report.py hedge_fund/tui/test_scorecard_view.py hedge_fund/tui/test_builder.py::test_builder_minute_helpers_are_pure hedge_fund/tui/test_backtest.py::test_backtest_daily_board_matches_final_metrics_and_uses_fill_dates -q`: **17 passed in 22.47 s**, exit 0. Baseline wall-clock timestamp was not captured.
- `2026-10-31T18:11:27.3747594+01:00` → `2026-10-31T18:11:30.2576631+01:00`: `python -m poetry run pytest hedge_fund/reporting/test_console.py hedge_fund/runtime/test_defaults.py -q`; **2 expected collection errors in 0.60 s**, exit 2. Both errors name only the planned, not-yet-created modules `hedge_fund.reporting.console` and `hedge_fund.runtime.defaults`.
- Black `--check`, isort `--check-only`, flake8 `--max-line-length=420`, and `git diff --check` passed on the two added test files. Plain flake8's default 79-character limit reports style-compatible long lines; project Black/flake8 line-length is 420.
- No runtime acceptance, report replacement pass, serialization change, TUI retirement, network call or Linux/ext4 result follows from this test-design task.

## T012 root-first bootstrap and handle-relative cache/config I/O

| Field | Evidence |
|---|---|
| Status | **PASS — implementation and synthetic Windows/NTFS tests.** Linux/ext4 acceptance is **BLOCKED** under T022. CLI test-process exit remains **INCONCLUSIVE**. |
| Base revision | `5860036d6a247d5858b5a34204bda3cb4c82816b` |
| Branch | `cgjedrem-vigilant-robot` |
| Source/test identity | SHA-256 over 31 sorted source/test paths, path/content NUL separators: `6be026d52b9431c1747e89269d43bf9fa88662978ab5a88b226c091a16493431`. |
| Files in identity | `hedge_fund/conftest.py`, `hedge_fund/data/cached.py`, `hedge_fund/data/test_cached.py`, `hedge_fund/features/breakpoints.py`, `hedge_fund/features/test_breakpoints.py`, `hedge_fund/fund/spec.py`, `hedge_fund/fund/test_spec.py`, `hedge_fund/llm/cache.py`, `hedge_fund/llm/test_client.py`, `hedge_fund/paths.py`, `hedge_fund/run.py`, `hedge_fund/runtime/__init__.py`, `hedge_fund/runtime/root.py`, `hedge_fund/runtime/test_root.py`, `hedge_fund/runtime/test_bootstrap.py`, `hedge_fund/test_paths.py`, `hedge_fund/test_run.py`, `hedge_fund/test_support/__init__.py`, `hedge_fund/test_support/network_guard.py`, `hedge_fund/test_support/sitecustomize.py`, `hedge_fund/web/__main__.py`, `hedge_fund/web/app.py`, `hedge_fund/web/conftest.py`, `hedge_fund/web/demo.py`, `hedge_fund/web/services.py`, `hedge_fund/web/test_actions.py`, `hedge_fund/web/test_app.py`, `hedge_fund/web/test_launcher.py`, `hedge_fund/web/test_main.py`, `hedge_fund/web/test_services.py`, `hedge_fund/web/test_settings.py`. |
| Artifact | Source-run; no wheel, container, or live production server. |
| Environment | Windows 11 Enterprise build `26200`; local NTFS worktree; Python `3.13.7`; Poetry `2.5.1`. |
| Isolation | Checkout-owned marked HOME/USERPROFILE and test roots under `outputs`; `PYTHON_DOTENV_DISABLED=1`; provider, model, credential, root and proxy variables cleared; fakes and non-loopback socket denial active. No provider, broker or external network calls. |
| Scenario | Explicit absolute root before engine imports; missing-root process exits 2; no implicit home path; exact-root opt-in non-secret dotenv; relative CLI mandate/output paths under root; handle-relative mandate/config/cache I/O; root identity revalidation and reparse/path denial. |
| Provenance | Direct commands in this worktree; execution owner python-dev. Test/process results below are current observations, not inherited PR counts. |

### Measurements

- `2026-10-31T19:05:22.6204820+01:00` → `2026-10-31T19:05:27.6668136+01:00`: `python -m poetry run python -c "import pytest; code=pytest.main(['hedge_fund/runtime/test_root.py','hedge_fund/runtime/test_bootstrap.py','hedge_fund/test_paths.py','hedge_fund/fund/test_spec.py','-p','no:cacheprovider','-q','--durations=10']); print('PYTEST_MAIN_RETURN='+str(code)); raise SystemExit(code)"`; **129 passed, 2 skipped in 2.67 s**, pytest return 0, process exit 0. Skips are POSIX-only file-mode tests.
- `2026-10-31T19:01:50.7821277+01:00` → `2026-10-31T19:02:00.7166422+01:00`: isolated `hedge_fund/web` suite through `pytest.main`; **80 passed in 5.58 s**, pytest return 0, process exit 0.
- `2026-10-31T18:57:05.5279211+01:00` → `2026-10-31T18:57:23.7218264+01:00`: `python -m poetry run pytest hedge_fund/data/test_cached.py hedge_fund/features/test_breakpoints.py hedge_fund/llm/test_client.py -q`; **163 passed in 15.21 s**, process exit 0. CLI result-file assertions read explicit UTF-8.
- `2026-10-31T19:02:06.6329472+01:00`: `hedge_fund/test_run.py` produced **31 passed in 3.84 s** and `pytest.main` returned `0`; the enclosing tool process returned `1` before its end marker. Assertion results passed; process-level completion is **INCONCLUSIVE**. This matches the previously observed Windows exit anomaly; no pytest/code repair is justified by this output.
- `2026-10-31T19:05:41.7676420+01:00` → `2026-10-31T19:05:51.2163220+01:00`: changed-scope isort and flake8 (`--max-line-length=420 --extend-ignore=E203`) passed; `git diff --check` passed. Black reports only `hedge_fund/data/cached.py`, `hedge_fund/llm/test_client.py` and `hedge_fund/test_run.py`; each file also fails `black --check` at the base revision. Black diff touches pre-existing formatting blocks, not T012 additions. No broad reformat was applied.

### Limits

- Windows/NTFS handle-relative reads, writes, metadata and identity revalidation were exercised with synthetic roots. No real user root or protected deployment was accessed.
- Linux/ext4 operations were not run. `_posix_filesystem_identity` identifies ext4 but currently reports `cloud_synced=False` without a generic ext4 cloud-sync detector. That value is not proof that an ext4 directory is unsynced; resolve or fail closed before Linux acceptance. Required native evidence remains blocked.
- No shared cross-process writer admission, lifecycle ownership, private credential ACL, network policy or TUI retirement is implemented by T012.

## T013 neutral report/default/credential helper extraction

| Field | Evidence |
|---|---|
| Status | **PASS — focused helper, import-closure and TUI-compatibility tests on Windows/NTFS.** This is not credential-capture/ACL or TUI-retirement acceptance. |
| Base revision | `5860036d6a247d5858b5a34204bda3cb4c82816b` |
| Branch | `cgjedrem-vigilant-robot` |
| Source/test identity | SHA-256 over 24 sorted T013 source/test paths with path/content NUL separators: `721115bca1ff70d9e5649191535e2ac9d81cfd6632bc02ad8cf9d1944c6e4f94`. |
| Artifact | Source-run; no package, wheel, installed TUI-free artifact or production server. |
| Environment | Windows 11 Enterprise build `26200`; local NTFS `C:`; Python `3.13.7`; Poetry `2.5.1`; Python from cached `aihf-jeXvH3Gy-py3.13` environment. |
| Isolation | Test HOME/USERPROFILE/TEMP under checkout `outputs`; `PYTHON_DOTENV_DISABLED=1`; credential/provider/config variables cleared before pytest; co-located harness clears provider registry variables and denies non-loopback sockets. Synthetic fixtures/fakes only. |
| Scenario | Rich report/scorecard parity, signed/fractional formatting, defaults/schedule labels, import closure without TUI/Textual, headless CLI/web/check_stock/LLM imports, TUI compatibility wrappers, credential save/mask/missing-key behavior. No live provider, paid call, protected root, real runner or port `8765`. |
| Provenance | Direct test/style commands in this worktree. No historical count or user report treated as current evidence. |

### Measurements

- `2026-10-31T19:33:19.4786662+01:00` → `2026-10-31T19:33:37.2514938+01:00`: `pytest hedge_fund/reporting/test_console.py hedge_fund/runtime/test_defaults.py hedge_fund/runtime/test_credentials.py hedge_fund/llm/test_client.py -p no:cacheprovider -q --durations=10`; **168 passed in 15.39 s**, process exit 0.
- `2026-10-31T19:33:44.5785294+01:00` → `2026-10-31T19:34:09.5394355+01:00`: `pytest hedge_fund/tui/test_keys.py hedge_fund/tui/test_report.py hedge_fund/tui/test_scorecard_view.py hedge_fund/tui/test_builder.py hedge_fund/tui/test_builder_broker.py -p no:cacheprovider -q --durations=10`; **31 passed in 22.61 s**, process exit 0.
- `2026-10-31T19:34:15.6192614+01:00` → `2026-10-31T19:34:20.0702157+01:00`: `pytest hedge_fund/tui/test_paper.py -k session_report -p no:cacheprovider -q --durations=10`; **8 passed, 20 deselected in 2.20 s**, process exit 0. The separately intended backtest node was not collected by that invocation; it was rerun explicitly below.
- `2026-10-31T19:34:29.4353500+01:00` → `2026-10-31T19:34:32.4661076+01:00`: `pytest hedge_fund/tui/test_backtest.py::test_backtest_daily_board_matches_final_metrics_and_uses_fill_dates -p no:cacheprovider -q --durations=10`; **2 passed in 0.78 s**, process exit 0.
- `2026-10-31T19:34:45.4291443+01:00` → `2026-10-31T19:34:50.8513461+01:00`: initial `tui/test_home.py` run yielded **3 failed, 6 passed in 3.18 s**. One assertion treated Windows `stat.S_IMODE` as NTFS ACL proof (`0666`, not POSIX `0600`); two dotenv-precedence cases expected file loading while required `PYTHON_DOTENV_DISABLED=1` disabled `load_dotenv`. Tests now assert the requested atomic-write mode and use a fake loader restricted to synthetic fixture paths.
- `2026-10-31T19:39:05.5987382+01:00` → `2026-10-31T19:39:11.0868609+01:00`: final isolated `pytest hedge_fund/tui/test_home.py -p no:cacheprovider -q`; **9 passed in 2.74 s**, process exit 0.
- `2026-10-31T19:36:42.5801381+01:00`: `pytest hedge_fund/test_run.py -p no:cacheprovider -q --durations=10` printed **31 passed in 3.63 s**, but the PowerShell session returned **1** and did not emit its scripted end marker. Assertion output is green; process-boundary completion is **INCONCLUSIVE**, not PASS. End timestamp was not observed. Reproduce against the exact pre-feature revision under T129 before classifying it as baseline.
- `2026-10-31T19:40:11.0426221+01:00` → `2026-10-31T19:40:12.3958645+01:00`: flake8 over all T013 files reported only `check_stock.py` E402×3, E306 and W292. `HEAD:check_stock.py` already has E402×4 and E306; both base/current byte streams lack a final newline. The removed TUI import reduced E402 count; no new finding was introduced.
- `2026-10-31T19:41:14.7189277+01:00` → `2026-10-31T19:41:16.8562081+01:00`: all T013 paths passed isort; selected new/clean scope passed Black (16 files), flake8 at 420 (`E203` ignored) and `git diff --check`. Black `--check` still reports inherited formatting in `check_stock.py`, `tui/shared.py`, `tui/backtest.py`, `tui/report.py`, `llm/test_client.py` and `test_run.py`; direct HEAD-blob checks confirmed the first four, and existing evidence records the latter two. No broad reformat was applied.

### Limits

- `runtime.credentials.save_credential` remains the current `.env` compatibility writer; it is not the versioned private credential store/frozen capture required by T016/T050. Windows mode bits do not prove NTFS ACL privacy; T059 remains open.
- `tui.keys.apply_credentials()` still loads CWD and configured-root dotenv files. Exact-root-only settings and child-environment isolation remain pending T016. `check_stock.py` now requires process-exported provider credentials; it does not hydrate persisted credentials.
- T009–T011 test-design tasks are complete; T014/T016/T017 source and synthetic-unit implementations exist. All-writer integration, owned-process lifecycle, private credential storage, endpoint-bound dispatch, full web parity and retirement remain open. Linux/ext4 remains blocked; no support or retirement claim follows from T013.

## T009 shared admission test design

| Field | Evidence |
|---|---|
| Status | **PASS — expected-red test design only.** No admission or OS-lock behavior was executed. |
| Base revision | `5860036d6a247d5858b5a34204bda3cb4c82816b` |
| Branch | `cgjedrem-vigilant-robot` |
| Source/test identity | SHA-256 over sorted paths with NUL-delimited paths and full bytes: `ccf728a8b4f3b1f6b8857f148d030ce3124af64004dcc9fc82187db34d2adc0f`. |
| Files in identity | `hedge_fund/runtime/root.py`, `hedge_fund/runtime/test_admission.py`, `hedge_fund/runtime/test_root.py`. |
| Artifact | Source test file only; no package, wheel, installed artifact or production server. |
| Environment | Windows 11 Enterprise build `26200`; local NTFS worktree; Python `3.13.7`; Poetry `2.5.1`; cached `aihf-jeXvH3Gy-py3.13` environment. |
| Isolation | Test HOME/USERPROFILE/TEMP/TMP under checkout `outputs`; `PYTHON_DOTENV_DISABLED=1`; credential/provider/root/proxy variables cleared; test harness denies non-loopback sockets and owns spawned Python children. |
| Scenario | Synthetic root only. Tests specify sorted registry/deployment locks, cross-process registry/deployment/control contention, per-fund independence, runner reservation versus manual admission, control access during runner reservation, kernel release after owned-process exit, unknown/legacy owner denial before lock-state creation, and bounded control-lane contention. |
| Provenance | Direct pytest/style commands in this worktree; execution owner python-dev. The collection error is the planned red result, not a behavior pass. |

### Measurements

- Baseline before test addition: `hedge_fund/runtime/test_root.py`, `hedge_fund/runtime/test_bootstrap.py`, `hedge_fund/test_paths.py`; **49 passed, 2 skipped in 3.19 s**, process exit 0, `2026-10-31T19:43:56.4159176+01:00` → `2026-10-31T19:44:02.3644676+01:00`.
- Final expected-red command: `python -m pytest hedge_fund/runtime/test_admission.py -p no:cacheprovider -q --tb=short`; **1 collection error in 0.23 s**, process exit **2**, `2026-10-31T19:51:33.5089364+01:00` → `2026-10-31T19:51:35.6129435+01:00`. Exact error: `ModuleNotFoundError: No module named 'hedge_fund.runtime.admission'`.
- Final test-scope Black `--check`, isort `--check-only`, and flake8 (`--max-line-length=420 --extend-ignore=E203`) passed; `2026-10-31T19:51:33.4674346+01:00` → `2026-10-31T19:51:34.4101699+01:00`.

### Failed attempts and repairs

- Initial style check found Black formatting differences and flake8 F541 in the test helper. The formatter diff identified wrapped signatures and the non-interpolated f-string; both were corrected.
- Expanded cross-process registry/deployment cases then produced another Black-only formatting finding. The exact formatter diff was applied; final style checks passed.
- No assertion ran during expected-red collection. T014 implementation and green cross-process observations are still required.

### Limits

- Expected-red collection proves only that the new admission module is absent at this revision. It does not prove OS lock behavior, ownership fencing, Linux/ext4 primitives, emergency-control latency or production integration.
- No live root, protected deployment, runner, provider, broker or external network was accessed.

## T014 OS-backed admission lanes

| Field | Evidence |
|---|---|
| Status | **PASS — synthetic Windows/NTFS OS-lock behavior and root-relative handle tests.** Linux/ext4 native acceptance and writer integration remain **BLOCKED/PENDING** under T022/T021. |
| Base revision | `5860036d6a247d5858b5a34204bda3cb4c82816b` |
| Branch | `cgjedrem-vigilant-robot` |
| Source/test identity | SHA-256 over four sorted source/test paths with NUL-delimited paths and full bytes: `1f82dc514edfe9bd6e8d3a70e5d4973ab57c35b685de1616b4f069a629e1ad68`. |
| Files in identity | `hedge_fund/runtime/admission.py`, `hedge_fund/runtime/root.py`, `hedge_fund/runtime/test_admission.py`, `hedge_fund/runtime/test_root.py`. |
| Artifact | Source-run; no wheel, installed artifact, container or production server. |
| Environment | Windows 11 Enterprise build `26200`; local NTFS `C:`; Python `3.13.7`; Poetry `2.5.1`; cached `aihf-jeXvH3Gy-py3.13` environment. |
| Isolation | Test HOME/USERPROFILE/TEMP/TMP under checkout `outputs`; `PYTHON_DOTENV_DISABLED=1`; credential/provider/root/proxy variables cleared; test harness denies non-loopback sockets and reaps exact owned Python children. All roots and lock files synthetic. |
| Scenario | Real Windows `LockFileEx` and owned Python processes test registry/deployment/control contention, independent funds, runner reservation versus manual-between-sessions, control access during runner reservation, process-exit lock release, timeout bounds, invalid-input denial, canonical alias denial and unknown/legacy ownership denial. Root lock-file opens use relative no-follow handles. |
| Provenance | Direct pytest and style commands in this worktree; execution owner python-dev. No inherited count, provider call or user report treated as current evidence. |

### Measurements

- Root/bootstrap/path regressions after adding the root-relative lock handle: **50 passed, 2 skipped in 2.63 s**, process exit 0, `2026-10-31T19:50:48.7898095+01:00` → `2026-10-31T19:50:53.9626019+01:00`.
- Final command: `python -m pytest hedge_fund/runtime/test_admission.py hedge_fund/runtime/test_root.py hedge_fund/runtime/test_bootstrap.py hedge_fund/test_paths.py -p no:cacheprovider -q --durations=20`; **70 passed, 2 skipped in 4.82 s**, process exit 0, `2026-10-31T19:55:09.5304814+01:00` → `2026-10-31T19:55:16.9480670+01:00`.
- Changed-scope Black `--check`, isort `--check-only`, flake8 (`--max-line-length=420 --extend-ignore=E203`) and `git diff --check` passed, `2026-10-31T19:55:09.4770235+01:00` → `2026-10-31T19:55:11.6896605+01:00`.

### Failed attempts and repairs

- Initial root-helper patch split `_windows_read_relative()` and caused collection failure: **SyntaxError at `root.py:986`**, pytest exit 4, `2026-10-31T19:50:23.7552656+01:00` → `2026-10-31T19:50:25.1367271+01:00`. The function boundary was inspected and restored; root regressions passed afterward.
- First admission run: **7 passed, 1 failed in 1.90 s**, process exit 1, `2026-10-31T19:52:57.5980464+01:00` → `2026-10-31T19:53:02.1031358+01:00`. The owned child passed `timeout=1.0` to a control lane capped at `0.5`, exited before readiness, and did not exercise the lock. The test helper now uses `0.1`; subsequent admission run passed.
- Initial Black/isort checks found formatting and import-order differences. Exact formatter/import diffs were applied; final style checks passed.

### Limits

- Windows/NTFS only. Linux/ext4 `fcntl.flock`, filesystem identity, lock crash-release, namespace/incarnation and atomic-replacement acceptance were not run.
- `OwnershipState.VERIFIED` is a trusted internal bootstrap input; constructor default is `UNKNOWN`. T015 must provide verified offline handover before any production writer supplies verified ownership.
- No CLI/web/runner writer is integrated here. Durable journals, Halt marker, process ownership, handover recovery, ACL proof and production mutation gating remain pending.
- Bounded control covers lock wait only; it is not emergency-marker publication or end-to-end Halt latency evidence.

## T010 capture/configuration/provider-policy test design

| Field | Evidence |
|---|---|
| Status | **PASS — expected-red test design only.** No capture/configuration or provider-policy behavior ran. |
| Base revision | `5860036d6a247d5858b5a34204bda3cb4c82816b` |
| Branch | `cgjedrem-vigilant-robot` |
| Test-source identity | SHA-256 over sorted test paths, NUL-delimited paths and full bytes: `82a7eff59ba017f33cb2c4cd45bf086b5d6317da2094dc8e7108f76841177d2d`. |
| Source/harness snapshot | SHA-256 over sorted relevant source/test paths and explicit absent-module markers: `6da3cecf023235166a53e6282f0c924ced27ea09a012bd82c2f87c4f671f30d9`. |
| Files | `hedge_fund/conftest.py`, `hedge_fund/runtime/__init__.py`, `hedge_fund/runtime/root.py`, `hedge_fund/runtime/test_capture.py`, `hedge_fund/runtime/test_policy.py`, `hedge_fund/test_support/network_guard.py`, `hedge_fund/test_support/sitecustomize.py`; `hedge_fund/runtime/capture.py` and `hedge_fund/runtime/policy.py` were absent. |
| Artifact | Source test files only; no package, wheel, installed artifact or provider client. |
| Environment | Windows 11 Enterprise build `26200`; local NTFS worktree; Python `3.13.7`; Poetry `2.5.1`. |
| Isolation | Test HOME/USERPROFILE/TEMP/TMP in a newly created temporary home; `PYTHON_DOTENV_DISABLED=1`; credential/provider/root/proxy references removed before pytest; harness creates a synthetic checkout root and denies non-loopback sockets. |
| Scenario | Synthetic `RootContext`; tests specify launch/environment/persisted/default precedence, capability-field rejection, immutable copied credential-version references, public redaction, cloud-labelled Ollama classification, paid manual one-shot binding, scheduled cloud denial and finite free-data authorization. No network client is constructed. |
| Provenance | Direct pytest/style commands in this worktree; execution owner python-dev. Test collection failure is the planned red result, not a behavior pass. |

### Measurements

- Final expected-red command: `python -m pytest hedge_fund/runtime/test_capture.py hedge_fund/runtime/test_policy.py -p no:cacheprovider -q --tb=short`; `2026-10-31T20:02:41.0789604+01:00` to `2026-10-31T20:02:42.0065641+01:00`; **2 collection errors in 0.15 s**, process elapsed **0.9276037 s**, exit **2**. Exact errors: `ModuleNotFoundError: No module named 'hedge_fund.runtime.capture'` and `ModuleNotFoundError: No module named 'hedge_fund.runtime.policy'`. No assertion ran.
- Final changed-scope Black `--check`, isort `--check-only`, flake8 (`--max-line-length=420 --extend-ignore=E203`) and `git diff --check` passed; `2026-10-31T20:03:17.9283509+01:00` to `2026-10-31T20:03:25.2900388+01:00`, process elapsed **7.3616879 s**.

### Failed attempts and repairs

- Initial global-Python style commands were blocked because Black/isort/flake8 were absent. `python -m poetry install --with dev --no-interaction --no-ansi` installed the locked development dependencies; Poetry-environment style checks then passed.
- A Poetry-environment pytest invocation failed before collection with `No module named pytest`; no assertion ran. Final expected-red evidence used the already-available global Python 3.13 pytest process under the same isolated HOME/USERPROFILE/TEMP, dotenv-disabled, credential-cleared test boundary.
- First style run found import-order differences and one unused `FrozenCapture` import. The exact isort diff identified the import order; the unused import was removed, then all final style checks passed.

### Limits

- Collection proves only that the two implementation modules are absent at this source snapshot. It does not prove settings resolution, capture privacy, credential ACLs, child environment filtering, provider classification, dispatch budgets or scheduled-runner safety.
- No paid provider/LLM calls, secret fixtures, real data roots, protected runners, live endpoints or port `8765` were accessed.

## T016–T017 settings, capture and provider-policy implementation

| Field | Evidence |
|---|---|
| Status | **PASS — source/unit behavior on synthetic Windows/NTFS only.** No live provider dispatch, credential store, ACL, child-runner lifecycle or production wiring. |
| Base revision | `5860036d6a247d5858b5a34204bda3cb4c82816b` |
| Branch | `cgjedrem-vigilant-robot` |
| Test-source identity | SHA-256 over sorted test paths, NUL-delimited paths and full bytes: `b153e7edf0af5a331fec3de63fa1df0ddfe6866d1db185ffc628e549ddfe724d`. |
| Source/harness snapshot | SHA-256 over sorted relative paths, NUL separators and full bytes: `20cd2c88a493c80be68716c21d12f3a8b6e4d2f73652f7e8d8b60c8a816319c7`. |
| Files in snapshot | `hedge_fund/conftest.py`, `hedge_fund/runtime/__init__.py`, `hedge_fund/runtime/root.py`, `hedge_fund/runtime/configuration.py`, `hedge_fund/runtime/capture.py`, `hedge_fund/runtime/policy.py`, `hedge_fund/runtime/test_capture.py`, `hedge_fund/runtime/test_policy.py`, `hedge_fund/test_support/network_guard.py`, `hedge_fund/test_support/sitecustomize.py`. |
| Artifact | Direct source tests; no wheel, package install, browser artifact or production build. |
| Environment | Windows 11 Enterprise build `26200`; local NTFS worktree; global Python `3.13.7`; pytest `9.1.1`; Poetry `2.5.1`. |
| Isolation | Unique temporary HOME/USERPROFILE/TEMP/TMP; `PYTHON_DOTENV_DISABLED=1`; provider/key/root/proxy references removed; synthetic `RootContext`; test harness denies non-loopback sockets and owns/reaps its import-check child. |
| Scenario | Settings precedence and free data default; provider/model catalog parity and provider-client-free module import; capability-field rejection; settings CAS; immutable digest-checked capture and scoped version handles; root/secret-free child env and exact `--root`; paid one-shot binding, reservation-before-dispatch, unknown-cost/retry denial, local/cloud classification, finite runner sessions/calls/resources and scheduled paid denial. No provider client was constructed. |
| Provenance | Direct pytest/style commands in this worktree; execution owner python-dev. T010 expected-red snapshot remains separately recorded above. Additional hardening cases were added after implementation; no expected-red claim is made for those additions. |

### Measurements

- Final T016/T017 targeted tests: `python -m pytest hedge_fund/runtime/test_capture.py hedge_fund/runtime/test_policy.py -p no:cacheprovider -q --tb=short`; `2026-10-31T20:21:52.7287923+01:00` to `2026-10-31T20:21:54.0932525+01:00`; **21 passed in 0.47 s**, exit 0.
- Related root/admission/capture/policy slice: `python -m pytest hedge_fund/runtime/test_root.py hedge_fund/runtime/test_admission.py hedge_fund/runtime/test_capture.py hedge_fund/runtime/test_policy.py -p no:cacheprovider -q --tb=short`; `2026-10-31T20:23:23.9765394+01:00` to `2026-10-31T20:23:27.3066023+01:00`; **74 passed in 2.29 s**, exit 0.
- Changed-scope Black `--check --line-length 420`, isort `--check-only --profile black --line-length 420`, flake8 `--max-line-length=420 --extend-ignore=E203`, and `git diff --check`: all exit 0; `2026-10-31T20:22:46.2155686+01:00` to `2026-10-31T20:22:51.7915507+01:00`.
- Broader `python -m pytest hedge_fund/runtime -p no:cacheprovider -q --tb=short`: **BLOCKED** at collection, `2026-10-31T20:22:46.2629299+01:00` to `2026-10-31T20:22:48.0948705+01:00`, exit 2. `test_defaults.py` imports `hedge_fund.signals.base`, which requires unavailable `pandas`; no runtime-directory assertions ran. Poetry's selected interpreter also lacked `pandas` and `pytest`; no project dependency or source change was made.

### Limits

- `CredentialHandle` contains root/provider/version identity only. No credential material is retained, read or persisted; versioned credential storage and active-capture retention remain T050.
- `FrozenCapture.private_bytes()` serializes validated metadata and version handles only. Durable sidecars/admission remain T018; Windows ACL and Linux/ext4 evidence remain blocked under T022/T059.
- Child environment and argv helpers were unit-tested; no child engine/runner lifecycle was launched. Provider-policy reservations were tested before any fake dispatch boundary; actual endpoint-bound dispatch remains T051 and writer integration T021.
- The runtime-directory suite is blocked by missing test dependencies. No claim follows for Linux/ext4, wheel/no-Node compatibility, browser behavior, production startup, mutation guard or TUI retirement.
- No paid provider/LLM calls, secret fixtures, live endpoints, real data roots, protected runners or port `8765` were accessed.

## T011 durable operation tests

| Field | Evidence |
|---|---|
| Status | **PASS — test design plus implementation-backed durable-store regressions on synthetic Windows/NTFS.** One earlier sidecar-write failure remains **INCONCLUSIVE** as an intermittent anomaly; no repair was made. T018 production integration remains partial. |
| Base revision | `5860036d6a247d5858b5a34204bda3cb4c82816b` |
| Branch | `cgjedrem-vigilant-robot` |
| Test-source identity | SHA-256 over sorted test paths, NUL-delimited paths and full bytes: `74ae77d52be6c447b7eb2ebd943d85fa0ef775fe1ae73a5aa7a1c9cfc6cb6b8e`. |
| Source/harness snapshot | SHA-256 over sorted paths, NUL separators and file bytes or explicit `ABSENT` marker: `6c794f5a5fb72ebda0a2d933e5ec98311b4475f53a7f6bc1e8e8fef20b175e5a`. |
| Files in snapshot | `hedge_fund/conftest.py`, `hedge_fund/runtime/__init__.py`, `hedge_fund/runtime/root.py`, `hedge_fund/runtime/admission.py`, `hedge_fund/runtime/configuration.py`, `hedge_fund/runtime/capture.py`, `hedge_fund/runtime/test_operations.py`, absent `hedge_fund/runtime/operations.py`, `hedge_fund/test_support/network_guard.py`, `hedge_fund/test_support/sitecustomize.py`. |
| Final source/test snapshot | SHA-256 over 64 changed Python/frontend source and test paths, sorted path/content/NUL framing: `774c93db77b948fabf44216f4fe911558a109ab771b29124b28a38c8b566adf4`; 795,260 bytes. Base `5860036d6a247d5858b5a34204bda3cb4c82816b`. |
| Artifact | `hedge_fund/runtime/operations.py`, `hedge_fund/runtime/test_operations.py`, `hedge_fund/runtime/admission.py`, `hedge_fund/runtime/test_admission.py`, `hedge_fund/web/jobs.py`, `hedge_fund/web/test_jobs.py`; installed-wheel evidence below covers a prior source snapshot only. |
| Environment | Windows 11 Enterprise build `26200`; local NTFS worktree; expected-red run used Python `3.13.7`/pytest `9.1.1`; follow-up used isolated Python `3.13.7`/pytest `7.4.4` venv. |
| Isolation | Marked test root under checkout `outputs`; HOME/USERPROFILE/TEMP/TMP/APPDATA/XDG isolated; `PYTHON_DOTENV_DISABLED=1`; provider/key/root/proxy references removed; synthetic account name; synthetic `RootContext`; test harness denies non-loopback sockets. |
| Scenario | Canonical payload digest and exact ordered due-set; operator-session binding and expiry; single-use token with same-request idempotency; changed-payload conflict; head/due-set revalidation before a fake worker callback; durable accepted record before callback; restart interruption and stale-fence effect denial. No effect is inferred from a missing record alone. |
| Provenance | Direct expected-red, targeted and runtime/web pytest runs in this worktree; execution owner python-dev. Fake callbacks only; no provider dispatch or production worker. |

### Measurements

- Expected-red command: `python -m pytest hedge_fund/runtime/test_operations.py -p no:cacheprovider -q --tb=short`; `2026-10-31T20:27:15.5448772+01:00` to `2026-10-31T20:27:16.5196076+01:00`; **1 collection error in 0.16 s**, exit 2. Exact error: `ModuleNotFoundError: No module named 'hedge_fund.runtime.operations'`; no assertion ran.
- Black `--check --line-length 420`, isort `--check-only --profile black --line-length 420`, flake8 `--max-line-length=420 --extend-ignore=E203` and `git diff --check` passed; `2026-10-31T20:27:15.4704881+01:00` to `2026-10-31T20:27:20.0685294+01:00`.
- First isolated suite wrapper attempt: `2026-10-31T21:26:31.421460+01:00` to `2026-10-31T21:26:39.049197+01:00`; **54 passed, 159 setup errors in 5.44 s**, exit 1. `child_test_environment()` omitted an OS username variable; pytest temporary-directory setup raised `OSError: No username set in the environment`. The test root was cleaned. No source was changed; the rerun set synthetic `USERNAME`/`USER`/`LOGNAME`/`LNAME`.
- Runtime/web attempt: `python -m pytest -q -p no:cacheprovider hedge_fund/runtime hedge_fund/web --tb=short`; `2026-10-31T21:27:29.5734500+01:00` to `2026-10-31T21:28:36.3136993+01:00`; **212 passed, 1 failed in 57.01 s**, exit 1. `test_cancel_before_worker_claim_can_finish_without_starting_a_worker` raised `OperationError: operation storage write failed` while replacing its preview sidecar. The wrapped OS exception was not retained.
- Discriminating follow-up: the failing test alone passed **1/1 in 1.51 s** (`21:29:01.3289540+01:00` → `21:29:05.8338271+01:00`). Operation/admission/job regressions passed **65 tests in 42.46 s** (`21:29:17.4839577+01:00` → `21:30:09.0978895+01:00`), exit 0.
- Final runtime/web rerun, unchanged source: `2026-10-31T21:30:17.2427301+01:00` → `2026-10-31T21:31:22.5947968+01:00`; **213 passed in 54.25 s**, pytest/process exit 0; marked root cleanup returned true.

### Limits

- One earlier isolated write failure remains unexplained. Focused and broad reruns passed without a code repair; do not infer the underlying write failure was fixed.
- `private_storage_verified=True` is synthetic test injection, not NTFS ACL or production ownership proof. Operation jobs use an in-process thread registry and are not wired into `DeskService` or API routes.
- No owned child lifecycle, handover, live provider, paid call, secret, real root, protected runner or port `8765` was accessed. Linux/ext4, Windows ACL, production mutation, full-suite, and TUI-retirement acceptance remain open.

## Installed wheel / no-Node smoke

| Field | Evidence |
|---|---|
| Status | **PASS — installed wheel and FastAPI in-process SPA/asset serving on synthetic Windows/NTFS.** Not a live-server, lifecycle, sdist, Linux or retirement pass. |
| Source revision | Base `5860036d6a247d5858b5a34204bda3cb4c82816b` plus source/test snapshot `12383e7c521438dcc7fb98305cb3ef3d9cab744a5794565d6fc6c1ba7db7955f` (64 changed source/test paths; 795,476 bytes). |
| Artifact | `aihf-2.6.1-py3-none-any.whl`; SHA-256 `dc1f1e86dd07b9dfce161201cdd2663176ccd68393f8988989cdc0d4e6829920`; 593,850 bytes. Built from the working source snapshot, installed to a marked checkout-owned target, then deleted during guarded cleanup. |
| Time | `2026-10-31T21:32:27.6344736+01:00` → `2026-10-31T21:32:53.8713471+01:00`; elapsed **26.237 s**. |
| Environment | Windows 11 Enterprise build `26200`; NTFS; build tools `build 1.6.1` and `poetry-core 2.5.0`; runtime venv Python `3.13.7`; system Node path filtered from smoke process. |
| Isolation | Marked `outputs/spec005-test-wheel-*` root; HOME/USERPROFILE/TEMP/TMP/APPDATA/XDG isolated; dotenv disabled; credential/provider/proxy references cleared; `PIP_NO_INDEX=1`; wheel build `--no-isolation`; runtime `sitecustomize` enforced socket guard. |
| Scenario | Installed wheel import resolved inside the target. `TestClient` requested `/` and each packaged JS/CSS asset with `Host: 127.0.0.1`; app had writes/network disabled and synthetic demo root. `shutil.which("node")` returned `None`. |
| Provenance | `python -m build --wheel --no-isolation`; isolated venv `pip --isolated install --no-index --no-deps --target`; direct Python `TestClient` smoke; execution owner python-dev. **2 packaged assets served; test root cleanup returned true.** |

### Limits

- The Poetry CLI module was absent from the acceptance venv. The wheel used locally installed `build`/`poetry-core` with `--no-isolation`; no package/index installation occurred.
- TestClient exercised ASGI in-process, not a bound production server. The acceptance venv supplied runtime dependencies; this was not a dependency-free environment.
- No sdist, Docker image/compose, Linux/ext4, child lifecycle, credentials, provider calls, protected root, paid service or port `8765` was used. T080/T087 and retirement remain open.

## Final candidate verification continuation

| Field | Evidence |
|---|---|
| Status | **PARTIAL PASS.** Final frontend and runtime/web synthetic checks passed. Full migration, native-platform acceptance and final wheel rebuild remain blocked/inconclusive. |
| Base revision | `5860036d6a247d5858b5a34204bda3cb4c82816b` on `cgjedrem-vigilant-robot`. |
| Candidate source/test identity | SHA-256 `774c93db77b948fabf44216f4fe911558a109ab771b29124b28a38c8b566adf4`; 64 Python/frontend source and test files; 795,260 bytes. Computed from changed source/test paths and contents; excludes docs, screenshots, and unrelated ignored/untracked `pypa/`. |
| Environment | Windows 11 Enterprise build `26200`; local NTFS worktree; Python `3.13.7`; Node `22.13.1`; Vitest `4.1.12`; Vite `6.4.5`; Playwright `1.64.1`; Edge `156.0.4314.50`. |
| Isolation | Acceptance venv and checkout-owned HOME/USERPROFILE/TEMP roots; dotenv disabled; credential/provider/proxy references removed; fake provider/demo inputs; Python test socket guard denies non-loopback traffic. |
| Browser scenario | Owned root `outputs/spec005-test-e2e-25904-4eff9c1c`; loopback port `8876`; production Vite output served by the owned Python demo process; external browser requests denied. No server reuse. |
| Browser artifact | SHA-256 `58a6fb074175e08905a77a214741a92cef02c965317e35f279136e8629c7f434`; 3 files; 944,284 bytes. Same frontend bundle identity as the earlier T003 run. |
| Provenance | Direct commands in this worktree; execution owner python-dev. No provider dispatch, real account/root, paid service, protected runner, or port `8765` used. |

### Measurements

- `2026-10-31T21:47:54.9085379+01:00` → `2026-10-31T21:47:55.8103080+01:00`: from `frontend/`, `node --test scripts/run-owned.test.mjs`; **6 passed**, Node duration **639.333 ms**, process elapsed **0.902 s**, exit 0. Covered exact owned-child abort, no server reuse, fixed port/output, external-route guard, environment scrub and artifact fingerprint.
- `2026-10-31T21:47:54.9219658+01:00` → `2026-10-31T21:49:45.8721135+01:00`: from `frontend/`, `node e2e/run-owned.mjs`; TypeScript check passed; Vite transformed **2,307 modules**, built in **34.71 s**, emitted 3 files / **944,284 bytes**, artifact hash above. Playwright: **6 passed in 14.5 s**, process elapsed **110.950 s**, exit 0. Cases covered routes at desktop/narrow widths, canonical builder submission, reviewed backtest/cancel, dotted deep links, disabled decisions and job reload recovery. Vite emitted a non-fatal minified-chunk warning.
- Same browser run: **17 synthetic screenshots / 2,783,348 bytes** under `specs/005-web-engine-migration/screenshots/`. Root absent after cleanup; Uvicorn PID `53632` absent; an exclusive `127.0.0.1:8876` bind passed. No port `8765` probe or access.
- `2026-10-31T21:49:58.6883681+01:00` → `2026-10-31T21:51:18.4031213+01:00`: from `frontend/`, `node node_modules/vitest/vitest.mjs run src --reporter=verbose`; **2 files / 11 tests passed**, Vitest duration **76.75 s**, process elapsed **79.715 s**, exit 0. jsdom/Recharts zero-size chart warnings remain; tests pass.
- `2026-10-31T21:51:54.6062089+01:00` → `2026-10-31T21:52:59.9536169+01:00`: isolated acceptance Python `3.13.7`, `python -m pytest -q -p no:cacheprovider hedge_fund/runtime hedge_fund/web --tb=short`; **213 passed in 54.65 s**, process exit 0.
- `2026-10-31T21:53:11.2453049+01:00` → `2026-10-31T21:53:18.3533673+01:00`: isolated acceptance Python `3.13.7`, `python -m pytest hedge_fund/runtime/test_root.py hedge_fund/runtime/test_defaults.py hedge_fund/reporting/test_console.py hedge_fund/tui/test_keys.py hedge_fund/tui/test_home.py -p no:cacheprovider -q --tb=short`; **59 passed in 5.22 s**, process exit 0.
- `2026-10-31T21:56:31.0194510+01:00` → `2026-10-31T21:56:34.5877793+01:00`: changed-scope formatting after import-only cleanup: Black **49 files**, isort **47 files**, flake8 **55 files**, `git diff --check`; all passed. Differential review against `HEAD` confirms the remaining all-scope findings are inherited: Black's seven existing files and isort's nine existing files still fail their all-scope checks; `check_stock.py` has no new flake8 finding. No behavior changes in this formatting slice.

### Final artifact blocker and limits

- Final wheel rebuild is **BLOCKED**. `python -m build` was unavailable in the acceptance venv and system Python. Offline installation of `build==1.6.1` and `poetry-core==2.5.0` from the checkout cache failed; at `2026-10-31T21:45:52.1105983+01:00` → `2026-10-31T21:45:52.3334524+01:00`, the required `build` package was not cached. No package index/network was used. The failed synthetic root was cleaned.
- The installed-wheel PASS above is bound to earlier source/test identity `12383e7c521438dcc7fb98305cb3ef3d9cab744a5794565d6fc6c1ba7db7955f` (795,476 bytes). It does **not** validate candidate identity `774c93db77b948fabf44216f4fe911558a109ab771b29124b28a38c8b566adf4`.
- The prior unexplained sidecar-write failure remains **INCONCLUSIVE**; the final unchanged-source runtime/web rerun passed without repair.
- Full Python suite remains **INCONCLUSIVE**. Linux/ext4, NTFS ACL/private-storage proof, writer admission/handover, production operation API/DeskService wiring, owned child-runner lifecycle, live provider dispatch and TUI retirement remain open. Current web mutation code is not gated by the new durable operation protocol; keep explicit write/network/container flags off.
- Manual visual review previously found a large empty overview panel; browser assertions do not prove visual completeness. The final rerun refreshed synthetic screenshots but did not change that status.
- No preview service was left running. No real user root, protected runner, provider credential, paid call or external network destination was used.
