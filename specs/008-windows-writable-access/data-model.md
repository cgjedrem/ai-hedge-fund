# Phase 1 Data Model: Native Single-User Writable Access

Storage: JSON artifacts under the destination root-private `runtime/private/v1/` tree (existing convention), plus a source-evidence bundle stored OUTSIDE the source tree. All artifacts are append/record-only; none mutate ledger data. The source root is never written by this procedure.

## Trust Record (extends existing)

The existing trusted-single-writer record (`handover.py:431-565,641-686`) gains a Windows-capable scope identity.

- **root binding**: canonical path, root device/volume identity, filesystem type, host (existing `root_binding`, `handover.py:188-199`) — unchanged
- **runtime scope**: NEW Windows variant = machine identity + operator account SID + root volume identity; mismatch denies and requires fresh challenge
- **inventory digest**: exact reviewed inventory hash at grant time — unchanged
- **protocol/build binding**: unchanged
- **operator acknowledgement**: exact challenge statement — unchanged
- **expiry/challenge**: 15-minute challenge window — unchanged

Validation: any field mismatch at recheck → deny (FR-006, FR-008).

## Source Evidence Bundle (new; stored outside the source tree)

Read-only observation record produced by `inspect-source`, written to an operator-chosen path outside the source root (e.g. the destination staging area or an operator directory).

| Field | Meaning |
|-------|---------|
| `source_root_binding` | identity of the observed source root |
| `observed_inventory_digest` | hash of the read-only source inventory, including blockers |
| `blockers` | list of protected fund names and marker paths with observed content class and liveness-check input data |
| `recorded_at` | timestamp |

The bundle is hash-bound provenance: destination attestation artifacts reference its digest so the destination record proves which source observation justified each attestation. Nothing is written into the source tree.

## Attestation Artifact (new; destination-bound)

Recorded at the DESTINATION root, after the verified copy and BEFORE target inventory validation/enrollment (which would otherwise reject them, `handover.py:1033-1045`).

| Field | Meaning |
|-------|---------|
| `kind` | `stale-marker-retirement` or `protected-fund-inclusion` |
| `subject` | marker path (e.g. `paper/watchtower/runner.pid`) or fund name (e.g. `watchtower`) — original name, never a rename |
| `evidence` | liveness-check result for markers (no live owning process, how checked); inventory context for funds |
| `source_evidence_digest` | hash-binding to the source evidence bundle entry that justifies this attestation |
| `operator_statement` | exact operator-supplied attestation text |
| `recorded_at` | timestamp |
| `root_binding` | DESTINATION root identity the attestation applies to |

Validation rules:
- A marker may be excluded from destination inventory only with a matching `stale-marker-retirement` artifact at the destination whose evidence shows no live owning process (FR-004). Retirement moves the marker into the destination root-private attestation record area; the SOURCE marker is never touched.
- A protected fund may be included only with a matching `protected-fund-inclusion` artifact naming the fund under its original name (FR-005); renaming never satisfies this.
- Artifacts are bound to one root identity; they never transfer between roots. The destination-bound stage exists precisely so that target inventory validation sees destination-owned attestations.
- Root-layer enforcement: attestation-aware authorization in `root.py` `_relative_parts` and admission resource validation checks for a valid destination-bound artifact; absent one, protected names remain denied, and alias/evasion paths stay blocked.

## Inventory Manifest (extends existing)

`build_head_inventory` (`handover.py:1159-1218`) output extended so attested-retired markers and attested-included protected funds appear as explicit, attestation-referenced entries rather than refusals. Unattested blockers still refuse the whole inventory (fail-closed).

## Relocation Manifest (extends existing)

`relocate-from` (`handover.py:971-1149`) verification extends to the settings file (`runtime/private/v1/settings.json`): copied with hash verification and ledger-head comparison like `mandates`/`paper`/`research`. `.env` and `cache` remain excluded by design (secrets are never tool-copied; cache is regenerable). The copy stage performs no target inventory validation and no enrollment; validation runs only after destination-bound attestations exist (see state machine).

## State Transitions

Root enablement state machine (fail-closed; every transition requires the recorded artifact shown; source tree read-only throughout):

```text
SOURCE: UNSUPPORTED
  -- inspect-source (read-only; evidence bundle written OUTSIDE source) --> SOURCE-INVENTORIED (blockers listed)

DESTINATION: EMPTY
  -- relocate copy, hash-verified incl. settings, no enrollment --> COPIED (unenrolled)
  -- attest-stale-marker xN + attest-protected-fund xM (destination-bound, source-evidence-referenced;
     marker retirement applied at destination only) --> ATTESTED
  -- target inventory validation + enrollment --> RELOCATED (enrolled, read-only)
  -- inspect challenge issued --> CHALLENGED (15-min window)
  -- trust-single-writer exact ack (Windows scope) --> TRUSTED-SINGLE-WRITER (writable)
  -- scope/inventory mismatch at any recheck --> DENIED (fresh challenge required)
```

Interruption at any step leaves the source root authoritative and untouched; partial destinations are discarded or marked incomplete (spec Edge Cases).