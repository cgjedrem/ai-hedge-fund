# Implementation Evidence: Ollama Model Selection

**Date**: 2026-11-17 | **Spec**: [spec.md](spec.md) | **Branch**: `cgjedrem-cuddly-winner`

## Build / static verification

- Implementation commits: `0b1f8d2` (baseline record), `cb311d2` (catalog validation), `473521e` (error surfacing), `b238e04` (web settings policy), `a46491c` (paid-cloud dispatch gating), `3b39982` (black/isort).
- black (line-length 420), isort (black profile), flake8 run on changed files; writer-map AST scan passing (T018, T019).

## Full suite (T020)

- **Feature branch (3b39982)**: `poetry run pytest hedge_fund -q` → **26 failed, 3030 passed, 62 skipped** in 5408s (1h30m), 2026-11-17, Windows, Python 3.13.7 (poetry venv `aihf-FuzY57Jh-py3.13`).
- **Baseline (e6f04d2)**: the same 26 tests rerun in a detached clean worktree (`%TEMP%\aihf-spec009-baseline-e6f04d2`) → **26 failed, 192 passed** — byte-identical failure set.
- **Verdict**: zero new failures attributable to this feature. The 26 failures are pre-existing baseline defects in Saxo broker paths (`test_run.py` saxo guards, `paper/test_saxo_e2e.py`, `web/test_actions.py`), yfinance news fallback (`data/test_yfinance_client.py` — the sibling session's in-flight area), and runtime writer/process tests (`test_writer_races.py`, `test_writer_inventory.py`, `test_process_identity.py`, `test_inventory_cache_race.py`). Per Principle III these are individually evidenced baseline failures, not regressions; repairing them is out of scope for this feature.

## Targeted evidence per acceptance scenario (T021, test-level)

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

V4.5 (authorized one-shot dispatch with a real verified cost model) remains **blocked on D7**: operator pricing/budget input not yet supplied; mechanism refuses with the explicit reason until then.

## Environment note

The session worktree's poetry venv was missing `rich` at the start of T020 (dependency drift in the fresh worktree); restored via `poetry install`. The specialist's earlier T001 "clean baseline" record was made in its own detached worktree before this venv was repaired; the rerun above is the authoritative evidence.

## Known baseline failures (26, pre-existing, NOT caused by this feature)

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
