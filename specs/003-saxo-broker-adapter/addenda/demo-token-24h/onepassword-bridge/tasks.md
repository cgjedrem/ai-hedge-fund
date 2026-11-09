# Tasks: In-app Saxo SIM inspection bridge

**Input**: This directory's `spec.md`, `plan.md`, `research.md`, `data-model.md`,
`contracts\inspection.md`, `quickstart.md`.
**Prerequisites**: Parent caveman review with findings resolved before source edits;
no branch/commit/push/PR/active-feature mutation. Tests explicitly required.
**Organization**: Setup, foundations, independently testable user stories, acceptance.
**Status**: Final parent code review PASS (including the publication race fix);
governed focused Python tests, full frontend tests/build and changed-file style
validation pass. T022 remains partial: full Python suite NOT RUN; Linux IPC/HTTP
verification is blocked by normal root admission rejecting helper tmpfs.
T023 source review is complete; T026 host acceptance is blocked
on operator-local inputs and is not authorized by this source-only phase.

## Format: `[ID] [P?] [Story] Description`

Paths are repository-relative. `[P]` indicates non-overlapping independent files
after stated prerequisites; execute sequentially unless parent expressly chooses
otherwise. Do not spawn a swarm. Report completion/evidence after each task.

## Phase 1: Setup (Shared Infrastructure)

- [x] T001 Record the requested caveman review and disposition every comment against `specs\003-saxo-broker-adapter\addenda\demo-token-24h\onepassword-bridge\spec.md`, `plan.md`, `tasks.md` and `contracts\inspection.md`; report actual governance gates without fabricating a formal red-team/PR pass.
- [x] T002 Record the evidence-backed deployment finding and selected implementable topology in `research.md`: keep `op-runtime` network-none and unchanged; add a separate `saxo-inspection` service with sole private bridge, `127.0.0.1:8877:8876`, separate already-admitted no-fund-state root/volume, and application-only exact TLS SIM GET allowlist (never claim Docker bridge domain filtering). Record pre-resolution host checks, rejection cases, route/UI, platform smoke and provenance acceptance. Do not mutate a running container. SB-A08 remains blocked until T024-T026 pass.

## Phase 2: Foundational (Blocking Prerequisites)

- [X] T003 Add failing synthetic coverage in `hedge_fund\runtime\test_external_credentials.py` for separate capability/destination composition, explicit expiry, application-registry exclusion, invalid metadata and wrong-purpose capture; use injected clocks and no real configuration. Red/green: `python -m pytest hedge_fund\runtime\test_external_credentials.py hedge_fund\runtime\test_credential_delivery.py -q --tb=short -p no:cacheprovider --confcutdir=hedge_fund\runtime --basetemp=.\.pytest-saxo-foundations` -> 49 passed, 9 skipped after the capability implementation.
- [X] T004 Implement the dedicated capability table/parser and purpose-aware lease admission/expiry in `hedge_fund\runtime\external_credentials.py` while leaving `APPLICATION_PROVIDER_IDS` and `runtime_provider_destinations` application-only; make T003 pass without broadening model/data consumers.

**Checkpoint**: Purpose separation is proven offline before transport/UI work.

## Phase 3: User Story 1 - Deliver a purpose-scoped inspection credential (Priority: P1)

**Goal**: Attended host delivery publishes only to the authorized in-memory purpose.
**Independent Test**: Fake delivery success plus zero-resolver wrong-target/expiry/
provider cases; status contains no value/reference and triggers zero network.

### Tests for User Story 1

- [x] T005 [P] [US1] Extend `hedge_fund\secrets\test_docker_delivery.py` with failing allowed-capability delivery, exact destination/pins/expiry, before-resolution denial, post-resolution authority loss, ambiguous auth and lost-ack cases; replace only obsolete blanket `saxo-demo-token` denial expectations while retaining generic Saxo/OAuth/wrong-purpose denial tests. Offline delivery/topology regressions passed in the focused 230-test combined run.
- [X] T006 [P] [US1] Create `hedge_fund\runtime\test_credential_delivery.py` with failing bounded expiry-envelope/lease publication and legacy-frame compatibility cases, duplicate/unknown fields, unauthorized publication and sentinel-free repr/replies; reuse existing fake protocol patterns from `hedge_fund\runtime\test_external_credentials.py`.

### Implementation for User Story 1

- [x] T007 [US1] Extend strict mapping validation and host capability selection in `hedge_fund\secrets\docker_delivery.py`; validate non-secret expiry and exact destination before resolving, retain the private stdin path, target checks, safe errors and 60-second bound. Offline delivery/topology regressions passed in the focused 230-test combined run.
- [x] T008 [US1] Extend purpose-specific publish metadata in `hedge_fund\runtime\credential_delivery.py` compatibly, enforcing the same expiry/value/frame bounds and existing backend admission before publication. Legacy-frame and bounded capability-envelope cases passed in the focused 230-test combined run.
- [x] T009 [US1] Compose the capability allowlist/store in `hedge_fund\web\services.py` using an explicit empty-by-default capability setting; expose dedicated status without app-provider catalog changes and preserve existing root-owner/role startup checks. Source wiring is implemented; dedicated status tests cover observer redaction and state projection.

**Checkpoint**: Delivery tests pass; no claim of connectivity or Docker platform acceptance.

## Phase 4: User Story 2 - Explicitly inspect a SIM account (Priority: P1)

**Goal**: Explicit, scoped, bounded in-app discovery and selected-account summary.
**Independent Test**: Fake service/browser discovery -> choice -> inspection flow;
no raw account injection, orders, provider use or state writes.

### Tests for User Story 2

- [x] T010 [P] [US2] Add lease-backed-manager GET/path/SIM/redirect/no-refresh and bounded paging/body/clock cases in `hedge_fund\brokers\test_saxo_tokens.py`, `hedge_fund\brokers\test_saxo_client.py` and `hedge_fund\brokers\test_factory.py`; explicitly exercise the `isinstance(DemoTokenManager)` fence. Covered in the final 285-pass governed bridge selection, including subtype/order/live-path and factory regressions. Additions verify an existing implementation; no retrospective red-first claim.
- [x] T011 [P] [US2] Create `hedge_fund\web\test_saxo_inspection.py` covering session/origin/CSRF/owner/network/consent denial before transport, actor/generation-scoped choice, ambiguity/malformed responses, body/page/row/request/elapsed bounds, busy/cancel behavior, redaction and zero fund/order/shared-state effects. All 48 tests pass; real middleware/routes/services use enrolled marked roots and fake upstream transport only. Full root file-byte equality and forbidden application data/fund factories guard effects.
- [x] T012 [P] [US2] Add separate-card/action/reset tests in `frontend\src\pages\settings-saxo.test.tsx`; assert no Saxo model/data option, token/reference/endpoint input, polling, secret HTTP, browser persistence or optimistic trading-readiness message. Nine focused UI tests pass, including per-action consent, typed results, revoke clearing and late cancel/revoke/reconnect completion suppression. A late-summary regression failed first and was fixed.

### Implementation for User Story 2

- [x] T013 [US2] Add the lease-backed demo manager and bounded inspection path in `hedge_fund\brokers\saxo.py` plus dedicated runtime inspection builder in `hedge_fund\brokers\factory.py`; preserve host CLI behavior and all OAuth/trading ownership gates, no synthetic reference or client token cache. Broker and factory tests pass in the recovered existing Poetry Python 3.11.15 environment.
- [x] T014 [US2] Implement transient actor-scoped discovery/inspection orchestration in `hedge_fund\web\saxo_inspection.py` with exact purpose/handle pins, revalidation, explicit choice, finite resource limits, typed allowlisted projection and safe final token-reflection checks; release on all exit paths. Focused broker/web-coordinator tests passed (99 passed).
- [x] T015 [US2] Add strict request/response types in `hedge_fund\web\schemas.py`, authenticated routes in `hedge_fund\web\app.py` and capability/service wiring in `hedge_fund\web\services.py` per `contracts\inspection.md`; no durable jobs/root initialization and no generic provider exposure. Real FastAPI session/origin/CSRF/owner/root/permission integration now passes with no admission bypass.
- [x] T016 [US2] Implement a separate inspection card in `frontend\src\pages\settings.tsx` and typed capability/results in `frontend\src\lib\types.ts` using existing `frontend\src\lib\api.ts` authenticated helpers; explicit actions only, clear transient results on identity/generation/reconnect/failure/revoke. Focused UI tests passed and the production TypeScript/Vite build succeeded.

**Checkpoint**: Discovery/inspection flow passes fake service/UI tests independently;
real Docker action remains blocked until the dedicated topology and acceptance
tasks T024-T026 are complete.

## Phase 5: User Story 3 - Lose access safely (Priority: P2)

**Goal**: Revoke/expiry/rejection/restart cannot retain or accidentally transfer access.
**Independent Test**: Controlled A/B races, injected clock and backend recreation.

### Tests for User Story 3

- [x] T017 [P] [US3] Extend `hedge_fund\runtime\test_external_credentials.py` with A/B rotation, late A rejection, CAS revoke, expiry mid-action, close/restart, stale pins and capture-count release tests. Final governed selection passes, including two-capture retention until the final release, stale revoke preserving the active generation and fresh-boot requires-auth.
- [x] T018 [P] [US3] Extend `hedge_fund\web\test_saxo_inspection.py` and `frontend\src\pages\settings-saxo.test.tsx` with revoke/authority-loss while GET in flight, publication fencing, 401/403 without fallback, stale actor/selection after restart and no retained summary tests. Real HTTP final-GET revoke, root/permission/owner loss, session/selection restart and late A rejection pass; nine frontend tests include cancel/revoke/reconnect late-result fencing. Final-QA follow-up added 14 discriminating post-redaction loss cases (all failed before the fix), cancellation-lock contention and two publication-wins/pre-HTTP-handoff cases. All pass in the refreshed 306-test bridge selection; publication means local commit, not socket transmission.

### Implementation for User Story 3

- [x] T019 [US3] Add generation-local rejection/expiry invalidation in `hedge_fund\runtime\external_credentials.py` and integrate `hedge_fund\brokers\saxo.py` so late A failure never revokes B, while revoked/expired A cannot dispatch or publish. Runtime generation-race/expiry tests and broker 401/403 no-fallback tests passed in focused offline runs.
- [x] T020 [US3] Extend existing generation-CAS revoke and shutdown in `hedge_fund\web\services.py`, transient cancellation/choice cleanup in `hedge_fund\web\saxo_inspection.py` and UI lifecycle cleanup in `frontend\src\pages\settings.tsx`; keep restart requires-auth and no automatic redelivery. Real HTTP lifecycle integration passes. Fixed late frontend result resurrection with an action epoch and enabled revoke during in-flight reads; stale finalizers cannot mutate a newer action. Final-QA follow-up serializes the prepared-result commit under coordinator then lease-store locks, sharing revoke/invalidation/close and actor-cancel boundaries. Broker I/O and projection/redaction remain outside these locks. Runtime contention plus revoke/invalidate/close-before-commit tests pass; no provider-wide rejection or generation-CAS semantics changed.

**Checkpoint**: All lifecycle cases pass; no resurrection or latest-value substitution.

## Phase 6: Polish & Cross-Cutting Concerns

- [x] T021 Reconcile parent/addendum/1Password documentation and runbook claims in `specs\003-saxo-broker-adapter\addenda\demo-token-24h\acceptance-evidence.md` and `onepassword-bridge\quickstart.md`; retain historical evidence, label new bridge evidence separately, preserve fund/order and unresolved deployment blockers. Historical evidence is retained; the new bridge status, actual focused results, source fingerprint and T026/SB-A08 blockers are recorded separately.
- [ ] T022 **PARTIAL** — recovered the existing Poetry Python 3.11.15 environment; no restore or manifest change needed. Fresh final-QA publication fix validation: 306 passed/9 Windows-only skips (54.55s); adjacent suites: 136 passed/1 skip (107.78s). All four Python files changed by this follow-up pass Black/isort/Flake8 with 420-column convention and no ignored codes. Earlier frontend: 232 passed/14 files (45.20s), TypeScript/Vite build passed (32.25s), all 16 then-changed/new Python files passed style; frontend was not modified or rerun in this follow-up. Full Python suite **NOT RUN**. Linux verification attempted 2026-11-09: existing image lacked pytest; offline installed-source pytest 9.1.1 bootstrap succeeded without installs/network, but normal conftest admission rejected isolated tmpfs (`UnsupportedFilesystemError: root requires local NTFS or ext4`). Exit 4 before collection, zero tests executed, 0.92s. No admission bypass or source change; Linux IPC remains **BLOCKED**, not failed or passed. Helper/archive cleanup verified; see parent acceptance evidence.
- [x] T023 **FINAL CODE REVIEW PASS** — parent final QA passed on the publication race fix, as confirmed by the parent/user. SB-A01--SB-A08 rows and parent acceptance evidence cite governed tests, exact environment/revision/source hashes and honest host/Linux/full-suite limitations. This is code/static/focused review acceptance only, not full-suite, Linux IPC or real host acceptance. No commit/push/PR or real-secret/network operation.
- [x] T024 [US2] Add failing offline Compose/host-target tests proving the existing `op-runtime` network-none profile remains accepted unchanged and the new inspection mode rejects arbitrary/host networks, shared or extra volumes, non-loopback/wildcard/extra ports, extra attachments, wrong service/role/root, source/image drift, unexpected proxy configuration and authority loss before secret resolution. Fake-only topology tests passed.
- [x] T025 [US2] Implement only the dedicated `docker-compose.saxo-inspection.yml` service/profile, isolated bridge, loopback-only browser publish, distinct inspection volume/root target and exact capability-specific host-delivery topology mode; validate all pins and permissions before resolver invocation. Preserve the current network-none profile/validator and do not change or connect a running container. SIM-only egress remains enforced at the application client (fixed TLS origin/path/method, redirects/proxies/custom endpoints denied), not by claiming Docker's bridge filters domains. Compose/host checks passed offline; no Docker command or container change was run.
- [ ] T026 [US2] **BLOCKED** — operator has not supplied approved local field reference/expiry and no host/browser/SIM smoke was authorized. Do not infer values or attempt this task.

## Dependencies & Execution Order

### Phase Dependencies

- T001 is a prerequisite for every source/test edit. T002 records the selected
  topology design and acceptance boundary; real Docker remains blocked pending
  T024-T026.
- T003 -> T004. Both are prerequisites for T005/T006.
- T005 -> T007; T006 -> T008. T007/T008/T004 -> T009. US1 completes at T009.
- T009 -> T010/T011/T012; tests must fail for their intended missing behavior.
- T010 -> T013; T011/T013 -> T014; T014/T009 -> T015.
  T012/T015 -> T016. US2 completes at T016.
- T016 -> T017/T018; T017 -> T019; T018/T019 -> T020.
  Lifecycle correctness is mandatory before any release, including a US1-only MVP.
- T020 -> T021 -> T024 -> T025 -> T022 -> T026. T023 records completed
  source review separately and does not complete or bypass T022/T026. T026 is a manual,
  operator-local acceptance only after explicit local inputs; this documentation
  phase authorizes no real credential resolution, network call or container action.

### User Story Dependencies

US1 builds on purpose-safe foundations; US2 uses US1 delivered leases; US3 hardens
their shared lifecycle. Each story has independent fake acceptance checks, but
US3 protections cannot be omitted from a usable bridge.

### Within Each User Story

Write tests first, observe the intended failure, implement, re-run the smallest
relevant combined selection, record evidence, then proceed. Never weaken a guard
or remove failing tests merely to complete a task.

### Parallel Opportunities

T005/T006, T010/T011/T012 and T017/T018 edit independent files within their own
phase. Shared `services.py`/`saxo.py`/settings edits are sequential.

## Parallel Example: User Story 2

```text
T010: fake broker read-only/bounds regressions
T011: fake service/HTTP authorization and no-effects regressions
T012: separate settings-card consumer regressions
```

These are optional scheduling opportunities, not authorization for nested agents.

## Implementation Strategy

### MVP First

Review -> purpose/lifetime foundations -> fake host delivery/status. Stop and
verify separation before adding broker HTTP/UI. Do not claim user-visible
connectivity until US2 and US3 acceptance is green.

### Incremental Delivery

Complete US1, US2 and US3 with progress/evidence updates at each task. Report
application-source completion separately from platform acceptance. If topology
remains unresolved, deliver honest offline capability evidence and SB-A08 BLOCKED.

### Notes

26 tasks: setup 2, foundations 2, US1 5, US2 7, US3 4, final acceptance 6.
No new numbered feature, branch, dependency install or source changes in this
documentation phase. All future source changes require the parent review first.
