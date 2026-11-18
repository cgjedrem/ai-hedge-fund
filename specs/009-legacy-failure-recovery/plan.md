# Implementation Plan: Legacy Failure Recovery

**Branch**: `009-legacy-failure-recovery` (authored on worktree branch `cgjedrem-effective-winner`) | **Date**: 2026-11-17 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/009-legacy-failure-recovery/spec.md`

## Summary

Restore schedulability of otherwise-consistent paper funds blocked by multiple historical (partly unkeyed) tick failures, via one operator-mediated, audited, append-only **reconciliation decision record** that binds the resolved failure-digest set + ledger head + broker-book digest + exact audit-history digest + operator + recorded time + exact attestable subset. Per-failure evidence is `verified`, `attestable`, or `not_resolvable`; ambiguous, corrupt, mismatched, stale, or contended cases refuse with zero writes. No historical bytes change; no fees/cash/positions are touched. Web surface only, reusing spec006/007 lanes and receipt-binding discipline.

## Technical Context

**Language/Version**: Python 3.11 (Poetry)
**Primary Dependencies**: existing `hedge_fund` runtime — `runtime/reconciliation.py`, `paper/ledger.py`, `paper/tick.py`, `web/services.py`, `web/app.py`; React desk `frontend/src/pages/paper.tsx`
**Storage**: hash-chained paper ledgers + JSONL audit events under enrolled data roots (unchanged)
**Testing**: `poetry run pytest hedge_fund -q`, tests co-located; synthetic enrolled roots; Playwright only if the desk panel changes (frontend unit tests preferred)
**Target Platform**: Windows dev, cross-platform suite
**Project Type**: single Python service + React desk
**Performance Goals**: N/A (operator-paced recovery flow)
**Constraints**: byte-identical historical replay (constitution I); no provider/LLM calls or paid credits in dev/tests (II); append-only audit through anchored boundary; existing admission/audit lanes only
**Scale/Scope**: single-operator; 2 production funds / 6 known events motivate, synthetic fixtures validate

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Verdict | Basis |
|---|---|---|
| I. Ledger integrity (MUST) | PASS | Append-only decision record; no re-serialization; replay compatibility is acceptance scenario P1-3 and quickstart Scenario A step 3 |
| II. Paper only, no unattended risk (MUST) | PASS | No provider/LLM calls; synthetic fixtures only; production reconciliation is separate attended operator approval (SC-005) |
| III. Tests co-located and green (MUST) | PASS | Focused tests beside touched modules + full-suite evidence rule carried into quickstart Scenario D |
| IV. Determinism (SHOULD) | PASS | Recorded clock on decision record; digest-derived IDs; replay dedup |
| V. Surfaces consistent (SHOULD) | PASS w/ documented exception | Web-only reviewed recovery continues spec007 precedent; TUI headless exception documented in spec Assumptions |
| VI. Style (MUST) | PASS | black 420 / isort / flake8; no BOM |

Pre-design gate: **PASS**. Post-design re-check after Phase 1 artifacts: **PASS** (no new violations introduced by data model or contracts).

## Phase 0 — Research

Output: [research.md](research.md). All clarification candidates resolved from code trace at `e6f04d2`; zero open NEEDS CLARIFICATION.

Key trace anchors:
- Multi-failure dead-end: `runtime/reconciliation.py:446-501` (preview), `:466-470`, `paper/ledger.py:1432-1441` (Resume rejection).
- Unkeyed failures are matchable (`failed_request_id` optional): `reconciliation.py:113-118,142-185`; identity = whole-event digest `:365-405`.
- Receipt binding discipline to extend: `reconciliation.py:109-185,371-405`; expiry/effect-intent rules `:726-749,779-797`.
- Gate semantics: `web/services.py:4126-4167` (readiness states), `:4246-4275` (423 guard), `:846-864` (`resume_allowed`).
- Effect-boundary ambiguity of legacy errors: `pipeline/session.py:197-240`, `paper/tick.py:810-855,897-955,983-1008`, `paper/ledger.py:586-605`.
- Write discipline: `paper/ledger.py:2200-2254`, `runtime/root.py:1984-2027`, lanes `web/services.py:3861-3869,4046-4076`.

## Phase 1 — Design

Outputs: [data-model.md](data-model.md), [contracts/legacy-failure-recovery.md](contracts/legacy-failure-recovery.md), [quickstart.md](quickstart.md).

Design summary:
1. **Classification function** (runtime/reconciliation.py): pure computation over verified replay + events + book evidence → per-failure `verified`/`attestable`/`not_resolvable` with per-check detail. `verified` requires no pending decision at `expected_head`; structurally sound uncertainty requires per-failure attestation; any structural failure blocks the set. No writes.
2. **Decision record** (paper/ledger.py audit kinds + reconciliation replay): new append-only audit kind; replay treats bound digests as resolved; digest-derived ID dedups.
3. **Web flow** (web/services.py + web/app.py): extended preview; confirm route with fund lock + control/audit lanes; stale/refusal matrix per contract.
4. **Desk display** (frontend paper.tsx): per-failure classification list + confirm affordance gated on `confirm_offered`.

## Project Structure

### Documentation (this feature)

```text
specs/009-legacy-failure-recovery/
├── plan.md              # This file
├── research.md          # Phase 0
├── data-model.md        # Phase 1
├── quickstart.md        # Phase 1
├── contracts/
│   └── legacy-failure-recovery.md
└── checklists/
    └── requirements.md  # /speckit-specify output
```

### Source Code (repository root)

```text
hedge_fund/
├── runtime/
│   ├── reconciliation.py          # classification fn, decision replay/dedup, unresolved-failure computation
│   └── test_reconciliation.py     # classification + replay + idempotency fixtures
├── paper/
│   ├── ledger.py                  # new audit kind append + replay treatment
│   └── test_ledger.py             # append boundary + byte-identity tests
├── web/
│   ├── services.py                # preview extension, confirm orchestration, lane usage
│   ├── app.py                     # confirm route
│   └── test_recovery.py / test_services.py  # refusal matrix, stale preview, lanes
frontend/
└── src/pages/
    ├── paper.tsx                  # per-failure evidence list + gated confirm
    └── paper.test.tsx             # display/gating tests
```

**Structure Decision**: extend existing modules; no new packages. Writer-map and admission boundaries are touched only via existing anchored helpers (any new raw write requires a WRITER_MAP entry with citing tests — repo convention).

## Risk register (carried into tasks)

- **R1 Over-classification**: the evidence rule (research.md Decision 2) could mark a genuinely post-effect failure `verified` if the no-pending discriminator or structural checks are too weak → mitigated by treating effect metadata and post-advance failure shapes as `attestable`, blocking structural gaps, and testing pending/no-pending heads.
- **R2 Replay semantic drift**: decision records must not alter resolution of legacy receipts/intents → FR-011 regression fixtures.
- **R3 Writer-map/admission regressions**: new append path must reuse anchored boundary → ledger.py tests + writer-map scan.

## Complexity Tracking

No constitution violations; table intentionally empty.
