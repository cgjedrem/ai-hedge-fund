# Acceptance Evidence

Status: implementation phase complete for T001–T022. T023 is partial because protected-root content identity is inconclusive. Independent QA and PR handoff remain with the coordinator.

## Environment and revision

- Baseline revision: `85e5ec618e40cec2a994faebd16b8717c5888df8`; branch `cgjedrem-fictional-winner`.
- Worktree: Windows 11, Python 3.13.7, Poetry 2.5.1, Node 22.13.1, npm 10.9.2, Playwright 1.64.1, Chromium build v1248, Docker 29.9.2. GNU Make unavailable.
- Historical progress-checkpoint SHA-256: `f7eee7fa30a4a341047425bd00671ece8ac3878f911a09064f7fd1472c276bc0` at `2026-10-30T17:17:49.4684515Z`; not final-artifact evidence.
- Final implementation-input identity before evidence-doc edits: SHA-256 `eec381c33fd1ccce1f55a3341d32000d3f41bd932f3bb8a42ec3be6d4bc04cb2`. Covers 67 changed/untracked non-spec files by sorted path and current bytes; excludes `specs/004-react-web-ui/`, `memory.md`, and generated static assets. Base revision above.
- Final implementation commit: `b183ac7b7ad34fdc085526cf8c8a56891a2327dc`, committed `2026-10-30T19:24:07+01:00`. Evidence follow-up contains this source revision.
- Production static tree: SHA-256 `0da7625137a3aaa59a9034e25cbff6f062317fae4cc3a5eb2068a4e1abc8ea9e`.
- Temporary wheel `aihf-2.6.1-py3-none-any.whl`: SHA-256 `25edb5fef57c676e1b6e31442a635f993ef46572a0745b3bed2fc3fa4f5a30d0`.
- Synthetic screenshot tree: 17 PNG files, SHA-256 `3531686516b9d093970cd86da59b793487e943b50f9e876b7644eb775146770b`.

## Implementation progress evidence (historical)

These rows preserve intermediate checks. Final-artifact results follow separately.

| Result | Scenario and provenance | Exact command and observation |
|---|---|---|
| PASS | API boundary unit tests; temporary `tmp_path`; FastAPI `TestClient`; no network adapter; revision `85e5ec6`; dirty-diff SHA-256 above; Python 3.13.7 on Windows; `2026-10-30T17:18:08.5497653Z`–`2026-10-30T17:18:12.1483536Z`. | `python -m poetry run pytest hedge_fund/web/test_app.py -q` — 5 passed in 0.43s; exit 0. |
| PASS | API boundary, seeded read adapters, ledger approval actor, and explicit research-root regression tests; synthetic root under pytest temp; outbound socket tests deny non-loopback; revision `85e5ec6`; dirty-diff SHA-256 `960e13f7c06423cbe41e4aca82c6ca6b6106e5d8569d89d664d5fc5305447807`; Python 3.13.7 on Windows; `2026-10-30T17:20:39.2599976Z`–`2026-10-30T17:20:44.0539752Z`. | `python -m poetry run pytest hedge_fund/web/test_app.py hedge_fund/web/test_services.py hedge_fund/paper/test_ledger.py hedge_fund/backtesting/test_research.py -q` — 32 passed in 1.57s; exit 0. |
| PASS | Full web test package plus affected ledger/research regressions; temporary synthetic roots; tests denied non-loopback sockets; revision `85e5ec6`; dirty-diff SHA-256 `9f2e99573d50f1d9be8bdf3a3c3955f6633d8325d717769f8b3f898412f2f2ec`; Python 3.13.7 on Windows; `2026-10-30T17:23:22.2715982Z`–`2026-10-30T17:23:27.5750528Z`. | `python -m poetry run pytest hedge_fund/web hedge_fund/paper/test_ledger.py hedge_fund/backtesting/test_research.py -q` — 45 passed in 1.30s; exit 0. |
| PASS | Changed Python style gates; revision and dirty-diff SHA-256 as preceding row; Python 3.13.7 on Windows; same invocation window. | `black --check <explicit changed Python files>`, `isort --check-only <same files>`, `flake8 --max-line-length=420 <same files>` — all exit 0. |
| INCONCLUSIVE | Pre-change suite attempt was interrupted in earlier baseline runs. A safe package slice completed before implementation; test output showed a Windows formatting failure, not a feature regression. Exact timestamp was not captured, so this is not a revision-bound acceptance row. | `python -m poetry run pytest hedge_fund/backtesting hedge_fund/data hedge_fund/features hedge_fund/fund hedge_fund/llm -q` — 548 passed, 36 skipped, 1 failed in 104.33s. Failure: `hedge_fund/features/test_intraday.py::test_a_headline_a_filing_or_a_band_crossing_changes_the_block`; `strftime("%b %-d %H:%M")` raised `ValueError: Invalid format string` on Windows. |

## Final-artifact evidence

| Result | Scenario and provenance | Exact command and observation |
|---|---|---|
| PASS | Final backend adapters after root-specific `.env` loading; pytest temp roots; fake credentials; non-loopback DNS/connect denied; loopback allowed; baseline revision plus implementation-input SHA above; Windows/Python 3.13.7; `2026-10-30T18:19:28.018922+00:00`–`2026-10-30T18:19:31.145599+00:00`. | Inline network-guard wrapper ran `pytest.main(["hedge_fund/web", "hedge_fund/paper/test_ledger.py", "hedge_fund/backtesting/test_research.py", "-q"])` — 49 passed in 1.55s; process exit 0. Includes root `.env` load, shell-over-file precedence, write-only sentinel, protected names, stale approval, fake backtest jobs and research persistence. |
| PASS | Root `.env` configuration and precedence regression; pytest temp roots; fake secret; no external sockets; `2026-10-30T18:19:17.584374+00:00`–`2026-10-30T18:19:19.510339+00:00`. | Same guarded runner with `pytest.main(["hedge_fund/web/test_settings.py", "-q"])` — 5 passed in 0.14s; process exit 0. |
| PASS | React unit tests on the final implementation-input identity above; Node 22.13.1; `2026-10-30T18:22:47.5851016Z`–`2026-10-30T18:23:01.5248519Z`. | `cd frontend; npm test` — 4 passed in 12.30s; process exit 0. JSDOM emitted Recharts zero-size and React Router future-flag warnings. |
| PASS | Final production bundle served by FastAPI demo process on `127.0.0.1:8765`; synthetic temp root; Chromium; external-request listener active before first navigation; `2026-10-30T18:19:36.3621050Z`–`2026-10-30T18:20:03.6323022Z`. | `cd frontend; npm run e2e` — TypeScript check passed; Vite built 2,299 modules; 1 Playwright test passed in 10.9s. All 11 configured routes and research detail rendered at 1440px and 390px; no horizontal overflow; zero external browser requests. 12 desktop and 5 mobile synthetic screenshots written. |
| PASS | Changed Python style gates; baseline revision plus implementation-input SHA above; Python 3.13.7; `2026-10-30T18:19:16.1068728Z`–`2026-10-30T18:19:22.1869113Z`. | `black --check hedge_fund/web hedge_fund/backtesting/research.py hedge_fund/paper/ledger.py hedge_fund/paper/test_ledger.py hedge_fund/tui/keys.py`; `isort --check-only` on same targets; `flake8 --max-line-length=420` on same targets — all exit 0; Black reported 18 files unchanged. |
| PASS | Python package artifact after final Python changes; temporary output directory; `2026-10-30T18:20:11.0314186Z`–`2026-10-30T18:20:13.1474940Z`. | `python -m poetry build --format wheel --output <temporary directory>` — built `aihf-2.6.1-py3-none-any.whl`, SHA-256 above; archive contains `hedge_fund/web/static/index.html` and both hashed CSS/JS assets (3 static entries). Temporary wheel directory removed. |
| PASS | Compose syntax only; no image/container started; `2026-10-30T18:15:31.9978851Z`–`2026-10-30T18:15:32.4889384Z`. | `docker compose -f docker-compose.yml -f docker-compose.linux.yml config --quiet` — exit 0. |
| INCONCLUSIVE | Static frontend injection/remote-reference scan; exact timestamp not captured. | `rg -n "dangerouslySetInnerHTML|innerHTML|https?://" frontend/src frontend/index.html` — no matches. Browser request test independently observed zero external requests. |
| FAIL | TUI credential save test after resolving the default path at call time; pytest temp `.env`; fake credential; non-loopback DNS/connect denied; `2026-10-30T18:09:41.904828+00:00`–`2026-10-30T18:09:47.289471+00:00`. | Guarded `pytest.main(["hedge_fund/tui/test_home.py", "-q"])` — 8 passed, 1 failed. The saved file was the fixture temp path and content assertions passed; Windows `stat.S_IMODE` reported `0o666` after chmod while the test expects POSIX `0o600`. This platform assertion remains unresolved; no TUI permission behavior change was attempted. |
| PASS | Real credential-file metadata only; no contents read by this check; `2026-10-30T18:23:17.5983104Z`–`2026-10-30T18:23:17.6364418Z`. | `Get-Item` on `~/.hedge-fund/.env` — length 509 bytes; `LastWriteTimeUtc=2026-10-26T15:33:49.5078305Z`. Timestamp matched the prior metadata observation. |

### Existing-suite observations not bound to the final diff

These chunked outcomes were captured during earlier implementation runs. Exact run timestamps/diff identities were not retained, so they are not final PASS evidence. Failures are reported as observed; no clean baseline rerun is claimed.

- `backtesting data features fund llm`: 548 passed, 36 skipped, 1 failed; Windows `strftime("%b %-d %H:%M")` formatting failure in `features/test_intraday.py`.
- `brokers`: 98 passed.
- `pipeline portfolio risk scorecard secrets signals`: 231 passed.
- `web` plus `test_paths.py`: 28 passed before the root-environment regression test was added; final web-adapter evidence is the 49-pass row above.
- `test_run.py`: pytest printed 30 passed, but process exit was 1; result INCONCLUSIVE.
- Paper slices: deployed-broker 7 passed; ledger 22 passed; runner 11 passed/1 failed; simulated Saxo 8 passed; tick 29 passed/1 failed. The two failures were Windows `FileExistsError` collisions in the existing ledger rewind/redo path; unchanged test and ledger source at baseline `85e5ec6`.
- TUI slices: backtest 2, builder 15, builder-broker 1, funds 4, report 11, scorecard 3 and paper 24 passed; `paper-view` 5 passed/1 Windows `%-d` formatting failure. Daily/minute runner cases were deselected after earlier teardown hangs.

## Safety, runtime gaps and limitations

- Tests and screenshots use explicit pytest temporary roots or the synthetic `--demo` root. No test called a paid data provider, external LLM, broker or live feed. Focused API test runs denied non-loopback DNS/connect; browser E2E denied external requests.
- The final web service loads only the configured root's `.env`, keeps existing process environment values authoritative, and blocks reparse-point paths before reading. The regression test uses fake sentinel values in pytest temp storage.
- Safety deviation: before the `save_credential` default-path fix, a TUI test attempted to read the real `~/.hedge-fund/.env`; decoding failed on Windows. No content was printed and no write completed. The call now resolves the current `ENV_PATH` at runtime; the post-fix test wrote only to its temporary fixture path. Real-file metadata above remained unchanged.
- Safety deviation: an early protected-root fingerprint routine read regular-file contents, including `runner.pid` contents; no PID text was emitted and no process was controlled. This violated the no-PID-read constraint. Further PID reads stopped. Later metadata-only counts/bytes, excluding `runner.pid`, matched the recorded reference, but the prior aggregate-hash algorithm could not be reproduced. Protected-root identity is INCONCLUSIVE; T023 stays unchecked. No protected files were written, runners restarted, rewound, deleted or stopped.
- GNU `make` was unavailable, so Make targets were not executed. The documented direct launcher `poetry run aihf-web --demo --port 8765` was exercised by Playwright through the production static build. Docker Compose config passed, but no image/container was built or started.
- Production JS chunk is 893,484 bytes (261.67 kB gzip), above Vite's 500 kB warning threshold. No code splitting was added.
- Runner lifecycle/manual runs, deletion, redo and live quote fetching remain explicitly deferred. Per-fund locks are process-local. See `parity-checklist.md`.
- The Playwright server stopped after E2E. No persistent preview remains running. Coordinator owns T024 independent QA and T025 PR/preview handoff; no push or PR update was performed here.
