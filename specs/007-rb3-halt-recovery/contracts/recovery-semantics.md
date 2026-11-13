# Contract: Recovery Semantics (service level)

**Date**: 2026-11-12 (revised post-rebase onto `448056f` / PR #11) | **Plan**: [../plan.md](../plan.md)

Internal contract between the ledger/runtime layer and the web desk surface. Extends PR #11 semantics; no new endpoints. TUI/CLI unchanged (spec FR-009).

## Snapshot / Recovery Visibility (read)

- Snapshot distinguishes three states: `corrupt` (replay/link verification failed), `reconciliation_required` (valid replay, unresolved-state set non-empty), `ready`.
- A readiness denial (e.g. unresolved approval consumption) MUST surface as `reconciliation_required`, NOT collapse into a generic not-ok that suppresses recovery (FR-001).
- The desk fetches and displays the recovery surface in `reconciliation_required` state — with or without an active Halt — and in the halted state (existing PR #11 behavior).

## Reconciliation Preview (read)

**Output**: entries for every reconciliation-required condition — recorded failures, orphaned tick intents (PR #11), and unmatched approval-consumption entries (new, FR-002) — each with operation identity, ledger head, broker-book digest, fill digest, reason; plus `resume_allowed` and `denial_reason`.

**`resume_allowed` semantics** (clarifies PR review R1): the flag governs whether the desk offers the reviewed Resume/confirmation action; it does not require a pre-existing receipt (the confirmed Resume creates the receipt). Eligibility to *submit* review and *authorization* of the write are distinct: the write path re-verifies at commit time.

## Unresolved-State Gate (enforcement, all ordinary-work callers)

One fund-level unresolved-state set — recorded failures pending review + outstanding tick intents + unresolved Resume intents + unmatched approval consumption — denies ordinary ledger-mutating work identically at:

1. `Ledger.require_ready_for_work()` (all ordinary work),
2. web `resume_allowed` (desk permission display),
3. `Ledger.resume()` pre-check (backend authorization).

Recovery operations (intent resolution, unmatched-consumption resolution, confirmed Resume) use their own admission and are NEVER blocked by the gate they serve (clarifies PR review R5). PR #11's separate new-identity tick fence (`require_ready_for_tick`) is unchanged.

## Receipts (write authorization)

Both receipt types (failure-bound, intent-bound):

1. Bind to current identity + ledger head + book digest + fill digest — any change invalidates (existing rebind, preserved).
2. Carry `issued_at`/`valid_until` on the recorded clock; expired → denied with re-review reason (new, FR-006).
3. Missing expiry fields (legacy) → denied as expired, fail-closed (new).
4. Single-use; consumed by the operation they authorize (existing).
5. Expiry invalidates the authorization only; the reconciliation requirement persists until reviewed against current state (FR-008).

## Preserved invariants

Resume records effect intent before clearing Halt and completion after; retries add zero additional fills; completed operations return recorded outcomes; zero-effect interruptions require no book-ambiguity review; daily/weekly session keys unchanged; Halt stops admission only.

## Out of scope

Live/broker recovery, multi-writer coordination, TUI/CLI recovery flows, auto-resolution of reconciliation requirements.
