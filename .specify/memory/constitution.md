# ai-hedge-fund Constitution

## Preamble

This repo is a personal paper-trading hedge-fund engine (Python 3.11 + Poetry, Textual TUI,
hash-chained paper ledgers). The constitution binds every feature, bugfix, and refactor.
Non-negotiable principles are marked MUST; everything else is SHOULD with judgment allowed.

## Principles

### I. Ledger integrity first (MUST)

Session records, checkpoints, and broker books are hash-chained. New code MUST keep old
records replayable byte-identically: never change serialization of existing fields without a
documented migration, never rewrite history except through the explicit redo path
(`paper tick --again`), and never break the never-overshoot-cash invariant in sizing.

### II. Paper only, no unattended live risk (MUST)

The engine trades paper. No feature may place real orders, call paid data providers by
default, or run unattended live data loops. Data providers are pluggable; the free yfinance
path must keep working with zero credentials. Financial-datasets credits are reserved and
MUST NOT be spent by tests or dev loops.

### III. Tests co-located and green (MUST)

Tests live next to code under `hedge_fund/` and run with `poetry run pytest hedge_fund -q`.
A change is done when the suite passes. Six pre-existing Windows-only failures (features
intraday `%-d` strftime, 2x paper redo `os.rename`, paper sigterm `os.kill`, tui home
file-mode, tui paper_view `%-d`) are documented baseline — do not fix them in feature work,
and do not treat them as license for new failures.

### IV. Determinism and reproducibility (SHOULD)

Prefer recorded clocks, seeded randomness, and cacheable LLM calls so any session can be
replayed. Side effects (fills, costs, NAV) must be derivable from the ledger alone.

### V. User-visible surfaces stay consistent (SHOULD)

CLI (`run.py`), TUI (`tui/`), and mandate YAML must agree on fund configuration. A setting
is only "configurable" when it is settable in the mandate, validated in the spec, honored by
the scheduler, and visible/editable in the TUI builder.

### VI. Style (MUST)

black with line-length 420 (deliberate — do not reformat), isort (black profile), flake8.
Never write UTF-8 BOM into YAML or spec files.

## Governance

Amendments require a spec under `specs/` and a passing full suite. All PRs target `main`.