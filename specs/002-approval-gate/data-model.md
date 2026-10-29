# Data Model: Per-Fund Approval Gate

**Date**: 2026-10-29 | **Spec**: [spec.md](./spec.md)

## Entities

### 1. `approval_required` (FundSpec field)

| Aspect | Value |
|---|---|
| Kind | pydantic v2 field on `FundSpec` (`hedge_fund/fund/spec.py`) |
| Type | `bool` |
| Default | `False` (= current auto-execute behavior) |
| Validation | must be boolean; mandate YAML non-boolean ⇒ `ValidationError` wrapped as `ValueError` naming the path |
| Serialization | popped by `_serialize` when `False` (byte-parity with pre-feature output); present when `True` |
| Surfaces | mandate YAML key `approval_required`, TUI builder step (paper mode), `aihf paper create --approval` |
| Frozen | snapshot into `paper/<name>/fund.yaml` at deploy; no live-edit path (mandate-hash guard) |

### 2. Approval verdict mailbox (`pending-approval.json` in the fund dir)

```json
{
  "verdict": "approve",
  "decision_as_of": "2026-10-28",
  "decision_hash": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
  "decided_at": "2026-10-29T21:04:11+00:00",
  "by": "cli"
}
```

| Field | Meaning | Rules |
|---|---|---|
| `verdict` | `"approve"` or `"reject"` | only these two values ever written |
| `decision_as_of` | the `as_of` of the pending decision the verdict refers to | must match current `state.pending.as_of`; readable date, not unique identity |
| `decision_hash` | hash of the record that produced the pending decision (`state.prev_hash`) | lowercase SHA-256; must match current source record hash; mismatch ⇒ stale, never honored |
| `decided_at` | ISO-8601 timestamp of the verdict | informational/audit |
| `by` | `"cli"` or `"tui"` | which surface recorded it |

Lifecycle: written by `approve`/`reject` (CLI or TUI) → resolved by both decision fields in `_run` → consumed (file cleared) after the session's `ledger.append` succeeds. Missing/corrupt ⇒ treated as no verdict (fail-safe; never a yay). Written with `paths.write_atomic` (UTF-8, no BOM, `os.replace`, unique sibling temp path). A vote arriving after the gate read cannot alter that run or be rebound to a replacement decision; the next gate expires its mismatched source identity.

`clear_approval(expected)` compares the mailbox before unlink. The read/compare/unlink race is accepted at human voting speed. An unlink `OSError` records `approval_clear_failed` best-effort and does not stop the runner.

### 3. Audit events (`events.jsonl`, append-only, NOT hash-chained)

| Kind | When | Fields |
|---|---|---|
| `approve` | verdict recorded | `decision_as_of`, `decision_hash`, `by` |
| `reject` | verdict recorded or consumed | `decision_as_of`, `decision_hash`, `by`, `consumed` on consumption |
| `expire` | session skipped an unapproved/stale decision, or source session redone | `decision_as_of`, `decision_hash`, `reason` (`"no verdict"` / `"stale verdict"` / `"decision redone"`) |
| `tick` | gated verdict consumed successfully | existing tick fields plus `decision_as_of`, `decision_hash`, `approval_verdict`, `approval_by`; provides redo replay identity |
| `approval_clear_failed` | mailbox unlink failed | decision identity when available, `error`; nonfatal |

Existing kinds (`tick`, `tick_failed`, `halt`, `resume`, `redo`, `gap`, `checkpoint`) unchanged.

### 4. Unchanged entities (pinned)

- **`SessionRecord` / hash chain**: untouched. The pending decision lives only in the chain (`SessionRecord.decision` → `FundState.pending`).
- **Kill switch (`control.json`)**: untouched; the gate never reads or writes it.
- **`FundState`**: untouched — the skip path feeds `advance` a state copy with `pending=None`; no schema change.

## Validation rules

1. `approval_required` must be boolean (pydantic type) — non-boolean mandate value rejected with a clear error (FR-003).
2. Verdict `verdict` value must be `approve`/`reject` — anything else read from the file is treated as no verdict (fail-safe, FR-015).
3. Verdict `decision_as_of` and `decision_hash` must match the pending decision's source record to be honored (FR-006).
4. `approve`/`reject` commands refuse when the fund's gate is OFF or nothing is pending (FR-009).
5. Byte-parity: an approval-OFF FundSpec serializes byte-identically to the pre-feature output (FR-004) — enforced by test.
6. Explicit YAML `approval_required: false` must also preserve legacy serialization/hash parity.

## Redo semantics

- **Redo of decision-producing session**: clear a mailbox matching the superseded source record. Emit `expire` with `reason="decision redone"` and that decision identity. Resolution treats the latest matching expiry as invalidation even if unlink fails or the rerun produces the same hash.
- **Redo of execution session**: replay the consumed verdict from its original successful `tick` event when the mailbox is absent. Consumption metadata is keyed by `decision_as_of` + `decision_hash`; a later matching approve/reject event may replace it, and a later matching expiry invalidates it. No separate consume event kind.
- **Failed tick**: append does not succeed, so the mailbox remains. The halt is orthogonal; after resume, the same source record identity can consume the verdict on retry.

This design preserves the execution outcome on replay while preventing a verdict from authorizing a replacement decision.

## State transitions

```
(pending decision exists in chain; gate ON)
  ┌─ no matching verdict/history ─► next session: skip + expire event ─► pending replaced by next decision
  ├─ approve, both keys match ─────► next session: execute ─────────────► verdict consumed; tick stores identity
  ├─ reject, both keys match ──────► next session: skip + reject audit ─► book unchanged; tick stores identity
  ├─ stale/mismatched verdict ─────► next session: skip + expire event ─► stale file cleared best-effort; never honored
  └─ source decision redone ───────► invalidate matching verdict/history ► replacement needs a new verdict

(execution session redone): replay consumed approve/reject from matching tick history

(gate OFF): next session executes the pending decision exactly as today — no new state read or written.
```