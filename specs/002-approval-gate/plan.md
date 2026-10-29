# Implementation Plan: Per-Fund Approval Gate (Yay/Nay Mode)

**Branch**: `cgjedrem-super-telegram` | **Date**: 2026-10-29 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/002-approval-gate/spec.md`

## Summary

Add a per-fund approval gate: when `approval_required` is set on a fund (mandate YAML, TUI builder step, or `aihf paper create --approval`), the paper layer stops auto-executing the pending decision at the next close. The owner yay/nays it via `aihf paper approve|reject <name>` (CLI) or the `y`/`n` actions on the TUI fund screen; the verdict is a small mailbox file (`pending-approval.json`) in the fund dir — visible to both the runner and TUI containers over the shared volume — keyed to the decision it refers to. An unapproved decision is skipped at the next session (audit event, book marked, session recorded, fund NOT halted) and the next decision cycle proceeds normally. The gate lives entirely in the paper layer (`paper/tick.py::_run`, the single choke point shared by `tick`, `redo`, and both runner loops); the engine (`pipeline/session.py`) is untouched. Default OFF keeps byte-identical serialization for existing funds (the new FundSpec field joins the pop-when-default serializer list) so every existing ledger still verifies.

## Technical Context

**Language/Version**: Python 3.11 (Poetry)

**Primary Dependencies**: pydantic v2 (FundSpec), argparse (CLI), Textual 8.x (TUI), PyYAML

**Storage**: filesystem — verdict mailbox `pending-approval.json` in the fund dir (atomic write via `paths.write_atomic`); hash-chained ledgers untouched; `events.jsonl` gains `approve`/`reject`/`expire` kinds (append-only, not hash-chained)

**Testing**: pytest, co-located under `hedge_fund/` (`python -m poetry run pytest hedge_fund -q`); fixtures only — no network, no `~/.hedge-fund` touches, no Docker

**Target Platform**: Windows host (dev), cross-platform Python CLI/TUI; runner + TUI containers share `~/.hedge-fund`

**Project Type**: CLI + TUI application (single package `hedge_fund/`)

**Performance Goals**: N/A — control-path feature; no hot loops touched

**Constraints**: never touch `~/.hedge-fund` live state or Docker in tests/dev; never change `SessionRecord` serialization or the chain; black line-length 420; no UTF-8 BOM in YAML/spec; six documented Windows baseline failures are pre-existing; TUI tests run per-file on Windows

**Scale/Scope**: ~8 source files touched (fund/spec.py, fund/example.yaml, paper/ledger.py, paper/tick.py, run.py, tui/paper.py, tui/paper_view.py, tui/builder.py, README.md), ~6 test files extended/added, 1 new verdict-mailbox module-level helper set in `paper/ledger.py`

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Ledger integrity first (MUST) | PASS | No `SessionRecord`/chain changes. New FundSpec field pops from serialization when default (byte-parity test mandatory). The verdict mailbox is keyed to `decision_as_of` so a stale verdict after `redo` is ignored, never honored. The pending decision is never duplicated — the ledger stays the single source of truth. |
| II. Paper only (MUST) | PASS | No data-provider changes; tests use offline fixtures per existing conftest guards. |
| III. Tests co-located and green (MUST) | PASS | New tests co-located; suite run in directory chunks on Windows; only the six documented baseline failures tolerated. |
| IV. Determinism (SHOULD) | PASS | Gate decisions derive from ledger state + verdict file only; tests inject clocks/series per existing conventions. |
| V. User-visible surfaces stay consistent (SHOULD) | PASS | Approval mode is settable in mandate, validated in spec, honored by the paper scheduler path, selectable in the TUI builder, operable via CLI and TUI, and documented. |
| VI. Style (MUST) | PASS | black line-length 420 (no reformatting of pre-existing flaky regions in run.py/test_run.py), isort black profile, flake8; all writes BOM-free. |

**Post-design re-check**: PASS — design adds one FundSpec field (popped at default), one mailbox file, three event kinds; no engine, chain, or scheduler changes.

## Project Structure

### Documentation (this feature)

```text
specs/002-approval-gate/
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
│   ├── spec.py            # FundSpec: approval_required field (default False) +
│   │                      #   _serialize pops it when False (hash parity)
│   ├── example.yaml       # document the key (commented; parsed content unchanged)
│   └── test_spec.py       # default/serialization/validation tests
├── paper/
│   ├── ledger.py          # APPROVAL_FILE, approval()/set_approval()/clear_approval()
│   │                      #   (mailbox semantics: corrupt/missing => None)
│   ├── tick.py            # gate in _run(): resolve verdict, skip-or-execute,
│   │                      #   consume verdict after successful append
│   ├── __init__.py        # re-export new public helpers if needed
│   ├── test_tick.py       # gate ON/OFF, approve/reject/expire/stale paths
│   └── test_ledger.py     # mailbox read/write/clear + corrupt-file fail-safe
├── run.py                 # approve/reject subcommands (+ --now), --approval on
│   │                      #   paper create, status/_status_line approval state
├── test_run.py            # CLI tests via the offline fixture
├── tui/
│   ├── paper.py           # y/n bindings, check_action gating, action_approve/reject
│   ├── paper_view.py      # snapshot approval/gate properties, next_run_rows copy
│   ├── builder.py         # approval step (paper mode), _finish_build wiring
│   ├── test_paper.py      # y/n gating + verdict writes (run per-file on Windows)
│   └── test_builder.py    # builder step produces the flag
└── README.md              # approval mode + approve/reject + expiry (FR-016)
README.md                  # top-level: approval mode in fund settings
```

**Structure Decision**: Single-package layout unchanged. The gate lives in `paper/tick.py::_run` (paper-layer policy; engine untouched — backtests unaffected). Mailbox helpers live in `paper/ledger.py` beside the kill-switch control-file code they mirror. CLI wiring follows the `halt`/`resume` pattern in `run.py`.

## Complexity Tracking

No constitution violations — table intentionally empty.