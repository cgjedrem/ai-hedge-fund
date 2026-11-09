# Research: Saxo inspection delivery integration

**Date**: 2026-11-09
**Method**: Read-only local source and governance inspection; no scripts, tests,
credentials, environment dumps, external research or network calls.

## Decision: Reuse the private backend channel, not a token file

`hedge_fund\secrets\docker_delivery.py` validates `SourceMapping`, pins container,
image/revision/source hash/volume, exchanges status, resolves on the host and sends
a bounded frame to `hedge_fund.runtime.credential_delivery --receive` on private
stdin. `CredentialDeliveryServer` publishes into the web process's
`RuntimeCredentialLeaseStore`. `docker exec aihf saxo inspect` cannot see this
process-local memory. A new file, environment variable or argv token is rejected.
OP-FR-007 needs no supersession.

## Decision: Separate credential capability from application providers

Today `SourceMapping`, `_provider_id`, `runtime_provider_destinations` and the lease
constructor all restrict delivery to `APPLICATION_PROVIDER_IDS`. That set is
derived from the model/data registries. Do not insert Saxo into those registries or
the application-provider set. Add an exact capability/destination table for the
bridge and compose validated application destinations with explicitly configured
inspection destinations only at the delivery/lease boundary. Existing
`runtime_provider_destinations` remains application-only. Test both positive
purpose admission and negative application-consumer paths.

## Decision: Retain the demo-client type guard

`SaxoClient.request` gates read-only access with
`isinstance(self.tokens, DemoTokenManager)`, not merely `auth_mode`.
An arbitrary duck-typed lease manager would bypass this guard. Introduce a
lease-backed `DemoTokenManager` subtype that overrides token access/rejection,
never caches the raw value, and retains the exact GET/path restrictions. Do not
invent an `op://` reference, invoke `SecretProvider`, or convert the demo token
into an OAuth credential. Add a dedicated runtime inspection builder rather than
relaxing `_credential_mode` or `build_broker`.

The existing client hardcodes the SIM base and `RequestsTransport` disables
redirects. Existing demo 401 handling avoids retry/refresh. Preserve these.
The existing `inspect_accounts` iterates all candidates and pages positions without
the proposed total bounds; reuse validated parsing with explicit inspection
limits rather than calling this unbounded aggregate unchanged.

## Decision: Use existing operator authority; no new mutable root

`DeskService` opens an existing `RootContext`. Runtime delivery starts only for
`allow_writes` and role `web-operator`; `_admit_external_credential_delivery`
requires writes, root revalidation and current root owner. This is local authority,
not broker ownership. Keep it. The bridge service must not call deployment,
enrollment, operation/result persistence or trading factory functions.

`web\app.py` checks loopback host/client, same origin, server-owned session and
`x-csrf-token` for unsafe HTTP methods. Inspection is a POST so this boundary
continues to apply, even though its outbound broker calls are GET-only.
Recheck captured actor identity in service work. The host IPC has root/role
admission, not browser CSRF; do not pretend a browser token authenticates `op`.

## Decision: Expiry is explicit metadata, not guessed from an opaque bearer

The old demo manager learns rejection only from the broker and has no expiry
metadata. The generic lease store has no clock/expiry or generation-specific
rejection fence. Add optional purpose-specific expiry to mapping/private publish
and lease state, mandatory for this capability, forbidden for unrelated legacy
shapes. Maintain legacy frames/replies and application behavior. A generation-local
invalidation path must not use a provider-wide revoke on a late A rejection after B
was published. A 24-hour local cap does not assert 24 hours remain at the issuer.
Never decode a token as trusted configuration or expose its claims/fingerprint.

## Decision: Bound and scope transient account selection

The CLI currently accepts `--account-key` and runs before `RootContext.open`;
retain that independent host path unchanged. The new browser path accepts only an
opaque choice issued to the current actor/generation. Revalidate candidate identity
when fetching the selected book. Return typed currency/cash/UIC/amount fields,
never raw upstream JSON. A valid JSON scalar can still contain the sentinel:
projection and final token-aware redaction/fail-closed checks need adversarial tests.

## Deployment finding: Delivery success is not network/browser readiness

`docker-compose.op-runtime.yml` uses `network_mode: none`, publishes no browser
port, mounts one named volume and starts the supervisor with existing write/network
trust gates. `DockerCredentialDelivery._validate_operator_container` requires the
network-none topology, exact supervisor entrypoint, no extra mounts/capabilities
and a read-only container filesystem. Keep this existing profile and its validator
unchanged for existing consumers. `docker-compose.yml` has a loopback-published
`web-operator`, but it is on the general `webdesk` bridge and is explicitly not an
approved operator target. `docker-compose.linux.yml` uses host networking and is
Linux-only; neither is an in-app inspection deployment.

**Decision**: Plan a separate opt-in `docker-compose.saxo-inspection.yml` defining
`saxo-inspection-operator` in profile `saxo-inspection`; publish only
`127.0.0.1:8877:8876`; attach it only to its own bridge; mount only a separate,
already admitted inspection-root volume containing no fund state. Do not connect
it to `webdesk`, any fund volume, host networking, or a running container. The
operator must supply an existing approved root/volume; no root initialization,
enrollment, trust change, or migration is part of this feature.

The bridge isolates service membership, not internet destinations: ordinary Docker
bridge egress can reach arbitrary IPs absent host firewall rules. Therefore the
stated narrow SIM egress is an application-layer property only: the inspection
client hardcodes the TLS-verified SIM origin, permits only the four contract GET
paths, disables redirects/proxies/custom endpoints and requires a fresh explicit
consent per action. Never claim that Compose/Docker enforces a Saxo-domain
allowlist. If deployment policy requires network-layer domain filtering, this
design is insufficient and acceptance remains blocked until a separately verified
host egress control is supplied.

Add a capability-specific host-delivery target mode selected only by the explicit
non-secret `topology_profile=saxo-inspection` mapping field. Before any 1Password
field read it must verify the exact fresh service/profile identity, image/source/revision
pins, role/root, one dedicated volume, one expected bridge, exact loopback port
binding, read-only filesystem, dropped capabilities, no extra mounts, and no
unexpected proxy configuration. Reject host networking, non-loopback/wildcard
publishing, extra networks/ports/mounts, fund roots/volumes, unrecognized service
labels and any mismatch; keep the existing network-none checks as a separate,
unchanged path. Host delivery remains the attended `aihf-op-deliver` private-stdin
flow and targets the new running service only after this preflight. Existing actor,
origin/CSRF, root-owner, role and SIM mutation guards remain in force.

The topology is a design, not an available deployment: its Compose file, source
validator and tests do not exist yet. SB-A08 stays BLOCKED until implementation,
offline positive/negative topology tests, source/image provenance, and an
operator-run host-loopback/browser smoke pass on each claimed Docker host platform.
The smoke is read-only and manual: no order, fund action, new schedule, live
endpoint, network/container mutation, automatic delivery, or shared fund-root
write. Record provenance without a vault reference, token, account result or
secret-bearing trace.

## Governance and execution findings

- Active templates resolve to `.specify\templates\`: no custom or preset directory
  is present. Their required spec/plan/tasks headings are retained.
- `.specify\feature.json` names `specs/005-web-engine-migration`; preserve it.
  `common.ps1` supports `SPECIFY_FEATURE_DIRECTORY`, but mutating setup calls may
  persist it. No setup script was run; documents use the explicit nested path.
- `.specify\extensions.yml` registers only Git hooks here: mandatory branch
  creation before specify and optional commits before/after plan/tasks/specify.
  All branch/commit actions are forbidden by this assignment and are skipped as
  an explicit scoped workflow deviation; the registry itself is unchanged.
- Constitution has Principles I-VI, no adopted Principle VIII. No active
  red-team or plan-review hook is registered; red-team lens configuration and
  skills exist, but that is not an installed mandatory hook. This scope matches
  red-team money/currency, contracts and immutable-capture triggers. Recommend
  targeted adversarial treatment in the requested review; no findings report or
  formal red-team pass is fabricated. A caveman style review is not automatically
  proof of the formal red-team protocol.
- No new PR, commit, push or live forge check is allowed. Consequently no claim
  of new plan-review PR satisfaction is made. Parent review and finding resolution
  are preimplementation gates; source acceptance still requires Principle III.

## Unknowns / handoff

Code architecture is sufficiently identified for offline implementation.
Operational unknowns are the exact operator-supplied source reference and expiry,
eligible existing dedicated root/container identities, and successful host
delivery plus loopback/browser smoke on each claimed Docker platform, including
Windows Docker Desktop. They cannot be solved by reading real secrets or loosening
policy. The selected topology is a design only; real in-app connectivity is not
runnable on the currently admitted network-none target.
