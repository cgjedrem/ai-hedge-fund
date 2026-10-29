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
  "decided_at": "2026-10-29T21:04:11+00:00",
  "by": "cli"
}
```

| Field | Meaning | Rules |
|---|---|---|
| `verdict` | `"approve"` or `"reject"` | only these two values ever written |
| `decision_as_of` | the `as_of` of the pending decision the verdict refers to | mismatch with current `state.pending.as_of` ⇒ stale ⇒ ignored, never honored |
| `decided_at` | ISO-8601 timestamp of the verdict | informational/audit |
| `by` | `"cli"` or `"tui"` | which surface recorded it |

Lifecycle: written by `approve`/`reject` (CLI or TUI) → read at gate time in `_run` → consumed (file cleared) after the session's `ledger.append` succeeds. Missing/corrupt ⇒ treated as no verdict (fail-safe; never a yay). Written with `paths.write_atomic` (UTF-8, no BOM, `os.replace`).

### 3. Audit events (`events.jsonl`, append-only, NOT hash-chained)

| Kind | When | Fields |
|---|---|---|
| `approve` | verdict recorded | `decision_as_of`, `by` |
| `reject` | verdict recorded | `decision_as_of`, `by` |
| `expire` | session skipped an unapproved (or stale-verdict) pending decision | `decision_as_of`, `reason` (`"no verdict"` / `"stale verdict"`) |

Existing kinds (`tick`, `tick_failed`, `halt`, `resume`, `redo`, `gap`, `checkpoint`) unchanged.

### 4. Unchanged entities (pinned)

- **`SessionRecord` / hash chain**: untouched. The pending decision lives only in the chain (`SessionRecord.decision` → `FundState.pending`).
- **Kill switch (`control.json`)**: untouched; the gate never reads or writes it.
- **`FundState`**: untouched — the skip path feeds `advance` a state copy with `pending=None`; no schema change.

## Validation rules

1. `approval_required` must be boolean (pydantic type) — non-boolean mandate value rejected with a clear error (FR-003).
2. Verdict `verdict` value must be `approve`/`reject` — anything else read from the file is treated as no verdict (fail-safe, FR-015).
3. Verdict `decision_as_of` must equal the current pending decision's `as_of` to be honored (FR-006).
4. `approve`/`reject` commands refuse when the fund's gate is OFF or nothing is pending (FR-009).
5. Byte-parity: an approval-OFF FundSpec serializes byte-identically to the pre-feature output (FR-004) — enforced by test.

## State transitions

```
(pending decision exists in chain; gate ON)
  ┌─ no verdict file ────────────► next session: skip + expire event ──► pending replaced by next decision
  ├─ verdict=approve, key matches ─ next session: execute ──────────────► verdict consumed (file cleared)
  ├─ verdict=reject,  key matches ─ next session: skip + reject-consumed ► book unchanged; verdict consumed
  └─ verdict present, key stale ── next session: skip + expire event ──► stale file cleared; never honored

(gate OFF): next session executes the pending decision exactly as today — no new state read or written.
```