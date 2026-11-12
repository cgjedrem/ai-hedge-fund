"""Source-based T021 writer map.

Every low-level write primitive in production code must be classified here
with the seam that admits it and the concrete test cases that exercise that
seam. ``level`` records how strong the evidence is:

* ``race``      - deterministic barrier/interleaving test on this seam
* ``denial``    - fail-closed admission/authority denial test, no interleaving
* ``primitive`` - the no-follow primitive itself (exercised by its own tests)
* ``none``      - residual with no race evidence; ``note`` states why

The map is evidence of coverage, not a claim that out-of-band writers are
excluded: same-account writers outside the cooperative protocol are not fenced.
"""

import ast
from pathlib import Path
from typing import NamedTuple

import pytest

PACKAGE = Path(__file__).resolve().parents[1]
REPO = PACKAGE.parent

PRIMITIVES = {
    "write_text",
    "write_bytes",
    "append_bytes",
    "unlink",
    "unlink_file",
    "rename",
    "rename_file",
    "rename_directory",
    "replace",
    "mkdir",
    "touch",
    "rmdir",
    "rmtree",
    "makedirs",
    "remove",
    "move",
    "copy2",
    "copyfile",
    "copytree",
    "write_atomic",
    "symlink",
    "link",
    "truncate",
}

ROOT = "root-no-follow"
TRANSITION = "paper-inventory-transition"
BOUND = "bound-root-write-atomic"
HELPER = "paths-root-helper"
LEGACY = "unenrolled-legacy-branch"
DENIED = "denied-entrypoint"
PRIMITIVE = "no-follow-primitive"
BOOTSTRAP = "pre-enrollment-bootstrap"
RESIDUAL = "residual"


class Writer(NamedTuple):
    seam: str
    level: str
    evidence: tuple[str, ...]
    note: str = ""


M = "hedge_fund/runtime/test_writer_race_matrix.py::"
ICR = "hedge_fund/runtime/test_inventory_cache_race.py::"
ROOT_TESTS = (
    "hedge_fund/runtime/test_root.py::test_handle_relative_mkdir_rejects_reparse_parent",
    "hedge_fund/runtime/test_root.py::test_root_replacement_is_denied_or_detected_before_child_access",
    "hedge_fund/runtime/test_root_unlink.py::test_unlink_never_follows_link_parent_outside_root",
)
LEGACY_NOTE = "raw path is reached only when the paper root is not enrolled; enrolled roots take the transition branch"
BOUND_NOTE = "admitted through RootContext while paths.bound_root covers the target or the target lies under an enrolled root (unbound callers are routed via paths._write_in_root); the raw os.replace remains only for paths outside every enrolled root"
LANE_LOCK = ("hedge_fund/runtime/test_admission.py::test_subject_sessions_conflict_while_controls_remain_independent", "hedge_fund/runtime/test_admission.py::test_control_lane_conflict_has_a_bounded_wait")

WRITER_MAP: dict[tuple[str, str, str], Writer] = {
    # backtesting / research
    ("hedge_fund.backtesting.research", "save_result", "mkdir"): Writer(ROOT, "race", ("hedge_fund/backtesting/test_research.py::test_research_lanes_for_independent_funds_do_not_contend", "hedge_fund/backtesting/test_research.py::test_save_result_admission_denial_preserves_existing_bytes")),
    ("hedge_fund.backtesting.research", "save_result", "write_bytes"): Writer(ROOT, "race", ("hedge_fund/backtesting/test_research.py::test_research_writer_holds_fund_lane_without_runner_lane", "hedge_fund/backtesting/test_research.py::test_save_result_admission_denial_preserves_existing_bytes")),
    # paper broker book
    ("hedge_fund.brokers.paper", "PaperBroker.create", "write_atomic"): Writer(LEGACY, "denial", (ICR + "test_external_drift_during_deploy_is_not_published",), LEGACY_NOTE),
    ("hedge_fund.brokers.paper", "PaperBroker.restore", "write_atomic"): Writer(BOUND, "none", ("hedge_fund/test_run.py::test_enrolled_cli_redo_preserves_guarded_dispatch_and_expires_approval",), "redo-only writer; functional enrolled redo test, no interleaving at restore"),
    ("hedge_fund.brokers.paper", "PaperBroker._save", "write_atomic"): Writer(BOUND, "race", ("hedge_fund/test_run.py::test_enrolled_cli_tick_lane_conflict_leaves_ledger_unchanged", "hedge_fund/web/test_paper_operations.py::test_manual_tick_denies_runner_lane_conflict_without_ledger_change"), BOUND_NOTE),
    # Saxo token refresh lock (user credential scope, not the data root)
    # test-owned SIM policy simulation (outside any fund root; never production custody authority)
    ("hedge_fund.brokers.account_binding", "AccountRegistry._locked", "write_bytes"): Writer(
        ROOT,
        "race",
        ("hedge_fund/brokers/test_account_binding.py::test_concurrent_transfers_of_one_release_digest_are_bounded_and_admit_at_most_one", "hedge_fund/brokers/test_account_binding.py::test_registry_lock_contention_is_busy_without_effects", "hedge_fund/brokers/test_account_binding.py::test_unreadable_or_corrupt_registry_denies_and_inspects_unknown"),
        "generation-checked state replace under the exclusive synthetic registry lock; no production custody authority",
    ),
    ("hedge_fund.brokers.account_binding", "AccountRegistry.initialize", "mkdir"): Writer(ROOT, "denial", ("hedge_fund/brokers/test_account_binding.py::test_registry_initialization_requires_empty_directory", "hedge_fund/brokers/test_account_binding.py::test_root_local_registry_is_rejected"), "one-time provisioning of an empty per-user directory; not concurrently raced"),
    ("hedge_fund.brokers.account_binding", "AccountRegistry.initialize", "write_bytes"): Writer(ROOT, "denial", ("hedge_fund/brokers/test_account_binding.py::test_registry_initialization_requires_empty_directory", "hedge_fund/brokers/test_account_binding.py::test_unverified_private_registry_storage_denies"), "one-time provisioning of key/state; not concurrently raced"),
    ("hedge_fund.brokers.saxo", "_refresh_lock", "mkdir"): Writer(RESIDUAL, "race", ("hedge_fund/brokers/test_saxo_tokens.py::test_two_managers_reread_rotated_token_under_shared_reference_lock", "hedge_fund/brokers/test_saxo_tokens.py::test_existing_refresh_lock_times_out_with_owner_and_is_not_removed"), "credential-scope lock directory outside root admission; raw path follows links"),
    ("hedge_fund.brokers.saxo", "_refresh_lock", "write_text"): Writer(RESIDUAL, "race", ("hedge_fund/brokers/test_saxo_tokens.py::test_existing_refresh_lock_times_out_with_owner_and_is_not_removed",), "credential-scope lock owner file outside root admission"),
    ("hedge_fund.brokers.saxo", "_refresh_lock", "unlink"): Writer(RESIDUAL, "race", ("hedge_fund/brokers/test_saxo_tokens.py::test_refresh_lock_cleanup_failure_does_not_discard_persisted_token",), "credential-scope lock cleanup outside root admission"),
    ("hedge_fund.brokers.saxo", "_refresh_lock", "rmdir"): Writer(RESIDUAL, "race", ("hedge_fund/brokers/test_saxo_tokens.py::test_refresh_lock_cleanup_failure_does_not_discard_persisted_token",), "credential-scope lock cleanup outside root admission"),
    # root caches through the paths helpers
    ("hedge_fund.data.cached", "CachedDataClient._write", "write_text"): Writer(HELPER, "denial", ("hedge_fund/runtime/test_bootstrap.py::test_cache_writes_deny_unenrolled_root",)),
    ("hedge_fund.features.breakpoints", "load_breakpoints", "write_text"): Writer(HELPER, "denial", ("hedge_fund/runtime/test_bootstrap.py::test_cache_writes_deny_unenrolled_root", "hedge_fund/features/test_breakpoints.py::test_authorization_denial_does_not_fall_back_to_stale_cache")),
    ("hedge_fund.llm.cache", "PromptCache.put", "write_text"): Writer(HELPER, "denial", ("hedge_fund/runtime/test_bootstrap.py::test_cache_writes_deny_unenrolled_root",)),
    ("hedge_fund.run", "_backtest", "write_text"): Writer(HELPER, "denial", ("hedge_fund/runtime/test_bootstrap.py::test_cache_writes_deny_unenrolled_root",), "backtest receipt; admitted through the bound root"),
    # fund storage
    ("hedge_fund.fund.storage", "save_spec", "mkdir"): Writer(ROOT, "denial", ("hedge_fund/fund/test_storage.py::test_save_spec_uses_root_context_and_registry_lane", "hedge_fund/fund/test_storage.py::test_save_spec_fails_closed_when_shared_admission_is_unavailable")),
    ("hedge_fund.fund.storage", "save_spec", "write_bytes"): Writer(ROOT, "denial", ("hedge_fund/fund/test_storage.py::test_save_spec_denial_preserves_existing_bytes", "hedge_fund/fund/test_spec.py::test_save_spec_round_trips_and_never_overwrites")),
    # paper deployment
    ("hedge_fund.paper.deployed", "deploy", "mkdir"): Writer(TRANSITION, "race", (M + "test_authority_flip_inside_deploy_creates_no_fund", ICR + "test_external_drift_during_deploy_is_not_published"), "transition branch when enrolled; raw directory.mkdir only on unenrolled roots"),
    ("hedge_fund.paper.deployed", "deploy", "write_bytes"): Writer(TRANSITION, "race", (M + "test_authority_flip_between_deploy_effects_denies_the_next_effect",), "transition branch when enrolled; raw write only on unenrolled roots"),
    ("hedge_fund.paper.deployed", "deploy", "write_text"): Writer(TRANSITION, "race", (M + "test_authority_flip_between_deploy_effects_denies_the_next_effect",)),
    # paper ledger
    ("hedge_fund.paper.ledger", "Ledger._write_approval_publication", "write_atomic"): Writer(BOUND, "denial", ("hedge_fund/web/test_paper_operations.py::test_paper_accept_retries_only_busy_storage_and_records_no_effects",), BOUND_NOTE),
    ("hedge_fund.paper.ledger", "Ledger.begin_redo", "write_atomic"): Writer(BOUND, "denial", ("hedge_fund/paper/test_tick.py::test_redo_completion_failure_keeps_recovery_guard",), BOUND_NOTE),
    ("hedge_fund.paper.ledger", "Ledger.finish_redo", "write_atomic"): Writer(BOUND, "denial", ("hedge_fund/paper/test_tick.py::test_redo_completion_failure_keeps_recovery_guard", "hedge_fund/paper/test_tick.py::test_redo_failure_with_unavailable_halt_requires_reconciliation_and_keeps_cause"), BOUND_NOTE),
    ("hedge_fund.paper.ledger", "Ledger.init", "mkdir"): Writer(ROOT, "race", (M + "test_authority_flip_after_ledger_init_admission_denies_its_mkdir",), "root mkdir when enrolled (flip after init admission, before the effect recheck); raw records_dir mkdir only on unenrolled roots"),
    ("hedge_fund.paper.ledger", "Ledger.init", "write_atomic"): Writer(BOUND, "none", ("hedge_fund/paper/test_ledger.py::test_initialization_cannot_overwrite_a_concurrent_halt",), "cited test takes the unbound raw fallback; no interleaving at the bound root write"),
    ("hedge_fund.paper.ledger", "Ledger.append", "mkdir"): Writer(TRANSITION, "race", (M + "test_authority_flip_inside_ledger_transaction_denies_effect_and_publication", M + "test_ledger_directory_swap_during_append_cannot_write_outside_root"), LEGACY_NOTE),
    ("hedge_fund.paper.ledger", "Ledger.append", "write_text"): Writer(TRANSITION, "race", (M + "test_authority_flip_inside_ledger_transaction_denies_effect_and_publication", ICR + "test_external_target_drift_during_append_is_not_published")),
    ("hedge_fund.paper.ledger", "Ledger.append", "write_atomic"): Writer(LEGACY, "denial", ("hedge_fund/test_run.py::test_cli_paper_writer_denies_attested_migration_as_ownership_unknown",), "denial is the gate on legacy/attested roots; the raw unenrolled branch is functional-tested only"),
    ("hedge_fund.paper.ledger", "Ledger.rewind", "mkdir"): Writer(TRANSITION, "race", (M + "test_junction_swap_during_rewind_cannot_move_record_outside_root",), LEGACY_NOTE),
    ("hedge_fund.paper.ledger", "Ledger.rewind", "rename"): Writer(LEGACY, "denial", ("hedge_fund/test_run.py::test_cli_paper_writer_denies_attested_migration_as_ownership_unknown", "hedge_fund/paper/test_tick.py::test_redo_runs_the_latest_session_again_and_replaces_its_record"), "denial is the gate on legacy/attested roots; the raw unenrolled branch is functional-tested only"),
    ("hedge_fund.paper.ledger", "Ledger.rewind", "rename_file"): Writer(TRANSITION, "race", (M + "test_junction_swap_during_rewind_cannot_move_record_outside_root", M + "test_crash_after_rewind_rename_requires_offline_reconciliation")),
    ("hedge_fund.paper.ledger", "Ledger.rewind", "unlink"): Writer(LEGACY, "denial", ("hedge_fund/test_run.py::test_cli_paper_writer_denies_attested_migration_as_ownership_unknown", "hedge_fund/paper/test_tick.py::test_redo_runs_the_latest_session_again_and_replaces_its_record"), "denial is the gate on legacy/attested roots; the raw unenrolled branch is functional-tested only"),
    ("hedge_fund.paper.ledger", "Ledger.rewind", "unlink_file"): Writer(TRANSITION, "race", (M + "test_authority_flip_after_rewind_effect_blocks_head_publication",)),
    ("hedge_fund.paper.ledger", "Ledger.checkpoint", "write_atomic"): Writer(BOUND, "race", (ICR + "test_reserved_intraday_observation_still_rejects_external_drift",), BOUND_NOTE),
    ("hedge_fund.paper.ledger", "Ledger._write_control", "write_atomic"): Writer(BOUND, "race", ("hedge_fund/test_run.py::test_cli_halt_does_not_wait_for_a_busy_control_lane", "hedge_fund/paper/test_ledger.py::test_initialization_cannot_overwrite_a_concurrent_halt"), BOUND_NOTE),
    ("hedge_fund.paper.ledger", "Ledger._publish_approval", "write_atomic"): Writer(BOUND, "denial", ("hedge_fund/web/test_paper_operations.py::test_paper_accept_retries_only_busy_storage_and_records_no_effects",), BOUND_NOTE),
    ("hedge_fund.paper.ledger", "Ledger._clear_approval", "unlink"): Writer(LEGACY, "denial", ("hedge_fund/paper/test_ledger.py::test_approval_clear_logs_unlink_error",), LEGACY_NOTE),
    ("hedge_fund.paper.ledger", "Ledger._unlink_enrolled", "unlink_file"): Writer(ROOT, "race", (M + "test_authority_flip_between_entry_and_approval_unlink_keeps_approval", M + "test_junction_swap_before_approval_unlink_removes_nothing_outside")),
    ("hedge_fund.paper.ledger", "Ledger.log_event", "append_bytes"): Writer(
        ROOT,
        "race",
        (
            M + "test_authority_flip_inside_audit_transition_appends_no_event",
            "hedge_fund/paper/test_ledger.py::test_audit_append_rejects_hardlinked_event_file",
            "hedge_fund/runtime/test_writer_races.py::test_two_process_audit_appends_are_complete_and_uninterleaved",
        ),
        "handle-relative append runs under paper_audit_transition; reparse and hard-link targets deny",
    ),
    # legacy paper runner (disabled on enrolled roots)
    ("hedge_fund.paper.runner", "serve", "write_text"): Writer(DENIED, "denial", ("hedge_fund/paper/test_runner.py::test_legacy_runner_entrypoints_deny_before_pid_or_provider_effects", "hedge_fund/paper/test_runner.py::test_enrolled_root_blocks_legacy_runner_start_and_pid_signaling")),
    ("hedge_fund.paper.runner", "serve", "unlink"): Writer(DENIED, "denial", ("hedge_fund/paper/test_runner.py::test_legacy_runner_entrypoints_deny_before_pid_or_provider_effects",)),
    ("hedge_fund.paper.runner", "spawn_runner", "open:a"): Writer(DENIED, "denial", ("hedge_fund/paper/test_runner.py::test_enrolled_root_blocks_legacy_runner_start_and_pid_signaling",)),
    # paths helpers
    ("hedge_fund.paths", "write_bytes", "mkdir"): Writer(HELPER, "denial", ("hedge_fund/runtime/test_bootstrap.py::test_cache_writes_deny_unenrolled_root",), "root branch when bound or under an enrolled root; raw branch only for targets outside every enrolled root"),
    ("hedge_fund.paths", "write_bytes", "write_bytes"): Writer(HELPER, "denial", ("hedge_fund/runtime/test_bootstrap.py::test_cache_writes_deny_unenrolled_root",), "root branch when bound or under an enrolled root; raw branch only for targets outside every enrolled root"),
    ("hedge_fund.paths", "_write_in_root", "mkdir"): Writer(ROOT, "race", ("hedge_fund/runtime/test_writer_admission_race_matrix.py::test_unconfigured_writes_into_an_enrolled_root_are_routed_through_admission", "hedge_fund/runtime/test_writer_admission_race_matrix.py::test_alias_into_an_enrolled_root_subdirectory_is_routed_through_admission")),
    ("hedge_fund.paths", "_write_in_root", "write_bytes"): Writer(
        ROOT, "race", ("hedge_fund/runtime/test_writer_admission_race_matrix.py::test_unconfigured_writes_into_an_enrolled_root_are_routed_through_admission", "hedge_fund/runtime/test_writer_admission_race_matrix.py::test_unconfigured_paper_write_without_a_held_lane_is_denied", "hedge_fund/runtime/test_writer_admission_race_matrix.py::test_unusual_enrollment_state_never_falls_back_to_a_raw_write")
    ),
    ("hedge_fund.paths", "write_text", "write_bytes"): Writer(HELPER, "denial", ("hedge_fund/runtime/test_bootstrap.py::test_cache_writes_deny_unenrolled_root",)),
    ("hedge_fund.paths", "ensure_directory", "mkdir"): Writer(HELPER, "denial", ("hedge_fund/runtime/test_bootstrap.py::test_cache_writes_deny_unenrolled_root",)),
    ("hedge_fund.paths", "ensure_mandates_dir", "mkdir"): Writer(HELPER, "denial", ("hedge_fund/fund/test_storage.py::test_save_spec_uses_root_context_and_registry_lane",)),
    ("hedge_fund.paths", "ensure_mandates_dir", "write_bytes"): Writer(HELPER, "denial", ("hedge_fund/fund/test_storage.py::test_save_spec_uses_root_context_and_registry_lane",)),
    ("hedge_fund.paths", "write_atomic", "write_bytes"): Writer(HELPER, "none", (), "bound RootContext write; no interleaving test at this helper (callers are lane-guarded)"),
    ("hedge_fund.paths", "write_atomic", "os.open"): Writer(RESIDUAL, "none", (), "temporary file of the unbound raw fallback (O_CREAT|O_EXCL, follows parent links)"),
    ("hedge_fund.paths", "write_atomic", "fdopen:w"): Writer(RESIDUAL, "none", (), "writes the unbound raw fallback temporary file"),
    ("hedge_fund.paths", "write_atomic", "replace"): Writer(RESIDUAL, "none", (), BOUND_NOTE),
    ("hedge_fund.paths", "write_atomic", "unlink"): Writer(RESIDUAL, "none", (), "temporary-file cleanup of the unbound raw fallback"),
    # admission / registry locks
    ("hedge_fund.runtime.admission", "RootOwnerLease.acquire", "mkdir"): Writer(ROOT, "race", ("hedge_fund/runtime/test_handover.py::test_migration_exclusive_lock_conflicts_with_shared_participant",)),
    ("hedge_fund.runtime.admission", "RootMigrationLease.acquire", "mkdir"): Writer(ROOT, "race", ("hedge_fund/runtime/test_handover.py::test_migration_exclusive_lock_conflicts_with_shared_participant",)),
    ("hedge_fund.runtime.admission", "AdmissionCoordinator._lock", "mkdir"): Writer(ROOT, "race", LANE_LOCK),
    ("hedge_fund.runtime.admission", "AdmissionCoordinator.operation_service_lease", "mkdir"): Writer(
        ROOT,
        "race",
        ("hedge_fund/web/test_jobs.py::test_second_process_cannot_recover_a_live_peer_operation",),
        "root-private lifetime lock; cooperating service recovery only",
    ),
    ("hedge_fund.runtime.admission", "_local_lane", "remove"): Writer(PRIMITIVE, "primitive", (), "list.remove on an in-memory waiter queue; not a filesystem write"),
    # settings, child environment, credentials
    ("hedge_fund.runtime.configuration", "save_settings", "mkdir"): Writer(ROOT, "race", ("hedge_fund/web/test_settings_provenance.py::test_version_changes_and_external_writer_require_restart_and_reject_stale_saves",)),
    ("hedge_fund.runtime.configuration", "save_settings", "write_bytes"): Writer(ROOT, "race", ("hedge_fund/web/test_settings_provenance.py::test_version_changes_and_external_writer_require_restart_and_reject_stale_saves",)),
    ("hedge_fund.runtime.configuration", "build_child_environment", "mkdir"): Writer(ROOT, "denial", ("hedge_fund/web/test_settings_provenance.py::test_settings_update_after_snapshot_requires_restart_of_active_capture_without_hot_swap",), "creates private child HOME/temp directories inside the root"),
    ("hedge_fund.runtime.credentials", "CredentialStore._write_bytes", "mkdir"): Writer(ROOT, "race", ("hedge_fund/runtime/test_credentials.py::test_credential_store_compare_and_swap_rejects_stale_version",)),
    ("hedge_fund.runtime.credentials", "CredentialStore._write_bytes", "write_bytes"): Writer(ROOT, "race", ("hedge_fund/runtime/test_credentials.py::test_credential_store_compare_and_swap_rejects_stale_version",)),
    ("hedge_fund.runtime.credentials", "save_credential", "write_atomic"): Writer(RESIDUAL, "denial", ("hedge_fund/web/test_settings.py::test_credential_write_is_allowlisted_write_only_and_control_safe",), BOUND_NOTE),
    # handover records and relocation
    ("hedge_fund.runtime.handover", "relocate_existing", "mkdir"): Writer(ROOT, "denial", ("hedge_fund/runtime/test_write_authority.py::test_relocation_refuses_reparse_points_in_source",)),
    ("hedge_fund.runtime.handover", "relocate_existing", "write_bytes"): Writer(ROOT, "denial", ("hedge_fund/runtime/test_write_authority.py::test_relocation_refuses_reparse_points_in_source",)),
    ("hedge_fund.runtime.handover", "_write_private_json", "write_bytes"): Writer(
        BOOTSTRAP,
        "denial",
        ("hedge_fund/runtime/test_write_authority.py::test_existing_root_needs_fresh_root_bound_trust_ack_and_revocation_is_fail_closed",),
        "root-private trust records require offline RootMigrationLease admission",
    ),
    ("hedge_fund.runtime.handover", "_write_attestation_artifact", "mkdir"): Writer(
        BOOTSTRAP,
        "denial",
        ("hedge_fund/runtime/test_handover.py::test_attestation_artifact_storage_is_root_private_and_refuses_overwrite",),
        "destination-only attestation path after private-storage verification",
    ),
    ("hedge_fund.runtime.handover", "_remove_single_writer_challenge", "unlink_file"): Writer(
        BOOTSTRAP,
        "denial",
        ("hedge_fund/runtime/test_write_authority.py::test_existing_root_needs_fresh_root_bound_trust_ack_and_revocation_is_fail_closed",),
        "root-private review challenge removal requires offline RootMigrationLease admission",
    ),
    ("hedge_fund.runtime.handover", "PaperInventoryTransition.mkdir", "mkdir"): Writer(TRANSITION, "race", (M + "test_authority_flip_inside_deploy_creates_no_fund", M + "test_ledger_directory_swap_during_append_cannot_write_outside_root")),
    ("hedge_fund.runtime.handover", "PaperInventoryTransition.write_text", "write_bytes"): Writer(TRANSITION, "race", (M + "test_authority_flip_inside_ledger_transaction_denies_effect_and_publication", M + "test_authority_flip_between_deploy_effects_denies_the_next_effect")),
    ("hedge_fund.runtime.handover", "PaperInventoryTransition.write_bytes", "write_bytes"): Writer(TRANSITION, "race", (M + "test_authority_flip_between_deploy_effects_denies_the_next_effect",)),
    ("hedge_fund.runtime.handover", "PaperInventoryTransition.rename_file", "rename_file"): Writer(TRANSITION, "race", (M + "test_junction_swap_during_rewind_cannot_move_record_outside_root",)),
    ("hedge_fund.runtime.handover", "PaperInventoryTransition.unlink_file", "unlink_file"): Writer(TRANSITION, "race", (M + "test_authority_flip_after_rewind_effect_blocks_head_publication",)),
    ("hedge_fund.runtime.handover", "recover_stale_reservation", "mkdir"): Writer(ROOT, "race", ("hedge_fund/runtime/test_handover.py::test_stale_reservation_recovery_waits_for_shared_root_owners",)),
    ("hedge_fund.runtime.handover", "_write_stale_recovery_record", "write_bytes"): Writer(ROOT, "denial", ("hedge_fund/runtime/test_handover.py::test_stale_reservation_recovery_requires_attestation_and_leaves_no_record_on_denial",)),
    ("hedge_fund.runtime.handover", "_write_record", "write_bytes"): Writer(ROOT, "race", (M + "test_authority_flip_after_rewind_effect_blocks_head_publication", ICR + "test_existing_drift_is_not_published_by_a_later_append", "hedge_fund/runtime/test_write_authority.py::test_writer_already_holding_lanes_is_denied_at_write_time_after_authority_flips")),
    # lifecycle archive
    ("hedge_fund.runtime.lifecycle", "LifecycleArchiveStore.archive", "mkdir"): Writer(ROOT, "race", (M + "test_authority_flip_after_lifecycle_journal_denies_move", "hedge_fund/runtime/test_lifecycle.py::test_cross_process_writer_conflict_preserves_independent_template")),
    ("hedge_fund.runtime.lifecycle", "LifecycleArchiveStore._move", "rename_file"): Writer(ROOT, "race", (M + "test_authority_flip_after_lifecycle_journal_denies_move",)),
    ("hedge_fund.runtime.lifecycle", "LifecycleArchiveStore._move", "rename_directory"): Writer(ROOT, "race", (M + "test_authority_flip_after_lifecycle_journal_denies_move",)),
    ("hedge_fund.runtime.lifecycle", "LifecycleArchiveStore._write_index", "mkdir"): Writer(ROOT, "race", (M + "test_authority_flip_before_lifecycle_head_transition_keeps_heads",)),
    ("hedge_fund.runtime.lifecycle", "LifecycleArchiveStore._write_index", "write_bytes"): Writer(ROOT, "race", (M + "test_authority_flip_before_lifecycle_head_transition_keeps_heads",)),
    # operations store
    ("hedge_fund.runtime.operations", "OperationStore._write_bytes", "mkdir"): Writer(ROOT, "race", ("hedge_fund/runtime/test_operations.py::test_confirmation_race_admits_only_one_request",)),
    ("hedge_fund.runtime.operations", "OperationStore._write_bytes", "write_bytes"): Writer(ROOT, "race", ("hedge_fund/runtime/test_operations.py::test_confirmation_race_admits_only_one_request", "hedge_fund/runtime/test_operations.py::test_same_request_id_with_changed_payload_conflicts")),
    # owned runner
    ("hedge_fund.runtime.owned_runner", "OwnedRunnerManager._start_locked", "mkdir"): Writer(ROOT, "race", ("hedge_fund/web/test_paper_operations.py::test_runner_start_rejects_head_changed_after_acceptance_before_spawn",)),
    ("hedge_fund.runtime.owned_runner", "_write_record", "write_bytes"): Writer(ROOT, "race", ("hedge_fund/web/test_paper_operations.py::test_owned_runner_child_starts_and_stops_with_exact_process_identity", "hedge_fund/runtime/test_lifecycle.py::test_unverified_starting_record_blocks_archive_even_with_free_runner_lane")),
    # no-follow primitives
    ("hedge_fund.runtime.root", "RootContext.prepare_private_storage", "mkdir"): Writer(PRIMITIVE, "primitive", ("hedge_fund/runtime/test_root.py::test_concurrent_root_validation_and_private_storage_checks",)),
    ("hedge_fund.runtime.root", "_posix_unlink_relative", "unlink"): Writer(PRIMITIVE, "primitive", ROOT_TESTS, "POSIX lstat->unlinkat is not identity-fenced against a same-name swap"),
    ("hedge_fund.runtime.root", "_posix_mkdir_relative", "mkdir"): Writer(PRIMITIVE, "primitive", ROOT_TESTS),
    ("hedge_fund.runtime.root", "_open_posix_chain", "os.open"): Writer(PRIMITIVE, "primitive", ROOT_TESTS, "POSIX-only no-follow open with computed flags (directory/read, no create); not executed on the Windows evidence host"),
    ("hedge_fund.runtime.root", "_posix_parent_fd", "os.open"): Writer(PRIMITIVE, "primitive", ROOT_TESTS, "POSIX-only no-follow open with computed flags (directory/read, no create); not executed on the Windows evidence host"),
    ("hedge_fund.runtime.root", "_posix_read_relative", "os.open"): Writer(PRIMITIVE, "primitive", ROOT_TESTS, "POSIX-only no-follow open with computed flags (directory/read, no create); not executed on the Windows evidence host"),
    ("hedge_fund.runtime.root", "_posix_mkdir_relative", "os.open"): Writer(PRIMITIVE, "primitive", ROOT_TESTS, "POSIX-only reopen of the created directory with O_NOFOLLOW; not executed on the Windows evidence host"),
    ("hedge_fund.runtime.root", "_posix_open_lock_relative", "os.open"): Writer(PRIMITIVE, "primitive", ("hedge_fund/runtime/test_admission.py::test_control_lane_conflict_has_a_bounded_wait",), "POSIX-only O_CREAT|O_NOFOLLOW lock file relative to a no-follow parent fd; not executed on the Windows evidence host"),
    ("hedge_fund.runtime.root", "_posix_append_relative", "os.open"): Writer(PRIMITIVE, "primitive", ("hedge_fund/runtime/test_root.py::test_handle_relative_append_preserves_bytes_and_rejects_hardlinks",), "POSIX-only O_APPEND|O_NOFOLLOW open; not executed on the Windows evidence host"),
    ("hedge_fund.runtime.root", "_posix_append_relative", "os.write"): Writer(PRIMITIVE, "primitive", ("hedge_fund/runtime/test_root.py::test_handle_relative_append_preserves_bytes_and_rejects_hardlinks",), "POSIX-only write through the verified append handle; not executed on the Windows evidence host"),
    ("hedge_fund.runtime.root", "_posix_write_relative", "os.open"): Writer(PRIMITIVE, "primitive", ROOT_TESTS),
    ("hedge_fund.runtime.root", "_posix_write_relative", "fdopen:wb"): Writer(PRIMITIVE, "primitive", ROOT_TESTS),
    ("hedge_fund.runtime.root", "_posix_write_relative", "replace"): Writer(PRIMITIVE, "primitive", ROOT_TESTS),
    ("hedge_fund.runtime.root", "_posix_write_relative", "unlink"): Writer(PRIMITIVE, "primitive", ROOT_TESTS),
    # TUI destructive writer (always denied)
    ("hedge_fund.tui.funds", "wipe_fund", "unlink"): Writer(DENIED, "denial", ("hedge_fund/tui/test_paper.py::test_tui_delete_denies_orphaned_admission_state_without_side_effects", "hedge_fund/tui/test_admission_regressions.py::test_mandate_library_delete_is_denied_and_keeps_every_file")),
    ("hedge_fund.tui.funds", "wipe_fund", "rmtree"): Writer(DENIED, "denial", ("hedge_fund/tui/test_paper.py::test_tui_delete_denies_orphaned_admission_state_without_side_effects",)),
    # web
    ("hedge_fund.web.__main__", "main", "mkdir"): Writer(BOOTSTRAP, "none", (), "creates the explicit demo root before RootContext opens it; no enrolled data exists yet"),
    ("hedge_fund.web.demo", "seed_demo", "mkdir"): Writer(BOOTSTRAP, "none", (), "creates an empty synthetic demo root before enroll_fresh"),
    ("hedge_fund.web.services", "DeskService.update_mandate", "rename_file"): Writer(ROOT, "race", (M + "test_mandate_update_authority_flip_reports_exact_partial_state",), "rename and rewrite are not journaled; a flip between them is reported as needing reconciliation"),
    ("hedge_fund.web.services", "DeskService.update_mandate", "write_bytes"): Writer(ROOT, "race", (M + "test_mandate_update_authority_flip_reports_exact_partial_state", "hedge_fund/web/test_services.py::test_mandate_update_denies_paper_inventory_drift_before_mutation")),
    ("hedge_fund.web.services", "DeskService._ensure_dir", "mkdir"): Writer(ROOT, "denial", ("hedge_fund/web/test_services.py::test_read_only_enrolled_service_reports_explicit_write_denial",)),
}


def _open_mode(node: ast.Call) -> str | None:
    mode = None
    if len(node.args) >= 2 and isinstance(node.args[1], ast.Constant):
        mode = node.args[1].value
    for keyword in node.keywords:
        if keyword.arg == "mode" and isinstance(keyword.value, ast.Constant):
            mode = keyword.value.value
    if isinstance(node.func, ast.Attribute) and node.args and isinstance(node.args[0], ast.Constant) and mode is None:
        mode = node.args[0].value
    return mode if isinstance(mode, str) and any(flag in mode for flag in "wax+") else None


class _Scanner(ast.NodeVisitor):
    def __init__(self, module: str) -> None:
        self.module = module
        self.stack: list[str] = []
        self.found: dict[tuple[str, str, str], list[int]] = {}

    def _scope(self, node) -> None:
        self.stack.append(node.name)
        self.generic_visit(node)
        self.stack.pop()

    visit_FunctionDef = visit_AsyncFunctionDef = visit_ClassDef = _scope

    def visit_Call(self, node: ast.Call) -> None:
        func = node.func
        name = func.attr if isinstance(func, ast.Attribute) else func.id if isinstance(func, ast.Name) else None
        primitive = None
        if name in PRIMITIVES:
            # str.replace(old, new) is not a filesystem write; Path.replace(target) is.
            is_os = isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name) and func.value.id == "os"
            if not (name == "replace" and not is_os and len(node.args) != 1):
                primitive = name
        elif name == "open" and isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name) and func.value.id == "os":
            flags = {item.attr for item in ast.walk(node.args[1]) if isinstance(item, ast.Attribute) and item.attr.startswith("O_")} if len(node.args) >= 2 else set()
            # Flags built elsewhere (a variable) cannot be proven read-only, so they must be mapped.
            if not flags or flags & {"O_CREAT", "O_WRONLY", "O_RDWR", "O_APPEND", "O_TRUNC"}:
                primitive = "os.open"
        elif name == "write" and isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name) and func.value.id == "os":
            primitive = "os.write"
        elif name == "fdopen":
            mode = _open_mode(node)
            if mode is not None:
                primitive = f"fdopen:{mode}"
        elif name == "open":
            mode = _open_mode(node)
            if mode is not None:
                primitive = f"open:{mode}"
        if primitive is not None:
            key = (self.module, ".".join(self.stack) or "<module>", primitive)
            self.found.setdefault(key, []).append(node.lineno)
        self.generic_visit(node)


def _production_modules():
    for path in sorted(PACKAGE.rglob("*.py")):
        relative = path.relative_to(REPO)
        if path.name.startswith("test_") or path.name == "conftest.py" or "test_support" in relative.parts:
            continue
        yield ".".join(relative.with_suffix("").parts), path


def _scan() -> dict[tuple[str, str, str], list[int]]:
    found: dict[tuple[str, str, str], list[int]] = {}
    for module, path in _production_modules():
        scanner = _Scanner(module)
        scanner.visit(ast.parse(path.read_text(encoding="utf-8-sig")))
        found.update(scanner.found)
    return found


def _test_names(relative: str) -> set[str]:
    tree = ast.parse((REPO / relative).read_text(encoding="utf-8-sig"))
    return {node.name for node in tree.body if isinstance(node, ast.FunctionDef) and node.name.startswith("test_")}


def test_every_production_write_primitive_is_mapped():
    found = _scan()
    unmapped = sorted(f"{module}:{qualname}:{primitive} lines {lines}" for (module, qualname, primitive), lines in found.items() if (module, qualname, primitive) not in WRITER_MAP)
    assert not unmapped, "unmapped raw write callsites:\n" + "\n".join(unmapped)


def test_writer_map_has_no_stale_entries():
    found = _scan()
    stale = sorted(":".join(key) for key in WRITER_MAP if key not in found)
    assert not stale, "writer map entries no longer present in source:\n" + "\n".join(stale)


@pytest.mark.parametrize("key", sorted(WRITER_MAP), ids=lambda key: ":".join(key))
def test_writer_map_entry_is_classified_with_real_evidence(key):
    writer = WRITER_MAP[key]
    assert writer.seam in {ROOT, TRANSITION, BOUND, HELPER, LEGACY, DENIED, PRIMITIVE, BOOTSTRAP, RESIDUAL}
    assert writer.level in {"race", "denial", "primitive", "none"}
    if writer.level == "none" or writer.seam in {RESIDUAL, BOOTSTRAP, BOUND, LEGACY}:
        assert writer.note, "residual, bootstrap, bound and legacy writers must state their limitation"
    if writer.level != "none" and writer.seam != PRIMITIVE:
        assert writer.evidence, "evidence-bearing entries must name at least one test"
    for node in writer.evidence:
        relative, _, name = node.partition("::")
        assert name in _test_names(relative), f"{node} does not exist"


def test_writer_map_reports_residuals_explicitly():
    residual = sorted(":".join(key) for key, writer in WRITER_MAP.items() if writer.seam == RESIDUAL or writer.level == "none")
    # Keep the residual set visible; shrinking it must be a deliberate edit.
    assert residual == [
        "hedge_fund.brokers.paper:PaperBroker.restore:write_atomic",
        "hedge_fund.brokers.saxo:_refresh_lock:mkdir",
        "hedge_fund.brokers.saxo:_refresh_lock:rmdir",
        "hedge_fund.brokers.saxo:_refresh_lock:unlink",
        "hedge_fund.brokers.saxo:_refresh_lock:write_text",
        "hedge_fund.paper.ledger:Ledger.init:write_atomic",
        "hedge_fund.paths:write_atomic:fdopen:w",
        "hedge_fund.paths:write_atomic:os.open",
        "hedge_fund.paths:write_atomic:replace",
        "hedge_fund.paths:write_atomic:unlink",
        "hedge_fund.paths:write_atomic:write_bytes",
        "hedge_fund.runtime.credentials:save_credential:write_atomic",
        "hedge_fund.web.__main__:main:mkdir",
        "hedge_fund.web.demo:seed_demo:mkdir",
    ]
