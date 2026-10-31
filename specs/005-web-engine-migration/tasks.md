---
description: "Executable, mandatory-test work plan for complete web-only engine migration"
---

# Tasks: Complete web-only engine migration

**Input:** `specs\005-web-engine-migration\spec.md`, `plan.md`, `discovery.md`,
`research.md`, `data-model.md`, `quickstart.md`, `contracts\runtime-api.md`,
`contracts\headless-and-deployment.md`, amended constitution and the normative
`docs\governance\web-migration-contract.md`.
**Prerequisite gate:** [exact Git/API receipt](tasks-gate-2026-10-31.md): clean/pushed
spec and plan at `193d16dc754567710c8dd5703e4f427184c9079f`, open main-targeting PR #8.
**Current state:** user-directed implementation authorized. T001–T014, T016 and T017
are complete as recorded; T009/T010 are test-design/red-phase tasks. T011 durable-store
tests pass on synthetic Windows/NTFS, but T018 production integration remains partial.
T014/T016/T017 evidence is source/unit only. T006/T007/T012/T014/T016/T017 do not establish
Linux/ext4 or live-runtime acceptance. T003's isolated production build and browser
harness passed; T004–T005 inventories are complete. T015 and T018–T136 remain open.
Credential material/version retention, NTFS ACL proof, writer/provider integration,
Linux/ext4 and legacy TUI dotenv cleanup remain future work. No merge is authorized.
Runtime work remains subject to the isolation and evidence gates below.

**Tests: MANDATORY.** Unit, regression, contract, cross-process, browser, native Windows,
native Linux, package and full-suite acceptance are required, never optional. Write
discriminating tests before implementations, observe expected red, implement, then
record green; no paid/external calls even when testing paid policy. Native tests use real
test-owned processes/OS primitives with fake providers, not mocked OS-success assertions.

## Format and path conventions

Every task has `- [ ] Tnnn`, optional `[P]`, story label inside story phases, and concrete
repository-relative Windows paths. Python tests are co-located next to changed code under
`hedge_fund`; React unit tests are adjacent under `frontend\src`; actual browser tests
use the existing `frontend\e2e` harness. New `runtime`/`reporting` files are proposed
destinations, not existing/shipped modules. Evidence documents below are future outputs
requested by these tasks, not fabricated acceptance.

`[P]` means distinct files with no peer-task dependency after that phase's prerequisites;
it does not permit executing guarded implementations before red tests, cross-phase
shared-file races, or skipping a named dependency. All implementation tasks depend on
their listed preceding discriminating tests. Validation tasks depend on all story
implementations they exercise. Dependencies and shared-file ownership are below.

### Scope/authority rules for every task

- Domain scheduling, execution, broker reconciliation, sizing, serialization, approvals
  and backtesting stay canonical. Pin code-version stamps in cross-revision ledger fixtures;
  never change existing ledger bytes/default-off field ordering to fit a new UI.
- G1–G4 expressly supersede the historical amendment/paid-default/SIM-browser contradictions.
  Web mutation is local-paper only; SIM browser inspection/provisioning guidance is an
  explicit exemption, not browser execution parity. Headless SIM needs exclusive binding
  across roots and verified transfer, never real-brokerage setup.
- All writes use shared admission: CLI, runner, manual, redo, control/verdict, templates,
  settings/credentials, deployment/research lifecycle/results, account registry.
  Legacy/nonparticipating/out-of-band uncertainty denies mutation, not just stop.
- Mandatory explicit root before sensitive imports, exact-root dotenv only if opted in,
  minimal child environment/private captures; NTFS/ext4 with actual identity/lock/ACL
  evidence. Unknown primitives deny capability. No HOME/CWD/network-filesystem fallback.
- Observer GET/poll/reconnect never authorizes calls or creates sidecars. Container is
  read-only, credential-free/provider-free and loopback-published; no write proxy.
- Every future run must use checkout-owned synthetic fixtures/HOME/USERPROFILE, cleared
  credential variables before imports, disabled dotenv and below-guard I/O sentinels.
  Never touch real `watchtower`, `watchtower-weekly`, `umbrella`, their aliases/runners,
  creator port `8765`, production credentials or existing compose services.
- Evidence needs criterion, expected/observed, exact revision/build/time/environment,
  synthetic fixture provenance, exclusions and pass/fail/blocked status. Probe tooling
  safely before claiming unavailable; blocked required evidence never passes retirement.

## Phase 1: Setup (Shared Infrastructure)

**Purpose:** prepare a safe test-first implementation environment and assertion/evidence
inventory without operating real deployments. No existing test command is safe merely
because it is documented.

- [X] T001 Audit pre-import isolation and implement checkout-owned synthetic root/HOME/USERPROFILE fixtures, credential clearing, enforced dotenv suppression, external-I/O deny sentinels and exact owned-process cleanup in `hedge_fund\conftest.py` and `hedge_fund\web\conftest.py`; preserve current fixture contracts and prove below-guard adapters cannot reach real resources before any selected test run.
- [X] T002 Add harness self-tests for decoy CWD/parent dotenv, credential variables, protected-name aliases and escaped fixture cleanup in `hedge_fund\test_acceptance_isolation.py`; verify denied access/provider/process effects are zero and isolation applies before project imports and to spawned children (depends on T001).
- [X] T003 Adapt `frontend\playwright.config.ts`, `frontend\src\test\setup.ts`, `frontend\src\test\setup.test.ts`, `frontend\e2e\desk.spec.ts`, `frontend\e2e\run-owned.mjs`, `frontend\scripts\run-owned.test.mjs`, `frontend\package.json`, `frontend\vite.config.ts`, `hedge_fund\web\__main__.py`, `hedge_fund\web\demo.py`, `hedge_fund\web\test_main.py` and `hedge_fund\web\test_launcher.py` to a test-owned explicit root/port 8876, external-request denial, no reuse of unrelated servers, isolated fixture-owned output/cache, exact owned-process cleanup and persistent spec005 screenshots; remove the current 8765 acceptance defaults (depends on T001–T002).
- [X] T004 [P] Create an individual 74-row FR-001–FR-062/test/required-or-explicit-exemption/status matrix in `specs\005-web-engine-migration\acceptance-matrix.md`, preserving discovery IDs and recording G4 SIM exemptions separately; add expanded entrypoint/helper/compose assertions and LM1–LM5/LB1–LB5/HM1–HM5 obligations, with all runtime rows initially pending.
- [X] T005 [P] Inventory each assertion in `hedge_fund\tui\test_home.py`, `test_keys.py`, `test_builder.py`, `test_builder_broker.py`, `test_funds.py`, `test_paper.py`, `test_paper_view.py`, `test_backtest.py`, `test_report.py`, `test_scorecard_view.py` and TUI-importing external tests into `specs\005-web-engine-migration\retired-assertions.md`; assign named neutral/web/browser replacement tests before any deletion, including schedule/progress/default/console semantics.
- [X] T006 Record safely checked Python/Poetry/Node/npm/browser/Windows/Linux/container tooling and supported NTFS/ext4 runtime availability in `specs\005-web-engine-migration\environment-evidence.md`; inspect only test-owned environments, never current compose services or real roots, install only after an authorized missing-tool/dependency failure, and leave unevidenced required platform rows pending/blocked rather than inferred passed (depends on T001–T003).

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose:** neutral helper/import closure, fixed root and all-writer safety must precede
story mutations. Tests below are mandatory red-green implementation tasks.

- [X] T007 [P] Add fixed-root/bootstrap/path/filesystem contract tests in `hedge_fund\runtime\test_root.py` and regressions in `hedge_fund\test_paths.py` for absent root, decoy home/CWD/dotenv, case/YAML aliases, traversal/reserved/trailing-dot-space/reparse/race, protected synthetic identities and UNC/mapped/network/cloud/unknown filesystem denial before access; cover R1–R3 and FR-006/044/058.
- [X] T008 [P] Add neutrality/byte-parity tests in `hedge_fund\reporting\test_console.py` and `hedge_fund\runtime\test_defaults.py` comparing existing cost/report/scorecard order, signed fractional precision, backtest defaults and schedule/progress assertions with fixed code-version fixtures; map moved TUI assertions without removing originals. Expected-red imports are recorded in `implementation-evidence.md`; neutral implementations are complete under T013.
- [X] T009 [P] Add cross-process registry/deployment/control lock tests in `hedge_fund\runtime\test_admission.py` for sorted lock order, two independent funds, runner reservation versus manual-between-sessions, crash release, unknown legacy owner and bounded Halt/verdict lane; fakes sit below admission, not in place of admission. Expected-red collection and test-only scope are recorded; OS-lock behavior remains pending T014.
- [X] T010 [P] Add capture/config/credential-policy tests in `hedge_fund\runtime\test_capture.py` and `hedge_fund\runtime\test_policy.py` for launch/environment > persisted > free defaults, no capability elevation, frozen private versions, local-versus-cloud-labelled models and paid one-shot versus finite free/local scheduled scope. Expected-red test design and subsequent implementation checks are recorded; no provider dispatch ran.
- [X] T011 [P] Add durable confirmation/request/journal tests in `hedge_fund\runtime\test_operations.py` for canonical preview digest, operator session, expiry, single-use admission transaction, same-ID/same-payload replay versus changed-payload conflict, crash points and interrupted/fenced surviving worker; never infer no effects from a missing record. Expected-red history and green synthetic Windows/NTFS regressions are recorded in `implementation-evidence.md`; T018 production integration remains partial.
- [X] T012 Implement pre-import `RootContext`, filesystem/device/namespace identity, handle-relative use-time revalidation, explicit-root caches/plots/config and exact-root opted-in dotenv in `hedge_fund\runtime\root.py`, `hedge_fund\paths.py`, `hedge_fund\run.py` and `hedge_fund\web\__main__.py`; preserve only safe explicit non-secret overrides (depends on T007). Windows/NTFS tests pass; Linux/ext4 acceptance remains blocked under T022.
- [X] T013 Extract non-interactive console report/scorecard/cost/default helpers into `hedge_fund\reporting\console.py` and `hedge_fund\runtime\defaults.py`; redirect `hedge_fund\run.py`, `hedge_fund\web\services.py`, root-level `check_stock.py` and `hedge_fund\llm\test_client.py` away from TUI helper imports, retain TUI compatibility wrappers until assertion migration, and do not change domain outputs (depends on T008, T012).
- [X] T014 Implement versioned OS-released registry/runner-reservation/execution/control lanes and ordered multi-resource acquisition in `hedge_fund\runtime\admission.py`; use bounded emergency lane, deny unknown owner/manual during runner lifetime and keep independent funds independent (depends on T009, T012). Synthetic Windows/NTFS OS-lock tests pass; Linux/ext4 and writer integration remain blocked/pending under T022/T021.
- [ ] T015 Implement controlled offline handover, protocol/build compatibility and explicit stale-reservation recovery records in `hedge_fund\runtime\handover.py` and `hedge_fund\runtime\test_handover.py`; deny all mutation until old CLI/cron/service/writable-container/out-of-band writers are verifiably excluded, never trust a marker/TTL/PID alone (depends on T014).
- [X] T016 Implement non-secret settings resolution, immutable private `FrozenCapture`, root-scoped credential-version handles and minimal owned-child environment in `hedge_fund\runtime\configuration.py` and `hedge_fund\runtime\capture.py`; children receive exact root, isolated HOME/USERPROFILE and no ambient key/root/capability variables or secret argv (depends on T010, T012, T014). Source/unit checks pass on synthetic Windows/NTFS; credential material, child lifecycle, ACL and Linux/ext4 remain open.
- [X] T017 Implement authorized provider classification and dispatch budget reservations in `hedge_fund\runtime\policy.py`; unknown upper-bound cost denies paid admission, worst-case budget is reserved before each call, caps stop the next call/session, no automatic paid retries, and scheduled cloud/paid is always denied (depends on T010, T016). Source/unit checks pass; live provider dispatch and shared writer integration remain open.
- [ ] T018 Implement root-private atomic preview/token consumption plus durable request/journal/state/result sidecars in `hedge_fund\runtime\operations.py` and `hedge_fund\web\jobs.py`; accepted must persist before spawn/effects, cancellation is boundary-based, server restart fences unfinished workers and marks interrupted without resume/retry (depends on T011, T014, T016–T017). Partial: store, snapshot reads, in-process job tests, safe-boundary cancellation and restart fencing exist; no production API/DeskService wiring, owned child lifecycle, ACL/private-storage proof or verified handover. Mutation stays disabled.
- [ ] T019 Wire common observational/mutation schemas and safe 400/403/409/410/422/423/429/503 errors in `hedge_fund\web\schemas.py`, `hedge_fund\web\app.py` and `hedge_fund\web\services.py`; enforce fixed root, Host/Origin/CSRF/session guards on routes/channels, no secret/root/PID/capability payload and no GET writes/providers/starts (depends on T012–T018).
- [ ] T020 Add contract regressions in `hedge_fund\web\test_app.py`, `hedge_fund\web\test_actions.py` and `hedge_fund\web\test_jobs.py` covering every common error, foreign Host/Origin/expired or absent CSRF, read-only/SIM mutation denial, malicious inert text and zero downstream denied effects, including observation reconnect (depends on T019).
- [ ] T021 Integrate shared root/admission/capture/policy/request handling into every existing writer in `hedge_fund\run.py`, `hedge_fund\paper\runner.py`, `hedge_fund\paper\tick.py`, `hedge_fund\paper\ledger.py`, `hedge_fund\fund\storage.py`, `hedge_fund\backtesting\research.py` and `hedge_fund\web\services.py`; add matching regressions in adjacent `test_*.py`, keep domain algorithms canonical and protect existing template/config/result/control entrypoints (depends on T014–T020).
- [ ] T022 Add and run actual Windows NTFS and Linux ext4 identity/lock/atomic-replace/incarnation-boundary tests in `hedge_fund\runtime\test_native_primitives.py`; record native source/build/fixture evidence in `specs\005-web-engine-migration\native-primitives-evidence.md`, and deny capability/block required acceptance if primitive verification fails or a checked runtime is unavailable (depends on T006–T007, T014–T021).
- [ ] T023 Integrate no-retry typed operation preview/admission/status/cancel client and identity-aware bounded polling in `frontend\src\lib\api.ts`, `types.ts`, `hooks.tsx` and adjacent `api.test.ts`, `hooks.test.tsx`; query persisted operation IDs on reload, reject late identity/cursor updates and never store keys/tokens or re-submit on mount/reconnect (depends on T018–T020).
- [ ] T024 Run the isolated affected foundation regressions with existing pytest/Vitest/TypeScript/lint runners and record exact output/status plus LM/LB/HM coverage in `specs\005-web-engine-migration\foundation-evidence.md`; distinguish red-green development from acceptance, require successful applicable native rows before enabling host mutation, and keep failed/blocked primitives fail-closed (depends on T002–T023).

**Checkpoint:** all foundational seams exist and safety regressions pass; platform mutation
is enabled only where primitives are actually verified. Blocked native evidence never
permits a retirement claim or a fallback process/ACL implementation.

## Phase 3: User Story 1 — Operate the paper engine from the desk (P1, MVP)

**Goal:** deliberately start/stop a verified owned local-paper runner and execute a
reviewed canonical manual session with durable observation and independent-fund safety.
**Independent test:** synthetic fund, fake clock/providers, real test-owned admission and
native child; start/acknowledge one runner, complete one canonical session, stop at its safe
boundary, then separately run due/nothing-due manual work. Reload/server restart observes,
not repeats. Unrelated PID, unknown owner and second fund are discriminators.
**Coverage:** FR-003/006–017/023–026/053–055/058; discovery A03/A05, B05/B10
and D01–D09/D11/D16.

### Mandatory tests (write and observe red first)

- [ ] T025 [P] [US1] Add native ownership/runner state tests in `hedge_fund\runtime\test_ownership.py` for root/deployment/protocol/build/boot/namespace/PID-incarnation/nonce/capture binding, forged/legacy/unknown owner denial, handshake timeout, unrelated PID survival and no auto-adoption/start.
- [ ] T026 [P] [US1] Add manual/cadence regression tests in `hedge_fund\paper\test_tick.py` and `hedge_fund\paper\test_runner.py` for exact reviewed oldest-first daily backlog, explicit dates/backfill, nothing-due/idempotent recorded sessions, weekly/monthly/minute one-second cadence, holidays/gaps/lateness and fake headless SIM cutoff.
- [ ] T027 [P] [US1] Add cross-process writer-race tests in `hedge_fund\runtime\test_writer_races.py` competing real test-owned CLI/web/runner/manual/redo/archive admissions, unknown legacy/out-of-band presence and independent funds; assert zero duplicate fills/appends and responsive Halt/verdict under bounded research saturation.
- [ ] T028 [P] [US1] Add React runner/manual unit tests in `frontend\src\pages\paper.test.tsx` and `frontend\src\components\operation-status.test.tsx` for readiness/capture/due-set confirmation, starting/running/stopping/unknown/error/nothing-due labels, repeated clicks/lost response/reload and late status rejection.
- [ ] T029 [P] [US1] Add real-browser synthetic runner/manual scenarios in `frontend\e2e\operations.spec.ts` using the guarded backend fixture for start, admission conflict, exact due-set review, stop boundary, navigation/reload/closure and offline monitoring; assert no reconnect/reload mutation or provider authorization.

### Implementation

- [ ] T030 [US1] Implement private owned-process handshake/incarnation records and OS-specific graceful control channels in `hedge_fund\runtime\ownership.py`; never accept raw PID liveness, signal unknown descendants or adopt cross-namespace owners (depends on T025, T022).
- [ ] T031 [US1] Implement detached Windows owned process-group/control and POSIX session/process-group launch/observation in `hedge_fund\runtime\processes.py` and `hedge_fund\runtime\test_processes.py`; allow browser/server-independent runner life and explicit verified stop with bounded diagnostics (depends on T025, T030).
- [ ] T032 [US1] Integrate reservation lifetime, per-session short lease, owned readiness handshake and starting/running/stopping/stopped/failed/unknown transitions into `hedge_fund\paper\runner.py`; check Halt and finite free/local expiry/session/call/resource bounds before each next admission/provider boundary and never auto-restart (depends on T026–T027, T030–T031).
- [ ] T033 [US1] Implement canonical manual/start previews with ordered exact head/due-set, explicit backlog selection/skip decision, dates/universe/capture digest and separate finite future authorization in `hedge_fund\runtime\preflight.py` and `hedge_fund\runtime\test_preflight.py`; revalidate clock/window/head at admission, not retarget stale work (depends on T026, T018, T032).
- [ ] T034 [US1] Adapt canonical manual tick and stage/agent progress into durable bounded jobs in `hedge_fund\web\services.py`, `hedge_fund\web\jobs.py` and `hedge_fund\paper\tick.py`; preserve no-work/cash/replay/record bytes and expose append-failure ambiguity without retry (depends on T026–T027, T033).
- [ ] T035 [US1] Implement runner/schedule/status/start/owned-stop/manual endpoints and operation preview/admission/cancel routes in `hedge_fund\web\app.py` and `hedge_fund\web\schemas.py`; start is explicit, SIM mutation denied, stop remains requested until verified quiescence and runner reservation denies manual rather than queues (depends on T030–T034).
- [ ] T036 [US1] Add implemented headless explicit-root preview/expected-head/due-set/digest/request/finite-policy arguments to `hedge_fund\run.py` and `hedge_fund\test_run.py` for paper run/tick/stop/status; route through the same protocol, document intentional root/free-default incompatibilities and reject unspecified future confirmation (depends on T033–T035).
- [ ] T037 [US1] Implement restart recovery/verified live-owner reattachment and interrupted surviving bounded-worker fencing in `hedge_fund\runtime\recovery.py` and `hedge_fund\runtime\test_recovery.py`; prove owner quiescence/journal inspection before conflicting admission, never restart stopped/failed/unknown or replay an old request (depends on T030–T036).
- [ ] T038 [US1] Implement runner/manual/backlog review, status and safe Stop/cancel panels in `frontend\src\pages\paper.tsx` and new `frontend\src\components\operation-status.tsx`; show root/capture/progress/last-next/skips/readiness and exact safe-boundary outcome with durable recovery links (depends on T028, T035–T037, T023).
- [ ] T039 [US1] Integrate active recorded/error/root/owner status and explicit refresh into `frontend\src\pages\home.tsx`, `frontend\src\lib\hooks.tsx` and `frontend\src\pages\home.test.tsx`; observation is provider-free and stale responses cannot replace newer subjects/operations (depends on T038).
- [ ] T040 [US1] Add endpoint/CLI parity regressions in `hedge_fund\web\test_actions.py`, `test_services.py` and `hedge_fund\test_run.py` for invalid root/config/model/key/network/halt/replay/capacity denial before provider construction, duplicate request responses, lifecycle states and frozen capture (depends on T034–T039).

### Required acceptance

- [ ] T041 [US1] Run native Windows owned-runner lifecycle tests in `hedge_fund\runtime\test_native_runner.py` with synthetic daily/minute schedules, browser/server death, restart observation, unrelated PID reuse, in-flight Stop/Halt and bounded-job independence; record actual Windows build/process/fixture outcomes in `specs\005-web-engine-migration\runner-windows-evidence.md` (depends on T025–T040).
- [ ] T042 [US1] Run the same actual Linux ext4/POSIX lifecycle in `hedge_fund\runtime\test_native_runner.py` and record `specs\005-web-engine-migration\runner-linux-evidence.md`; first check an authorized runtime, never replace Linux observations with Windows/mocks/historical PR7 or leave a required blocked row counted passed (depends on T025–T040, T006).
- [ ] T043 [US1] Run co-located runner/tick/runtime/web/CLI regressions plus React unit/build and `frontend\e2e\operations.spec.ts`; record due/no-work, race, lost-response, offline and SC-009 measured acknowledgment/status outcomes in `specs\005-web-engine-migration\us1-evidence.md` with fixture/revision/time (depends on T040–T042).
- [ ] T044 [US1] Update individual A03/A05/B05/B10/D01–D09/D11/D16 and FR/LM/HM links in `specs\005-web-engine-migration\acceptance-matrix.md` and moved paper/home assertions in `retired-assertions.md`; block the story/platform where mandatory evidence is not passed and retain SIM cutoff as headless-only (depends on T043).

## Phase 4: User Story 2 — Configure a complete reproducible fund (P1)

**Goal:** complete validated ordinary/advanced mandate editing plus persistent provider/model/
endpoint/credential settings with provenance and immutable active captures.
**Independent test:** round-trip every domain field/non-default/omission in synthetic YAML/YML,
freeze an operation, change/delete credentials/settings and prove next-versus-active versions;
no validation call or sentinel disclosure. A runner adoption test requires US1.
**Coverage:** FR-018–034/053–056; B01–B12, C01–C17 with G4 SIM exemption.

### Mandatory tests

- [ ] T045 [P] [US2] Add complete settings/provenance/private-key set/delete/frozen-active tests in `hedge_fund\web\test_settings.py` and `hedge_fund\runtime\test_credentials.py`; search returned/logged/exported/browser/argv material for sentinels and distinguish absent/present/overridden/deleted-after-capture/restart-required.
- [ ] T046 [P] [US2] Add full mandate round-trip/library-custom/parameter/risk/cost/threshold/benchmark/approval/cadence/YAML-YML/revision/immutable-snapshot tests in `hedge_fund\fund\test_spec.py`, `test_spec_broker.py`, `test_strategy_library.py` and new `test_storage.py`; preserve field order/default omissions and no arbitrary constructor execution.
- [ ] T047 [P] [US2] Add endpoint/destination dispatch tests in `hedge_fund\runtime\test_endpoints.py` for HTTPS approved host/port, secret userinfo/query/fragment, unsupported schemes, redirects/rebinding/private/metadata/link-local/IPv4-mapped IPv6, TLS pinning and approved literal-loopback genuinely-local exception; use fake resolver/transports below actual guards with zero live calls.
- [ ] T048 [P] [US2] Add React ordinary/advanced editor and settings unit tests in `frontend\src\pages\builder.test.tsx` and `settings.test.tsx` for every supported field, day/minute conversion, no dropped values, library-to-custom identity, override/active-version warnings and write-only delete/set (no secret persistence).
- [ ] T049 [P] [US2] Add real-browser editor/configuration scenarios in `frontend\e2e\configuration.spec.ts` for unchanged full-field save, stale revision/edit/clone/rename, runtime settings restart, credential sentinel non-echo, malformed catalog visibility and free/local zero-cloud-key readiness.

### Implementation

- [ ] T050 [US2] Implement private root-scoped surgical atomic credential set/delete and monotonic versions in `hedge_fund\runtime\credentials.py`; verify POSIX owner modes or restrictive Windows ACL inheritance/owner SID, deny mutation/use if protection fails, retain captured active material privately and replace `hedge_fund\tui\keys.py` logic with a compatibility wrapper (depends on T045, T016, T022).
- [ ] T051 [US2] Implement approved endpoint validation and authorized resolved/pinned TLS dispatch in `hedge_fund\runtime\endpoints.py`, `hedge_fund\llm\client.py` and `hedge_fund\data\__init__.py`; bind credentials to exact destination, deny redirects/rebinding and proxy-cloud scheduled models without network validation (depends on T047, T017, T050).
- [ ] T052 [US2] Make credential-free yfinance the installed safe default across CLI/web/backtest/runner in `hedge_fund\data\__init__.py`, `hedge_fund\data\test_factory.py`, `pyproject.toml` and `poetry.lock`; preserve supported explicit provider aliases but keys/environment never authorize network/paid and no paid test calls (depends on T045, T051).
- [ ] T053 [US2] Implement normalized persistent provider/model/approved endpoint/context/timeout settings and redacted stored/effective/active provenance APIs in `hedge_fund\web\services.py`, `hedge_fund\web\schemas.py` and `hedge_fund\web\app.py`; dedicated version/session/preview-bound credential endpoint alone accepts secret material, never a generic job/digest/storage payload (depends on T045, T050–T052).
- [ ] T054 [US2] Extend authoritative registry/constructor validation and lossless supported FundSpec serialization in `hedge_fund\fund\spec.py` and `hedge_fund\fund\storage.py`; preserve historical omissions/order, explicit dollar neutrality and canonical library rosters until deliberately custom (depends on T046).
- [ ] T055 [US2] Implement canonical template list/read/create/edit/clone/rename with revision-bound admission, YAML/YML/case/protected collision checks and malformed-entry errors in `hedge_fund\web\services.py` and `hedge_fund\web\schemas.py`; distinct universe resource/admission must never rewrite deployment snapshots/pending decisions (depends on T046, T054, T021).
- [ ] T056 [US2] Implement complete ordinary/structured JSON advanced editor in `frontend\src\pages\builder.tsx`, `mandates.tsx` and `frontend\src\lib\types.ts`; cover capital/universe/roster/sleeve-model weights/parameters/blend/neutrality/risk/cost/order-threshold/benchmark/approval/broker/cadence/window/timezone, remove minute-only fields on day grid and restore valid minute defaults (depends on T048, T054–T055).
- [ ] T057 [US2] Implement persistent provider/model/local/remote runtime settings and write-only version-bound credential set/delete UI in `frontend\src\pages\settings.tsx`; show effective overrides/active capture/deleted-after-capture/restart requirement, no network validation/secret value in browser storage/errors or hot swapping (depends on T048, T050–T053).
- [ ] T058 [US2] Integrate builder→inspect/deploy/reviewed backtest/manual actions, separate universe validation and redacted local-paper/SIM headless-provisioning readiness in `frontend\src\pages\builder.tsx`, `mandates.tsx`, `settings.tsx` and `hedge_fund\web\test_settings.py`; never advertise SIM web mutations and never treat provisioning as authorization (depends on T056–T057; actual run action also depends on US1 T044, deploy/backtest on US4/US5).

### Required acceptance

- [ ] T059 [US2] Add and run native Windows credential ACL/inheritance/owner and Linux mode/atomic version/private-capture tests in `hedge_fund\runtime\test_native_credentials.py`; record OS-specific actual results in `specs\005-web-engine-migration\credential-platform-evidence.md`, check missing tooling before declaring blocked and never substitute POSIX mode for Windows ACL proof (depends on T045, T050, T006).
- [ ] T060 [US2] Run co-located fund/config/provider/credential/LLM/web/CLI regressions with frozen active runner and next-operation captures, fake budget/endpoint denials and secret non-echo assertions; record exact results in `specs\005-web-engine-migration\us2-evidence.md` (depends on T045–T059, US1 T044 for runner adoption).
- [ ] T061 [US2] Run React unit/build and `frontend\e2e\configuration.spec.ts` full-field/revision/secret/provenance scenarios against production guards with fakes; append actual browser/revision/fixture results to `specs\005-web-engine-migration\us2-evidence.md` (depends on T049, T056–T060).
- [ ] T062 [US2] Update individual B01–B12/C01–C17 coverage and named keys/builder/funds/helper replacement assertions in `specs\005-web-engine-migration\acceptance-matrix.md` and `retired-assertions.md`; mark B12/C09 SIM browser mutation explicitly exempt while requiring headless readiness tests, not blanket editor/US2 exemption (depends on T060–T061).

## Phase 5: User Story 3 — Approve and recover without unsafe retries (P1)

**Goal:** decision-identity-bound approvals, bounded emergency Halt, verified Resume and
local-paper latest redo preserve ledger and reconciliation semantics.
**Independent test:** synthetic ledger/book/fills with matching/stale/consumed/expired votes,
source/execution redo, malformed controls/replay and append-failure/lost-response injection;
replay alone cannot clear ambiguous fills and no control implicitly starts work.
**Coverage:** FR-013/017/035–039/053–055; A06, D10/D12/D13, E04–E08; O3–O5.

### Mandatory tests

- [ ] T063 [P] [US3] Add canonical verdict/redo byte-parity regressions in `hedge_fund\paper\test_ledger.py` and `test_tick.py` for timestamp/source hash, stale/consumed/expired/replacement semantics, latest expected head/local-paper-only redo, superseded history retention and source-versus-execution vote behavior.
- [ ] T064 [P] [US3] Add corruption/post-fill reconciliation tests in `hedge_fund\runtime\test_reconciliation.py` and `hedge_fund\web\test_recovery.py` for unreadable controls versus replay corruption, atomic emergency Halt, fake fills then append failure/crash, journal/broker-book comparison and denied replay-only Resume.
- [ ] T065 [P] [US3] Add control/approval/redo React unit tests in `frontend\src\components\decision-controls.test.tsx` for exact timestamp/hash/head confirmation, stale-refresh not retarget, active-runner future-execution warning, separate Run/Resume, ambiguity/residual uncertainty and stop/cancel-not-rollback labels.
- [ ] T066 [P] [US3] Add real-browser synthetic approval/recovery scenarios in `frontend\e2e\recovery.spec.ts` for matching/stale/consumed votes, corrupt controls emergency Halt, source/execution redo, lost response and reconciliation-bound Resume without implicit execution.

### Implementation

- [ ] T067 [US3] Implement root/identity-safe atomic emergency Halt and bounded decision/control lane in `hedge_fund\runtime\controls.py`, `hedge_fund\paper\ledger.py` and `hedge_fund\paper\tick.py`; new admission stops immediately, in-flight effects respect documented boundaries, no ordinary-corrupt-control trust or indefinite runner lock wait (depends on T063–T064, T021, T032).
- [ ] T068 [US3] Implement durable reconciliation provenance in `hedge_fund\runtime\reconciliation.py` using canonical `hedge_fund\pipeline\session.py`/broker reconciliation; bind request/head/book/fill/capture/operator/time/decision/residual uncertainty and require both reconciliation and replay before Resume, irreconcilable stays halted/unknown (depends on T064, T037, T067).
- [ ] T069 [US3] Implement reviewed decision verdict/Halt/Resume/redo adapters in `hedge_fund\web\services.py`, `hedge_fund\web\app.py` and `hedge_fund\web\schemas.py`; exact identity/head/digest/admission, local-paper redo only, durable consumed request, no approval/Resume start or repeated failed effects (depends on T063–T064, T067–T068).
- [ ] T070 [US3] Integrate identical approved/head-bound recovery/control semantics into paper approve/reject/halt/resume/redo in `hedge_fund\run.py`, `hedge_fund\test_run.py` and `hedge_fund\paper\test_saxo_e2e.py`; retained fake SIM headless controls require exclusive ownership while every SIM web control/redo is denied (depends on T069; SIM mutation acceptance also depends on US4 T099).
- [ ] T071 [US3] Implement `frontend\src\components\decision-controls.tsx` and integrate into `frontend\src\pages\paper.tsx`; show pending/matching/stale/consumed/expired identities, active-runner warning, separate explicit Run, corruption/ambiguity distinctions and reviewed latest redo/reconciliation, never auto-refresh into a new mutation (depends on T065, T069).
- [ ] T072 [US3] Add implemented web/CLI denial and append-failure regressions in `hedge_fund\web\test_actions.py`, `test_recovery.py` and `hedge_fund\paper\test_tick.py`; test live/unknown writer conflict, SIM redo denial, stale confirmation, journal restart and unchanged canonical cash/replay/hash bytes (depends on T067–T071).

### Required acceptance

- [ ] T073 [US3] Run actual Windows/Linux cross-process emergency-control and redo/reconciliation scenarios in `hedge_fund\runtime\test_native_controls.py`, including research-saturated runner and crash-held lease, then record responsive no-new-admission and ambiguity boundaries in `specs\005-web-engine-migration\recovery-platform-evidence.md` (depends on T063–T072, T006).
- [ ] T074 [US3] Run isolated ledger/tick/broker/runtime/web/CLI regressions and paired fixed-code-stamp replay fixtures; record exact expected/observed source/fill/head/cash/vote outcomes in `specs\005-web-engine-migration\us3-evidence.md` (depends on T072–T073; fake SIM coverage waits for T099).
- [ ] T075 [US3] Run React unit/build and `frontend\e2e\recovery.spec.ts` against synthetic corrupted controls/append-failure fixtures, record actual keyboard confirmation/reload/no-repeat evidence in `specs\005-web-engine-migration\us3-evidence.md` (depends on T066, T071–T074).
- [ ] T076 [US3] Update A06/D10/D12/D13/E04–E08, FR-035–039 and LM3/HM5 closure evidence plus each moved paper recovery/vote/redo assertion in `specs\005-web-engine-migration\acceptance-matrix.md` and `retired-assertions.md`; ambiguous/interrupted/blocked never counts as success (depends on T074–T075).

## Phase 6: User Story 6 — Retire the terminal UI without losing deployment support (P1)

**Goal:** default packaged desk and retained headless support with terminal-inspired,
keyboard/narrow-screen usability, no Textual/Node runtime/ttyd/autostart topology.
**Independent test:** staged clean wheel/sdist installation without Textual or frontend build
tools launches assets/default desk, fails actionably if missing, exercises all headless
commands with fakes and denies observer/SIM browser mutations. Actual Windows/Linux and
all six keyboard/360px journeys are required before final removal/retirement.
**Coverage:** FR-001–005/027/053–062, SC-007–010; A01/A02/A04/A07, retained headless
aspects of D09/F10/F12, explicit G4 SIM exception.
**Scheduling:** priority is P1, but retirement substage T090–T094 must wait for US4/US5
and cross-cutting acceptance. This phase is not permission to delete early.

### Mandatory tests and non-destructive candidate preparation

- [ ] T077 [P] [US6] Add default desk/missing-bundle/TUI-import-closure tests in `hedge_fund\test_run.py`, `hedge_fund\web\test_launcher.py`, `test_main.py` and `hedge_fund\reporting\test_console.py`; exercise all retained paper/backtest/report/stdout/output-file commands with fakes and ban Textual import without changing canonical meaning except documented safety defaults/root policy.
- [ ] T078 [P] [US6] Add read-only snapshot/projection/topology tests in `hedge_fund\web\test_observer.py` for paired head/snapshot conflict, no GET sidecar/cache/config writes/provider construction/credential mount, no preview token persistence or mutation proxy and Host/Origin/CSRF/internal-bind carveout denial.
- [ ] T079 [P] [US6] Add six-journey keyboard/360px/accessibility/terminal-appearance browser tests in `frontend\e2e\accessibility.spec.ts` and component focus/navigation regressions in `frontend\src\App.test.tsx`; require command palette, back navigation, labelled statuses, confirmations, contrast and unclipped signed precision (full run depends on US1–US5).
- [ ] T080 [P] [US6] Add clean wheel/sdist asset/runtime/import and image/compose policy tests in `hedge_fund\web\test_distribution.py`; prepare candidate artifacts excluding TUI without deleting old source tests, verify Node only build-time, free-data/default desk dependencies and deny missing-assets terminal fallback.
- [ ] T081 [US6] Implement default no-command desk launch and actionable missing-assets handling in `hedge_fund\run.py`, `hedge_fund\web\__main__.py` and `hedge_fund\web\app.py`; retain explicit-root headless scripts and no terminal fallback, complete neutral helper closure first (depends on T077, T013, T050).
- [ ] T082 [US6] Implement sanitized immutable observer projection/head pairing in `hedge_fund\runtime\observation.py`, `hedge_fund\web\services.py` and `hedge_fund\web\__main__.py`; read-only container never opens credentials/providers/jobs/config/cache writers, no safe projection means deny startup and cross-namespace mutation is forbidden (depends on T078, T019).
- [ ] T083 [US6] Implement accessible dense terminal-inspired navigation/control/focus/numeric layout in `frontend\src\App.tsx`, `index.css`, `components\command-palette.tsx`, `confirm-dialog.tsx`, `page.tsx` and affected story pages; preserve existing design and all six keyboard/360px journeys rather than a screenshot-only demo (depends on T079 and respective story UI tasks).
- [ ] T084 [US6] Build/package candidate static assets and dependency/import closure in `pyproject.toml`, `poetry.lock`, `frontend\vite.config.ts` and `hedge_fund\web\static`; make supported desk/free default available in clean installation, exclude Textual only in the staged candidate until replacement acceptance, never require runtime Node (depends on T080–T081, T052).
- [ ] T085 [US6] Rewrite `Dockerfile`, `Dockerfile.web`, `docker-compose.yml` and `docker-compose.linux.yml` to packaged read-only observer, sanitized read-only projection, no credentials/provider calls/ttyd/TUI services/writable runner/autorestart, explicit root and host-loopback-only publication; validate only isolated candidate services, not existing compose deployments (depends on T078, T080, T082, T084).
- [ ] T086 [US6] Update `Makefile`, `README.md` and `hedge_fund\README.md` with tested desk/headless explicit-root commands, free-default and reviewed policy flags, controlled legacy handover, finite runner authorization, stopped restore/backlog review, SIM provisioning/exclusive binding exception and safe synthetic names/ports/topology (depends on T081–T085, all relevant CLI/lifecycle implementations).

### Mandatory candidate acceptance before destructive removal

- [ ] T087 [US6] Run Windows native staged clean wheel/sdist desk launch, all retained headless commands/console/stdout/output-file exports and fake SIM provisioning/readiness without Textual/Node runtime using `hedge_fund\web\test_native_distribution.py`; record build/install/import/process/asset results in `specs\005-web-engine-migration\distribution-windows-evidence.md` (depends on T077–T086, US1–US5 acceptance and T099).
- [ ] T088 [US6] Run actual Linux staged clean wheel/sdist/headless acceptance plus isolated observer container/loopback/read-only/no-autorestart scenarios in `hedge_fund\web\test_native_distribution.py` and `test_observer.py`; record `specs\005-web-engine-migration\distribution-linux-evidence.md`, checking authorized runtime readiness first and retaining blocked if required evidence cannot be obtained (depends on T077–T086, US1–US5 acceptance, T006).
- [ ] T089 [US6] Run React unit/build, all story Playwright suites and `frontend\e2e\accessibility.spec.ts`; capture synthetic desktop/360px keyboard/focus/status/precision/terminal-appearance screenshots and measured SC-009 95%-within-two-seconds outcomes in `specs\005-web-engine-migration\browser-acceptance.md` (depends on T079, T083, T087–T088 and US1–US5 browser acceptance).
- [ ] T090 [US6] Reconcile every retired assertion and all 74 individual capability/FR/test/platform rows against fresh candidate evidence in `specs\005-web-engine-migration\retired-assertions.md`, `acceptance-matrix.md` and `retirement-evidence.md`; require zero non-exempt blocked/inconclusive rows plus full-suite/QA candidate gates before authorizing destructive retirement, preserving explicit exemptions rather than asserting all 74 browser controls (depends on T087–T089, T127–T132).
- [ ] T091 [US6] Remove `hedge_fund\tui` supported entrypoints/widgets/tests only after T090 passes, retaining moved behavior in named neutral/web/browser tests and removing every outside TUI import from `hedge_fund\run.py`, root-level `check_stock.py`, `hedge_fund\web\services.py`, `hedge_fund\llm\test_client.py`, `hedge_fund\test_run.py` and `hedge_fund\paper\test_saxo_e2e.py`; audit full repository import closure without dropping assertions (depends on T090).
- [ ] T092 [US6] Remove Textual/textual-dev dependencies and regenerate `poetry.lock` via existing package tooling, finalize `pyproject.toml` distribution metadata/static assets and eliminate obsolete TUI/ttyd/Make/README paths; preserve Rich noninteractive console reporting and staged candidate behavior (depends on T091).
- [ ] T093 [US6] Rebuild and rerun fresh Windows/Linux native distribution/lifecycle, complete co-located suite, React/build/browser and observer acceptance after removal using `hedge_fund\web\test_native_distribution.py`, `hedge_fund\runtime\test_native_runner.py` and `frontend\e2e`; reopen all affected rows in `specs\005-web-engine-migration\retirement-evidence.md`, never reuse pre-removal source stamps (depends on T091–T092).
- [ ] T094 [US6] Record sole-supported-desk readiness or fail-closed non-retirement decision in `specs\005-web-engine-migration\retirement-evidence.md` with exact final revision/build/full-suite/platform/import/assertion/browser links; any new failure/blocked/inconclusive row keeps FR-062 unpassed and TUI removal changes unaccepted pending correction (depends on T093, final re-review T133).

## Phase 7: User Story 4 — Manage a reversible fund lifecycle (P2)

**Goal:** immutable deploy, scoped reversible archive, stopped collision-safe restore and
distinct linked replacement, with active job/research/account coordination.
**Independent test:** synthetic templates/deployments/research plus decoy sibling identity,
concurrent real test-owned writers and interrupted archive journals; no broad wipe, snapshot
rewrite, implicit catch-up or duplicate fake SIM account binding across roots.
**Coverage:** FR-028/033–034/040–044, R1–R4/A1–A5/C2; C05/C18/D14/D15/F11, G4.

### Mandatory tests

- [ ] T095 [P] [US4] Add immutable-deploy/exact-scope/archive/restore/replace/collision/protected-name/interrupt regressions in `hedge_fund\paper\test_deployed_broker.py`, new `hedge_fund\runtime\test_lifecycle.py` and `hedge_fund\fund\test_storage.py`; use sibling decoys and expected head/revision/references, require stopped restore and no snapshot/history overwrite.
- [ ] T096 [P] [US4] Add fake SIM account/environment binding tests in `hedge_fund\brokers\test_account_binding.py` for duplicates within/across roots, unverifiable global exclusivity denial, owned stopped/quiescent release/transfer and no real-brokerage configuration; provisioning grants no execution.
- [ ] T097 [P] [US4] Add scoped lifecycle React unit tests in `frontend\src\components\lifecycle-controls.test.tsx` for exact consequences/head/revision/reference review, writer/unknown-owner denial, stopped restore and new linked replacement identity; test template/deployment/research scope cannot be confused.
- [ ] T098 [P] [US4] Add real-browser lifecycle scenarios in `frontend\e2e\lifecycle.spec.ts` with synthetic sibling decoys, immutable snapshot, revision conflicts, archive/restore/replace, active runner/job references and explicit SIM web mutation denial.

### Implementation

- [ ] T099 [US4] Implement exclusive SIM environment/account registry and verifiable across-root account-control/handover denial in `hedge_fund\brokers\account_binding.py`, `factory.py`, `saxo_auth.py` and `paper\deployed.py`; require explicit released/transfer provenance under root/sorted deployment admission and retain fake-only non-TUI provisioning/headless behavior (depends on T096, T015, T021).
- [ ] T100 [US4] Implement distinct canonical immutable deployment admission/readiness in `hedge_fund\paper\deployed.py` and `hedge_fund\web\services.py`; validate template revision/universe/collision/root/account and local-paper-only web deploy before snapshot creation, never auto-run (depends on T095–T096, T055, T099).
- [ ] T101 [US4] Implement versioned exact-scope reversible archive/move/restore journal with interruption recovery in `hedge_fund\runtime\lifecycle.py`; preserve old rules/history/research, recheck head/reference/collision under admission and leave unknown phases recovery-required rather than broad delete (depends on T095, T018, T100).
- [ ] T102 [US4] Integrate template/deployment archive and stopped restore/new-identity linked replacement into `hedge_fund\fund\storage.py`, `hedge_fund\paper\deployed.py` and `hedge_fund\web\services.py`; require owned stopped runner plus no queued/in-flight writer, never implicitly catch up or replay pending decisions (depends on T101, T037).
- [ ] T103 [US4] Integrate scoped research archive/reference coordination into `hedge_fund\backtesting\research.py`, `hedge_fund\web\jobs.py` and `hedge_fund\web\services.py`; independent jobs/results remain intact, active refs deny archive and persisted completed results remain discoverable (depends on T101–T102; final bounded research integration depends on US5 T116–T118).
- [ ] T104 [US4] Implement reviewed deploy/archive/restore/replace endpoints and matching retained headless identity-safe lifecycle/account behavior in `hedge_fund\web\app.py`, `schemas.py`, `hedge_fund\run.py` and adjacent `hedge_fund\web\test_actions.py`/`hedge_fund\test_run.py`; deny every SIM web lifecycle mutation and keep restored fund stopped (depends on T099–T103).
- [ ] T105 [US4] Implement `frontend\src\components\lifecycle-controls.tsx` in `pages\mandates.tsx`, `paper.tsx` and `research.tsx`; separate scopes/references/head confirmations, archive recovery/status, collision-safe restore and linked replacement with deliberate future run/backtest actions (depends on T097, T104, relevant US1/US2 UI).

### Required acceptance

- [ ] T106 [US4] Run actual Windows/Linux lifecycle/locking/atomic-journal interruption/race tests in `hedge_fund\runtime\test_native_lifecycle.py` against fake providers and test-owned processes, including concurrent CLI/browser/runner/research and account transfer; record `specs\005-web-engine-migration\lifecycle-platform-evidence.md` with no broad removal/duplicate effects (depends on T095–T105, T006, US5 T118).
- [ ] T107 [US4] Run co-located lifecycle/deployment/fund/SIM/research/web/CLI regressions, React unit/build and `frontend\e2e\lifecycle.spec.ts`; record exact fixture sibling retention/stopped restore/linked replacement/exclusive fake account outcomes in `specs\005-web-engine-migration\us4-evidence.md` (depends on T106, T098, US5 T118).
- [ ] T108 [US4] Update C05/C18/D14/D15/F11 plus all affected SIM/account/lifecycle FRs and moved funds/paper assertions in `specs\005-web-engine-migration\acceptance-matrix.md` and `retired-assertions.md`; actual web-local-paper acceptance and explicit headless SIM exception stay distinct (depends on T107).

## Phase 8: User Story 5 — Observe honest valuation and research (P2)

**Goal:** explicitly authorized estimated valuation, durable bounded canonical backtests,
complete discoverable reports/exports and honest data/grid/provenance labels.
**Independent test:** fake quotes/backtest stage callbacks and known canonical signed/
fractional/cost/scorecard fixtures; no observation-triggered call, partial NAV never complete,
lost response/restart/cancel never repeats work, paginated malformed research stays visible.
**Coverage:** FR-003/015–017/023–025/045–055, C3/O5; E01–E03, F01–F10/F12/F13.

### Mandatory tests

- [ ] T109 [P] [US5] Add valuation authorization/signed precision/cash/coverage/stale/head/late response and recorded-series-unchanged regressions in `hedge_fund\web\test_valuation.py`; fake quotes beneath actual policy, network-disabled/unauthorized paid denial must invoke no provider even on poll/mount/reconnect.
- [ ] T110 [P] [US5] Add canonical backtest review/dates/universe/default/capture/grid label/progress/cancel/interruption/idempotency regressions in `hedge_fund\backtesting\test_fund.py` and `hedge_fund\web\test_jobs.py`; cap before next fake call and preserve result discovery without automatic worker resumption.
- [ ] T111 [P] [US5] Add report/research bounded pagination/search/malformed identity/export precision and malicious inert text tests in `hedge_fund\backtesting\test_research.py`, `hedge_fund\web\test_reports.py` and `hedge_fund\reporting\test_console.py`; cover all proposed/executed allocations/clamps/orders/fills/cost/tape/theses/NAV/benchmark/analyst-strategy metrics.
- [ ] T112 [P] [US5] Add valuation/backtest/research/report React unit tests in `frontend\src\pages\research.test.tsx`, `backtests.test.tsx` and `frontend\src\components\valuation-panel.test.tsx`; distinguish current estimate/recorded/partial/stale, daily-grid/non-point-in-time labels, durable job links, safe cancel, stale response and lossless downloads.
- [ ] T113 [P] [US5] Add real-browser valuation/research/report scenarios in `frontend\e2e\research.spec.ts` against guarded fake quote/backtest fixtures for explicit refresh authorization, partial/short/fractional values, progress/reload/interruption/cancel, >100 result pagination/malformed records and inert report exports.

### Implementation

- [ ] T114 [US5] Implement explicitly admitted valuation estimate service in `hedge_fund\web\valuation.py` and `hedge_fund\web\services.py`; bind root/deployment/head/provider/call-budget request, preserve signed/fractional cash precision, include per-ticker print/time/freshness/coverage and never write recorded NAV/benchmark/metrics (depends on T109, T017–T018, T051–T053).
- [ ] T115 [US5] Implement observational valuation GET and reviewed refresh routes in `hedge_fund\web\app.py` and `hedge_fund\web\schemas.py`; offline/partial/stale/error labels, no auto refresh/paid polling, obsolete request/head result cannot replace newer estimate and secret-free estimate exports (depends on T114).
- [ ] T116 [US5] Adapt canonical `hedge_fund\backtesting\fund.py` progress/warming/stage/agent/thesis callbacks and safe cancellation boundaries without TUI renderables or new simulation algorithm; retain daily-grid minute semantics, fixed code-stamp/provenance and authoritative cash/sizing (depends on T110, T013).
- [ ] T117 [US5] Implement full backtest preview/capture/dates/universe/budget admission and durable job/progress/cancel/interrupted/result links in `hedge_fund\web\services.py`, `web\jobs.py` and `web\schemas.py`; independent capacity excludes runner lifetime, unknown upper-bound paid cost denies, no restart/reconnect retry (depends on T110, T116, T018, T053).
- [ ] T118 [US5] Implement stable bounded cursor/search/reopenable research catalog with malformed-record errors and canonical persisted identities in `hedge_fund\backtesting\research.py` and `hedge_fund\web\services.py`; remove current 100-only browsing limitation, coordinate US4 archive refs without altering independent result history (depends on T111, T117, T103 interface).
- [ ] T119 [US5] Implement complete canonical session/day/research/scorecard report and JSON/download adapters in `hedge_fund\reporting\reports.py`, `hedge_fund\web\services.py` and `hedge_fund\web\app.py`; preserve proposed/executed allocations/risk/clamps/weights/orders/fills/spread/commission/tape/theses/cash/NAV/benchmark/metrics with inert text and exact numeric provenance (depends on T111, T116–T118).
- [ ] T120 [US5] Implement `frontend\src\components\valuation-panel.tsx` in `pages\paper.tsx` with explicit reviewed refresh, provider authorization/estimate budget, per-ticker freshness/partial coverage and separate recorded series; discard obsolete responses and never let formatting feed authoritative records (depends on T112, T115).
- [ ] T121 [US5] Implement durable backtest review/progress/cancel/reload and research pagination/search/reopened report views in `frontend\src\pages\backtests.tsx` and `research.tsx`; show captured settings, finite caps, daily-grid replay/non-point-in-time caveats and actual interrupted/cancel boundary status (depends on T112, T117–T119).
- [ ] T122 [US5] Integrate complete paper/research report drilldowns, scorecards and canonical downloads in `frontend\src\pages\paper.tsx`, `research.tsx`, `components\data-table.tsx`, `equity-chart.tsx` and `hedge_fund\test_run.py`; verify browser plus headless JSON/stdout/output-file precision without secret/browser-round-trip pollution (depends on T111–T112, T119–T121).

### Required acceptance

- [ ] T123 [US5] Run actual Windows/Linux bounded research worker restart/fencing/cancel/capacity tests in `hedge_fund\runtime\test_native_jobs.py`, including runner lifetime/Halt/verdict concurrency; record exact interrupted/surviving-worker/result/cancel boundary evidence in `specs\005-web-engine-migration\jobs-platform-evidence.md` (depends on T109–T122, T006, T067).
- [ ] T124 [US5] Run isolated valuation/backtest/research/report/runtime/web/headless regressions and fake endpoint/budget denial; record exact partial/stale/signed value/cash/report byte/provenance/pagination/grid/secret outcomes in `specs\005-web-engine-migration\us5-evidence.md` (depends on T123).
- [ ] T125 [US5] Run React unit/build and `frontend\e2e\research.spec.ts` with guarded fake callbacks/quotes and >100 synthetic research records; append real browser refresh/progress/reload/cancel/exports/keyboard outcomes to `specs\005-web-engine-migration\us5-evidence.md` (depends on T113, T120–T124).
- [ ] T126 [US5] Update individual E01–E03/F01–F10/F12/F13, FR-045–052 and moved backtest/paper-view/report/scorecard assertions in `specs\005-web-engine-migration\acceptance-matrix.md` and `retired-assertions.md`; daily-grid and headless console/export exceptions are explicit, incomplete NAV or interrupted job is not a completed result (depends on T124–T125).

## Phase 9: Polish & Cross-Cutting Acceptance

**Purpose:** candidate convergence/full-suite/multi-pass QA before TUI removal, then
fresh final revalidation/re-review and an unmerged main-targeting implementation PR.
This phase is split by the destructive US6 gate; dependency order, not numeric order
alone, determines execution. No optional tests or unverifiable platform exemptions.

- [ ] T127 Reconcile FR-001–FR-062, SC-001–SC-010, all 74 capability rows, contract G/R/A/O/C clauses and 15 finding IDs in `specs\005-web-engine-migration\acceptance-matrix.md`; perform implementation convergence, add explicit executable gap/remediation tasks to `tasks.md` without checking missing work done, and require new tests for every remaining non-exempt seam (depends on US1 T044, US2 T062, US3 T076, US4 T108, US5 T126 and US6 candidate T087–T089).
- [ ] T128 Run isolated complete `poetry run pytest hedge_fund -q` on the candidate, existing React Vitest/build/Playwright and changed-source black 420/isort/flake8 checks; record commands/full output/exit/interrupt status in `specs\005-web-engine-migration\full-suite-evidence.md`, never call interrupted cleanup a pass or use historical suite counts (depends on T127).
- [ ] T129 Individually reproduce each candidate full-suite failure on pre-feature revision `6443490db64056742fbbe6a18abf92c903c10861` using identical isolated synthetic fixtures/platform/code stamps in a checkout-owned comparison workspace; record exact test ID/expected/observed/revision/build/time/provenance/exclusions in `specs\005-web-engine-migration\baseline-evidence.md`, never blanket-waive Windows strftime/rename/signal/mode or fix unrelated baseline defects (depends on T128).
- [ ] T130 Perform an independent ledger/money QA pass over candidate diffs, canonical replay/cash/approval/reconciliation/admission/budget and acceptance evidence; record source-bound high-confidence findings and pass/fail/blocked obligations in `specs\005-web-engine-migration\qa-ledger-money.md`, adding actionable remediation tasks for defects rather than accepting design-only LM closures (depends on T128–T129).
- [ ] T131 Perform a separate independent local-boundary QA pass over root/legacy/namespace/OS ownership/ACL/endpoint DNS-TLS/credential/observer/package/import closure with native evidence; record exact findings and required reopened rows in `specs\005-web-engine-migration\qa-local-boundary.md` (depends on T128–T129; distinct from T130).
- [ ] T132 Perform a separate independent human/model-control QA pass over single-use confirmation/due-set/finite authorization/active approval warning/cancel/restart/complete editor/accessibility and six-journey evidence; record `specs\005-web-engine-migration\qa-human-control.md`, require all T130–T132 defects fixed test-first with targeted revalidation before candidate T090, and rerun affected independent reviews after those fixes.
- [ ] T133 After destructive retirement and T093 revalidation, conduct independent final source-bound re-review of all fixes and final full-suite/platform/browser/package/assertion evidence, reopen affected rows and record `specs\005-web-engine-migration\qa-final.md`; any new failure/blocked criterion prohibits T094 readiness (depends on T130–T132, T091–T093).
- [ ] T134 Update final tested commands/migration cautions/support/exemptions/evidence links in `README.md`, `hedge_fund\README.md`, `specs\005-web-engine-migration\quickstart.md` and `docs\governance\web-migration-contract.md` only where implementation clarified spelling, never rewrite historical spec/discovery or claim unsupported SIM/cross-namespace/network-filesystem parity (depends on T094, T133).
- [ ] T135 Publish a new implementation PR targeting `main` using explicit `gh -R cgjedrem/ai-hedge-fund` repository selection, retaining plan-review PR #8 evidence and all source-bound acceptance/QA/retirement links in `specs\005-web-engine-migration\implementation-handoff.md`; if another authorized implementation branch is needed choose it explicitly in that later workflow, never replace/merge the documentation PR or merge either PR autonomously (depends on T094, T133–T134).
- [ ] T136 Verify final exact changed-file manifest, clean commit/log/remote/PR state and no test-owned process/server/fixture leakage, record accepted or blocked deliverables and unsupported exemptions in `specs\005-web-engine-migration\implementation-handoff.md`; preserve pending tasks/failed evidence honestly, close no unsupported gate and stop without merging (depends on T135).

## Dependencies & execution order

### Phase/story graph

```text
Setup T001–T006
  → Foundation T007–T024 (blocks all mutation stories)
    → US1 implementation/acceptance T025–T044
    → US2 core config/editor T045–T059 → runner adoption acceptance after US1 → T060–T062
    → US3 T063–T076 after US1; fake SIM acceptance waits for US4 T099
    → US4 core T095–T105 after US1/US2; research refs acceptance waits for US5 T118
    → US5 T109–T126 after config and durable operations; no dependency on US4 acceptance
    → US6 non-destructive candidate T077–T086 in priority order as seams become ready
US1–US5 acceptance + US6 candidate native/browser T087–T089
  → convergence/full-suite/baseline/three QA passes T127–T132
  → candidate retirement gate T090
  → remove TUI/dependencies T091–T092
  → fresh complete native/full-suite/browser revalidation T093
  → independent final re-review T133
  → final readiness or fail-closed decision T094
  → final docs/implementation PR/handoff T134–T136 (never merge)
```

US6 remains P1, placed before P2 story sections as required by priority; its destructive
gate is intentionally delayed. US1 is the MVP, not a retirement-ready product.
US2 core editor/settings can be tested independently with frozen fixtures; runner adoption
needs US1. US3 controls need US1 admission/ownership; native fake SIM compatibility waits for
US4 account binding, not vice versa. US4 core archive/deploy tests are independent of
research execution; full research reference acceptance waits for US5. US5 uses US4's
archive coordination interface, not completed US4 acceptance, avoiding a cycle.

### Additional task prerequisites (in addition to inline dependencies)

- Setup: T001 → T002 → T003 → T006. T004 and T005 may run independently in parallel.
  All foundation tests depend on T002, T004–T006; browser-related work also needs T003.
- Foundation: T007–T011 are independent test authoring. Each implementation follows its
  red tests; T020 is post-envelope regression, not permission to defer denial tests.
  T021 writer integration precedes enabling any new story mutation. T024 depends on all
  foundation tasks and records platform gating, not a guessed universally enabled mode.
- US1 T025–T029 start after T024. T025–T027 → T030–T037; T028 → T038–T039;
  T029/T040 plus implementations precede T041–T044. Browser closure tests exercise native
  owner through fixture server, not a fake route-only runner.
- US2 T045–T049 start after T024; T045/T047 → T050–T053; T046 → T054–T056.
  T057 follows backend settings; T058 follows both UI branches. T059 is mandatory
  native ACL evidence, not a best-effort omission. T060 adoption depends on T044;
  its deploy/backtest action wiring is accepted only when T104/T117 also exist.
- US3 tests start after T044. T064 → T068; T063–T064 → T067/T069;
  T070/T074 fake SIM cases additionally need T099. No T099 dependency on T074.
- US4 tests/core start after T044 and T055; T096 → T099 → T100–T104.
  T101 lifecycle interface → T103 research archive coordination → T118 final research
  catalog integration → T106/T107 final races; T118 does not depend on T107/T108.
- US5 tests/core start after T024 and T053; T110 → T116–T117; T111 → T118–T119.
  T118 consumes the T103 interface; native job Halt test T123 also needs T067.
  No US5 task requires completed US4 acceptance.
- US6 T077–T080 test authoring starts after T024, but T077 extension of shared
  `test_run.py` is serialized after US1/US3/headless writers; T083 integrates story UIs
  only after their implementation. T084 free-data packaging follows T052. T086 commands
  follow implemented flag spellings, not copied proposed examples.
- T087–T090 require US1 T044, US2 T062, US3 T076, US4 T108 and US5 T126.
  T090 additionally requires T127–T132 including test-first remediation/re-review;
  T128 is pre-removal full suite and T093 is fresh post-removal full suite. T133 precedes
  T094; final acceptance cannot use a candidate source stamp after fixes/removal.
- QA T132 follows T128–T129 for its own pass. Before T090, all three independent QA
  passes and any remediation/re-review must be closed with evidence. T133 follows all
  final fixes/revalidation, never only the initial review.

### Co-located/shared file ownership

| Shared seam / exact files | Owning order / required coordination |
| --- | --- |
| `hedge_fund\run.py`, `test_run.py`, `paths.py` | T012/T013/T021 → US1 T036/T040 → US3 T070 → US4 T104 → US5 T122 → US6 T077/T081/T091. Do not parallel-edit CLI entry or assertions across stories. |
| `hedge_fund\web\app.py`, `schemas.py`, `services.py`, adjacent `test_app.py`/`test_actions.py`/`test_services.py` | Foundation T019–T021 owns common envelope; merge story-owned runner/config/control/lifecycle/research adapters serially. Re-run affected common guards after each merge. |
| `hedge_fund\web\jobs.py`, `test_jobs.py`, `runtime\operations.py` | Foundation durable protocol → US1 manual/recovery → US4 archive refs interface → US5 bounded research → native restart acceptance. No independent mutable job registry. |
| `hedge_fund\paper\tick.py`, `ledger.py`, `runner.py` and adjacent tests | Foundation writer integration → US1 canonical schedule/runner → US3 vote/redo/reconciliation → US4 lifecycle admission. Domain fixture/code stamps are shared, not duplicated trading logic. |
| `hedge_fund\fund\spec.py`, `storage.py`, adjacent tests; `paper\deployed.py` | US2 full editor/template validation → US4 immutable deploy/account/lifecycle. Existing snapshot/serialization assertions remain authoritative. |
| `hedge_fund\backtesting\research.py`, `test_research.py` | US4 T103 defines archive/ref interface → US5 T118 adds stable catalog/pagination → US4/US5 joint final acceptance. |
| `frontend\src\pages\paper.tsx`, `research.tsx`, `builder.tsx`, `settings.tsx`, `lib\hooks.tsx`, `types.ts` | Foundation typed no-retry client → owning story UI → dependent journey wiring → US6 accessibility integration. Shared pages/hooks/types are serialized, not `[P]` implementation tasks. |
| `hedge_fund\runtime\credentials.py`, `llm\client.py`, `data\__init__.py` | Foundation captures/policy → US2 private store/endpoints/free default; all later operations reuse them. Native ACL/dispatch tests co-located, no TUI credential backdoor. |
| `pyproject.toml`, `poetry.lock`, static assets/Docker/Make/READMEs | US2 free default dependency → US6 staged candidate packaging → candidate proof → final dependency/TUI removal → fresh final docs. Do not edit lock/manifests concurrently. |
| `acceptance-matrix.md`, `retired-assertions.md`, evidence docs | Each story submits evidence, one owner reconciles shared matrices serially. A test file mapping alone is not individual assertion acceptance. |

### Parallel opportunities/examples per story

All examples are **test authoring after prerequisites**, not parallel privileged execution
or parallel edits of shared implementation files. Existing OS-safe validation can then use
one runner for related selectors rather than redundant suites.

- **Setup:** T004 matrix and T005 retired-assertion inventory are distinct documents.
- **Foundation:** T007 root, T008 neutral output, T009 admission, T010 capture/policy and
  T011 journal tests have distinct files; implementations follow the explicit graph.
- **US1:** author T025 ownership, T026 domain schedule, T027 writer races, T028 React
  control units and T029 `frontend\e2e\operations.spec.ts` together after T024.
- **US2:** author T045 settings/credentials, T046 domain editor, T047 endpoint, T048
  React editor/settings and T049 `frontend\e2e\configuration.spec.ts` together.
- **US3:** author T063 domain votes/redo, T064 reconciliation, T065 decision-control
  units and T066 `frontend\e2e\recovery.spec.ts` together after US1 and shared files settle.
- **US6:** author T078 observer, T079 accessibility and T080 distribution tests together;
  T077 shared CLI/report tests wait for their owners. Run complete accessibility only
  after all six journeys exist; no assumed browser/tool availability.
- **US4:** author T095 lifecycle/deploy, T096 account binding, T097 lifecycle-control
  units and T098 `frontend\e2e\lifecycle.spec.ts` together after US2 storage tests settle.
- **US5:** author T109 valuation, T110 canonical research, T111 report/catalog,
  T112 React observation/research and T113 `frontend\e2e\research.spec.ts` together after
  the US4 shared research interface and US1 shared job tests settle.
- **Independent QA:** T130–T132 are distinct evidence lenses; each must be independent
  of implementation authors and retain complete findings. Execution order/capacity can
  be chosen in the later authorized workflow; no nested delegation is needed here.

## Requirement/capability coverage index

This index allocates every discovery ID; T004/T127 must expand ranges into **individual**
rows with exact named test IDs/outcomes. It is not a runtime acceptance claim.

| Discovery IDs | Tasks / story acceptance | Requirement allocation / explicit exception |
| --- | --- | --- |
| A01/A02/A04/A07 | T077–T094 | FR-001/002/004/005/056/062; launch, keyboard, package, removal evidence. |
| A03/A05 | T038–T044, T114–T125 | FR-003/009/028/035/045; recorded catalog, active refresh and estimate provenance. |
| A06 | T063–T076 | FR-037; safe corrupt-control Halt/verified Resume. |
| B01–B11 | T045–T062, T033/T040 | FR-018–025/056; complete frozen private config, readiness, local/default/endpoint policy. |
| B12 | T058/T062/T096/T099/T070/T087–T088 | FR-027 plus G4: redacted browser readiness, **headless non-TUI SIM provisioning/control exemption**, exclusive account evidence mandatory. |
| C01–C04/C06–C08/C10–C17 | T045–T062 | FR-028–034; complete registry/editor/revision/cadence/custom composition and next actions. |
| C05 | T046/T056/T058/T095/T100/T104–T108 | FR-029/034/040; distinct capital/universe/template/deployment identity. |
| C09 | T046/T054/T058/T062/T096/T099 | FR-027/029/032 plus G4: broker editor/readiness with fakes, SIM browser mutation explicitly exempt not accepted parity. |
| C18 | T095/T101–T108 | FR-041/043; reversible template archive instead of broad wipe. |
| D01–D06/D08/D09/D11/D16 | T025–T044, T119–T126 | FR-003/006–017/024/050; owned runner/manual/daily/backfill/progress/records/diagnostics; D09 headless date/output compatibility retained. |
| D07 | T026/T032/T041–T044/T070/T099 | FR-014/032 and G4; canonical minute/market/gap/lateness with headless fake SIM cutoff, no claim of SIM browser execution. |
| D10/D12/D13 | T063–T076 | FR-013/036–039; latest redo/Halt/Resume, no implicit run, ambiguity reconciliation. |
| D14/D15 | T095–T108 | FR-041–043; scoped archive/stopped restore/distinct replacement. |
| E01–E03 | T109/T114–T115/T120/T123–T126 | FR-025/045/046; explicit estimate with per-ticker coverage/freshness, no recorded contamination. |
| E04–E08 | T063–T076 | FR-003/017/035–039; source-bound votes/states/separate Run/source-execution redo/post-fill failures. |
| F01–F09 | T110–T113/T116–T126 | FR-015–017/023–025/047–050/054–056; review, stage/cancel/interruption, canonical reports, stable >100 catalog. |
| F10/F12 | T008/T013/T077/T087–T093/T111/T119/T122–T126 | FR-004/050/051/056; complete browser scorecards/downloads and **retained headless console/stdout/output-file exception** without Textual. |
| F11 | T095/T101/T103/T106–T108/T118 | FR-041/043; exact research archive with active-reference coordination. |
| F13 | T110/T116–T117/T121/T124–T126 | FR-052: explicit **daily-grid minute research**, historical intraday engine excluded, not hidden parity. |
| Expanded helper/Docker/Make/CLI/dependency assertions | T005/T008/T013/T050/T077–T094 | FR-004/005/053/056/062, R4/R5/A4; individual assertion replacement before removal. |
| Cross-cutting all rows | T001–T024/T127–T136 | FR-006/007/044/053–062, SC-001–010; isolation, authority, evidence, convergence/full suite/independent QA/main PR never merged. |

### Forward red-team resolution implementation index

- LM1 → T009/T014–T015/T021–T022/T027/T037/T106 (all writers/legacy/locks/recovery).
- LM2 → T025/T030–T032/T041–T042/T078/T082/T085/T087–T088 (namespace/topology/ownership).
- LM3 → T064/T067–T075 (post-fill reconciliation, not replay alone).
- LM4 → T026/T033/T038/T095/T102/T105–T108 (exact bounded backlog/stopped restore).
- LM5 → T058/T062/T070/T096/T099/T104/T108/T087–T088 (SIM exemption/exclusive binding).
- LB1 → T001–T003/T007/T012/T016/T021/T040/T077 (fixed root/import/child/dotenv).
- LB2 → T019–T020/T078/T082/T085/T088 (observer loopback/no capability elevation).
- LB3 → T047/T051/T109/T114/T124 (host-bound endpoint/DNS/TLS/no validation calls).
- LB4 → T045/T050/T057/T059–T062 (atomic private credentials/delete/frozen/ACL).
- LB5 → T007/T012/T022/T041–T042/T059/T106/T087–T088 (actual supported filesystems).
- HM1 → T004/T024/T127–T136 and candidate/final US6 gates (amended design, strict evidence).
- HM2 → T010/T017/T045/T051–T053/T060/T084 (free default/all-cloud paid, no env/key auth).
- HM3 → T010/T017/T032–T033/T110/T117/T123–T124 (finite sessions/calls/resources/budget).
- HM4 → T011/T018/T025/T030–T037/T041–T043/T110/T123 (detached ownership/durable restart).
- HM5 → T011/T018/T027/T033/T063–T076/T095/T101–T105 (single-use exact identity/control).

## Implementation strategy

### MVP first (US1 only, not retirement)

1. Obtain separate implementation authority and complete safe Setup/Foundation.
2. Implement US1 test-first vertical slices: root/admission → durable preview/capture →
   owned runner → canonical manual → no-retry browser observation.
3. Run mandatory targeted, native and browser acceptance, record exact independent results.
4. Demonstrate synthetic local-paper operation only. Do not retire the TUI, claim SIM
   browser control, enable paid/cloud scheduled work or skip any future parity/platform row.

### Incremental complete delivery

Add US2 editor/config/private captures, US3 recovery/votes, US4 reversible lifecycle and
US5 honest research/valuation while assembling non-destructive US6 distribution/observer/
accessibility candidates. Revalidate affected shared seams at each merge. Finish individual
assertion and 74-ID convergence, candidate full suite/baseline and three independent QA
passes before the removal gate. Remove only after required candidate evidence passes,
then obtain fresh final native/full-suite/browser evidence and independent re-review.
Publish an explicitly main-targeting implementation PR, keep it and plan PR unmerged.

### Mandatory evidence and blocked work

Run smallest related selectors first, then affected shared regressions/build/browser/native,
then the full suite at candidate and final gates. Examples in `quickstart.md` are prospective
and unsafe until T001–T003 establish isolation; never execute current global-root/compose/
8765 defaults as acceptance. Tool/runtime availability must be checked and recorded, not
invented. A platform/tool failure, missing required Linux runtime, uncertain ACL/ownership,
inconclusive interruption or irreconcilable fill history is blocked/failing evidence, never
an optional test or pass. Per-test pre-feature baseline proof is the sole permitted
unchanged-failure classification; it grants no blanket platform exemption.

## Generated-list validation

136 sequential pending checklist tasks: Setup 6, Foundation 18, US1 20, US2 18, US3 14,
US6 18, US4 14, US5 18, Polish 10. There are 34 distinct-file `[P]` opportunities.
All story-phase tasks carry their exact spec story label, including P1 US6 before P2
sections; setup/foundation/polish carry no story labels. Every task includes concrete
paths, required tests/evidence are non-optional, all six independent test criteria are
stated, and retirement/removal dependencies are explicit rather than implied by list order.
