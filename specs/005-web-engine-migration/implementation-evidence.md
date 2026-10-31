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
