# Tasks: Local React Trading Desk

**Input**: spec.md, plan.md, research.md, data-model.md, contracts/.
**Gate**: Spec/plan clean, committed, pushed and under open PR #7 targeting main on 2026-10-30. Red-team constraints resolved before implementation. User authorized autonomous decisions; no merge.
**Tests**: Required, isolated/fake-backed, co-located Python and frontend tests.

## Phase 1: Setup

- [x] T001 Add web optional dependencies/entry point and locked frontend scaffold in pyproject.toml, poetry.lock, frontend/package.json and frontend/package-lock.json.
- [x] T002 Configure TypeScript/Vite/Tailwind/shadcn and local dark theme in frontend/components.json, frontend/vite.config.ts and frontend/src/index.css.

## Phase 2: Foundation

- [x] T003 Add root/capability/path/Host/Origin/token negative tests in hedge_fund/web/test_app.py.
- [x] T004 Implement app factory, guarded schemas and static serving in hedge_fund/web/app.py, hedge_fund/web/schemas.py and hedge_fund/web/__main__.py.
- [x] T005 Add synthetic demo data and network-denying fixtures in hedge_fund/web/demo.py and hedge_fund/web/conftest.py.

## Phase 3: US1 - Inspect the Desk (P1 / MVP)

**Independent test**: Seeded fund -> detail -> session report -> scorecard with matching recorded values and no network.

- [x] T006 [US1] Test mandate/paper/session/research/scorecard reads and corrupt-state reporting in hedge_fund/web/test_services.py.
- [x] T007 [US1] Implement thin canonical read/metric/forecast/report adapters in hedge_fund/web/services.py.
- [x] T008 [US1] Implement home, funds and paper master/detail with chart, holdings, sessions and reports in frontend/src/pages/.
- [x] T009 [US1] Implement scorecards/research report views and loading/error/empty states in frontend/src/pages/.
- [x] T010 [US1] Add read navigation/value/report tests in frontend/src/App.test.tsx.

## Phase 4: US2 - Deliberate Paper Operations (P1)

**Independent test**: Temporary fund verdicts use original mailbox; stale/protected/readonly actions denied before fake adapters.

- [x] T011 [US2] Test timestamp+hash stale/expired approvals, halt/resume and process ownership denials in hedge_fund/web/test_actions.py.
- [x] T012 [US2] Implement guarded mailbox/halt adapters and safe runner lifecycle or explicit unsupported reasons in hedge_fund/web/services.py.
- [x] T013 [US2] Add confirmation/pending/error controls and disabled-action explanations in frontend/src/pages/.

## Phase 5: US3 - Build and Research (P2)

**Independent test**: Create/deploy to temporary root, fake-backed backtest and reopen persisted report.

- [x] T014 [US3] Test builder cadence validation/name conflicts and bounded fake-backed research jobs in hedge_fund/web/test_jobs.py.
- [x] T015 [US3] Implement canonical mandate create/deploy and backtest job adapter in hedge_fund/web/services.py and hedge_fund/web/jobs.py.
- [x] T016 [US3] Implement builder wizard and backtest progress/results in frontend/src/pages/.
- [x] T017 [US3] Add form/conflict/failure frontend tests in frontend/src/App.test.tsx.

## Phase 6: US4 - Settings and Navigation (P2)

**Independent test**: Keyboard navigation plus write-only sentinel credential with no response/log leaks.

- [x] T018 [US4] Test allowlisted model/key settings and control-character rejection in hedge_fund/web/test_settings.py.
- [x] T019 [US4] Implement safe settings adapters in hedge_fund/web/services.py.
- [x] T020 [US4] Implement settings dialogs and shadcn command palette with input-safe shortcuts in frontend/src/pages/ and frontend/src/components/.

## Phase 7: Packaging, QA and Evidence

- [x] T021 Add one-command launcher, Compose web service/Linux override, Dockerfile.web and README.md instructions.
- [x] T022 Run affected API/frontend/build/changed-file style checks and chunk existing-suite checks; record exact passes, platform failures, and exclusions in specs/004-react-web-ui/acceptance-evidence.md.
- [x] T023 Capture production-build browser desktop/narrow screenshots, every screen and real-fund read-only checks in frontend/e2e/ and specs/004-react-web-ui/acceptance-evidence.md. Cycle 2: 17 synthetic screenshots refreshed; read-only browser checked 18 available real-root routes, all HTTP 200 with no UI/API errors. No live research report existed (0 saved reports); synthetic E2E covered report detail. Protected-root byte identity remains intentionally INCONCLUSIVE and was not fingerprinted.
- [ ] T024 Complete independent QA dev loop, rerun affected final-artifact evidence, and update parity/gaps in specs/004-react-web-ui/acceptance-evidence.md.
- [ ] T025 Update PR #7 with self-contained run instructions/screenshots/parity/assumptions/limitations and leave safe read-only preview running.

## Dependencies and Execution Order

T001-T002 -> T003-T005 -> each story. US1 establishes shared presentation/data contract for US2-US4 integration; each story's backend tests are independently seeded. T021 after entry points exist; T022-T023 after desired stories; T024 after implementation and again after repairs; T025 after final QA. Sequential specialists by coordinator policy.

## Parallel Opportunities

Independent API/frontend commands may run together after contract stabilization. US1 API read tests and frontend renderer tests use independent fixtures; US2 safety tests and confirmation rendering tests likewise. US3 backtest fake tests and wizard tests, US4 credential and palette tests are independent. No parallel source owners or broad staging.

## Implementation Strategy

Deliver US1 MVP first, then safe action/builder/settings slices with tests before implementation. Keep TUI intact. Commit logical phases with named-file staging. Do not mark a deferred action as implemented: record explicit parity gaps and disable unsafe controls. Runtime acceptance requires final revision/build/time/environment/scenario/provenance, not static review alone.
