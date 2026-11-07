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

## Convergence — SIM denial and responsive Halt (partial)

| Field | Evidence |
|---|---|
| Status | **PARTIAL PASS.** Web SIM mutation/effect denials and bounded emergency Halt have focused synthetic coverage. This does not close T139 lifecycle/provisioning or T140 reconciliation/resume/redo, and does not establish runtime/platform acceptance. |
| Revision / dirty diff | Base `9694f619207e14fb5e55de1bef96deb79df7a360`; `git diff --binary` SHA-256 `bff9ec9c4e428ddfec05bb51b96d306f13239a8938696b1c3e41fb76ac9250cb`, **41,459 bytes**. |
| Environment | Windows 11 Enterprise build `26200`; NTFS; isolated test venv Python `3.13.7`; system timezone `W. Europe Standard Time` (UTC+01:00). |
| Isolation | Per-run synthetic HOME/USERPROFILE/TEMP roots; dotenv disabled; credential/provider/proxy environment references cleared; pytest plugin autoload disabled. Test providers were offline fakes. |
| Scenario | Web TestClient routes used synthetic demo roots. Valid paper previews were accepted for review, then the fixture deployment was changed to `saxo`; manual/runner accept, control, approval, preview, valuation, and deploy routes returned 403 before data calls, ledger writes, operation acceptance, deploy, or worker stop. Headless Saxo compatibility tests used test doubles. Halt regression held the fund-work mutex in one thread and observed the emergency halt complete and persist through the bounded control lane. |
| Provenance | Python source/tests only; no wheel, server, paid provider, network, real brokerage, protected root, owned child or process signal. Fake unit results are not runtime acceptance. |

### Measurements

- `2026-11-01T08:03:33.8590619+01:00` → `2026-11-01T08:03:42.2973613+01:00`: frontend `App.test.tsx`, **19 passed in 7.49 s**, exit 0. Non-fatal Recharts/jsdom chart-size warnings.
- `2026-11-01T08:05:51.2369289+01:00` → `2026-11-01T08:05:56.5174922+01:00`: valid-preview SIM manual/runner acceptance regression, **1 passed in 2.88 s**, exit 0.
- `2026-11-01T08:06:09.4642750+01:00` → `2026-11-01T08:06:11.0913676+01:00`: paper runner/deployed-broker Saxo selections, **8 passed, 15 deselected in 0.89 s**, exit 0.
- `2026-11-01T08:07:46.0781657+01:00` → `2026-11-01T08:07:50.2869936+01:00`: red Halt concurrency regression, **1 failed in 2.10 s**, exit 1; `completed.wait()` was false while another thread held the per-fund work lock.
- `2026-11-01T08:08:21.1530508+01:00` → `2026-11-01T08:09:54.7782174+01:00`: `python -m pytest hedge_fund/web/test_actions.py hedge_fund/web/test_paper_operations.py -p no:cacheprovider -q --tb=short`, **33 passed in 77.54 s**, process exit 0. Includes SIM effect-denial routes, accepted-preview denials, shared control-lane use, and Halt responsiveness/persisted-state assertions.
- Same final source slice: Black `--check --line-length=420` passed for `services.py` and `test_paper_operations.py`; `test_actions.py` has the same formatter finding on `HEAD` and contains no new Black diff in the added tests. Isort and flake8 passed on all three files; `git diff --check` passed.

### Limits

- Web SIM controls are denied; headless SIM compatibility remains fake-only. No account-binding provisioning/validation was exercised.
- Halt no longer waits for the in-process fund-work mutex; this does not prove cancellation of an already-in-flight model/data call or reconcile ambiguous external fills.
- `T139` and `T140` remain unchecked in `tasks.md` until all residual contract criteria and acceptance gates have evidence.

### Final artifact blocker and limits

- Final wheel rebuild is **BLOCKED**. `python -m build` was unavailable in the acceptance venv and system Python. Offline installation of `build==1.6.1` and `poetry-core==2.5.0` from the checkout cache failed; at `2026-10-31T21:45:52.1105983+01:00` → `2026-10-31T21:45:52.3334524+01:00`, the required `build` package was not cached. No package index/network was used. The failed synthetic root was cleaned.
- The installed-wheel PASS above is bound to earlier source/test identity `12383e7c521438dcc7fb98305cb3ef3d9cab744a5794565d6fc6c1ba7db7955f` (795,476 bytes). It does **not** validate candidate identity `774c93db77b948fabf44216f4fe911558a109ab771b29124b28a38c8b566adf4`.
- The prior unexplained sidecar-write failure remains **INCONCLUSIVE**; the final unchanged-source runtime/web rerun passed without repair.
- Full Python suite remains **INCONCLUSIVE**. Linux/ext4, NTFS ACL/private-storage proof, T021 all-writer integration/T015 handover, manual paper tick, owned child-runner lifecycle, live provider dispatch and TUI retirement remain open. Backtest operation API/DeskService wiring is exercised by fake-provider tests; this does not establish runner/manual-tick parity. General mandate/settings/credential/approval/halt/valuation writes do not use the durable operation protocol. The explicit write capability and root-owner lease do not prove legacy or out-of-band writers are excluded; keep write/network/container flags off against existing roots.
- Manual visual review previously found a large empty overview panel; browser assertions do not prove visual completeness. The final rerun refreshed synthetic screenshots but did not change that status.
- No preview service was left running. No real user root, protected runner, provider credential, paid call or external network destination was used.

## QA-rework continuation

| Field | Evidence |
|---|---|
| Status | **PARTIAL PASS.** Root-bound launchers, durable backtest operations, paper valuation and frontend flows are exercised with synthetic fixtures. This is not complete web-driver parity or production handover evidence. |
| Base revision | `5a4dddf589249637a1688815d92b39702017f679` on `cgjedrem-vigilant-robot`; code/test changes remain a working-tree candidate at this checkpoint. No branch switch or PR #9 action. |
| Source/test identity | **44** changed Python/frontend source and test paths; **983,516 bytes**; SHA-256 `97a5065aa72f1d50a0b2ae1d0a5fd0a3c02fd0bcb75568ddad878a23666f416b`. Hash input: sorted relative `.py`, `.ts`, `.tsx`, `.js`, `.jsx`, `.mjs` paths and exact bytes with 8-byte big-endian length prefixes. Includes untracked valuation source/test files; excludes docs, screenshots, config-only files and `pypa/`. |
| Dirty-diff identity at code/test checkpoint | SHA-256 `0a71690efb29c19669cef0b9bb674cc4d88995ecc286d4002f8d4ae969a99cf7`. Input: 8-byte-length-prefixed `git diff --binary HEAD` (**4,217,381 bytes**) plus sorted relative paths/content for untracked `hedge_fund/web/valuation.py` and `hedge_fund/web/test_valuation.py`; `pypa/` excluded. Evidence/progress/task/memory documentation changed after this checkpoint; source/test identity is unchanged. |
| Environment | Windows 11 Enterprise build `26200`; local NTFS worktree; Python `3.13.7`; isolated existing pytest environment under checkout `outputs`; Node `22.13.1`; Vite `6.4.5`; Vitest `4.1.12`; dotenv disabled; synthetic roots/fake providers; no paid calls or non-loopback provider traffic. |
| Browser artifact | Production Vite output built after the backend repair and exercised through fake API routes: SHA-256 `8fb49c2aef6e74b10133cee513e588d72a571057023e97f44624b4c137518a33`, **3 files / 954,901 bytes**. Build output was removed with the owned E2E root after hashing; artifact is not retained and is not a wheel or installed backend artifact. |

### Measurements

- `2026-11-01T01:58:50.7113583+01:00` → `2026-11-01T01:58:53.3087131+01:00`: red reproduction of a one-shot result-sidecar write failure; **1 failed in 1.75 s**, pytest exit 1. Durable index said `completed`; `get_operation` failed sidecar verification before recovery.
- `2026-11-01T01:59:15.6255854+01:00` → `2026-11-01T01:59:21.2601252+01:00`: after repair, terminal-sidecar and terminal-index fault tests: **2 passed in 4.45 s**, process exit 0. One-shot sidecar failure now repairs projection from committed index while registry lock remains held; operation reads `completed` immediately; no effect replay.
- `2026-11-01T01:59:33.6181159+01:00` → `2026-11-01T02:00:22.4927528+01:00`: Python `hedge_fund/runtime/test_operations.py`; **35 passed in 43.42 s**, process exit 0.
- `2026-11-01T01:59:33.5713430+01:00` → `2026-11-01T02:00:33.8956883+01:00`: Python `hedge_fund/web/test_jobs.py`; **18 passed in 48.84 s**, process exit 0. Covers queued-cancel completion cleanup and late cancellation after a guarded effect.
- `2026-11-01T01:59:33.5270062+01:00` → `2026-11-01T01:59:35.9296863+01:00`: Black check on six selected Python files, flake8 on seven selected Python files, and `git diff --check`; all exit 0.
- Python `hedge_fund/web/test_valuation.py`: **7 passed**, process exit 0. CLI/container/compose root-selection tests: **4 passed**, process exit 0.
- `2026-11-01T02:00:50.9237126+01:00` → `2026-11-01T02:00:51.2269129+01:00`: first final E2E attempt **BLOCKED before root/server creation**, exit 1; owned runner could not resolve Poetry's interpreter. Corrected by supplying the isolated interpreter's absolute path.
- `2026-11-01T02:00:57.0485452+01:00` → `2026-11-01T02:01:30.5128586+01:00`: `frontend/e2e/run-owned.mjs` with isolated Python `3.13.7`; Vite `6.4.5` transformed **2,307 modules**, built in **10.83 s**, emitted the artifact above; Playwright **7 passed in 14.1 s**, process exit 0. Total elapsed **33.464 s**. Scenarios: desktop/narrow routes, paper valuation, canonical builder, durable backtest preview/accept/cancel, deep links, disabled decisions and reload recovery.
- Same run refreshed **17 screenshots / 2,839,052 bytes** under `specs/005-web-engine-migration/screenshots/`. Synthetic root `outputs/spec005-test-e2e-52828-d8e63abc` was absent after cleanup; owned Uvicorn PID `45716` was absent. `2026-11-01T02:02:04.9417456+01:00` → `2026-11-01T02:02:05.0166167+01:00`: exclusive bind to `127.0.0.1:8876` passed, exit 0. Earlier two bind-check commands failed on PowerShell path/quoting; corrected here-string command passed.
- Vitest: **2 files / 16 tests passed in 76.91 s**, exit 0; timestamp not retained. Frontend source did not change after that run. Recharts/jsdom zero-size warnings remain; tests pass.
- A broader `test_run.py` selection returned **45 passed / 1 failed**, then `KeyboardInterrupt`. The failure was a console-wrap-sensitive absolute test-root assertion; the assertion now uses `<selected-root>`. Isolated rerun reported **1 passed in 0.92 s**, but the host process exited 1. Treat the CLI process result as **INCONCLUSIVE**; the four isolated launcher/root-selection tests above exit 0.
- Full Python suite remains **INCONCLUSIVE** at the previously recorded stall after 149 passed / 2 skipped of 1,207 collected. No full-suite retry occurred in this checkpoint.
- `2026-11-01T02:09:22.6321742+01:00` → `2026-11-01T02:09:25.2147992+01:00`: expected-red fault tests for preview, acceptance and cancellation sidecars; **3 failed in 1.48 s**, pytest exit 1. Each failure left a committed index projection that was unreadable or unreplayable.
- `2026-11-01T02:09:58.4640016+01:00` → `2026-11-01T02:10:09.4672019+01:00`: after repair, terminal/index, preview, acceptance and cancellation fault tests; **5 passed in 8.14 s**, process exit 0. Acceptance starts its worker only after the committed projection is repaired; identical replay does not start a second worker. Successful repair logs error type/OS codes only; failed repair rethrows original write error.
- Final operation-store suite `2026-11-01T02:14:55.3622386+01:00` → `2026-11-01T02:15:49.9928703+01:00`: **38 passed in 45.03 s**, exit 0. Final `web/test_jobs.py` `02:14:55.3622386+01:00` → `02:15:58.5909342+01:00`: **18 passed in 50.15 s**, exit 0. Final `runtime/test_root.py` `02:14:55.3622386+01:00` → `02:14:58.4897067+01:00`: **41 passed, 1 skipped in 0.68 s**, exit 0; includes POSIX FIFO nonblocking, Windows short-name rejection and concurrent reader/replacement coverage. All used isolated/synthetic roots.
- System Python `3.13.7` `web/test_jobs.py` attempt `02:10:21.1148444+01:00` → `02:10:22.9676881+01:00` was **BLOCKED during collection**, exit 4, because `pandas` was absent. The suite passed in the existing isolated pytest environment above; no package installation or network access was used.
- Final Black, isort, flake8 and `git diff --check` over the changed operation files passed after exact formatting/import-order corrections; formatter command duration was not retained.
- Final E2E `2026-11-01T02:13:42.6773384+01:00` → `2026-11-01T02:14:15.9908236+01:00`: Vite transformed **2,307 modules**, built in **10.69 s**; Playwright **7 passed in 13.9 s**, exit 0; total **33.313 s**. The bundle hash matched the artifact row above. At `02:17:24.7800357+01:00` → `02:17:25.0139655+01:00`, the owned E2E root and Uvicorn PID were absent and `127.0.0.1:8876` bound successfully.

### Remaining blockers at the 02:15 checkpoint (historical)

- `T015/T021`: no verified offline handover and no complete shared admission in every legacy/headless writer. A root-owner lease coordinates only participating processes; do not use writable web mode against existing roots.
- `T018/T025–T043`: no canonical manual-tick endpoint, owned child-runner lifecycle, verified stop, restart observation, or React manual-run flow. UI controls remain disabled.
- Linux/ext4, actual NTFS ACL proof, Docker image build, final wheel rebuild, full Python suite, and retirement/parity evidence remain pending or inconclusive. The existing CLI runner remains a legacy path and was not started.

## Latest bounded vertical-slice evidence — 2026-11-01

### Identity and scope

| Field | Evidence |
|---|---|
| Status | **T018 PASS — implementation/test criteria only. T015/T021 PARTIAL.** No release, existing-root or cross-platform acceptance claim. |
| Base revision | `865429c0d1a64e4b15e1b55361f6c96f4fb6af36`, branch `cgjedrem-vigilant-robot`; source/test changes were uncommitted at observation. |
| Source/test snapshot | **50 changed paths / 1,131,093 bytes**, SHA-256 `4f482e6e789aea5b966f30eb8542f2740de2a9b9c4738eaa7141aa7b17ec9a4e`. Sorted relative `.py`, `.ts`, `.tsx`, `.js`, `.jsx`, `.mjs` paths and exact bytes; UTF-8 paths and file bytes each length-prefixed with 8-byte big-endian lengths. `frontend/` and `hedge_fund/` only; docs, screenshots and `pypa/` excluded. Final after the durable-cancel barrier, fake TUI quote source and changed-line formatting corrections. |
| Source/test dirty-diff identity | SHA-256 `0748800c49f610e48de174356ac90381b8df9cbd173e2bf72a412c775e8f2352`; 40 tracked source/test paths / **280,850 binary diff bytes** plus 10 untracked source/test files. Hash input: 8-byte big-endian length and bytes of `git diff --binary --full-index HEAD -- <sorted tracked source/test paths>`, then sorted untracked path and content records, each length-prefixed with 8-byte big-endian lengths. Base `865429c0d1a64e4b15e1b55361f6c96f4fb6af36`; docs, screenshots and `pypa/` excluded. |
| Environment | Final evidence collection `2026-11-01T07:16:36.2950172+01:00` → `07:16:36.6667427+01:00`: Windows 11 Enterprise build `26200`, C: NTFS, branch `cgjedrem-vigilant-robot`, base revision above. Python tests used `outputs/spec005-poetry-envs/aihf-Tbl0PwyA-py3.13/Scripts/python.exe` (Python `3.13.7`, pytest `7.4.4`, pandas `2.3.3`); `yfinance` is absent from this environment. Browser run used Node `22.13.1`, Vite `6.4.5`, Playwright `1.64.1`. Synthetic roots, fake/local analysts and offline network guards; dotenv disabled; credential/provider/proxy variables cleared. |
| Frontend build artifact | Final `node e2e/run-owned.mjs` from `frontend/`, with `AIHF_E2E_PYTHON` set to the isolated interpreter: `2026-11-01T07:04:55.5479524+01:00` → `07:06:22.3615725+01:00`. TypeScript/build harness exited 0; Vite transformed **2,307 modules**, built in **23.12 s**, emitted **3 files / 965,278 bytes**, SHA-256 `787e53b0bc4fc9b6017456a9f8057c0662a2ca86e7975cf10846f3f4f3303171`. Playwright: **10 passed in 18.9 s**. Build output was removed by the owned harness. Browser API scenarios used fake routes; this is not backend paper-operation evidence. No final backend wheel/installed artifact was built. |
| Screenshots | **17 synthetic screenshots / 2,741,160 bytes** under `specs/005-web-engine-migration/screenshots/`; nine changed relative to `HEAD` in the final browser run. `desktop-paper-detail.png` SHA-256 `81bdf6779175dc62a1654e58932c0a409e76a6d6425fe6846a47d2a29d380abf`; `mobile-paper-detail.png` SHA-256 `8de9e318b28b06a447e9470cb88731dfa79e7d50228690bc5616f11df73c76a2`. Count, bytes and hashes checked at `2026-11-01T07:16:36.2950172+01:00` → `07:16:36.6667427+01:00`. |
| Cleanup | Owned synthetic root `outputs/spec005-test-e2e-53280-a11fedad` absent; exact Uvicorn PID `54196` absent; exclusive bind to `127.0.0.1:8876` succeeded at `2026-11-01T07:16:36.2950172+01:00` → `07:16:36.6667427+01:00`. An initial read-only cleanup probe stopped at assignment to PowerShell's reserved `$PID`; corrected probe used `$ownedId` and verified all three conditions. Other synthetic `outputs/spec005-test-*` roots remain and were not removed. No port `8765`, protected home root, paid provider or unknown process was accessed/signalled. |
| Provenance | Execution owner: python-dev. Evidence types: source review, synthetic Windows/NTFS pytest, frontend unit result, final owned fake-route browser build/E2E, screenshot measurement and cleanup probe. Test timestamps are recorded where retained; absent wall-clock times are explicitly labeled. QA2 finding origin is the user-provided summary; no independent QA2 review occurred. `qa2-direct-writer-report-2026-11-01.md` records implementation-owner disposition, not QA sign-off. |

### Source review and dispositions

- **C1 — unenrolled web writes:** starting-revision `DeskService.__init__` prepared private storage and acquired a root lease when `allow_writes=True`; it did not require a valid offline handover. Current service computes `enrollment_status(..., verify_inventory=True)` and enables writes only for an enrolled root plus explicit capability and shared owner lease. Web routes do not enroll a root. `seed_demo()` requires an empty explicit demo root and enrolls before seeding. Final synthetic handover/admission/manual/runner slice: **99 passed in 52.62 s**.
- **C2 — same-build writer bypass:** enrolled CLI paper create/tick/redo/approval/halt paths use deployment/manual/control admission or deny; `paper.tick.tick()` and `redo()` verify inventory before effects; `deploy()` requires its deployment lane; legacy `paper.runner` paths deny enrolled roots; low-level ledger mutations require an admitted lane; web paper operations share root/deployment/runner/execution/control admission; TUI paper writes fail closed without admission. Final cross-process/manual/owned-runner slice: **99 passed in 52.62 s**; CLI selection **17 passed / 24 deselected**; web boundary/actions/settings **45 passed**; TUI paper file **28 passed**. This is **partial T021**, not exhaustive writer proof.
- **Owner self-review C3 — missing handover with orphaned admission state:** when `handover.json` disappeared but private admission artifacts remained, legacy admission could report `unenrolled`; the legacy runner and TUI deletion path then stayed writable. `enrollment_status()` now reports invalid for missing handover plus existing/unverifiable owner/admission state; CLI writer admission, legacy runner and TUI deletion deny before effects. Explicit `handover inspect` can inventory under the migration lock for deliberate offline recovery. Expected-red regression set: **4 failed in 1.65 s**; after correction focused orphan/recovery regressions: **18 passed in 4.99 s**. Final backend slice and CLI/TUI tests above pass. This was an implementation-owner self-review finding, not a QA2 assertion.
- **I1 — deployment lane:** enrolled CLI/web deploy paths take a per-fund deployment lane; handover-head updates take the registry lane. The lane implementation is cross-process tested on synthetic NTFS.
- **I2 — root participation:** `RootOwnerLease` is shared for participating processes; `RootMigrationLease` is exclusive for offline enrollment. Acquisition closes its OS handle/releases a held token on exception. Tests verify shared/exclusive conflict and no lease leak after malformed/copy-bound record rejection.
- **Container observer:** `DeskService(container_observer=True)` rejects construction. No Docker/compose change or container bind test ran; deployment-role/namespace acceptance remains **BLOCKED**.
- **UI state:** `paper.tsx` renders `enrollment_state` and `write_unavailable_reason`; write-disabled controls have `disabled` attributes and the stopped-runner badge is muted/warning, not green. The screenshot is a synthetic demo in read-only/network-off mode, not proof of backend mutation behavior.

### Test and runtime observations

| Evidence row | Status and observation |
|---|---|
| Offline handover, admission, local-paper tick, owned child | **PASS — scoped synthetic Windows/NTFS.** At `2026-11-01T07:11:55.7070018+01:00` → `07:12:58.2840683+01:00`, `python -m pytest hedge_fund/runtime/test_admission.py hedge_fund/runtime/test_handover.py hedge_fund/runtime/test_ownership.py hedge_fund/runtime/test_owned_runner.py hedge_fund/runtime/test_owned_runner_child.py hedge_fund/paper/test_tick.py hedge_fund/paper/test_runner.py hedge_fund/web/test_paper_operations.py -p no:cacheprovider -q --tb=short`: **99 passed in 52.62 s**, exit 0. Actual enrollment functions are used. Includes exact inventory/attestation, fresh-empty denial, any-`runner.pid` refusal, copied/malformed record denial, shared/exclusive lock conflict, ledger drift denial before data access, local-fake manual tick, stale-head rejection, exact owned-child identity, cooperative stop, startup/manual lane conflict and no duplicate append. |
| Durable operation store | **INCONCLUSIVE as a formal evidence row.** `python -m pytest hedge_fund/runtime/test_operations.py -p no:cacheprovider -q --tb=short` was observed exiting 0: **39 passed in 59.69 s**. Exact wall-clock timestamp was not retained, so this observation does not meet the evidence contract. Covers idempotent request acceptance, stale review, restart interruption/fencing, guarded result and sidecar repair. |
| Shutdown cancellation ordering | **FAIL reproduced → PASS after repair.** An earlier code-order run observed **17 passed / 1 failed**, `INTERRUPTED` instead of `CANCELLED`. After code ordering was fixed, a later full run observed **17 passed / 1 failed**, `COMPLETED`: the test released worker and durable-cancel barriers together, so completion could win before request persistence. The test now waits for `original_request_cancel()` to return before releasing the worker. Full file at `2026-11-01T07:01:02.1756999+01:00` → `07:02:22.5729120+01:00`: **18 passed in 66.55 s**, exit 0. After final assertion-message formatting, targeted `test_close_waits_for_worker_boundary_before_interruption` at `07:14:34.4104278+01:00` → `07:14:41.0661791+01:00`: **1 passed, 17 deselected in 3.79 s**, exit 0. Code persists durable cancellation before local shutdown signal; test asserts cancellation acknowledgment and no interruption. |
| CLI handover/paper/approval | **PASS — scoped.** At `2026-11-01T07:13:04.6363270+01:00` → `07:13:14.5574770+01:00`, `python -m pytest hedge_fund/test_run.py -k "handover or enrolled_cli_tick or paper_flow_create_tick_status_halt_resume or paper_create_approval_and_approve_commands_show_status or paper_approve_now or paper_reject or paper_approval_commands" -p no:cacheprovider -q --tb=short`: **17 passed, 24 deselected in 7.66 s**, exit 0. |
| Web boundary/actions/settings | **PASS — synthetic.** At `2026-11-01T07:13:17.8009134+01:00` → `07:14:09.1353932+01:00`, `python -m pytest hedge_fund/web/test_app.py hedge_fund/web/test_actions.py hedge_fund/web/test_settings.py -p no:cacheprovider -q --tb=short`: **45 passed in 41.32 s**, exit 0. |
| TUI paper controls | **FAIL → PASS — fake quote source.** Initial full-file run failed one navigation assertion because background `_fetch_quotes` raised `ImportError` (`yfinance` absent from the isolated venv). The screen test now stubs `fetch_snapshots` with an empty mapping; no provider import or request is needed. Final full file at `2026-11-01T07:14:11.9191814+01:00` → `07:14:31.1315738+01:00`: **28 passed in 16.64 s**, exit 0. |
| React unit tests | **INCONCLUSIVE as a formal evidence row.** `npm test -- --reporter=dot` from `frontend/` was observed exiting 0: **2 files / 19 tests passed**, Vitest duration **44.65 s**. Exact wall-clock timestamp was not retained, so this observation does not meet the evidence contract. |
| Browser build/E2E | **PASS — frontend fake-route scenarios only.** Final `node e2e/run-owned.mjs` from `frontend/` at `2026-11-01T07:04:55.5479524+01:00` → `07:06:22.3615725+01:00`: Playwright **10 passed in 18.9 s**, exit 0; Vite **2,307 modules, 23.12 s**, bundle SHA-256 `787e53b0bc4fc9b6017456a9f8057c0662a2ca86e7975cf10846f3f4f3303171` (3 files / 965,278 bytes). Scenarios include review/accept-once/reload, stale-head denial, finite runner controls and cooperative stop UI. No backend paper operation was driven by the browser. |
| Style/static checks | **PASS for changed lines; inherited full-file failures remain.** Final changed-line Black/isort attribution across **46 Python files** found **0 added-line findings**. Flake8 `--max-line-length=420 --extend-ignore=E203` and `git diff --check` exited 0 at `2026-11-01T07:15:17.1110394+01:00` → `07:15:34.6865486+01:00`. Full-scope check still reports Black on 6 files, all already failing at `HEAD`; baseline had 7, with `web/app.py` corrected. Isort reports 3 inherited files; baseline had 4, with new import changes corrected. Current Black failures: `paper/test_runner.py`, `runtime/configuration.py`, `test_run.py`, `tui/funds.py`, `web/test_actions.py`, `web/test_settings.py`. Current isort failures: `runtime/configuration.py`, `runtime/test_policy.py`, `web/jobs.py`. |
| Full Python suite | **INCONCLUSIVE.** Prior full-suite attempts stalled after 149 passed / 2 skipped of 1,207 collected; no full-suite rerun after the latest code edit. |
| Linux/ext4, NTFS ACL, wheel/container | **BLOCKED.** Linux/ext4 lock/identity behavior and actual NTFS private-storage ACL enforcement were not exercised. A previous wheel smoke binds an older snapshot; final wheel/container build not performed. |

### Remaining risks and stop condition

- **T015 remains partial:** migration requires exact inventory digest and operator attestation, refuses every `runner.pid`, and holds the exclusive migration lease. Application locks cannot fence an unaware legacy binary or an out-of-band writer; the operator statement is not OS proof. Explicit stale-reservation recovery records remain absent.
- **T021 remains partial:** `fund/storage.py` and `backtesting/research.py` are not integrated; no complete CLI/web/TUI/runner/archive/out-of-band race matrix exists. Some low-level `Ledger` mutations rely on top-level admission preflight rather than verifying the full inventory themselves. Do not claim every possible caller fails closed.
- A drifted root disables ordinary write capability and owned-runner stop in `DeskService`; emergency halt is separate. The owned child verifies its head at session boundaries, but a stop route on drift is not enabled. No unknown PID is signalled.
- Required final status is **INCONCLUSIVE/BLOCKED outside this bounded slice**. Next stop: complete T015 stale-reservation/offline exclusion evidence and T021 remaining writer integration before any existing-root deployment; separately obtain native Linux/ext4 and ACL evidence. Do not resume into TUI retirement or broader US1 acceptance in this slice.

## Convergence — T141 physical mandate rename (partial)

| Field | Evidence |
|---|---|
| Status | **PARTIAL PASS.** Revision-bound update now atomically moves the mandate file to its canonical target without replacement, then writes the validated revision. The prior advanced-field update/clone code remains; this slice does not prove complete `FundSpec` round-trip or browser parity. T141 remains unchecked. |
| Source identity | Base revision `9694f619207e14fb5e55de1bef96deb79df7a360`; source/test snapshot `hedge_fund/runtime/root.py`, `hedge_fund/runtime/test_root.py`, `hedge_fund/web/services.py`, `hedge_fund/web/test_services.py`: 4 paths / 224,930 bytes / SHA-256 `743edd853a24164a1075a3a8baa9028208a713b8025e20b824b2ccc40c1fc8dd`. No wheel or installed artifact; pytest imported this working-tree snapshot. |
| Dirty-diff identity | At the test checkpoint, tracked `git diff --binary HEAD`: 148,984 bytes / SHA-256 `48fb92f6aea25b54c78951d8e1daccc7d8d7d4a76e956f44031efe012780ba68`. This identity excludes untracked `pip/` and `pypa/`; neither directory was touched. |
| Environment | Windows 11 `10.0.26200`, local `C:` NTFS, Python `3.13.7` in `outputs/spec005-run-t138-targeted/.venv`; dotenv disabled; credential/provider/proxy environment names cleared before pytest; repository test harness used synthetic roots and blocked unapproved network requests. |
| Scenario | Root tests moved a regular file under a synthetic root, rejected destination collision without replacing either file, denied traversal and rejected a directory leaf. Service tests renamed the mandate under its expected-hash revision, retained the deployed `fund.yaml` bytes, confirmed old logical name absence, and reused that old name with a new mandate. Collision preserved the source revision. |
| Provenance | Execution owner: python-dev. Automatic fake/unit tests only. No provider, external network, real broker, protected root, owned runner, process signal or browser route was used. |
| Result | At `2026-11-01T10:12:04.2664564+01:00` → `2026-11-01T10:12:55.8618147+01:00`, `python -m pytest -p no:cacheprovider hedge_fund/runtime/test_root.py hedge_fund/web/test_services.py -q --tb=short`: **71 passed, 1 skipped in 41.95 s**, exit 0. Black check passed on these four changed Python files; flake8 passed with `--max-line-length=420 --extend-ignore=E203`. Isort still reports `test_root.py` and `web/services.py`; both already required sorting at base HEAD. |
| Repair evidence | First run (`10:02:37.8238063+01:00`–`10:03:29.2381499+01:00`) and second run (`10:03:47.1009618+01:00`–`10:04:37.2366568+01:00`) each observed **1 failed, 70 passed, 1 skipped**: Windows returned `PermissionError [WinError 5]` when the test expected `RootPathError` for a directory leaf. The second stack showed `NtCreateFile` rejected the leaf before `_validate_windows_handle`; the extra metadata preflight did not distinguish directory from denied access. The preflight was removed; the cross-platform denial test now accepts native `OSError` or `RootPathError`. Final regression above passed. |
| Limits | The Linux `renameat2(RENAME_NOREPLACE)` path is unexecuted; Linux/ext4 is **BLOCKED** in this environment. No concurrent out-of-band writer, crash between rename and content rewrite, actual ACL, browser, or full migration acceptance was exercised. A crash after the move but before the rewrite is not journaled; retry behavior is not crash-injection verified. |

## Convergence — T141 advanced JSON round-trip (partial)

| Field | Evidence |
|---|---|
| Status | **PARTIAL PASS.** Revision-bound update now has an assertion that the full saved spec equals `FundSpec.model_validate(candidate).model_dump(mode="json")`; this covers field preservation in the tested candidate, not every constructor/field combination. T141 remains unchecked. |
| Source identity | Base revision `9694f619207e14fb5e55de1bef96deb79df7a360`; 4 source/test paths (`hedge_fund/runtime/root.py`, `hedge_fund/runtime/test_root.py`, `hedge_fund/web/services.py`, `hedge_fund/web/test_services.py`): 237,070 bytes / SHA-256 `754f7004deffbc5c75a60e77afea3b615ec07d578bf5076cbf106b4499bafe2c`. `services.py` and `test_services.py` also contain T146 work. |
| Dirty-diff identity | `git diff --binary HEAD` limited to those 4 source/test paths: 52,762 bytes / SHA-256 `37ffc0ef806313813fe9e5a978f9a7a892f5e9063f1c63f7f29c3fe19d98686d`. Untracked `pip/` and `pypa/` excluded and untouched. |
| Environment | Windows 11 `10.0.26200`, NTFS, Python `3.13.7` in `outputs/spec005-run-t138-targeted/.venv`; dotenv disabled; credential/provider/proxy environment names cleared; all file tests use synthetic roots. |
| Scenario | Revision-bound JSON edit checks the exact full serialized candidate after model validation, stale-hash rejection and immutable deployed bytes. Root/service cases exercise canonical physical rename, old-name reuse and no-replace collision. |
| Provenance | Execution owner: python-dev. Automatic pytest only; no provider, paid network, real broker, protected root, owned runner or process signal. |
| Result | At `2026-11-01T10:42:19.8916853+01:00` → `2026-11-01T10:44:41.0003325+01:00`, `python -m pytest -p no:cacheprovider hedge_fund/runtime/test_root.py hedge_fund/web/test_services.py hedge_fund/web/test_actions.py hedge_fund/web/test_paper_operations.py -q --tb=short`: **106 passed, 1 skipped in 114.59 s**, exit 0. |
| Limits | Mandate-editor browser save/rename, exhaustive registered-parameter/field matrix, Linux/ext4 no-replace, crash injection and full migration acceptance remain unverified. Rename then rewrite is not one journaled transaction. |

## Convergence — T146 bounded research and paper-history pages (partial)

| Field | Evidence |
|---|---|
| Status | **PARTIAL PASS.** Research index and verified paper-session history now expose bounded stable cursor/search pages, including records beyond 100. T146 remains unchecked: canonical drilldown/export coverage, full risk/tape/thesis detail parity and honest per-ticker valuation freshness are still open. |
| Source identity | Base revision `9694f619207e14fb5e55de1bef96deb79df7a360`; 8 source/test paths (`hedge_fund/web/services.py`, `hedge_fund/web/app.py`, `hedge_fund/web/test_services.py`, `frontend/src/pages/research.tsx`, `frontend/src/pages/paper.tsx`, `frontend/src/lib/types.ts`, `frontend/src/App.test.tsx`, `frontend/e2e/desk.spec.ts`): 368,295 bytes / SHA-256 `74844d4d8b88b8ed908e1f887b6eb9dbc1eea2da34a7ebbe9c9510c6b66badce`. |
| Dirty-diff identity | `git diff --binary HEAD` limited to those 8 source/test paths: 82,611 bytes / SHA-256 `77e9c244470657cbccabef1fc80b8c1c26a7e80cd7f1058ee253ec85ea1e78b7`. Combined T141/T146 10-path source/test snapshot: 448,294 bytes / SHA-256 `fef200395abef9e2fdb55c6cf7e082172eba8d1ede614c44c43f85efcb10ae57`; selected dirty diff: 91,560 bytes / SHA-256 `55d345451fd714d9d71848220d667bae3c6d647338c497601bd70d15f75d9599`. |
| Artifact identity | Node `v22.13.1`, Vite `6.4.5`; isolated production build in the owned E2E root: SHA-256 `309b88c7a472685221fee0cb89f207d9d72e8f36d9f38a2a9a2301c82df7897a` (3 files / 973,294 bytes). Source-to-artifact mapping: the T146 source snapshot above, built by `run-owned.mjs`; no wheel/install artifact. Bundle-size warning (>500 kB minified) remained non-fatal. |
| Environment | Windows 11 `10.0.26200`, NTFS, Python `3.13.7`, Node `v22.13.1`, npm `10.9.2`; test HOME/USERPROFILE and web root isolated; dotenv, credentials and proxies cleared. Playwright Chromium project used configured Microsoft Edge channel; exact browser build was not logged. Owned local server used `127.0.0.1:8876`; no port `8765`, external provider or paid call. |
| Scenario | Backend research test paginates 107 synthetic JSON entries including one malformed report, checks case-insensitive fund search, cursor continuity, error visibility and bounds. Paper-history test appends 105 hash-chained records to the 3-record synthetic demo ledger; the actual `Ledger.replay(full=True)` verifies all 108, then pages 40/40/28 with date/hash search, cursor validation and API query bounds. UI tests and browser tests confirm search/reset/next/previous cursor wiring; browser API responses are deliberately fake. |
| Provenance | Final backend command and result are recorded in the T141 row above; the same 106-test run includes research and paper-history API cases. `npm test`: **26 passed** in 8.06 s, exit 0. `npm run build` (`tsc --noEmit && vite build`): exit 0, Vite build 11.73 s. At `2026-11-01T10:31:16.9160415+01:00` → `2026-11-01T10:31:52.6138198+01:00`, `node ./e2e/run-owned.mjs --grep "history search follows"`: **2 Playwright tests passed** in 15.3 s, exit 0; the isolated root was cleaned. |
| Invocation note | First attempt via `npm run e2e -- --grep "research history search follows stable page cursors"` forwarded the words without `--grep`; Playwright reported “No tests found” and exited 1. No assertion ran. Direct Node invocation above selected and passed both browser cases. |
| Limits | Playwright pagination routes return fakes; backend pages are separately exercised against synthetic root files and a real hash-chained ledger. Full browser-to-backend pagination, >100 browser dataset, report exports, full drilldowns, risk detail, valuation freshness, wheel, Linux/ext4 and final migration acceptance remain unverified. |

## Final bounded QA closure — partial

The final service fixes, exact test commands, timezone-qualified observations, full source/test/screenshot identity, current browser artifact, wheel identity and remaining blockers are consolidated in [`spec005-final-evidence.md`](spec005-final-evidence.md). Final readiness is **PARTIAL / NOT READY TO MERGE**; see [`qa-final-disposition.md`](qa-final-disposition.md).

At `2026-11-01T11:26:18.3783384+01:00` → `11:29:20.1900746+01:00`, the final isolated root/services/actions/manual-paper slice passed **112 tests, 1 skipped in 152.76 s**, exit 0. Final frontend unit tests passed **26**, TypeScript/build exited 0, owned fake-route Playwright passed **12**, bounded fake-transport Saxo tests passed **8**, and the candidate wheel built. Full Python suite remains **INCONCLUSIVE**; Linux/ext4 and actual ACL acceptance remain **BLOCKED**. T015/T021 remain partial; T137/T138/T140–T148 remain incomplete, including bounded partial evidence for T139/T141/T146. No production write activation or TUI retirement.

## Convergence — T137 provider dispatch authority (implementation-owner evidence)

**Disposition: PASS — scoped implementation and fake-transport regressions.** This does not establish live-provider behavior, an installed T137 artifact, or full migration acceptance. Existing rows above are historical snapshots; this row binds the later implementation commit.

### Revision and artifact identity

| Field | Observation |
|---|---|
| Branch / parent / implementation commit | `cgjedrem-vigilant-robot`; parent `4c6eee41b926f3195a602330225276dc859433a2`; implementation commit `4177741ee06a1daddf4751eb441f0924c4f7407a`. |
| Commit patch | Base-to-commit binary full-index diff: **62 paths / 460,726 bytes / SHA-256 `8ce120b126b30f1a86d927fdada6ac791c9ddbedf495f94487baad59fa4fdcd9`**. Commit contains 6,044 insertions and 1,212 deletions. |
| Committed source/test snapshot | **57 `.py`, `.ts`, `.tsx`, `.json` paths / 1,207,747 content bytes / SHA-256 `be3f2d8718e2d97f1253444450d633d426f1ac5bfc2d8dc5396ee03a83f58ff2`**. |
| Tested worktree source/test snapshot | **57 paths / 1,237,567 content bytes / SHA-256 `f20174a78e17a9e1a57096bb38322fb083fd109a26fef48e4a72c1e83d94be80`**. Snapshot digest sorts repository-relative paths and feeds each UTF-8 path and file content preceded by an 8-byte big-endian length. All 57 worktree files normalize to their commit blobs by CRLF→LF; no other content mismatch. |
| All committed file snapshot | **62 paths / 1,238,212 content bytes / SHA-256 `57f77010cc8f6472f9f539e5bce0de4cf76583185497f6d9dce13d42b6beb9b3`**, with the same path/content digest algorithm. |
| Artifact | Source-run against the worktree content above. No wheel, installed T137 package, container, or live-provider artifact was built. The older `aihf-2.6.1` wheel and smoke in prior rows predate this commit and are not T137 evidence. |

### Environment and isolation

- Observed on Windows 11 Enterprise `10.0.26200`, NTFS, Python `3.13.7`, pytest `7.4.4`, using `outputs/spec005-poetry-envs/aihf-Tbl0PwyA-py3.13/Scripts/python.exe`.
- The isolated environment contains `yfinance 1.7.0` and `curl_cffi 0.16.3`; neither was installed during this task.
- Tests use checkout-owned synthetic roots, isolated HOME/USERPROFILE/TEMP, `PYTHON_DOTENV_DISABLED=1`, `PYTHONNOUSERSITE=1`, and cleared provider, credential, model and proxy environment variables. Test network sentinels and fake HTTP/model transports prevent provider I/O.
- No paid provider, broker or market-data service endpoint was called; no provider credit was used. No protected user root, protected runner/process, or port `8765` was accessed.

### Implemented boundary and scope

- `ProviderDispatch` is the synchronous outbound HTTP authority. It validates operation/deadline/fence, target, hostname and every DNS answer; disables environment proxies and redirect following; pins the approved public address; reserves cost/call budget before each attempt and rechecks expiry/fence before transport. Unknown provider/cost/destination and unsupported async dispatch deny.
- Production Financial Datasets, TypeSafe Jev, curl-cffi Yahoo data and guarded breakpoint/search paths use the dispatch seam. FD pagination creates separately reserved transport attempts. Model-call bounds and SDK retry controls prevent an unattended paid retry from bypassing the budget.
- Paid one-shot/backtest approval is explicit and bound to the frozen operation/config/deadline and bounded worst-case budget. An environment key is credential material, not consent. The CLI and web paths deny before downstream effects when required consent is absent; the existing scheduled runner and child deny paid/cloud modes.
- Verified paid bounds cover Financial Datasets self-service data and TypeSafe Jev `1.13.0`; only one paid provider is supported per operation. Combined paid FD+TypeSafe, other cloud providers, custom-cost endpoints and scheduled paid work fail closed.
- The TypeSafe cost guard parses request JSON and requires the actual wire-body model to match the authorized Jev target before reservation. Credential references stay private; tests verify the synthetic bearer value appears only in the fake guarded request, not result data.
- Free/local modes remain subject to explicit network capability; supported local-model and free-data paths are exercised with fakes. This row proves code/test wiring, not a live free-provider request.
- Discriminating regressions include immutable operation scope, paid retry denial before a second fake request, expiry/fence changes after DNS, private/mapped DNS denial, host/provider mismatch, pagination exhaustion before the next request, TypeSafe wire-model mismatch before reservation, absent CLI consent despite an environment key, positive CLI/web paid fakes, zero-cost local Ollama, and scheduled/legacy paid denial. Fixture-owned roots, dotenv suppression, scrubbed provider/credential/proxy variables and network sentinels are active in the suites.

### Measurements

| Evidence | Status | Exact observation |
|---|---|---|
| TypeSafe target-binding expected-red | **FAIL — expected before repair** | `2026-11-01T17:40:16.7719444+01:00` → `17:40:19.2532478+01:00`; the fake HTTPX regression observed a request body naming `jev-9.99.0` accepted under `jev-1.13.0` authorization instead of raising `AuthorizationDenied`. No provider/DNS/socket call. |
| TypeSafe binding focused green | **PASS — fake transport** | `2026-11-01T17:41:23.2773304+01:00` → `17:41:25.6981824+01:00`; dispatch/cost/client-constructor selector: **11 passed in 0.18 s**, exit 0. Model mismatch was denied before reservation and fake inner I/O. |
| Provider/data/cost/dispatch/capture/LLM/signal/fund | **PASS — fake transports and network sentinel** | `2026-11-01T17:43:55.4253179+01:00` → `17:44:25.4272914+01:00`; command: `outputs/spec005-poetry-envs/aihf-Tbl0PwyA-py3.13/Scripts/python.exe -X faulthandler -m pytest hedge_fund/data/test_client_contract.py hedge_fund/data/test_yfinance_client.py hedge_fund/features/test_breakpoints.py hedge_fund/runtime/test_policy.py hedge_fund/runtime/test_costs.py hedge_fund/runtime/test_dispatch.py hedge_fund/runtime/test_capture.py hedge_fund/runtime/test_credentials.py hedge_fund/runtime/test_bootstrap.py hedge_fund/llm/test_client.py hedge_fund/signals/test_llm_agents.py hedge_fund/fund/test_spec.py -p no:cacheprovider -q --tb=short -o faulthandler_timeout=120`; **491 passed in 26.05 s**, exit 0. |
| CLI, tick, scheduled runner and owned child | **PASS — fake provider transport** | `2026-11-01T17:44:30.3273843+01:00` → `17:44:55.6027384+01:00`; command: `outputs/spec005-poetry-envs/aihf-Tbl0PwyA-py3.13/Scripts/python.exe -X faulthandler -m pytest hedge_fund/test_run.py hedge_fund/paper/test_tick.py hedge_fund/paper/test_runner.py hedge_fund/runtime/test_owned_runner.py hedge_fund/runtime/test_owned_runner_child.py -p no:cacheprovider -q --tb=short -o faulthandler_timeout=120`; **104 passed in 20.46 s**, exit 0. Paid CLI FD action uses production client with fake HTTP below dispatch; scheduled paid/cloud calls deny. |
| Web jobs, paper operations, services, settings, actions, app and valuation | **PASS — fake transports** | `2026-11-01T17:45:00.6054784+01:00` → `17:50:00.0222747+01:00`; command: `outputs/spec005-poetry-envs/aihf-Tbl0PwyA-py3.13/Scripts/python.exe -X faulthandler -m pytest hedge_fund/web/test_jobs.py hedge_fund/web/test_paper_operations.py hedge_fund/web/test_services.py hedge_fund/web/test_settings.py hedge_fund/web/test_actions.py hedge_fund/web/test_app.py hedge_fund/web/test_valuation.py -p no:cacheprovider -q --tb=short -o faulthandler_timeout=120`; **119 passed in 242.26 s**, exit 0. Explicit paid preview/accept uses the production factory with fake transport; missing consent denies before operation/client effects. |
| Full LLM client module after formatting | **PASS — fake HTTP/model providers** | `2026-11-01T17:51:19.0120784+01:00` → `17:51:39.3598433+01:00`; command: `outputs/spec005-poetry-envs/aihf-Tbl0PwyA-py3.13/Scripts/python.exe -X faulthandler -m pytest hedge_fund/llm/test_client.py -p no:cacheprovider -q --tb=short -o faulthandler_timeout=120`; **149 passed in 16.71 s**, exit 0. |
| Real yfinance wrapper failure behavior | **PASS — real wrapper, monkeypatched transport method** | `2026-11-01T17:57:57.1319847+01:00` → `17:58:00.1247748+01:00`; command: `outputs/spec005-poetry-envs/aihf-Tbl0PwyA-py3.13/Scripts/python.exe -X faulthandler -m pytest hedge_fund/data/test_yfinance_client.py::test_transport_failure_raises_through_the_real_scraper -p no:cacheprovider -q --tb=short -o faulthandler_timeout=120`; **1 passed in 0.02 s**, exit 0. Real `yfinance 1.7.0` internals surface a synthetic `RequestException` as `DataClientError`; `YfData.get` is monkeypatched to raise before external I/O. `curl_cffi 0.16.3` was installed. |
| Frontend unit/type/build | **PASS — isolated build only** | Run began `2026-11-01T16:42:07.4245738+01:00`; end timestamp was not retained. Vitest: **2 files / 26 tests passed in 67.94 s**; TypeScript check exited 0; isolated Vite build exited 0 in **20.80 s**. No API/provider call. No frontend files changed after this run; the later model-binding review repair was Python-only. This is not a packaged T137 artifact. |
| Static checks | **PASS for changed lines** | `2026-11-01T17:51:19.164505+01:00` → `17:51:22.528379+01:00`; Black `--check --line-length 420` and isort Black profile passed over **53 Python paths**; changed-line flake8 found **0**; `git diff --check` passed. Six flake8 findings remain on unchanged lines in affected files; package-wide flake8 is not claimed green. |
| Full Python suite | **INCONCLUSIVE** | Not rerun for T137. Prior recorded attempts stalled at **149 passed / 2 skipped of 1,207 collected**; no full-suite pass is claimed. |

### Limits

- The observations are source-run unit/integration tests with fake transports. They do not prove an actual provider accepts the request, an installed T137 artifact behaves the same, or platform/network behavior outside the guarded test harness.
- No live provider, broker, paid retry or scheduled job was run. No production key was loaded. The old wheel smoke is unrelated to the T137 code identity.
- T137 is scoped complete only for the supported guarded paths above. Wider migration remains **PARTIAL / NOT READY TO MERGE**; combined paid providers, all cloud providers, live runtime, full-suite completion, Linux/ext4, and actual ACL evidence remain unresolved.

## T138 / T015 / T021 — storage and research writer slice

**Status: PARTIAL.** Evidence is source-run unit testing, not an installed artifact or runtime deployment.

- Observation timestamp: `2026-11-01T18:59:11.694992+01:00`.
- Revision: `1acbf4623686c90a04aba95099dc4fe5fe14db34`. Scoped source/test content identity: 11 paths / 221,544 bytes / SHA-256 `279429839f430abd7042e9f685de94f06ff4208cbd9d517f6bacdffdcf9fd7e9`. Scoped tracked diff: 50,705 bytes / SHA-256 `48c01317a58dbe5182d00197a93eb5e07135dd06db9bc38e7b4a6e2151d5b487`. `fund/storage.py` already used RootContext plus `root_registry_writer`; it was not modified in this slice.
- Environment: Windows checkout, project venv `outputs/spec005-poetry-envs/aihf-DI2Co9qP-py3.13/Scripts/python.exe`, Python 3.13.7; `PYTHON_DOTENV_DISABLED=1`; project pytest fixtures isolate HOME/TEMP/root/credentials/network. Synthetic roots and fakes only.
- For the pytest commands below, `$py` was set to that venv interpreter and dotenv was disabled in the PowerShell process.

| Result | Exact command | Observation |
|---|---|---|
| **PASS** | `& $py -m pytest hedge_fund\fund\test_storage.py hedge_fund\backtesting\test_research.py hedge_fund\runtime\test_handover.py hedge_fund\test_paths.py -q -p no:cacheprovider --tb=short` | Final run: **34 passed, 2 skipped in 8.29 s**, exit 0. Covers unchanged-byte denial for ordinary and paper paths, enrolled lane acceptance, research lane isolation from unrelated runner reservation, independent-fund concurrent writes, and explicit stale-recovery attestation/record identity. |
| **PASS** | `& $py -m pytest hedge_fund\test_run.py -q -p no:cacheprovider --tb=short` | Final run: **45 passed in 41.56 s**, exit 0. CLI backtest persistence uses an owner lease and the shared research lane; paper test helpers now mirror owner/manual-session admission and ledger-head update. |
| **PASS** | `& $py -m pytest hedge_fund\web\test_main.py hedge_fund\web\test_app.py -q -p no:cacheprovider --tb=short` | **20 passed in 6.57 s**, exit 0. Dotenv fixture uses a supported catalog model. |
| **PASS** | Owned subprocess: `python -m hedge_fund.web --demo --root <owned-root> --port 49678` | **4.282 s**, PID 31260. `/api/capabilities`: `mode=demo`, `writes=false`, `network=false`; dynamic loopback port, not 8765. `Stop-Process -Id 31260` stopped only the owned child; marked scratch root cleanup passed. |
| **FAIL** | `& $py -m pytest hedge_fund\tui\test_paper.py hedge_fund\tui\test_builder.py -q -p no:cacheprovider --tb=no` | **16 failed, 27 passed in 33.82 s**, exit 1. TUI flow is not green and is not treated as acceptance evidence. |

Black `--check --line-length 420` passed on 8 focused files. Black reports `test_research.py` and `test_run.py`; both also fail when checked from `HEAD` content. isort Black profile, flake8 with `--ignore=E203,W503 --max-line-length=420`, and `git diff --check` passed on selected changed paths. No build/install was performed for this slice.

The paper-path regression was red before the guard: **1 failed in 0.43 s** because `RootConfigurationError` was not raised; that red run stopped before asserting byte preservation. After the false-admission denial, the test passed **1 test in 0.12 s**, including unchanged bytes. An enrolled CLI deployment then identified the control-file lane requirement: `Ledger.init()` writes `control.json` under deployment admission. The path guard now recognizes that lane; final CLI and focused path suites pass.

### Direct-writer audit and limits

- `fund/storage.py::save_spec` uses root-relative `RootContext` I/O and registry admission; typed storage error on unavailable/denied admission.
- `backtesting/research.py::save_result` requires an `AdmissionCoordinator`, writes through `RootContext`, and holds the per-fund research lane. Research lanes are independent across funds and separate from runner reservations.
- `paths.py::write_bytes`, `write_text`, and `ensure_directory` enforce root registry admission for ordinary root paths and paper-lane admission for conventional paper paths; false admission on an unenrolled paper root now denies before bytes change. The paper fund directory, not its target file, binds the lane identity. `control.json` initialization also accepts the deployment lane; ordinary control writes still require control or execution lanes. `features/breakpoints.py`, `data/cached.py`, `llm/cache.py`, and root-bound CLI output use these helpers. Explicit output paths outside the selected root remain caller-owned paths.
- `paper/deployed.py` checks the deployment lane; `paper/ledger.py` checks write/control lanes. `paper/runner.py` retains direct legacy PID/log writes and denies enrolled roots; it remains a legacy/out-of-band boundary, not a proof that an unaware binary is stopped. `web/services.py`, `runtime/configuration.py`, `runtime/credentials.py`, `runtime/operations.py`, `runtime/handover.py`, and `runtime/owned_runner.py` use root-relative writes under their respective admission/operation/owner paths. `brokers/saxo.py` writes its refresh-lock owner under a temp lock directory, not a fund root.
- `tui/funds.py` still has direct unlink/rmtree fund deletion paths without shared admission on an unenrolled root. Existing TUI paper-denial behavior is not a complete fail-closed proof for legacy roots. This clause remains open; no TUI code was changed.
- Fresh web demo seeding enrolls the owned root, acquires `RootOwnerLease`/`AdmissionCoordinator`, and uses deployment, manual-session, and research lanes. The live launcher smoke proved this path after paper-path admission began rejecting unenrolled roots; no real-root exception was added.
- Legacy and out-of-band binaries remain **unfenced unless explicitly excluded**. Operator attestation and application locks do not prove that an unaware writer is absent. No full direct-writer race matrix, full Python suite, live provider, broker, network call, protected root, or production write was exercised.

T138, T015, and T021 remain unchecked. Stale-recovery record creation is implemented and explicitly attested, but T015 remains partial because legacy/out-of-band exclusion is unproven; T021 remains partial because the complete writer inventory/race matrix and TUI mutation boundary are unresolved.

## T021 / T138 — TUI admission regression repair and full-suite reassessment (2026-11-01T21:03+01:00)

Environment: Windows 11 / NTFS, Python 3.13.7 `.venv` (uv, `-e ".[web]"`, pytest 7.4.4), `PYTHON_DOTENV_DISABLED=1`, synthetic tmp roots, fake providers/brokers. Command form: `.venv\Scripts\python.exe -m pytest <paths> -q -p no:cacheprovider`.

- Supersedes the clause above that `tui/funds.py` keeps direct unlink/rmtree deletion: `_delete_fund` was removed; `action_delete`/`_finish_delete` return `mandate_delete_denial()`; `paper_write_denial()` denies in every state. `tui/paper.py` halt/resume/verdict/delete/run and `tui/builder.py` paper deploy/wipe fail closed with notices; `tui/backtest.py::_save_admitted` uses `RootOwnerLease` + `AdmissionCoordinator` research lane, closed in `finally`.
- Root cause of 16 TUI failures: pre-admission TUI writers crashed on admission errors (unenrolled) and bypassed lanes (enrolled). Tests converted to assert denial, unchanged ledger/events and file trees; new `hedge_fund/tui/test_admission_regressions.py` (7 tests). TUI: **87 passed**. Targeted TUI+admission+web+research: **249 passed, 2 skipped** plus 2 intermittent web failures passing on rerun.
- Full suite #1: **3 failed, 1549 passed, 42 skipped in 586.44 s** (wall 685 s); old 149/1,207 stall did not recur. Deterministic: `paper/test_saxo_e2e.py::test_saxo_external_adapter_records_order_fill_in_ledger` (TUI build on unenrolled root) and `runtime/test_bootstrap.py::test_cache_defaults_follow_configured_root` (cache write into unenrolled root denied by 3042c85 `_root_write_admission`). Repairs: direct `deploy()` with wizard-equal `FundSpec` (equality proven by temporary probe, deleted); cache child calls `enroll_fresh` after cache imports; new `test_cache_writes_deny_unenrolled_root`. bootstrap+saxo **22 passed in 5.25 s**.
- Behavioral consequence of 3042c85 (intended): production cache writes (`data/cached.py`, `llm/cache.py`, `features/breakpoints.py`) fail closed on unenrolled roots; operators must run `aihf --root <root> handover enroll-fresh`.
- Full suite #2: **2 failed, 1551 passed, 42 skipped in 526.58 s** (wall 617 s). Failures `web/test_jobs.py::test_reviewed_operation_preview_accept_persists_capture_and_report` and `::test_reviewed_backtest_cancellation_closes_fake_client_and_freezes_model`; rerun alone **2 passed in 27.58 s**; web package **134 passed in 265.16 s**. UNRESOLVED load sensitivity; `web/jobs.py` records only `worker-failed`, hiding the cause.
- Independent QA (code-review agent): no significant issues; **109 passed** (tui + saxo + bootstrap). Caveats: unenrolled-root TUI builder test relies on patched `ensure_mandates_dir`; halt/resume/verdict assert ledger state, not byte snapshots.
- Lint: isort and flake8 clean on changed files; Black findings on `tui/funds.py`, `tui/backtest.py` pre-exist at HEAD. Windows `OpenProcess` PID probe and native NTFS/ext4 evidence from 3042c85 preserved unchanged.

T021/T138 remain unchecked: deletion primitive parity, unaware legacy/out-of-band writers and the exhaustive writer-race matrix remain open. No TUI module or assertion was deleted.

## T019 / T020 ? common error envelope and intermittent web-failure root causes (2026-11-01T22:33:09+01:00)

**Status: PARTIAL.** Source-run evidence on Windows 11 / NTFS, Python 3.13.7 `.venv`, `PYTHON_DOTENV_DISABLED=1`, synthetic roots and fake providers only. Base `d5858e4`. Command form: `.venv\Scripts\python.exe -m pytest <paths> -q -p no:cacheprovider`.

### Error envelope (T019/T020 partial)

- `web/schemas.py` adds `ErrorCode`, `RetryPolicy`, default/retry/refresh maps, `ErrorResponse`, `error_code_for` and `error_payload`. Every HTTP error (middleware denials, Starlette 404/405, 413, 422 validation, `ServiceError`, unhandled 500) returns the additive envelope `{detail, code, message, refresh_required, retry_policy}`; `detail` is preserved for compatibility. About 47 `ServiceError` sites carry contract codes. 422 `loc` echoes of unknown field names are redacted; 500 responses carry security headers. Frontend `api.ts`/`types.ts` parse the envelope with a code whitelist; new `api.test.ts`.
- Red/green: `web/test_app.py` **16 failed / 8 passed** before, **24 passed** after. Vitest **3 files / 29 tests passed**; `npx tsc --noEmit` exit 0.
- Documented contract deviations (kept): halted, replay-corrupt and reconciliation-required stay 409 (not 423); validation stays 422 `invalid-request`; subject/request identity and current head are not yet in error bodies.

### Intermittent web failures ? discriminating evidence and repairs

1. **Swallowed worker exception.** `web/jobs.py::_log_worker_failure` logs only exception type and innermost frame basename:line (no message, path or secret) for start and worker failures; `test_operation_job_failure_logs_only_type_and_frame` proves message/secret/path are absent. First diagnostic capture: worker `AssertionError at test_jobs.py:1081` (second `cancelled()` check) ? the main thread's 5 s event wait expired under load and `close()` requested cancellation. Repair: test wait budgets `_WAIT_SECONDS = 60`.
2. **Owned-runner readiness budget.** Production readiness was 8.0 s; idle cold import of the child alone measured **5.52 s / 2.12 s / 2.11 s**. Repair: `owned_runner._READINESS_TIMEOUT_SECONDS = 30.0`. New `test_owned_runner_readiness_timeout_fails_closed_and_stops_child` (constant patched to 0): operation and runner `failed` with `runner-readiness-timeout`, stop requested, child exits, ledger unchanged. Red on baseline: `AttributeError` (no constant). Paper-ops + jobs + owned-runner: **32 passed in 144 s**.
3. **Lock-timeout misclassification and fatal transient busy.** Full suite after (1)?(2): **1 failed, 1569 passed, 42 skipped in 532.12 s** (`KeyError: 'status'` on a status poll). Added `operations.OperationBusy` and 503 `observation-conflict` / `retry-read-only` mapping for operation status/list reads; red (mapping removed) **409 request-conflict**, green **503**. Independent review found the conversion too broad (lock-file stat/open, ACL, reparse and `OwnershipUnknown` failures would be reported as retryable). Repair: `OperationStore._acquire_registry` raises `OperationBusy` **only** for `WriterConflict` during acquisition; other acquisition failures and `AdmissionError` from the locked body stay plain `OperationError` (409).
4. Confirmatory full suite: **3 failed, 1568 passed, 42 skipped in 502.02 s**. Captured logs: `start failed: OperationBusy at operations.py:609` ? reviewed preview ended `interrupted`; test helper `_wait_for_operation` raised `WriterConflict`?`OperationBusy` after the 5 s bound; paper `start_entered.wait(timeout=10)` expired (worker later failed closed with `ServiceError at services.py:1188`).
5. **Lock-contention experiment** (scratch roots under the session folder, one 60-write progress writer plus one status poller, deleted afterwards): idle durable write ~0.35 s each. Poll 10 ms: max writer lock wait **0.785 s** idle, **3.441 s** with 28 CPU burners. Poll 100 ms: **0.096 s** idle, **6.362 s** with burners (1 `OperationBusy`). Conclusion: the 5 s bound is exceeded under CPU saturation regardless of poll rate; slow durable writes are an open performance item.
6. Repairs: `OperationJobRegistry._retry_busy` retries only `OperationBusy` (bounded 30 s, backoff 0.05?0.5 s, stops on shutdown) for `claim_worker`, `mark_running`, `update_progress`, `cancellation_requested`, `complete` and `fail`; each takes the registry lock once and writes only while held, so a busy result means no durable change. Test pollers retry only `OperationBusy` / 503 `observation-conflict`; paper start barrier widened to 60 s.
7. New tests: `test_operation_lock_failure_other_than_timeout_is_not_retryable` (409 `request-conflict`, not retryable), `test_operation_body_admission_error_is_not_reported_busy`, `test_operation_job_retries_transient_busy_without_interrupting`. Red with blanket busy conversion and no job retry: **3 failed** (the retry test reproduced the full-suite `interrupted` symptom); sources restored byte-exact (SHA-256 verified). Green: **5 passed in 13.33 s**.

### Results

| Result | Command / scope | Observation |
|---|---|---|
| **PASS** | `hedge_fund\web` + runtime `test_*operations*`/`*owned_runner*`/`*admission*` + `backtesting\test_research.py` | **225 passed in 360.85 s** |
| **PASS** | `pytest hedge_fund` (full suite) | **1574 passed, 42 skipped, 0 failed in 567.23 s** (wall 664 s) ? first fully green full suite in this migration |
| **PASS** | `frontend`: `npx vitest run src`; `npx tsc --noEmit` | **29 passed**; tsc exit 0 |
| **PASS** | flake8 (`--max-line-length 420 --extend-ignore E203,W503`), Black, isort on changed files; `git diff --check` | clean; pre-existing Black findings in `test_actions.py` unchanged |

Independent reviews (code-review agents; no custom python-dev/qa-reviewer persona available): envelope diff **no significant issues**; OperationBusy delta **one medium finding** (non-timeout lock failures classified retryable) ? fixed; follow-up delta **no significant issues**.

T019/T020 remain unchecked: identity/head fields in error bodies, 423 realignment, remaining 503 sites, expired-CSRF and SIM-denial envelope coverage, and observation reconnect are open. One green full suite is not a statistical flake-free claim.

## T015 / T021 / T138 bounded lifecycle slice (2026-11-02)

**Status: implemented bounded slice; migration remains PARTIAL / NOT READY TO MERGE.**
T015/T021/T138 remain unchecked. This section supersedes earlier statements that no
web/headless scoped archive implementation exists; it does not supersede the A3
external-writer exclusion, complete writer-matrix, linked-replacement or retirement gates.

### Candidate, isolation and manifest

- Verified base and remote PR8 head before work: `d2e4f313ca27fd7e6f733c6760beb1bff32c2d0a`.
  Publication targets existing `cgjedrem-vigilant-robot`; no force push, duplicate PR or merge.
- Final code/test identity captured `2026-11-02T00:26:45.001715+01:00`:
  **`3a8b9e654043f76be905415e6998cb0aca6790cb14f71176060c0b3c64f4eb1e`**,
  **23 paths / 776,647 bytes**. Algorithm: sorted repository-relative UTF-8 paths, NUL,
  complete file bytes, NUL. Documentation and screenshots are excluded from this code
  identity; later documentation-only changes do not change loaded code.
  Canonical staged Git blobs: **`958fa00ff343a07df1e6777fbbbcbd8f8b99d770bef548f7afd0c93dba4f6e7e`**,
  **23 paths / 759,003 bytes**. At `2026-11-02T00:44:01.965031+01:00`, all 23 staged
  blobs were compared to the tested files: **only CRLF-to-LF normalization, zero
  non-newline differences**. The first attempted byte-exact assertion detected this
  normal Windows/Git conversion; neither hash is silently substituted for the other.
- Windows 11 / NTFS; Python 3.13.7 from the existing dependency-cache environment
  `aihf-jeXvH3Gy-py3.13`; Node 22.13.1. No other session checkout was accessed.
  Existing `hedge_fund/conftest.py` isolation scrubs HOME/provider/proxy/credential
  variables, disables dotenv, uses marked checkout-owned roots and denies non-loopback
  Python sockets. Browser harness owns port 8876, refuses reuse, strips inherited
  interpreter/Node overrides, uses fake demo data and denies non-loopback requests.
- No live root, paid/data/LLM/broker provider, credential, protected runner, port 8765,
  synthetic preview 49292 or PID 54644 was accessed, stopped or restarted.
- Runtime manifest: `runtime/lifecycle.py`, `test_lifecycle.py`, `admission.py`,
  `handover.py`, `operations.py`, `test_operations.py`, `root.py`.
- Adapter manifest: `run.py`, `test_run.py`, `web/app.py`, `schemas.py`, `services.py`,
  `test_lifecycle.py`.
- React/harness manifest: `frontend/src/components/{archive-panel.tsx,archive-panel.test.tsx,
  lifecycle-actions.tsx,lifecycle-actions.test.tsx}`, `pages/{mandates,paper,research}.tsx`,
  `frontend/e2e/lifecycle.spec.ts`, `e2e/run-owned.mjs`, `playwright.config.ts`.
- Documentation: governance contract, this evidence, tasks and retired-assertion inventory.
  The existing 17 synthetic desktop/narrow screenshots were regenerated by the final
  owned route workflow. No TUI source, dependency, module or assertion was removed.
  Screenshot identity at `2026-11-02T00:38:19.859133+01:00`: **17 PNGs / 2,857,154 bytes /
  SHA-256 `f0e5cb3b583139e07d63a04501da9792dff7a87ff04fe8d35c6de4cac6551e9a`**,
  using the same full repository-relative path/content NUL-separated algorithm.

### Implemented criteria and deliberate limits

- Three distinct, reversible scopes: template YAML/YML, local-paper deployment directory,
  persisted research JSON. Root-relative no-replace file/directory rename retains history
  under the private archive store, never broad-deletes or changes a deployment snapshot.
- Registry-before-object lanes cover deployment, runner, execution, control and research;
  verified same-thread registry reuse avoids self-deadlock without trusting an unverified
  owner. Real child-process tests prove conflicting execution exclusion and independent
  object progress. Starting/unknown runner records block even when the OS lane is free.
- Enrollment and exact bytes/references/runner observations are rechecked under admission.
  Deployment inventory transition compares the target entry while retaining live enrolled
  siblings and verifying the full resulting inventory. Legitimate independent fund
  progress does not permanently strand an interrupted target archive.
- Single-use expiring operator-session-bound review, durable accepted-before-effects,
  idempotent request replay and stale-state rejection remain in the common operation
  protocol. Host/Origin/CSRF/path/budget/paid-operation protections are unchanged.
- Restores reject exact/canonical collisions, preserve history and remain stopped, with
  no automatic tick, pending-decision replay, provider dispatch or linked replacement.
- Prepared, accepted-before-journal and final-journal/completion gaps have deliberate
  recovery. Retained journals atomically record exact reconciled operation IDs, including
  recovery itself. An unprepared restore can be closed against intact archived bytes
  without overwriting a newly occupied destination.
- Unprepared deployment recovery permits only forward canonical history with the same
  fund-file digest, nondecreasing session count and exact retained prior-session hash.
  It binds current source bytes/head to a new explicit review; newer sessions survive.
  Changed templates/reports, changed deployment snapshots/history and unknown archive
  destinations remain manual-review. Missing records alone never establish safe recovery.
- GET list/inspect do not reconcile or mutate. Per-record unsupported recovery is visible
  as `manual-review` plus an error, leaving independent records usable. Root/ownership/
  storage errors still fail closed globally. React hides unsafe actions but the backend
  independently denies them.
- Retained offline CLI list/inspect/preview/archive/restore/recover use the same service,
  source hash and request protocol without importing TUI/providers. Explicit-root paper
  commands no longer fall back to an unenrolled legacy writer.
- Enrollment/attestation and OS lanes still fence cooperating writers only. They do
  **not** establish verifiable exclusion of old executables, writable containers or
  arbitrary filesystem writers. The governance note explicitly preserves A3.

### Fresh measurements

| Timestamp / scope | Command and observed result |
|---|---|
| Final candidate, `2026-11-02T00:26:45.001715+01:00` to `00:45:00.948896+01:00` | Cached Python `-m pytest hedge_fund -q --tb=short`: **1617 passed, 42 skipped, 0 failed in 938.29 s**, process exit 0 after fixture cleanup. Exact 23-path code/test identity printed immediately before invocation and rechecked unchanged after the final browser runs. Includes all co-located runtime/web/CLI, guards, adjacent writer and TUI regressions. |
| `2026-11-02T00:04:15.716589+01:00` to `00:06:02.841631+01:00` | New crash-boundary selection initially **1 failed, 9 passed**; durable deployment payload is deeply frozen, so a nested mapping was not a dict. Fallback now uses the operation's thawed public payload. |
| Subsequent discriminating selection, before final panel closure | `pytest web/test_lifecycle.py runtime/test_operations.py -k 'before_or_after or missing_journal or prepared_move or legitimate_new_sessions or accept_persists'`: **10 passed, 53 deselected in 100.58 s**. |
| `2026-11-02T00:22:41.972043+01:00` to `00:24:26.174306+01:00` | `npm --prefix frontend test -- --run`: **5 files / 34 passed in 45.36 s**; `npm --prefix frontend run build`: TypeScript passed; Vite 2,309 modules, 21.37 s. Non-fatal large-chunk advisory remains. Final React code/test identity matches the candidate above. |
| Final per-record/collision selection, ended `2026-11-02T00:26:23.909047+01:00` | `pytest hedge_fund/web/test_lifecycle.py -k 'missing_journal or prepared_move'`: **5 passed, 19 deselected in 68.50 s**. |
| `2026-11-02T00:26:39.809031+01:00` to `00:28:07.148199+01:00` | `node e2e/run-owned.mjs --lifecycle lifecycle.spec.ts`: **1 passed in 36.6 s**, real workflow 30.5 s. Six real API archive/restore mutations across all three scopes; stale template confirmation denied; deployment snapshot/head preserved and restore stopped. No `page.route` response fakes. Followed by owned `desk.spec.ts --grep 'production routes render'`: **1 passed in 12.7 s**, desktop/narrow routes and no external requests. Both include fresh TypeScript/build. |
| Same final two browser builds | **3 files / 984,294 bytes / SHA-256 `f5448fd39c8ff2057e4505d0e41f04cfc036f72556586d288be2cc7ebfa95014`**. JS `index-CSg9ctmY.js`. The earlier `c4049a95...` bundle is superseded, not final evidence. |
| `2026-11-01T23:58:59.933605+01:00` to `23:59:27.339732+01:00` | Node harness safety **6 passed**; prior frontend 33 passed/build also green, superseded by final 34-test/build rows above. Harness source unchanged afterward. |
| `2026-11-02T00:36:46.494849+01:00` to `00:36:49.211129+01:00` | Black check, isort check, configured flake8 (`--max-line-length=420 --extend-ignore=E203,W503`) over all **13 changed/new Python files**, plus `git diff --check`: exit 0. |

### Review-driven repairs and failed attempts

- Initial independent `qa-reviewer` identified missing lifecycle implementation,
  lock order/reuse, unsafe directory rename, runner-starting gap and writer-enrollment
  limitations. Execution specialist left partial runtime work before a provider-policy
  failure; the parent completed it directly. Separate adapter specialist completed
  web/CLI wiring and adjacent tests. There was no repeated implementation delegation.
- Final independent `qa-reviewer` inspected the current runtime/adapters/React diffs across
  at most three bounded repair cycles. Final closure response: **PASS for the listed
  closures**, static only, no test execution or source-hash attestation by that reviewer.
  Parent-recorded candidate identity and measurements above supply that separate evidence.
- Reproduced red before repairs: abandoning a prepared archive lost its only journal and
  permanently blocked later archive/restore; recovering one deployment rejected a
  legitimately advanced independent fund; completion-gap and unprepared interruptions
  could strand operations; canonical restore collisions were not denied during review.
- Discriminating timestamp regression: after a synchronous worker moved to RUNNING at a
  later timestamp and raised, launch fallback reused the earlier accept timestamp.
  `_set_interrupted` failed journal validation and its caller left RUNNING. New operation
  test was **1 failed / 1 passed** before fixing the timestamp to
  `max(now, operation.updated_at)`. It now fences and interrupts rather than replaying.
- A misplaced multi-hunk edit temporarily broke service syntax and backtest-call
  parentheses. Exact surrounding code was restored; subsequent import, lifecycle, full
  suite and real browser checks exercise the corrected code. No claim uses that attempt.
- Per-record recovery test first used a research decoy with the **same fund identity**.
  The expected independent restore was correctly blocked by its subject lane. Fixture
  was corrected to a genuinely independent report/fund identity; final five-case run
  above passed. Same-subject exclusion was not relaxed.
- An earlier full-suite attempt reported **1 failed / 1603 passed / 42 skipped in
  732.40 s**: a synthetic paper-redo `os.replace` raised Windows WinError 5. The complete
  adjacent tick module immediately passed **40 tests in 5.14 s** without source changes.
  No speculative production retry was added. A later pre-panel-closure full suite passed
  **1616 / 42 skipped in 876.85 s**, but is not substituted for final-candidate evidence.

### Remaining migration gates

Cleanup: owned browser processes exited and port 8876 was verified released at
`2026-11-02T00:43:28.088774+01:00`; no marked test roots remained. One older failed-run
residue was removed only after verifying its exact exited pytest PID 49652 and
`.test-owned` marker, using `cleanup_test_root` on that single resolved fixture.
No other session process, checkout, preview or the worktree itself was removed.

- T015: verified exclusion of unaware/out-of-band writers, not merely operator attestation.
- T021/T138 and T027: exhaustive direct-writer/CLI/web/runner/manual/redo/lifecycle race
  matrix; all cooperating writers under sustained contention. Long lifecycle digest
  holding the registry versus an independent runner's bounded head-recording wait remains
  **INCONCLUSIVE**, not a proven independent-fund throughput guarantee.
- Production-root enumeration with protected deployments currently fails closed. This
  synthetic slice is not authorization to enable mutation on any existing live root.
- FR-043 linked new-identity replacement/redeployment, complete US4 and remaining
  Spec005 story parity. No task count increase or TUI retirement follows from this slice.
- Current-source bare-metal Linux/native lifecycle acceptance and wheel/container/
  installed-artifact gates; historical native/smoke rows are not current artifact proof.
- T019/T020 envelope gaps, full browser/visual parity, final packaging and TUI removal
  remain open. No merge or complete-migration claim.

## T019 / T020 error-envelope and reconnect recovery slice (2026-11-02)

**Status: implemented bounded slice; T019/T020 remain unchecked (PARTIAL). Migration remains 20/148, NOT READY TO MERGE.**

### Candidate and isolation

- Verified base and remote PR8 head before work and before publication: `89e0b49bb9cee2d7aaeb44a125e128acfbcce296`
  (`origin/cgjedrem-vigilant-robot`); publication is a non-force push to that branch, no duplicate PR or merge.
- Code/test identity captured `2026-11-02T02:34:28+01:00`: **`492ce48e005eab554c625e838a5ddb55d990b62dbc30e3ef546ce4c4c73281f0`**,
  **30 paths / 779,905 bytes** (sorted repo-relative paths, NUL, staged blob bytes, NUL; docs/screenshots excluded).
  Every staged blob was compared with the working tree (CRLF->LF normalization only) and matched.
- Windows 11 / NTFS, Python 3.13.7 Poetry venv, Node/Vitest/Playwright Chromium; `PYTHON_DOTENV_DISABLED=1`, isolated synthetic roots,
  HOME/TEMP/provider/proxy/credential env cleared by the existing harnesses; loopback only. No live root, runner, credential,
  provider, LLM, paid or broker call; no other checkout/process (8765, 49292, PID 54644) touched.

### Behavior implemented (source)

- `schemas.error_payload`/`ErrorResponse`: optional `subject_id`, `request_id`, `current_head` echoed only when they fully match bounded
  opaque-token patterns (hostile values dropped); explicit `refresh_required`/`retry_policy` overrides validated against `RETRY_POLICIES`.
- Contract code->status table with `error_code_status_matches`; `halted`/`replay-corrupt`/`reconciliation-required` moved 409->423,
  request validation 422->400 `invalid-request`, stored-artifact readiness 422 `readiness-denied`; new codes `protected-root`,
  `unsupported-filesystem`, `private-storage-unverified`, `budget-exhausted`.
- Retry semantics: `writer-conflict` defaults to `inspect-status`; only pre-acceptance registry-lock `OperationBusy` (paper/lifecycle/operation
  accept) opts into `retry-later` with neutral wording ("this request was not processed now ... inspect its operation status first").
  A busy status read after a durable lifecycle transition returns the accepted record; busy replay of a known request is `inspect-status`.
  An unavailable operation store reads as 503 `observation-conflict`/`retry-read-only` (not 404).
- A mutation rejected for an absent/expired operator session (e.g. after server restart) returns 403 `reload`; Host/Origin/CSRF checks unchanged.
- Frontend: `ApiError` + `errors.ts` actionable guidance (Review again, Refresh status, Reload session, Reconnect; no retry for permanent faults;
  mutations never auto-resubmitted); `ConnectionBanner`; per-page recovery; connection epoch so a pre-loss response cannot report recovery;
  Reconnect issues a fresh capabilities read bounded to 10 s.

### Results (source-bound unless stated)

- Full Python suite (post all repairs): **1640 passed, 42 skipped, 0 failed in 1233.76 s** (skips: live-key smoke, Linux-only, FIFO).
  Only trailing blank-line removal in three test files followed this run.
- Targeted: `test_lifecycle.py` **25 passed** (254 s); `test_app.py` **43 passed**; paper accept fault matrix **3 passed**.
- Frontend Vitest (`npm test`): **5 files, 49 passed**; `npm run build` (tsc + vite) OK; e2e safety **6/6**.
- Owned real-API Playwright (runtime against the source-built static bundle, synthetic root, port 8876, no `page.route` fakes):
  `recovery.spec.ts` **3 passed in 4 consecutive runs**; `lifecycle.spec.ts` **1 passed**; desk suite **12 passed, 4 skipped**.
- Lint: changed-file flake8 and isort clean; Black failures only in `test_actions.py`/`test_settings.py`, identical at HEAD; `git diff --check` clean.

### QA cycles and failed attempts

- Initial independent QA: 3 findings (writer-conflict always `retry-later`; misleading reload guidance; missing store as 404 offering Forget). Repaired.
- First discriminating test for lifecycle busy-only retry vacuously skipped; rewritten to patch `OperationStore.get_by_request` so it exercises the path.
- Final QA 1: busy status read after durable transition misreported as nothing accepted -> fixed, new regression. Final QA 2: busy replay
  wording -> fixed. Final QA 3 (fresh reviewer): **no blocking findings**.
- Recovery e2e offline test failed 2 of 3 runs: a background read sent before the loss completed afterwards and flipped the banner online,
  and Reconnect could reuse a hung in-flight request. Fixed via connection epoch and fresh bounded reconnect; then 4/4 runs green.

### Open (keeps T019/T020 unchecked)

- No production site emits 429 `capacity-denied`/`budget-exhausted`; worker-capacity rejection occurs after durable acceptance and surfaces as
  409 `ownership-unknown`. Next: a pre-acceptance capacity check that preserves idempotent replay, plus its envelope regression.
- No observation stream/channel exists (polling only); T023 identity-aware polling and late-response rejection remain open.
- No current-source wheel/container/installed-artifact, bare-metal Linux or cross-browser evidence for this slice.

## T142 — verified owned-runner reattachment, fencing and stale-owner review (2026-11-03, PARTIAL)

**Status: implemented bounded slice; T142 remains unchecked (PARTIAL).**

### Candidate and isolation

- Started from PR8 head `07f6d8bdb2540db38d113eb62c9993a0736e1c19`; before publication the remote had advanced to
  `5e7b15e9bc81f6f4fa53e139b3dd256e316d0954` (6 commits incl. T145 runner restart-required summary, none touching runtime runner code; compatible: reattached runners now count as running instead of ownership-unknown); the slice was rebased onto it
  and re-verified. Non-force fast-forward push to `cgjedrem-vigilant-robot`; no duplicate PR or merge.
- Windows 11 10.0.26200 / NTFS, Python 3.13.7 isolated venv (`outputs/t142-venv`, gitignored). HOME/USERPROFILE/TEMP/APPDATA
  under a synthetic test home, `PYTHON_DOTENV_DISABLED=1`, provider/proxy/credential/`HEDGE_FUND*` env scrubbed, loopback only.
  Only synthetic enrolled roots and test-owned children (`sleep` stand-in or the real offline `owned_runner_child` in a closed
  market window). No live root, runner, watchtower/umbrella, credential, provider, LLM, broker or network call; ports 8765/49292
  and other checkouts untouched.

### Behavior implemented (source)

- `runtime/ownership.py`: `launch_command_digest` and `process_launch_fingerprint` — Windows: native command line via
  `NtQueryInformationProcess` + token user SID; Linux: `/proc` cmdline, euid and cwd.
- `runtime/owned_runner.py`: the launching manager writes a root-private `owner.json` (schema/protocol/build, root binding, fund,
  operation ID/digest, nonce hash, command and executable SHA-256, process incarnation, launch fingerprint, manager identity)
  only after verifying the launched child. A manager without the in-memory handle presents `running`/`stopping` only when:
  owner/launch/state/control records validate and agree (nonce, operation, root, command), the PID's incarnation matches,
  the native fingerprint matches, the image is the same executable (digest), this server holds a verified root-owner lease,
  and a `timeout=0` probe proves the runner reservation is held. Any mismatch → `unknown` (no attach, no stop);
  dead incarnation → `unknown` with offline `recover_stale_reservation` guidance. A same-nonce terminal record written while
  the owner exits during verification is presented instead of `unknown`.
- Stop is cooperative only (control `stop_requested`), fenced by `deployment_lock(timeout=0)`; busy/unobservable admission
  raises `RunnerOwnershipUnknown` (HTTP 409 `ownership-unknown`) with no control write. Nothing is signalled or killed by PID;
  public status payloads carry no PID.
- `runtime/handover.py` (pre-existing bug): stale-recovery creation compared `process_identity` host/namespace with the
  root's host-identity scheme, so a real child could never be recovered. Creation now checks against
  `ownership.process_identity(os.getpid())`; reads validate structure, root binding and digest only.

### Results

- Focused (final source, pre-rebase): `test_owned_runner.py`, `test_handover.py`, `test_ownership.py`,
  `web/test_paper_operations.py` — **58 passed in 255.32 s** (2026-11-03T02:16:36–02:20:57+01:00).
- Rebased on `5a41b2d`: `test_owned_runner.py`, `test_owned_runner_child.py`,
  `test_handover.py`, `test_ownership.py`, `web/test_paper_operations.py`, `web/test_app.py`, `web/test_reports.py` —
  **137 passed in 502.05 s** (2026-11-03T02:21:26–02:29:54+01:00).
- Final, rebased on `5e7b15e` (same suites + `web/test_settings_provenance.py`): **145 passed in 503.20 s**
  (2026-11-03T02:30:37–02:39:12+01:00).
- New unit coverage (`test_owned_runner.py`, 22 tests): restarted + parallel reattach and cooperative stop; reservation
  not held; PID reuse, foreign command, foreign fingerprint, replaced executable, nonce, operation, wrong root, missing owner,
  state identity, server command (10 tamper cases, control unchanged); crashed child → stale review; `starting` never adopted;
  read-only server unknown; stop fenced by deployment lock; admission `OSError` fail-closed; exact owner validator;
  fingerprint of exact child; terminal record during exit.
- Integration (`web/test_paper_operations.py`, real offline owned child, synthetic root): service A starts; parallel service B
  reattaches; A closes (simulated web restart); a fresh `create_app(...)` FastAPI TestClient reports `running` /
  reattached with no `pid`, CSRF-checked `POST /runner/stop` → `stopping` → `stopped`; child exits 0; ledger unchanged.
  Crash case: child killed through the test-owned handle → `unknown`/stale review, stop 409 with control unchanged,
  offline `recover_stale_reservation` → `failed`/`operator-stale-recovery`, ledger unchanged.
- Runtime + web suite (pre-review-fix source, under heavy concurrent load): **651 passed, 13 skipped, 4 failed in 3392 s**.
  Three failures (10 s import timeouts ×2, child preflight thread liveness) passed on isolated rerun.
  `test_actions.py::test_web_halt_does_not_wait_for_fund_work_lock` (1 s responsiveness bound) fails deterministically
  (6.3–7.8 s) on this machine **also on unmodified HEAD `07f6d8b`** — pre-existing/environmental, not caused by this slice.
- Lint: Black/isort applied to changed files; flake8 (repo line length) clean on changed lines; remaining Black drift in
  `handover.py` and E203 in `ownership.py` pre-date this slice. No UI change, so no TS build.

### Independent review

- Review 1: (Medium) admission `OSError`/`RootPathError` could escape as HTTP 500 → caught, fail-closed, regression test
  added; (Low) restart-test cleanup could leak a child → test-owned handle kill fallback.
- Final review: no production findings; one test-harness cleanup issue (stop raising skipped the kill fallback) → repaired;
  both integration tests re-run green.

### Open (keeps T142 unchecked)

- Integration with the canonical headless runner upgrade path and native owned-child fake-canonical completion not proven.
- Windows verifies command line, token SID, creation time, image path and executable digest; cwd and parent are recorded
  for audit but not verified. Linux path (cmdline/euid/cwd) has no native run in this slice.
- Depends on incomplete T015/T021; existing-root read-only uncertainty remains. No browser (Playwright) restart run — API
  restart proven through FastAPI TestClient only.

## T019 / T020 operation capacity and continuity slice (2026-11-03)

**Status: implemented bounded slice; T019/T020 remain unchecked (PARTIAL). Migration remains 21/148 at `c2d56a4` (T096 accepted upstream in `294f9db`; this slice checks none), NOT READY TO MERGE.**

### Candidate and isolation

- Base and remote PR8 head verified before and after work: `5f3f909c4f9151d531b571dd37bdebe368ee127c` (`cgjedrem-vigilant-robot`).
  Built in a separate worktree/branch (`cgjedrem-implement-t019-t020-recovery-gaps`); committed locally only, not pushed, pending
  reconciliation with the concurrent T021 writer-race work. No write-authority, admission, ledger, cache, handover or race-matrix file changed.
- Source/test identity (sorted repo-relative paths, NUL, staged blob bytes, NUL; `specs/` excluded): **`172ec10fc8e370d4e36e48674bf60e0e0e1023cc2aed4e7e02ebba1352f13fe5`**, **15 paths / 672,823 bytes**.
- Windows/NTFS, Python 3.13.7 (an existing project venv used read-only with `PYTHONPATH` bound to this worktree), Node/Vitest/Playwright with
  Edge channel. `PYTHON_DOTENV_DISABLED=1`, scratch HOME/TEMP removed after each run, credential/provider/proxy variables scrubbed;
  loopback only; synthetic roots and fakes only. Ports 8765/49292 untouched; the owned browser harness used 8876 and released it.

### Behavior implemented (source)

- `OperationStore.accept_request(capacity=(actions, limit))`: under the registry lock and after replay, preview, expiry and stale checks,
  counts root-wide unfinished records for the pool's actions; at the bound it raises `OperationCapacityExceeded` before any record is
  written (preview stays issued, token unconsumed). Limit is validated as an integer 0..16 over a non-empty action set.
- `OperationJobRegistry`: `try_reserve`/`release`/`submit(reservation=)` reserve an in-process worker slot before acceptance; startup
  recovery refuses while slots are reserved. Records this process accepted but could not start or settle (status-read, start, interrupt,
  fail or acknowledgement write failures) are tracked and re-interrupted by `reclaim_stranded()` at the next successful reservation;
  active and foreign records are never touched.
- Services: backtest pool capacity 1; paper tick/runner-start shared pool capacity 2. Either bound denies with 429 `capacity-denied` /
  `retry-later`, `Retry-After: 30` and `retry_after_seconds: 30`, echoing subject and request. A replay of an accepted request still
  returns its record at capacity.
- Schema: `retry_after_seconds` allowed only on 429/503 for `capacity-denied`, `budget-exhausted`, `observation-conflict`,
  `assets-unavailable`, integer 1..300; omitted otherwise. The handler mirrors it into the `Retry-After` header.
- Frontend: `ApiError.retryAfterSeconds` (body first, header fallback, out-of-bound ignored), capacity guidance with the advisory wait,
  and `isPreAdmissionDenial` releasing a pending identity only for 410 `expired-confirmation` or a same-request echoed 429
  `capacity-denied`. No automatic resubmission. Existing polling (single in-flight read, 10 s timeout, abort on unmount, late
  identity/cursor rejection, bounded read retries) is unchanged.

### Results

- Focused Python (`test_jobs.py`, `test_app.py`, `test_operations.py`, `test_actions.py`, `test_paper_operations.py`) before the final
  review fix: **204 passed in 760.22 s**. After the fix: `test_jobs.py` + `test_paper_operations.py` + `test_operations.py` **117 passed in 563.55 s**; `test_app.py` **50 passed in 9.06 s**; `test_actions.py` was not rerun after the jobs-only fix.
- Frontend `npm test`: **7 files, 110 passed**; `npm run build` (tsc + vite) passed; `npm run test:e2e-safety` 0 failures.
- Owned real-API Playwright (`node e2e/run-owned.mjs --lifecycle`, port 8876, synthetic root; `page.route` only aborts non-origin
  traffic): full run **9 passed, 6 failed, 2 did not run**. The same 6 failures occur identically at the unmodified base
  `5f3f909` in this environment: lifecycle/mandate preview returns `writer-conflict` / "writer admission is unavailable" on the
  harness demo root, a write-authority precondition outside this slice. Targeted rerun of lost-session renewal, server-loss
  reconnect, stale-head tick rejection and running-operation reload restore: **4 passed**.
- Style: changed-file Black/isort/flake8 (max line 420) findings equal to `HEAD` per file after isort repair; `git diff --check` clean.

### Reviews and failed attempts

- Initial independent review: one medium finding (own unsettled record held the durable bound until restart) -> stranded tracking and reclaim.
- Final independent review: one medium finding (a `submit` failing before activation left an ACCEPTED record unreclaimed) -> stranded on
  status-read and capacity/history refusal, with a regression test. No other findings.
- First Vitest run failed 9 App tests because some fetch fakes lack `headers`; header read is now guarded. First build failed on the option
  type (header string); fixed.

### Open (keeps T019/T020 unchecked)

- No production site emits 429 `budget-exhausted`.
- Records orphaned by a crashed other process hold capacity until server-start recovery (fail-closed). `Retry-After` is advisory.
- The capacity 429 is proven at the HTTP/app level, not browser-driven: demo work cannot be held deterministically without a production hook.
- No observation stream/channel (polling only). Full Python suite, wheel/container, Linux and cross-browser evidence not run for this slice.

## T019 / T020 capacity integration onto PR8 head (2026-11-03)

**Status: integrated bounded slice; T019/T020 remain unchecked (PARTIAL). Migration remains incomplete, NOT READY TO MERGE.**

### Integration

- Remote `cgjedrem-vigilant-robot` verified at `16369e9ee93801a2ef7abcd3b02604f1c3b12866` before integration; merge-base with the
  reviewed local commit `13edce3` was `5f3f909`. `git cherry-pick 13edce3` applied with **no conflicts** (19 files) as `bb9aeb3`;
  original commits preserved. Report/session/settings features from `16369e9` are untouched; the shared operation identity/table
  was not changed or duplicated (capacity counts the existing registry records).
- Budget decision: no production 429 `budget-exhausted` emitter. `DispatchBudget` is a per-operation reservation taken after
  acceptance with no cumulative cap or reset window, so no truthful per-operation cap or `Retry-After` exists; fail closed by not
  inventing one.
- Source/test identity of the integrated change vs `16369e9` (sorted repo-relative paths, NUL, staged blob bytes, NUL; `specs/`
  excluded): **`fc044af5d15fa1fdee82368fde6c10b94340780bebfa589e928074db0a496627`**, **20 paths / 733,887 bytes**.

### Added in the integration

- `test_jobs.py`: a record durably accepted by a separate (crashed) store holds the backtest pool on a live server (429
  `capacity-denied`, record stays `accepted`); only a restart's verified recovery interrupts it (fence +1), after which writes are
  enabled and a new acceptance completes. A corrupted orphan capture sidecar makes startup recovery fail closed (writes disabled,
  `operation-recovery-unavailable`, operation store absent) and leaves the record `accepted`; restoring the exact bytes lets the next start recover it (writes on, `interrupted`). Process absence never frees capacity on a running server.
- `hedge_fund\test_support\capacity_holder.py` (test-only): holds/releases one durable backtest slot from a second process; refuses
  unless `HEDGE_FUND_TEST_MODE=1` and the root is inside the marked owned test root; release only interrupts its own holder record.
- `frontend/e2e/capacity.spec.ts` + owned `--capacity` mode (`run-owned.mjs`, `playwright.config.ts`): runs alone with
  `--demo --allow-writes --enable-network` (capability only; the test-child guard still refuses all non-loopback sockets) and only
  this spec. Real API, no `page.route` fakes. Holds the slot from the holder process, drives one browser Accept to 429 with
  `Retry-After: 30` and `retry_after_seconds: 30`, verifies "Nothing was accepted or started" guidance, exactly one mutation POST,
  by-request lookup 404 and released pending identity; then reloads onto the held operation, goes offline, releases the hold,
  reconnects via "Inspect status" (read-only GET) and observes `interrupted` with no new mutation and no external request.
  Browser-level server restart is not driven (fixed harness web server); restart recovery is proven at TestClient level.

### Results (Windows/NTFS, Python 3.13 Poetry env under `outputs\`, synthetic roots, dotenv off, credential/proxy env scrubbed)

- Pytest `runtime\test_operations.py`, `web\test_jobs.py`, `web\test_app.py`, `web\test_paper_operations.py`, `web\test_reports.py`,
  `web\test_settings_provenance.py` (`-x`): **185 passed in 1132.59 s**. `web\test_main.py` + `web\test_actions.py` + the two new
  orphan tests: **50 passed, 1 failed in 622.42 s**; the failure `test_actions.py::test_web_halt_does_not_wait_for_fund_work_lock`
  fails identically at unmodified `16369e9` (pre-existing, outside this slice). New orphan tests alone: **2 passed**.
- Frontend `vitest run src`: **9 files, 122 passed**; `tsc --noEmit` passed; `npm run test:e2e-safety`: **9 passed**; the harness
  build (vite) passed. ESLint has no repository config (not a gate). Python black/isort/flake8 (line 420): no new findings
  (`runtime\test_operations.py` black drift pre-exists at `16369e9` and `5f3f909`).
- Owned Playwright (port 8876, Chromium): `--capacity` **1 passed (1.0 m)**, rerun after review fixes **1 passed (29.3 s)**; orphan pytest pair after fixes **2 passed in 63.30 s**; default **11 passed, 3 failed, 6 skipped**;
  `--reports` **11 passed, 3 failed, 6 skipped**; `--lifecycle` **10 passed, 7 failed, 1 skipped, 2 did not run**. Comparison on a
  temporary detached `16369e9` checkout (removed afterwards): default desk spec **9 passed, 3 failed** (same three: manual tick
  running, runner stop, backtest running); `--lifecycle` **10 passed, 7 failed, 2 did not run** with the identical failing set
  (lifecycle, stale lifecycle review, operation receipts, report clamps JSON, the same three desk tests). These are pre-existing;
  lifecycle denials surfaced as `writer-conflict` or `reconciliation-required` depending on run. The earlier unreproduced
  "9 pass / 6 fail / 2 not-run" claim is superseded by these counts and is not a pass.

### Open (keeps T019/T020 unchecked)

- No production 429 `budget-exhausted` emitter (by decision above). No observation stream/channel (bounded polling only).
- Crashed-process orphans hold capacity until verified server-start recovery; no live reclamation. `Retry-After` is advisory.
- Startup recovery (pre-existing) interrupts every unfinished record on the root after sidecar verification; under the shared owner
  lease it does not prove owner liveness, so a live peer process sharing the root would also be fenced (in-flight work lost, no
  durable effect). Exclusive-lease or liveness-proof recovery is open.
- `--capacity` runs with writes and network capability, but the owned server's test guard is restricted to its own loopback port
  (see "Capacity browser model-endpoint lockout" below), so even a regressed 429 cannot reach a local model endpoint.
  `hedge_fund\test_support\*` (including the guarded holder) ships in the
  wheel like the existing test-support modules; packaging exclusion is open.
- Browser server-restart observation, the pre-existing desk/lifecycle browser failures, full Python suite, Linux, wheel/container
  and cross-browser evidence remain open.

### Remote advance during publication (incorporated by rebase)

- At the pre-push recheck, `cgjedrem-vigilant-robot` had advanced `16369e9` -> `5a41b2d` (`d008101` report evidence docs,
  `294f9db` T096 fake SIM account binding, `5a41b2d` paper session day grouping). The three slice commits were rebased onto
  `5a41b2d` (no force, original commits' content preserved). Only conflict: `implementation-progress.md` (both new log lines kept);
  `frontend/src/pages/paper.tsx` auto-merged.
- Integrated identity vs `5a41b2d` (same hash method, `specs/` excluded): **`a82dd750fff6f2a3629ad45cdbf36d5c6df4a187613382af24748dfef20d22f5`**, **20 paths / 733,337 bytes**.
- Fresh reruns on the rebased source: pytest `brokers\test_account_binding.py`, `web\test_paper_operations.py`,
  `web\test_app.py`, `web\test_main.py`, `web\test_jobs.py` **163 passed in 762.01 s**; Vitest **11 files, 161 passed**;
  `npm run build` (tsc + vite) passed; harness unit **9 passed**; owned `--capacity` **1 passed (34.0 s)**; owned default
  **10 passed, 4 failed, 6 skipped** -- the 4 failures (paper session history "No verified sessions", manual tick running, runner
  stop, backtest running) reproduce identically on an unmodified temporary `5a41b2d` checkout (desk spec **8 passed, 4 failed**),
  so they are pre-existing at the remote head. `--lifecycle`/`--reports` modes were not rerun after the rebase (unchanged
  harness paths; prior results above). Recorded 2026-11-03T02:23:02.7079614+01:00.

### Second remote advance (incorporated by rebase)

- Before push the remote advanced again `5a41b2d` -> `b36da71` ("serialize reviewed operations and disable legacy backtest
  starts": async Web Locks `pending.remember` with abort/dismiss, `data/client.py` redaction, TUI backtest refusal). The four
  slice commits rebased onto `b36da71` with **no conflicts**. In `backtests.tsx`/`paper.tsx` the capacity catch path
  (`isPreAdmissionDenial` forgets the request identity only for 410 expired confirmation or a same-request 429 `capacity-denied`)
  now sits after the awaited, lock-serialized `remember`; unknown outcomes keep the identity and nothing is resubmitted.
- Integrated identity vs `b36da71` (same method, `specs/` excluded): **`9d0b51e31cea37b00c5df7e0ee4dc4cdb1c94d6b5d9dd0aba445c287a5689002`**, **20 paths / 752,031 bytes**.
- Fresh reruns: pytest `data\test_client_contract.py`, `tui\test_backtest.py`, `web\test_paper_operations.py`,
  `web\test_app.py`, `web\test_main.py`, `web\test_jobs.py` **153 passed in 669.33 s**; Vitest **12 files, 181 passed**;
  `npm run build` passed; harness unit **9 passed**; owned `--capacity` **1 passed (30.3 s)**; owned default
  **22 passed, 4 failed, 6 skipped** (same 4 desk failures as an unmodified temporary `b36da71` checkout: **22 passed, 4 failed,
  5 skipped**; the extra skip is the mode-gated capacity spec). One earlier head default run additionally failed
  `operation-coordination.spec.ts:137` (paper-tick two-tab lock); it did not reproduce in four subsequent head runs
  (2x isolated 12/12, full suite) nor 2x isolated on base -- recorded as an intermittent, unexplained flake, not a pass.
  Recorded 2026-11-03T02:38:56.7068875+01:00.

  ### Third remote advance (incorporated by rebase)

- The remote advanced again `b36da71` -> `c2d56a4` (`5e7b15e` T145 bounded restart-required, `2abf68f` T142 partial owned-runner
  reattachment, `c2d56a4` T142 evidence). Rebased; the only conflict was this file (both appended sections kept, upstream first).
  Semantic check: T142 reattachment and T145 runner summaries read **completed** `paper-runner-start` operations, while capacity
  counts only **unfinished** records, and server-start operation recovery is unchanged, so neither feature alters capacity accounting.
- Integrated identity vs `c2d56a4` (same method, `specs/` excluded): **`c096dff3ce1e1c9c88ae0e1c61cae9c9f3103a461fd4b66619090d27b894bd80`**, **20 paths / 762,535 bytes**.
- Fresh reruns: pytest `runtime\test_operations.py`, `runtime\test_owned_runner.py`, `runtime\test_handover.py`,
  `web\test_settings_provenance.py`, `web\test_paper_operations.py`, `web\test_app.py`, `web\test_main.py`, `web\test_jobs.py`
  **229 passed in 716.30 s**; Vitest **12 files, 184 passed**; `npm run build` passed; harness unit **9 passed**; owned `--capacity`
  **1 passed (21.9 s)**; owned default **22 passed, 4 failed, 6 skipped**, identical failing set on an unmodified temporary
  `c2d56a4` checkout (**22 passed, 4 failed, 5 skipped**). Black: only the pre-existing `test_operations.py` drift (also fails at
  `c2d56a4`); isort clean. Recorded 2026-11-03T02:53:59.9072361+01:00.

### Capacity browser model-endpoint lockout (post-publication review fix)

- Defect: the network-capable `--capacity` server allowed every loopback connect, so a regressed 429 could let the single browser
  Accept start a demo backtest that reaches a local loopback model endpoint (e.g. default Ollama `localhost:11434`).
- Fix: `network_guard.install_network_guard` honours `HEDGE_FUND_TEST_LOOPBACK_PORTS` (comma-separated ports; any invalid value
  fails closed, so the guarded child exits before running). When set, `connect`/`connect_ex`/`sendto`/`create_connection` to
  loopback are refused unless the port is listed; only the in-process `socket.socketpair` fallback (Windows asyncio self-pipe) is
  exempt. `run-owned.mjs --capacity` strips any inherited value and sets it to the owned server port `8876`; `playwright.config.ts`
  refuses capacity mode unless it equals `8876` (and refuses the variable in other modes); `capacity.spec.ts` asserts it.
  Owned runner children keep `HEDGE_FUND_TEST_BLOCK_LOOPBACK=1` (no loopback at all).
- Tests: `test_acceptance_isolation.py` adds a guarded-child probe (allowed port connects; other loopback port, `localhost`, and
  `11434` refused via `create_connection` and `connect_ex`; `socketpair` and an asyncio loop still work) and 6 fail-closed invalid
  values: **57 passed in 7.28 s** (with `web\test_main.py`: **68 passed in 18.03 s**). Harness unit **9 passed**; Vitest **12
  files, 184 passed**; `tsc --noEmit` passed; owned `--capacity` **1 passed (18.0 s)** with the allowlist active; owned default
  **22 passed, 4 failed, 6 skipped** (same 4 pre-existing desk failures). flake8/isort clean; Black drift in the two touched
  Python files is pre-existing and unchanged in size. Recorded 2026-11-03T03:08:08+01:00.
- Review follow-up (MEDIUM): on Windows the asyncio `ProactorEventLoop` connects/sends via `IocpProactor.connect` (ConnectEx)
  and `IocpProactor.sendto` (WSASendTo), bypassing the `socket.socket` wrappers. The guard now also wraps those two methods with
  the same non-loopback denial and loopback-port allowlist (AF_UNIX exempt; `sendto` with no address passes through). The probe
  now asserts asyncio `open_connection` to the allowed port succeeds while the other loopback port, `localhost`, and
  `203.0.113.1:443` raise, and `loop.sock_sendto` to another loopback port raises. Rerun: `test_acceptance_isolation.py`,
  `web\test_main.py`, `runtime\test_owned_runner.py`, `web\test_jobs.py` **135 passed in 302.30 s**; harness unit **9 passed**;
  owned `--capacity` **1 passed (19.2 s)**; owned default **22 passed, 4 failed, 6 skipped** (same 4 pre-existing desk failures);
  flake8/isort clean, Black drift unchanged (20/20 lines). Recorded 2026-11-03T03:20:33+01:00.

## T021 writer map and deterministic race matrix slice (2026-11-03)

Status: PARTIAL. T021 and T015 stay unchecked. Base: PR #8 head
`d0081011b3c6428959d9759dda0aaa8189d16a61`. Environment: synthetic roots only, isolated
HOME/USERPROFILE/TEMP, `PYTHON_DOTENV_DISABLED=1`, and provider/token/proxy variables
cleared. No providers, brokers, network, runner processes or ports 8765/49292 were used.

### Writer map (source, not a static claim)

`hedge_fund\runtime\test_writer_map.py` AST-scans all non-test production modules for
these writes:

- path/os write primitives;
- `open` in write/append mode;
- `os.open` with create/write or non-literal flags;
- `os.fdopen` in write mode;
- root `rename_file`/`rename_directory`/`unlink_file`.

It fails on any unmapped or stale callsite and on any cited test node that does not exist.

After rebasing onto PR8 head `042cfbc`, the scanner flagged three new raw-write callsites from the per-user SIM account registry (`brokers\account_binding.py`: `AccountRegistry.initialize` mkdir/write_bytes and `AccountRegistry._locked` write_bytes) plus one renamed settings test node. They are now mapped: the locked state replace is race-level (barrier-started concurrent transfers admit exactly one; lock contention is busy without effects), and one-time initialization is denial-level only. The registry lives outside every fund root and is guarded by its own OS lock, not root admission.

The map has 106 entries:

| By level | Count |
| --- | --- |
| race | 48 |
| denial | 36 |
| none | 9 |
| primitive | 13 |

| By seam | Count |
| --- | --- |
| root no-follow | 36 |
| paper inventory transition | 13 |
| residual | 11 |
| paths helper | 11 |
| bound-root `write_atomic` | 9 |
| no-follow primitive | 13 |
| unenrolled legacy branch | 6 |
| denied entrypoint | 5 |
| bootstrap | 2 |

The residual/`none` set is pinned exactly:

- Saxo refresh lock;
- `Ledger.log_event` raw append;
- unbound `paths.write_atomic` fallback (`os.open`/`fdopen`/`replace`/`unlink`) and its bound
  `write_bytes`;
- `Ledger.init` `write_atomic`;
- `PaperBroker.restore`;
- explicit credential file;
- web demo/bootstrap mkdir.

Denial-level entries are not race evidence. POSIX no-follow primitives are mapped, but this Windows evidence host does not execute them.

### Deterministic race matrix (barriers, no sleeps)

`hedge_fund\runtime\test_writer_race_matrix.py` has 28 tests. Each one uses a monkeypatched
hook at an exact seam and makes event-ordered thread handoffs, plus a subprocess crash case.

- **Authority flip inside held lanes and transaction.** The flip is a legacy home alias or
  `runner.pid`, applied inside:
  - append and rewind;
  - deploy, both before the first effect and between mkdir, `write_bytes` and `write_text`;
  - `Ledger.init`, after its entry admission and before its effect recheck;
  - approval-clear;
  - audit;
  - after the rewind effect, before head publication;
  - after the lifecycle journal, before move;
  - before the lifecycle head transition;
  - between the mandate rename and the rewrite (exact 409 partial state).
- **Junction/link swap.** Swapping `ledger/superseded`, the ledger directory or the approval
  parent mid-transaction writes and removes nothing outside the root.
- **Lane conflicts.** A same-fund `WriterConflict` occurs while a transaction is paused, and
  an independent fund progresses while another fund holds its lanes.
- **Crash and restart.** A crash after the rewind rename leaves root-wide `LedgerDrift`, and
  every fund needs offline reconciliation.
- **No residue.** No legacy alias is left in the synthetic home.

Other new tests:

- `hedge_fund\runtime\test_root_unlink.py`: 9 tests of the no-follow unlink semantics.
- `paper\test_tick.py::test_redo_failure_with_unavailable_halt_requires_reconciliation_and_keeps_cause`.

### Fixes driven by the matrix

1. Paper ledger and deploy effects on enrolled roots go through `PaperInventoryTransition`
   effect methods (`mkdir`, `write_text`, `write_bytes`, `rename_file`, `unlink_file`). Each
   method rechecks write authority immediately before its effect.
2. Approval unlink uses the new `RootContext.unlink_file`, a no-follow primitive (POSIX
   `unlinkat` and Windows handle-relative delete).
3. Ledger-head records are published only after a final authority recheck. This fixes G1,
   where an authority flip during a rewind still published the head.
4. The raw rewind rename/unlink on enrolled roots is removed. This fixes G2, where a junction
   swap moved a record outside the root.
5. Lifecycle `_move` and `_write_index` recheck root ownership.
6. The web mandate update rechecks authority and returns 409 naming the partial state.
7. A redo failure followed by a failed emergency Halt raises `PaperReconciliationRequired`
   chained to the original error.

`PaperInventoryTransition.mkdir(..., ensure_base=True)` creates `paper/` on fresh roots.
Without it there was a deploy regression, found by the first matrix run.

Six existing `test_inventory_cache_race.py` tests hooked `ledger.write_atomic` for the record
write. That hook no longer sees enrolled record writes, so the tests silently stopped
exercising their interleaving and failed. They now hook the transition write via
`_after_record_write`, keeping the same assertions.

### Results (this candidate, uncommitted tree before commit)

| Run | Result |
| --- | --- |
| Writer map, matrix, unlink (143 after the second review round), `paper/test_tick.py`, `paper/test_ledger.py`, `paper/test_deployed_broker.py` | 305 passed |
| `runtime/test_inventory_cache_race.py` after hook retarget | 46 passed |
| Broad isolated run: `runtime`, `paper`, `brokers`, `fund`, `backtesting`, `web`, `test_run.py`, TUI paper/admission, `features`, acceptance isolation | 1378 passed, 13 skipped, 10 failed, 1 deselected |

In the broad run:

- The deselected test is the pre-existing baseline failure
  `test_admission.py::test_second_process_can_join_shared_root_participants`.
- 9 of the 10 failures were the stale hooks above; that file now passes.
- The 10th, `web/test_actions.py::test_web_halt_does_not_wait_for_fund_work_lock`, uses a 1 s
  wall-clock wait. It failed under heavy host load and passed 3/3 in isolation on both this
  tree and the d008101 baseline.

A full pytest was not rerun after the hook retarget. Lint is `flake8 --max-line-length 420
--extend-ignore E203,W503`, `black -l 420 --check` and `isort --check-only`, all clean on the
new and changed test files. Pre-existing non-black files were not reformatted.

### Reviews

- **Initial independent rubber-duck review.** Its findings were applied before the matrix.
- **Final independent code review.** It found no product bugs. It flagged map entries whose
  cited tests did not reach the claimed write, and `os.open`/`fdopen` writers the scanner
  missed. Both were fixed:
  - added the staged deploy flip test;
  - downgraded Ledger.init `write_atomic`, the helper `write_bytes` and
    `PaperBroker.restore` to `none`;
  - recited the legacy entries;
  - extended the scanner.
- **Second final review round, on the delta.** It confirmed the inventory hook retarget keeps assertion strength. It flagged two gaps, both now fixed:
  - `Ledger.init` mkdir was still only entry-denied, so a `_enrolled_root` flip test was added;
  - variable-flag `os.open` calls were missed, so the scanner now maps them (5 POSIX primitives).

### Open (keeps T021/T015 unchecked)

- No exhaustive every-writer race evidence: 34 entries are denial-only and 9 are `none`.
- `events.jsonl` append follows links; unbound `write_atomic` falls back to raw
  `os.replace`.
- There is no durable rewind intent, so crash drift is root-wide. The mandate rename+write is
  unjournaled.
- The POSIX `lstat`→`unlinkat` delete is not identity-fenced. The Saxo lock and explicit
  credential file are outside root admission.
- Same-account out-of-band writers are not fenced. The A3 decision (drift detection versus OS
  isolation) is unresolved, so production mutation stays disabled for legacy/attested roots.

Post-rebase verification (onto `042cfbc`, isolated temp HOME/USERPROFILE/TEMP, dotenv off, provider/proxy/token env removed, no network or ports): a combined suite of 21 files (writer map/matrix/unlink, inventory cache race, write authority, lifecycle, handover, admission, operations, paper tick/ledger/deployed broker/runner, account binding, research, fund storage, web services/actions/jobs/paper operations and `test_run.py`) gave **787 passed, 7 skipped, 0 failed, 1 deselected** (pre-existing `test_second_process_can_join_shared_root_participants`) in 31 min 18 s. Writer map after the rebase: **109 passed**. Full pytest was not rerun after the rebase. T021 stays PARTIAL.

Second rebase onto `9c5f491` (`bf541c5`/`9c5f491` touched only frontend e2e, `test_support\network_guard.py`, `test_acceptance_isolation.py` and this file; no production writer changed): evidence-doc conflict only. Writer map + race matrix + unlink + acceptance isolation: **203 passed** in 2 min 16 s.

## T021 admission slice: A3 exclusion gate, writer inventory and admission race matrix (2026-11-03, PARTIAL)

Status: PARTIAL. T021, T015, T019 and T020 stay unchecked. This slice complements the writer map above. Base: PR #8 head `14e1793`. Environment: synthetic `outputs/spec005-test-*` roots, isolated home, dotenv off, and provider/proxy variables scrubbed. Only fake providers were used, with no network, brokers or runners, and ports 8765/49292 were not touched.

### A3 decision (conservative)

Cooperative registry and OS locks do **not** prove that unaware or out-of-band writers from the same account are excluded.

- `runtime/exclusion.py` defines `out_of_band_exclusion_basis`. The only basis it recognises is `SYNTHETIC_TEST_OWNED`, which requires all of:
  - `HEDGE_FUND_TEST_MODE=1`;
  - a root strictly inside `<checkout>/outputs/spec005-test-*`;
  - a `.test-owned` marker;
  - no reparse points.
- `handover.write_authority` requires a basis. Every production root therefore reports `ownership-unknown` / `out-of-band-exclusion-unproven` and is read-only.
- Production mutation stays disabled until there is explicit proof of OS sandbox, account or ACL isolation.

### Changes

- **Hidden bypass removed.** Unconfigured `paths.write_bytes` and `write_atomic` calls that land under an enrolled root are now routed through that root's admission (`paths._write_in_root`), including through alias/junction parents. They no longer fall back to a raw write.
- **Raw mkdirs replaced.** The raw mkdirs in `PaperBroker.create`, `save_credential` and the owned-runner child were replaced, so the stale writer-map entries were removed.
- **Demo disabled outside the harness.** `aihf-web --demo` now fails closed outside the test harness with `DEMO_SEEDING_UNAVAILABLE`.
- **Synthetic enrollment guarded.** The shipped helper `test_support.enroll_synthetic_root` refuses to run unless the basis is `SYNTHETIC_TEST_OWNED`.
- **Writer inventory.** `runtime/test_writer_inventory.py` is an AST ratchet that classifies every production write site by admission class (`test_support/` is included). It now also classifies upstream's `PaperInventoryTransition`, ledger/deploy effects and POSIX unlink.
- **Admission race matrix.** `runtime/test_writer_admission_race_matrix.py` covers:
  - same-object contention with crash/cooperative release and retry;
  - independent-object progress;
  - a registry snapshot taken during an in-flight commit;
  - an authority flip while a lane is held (legacy alias, runner);
  - authority lost while waiting for the OS lock;
  - a production root being read-only;
  - the synthetic-basis binding;
  - unconfigured, alias and unusual-state routing;
  - Saxo lock rejection.
- **Upstream SIM-custody denial.** After the rebase, upstream's `14e1793` refuses unverified SIM custody before the write-authority check runs. The A3 binding test accepts either denial; its invariant (no custody call, no binding) is unchanged.

### Results (candidate `a5d6706`)

| Run | Result |
| --- | --- |
| Writer inventory + writer map | 109 passed |
| 16 affected files (both matrices, inventory, map, account binding, handover, inventory cache race, lifecycle x2, root unlink, write authority x2, paper tick, web main/app/paper operations), pre-rebase onto `14e1793` | 560 passed |
| Overlap set after rebase (ratchets, matrices, account binding + guards, write authority, `test_run.py`, deployed broker, tick) | 487 passed, 1 failed (stale message match, fixed), then `test_account_binding.py` 71 passed |
| **Full pytest `hedge_fund`**, clean detached worktree, nothing concurrent | **2391 passed, 51 skipped, 0 failed** in 2412 s; log SHA-256 `9b2dc30b466d54f7e0883802bda165e3d8be514a597dec151960565d0b720015` |

Earlier full-suite counts belong to superseded SHAs and are not evidence for this one. A previous full run at superseded `20f4df7` hit one intermittent failure: `web/test_paper_operations.py::test_owned_runner_readiness_timeout_fails_closed_and_stops_child`, raising `ProcessIdentityError` "command line unavailable" at launch. It passed 5/5 in isolation and did not recur here. It is recorded as an unexplained flake in the T142 launch path.

**Style follow-up (2026-11-03).** A review flagged an earlier changed-file Black failure (`black=1`) that was not rerun. Black was rerun with the locked `black==23.12.1`, using the repo `line-length = 420`, over every `.py` file changed since `5f3f909`:

- **Files the review cited:** `web/demo.py`, `web/__main__.py`, `web/test_main.py`, `test_support/handover.py` and `runtime/test_writer_race_matrix.py` all pass.
- **Two hunks introduced by this slice (`33b83cf`) are now fixed:**
  - the `run.py` paper-writer remedy expression;
  - the `runtime/handover.py` `WriteAuthorityDenied` message. Its text is unchanged; it was collapsed to one line.
- **Remaining drift is pre-existing:** Black still reports drift in 19 changed files, but a line-level `git blame` shows none of the lines it would rewrite come from this slice's commits. 18 of those files already fail at `5f3f909`. The other one, `runtime/test_inventory_cache_race.py`, came from upstream commit `b6a8a5b`.
- **Tests after the fix:** the affected run/handover/write-authority/writer-matrix/inventory/map tests gave **314 passed**.
### Reviews

- Independent read-only QA review of the rebased slice. It found no admission bypass and no A3 breach.
- Its findings were:
  - the demo crash outside test mode (fixed);
  - the unguarded shipped synthetic-enrollment helper (fixed);
  - no production-mode entry-point tests (a demo fail-closed test was added);
  - `write_runner_record` has no per-write authority recheck. This is unreachable in production under A3 and left open.

### Open (keeps T021 unchecked)

- **No production exclusion basis.** All production mutation is disabled, which is fail-closed and intentional.
- **Matrix scope.** The matrix exercises the shared admission primitives and paper lanes, not a per-domain race for every writer.
- **Ratchet blind spots.** The inventory does not see `os.fdopen` or an aliased `os.replace` (the writer map does scan `os.fdopen`).
- **Unchecked locations.** `write_runner_record` has no per-write recheck, and the location of `AccountRegistry.initialize` is not checked.
- **Upstream residuals from the writer-map section still apply:**
  - the `events.jsonl` append;
  - no durable rewind intent;
  - the unjournaled mandate rename;
  - the POSIX unlink fence;
  - the Saxo lock and credential file.
- **Historical demo smoke.** The 2026-11-01 wheel demo smoke predates A3. The demo now requires the test harness.

## T019–T021/T027 scoped continuation (2026-11-03)

**Partial, not migration acceptance.** T015 and T021 remain open because no
production exclusion basis exists. T019/T020 retain open dependencies and
coverage gaps; T024 remains blocked; T027 still lacks the complete real
CLI/web/runner/redo/archive and fill-race matrix. T023, T025, T026 and T028
were previously checked; this continuation does not change task markers.

| Field | Evidence |
| --- | --- |
| Source | Base `3c6553156acb1b0add94b3243c8df81416390963`; final dirty code/test diff Git blob `3dad693f6bc210b0a4e8af23f04ade4e4a0f74fd`, computed with `git diff --binary -- hedge_fund frontend \| git hash-object --stdin`. Documentation is excluded from that identity. |
| Environment | Windows 11 Enterprise build 26200, NTFS worktree; Python 3.13.7; Node 22.13.1; npm 10.9.2. Python tests use marked synthetic roots, isolated HOME/TEMP, cleared credentials/provider and proxy overrides, disabled dotenv, and the test harness's non-loopback network guard. |
| Execution | Direct source-run and frontend build by this session; no installed wheel, real fund, real provider/LLM, paid request or production writer was exercised. The cross-process tests start only harness-owned children. |
| Runtime bounds | Existing production roots remain read-only. Rechecks do not establish OS-account/ACL/sandbox exclusion and cannot undo already-issued effects. |

### Changes and observed targeted scenarios

- Valuation refresh now returns 429 `budget-exhausted` with no automatic retry
  hint when its operation-local dispatch budget is exhausted. A real guarded
  Yahoo session with fake underlying transport makes ten allowed attempts and
  denies the eleventh before fake I/O; no new valuation or paper-file change
  results. Earlier calls may have completed. This is not a global spend cap.
- Runner-record publication rechecks root write authority. A running synthetic
  runner now rechecks its owner before each new provider dispatch and fails
  instead of returning success if terminal status cannot be published. The
  three stop/legacy-marker/exclusion-loss variants passed in **22.70 s**;
  they preserve the pre-existing in-flight call but deny a subsequent dispatch,
  leave the ledger and last published runner state unchanged on revocation,
  and surface a runner error. Six record-write cases and two actual-child
  admitted-append cases cover both legacy markers and lost exclusion proof.
- A barrier-synchronized synthetic **real CLI plus HTTP web preview plus owned
  runner child** test denies both competing manual ticks, with no new session
  or paper-file change and no web provider construction. The final complete
  paper-operation file passed **19 tests in 243.31 s**, followed by five
  independent repeats of that race (all passed; **20.80, 21.34, 20.55, 32.25
  and 25.94 s**). A second real-child test passed in
  **10.05 s**: web Halt fences a CLI approval paused after pending mailbox
  publication, leaves no actionable verdict, records expiry against the
  original decision hash and leaves the ledger records unchanged. Neither
  test proves the complete domain-writer or duplicate-fill matrix.
- The manual preview now distinguishes an occupied lane (`writer-conflict`)
  from unknown ownership (`ownership-unknown`). The API contract documents
  that a pre-admission denial has no provider effect; a later failure cannot
  retroactively cancel earlier calls.
- Expected-red checks exposed the swallowed runner error, the missing
  dispatch exclusion check, and the generic conflict response. A broader
  isolated run on code/test diff `95ab0a246343c64fc825013e7f2ceeab9abbf4b5`
  returned **434 passed, 1 failed in 966.75 s**: the CLI exited before the
  race barrier, and that run did not capture the precise startup cause.
  Earlier, a separate attempt showed an admission denial during CLI startup;
  five diagnostic repeats and a full paper-operation run then passed. The
  final test stages CLI startup and its real manual-lane barrier before
  launching the owned runner, captures any startup error, and does not retry
  the mutation. Only test sequencing changed after the broader run; its
  failure is not counted as a full-suite pass.

### Frontend and style

- With isolated HOME/TEMP, cleared credentials and proxies, disabled dotenv
  and offline npm, `npm test`: **13 files, 214 tests passed**, Vitest duration
  **79.04 s**, start 2026-11-03 15:33:10 local. `npm run build`: TypeScript
  check passed; Vite transformed **2,317 modules**, built in **33.16 s**, exit 0. The
  1,008.95 kB minified JavaScript chunk triggered Vite's non-fatal size warning.
- Source-built static artifacts: `index.html` 468 bytes, SHA-256
  `47ca1603c73c327d3ad74adc1b666a9b23f34a7038d572e9ec44313e49877375`;
  `index-B_xGBpOx.css` 25,746 bytes,
  `83c2733e73c333dc782921d45d87f8b339369492ecfd925dad7e9f76a6b5e604`;
  `index-B2Az4k56.js` 1,008,953 bytes,
  `429c17a09721ed4b77bef0c087e8a10cc21b2c8de6f1b9cb3bd3eb3b53259c54`.
  This build does not constitute installed-artifact acceptance.
- The owned, network-disabled browser fixture built three files (1,035,167
  bytes, aggregate SHA-256
  `bbfbf686c1b100e976c5c9be0ed6c7592e82de93febc88ef48deb865c28dee14`)
  and used loopback port 8876. Three real-API recovery scenarios passed in
  **18.4 s**: stale lifecycle review, operator-session renewal without
  resubmission, and read-only reconnect. The server process and fixture root
  were absent afterward. An initial broader filename match also ran
  `operation-recovery.spec.ts` concurrently: one test passed, the stale-review
  case failed with mandate writer admission unavailable, and two serial
  cases did not run. The three-case one-worker rerun above passed; the first
  run is not counted as a pass and the exact cause of its contention is not
  independently proven.
- Black changed-line checks and the other changed Python files passed;
  isort passed on the baseline-clean changed files; flake8 with a 420-character
  limit and `git diff --check` passed. Full-file Black flags pre-existing formatting
  in `owned_runner_child.py` and `test_actions.py`; isort flags a pre-existing
  import layout in `test_writer_races.py`. Each was also verified at the base
  revision and is not attributed to this continuation.

## T027 synthetic admission and fill-race continuation (2026-11-03)

**Historical partial result, not foundation or migration acceptance.** No task
checkbox was changed. At this revision, T027 gained actual synthetic fill
coverage, but the archive/redo case stopped after CLI redo admission and before
redo effects; the owned-runner conflict had no due session. The executed-redo
follow-up below supersedes that scope, but T024 and the runner due-session
race remain open.

| Field | Evidence |
| --- | --- |
| Source under test | Published base `92b6a42d4e9af576b8ebd23ed000c59d5600cc06` plus the dirty `hedge_fund\runtime\test_writer_races.py` test blob `0bbd8de2d1e0c3bf9257bfaf1fa228539a01786d`; its `git diff --binary` blob is `0073a505800c95b500f51528b246b3f449d74fb9`. No production code or frontend changed in this continuation. |
| Environment and isolation | Windows 11 Enterprise build 26200, NTFS; Python 3.13.7; test-owned synthetic roots and children, isolated HOME/TEMP, cleared credentials/provider and proxy overrides, dotenv disabled and non-loopback network denied. Fake data and fake analysts only; no real fund, provider, LLM or paid call. |
| Runtime bound | Existing production roots remain read-only. These tests do not establish OS-account/ACL/sandbox exclusion, an installed artifact, or protection against a non-cooperating writer. |

- A real CLI child held the manual admission for `paper tick --again`. The
  reviewed HTTP archive was rejected with 409 `writer-conflict`, produced no
  durable operation, and left the original paper bytes and its recorded
  100-share AAPL fill unchanged. The child was released and intentionally
  stopped **before redo effects**; the same reviewed archive then completed,
  and restore reproduced the original paper bytes and fill.
- An engine-generated, hash-approved pending decision on a second synthetic
  fund was advanced by a real CLI child using a fake data-client factory and
  fake analyst. While it held manual admission, a second CLI tick failed
  with a busy denial and an HTTP preview returned 409 `writer-conflict`
  without constructing a web data client or altering paper bytes. The winner
  recorded exactly one 500-share AAPL buy, one new session and the event
  sequence `tick, approve, consume, tick`; its broker cash/positions matched
  the ledger and the approval mailbox was cleared. The fake factory does not
  exercise live provider transport or dispatch authorization.
- An accepted fake backtest occupied its bounded worker while another real
  test-owned process held the fund's research lane. A second backtest
  admission returned 429 `capacity-denied` with no request record. Hash-bound
  HTTP approval and Halt succeeded without changing existing session records
  or fills; the backtest was cancelled before fake price fetch. In the final
  combined run, verdict took **0.866 s** and Halt **0.588 s** end to end.
  The test's bound is `MAX_CONTROL_WAIT_SECONDS + 5` seconds; the configured
  0.5-second control lock wait is not an end-to-end HTTP latency guarantee.
- The three new cases ran together three times before the final mailbox,
  event and exact-session assertions: **3 passed in 28.95, 28.64 and 29.07 s**.
  On the final dirty test blob above, the entire writer-race file plus the
  adjacent owned-runner conflict, CLI approval/web Halt, capacity,
  cancellation and stale-archive tests gave **20 passed in 137.23 s**,
  2026-11-03 16:13:37–16:15:56 local, exit 0. Two preceding combined runs
  gave **20 passed in 146.26 and 142.12 s** on earlier test revisions. These
  are synthetic source-run tests, not native deployment or browser acceptance.
- Development failures are retained: the first saturation fixture hit the
  non-loopback DNS guard even with a fake transport, so it was changed to
  cancel before provider dispatch without weakening the guard. The first
  real-fill fixture used a fake `get_prices` signature incompatible with
  `CachedDataClient`; the next used a demo decision rejected by canonical
  eligible-score validation. The fixture was replaced with a canonical
  engine-generated decision. A missing `schema_version` then failed setup;
  that failure exposed a Windows locked-file cleanup error because the
  service was not yet covered by teardown. A finalizer and the required
  schema version fixed the fixture, and the single abandoned synthetic root
  was inspected and removed. These were test-fixture failures, not evidence
  of a production repair.
- On the final test blob, Black (`--line-length 420`), isort (Black profile,
  line length 420), Flake8 (`--max-line-length=420`) and `git diff --check`
  passed. The earlier frontend and browser evidence above remains historical;
  they were not rerun for this test/documentation-only continuation.

## T027 executed-redo/archive follow-up (2026-11-03)

**Partial, not foundation or migration acceptance.** On the same approved
synthetic fund from the prior fill race, a real CLI child was released after
holding redo admission and actually completed `paper tick --again` with a
fake data factory and fake analyst. While it held the lane, a reviewed HTTP
archive returned 409 `writer-conflict`, produced no operation record and
left paper bytes unchanged. The redo restored and re-executed the original
approved 500-share AAPL buy: the active ledger still has exactly two sessions
and one fill, the prior record is retained once under `superseded`, the
broker book matches the redone ledger, and the original approval was consumed
only once. Its new head makes the old archive preview stale; retrying that
review returns 409 `stale-preview` with no operation.

| Field | Evidence |
| --- | --- |
| Source under test | Published base `688c58768628604936caff287996684fb50171e7` plus dirty test blob `29df203679834006e9bb1418f90b2b53a39f0e55`; `git diff --binary` blob `6474a58782ff72e712c79f715b12c34e754c4cd0`. No production code or frontend changed. |
| Environment | Windows 11 Enterprise build 26200, NTFS; Python 3.13.7; test-owned roots/children, isolated HOME/TEMP, credentials/provider and proxy overrides cleared, dotenv disabled and non-loopback network denied. No real fund, external provider/broker or paid/LLM call was used. |
| Focused results | Initial pass **1 in 22.03 s**; three independent repeats **1 in 21.60, 23.52 and 21.51 s**, all exit 0. |
| Combined result | The writer-race file plus the adjacent owned-runner conflict, CLI approval/web Halt, capacity, cancellation and stale-archive tests: **20 passed in 150.05 s**, 2026-11-03 16:23:10–16:25:42 local, exit 0. Saturated HTTP verdict was **1.462 s**, Halt **0.540 s** end to end; these are not guarantees for arbitrary storage or scheduling. |
| Style | Full-file Black and isort at 420 characters, Flake8 at 420 characters and `git diff --check` passed on the test blob. |

The separately tested real owned-runner conflict still has no due session and
does not execute a fill. T024's foundation prerequisites and production
out-of-band exclusion remain open, so T027 and the other incomplete tasks
stay unchecked; no full migration, installed-artifact or production
acceptance is claimed.

## T027 owned-runner fill and completed-lifecycle follow-up (2026-11-03)

**Partial, not foundation or migration acceptance.** This section supersedes
the preceding statement that the owned-runner race has no due session. No
task checkbox changed: T024's prerequisites and production out-of-band writer
exclusion remain open, so T027 stays unchecked.

| Field | Evidence |
| --- | --- |
| Source under test | Base `9c4602d35f618ee8c91a3a5baa100162c5cedd88` plus dirty blobs: `hedge_fund\runtime\test_writer_races.py` `1031cd93b507b28ec41c801d5312a5fad46d3dbc`; `hedge_fund\web\services.py` `b41d19c2bbc001bbd24948e4dfa9cbad1e5814ae`; `hedge_fund\web\test_lifecycle.py` `2de3dbaaccb26f27e8f988247fc1a1cd8a13595f`; `frontend\src\components\lifecycle-actions.test.tsx` `5f034f65a941388bb3fd5b4252c07384fe3c98bb`. These are source runs, not an installed wheel or container. |
| Environment and isolation | Windows 11 Enterprise build 26200, NTFS, Python 3.13.7; Node 22.13.1; marked synthetic roots, owned child processes, isolated HOME/TEMP and Vite environment, cleared provider/credential/proxy overrides and disabled dotenv. The guarded runner child blocks loopback and non-loopback network; provider resolution, market data and analyst outputs are fakes. No protected fund, real runner, external provider/broker or LLM was contacted. |
| Runner and lifecycle scenario | The real manager launches a guarded test child invoking `run_owned_runner` with fake data and analyst injection, one reviewed due session and a one-session bound. After a hash-bound approval, the child pauses before the fake fill while real CLI tick, web tick preview and a reviewed web archive are denied; no competing operation or paper-file effect appears. The runner then records one 500-share AAPL buy, consumes the approval once and leaves matching ledger and broker state. An additional barrier holds the runner reservation *after* the child publishes `completed`: archive still receives 409 `writer-conflict` and creates no operation. After release and process exit, the old review is stale; a fresh reviewed archive and restore succeed without starting a runner. |
| Negative and adjacent state | `completed` is accepted for lifecycle only with its matching runner reservation held and `available` false; its actual state and control digests are bound into the review. Starting, running, stopping, failed, unknown, inconsistent available and unreserved completed states deny. A related deployment whose reservation was not acquired remains denied. Production write authority is unchanged and remains fail-closed. |

- **Expected red:** at 2026-11-03 16:39:13–16:39:31 +01:00, the owned-runner
  scenario failed after completing its fill because archive returned
  `ownership-unknown` instead of allowing stale-review detection. The
  lifecycle implementation had required exactly `stopped`, even after a
  one-session runner exited as `completed`. The repair admits `completed`
  only under its matching held reservation; it does not treat the terminal
  record alone as quiescence. The initial corrected scenario passed at
  16:39:43–16:40:07, **1 passed in 22.14 s**.
- **Backend regression:** at 16:45:04–16:51:25 +01:00, the complete
  writer-race and web-lifecycle files plus the selected owned-runner
  stop/readiness/reattach/crash tests passed **52 tests in 378.98 s**, exit 0.
  That run used the same production and lifecycle-test blobs above, but the
  runner-race test blob was `93b82597204cd953199bc08c9cb788581ab2e902`:
  afterward, its two file handshakes were made atomic to avoid observing
  partially written sentinels. On final blob `1031cd93...`, the full
  owned-runner scenario passed three independent repeats in **22.35, 21.72
  and 20.16 s**, 16:51:45–16:52:55 +01:00, all exit 0.
- **Frontend unit/fake tests:** an owned empty Vite env and disabled network
  ran the full Vitest suite at 16:53:34–16:55:34 +01:00: **13 files, 215
  tests passed in 108.78 s**, exit 0. The added component regression displays
  the reviewed `completed` runner and requires explicit confirmation.
- **Build and browser runtime:** the owned lifecycle browser harness ran
  `tsc --noEmit` and a production Vite build, then exercised the real local API
  at 16:55:47–16:57:24 +01:00: **1 Playwright test passed in 29.6 s**,
  exit 0. The isolated three-file frontend artifact was 1,035,167 bytes,
  SHA-256 `bbfbf686c1b100e976c5c9be0ed6c7592e82de93febc88ef48deb865c28dee14`;
  Vite build took **31.24 s**. This browser case covers stale review, archive
  and stopped restore, not the completed-runner race, which is covered by the
  backend test and frontend fake test separately. The owned browser root was
  cleaned; no production artifact was installed.
- **Style:** Black at 420 characters, Flake8 at 420 characters, isort with the
  Black profile at 420 for the two changed test files, configured isort
  defaults for `services.py`, and `git diff --check` all passed. Forcing
  420-character isort on `services.py` flags its pre-existing multiline import
  layout; unrelated imports were not reformatted.
- **Development failures:** early runner fixtures failed before readiness
  because Windows' known-folder lookup rejected the overly long pytest child
  HOME path (`WinError -2147024690`); using a shorter path within the same
  marked synthetic test root fixed the fixture. The first Vitest fixture setup
  had a PowerShell-to-Python quoting syntax error and ran no tests or created
  a fixture; the here-string invocation above succeeded and cleaned its root.
  These fixture failures are not production runtime passes.

At this 2026-11-03 checkpoint, no current-source Linux/native exclusion,
installed-artifact, full-suite or live-provider acceptance was claimed. The
earlier broader backend attempt remained **434 passed / 1 failed**, not a pass;
its child exited before a barrier for a cause not captured. The existing
read-only preview was not that source artifact.

## T025/T026 historical date correction (2026-11-03)

The T025 and T026 task notes previously gave the future date 2026-11-04.
The session records show their validation commands were invoked on
2026-11-03 at 11:48:37.065 and 11:51:06.321 +01:00, respectively. Those
commands included file edits or formatting before pytest, so these are not
exact test-start times. The subsequent task commits were `a08fffd` at
11:48:47 +01:00 and `fcbff96` at 11:51:16 +01:00. Session checkpoint 003
reports 31 ownership tests and 115 cadence/runner tests passed. Original
test-end timestamps and standalone stdout/exit records were not located;
no tests were rerun for this date correction. These historical observations
are not current-artifact or final migration acceptance.

## Final bounded validation and dispositions (2026-11-04)

**Result: partial; no full-suite, T021, T024 or broad T027 pass claimed.**
The accepted trust model is deliberate operator trust for one identified root:
existing data remain read-only until exact offline acknowledgement; the
operator must stop and exclude old CLIs, cron, services, scripts and every
other program able to reach that root. Cooperative locks coordinate
participants only. They are not OS enforcement and do not fence unaware or
malicious same-account writers.

### Source identity and provenance

- Test base: published `HEAD` `146a242610d7ba50c72620db398498d34520cc1d`,
  branch `cgjedrem-vigilant-robot`.
- Final changed code/test source: 28 files under `hedge_fund/` and
  `frontend/`; code/test diff from that base: 142,499 bytes,
  SHA-256 `ee1a9e12939a105805fa329d59d907295e2a28312703c27804f7dfbc01d37f51`.
  The normalized changed-source manifest recorded for the final test snapshot
  is 1,434,222 bytes, SHA-256
  `dd829f011b549605045aef05df9ae17dc3b1a2590d31abbcf43cdc241b82ad7d`.
- Environment: Windows 11 Enterprise build 26200, NTFS, Python 3.13.7;
  pytest selections used isolated synthetic roots, disabled dotenv, scrubbed
  provider/credential/proxy settings and fake provider/transport. Browser
  tests used an owned loopback server on port 8876. No protected funds, live
  runners, provider, broker or LLM were accessed; port 8765 was not touched.
- Linux native snapshot: 248 tracked files from `hedge_fund/` plus
  `pyproject.toml`, 3,536,711 bytes, manifest SHA-256
  `5b509368df319f5dd2ae8a0ec493fa6bf3fe8d508ea730d47b9a6c9163eb0f1c`.
  Container image `aihf-qa2-pytest:d054b3ae`, image SHA-256
  `f46586c33e835ed3ecf57a9b3199396d0301571007955c87cf69905ac4e67412`.
  Docker 29.9.2, WSL2 kernel `6.6.87.2-microsoft-standard-WSL2`, ext4 named
  volume, `--network none`, effective UID 1000. Container-only `USER` and
  `LOGNAME` values allowed `getpass` to resolve the existing UID; the test
  process still ran as UID 1000. Volume and staging tree were removed.

### Sequential full-suite result and triage

Exact command: `python -m pytest -q --tb=short hedge_fund
--ignore=hedge_fund/tui`.

The serial run started `2026-11-04T11:35:49.9994857+01:00` and ended
`2026-11-04T13:06:45.6327229+01:00`; **2,367 passed, 51 skipped, 14 failed
in 5,452.28 s**, exit 1. Captured output was 20,914 bytes,
SHA-256 `e5434bf3b44037aad9e7ed631c4173c8a5ee01abc37704ff835d5fdd08c83efc`.
This was on the run-start source manifest `fe5c17db...` (27 files,
1,426,640 normalized bytes), tracked dirty diff SHA-256 `e3a62cd0...`
(201,740 bytes). The run predates the final `web/demo.py` denial-message
correction; it is not represented as a full-suite result on the final source.
The available run record gives failure classes and measurements but not the
14 individual pytest node IDs; those IDs cannot be verified from retained
artifacts.

Recorded failures: cross-process audit-marker publication; research-saturated
Halt/verdict latency, including **5.910 s against a 5.5 s bound** and a web
verdict at **8.18 s**; archive/Halt and CLI-approval races; peer-service
recovery timeout; operation-completion/backtest timeouts; worker-failure and
busy-retry timeouts. Exact failed nodes:

1. `hedge_fund/runtime/test_writer_races.py::test_two_process_audit_appends_are_complete_and_uninterleaved`
2. `hedge_fund/runtime/test_writer_races.py::test_halt_and_verdict_lanes_stay_responsive_under_research_saturation`
3. `hedge_fund/runtime/test_writer_races.py::test_web_verdict_and_halt_remain_responsive_during_cross_process_research_saturation`
4. `hedge_fund/web/test_actions.py::test_archive_cannot_move_a_fund_during_an_inflight_halt`
5. `hedge_fund/web/test_actions.py::test_web_halt_fences_cli_approval_publication_across_processes`
6. `hedge_fund/web/test_actions.py::test_web_halt_does_not_wait_for_fund_work_lock`
7. `hedge_fund/web/test_jobs.py::test_second_process_cannot_recover_a_live_peer_operation`
8. `hedge_fund/web/test_jobs.py::test_reviewed_operation_preview_accept_persists_capture_and_report`
9. `hedge_fund/web/test_jobs.py::test_paid_fd_web_backtest_uses_guarded_real_client_and_fake_transport`
10. `hedge_fund/web/test_jobs.py::test_reviewed_backtest_executes_captured_mandate_after_template_edit`
11. `hedge_fund/web/test_jobs.py::test_operation_worker_failures_log_safe_cause_without_payload[claim]`
12. `hedge_fund/web/test_jobs.py::test_operation_worker_failures_log_safe_cause_without_payload[work]`
13. `hedge_fund/web/test_jobs.py::test_operation_worker_failures_log_safe_cause_without_payload[complete]`
14. `hedge_fund/web/test_jobs.py::test_busy_interrupt_after_claim_failure_is_retried`

The audit children did not publish a marker before the parent's wait expired.
`test_halt_and_verdict_lanes_stay_responsive_under_research_saturation`
measured **5.9108674 s** against 5.5 s; cross-process web verdict measured
**8.1832771 s** against 5.5 s; CLI approval publication measured
**9.5433004 s** against 5.5 s. The inflight archive/Halt case observed
`state=archived` while Halt timed out. The fund-work-lock case observed
`responsive=False`. The peer-service child exceeded its 30 s process
timeout. Operation preview/accept and guarded fake-transport backtest cases
remained `running`; captured-mandate backtest exceeded its 30 s future wait.
Worker-failure cases exceeded 5 s while logging `OSError(errno=5)`; the
busy-retry case exceeded 5 s after `OperationBusy`. Root cause remains
unproven. No timeout threshold was relaxed.

All failing selections were rerun serially on the final changed source:

| Selection | Final focused result | Relationship to full run |
| --- | --- | --- |
| `hedge_fund/runtime/test_writer_races.py` | 12 passed in 105.39 s, exit 0 | All three full-run failures from this race file passed focused; broader T027 remains partial because full-run saturation/marker failures are unexplained. |
| Three previously failing `hedge_fund/web/test_actions.py` cases | 3 passed in 13.91 s, exit 0 | Archive/Halt and CLI-approval selections passed. |
| Eight previously failing `hedge_fund/web/test_jobs.py` cases | 8 passed in 45.27 s, exit 0 | Peer recovery, operation completion/backtest, worker failure and busy retry selections passed. |

These focused passes do not erase or convert the full-suite failure. A second
full non-TUI suite was not run after the isolated demo-message correction;
final-source broad-suite status is therefore not verified.

### Final-source selections and platform checks

- **T015:** `python -m pytest` over handover, write-authority, explicit CLI
  trust/migration/relocation/revocation cases, trusted web capability, and
  peer-recovery guards — **55 passed in 30.42 s**, exit 0,
  `2026-11-04T14:05:09.885+01:00`–`14:05:42.895+01:00`. Synthetic
  Windows/NTFS, fake providers. Existing, migrated and relocated roots remain
  read-only until separate acknowledgement; peer service leaves a held
  operation running. The CLI acknowledgement is root/build/protocol and
  inventory-bound; no web enrollment path exists.
- **T019/T020 backend:** final contract selection over
  `hedge_fund/web/test_app.py`, `test_actions.py`, `test_jobs.py` and
  `test_valuation.py` — **145 passed in 282.76 s**, exit 0,
  `14:00:14.859+01:00`–`14:05:00.637+01:00`; final
  `hedge_fund/web/test_main.py` — **12 passed in 4.82 s**, exit 0,
  `14:00:01.783+01:00`–`14:00:09.751+01:00`. Synthetic NTFS and fake
  transport cover common error/status envelopes, Host/Origin/CSRF, read-only
  and SIM denials, zero denied downstream effects, polling/reconnect and the
  existing synchronous valuation `budget-exhausted` 429 emitter. Accepted
  dispatch budgets still have no truthful retry/reset hint.
- **Web error-message correction:** the five-file run first returned
  **156 passed, 1 failed in 523.12 s**, exit 1. The failing case was
  `test_demo_seeding_fails_closed_without_out_of_band_exclusion_proof`;
  expected denial wording was absent. `hedge_fund/web/demo.py` now reports
  `out-of-band writer exclusion is unproven`. The affected `test_main.py`
  and full backend contract selection above passed afterward on final source.
- **T019/T020 frontend:** Vitest 4.1.12, Node 22.13.1/npm 10.9.2,
  `npm test` in `frontend/` — **13 files / 216 tests passed**, exit 0,
  `10:48:14.7504365+01:00`–`10:50:12.6643051+01:00`; `tsc --noEmit` and
  Vite 6.4.5 build passed. Build artifact: 3 files / 1,035,387 bytes,
  SHA-256 `57f1e1c18ab9f70739b8f4ec8e6f958b064a30407ef1664cb403e5e1fb9142e1`.
  No frontend source changed after that build.
- **T020 owned browser:** `node .\e2e\run-owned.mjs --lifecycle
  e2e/recovery.spec.ts` in `frontend/`, owned synthetic root, loopback 8876,
  real local API, external requests guarded — **3 Playwright tests passed
  in 17.3 s**, exit 0. Covers stale review, expired session without resubmit
  and lost-server GET-only reconnect. No live provider/broker/LLM.
- **T027 focused races:** the same final `test_writer_races.py` selection
  above passed **12 tests in 105.39 s**. It covers owned cross-process
  audit append, fake-data ledger effects, independent funds, concurrent
  runner fill, redo/archive contention, unsafe legacy/revoked authority and
  bounded controls. Because the full run failed three tests in this file,
  including saturation latency, T027 remains unchecked pending explanation.
- **TUI:** all 11 files under `hedge_fund/tui/test_*.py` were invoked
  sequentially, with no concurrent pytest process — **90 passed, 0 failed
  files**, exit 0, `2026-11-04T14:14:16.350+01:00`–
  `14:15:31.185+01:00`. Files:
  `test_admission_regressions.py`, `test_backtest.py`, `test_builder.py`,
  `test_builder_broker.py`, `test_funds.py`, `test_home.py`, `test_keys.py`,
  `test_paper.py`, `test_paper_view.py`, `test_report.py`,
  `test_scorecard_view.py`.
- **Windows native:** `python -m pytest
  hedge_fund/runtime/test_native_primitives.py
  hedge_fund/runtime/test_native_credentials.py -q -p no:cacheprovider`
  — **10 passed, 3 skipped in 10.46 s**, exit 0,
  `14:10:22.178+01:00`–`14:10:34.930+01:00`, Windows/NTFS.
- **Linux native:** same pytest selection in the isolated Linux container —
  **9 passed, 4 skipped in 4.74 s**, exit 0,
  `2026-11-04T14:10:59.497+01:00`–`14:11:08.433+01:00`; ext4 named
  volume, UID 1000, no network. Initial setup without container-only
  `USER`/`LOGNAME` had nine setup errors and no assertions; corrected
  environment rerun produced the final result above.
- **T021 POSIX append boundary:** `python -m pytest
  hedge_fund/runtime/test_root.py::test_handle_relative_append_preserves_bytes_and_rejects_hardlinks
  -q -p no:cacheprovider` in the same pinned Linux image, ext4 named test
  volume, UID 1000, `--network none`, read-only source bind mounts and
  `PYTHON_DOTENV_DISABLED=1` — **1 passed in 0.19 s**, exit 0,
  host `2026-11-04T14:30:09.7656523+01:00`–`14:30:14.5056497+01:00`.
  Unique volume `spec005-append-1333a918d2e14345929105affc46ce83` was removed.
  This verifies the selected append boundary on ext4; it does not prove
  identity-fenced POSIX unlink or broad POSIX writer behavior.
- **Static checks, final source:** the global Python 3.13 interpreter lacked
  Black/isort/flake8, so no dependency was installed; checks reran with the
  existing isolated project venv. Black `--check --line-length 420`:
  **24 changed Python files unchanged**; isort `--check-only --profile
  black`: exit 0; Flake8 `--ignore=E203,W503 --max-line-length=420`: exit 0;
  `git diff --check`: exit 0. The whitespace check emitted only Git's
  LF-to-CRLF working-copy warning for `tasks.md`.

### T021/T024 and red-team coverage disposition

T021 remains unchecked. Remaining writer-boundary gaps are durable rewind
intent, mandate rename-plus-rewrite journaling, identity-fenced POSIX unlink
evidence, complete Saxo credential/demo/bootstrap admission, and exhaustive
dynamic/out-of-repository writer inventory with race-level evidence. The
POSIX append boundary has one focused ext4 pass; it lacks broad POSIX writer
and race coverage. The Windows writer matrices passed 214 tests at the earlier
final matrix checkpoint; the final focused cross-process race suite passed
12 tests. These results do not prove all writers are inventoried or fence
unaware processes.

T024 remains unchecked and **BLOCKED**: its T002–T023 prerequisites include
open T021; the non-TUI full suite failed and was not rerun on the final
demo-message source. Both final native filesystem rows and one focused ext4
append boundary passed. Native rows do not establish full migration acceptance.

Current LM/LB/HM coverage is deliberately partial:

| Obligation | Final evidence and open condition | Status |
| --- | --- | --- |
| LM1 | Root-bound operator trust and cooperative writer tests pass focused; out-of-band writers remain outside the guarantee and broad T027 failures are unexplained. No OS-enforcement claim. | PARTIAL |
| LM2 | Owned loopback browser recovery passes; host-writer/read-only-container and no-autostart deployment proof absent. | NOT VERIFIED |
| LM3 | Ledger append/fill and selected approval races pass; durable rewind intent and complete post-fill reconciliation remain open. | PARTIAL |
| LM4 | Selected archive/restore and stale-review cases pass; full due-set/backlog and stopped-deployment restore remain open. | PARTIAL |
| LM5 | Synthetic account-binding tests do not establish complete production SIM lifecycle wiring. | NOT VERIFIED |
| LB1 | Root, isolation, headless and writer selections pass; active-child credential lifecycle and complete writer integration remain open. | PARTIAL |
| LB2 | Selected Host/Origin/CSRF and loopback checks pass; read-only-container and future-channel guarantees absent. | PARTIAL |
| LB3 | No live endpoint/DNS/TLS/redirect test is claimed. | NOT VERIFIED |
| LB4 | Windows/NTFS and Linux/ext4 native primitive selections pass with skips; credential UI and active-capture workflow remain open. | PARTIAL |
| LB5 | Native rows pass on tested NTFS and ext4; skipped cases, other filesystems and full deployment remain outside evidence. | PARTIAL |
| HM1 | The full non-TUI suite failed 14 tests; focused reruns pass, root cause unresolved. | PARTIAL |
| HM2 | Selected bounded-policy tests use fakes; complete provider/UI acceptance is not established. | PARTIAL |
| HM3 | Selected bounded-policy regressions pass; scheduled-runner and dispatch acceptance remain open. | PARTIAL |
| HM4 | Selected durable/interruption and fencing tests pass; detached-owner/restart and platform lifecycle acceptance remain open. | PARTIAL |
| HM5 | Selected durable confirmation/idempotency and approval boundary tests pass; complete provenance and operation UI acceptance remain open. | PARTIAL |

Task disposition on this evidence: **T015 checked; T019 checked; T020
checked; T021 unchecked; T024 unchecked; T027 unchecked**. T027 is unchecked
because its focused file passed but three of its cases failed in the full
run; those failures have not been explained. Existing T023/T025/T026/T028
checkboxes remain unchanged.

## 2026-11-05 report-byte and Docker continuation

**Status at this checkpoint:** report byte parity **PASS** for synthetic
source/API/browser tests. The selected Docker desk was blocked at this checkpoint.
The later final-image observations and current evidence limits are appended below;
independent QA and operator cutover remain pending. No task checkbox was changed here.

### Source and environment

- Worktree/branch: `cgjedrem-super-fiesta`; base `3498ef8a7a1751917b16936c9219dda70dd7fa74`.
- Test snapshot used for the 15:29–17:05 rows: six changed files, 375,701 bytes;
  SHA-256 `90cb132f20f18aa5131f866d87e22af33d3af3f63fca496b0a0979b077e6dda5`.
  Formula: sorted slash-normalized relative path + NUL + full bytes + NUL.
- Final source/test identity: six changed files, 375,729 bytes; SHA-256
  `ee1441d6e50a58093b1c5ce06ffc114734feaf2ee9eb2c5ecd5f92d3f0506c15`.
  Only `Ledger.replay` docstring wording differs from the earlier test snapshot;
  executable code is unchanged.
- Environment: Windows 11 build 26200 / NTFS; Python 3.11.15 / pytest 7.4.4;
  Node 22.13.1 / npm 10.9.2; Vitest 4.1.12; Vite 6.4.5;
  Docker Desktop 29.9.2, `linux/amd64`.
- Test data: synthetic `demo-quality` paper root only. No real root/fund,
  provider, broker, paid request or external runtime request.

### Current measurements

| Timestamp / scope | Status and observed result |
|---|---|
| `2026-11-05T15:29:23.6974840+01:00`; report API | **PASS** — `hedge_fund/web/test_reports.py`: **12 passed in 49.65 s**, process elapsed 52.0228 s, exit 0. CRLF persisted ledger bytes returned unchanged from verified replay. |
| `2026-11-05T15:30:26.1586491+01:00`; owned report browser | **PASS** — `node .\e2e\run-owned.mjs --reports reports.spec.ts` from `frontend`: **2 passed in 8.5 s**, process elapsed 108.1182 s, exit 0. Production bundle SHA-256 `ae28e5180ddf67269bc02034228223741471981cf6af3e13bde27c5f40eafc79`; 3 files / 1,040,584 bytes. Synthetic report-tree hash unchanged. |
| `2026-11-05T15:37:27.0948848+01:00`; first full backend run | **FAIL / attribution INCONCLUSIVE** — **1 failed, 2,413 passed, 51 skipped in 2,390.20 s**, process elapsed 2,392.6120 s, exit 1. One `test_create_mandate_rejects_duplicate_canonical_name[...]` failed before its assertion: Windows `PermissionError [WinError 5]` during `os.replace` in synthetic-root relocation setup. A bounded Docker filesystem probe overlapped this long run; no link to the failure is established. |
| `2026-11-05T16:18:07.3538551+01:00`; exact failure node rerun | **PASS** — **1 passed in 2.32 s**, process elapsed 4.7962 s, exit 0. Cause of the prior full-run error remains **unattributed**. |
| `2026-11-05T16:18:45.0056710+01:00`; second full backend run | **PASS** — `pytest hedge_fund --ignore=hedge_fund/tui -q --tb=short`: **2,414 passed, 51 skipped in 2,255.64 s**, process elapsed 2,258.6230 s, exit 0. The green rerun does not establish a cause for the earlier WinError 5. |
| `2026-11-05T16:56:47.5349031+01:00`; TUI/report group | **PASS** — `pytest hedge_fund/tui/test_paper.py hedge_fund/web/test_reports.py -q --tb=short`: **40 passed in 85.75 s**, process elapsed 89.3230 s, exit 0. |
| `2026-11-05T17:00:38.9198613+01:00`; frontend unit tests | **PASS** — package script `npm test` (`vitest run src`): **13 files / 223 tests passed in 24.26 s**, process elapsed 26.6878 s, exit 0. |
| `2026-11-05T17:01:15.4845708+01:00`; browser harness safety | **PASS** — `npm run test:e2e-safety`: **9 passed**, Node duration 651.4047 ms, process elapsed 1.7330 s, exit 0. |
| `2026-11-05T17:01:24.9396054+01:00`; TypeScript | **PASS** — `npm exec -- tsc --noEmit`, exit 0, process elapsed 17.7429 s. |
| `2026-11-05T17:01:57.0782937+01:00`; static checks | **PASS** — Black, isort, configured Flake8, Node syntax and `git diff --check`; all exit 0. |
| `2026-11-05T17:02:11.5894275+01:00`; `Dockerfile.web` | **PASS — build only** — build exit 0 in 59.9403 s. Image tag `aihf-web-spec005-r1-20261105-1a6159b96b4840d2918262e32d4f178f`; ID/repo digest `sha256:668bd2945183b4ad1e8d350d1d5a43c2efcc02c82e83b6518325e1a5866b9ec0`, `linux/amd64`. TypeScript and Vite production build succeeded; 2,317 modules transformed. |
| `2026-11-05T17:05:10.5787101+01:00`; image default entrypoint | **BLOCKED** — owned synthetic root; network disabled, no ports. Configured `--container-bind` rejected as `container observer projection is unavailable`; container exit 2. |
| `2026-11-05T17:05:24.0658523+01:00`; image root-open override | **BLOCKED** — removed only `--container-bind`, supplied `--port 8876 --allow-writes`; `RootContext.open` denied `/data` as `root requires local NTFS or ext4`; container exit 2. Docker mount was `9p`; no app server/API started. Synthetic root had 16 files; tree digest stayed `14ba05231e8448f9401b7e936915f966e87bceb84d06f962ff3ba452e14d65aa`. Both exact containers were removed; synthetic root was removed after another matching digest check; built image retained locally. |
| `2026-11-05T17:13:08.8611670+01:00`; final-source TUI/report group | **PASS** — `C:\Users\ChristianGjedrem\AppData\Local\pypoetry\Cache\virtualenvs\aihf-WidgQWGy-py3.11\Scripts\python.exe -m pytest hedge_fund/tui/test_paper.py hedge_fund/web/test_reports.py -q --tb=short`: **40 passed in 79.43 s**, process elapsed 82.6465 s, exit 0. Final six-file identity `ee1441d6e50a58093b1c5ce06ffc114734feaf2ee9eb2c5ecd5f92d3f0506c15`; earlier full suite differs only by a `Ledger.replay` docstring clarification. |
| `2026-11-05T17:14:45.7299788+01:00`; intermediate image before README correction | **PASS — build only** — `docker build --progress=plain --file Dockerfile.web --tag aihf-web-spec005-r1-20261105-1713-ee1441d6e50 .`; exit 0 in 4.6990 s. Image ID/repo digest `sha256:778675c638e6b2033bcf669d70f5682593b91d22f41a620b60cf40ef638359db`, `linux/amd64`, created `2026-11-05T16:14:49.914503749Z`. The image predates the final README command cleanup below. |
| `2026-11-05T17:16:25.1288294+01:00`; intermediate-image default entrypoint | **BLOCKED** — image `sha256:778675c638e6b2033bcf669d70f5682593b91d22f41a620b60cf40ef638359db`; owned synthetic root, `--network none`, no ports, read-only image rootfs, dropped capabilities, no-new-privileges. Container `0daf0b587b2019ea7c4f8f27f8b6251ba28100c2b86f2d79b0f2c2655838d3c4` rejected `--container-bind` as `container observer projection is unavailable`; exit 2, elapsed 0.8447 s. |
| `2026-11-05T17:16:27.0453952+01:00`; intermediate-image root-open override | **BLOCKED** — same image/root; container `ebf37d08b91e5a9140f849a2a6c152fc9283dc632ce71536caeb5dbbbfd457b0` used `--port 8876 --allow-writes`, without `--container-bind`; `RootContext.open` denied `/data` as `root requires local NTFS or ext4`, exit 2, elapsed 0.7632 s. Synthetic tree had 16 files / 40,399 bytes; digest `77b489543925478f72ec335ae31b48a807b419502816931e6053fd5c2524d904` unchanged before/after. Both containers were removed by full ID and verified absent; synthetic root was removed by the owned-root cleanup helper. |
| `2026-11-05T17:24:17.1039712+01:00`; README-inclusive final image | **PASS — build only** — `docker build --progress=plain --file Dockerfile.web --tag aihf-web-spec005-r1-20261105-1720-ee1441d6e50 .`; exit 0 in 3.8389 s. Image ID/repo digest `sha256:4c78a55ad7ff0e55df9dde3ff5527946163adb5491734037f6d7b2948c9df1e8`, `linux/amd64`, created `2026-11-05T16:24:20.597893426Z`. Final README and Python source copied; application/dependency/frontend layers were cached. |
| `2026-11-05T17:24:39.9564121+01:00`; README-inclusive final-image default entrypoint | **BLOCKED** — image `sha256:4c78a55ad7ff0e55df9dde3ff5527946163adb5491734037f6d7b2948c9df1e8`; owned synthetic root, no network/ports, read-only image rootfs, dropped capabilities, no-new-privileges. Container `722e56faa3e4fdd1f2e16876596cd6f9f157d87052fbf7567ec3cc776402a616` rejected `--container-bind` as `container observer projection is unavailable`; exit 2, elapsed 0.8388 s. |
| `2026-11-05T17:24:41.6972386+01:00`; README-inclusive final-image root-open override | **BLOCKED** — same image/root; container `7a93a8b462b87417968a95dd05a528cf64abafc52097c3ace33cc77dd6b35d2f` used `--port 8876 --allow-writes`, without `--container-bind`; `RootContext.open` denied `/data` as `root requires local NTFS or ext4`, exit 2, elapsed 0.6031 s. Synthetic tree had 16 files / 40,404 bytes; digest `62642be04d0c702a235bb043790daa8caa59bed71eed6fad322db78bb9882ee4` unchanged before/after. Both containers were removed by full ID and verified absent; synthetic root was removed by the owned-root cleanup helper. |
| `2026-11-05T17:28:22.3954832+01:00`; final changed-scope static checks | **PASS** — Black `--check` on four Python files, isort `--check-only`, Flake8 `--max-line-length=420 --extend-ignore=E203,W503`, Node syntax and `git diff --check`; all exit 0 in 2.5674 s. Final source/test identity remains `ee1441d6e50a58093b1c5ce06ffc114734feaf2ee9eb2c5ecd5f92d3f0506c15`. |

### Failed attempts, limits and disposition

- `npm exec -- vitest run` was the wrong selector: Vitest discovered Playwright/Node
  files, reported **223 source tests passed** and eight suite-import errors. No source
  change followed; configured `npm test` then passed its 223 source tests.
- Docker image startup never reached a listener. Writable action, same-fund exclusion,
  stale/ambiguous recovery, Host/Origin behavior inside the container, Linux/ext4,
  Ollama transport and container replacement remain unverified. TUI regression tests
  passed; they do not prove a running web container's fallback or coexistence behavior.
- No cutover, root migration, production trust operation, real funds, provider calls,
  credentials, or public/host-network container was used. The uniquely tagged image
  is a build/runtime-probe artifact, not Release 1 acceptance.
- Final image/runtime rows use the final source/test identity above. The full-suite,
  frontend, and initial browser rows predate only a docstring-only code edit; no behavior
  changed after those measurements. The final-source TUI/report group was rerun. The
  README-only operating-instruction correction was included in the final Docker image.
- The earlier full-suite WinError 5 remains unexplained. Do not infer a cause from the
  focused or full green rerun. The independent coordinator QA gate remains pending.

### Intermediate image runtime commands (before README correction)

Image tag `aihf-web-spec005-r1-20261105-1713-ee1441d6e50` resolves to
`sha256:778675c638e6b2033bcf669d70f5682593b91d22f41a620b60cf40ef638359db`.
Both commands used a test-owned synthetic bind at
`C:\Users\ChristianGjedrem\source\repos\copilot-worktrees\ai-hedge-fund\cgjedrem-super-fiesta\outputs\spec005-test-docker-final-f44921a7e9974623b1d64c1331e37760\demo-quality`.
No network or published ports; rootfs read-only; all capabilities dropped;
no-new-privileges. Only `/data` was writable.

```powershell
docker run --name spec005-web-final-default-f44921a7 --network none --read-only --cap-drop ALL --security-opt no-new-privileges:true --mount "type=bind,source=C:\Users\ChristianGjedrem\source\repos\copilot-worktrees\ai-hedge-fund\cgjedrem-super-fiesta\outputs\spec005-test-docker-final-f44921a7e9974623b1d64c1331e37760\demo-quality,target=/data" aihf-web-spec005-r1-20261105-1713-ee1441d6e50

docker run --name spec005-web-final-root-f44921a7 --network none --read-only --cap-drop ALL --security-opt no-new-privileges:true --mount "type=bind,source=C:\Users\ChristianGjedrem\source\repos\copilot-worktrees\ai-hedge-fund\cgjedrem-super-fiesta\outputs\spec005-test-docker-final-f44921a7e9974623b1d64c1331e37760\demo-quality,target=/data" aihf-web-spec005-r1-20261105-1713-ee1441d6e50 --port 8876 --allow-writes
```

### README-inclusive final image runtime commands

Image tag `aihf-web-spec005-r1-20261105-1720-ee1441d6e50` resolves to
`sha256:4c78a55ad7ff0e55df9dde3ff5527946163adb5491734037f6d7b2948c9df1e8`.
Both commands used a test-owned synthetic bind at
`C:\Users\ChristianGjedrem\source\repos\copilot-worktrees\ai-hedge-fund\cgjedrem-super-fiesta\outputs\spec005-test-docker-final-1720-6629c68fe9c240b18c0d36cfe62e666e\demo-quality`.
No network or published ports; rootfs read-only; all capabilities dropped;
no-new-privileges. Only `/data` was writable.

```powershell
docker run --name spec005-web-final-default-6629c68f --network none --read-only --cap-drop ALL --security-opt no-new-privileges:true --mount "type=bind,source=C:\Users\ChristianGjedrem\source\repos\copilot-worktrees\ai-hedge-fund\cgjedrem-super-fiesta\outputs\spec005-test-docker-final-1720-6629c68fe9c240b18c0d36cfe62e666e\demo-quality,target=/data" aihf-web-spec005-r1-20261105-1720-ee1441d6e50

docker run --name spec005-web-final-root-6629c68f --network none --read-only --cap-drop ALL --security-opt no-new-privileges:true --mount "type=bind,source=C:\Users\ChristianGjedrem\source\repos\copilot-worktrees\ai-hedge-fund\cgjedrem-super-fiesta\outputs\spec005-test-docker-final-1720-6629c68fe9c240b18c0d36cfe62e666e\demo-quality,target=/data" aihf-web-spec005-r1-20261105-1720-ee1441d6e50 --port 8876 --allow-writes
```

## Historical Docker continuation evidence — 2026-11-05 (cad96a; superseded)

### Historical identity and provenance record

- The prior record attributed image `aihf-web-spec005-r1-cad96a0-8875cf1`, ID
  `sha256:21582eeedfa316925b6656f4eedcb4dfd0b999062af3d3aa72f84ceaaa9597b6`,
  with reported labels `cad96a05875efe13d229a8a079d2348ed6d0cf95` and
  `8875cf13798d0b6f8468bba97ab3e7f4a21eb48ccd1f61f951b30cd94026d815`.
- Earlier evidence listed `docker build --progress=plain --file Dockerfile.web
  --tag aihf-web-spec005-r1-cad96a0-8875cf1 .` and a 44.5122 s interval. That
  command string omits `AIHF_SOURCE_REVISION` and `AIHF_SOURCE_SHA256`. The
  `Dockerfile.web` at `cad96a05875efe13d229a8a079d2348ed6d0cf95` declares both
  required build args and passes them to `bake_build_identity`. No prior image-build
  log remains in `outputs/`; the recorded command does not establish how that image
  was built. Treat its build/source provenance as **INCONCLUSIVE**, not PASS.
- Revision labels are operator-supplied, format-checked values; they do not verify
  a Git checkout. Package digest scope and exclusions are described in `README.md`.
- The prior runtime observations below are retained as historical observations only.
  Their exact timestamped invocation was not retained and they do not satisfy the
  current replacement-container gate.

### Historical evidence rows

| Row | Time / duration | Scenario and provenance | Expected / observed | Result |
|---|---|---|---|---|
| Historical `cad96a` image record | Prior record reports `2026-11-05T19:24:08.3366748+01:00`–`19:24:52.8510996+01:00`; **44.5122 s** | Previously listed direct `docker build` string omits required identity args; no build log retained. | Image ID and labels were reported, but exact build invocation/source mapping is not established. | **INCONCLUSIVE — provenance not accepted** |
| Final Compose merge | `2026-11-05T19:52:45.5403224+01:00`–`2026-11-05T19:52:46.0710415+01:00`; **0.528331 s** | `docker compose -f docker-compose.yml -f docker-compose.linux.yml --profile web --profile web-operator --profile tui --profile tui-web config --format json`; env: `AIHF_DATA_ROOT=/tmp/spec005-compose-config-only`, baked revision/digest supplied as build inputs; PowerShell assertions. | 13/13 checks: read-only `web`, writable operator `/data`, read-only image, host network, explicit flags, no bridge ports/networks, retained TUI services, literal-loopback Ollama setting, `CAP_DROP=ALL` and `no-new-privileges`. | **PASS — configuration only** |
| Final-image runtime matrix | Exact timezone start/end, full command invocation and per-check durations not retained in the current evidence record; outcomes are summarized below. | Implementation-owner runtime observation on the final image; `--network none`, no published ports, read-only image rootfs, dropped capabilities, `no-new-privileges`, tmpfs `/tmp`, synthetic ext4 volume. | The observed outcomes were positive, but required timestamp/provenance fields are incomplete. | **INCONCLUSIVE — not a formal acceptance PASS** |
| Final targeted Python regression | `2026-11-05T20:01:02.7436917+01:00`–`2026-11-05T20:05:59.4019964+01:00`; **293.92 s pytest**, **296.6548349 s process**. | Source revision `cad96a05875efe13d229a8a079d2348ed6d0cf95`; immutable source snapshot `HEAD:hedge_fund` tree `36ad8b23874224ca3883bd6f6b05686d7c5ef145`; Python 3.11.15 / pytest 7.4.4; `Windows-10-10.0.26200-SP0`; synthetic fixtures and fakes. Exact selector below. | Ten modules, **302 passed**, exit 0. | **PASS — targeted unit/fake tests only; not full suite** |
| Python style | Black `2026-11-05T20:08:09.5697509+01:00`–`2026-11-05T20:08:10.1517368+01:00`, **0.579279 s**; isort `2026-11-05T20:08:22.2553086+01:00`–`2026-11-05T20:08:22.6204871+01:00`, **0.3626526 s**; Flake8 `2026-11-05T20:08:09.5427636+01:00`–`2026-11-05T20:08:11.2700414+01:00`, **1.7238262 s**. | Revision and source snapshot above; repository-configured tools on all 13 task-changed Python files. Exact commands below. | Black, isort and Flake8 exited 0. | **PASS — static style only** |
| Synthetic credential log scan | `2026-11-05T19:47:20.2135310+01:00`–`2026-11-05T19:47:20.8711177+01:00`; **0.6575867 s**. | `docker logs` for the exact three final-image containers; 16 lines inspected. | Unique synthetic credential sentinel absent from logs. API settings/status non-disclosure is a separate observation with incomplete runtime provenance. | **PASS — log scan only** |
| Owned resource cleanup | `2026-11-05T19:47:46.7461202+01:00`–`2026-11-05T19:48:34.1820983+01:00`; **47.4359781 s**. | Exact container IDs and volume names listed in `implementation-progress.md`; ownership and mounts inspected before stop. | Four task-owned containers and three task-owned synthetic volumes removed; final image retained. | **PASS — owned resources only** |
| Final cleanup and image identity | `2026-11-05T19:59:24.1365443+01:00`–`2026-11-05T19:59:25.9085009+01:00`; **1.7719566 s**. | Exact-ID `docker inspect`, exact-name `docker volume inspect`, `docker image inspect` on retained final tag. | Four owned containers absent, three owned volumes absent; image ID, revision and package-source labels match the mapping above. | **PASS — final state** |
| Final retained image/resource recheck | `2026-11-05T20:13:29.3788001+01:00`–`2026-11-05T20:13:31.0562602+01:00`; **1.6774601 s**. | `docker image inspect aihf-web-spec005-r1-cad96a0-8875cf1`; exact-ID `docker ps -a -q --filter id=...` and exact-name `docker volume ls -q --filter name=...` for the four IDs and three names in `implementation-progress.md`; PowerShell JSON/absence checks. | ID `sha256:21582eeedfa316925b6656f4eedcb4dfd0b999062af3d3aa72f84ceaaa9597b6`, `linux/amd64`, baked revision/digest match; four owned container IDs and three volume names absent; exit 0. | **PASS — read-only identity/cleanup recheck** |

### Timestamped Python and style checks

- Source revision: `cad96a05875efe13d229a8a079d2348ed6d0cf95`; immutable package/test
  snapshot: `git rev-parse HEAD:hedge_fund` →
  `36ad8b23874224ca3883bd6f6b05686d7c5ef145`. The worktree package subtree was clean;
  tests imported the source tree, not a wheel or container.
- Environment: Python 3.11.15, pytest 7.4.4,
  `C:\Users\ChristianGjedrem\AppData\Local\pypoetry\Cache\virtualenvs\aihf-WidgQWGy-py3.11\Scripts\python.exe`;
  `platform.platform()` returned `Windows-10-10.0.26200-SP0`.
- Exact test command, exit 0:
  `C:\Users\ChristianGjedrem\AppData\Local\pypoetry\Cache\virtualenvs\aihf-WidgQWGy-py3.11\Scripts\python.exe -m pytest -q --tb=short hedge_fund/paper/test_ledger.py hedge_fund/pipeline/test_session_build_identity.py hedge_fund/runtime/test_build_identity.py hedge_fund/test_run.py hedge_fund/tui/test_paper.py hedge_fund/web/test_app.py hedge_fund/web/test_main.py hedge_fund/web/test_reports.py hedge_fund/web/test_services.py hedge_fund/web/test_write_authority.py`
- Result: **302 passed in 293.92 s**; PowerShell process elapsed **296.6548349 s**.
  Start `2026-11-05T20:01:02.7436917+01:00`; end
  `2026-11-05T20:05:59.4019964+01:00`.
- Style commands ran on these 13 task-changed files:
  `hedge_fund/paper/ledger.py`, `hedge_fund/pipeline/session.py`,
  `hedge_fund/pipeline/test_session_build_identity.py`,
  `hedge_fund/runtime/build_identity.py`, `hedge_fund/runtime/test_build_identity.py`,
  `hedge_fund/test_run.py`, `hedge_fund/tui/test_paper.py`,
  `hedge_fund/web/__main__.py`, `hedge_fund/web/app.py`,
  `hedge_fund/web/services.py`, `hedge_fund/web/test_app.py`,
  `hedge_fund/web/test_main.py`, `hedge_fund/web/test_reports.py`.
- Exact PowerShell invocations, all exit 0:
  ```powershell
  $python = 'C:\Users\ChristianGjedrem\AppData\Local\pypoetry\Cache\virtualenvs\aihf-WidgQWGy-py3.11\Scripts\python.exe'
  $files = @(
      'hedge_fund/paper/ledger.py',
      'hedge_fund/pipeline/session.py',
      'hedge_fund/pipeline/test_session_build_identity.py',
      'hedge_fund/runtime/build_identity.py',
      'hedge_fund/runtime/test_build_identity.py',
      'hedge_fund/test_run.py',
      'hedge_fund/tui/test_paper.py',
      'hedge_fund/web/__main__.py',
      'hedge_fund/web/app.py',
      'hedge_fund/web/services.py',
      'hedge_fund/web/test_app.py',
      'hedge_fund/web/test_main.py',
      'hedge_fund/web/test_reports.py'
  )
  & $python -m black --check --line-length 420 @files
  & $python -m isort --check-only @files
  & $python -m flake8 --ignore=E203,W503 --max-line-length=420 @files
  ```
  Black left **13 files unchanged** in **0.579279 s**. Isort 5.13.2 used repository
  config (`profile=black`, `force_alphabetical_sort_within_sections=true`) and passed
  in **0.3626526 s**. Flake8 passed in **1.7238262 s**. Exact timezone start/end values
  are in the Python style evidence row above.
- An exploratory isort command that manually supplied `--profile black --line-length
  420` but omitted the repository's alphabetical-sort setting failed. The configured
  isort command passed; no source files were changed by either check.
- The earlier **274 passed** selection had no retained selector/time and is not counted
  as a formal row. The timestamped 302-test selection supersedes it for these modules.

### Runtime observations; incomplete formal provenance

The final image's bounded runtime observations are transcribed here from the preceding
implementation execution. Their exact command script and timezone-qualified start/end
timestamps were not retained. Do not upgrade this row to PASS from the prose summary.

- Fresh synthetic ext4 root reached the API. Runtime identity environment overrides did
  not override the baked revision or package digest.
- Wrong root-specific trust acknowledgement exited 2 and left a three-file, 1,365-byte
  synthetic root unchanged; SHA-256
  `f92595826ad79ed68c5580d97f4ba770b626732a7546c3d2cab5965e222652f0`.
- Correct offline trust was recorded inside the same container. After same-container
  restart, PID namespace `pid:[4026532992]` and mount namespace `mnt:[4026532985]`
  were unchanged; API capability reported writes/network enabled and
  `operator-trusted-single-writer`.
- Missing session, missing/bad CSRF, bad Origin and bad Host returned 403. Protected-name
  create/deploy returned 403 `protected-root`. Synthetic
  `spec005-runtime-fund` create/deploy returned 201 with universe `SYNTH`.
- A cooperating process held the synthetic fund deployment lane; duplicate deploy
  returned 409. Root stayed at 11 files / 3,073 bytes, SHA-256
  `0b8384dd7ab849ec57101da4409bbba1dc6d91da2c1f3aa9c0fde549046ec681`.
- A replacement container changed PID/mount namespaces and reported invalid enrollment,
  unavailable authority, read-only mode and writes/network disabled. Host/Origin and write
  requests were denied; root stayed at 12 files / 5,165 bytes, SHA-256
  `7a8c5c2e0312acb0656197ca43b6f1ec7137736dec576737310f3b3f58660f20`.
- Sequential TUI rendering used a separate synthetic volume after graceful stop of exact
  web child PID 97. Textual 8.2.8 rendered `HomeScreen` with two menu options and created
  only `mandates/` plus the expected 2,092-byte `mandates/example.yaml`. The initial
  exploratory TUI assertion failed because first render creates that example; it is not
  evidence of a no-write fallback. Same-root cross-namespace TUI use remains untested.

For this earlier `cad96a` observation, Linux host-network/browser/Ollama was checked as
Compose configuration only. Windows bridge/browser/Ollama, actual funds, FR-044 target
operation, NTFS-to-ext4 relocation, container recreation/rebind, and operator cutover
remain unsupported, blocked or unverified. RB-5 remains unchecked. Independent QA is
pending.

## Current Compose-built image and runtime gate — 2026-11-05

### Source and artifact identity

- Clean source at build: revision `7ec7aaa970a1805478940691a948f1b0dbed4649`,
  tree `494c596575e7b74eb0af0d0ab5d8ae4bfb4916a9`, `hedge_fund` tree
  `79bc529e6207667271a5cf79063bee0e5f121994`, tracked diff SHA-256
  `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`.
- Compose image tag:
  `aihf-web:7ec7aaa970a1805478940691a948f1b0dbed4649-152aa83b71b6cab8569aaf270ee7215208444335713bc4887cd17544c9bad263`.
- Image ID `sha256:b998cd64d5d28c5853ee36fe88381b3ff4a5b4ea7cabb0f1c7d239d5ba7fd977`,
  Linux/amd64, image-created `2026-11-05T20:13:08.455929837Z` UTC.
- `AIHF_SOURCE_REVISION=7ec7aaa970a1805478940691a948f1b0dbed4649` is operator-supplied
  and format-checked; it is not checked against Git.
  `AIHF_SOURCE_SHA256=152aa83b71b6cab8569aaf270ee7215208444335713bc4887cd17544c9bad263`
  was recomputed from selected package-relative `hedge_fund` files and verified before baking.
  The package digest excludes generated `_build_identity.py`, `web/static`, frontend
  inputs, Dockerfile, lockfiles, base-image contents and OS layers. See `README.md`.
- OCI labels and a read-only networkless image probe returned the same baked tuple.
  The final source-tree digest recomputation returned the same package SHA-256.

### Build identity inputs and recorded command

The identity inputs and recorded Compose build command:

```powershell
$env:AIHF_SOURCE_REVISION='7ec7aaa970a1805478940691a948f1b0dbed4649'
$env:AIHF_SOURCE_SHA256='152aa83b71b6cab8569aaf270ee7215208444335713bc4887cd17544c9bad263'
docker compose -p spec005r1-7ec7aaa-20261105-2111 -f docker-compose.yml -f docker-compose.linux.yml --profile web-operator build --progress plain web-operator
```

Build ran `2026-11-05T21:12:44.2275928+01:00`–`21:13:29.7910203+01:00`,
**45.5606261 s**, exit 0. Compose emitted a flag-placement warning; the command
completed and built the tag above. Raw output: `outputs/spec005-r1-runtime-7ec7aaa-20261105-2111/docker-compose-build.log`.
The build log does not retain the `AIHF_DATA_ROOT` value. That variable supplies
Compose bind-source interpolation; it is not a Docker build argument. No prior value
is inferred. The recorded runtime/config check used an existing synthetic artifact path.

The final merged config command was
`docker compose -p spec005r1-7ec7aaa-20261105-2111 -f docker-compose.yml -f docker-compose.linux.yml -f outputs/spec005-r1-runtime-7ec7aaa-20261105-2111/compose.synthetic.yml --profile web-operator config --format json`.
At `2026-11-05T21:51:23.1059720+01:00`–`21:51:23.6011727+01:00`,
**0.4922582 s**, exit 0, **13/13** assertions passed. Selected service used
`network_mode: host`, no port bindings or Compose bridge network, read-only image
root, all capabilities dropped, `no-new-privileges`, the exact ext4 named volume
at `/data` and `/app/outputs`, test loopback allowlist `8876`, scrubbed credentials,
and no `tui-web` service in the selected profile. This is config evidence, not
browser/Ollama evidence.

### Runtime environment and provenance

- Host: Windows 11 build 26200.0; Docker Desktop server 29.9.2; Compose 5.6.1;
  Python 3.11.15. Image: Linux/amd64.
- Volume: `spec005r1-ext4-7ec7aaa-20261105-2111`, Compose project
  `spec005r1-7ec7aaa-20261105-2111`; `/proc/mounts` reported `/data` as ext4.
  Test marker `.test-owned`; roots `fresh-root`, `recovery-root`, `home`, `tmp`.
- All roots and mandates were synthetic and disposable. No actual fund, real root,
  cutover, NTFS-to-ext4 copy, provider, market-data, LLM or broker call. App traffic
  used `docker exec` and loopback `127.0.0.1:8876`; API capabilities reported
  `network=false`, the test guard blocked an unlisted loopback port, and Compose
  exposed no host port. Host networking still permits reachability in principle;
  no external endpoint was called.
- `tui-web`/ttyd was not started and remains unapproved. The browser and Ollama paths
  were not exercised. Base bridge profiles remain unsupported; validation used the
  documented Linux overlay.
- Raw commands and logs are retained locally under
  `outputs/spec005-r1-runtime-7ec7aaa-20261105-2111/` (ignored runtime artifacts).

### Current evidence rows

| Row | Time / duration | Scenario and provenance | Observed result | Disposition |
|---|---|---|---|---|
| Compose image build | `21:12:44.2275928+01:00`–`21:13:29.7910203+01:00`; **45.5606261 s** | Identity inputs and recorded Compose command above; clean source and baked identity. `AIHF_DATA_ROOT` was not retained and is not a build arg. | Compose tag and image ID match; package digest matches source recomputation. Revision label carries the operator-supplied, format-checked value. | **PASS — image build and package mapping; revision not Git-verified** |
| Baked identity and digest | Identity probe `21:48:49.8987371+01:00`–`21:48:50.3720654+01:00`; digest recompute `21:50:03.4306137+01:00`–`21:50:11.9781684+01:00`, **8.5451879 s**; image inspect `21:55:01.2891997+01:00`–`21:55:01.5311331+01:00`. | `baked-identity-probe.log`, `package-digest-recompute.log`, `docker-image-inspect-final-corrected.log`. | Probe and OCI labels match the baked tuple; source digest recomputation matches. | **PASS — package digest verified; revision format-only** |
| Compose merge | `21:51:23.1059720+01:00`–`21:51:23.6011727+01:00`; **0.4922582 s**. | Exact command above; `compose-final-config-check.log`, `compose-final.config.json`. | **13/13** topology and guard assertions passed. | **PASS — config only** |
| Fresh-root read-only service | `21:57:02.4669552+01:00`–`21:57:06.6129489+01:00`; separate create/readiness/probe/stop timings in `fresh-trace-runtime.log`. | Linux overlay, host network, same ext4 named volume; exact `docker compose run` and `docker exec` commands in the log. | Capabilities/empty mandates 200; bad Host/foreign Origin 403; mutation 403 `read-only`; root unchanged. Container `d0a5a1c109b63d5e8c0ceedf3cf5a3b8706c4208af5e3dd28d369ab061d55211`, exit 0. | **PASS — fresh synthetic root** |
| Enrolled recovery-root API scenarios | HTTP probe `21:36:09.6642992+01:00`–`21:36:11.5538767+01:00`, **1.8867976 s**. | `recovery-http-scenarios.log`; server launched by `recovery-container-start.log`; loopback network guard in `network-guard-probe.log`. | Host/Origin/session/CSRF failures 403; credential status redacted, credential-like mandate rejected 400; protected roots `watchtower`, `watchtower-weekly`, `umbrella` denied 403; synthetic create/deploy 201; duplicate same-fund 409; ambiguous recovery preview 200; stale recovery 409 with Halt/events unchanged; unlisted loopback port blocked. API writes true only for the synthetic enrolled root; network false. | **PASS — synthetic API scenarios** |
| Replacement-container identity | Start `21:38:53.7960996+01:00`–`21:38:54.4967824+01:00`; readiness `21:38:55.0545225+01:00`–`21:38:56.8162680+01:00`; corrected probe `21:40:52.1251749+01:00`–`21:40:54.3006122+01:00`, **2.1720159 s**, exit 1. | Same Compose host-network profile and ext4 volume; replacement ID `82aa2c03ecbe0bacb1f333318eceb585645980649352d523a0a8415fd6e41570`; original recovery ID `c839d4fc140eb7d9efbe097f846e510657a0f93ebe797b23cf6dee9c27fc8bdb`. | Recovery seed log records `pid:pid:[4026532817];mnt:mnt:[4026532804]`. Corrected probe aborts at equality check (`stored_namespace == current_namespace`) with “replacement container unexpectedly retained the enrolled namespace”; readiness reports `enrollment=enrolled`. The probe does not print the replacement tuple, and aborts before capability/mutation checks. No write-enabled replacement or reenrollment ran. Cause is unknown. | **FAIL — replacement identity gate; fail-closed denial not established** |
| Sequential TUI CLI fallback | Web child shutdown `21:43:54.6823685+01:00`–`21:43:55.1108314+01:00`; TUI probe `21:44:09.9673569+01:00`–`21:44:14.1381211+01:00`, **4.1694781 s**. | `cli-web-shutdown.log`, `cli-processes-after-web-shutdown.log`, `cli-tui-probe.log`, terminal capture `cli-tui-render.bin`. | Web child absent after graceful shutdown; TUI exited 0 and rendered 15,731 bytes, SHA-256 `8ade2127e3e48a111040ee2896d8bfe2af7b221d430b70c5b86ffb1feb414290`. First use added only synthetic `mandates/example.yaml` (2,092 bytes). | **PASS — sequential CLI fallback; expected first-use write** |
| Identity regressions and style | Tests `21:54:25.1222691+01:00`–`21:54:28.9888218+01:00`, **3.8635065 s**; style `21:57:58.3821588+01:00`–`21:58:00.3200438+01:00`, **1.9348404 s**. | Exact pytest, Black, isort and Flake8 commands in `final-identity-tests.log` and `final-python-style.log`. | **13 passed**; four Python files pass Black, repository-configured isort, and Flake8 with `--max-line-length=420`. | **PASS — focused unit/fake and style checks only** |
| Runtime supervisor shutdown | `21:37:10.5566481+01:00`–`21:37:25.8712599+01:00`. | Recovery harness received SIGTERM; `recovery-supervisor-exit.log`. | Uvicorn logged application shutdown complete; test supervisor recorded child exit `-15` and container exited 241. This harness exit is retained, not counted as an API-scenario failure or a clean supervisor exit. | **INCONCLUSIVE — harness shutdown status** |
| Owned runtime cleanup | `2026-11-05T22:09:07.3937573+01:00`–`22:09:15.3986133+01:00`; **8.004856 s**. | `runtime-cleanup.log`; exact five container IDs and the Compose-labeled synthetic volume were inspected before removal. | Removed only five stopped task-owned containers and `spec005r1-ext4-7ec7aaa-20261105-2111`; no project containers, networks or that volume remain. Final image tag/ID retained. | **PASS — exact task-owned resources only** |
| Final resource state | `2026-11-05T22:12:29.8108480+01:00`–`22:12:31.1186163+01:00`; **1.3046777 s**. | `final-resource-state.log`; exact project label, volume name, `probe2` name and image tag inspected. | No project containers, running containers, named volume, networks or `probe2` containers; final image ID/tag/platform remain. | **PASS — read-only final state** |

### Raw evidence file integrity

Logs and terminal capture remain in the ignored local directory
`outputs/spec005-r1-runtime-7ec7aaa-20261105-2111/`; each digest below identifies the
exact retained bytes. These files are not included in the docs-only commit.

| File | Bytes | SHA-256 |
|---|---:|---|
| `prepare_synthetic_volume.py` | 1050 | `4fccbbd2ebf8757be21cdebaa0f0213c8b47185bad032a5c4c8fba673680b9c5` |
| `runtime_fresh_probe.py` | 3265 | `7b9f9bc117677fdee85a945ecac3717eed8f86655afcb49b7929b31f6bcc695e` |
| `runtime_http_scenarios.py` | 13262 | `7eef33cf94b11fabb673aa7a901af627e6ba0ee0fbcf189400d04101b786b4aa` |
| `runtime_replacement_probe_v2.py` | 3854 | `ed4ac0ac83d02862c0c4051e5157398544c9f0885eb1f62f9223e13ac9e1791d` |
| `runtime_seed_server_v2.py` | 5423 | `283a74cfc9b73aa83ff203936abdbdde9c46f9e96fe74c02eebd222beaa858e9` |
| `runtime_tui_probe_v2.py` | 4124 | `d6b93cebd59013b0c30eb7e6c293bef377d9d3a333e8dcb7a119775de419f02d` |
| `docker-compose-build.log` | 28219 | `7c8434cd266e83f63b70170e97d9a488385c6b5a80d6d31518fb9410629029d9` |
| `baked-identity-probe.log` | 601 | `7cf334e69c65081cf6aa45ad4933c378b2b807b40735913b62322aecca29fee4` |
| `package-digest-recompute.log` | 308 | `51f6523440d39a8d3813087db6b4cdeb0228f417e3de0605bf7fe0456fc2b803` |
| `docker-image-inspect-final-corrected.json` | 3922 | `1dd94e9b315dafa2fd13c3f3a19aa6f8e4220cda638d8587d2ca5a59fe732dc6` |
| `docker-image-inspect-final-corrected.log` | 912 | `2080c0dfa6ea1436121608b9f179faf2d1cea8ee4bbdee9afc64a0348bb69651` |
| `compose.synthetic.yml` | 1414 | `d39de8d4d6b56439c18dbc6b257ad8fae80776eec1f27456d4cacadda0f24c5e` |
| `compose-final.config.json` | 2587 | `bdda2d9a25e6ad4e7dead841f66b929845dc453cd1f21a5a33066a3549fbfe61` |
| `compose-final-config-check.log` | 1061 | `68802d3390f616d790a11dd78374dc203b5a8934c74f8aefce509cf6449f50a2` |
| `synthetic-volume-setup.log` | 122 | `0301fcf0cdb47882101525bfdaac323c4ea9bf9461395bfaee14cc2392fdb270` |
| `synthetic-volume-verify.log` | 230 | `850056afd4b30bc4afb0cb585996b391469305e7d391cbb3b9357ca54282bce9` |
| `fresh-container-start.log` | 538 | `b0b75b70e97da68bd50a94d18a5d48aec50be56f21caa13d82c7ea4c7ef02e88` |
| `fresh-readiness.log` | 240 | `4c12428b979f8b67ca7395769d0714487d2bc599f4cfde4fe6c33ee6978d93a0` |
| `fresh-probe.log` | 907 | `749bd9a35eed971f5c30262b123fc841235db2aa0467f9cd5966fcbabbb2bb6c` |
| `fresh-container-stop.log` | 221 | `0145381fd4db26836f3bc1dfe7d13f8b98dae07051908515e1b9fb3a76e6b848` |
| `fresh-trace-runtime.log` | 3249 | `d7f53012d93ea8b98683f06ecf02bb89a70e22900da0fef69ff8834aaa205082` |
| `recovery-container-start.log` | 947 | `a891f23d4c6fa82eddfb79d133020a224c9e0b093e671b6ef02345f62a7cec3d` |
| `recovery-readiness.log` | 269 | `07bc26553614b2bfdbe922e66b90e9caaaa848e8e5319bc0f89765d4e05083ca` |
| `recovery-supervisor-live.log` | 702 | `24413716c023d392914b34233030d1b56954f0c9b484b139d0feca191c68caf5` |
| `recovery-supervisor-exit.log` | 1222 | `d93aa0d472821634d0842ac8147c906fd52fd3b93474c0237a5cd4c629d1042f` |
| `recovery-http-scenarios.log` | 3451 | `13307dbc41d796dbd0a50ba40b42f2d6beb54742867d2f36d641c7b3fc782d1f` |
| `replacement-container-start.log` | 1011 | `eb09c8669e76e88ae6a7add4c0bd1bfb9c4928351580396b0824aa6f62220cf9` |
| `replacement-readiness.log` | 273 | `6e0347848bc91b395832dadbf8813bf755df1a12f156304b07d1914145d7585f` |
| `replacement-volume-diagnosis.log` | 1039 | `3e95f249d5e5dec1598da753e7072b3d7c076450a784ea46c9b885f7f7c30964` |
| `replacement-container-stop.log` | 233 | `25d88218588bb6368a1221f428cd0c22955de03809d24fdbe2ae23a9a462746b` |
| `replacement-probe-v2.log` | 711 | `0e5bc9b62957fc67e02a1fe1613af835395ff247afecb6898061ee6f0032bbf5` |
| `network-guard-probe.log` | 215 | `b10603c95d2c02eb7799ad245d210351ecdc2aa5eae74ab6b7570c7d7dd0cc03` |
| `cli-web-shutdown.log` | 1290 | `4fbcca96dc0b89af658c08212f708444326d6e4f12a091be6779955d348f8834` |
| `cli-processes-after-web-shutdown.log` | 531 | `af2bebd6e69b65f6d834359c15065e7057c3773acb7a9de98a9b605ba816e044` |
| `cli-tui-probe.log` | 499 | `f50c3aa232a4daed9849b6ce8a2e02f68bf3e0f69ac0ab638a5a79ac675fb379` |
| `cli-tui-render.bin` | 15731 | `8ade2127e3e48a111040ee2896d8bfe2af7b221d430b70c5b86ffb1feb414290` |
| `cli-tui-added-file-inspect.log` | 2319 | `95a40b74f4060f389eefc3485e557a661a843e168203a7d78b524a5ad57212f2` |
| `cli-post-tui-root-status-v2.log` | 1716 | `c0bdc89075e40ae34fea195552847e5a00540f1e75fafb48e13c363b5e0d5cf9` |
| `final-identity-tests.log` | 464 | `3bc2010c9939ea3558ae46faa22ca37e8b50e27d4fb3edb0ef1ef296852aa543` |
| `final-python-style.log` | 1114 | `5aafa4446936bc3fbf7126dbb60ef8386956b8b868af23c24571388f57bfb675` |
| `final-flake8-configured.log` | 419 | `a33e9dc67e674d96ca2474cad29d8ebae48e9fd9b91725e1ca2e60e36ff08025` |
| `runtime-cleanup.log` | 2984 | `877729c4260a6f45faeed1ca8be947fcb472654d2f65fd5469317ea8757830d5` |
| `final-resource-state.log` | 424 | `0d9e2f4d1dbfe8733bff235849876b40ae566377f72bed1741be848ca3dbe1ac` |

### Acceptance disposition

Overall Spec005 acceptance remains **INCONCLUSIVE / not accepted**. The required
replacement-container identity gate is **FAIL**: the new container retained the enrolled
PID/mount namespace identity and readiness still reported `enrolled`. Because the probe
stopped at that comparison, it did not establish the later fail-closed write-denial path.
Do not treat the replacement as safe, do not launch a write-enabled replacement, and do not
reenroll or rebind. Next diagnostic should compare namespace identifiers across two
simultaneously running host-network containers, then across a stop/recreate using separate
marked synthetic roots; no real root or write-enabled replacement. RB-5 stays unchecked.

FR-044 protected names remain denied. Windows bridge and host Ollama access remain blocked;
browser/Ollama runtime, NTFS-to-ext4 relocation, real-fund operation, cutover and container
rebind remain unsupported, blocked or unverified. Independent QA remains pending.

## Runtime-incarnation trust change: code evidence and Docker disposition

This addendum preserves the earlier replacement-container observation. That observation
was made against source `7ec7aaa` before the runtime-scope fix; it is not evidence that
the committed fix passed a container replacement test. Overall Spec005 acceptance remains
INCONCLUSIVE.

### Source implementation and tests

- Code commit: `0b6f30aeb0c504a7741fc4e2adcda8ead06139d8`, parent
  `b7af9b57fba9bb1c0998073599167a041a37fdc9`, branch
  `cgjedrem-super-fiesta`. Commit includes the Copilot coauthor trailer. No push or merge.
- Source package digest: `99ea8cd62078af860570388d768ba827c84ae659d911f46c842b15f3a56448e1`,
  computed from `hedge_fund` using `hedge_fund.runtime.build_identity.source_sha256`.
  The Docker revision and digest were explicit operator-supplied build args. A failed
  build produces no image provenance mapping.
- Source validation ran Python 3.11.15 / pytest 7.4.4 on Windows/NTFS, from
  `2026-11-06T08:45:29.075859+01:00` through
  `2026-11-06T08:49:37.532335+01:00`. Exact pytest command:

  ```text
  C:\Users\ChristianGjedrem\AppData\Local\pypoetry\Cache\virtualenvs\aihf-WidgQWGy-py3.11\Scripts\python.exe -m pytest hedge_fund/runtime/test_handover.py hedge_fund/runtime/test_write_authority.py hedge_fund/runtime/test_admission.py hedge_fund/test_run.py hedge_fund/tui/test_admission_regressions.py hedge_fund/web/test_app.py hedge_fund/web/test_main.py hedge_fund/web/test_services.py hedge_fund/web/test_write_authority.py -q --tb=short
  ```

- Result: **277 passed, 7 skipped in 243.46 s**; pytest process elapsed
  `246.066527 s`. Black, isort, Flake8 and `git diff --check` all exited 0.
  This is targeted unit/fake-test evidence, not a full-suite or Docker runtime result.
- Exact stdout/stderr, per-command durations and manifest:
  `outputs/spec005-runtime-incarnation-20261106/source-validation-9dd1e095/`.
  Manifest SHA-256:
  `617e820f69575911f6f8011abd87362fb09f82ae12cfc7ab7192ea4cf2c6a77c`.
  The validated source revision had no tracked diff; empty-diff SHA-256:
  `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`.

### Final Docker image build: BLOCKED

- Attempted image tag:
  `aihf-web:0b6f30aeb0c504a7741fc4e2adcda8ead06139d8-99ea8cd62078af860570388d768ba827c84ae659d911f46c842b15f3a56448e1`.
  No image ID was produced; this tag is not an artifact mapping.
- Exact build command:

  ```text
  docker build --network=none --pull=false --progress=plain --file Dockerfile.web --tag aihf-web:0b6f30aeb0c504a7741fc4e2adcda8ead06139d8-99ea8cd62078af860570388d768ba827c84ae659d911f46c842b15f3a56448e1 --build-arg AIHF_SOURCE_REVISION=0b6f30aeb0c504a7741fc4e2adcda8ead06139d8 --build-arg AIHF_SOURCE_SHA256=99ea8cd62078af860570388d768ba827c84ae659d911f46c842b15f3a56448e1 .
  ```

- Build interval:
  `2026-11-06T08:55:10.699385+01:00` to
  `2026-11-06T08:55:23.193607+01:00`; elapsed `12.494129 s`; exit 1.
  BuildKit failed at `pip install poetry==2.5.1`: network was disabled, `/simple/poetry/`
  name resolution failed, and pip reported `No matching distribution found for
  poetry==2.5.1`. The concurrent `npm ci` stage was cancelled. No alternate build path,
  dependency download, or network-enabled retry was attempted.
- Exact build artifacts:
  `outputs/spec005-runtime-incarnation-20261106/docker-build-35f780ed/`.
  `build.stdout.bin`: 0 bytes, SHA-256
  `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`.
  `build.stderr.bin`: 8,726 bytes, SHA-256
  `5a7bc9b0be6584ed040921fba00bf3e8e665b10059d085ea8c5b9528a2a274a9`.
  Build manifest SHA-256:
  `7675a6f2d595893463a57075eab4f4c4dcf4e3d08869fa7c239e8f2b3e2beb33`.

### Docker runtime acceptance: BLOCKED / NOT RUN

- Read-only final inventory ran from `2026-11-06T09:04:52.120892+01:00` through
  `2026-11-06T09:04:55.180385+01:00`. Environment: Docker client/server 29.9.2,
  Compose 5.6.1, context `desktop-linux`, Docker server `linux/x86_64` on Windows
  Docker Desktop. This is not a native Linux host observation.
- Exact per-command stdout/stderr and hashes:
  `outputs/spec005-runtime-incarnation-20261106/docker-final-inventory-20261106T0900/`.
  Manifest SHA-256:
  `df1182725153e44ac9ebac1b6cd8d0463550c68a65442051e622fac88d9e18cc`.
- The uniquely named task project had no containers, service container, volume or network.
  Inspection of the exact attempted image tag returned `No such image`. No task container
  or volume was started or created; no API request, loopback or forwarded-port probe ran.
- Runtime A enrollment/trust; runtime B stale-trust denial and explicit re-trust;
  one synthetic paper deployment; runtime C replacement denial; ext4 confirmation;
  host/Origin/API behavior; same-fund exclusion; protected-name attempts; and TUI runtime
  behavior are all **BLOCKED / NOT RUN** in Docker. No secrets, provider, market-data,
  LLM, broker, real root or real fund were used. CSRF, stale/ambiguous recovery and
  same-fund behavior were not observed in a Docker runtime and are not claimed here.
- The source test result above does not establish the A→B→C container behavior. The prior
  replacement finding is not yet resolved by runtime evidence. Resume only with the
  approved final image build and synthetic-volume protocol; do not infer acceptance from
  the unit tests or the absent-image inventory. Independent QA remains coordinator-owned.

## 2026-11-07 operator-trust gate and final-image continuation

### Source and artifact identity

- Prior implementation commit: `c77163e3862410813af5497a82f0ad6a0badda59`; package
  SHA-256 `d02fdc6fd43d9fe22eae4c9410b7adc0e3b2bc6e3ac16b3dda4d6bedb93107a5`;
  image `aihf-web:c77163e3862410813af5497a82f0ad6a0badda59-d02fdc6fd43d9fe22eae4c9410b7adc0e3b2bc6e3ac16b3dda4d6bedb93107a5`;
  image ID `sha256:1d075886ed7ba5458cbedda0e8b257d7322b0e4dd32a8efc4f5d3d504be011a2`.
- Runtime finding below belongs only to that `c77163e` artifact. It caused a focused
  source correction in commit `1846c970acd88d836a84ae03a9699966c31154df`.
- Corrected source was clean at build start: full revision
  `1846c970acd88d836a84ae03a9699966c31154df`; selected-package SHA-256
  `415e28b31527c2a10c295ef92d2729c8a60e8d39604d3df26d1dd0fac8ec5cab`.
- Final image: `aihf-web:1846c970acd88d836a84ae03a9699966c31154df-415e28b31527c2a10c295ef92d2729c8a60e8d39604d3df26d1dd0fac8ec5cab`;
  ID `sha256:a834e17d6b4d627ea4132a3ed223c38c0bf219eb659e41b3ff2faa7af6283713`;
  `linux/amd64`. Revision and package-digest labels match the build inputs.
- Environment: Windows 11 Enterprise build 26200, Python 3.11.15, pytest 7.4.4;
  Docker Desktop client/server 29.9.2, context `desktop-linux`, Linux/amd64 under the
  Windows Docker Desktop LinuxKit/WSL2 engine. Not a native-Linux observation.
- Final build command:
  `docker build --pull=false --file Dockerfile.web --build-arg AIHF_SOURCE_REVISION=1846c970acd88d836a84ae03a9699966c31154df --build-arg AIHF_SOURCE_SHA256=415e28b31527c2a10c295ef92d2729c8a60e8d39604d3df26d1dd0fac8ec5cab --tag aihf-web:1846c970acd88d836a84ae03a9699966c31154df-415e28b31527c2a10c295ef92d2729c8a60e8d39604d3df26d1dd0fac8ec5cab .`
- Build: `2026-11-07T10:01:43.6594073+01:00` →
  `2026-11-07T10:02:33.5713712+01:00`; **49.909 s**, exit 0. No network restriction
  was used. Full captured tool output: temporary host file
  `C:\Users\ChristianGjedrem\AppData\Local\Temp\1794042115552-copilot-tool-output-47764-aa9bc3cc-8988-4a82-80c6-7a0369c53c79.txt`,
  27,876 bytes, SHA-256
  `abf58b89fec29111bd6cde00ba4e10ab35556cf0f484a10c647846df17190a0d`.
- The prior `c77163e` image build passed in **72.642 s** at
  `2026-11-07T09:36:38.2482749+01:00`–`09:37:50.8905149+01:00`; that image is
  superseded for web activation and retained only as historical runtime evidence.
  Exact command was `docker build --pull=false --file Dockerfile.web --build-arg
  AIHF_SOURCE_REVISION=c77163e3862410813af5497a82f0ad6a0badda59 --build-arg
  AIHF_SOURCE_SHA256=d02fdc6fd43d9fe22eae4c9410b7adc0e3b2bc6e3ac16b3dda4d6bedb93107a5
  --tag
  aihf-web:c77163e3862410813af5497a82f0ad6a0badda59-d02fdc6fd43d9fe22eae4c9410b7adc0e3b2bc6e3ac16b3dda4d6bedb93107a5 .`.
  Its raw build log is not retained as a separate task artifact.
- Two successful normal builds were run, not the single build originally planned: the
  first image exposed the no-trust activation failure; the source correction invalidated
  that artifact for final behavior, so the second build maps to corrected commit `1846c97`.
  No further image build was run.

### Historical runtime result — `c77163e` image

- Scenario: Compose host-network profile, read-only rootfs, `CAP_DROP=ALL`,
  no-new-privileges, no published ports, test network guard, and one synthetic ext4
  volume `aihf-spec005-g5-ext4-c77163e-20261107-0940`, mounted at `/data` and
  `/app/outputs`. Compose configuration passed **16/16** assertions at
  `2026-11-07T09:43:08+01:00`. Runtime ran on
  Windows Docker Desktop/LinuxKit, not native Linux.
- Owned synthetic root:
  `/app/outputs/spec005-test-g5-c77163e-20261107-0940/recovery-root`.
  The root had a test-owned marker and was freshly enrolled. `enroll-fresh` returned
  mode `fresh`, inventory digest
  `44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a`, and
  authority `protocol-native`. No `handover inspect` or `trust-single-writer` command ran.
- Initial API capabilities: `read_only=true`, `writes=false`, `network=false`.
  After no-trust SIGHUP, the same PID 1 creation time (`103081`) and PID namespace
  inode (`4026532926`) remained, but capabilities became `read_only=false`,
  `writes=true`, `network=true`, with `write_authority=protocol-native`.
  **Result: FAIL** against the no-trust/read-only requirement.
- An unauthenticated POST returned **403 `capability-denied`**. No valid authenticated
  mutation was submitted; no state mutation was observed. The exact container
  `4f2f24871f438e2232a8806a1c9bdf19de8d36a28c5ba2ba8bfef2396c3034e8` was stopped
  after the failure. No writable replacement, positive trust/HUP, stale-trust B,
  fresh replacement trust, or C scenario ran.
- The test network guard was configured, but outbound-denial behavior was not separately
  probed. Capability `network=true` is an observed exposure, not an observed external
  request. No market/data, LLM, broker, paid-provider or real-root calls occurred.
  Host/Origin/CSRF, protected-name (`watchtower`, `watchtower-weekly`, `umbrella`),
  same-fund, recovery and valid-write runtime cases were not run in this attempt; older
  `7ec7aaa` checks are not carried forward. Existing source guards were not relaxed.
- Exact runtime probe timestamps and raw stdout/API logs were not retained in the
  surviving task artifacts; only this owner-observation summary remains. A read-only
  Docker event query returned no rows. Do not assign runtime timestamps from the
  image-build time. The runtime failure is historical to `c77163e`, not a pass for
  the corrected image.
- Exact task-owned containers and the synthetic volume were inspected and removed;
  no project network remained. Final `docker ps -a` and named-volume queries returned
  no owned resources. No prune ran. Both image artifacts remain. Ignored helper
  `outputs/spec005-g5-runtime-c77163e-20261107-0940/compose.g5.ext4.yml` remains.

### Correction and focused source evidence

- Source review found `_current_write_authority()` treated generic `has_write_authority()`
  as sufficient; that predicate accepts both `protocol-native` and
  `operator-trusted-single-writer`. Commit `1846c97` now admits only the explicit
  `TRUSTED_SINGLE_WRITER_AUTHORITY` after current enrollment and inventory verification.
- Final corrected-source tests ran sequentially on Windows 11/NTFS, Python 3.11.15,
  pytest 7.4.4:

| Timestamp (+01:00) | Exact command | Result |
|---|---|---|
| `09:59:58.9377556`–`10:00:01.5579807` | `C:\Users\ChristianGjedrem\AppData\Local\pypoetry\Cache\virtualenvs\aihf-WidgQWGy-py3.11\Scripts\python.exe -m pytest hedge_fund/web/test_supervisor.py -q --tb=short` | **20 passed in 0.11 s**; process elapsed **2.619 s**; exit 0 |
| `10:00:01.5691374`–`10:00:21.3781487` | `C:\Users\ChristianGjedrem\AppData\Local\pypoetry\Cache\virtualenvs\aihf-WidgQWGy-py3.11\Scripts\python.exe -m pytest hedge_fund/runtime/test_write_authority.py -q --tb=short` | **41 passed in 17.60 s**; process elapsed **19.810 s**; exit 0 |
| `10:00:21.3781487`–`10:00:33.9508336` | `C:\Users\ChristianGjedrem\AppData\Local\pypoetry\Cache\virtualenvs\aihf-WidgQWGy-py3.11\Scripts\python.exe -m pytest hedge_fund/web/test_write_authority.py -q --tb=short` | **3 passed in 9.77 s**; process elapsed **12.572 s**; exit 0 |

- The new supervisor parameterized regression denies `protocol-native` and admits
  `operator-trusted-single-writer`. These are fake/unit observations, not final-image
  runtime behavior.
- Black (`--check --line-length 420`), isort (`--check-only --profile black`),
  Flake8 (`--ignore=E203,W503 --max-line-length=420`), and `git diff --check` all
  passed at `2026-11-07T10:00:39.6311718+01:00`–`10:00:42.0590819+01:00`;
  **2.426 s**, exit 0. The first Black check at `09:59:40.4681242+01:00`–
  `09:59:43.1928436+01:00` exited 1 because it would reformat one conditional; the
  reason assignment was simplified and all tests/static checks reran on the final
  source before commit.
- Earlier passing tests against `c77163e` do not transfer to corrected behavior.
  Final-image runtime A, explicit trust/HUP positive, B stale-trust denial, fresh
  replacement trust, and C remain **NOT RUN** under the fail-stop rule. Final runtime
  acceptance is **INCONCLUSIVE / not accepted**; RB-5 stays unchecked. Independent
  QA remains coordinator-owned.

### Corrected final-image Compose configuration

- Command:
  `docker compose --profile web-operator --file docker-compose.yml --file docker-compose.linux.yml config --format json`.
  Build revision and package digest were set to `1846c970acd88d836a84ae03a9699966c31154df`
  and `415e28b31527c2a10c295ef92d2729c8a60e8d39604d3df26d1dd0fac8ec5cab`.
  `AIHF_DATA_ROOT` pointed at the existing repository `outputs` directory for config
  interpolation only; no service or container started.
- `2026-11-07T10:10:38.4028187+01:00`–`10:10:38.6012255+01:00`, **0.198 s**,
  **9/9** assertions, exit 0: exact final image tag, host network, read-only rootfs,
  `CAP_DROP=ALL`, no-new-privileges, no published ports, matching build revision and
  digest, and service presence.
- Two config-only harness attempts failed and were corrected without resource changes:
  missing `AIHF_DATA_ROOT` caused Compose's required-variable error (exit 1); a first
  PowerShell check treated the empty/null `ports` field as present at
  `10:10:23.5290529+01:00`–`10:10:23.7573993+01:00` (**8/9**, **0.227 s**, exit 1).
  The corrected null/empty check passed above. A pre-build Python helper probe imported
  nonexistent `package_digest` (exit 1); it was corrected to the module's
  `source_sha256` before computing build args. No incorrect image was built and no
  config-only attempt started a container or changed a resource.

### Remaining unknowns and smallest falsification experiment

- The failed `c77163e` runtime used a marker-owned fresh synthetic root that classified
  as `protocol-native`; it did not exercise a trust-required migration-mode root. The
  CLI trust command was not run. The new unit regression checks the supervisor's two
  authority classes, not the CLI challenge flow or the final image.
- Unknown: whether a trust-required synthetic root can complete the intended same-container
  CLI inspect/trust/HUP lifecycle on the corrected image, and whether replacement identity
  denies stale trust on that artifact.
- Smallest next check, only after coordinator authorization: start the corrected image
  against a uniquely named synthetic ext4 root whose existing test fixture yields
  trust-required migration authority; verify initial read-only and no-trust HUP remains
  read-only. Stop on any mismatch. Only after that pass, proceed to explicit trust/HUP
  and replacement cases under a renewed fail-stop boundary.

### 2026-11-07 supervisor lifecycle repair, final image, and runtime blocker

#### Source identity and focused checks

- Implementation/docs commit `2b4cbed2a20c6f9877cbbc762e6df378c960d3f8`,
  parent `66bc100`; commit message includes the requested Copilot coauthor.
  The committed source diff is 29,256 bytes,
  SHA-256 `42cff85f38eb517236539f88dd184841ec42577ed42a28e4090e269901c868c4`.
  Package-source SHA-256 is
  `3f1922909961798b36353a9309c4de9ddc6651b031f2ac7c0dd1ff529550cbd5`.
- Tests used Python 3.11.15 and pytest 7.4.4 on the Windows host. The test tree
  matched the implementation diff later committed as `2b4cbed`.
  Exact executable:
  `C:\Users\ChristianGjedrem\AppData\Local\pypoetry\Cache\virtualenvs\aihf-WidgQWGy-py3.11\Scripts\python.exe`;
  table commands use that interpreter for `python -m pytest`.

| Timestamp (+01:00) | Exact command | Result |
|---|---|---|
| `10:47:13.3123264`–`10:47:17.1456680` | `python -m pytest hedge_fund/web/test_supervisor.py -q` | **26 passed, 1 skipped**; pytest 0.18 s, process wall 3.83 s, exit 0. POSIX Popen-status test skipped on Windows. |
| `10:47:17.1537829`–`10:47:20.0517434` | `python -m pytest hedge_fund/runtime/test_process_identity.py -q` | **6 passed**; pytest 0.14 s, process wall 2.90 s, exit 0. |
| `10:47:20.0529208`–`10:47:54.3545676` | `python -m pytest hedge_fund/runtime/test_handover.py hedge_fund/runtime/test_write_authority.py -q` | **59 passed**; pytest 31.01 s, process wall 34.30 s, exit 0. |
| `10:47:54.3545676`–`10:48:02.8445110` | `python -m pytest hedge_fund/test_run.py -k handover -q` | **7 passed, 75 deselected**; pytest 4.29 s, process wall 8.49 s, exit 0. |
| `10:48:02.8445110`–`10:48:19.1453039` | `python -m pytest hedge_fund/web/test_app.py -q` | **52 passed**; pytest 12.42 s, process wall 16.30 s, exit 0. |
| `10:48:19.1453039`–`10:48:41.6936698` | `python -m pytest hedge_fund/web/test_paper_operations.py::test_owned_runner_reattaches_after_web_restart_and_parallel_manager -q` | **1 passed**; pytest 19.27 s, process wall 22.55 s, exit 0. |

- Black `--check`, isort `--check-only`, Flake8
  (`--max-line-length=420 --extend-ignore=E203,W503`), `git diff --check`,
  and AST parsing of the three synthetic runtime scripts passed at
  `10:49:07.6770590`–`10:49:10.2766657+01:00`, wall 2.60 s, exit 0.
- Merged Compose configuration passed at
  `10:49:07.7437494`–`10:49:07.9936840+01:00`, wall 0.25 s: host network,
  no published ports or Compose networks, 30 s stop grace, read-only rootfs,
  `cap_drop=ALL`, no-new-privileges, synthetic `/data` volume, and explicit
  trust-gated writes.

#### Build identity and artifact

- Clean committed source was built with normal dependency-enabled networking;
  `--network none` was not applied to the build. Exact command:

  ```text
  docker compose --progress plain --project-name aihf-lifecycle-20261107-102921 \
    -f docker-compose.yml -f docker-compose.linux.yml \
    -f outputs/spec005-supervisor-lifecycle-20261107-102921/compose.lifecycle.yml \
    --profile web-operator build --pull=false web-operator
  ```

- `AIHF_SOURCE_REVISION=2b4cbed2a20c6f9877cbbc762e6df378c960d3f8`;
  `AIHF_SOURCE_SHA256=3f1922909961798b36353a9309c4de9ddc6651b031f2ac7c0dd1ff529550cbd5`.
  Build start/end `2026-11-07T10:51:01.2027564+01:00`–
  `10:51:51.4720774+01:00`; build subcommand exit 0, **50.27 s**.
- Environment: Docker Desktop 29.9.2, LinuxKit, kernel
  `6.6.87.2-microsoft-standard-WSL2`; image OS/architecture `linux/amd64`.
- Image tag
  `aihf-web:2b4cbed2a20c6f9877cbbc762e6df378c960d3f8-3f1922909961798b36353a9309c4de9ddc6651b031f2ac7c0dd1ff529550cbd5`;
  image ID `sha256:ededc795ef56179fc923a28043a3e00d424558b5f06bc20d0f2e43f0716c430e`.
  OCI revision/package labels and in-image `baked_build_identity()` both matched.
- The first two post-build Go-template label probes exited 64 due PowerShell
  quoting; the build itself had already returned 0. Corrected JSON inspection and
  a `docker run --network none` identity probe passed at
  `10:52:15.4951821`–`10:52:16.2972948+01:00`, wall 0.80 s. No rebuild followed.

#### Synthetic runtime observation and stop

- One uniquely named local volume was created:
  `aihf-supervisor-lifecycle-20261107-102921`, owner label
  `spec005-supervisor-lifecycle-20261107-102921`. The guarded migration fixture
  verified ext4, enrollment `enrolled`, mode `migrate-existing`, authority
  `ownership-unknown`, inventory digest
  `be0dfde7a94765b90cf25161a34a96b10c69c626f6b37bbc3e021913722d120b`.
- The fixture was prepared by a one-shot helper container, then serviced by
  Compose container
  `885eb400a8d8964dd98889151c3468076902cf1a19c94dcda22132584b35e206`.
  Actual inspection showed host networking, empty `HostConfig.PortBindings`,
  read-only rootfs, `cap_drop=ALL`, `no-new-privileges:true`, two RW mounts of
  the exact labeled volume, and no provider credential or proxy environment names.
- Initial API capabilities were `writes=false`, `network=false`,
  `enrollment_state=invalid`, `write_authority=unavailable`, and
  `write_unavailable_reason=handover-unavailable`. Read-only `require_enrollment`
  raised `EnrollmentInvalid: handover root identity does not match`.
- A read-only binding comparison showed matching path, ext4 filesystem, device
  `2096`, root identity `[2096, 867395]`, PID namespace
  `4026532926`, and mount namespace `4026532923`. The immutable `host` field
  differed: helper container `41f91cc779f6`, service container `docker-desktop`.
  `root_binding()` includes host and namespace. This is a safe enrollment denial;
  no rebind was attempted.
- **A startup read-only: PASS. Helper-to-service enrollment reuse: FAIL.**
  Explicit CLI trust/HUP, no-trust HUP, downgrade/revoke, API boundary probes,
  fake orphan reaping, B replacement, and C replacement are **NOT RUN**.
  No valid write, trust command, or revoke command ran. Overall lifecycle
  acceptance is **INCONCLUSIVE / not accepted**; RB-5 remains unchecked.
- The exact A container stopped with exit 0 and was removed. Its exact owner-labeled
  volume was removed after checking the project/service labels, full container ID,
  and absence of other volume users. Image remains available; no prune ran.
  Runtime interval was Windows Docker Desktop/LinuxKit, not native Linux.
- This result does not alter historical runtime outcomes: the prior
  `c77163e` no-trust HUP failure remains attributed only to that artifact.
  No provider, market-data, LLM, broker, paid-service, real-root, or real-fund
  action occurred. Independent QA remains coordinator-owned.
- Manual self-review found no additional in-scope source finding. POSIX reaping,
  HUP promotion, downgrade/revoke, runtime API negatives, and replacement behavior
  remain unobserved on this image; the Windows-only test skip does not transfer to
  Linux runtime. Do not claim those runtime rows passed.
- Smallest future falsification experiment, not authorized or run here: prepare a
  new synthetic migration fixture within the exact target service `RootContext`,
  compare its immutable `root_binding()` before any trust action, and stop on
  mismatch. If replacement changes that immutable binding, record the denial and
  do not rebind.
