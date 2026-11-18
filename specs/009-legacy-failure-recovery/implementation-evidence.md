# Spec 009 Implementation Evidence

## Evidence identity and environment

- Baseline: `e6f04d2c76d761a0403f24c4b6adf40db48a8346` (`origin/main` per authored research).
- Implementation starting revision: `0c1854b0c3798fc8c4d2940c5fe5fd6c82fc43a7`.
- Platform: Microsoft Windows 11 Enterprise, version `10.0.26200`, build `26200`.
- Runtime: Python `3.11.15`, Poetry `2.5.1`, pytest `7.4.4`, Pydantic `2.13.4`, FastAPI `0.115.14`; Poetry environment `C:\Users\ChristianGjedrem\AppData\Local\pypoetry\Cache\virtualenvs\aihf-BhBKDBt4-py3.11`.
- Test setup: Poetry and locked dependencies installed after the initial environment lacked Poetry; tests use synthetic enrolled roots and local fakes only. No provider, LLM, broker, paid-credit, or production-root access.
- Initial worktree was clean. Test environment observation recorded `2026-11-17T10:56:47.0605128+01:00`.

## T001 — synthetic fixture probe

- Result: **FAIL** (fixture construction only; acceptance Scenarios A–D remain **INCONCLUSIVE**, not run).
- Recorded: `2026-11-17T10:58:30.3825010+01:00`.
- Source: starting revision `0c1854b0c3798fc8c4d2940c5fe5fd6c82fc43a7`; dirty source diff SHA-256 `21f07d48734c6f9603ffc83a865bf1e3b986789d20201338e2370facd2b1017f` (`5241` bytes).
- Exact command: `poetry run pytest hedge_fund/runtime/test_reconciliation.py::test_legacy_failure_fixture_is_enrolled_and_replays_later_sessions -q`.
- Provenance: automated fake/unit test, pytest output retained in session transcript; no external calls.
- Expected: build an enrolled synthetic fund with three unkeyed failures and replay later synthetic sessions.
- Observed: `1 failed in 3.68s`, exit `1`; `FundSpec` rejected fixture analyst name `a` (`unknown analyst 'a'`; available names included `graham`). No external or production state was accessed.
- Disposition: corrected the synthetic fixture to use the registered `graham` model; passing result is recorded below.

### T001 passing fixture

- Result: **PASS** for the fixture builder only; Scenario A remains **INCONCLUSIVE** until the recovery flow is implemented and exercised.
- Recorded: `2026-11-17T10:59:14.4460236+01:00`.
- Source: starting revision `0c1854b0c3798fc8c4d2940c5fe5fd6c82fc43a7`; `hedge_fund/runtime/test_reconciliation.py` diff SHA-256 `53af8858ca34df98e4bf638461b33c9d56b6e84fb12e264bd0d081ffaab95b55` (`5246` bytes).
- Exact command: `poetry run pytest hedge_fund/runtime/test_reconciliation.py::test_legacy_failure_fixture_is_enrolled_and_replays_later_sessions -q`.
- Provenance: automated fake/unit test, pytest output retained in session transcript; no external calls.
- Expected/observed: `1 passed in 10.00s`, exit `0`; three request-ID-less events precede verified later sessions, all chain to the base head, and replay leaves the empty synthetic broker book in agreement.

### T002 failing-first variant

- Result: **FAIL** as expected before helper implementation.
- Recorded: `2026-11-17T11:00:00.1003523+01:00`.
- Source: starting revision `0c1854b0c3798fc8c4d2940c5fe5fd6c82fc43a7`; `hedge_fund/runtime/test_reconciliation.py` diff SHA-256 `3babcb1b97de2bdb8e417af45d2e1352ea93aae72c26370b04f4d6496f55f7d4` (`5496` bytes).
- Exact command: `poetry run pytest hedge_fund/runtime/test_reconciliation.py::test_legacy_failure_fixture_supports_post_effect_variant -q`.
- Provenance: automated fake/unit test, pytest output retained in session transcript; test failed before any root enrollment or file effect.
- Expected/observed: `1 failed in 0.87s`, exit `1`; `TypeError` confirmed the fixture did not yet accept `post_effect_indices`.
- Next check: add the requested variant helpers and rerun T001/T002 focused tests.

### T005 failing-first decision-record tests

- Result: **FAIL** as expected before T003/T004 implementation.
- Recorded: `2026-11-17T11:03:16.9805610+01:00`.
- Source: phase-1 commit `a4ae12c36c799593db8326508ba245138295bbce`; dirty test diff SHA-256 `dbfb92dfcf668f89a3acf1a363c1d7e3e6826f9059fb05963e33918cf85e49a5` (`4617` bytes).
- Exact command: `poetry run pytest hedge_fund/runtime/test_reconciliation.py::test_legacy_failure_decision_resolves_the_exact_unkeyed_set hedge_fund/runtime/test_reconciliation.py::test_legacy_failure_decision_replay_deduplicates_and_rejects_invalid_sets hedge_fund/runtime/test_reconciliation.py::test_legacy_failure_decision_append_preserves_existing_bytes -q`.
- Provenance: automated fake/unit tests on isolated temporary roots; the append test failed before its ledger write.
- Expected/observed: `3 failed in 25.77s`, exit `1`; all failed at the missing `LegacyFailureReconciliationDecision` import. This establishes the planned T003/T004 behavior was absent before implementation.
- Next check: add the validated decision model, anchored Ledger append method, and fail-closed event replay; rerun decision tests plus legacy receipt regression.

### T005 failing-first rerun before test commit

- Result: **FAIL** as expected before implementation.
- Recorded: `2026-11-17T12:15:17.2598268+01:00`.
- Source: `HEAD` `a4ae12c36c799593db8326508ba245138295bbce`; uncommitted `hedge_fund/runtime/test_reconciliation.py` diff SHA-256 `dbfb92dfcf668f89a3acf1a363c1d7e3e6826f9059fb05963e33918cf85e49a5` (`4617` bytes).
- Exact command: `poetry run pytest hedge_fund/runtime/test_reconciliation.py::test_legacy_failure_decision_resolves_the_exact_unkeyed_set hedge_fund/runtime/test_reconciliation.py::test_legacy_failure_decision_replay_deduplicates_and_rejects_invalid_sets hedge_fund/runtime/test_reconciliation.py::test_legacy_failure_decision_append_preserves_existing_bytes -q`.
- Environment/provenance: Windows; isolated `tmp_path` fixtures; fake/unit tests only; no provider calls or real-data-root access.
- Expected/observed: `3 failed in 29.72s`, exit `1`; each failed with `ImportError` for `LegacyFailureReconciliationDecision` before the append test reached its ledger write.
- Next check: commit only the failing-first tests and this evidence update, then implement T003/T004.

### T001–T002 passing fixture matrix

- Result: **PASS** for setup fixtures only; acceptance Scenarios A–D remain **INCONCLUSIVE** pending the recovery implementation.
- Recorded: `2026-11-17T11:01:29.9539904+01:00`.
- Source: starting revision `0c1854b0c3798fc8c4d2940c5fe5fd6c82fc43a7`; `hedge_fund/runtime/test_reconciliation.py` diff SHA-256 `bd7cb39478d25b6847c1a86e696d14f3589dadf79fa16224410cc2b9dddbde13` (`8163` bytes).
- Exact command: `poetry run pytest hedge_fund/runtime/test_reconciliation.py::test_legacy_failure_fixture_is_enrolled_and_replays_later_sessions hedge_fund/runtime/test_reconciliation.py::test_legacy_failure_fixture_supports_post_effect_variant hedge_fund/runtime/test_reconciliation.py::test_legacy_failure_fixture_supports_corrupt_book_and_head_variants -q`.
- Provenance: automated fake/unit tests on three separate synthetic roots, each enrolled before writes; no providers, LLMs, external broker, or production roots.
- Expected/observed: `3 passed in 27.94s`, exit `0`; fixtures cover unkeyed/no-effect failures, explicit transmitted-fill metadata, verified head advancement, broker-book divergence, and malformed audit bytes.
- T002 failing-first probe disposition: added the missing fixture variant support and helpers; no production write primitive was introduced.

### T003–T005 foundational decision record and replay

- Result: **PASS** for foundational model, append, and replay tests; quickstart Scenarios A–D remain **INCONCLUSIVE** pending the web/API/UI implementation and final suite.
- Recorded: `2026-11-17T12:25:13.6744204+01:00`.
- Source: `HEAD` `b90a5d95f2bd8ed27d88dd81b355683120e1e3d0`; dirty source diff SHA-256 `242eb7a31953a50d72919a6926fc998928461a1465443aef884a67d7eaa608df` (`12529` bytes) for `hedge_fund/paper/ledger.py`, `hedge_fund/runtime/reconciliation.py`, and `hedge_fund/runtime/test_reconciliation.py`.
- Artifact/environment: no built wheel; Poetry executed working-tree source. Microsoft Windows NT `10.0.26200.0`; Python `3.11.15`; Poetry `2.5.1`.
- Exact commands and results:
  - `poetry run pytest hedge_fund/runtime/test_reconciliation.py -q` — `18 passed in 83.34s`, exit `0`.
  - `poetry run pytest hedge_fund/runtime/test_writer_map.py -q` — `119 passed in 6.25s`, exit `0`.
- Scenario/provenance: automated fake/unit tests on isolated enrolled `tmp_path` roots; verified decision validation, exact multi-failure resolution, duplicate replay, unknown/partial-set refusal, invalid-input and missing-lane zero writes, and preservation of pre-existing file bytes. Existing `test_legacy_failure_receipt_replay_preserves_resolution` ran in the reconciliation module. No provider, LLM, broker, paid-credit, or real-data-root access.
- Next check: failing-first US1 preview/confirm tests, then implement the web flow.

### T006–T008 failing-first US1 preview and confirm tests

- Result: **FAIL** as expected before T009–T012 implementation.
- Recorded: `2026-11-17T12:30:42.5674512+01:00`.
- Source: `HEAD` `fb63e62480833f7e41ad7317cf223f8e387377cf`; uncommitted test diff SHA-256 `f327a43c3f0269a6fc8049fa3dacf9babeb432d95b1bcc46e4731025eef8a79a` (`7461` bytes).
- Exact command: `poetry run pytest hedge_fund/web/test_services.py::test_paper_reconciliation_exposes_evidence_for_unkeyed_failures hedge_fund/web/test_recovery.py::test_legacy_failure_confirm_restores_work_readiness hedge_fund/web/test_recovery.py::test_legacy_failure_confirm_is_append_only_and_idempotent -q`.
- Environment/provenance: Microsoft Windows NT `10.0.26200.0`; Poetry source execution; automated fake tests on enrolled synthetic roots; web conftest clears provider credentials and denies provider network access.
- Expected/observed: `3 failed in 44.38s`, exit `1`; preview lacked `failures`, and both new confirm requests returned HTTP `405`. The readiness guard still returned the expected `423` before confirmation; no confirmation write occurred.
- Next check: implement pure classification, preview fields, confirm orchestration, and the route; rerun the three tests.

### T009 failing-first error-text independence

- Result: **FAIL** as expected before T009 implementation.
- Recorded: `2026-11-17T12:35:14.1215607+01:00`.
- Source: `HEAD` `fb63e62480833f7e41ad7317cf223f8e387377cf`; uncommitted test diff SHA-256 `04d10a0dcc9c0f68503d8d506a2d7c04e90cf0b90d8ba18c3955a9acb77890fc` (`9294` bytes).
- Exact command: `poetry run pytest hedge_fund/runtime/test_reconciliation.py::test_legacy_failure_classification_does_not_use_error_text -q`.
- Environment/provenance: Microsoft Windows NT `10.0.26200.0`; Poetry source execution; automated test on a synthetic enrolled root; no provider calls or real-data-root access.
- Expected/observed: `1 failed in 1.53s`, exit `1`; import failed because `classify_legacy_failure_evidence` was absent. The test changes only synthetic `error` text and compares classifications/checks separately from display summaries.
- Next check: implement classification from replay, corruption, broker-book, verified-session continuity, and post-effect fields only.

### T009 classification unit

- Result: **PASS** for error-text-independent classification only; US1 preview/confirm remains **INCONCLUSIVE**.
- Recorded: `2026-11-17T12:40:07.8003740+01:00`.
- Source: `HEAD` `fb63e62480833f7e41ad7317cf223f8e387377cf`; dirty source diff SHA-256 `496883e242458bb2e4b563219f8c743395552f21a5155e3839bd8a550f58e021` (`7654` bytes) for `hedge_fund/runtime/reconciliation.py` and `hedge_fund/runtime/test_reconciliation.py`.
- Exact command: `poetry run pytest hedge_fund/runtime/test_reconciliation.py::test_legacy_failure_classification_does_not_use_error_text -q`.
- Environment/provenance: Microsoft Windows NT `10.0.26200.0`; Python `3.11.15`; Poetry source execution; synthetic enrolled root and fake/unit test only.
- Expected/observed: `1 passed in 15.06s`, exit `0`; replacing only synthetic error text changed display summaries but left per-failure classifications and all five checks unchanged.
- Next check: integrate the same classifier into preview and confirm, then run all T006–T008 tests.

### T006–T012 US1 preview and confirm

- Result: **PASS** for focused preview, confirm, replay, append-only, idempotency, and existing recovery regressions; quickstart Scenario A remains **INCONCLUSIVE** pending the T022 evidence run.
- Recorded: `2026-11-17T12:49:05.8196107+01:00`.
- Source: `HEAD` `fb63e62480833f7e41ad7317cf223f8e387377cf`; dirty source/test diff SHA-256 `8b8c398bf799250660ed417b4f1f9cabe5da669c4f5afaab3a4c8ac01f9a7f92` (`33952` bytes) for `hedge_fund/runtime/reconciliation.py`, `hedge_fund/runtime/test_reconciliation.py`, `hedge_fund/web/app.py`, `hedge_fund/web/schemas.py`, `hedge_fund/web/services.py`, `hedge_fund/web/test_services.py`, and `hedge_fund/web/test_recovery.py`.
- Artifact/environment: Poetry executed working-tree source; no built artifact. Microsoft Windows NT `10.0.26200.0`; Python `3.11.15`; Poetry `2.5.1`.
- Exact commands and results:
  - `poetry run pytest hedge_fund/web/test_services.py::test_paper_reconciliation_exposes_evidence_for_unkeyed_failures hedge_fund/web/test_recovery.py::test_legacy_failure_confirm_restores_work_readiness hedge_fund/web/test_recovery.py::test_legacy_failure_confirm_is_append_only_and_idempotent -q` — `3 passed in 46.23s`, exit `0`.
  - `poetry run pytest hedge_fund/runtime/test_reconciliation.py hedge_fund/web/test_recovery.py -q` — `33 passed in 327.70s (0:05:27)`, exit `0`.
- Scenario/provenance: synthetic enrolled roots and local fakes only. Preview exposed three unkeyed failures and all five passing checks; confirm appended one anchored decision, readiness passed, and repeated confirm returned already-resolved. Existing receipt replay, intent, halt, and Resume regression tests passed in the focused modules. No provider/LLM/broker network calls or production roots.
- Next check: author T013–T018 failing-first refusal/crash tests, then implement only gaps those tests establish.

### US1 final checkpoint after review

- Result: **PASS** for final focused classification, preview, confirm, byte-preservation, and idempotency tests.
- Recorded: `2026-11-17T13:01:40.0766212+01:00`.
- Source: `HEAD` `fb63e62480833f7e41ad7317cf223f8e387377cf`; final tested source/test diff SHA-256 `baf18be97e4589113d8bed0ab3209208c8efd2da8495702aa5d150a75d34f3b8` (`34152` bytes), same seven paths listed in the T006–T012 entry above.
- Exact command: `poetry run pytest hedge_fund/runtime/test_reconciliation.py::test_legacy_failure_classification_does_not_use_error_text hedge_fund/web/test_services.py::test_paper_reconciliation_exposes_evidence_for_unkeyed_failures hedge_fund/web/test_recovery.py::test_legacy_failure_confirm_restores_work_readiness hedge_fund/web/test_recovery.py::test_legacy_failure_confirm_is_append_only_and_idempotent -q`.
- Environment/provenance: Microsoft Windows NT `10.0.26200.0`; Python `3.11.15`; Poetry `2.5.1`; synthetic enrolled roots and fake/unit tests only.
- Expected/observed: `4 passed in 45.88s`, exit `0`; no provider calls or production-root access.

### T013–T019 refusal and crash coverage

- Result: **PASS** on the first run after test authoring; no T019 production gap reproduced. This differs from the plan's failing-first expectation because the T009–T012 implementation already contained the refusal paths.
- Recorded: `2026-11-17T13:07:14.7274095+01:00`.
- Source: `HEAD` `291cc72841f4f0cabdd492e0ac4e2e24fe4f3e9a`; uncommitted test-only diff SHA-256 `52380f4727cc83cadfa1574780c29a951611c7fa14abdf7950a4fd16ac255c56` (`15020` bytes) for `hedge_fund/web/test_services.py` and `hedge_fund/web/test_recovery.py`.
- Exact command: `poetry run pytest hedge_fund/web/test_services.py::test_paper_reconciliation_blocks_post_effect_failure_set hedge_fund/web/test_recovery.py::test_corrupt_replay_stays_distinct_from_reconciliation_required hedge_fund/web/test_recovery.py::test_legacy_failure_confirm_rejects_corrupt_audit_without_writes hedge_fund/web/test_recovery.py::test_legacy_failure_confirm_rejects_book_mismatch_without_writes hedge_fund/web/test_recovery.py::test_legacy_failure_confirm_rejects_post_effect_set_without_writes hedge_fund/web/test_recovery.py::test_legacy_failure_confirm_rejects_stale_head_without_writes hedge_fund/web/test_recovery.py::test_legacy_failure_confirm_rejects_changed_failure_set_without_writes hedge_fund/web/test_recovery.py::test_legacy_failure_confirm_rejects_control_lane_contention hedge_fund/web/test_recovery.py::test_legacy_failure_confirm_retry_deduplicates_after_append_interruption hedge_fund/web/test_recovery.py::test_legacy_failure_request_requires_true_attestation_and_unique_digests -q`.
- Environment/provenance: Microsoft Windows NT `10.0.26200.0`; Python `3.11.15`; Poetry `2.5.1`; synthetic enrolled roots and local fakes only.
- Expected/observed: `10 passed in 47.20s`, exit `0`. Corrupt replay/audit, book mismatch, post-effect ambiguity, stale head/set, lane contention, attestation validation, and append-interruption retry all refused or retried with expected status and unchanged bytes where refusal applied. No provider/LLM calls or production-root access.
- Disposition: T013–T018 tests cover their required negative states. T019 requires no production edit; confirm remains all-or-nothing and uses existing replay, root, and lane boundaries.

### T020 failing-first frontend evidence tests

- Result: **FAIL** as expected before T021 implementation.
- Recorded: `2026-11-17T13:12:39.0615715+01:00`.
- Source: `HEAD` `68de2dfcd7dffe2766848249cc6a142d89a75865`; uncommitted `frontend/src/pages/paper.test.tsx` diff SHA-256 `d12099c6255cc9516a19c76baebdfaf0e55f702219fc0a5f13931389dd4a21ec` (`5973` bytes).
- Artifact/environment: Vitest `4.1.12` over working-tree source; Microsoft Windows NT `10.0.26200.0`; Node `v22.13.1`; npm `10.9.2`; dependencies installed from `frontend/package-lock.json`. No production build or browser automation.
- Exact command: `Set-Location frontend; .\node_modules\.bin\vitest.cmd run src/pages/paper.test.tsx -t "mixed legacy failure evidence|submits an attested preview"`.
- Provenance: unit tests use `renderDesk` fetch stubs and mixed synthetic recovery data only; no API server, provider, broker, paid-credit, or production-root access.
- Expected/observed: `3 failed | 30 skipped` in `8.59s`, exit `1`; mixed evidence test could not find `legacy-failure-reconciliation`, and both confirm/refusal tests could not find the confirm button. Failures are missing T021 UI, not fixture or assertion errors.
- Command calibration: an initial `npm --prefix frontend exec` invocation ran Vitest from the repository root and failed before collection because the `@/` alias was unresolved; the exact frontend-working-directory command above reached and ran the three intended tests.
- Next check: implement the evidence list, offered-only confirm action, explicit operator attestation, request wiring, and verbatim refusal display; rerun the three tests.

### T020–T021 frontend evidence and confirmation (superseded snapshot)

- Result: **PASS** for legacy failure evidence display, confirmation gating, payload binding, and verbatim 409/422 details on the recorded source snapshot. Final source/build identity is superseded by the revalidation below. Full project acceptance Scenarios A–D remain **INCONCLUSIVE** pending T022/T024.
- Recorded: `2026-11-17T13:17:44.5226343+01:00`.
- Source: `HEAD` `68de2dfcd7dffe2766848249cc6a142d89a75865`; tested `frontend/src/pages/paper.tsx` + `frontend/src/pages/paper.test.tsx` diff SHA-256 `56566f8a0bd702cf04ce5954caae15dd0a8f7304d2882a8e8cecbcb5606d16af` (`19863` bytes).
- Artifact/environment: TypeScript `tsc --noEmit` and Vite `6.4.5` working-tree build; Windows NT `10.0.26200.0`; Node `v22.13.1`; npm `10.9.2`; Vitest `4.1.12`; dependency lock SHA-256 `380011FEB3BD4CE8888CCC3ECB13DB8BFAEC6CEE2C1EECAF30F5BF97E8F444A0`. Vite output in ignored `hedge_fund/web/static`: `index.html` SHA-256 `F23A04618CB6627C5997876C340BE877C2EB3DFE85E9376C192E8914914BFA8D`; CSS `index-DBkeKs0M.css` SHA-256 `BE48D0F397A6CC2063F89F1123B387AC886A719AF878F2F92A18F198CA542052`; JS `index-DoDHNM1-.js` SHA-256 `A5B99C6CF8F7D125FD773042F8B045F028DDA685242FA5C98661A0AFFB6D49D3`.
- Exact commands and results:
  - `Set-Location frontend; .\node_modules\.bin\vitest.cmd run src/pages/paper.test.tsx -t "mixed legacy failure evidence|submits an attested preview"` — `3 passed | 30 skipped` in `5.52s`, exit `0`, started `13:15:15`.
  - `Set-Location frontend; .\node_modules\.bin\vitest.cmd run src/pages/paper.test.tsx` — `33 passed` in `17.12s`, exit `0`, started `13:15:27`.
  - `Set-Location frontend; npm test` — `15` test files, `243` tests passed in `27.73s`, exit `0`, started `13:16:37`.
  - `Set-Location frontend; npm run build` — TypeScript check passed; Vite build succeeded in `12.75s`. Vite emitted its existing >500 kB chunk-size warning; no build error.
- Scenario/provenance: frontend unit tests use `renderDesk` fetch stubs and synthetic failure previews. Assertions cover the mixed resolvable/not-resolvable evidence list, all five check details, set-level reason, disabled confirmation for `confirm_offered=false`, exact request body for offered previews, required operator and explicit attestation, and exact 409/422 refusal text. No Playwright, API server, provider, broker, paid-credit, or production-root access.

### T020–T021 final artifact revalidation

- Result: **PASS** on final frontend source/test diff and generated build. Acceptance Scenarios A–D remain **INCONCLUSIVE** pending T022/T024.
- Recorded: `2026-11-17T13:22:13.7738325+01:00`.
- Source: `HEAD` `68de2dfcd7dffe2766848249cc6a142d89a75865`; final `frontend/src/pages/paper.tsx` + `frontend/src/pages/paper.test.tsx` diff SHA-256 `583cbb6616b7bc6afb78ba38e942803b422bddd7f767ebda422a2dd1cf2b2c7c` (`22300` bytes).
- Artifact/environment: TypeScript `tsc --noEmit` and Vite `6.4.5` working-tree build; Windows NT `10.0.26200.0`; Node `v22.13.1`; npm `10.9.2`; Vitest `4.1.12`; dependency lock SHA-256 `380011FEB3BD4CE8888CCC3ECB13DB8BFAEC6CEE2C1EECAF30F5BF97E8F444A0`. Final ignored Vite artifacts: `hedge_fund/web/static/index.html` SHA-256 `ACC1DF514F6A869010B99CEFDC0C2FC1AB5EE3A2BF3661271E12E0FC2924A716`; CSS `index-DBkeKs0M.css` SHA-256 `BE48D0F397A6CC2063F89F1123B387AC886A719AF878F2F92A18F198CA542052`; JS `index-DePDOT2r.js` SHA-256 `1EFC1646D59ED74103214C924E26D20C49455DBF0F00C6ED715077A1471D79CF`.
- Exact commands and results:
  - `Set-Location frontend; .\node_modules\.bin\vitest.cmd run src/pages/paper.test.tsx -t "reports the legacy reconciliation result"` — `2 passed | 33 skipped` in `7.39s`, exit `0`, started `13:21:14`.
  - `Set-Location frontend; npm test` — `15` test files, `245` tests passed in `37.14s`, exit `0`, started `13:21:30`.
  - `Set-Location frontend; npm run build` — TypeScript check passed; Vite build succeeded in `20.71s`. Vite emitted its >500 kB chunk-size warning; no build error.
- Scenario/provenance: final unit tests include mixed failure evidence, confirmation gating, required operator and attestation, request binding, verbatim 409/422 refusal text, and distinct `reconciled` / `already-resolved` success notices; all use synthetic fetch stubs. No Playwright, API server, provider, broker, paid-credit, or production-root access.

### T022 quickstart Scenarios A–C

- Result: **PASS** for Scenarios A, B and C on final implementation source; Scenario D remains **INCONCLUSIVE** pending T024.
- Recorded: `2026-11-17T13:31:28.5469355+01:00`.
- Source: `HEAD` `da5819bf6d37d7eaa520345c52f4f3abbbc283ae`; `hedge_fund/` source diff SHA-256 `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` (`0` bytes). Poetry ran source from the worktree; no built wheel. Windows NT `10.0.26200.0`; Python `3.11.15`; Poetry `2.5.1`; pytest `7.4.4`; environment `C:\Users\ChristianGjedrem\AppData\Local\pypoetry\Cache\virtualenvs\aihf-BhBKDBt4-py3.11`.
- Exact commands and results:
  - Scenario A, started `2026-11-17T13:24:38.7566769+01:00`: `poetry run pytest hedge_fund/runtime/test_reconciliation.py hedge_fund/web/test_services.py::test_paper_reconciliation_exposes_evidence_for_unkeyed_failures hedge_fund/web/test_recovery.py::test_legacy_failure_confirm_restores_work_readiness hedge_fund/web/test_recovery.py::test_legacy_failure_confirm_is_append_only_and_idempotent -q` — `22 passed in 183.51s`, exit `0`; ended `2026-11-17T13:27:50.5692668+01:00`.
  - Scenario B, started `2026-11-17T13:27:56.2530961+01:00`: `poetry run pytest hedge_fund/web/test_services.py::test_paper_reconciliation_blocks_post_effect_failure_set hedge_fund/web/test_recovery.py::test_corrupt_replay_stays_distinct_from_reconciliation_required hedge_fund/web/test_recovery.py::test_legacy_failure_confirm_rejects_corrupt_audit_without_writes hedge_fund/web/test_recovery.py::test_legacy_failure_confirm_rejects_book_mismatch_without_writes hedge_fund/web/test_recovery.py::test_legacy_failure_confirm_rejects_post_effect_set_without_writes hedge_fund/web/test_recovery.py::test_legacy_failure_confirm_rejects_stale_head_without_writes hedge_fund/web/test_recovery.py::test_legacy_failure_confirm_rejects_changed_failure_set_without_writes hedge_fund/web/test_recovery.py::test_legacy_failure_confirm_rejects_control_lane_contention hedge_fund/web/test_recovery.py::test_legacy_failure_confirm_retry_deduplicates_after_append_interruption hedge_fund/web/test_recovery.py::test_legacy_failure_request_requires_true_attestation_and_unique_digests -q` — `10 passed in 145.61s`, exit `0`; ended `2026-11-17T13:30:30.0392170+01:00`.
  - Scenario C, started `2026-11-17T13:30:35.9718477+01:00`: `poetry run pytest hedge_fund/web/test_recovery.py::test_legacy_failure_confirm_retry_deduplicates_after_append_interruption -q` — `1 passed in 15.55s`, exit `0`; ended `2026-11-17T13:30:59.3229387+01:00`.
- Provenance: automated fake/unit tests on synthetic enrolled roots, with no production data root, provider, LLM, broker, or paid-credit access; pytest output retained in the session transcript. Scenario A verifies preview, decision replay, readiness, byte preservation and idempotency; B asserts refusal distinctions and zero writes; C asserts one durable decision after injected append interruption and retry.

### T022 post-style-source revalidation — Scenarios A–C

- Result: **PASS** for Scenarios A, B and C on the post-style source. Scenario D remains **INCONCLUSIVE** pending T024.
- Recorded: `2026-11-17T13:43:33.7841162+01:00`.
- Source: `HEAD` `da5819bf6d37d7eaa520345c52f4f3abbbc283ae`; full dirty diff SHA-256 `c99e44a51316864e4679483943e06bde58cbdebe0dd23575eb407ca760911f64` (`17083` bytes); `hedge_fund/` diff SHA-256 `93f2b7f62fb24bb17801b6750b372bfa3dab2abcf3e9251a7b05b5627e08aca0` (`10845` bytes). Full diff identity recorded before adding this evidence entry; source diff remained unchanged during all runs.
- Artifact/environment: Poetry executed working-tree source; no wheel built or installed. Microsoft Windows NT `10.0.26200.0`; Python `3.11.15`; Poetry `2.5.1`; pytest `7.4.4`; Pydantic `2.13.4`; environment `C:\Users\ChristianGjedrem\AppData\Local\pypoetry\Cache\virtualenvs\aihf-BhBKDBt4-py3.11`.
- Exact commands and results:
  - Scenario A, started `2026-11-17T13:38:03.9136290+01:00`, ended `2026-11-17T13:39:59.3362854+01:00`: `poetry run pytest hedge_fund/runtime/test_reconciliation.py hedge_fund/web/test_services.py::test_paper_reconciliation_exposes_evidence_for_unkeyed_failures hedge_fund/web/test_recovery.py::test_legacy_failure_confirm_restores_work_readiness hedge_fund/web/test_recovery.py::test_legacy_failure_confirm_is_append_only_and_idempotent -q` — `22 passed in 109.37s`, command elapsed `115.42s`, exit `0`.
  - Scenario B, started `2026-11-17T13:40:04.2737382+01:00`, ended `2026-11-17T13:41:59.3700655+01:00`: `poetry run pytest hedge_fund/web/test_services.py::test_paper_reconciliation_blocks_post_effect_failure_set hedge_fund/web/test_recovery.py::test_corrupt_replay_stays_distinct_from_reconciliation_required hedge_fund/web/test_recovery.py::test_legacy_failure_confirm_rejects_corrupt_audit_without_writes hedge_fund/web/test_recovery.py::test_legacy_failure_confirm_rejects_book_mismatch_without_writes hedge_fund/web/test_recovery.py::test_legacy_failure_confirm_rejects_post_effect_set_without_writes hedge_fund/web/test_recovery.py::test_legacy_failure_confirm_rejects_stale_head_without_writes hedge_fund/web/test_recovery.py::test_legacy_failure_confirm_rejects_changed_failure_set_without_writes hedge_fund/web/test_recovery.py::test_legacy_failure_confirm_rejects_control_lane_contention hedge_fund/web/test_recovery.py::test_legacy_failure_confirm_retry_deduplicates_after_append_interruption hedge_fund/web/test_recovery.py::test_legacy_failure_request_requires_true_attestation_and_unique_digests -q` — `10 passed in 108.33s`, command elapsed `115.10s`, exit `0`.
  - Scenario C, started `2026-11-17T13:42:02.0149539+01:00`, ended `2026-11-17T13:42:23.3751903+01:00`: `poetry run pytest hedge_fund/web/test_recovery.py::test_legacy_failure_confirm_retry_deduplicates_after_append_interruption -q` — `1 passed in 14.15s`, command elapsed `21.36s`, exit `0`.
- Provenance: synthetic enrolled roots and local fakes only. A covers replay, readiness, append-only bytes and idempotency; B covers distinct refusals and zero writes; C covers durable append interruption and retry. No provider/LLM/broker/paid-credit calls or production-root access.

### T023 writer map and style gates

- Result: **PASS** for writer-map, Black, isort, and Black-compatible flake8. Default flake8 has four E203 findings; all four reproduce on clean baseline `e6f04d2`, so no unrelated source was reformatted.
- Recorded: `2026-11-17T13:43:55.5637739+01:00`.
- Source: `HEAD` `da5819bf6d37d7eaa520345c52f4f3abbbc283ae`; full dirty diff SHA-256 `c99e44a51316864e4679483943e06bde58cbdebe0dd23575eb407ca760911f64` (`17083` bytes); `hedge_fund/` diff SHA-256 `93f2b7f62fb24bb17801b6750b372bfa3dab2abcf3e9251a7b05b5627e08aca0` (`10845` bytes).
- Environment: Microsoft Windows NT `10.0.26200.0`; Python `3.11.15`; Poetry `2.5.1`; Black `23.12.1`; isort `5.13.2`; flake8 `6.1.0`. Baseline worktree at `C:\Users\ChristianGjedrem\AppData\Local\Temp\aihf-spec009-baseline-e6f04d2`, clean at `e6f04d2c76d761a0403f24c4b6adf40db48a8346`.
- Exact checks and results on the implementation source:
  - `poetry run black --check --line-length 420 hedge_fund/runtime/reconciliation.py hedge_fund/runtime/test_reconciliation.py hedge_fund/paper/ledger.py hedge_fund/web/services.py hedge_fund/web/schemas.py hedge_fund/web/app.py hedge_fund/web/test_services.py hedge_fund/web/test_recovery.py` — `8 files would be left unchanged`, exit `0`; started `2026-11-17T13:42:51.3595630+01:00`, ended `2026-11-17T13:43:01.0969688+01:00`.
  - `poetry run isort --check-only --profile black hedge_fund/runtime/reconciliation.py hedge_fund/runtime/test_reconciliation.py hedge_fund/paper/ledger.py hedge_fund/web/services.py hedge_fund/web/schemas.py hedge_fund/web/app.py hedge_fund/web/test_services.py hedge_fund/web/test_recovery.py` — no findings, exit `0`; started `2026-11-17T13:42:51.3010291+01:00`, ended `2026-11-17T13:43:01.0708160+01:00`.
  - `poetry run flake8 --max-line-length=420 --extend-ignore=E203 hedge_fund/runtime/reconciliation.py hedge_fund/runtime/test_reconciliation.py hedge_fund/paper/ledger.py hedge_fund/web/services.py hedge_fund/web/schemas.py hedge_fund/web/app.py hedge_fund/web/test_services.py hedge_fund/web/test_recovery.py` — no findings, exit `0`; started `2026-11-17T13:42:51.3231504+01:00`, ended `2026-11-17T13:43:06.0916956+01:00`.
  - Unmodified default E203 check, `poetry run flake8 --max-line-length=420` on the same eight files — exit `1`, only `paper/ledger.py:1309,1494,2558` and `runtime/reconciliation.py:482`; started `2026-11-17T13:42:51.2522125+01:00`, ended `2026-11-17T13:43:06.0463152+01:00`. Clean baseline produced the same four slice-whitespace findings at `paper/ledger.py:1308,1493,2542` and `runtime/reconciliation.py:402`; baseline check ended `2026-11-17T13:43:55.5637739+01:00`. Baseline Black reported eight files unchanged and baseline isort had no findings (both exit `0`). Current line shifts match the same baseline expressions; no new default-flake8 diagnostic remains.
  - `poetry run pytest hedge_fund/runtime/test_writer_map.py -q` — `119 passed in 4.71s`, command elapsed `12.31s`, exit `0`; started `2026-11-17T13:43:12.3162761+01:00`, ended `2026-11-17T13:43:24.6308605+01:00`.
- Provenance: static checks ran against the eight touched Python files; writer-map tests use synthetic test roots and local fakes. Style-only edits reorder imports and match Black formatting; no new raw writer was added. No provider/LLM/broker/paid-credit calls or production-root access.

### T024 full-suite gate — BLOCKED

- Result: **BLOCKED** for final acceptance. The first completed run is **INCONCLUSIVE** after concurrency was reported; no completed suite is bound to the final source revision.
- First run source/environment: `HEAD` `9914ef4d893f62e606378ada4585e1d0f299cfd1`, clean worktree, source diff `0` bytes / SHA-256 `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`; Poetry ran working-tree source, no wheel. Windows NT `10.0.26200.0`; Python `3.11.15`; Poetry `2.5.1`; pytest `7.4.4`; Pydantic `2.13.4`; environment `C:\Users\ChristianGjedrem\AppData\Local\pypoetry\Cache\virtualenvs\aihf-BhBKDBt4-py3.11`.
- First run time/command: `2026-11-17T21:37:14.4005763+01:00` to `2026-11-17T23:17:03.5077813+01:00`; `poetry run pytest hedge_fund -q`; **28 failed, 3029 passed, 62 skipped in 5966.77s (1:39:26)**, exit `1`. Initial isolation check reported clear. The retained output is `C:\Users\CHRIST~1\AppData\Local\Temp\1794953821126-copilot-tool-output-23852-6dfd4914-fa78-4b64-b91c-edaa70feab8b.txt`.
- Diagnostic failure IDs from that run:
  - `hedge_fund/test_run.py::test_saxo_demo_execution_refuses_before_ledger_or_execution[argv0]`, `[argv1]`, `[argv2]`, `[argv3]`.
  - `hedge_fund/test_run.py::test_saxo_guard_preserves_nonexecuting_verdicts_and_oauth_paper_approvals[saxo-False-approve-True]`, `[saxo-False-approve-False]`, `[saxo-True-approve-False]`, `[saxo-True-reject-False]`, `[paper-True-approve-True]`, `[paper-False-approve-True]`.
  - `hedge_fund/data/test_yfinance_client.py::test_news_falls_back_to_search_when_ticker_endpoint_is_down`, `::test_news_preserves_failure_when_search_is_empty_after_outage`, `::test_news_raises_when_search_also_fails`.
  - `hedge_fund/paper/test_deployed_broker.py::test_saxo_reconciliation_uses_accounting_cash_and_refuses_mismatch`.
  - `hedge_fund/paper/test_saxo_e2e.py::test_fake_transport_saxo_client_deferral_reaches_the_session_ledger`, `::test_saxo_external_adapter_records_order_fill_in_ledger`.
  - `hedge_fund/paper/test_tick.py::test_cli_shaped_tick_races_web_logical_operation_submission`.
  - `hedge_fund/runtime/test_inventory_cache_race.py::test_approval_waiting_for_sibling_publication_does_not_block_halt`.
  - `hedge_fund/runtime/test_writer_inventory.py::test_every_production_writer_is_classified_by_admission_class`.
  - `hedge_fund/web/test_actions.py::test_nonlocal_broker_mutations_stop_before_ledger_adapter[approve]`, `[halt]`, `[resume]`, `[runner-stop]`, `::test_saxo_web_routes_deny_before_provider_or_writer_effects`, `::test_saxo_accept_routes_reject_previews_before_worker_or_ledger_effects`.
  - `hedge_fund/web/test_paper_operations.py::test_corruption_receipt_does_not_resolve_later_identical_line`, `::test_reconciled_corruption_allows_resume_after_manual_halt`, `::test_crashed_owned_runner_requires_offline_stale_review_before_restart`.
- Baseline note: prior-session reports state that clean `e6f04d2` reproduced `24 failed / 4 passed` on Python `3.13.7` and `23 failed / 5 passed` on Python `3.11.15`; the per-test baseline log is unavailable here, so no failure is marked baseline-matched from those counts. The two corruption-reconciliation regressions were addressed in `a238062`; its reported focused `8 passed` result was not rerun in this session.
- Second run: `HEAD` `a238062254dad8fa19dfdfef76e22af3d532d530`, reported clean at start; `poetry run pytest hedge_fund -q` started `2026-11-17T23:35:09.7879077+01:00`. It was stopped at 57% after another suite appeared. No final summary or exit code; **INCONCLUSIVE**, not acceptance evidence.
- Active-process blocker: process enumeration at `2026-11-18T01:15:30.9250634+01:00` found `pytest.exe` PID `10544` in `aihf-FuzY57Jh-py3.13`, started `2026-11-18T01:09:59`; its worktree, source revision, dirty-diff identity, owner and output were unavailable. An earlier process in the same environment, started `2026-11-17T23:47:31.9598740+01:00`, was observed active at `2026-11-18T01:04:18.5801715+01:00`. Neither process is used as acceptance evidence. No new pytest was started in this session.
- Open Scenario B shape check: static review of `hedge_fund/web/services.py` shows the legacy `failures` and `confirm_offered` fields are returned when unresolved failures coexist with corrupt audit events. Spec009 requires the existing corrupt state to expose no legacy failures array or confirmation. No implementation change was made without a runnable discriminating test.
- Smallest falsification experiment: after process enumeration finds no active pytest, add/run a synthetic GET test using `_legacy_failure_recovery_fixture` plus `_append_corrupt_legacy_audit_event`; assert the existing corruption `intent_preview` remains available while the response contains neither `failures` nor `confirm_offered`. If it fails, suppress only Spec009 preview fields for unresolved corrupt audit while preserving the intent preview, rerun Scenario B, then run T024 alone on the final source and baseline every remaining failure.

### T025 recovery-semantics cross-reference

- Result: **PASS** for the Spec007 contract pointer; Spec005's 423 row remains unchanged because denial-until-ready semantics still hold after an eligible decision.
- Recorded: `2026-11-18T01:05:02.7457129+01:00`.
- Source: `HEAD` `a238062254dad8fa19dfdfef76e22af3d532d530`; `specs/007-rb3-halt-recovery/contracts/recovery-semantics.md` diff SHA-256 `a6cd54dd12b2cfe2d4297446425dd6e5842644c934965e0f959e62458acef03f` (`1739` bytes).
- Artifact/environment: contract Markdown only; no build or runtime artifact. Windows NT `10.0.26200.0`.
- Validation: `git diff --check` passed; the relative Spec009 contract link target exists. Static review confirmed the Spec005 423 row still describes the unchanged deny state; Spec009 states the guard stops firing once readiness passes.
- Provenance: static contract/link review only. No test or implementation behavior changed in T025.

## Acceptance scenarios

| Scenario | Status | Evidence |
|---|---|---|
| A — multiple unkeyed failures, confirm, replay byte identity | PASS | T022 post-style-source revalidation |
| B — ambiguity, corruption, mismatch, stale preview, contention refusals | INCONCLUSIVE | `a238062` changed corrupt-audit preview behavior; final response-shape test pending |
| C — durable append interruption and retry | PASS | T022 post-style-source revalidation |
| D — full suite and baseline comparison | BLOCKED | No isolated final run; external pytest process active with source identity unavailable |
