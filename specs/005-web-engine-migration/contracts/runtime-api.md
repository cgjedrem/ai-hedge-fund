# Runtime API contract

**Proposed interface, not shipped.** Names below are the design target; existing routes
may be retained/aliased only with the same policy. Implement against the
[forward contract](../../../docs/governance/web-migration-contract.md) and [data model](../data-model.md).
All endpoints are local, with fixed-root/path/Host/Origin/CSRF guards. No browser payload
chooses a root, process PID, capability or arbitrary file path.

## Common observation and mutation envelopes

GET is observational: no network/provider construction, worker starts or root-side writes.
Return subject identity, source/head/revision, captured/effective config provenance, server
read-only/writable mode and explicit offline/recorded/live/error status. Sensitive material
and ownership nonce never leave private storage. Container observer denies all mutations
before touching a writable resource, including previews that would persist tokens.

Preview is POST `/api/operations/preview` with `action`, `subject_id`, expected
revision/head when applicable and validated action inputs. It returns `preview_id`,
`preview_digest`, `expires_at`, exact due-set/range, frozen non-secret capture, warnings,
scope/consequences, call/cost estimate, enforceable requested caps and a single-use confirmation.
Accept POST `/api/operations` with `request_id`, action/subject, preview ID/digest/token
and exact reviewed payload. Payload has no secret credentials, root/capability elevation
or arbitrary process arguments. Confirmation/session identity is checked under admission.
No endpoint sends a stale request to a new head/due-set.

Success: HTTP 202 with durable `operation_id`, `request_id`, `status`, `status_url`,
subject/capture identity and redacted progress. A repeated identical admitted ID returns
its existing response/status, not another job; changed payload with same ID conflicts.
No-work manual completion is explicit completed/nothing-due, not a fabricated session.
GET `/api/operations/{id}` and bounded GET `/api/operations` recover progress/results after
browser reload/server restart; unfinished jobs become interrupted, never automatically resumed.
POST `/api/operations/{id}/cancel` uses its own idempotent request identity and safe-boundary
status; it cannot erase already-issued effects.

Validation/mutation error body: `code`, safe `message`, subject/request identity when known,
current safe head/revision where permitted, `refresh_required`, `retry_policy`.
Never include credentials, unsafe paths or raw provider errors.

| HTTP / code | Meaning / effect boundary |
| --- | --- |
| 400 invalid-request | Unknown field/provider/model/parameter, unsupported endpoint scheme or bad range; zero provider/worker calls. |
| 403 capability-denied / protected-root / read-only / broker-not-web-supported | Root/capability/SIM/observer boundary denial before side effects. |
| 409 stale-preview / request-conflict / writer-conflict / ownership-unknown | Re-review or explicit ownership recovery; never queue manual behind active runner or retarget stale preview. |
| 423 halted / replay-corrupt / reconciliation-required | Execution denied; safe Halt remains available, ambiguous Resume denied. |
| 422 readiness-denied / unsupported-filesystem / private-storage-unverified | Invalid configuration/ACL/primitive/cost bound; no providers constructed. |
| 410 expired-confirmation | Issue a new preview, never replay token. |
| 429 capacity-denied / budget-exhausted | Bounded capacity or authorization limits reached; stop before next call/session. |
| 503 observation-conflict / assets-unavailable | Retry read only, or actionable installation failure; no fallback/TUI/mutation. |

Implementation notes (2026-11-02 error-recovery slice and 2026-11-03 capacity slice, source-tested;
429 `budget-exhausted` still unproven):

- Optional `subject_id`, `request_id` and `current_head` are echoed only when they match bounded
  opaque-token patterns; anything else is dropped, never repaired or echoed.
- `retry_policy` defaults per code. `writer-conflict` defaults to `inspect-status`; only a
  registry-lock `OperationBusy` before acceptance opts into `retry-later`. A busy status read after
  a durable transition returns the accepted record; a busy replay of a known request requires
  status inspection. Permanent faults (`none`, `inspect-status`, `review-again`) are never retried
  automatically, and mutations are never auto-resubmitted by the client.
- A mutation rejected because the operator session is absent or expired (for example after a
  server restart) returns 403 with `retry_policy=reload`; the client renews via a read-only
  capabilities reload and asks the operator to submit again.
- An unavailable operation store is 503 `observation-conflict` / `retry-read-only`, not 404, so a
  remembered operation is not offered for forgetting.
- The partial implementation also supports read-only GET
  `/api/operations/by-request/{request_id}` to recover a lost admission response. It verifies
  durable request, operation and capture linkage; 404 leaves the outcome unknown rather than
  proving no effects. The browser retains only non-secret request/operation identities, keeps
  recovered identities independently, and does not resubmit on reload or reconnect. It observes
  at most 16 saved identities per surface at once; active, unavailable, mismatched and unobserved
  identities block a new admission until terminal status is verified or the operator explicitly
  removes the monitor. Removing a monitor does not cancel the operation or establish its outcome.
  A structured 410 `expired-confirmation` from this single admission attempt is a pre-admission
  denial; malformed or ambiguous responses remain subject to status inspection.
- Observation is polling only (no stream/channel). The client tracks a connection epoch: a
  response to a request sent before a connection loss does not report recovery; Reconnect issues a
  fresh capabilities read bounded to 10 s.
- Operation capacity (2026-11-03 slice, source-tested): backtest acceptance (pool capacity 1) and
  paper tick / runner start (shared pool capacity 2) reserve an in-process worker slot before
  acceptance, then `OperationStore.accept_request` counts the root's unfinished records for the
  pool's actions under the registry lock, after the replay/preview/expiry/stale checks and before
  any record is created. Either bound failing returns 429 `capacity-denied` / `retry-later`
  with `Retry-After: 30` and `retry_after_seconds: 30`, plus an echo of the subject and request.
  It writes nothing durable: the preview stays issued, the confirmation token is not consumed, and
  no worker starts. A replay of an already accepted request returns its record even at capacity.
  Scope: slots are per process; the durable count bounds every process sharing the root. An
  unfinished record orphaned by a crashed process holds capacity until a server start runs
  recovery (fail-closed). A record this process failed to settle is re-interrupted at the next
  admission. `Retry-After` is advisory, never a promise of success. The schema accepts it only on
  429/503 for `capacity-denied`, `budget-exhausted`, `observation-conflict` or
  `assets-unavailable`, as an integer from 1 to 300 seconds. The client ignores out-of-bound hints
  and releases a pending identity only for an echoed same-request `capacity-denied` (or 410
  `expired-confirmation`).
- Gap: no production site emits 429 `budget-exhausted` yet. Lifecycle, halt and verdict writes
  have no capacity pool.

## Resource and action matrix

| Resource / observation | Reviewed action / payload | Required guards and result |
| --- | --- | --- |
| GET `/api/capabilities`, `/api/configuration` | Save non-secret configuration version | Expected settings version; validate without calls, disclose overrides/restart-needed. Root/capabilities unchanged. |
| GET `/api/models`, `/api/providers` | Select approved provider/model/endpoint/context/timeout | Free default, host-bound endpoint policy, cloud class explicit; selection grants no calls. |
| GET `/api/credentials/status` | POST `/api/credentials/{provider}` set/delete | Write-only material on dedicated guarded endpoint; private atomic surgical version update, redacted status, active-capture warning. Never put key in generic operation payload. |
| GET `/api/templates`, `/api/templates/{id}` | Create/edit/clone/rename with complete validated mandate JSON | Expected revision, canonical YAML/YML/case/protected identity; custom roster explicit; no deployment snapshot rewrite. |
| GET `/api/deployments`, `/api/deployments/{id}` | Deploy template revision + universe; archive/restore/replace exact scope/head | Local paper only, collision/account/name registry, stopped/quiescent, durable archive journal, distinct replacement link. |
| GET `/api/deployments/{id}/runner` | Start with frozen capture + initial due-set + finite authorization; Stop verified owner | Local paper, all-writer admission/handshake; no auto-start; stop is requested until quiescent. |
| GET `/api/deployments/{id}/schedule` | Manual tick/backfill exact head/due-set; redo latest local-paper session | Runner active/unknown denies manual; cadence canonical, bounded backlog, no silent re-date or duplicate fills. |
| GET `/api/deployments/{id}/controls` | Halt/Resume | Identity-safe emergency Halt lane under corrupt controls; Resume requires replay plus reconciliation where ambiguous, never starts. |
| GET `/api/deployments/{id}/decisions` | Approve/reject decision timestamp + source hash | Canonical replacement/consumed semantics; active-runner execution warning; approval and Run separate. |
| GET `/api/deployments/{id}/valuation` | Explicit valuation refresh with provider/network/cost authorization | Estimated source/time/coverage and signed precision; incomplete NAV not complete; recorded data unchanged. |
| GET `/api/research` cursor/filter, `/api/research/{id}` | Backtest reviewed dates/universe/template/provider/capture and caps; archive selected result | Canonical backtest, bounded progress/cancel, stable reopened results, malformed entries visible, active refs checked. |
| GET `/api/reports/{id}`, `/api/reports/{id}/download` | No execution action | Complete canonical proposed/executed/risk/cost/scorecard values; inert text, exact precision, no secrets. |
| GET redacted SIM readiness/records | No SIM web mutation | Headless provisioning/account-control exemption explicit; no advertised web execution/lifecycle parity. |

Credential set/delete uses expected version and single-use preview tied to provider/action,
but secret material is supplied only to the dedicated private handler; digest binds non-secret
action/provider/version, not an exposed hash of the key. Safe response never persists a key
in browser storage, generic sidecars or exported provenance.

## Runner, approvals and interruption

Start readiness must acknowledge owned process incarnation/root/capture before displaying
running. Runner reservation blocks manual regardless of current session activity. A bounded
backtest has independent capacity, never occupies a global runner lock. Halt/verdict uses
short responsive lane; stop/cancel communicates actual safe-boundary semantics.

Monitoring may use bounded polling or guarded server events; event reconnect is read-only,
redacted and identity/cursor-bound, never enables providers. Late responses cannot overwrite
newer operation/head state. Browser closure leaves runner unchanged. Server restart observes
verified live owner or unknown; bounded jobs interrupted, fenced and never auto-resumed.

## Acceptance obligations

### Bounded implemented session-report adapter

The existing paper-resource spelling is retained for this partial read-only slice:

- GET `/api/paper/{name}/sessions/{session}` projects the verified session record.
  `proposed.clamps`, `proposed.risk` and `proposed.risk_scale_factor` come directly from
  its stored decision and mandate. Requested pre-risk and final post-risk weights remain
  distinct; executed clamps and limits come from the separate stored execution record.
- GET `/api/paper/{name}/sessions/{session}/download?expected_hash={displayed_record_hash}`
  returns the complete canonical `SessionRecord` JSON, not the display projection.
  The server serializes the exact record captured by full ledger replay using the existing
  canonical serializer. The browser follows a native link and performs no numeric
  parse/stringify or authoritative-record round trip.
- A changed record hash returns 409 `stale-preview` and requires reopening the report;
  malformed/missing hashes return 400 `invalid-request`, and corrupt replay returns
  423 `replay-corrupt`. Only successful downloads receive an attachment header.
  Existing root/Host/Origin/security-header guards remain unchanged.

`node .\e2e\run-owned.mjs --reports reports.spec.ts` from `frontend` builds production
assets, preseeds deterministic clamped records before starting a read-only server, rejects
combining report acceptance with lifecycle writes, and verifies the entire fixture tree
is unchanged after browser reads. It refuses an occupied 8876 port and removes only its
owned fixture after the server releases the port.

This does not complete the general report resource row, FR-050/051, research scorecards,
book/tape drilldowns, headless export acceptance, or any Spec005 story.

Contract tests must assert denial yields zero downstream path/provider/process/fill/append
effects with fakes below production guards, not by mocking the route itself. Verify cross-
process duplicate CLI/web/runner/lifecycle races and legacy ownership-unknown; lost responses/
duplicate IDs; token expiry/due-set mismatch; secret set/delete/frozen capture; corrupted
controls/replay/post-fill reconciliation; signed partial valuation; bounded paid-policy denial
with fake providers only. Actual Windows/Linux process/ACL/runtime evidence remains mandatory.
