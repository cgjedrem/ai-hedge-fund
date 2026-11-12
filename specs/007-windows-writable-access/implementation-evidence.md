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
