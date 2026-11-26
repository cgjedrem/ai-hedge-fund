# Implementation Plan: Discovery Snapshot Contract

**Branch**: `cgjedrem-evaluate-alphasift-integration` (app-managed worktree; Spec Kit numbering `010`) | **Date**: 2026-11-25 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/010-discovery-snapshot-contract/spec.md`

## Summary

Deliver an offline, headless Python validator for discovery snapshot version 1. A small `hedge_fund.discovery` package will use existing Pydantic v2 models for strict structural validation, explicit adapters for stable issues and timestamp semantics, and shared ticker normalization behavior. Validation returns either a complete canonical JSON-compatible snapshot or deterministic field-level issues, never a partial snapshot. Synthetic in-memory fixtures prove valid acceptance, all-or-nothing rejection, canonicalization, and explicit-reference freshness. There is no provider, persistence, ranking, API, UI, or migration work.

## Technical Context

**Language/Version**: Python 3.11, managed by Poetry
**Primary Dependencies**: Existing Pydantic v2 (locked at 2.13.4; declared `^2.4.2`); Python standard library; existing pytest tooling
**Storage**: N/A — in-memory dictionaries and synthetic fixtures only
**Testing**: Co-located pytest modules; global test setup already blocks external network and clears provider credentials
**Target Platform**: Windows and Linux Python environments; importable offline library
**Project Type**: Internal library contract for the later offline ranking feature 011
**Performance Goals**: N/A for the MVP; correctness, complete issue reporting, and deterministic replay take precedence
**Constraints**: No new dependencies; no network, wall-clock reads, providers, LLMs, persistence, ledger/trading changes, or byte-level JSON guarantees; strict types with finite numeric values; explicit freshness inputs; canonical UTC timestamps without fractional precision loss
**Scale/Scope**: One versioned snapshot shape, one public validation entry point, one small fixture matrix, and focused regression tests; empty snapshots supported; only schema version 1 supported

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Verdict | Notes |
|---|---|---|
| I. Ledger integrity | PASS | No execution ledger, migration, replay accounting, or fund workflow is changed |
| II. Paper only, no unattended live risk | PASS | Pure offline computation; no provider, broker, credential, or paid-model use; existing test network guard remains active |
| III. Tests co-located and green | PASS | New tests live under `hedge_fund/discovery/`; shared ticker behavior is checked in `hedge_fund/fund/test_spec.py`; full `poetry run pytest hedge_fund -q` is required for implementation acceptance |
| IV. Determinism | PASS | No wall clock, sampling, randomness, or network; freshness takes explicit reference data; issues have documented ordering; fixtures replay fixed expected values |
| V. Surfaces stay consistent | PASS | Headless exception is explicit; there is no web/API/UI configuration or presentation surface |
| VI. Style | PASS | Use black line length 420, isort black profile, flake8, and UTF-8 without BOM for new specification artifacts |

*Post-Phase-1 re-check: the detailed design adds no service, integration, storage, or execution path. All gates remain PASS; no complexity exception is required.*

## Project Structure

### Documentation (this feature)

```text
specs/010-discovery-snapshot-contract/
├── spec.md
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   └── discovery-snapshot-v1.md
└── checklists/
    └── requirements.md
```

`tasks.md` is deliberately left for `/speckit-tasks`; implementation is outside this planning command.

### Source Code (repository root)

```text
hedge_fund/
├── discovery/
│   ├── __init__.py          # Public validator and result/issue types
│   ├── models.py            # Strict Pydantic input models; immutable result records
│   ├── snapshot.py          # Issue adaptation, timestamps, canonicalization, freshness
│   ├── fixtures.py          # Synthetic inputs and exact expected outcomes
│   └── test_snapshot.py     # Contract, rejection, freshness, and replay scenarios
└── fund/
    ├── spec.py              # Extract shared single-ticker normalization helper
    ├── __init__.py          # Export that helper without changing existing exports
    └── test_spec.py         # Regression coverage for existing universe behavior
```

**Structure Decision**: Use the existing single Python package and co-located tests. A separate `discovery` namespace avoids confusion with `features.snapshot.FundamentalsSnapshot`. Extracting the existing `strip().upper()` step into a shared helper preserves `normalize_universe` behavior while preventing ticker canonicalization drift. No new project, service, fixture storage format, or generated schema is introduced.

## Complexity Tracking

No constitution violations require justification.
