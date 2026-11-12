# Phase 0 Research: Native Single-User Writable Access

All findings verified against commit `b6aefe5cf04753265168ec32bcb02976932a9588` by read-only code exploration. No NEEDS CLARIFICATION items remain.

## R1 — Windows runtime-scope identity for trusted single-writer

- **Decision**: Extend `_runtime_scope_identity` (`hedge_fund/runtime/handover.py:202-235`) to produce a Windows scope identity instead of disabling the platform, so the existing `trust-single-writer` ceremony (`handover.py:431-565,641-686`) can bind and recheck it.
- **Design**: Windows scope binds: machine identity + operator account identity (SID) + root device/volume identity. Scope mismatch on later checks → trust denied, fresh challenge required (same semantics as the existing Linux PID 1 scope binding, per commit `0b6f30a`).
- **Rationale**: Reuses the entire existing ceremony (challenge, 15-minute expiry, exact acknowledgement, inventory recheck, exclusive admission) instead of inventing a parallel grant path. Keeps fail-closed semantics: unknown/changed scope = denied.
- **Alternatives considered**: (a) Bless the legacy path in place — rejected: permanently weakens the legacy-layout safeguard (spec Decisions). (b) Docker ext4 named-volume path — rejected: strictly larger, NTFS→ext4 relocation expressly unapproved (`README.md:389-392`, `specs/005-web-engine-migration/spec.md:91`). (c) A config-flag grant — rejected: violates FR-003 (explicit recorded acknowledgement) and the documented governance posture.

## R2 — Legacy path resolution via relocation

- **Decision**: Use the existing `relocate-from` handover mechanism (`handover.py:971-1149`) from `C:\Users\ChristianGjedrem\.hedge-fund` to `C:\Users\ChristianGjedrem\aihf-data`, both native NTFS paths opened through `RootContext` (no 9p/bind involved — `root.py:201-206` accepts local NTFS).
- **Gap found and resolution**: `relocate-from` transfers only `mandates`, `paper`, `research`; persisted settings live at `runtime/private/v1/settings.json` (`runtime/configuration.py:24`) and would be lost. Extend relocation (or add a documented, recorded settings-transfer step inside the same verified ceremony) so settings arrive at the target with the same hash-verified treatment. `.env` and `cache` remain deliberately untransferred (secrets never copied by tooling; cache is regenerable).
- **Rationale**: Native NTFS→NTFS relocation exercises an already-implemented, hash-verified code path; no new filesystem admission is needed.
- **Alternatives considered**: in-place blessing of `.hedge-fund` (rejected, see R1); manual `robocopy` outside the ceremony (rejected: no identity manifest binding, no ledger-head verification, violates FR-007/FR-010 auditability).

## R3 — Stale `runner.pid` marker retirement

- **Decision**: Add a supported, attestation-based marker-retirement step to the handover flow: the operator supplies an explicit statement; the system records an evidence artifact (marker path, observed content class, liveness-check result, operator statement, timestamp) and only then excludes the marker from inventory.
- **Constraint**: markers are never silently deleted; liveness is verified, not assumed (spec Assumptions). `build_head_inventory` (`handover.py:1159-1218`) and the migration marker scan (`handover.py:945-946,1942-1952`) accept only attested-retired markers, recorded in root-private artifacts.
- **Rationale**: FR-004; keeps the marker protection meaningful while giving the operator a supported exit. Existing stale-reservation recovery (`handover.py:1621-1653`) is NOT reused — it targets enrolled owned-runner state and itself refuses legacy markers.
- **Alternatives considered**: operator deletes markers manually (rejected: unrecorded, violates FR-010); auto-expiry by PID age heuristic (rejected: guesses about process liveness, unsafe).

## R4 — Protected fund names (`umbrella`, `watchtower`, `watchtower-weekly`)

- **Decision**: Add an explicit per-fund operator attestation step that records ownership/intent for each protected identity and includes the fund, under its original name, in inventory and trust. Protection remains: without the attestation the names still block.
- **Constraint**: no renaming to evade `ensure_unique_resource_name` (`root.py:217-255`); no relaxation of the protected set. FR-044 protection of these real funds (`specs/005-web-engine-migration/spec.md:282`) is preserved and strengthened with an audit trail.
- **Rationale**: FR-005; the names are the operator's real funds and must stay under their original names (spec User Story 3).
- **Alternatives considered**: archive-then-recreate under new names (rejected: changes fund identity and history addressing; user requires original funds kept); blanket removal of the protected set (rejected: destroys a deliberate safeguard).

## R5 — Enrollment/trust sequence after code changes

- **Decision**: Final operator sequence (native, both roots NTFS):
  1. `aihf --root C:\Users\ChristianGjedrem\.hedge-fund handover inspect-source` (read-only inventory of source)
  2. Resolve blockers on the source record: per-fund protected-name attestations; stale-marker retirement with liveness evidence
  3. `aihf --root C:\Users\ChristianGjedrem\aihf-data handover relocate-from C:\Users\ChristianGjedrem\.hedge-fund --content-digest DIGEST` (verified copy incl. settings)
  4. `aihf --root C:\Users\ChristianGjedrem\aihf-data handover inspect` (issues challenge)
  5. `aihf --root C:\Users\ChristianGjedrem\aihf-data handover trust-single-writer --inventory-digest DIGEST --operator-acknowledgement "EXACT STATEMENT"`
  6. Launch native TUI against the new root; synthetic-fund write smoke precedes real-fund use
- **Rationale**: every step is an existing ceremony shape; only R1/R2-gap/R3/R4 are new code.
- **Note**: exact subcommand names/flags are contract-level decisions finalized in `contracts/handover-cli.md` during Phase 1; the sequence above is the design baseline.

## R6 — PR11 relationship

- **Decision**: No dependency. PR11 (`cgjedrem-didactic-meme`, head `da6cfee1`, tick-intent fencing + operation dedup) does not touch `runtime/root.py`, `runtime/handover.py`, or the migration contract, and leaves protected production funds and platform work out of scope. This feature proceeds on `main`; if PR11 merges first, rebase and re-run targeted admission tests.