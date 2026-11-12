# Phase 1 Data Model: Native Single-User Writable Access

Storage: JSON artifacts under the root-private `runtime/private/v1/` tree (existing convention). All artifacts are append/record-only; none mutate ledger data.

## Trust Record (extends existing)

The existing trusted-single-writer record (`handover.py:431-565,641-686`) gains a Windows-capable scope identity.

- **root binding**: canonical path, root device/volume identity, filesystem type, host (existing `root_binding`, `handover.py:188-199`) — unchanged
- **runtime scope**: NEW Windows variant = machine identity + operator account SID + root volume identity; mismatch denies and requires fresh challenge
- **inventory digest**: exact reviewed inventory hash at grant time — unchanged
- **protocol/build binding**: unchanged
- **operator acknowledgement**: exact challenge statement — unchanged
- **expiry/challenge**: 15-minute challenge window — unchanged

Validation: any field mismatch at recheck → deny (FR-006, FR-008).

## Attestation Artifact (new)

One artifact per resolved blocker, recorded before the blocker is excluded from inventory.

| Field | Meaning |
|-------|---------|
| `kind` | `stale-marker-retirement` or `protected-fund-inclusion` |
| `subject` | marker path (e.g. `paper/watchtower/runner.pid`) or fund name (e.g. `watchtower`) |
| `evidence` | liveness-check result for markers (owning process absent/present, how checked); inventory context for funds |
| `operator_statement` | exact operator-supplied attestation text |
| `recorded_at` | timestamp |
| `root_binding` | root identity the attestation applies to |

Validation rules:
- A marker may be excluded from inventory only with a matching `stale-marker-retirement` artifact whose evidence shows no live owning process (FR-004).
- A protected fund may be included only with a matching `protected-fund-inclusion` artifact naming the fund under its original name (FR-005); renaming never satisfies this.
- Artifacts are bound to one root identity; they do not transfer to a different root without re-attestation.

## Inventory Manifest (extends existing)

`build_head_inventory` (`handover.py:1159-1218`) output extended so attested-retired markers and attested-included protected funds appear as explicit, attestation-referenced entries rather than refusals. Unattested blockers still refuse the whole inventory (fail-closed).

## Relocation Manifest (extends existing)

`relocate-from` (`handover.py:971-1149`) verification extends to the settings file (`runtime/private/v1/settings.json`): copied with hash verification and ledger-head comparison like `mandates`/`paper`/`research`. `.env` and `cache` remain excluded by design (secrets are never tool-copied; cache is regenerable).

## State Transitions

Root enablement state machine (fail-closed; every transition requires the recorded artifact shown):

```text
UNENROLLED/UNSUPPORTED
  -- inspect-source (read-only record) --> INVENTORIED-BLOCKED
  -- all blockers attested --> INVENTORIED-CLEAN (source)
  -- relocate-from verified --> RELOCATED (target enrolled, read-only)
  -- inspect challenge issued --> CHALLENGED (15-min window)
  -- trust-single-writer exact ack --> TRUSTED-SINGLE-WRITER (writable)
  -- scope/inventory mismatch at any recheck --> DENIED (fresh challenge required)
```

Interruption at any step leaves the source root authoritative and untouched; partial targets are discarded or marked incomplete (spec Edge Cases).