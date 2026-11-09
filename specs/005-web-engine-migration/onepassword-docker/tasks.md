# Tasks: 1Password runtime secrets for the Docker desk

**Input**: This directory's spec/plan/research/data-model/contracts/quickstart.
**State**: Implementation authorized; tasks remain unchecked until evidenced.
**Count**: 8 remaining tasks; T001-T002 and T005-T006 completed. IDs are local to this unnumbered extension,
not replacements for parent Spec005 T001-T134 or W01-W09.
**Tests**: Required by OP-FR-014 and OP-SC-005; use red-green slices and fake adapters only.
Proposed new filenames below are implementation targets, not claims that these files exist.

## Phase 1: Setup

- [x] T001 Record approved runtime-only compatibility, attended-auth assumption, empty initial provider allowlist, and implementation authorization; reconcile pinned Spec005 history while preserving main's Yahoo news fix. Local commits: `95dad8b`, `19b4913`. Auth attempt and final validation are recorded below and in `quickstart.md`.

## Phase 2: Foundation

- [x] T002 Specify and test source-typed external runtime handle validation, root/instance/destination binding, private metadata and value-free durable serialization in `hedge_fund\runtime\external_credentials.py` and `hedge_fund\runtime\test_external_credentials.py`; integrate the discriminator with `hedge_fund\runtime\capture.py` without changing durable saved-credential mode.

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

- [x] T005 [US2] Add fake-resolver/transport/denial/framing/status tests in `hedge_fund\secrets\test_docker_delivery.py`, `hedge_fund\runtime\test_external_credentials.py` and `hedge_fund\web\test_settings.py`; cover fail-closed initial denial and fake delivery. Full OP-A03/05/06/07 scenarios remain partial.
- [x] T006 [US2] Implement `hedge_fund\secrets\docker_delivery.py` host launcher, bounded private resolver capture, strict local mapping config/CLI, auth-mode conflict checks, pinned local Docker target and non-TTY stdin framing. No Saxo semantics changed.
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
Planning completion does not check off implementation tasks. T001-T002 have focused evidence;
T003-T012 remain unchecked because their full scenarios, race/platform/artifact gates or
independent QA are incomplete.

## Implementation checkpoint — 2026-11-09

- Owner: Python implementation; automatic check: focused pytest in one runner.
- Implementation commit: `15fc2d9c62c73e5eb40aec3c0a3a46022a82287c` (local only; no push).
  Its 133,271-byte binary source patch SHA-256 is
  `b9c005969127a269aeb70470cdcab4946f915cf166396817c2863450ec9d58b3`.
- Integrated focused + W07 + web service selection: **255 passed, 1 skipped in 178.94 s**;
  process wall time **181.461 s**, at 2026-11-09T11:27:31.7859045Z. This final run
  includes the provider-allowlist target denial and durable no-fallback tests. The earlier
  affected selection was **83 passed, 1 skipped in 6.81 s**, wall time **9.187 s**, at
  11:20:19Z. Both used Python 3.11.15 / pytest 7.4.4 on Windows; exact commands are in
  acceptance evidence.
- Broader adjacent regression run: **194 passed, 7 failed, 1 skipped in 405.98 s**;
  seven unchanged runner/ledger failures remain unresolved. The malformed-audit failure
  reproduced alone. This is not a full-suite pass and is not independently baseline-proven.
- First host `op whoami` ran at 2026-11-09 11:27:18 +01:00; result: unauthenticated,
  CLI 2.34.1, sanitized reason `desktop-integration-unavailable`, 0.093 s. No prompt
  activity was recorded.
- After the user's integration-enabled report, one follow-up ran at 12:19:34 +01:00;
  result: unauthenticated in 1.070 s, sanitized reason `desktop-account-not-signed-in`.
  The CLI child was hidden with streams redirected; Path of Practice's documented command
  runs in an attached terminal. This is a plausible prompt discrepancy, not confirmed cause
  or proof of desktop sign-out. No further check was run.
- Read-only Path of Practice prior art uses host `op run` environment injection, including
  Compose values forwarded into a backend container. This differs from approved private IPC
  and is not copied. No external repository files or secret config were read or changed.
- A no-config host CLI smoke at 2026-11-09T11:28:52.9090344Z exited 2 in 0.729 s with
  sanitized `provider-not-allowed` output and empty stderr. No mapping or secret was supplied.
- No `op read`, vault/item access, provider/model/broker call, image build, container
  mutation, synthetic Docker runtime scan, push or merge occurred.
- CLI/configuration path is callable and fake-tested; Compose currently bind-mounts `/data`,
  which the host launcher rejects before source resolution. Runtime transport remains fake-
  tested only.
- T007 remains unchecked: receiver, operator lifecycle, and captured-key guard exist, but
  explicit external-source selection/operation wiring and its end-to-end tests are absent.
- T003-T004, T009-T012 remain unchecked because their full disabled/free-local, race/restart,
  artifact/platform and independent-QA scenarios are incomplete. No task is marked complete
  solely because part of its implementation exists.

Stop condition: do not mark remaining tasks complete until their explicit scenarios pass;
OP-A02/03/08/10 remain blocked on final artifact and supported synthetic Windows runtime.
