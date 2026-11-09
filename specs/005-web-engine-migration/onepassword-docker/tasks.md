# Tasks: 1Password runtime secrets for the Docker desk

**Input**: This directory's spec/plan/research/data-model/contracts/quickstart.
**State**: Implementation authorized; tasks remain unchecked until evidenced.
**Count**: 12 remaining tasks; 0 executed. IDs are local to this unnumbered extension,
not replacements for parent Spec005 T001-T134 or W01-W09.
**Tests**: Required by OP-FR-014 and OP-SC-005; use red-green slices and fake adapters only.
Proposed new filenames below are implementation targets, not claims that these files exist.

## Phase 1: Setup

- [ ] T001 Record approved runtime-only compatibility, assumed attended auth, empty initial provider allowlist, and implementation authorization in `specs\005-web-engine-migration\onepassword-docker\plan.md`; reconcile the pinned Spec005 basis in this authorized local integration, preserve main's Yahoo news fix, bind final revision and enumerate exact new test node IDs in `quickstart.md`.

## Phase 2: Foundation

- [ ] T002 Specify and test source-typed external runtime handle validation, root/instance/destination binding, private metadata and forbidden durable serialization in proposed `hedge_fund\runtime\external_credentials.py` and `hedge_fund\runtime\test_external_credentials.py`; integrate the discriminator with `hedge_fund\runtime\capture.py` without changing durable saved-credential mode.

## Phase 3: US1 - Keep free paper operation secret-free (P1; safety MVP)

**Goal**: Disabled integration leaves free/local work unchanged.
**Independent test**: No mappings, fake locked/missing CLI, free/local operation: zero
resolver calls, zero paid clients, zero inherited keys.

- [ ] T003 [US1] Add initially failing disabled/keyless/decoy-dotenv and owned-runner inheritance cases to `hedge_fund\runtime\test_external_credentials.py`, `hedge_fund\runtime\test_configuration.py` and `hedge_fund\runtime\test_capture.py`, with exact row OP-A01/OP-A04 assertions.
- [ ] T004 [US1] Implement opt-in empty-allowlist source selection and non-fallback guards in `hedge_fund\runtime\external_credentials.py` and `hedge_fund\runtime\configuration.py`; preserve `hedge_fund\runtime\owned_runner_child.py` free/local restrictions and pass T003 without adding a TUI/runner injection path.

## Phase 4: US2 - Authorize only the selected backend (P1)

**Goal**: One explicitly approved fake credential reaches one eligible backend.
**Independent test**: Fake resolver/target, sentinel equality, denied observer/root/provider,
bounded failure and zero exposed sentinel occurrences.

- [ ] T005 [US2] Add failing fake-resolver/transport/denial/framing/status tests in proposed `hedge_fund\secrets\test_docker_delivery.py`, `hedge_fund\runtime\test_external_credentials.py` and existing `hedge_fund\web\test_settings.py`; cover OP-A03/OP-A05/OP-A06/OP-A07 and no resolver call on initial denial.
- [ ] T006 [US2] Implement proposed `hedge_fund\secrets\docker_delivery.py` host launcher and bounded private resolver capture, strict reference/provider mapping, auth-mode conflict checks, pinned local Docker target and non-TTY stdin framing; reuse sanitized patterns from `hedge_fund\secrets\provider.py` without changing Saxo read/write semantics.
- [ ] T007 [US2] Implement proposed `hedge_fund\runtime\credential_delivery.py` private receiver/helper, atomic memory-lease publication and redacted status; wire explicit-root entry in `hedge_fund\run.py` and explicit captured-key consumption/status in `hedge_fund\web\services.py`/`schemas.py`; forbid raw values in existing job snapshots or child environments and pass T005.
- [ ] T008 [US2] Package only the eligible operator helper/private IPC in `Dockerfile.web` and `docker-compose.yml`/`docker-compose.linux.yml` as applicable to the reconciled Windows plan; verify peer identity, permissions, immutable instance/image/root checks and ext4 topology on a synthetic Windows Docker Desktop artifact, recording OP-A10 in this directory's `acceptance-evidence.md`; stop for redesign if unsupported.

## Phase 5: US3 - Rotate and restart deliberately (P2)

**Goal**: Predictable bounded capture, revocation and no restart resurrection.
**Independent test**: Fake A captured, B refreshed, concurrent revoke, failed refresh, backend
recreated: correct generation isolation, fenced dispatch and explicit reauthorization.

- [ ] T009 [US3] Add failing refresh/revoke/admission races, stale boot, crash/recreate and lost-ack reconciliation cases in `hedge_fund\runtime\test_external_credentials.py` and `hedge_fund\secrets\test_docker_delivery.py`; assert OP-A08/OP-A09 and no latest-value lookup under an old handle.
- [ ] T010 [US3] Implement generation CAS, lifetime release, revoke dispatch fencing, explicit refresh/requires-auth and unknown-outcome status in `hedge_fund\runtime\external_credentials.py`, `hedge_fund\runtime\credential_delivery.py` and `hedge_fund\web\services.py`; pass T009 without automatic polling, secret recovery or app/fund restarts.

## Phase 6: Cross-cutting acceptance and handoff

- [ ] T011 Add and execute synthetic sentinel exposure coverage in `hedge_fund\secrets\test_docker_delivery.py` plus the existing frontend settings/status tests if changed; scan final exported image layers/config/history, Compose/inspect/exec argv/environment, logs/browser/export and durable synthetic volume/writable layer, recording OP-A02/OP-A03/OP-A04/OP-A08 in `specs\005-web-engine-migration\onepassword-docker\acceptance-evidence.md` without storing secret-bearing evidence.
- [ ] T012 Run smallest combined affected pytest/style/frontend checks then repository-required broader acceptance on the final revision; retain Spec005 Linux/W07 regressions, complete all OP-A rows or mark blockers explicitly, obtain independent QA/evidence review, and update this directory's `quickstart.md`/`analysis.md`/`acceptance-evidence.md` and `README.md` with approved local auth/restart instructions; no real-key/provider smoke, push, merge or real-fund cutover without separate authorization.

## Dependencies and execution order

| Task | Actual prerequisites |
| --- | --- |
| T001 | User approval (received); authorized baseline reconciliation |
| T002 | T001 |
| T003 | T002 |
| T004 | T003 |
| T005 | T002 |
| T006 | T005 |
| T007 | T004, T006 |
| T008 | T007; synthetic Windows Docker runtime available |
| T009 | T007 |
| T010 | T009 |
| T011 | T008, T010 |
| T012 | T011 |

US1 is independently testable without a vault/bridge. US2 uses its regression guard.
US3 builds on the delivered fake bridge; none authorizes a provider call.

## Parallel opportunities and execution policy

No tasks have `[P]`: shared source/test files and target state make parallel editing unsafe.
US1's keyless fake scenario and US2's resolver fake scenario can later be selected together
in one pytest command; US3's race/restart assertions can be checked in that same isolated run
after implementation. These are scenario examples, not parallel specialist spawns.
Current coordinator uses sequential specialists only; do not run concurrent pytest/Docker jobs.

## Incremental strategy and traceability

First prove no new credential dependency (US1); then private fake delivery (US2); then
rotation/restart (US3); finally one final-artifact exposure/platform/evidence gate.

| Requirements | Implementation tasks | Acceptance rows |
| --- | --- | --- |
| OP-FR-001 | T003, T004 | OP-A01 |
| OP-FR-002, OP-FR-003 | T005-T008 | OP-A05 |
| OP-FR-004 | T005-T008, T011 | OP-A02, OP-A03 |
| OP-FR-005 | T003, T004, T007, T011 | OP-A04 |
| OP-FR-006 | T005, T006, T007 | OP-A07 |
| OP-FR-007 | T002, T009-T011 | OP-A08 |
| OP-FR-008 | T002, T007, T009, T010 | OP-A06, OP-A09 |
| OP-FR-009 | T009, T010 | OP-A09 |
| OP-FR-010 | T005, T007, T010, T011 | OP-A03, OP-A07 |
| OP-FR-011 | T005-T007, T009, T010 | OP-A06, OP-A07 |
| OP-FR-012 | T003-T008, T012 | OP-A04, OP-A05, OP-A10 |
| OP-FR-013 | T008, T011, T012 | OP-A08, OP-A10 |
| OP-FR-014 | T001, T003, T005, T009, T011, T012 | OP-A01 and all validation provenance |

Task count by phase: setup 1, foundation 1, US1 2, US2 4, US3 2, cross-cutting 2.
Planning completion does not check off any of these implementation tasks.
