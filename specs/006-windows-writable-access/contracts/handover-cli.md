# Phase 1 Contracts: Handover CLI Extensions

Interface: `aihf --root ROOT handover <subcommand>` (existing CLI surface in `run.py`). All new subcommands are offline operator ceremonies: they require the terminal operator's explicit input, never run unattended, and never accept credentials or secrets as arguments.

## 1. `handover attest-stale-marker --marker RELPATH --operator-statement "TEXT"` (new)

- **Preconditions**: root opens via `RootContext`; marker exists under a fund subtree; liveness check finds no live owning process.
- **Effects**: records a `stale-marker-retirement` attestation artifact (see data-model.md); marker becomes excludable from inventory. The marker file itself is renamed into the root-private attestation record area, not deleted in place without record.
- **Failure modes**: live owning process detected → refuse, exit non-zero, no artifact. Missing marker → refuse. Repeated attestation for same marker → idempotent refusal pointing at existing artifact.

## 2. `handover attest-protected-fund --fund NAME --operator-statement "TEXT"` (new)

- **Preconditions**: NAME is in the protected set and exists under the root.
- **Effects**: records a `protected-fund-inclusion` artifact; fund becomes includable in inventory under its original name.
- **Failure modes**: unknown/unprotected name → refuse. Attempt to satisfy via a renamed fund → impossible by construction (artifact binds original name).

## 3. `handover relocate-from SOURCE --content-digest DIGEST` (extended)

- **Change**: verification set extended with `runtime/private/v1/settings.json` (hash-verified like `mandates`/`paper`/`research`). `.env`/`cache` remain excluded.
- **Unchanged**: target must be empty, disjoint, legacy-unreachable; source quiescent; ledger heads compared post-copy; re-hash verification.

## 4. `handover trust-single-writer --inventory-digest D --operator-acknowledgement "EXACT"` (extended)

- **Change**: accepts a Windows runtime-scope identity (machine + account SID + root volume). All existing semantics unchanged: challenge required, 15-minute expiry, exclusive admission, inventory recheck, scope recheck on every later authority check.

## 5. `handover inspect` / `inspect-source` (unchanged surface)

- Output additionally lists attestation artifacts present and any remaining blockers with the exact subcommand that resolves each (operator guidance only; no auto-execution).

## Error contract

Every denial prints the failed precondition and the resolving command, and creates no partial state (FR-008, FR-010). Exit code 2 preserves the existing "offline enrollment and root writer admission are required" family for unenabled roots.