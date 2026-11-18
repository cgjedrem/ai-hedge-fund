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

### QA rework cycle 1 — tests authored; execution blocked

- Result: **BLOCKED** for failing-first and post-fix tests, and for per-test branch/baseline isolation. No test was run after authoring these regressions.
- Recorded: `2026-11-18T01:30:36.1214555+01:00`.
- Source: `HEAD` `4f2302c6fcc39bdc6ab9ee726eb3fb702d6cd870`; dirty test diff SHA-256 `883d96a984625cb72b90e25a6134733231ddc7f0d774b98dfa33b08ca3908a6a` (`6283` bytes). Only the three test files were modified at this checkpoint.
- Environment: Windows NT `10.0.26200.0`. Process enumeration found active `poetry run pytest hedge_fund -q` trees: Python 3.11 process PID `43752` (started `2026-11-18T01:09:57`) and Python 3.13 `pytest.exe` PID `10544` (started `2026-11-18T01:09:59`); both were still active at observation time. Ownership/source identity were not established; neither process was stopped or used as evidence. No pytest process was started by this cycle.
- Authored regressions: `test_corrupt_audit_suppresses_legacy_failure_preview_fields` in `hedge_fund/web/test_services.py`; `test_legacy_failure_recorded_after_decision_remains_unresolved` and `test_legacy_receipt_and_resume_before_decision_resolve_mixed_set` in `hedge_fund/runtime/test_reconciliation.py`; parameterized `test_legacy_failure_confirm_reports_distinct_book_status_reason` in `hedge_fund/web/test_recovery.py`. They use synthetic roots and fixtures. The corrupt-audit test preserves `intent_preview` assertions while requiring all five Spec009 extension fields absent. No provider, LLM, broker, paid-credit, or production-root access.
- Static status: `git diff --check` passed. Source inspection shows current corrupt-audit responses still include the Spec009 fields, and current confirm classification uses the generic book/replay reason for invalid/changed statuses. This predicts the new response/reason tests should distinguish the reported gaps; it is not failing-first runtime evidence.
- T024 failure triage: retained output for clean `9914ef4` / Python `3.11.15` records `test_cli_shaped_tick_races_web_logical_operation_submission` failing with `WriterConflict` while acquiring an admission lane after a 5-second wait; `test_approval_waiting_for_sibling_publication_does_not_block_halt` observing `2.655999999959022s` against a `<2.0s` bound; and `test_crashed_owned_runner_requires_offline_stale_review_before_restart` receiving `worker-failed` with `OwnedRunnerError` during runner readiness. Static diff found no changes in `runtime/admission.py`, `runtime/operations.py`, `runtime/owned_runner.py`, `paper/tick.py`, or those tests; no causal link is established. Aggregate baseline counts do not identify per-test outcomes. Branch and baseline single-test runs remain **BLOCKED** by the active pytest processes.
- Blocker recheck: `2026-11-18T01:37:06.0480211+01:00`; both process trees remained active. `git diff --check` exited `0`; no test was started.
- Next check: coordinator message after machine clears; failing-first capture is moot after the static fixes land. Run the new regression tests, Scenario A/B selections, and frontend `paper.test.tsx` tests on the final source; run branch/baseline diagnostic IDs only with no active pytest.

### QA rework cycle 1 — static-only fixes (unverified)

- Result: **INCONCLUSIVE** for runtime behavior. Corrupt-preview suppression, optional frontend fields, and confirm book-status reasons are implemented in source but unverified by any test, build, or runtime run.
- Recorded: `2026-11-18T01:39:18.9245078+01:00`.
- Source: `HEAD` `d44fb9e2564f17ae0e43102c2c4cdd0c4450588b`; dirty source diff SHA-256 `c4b9840f92b4790d5d73d3ec148a13fe1ee6a0e399b1189dea54ff76b175d030` (`4430` bytes), covering `hedge_fund/web/services.py` and `frontend/src/pages/paper.tsx`.
- Artifact/environment: working-tree source only; no Vite build, installed bundle, or runtime artifact. Windows NT `10.0.26200.0`.
- Static changes: `paper_reconciliation` retains `preview`, `intent_preview`, and `intent_targets` but omits all five Spec009 extension fields when `corrupt_event_digests` is non-empty; the frontend models those fields as optional and guards the `failures` map. Confirm refusal replaces the generic book/replay reason with a status-specific reason for invalid, changed, unavailable, mismatch, and non-local-paper book states; the existing mismatch 423 path and preview set-level messages remain unchanged.
- Validation: manual diff review and `git diff --check` passed (exit `0`). No pytest, frontend test, lint, build, or runtime command was run. Existing regression tests remain unexecuted.
- Acceptance freshness: Scenarios A and B are **INCONCLUSIVE** pending reruns because the frontend recovery contract and corrupt/refusal responses changed. Scenario C remains PASS: static diff does not touch successful append/retry or idempotency behavior. Scenario D remains BLOCKED under coordinator-managed T024. `tasks.md` checkboxes unchanged.
- Provenance/next owner: static review only; coordinator owns execution after machine clearance. Next run: new regression tests, Scenario A/B selections, and `frontend` `paper.test.tsx` on final source. No provider, LLM, broker, paid-credit, or production-root access.

### QA rework cycle 1 — verification

- Result: **PASS** for the corrupt-audit response regression, replay/refusal tests, focused Scenarios A–C, frontend paper tests, changed-file style gates, and writer-map test. The three prior suite-failure candidates pass individually on both branch and baseline; aggregate-suite attribution remains **INCONCLUSIVE**. T024 was not run here; coordinator owns it. Scenario D remains **BLOCKED**.
- Recorded: `2026-11-18T02:51:52.4859933+01:00`, final focused backend run end.
- Source: branch `HEAD` `26161f28015df4fd8f6c3723f57770b76213d57b`. Initial QA verification runs used a clean tree, diff SHA-256 `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` (`0` bytes). Final post-style backend re-run used the same `HEAD` plus dirty-diff SHA-256 `816b855b5eeb4f01f3a47efbff5cfb781b630f3ae29ccdf9c258e81043a9891c` (`769` bytes), containing only isort wrapping in `hedge_fund/runtime/test_reconciliation.py`. Baseline worktree was clean at `e6f04d2c76d761a0403f24c4b6adf40db48a8346`.
- Environment: Windows NT `10.0.26200.0`; Python `3.11.15`; Poetry `2.5.1`; pytest `7.4.4`; Poetry environment `C:\Users\ChristianGjedrem\AppData\Local\pypoetry\Cache\virtualenvs\aihf-BhBKDBt4-py3.11`. Frontend test used local `frontend/node_modules/.bin/vitest.cmd`; Node `v22.13.1`, npm `10.9.2`. Backend tests ran against checkout source in place; no wheel was built. Frontend source was tested directly; no Vite build artifact was produced.
- Isolation: process enumeration returned zero pytest processes at `2026-11-18T02:32:40+01:00`. Before the writer-map test, enumeration returned zero at `2026-11-18T02:45:25.1285922+01:00`. All test commands ran sequentially. Outputs are retained in the execution transcript.
- Focused backend verification:
  - `poetry run pytest hedge_fund/web/test_services.py::test_corrupt_audit_suppresses_legacy_failure_preview_fields hedge_fund/runtime/test_reconciliation.py hedge_fund/web/test_recovery.py -q` — `46 passed in 318.97s`, exit `0`; started `2026-11-18T02:32:47.7673551+01:00`, ended `2026-11-18T02:38:27.2552462+01:00`.
  - `poetry run pytest hedge_fund/web/test_services.py::test_paper_reconciliation_exposes_evidence_for_unkeyed_failures hedge_fund/web/test_recovery.py::test_legacy_failure_confirm_restores_work_readiness hedge_fund/web/test_recovery.py::test_legacy_failure_confirm_is_append_only_and_idempotent -q` — `3 passed in 29.65s`, exit `0`; started `2026-11-18T02:38:36.0524186+01:00`, ended `2026-11-18T02:39:12.3896168+01:00`.
  - `poetry run pytest hedge_fund/web/test_recovery.py::test_legacy_failure_confirm_retry_deduplicates_after_append_interruption -q` — `1 passed in 11.43s`, exit `0`; started `2026-11-18T02:39:16.2525749+01:00`, ended `2026-11-18T02:39:34.2790047+01:00`.
  - After the import-only style edit, reran `poetry run pytest hedge_fund/web/test_services.py::test_corrupt_audit_suppresses_legacy_failure_preview_fields hedge_fund/runtime/test_reconciliation.py hedge_fund/web/test_recovery.py -q` on the dirty-diff identity above — `46 passed in 318.69s`, exit `0`; started `2026-11-18T02:46:26.9530922+01:00`, ended `2026-11-18T02:51:52.4859933+01:00`.
- Frontend verification: `Set-Location frontend; .\node_modules\.bin\vitest.cmd run src/pages/paper.test.tsx` — `35 passed in 86.93s`, exit `0`; started `2026-11-18T02:39:38.8142624+01:00`, ended `2026-11-18T02:41:09.8931408+01:00`. Covers the page after recovery fields became optional; backend regression separately asserts the corrupt response omits all five Spec009 fields and retains `intent_preview`.
- Isolated branch/baseline diagnostics, Python `3.11.15` / pytest `7.4.4` on Windows NT `10.0.26200.0`; branch source was clean `26161f2`, baseline source was clean `e6f04d2`. Expected results are the test assertions; observed each test passed on both revisions:
  - `hedge_fund/paper/test_tick.py::test_cli_shaped_tick_races_web_logical_operation_submission`: exactly one safe winner (stale web preview plus completed CLI tick, or accepted web operation plus duplicate CLI refusal), with the asserted session count. Branch: `1 passed in 6.11s`, `2026-11-18T02:41:19.2870602+01:00`–`2026-11-18T02:41:30.0684433+01:00`, exit `0`; baseline: `1 passed in 5.83s`, `2026-11-18T02:41:40.0097073+01:00`–`2026-11-18T02:42:00.0803160+01:00`, exit `0`.
  - `hedge_fund/runtime/test_inventory_cache_race.py::test_approval_waiting_for_sibling_publication_does_not_block_halt`: emergency Halt completes below the asserted `2.0s` bound while sibling publication remains paused; publication then releases and approval receives `423`. Branch: `1 passed in 12.73s`, `2026-11-18T02:42:05.1073637+01:00`–`2026-11-18T02:42:22.9854228+01:00`, exit `0`; baseline: `1 passed in 16.67s`, `2026-11-18T02:42:26.9992441+01:00`–`2026-11-18T02:42:48.7123468+01:00`, exit `0`. Exact halt latency was not separately emitted.
  - `hedge_fund/web/test_paper_operations.py::test_crashed_owned_runner_requires_offline_stale_review_before_restart`: crashed owner remains unavailable and stop-denied until explicit offline stale review; recovered runner state and ledger session/head meet the test assertions. Branch: `1 passed in 21.73s`, `2026-11-18T02:42:54.3281064+01:00`–`2026-11-18T02:43:21.6355201+01:00`, exit `0`; baseline: `1 passed in 22.95s`, `2026-11-18T02:43:27.3964000+01:00`–`2026-11-18T02:43:55.7142652+01:00`, exit `0`.
  - None of the three aggregate-suite failures reproduced in isolated runs on either revision. This does not attribute or resolve the aggregate T024 result.
- Style and writer-map verification:
  - First isort check found one import-format issue in `hedge_fund/runtime/test_reconciliation.py`; `poetry run isort --diff --profile black hedge_fund/runtime/test_reconciliation.py` confirmed only a local import line-wrap. Initial isort check exited `1`, started `2026-11-18T02:44:24.6049387+01:00`, ended `2026-11-18T02:44:28.6825294+01:00`. The formatting-only edit is included in the dirty-diff identity above; the affected backend batch was rerun.
  - `poetry run black --check --line-length 420 hedge_fund/runtime/test_reconciliation.py hedge_fund/web/test_recovery.py hedge_fund/web/test_services.py hedge_fund/web/services.py` — `4 files would be left unchanged`, exit `0`; `2026-11-18T02:45:12.8291362+01:00`–`2026-11-18T02:45:17.8209715+01:00`.
  - `poetry run isort --check-only --profile black hedge_fund/runtime/test_reconciliation.py hedge_fund/web/test_recovery.py hedge_fund/web/test_services.py hedge_fund/web/services.py` — no findings, exit `0`; `2026-11-18T02:45:12.8021298+01:00`–`2026-11-18T02:45:15.8940713+01:00`.
  - `poetry run flake8 --max-line-length=420 --extend-ignore=E203 hedge_fund/runtime/test_reconciliation.py hedge_fund/web/test_recovery.py hedge_fund/web/test_services.py hedge_fund/web/services.py` — no findings, exit `0`; `2026-11-18T02:45:12.8261347+01:00`–`2026-11-18T02:45:18.2931755+01:00`. E203 remains ignored per T023's clean-baseline-equivalence record.
  - With zero pytest processes, `poetry run pytest hedge_fund/runtime/test_writer_map.py -q` — `119 passed in 7.10s`, exit `0`; started `2026-11-18T02:45:25.1335943+01:00`, ended `2026-11-18T02:45:36.9967767+01:00`.
- Provenance: automated fake/unit tests use synthetic roots and local fakes; branch/baseline comparison used the specified clean baseline worktree. No provider, LLM, broker, paid-credit, or production-root access. `tasks.md` checkboxes remain unchanged. No T024 full-suite run is claimed.

## Acceptance scenarios

| Scenario | Status | Evidence |
|---|---|---|
| A — multiple unkeyed failures, confirm, replay byte identity | PASS | Backend/recovery and residual tests passed; final paper UI tests 36/36, build, and writer-map passed on the source snapshot committed as `aeffcd3`; see attestation-close verification |
| B — ambiguity, corruption, mismatch, stale preview, contention refusals | PASS | Backend refusal tests and mixed three-way evidence UI test passed; final paper UI tests 36/36, build, and writer-map passed on the source snapshot committed as `aeffcd3`; see attestation-close verification |
| C — durable append interruption and retry | PASS | Backend append-interruption/retry test passed; final paper UI tests 36/36, build, and writer-map passed on the source snapshot committed as `aeffcd3`; see attestation-close verification |
| D — full suite and baseline comparison | PASS | T024 ran on `aeffcd3`; all 23 failures reproduced individually with matching substantive failure signatures on clean baseline `e6f04d2`; see attribution table below |

### Coordinator revision-binding closure (QA cycle-1 re-review)

- Recorded: 2026-11-18T03:0x+01:00 (post QA re-review).
- QA flagged: batch-of-46 bound to 26161f2 + 769-byte isort-only dirty diff; equivalence to committed 4818fb0/1ff3114 unverified.
- Closure: `git diff 26161f2 1ff3114 -- hedge_fund` touches exactly one file, hedge_fund/runtime/test_reconciliation.py, a 5-line isort-only import rewrap (no behavior); memory/evidence/tasks files are documentation. The tested source and final committed source are behaviorally identical; the dirty diff QA referenced is the same rewrap.
- Residual open items for the solo-suite window (QA caveats): rerun test_paper_reconciliation_blocks_post_effect_failure_set on final source; run test_paper_operations.py::test_corruption_receipt_does_not_resolve_later_identical_line and ::test_reconciled_corruption_allows_resume_after_manual_halt on final source; frontend tsc/build after optional-field change; then T024 isolated full suite with per-test baseline attribution for every failure.

### QA rework cycle 2 — finding 1 discriminator gate

- Result: **BLOCKED** at finding 1. No source or regression-test changes were made. User-directed stop applies because legacy unkeyed `tick_failed` events have no positive per-failure no-effect discriminator in the inspected code; choosing to make them permanently non-resolvable requires a spec-owner decision.
- Recorded: `2026-11-18T13:16:51.1769008+01:00`.
- Source: `HEAD` `0c1278b65a6396002d701ac425f595a24aeb0ad8`; worktree clean before this evidence entry; source diff `0` bytes / SHA-256 `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`.
- Environment: Microsoft Windows; no test environment or artifact used.
- Static evidence:
  - `hedge_fund/paper/tick.py:792-796` keeps `effect_state["started"]` in memory. The `tick_failed` write at `:994-1005` records `session`, `error`, `expected_head`, and optional operation context; it does not persist effect state.
  - `tick_aborted` with `no_effects=True` is a separate attempt-keyed outcome (`:504-522`); legacy unkeyed `tick_failed` records have no attempt identity to bind to it.
  - `paper_effect_registry` reserves a process-local `_PaperObservationWindow`; it does not persist per-failure effect accounting. `PaperBroker` persists the current book after fills, not an append-only per-failure effect history.
  - The classifier's current absence-of-post-effect-fields check therefore cannot distinguish an old no-effect failure from an unmarked post-effect failure.
- Process blocker: the following command at the recorded time found five active processes whose command lines contained pytest: `Get-CimInstance Win32_Process -Filter "Name like 'python%' or Name like 'pytest%'" | Where-Object { $_.CommandLine -match 'pytest' }`. PIDs `32556`, `61776`, `26196`, `32240`, and `74272` were running `poetry run pytest hedge_fund -q --tb=line` / `pytest hedge_fund -q --tb=line`. No process was stopped.
- Tests/builds: no pytest, frontend unit test, TypeScript check, or frontend build was started. This includes the requested Scenario B rerun and both `test_paper_operations.py` residual tests. No failing-first regression was added because the required policy change is blocked.
- Findings 2–4: not implemented or revalidated; work stopped at finding 1 as directed. Existing acceptance rows above remain unchanged; no Scenario A–D row was rerun in this cycle.
- Provenance: code/spec static inspection only. No provider, LLM, broker, paid-credit, or production-root access.

### QA rework cycle 2 — Copilot findings 1–4

- Result: **INCONCLUSIVE** for runtime acceptance. Findings 1–4 and requested regressions are implemented; no pytest, frontend unit test, TypeScript check, or build ran on this source. This entry supersedes the earlier finding-1 stop; Scenario A–C rows above are invalidated until rerun. Scenario D remains coordinator-owned and **BLOCKED**.
- Recorded: process gate `2026-11-18T14:58:47.2102369+01:00`; final static checks `2026-11-18T15:07:08.7395200+01:00`–`2026-11-18T15:07:30.0905603+01:00`.
- Source: starting `HEAD` `11ea2f8023b1950f24d167ae25865a8a25790212`; implementation diff SHA-256 `aa7bc8674fe2fc1eccaf14e540cfb4efcbbea1c9e594b7d9423188c30f0ac1da` (`137304` bytes), over all 14 modified paths except this evidence file. It includes Python, frontend, spec, and memory edits; final commit revision binds this evidence entry.
- Environment/artifact: Windows NT `10.0.26200.0`; Python `3.11.15`; Poetry `2.5.1`; working-tree source only. No wheel, frontend bundle, or runtime artifact was built.
- Process blocker: exact command `Get-CimInstance Win32_Process -Filter "Name like 'python%' or Name like 'pytest%'" | Where-Object { $_.CommandLine -match 'pytest' }` found five active processes: PIDs `17824`, `23672`, `8668`, `12496`, and `25096`, each running `poetry run pytest hedge_fund -q --tb=line` or its pytest child. No process was stopped; no pytest command was started.
- Implemented:
  - `verified` requires passing structural checks and replay at `expected_head` with no pending decision; `attestable` covers structural-but-ambiguous evidence and requires exact per-failure attestation; any `not_resolvable` member blocks the set.
  - Continuity uses the failure event's stream index, requires a later successful tick tied to a verified successor, and uses the latest occurrence for duplicate identical failure digests. Session ordering preserves naive intraday time.
  - Preview/confirm/decision bind SHA-256 of exact audit-history bytes. Confirm holds the audit lane through digest recheck and append; any append, including Halt, stales the preview.
  - Regression tests cover pending-at-head, no-pending verified, missing pending-state evidence, invalid event shapes, post-effect and session-already-recorded attestable cases, late stream-position failures (including duplicate identity), intraday minute ordering, stale Halt/corrupt-event appends, exact attestations, and audit-lane ownership.
- Tests/builds not started under the active-process gate; exit code **N/A**:
  - `poetry run pytest hedge_fund/runtime/test_reconciliation.py hedge_fund/web/test_recovery.py hedge_fund/web/test_services.py -q`
  - `poetry run pytest hedge_fund/web/test_services.py::test_paper_reconciliation_blocks_post_effect_failure_set -q`
  - `poetry run pytest hedge_fund/web/test_paper_operations.py::test_corruption_receipt_does_not_resolve_later_identical_line hedge_fund/web/test_paper_operations.py::test_reconciled_corruption_allows_resume_after_manual_halt -q`
  - `Set-Location frontend; npm test`
  - `Set-Location frontend; npm run build`
  - T024 full suite was not run; coordinator-owned.
- Static checks on the final Python source:
  - `poetry run black --check --line-length 420 hedge_fund/runtime/reconciliation.py hedge_fund/runtime/test_reconciliation.py hedge_fund/paper/ledger.py hedge_fund/web/schemas.py hedge_fund/web/services.py hedge_fund/web/test_services.py hedge_fund/web/test_recovery.py` — 7 files unchanged, exit `0`; `15:07:08.7395200+01:00`–`15:07:14.8341961+01:00`.
  - `poetry run isort --check-only --profile black hedge_fund/runtime/reconciliation.py hedge_fund/runtime/test_reconciliation.py hedge_fund/paper/ledger.py hedge_fund/web/schemas.py hedge_fund/web/services.py hedge_fund/web/test_services.py hedge_fund/web/test_recovery.py` — no findings, exit `0`; `15:07:14.8341961+01:00`–`15:07:20.3628618+01:00`.
  - `poetry run flake8 --max-line-length=420 --extend-ignore=E203 hedge_fund/runtime/reconciliation.py hedge_fund/runtime/test_reconciliation.py hedge_fund/paper/ledger.py hedge_fund/web/schemas.py hedge_fund/web/services.py hedge_fund/web/test_services.py hedge_fund/web/test_recovery.py` — no findings, exit `0`; `15:07:20.3628618+01:00`–`15:07:29.9620316+01:00`.
  - `git diff --check` — no whitespace findings, exit `0`; `15:07:29.9620316+01:00`–`15:07:30.0905603+01:00`. Git emitted LF-to-CRLF normalization warnings for `memory.md` and this evidence file.
- Provenance: static review and style tools only. Tests and frontend build remain unexecuted; no provider, LLM, broker, paid-credit, or production-root access.

### Option-C verification — FAIL

- Result: **FAIL** for the verification batch. Backend tests passed (`96/96`); residual paper-operation tests passed (`2/2`); frontend paper tests failed (`31 failed, 5 passed`). Per instruction, execution stopped at that first failure. No source fix was made. Scenarios A–C remain **INCONCLUSIVE**; Scenario D remains **BLOCKED** under coordinator-owned T024.
- Recorded: zero-process gate `2026-11-18T17:15:12.6297779+01:00`; final failing test command ended `2026-11-18T17:24:14.3360489+01:00`.
- Source: `HEAD` `06d05185d11bcc1437ff3ca9e901381dba33d928`; checkout source, no wheel or frontend build artifact. Source diff at test start was empty, SHA-256 `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`; worktree was clean before this evidence update. No Python/frontend source changed during verification.
- Environment: Windows NT `10.0.26200.0`; Python `3.11.15`; Poetry `2.5.1`; pytest `7.4.4`; frontend Vitest `4.1.12`. Tests used synthetic roots/local fakes; no provider, LLM, broker, paid-credit, or production-root access.
- Process gate: exact command `Get-CimInstance Win32_Process -Filter "Name like 'python%' or Name like 'pytest%'" | Where-Object { $_.CommandLine -match 'pytest' }`. Polls returned `COUNT=5` at `16:42:53.0420207+01:00` and `16:52:53.6206919+01:00`; `COUNT=0` at `17:02:54.2321234+01:00`, followed by a pre-test recheck at `17:03:05.5765985+01:00` with `COUNT=2` (PIDs `43548`, `19656`, running `test_kimi_cost_model_rejects_non_loopback_endpoint`). No test started during that race. Monitor resumed at `17:05:10.7040871+01:00` with `COUNT=5`; next poll at `17:15:11.4705481+01:00` and pre-batch recheck at `17:15:12.0420760+01:00` both returned `COUNT=0`.
- Exact commands and results:
  - `poetry run pytest hedge_fund/runtime/test_reconciliation.py hedge_fund/web/test_recovery.py hedge_fund/web/test_services.py -q` — `96 passed in 426.87s`, exit `0`; started `2026-11-18T17:15:12.6736756+01:00`, ended `2026-11-18T17:22:27.6101721+01:00`.
  - `poetry run pytest hedge_fund/web/test_paper_operations.py::test_corruption_receipt_does_not_resolve_later_identical_line hedge_fund/web/test_paper_operations.py::test_reconciled_corruption_allows_resume_after_manual_halt -q` — `2 passed in 16.37s`, exit `0`; started `2026-11-18T17:22:28.2161569+01:00`, ended `2026-11-18T17:22:50.9033688+01:00`.
  - `Set-Location frontend; .\node_modules\.bin\vitest.cmd run src/pages/paper.test.tsx` — `1 failed (1); 31 failed, 5 passed (36)`; started `2026-11-18T17:22:51.5169513+01:00`, ended `2026-11-18T17:24:14.3360489+01:00`, exit `1`. Vitest reported `78.43s` duration, start `17:22:55`.
- Exact failure: `ReferenceError: setLegacyAttestation is not defined` at `src/pages/paper.tsx:347:5`, on `setLegacyAttestation(false)`. React hit this while mounting the paper page; all 31 failing tests reported this same exception. Failed tests were: “shows operator responsibility in trusted single-writer mode”; “reuses the reviewed verdict request ID after a lost response”; “reuses a Halt request ID after a lost response”; “reviews readiness, capture and the exact due-set before one accepted manual tick”; “labels an empty reviewed runner due-set as nothing due and sends the reviewed bounds”; “reviews and records an idempotent nothing-due manual operation”; “loads reviewed recovery when ledger replay is valid but readiness requires reconciliation”; “allows reviewed Resume when ledger readiness requires reconciliation”; “keeps Resume disabled when ledger replay is corrupt”; “reviews hash-bound local reconciliation before resuming without retrying the failed tick”; “does not auto-resubmit a lost recovery response and reuses its request identity after review”; “allocates a fresh recovery request after explicit review of an expired receipt”; “resumes a manual halt with an empty confirmation and no paper operation”; “reuses a manual Resume request ID after a lost response”; “completes a landed Resume after reload using identity from the journal-backed recovery snapshot”; “keeps resume disabled when local reconciliation is not recoverable”; “selects an ID-less tick-intent target by digest before confirming recovery”; “shows approval journal identities covered by tick-intent recovery”; runner-state cases `starting`, `running`, `stopping`, `failed`, and `unknown`; “does not resubmit when an accepted response is lost and keeps the request identity for inspection”; “restores a persisted operation on reload by reading it and rejects a late older status”; “shows mixed legacy failure evidence and disables confirmation when the set is not offered”; “submits a verified preview and displays the 409 refusal verbatim”; “submits a verified preview and displays the 422 refusal verbatim”; “requires and submits per-failure attestations for attestable failures”; and legacy reconciliation results `reconciled` and `already-resolved`. Full Vitest output retained in the PowerShell execution transcript, session `151`.
- Stop condition: `npm run build`, Black, isort, flake8, and `hedge_fund/runtime/test_writer_map.py` were **NOT RUN** after the frontend failure. T024 was not run. No retry or fix attempted.
- Provenance: automated fake/unit tests on working-tree source. Backend test process gates before the residual and frontend phases were `COUNT=0` at `2026-11-18T17:22:28.2056054+01:00` and `2026-11-18T17:22:51.5169513+01:00`.

### Option-C reset-fix follow-up — FAIL

- Result: **FAIL** after the one-line fund-change reset fix. The stale `setLegacyAttestation` ReferenceError did not recur; `34/36` frontend paper tests passed and two assertions still failed. Execution stopped without another fix. Scenarios A–C remain **INCONCLUSIVE**; Scenario D remains **BLOCKED** under coordinator-owned T024.
- Recorded: pre-test process gate `2026-11-18T17:28:38.8234568+01:00`, `COUNT=0`; frontend test ended `2026-11-18T17:28:55.8993856+01:00`.
- Source: base `HEAD` `06d05185d11bcc1437ff3ca9e901381dba33d928` plus the one-line `frontend/src/pages/paper.tsx` reset change; full file SHA-256 `76c05f9af9251f7716516464d031ce03c5e470af851aa823e0d3b80a1e331e38`. Backend source was unchanged. No build artifact was produced.
- Fix and grep: fund-change reset now calls `setLegacyAttestationDigests([])`. `rg "setLegacyAttestation\\b" frontend/src/pages/paper.tsx` returned no matches; all remaining setter references target `setLegacyAttestationDigests`.
- Backend test disposition: standalone `hedge_fund/web/test_services.py::test_paper_reconciliation_blocks_post_effect_failure_set` was skipped per coordinator instruction; complete `hedge_fund/web/test_services.py` was included in the prior 96-pass batch at `17:15:12.6736756+01:00`–`17:22:27.6101721+01:00`, exit `0`. Current source change is frontend-only.
- Exact command: `Set-Location frontend; .\node_modules\.bin\vitest.cmd run src/pages/paper.test.tsx` — `1 failed (1); 2 failed, 34 passed (36)`, exit `1`; started `2026-11-18T17:28:38.8374475+01:00`, ended `2026-11-18T17:28:55.8993856+01:00`. Vitest `4.1.12` reported `15.38s`, start `17:28:40`.
- Failure 1: `shows mixed legacy failure evidence and disables confirmation when the set is not offered`; `expect(element).toHaveTextContent()` expected `Post-effect metadata is present on this failure.` but rendered text showed `Verified — no effect proven` for the first failure and `Not resolvable` for the second. Assertion at `src/pages/paper.test.tsx:1233:19`.
- Failure 2: `requires and submits per-failure attestations for attestable failures`; `expect(submit).toBeEnabled()` received a disabled button. Assertion at `src/pages/paper.test.tsx:1317:18`.
- Stop condition: `npm run build`, Black, isort, flake8, `hedge_fund/runtime/test_writer_map.py`, and T024 were **NOT RUN** after the frontend test failure. No further fix or retry attempted.
- Provenance: Vitest ran against checkout source with local `frontend/node_modules`; no provider, LLM, broker, paid-credit, or production-root access.

### Option-C three-way fixture update follow-up — FAIL

- Result: **FAIL** after the authorized fixture repair. The mixed three-way evidence case now passes; paper-page tests report `35 passed, 1 failed` out of 36. Scenarios A–C remain **INCONCLUSIVE**; Scenario D remains **BLOCKED** under coordinator-owned T024.
- Recorded: zero-process gate `2026-11-18T17:34:21.3180286+01:00`; test command started `2026-11-18T17:34:21.3260311+01:00` and ended `2026-11-18T17:34:40.5870682+01:00`.
- Source: base `HEAD` `06d05185d11bcc1437ff3ca9e901381dba33d928`; frontend source diff SHA-256 `b1f8b3629298dcf99984732655a468292c66af8a2e110921f41836944cd64bf6` (`10852` bytes), covering `frontend/src/pages/paper.tsx` and `frontend/src/pages/paper.test.tsx`. Full-file SHA-256: `paper.tsx` `76c05f9af9251f7716516464d031ce03c5e470af851aa823e0d3b80a1e331e38`; `paper.test.tsx` `ac5e2a05697f48bd6f33506c7496c80f3f44ae623ef0a776656fa82551bbf2cc`. No build artifact was produced.
- Process gate: exact command `Get-CimInstance Win32_Process -Filter "Name like 'python%' or Name like 'pytest%'" | Where-Object { $_.CommandLine -match 'pytest' }` returned `COUNT=0`. No Python test command was started.
- Fixture update: helper now receives explicit effect evidence; mixed-evidence case covers `verified`, `attestable`, and `not_resolvable`; attestation case uses two attestable digests plus one verified digest and checks partial versus exact coverage and the submitted payload.
- Exact command: `Set-Location frontend; .\node_modules\.bin\vitest.cmd run src/pages/paper.test.tsx` — `35 passed, 1 failed (36)`, exit `1`; Vitest `4.1.12` reported `17.90s`, start `17:34:22`.
- Remaining failure: `requires and submits per-failure attestations for attestable failures`; `expect(submit).toBeEnabled()` received a disabled button at `src/pages/paper.test.tsx:1374:18`. Both selected checkboxes were verified checked before opening the dialog, and the operator identity was entered. The confirm-button handler in `paper.tsx` clears `legacyAttestationDigests` while opening that dialog, so the submit gate still sees incomplete coverage. No production change was made.
- Stop condition: `npm run build`, Black, isort, flake8, `hedge_fund/runtime/test_writer_map.py`, and T024 were **NOT RUN** after this failure. No further fix or retry attempted.
- Provenance: Vitest ran against checkout source with local `frontend/node_modules`; no provider, LLM, broker, paid-credit, or production-root access. Scenarios A–C remain **INCONCLUSIVE**; no acceptance row was promoted to PASS.

### Option-C dialog-open reset removal follow-up — FAIL

- Result: **FAIL** after removing the attestation clear from the confirm-dialog open handler. The paper-page suite reports `35 passed, 1 failed` out of 36; Scenarios A–C remain **INCONCLUSIVE** and Scenario D remains **BLOCKED** under coordinator-owned T024.
- Recorded: test started `2026-11-18T17:37:02.7830321+01:00` and ended `2026-11-18T17:37:21.0307544+01:00`.
- Source: base `HEAD` `06d05185d11bcc1437ff3ca9e901381dba33d928`; frontend source diff SHA-256 `0c42b5084a9c15ca23b54591c42070d633fb5bfb6569409a180be438dd420b73` (`11370` bytes), covering `frontend/src/pages/paper.tsx` and `frontend/src/pages/paper.test.tsx`. Full-file SHA-256: `paper.tsx` `bf415beab8410e9869a50a8577af04c635da2f53bb50eab5884f6b1241ee8bde`; `paper.test.tsx` `ac5e2a05697f48bd6f33506c7496c80f3f44ae623ef0a776656fa82551bbf2cc`. No build artifact was produced.
- Fix and grep: removed `setLegacyAttestationDigests([])` from the dialog-open handler. `rg` now finds only four clear sites: fund change, successful reconciliation, failed reconciliation, and dialog close.
- Exact command: `Set-Location frontend; .\node_modules\.bin\vitest.cmd run src/pages/paper.test.tsx` — `35 passed, 1 failed (36)`, exit `1`; Vitest `4.1.12` reported `16.95s`, start `17:37:04`.
- Failure: `requires and submits per-failure attestations for attestable failures`; `expect(attestations[0]).toBeChecked()` received an unchecked checkbox at `src/pages/paper.test.tsx:1368:27`, after the test clicked both attestable checkboxes. Failure occurred before reopening the confirmation dialog or asserting the submitted payload.
- Stop condition: `npm run build`, Python style checks, `hedge_fund/runtime/test_writer_map.py`, and T024 were **NOT RUN** after this failure. No further fix or retry attempted.
- Provenance: Vitest ran against checkout source with local `frontend/node_modules`; no provider, LLM, broker, paid-credit, or production-root access. No acceptance row was promoted to PASS.

### Option-C attestation test interaction rework — FAIL

- Result: **FAIL** after re-querying checkboxes after each Cancel and asserting intended selection state before each dialog open. The paper-page suite reports `35 passed, 1 failed` out of 36; Scenarios A–C remain **INCONCLUSIVE**, Scenario D remains **BLOCKED** under coordinator-owned T024.
- Recorded: test started `2026-11-18T17:39:24.4144784+01:00` and ended `2026-11-18T17:39:44.0730539+01:00`.
- Source: base `HEAD` `06d05185d11bcc1437ff3ca9e901381dba33d928`; frontend source diff SHA-256 `0eb7b2451779ab3d27f151cc2d9251dc810cb66cf1f80b531f009af5aff6ee19` (`11771` bytes), covering `frontend/src/pages/paper.tsx` and `frontend/src/pages/paper.test.tsx`. Full-file SHA-256: `paper.tsx` `bf415beab8410e9869a50a8577af04c635da2f53bb50eab5884f6b1241ee8bde`; `paper.test.tsx` `6eac4eb01c79ccb89f11be908ed83ecc65b43b7d0e6a1190602b542cd7051dae`. No build artifact was produced.
- Test change: checkbox queries now retrieve current inputs after each state transition; the test asserts no selection after Cancel, one selected digest before partial confirmation, and both selected digests before full confirmation. It still checks disabled partial submit, enabled full submit after operator entry, and exact payload coverage.
- Exact command: `Set-Location frontend; .\node_modules\.bin\vitest.cmd run src/pages/paper.test.tsx` — `35 passed, 1 failed (36)`, exit `1`; Vitest `4.1.12` reported `18.23s`, start `17:39:25`.
- Failure: `requires and submits per-failure attestations for attestable failures`; after Cancel on the partial-attestation dialog, `expect(getAttestations()[0]).not.toBeChecked()` received a checked checkbox at `src/pages/paper.test.tsx:1371:36`. The test stopped before re-establishing full coverage, reopening the dialog, or asserting the submitted payload.
- Stop condition: `npm run build`, Python style checks (no Python source changed), `hedge_fund/runtime/test_writer_map.py`, and T024 were **NOT RUN** after this failure. No further fix or retry attempted.
- Provenance: Vitest ran against checkout source with local `frontend/node_modules`; no provider, LLM, broker, paid-credit, or production-root access. No acceptance row was promoted to PASS.

### Option-C attestation-close verification — PASS

- Result: **PASS** for Scenarios A–C. A/B backend recovery and refusal tests and the two requested paper-operation residuals passed in the prior Option-C batch; the backend source is unchanged in this follow-up. Final frontend paper tests, build, and writer-map passed. Scenario D remains **BLOCKED** under coordinator-owned T024.
- Recorded: final focused test `2026-11-18T17:43:41.7031756+01:00`–`17:45:24.3287083+01:00`; final full paper test `17:45:29.5324483+01:00`–`17:45:49.1475727+01:00`; build `17:45:54.6722790+01:00`–`17:47:05.1726892+01:00`; writer-map gate `17:47:13.7929976+01:00`, test `17:47:14.6964939+01:00`–`17:47:34.1613528+01:00`.
- Source identity: base `HEAD` `06d05185d11bcc1437ff3ca9e901381dba33d928`; frontend source diff SHA-256 `1119d3640cc3c79e840eb51ff5c54fbcef7fa78354cd415c83d653a510fd7959` (`12534` bytes), covering `frontend/src/pages/paper.tsx` and `frontend/src/pages/paper.test.tsx`. Full-file SHA-256: `paper.tsx` `c494e52e5514709191e7157dde917796c1f1925501e5e43469fea2997d070c00`; `paper.test.tsx` `a17d34886882aaebd4171da728f7214111e0ad27f53932ddea22b9d0dc2498b8`. No Python source changed.
- Verified mechanism: the attestation wipe lived in Radix `onOpenChange(false)`, but the custom Cancel button only called `setLegacyRecoveryOpen(false)` on the controlled Dialog. The parent prop change bypassed Radix's callback. Instrumented Cancel-close probe observed no mutation and no reconciliation refetch, then timed out waiting for the selected checkbox to clear (`17:42:32.2341416+01:00`–`17:42:39.9264515+01:00`, exit `1`). A differential probe showed Cancel preserved the selection while reopening and closing with Radix's `Close dialog` control cleared it (`17:42:56.1312659+01:00`–`17:43:04.2376557+01:00`, `1 passed`, exit `0`). The close-path comparison isolates Cancel's bypass of the cleanup callback; waiting did not observe a delayed reset.
- Fix: Cancel now clears `legacyAttestationDigests` directly before closing. Radix-originated close paths retain their existing reset. The final test waits for close cleanup, proves no mutation on Cancel, checks partial coverage stays disabled, full exact coverage plus operator enables submit, and asserts the exact digest list in the request.
- Environment: Windows NT `10.0.26200.0`; Poetry `2.5.1`, Poetry Python `3.11.15`; Node `v22.13.1`, npm `10.9.2`; Vitest `4.1.12`, Vite `6.4.5`; `frontend/package-lock.json` SHA-256 `380011FEB3BD4CE8888CCC3ECB13DB8BFAEC6CEE2C1EECAF30F5BF97E8F444A0`. Tests used local fakes only.
- Exact verification commands and results:
  - Prior unchanged-backend batch: `poetry run pytest hedge_fund/runtime/test_reconciliation.py hedge_fund/web/test_recovery.py hedge_fund/web/test_services.py -q` — `96 passed in 426.87s`, exit `0`; `2026-11-18T17:15:12.6736756+01:00`–`17:22:27.6101721+01:00`.
  - Prior residual batch: `poetry run pytest hedge_fund/web/test_paper_operations.py::test_corruption_receipt_does_not_resolve_later_identical_line hedge_fund/web/test_paper_operations.py::test_reconciled_corruption_allows_resume_after_manual_halt -q` — `2 passed in 16.37s`, exit `0`; `2026-11-18T17:22:28.2161569+01:00`–`17:22:50.9033688+01:00`.
  - `Set-Location frontend; .\node_modules\.bin\vitest.cmd run src/pages/paper.test.tsx -t "requires and submits per-failure attestations for attestable failures"` — `1 passed, 35 skipped`, exit `0`; Vitest reported `97.24s`; final focused run above.
  - `Set-Location frontend; .\node_modules\.bin\vitest.cmd run src/pages/paper.test.tsx` — `36 passed`, exit `0`; Vitest `18.29s`.
  - `Set-Location frontend; npm run build` — `tsc --noEmit` passed; Vite built successfully in `36.26s`, exit `0`. Vite emitted only the >500 kB chunk advisory. `index.html` 468 bytes, SHA-256 `871E2E6F7966CECC2B4B44942169B0DD6ACC32EDBA5CE756ED7614BBD597FFA7`; CSS 25772 bytes, SHA-256 `BE48D0F397A6CC2063F89F1123B387AC886A719AF878F2F92A18F198CA542052`; JS 1034902 bytes, SHA-256 `0707C5D593B2EC4D18560E6EA6400083F860E18AFA9D977485D514D86D7B752D`.
  - Pre-pytest gate: exact `Get-CimInstance Win32_Process -Filter "Name like 'python%' or Name like 'pytest%'" | Where-Object { $_.CommandLine -match 'pytest' }` returned `COUNT=0`.
  - `poetry run pytest hedge_fund/runtime/test_writer_map.py -q` — `119 passed in 10.32s`, exit `0`.
- Style: Black/isort/flake8 not run; no Python source changed. `git diff --check` passed, exit `0`.
- Acceptance at this checkpoint: Scenarios A–C **PASS** on the tested source identity above; Scenario D was pending then. The final T024 result below establishes Scenario D **PASS**.
- Provenance: synthetic backend roots, frontend fetch fakes, and writer-map unit tests only; no provider, LLM, broker, paid-credit, production-root, or real-money access.

### T024 full suite — complete; Scenario D PASS

- Result: `poetry run pytest hedge_fund -q` completed with **23 failed, 3052 passed, 62 skipped** (`3137` collected), duration `4326.24s` (`1:12:06`), exit `1`. All 23 failures reproduced individually on the clean baseline with matching substantive signatures; no branch-only failure found. Scenario D **PASS** under the specified baseline-attribution rule.
- Recorded: pre-run process gate `2026-11-18T17:51:58.9874304+01:00`, `COUNT=0`; suite started `2026-11-18T17:51:59.5328067+01:00`, ended `2026-11-18T19:04:11.2214745+01:00`.
- Source identity: checkout `C:\Users\ChristianGjedrem\source\repos\copilot-worktrees\ai-hedge-fund\cgjedrem-effective-winner`; clean `HEAD` `aeffcd3e4452cc6addf398513adde493ec3449a2` before run; source dirty-diff SHA-256 `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` (empty). Poetry ran checkout source; no built artifact.
- Baseline identity/environment: clean worktree `C:\Users\ChristianGjedrem\AppData\Local\Temp\aihf-spec009-baseline-e6f04d2`, `HEAD` `e6f04d2c76d761a0403f24c4b6adf40db48a8346`, clean before and after comparison. Windows 11 Enterprise `10.0.26200`, build `26200`; Python `3.11.15`, Poetry `2.5.1`, pytest `7.4.4`. Baseline tests used the branch Poetry venv's Python executable from baseline cwd; import probe resolved `hedge_fund.__file__` inside the baseline worktree.
- Exact command: `poetry run pytest hedge_fund -q`; started immediately after the recorded zero-process gate. No provider, LLM, broker, or production-root access.
- Foreign-process monitor: monitor anchored to the suite process tree from `2026-11-18T17:52:22.4928619+01:00` through `19:04:25.2572165+01:00`; final `FOREIGN_PID_COUNT=0`. At `18:17:33` two Python test-child processes referenced the active checkout's pytest temporary paths; they disappeared by `18:18:33`. No independent pytest process was observed.
- Full-suite failing test IDs (all individually attributed below):
  - `hedge_fund/test_run.py::test_saxo_demo_execution_refuses_before_ledger_or_execution[argv0]`
  - `hedge_fund/test_run.py::test_saxo_demo_execution_refuses_before_ledger_or_execution[argv1]`
  - `hedge_fund/test_run.py::test_saxo_demo_execution_refuses_before_ledger_or_execution[argv2]`
  - `hedge_fund/test_run.py::test_saxo_demo_execution_refuses_before_ledger_or_execution[argv3]`
  - `hedge_fund/test_run.py::test_saxo_guard_preserves_nonexecuting_verdicts_and_oauth_paper_approvals[saxo-False-approve-True]`
  - `hedge_fund/test_run.py::test_saxo_guard_preserves_nonexecuting_verdicts_and_oauth_paper_approvals[saxo-False-approve-False]`
  - `hedge_fund/test_run.py::test_saxo_guard_preserves_nonexecuting_verdicts_and_oauth_paper_approvals[saxo-True-approve-False]`
  - `hedge_fund/test_run.py::test_saxo_guard_preserves_nonexecuting_verdicts_and_oauth_paper_approvals[saxo-True-reject-False]`
  - `hedge_fund/test_run.py::test_saxo_guard_preserves_nonexecuting_verdicts_and_oauth_paper_approvals[paper-True-approve-True]`
  - `hedge_fund/test_run.py::test_saxo_guard_preserves_nonexecuting_verdicts_and_oauth_paper_approvals[paper-False-approve-True]`
  - `hedge_fund/data/test_yfinance_client.py::test_news_falls_back_to_search_when_ticker_endpoint_is_down`
  - `hedge_fund/data/test_yfinance_client.py::test_news_preserves_failure_when_search_is_empty_after_outage`
  - `hedge_fund/data/test_yfinance_client.py::test_news_raises_when_search_also_fails`
  - `hedge_fund/paper/test_deployed_broker.py::test_saxo_reconciliation_uses_accounting_cash_and_refuses_mismatch`
  - `hedge_fund/paper/test_saxo_e2e.py::test_fake_transport_saxo_client_deferral_reaches_the_session_ledger`
  - `hedge_fund/paper/test_saxo_e2e.py::test_saxo_external_adapter_records_order_fill_in_ledger`
  - `hedge_fund/runtime/test_writer_inventory.py::test_every_production_writer_is_classified_by_admission_class`
  - `hedge_fund/web/test_actions.py::test_nonlocal_broker_mutations_stop_before_ledger_adapter[approve]`
  - `hedge_fund/web/test_actions.py::test_nonlocal_broker_mutations_stop_before_ledger_adapter[halt]`
  - `hedge_fund/web/test_actions.py::test_nonlocal_broker_mutations_stop_before_ledger_adapter[resume]`
  - `hedge_fund/web/test_actions.py::test_nonlocal_broker_mutations_stop_before_ledger_adapter[runner-stop]`
  - `hedge_fund/web/test_actions.py::test_saxo_web_routes_deny_before_provider_or_writer_effects`
  - `hedge_fund/web/test_actions.py::test_saxo_accept_routes_reject_previews_before_worker_or_ledger_effects`

#### Individual branch/baseline attribution

- Process gate before every individual branch and baseline invocation: `Get-CimInstance Win32_Process -Filter "Name like 'python%' or Name like 'pytest%'" | Where-Object { $_.CommandLine -match 'pytest' }`; every recorded gate returned `COUNT=0`.
- Commands: branch `poetry run pytest <test-id> -q --tb=line`; baseline from the baseline worktree `C:\Users\ChristianGjedrem\AppData\Local\pypoetry\Cache\virtualenvs\aihf-BhBKDBt4-py3.11\Scripts\python.exe -m pytest <test-id> -q --tb=line`. Times are local ISO-8601 with `+01:00`; exit codes shown for each run.
- Failure signatures are identical after normalizing checkout paths. The yfinance regex failures were also rerun with `--tb=long`; their exact regex and input lines matched on both revisions. Full traceback comparison differed only in process-local object addresses.
- Comparator note: the first comparison attempt treated Python's repr-escaped checkout path in the `argv1` `AttributeError` as a mismatch. The `argv0` and `argv1` pairs were rerun below; both produced the same path-neutral error as baseline. No test or product source changed during attribution.
- Retained outputs: full T024 output `C:\Users\ChristianGjedrem\AppData\Local\Temp\1795025049561-copilot-tool-output-13336-5e381804-00af-4d0e-9ad1-82fc8df6cd81.txt`; 21 branch/baseline pair summary `C:\Users\ChristianGjedrem\AppData\Local\Temp\1795025471251-copilot-tool-output-13336-0afd5247-8bd0-42ef-954c-47107d642c78.txt`; detailed yfinance comparison `C:\Users\ChristianGjedrem\AppData\Local\Temp\1795025778404-copilot-tool-output-13336-135a1486-a4be-40fc-bbfc-52030105dbcb.txt`.

| Test ID | Branch run (start–end; exit) | Baseline run (start–end; exit) | Matching result |
|---|---|---|---|
| `hedge_fund/test_run.py::test_saxo_demo_execution_refuses_before_ledger_or_execution[argv0]` | `2026-11-18T19:14:52.0382548+01:00`–`2026-11-18T19:14:56.1912296+01:00`; 1 | `2026-11-18T19:14:56.7714273+01:00`–`2026-11-18T19:14:59.5469792+01:00`; 1 | `AttributeError`: `hedge_fund.run` has no attribute `apply_credentials` |
| `hedge_fund/test_run.py::test_saxo_demo_execution_refuses_before_ledger_or_execution[argv1]` | `2026-11-18T19:15:00.1421157+01:00`–`2026-11-18T19:15:04.4836817+01:00`; 1 | `2026-11-18T19:15:05.0377759+01:00`–`2026-11-18T19:15:07.9562499+01:00`; 1 | `AttributeError`: `hedge_fund.run` has no attribute `apply_credentials` |
| `hedge_fund/test_run.py::test_saxo_demo_execution_refuses_before_ledger_or_execution[argv2]` | `2026-11-18T19:09:53.0573985+01:00`–`2026-11-18T19:09:57.1548098+01:00`; 1 | `2026-11-18T19:09:57.7579901+01:00`–`2026-11-18T19:10:00.5332724+01:00`; 1 | `AttributeError`: `hedge_fund.run` has no attribute `apply_credentials` |
| `hedge_fund/test_run.py::test_saxo_demo_execution_refuses_before_ledger_or_execution[argv3]` | `2026-11-18T19:10:01.1360964+01:00`–`2026-11-18T19:10:05.2637833+01:00`; 1 | `2026-11-18T19:10:05.7873096+01:00`–`2026-11-18T19:10:08.5597825+01:00`; 1 | `AttributeError`: `hedge_fund.run` has no attribute `apply_credentials` |
| `hedge_fund/test_run.py::test_saxo_guard_preserves_nonexecuting_verdicts_and_oauth_paper_approvals[saxo-False-approve-True]` | `2026-11-18T19:10:09.1553088+01:00`–`2026-11-18T19:10:13.1410729+01:00`; 1 | `2026-11-18T19:10:13.6948068+01:00`–`2026-11-18T19:10:16.5165503+01:00`; 1 | `AttributeError`: `hedge_fund.run` has no attribute `apply_credentials` |
| `hedge_fund/test_run.py::test_saxo_guard_preserves_nonexecuting_verdicts_and_oauth_paper_approvals[saxo-False-approve-False]` | `2026-11-18T19:10:17.0618819+01:00`–`2026-11-18T19:10:21.1504437+01:00`; 1 | `2026-11-18T19:10:21.6702443+01:00`–`2026-11-18T19:10:24.3476899+01:00`; 1 | `AttributeError`: `hedge_fund.run` has no attribute `apply_credentials` |
| `hedge_fund/test_run.py::test_saxo_guard_preserves_nonexecuting_verdicts_and_oauth_paper_approvals[saxo-True-approve-False]` | `2026-11-18T19:10:24.9326592+01:00`–`2026-11-18T19:10:29.0439141+01:00`; 1 | `2026-11-18T19:10:29.5611203+01:00`–`2026-11-18T19:10:32.3149713+01:00`; 1 | `AttributeError`: `hedge_fund.run` has no attribute `apply_credentials` |
| `hedge_fund/test_run.py::test_saxo_guard_preserves_nonexecuting_verdicts_and_oauth_paper_approvals[saxo-True-reject-False]` | `2026-11-18T19:10:32.9029391+01:00`–`2026-11-18T19:10:36.9154536+01:00`; 1 | `2026-11-18T19:10:37.4285355+01:00`–`2026-11-18T19:10:40.1480685+01:00`; 1 | `AttributeError`: `hedge_fund.run` has no attribute `apply_credentials` |
| `hedge_fund/test_run.py::test_saxo_guard_preserves_nonexecuting_verdicts_and_oauth_paper_approvals[paper-True-approve-True]` | `2026-11-18T19:10:40.7229024+01:00`–`2026-11-18T19:10:44.7526646+01:00`; 1 | `2026-11-18T19:10:45.2787000+01:00`–`2026-11-18T19:10:48.0001177+01:00`; 1 | `AttributeError`: `hedge_fund.run` has no attribute `apply_credentials` |
| `hedge_fund/test_run.py::test_saxo_guard_preserves_nonexecuting_verdicts_and_oauth_paper_approvals[paper-False-approve-True]` | `2026-11-18T19:10:48.5695848+01:00`–`2026-11-18T19:10:52.5598148+01:00`; 1 | `2026-11-18T19:10:53.0963099+01:00`–`2026-11-18T19:10:55.8651458+01:00`; 1 | `AttributeError`: `hedge_fund.run` has no attribute `apply_credentials` |
| `hedge_fund/data/test_yfinance_client.py::test_news_falls_back_to_search_when_ticker_endpoint_is_down` | `2026-11-18T19:10:56.4288165+01:00`–`2026-11-18T19:11:00.3286027+01:00`; 1 | `2026-11-18T19:11:00.8989842+01:00`–`2026-11-18T19:11:03.6389881+01:00`; 1 | `DataClientError: yfinance data error on TEST news` |
| `hedge_fund/data/test_yfinance_client.py::test_news_preserves_failure_when_search_is_empty_after_outage` | `2026-11-18T19:11:04.1514048+01:00`–`2026-11-18T19:11:08.0991960+01:00`; 1 | `2026-11-18T19:11:08.6040578+01:00`–`2026-11-18T19:11:11.2467316+01:00`; 1 | `AssertionError`; regex `ticker news unavailable`, input `yfinance data error on TEST news` |
| `hedge_fund/data/test_yfinance_client.py::test_news_raises_when_search_also_fails` | `2026-11-18T19:11:11.8077678+01:00`–`2026-11-18T19:11:15.6592078+01:00`; 1 | `2026-11-18T19:11:16.2005496+01:00`–`2026-11-18T19:11:18.8397239+01:00`; 1 | `AssertionError`; regex `search unavailable`, input `yfinance data error on TEST news` |
| `hedge_fund/paper/test_deployed_broker.py::test_saxo_reconciliation_uses_accounting_cash_and_refuses_mismatch` | `2026-11-18T19:11:19.3816417+01:00`–`2026-11-18T19:11:23.4899217+01:00`; 1 | `2026-11-18T19:11:23.9699440+01:00`–`2026-11-18T19:11:26.6642538+01:00`; 1 | `SaxoReconcileError: Saxo broker requires an explicitly selected account identifier` |
| `hedge_fund/paper/test_saxo_e2e.py::test_fake_transport_saxo_client_deferral_reaches_the_session_ledger` | `2026-11-18T19:11:27.1987311+01:00`–`2026-11-18T19:11:31.5873469+01:00`; 1 | `2026-11-18T19:11:32.1325945+01:00`–`2026-11-18T19:11:34.9676378+01:00`; 1 | `SaxoReconcileError: Saxo broker requires an explicitly selected account identifier` |
| `hedge_fund/paper/test_saxo_e2e.py::test_saxo_external_adapter_records_order_fill_in_ledger` | `2026-11-18T19:11:35.5126513+01:00`–`2026-11-18T19:11:40.0159424+01:00`; 1 | `2026-11-18T19:11:40.5751320+01:00`–`2026-11-18T19:11:43.3397731+01:00`; 1 | `SaxoReconcileError: Saxo broker requires an explicitly selected account identifier` |
| `hedge_fund/runtime/test_writer_inventory.py::test_every_production_writer_is_classified_by_admission_class` | `2026-11-18T19:11:43.8632222+01:00`–`2026-11-18T19:11:53.1012494+01:00`; 1 | `2026-11-18T19:11:53.6714336+01:00`–`2026-11-18T19:11:59.6777566+01:00`; 1 | `AssertionError`: six unclassified raw writers (`runtime/build_identity.py`, `runtime/credential_delivery.py`; same six-entry list on both revisions) |
| `hedge_fund/web/test_actions.py::test_nonlocal_broker_mutations_stop_before_ledger_adapter[approve]` | `2026-11-18T19:12:00.2350587+01:00`–`2026-11-18T19:12:08.7338375+01:00`; 1 | `2026-11-18T19:12:09.2545937+01:00`–`2026-11-18T19:12:15.6571242+01:00`; 1 | `HandoverError: paper inventory is invalid (ValueError)` |
| `hedge_fund/web/test_actions.py::test_nonlocal_broker_mutations_stop_before_ledger_adapter[halt]` | `2026-11-18T19:12:16.2167686+01:00`–`2026-11-18T19:12:24.3626436+01:00`; 1 | `2026-11-18T19:12:24.9410724+01:00`–`2026-11-18T19:12:32.9193304+01:00`; 1 | `HandoverError: paper inventory is invalid (ValueError)` |
| `hedge_fund/web/test_actions.py::test_nonlocal_broker_mutations_stop_before_ledger_adapter[resume]` | `2026-11-18T19:12:33.4575066+01:00`–`2026-11-18T19:12:41.6767644+01:00`; 1 | `2026-11-18T19:12:42.2381263+01:00`–`2026-11-18T19:12:48.9010467+01:00`; 1 | `HandoverError: paper inventory is invalid (ValueError)` |
| `hedge_fund/web/test_actions.py::test_nonlocal_broker_mutations_stop_before_ledger_adapter[runner-stop]` | `2026-11-18T19:12:49.4475893+01:00`–`2026-11-18T19:12:57.5272526+01:00`; 1 | `2026-11-18T19:12:58.0343637+01:00`–`2026-11-18T19:13:05.3757218+01:00`; 1 | `HandoverError: paper inventory is invalid (ValueError)` |
| `hedge_fund/web/test_actions.py::test_saxo_web_routes_deny_before_provider_or_writer_effects` | `2026-11-18T19:13:05.9123276+01:00`–`2026-11-18T19:13:14.8493786+01:00`; 1 | `2026-11-18T19:13:15.4079077+01:00`–`2026-11-18T19:13:22.6630764+01:00`; 1 | `HandoverError: paper inventory is invalid (ValueError)` |
| `hedge_fund/web/test_actions.py::test_saxo_accept_routes_reject_previews_before_worker_or_ledger_effects` | `2026-11-18T19:13:23.2217617+01:00`–`2026-11-18T19:13:36.3448095+01:00`; 1 | `2026-11-18T19:13:36.9384515+01:00`–`2026-11-18T19:13:46.7630444+01:00`; 1 | `HandoverError: paper inventory is invalid (ValueError)` |

The two yfinance assertion results were corroborated with full tracebacks: `test_news_preserves_failure_when_search_is_empty_after_outage` branch `2026-11-18T19:15:59.0083430+01:00`–`2026-11-18T19:16:04.0491559+01:00`, baseline `2026-11-18T19:16:04.6528692+01:00`–`2026-11-18T19:16:07.7329734+01:00`; `test_news_raises_when_search_also_fails` branch `2026-11-18T19:16:08.4913629+01:00`–`2026-11-18T19:16:13.6995146+01:00`, baseline `2026-11-18T19:16:14.3020868+01:00`–`2026-11-18T19:16:18.2561098+01:00`. Both runs exited `1`; baseline and branch reported the exact regex/input pairs in the table.
