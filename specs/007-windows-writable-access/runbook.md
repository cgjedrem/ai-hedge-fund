# Operator Runbook: Native Windows Root Handover

**Status:** planning artifact only. This procedure was not executed. Real-root
execution requires separate, explicit operator authorization.

## Safety boundary

- Use only a reviewed, test-owned synthetic root during development.
- Do not point this runbook at an existing production root without separate
  authorization and an approved backup/rollback plan.
- The source is authoritative and strictly read-only throughout the procedure.
- The destination must be a separate, empty local NTFS root.
- This protocol coordinates participating writers. It cannot fence unaware
  processes, scheduled tasks, older binaries or other same-account writers.
- Paper-trading scope only. No live broker execution or real-money orders.
- Never copy `.env` or secrets. Do not rewrite ledgers or rename protected funds.

## Required approvals and inputs

Record these outside both data roots before execution:

1. Operator and approver identities, authorization reference and maintenance
   window.
2. Exact source and destination paths. Do not infer either path from defaults.
3. Independent backup location, backup identity and restore owner.
4. Inventory of every process/service/task that can reach the source or
   destination, plus the operator responsible for stopping or excluding each.
5. Evidence/log location with restricted access. Store no credentials or secret
   values in the evidence package.

Stop if the source cannot be quiesced, the destination is not empty and
disjoint, either root is not on supported local NTFS, the backup is incomplete,
or any required identity/check is unavailable. Do not bypass a denial.

## Preflight

1. Confirm the application revision, dirty-diff identity, Python/Poetry
   environment and CLI version. Save the exact command transcript and timestamp.
2. Stop participating applications and confirm other writers are excluded for
   the full maintenance window. Admission locks are not proof that unaware
   writers have stopped.
3. Create and verify an independent backup of the source using the approved
   backup procedure. Keep it separate from source and destination.
4. Capture a read-only source manifest for `mandates`, `paper`, `research`, and
   `runtime/private/v1/settings.json` when present. Record relative path, type,
   size and SHA-256. Do not read or include `.env` contents.
5. Create the empty destination directory. Record its path and filesystem
   identity. Do not initialize, enroll or seed it manually.

## Inspect and stage

Substitute approved absolute paths for placeholders. Do not run until the
separate authorization is recorded.

```powershell
$Source = "<approved source path>"
$Destination = "<approved empty destination path>"
$Evidence = Join-Path $Destination "runtime\private\v1\source-evidence.json"

aihf --root $Source handover inspect-source --evidence-out $Evidence
```

Save the returned `content_digest`, `inventory_digest`,
`source_evidence_digest`, blockers and exact command output. Confirm the
evidence path is outside the source. Compare the source manifest with the
preflight manifest; any difference stops the procedure.

```powershell
aihf --root $Destination handover relocate-copy $Source --content-digest "<content_digest>"
```

Confirm the result is `copied`, no handover record exists yet, the destination
content matches the inspected digest, and the source manifest remains
byte-identical. Do not finalize while any blocker remains.

## Resolve destination blockers

Use `handover inspect` on the destination to review recorded artifacts,
remaining blockers and resolving commands.

- **Stale marker:** verify the source evidence identifies the exact relative
  `runner.pid` path. Confirm its owner is quiescent independently. The native
  liveness check must also confirm the process is not running. If the owner is
  live or unobservable, stop; do not remove or edit the marker. Run
  `handover attest-stale-marker --marker RELPATH --source-evidence DIGEST
  --operator-statement TEXT` only on the destination. The destination marker
  moves to private retired-marker storage with recorded evidence; the source
  marker remains untouched.
- **Protected fund:** verify its source evidence and original identity. Run
  `handover attest-protected-fund --fund ORIGINAL_NAME --source-evidence DIGEST
  --operator-statement TEXT` only on the destination. Never rename the fund to
  satisfy authorization.

Each artifact must bind to the destination and current source-evidence digest.
Repeat inspection after each attestation. Stop on any mismatch or unexpected
artifact; do not hand-edit private files.

## Finalize and enable

```powershell
aihf --root $Destination handover relocate-finalize
aihf --root $Destination handover inspect
```

Confirm enrollment is `relocated`, protected funds retain original names,
attestation references match their artifacts, destination ledger heads match
the source inventory, and the source manifest remains identical. Relocation
alone is read-only.

Only after a separate operator review, use the exact current inventory digest
and acknowledgement printed by `inspect`:

```powershell
aihf --root $Destination handover trust-single-writer `
  --inventory-digest "<reviewed digest>" `
  --operator-acknowledgement "<exact reviewed acknowledgement>"
```

Confirm runtime scope binds the intended Windows machine, operator SID and
destination volume. Any scope or inventory mismatch requires fresh inspection
and acknowledgement. Start the native TUI only after authority is reported
trusted. Verify an approved paper-only operation through the normal owner/lane
admission path; confirm prior ledger history hashes remain unchanged.

## Interruption, denial and rollback

- A failed/incomplete copy is not enrollable. Keep the source authoritative;
  preserve destination evidence and logs, then retry only under the approved
  recovery plan.
- A failed attestation must leave the source unchanged. If destination marker
  storage or artifacts are inconsistent, stop for offline recovery; never
  delete markers or forge artifacts.
- On any trust, identity, inventory, liveness or admission denial, stop. Do not
  add aliases, rename funds, remove locks, hand-edit ledgers or bypass checks.
- If enablement is abandoned, revoke destination trust after stopping
  participating writers. Keep the source and verified backup intact until the
  approver authorizes a separate retirement decision.
- Record expected versus observed results, exact measurements, failures and
  unknowns. A missing runtime check is INCONCLUSIVE, not PASS.

## Closeout record

Retain the authorization, backup reference, source/destination identities,
revision and dirty-diff digest, command transcript, evidence-bundle digest,
attestation artifact list, inventory digests, before/after source manifests,
trust scope and final verification. Record the execution owner and timestamp.
This document alone is not authorization and does not establish that a real
cutover has passed.
