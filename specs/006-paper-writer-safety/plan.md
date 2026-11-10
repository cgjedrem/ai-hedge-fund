# Implementation Plan: Paper Writer Safety — Intent Fencing and Operation Deduplication

**Branch**: `cgjedrem-didactic-meme` | **Date**: 2026-11-10 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/006-paper-writer-safety/spec.md`

## Summary

Close two evidenced gaps in single-user paper-trading write safety: (P1) a global unresolved tick-intent fence that refuses any new-identity session request while a prior session intent has no recorded outcome, and (P2) durable logical-operation deduplication so the same (fund, action, session, payload) submitted under two independently generated request IDs executes at most once. Both mechanisms build on existing durable records (ledger events, operation index) and are validated only on owned synthetic fixtures. The protected identities `watchtower`/`watchtower-weekly` stay blocked; no real fund root is touched.

## Technical Context

**Language/Version**: Python 3.11 (Poetry-managed)

**Primary Dependencies**: existing `hedge_fund` runtime only — no new third-party packages

**Storage**: JSON ledger event streams + hash-chained session records (`hedge_fund/paper/ledger.py`); durable operation index + sidecars (`hedge_fund/runtime/operations.py`)

**Testing**: `poetry run pytest hedge_fund -q`, tests co-located; synthetic enrolled test roots via existing `hedge_fund/runtime/test_bootstrap.py` / handover test support

**Target Platform**: Windows (dev) + Linux; local single-user install

**Project Type**: single Python package with CLI, web service, headless runner

**Performance Goals**: fence check and dedup lookup are O(records of one fund); no new I/O beyond one extra pass over already-read records

**Constraints**:
- Ledger byte-compatibility (Constitution I): new event/record fields are additive-optional; old records stay replayable byte-identically.
- Writer map discipline: any new raw write (`write_text`/`write_bytes`/`rename`/`mkdir`/`os.open`…) MUST gain a `WRITER_MAP` entry in `hedge_fund/runtime/test_writer_map.py` citing covering tests.
- Admission ordering: every root-bound write happens inside the correct held lane; a new write inside `root_registry_writer` calls `coordinator.require_write_boundary()` first.
- No paid providers, no real roots, synthetic fixtures only (Constitution II, FR-009).
- black line-length 420 (deliberate), isort black profile, flake8 (Constitution VI).

**Scale/Scope**: 2 slices, ~4 production modules touched, focused synthetic tests

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Verdict | Basis |
|---|---|---|
| I. Ledger integrity (MUST) | PASS | Fence reads existing intent/outcome events; dedup adds an optional field to operation records. No serialization change to existing fields, no history rewrite, redo path untouched. |
| II. Paper only, no paid credits (MUST) | PASS | Tests use fake market data and synthetic roots; no provider calls. |
| III. Tests co-located and green (MUST) | PASS | New tests co-located; full suite or individually evidenced baseline required at completion. Known: full `pytest hedge_fund` is ~40 min and must run alone (memory). |
| IV. Determinism (SHOULD) | PASS | Logical key is a deterministic digest; fence outcome derives from durable events only. |
| V. Surfaces consistent (SHOULD) | PASS | Refusal reasons are shared constants consumed by CLI and web (contracts/refusal-contract.md). |
| VI. Style (MUST) | PASS | No reformatting; line-length 420 preserved. |

No violations; Complexity Tracking empty.

## Project Structure

### Documentation (this feature)

```text
specs/006-paper-writer-safety/
├── spec.md
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   └── refusal-contract.md
└── checklists/
    └── requirements.md
```

### Source Code (repository root)

```text
hedge_fund/
├── paper/
│   ├── ledger.py            # P1: unresolved-intent query + fence; event helpers
│   ├── tick.py              # P1: fence call at tick admission; redo interplay
│   └── test_ledger.py / test_tick.py   # co-located regression + crash-window tests
├── runtime/
│   ├── operations.py        # P2: logical-operation identity derivation, persistence, acceptance dedup
│   ├── test_operations.py   # P2: dedup acceptance tests
│   ├── test_writer_races.py # cross-entry-point duplicate-submission race tests
│   ├── owned_runner_child.py # P1: blocked-skip recorded via existing durable runner-state write path
│   └── test_writer_map.py   # WRITER_MAP entries for any new raw writes
├── web/
│   └── services.py          # surface shared refusal reasons (no new write paths)
└── run.py                   # CLI: surface refusal reasons, unchanged lane behavior
```

**Structure Decision**: existing single-package layout; no new modules beyond small helpers inside the listed files. Tests co-located per Constitution III.

## Phase 0 Summary (research.md)

Decisions: (1) fence derives from the ledger's own intent/outcome event stream — no new marker file; (2) logical-operation identity stored as a new optional field on the durable operation record, derived as a canonical digest; (3) fail closed on torn intent metadata; (4) dedup matches only non-terminal operations; terminal failure frees the key. See [research.md](research.md).

## Phase 1 Summary

- [data-model.md](data-model.md): session-intent lifecycle, logical-operation identity, state transitions.
- [contracts/refusal-contract.md](contracts/refusal-contract.md): shared refusal reason contract for CLI/web.
- [quickstart.md](quickstart.md): runnable validation scenarios on synthetic fixtures.

## Post-Design Constitution Re-Check

Re-evaluated after Phase 1: no new violations. The fence adds reads plus one refusal path (no new write kind); dedup adds an optional record field written through the existing operation-store code paths (already writer-mapped). Any genuinely new raw write discovered during implementation must be added to `WRITER_MAP` before merge.
