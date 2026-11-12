# Research: RB-3 Halt Recovery Completion

**Date**: 2026-11-12 (revised after rebase onto `448056f` / PR #11) | **Plan**: [plan.md](plan.md)

No open NEEDS CLARIFICATION items (FR-009 surface scope resolved by user, option A). Decisions below are grounded in the 2026-11-12 re-verification against current main.

## Decision 0: Rescope after PR #11

- **Decision**: Discard the pre-rebase gap list; target only the four re-verified gaps (recovery reachability, gate consistency, legacy no-ID post-fill journaling, receipt expiry).
- **Rationale**: PR #11 (specs/006-paper-writer-safety) delivered orphaned-intent enumeration/fencing/resolution, safe pre-effect aborts (`tick_aborted` with `no_effects=true`), post-effect `tick_failed` journaling for request-identified ticks, receipt replay, and logical-operation dedup. Re-speccing done work would duplicate it.
- **Alternatives considered**: keep original scope — rejected: verified as largely fixed on current main.

## Decision 1: Recovery reachability at the service layer

- **Decision**: Translate readiness denial into a distinct `reconciliation_required` state in the web snapshot/report path, separate from corrupt replay; keep the desk's recovery fetch/card available in that state. Prefer the service-level fix; touch `frontend/src/pages/paper.tsx` only if the service state cannot drive the existing display conditions (`:157-159`, `:690-693`).
- **Rationale**: The review-verified failure mode is `observe_approval_for_display()` raising → `ledger.ok=false` → recovery fetch suppressed. The distinction must live where the snapshot is built (`web/services.py:4082-4089` region).
- **Alternatives considered**: frontend-only condition change — rejected: would still conflate corruption with not-ready at the API level.

## Decision 2: Unmatched approval-consumption resolution

- **Decision**: Extend the PR #11 orphaned-intent preview/resolution machinery to approval-consumption journal entries that match no intent, with the same audited, digest-bound review.
- **Rationale**: These entries currently wedge the fund (regression anchor `paper/test_tick.py:627-655`); the resolution machinery already exists and only needs a wider enumeration source.
- **Alternatives considered**: separate approval-resolution flow — rejected: duplicates the review surface.

## Decision 3: One unresolved-state query, three call sites

- **Decision**: Single fund-level query (failures pending review + outstanding tick intents + unresolved Resume intents + unmatched approval consumption) consumed by `require_ready_for_work()`, web `resume_allowed`, and the `Ledger.resume()` pre-check. PR #11's separate `require_ready_for_tick` fence and recovery-path admission stay unchanged — recovery operations must never be blocked by the gate they serve.
- **Rationale**: Review-verified divergence: web denies unresolved tick intents, backend Resume uses only the general guard; only `Ledger.resume()` rejects unfinished Resume intents. One query removes the divergence at the smallest change cost.
- **Alternatives considered**: per-call-site additions — rejected: re-creates the divergence the next time one site changes.

## Decision 4: Legacy no-ID post-fill journaling

- **Decision**: Mirror the request-identified outer-handler journaling (`tick.py:931-934`) in the no-request-ID path (`:212-216`, `:474-500`) only when ≥1 effect was transmitted and no outcome exists. Zero-effect interruptions keep PR #11 clean-abort semantics.
- **Rationale**: A post-fill interruption is genuinely ambiguous and must be reviewable on every execution path; a no-effect interruption has nothing to reconcile.
- **Alternatives considered**: require request IDs everywhere — rejected: changes legacy/TUI call contract beyond this feature's scope.

## Decision 5: Receipt expiry mechanics (spec005 T140)

- **Decision**: Add `issued_at`/`valid_until` (recorded clock) to both receipt types; verification rejects expired receipts and treats field-less legacy receipts as expired (fail-closed); digest rebinding preserved. Validity window: bounded, single-review-session scale; exact value fixed at implementation and recorded in evidence.
- **Rationale**: State change is already covered by rebinding; expiry closes the time window. Fail-closed legacy handling avoids grandfathering unbounded authorizations.
- **Alternatives considered**: digest-only (no time bound) — rejected: leaves T140 unimplemented; wall-clock expiry — rejected: violates determinism (Principle IV).

## Risk notes

- **Writer-map**: any new raw write needs a WRITER_MAP entry with citing test nodes (AST-enforced).
- **Replay compatibility**: additive journal fields/events only; byte-identical replay of pre-feature records is the hard invariant.
- **PR #11 regression surface**: safe aborts, dedup, tick fence, intent resolution, receipt replay — guarded by the existing suites plus task T022.
- **Test runtime**: full `pytest hedge_fund` ~40 min, isolated runs only.
