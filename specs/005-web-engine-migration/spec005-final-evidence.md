# Spec005 final bounded-QA evidence

**Disposition: PARTIAL. Not ready to merge.** This closes the supplied service-level QA blockers only. Full migration remains blocked; no new feature, production-write activation or TUI retirement was attempted.

## Candidate identity

| Field | Observation |
|---|---|
| Branch / base | `cgjedrem-vigilant-robot` / `9694f619207e14fb5e55de1bef96deb79df7a360` |
| Combined Python slice source/test identity | The source/test tree used by the `11:26:18.3783384+01:00` → `11:29:20.1900746+01:00` combined run was fingerprinted at `11:35:00.8004159+01:00` → `11:35:01.0587878+01:00`: 41 tracked source/test/screenshot paths / 2,308,082 bytes / SHA-256 `bce6894f9d927bd785e776d07f2c148d4252b1b57445d26e237394a81dc255dc`. `test_actions.py` then received formatting-only cleanup; its complete 28-test module was rerun on the final identity below. |
| Source/test/screenshot identity | At `2026-11-01T11:45:32.6822468+01:00` → `11:45:32.8695038+01:00`: 41 changed tracked `.py`, `.ts`, `.tsx`, `.mjs` and `.png` paths / 2,308,066 bytes / SHA-256 `875ade896c3869ffe4213cba47e7440edceb35d6ed4ce20da91ec25fe9b3e62b`. Hash: sorted UTF-8 repository-relative path + NUL + full worktree bytes + NUL. Includes prior convergence source/tests and changed screenshot files; excludes docs and untracked paths. |
| Screenshot collection | At the same identity check: 17 PNGs / 2,749,128 bytes / SHA-256 `18b4f94915483066e59286ab82626ab26b514e8c01c61729d7d6dafa44629039`, sorted filename + NUL + full bytes + NUL. Directory: `specs/005-web-engine-migration/screenshots/`. |
| Full candidate diff | Full tracked `git diff --binary` identity is recorded in the ignored session log and PR #8 body after commit. It includes all tracked source, test, docs and screenshot changes; untracked `pip/` and `pypa/` are excluded and untouched. |
| Python environment | Windows 11 `10.0.26200`, Python `3.13.7`, existing venv `outputs/spec005-poetry-envs/aihf-Tbl0PwyA-py3.13`. Tests used the marked synthetic root `outputs/spec005-test-final-closure-20261101-01`, isolated HOME/USERPROFILE/TEMP, `PYTHON_DOTENV_DISABLED=1`, `PYTHONDONTWRITEBYTECODE=1`, support+checkout `PYTHONPATH`, and cleared provider, credential and proxy variables. |
| Browser environment | Node `v22.13.1`, npm `10.9.2`, Vite `6.4.5`; isolated HOME, NPM cache/config and offline mode. The owned browser harness cleared credentials/proxies, ran synthetic demo data and verified test-server release plus root cleanup. |

## Corrected service blockers

- `_mandate_writer` acquires the admission registry lock and verifies root inventory before caller file effects. Root drift now denies same-name update and rename before direct write or physical rename.
- `home()` uses `list_research()["total"]`, not the default 50-item page length. Regression covers more than 50 records and a corrupt report.
- `clone_mandate` maps `StorageAdmissionError` to safe HTTP 409.
- Backtest preview uses the same local/free policy classifier as paper operations. Paid or unknown classification denies before operation persistence; `AuthorizationDenied` maps to HTTP 422.
- Rename then rewrite is not transactional. Fault injection shows a failed rewrite leaves original bytes at the new path; retry with the original logical identity succeeds. Crash-atomicity is not established.

## Observed validation

| Evidence | Status | Exact observation |
|---|---|---|
| Root/services/actions/manual-paper regressions | **PASS — scoped synthetic tests** | `2026-11-01T11:26:18.3783384+01:00` → `11:29:20.1900746+01:00`; `outputs/spec005-poetry-envs/aihf-Tbl0PwyA-py3.13/Scripts/python.exe -X faulthandler -m pytest hedge_fund/runtime/test_root.py hedge_fund/web/test_services.py hedge_fund/web/test_actions.py hedge_fund/web/test_paper_operations.py -p no:cacheprovider -q --tb=short -o faulthandler_timeout=120`; subprocess hard timeout 220 s. **112 passed, 1 skipped in 152.76 s**, exit 0. First capture used an incomplete `PYTHONPATH` and emitted the test-child isolation error; it is excluded. Final capture used exact `hedge_fund/test_support;checkout` path and emitted no isolation error. |
| Final action module after format-only cleanup | **PASS — affected file rerun** | `2026-11-01T11:42:41.4153138+01:00` → `11:43:49.6449405+01:00`; `outputs/spec005-poetry-envs/aihf-Tbl0PwyA-py3.13/Scripts/python.exe -X faulthandler -m pytest hedge_fund/web/test_actions.py -p no:cacheprovider -q --tb=short -o faulthandler_timeout=40`; hard timeout 100 s. **28 passed in 55.11 s**, exit 0. Formatting-only; behavior unchanged. |
| React unit tests | **PASS** | `2026-11-01T11:14:48.3439162+01:00` → `11:16:38.6337844+01:00`; from `frontend/`, `npm test -- --reporter=dot`: **2 files / 26 tests passed**, Vitest **101.76 s**, exit 0. |
| TypeScript check | **PASS** | `2026-11-01T11:16:38.6353551+01:00` → `11:16:55.8489008+01:00`; `.\node_modules\.bin\tsc.cmd --noEmit`, exit 0. |
| Direct production build | **PASS with size warning** | `2026-11-01T11:16:55.8489008+01:00` → `11:17:24.5519660+01:00`; `npm run build`, Vite transformed **2,307 modules**, built in **23.40 s**, exit 0. Minified JS chunk is **948.18 kB**; Vite's >500 kB advisory remains. |
| Production bundle identity | **PASS — build artifact only** | `hedge_fund/web/static/` and the wheel's embedded static files both fingerprint to **3 files / 973,294 bytes / SHA-256 `309b88c7a472685221fee0cb89f207d9d72e8f36d9f38a2a9a2301c82df7897a`**. |
| Owned browser E2E | **PASS — synthetic/fake-route only** | `2026-11-01T11:17:54.3331625+01:00` → `11:18:35.4355338+01:00`; `node e2e/run-owned.mjs`, owned loopback port `8876`, `--demo` synthetic root; selected interaction tests use API fakes via `page.route`: **12 passed in 20.3 s**, exit 0. Covered route rendering, cursor wiring, local preview/acceptance UI, stale-head rejection, runner controls, builder round-trip and reload restoration. Browser fakes do not prove backend mutation or real provider behavior. |
| Screenshots | **PASS — synthetic browser evidence** | Captured by the owned E2E run above. Seventeen current PNGs; collection identity and path are recorded above. Seven screenshot paths differ from the prior tracked image bytes. |
| Screenshot filenames | **Current set** | `desktop-backtests.png`, `desktop-builder.png`, `desktop-mandate-detail.png`, `desktop-mandates.png`, `desktop-overview.png`, `desktop-paper-detail.png`, `desktop-paper-list.png`, `desktop-research-list.png`, `desktop-research-report.png`, `desktop-scorecard.png`, `desktop-session-report.png`, `desktop-settings.png`, `mobile-overview.png`, `mobile-paper-detail.png`, `mobile-research-report.png`, `mobile-session-report.png`, `mobile-settings.png`. All under `specs/005-web-engine-migration/screenshots/`. |
| Saxo token diagnostic | **PASS — fake transport/clock** | `2026-11-01T11:20:30.7174908+01:00` → `11:20:32.3529761+01:00`; `python -X faulthandler -m pytest hedge_fund/brokers/test_saxo_tokens.py -p no:cacheprovider -q --tb=short -o faulthandler_timeout=45`; external hard timeout 100 s. **8 passed in 0.19 s**, exit 0. No Saxo service or credentials used. |
| Static checks | **PARTIAL — inherited Black baseline** | `isort --check-only`, flake8 (`--max-line-length=420 --extend-ignore=E203`) and `git diff --check` passed at `2026-11-01T11:42:14.2271967+01:00` → `11:42:16.0328639+01:00`. Black check at `11:42:14.2323081+01:00` → `11:42:17.8292335+01:00` passed for `services.py` and `test_services.py`; `test_actions.py` still requests reformatting, and project-config Black also requests reformatting at base HEAD. Added-line attribution found no Black-diff overlap after formatting convergence additions. |
| Wheel build | **PASS — build only** | Initial attempt was blocked by missing `build`. Public `build==1.6.1`, `poetry-core==2.5.0` and build dependencies were installed into isolated `outputs/.../build-tools` from `https://pypi.org/simple` at `2026-11-01T11:21:29.3649968+01:00` → `11:21:48.0511306+01:00`; no repository/provider credentials. Final no-isolation rebuild at `2026-11-01T11:44:02.7473482+01:00` → `11:44:12.1689334+01:00`, `python -m build --wheel --no-isolation` succeeded: `dist/aihf-2.6.1-py3-none-any.whl`, **653,276 bytes**, SHA-256 `db57b12627fcb5bf86b2587c1842cf7e6a5a9be7de01768d1721f50b68cc19e0`. Static bundle inside matches the built artifact. Pip emitted a target-only packaging-version conflict warning; project venv was not modified. |
| Full Python suite | **INCONCLUSIVE** | Prior attempts stalled at **149 passed / 2 skipped of 1,207 collected**. No full-suite rerun. The bounded Saxo file does not establish suite completion. |
| Wheel install/runtime smoke | **INCONCLUSIVE** | Wheel built and static entries inspected; installation and runtime smoke were not run. |
| Linux/ext4 and actual NTFS ACL | **BLOCKED** | This Windows run provides no native Linux/ext4 or ACL proof. |

## Safety and provenance

- No paid/provider call, real broker, protected fund root, port `8765`, actual watchtower process, or external runtime probe was used.
- No preview server was left running. The E2E harness owned `8876` and verified its server exit. Port `8877` is reserved for the handoff command only; availability must be checked when starting.
- Browser tests that intercept API routes are browser/UI evidence only. Backend pagination and service regressions use separate synthetic fixtures.
- Headless paid-provider defaults remain unsupported. No provider keys are required or to be supplied for the safe demo.
- T015/T021 remain partial. T137/T138/T140/T142–T145/T147/T148 remain open; T139/T141/T146 have bounded partial evidence but stay unchecked. Full migration and TUI retirement remain blocked.

See `qa-final-disposition.md` for readiness, open stop conditions and safe preview instructions.
