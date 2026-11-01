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
