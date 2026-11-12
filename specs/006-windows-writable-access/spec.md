# Feature Specification: Native Single-User Writable Access for Existing Funds

**Feature Branch**: `cgjedrem-cautious-spork` (app-managed worktree; branch creation skipped, numbering applied — computed name `006-windows-writable-access`)

**Created**: 2026-11-12

**Status**: Draft

**Input**: User description: "I want writer authority though — I need the TUI or UI to write into my funds" / "single user, no matter where the funds are, just only that the old funds are kept" / "let's do speckit workflow for this issue"

## Background

The operator's existing paper-fund root (`C:\Users\ChristianGjedrem\.hedge-fund`) currently cannot be opened writable by any supported surface. Three independent fail-closed gates block it: the legacy path layout denial, the disabled Windows trusted-single-writer identity, and inventory refusal caused by protected fund names (`umbrella`, `watchtower`, `watchtower-weekly`) and two stale `runner.pid` markers. Read-only access already works and is not the deliverable. This feature establishes a supported, preservation-safe path to a single active writer for the existing funds.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Writable access to all existing funds (Priority: P1)

The operator (sole user of this machine) starts the supported interface and can run ticks, record decisions, and manage every existing fund — including `umbrella`, `watchtower`, and `watchtower-weekly` — with all prior ledger history, approvals, book state, mandates, and settings intact and byte-identical.

**Why this priority**: This is the entire reason for the feature; without it the funds are frozen assets.

**Independent Test**: On a bit-for-bit copy of the real root, complete the documented enablement procedure, then perform one write operation per fund and verify prior history replays identically and the new record appends correctly.

**Acceptance Scenarios**:

1. **Given** the existing root with all funds and history, **When** the operator completes the documented enablement and opens the interface, **Then** every fund is listed with its full prior history and accepts new write operations.
2. **Given** a fund with years of ledger history, **When** a new session record is appended, **Then** all prior records verify byte-identically and the hash chain remains unbroken.
3. **Given** the enabled root, **When** the operator closes and reopens the interface, **Then** write access persists without repeating the full enablement ceremony.

### User Story 2 - Explicit, auditable trust grant (Priority: P2)

The operator grants single-writer trust through an explicit, recorded acknowledgement — not a config flag flip — so there is a durable audit record of who authorized writes, against which exact inventory, and when.

**Why this priority**: Preserves the governance posture (fail-closed by default) while allowing the legitimate single-user case.

**Independent Test**: Inspect the recorded trust artifacts after enablement and confirm they bind the exact root, inventory digest, operator statement, and timestamp; confirm no write was possible before the grant.

**Acceptance Scenarios**:

1. **Given** an unenabled root, **When** any write is attempted, **Then** it is denied with a clear reason and no partial state is created.
2. **Given** the enablement procedure, **When** the operator supplies the required acknowledgement, **Then** a durable, inspectable record of the grant exists before the first write succeeds.

### User Story 3 - Safe resolution of blocked funds and stale markers (Priority: P3)

The operator resolves the protected fund names and stale `runner.pid` markers through an explicit, evidence-backed attestation flow — not by renaming funds to evade checks and not by silently deleting markers.

**Why this priority**: These three funds are the operator's real funds; they must be included, but the resolution must stay auditable.

**Independent Test**: Run the resolution flow against a fixture root containing protected names and stale markers; verify each requires an explicit operator statement and produces a recorded artifact.

**Acceptance Scenarios**:

1. **Given** a stale `runner.pid` whose owning process no longer exists, **When** the operator attests it is stale, **Then** the marker is retired with a recorded evidence trail.
2. **Given** a protected fund name, **When** the operator explicitly attests ownership and intent, **Then** the fund becomes writable under its original name with the attestation recorded.

### Edge Cases

- A second writer process (cooperating or unaware) attempts writes while the trusted writer is active: the attempt is denied or serialized, never interleaved.
- Enablement is interrupted mid-procedure (crash, power loss): re-running resumes or safely restarts without corrupting the root or producing a half-trusted state.
- A stale trust record from a previous machine/runtime scope is presented: it is denied and a fresh challenge is required.
- The relocation copy is interrupted: the source root remains untouched and authoritative; the partial target is discarded or clearly marked incomplete.
- An attempt to rename a protected fund to evade inventory checks is detected and denied.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST provide a supported procedure that grants single-user writer authority for an existing, previously unsupported root on the operator's own Windows machine, delivered through the native TUI as the target interface.
- **FR-002**: The procedure MUST preserve every existing fund's complete ledger history, approval records, book state, mandates, and settings without rewriting, re-serializing, or re-hashing any prior record.
- **FR-003**: The system MUST require an explicit, recorded operator acknowledgement bound to an exact root inventory before any write is enabled.
- **FR-004**: The system MUST provide a supported, attestation-based resolution for stale runner markers that records evidence and never silently deletes them.
- **FR-005**: The system MUST provide a supported, attestation-based inclusion path for the protected funds `umbrella`, `watchtower`, and `watchtower-weekly` under their original names.
- **FR-006**: The system MUST continue to deny writes from any second concurrent writer and from stale or mismatched trust records.
- **FR-007**: If data relocation is part of the procedure, the source root MUST remain intact and authoritative until the destination is verified against an identity manifest with hashes, and a rollback path MUST exist.
- **FR-008**: The enabled surface MUST deny all writes with a clear reason whenever any precondition (inventory match, trust validity, single-writer exclusivity) is not met.
- **FR-009**: The procedure MUST NOT require renaming protected funds, forging enrollment records, disabling admission checks, or rewriting ledger hashes.
- **FR-010**: All enablement and attestation artifacts MUST be inspectable after the fact (who, what, when, which inventory).

### Key Entities

- **Root**: The directory tree holding all fund data; identified by path, filesystem identity, and an immutable binding record.
- **Fund**: A named paper-trading portfolio with a hash-chained ledger, book state, approvals, and mandate settings.
- **Trust record**: A durable artifact recording an operator's single-writer grant, bound to an exact inventory digest, runtime scope, and timestamp.
- **Attestation**: An operator-signed statement resolving a specific blocker (stale marker, protected fund), stored as an auditable artifact.
- **Inventory manifest**: A hashed listing of root contents used to bind trust and to verify relocation fidelity.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: The operator can open the supported interface and complete a write operation (e.g., a paper tick) on every existing fund, including the three protected funds, with 100% of pre-existing ledger records verifying byte-identically afterward.
- **SC-002**: The full enablement procedure, excluding operator reading time, completes in under 30 minutes on the operator's machine.
- **SC-003**: Zero data loss: a post-cutover comparison of source and destination manifests shows 100% hash match across all fund data, and the original root remains intact until the operator explicitly authorizes its retirement.
- **SC-004**: Every denial path (second writer, stale trust, inventory mismatch) is exercised in testing and produces a clear, actionable error message in 100% of tested cases.
- **SC-005**: Every trust grant and attestation is reconstructible from on-disk artifacts alone, with no information available only in chat or session logs.

## Assumptions

- The operator is the sole user of the machine and accepts personal responsibility for excluding other programs from writing to the root; cooperative locks among participating writers remain in force.
- All existing funds, including `umbrella`, `watchtower`, and `watchtower-weekly`, are to be preserved and made writable — none are abandoned or excluded.
- The two `runner.pid` markers are stale (no live owning process); this will be verified, not assumed, during the procedure.
- Relocation of the data directory to a new path is acceptable to the operator; the legacy path itself carries no required meaning.
- Paper-only operation is unchanged: no live broker orders, no paid data providers, no unattended trading loops are introduced by this feature.
- The target interface is the native TUI on the operator's Windows machine (operator decision, 2026-11-12). The React web UI is out of scope for this feature and may follow as a later spec.

## Decisions

- **Target interface (2026-11-12, operator)**: Native TUI. The web UI is explicitly out of scope for this feature.
- **Relocation target (2026-11-12, operator)**: `C:\Users\ChristianGjedrem\aihf-data` on the same NTFS volume. The legacy `.hedge-fund` path is not blessed in place; data is relocated by copy-then-verify, and the original root remains intact until the operator explicitly authorizes its retirement.
