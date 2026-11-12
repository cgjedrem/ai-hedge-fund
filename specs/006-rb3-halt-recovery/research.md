# Research: RB-3 Halt Recovery Completion

**Date**: 2026-11-12 | **Plan**: [plan.md](plan.md)

No open NEEDS CLARIFICATION items remained after the spec clarify round (FR-011 resolved to core + web only, user option A). Research below records the design decisions grounded in the verified 2026-11-12 discovery of baseline `b6aefe5`.

## Decision 1: Where readiness enforcement lives

- **Decision**: Extend `Ledger.require_ready_for_work()` as the single fund-level choke point for unresolved intents (execution and Resume), keeping the per-request-ID guard as a second layer.
- **Rationale**: Discovery showed the per-request guard (`ledger.py:784-841`) only examines the supplied request ID, so a *different* request ID bypasses it. A fund-level check closes the bypass for every caller of the readiness check without touching each entry point.
- **Alternatives considered**: (a) adding checks at every admission site (CLI/web/runner/tick) — rejected: N sites to keep consistent, easy to miss one; (b) checking only in the web preview — rejected: display-only, not enforcement.

## Decision 2: How outstanding intents appear in the preview

- **Decision**: Enumerate outstanding execution intents in the existing reconciliation preview builder, reusing the same evidence bundle (identity, head, book digest, fill digest) as recorded failures.
- **Rationale**: The preview already computes head/book/fill digests; adding an intent source keeps one rendering path in the web UI and one semantics for "needs reconciliation".
- **Alternatives considered**: a separate "intents" endpoint — rejected: fragments the operator's single review surface.

## Decision 3: Halt-interrupted executions

- **Decision**: Journal a reconciliation-required record at the halt re-raise boundary only when ≥1 effect was transmitted in the interrupted execution; zero-effect interruptions remain clean halts resumable after replay.
- **Rationale**: RB-3 semantics: Halt never undoes transmitted effects, so a partially-executed operation is genuinely ambiguous and must be reviewed; a no-effect interruption has nothing to reconcile. Matches the existing partial-fill boundary test (`test_tick.py:1476-1505`).
- **Alternatives considered**: always journal on halt-during-execution — rejected: forces review when nothing was transmitted, crying wolf on the recovery surface.

## Decision 4: Receipt expiry mechanics

- **Decision**: Add `issued_at`/`valid_until` (recorded clock) to the receipt; verification rejects expired receipts; legacy receipts without the fields are treated as expired (fail-closed). Validity window default: short and bounded (final value fixed in tasks; single-review-session scale, not days).
- **Rationale**: Spec005 T140 requires expiry; digest rebinding already covers state change, so expiry only needs a time bound. Fail-closed for legacy receipts avoids grandfathering unbounded authorizations.
- **Alternatives considered**: (a) no time bound, digest-only — rejected: leaves T140 unchecked and a receipt valid indefinitely across quiet periods; (b) wall-clock expiry — rejected: violates determinism principle (recorded clock required for replay).

## Decision 5: Surface scope

- **Decision**: No TUI/CLI changes; web desk remains the reviewed-recovery surface.
- **Rationale**: User-selected clarification option A (2026-11-12); TUI write-admission rules are a separate, larger question (enrollment/write authority) that must not be smuggled into a safety-semantics fix.
- **Alternatives considered**: TUI wiring now — deferred by user decision.

## Risk notes

- **Writer-map test**: any new raw write introduced by the implementation must be registered in `hedge_fund/runtime/test_writer_map.py` with citing test nodes (repo convention, AST-enforced).
- **Replay compatibility**: new journal event/field shapes must be ignored-or-handled by replay of pre-feature records; byte-identical replay of old records is the hard invariant (constitution Principle I).
- **Test runtime**: full `pytest hedge_fund` is ~40 min and must run isolated (concurrent runs cause runner timeouts); plan evidence accordingly.
