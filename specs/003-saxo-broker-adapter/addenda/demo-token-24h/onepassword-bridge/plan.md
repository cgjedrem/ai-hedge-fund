# Implementation Plan: In-app Saxo SIM inspection bridge

**Branch**: `cgjedrem-verbose-winner` | **Date**: 2026-11-09 | **Spec**: [spec.md](spec.md)
**Input**: Explicit nested feature directory
`specs\003-saxo-broker-adapter\addenda\demo-token-24h\onepassword-bridge`
**Status**: Documentation review finding resolved; implementation not started

## Summary

Add exactly one delivery capability, `saxo-demo-token` -> `saxo-sim-readonly`,
without widening the application-provider registry. Reuse host validation and
private framed stdin IPC into the existing authorized web process. A
generation-pinned, lease-backed demo token manager feeds a bounded GET-only SIM
inspection service, exposed as operator-only POST actions in a separate settings
panel. No secret crosses the browser. Root admission and SIM mutation gates remain
unchanged. The existing network-none `op-runtime` remains untouched. A separate
inspection-only Compose service uses a private bridge, a loopback-only published
desk port and a dedicated existing root volume with no fund state. Its application
client enforces the fixed SIM origin and exact GET allowlist; Docker bridge
connectivity itself is not a domain-level egress control.

## Technical Context

**Language/Version**: Python 3.11+, React 19/TypeScript, existing Poetry/npm tooling.
**Primary Dependencies**: Existing requests, FastAPI/Pydantic, React and UI controls;
no dependency change planned.
**Storage**: Backend memory for token/expiry/generation, actor choices and captures;
browser memory for current summary only; no durable inspection jobs or results.
**Testing**: Co-located pytest; Vitest/Testing Library; fake clocks/vaults/transports;
existing guarded synthetic-root harness.
**Target Platform**: Application Windows/Linux. The proposed port-published bridge
avoids Linux host networking and is intended for supported Docker Engine/Desktop
hosts; real acceptance on each claimed host platform remains gated on source-pinned
host-delivery and loopback/browser smoke evidence.
**Project Type**: Existing Python backend/host CLI and React web desk.
**Performance Goals**: 60-second total host delivery; 30-second total inspection;
10 seconds/request, five pages/collection, 100 rows/page, 500 rows/collection,
12 requests/action; one in-flight inspection per actor and bounded service capacity.
**Constraints**: Exact SIM origin/paths; no redirects/proxies/custom endpoint;
no refresh/retry/fallback; explicit consent; memory only; unchanged app-provider IDs.
**Scale/Scope**: One local operator, one selected account/action, no polling.

## Constitution Check

*Pre-design and post-design assessment; this is not runtime acceptance.*

- **I**: No ledger/book/history serialization or shared fund writes; fake filesystem
  inventory proves absence of inspection effects.
- **II**: Only explicit one-shot SIM GET actions; no orders/live/paid providers.
  Presence of a credential never grants consent.
- **III**: Tests first and co-located; targeted checks then full suite before source
  completion. Every residual failure needs exact, unchanged baseline evidence;
  historical fixture failures are not blanket exemptions. No suite run in this phase.
- **IV**: Inject clocks and controlled transport/concurrency.
- **V**: Dedicated desk panel and unchanged existing host inspection; document the
  backend-memory source as an in-app capability, not CLI Docker exec parity.
- **VI**: Existing Black 420/isort/Flake8 and UTF-8 no BOM conventions.
- **Governance**: Narrow dated OP-FR-002 scope supersession, no OP-FR-007 exception
  and no constitution amendment. Git hooks/setup are not executed because of
  explicit no-branch/no-commit/no-active-pointer-write instructions.
- **Review gates**: Parent performs caveman review, resolves comments and records
  disposition before source edits. No active formal red-team/plan-review hook was
  found; matching red-team triggers and lack of a new report/PR are disclosed in
  [research.md](research.md). Never report those gates as passed.
- **Deployment gate**: Preserve `docker-compose.op-runtime.yml` and its strict
  network-none target validation for all existing consumers. Add a standalone,
  opt-in `docker-compose.saxo-inspection.yml` with service
  `saxo-inspection-operator`, profile `saxo-inspection`, a uniquely isolated
  bridge, host publish `127.0.0.1:8877:8876`, and a separate, already admitted
  inspection-only data volume containing no fund state. Do not attach this service
  to `webdesk`, any fund volume, host networking, or another service network. The
  operator supplies the pre-existing dedicated root/volume; this change does not
  create, enroll, trust, or migrate roots. The app binds only the SIM origin and
  four GET paths in the inspection contract, uses verified TLS, disables redirects
  and proxies, and requires explicit per-action consent. Docker bridge networking
  permits general IP egress unless separately firewalled; only the application
  request layer is an asserted SIM allowlist here. Do not claim domain isolation.
  Add an exact `saxo-inspection` host-delivery target mode that checks the fresh
  container's service/profile labels, source/image pins, single dedicated volume,
  sole inspection network, exact loopback port binding, read-only filesystem,
  dropped capabilities, role and root before resolving anything. Keep the existing
  network-none validator path unchanged; never connect/reconfigure a running
  container or accept arbitrary bridge topology. Runtime acceptance remains gated
  on host-platform evidence and negative topology cases.

**Post-design result**: Offline architecture satisfies the documented constraints
by construction, subject to review and tests. Real Docker acceptance BLOCKED.

## Project Structure

### Documentation (this feature)

```text
specs\003-saxo-broker-adapter\addenda\demo-token-24h\onepassword-bridge\
  spec.md
  plan.md
  research.md
  data-model.md
  contracts\inspection.md
  quickstart.md
  tasks.md
  checklists\requirements.md
```

### Source Code (repository root)

```text
hedge_fund\secrets\docker_delivery.py           # capability-aware mapping and expiry
hedge_fund\runtime\external_credentials.py      # purpose/expiry/generation lease fences
hedge_fund\runtime\credential_delivery.py       # compatible optional expiry framing
hedge_fund\brokers\saxo.py                      # lease-backed demo subtype / bounded reads
hedge_fund\brokers\factory.py                   # explicit runtime inspection builder only
hedge_fund\web\saxo_inspection.py               # new transient actor-scoped service
hedge_fund\web\services.py                      # compose capability, root/actor checks
hedge_fund\web\schemas.py                       # strict action/response types
hedge_fund\web\app.py                           # dedicated operator routes
frontend\src\pages\settings.tsx                 # separate inspection card, no token input
frontend\src\lib\types.ts                       # capability and summary types
frontend\src\lib\api.ts                         # existing authenticated action helper
```

**Structure Decision**: Reuse existing transport and lease store with a separate
capability table; isolate inspection orchestration in one service. Do not use
durable `OperationStore`, trading factory, provider registry or shared-root mutations.

## Phase 0: Research

Completed source analysis is in [research.md](research.md). Notable constraints:
`isinstance(DemoTokenManager)` controls the GET guard; host CLI currently resolves
its own vault reference; all existing runtime allowlists are application-only;
existing operator target validation requires network-none. Preserve that existing
path and add a separate exact inspection-profile validator rather than bypassing
either constraint.

## Phase 1: Design

### Delivery and capability composition

Keep `APPLICATION_PROVIDER_IDS` and `runtime_provider_destinations` unchanged.
Add a fixed separate inspection-capability destination table and a parser for a
new non-secret `HEDGE_FUND_RUNTIME_CAPABILITIES` setting (empty by default).
Host mapping, lease validation and private server explicitly recognize the union
only at delivery boundaries. A Saxo capability must not be usable as an
LLM/data credential in readiness/admission/dispatch.

Use the existing host CLI `aihf-op-deliver --config ... --provider saxo-demo-token`.
The mapping retains exact root/container/image/revision/source/volume pinning,
adds a mandatory UTC `expires_at` only for this purpose, and never includes a
value. Existing legacy schema/frames remain valid. Extend strict private publish
shape with purpose-specific expiry, not a browser secret endpoint. Verify expiry,
target and backend permission before `op read`; recheck at publication.

### Runtime lifetime

Store injected-clock expiry and generation-local validity alongside the value.
Keep generic app-provider behavior unchanged. Capture current handle under lock;
every dispatch verifies capture, destination, owner/actor, revocation and expiry.
Release in `finally`. Rotation retains pinned A only through its bounded work;
late A rejection invalidates A, never current B. Revoke deletes/fences all affected
generations. Backend close clears everything. No latest-generation substitution.

Use a `DemoTokenManager` subtype for runtime lease use so the existing exact
GET/path guard still applies. Override secret resolution/cache and rejection:
no `SecretProvider`, synthetic reference or host `op` in the container; token is
retrieved only at dispatch and not kept on the client after request construction.
Fail closed on 401/403 credential rejection, local expiry, redirects, malformed
response and transport errors with fixed sanitized reasons.

### In-app service and actor boundary

Dedicated routes and payloads are defined in [contracts\inspection.md](contracts/inspection.md).
Existing HTTP session/origin/CSRF checks apply. Pass authenticated actor identity
from request state; do not accept it from JSON. Require existing owner/admission,
network enablement and per-action consent before client construction. No root
initialization, enrollment, fund binding or persisted jobs/results.

Discovery only lists eligible choices; selected inspection revalidates the
chosen identity then fetches just that account's balance/positions. Selections
expire after five minutes or sooner with their lease; they are actor/instance/
generation bound. At most 500 choices total per actor, one active action per actor,
and eight active actions/service; reject busy rather than queue unbounded work.
Record only monotonic deadlines and opaque identities in memory.

Use fixed SIM origin and four existing allowed paths. Build pagination parameters
internally; never fetch an upstream `__next` URL. Validate any next marker's
origin/path/query before extracting a strictly increasing skip, and detect loops.
Enforce collection/request/elapsed bounds and a 1 MiB streamed response-body cap
before JSON decoding. Ignore ambient proxy credentials for this transport.
All result construction uses typed allowlisted fields and final secret-aware
failure/redaction, so upstream strings cannot reflect the bearer into output.
Recheck authority/lifetime before returning. Disconnect cancels cooperatively;
the 30-second backend deadline still applies if immediate cancellation is unavailable.

### UI and reporting

Extend capabilities with a dedicated `saxo_sim_inspection` object; never append
Saxo to `settings.providers`, models or data providers. A separate settings card
shows unavailable/requires-auth/available/revoked/expired, generation and expiry.
Only explicit buttons discover/inspect/revoke. Use existing authenticated helpers;
no automatic POST, polling, secret input, endpoint/reference fields or browser
persistence. Disable overlapping actions and clear sensitive state on identity,
generation, capability/reconnect change, action failure or revoke. Visible warning:
"SIM read-only inspection; no fund connected; trading remains blocked."

### Deployment / validation boundary

Implement the dedicated source-pinned topology without altering the default
Compose profile or any running container. Before real Docker use, record the exact
supported loopback-browser/SIM-egress topology, its source/image pins,
capability-specific host checks and offline negative tests. No new container or
real secret action is run in this documentation phase. See the runbook's explicit
stop conditions.

## Complexity Tracking

| Added complexity | Why needed | Simpler alternative rejected because |
|---|---|---|
| Separate capability namespace | Broker bearer is not a model/data key | Adding Saxo to application enums authorizes unrelated consumers |
| Demo manager subtype | Preserve existing type-based GET fence | Duck typing alone bypasses the existing read-only check |
| Expiry and generation-local invalidation | Revocation/rejection races must not kill B or revive A | Provider-wide invalidation on a late A failure is incorrect |
| Transient actor-scoped choices | Prevent arbitrary account injection without durable state | Raw browser account keys and durable jobs broaden exposure/effects |

No constitutional violation is approved by this table.
