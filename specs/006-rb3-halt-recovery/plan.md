# Implementation Plan: RB-3 Safe Halt → Reconciliation → Resume Completion

**Branch**: `cgjedrem-musical-eureka` | **Date**: 2026-11-12 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/006-rb3-halt-recovery/spec.md`

## Summary

Complete RB-3 for the single-user local paper desk by closing four verified gaps in the existing Halt → reconciliation → Resume machinery (baseline `b6aefe5`, PR8 partial). Approach: extend the existing ledger/runtime reconciliation primitives — no new subsystem, no migration, no enterprise redesign.

1. **Intent visibility (FR-001/002/003)**: outstanding execution effect intents become reconciliation-required conditions, enumerated in the preview and enforced in work readiness regardless of incoming request ID.
2. **Halt-interrupted execution record (FR-004)**: an execution interrupted by Halt after ≥1 transmitted effect journals a reconciliation-required record bound to the transmitted effects; zero-effect interruptions stay clean.
3. **Resume gating completeness (FR-005)**: Resume permission and work readiness consider outstanding execution intents and unresolved Resume intents in addition to Halt/failure state.
4. **Receipt expiry (FR-006, spec005 T140)**: recovery receipts carry a recorded-clock validity bound; verification rejects expired receipts in addition to the existing state-digest rebinding.

Existing invariants preserved (FR-007/008/009/010): Resume intent-before-clear, no duplicate fills on retry, unchanged daily/weekly session keys, Halt stops admission only. TUI/CLI surfaces unchanged per clarified FR-011.

## Technical Context

**Language/Version**: Python 3.11 (Poetry)

**Primary Dependencies**: existing `hedge_fund` internals only — `paper/ledger.py`, `paper/tick.py`, `runtime/reconciliation.py`, `web/services.py`; no new packages

**Storage**: hash-chained JSONL paper ledger + reconciliation journal files under the fund root (existing formats; new fields additive only)

**Testing**: `poetry run pytest` on co-located test files (constitution Principle III); targeted files then broader suite per evidence contract

**Target Platform**: Windows + Linux local dev; synthetic writable test roots only (no production roots, no broker calls, no paid data)

**Project Type**: library/CLI/web-service (single-user local desk)

**Performance Goals**: N/A — correctness/safety feature; recovery preview is an on-demand read over already-loaded replay state

**Constraints**: ledger replay of pre-feature records MUST stay byte-identical (constitution Principle I); any new raw write MUST gain a `WRITER_MAP` entry citing test nodes (`hedge_fund/runtime/test_writer_map.py`); receipt format changes MUST be additive/backward-readable

**Scale/Scope**: 4 production files + 4 test files, est. <400 LOC total

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Evidence |
|-----------|--------|----------|
| I. Ledger integrity (MUST) | PASS | New event/intent fields are additive; replay of existing records unchanged; no serialization change to existing fields; redo path untouched |
| II. Paper only (MUST) | PASS | Synthetic fixtures only; no broker/paid-data/cloud calls; no new unattended loops |
| III. Tests co-located and green (MUST) | PASS | Tests added beside code in `hedge_fund/`; targeted runs per slice, full-suite evidence deferred to final acceptance per existing test-cost constraint (~40 min, isolated run) |
| IV. Determinism (SHOULD) | PASS | Receipt expiry uses the recorded clock, not wall time |
| V. Surface consistency (SHOULD) | PASS with documented exception | Web desk is the reviewed-recovery surface; TUI/CLI deferral is an explicit, documented headless exception (spec FR-011, user decision A) |
| VI. Style (MUST) | PASS | black 420 / isort / flake8; no BOM |

*Post-design re-check (Phase 1 complete)*: unchanged — design adds no new write paths beyond journaled ledger events and extends existing receipt verification; WRITER_MAP entries will cite the new test nodes if new raw writes appear. No violations; Complexity Tracking empty.

## Project Structure

### Documentation (this feature)

```text
specs/006-rb3-halt-recovery/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
│   └── recovery-semantics.md
├── checklists/
│   └── requirements.md  # from /speckit-specify (all pass)
└── tasks.md             # Phase 2 output (/speckit-tasks)
```

### Source Code (repository root)

```text
hedge_fund/
├── paper/
│   ├── ledger.py            # readiness choke point, intent guards, resume gating
│   ├── tick.py              # halt-interruption failure record
│   ├── test_ledger.py       # readiness/intent/resume regression tests
│   └── test_tick.py         # halt-mid-execution + retry duplication tests
├── runtime/
│   ├── reconciliation.py    # preview intent enumeration, receipt expiry
│   ├── test_reconciliation.py  # preview/receipt/expiry tests
│   └── test_writer_map.py   # WRITER_MAP entries if new raw writes appear
└── web/
    ├── services.py          # preview + resume_allowed include unresolved intents
    └── test_recovery.py     # web preview/resume decision tests
```

**Structure Decision**: Single-package layout per repo convention; tests co-located. No new modules beyond (at most) small helpers inside the files above.

## Design Details

### 1. Intent visibility and readiness (FR-001/002/003)

- `Ledger.require_ready_for_work()` (`hedge_fund/paper/ledger.py:307-317`) becomes the single choke point: deny when the journal holds (a) an outstanding execution intent with no outcome, or (b) an unresolved Resume intent — independent of the supplied request ID. The per-request intent guard (`ledger.py:784-841`) stays as the same-ID layer beneath it.
- `runtime/reconciliation.py` preview (`:185-225`) enumerates outstanding intents alongside `tick_failed` events, with operation identity, head, book digest and fill digest evidence per entry, so the web preview (`web/services.py:775-793`) renders them without frontend changes beyond tolerant display.
- `web/services.py` `resume_allowed` (`:783-793`) includes unresolved intents in its decision.

### 2. Halt-interrupted execution record (FR-004)

- In `paper/tick.py` around the halt re-raise boundary (`:804-819`): when execution is interrupted by Halt **after ≥1 transmitted effect**, journal a reconciliation-required failure record bound to the transmitted fill identities before propagating. When interrupted with zero transmitted effects, no record (clean interruption; Resume after replay per existing simple-halt path).
- Regression anchor: existing after-first-fill test (`paper/test_tick.py:1476-1505`) extended to assert the new record appears and drives preview/Resume review.

### 3. Receipt expiry (FR-006 / T140)

- Receipt fields (`runtime/reconciliation.py:104-136`) gain `issued_at` (recorded clock) and `valid_until`; verification (`:310-330`) rejects expired receipts in addition to the existing rebind against current failure/head/book/fill digest. State change already invalidates via digest rebinding; expiry closes the time window.
- Additive-only and fail-closed: receipts without the new fields are treated as expired, never as valid.

## Complexity Tracking

No constitution violations; table intentionally empty.
