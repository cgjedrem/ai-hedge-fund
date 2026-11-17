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

## Acceptance scenarios

| Scenario | Status | Evidence |
|---|---|---|
| A — multiple unkeyed failures, confirm, replay byte identity | INCONCLUSIVE | Pending implementation and final-artifact run |
| B — ambiguity, corruption, mismatch, stale preview, contention refusals | INCONCLUSIVE | Pending implementation and final-artifact run |
| C — durable append interruption and retry | INCONCLUSIVE | Pending implementation and final-artifact run |
| D — full suite and baseline comparison | INCONCLUSIVE | T024 not run |
