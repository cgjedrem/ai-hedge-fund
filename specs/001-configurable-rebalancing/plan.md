# Implementation Plan: Configurable Rebalancing Cadence

**Branch**: `cgjedrem-redesigned-invention` | **Date**: 2026-10-29 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/001-configurable-rebalancing/spec.md`

## Summary

Rebalance cadence is already a validated, scheduler-honored, TUI-selectable mandate field (`minute`/`daily`/`weekly`/`monthly`, default `weekly`). Discovery verified the core end-to-end; the delta is threefold: (1) a command-line override (`--rebalance`) on `backtest` and `paper create`, applied after mandate load and before any engine work or deploy freeze, with correct minute↔day-grid field handling; (2) the example mandate's cadence comment listing all four values; (3) top-level documentation of the mandate fields and the override. Backward compatibility is preserved by construction: no serialization changes, default stays `weekly`, existing default-path tests keep passing and new ones pin the CLI default path.

## Technical Context

**Language/Version**: Python 3.11 (Poetry)

**Primary Dependencies**: pydantic v2 (FundSpec model), argparse (CLI), Textual 8.x (TUI), PyYAML

**Storage**: filesystem — mandate YAML under the user's hedge-fund home; paper funds snapshot `fund.yaml`; hash-chained JSON ledgers (untouched by this feature)

**Testing**: pytest, co-located under `hedge_fund/` (`python -m poetry run pytest hedge_fund -q`); offline fixtures only (no network, no provider credits)

**Target Platform**: Windows host (dev/CI), cross-platform Python CLI/TUI

**Project Type**: CLI + TUI application (single package `hedge_fund/`)

**Performance Goals**: N/A — configuration-path feature; no hot loops touched

**Constraints**: never touch `~/.hedge-fund` live state in tests/dev; never change `SessionRecord`/mandate serialization (ledger hash chain); black line-length 420; no UTF-8 BOM in YAML/spec files; six documented Windows baseline test failures are pre-existing

**Scale/Scope**: ~4 source files touched (run.py, example.yaml, README.md, hedge_fund/README.md), ~2 test files extended (test_run.py, possibly test_spec.py), 1 new spec helper for the override transform

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Ledger integrity first (MUST) | PASS | No FundSpec field/serializer changes; override constructs an in-memory spec via the existing model; minute→day-grid override drops `interval`/`window` so the resulting spec serializes canonically. Deployed funds remain frozen — no override on tick/run/status. |
| II. Paper only (MUST) | PASS | No data-provider changes; tests use offline fixtures per existing `conftest.py` guard. |
| III. Tests co-located and green (MUST) | PASS | New tests co-located in `hedge_fund/`; suite run in directory chunks on Windows; only the six documented baseline failures tolerated. |
| IV. Determinism (SHOULD) | PASS | Override is a pure spec transform; tests inject clocks/series per existing conventions. |
| V. User-visible surfaces stay consistent (SHOULD) | PASS | This feature closes the last inconsistency: cadence settable in mandate, validated in spec, honored by scheduler, picked in TUI, overridable via CLI, documented. |
| VI. Style (MUST) | PASS | black line-length 420 (no reformatting of existing code), isort black profile, flake8; all file writes BOM-free. |

**Post-design re-check**: PASS — design adds no state, no serialization surface, no new persistence; the override is a validated in-memory transform before existing freeze points.

## Project Structure

### Documentation (this feature)

```text
specs/001-configurable-rebalancing/
├── plan.md              # This file
├── research.md          # Phase 0 output — decisions & rationale
├── data-model.md        # Phase 1 output — entities & validation rules
├── quickstart.md        # Phase 1 output — validation scenarios
├── contracts/
│   └── cli.md           # Phase 1 output — CLI surface contract
├── checklists/
│   └── requirements.md  # Spec quality checklist
└── tasks.md             # Phase 2 output (/speckit-tasks)
```

### Source Code (repository root)

```text
hedge_fund/
├── fund/
│   ├── spec.py            # FundSpec — NO changes (validation already complete)
│   ├── example.yaml       # cadence comment: list all four values (FR-013)
│   └── test_spec.py       # existing default/validation tests (keep green)
├── run.py                 # _parser(): --rebalance on backtest + paper create;
│                          # override applied post-load_spec, pre-deploy/backtest
├── test_run.py            # new CLI override tests (offline fixtures)
├── tui/
│   └── builder.py         # NO changes (picker already complete; pinned by tests)
├── pipeline/
│   └── session.py         # NO changes (is_rebalance_session already complete)
└── README.md              # mandate-field reference + CLI override (FR-014)
README.md                  # top-level: mandate fields incl. cadence + override
```

**Structure Decision**: Single-package layout unchanged. The override helper lives in `run.py` (it is a CLI concern: translating a flag into a valid spec) unless implementation shows it belongs beside `load_spec` in `fund/spec.py` for reuse — implementer's judgment within that constraint, documented in the file manifest.

## Complexity Tracking

No constitution violations — table intentionally empty.