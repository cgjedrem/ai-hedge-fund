# Quickstart: Validating Configurable Rebalancing Cadence

**Feature**: specs/001-configurable-rebalancing | **Date**: 2026-10-29

All validation is test-driven — no step below touches `~/.hedge-fund`, the network, or any provider credits.

## Prerequisites

- Python 3.11 + Poetry installed; repo checked out on `cgjedrem-redesigned-invention`.
- Windows host: run the suite in directory chunks (long single runs get killed externally).

## Run the affected tests

```powershell
# targeted first (fast feedback)
python -m poetry run pytest hedge_fund/test_run.py -q
python -m poetry run pytest hedge_fund/fund -q
python -m poetry run pytest hedge_fund/pipeline -q
python -m poetry run pytest hedge_fund/tui -q
python -m poetry run pytest hedge_fund/backtesting -q
python -m poetry run pytest hedge_fund/paper -q
```

Expected: all pass except the six documented Windows baseline failures (features intraday `%-d` strftime, 2× paper redo `os.rename`, paper sigterm `os.kill`, tui home file-mode, tui paper_view `%-d`).

## What proves the feature (map to spec)

| Spec item | Proof |
|-----------|-------|
| US1 — cadence set in mandate, validated, honored | existing + kept-green: `hedge_fund/fund/test_spec.py` (defaults, validation), `hedge_fund/pipeline/test_session.py` (period rule, holiday/ISO-boundary), `hedge_fund/backtesting/test_fund.py` (grid parity) |
| US2 — backward compat | `fund/test_spec.py` default test stays green; new CLI default-path test: mandate without `rebalance`, no flag ⇒ weekly |
| US3 — CLI override | new tests in `hedge_fund/test_run.py`: backtest override changes result cadence; `paper create` override lands in deployed `fund.yaml`; invalid value ⇒ usage error; minute→daily drops minute-only settings; daily→minute yields valid defaults; no override on tick/run |
| US4 — TUI picker | existing `hedge_fund/tui/test_builder.py` stays green (picker pinned) |
| US5 — docs | manual read-through of `README.md` mandate section + `hedge_fund/fund/example.yaml` comment listing all four values |

## Manual smoke (optional, isolated)

Using the repo's example mandate copied to a temp dir (never `~/.hedge-fund`):

```powershell
Copy-Item hedge_fund/fund/example.yaml $env:TEMP\smoke-mandate.yaml
python -m poetry run aihf backtest $env:TEMP\smoke-mandate.yaml --universe <offline-fixture-universe> --rebalance monthly
```

Expected: status line reports the monthly cadence; result JSON reflects monthly decision cycles. Invalid value check:

```powershell
python -m poetry run aihf backtest $env:TEMP\smoke-mandate.yaml --universe <offline-fixture-universe> --rebalance hourly
```

Expected: usage error naming `hourly` and the allowed choices; no engine output.

(Clean up `$env:TEMP\smoke-mandate.yaml` afterwards.)