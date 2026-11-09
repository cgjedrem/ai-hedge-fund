# Data Model: In-app SIM inspection bridge

All new runtime entities are memory-only. Existing durable credential/fund schemas
and application provider catalogs remain unchanged.

## Capability

`id = saxo-demo-token`, `destination = saxo-sim-readonly`, disabled by default.
Valid only for private delivery and the inspection service, never provider dispatch.

## Source mapping (non-secret, operator-local)

Legacy mapping fields: `provider_id`, `reference`, `destination`, `root_id`,
`container_id`, `image_id`, `revision`, `source_sha256`, `volume_name`.
New mandatory field for this capability: `expires_at` (UTC absolute timestamp).
New mandatory target selector: `topology_profile=saxo-inspection`; do not change
legacy application mapping shapes or accept an arbitrary profile.
Existing schema-1 application mappings remain accepted without expiry.
Strictly reject unknown/duplicate fields, OAuth/live destinations, ambiguous
authentication, unresolved placeholders, missing/elapsed/more-than-24-hour expiry,
and mismatched pins before resolution. Reference is never included in status/repr.

## Runtime lease

Existing handle: root ID, instance ID, provider ID, generation and destination;
value stored only in private lease state with suppressed repr. Add expiry and
generation-local rejection/expiry fence for the inspection purpose.
Expiry is metadata for a conservative local cutoff, not a claim about issuer TTL.

Transitions:

```text
disabled -> requires-auth              explicit capability configuration
requires-auth/revoked/expired -> available(g+1)   attended valid publication
available(A) -> available(B)            deliberate rotation; A may be pinned
available(A) -> requires-auth           rejected A; invalidate A only
available(A) -> expired                 local cutoff; fence captures
any enabled state -> revoked            explicit generation-CAS revoke
any state -> closed                     backend shutdown; no resurrection
new backend -> requires-auth            new instance, no inherited value/choice
```

Pin and release atomically. Check closed/revoked/invalid/expired state at every
dispatch and publication boundary; do not equate "still pinned" with "still valid".
A late A rejection or release cannot revoke/delete B. Public state is a projection,
not a new serialized fund setting.

## Account choice

Opaque random `selection_id`; private validated account key/client identity;
actor session ID; root/instance/generation/purpose; created/deadline timestamps.
Five-minute maximum TTL, additionally bounded by credential expiry. Choices
are cleared on actor/session loss, refresh/revoke/restart and generation change.
No browser-supplied account key/client key/URL enters dispatch. Discovery detects
duplicate account IDs across all pages before emitting any choices.

## Action capture

Actor, root/instance, exact handle, network consent, monotonic deadline, current
page/request/row counts, cancellation flag; no durable operation ID or record.
One active per actor, at most eight active service-wide; reject contention.
Every completion/failure/cancellation releases the pinned lease.

## Public status / summary

Status: capability enabled, purpose, environment `SIM`, state, opaque generation,
non-secret expiry, network readiness, fixed reason code and action availability.
No source reference, bearer, fingerprint, upstream auth JSON or account data in
availability responses.

Discovery: generation and a finite list of `selection_id`, display label, currency;
`selection_required = true`, including a one-candidate list.
Inspection: selected display identity, currency, finite cash balance and finite
positions `{uic: positive integer, amount: finite number}`, generation and SIM/read-only
markers. No fund ID, persisted binding, trading readiness or raw response body.
Apply final credential-reflection rejection even to syntactically valid text fields.
