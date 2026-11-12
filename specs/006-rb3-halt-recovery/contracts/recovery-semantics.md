# Contract: Recovery Semantics (service level)

**Date**: 2026-11-12 | **Plan**: [../plan.md](../plan.md)

Internal contract between the ledger/runtime layer and the web desk surface. No new endpoints; the existing web recovery preview/confirm/resume flow (`web/services.py:775-793`, `:3653-3738`) consumes these semantics. TUI/CLI unchanged (spec FR-011).

## Reconciliation Preview (read)

**Input**: fund identity (existing web recovery preview request).

**Output** (extended):
- `entries[]`: one per reconciliation-required condition —
  - `kind`: `recorded_failure` (existing) | `outstanding_intent` (new)
  - `operation_identity`, `ledger_head`, `broker_book_digest`, `fill_digest`, `reason`
- `resume_allowed`: boolean — true only when Halt is active, no unreviewed entries exist, and no unresolved Resume intent exists.
- `denial_reason` (when not allowed): includes `reconciliation_required` for outstanding intents.

**Guarantees**: every ambiguous interruption (crash-after-intent, halt-after-transmitted-effect) MUST appear as an entry. Preview is derived from one verified replay; no cross-process locking claims.

## Confirmed Resume (write)

**Input**: fund identity + recovery receipt + operator confirmation (existing flow).

**Receipt validity contract**:
1. Receipt binds to the current failure/intent identity, ledger head, book digest and fill digest — any change invalidates (existing).
2. Receipt carries `issued_at`/`valid_until` on the recorded clock; expired → denied (new).
3. Receipt missing expiry fields → denied as expired, fail-closed (new).
4. Single-use; consumed by the Resume it authorizes (existing).

**Resume behavior (unchanged invariants)**: effect intent recorded before clearing Halt; completion recorded after; retry of completed/intended operations returns the recorded outcome or is denied — never a duplicate fill.

## Work Readiness (enforcement, all callers)

Any ledger-mutating work request for a fund is denied with `reconciliation_required` while the fund has:
- an outstanding execution intent (no outcome), or
- an unresolved Resume intent, or
- an unreviewed recorded failure under Halt.

Denial is independent of the incoming request ID (no request-ID bypass).

## Out of scope

Live/broker recovery, multi-writer coordination, TUI/CLI recovery flows, auto-resolution or auto-expiry of reconciliation requirements.
