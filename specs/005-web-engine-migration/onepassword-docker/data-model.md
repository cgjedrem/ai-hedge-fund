# Data model: conditional runtime-only credential source

Status: proposed, not implemented. Existing durable credential records remain unchanged.

| Entity | Fields / validation | Retention and ownership |
| --- | --- | --- |
| SourceMapping | schema version; provider ID; exact root identity; destination policy; restricted `op://` reference; source=`external-runtime` | Private metadata; no value, no secret hash; excluded from browser/export |
| TargetIdentity | immutable container ID; image/build identity; root identity; operator role; backend boot nonce | Checked before resolving and again at publication; new boot invalidates leases |
| Delivery | protocol version; unique delivery ID; target identity; provider; expected generation; length-bounded UTF-8 value | Private stdin/IPC only; one credential, <=16 KiB; no durable queue/log |
| RuntimeLease | opaque generation; binding to mapping/provider/destination/root/boot; value; state; active capture references | Backend memory only; never serialized; dropped at release/revoke/shutdown |
| OperationCapture | source discriminator; opaque lease generation; exact provider/destination/root/boot; operation ID | Non-secret identity may use existing operation snapshots; value stays in owning process |
| Status | configured; available/requires-auth/revoked; opaque generation; sanitized reason | Browser-safe; no references, values, fingerprints or raw subprocess messages |

The exact wire field names can be chosen during implementation; these invariants cannot.
Source discrimination is mandatory: a missing external lease must not resolve a durable
saved key or ambient environment value. Old captures cannot point to a later generation.

## State transitions

`disabled -> configured/requires-auth -> resolving -> available(generation)`

Failed/denied/partial delivery returns to requires-auth, or retains the prior valid generation
on failed refresh. It never publishes a new generation or changes prior operation captures.
Delivery authorization itself does not admit a provider operation. Lost acknowledgement after
possible publication is `delivery-outcome-unknown`, not a confirmed failure/no-change result;
value-free generation reconciliation is required before an explicit retry.

Refresh `available(A) -> available(B)` is compare-and-swap under admission. New captures use B;
already admitted captures hold A for bounded completion. A is dropped once its last capture
releases it. No durable version file containing A or B is written.

Revoke serializes with admission: mark all relevant generations revoked, reject new captures
and fence next dispatch for admitted captures; signal cancellation and release references
on quiescence. Already-sent external requests cannot be recalled.

Restart/crash destroys the available lease set: `any -> requires-auth` on the next boot.
Persisted operation identities must be reported interrupted/unavailable, not resumed with a
new value. Duplicate/replayed delivery IDs fail; wrong expected generation fails without
overwriting the active generation.

## Relationship to Spec005

Reuse its admission and frozen-capture semantics. Do not overload existing durable version
filenames or claim existing CredentialStore reads can resolve process-local values.
Cross-process credential-dependent execution is denied unless it is explicitly part of the
approved owning-backend path; free/local owned runners remain credential-free.
