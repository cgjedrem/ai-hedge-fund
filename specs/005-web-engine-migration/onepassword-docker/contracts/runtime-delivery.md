# Conditional contract: host-to-operator runtime delivery

This is a private application interface to implement, not an existing command or product
guarantee. Windows runtime feasibility remains an acceptance gate.

## Roles and channels

- Host launcher: trusted local interactive process; one allowlisted reference per request.
  Host `op` may hold user authentication; no account/token authority is forwarded.
- Host Docker client: existing user authority; local Docker context only; no secret in
  arguments/configured environment. Remote TCP/SSH contexts are rejected in the first slice.
- Container helper: short-lived stdin receiver, no TTY, no provider/vault access. It validates
  target/root eligibility and talks only to the backend's private local IPC endpoint.
- Operator backend: owns leases, canonical admission and operation dispatch. Observer, browser
  and runner never receive a delivery message or secret.

A private Unix-domain endpoint inside the operator runtime namespace is proposed; it is
not the Docker daemon socket or desktop authentication socket. Endpoint owner, filesystem
protection and peer identity must be validated. No generic HTTP/browser secret-import route
is added. If these checks cannot be established, the connection is unavailable, not downgraded.

## Request and response

One length-delimited request on stdin carries the [Delivery entity](../data-model.md).
Parse without shell expansion, trailing records, control characters, partial publication
or unbounded reads. Require at most 16 KiB of value and at most 32 KiB of total frame.
Caller closes stdin after the single frame. A second frame is a protocol error.

Bind immutable container ID, image/build identity, root identity, operator role, boot nonce,
provider/destination policy and expected generation. Check authorization before resolver
invocation and under backend admission before publishing. Revocation/refresh use the same
serialization boundary as operation admission. Secret resolution never grants write authority.

Response contains protocol version, request identity, opaque generation, status and sanitized
reason code only. Neither request nor raw resolver output is attached to errors, diagnostics,
traces, browser responses, job snapshots or exported evidence. No success-shaped fallback.
Use nonzero process failure and explicit reason for missing CLI, denied/timeout auth, unsupported
target, invalid mapping/frame, stale generation, lost stream and revoked authority.

The overall host operation has a 60-second deadline, including auth. Publication and result
acknowledgement must finish inside that deadline. Timeout after possible publication is
ambiguous: report `delivery-outcome-unknown`, query value-free generation status before any
explicit retry, and never retry automatically or claim no change.

## Capture and lifetime

Only the selected provider client inside the owning backend receives the value explicitly.
No environment-based fallback. No serialization of lease contents. No provider construction,
network validation call, fund operation or job start follows merely from secret delivery.
Actual provider work retains separate existing authorization and spending limits.

Refresh publishes a new generation for new admissions. Failed refresh preserves the prior
generation unchanged and reports failure. Revoke denies new work and fences future dispatch.
No lease survives backend/container restart, and stale operation identities never resolve to
the latest source value. Private references/status may persist without enabling recovery.

## Authentication UX

Attended draft: user enables desktop integration and Windows Hello locally; launcher receives
ordinary 1Password approval/denial. It must not bypass a prompt, install an update or obtain
an account password through the application. Missing integration produces an actionable
sanitized requires-auth state. No vault-list/read command is needed to render status.

Reject ambiguous simultaneous authentication sources; do not silently select Connect or a
service account because inherited variables happen to exist. Do not log their values.
If unattended support is later chosen, require a locally provisioned dedicated read-only
vault service account and a separate bootstrap-token handling contract. Never request a
token in chat. Current approval does not cover that mode.
