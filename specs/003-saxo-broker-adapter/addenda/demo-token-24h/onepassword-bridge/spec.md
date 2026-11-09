# Feature Specification: In-app Saxo SIM inspection through 1Password delivery

**Feature Branch**: `cgjedrem-verbose-winner` (existing branch; no branch operation)
**Created**: 2026-11-09
**Status**: Offline implementation and focused governed validation complete; full Python suite, parent QA and host acceptance outstanding
**Input**: "yes do that using speckit workflow pls. write spec plan tasks - do a caveman review; address the review comments, then implement update me as you are completing the tasks"

## Context and scope

This is a nested, unnumbered extension of Spec003's demo-token addendum. The user
explicitly authorizes the narrow supersession of Spec005 1Password OP-FR-002:
deliver only a standalone Saxo 24-hour demo bearer for attended, in-app,
GET-only SIM inspection. See the dated amendment in
`specs\005-web-engine-migration\onepassword-docker\spec.md`.
No other broker credential is admitted. OP-FR-007 memory-only retention is unchanged.

The delivered credential is an inspection capability, never an application model or
data-provider option. Credential possession is not network consent, root authority,
SIM account ownership, fund readiness, or trading authorization.

Out of scope: live endpoints; OAuth app keys, client secrets or access/refresh
credential delivery; orders of any kind; account/fund binding, deployment, runners,
fund preparation, reconciliation writes; vault enumeration; token files,
environment/argument delivery, browser token entry; automated refresh or write-back;
automatic container/network changes. Existing SIM ownership denial remains intact.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Deliver a purpose-scoped inspection credential (Priority: P1)

As the local operator, I deliver the demo credential to the verified running
backend without putting its value in the browser or durable configuration.

**Why this priority**: Delivery must not turn a broker credential into general
application authority.

**Independent Test**: Synthetic host delivery reaches exactly one permitted
in-memory consumer; all wrong-target and wrong-purpose attempts resolve zero secrets.

**Acceptance Scenarios**:
1. **Given** an explicitly enabled inspection capability, a non-secret mapping and
   an already admitted operator backend, **when** attended delivery succeeds,
   **then** the desk shows availability, generation and expiry, never a value.
2. **Given** an observer, wrong root/instance/destination, expired mapping or lost
   ownership, **when** delivery is attempted, **then** it is denied before secret
   resolution initially and before publication after a failed authority recheck.
3. **Given** an available demo credential, **when** model/data settings or paper
   operations are inspected, **then** Saxo is absent from their provider catalogs
   and cannot supply any model/data call.

### User Story 2 - Explicitly inspect a SIM account in the desk (Priority: P1)

As the operator, I consent to one bounded SIM network action, see eligible account
choices, select one and inspect its currency, accounting cash and positions.

**Why this priority**: This is the requested in-app value; delivery alone does not
demonstrate connectivity.

**Independent Test**: Browser/service tests use fake responses and show candidate
discovery followed by explicit selected-account inspection with zero order calls.

**Acceptance Scenarios**:
1. **Given** delivered access and valid local operator authority, **when** I
   explicitly consent to discovery, **then** the desk shows eligible account choices
   and does not silently select even a sole candidate.
2. **Given** a current choice belonging to this actor and credential generation,
   **when** I explicitly consent to inspect that choice, **then** the desk shows a
   SIM/read-only summary and clearly states that no fund is connected or enabled.
3. **Given** absent consent, missing network capability, stale selection, malformed
   or ambiguous account data, **when** inspection is requested, **then** it fails
   safely without returning a successful or partial account summary.
4. **Given** paging that exceeds a finite limit or a stalled service, **when** a
   request cannot finish within its bound, **then** it stops and requires another
   deliberate user action; no automatic polling or retry occurs.

### User Story 3 - Lose access safely (Priority: P2)

As the operator, I revoke or replace the credential and understand why expiry,
rejection or restart requires fresh attended delivery.

**Why this priority**: Old inspection sessions must not retain hidden authority.

**Independent Test**: Fake clock and controlled concurrency cover rotation,
rejection, expiry, revoke, shutdown and restart without any real credential.

**Acceptance Scenarios**:
1. **Given** an inspection pinned to A, **when** B is delivered, **then** new work
   uses B and existing work never substitutes B for A.
2. **Given** revocation, expiry or rejection of A, **when** work reaches another
   dispatch or result-publication boundary, **then** affected work stops; an already
   transmitted request cannot be recalled.
3. **Given** a backend restart, **when** the desk reconnects, **then** old handles,
   selections and summaries are invalid and fresh delivery is required.

### Edge Cases

Duplicate/replayed delivery; generation conflict; concurrent revoke and dispatch;
late failure of A after B delivery; rejected/expired opaque bearer; missing or
invalid expiry; duplicate account IDs across pages; incomplete eligibility fields;
non-finite balances; repeated/hostile pagination links; live/cross-host redirects;
wrong account choice; request cancellation; authority loss during a network call;
transport exceptions or returned account fields containing credential material;
unsupported Docker network topology; old browser tabs after backend restart.

## Requirements *(mandatory)*

### Functional Requirements

- **SB-FR-001**: Delivery MUST be disabled unless the operator explicitly enables
  the dedicated `saxo-demo-token` capability and exact `saxo-sim-readonly` purpose.
  Saxo MUST remain absent from application provider/model/data catalogs.
- **SB-FR-002**: The host MUST use one explicit non-secret source/target mapping,
  verify the eligible Docker operator/root/instance and purpose before reading the
  field, and recheck authority/identity before publication. No reference is inferred.
- **SB-FR-003**: The value MUST travel only through the existing private delivery
  channel into backend memory. No resolved value, secret-derived fingerprint or
  vault path may appear in browser traffic, errors, logs, exports, files, configured
  environment or arguments. Browser forms MUST contain no token input.
- **SB-FR-004**: Delivery/status/revoke/inspection MUST retain existing root-owner,
  local operator session and applicable mutation-token checks. Observers MUST NOT
  import or invoke inspection. Inspection MUST NOT create, enroll or initialize a
  root; an already eligible context is required only by existing permission policy.
- **SB-FR-005**: Discovery and selected-account inspection MUST each require
  explicit per-action network consent and enabled network capability. Page loads,
  availability checks and credential delivery MUST make zero broker requests.
- **SB-FR-006**: Inspection MUST permit only identity, eligible-account discovery,
  accounting balances and position GETs to Saxo SIM. All redirects, arbitrary
  destinations, order APIs and non-GET broker calls MUST be refused before dispatch.
- **SB-FR-007**: Selection MUST be explicit, actor/instance/generation-bound,
  short-lived and drawn from validated discovery. Arbitrary browser account/client
  identifiers MUST NOT control outgoing account scope. Ambiguous, duplicate,
  incomplete or contradictory responses MUST fail closed.
- **SB-FR-008**: Each action MUST have a 30-second overall deadline, at most
  10 seconds per request, five pages per collection, 100 rows per page and 500 rows
  per collection, and at most 12 broker requests. Exceeding any limit MUST fail
  closed without a partial success; no automatic retry or background polling.
- **SB-FR-009**: Each action MUST pin one immutable generation and recheck root,
  actor, purpose, expiry and revocation before each dispatch and before publishing
  results. Rotation MUST NOT change an in-flight generation. All exit paths release
  the capture; no value may remain cached in a long-lived client.
- **SB-FR-010**: Operator-supplied non-secret absolute expiry MUST be validated
  at delivery and enforced with an injected clock; it must be future and no more
  than 24 hours from delivery. This is a conservative local cap, not proof of
  issuer validity. Rejection/known expiry invalidates the affected generation
  without refresh, retry, fallback or write-back; a late A failure MUST NOT revoke B.
- **SB-FR-011**: Revoke MUST immediately deny new admissions and subsequent
  dispatch/result boundaries. Restart/shutdown MUST discard values, captures,
  choices and summaries. A new process MUST require fresh attended delivery.
  The result boundary is the local commit of the complete reflection-checked
  projection, serialized with lease revoke/invalidation/close and actor cancel.
  Revocation winning before commit MUST suppress the result; publication winning
  first may still complete HTTP delivery after revocation. No transport recall
  or atomic HTTP-send guarantee is implied. Local authority is rechecked at
  commit, not held immutable through transport.
- **SB-FR-012**: The desk MUST display only allowlisted summary fields and fixed,
  actionable error codes; availability MUST NOT be labelled a verified connection.
  Sensitive account results stay transient and are cleared on revoke, stale
  generation, logout/reconnect/restart or action failure; no durable job/result store.
- **SB-FR-013**: Fund state, ledgers, caches, approvals, ownership policy and runners
  MUST remain unchanged. Inspection MUST NOT construct a trading broker or imply
  readiness for fund deployment or any order.
- **SB-FR-014**: Offline acceptance MUST cover all foregoing requirements using
  fake vaults/transports/clocks and synthetic admitted contexts, including sentinel
  redaction, zero order calls and zero shared-state writes. No real vault read,
  environment/token-file read or network call belongs in automated validation.
- **SB-FR-015**: Existing default Docker network isolation and target eligibility
  MUST NOT be silently relaxed. The `op-runtime` profile remains `network_mode: none`
  with no published port. In-app inspection MUST use a separately declared,
  opt-in `saxo-inspection` service/profile, isolated from every fund root and bound
  only to a host-loopback browser port. Its only broker client MUST enforce the
  fixed TLS-verified SIM origin, exact read-only GET paths, no redirects, no
  proxy/custom endpoint and explicit per-action consent; a Docker bridge MUST NOT
  be described as a domain allowlist. Host delivery MUST admit only this explicitly
  pinned inspection target while preserving all current checks and denial of
  arbitrary networks, mounts, ports, roles and roots. This is the sole topology
  exception and applies only to the `saxo-sim-readonly` inspection purpose; it
  does not authorize application-provider use or loosen existing profile
  governance. The design and supported host/platform checks must be reviewed
  before runtime use; unavailable evidence is reported BLOCKED, never as a
  connected or validated deployment.

### Key Entities *(include if feature involves data)*

- **Inspection capability**: Dedicated purpose authorization, separate from provider selection.
- **Delivery mapping**: Operator-supplied reference, exact target identity and conservative expiry.
- **Runtime lease**: In-memory value, generation, instance, purpose and invalidation state.
- **Account choice**: Ephemeral actor-scoped selection identity from validated discovery.
- **Inspection summary**: Transient account identity/currency/cash/position projection, not a fund binding.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SB-SC-001**: Every wrong-purpose, unauthorized or wrong-target initial delivery
  test performs zero secret resolutions and zero publications.
- **SB-SC-002**: All success/failure scenarios contain zero token/sentinel occurrences
  on forbidden surfaces and perform zero orders or fund-state changes.
- **SB-SC-003**: Every accepted inspection completes or safely stops within 30 seconds;
  100% of over-bound, stale, rejected and malformed scenarios fail closed.
- **SB-SC-004**: Every multi-account scenario requires explicit selection and displays
  only the selected account's validated summary.
- **SB-SC-005**: All lifecycle cases prevent stale admissions/dispatch/publication,
  and every restarted backend requires explicit fresh delivery.

## Assumptions

- One trusted attended host operator controls an existing eligible backend.
  Host/Docker administrator or compromised-process memory attacks are outside scope;
  removal of Python references is not a cryptographic erasure guarantee.
- The operator supplies the exact local field reference and a conservative expiry;
  no real vault/configuration is read while preparing these documents.
- Read-only SIM testing has prior user authorization, but this phase exercises none.
  Missing real source mapping, admission or supported topology remains a runtime blocker.
- The parent executes the requested caveman review and resolves findings before
  implementation; checklist completion is requirements quality, not runtime acceptance.
