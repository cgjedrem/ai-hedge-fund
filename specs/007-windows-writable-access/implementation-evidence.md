# Feature 007 implementation evidence

## T001 — pre-change focused baseline

- **Identity**: revision `b35b0d0dc2dda4dadf7f95fc380de24db5a9e81d`; clean worktree; no implementation diff.
- **Observation**: captured `2026-11-12T12:38:49.0701629+01:00`; pytest reported `1372.71s` (`22:52`).
- **Environment**: Windows `10.0.26200`, Python `3.11.15` 64-bit, Poetry Python 3.11 environment, pytest `7.4.4`.
- **Command**: `py -m poetry run pytest hedge_fund/runtime hedge_fund/tui -q`.
- **Artifact**: `C:\Users\CHRIST~1\AppData\Local\Temp\1794483496805-copilot-tool-output-46128-6590c1ce-12a3-4c7d-9191-ab1ce4f3bfa4.txt`; SHA-256 `4dca215436f0d07912f88be7860d7f79bc18a80e24519a2c47fa952e9dd64a95`.
- **Result**: FAIL — `883 passed, 22 skipped, 13 failed`.

### Exact baseline failures

1. `hedge_fund/runtime/test_inventory_cache_race.py::test_approval_waiting_for_sibling_publication_does_not_block_halt` — expected halt under `2.0s`; observed `2.3439999998081475s`.
2. `hedge_fund/runtime/test_writer_admission_race_matrix.py::test_authority_flip_while_lane_is_held_denies_every_write_time_check[registry-synthetic-test-owner-removed]`
3. `hedge_fund/runtime/test_writer_admission_race_matrix.py::test_authority_flip_while_lane_is_held_denies_every_write_time_check[deployment-synthetic-test-owner-removed]`
4. `hedge_fund/runtime/test_writer_admission_race_matrix.py::test_authority_flip_while_lane_is_held_denies_every_write_time_check[runner-synthetic-test-owner-removed]`
5. `hedge_fund/runtime/test_writer_admission_race_matrix.py::test_authority_flip_while_lane_is_held_denies_every_write_time_check[execution-synthetic-test-owner-removed]`
6. `hedge_fund/runtime/test_writer_admission_race_matrix.py::test_authority_flip_while_lane_is_held_denies_every_write_time_check[control-synthetic-test-owner-removed]`
7. `hedge_fund/runtime/test_writer_admission_race_matrix.py::test_authority_flip_while_lane_is_held_denies_every_write_time_check[halt-synthetic-test-owner-removed]`
8. `hedge_fund/runtime/test_writer_admission_race_matrix.py::test_authority_flip_while_lane_is_held_denies_every_write_time_check[audit-synthetic-test-owner-removed]`
9. `hedge_fund/runtime/test_writer_admission_race_matrix.py::test_authority_flip_while_lane_is_held_denies_every_write_time_check[research-synthetic-test-owner-removed]`
10. `hedge_fund/runtime/test_writer_admission_race_matrix.py::test_root_without_operator_acknowledgement_is_read_only`
11. `hedge_fund/runtime/test_writer_inventory.py::test_every_production_writer_is_classified_by_admission_class` — observed six unclassified baseline sites: `runtime/build_identity.py::bake_build_identity/write_text`; `runtime/credential_delivery.py::CredentialDeliveryServer._prepare_socket_directory/mkdir`, `_recover_stale_socket/unlink`, `close/rmdir`, `close/unlink`, and `start/os.chmod`.
12. `hedge_fund/runtime/test_writer_map.py::test_every_production_write_primitive_is_mapped` — observed five unmapped baseline sites: `build_identity.py::bake_build_identity/write_text`; `credential_delivery.py::_prepare_socket_directory/mkdir`, `_recover_stale_socket/unlink`, `close/rmdir`, and `close/unlink`.
13. `hedge_fund/runtime/test_writer_races.py::test_authority_revoked_across_processes_blocks_an_admitted_append[synthetic-test-owner]`

Failures 2–10 and 13 expected `operator-single-writer-acknowledgement-required`; observed `operator-single-writer-runtime-scope-unavailable`. The pre-change focused run is the baseline reproduction. These results are not feature acceptance.

## T002–T003 — foundation checkpoint

- **Identity**: base revision `b211dcbe05b18e7de14f0012373504796e36e523`; implementation-file dirty-diff SHA-256 `a9059d82dee23fa8c33db6839411f24aedecd3a40a35a74febb5c1e7565432c3`; observed `2026-11-12T12:50:09.0149641+01:00`.
- **Environment / artifact**: Windows `10.0.26200`, Python `3.11.15` 64-bit, Poetry environment, pytest `7.4.4`; pytest loaded repository source directly (no built wheel).
- **Scenarios**: Windows scope binds machine, account SID, and root volume; trust accepts scope and requires fresh review after SID change. Attestation schema round-trips, rejects another root and invalid values, stores under destination-private storage, and refuses overwrite. Writer map classifies the new directory write.
- **Command**: `py -m poetry run pytest hedge_fund/runtime/test_handover.py hedge_fund/runtime/test_write_authority.py -q` — **65 passed in 34.36s**.
- **Command**: `py -m poetry run pytest hedge_fund/runtime/test_writer_map.py::test_writer_map_has_no_stale_entries hedge_fund/runtime/test_writer_map.py::test_writer_map_entry_is_classified_with_real_evidence -q` — **111 passed in 3.21s**.
- **Style**: project Black check, isort with Black profile, and flake8 at configured `420` line length passed on five changed Python files.
- **Progress**: `hedge_fund/runtime/handover.py`, runtime tests, and writer-map inventory — T002/T003 PASS; relocation/evidence and attestation CLI flows remain pending.

## Evidence-bundle lookup decision

`attest-*` contracts accept a source-evidence digest but no evidence path. `inspect-source --evidence-out` therefore uses the destination's canonical private staging path `runtime/private/v1/source-evidence.json`. The CLI still requires that exact absolute path as `--evidence-out`; source and destination remain disjoint, and the source is read-only.

## T004–T006 — evidence staging and two-stage relocation

- **Identity**: base revision `bc3f1fd4f0dfcba5ec24f855bf04efd2d1374bb7`; implementation diff SHA-256 `0bb10bb2e3ee067dcabccaae20255a8dafcd08a708ab66195b73c06e694bc2dc`; captured `2026-11-12T13:22:38.7880778+01:00`.
- **Environment / artifact**: Windows `10.0.26200`, Python `3.11.15` 64-bit, pytest `7.4.4`, Poetry environment. Tests imported the worktree source directly; no wheel was built.
- **Scenarios**: `inspect-source --evidence-out` stages destination-private evidence idempotently and leaves source tree digest unchanged. `relocate-copy` hash-copies settings and data, remains unenrolled, skips target ledger inventory validation, rejects digest mismatch without target state, and retries an interrupted copy. `relocate-finalize` validates inventory and enrolls only after copy completes.
- **Commands**:
  - `py -m poetry run pytest hedge_fund/runtime/test_handover.py -q` — **29 passed in 17.63s**.
  - `py -m poetry run pytest hedge_fund/test_run.py::test_handover_cli_relocates_legacy_root_without_writing_source hedge_fund/test_run.py::test_handover_cli_runs_copy_then_finalize_with_staged_evidence -q` — **2 passed in 4.29s**.
  - `py -m poetry run pytest hedge_fund/runtime/test_write_authority.py -k relocation -q` — **12 passed, 30 deselected in 7.83s**.
  - `py -m poetry run pytest hedge_fund/runtime/test_writer_map.py hedge_fund/runtime/test_writer_inventory.py -q` — **113 passed, 2 failed in 5.95s**. Failures are the exact T001 baseline gates and sites: `test_every_production_write_primitive_is_mapped` (five unmapped legacy sites) and `test_every_production_writer_is_classified_by_admission_class` (six unclassified legacy sites); no new writer site reported.
  - Black (`--line-length 420`), isort (`--profile black`), flake8 (`--max-line-length=420 --extend-ignore=E203`), and `git diff --check` passed on changed Python files.
- **Unrelated CLI baseline**: current-diff selection `py -m poetry run pytest hedge_fund/test_run.py -k 'test_saxo_demo_execution_refuses_before_ledger_or_execution or test_saxo_guard_preserves_nonexecuting_verdicts_and_oauth_paper_approvals' -q` — **10 failed, 94 deselected in 0.76s**. Every case fails at `monkeypatch.setattr(run, "apply_credentials", ...)` because `hedge_fund.run` lacks that attribute. Reproduced all same 10 IDs on clean pre-change revision `b35b0d0` — **10 failed, 93 deselected in 2.71s**. Current CLI diff does not add/remove this symbol.
- **Progress**: T004–T006 PASS on synthetic roots. Writer-map gates remain documented baseline failures; Saxo test failures reproduced on pre-change revision.

## T007 - Windows scope and trust challenge validation

- **Identity**: revision `59bde80d54fa8e7404a82e79b3ce74c794c5e040`; clean worktree; dirty-diff SHA-256 `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`; observed `2026-11-12T13:36:44.4849574+01:00`.
- **Environment / artifact**: Windows `10.0.26200`, Python `3.11.15` 64-bit, pytest `7.4.4`, Poetry environment. Tests imported the worktree source directly; no wheel was built.
- **Scenarios**: Windows scope binds machine, account SID, and root volume; a changed Windows SID invalidates trust and requires a fresh acknowledgement; challenges cannot cross roots or survive inventory drift; expired reviews deny trust.
- **Command**: `py -m poetry run pytest hedge_fund/runtime/test_write_authority.py::test_windows_runtime_scope_binds_machine_account_and_volume hedge_fund/runtime/test_write_authority.py::test_windows_trust_scope_mismatch_requires_fresh_review hedge_fund/runtime/test_write_authority.py::test_trust_challenge_cannot_cross_roots_or_survive_inventory_drift hedge_fund/runtime/test_write_authority.py::test_single_writer_review_expires_before_acknowledgement -q` - **4 passed in 1.97s**.
- **Progress**: T007 PASS. Existing Windows identity and trust-path tests plus cross-root, inventory-drift, and stale-review denial tests pass on synthetic roots.

## T008–T011 — TUI admission and one-session run

- **Identity**: base revision `dcfc26a139e326213b4a5e9bed57127ba621c4f4`; implementation-file dirty-diff SHA-256 `f05b03a5b65a47ae5f5c7d8cd382e2c5154ee2c44ca4591d10279a538e8009f1`; captured `2026-11-12T15:00:45.5543754+01:00`.
- **Environment / artifact**: Windows `10.0.26200`, Python `3.11.15` 64-bit, pytest `7.4.4`, Poetry environment. Pytest imported worktree source directly; no wheel or installed artifact. Synthetic test roots use the marked `HEDGE_FUND_TEST_MODE` harness. No live provider or broker calls.
- **Scenarios**: trusted local-paper resume uses owner/control lanes and a request ID; a captured fake-data quant run records one tick bound to its request, operation, and capture; unenrolled/untrusted/runtime-scope-unavailable writes deny without root changes; a child process holding the control lane blocks TUI resume and preserves ledger/control bytes; creation and deletion remain denied.
- **Command**: `py -m poetry run pytest hedge_fund/tui/test_admission_regressions.py hedge_fund/runtime/test_writer_map.py::test_writer_map_has_no_stale_entries hedge_fund/runtime/test_writer_map.py::test_writer_map_entry_is_classified_with_real_evidence -q` — **121 passed in 26.74s**.
- **Style / hygiene**: Black (`--line-length 420`), isort (`--profile black`), flake8 (`--max-line-length=420 --extend-ignore=E203`), `git diff --check`, and UTF-8 BOM scan passed on the nine changed Python files.
- **Diagnostic focused gate**: `py -m poetry run pytest hedge_fund/runtime hedge_fund/tui -q` reported **907 passed, 22 skipped, 5 failed in 1875.39s**. Exact dirty-diff hash was not captured for that earlier source state; this run is not final-artifact acceptance evidence.
  - `test_inventory_cache_race.py::test_approval_waiting_for_sibling_publication_does_not_block_halt`: expected `<2.0s`, observed `2.422000000020489s`; T001 baseline observed `2.3439999998081475s`.
  - `test_writer_inventory.py::test_every_production_writer_is_classified_by_admission_class` and `test_writer_map.py::test_every_production_write_primitive_is_mapped`: same six unclassified and five unmapped non-feature sites recorded in T001.
  - `test_writer_map.py::test_writer_map_has_no_stale_entries`: the two stale `wipe_fund` entries were caused by removing the TUI raw delete primitives; entries were removed, and the final targeted writer-map selection passed.
  - `test_native_primitives.py::test_native_process_identity_expires_with_owned_child`: read an empty readiness file. It passed in one isolated worktree run and passed 50 consecutive isolated runs on pre-change revision `b35b0d0`; this occurrence is **INCONCLUSIVE**, not baseline-evidenced.
- **Progress**: T008–T011 targeted admission/run selection PASS. Full runtime/TUI gate remains FAIL on the recorded baseline cases plus the INCONCLUSIVE native-process test; no overall gate pass claimed.
