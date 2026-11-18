# Implementation Evidence: Ollama Model Selection

**Date**: 2026-11-18 | **Spec**: [spec.md](spec.md) | **Branch**: `cgjedrem-cuddly-winner`

## Build / static verification

- Prior implementation commits: `0b1f8d2` (baseline record), `cb311d2` (catalog validation), `473521e` (error surfacing), `b238e04` (web settings policy), `a46491c` (paid-cloud dispatch gating), `3b39982` (black/isort).
- QA rework commits: `cf37eec` (findings and regressions), `f7e41b7` (readiness error status contract), `7d10fc7` (I-2 catalog fail-closed), `f9808cf` (I-3 authorization-aware refusal).
- **Cycle-1 source snapshot**: final HEAD `f7e41b7cd5192c2db145d11390f431e51eab7780`; diff from amended QA baseline `88f857f27c748cdb9a7076a81b3adc05b284df9b` SHA-256 `8580f44db0875d3fb577e1c162ac33e4fbbca7214bf6730391d412b17eee5cbf`. Final full-suite run started with clean worktree.
- **Cycle-2 source snapshot**: code HEAD `f9808cf902749dbd99c63665f17772fee95a549d`; diff from amended QA baseline `88f857f27c748cdb9a7076a81b3adc05b284df9b` SHA-256 `01f02b00ac48edbe9bf3ee149b7da585a2af538ba157db38a0f183aa9d26616b`. Target and full suites ran from the clean committed tree; no wheel/container artifact built.
- **Historical hash audit**: QA requested `473521e` → `473521f`. Local `git log --all` resolves `473521e8956749764a45cb5946376f86ae0a3d2c`; `git rev-parse --verify 473521f^{commit}` fails. Retain verified local hash; requested replacement remains unverified.
- **Environment**: Windows; Python 3.13.7; Poetry 2.5.1; venv `C:\Users\ChristianGjedrem\AppData\Local\pypoetry\Cache\virtualenvs\aihf-FuzY57Jh-py3.13`. Tests ran from the checkout through Poetry; no wheel/container artifact built.
- black check passed on 17 changed Python files (project line length 420); isort check passed; flake8 passed with `--max-line-length=420 --extend-ignore=E203` (Black-compatible E203). Writer-map test passed; no UTF-8 BOM; `git diff --check` passed.
- **Cycle-2 static checks**: Black reported 10 changed Python files unchanged; isort, flake8 (`--max-line-length=420 --extend-ignore=E203`), and `git diff --check` passed. No writer-map entries added; no raw writes introduced.

## Full suite (T020)

- **Prior implementation (3b39982)**: `poetry run pytest hedge_fund -q` → **26 failed, 3030 passed, 62 skipped** in 5408s (1h30m), 2026-11-17, Windows, Python 3.13.7.
- **Pre-feature baseline (e6f04d2)**: module-level rerun collected 218 tests → **26 failed, 192 passed**. This was not a rerun of only 26 tests; failure set matched prior baseline evidence.
- **QA rework first full run (cf37eec; superseded)**: `poetry run pytest hedge_fund -q`, 2026-11-17 23:47:29–2026-11-18 01:08:31 +01:00 → **25 failed, 3047 passed, 62 skipped** in 4854.44s (1:20:54), exit 1. One new failure, `web/test_app.py::test_every_tagged_service_error_site_uses_a_contract_status`, found `readiness-denied` paired with status 403. Changed that branch to 422 in `f7e41b7`; the focused contract test then passed.
- **QA rework final (f7e41b7)**: `poetry run pytest hedge_fund -q`, 2026-11-18 01:09:56–02:29:22 +01:00 → **25 failed, 3047 passed, 62 skipped** in 4757.91s (1:19:17), exit 1. Final source diff SHA-256 and environment are recorded above.
- **Cycle-1 verdict (f7e41b7)**: full pytest execution is **FAIL** because baseline tests still fail. Regression verdict is **PASS**: all 25 final failures are in the documented baseline set; no new failure remains. `runtime/test_inventory_cache_race.py` did not fail in this final run. The baseline set spans `test_run.py`, `data/test_yfinance_client.py`, `paper/test_deployed_broker.py`, `paper/test_saxo_e2e.py`, `runtime/test_inventory_cache_race.py`, `runtime/test_process_identity.py`, `runtime/test_writer_inventory.py`, `runtime/test_writer_races.py`, and `web/test_actions.py`.
- **Cycle-2 full suite (f9808cf)**: `poetry run pytest hedge_fund -q --tb=line`, 2026-11-18 03:06:38–04:23:32 +01:00 → **24 failed, 3052 passed, 62 skipped** in 4602.20s (1:16:42), exit 1. All 24 failed test IDs are in the documented baseline list below; all five I-2/I-3 regression tests passed in this run.
- **Cycle-2 verdict**: pytest execution is **FAIL** due to baseline failures. Regression verdict is **PASS at test-ID level**: no new failing test ID. Failure-message-level comparison against baseline was not recorded (M-4); no message-level equivalence is claimed.

## Targeted evidence per acceptance scenario (T021, test-level — no live-surface walk; a live walk requires the D7 cost-model input and explicit operator authorization and is deferred)

| Scenario | Evidence | Result |
|---|---|---|
| V1 acceptance consistency (FR-001/002) | `hedge_fund/runtime/test_capture.py`, `web/test_settings.py` — kimi-k3:cloud accepted across CLI/env/persisted/web | PASS (targeted suites green) |
| V2 no silent substitution (FR-003) | `hedge_fund/tui/test_home.py` — invalid preset yields explicit notice, no substitution | PASS |
| V3 capability filtering (FR-006) | `test_capture.py` — embedding/OCR tags rejected with capability reason | PASS |
| V4 paid/cloud governance (FR-007) | `runtime/test_policy.py`, `runtime/test_dispatch.py` — scheduled refusal regardless of credentials; unauthorized one-shot refusal; "no verified cost model" refusal (D7 mechanism) | PASS |
| V5 picker presentation (FR-004) | `web/test_settings.py` — classifier fields in models/catalog payloads; rejection contract C2 | PASS |
| V6 precedence + persistence (FR-005) | `test_capture.py` — launch > env > persisted > default; restart persistence | PASS |
| V7 safe failure, no secrets (FR-008/010) | `test_dispatch.py` loopback guardrails unchanged; rejection messages contain no credential material | PASS |
| V8 non-Ollama unchanged (FR-011) | full-suite diff vs baseline shows no new failures outside pre-existing set | PASS |

## QA rework targeted evidence (cycle 1)

Results recorded 2026-11-18 02:32:55 +01:00. Implementation code in the Python target runs was later committed as `cf37eec` (commit diff SHA-256 `e895d2d42382fcb458ea22048e7a20210cd273750dcab0c4e08d602dd262657a`). Broad targets preceded a final test-only import-formatting edit; the added dynamic request-URL assertion passed after formatting. Web status/route retests and the final full suite ran on `f7e41b7`; frontend files were unchanged by this rework.

| Finding | Exact command | Result |
|---|---|---|
| 5a settings POST/PUT | `poetry run pytest hedge_fund/web/test_settings.py -k settings_routes_accept_and_persist_cloud_tag_across_restart -q` | **PASS** — 1 passed, 22 deselected; actual POST and PUT accept `kimi-k3:cloud`. |
| 5b restart persistence | Same command as 5a | **PASS** — same test verifies persisted file and restarted app returns `kimi-k3:cloud`, version 2. |
| 5c scheduled refusal | `poetry run pytest hedge_fund/runtime/test_dispatch.py -k scheduled_cloud_refusal_branch_reports_model_specific_reason -q` | **PASS** — 2 passed, 42 deselected; both verified-cost states return paid/cloud refusal. |
| 5d CLI run refusal | `poetry run pytest hedge_fund/test_run.py -k "cli_model_flag_accepts_catalog_ollama_cloud_tag or cli_backtest_paid_cloud_reports_transport_refusal" -q` | **PASS** — 2 passed, 109 deselected; actual CLI run reports the C2 reason. |
| 5d web run refusal | `poetry run pytest hedge_fund/web/test_jobs.py -k web_backtest_preview_reports_paid_cloud_refusal_at_route -q` | **PASS** — 1 passed, 51 deselected; actual preview route returns the C2 reason. |
| 5d web status contract | `poetry run pytest hedge_fund/web/test_app.py -k every_tagged_service_error_site_uses_a_contract_status -q` | **PASS** — 1 passed, 53 deselected on `f7e41b7`; readiness error status now matches its contract code. |
| Catalog-derived transport allowlist | `poetry run pytest hedge_fund/runtime/test_capture.py -k local_catalog_addition_updates_configuration_web_and_transport -q` | **PASS** — 1 passed, 28 deselected; one synthetic local catalog row enables config, web picker, provider validation, and loopback request URL. |
| Runtime/LLM regression suite | `poetry run pytest hedge_fund/runtime/test_policy.py hedge_fund/runtime/test_dispatch.py hedge_fund/runtime/test_capture.py hedge_fund/llm/test_client.py -q` | **PASS** — 247 passed in 30.58s. |
| Web jobs/settings suites | `poetry run pytest hedge_fund/web/test_jobs.py hedge_fund/web/test_settings.py -q` | **PASS** — 74 passed, 1 skipped in 457.64s. |
| TUI suites | `poetry run pytest hedge_fund/tui/test_home.py hedge_fund/tui/test_paper.py -q` | **PASS** — 40 passed in 36.84s. |
| Writer-map | `poetry run pytest hedge_fund/runtime/test_writer_map.py -q` | **PASS** — 119 passed in 5.12s. |
| 6 frontend tests | `(cwd=frontend) npm test` | **PASS** — Vitest 4.1.12; 15 files and 241 tests passed; started 2026-11-17 23:35:26 +01:00, duration 106.53s. |
| 6 frontend types | `(cwd=frontend) npx tsc --noEmit` | **PASS** — exit 0, no emitted files. |
| 6 frontend lint | `(cwd=frontend) npm run` | **N/A** — configured scripts contain no lint script; toolchain available. |

V4.5 (authorized one-shot dispatch with a real verified cost model) remains **blocked on D7**: operator pricing/budget input not yet supplied; mechanism refuses with the explicit reason until then.

## QA rework targeted evidence (cycle 2: I-2, I-3)

Focused I-2/I-3 checks ran before source commit; the same source/test diff was committed unchanged as `7d10fc7` and `f9808cf`. The combined target command then reran every changed area on final code commit `f9808cf`.
`hedge_fund/test_run.py` is in the documented baseline set, so the full-suite rerun was required. Frontend files were unchanged; cycle-1 Vitest and TypeScript evidence remains unaffected. No live network/Ollama calls were made. Command output is retained in this session transcript; no separate log artifact was written.

| Finding | Exact command | Result |
|---|---|---|
| I-2 catalog parser rejects `:cloud` with `local` cost class | `poetry run pytest hedge_fund/llm/test_client.py -k ollama_cloud_suffix_must_be_paid_cloud_in_catalog -q` | **PASS** — 1 passed, 151 deselected in 0.23s. |
| I-2 invalid catalog cannot select or dispatch the tag | `poetry run pytest hedge_fund/runtime/test_capture.py -k mislabelled_cloud_catalog_fails_closed_across_selection_and_dispatch -q` | **PASS** — 1 passed, 29 deselected in 0.78s. |
| I-3 validator reports cost-model blocker with authorization supplied | `poetry run pytest hedge_fund/runtime/test_policy.py -k transport_check_with_paid_authorization_reports_missing_cost_model -q` | **PASS** — 1 passed, 22 deselected in 0.13s. |
| I-3 real CLI path reports cost-model blocker | `poetry run pytest hedge_fund/test_run.py -k cli_backtest_paid_cloud_authorization_reports_missing_cost_model -q` | **PASS** — 1 passed, 111 deselected in 1.55s. |
| I-3 real web preview path reports cost-model blocker | `poetry run pytest hedge_fund/web/test_jobs.py -k web_backtest_preview_with_paid_authorization_reports_missing_cost_model -q` | **PASS** — 1 passed, 52 deselected in 8.82s. |
| Final targeted suites on `f9808cf` | `poetry run pytest hedge_fund/runtime/test_policy.py hedge_fund/runtime/test_dispatch.py hedge_fund/runtime/test_capture.py hedge_fund/llm/test_client.py hedge_fund/test_run.py hedge_fund/web/test_settings.py hedge_fund/web/test_jobs.py -q --tb=line` | **FAIL (baseline-only)** — 10 failed, 426 passed, 1 skipped in 844.73s (14:04); all 10 failures are the documented Saxo CLI cases in `test_run.py`. All five I-2/I-3 regressions passed. Started 2026-11-18 02:52:00 +01:00; ended 03:06:12 +01:00. |
| Final full suite on `f9808cf` | `poetry run pytest hedge_fund -q --tb=line` | **FAIL (baseline-only)** — 24 failed, 3052 passed, 62 skipped in 4602.20s (1:16:42); start/end and test-ID limitation recorded above. |

## Environment note

Earlier T020 setup restored the session venv's missing `rich` dependency via `poetry install`; the final rework run used the environment recorded above.

## Known baseline failures (25 observed in cycle-1 final run; pre-existing, NOT caused by this feature)

The heading count is the cycle-1 observed total; the list includes baseline cases that did not recur. The cycle-2 full suite observed 24 failures, all with IDs listed below.

- `hedge_fund/test_run.py::test_saxo_demo_execution_refuses_before_ledger_or_execution[argv0..3]`
- `hedge_fund/test_run.py::test_saxo_guard_preserves_nonexecuting_verdicts_and_oauth_paper_approvals` (6 parameterizations)
- `hedge_fund/data/test_yfinance_client.py::test_news_*` (3)
- `hedge_fund/paper/test_deployed_broker.py::test_saxo_reconciliation_uses_accounting_cash_and_refuses_mismatch`
- `hedge_fund/paper/test_saxo_e2e.py` (2)
- `hedge_fund/runtime/test_inventory_cache_race.py::test_approval_waiting_for_sibling_publication_does_not_block_halt`
- `hedge_fund/runtime/test_process_identity.py::test_linux_process_identity_parses_pid1_stat_with_parenthesized_command`
- `hedge_fund/runtime/test_writer_inventory.py::test_every_production_writer_is_classified_by_admission_class`
- `hedge_fund/runtime/test_writer_races.py::test_two_process_audit_appends_are_complete_and_uninterleaved`
- `hedge_fund/web/test_actions.py::test_nonlocal_broker_mutations_stop_before_ledger_adapter` (4), `test_saxo_web_routes_deny_before_provider_or_writer_effects`, `test_saxo_accept_routes_reject_previews_before_worker_or_ledger_effects`
