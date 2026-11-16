# Phase 1 Contracts: Handover CLI Extensions

Interface: `aihf --root ROOT handover <subcommand>` (existing CLI surface in `run.py`). All new subcommands are offline operator ceremonies: they require the terminal operator's explicit input, never run unattended, and never accept credentials or secrets as arguments. No subcommand in this contract writes to the SOURCE root.

## 1. `handover inspect-source` (extended)

- **Effects**: read-only inventory of the source root, listing protected-fund and marker blockers; writes the **source evidence bundle** to exactly `DEST/runtime/private/v1/source-evidence.json`. `--evidence-out PATH` must name that absolute canonical destination-private path. Nothing is created or modified inside the source root.

## 2. `handover relocate-copy SOURCE --content-digest DIGEST` (split from relocate-from)

- **Effects**: hash-verified copy of `mandates`, `paper`, `research`, and now `runtime/private/v1/settings.json` into the empty destination; ledger heads compared post-copy. Performs NO target inventory validation and NO enrollment. `.env`/`cache` remain excluded.
- **Failure modes**: digest mismatch or interrupted copy → destination marked incomplete; source untouched.

## 3. `handover attest-stale-marker --marker RELPATH --source-evidence DIGEST --operator-statement "TEXT"` (new; destination-bound)

- **Preconditions**: run against the COPIED (unenrolled) destination; marker exists in the destination copy; liveness check finds no live owning process; `--source-evidence` digest matches a blocker entry in the source evidence bundle.
- **Effects**: records a destination-bound `stale-marker-retirement` artifact referencing the source evidence; the marker in the DESTINATION copy is retired into the destination root-private attestation record area. Source marker untouched.
- **Failure modes**: live owning process detected → refuse, no artifact. Missing marker or mismatched evidence digest → refuse. Repeat attestation → idempotent refusal pointing at existing artifact.

## 4. `handover attest-protected-fund --fund NAME --source-evidence DIGEST --operator-statement "TEXT"` (new; destination-bound)

- **Preconditions**: run against the COPIED destination; NAME is in the protected set and exists in the destination copy; evidence digest matches the bundle.
- **Effects**: records a destination-bound `protected-fund-inclusion` artifact; the fund becomes authorizable under its ORIGINAL name at the destination in both the root layer (`root.py` `_relative_parts`) and admission resource validation, preserving default denial and alias checks for everything unattested.
- **Failure modes**: unknown/unprotected name → refuse. Rename-based satisfaction → impossible by construction (artifact binds original name + destination root identity).

## 5. `handover relocate-finalize` (split from relocate-from)

- **Preconditions**: destination is COPIED and all intended attestations recorded.
- **Effects**: target inventory validation (attestation-aware) and enrollment; destination becomes RELOCATED (enrolled, read-only) per the existing `relocate-from` semantics (`handover.py:1033-1045`), now reachable because destination-bound attestations exist beforehand.

## 6. `handover trust-single-writer --inventory-digest D --operator-acknowledgement "EXACT"` (extended)

- **Change**: accepts a Windows runtime-scope identity (machine + account SID + root volume). All existing semantics unchanged: challenge required, 15-minute expiry, exclusive admission, inventory recheck, scope recheck on every later authority check.

## 7. TUI admitted write path (contract-level behavior)

- TUI paper operations on an enrolled, trusted root acquire the owner/lane through existing admission machinery and bind each execution to the operation; the guards at `tui/funds.py:34-45` and `tui/paper.py:511-516` become admission checks (deny without held lane + valid trust), not blanket enrolled-root rejections. No bypass path is added.

## Error contract

Every denial prints the failed precondition and the resolving command, and creates no partial state (FR-008, FR-010). Exit code 2 preserves the existing "offline enrollment and root writer admission are required" family for unenabled roots.