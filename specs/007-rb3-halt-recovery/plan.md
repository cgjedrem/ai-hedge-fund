# Implementation Plan: RB-3 Safe Halt → Reconciliation → Resume Completion

**Branch**: `cgjedrem-musical-eureka` | **Date**: 2026-11-12 (revised after rebase onto `448056f`) | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/007-rb3-halt-recovery/spec.md`

## Summary

Close the four RB-3 gaps that remain after PR #11 (paper writer safety, merged @ `448056f`), re-verified by code-level discovery on the new main:

1. **Recovery reachability (US1, FR-001/002)**: the desk suppresses the recovery surface when readiness denial marks the snapshot not-ok, and unmatched approval-consumption entries are unrecoverable. Fix: distinguish "valid but not ready — reconciliation required" from corrupt replay in the web service snapshot path, keep fetching/displaying recovery in that state, and extend the PR #11 intent-resolution machinery to unmatched approval-consumption entries.
2. **One Resume gate (US2, FR-003/004)**: converge general work readiness, web `resume_allowed`, and `Ledger.resume()` on one unresolved-state set (recorded failures + outstanding tick intents + unresolved Resume intents), without weakening PR #11's separate tick fence.
3. **Legacy no-ID post-fill Halt journaling (US3, FR-005)**: give the no-request-ID tick path the same post-effect `tick_failed` journaling PR #11 added for request-identified ticks.
4. **Receipt expiry (US4, FR-006/008, spec005 T140)**: add recorded-clock `issued_at`/`valid_until` to both receipt types; expired or field-less receipts deny fail-closed; existing state rebinding preserved.

All work extends PR #11 machinery; no new subsystems, no migrations, no TUI/CLI behavior change (FR-009, user decision A).

## Technical Context

**Language/Version**: Python 3.11 (Poetry); React/TypeScript frontend only if US1 requires a display tweak (prefer backend/service-level fix)

**Primary Dependencies**: existing `hedge_fund` internals — `paper/ledger.py`, `paper/tick.py`, `runtime/reconciliation.py`, `web/services.py`; possibly `frontend/src/pages/paper.tsx` display conditions

**Storage**: hash-chained JSONL paper ledger + reconciliation journals (additive fields only)

**Testing**: `poetry run pytest` co-located tests (constitution Principle III); targeted slices, then isolated full suite

**Target Platform**: Windows + Linux local dev; synthetic writable test roots only

**Project Type**: library/CLI/web-service (single-user local desk)

**Performance Goals**: N/A — safety semantics feature

**Constraints**: byte-identical replay of pre-feature records (Principle I); new raw writes need WRITER_MAP entries citing test nodes; receipt changes additive/fail-closed; PR #11 behaviors (safe aborts, dedup, tick fence, intent resolution) must not regress

**Scale/Scope**: ~5 production files + ~5 test files, est. <500 LOC

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Evidence |
|-----------|--------|----------|
| I. Ledger integrity (MUST) | PASS | Additive fields/events only; no serialization change to existing records; redo path untouched |
| II. Paper only (MUST) | PASS | Synthetic fixtures; no broker/paid/cloud; no new loops |
| III. Tests co-located and green (MUST) | PASS | Tests-first per story; isolated full suite as final evidence |
| IV. Determinism (SHOULD) | PASS | Receipt expiry on recorded clock |
| V. Surface consistency (SHOULD) | PASS with documented exception | Web desk is the reviewed-recovery surface; TUI/CLI deferral documented (FR-009) |
| VI. Style (MUST) | PASS | black 420 / isort / flake8; no BOM |

*Post-design re-check*: PASS — no new external writes beyond journaled ledger events; WRITER_MAP entries added if new raw writes appear. No violations; Complexity Tracking empty.

## Project Structure

### Documentation (this feature)

```text
specs/007-rb3-halt-recovery/
├── plan.md              # This file
├── research.md          # Phase 0 output (updated post-rebase)
├── data-model.md        # Phase 1 output (updated post-rebase)
├── quickstart.md        # Phase 1 output (updated post-rebase)
├── contracts/
│   └── recovery-semantics.md
├── checklists/
│   └── requirements.md
└── tasks.md             # Phase 2 output
```

### Source Code (repository root)

```text
hedge_fund/
├── paper/
│   ├── ledger.py            # unified unresolved-state set; readiness/resume gate convergence; approval-consumption resolution
│   ├── tick.py              # legacy no-ID post-fill halt failure journaling
│   ├── test_ledger.py       # gate-consistency and resolution tests
│   └── test_tick.py         # legacy-path halt tests; unmatched-consumption cases
├── runtime/
│   ├── reconciliation.py    # receipt expiry fields + verification
│   ├── test_reconciliation.py  # expiry tests
│   └── test_writer_map.py   # WRITER_MAP entries if new raw writes appear
├── web/
│   ├── services.py          # valid-but-not-ready vs corrupt distinction; recovery fetch on reconciliation-required; resume_allowed convergence
│   └── test_recovery.py     # web recovery visibility/permission tests
└── frontend/src/pages/
    ├── paper.tsx            # display recovery card in reconciliation-required state (only if service-level fix insufficient)
    └── paper.test.tsx       # display regression
```

**Structure Decision**: single-package repo convention; tests co-located.

## Design Details

### 1. Recovery reachability (US1)

- In `web/services.py` snapshot/report path (`:4082-4089` region): catch/translate readiness denial into a distinct `reconciliation_required` state instead of collapsing to `ledger.ok=false`; keep genuine replay corruption on the existing error path (PR #11 receipts-replay behavior preserved).
- Desk (`frontend/src/pages/paper.tsx:157-159,690-693`): fetch/display the recovery card when state is reconciliation-required even if not halted — extend the existing PR #11 condition only if the service state alone cannot drive it.
- Unmatched approval-consumption entries: extend the orphaned-intent resolution path (`paper/ledger.py:1025-1104`) to enumerate and resolve them with the same audited, digest-bound review; regression anchor `paper/test_tick.py:627-655`.

### 2. One Resume gate (US2)

- Introduce (or extend the T002-style helper into) a single fund-level unresolved-state query covering recorded failures, outstanding tick intents, unresolved Resume intents, and unmatched approval consumption; use it in `require_ready_for_work()` (`ledger.py:359-369`), web `resume_allowed` (`web/services.py:824-846`), and the `Ledger.resume()` pre-check (`ledger.py:1207-1216`).
- Preserve PR #11's separate new-identity tick fence (`require_ready_for_tick`) unchanged.
- Recovery paths (intent resolution, confirmed Resume) must not be blocked by the gate they serve: recovery operations use their own admission, as PR #11 already does for intent resolution.

### 3. Legacy no-ID post-fill Halt journaling (US3)

- In `paper/tick.py` legacy path (`:212-216`, `:474-500`): when a no-request-ID tick is interrupted by Halt after ≥1 transmitted effect and no outcome exists, journal `tick_failed` bound to transmitted fill identities, mirroring the request-identified outer handler (`:931-934`). Zero-effect interruptions keep clean-abort semantics.

### 4. Receipt expiry (US4 / T140)

- Add `issued_at`/`valid_until` (recorded clock) at issuance for both receipt types (`runtime/reconciliation.py:104-136`, `:268-307`); reject expired or field-less receipts at verification (`:678-699` and the intent-receipt verifier), keeping digest rebinding. Validity window: bounded, single-review-session scale; value recorded in evidence.

## Complexity Tracking

No constitution violations; table intentionally empty.
