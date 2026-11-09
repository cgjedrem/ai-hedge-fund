# Feature Specification: 1Password runtime secrets for the Docker desk

**Feature Branch**: `cgjedrem-ubiquitous-sniffle` (app-managed worktree; branch creation skipped)
**Created**: 2026-11-09
**Status**: Implementation authorized 2026-11-09; provider allowlist remains empty
**Input**: "spawn another child session that will connect 1password to our docker environment. use coordinator agent to run speckit workflow pls"

## Context and scope

This is an unnumbered Spec005 provider/deployment extension, not a new numbered feature
and not completion of W07. Discovery maps it primarily to W05 and W06-W08.
W07 remains the constrained host-Ollama network path.

The current checkout is the clean main-derived baseline `3f7bea8ea2106670264b34520e0d2e6a6588fe20`,
not the implemented Spec005 continuation. The reference design is pinned to local Git object
`62c1dc46303eb98e73ba81375cb7848508bb0266`; see [research.md](research.md).
Parent Spec005 documents are absent from this checkout and are not recreated or replaced here.
These artifacts can be reviewed independently but are not an execution-ready plan for this tree.

The operator needs optional application credentials for explicitly selected bounded paper
research operations. The default free yfinance and local Ollama path needs no credential.
An Ollama endpoint/model choice is configuration, not an API key. Financial Datasets
credentials stay absent unless separately selected and authorized; this work grants no paid calls.

In scope: application-provider credential delivery to the intended Docker operator backend,
availability/status, isolation, revocation and restart policy. Existing TUI/CLI/web/runner
paths must not acquire broad ambient credentials. Legacy TUI remains outside the new delivery
path; read-only web and free/local scheduled runners must remain credential-free.

Out of scope: Saxo app keys, client secrets, OAuth access/refresh tokens, SIM authentication,
broker orders, unattended/cloud provider loops, 1Password write-back, Connect deployment,
new provider/model selection, real fund migration, root enrollment and automatic restarts.
Spec003 broker credential guidance is prior art, not authorization.

## Clarifications

### Session 2026-11-09

The user authorized autonomous implementation on 2026-11-09. Provider IDs were not supplied;
the allowlist remains empty until configured locally.

| Topic | Approved implementation decision / remaining boundary |
| --- | --- |
| Credential purpose | Optional bounded backend work; initial provider allowlist is empty. No paid or Saxo credentials by default. |
| Authentication | Attended Windows host CLI with desktop-app approval is the implementation assumption. Unattended service-account operation remains out of scope. |
| Retention | Runtime-only delivery is approved; values are not copied into the existing durable credential store. |
| Integration baseline | Local reconciliation of pinned Spec005 history is authorized; preserve the main-only Yahoo news fix. |

## User Scenarios & Testing

### User Story 1 - Keep free paper operation secret-free (Priority: P1)

As the operator, I can use free/local functions without unlocking a vault or adding keys.

**Why this priority**: Connecting a password manager must not create new financial or
authentication dependencies for existing keyless operation.

**Independent Test**: With password-manager access unavailable and no configured mappings,
fake free/local work succeeds and neither credential resolution nor paid-provider construction occurs.

**Acceptance Scenarios**:
1. **Given** no configured secret mapping, **when** free/local work is requested,
   **then** no vault access occurs and existing authorization rules remain unchanged.
2. **Given** a free scheduled runner, **when** the desk gains an optional credential,
   **then** that runner receives neither the credential nor password-manager authority.

### User Story 2 - Authorize only the selected backend (Priority: P1)

As the operator, I explicitly authorize a selected application credential for the intended
backend without typing its value into the browser or saving it in project configuration.

**Why this priority**: A working connection that leaks keys to Docker metadata or unrelated
services would not meet the request.

**Independent Test**: A fake resolver delivers a unique sentinel to the allowed fake backend
consumer; the same attempt against an observer, wrong root or unauthorized destination is denied.

**Acceptance Scenarios**:
1. **Given** an approved mapping and eligible target, **when** delivery is authorized,
   **then** only the selected consumer receives the resolved value and status contains no value.
2. **Given** a denied target or source, **when** delivery is attempted, **then** denial precedes
   vault resolution, publication, provider construction and fund effects.
3. **Given** a locked, absent or unavailable password manager, **when** credential-dependent
   work is requested, **then** it fails closed with a sanitized actionable reason.

### User Story 3 - Rotate and restart deliberately (Priority: P2)

As the operator, I can revoke or refresh access without silently changing admitted work,
reviving old credentials after a restart, or restarting an existing fund.

**Why this priority**: Credential lifetime must be predictable and independent of fund lifetime.

**Independent Test**: Rotate fake A to B during an admitted fake operation, revoke, then
recreate the synthetic backend; verify immutable capture and explicit reauthorization.

**Acceptance Scenarios**:
1. **Given** admitted work with A, **when** B is explicitly delivered, **then** new work
   uses B and the admitted work retains A only until its bounded completion or cancellation.
2. **Given** revoked access, **when** new work is requested, **then** it is denied;
   revocation cancels affected work cooperatively and prevents further dispatch boundaries.
3. **Given** process/container restart, **when** credential-dependent work is requested,
   **then** it requires fresh delivery and never recovers a value from a file or ambient key.

### Edge Cases

Partial/malformed delivery, empty/oversized values, terminal control characters, locked or
missing CLI, denied user prompt, network timeout, multiple 1Password authentication modes,
stale target identity, provider endpoint change, duplicate/replayed delivery, version conflict,
concurrent revoke/admission, helper crash, backend restart, Docker disconnect, child process
inheritance and error messages containing the sentinel must be covered.

## Requirements

### Functional Requirements

- **OP-FR-001**: Integration MUST be opt-in with an initially empty provider allowlist.
  yfinance and Ollama MUST NOT require or trigger credential resolution.
- **OP-FR-002**: Each configured mapping MUST identify an allowed application provider,
  exact selected root, eligible backend instance and approved provider destination.
  Broker credentials, arbitrary vault enumeration and unselected fields MUST be rejected.
- **OP-FR-003**: Authorization and target eligibility MUST be checked before secret
  resolution and again before publication or dispatch; read-only observers cannot import.
- **OP-FR-004**: Values and password-manager authority MUST NOT enter image layers,
  build arguments, repository files, Compose interpolation, Docker configured environment,
  command arguments, browser traffic/storage, exports or logs. Delivery MUST be runtime-only.
- **OP-FR-005**: Only the explicitly selected backend consumer and necessary short-lived
  delivery processes may hold the value. No blanket dotenv/HOME/vault/socket mounts,
  unrelated services, inherited child credentials or container vault access are permitted.
- **OP-FR-006**: Missing, locked, denied, expired, malformed or timed-out authentication
  MUST fail closed, without falling back to ambient keys, another account or stored values.
  Disabled integration MUST not block keyless operations.
- **OP-FR-007**: A resolved value MUST NOT be durably copied into the existing root credential
  store or any new plaintext cache. Non-secret source/version/status metadata may persist.
  A restart MUST invalidate all runtime-only handles.
- **OP-FR-008**: Admitted operations MUST capture an immutable credential generation bound to
  provider/destination/root/instance. Refresh affects only new admissions; unavailable old
  generations MUST fail rather than resolve the latest value under an old identity.
- **OP-FR-009**: Explicit revoke MUST stop new admissions immediately and fence subsequent
  dispatch of affected running work. Already transmitted provider requests cannot be recalled.
  No automatic polling, refresh, resurrection or app/fund restart is allowed.
- **OP-FR-010**: Status/errors MUST expose only configured/available/revoked/requires-auth,
  opaque generation and sanitized reason codes. Values, vault item paths and secret-derived
  fingerprints MUST NOT be exposed in browser status.
- **OP-FR-011**: Secret resolution MUST have a 60-second overall deadline including user
  authentication, no automatic retry and a non-echoing cancellation path. Limits MUST be
  enforced: at most one mapped credential per delivery, maximum 16 KiB UTF-8 value,
  reject empty values and NUL/CR/LF/control characters.
- **OP-FR-012**: Existing root admission, writer fencing, immutable captures, endpoint
  authorization, read-only observer role and free/local scheduler restrictions MUST remain.
  Delivery MUST NOT enroll a root, grant write authority or place any trade.
- **OP-FR-013**: Windows Docker Desktop Linux-container support MUST be demonstrated on a
  synthetic ext4 named-volume deployment with the final artifact. Host CLI desktop auth
  MUST NOT be assumed available inside LinuxKit, WSL or a container.
- **OP-FR-014**: Validation MUST use fakes/synthetic sentinels, isolated roots and provider
  adapters with no real provider/model/broker calls or real vault reads. Any later real
  credential smoke requires separate local user authorization and must not echo values.

### Key Entities

- **Source mapping**: Non-secret provider/root/target/destination association and restricted
  password-manager reference; never a resolved value.
- **Runtime lease**: In-memory value and opaque generation bound to the target process lifetime.
- **Operation capture**: Immutable lease identity, provider and destination used by admitted work.
- **Redacted status**: Availability and sanitized failure state, with no credential material.

## Success Criteria

### Measurable Outcomes

- **OP-SC-001**: All keyless positive/negative scenarios resolve zero secret references and
  construct zero paid-provider clients.
- **OP-SC-002**: A unique synthetic sentinel reaches exactly the intended fake consumer;
  zero occurrences appear on every forbidden surface listed in OP-FR-004 and durable storage.
- **OP-SC-003**: All unavailable/authentication-failure scenarios deny credential-dependent
  work within 60 seconds, with zero fallback, dispatch or fund effects.
- **OP-SC-004**: All rotate/revoke/restart scenarios preserve generation isolation and deny
  stale handles; post-restart delivery is always explicit.
- **OP-SC-005**: Every requirement has named automated coverage or a source-bound platform
  acceptance row; unexecuted/blocked rows are never reported as passed.

## Assumptions

One trusted local operator controls the host and Docker daemon. Protection against a malicious
host administrator, Docker administrator, compromised target process or privileged memory
inspection is outside this boundary; sentinel absence does not prove memory secrecy or
cryptographic erasure. Approved provider transmission is a necessary exception to the
no-browser/no-log rule. Remote/LAN Docker daemons are unsupported in the proposed first slice.

The runtime-only source is additive; existing durable credential behavior remains unchanged.
No provider IDs were supplied or inferred. An empty allowlist denies all credential delivery
until an operator explicitly configures an approved application-provider mapping locally.
