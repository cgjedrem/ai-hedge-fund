# Contract: Purpose-scoped delivery and in-app SIM inspection

**Status**: Proposed interfaces, not existing endpoint claims.
**Scope**: SB-FR-001 through SB-FR-015.

**Latest execution evidence (2026-11-09):** implementation `499fc83` is pushed to
existing PR #8; its pinned image built. A user-authorized isolated uncredentialed
no-volume readiness probe exited 2 under normal filesystem admission and host
HTTP was unreachable; it was removed. No approved pre-existing admitted
inspection volume or exact attended credential mapping is available.
T026/SB-A08 remain BLOCKED. A separate disposable Linux/ext4 fake test run
executed normally: 120 passed/9 failed (Unix socket tests hardcode read-only
`/tmp`), not IPC acceptance; all helper resources were removed. These actual
observations supersede older table statements that no Docker action or Linux
test execution occurred. See parent acceptance evidence for exact pins/results.

## Host delivery

Existing attended command, extended to the one new capability:

```powershell
poetry run aihf-op-deliver --config .\operator-local\saxo-inspection-mapping.json --provider saxo-demo-token
```

Configuration is non-secret, schema `1`, exactly one selected mapping; existing
application mapping shapes retain compatibility. The Saxo mapping requires
`provider_id=saxo-demo-token`, `destination=saxo-sim-readonly`, exact source reference,
`topology_profile=saxo-inspection`, root/container/image/revision/source/volume
pins and `expires_at`. This profile selector authorizes only the separately
validated inspection service, never arbitrary bridged targets.
All are operator supplied; placeholders are invalid until replaced locally.
Read no source field until mapping, expiry, role, root, instance and topology pass
preflight. A value goes only into the existing length-framed private stdin publish
envelope and backend lease, never command arguments or HTTP. Retain the 32 KiB frame,
16 KiB value and 60-second overall bounds, no automatic retry.

Private status remains value-free. Private publish adds `expires_at` only for the
new purpose, validated consistently by sender/envelope/receiver/store. Legacy
publish shapes and replies remain accepted; reject invalid or extra fields.
If publication acknowledgement is lost, report outcome unknown, reconcile using
value-free status only, and never silently resolve/publish a second time.

## HTTP authorization common to all routes

Use existing local loopback Host/Origin checks and server-owned operator session.
POST/DELETE additionally require same origin, loopback client and current
`x-csrf-token`; service revalidates existing root owner/admission. A browser actor
comes from the authenticated request context, never JSON.
No token input endpoint exists. Reject extra fields, including `value`, `token`,
`reference`, `url`, `endpoint`, `account_key`, `client_key`, `actor` or `root`.
All responses use `Cache-Control: no-store`; no raw errors, secret-derived IDs,
source paths or upstream bodies.

### GET /api/saxo/sim/status

No broker/network request and no source resolution. Return dedicated capability
status and action availability; do not alter `/api/settings` provider catalogs.
Observers receive only disabled/unavailable capability information, not runtime
identities, account results or mutation authority.

### POST /api/saxo/sim/accounts

Request: `{"authorize_network": true, "expected_generation": 1}`.
Boolean true is mandatory, generation a nonnegative integer subject to current
available handle equality. Require enabled network capability before client creation.
Discover validated candidates only, no balances/positions for every account.
Return `environment=SIM`, `read_only=true`, generation, `selection_required=true`
and bounded choices `{selection_id, label, currency}`.
Zero eligible or malformed/duplicate candidates fails; no partial choices.

### POST /api/saxo/sim/inspect

Request: `{"authorize_network": true, "expected_generation": 1, "selection_id": "<opaque-choice>"}`.
Require current actor/instance/generation-bound unexpired choice. Re-discover and
validate its account eligibility, then fetch only that account's balance/positions.
Return typed selected account/currency/cash/position summary with SIM/read-only/
generation markers and `fund_connected=false`, `trading_enabled=false`.
No durable result, fund or account binding is created.

### DELETE /api/credentials/runtime/saxo-demo-token?expected_generation=1

Reuse existing generation-CAS revoke behavior, with capability-aware lease
validation. No broker request. Return `{"state":"revoked","generation":2}`.
Clear associated choices/captures/publication authority. Wrong generation returns
conflict, never revokes a different current generation.

## Outgoing request contract

Fixed origin: `https://gateway.saxobank.com/sim/openapi`.
Only `GET` of `/port/v1/users/me`, `/port/v1/accounts/me`,
`/port/v1/balances`, `/port/v1/positions`.
Reject other methods/paths, non-SIM/live origins and redirects before further
dispatch. No OAuth calls, order builder, mutation, provider factory or credentials
fallback. HTTP POST above consents to an action; it is never a broker order POST.

Per action: total 30 seconds; per HTTP request `min(10, remaining)` seconds;
at most 12 requests; five pages and 500 rows per collection; at most 100 rows per
page; 1 MiB streamed body per response. Counters include validation rediscovery.
Use bounded page-size params, strictly increasing validated skip values, no
arbitrary next URL fetch; refuse duplicate/repeated/malformed paging and limit
overruns, never silently truncate success.

Recheck captured root/actor/purpose/generation-local validity/expiry immediately
before each dispatch and result publication. Rotation alone allows already pinned
A to finish inside its bounds, but revoke/expiry/rejection/authority loss fences A.
Broker 401/403 fails without retry/refresh and invalidates A only.

The result-publication boundary is a local commit of the fully constructed and
reflection-checked projection, before return to FastAPI. The coordinator lock
serializes actor cancellation with that commit; while holding it, recheck local
authority, then acquire the lease-store lock and validate the captured lease
before committing. The lease-store lock serializes validation/commit with
generation-CAS revoke, invalidation and close. Lock order is coordinator then
store, matching admission; revoke releases the store lock before clearing actor
state. No broker I/O, result construction or reflection traversal occurs under
these publication locks. The store callback only marks the action published and
hands off the prepared projection; it performs no I/O or further lock acquisition.

If revoke/cancel wins before this commit, return an error with no choices or
financial summary. Once the commit wins, cancel reports no active action and
subsequent revoke cannot recall the committed result, even if HTTP serialization
or transmission has not completed yet. This is not an atomic socket-send gate;
already returned/sent data cannot be recalled. Root/owner/storage/network
authority is rechecked at the local boundary, not locked against arbitrary
external authority changes through response delivery.

## Safe errors

Fixed application reasons: `capability-disabled`, `requires-auth`, `expired`,
`revoked`, `stale-generation`, `stale-selection`, `consent-required`,
`network-disabled`, `capability-denied`, `inspection-busy`, `inspection-timeout`,
`inspection-limit`, `invalid-broker-response`, `sim-request-failed`,
`deployment-unavailable`. Use the existing sanitized error envelope and appropriate
400/403/409/422/503/504 status; never derive public messages from upstream text.
Map new local errors separately from the legacy private IPC reason allowlist.

## Offline contract coverage

| Acceptance | Requirements | Required fake evidence | Current evidence/status |
|---|---|---|---|
| SB-A01 | 001-004 | Allowed purpose; wrong source/provider/destination/root/instance/role/expiry denied before resolver; recheck denial before publication | **OFFLINE PASS / PLATFORM PARTIAL** — refreshed after the publication-race fix: 306 passing governed bridge tests in 54.55s, including runtime frame/purpose/expiry and host-topology fakes. Nine existing Unix-socket tests skip on Windows; no real delivery or Linux/container smoke is claimed. |
| SB-A02 | 003,012,014 | Sentinel absent from frames' repr/status, stdout/stderr/errors/logs/browser requests/responses/storage and durable/image/configured env/argv surfaces | **PARTIAL** — frame/status/repr, fixed HTTP rejection errors, typed summaries, empty browser storage and root file-byte equality pass. No real host stdout/container/image scan was authorized or performed; source evidence does not substitute for that acceptance. |
| SB-A03 | 004-008 | Consent/CSRF/session/owner/network checks before transport; explicit scoped selection; strict SIM GET paths, no redirects | **OFFLINE PASS** — `test_http_denies_before_any_broker_dispatch` exercises 12 denials through real middleware/service/root admission. `test_http_discovery_explicit_selection_and_typed_inspection_are_disk_quiet` and `test_http_selection_is_session_bound_and_revoke_uses_generation_cas` cover explicit selection and scope; broker tests cover SIM GET/live/order/redirect/proxy fences. |
| SB-A04 | 007-008 | Duplicate/malformed/ambiguous data and malicious pagination; bounded elapsed/requests/pages/rows/body, no partial success | **OFFLINE PASS** — `test_http_collection_bounds_never_publish_partial_choices` covers page/total-row/per-page limits; `test_http_request_resource_and_clock_limits_return_no_partial_data` covers requests/body/elapsed/expiry. HTTP malformed/duplicate and broker malicious-pagination cases pass. Bounds are lowered in relevant tests to exercise the exact production limit branches without oversized fixtures. |
| SB-A05 | 009-011 | Rotate A/B, revoke during action, local expiry, 401/403, late A rejection, restart/close, stale handle/choice and release on every exit | **OFFLINE PASS / QA RECHECK PENDING** — the earlier final-GET test did not cover post-validation construction/redaction. Fourteen new HTTP cases block reflection checking of a prepared result, then complete revoke/cancel/owner/root/permission/expiry/invalidation before resuming; all failed with HTTP 200 before the fix and now return no result. Runtime lock-contention and HTTP cancel-contention tests distinguish a serialized commit from an unchecked extra validation. Publication-wins HTTP tests document the pre-transport boundary. Fresh bridge selection: 306 passed/9 skipped in 54.55s; adjacent HTTP/authority selection: 136 passed/1 skipped in 107.78s. Existing pinned A/B rotation, late A rejection preserving B, CAS, release and restart tests pass. Unix-socket skips remain explicit under SB-A01. |
| SB-A06 | 001,013 | Saxo absent from provider catalogs; rejected as model/data input; zero order/fund/cache/approval/runner calls and shared-state writes | **OFFLINE PASS** — `test_http_inspection_capability_cannot_become_model_data_or_durable_credential` verifies actual catalogs and rejected writes. Disk-quiet inspection compares every synthetic-root file byte; forbidden fund/application-data factories and GET-only transport assertions fence effects. No shared root or real fund was accessed. |
| SB-A07 | 005,012 | UI explicit action only; no token field/polling/persistence; reset on failure/revoke/reconnect/generation change | **OFFLINE PASS / REVIEW PENDING** — nine `settings-saxo.test.tsx` cases cover per-action consent, typed summary, revoke/storage clearing and late accounts/inspect completions after cancel/revoke/reconnect. A real late-summary bug failed first and was fixed with an action epoch; authority/status identity and unmount also invalidate that epoch. Final complete frontend run: 232 passed/14 files. No polling, token form or persistence was added; final QA still pending. |
| SB-A08 | 015 | Network-none baseline unchanged; fresh inspection-only service is source-pinned, uses a dedicated root with no fund state, exact host-loopback port and isolated bridge; app permits only consented SIM GETs, with no claim that the bridge filters domains; host checks reject all other topology; platform smoke provenance recorded or status remains BLOCKED | **BLOCKED** — fake Compose/host checks and separate profile source exist; no Docker command, host/browser smoke, operator-supplied field reference or deployment provenance was provided. |

These are source-bound offline results, not an end-to-end pass. Record exact test
IDs, revision/worktree, platform/time, fake fixture provenance and commands in
the parent `acceptance-evidence.md`; T022 full Python suite and T023 parent review
remain pending. Focused Python, full frontend tests/build and changed-file style
now pass in the recovered existing Poetry Python 3.11.15 environment.
