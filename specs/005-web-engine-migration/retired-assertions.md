# Retired UI assertion inventory

**Status:** inventory only; no TUI test, assertion, module, or dependency removed.
**Source inspected:** current `hedge_fund/tui/test_*.py`, plus external tests importing
`hedge_fund.tui`.
**Inventory:** 48 TUI test functions with 385 direct `assert` sites; 28 external
TUI-importing test functions with 179 direct `assert` sites. AST count includes `assert`
nodes inside each test function; `pytest.raises` and mock/helper checks are not included
in that count. Every replacement below is planned, not implemented or passed.

## `hedge_fund/tui/test_backtest.py`

| Existing test | Direct asserts | Assertion semantics | Planned neutral/web replacement | Status |
| --- | ---: | --- | --- | --- |
| `test_backtest_daily_board_matches_final_metrics_and_uses_fill_dates` | 4 | Final metrics, fill dates, and tape order match canonical backtest result. | `hedge_fund/reporting/test_console.py::test_backtest_report_uses_final_metrics_and_fill_dates`; T008, T013. | PENDING — keep original |

## `hedge_fund/tui/test_builder.py`

| Existing test | Direct asserts | Assertion semantics | Planned neutral/web replacement | Status |
| --- | ---: | --- | --- | --- |
| `test_mixed_description_identifies_short_analysts` | 3 | Short composition description names required analyst support. | `hedge_fund/fund/test_spec.py::test_custom_short_roster_requires_supported_analyst`; `frontend/src/pages/builder.test.tsx::shortCompositionShowsSupportRule`; T046, T048. | PENDING — keep original |
| `test_builder_derives_rules_and_back_navigation_does_not_duplicate` | 10 | Builder derives mandate fields; back navigation does not duplicate sleeves/rules. | `frontend/src/pages/builder.test.tsx::createsMandateWithoutDuplicateSleevesAfterBackNavigation`; `frontend/e2e/configuration.spec.ts::fullFieldSave`; T048, T049, T056. | PENDING — keep original |
| `test_builder_existing_name_and_save_race_never_overwrite` | 7 | Existing identity and concurrent save cannot overwrite a mandate. | `hedge_fund/fund/test_storage.py::test_revision_bound_create_rejects_collision_and_save_race`; `hedge_fund/web/test_services.py::test_stale_revision_conflicts`; T046, T055. | PENDING — keep original |
| `test_builder_paper_mode_builds_a_live_fund_and_refuses_taken_names` | 16 | Paper flow builds validated fund and rejects occupied names. | `hedge_fund/fund/test_spec.py::test_full_mandate_round_trip`; `frontend/src/pages/builder.test.tsx::validPaperMandateCreateRejectsCollision`; T046, T048, T054, T056. | PENDING — keep original |
| `test_builder_paper_mode_sets_approval_required` | 5 | Created paper mandate stores its approval gate. | `hedge_fund/fund/test_spec.py::test_approval_gate_round_trips_with_default_off_omission`; T046, T054, T056. | PENDING — keep original |
| `test_builder_minute_path_sets_interval_and_window_and_offers_start_running` | 29 | Cadence, interval, window and explicit start journey are preserved. | `hedge_fund/fund/test_spec.py::test_minute_schedule_round_trips`; `frontend/src/pages/paper.test.tsx::minuteCadenceShowsReviewedStart`; T026, T046, T048, T056. | PENDING — keep original |
| `test_builder_minute_helpers_are_pure` | 9 | Schedule labels/helpers are deterministic and have no side effects. | `hedge_fund/runtime/test_defaults.py::test_minute_schedule_labels_keep_interval_and_timezone_output`; `frontend/src/pages/paper.test.tsx::minuteCadenceShowsReviewedStart`; T008, T048. | EXPECTED-RED TEST ADDED — helper module absent; original retained |
| `test_builder_replaces_a_taken_name_only_after_yes_and_only_at_the_end` | 15 | Replacement follows explicit confirmation and occurs only after validation. | `hedge_fund/web/test_actions.py::test_replacement_is_revision_bound_and_creates_new_identity`; `frontend/src/components/lifecycle-controls.test.tsx::replacementRequiresReviewedNewIdentity`; T095, T097, T104, T105. | PENDING — keep original |
| `test_builder_paper_mode_run_its_first_session_opens_the_approval_step` | 5 | First-session action opens review before any execution. | `hedge_fund/web/test_jobs.py::test_manual_preview_precedes_admission`; `frontend/src/pages/paper.test.tsx::manualRunReviewPrecedesExecution`; T026, T028, T033, T038. | PENDING — keep original |

## `hedge_fund/tui/test_builder_broker.py`

| Existing test | Direct asserts | Assertion semantics | Planned neutral/web replacement | Status |
| --- | ---: | --- | --- | --- |
| `test_builder_blocks_daily_saxo_and_deploys_minute_saxo` | 14 | Broker/cadence restrictions are validated before deployment. | `hedge_fund/fund/test_spec_broker.py::test_saxo_cadence_restrictions_round_trip`; `hedge_fund/brokers/test_account_binding.py::test_fake_sim_binding_is_exclusive`; T046, T096, T099. | PENDING — keep original |

## `hedge_fund/tui/test_funds.py`

| Existing test | Direct asserts | Assertion semantics | Planned neutral/web replacement | Status |
| --- | ---: | --- | --- | --- |
| `test_both_pickers_disable_only_invalid_configurations` | 10 | Valid mandates remain selectable; malformed entries remain visible and disabled. | `hedge_fund/web/test_services.py::test_mandate_list_keeps_invalid_entry_errors`; `frontend/src/pages/mandates.test.tsx::invalidMandateIsVisibleAndNonExecutable`; T046, T055. | PENDING — keep original |
| `test_all_invalid_funds_do_not_crash_home_picker` | 1 | Empty valid set yields an actionable error, not a crash. | `hedge_fund/web/test_services.py::test_all_invalid_mandates_return_consistent_error`; `frontend/src/pages/home.test.tsx::allInvalidMandatesShowActionableState`; T039, T046, T055. | PENDING — keep original |
| `test_latest_backtest_sets_headline_regardless_of_version` | 5 | Latest persisted result drives headline independent of version label. | `hedge_fund/backtesting/test_research.py::test_latest_result_identity_drives_headline`; `hedge_fund/reporting/test_reports.py::test_research_headline_uses_latest_persisted_result`; T111, T118, T119. | PENDING — keep original |

## `hedge_fund/tui/test_home.py`

| Existing test | Direct asserts | Assertion semantics | Planned neutral/web replacement | Status |
| --- | ---: | --- | --- | --- |
| `test_picker_and_masked_key_save_or_cancel` | 12 | Provider/model selection and masked credential save/cancel behavior. | `hedge_fund/web/test_settings.py::test_secret_set_status_and_delete_never_echo`; `frontend/src/pages/settings.test.tsx::credentialSetDeleteNeverEcho`; T045, T048, T053, T057. | PENDING — keep original |
| `test_missing_key_gate_save_resumes_and_cancel_does_not` | 5 | Missing-key gate permits deliberate continuation only after explicit save. | `hedge_fund/runtime/test_policy.py::test_missing_credential_denies_before_provider`; `frontend/src/pages/settings.test.tsx::missingCredentialGateRequiresExplicitSave`; T010, T017, T045, T057. | PENDING — keep original |
| `test_yfinance_mode_needs_no_fd_key` | 2 | Free provider path works with no paid-provider key. | `hedge_fund/data/test_factory.py::test_yfinance_default_needs_no_key`; `hedge_fund/runtime/test_policy.py::test_free_data_needs_no_paid_credential`; T010, T052. | PENDING — keep original |
| `test_fd_mode_still_demands_the_fd_key` | 3 | Old paid-provider key gate. Replacement must also require per-operation paid authorization; key presence alone is not consent. | `hedge_fund/runtime/test_policy.py::test_paid_provider_requires_operation_authorization`; `hedge_fund/web/test_settings.py::test_key_presence_never_authorizes_call`; T010, T017, T052, T053. | PENDING — keep original |
| `test_credential_precedence` | 1 | Environment value outranks local dotenv value. | `hedge_fund/runtime/test_configuration.py::test_launch_override_precedes_persisted_setting_and_default`; `hedge_fund/runtime/test_root.py::test_dotenv_is_exact_root_opt_in`; T007, T010, T012, T016. | PENDING — keep original |
| `test_home_offers_paper_trading_first_and_an_empty_paper_screen_builds` | 12 | Home navigation prioritizes paper; empty paper state reaches builder. | `frontend/src/pages/home.test.tsx::paperEntryAndEmptyBuilderState`; T039, T048. | PENDING — keep original |

## `hedge_fund/tui/test_keys.py`

| Existing test | Direct asserts | Assertion semantics | Planned neutral/web replacement | Status |
| --- | ---: | --- | --- | --- |
| `test_save_credential_requests_private_atomic_file` | 3 | Credential persistence uses private atomic replacement/mode. | `hedge_fund/runtime/test_credentials.py::test_private_atomic_credential_update`; `hedge_fund/web/test_settings.py::test_credential_update_is_surgical`; T045, T050, T059. | PENDING — keep original |

## `hedge_fund/tui/test_paper.py`

| Existing test | Direct asserts | Assertion semantics | Planned neutral/web replacement | Status |
| --- | ---: | --- | --- | --- |
| `test_all_modes_can_be_backtested_and_paper_traded` | 6 | Supported mandate modes reach canonical backtest and paper flow. | `hedge_fund/test_run.py::test_headless_paper_and_backtest_modes_without_textual`; `hedge_fund/backtesting/test_fund.py::test_backtest_enforces_each_mode`; T077. | PENDING — keep original |
| `test_paper_screen_records_approval_verdicts_from_y_and_n` | 12 | Approve/reject votes are recorded against the displayed decision. | `hedge_fund/paper/test_ledger.py::test_verdict_binds_timestamp_and_source_hash`; `frontend/src/components/decision-controls.test.tsx::verdictsBindDisplayedIdentity`; T063, T065, T069, T071. | PENDING — keep original |
| `test_run_session_board_reports_a_gated_skip` | 2 | Expired/unapproved execution is skipped with explicit status. | `hedge_fund/paper/test_tick.py::test_due_execution_skips_expired_approval`; `frontend/src/pages/paper.test.tsx::gatedSkipHasExplicitStatus`; T026, T028, T034. | PENDING — keep original |
| `test_paper_screen_disables_approval_actions_outside_the_gate` | 3 | Verdict actions are unavailable outside approval gate. | `hedge_fund/web/test_actions.py::test_verdict_denied_outside_gate`; `frontend/src/components/decision-controls.test.tsx::approvalActionsDisabledOutsideGate`; T020, T065, T069, T071. | PENDING — keep original |
| `test_paper_screen_shows_live_prints_when_they_arrive` | 1 | Live marks update displayed valuation. | `hedge_fund/web/test_valuation.py::test_explicit_refresh_reports_quote_freshness`; `frontend/src/components/valuation-panel.test.tsx::refreshIsExplicitAndShowsCoverage`; T109, T114, T115, T120. | PENDING — keep original |
| `test_paper_screen_runs_through_the_approval_step` | 15 | Run review, approval, execution and report are separate visible steps. | `hedge_fund/web/test_jobs.py::test_manual_preview_admission_and_report_identity`; `frontend/src/pages/paper.test.tsx::manualRunReviewPrecedesExecution`; T028, T033–T035, T038. | PENDING — keep original |
| `test_session_report_separates_the_executed_cycle_from_the_new_decision` | 11 | Report separates previous executed cycle from new decision. | `hedge_fund/reporting/test_reports.py::test_session_report_separates_executed_cycle_and_new_decision`; `hedge_fund/web/test_reports.py::test_session_detail_preserves_decision_and_cycle`; T111, T119, T122. | PENDING — keep original |
| `test_paper_screen_works_the_kill_switch_and_sessions_reads_the_ledger` | 31 | Halt controls, ledger sessions and corrupt-control visibility remain distinct. | `hedge_fund/runtime/test_reconciliation.py::test_corrupt_controls_allow_only_emergency_halt`; `hedge_fund/web/test_actions.py::test_halt_and_resume_require_verified_replay`; T064, T067–T069, T072. | PENDING — keep original |
| `test_paper_screen_enter_on_a_minute_fund_opens_the_same_approval_step` | 6 | Minute cadence Enter path still requires the same reviewed approval step. | `hedge_fund/paper/test_tick.py::test_minute_manual_preview_binds_exact_bar`; `frontend/src/pages/paper.test.tsx::minuteManualRunUsesReviewedFlow`; T026, T028, T033, T038. | PENDING — keep original |
| `test_paper_screen_space_starts_and_stops_a_runner_at_any_cadence` | 7 | Runner start/stop is available at supported cadences. | `hedge_fund/runtime/test_ownership.py::test_runner_state_requires_verified_owner`; `frontend/src/pages/paper.test.tsx::runnerLifecycleRequiresExplicitOwnedStartAndStop`; T025, T028–T032, T038. | PENDING — keep original |
| `test_sessions_screen_groups_a_minute_funds_bars_by_day` | 8 | Intraday session history groups bars by day. | `hedge_fund/web/test_services.py::test_minute_history_groups_sessions_by_day`; `frontend/src/pages/paper.test.tsx::minuteHistoryGroupsByDay`; T026, T039, T111, T122. | PENDING — keep original |

## `hedge_fund/tui/test_paper_view.py`

| Existing test | Direct asserts | Assertion semantics | Planned neutral/web replacement | Status |
| --- | ---: | --- | --- | --- |
| `test_run_plan_says_exactly_what_the_run_will_do` | 15 | Preview names exact decision, execution date, and consequences. | `hedge_fund/runtime/test_preflight.py::test_preview_binds_exact_decision_and_consequences`; `hedge_fund/web/test_jobs.py::test_manual_preview_is_identity_bound`; T011, T033. | PENDING — keep original |
| `test_run_plan_on_a_bar_names_the_print_and_how_late_it_is_taken` | 7 | Minute preview identifies print timestamp and lateness. | `hedge_fund/runtime/test_preflight.py::test_minute_preview_binds_print_and_lateness`; `hedge_fund/paper/test_tick.py::test_minute_execution_preserves_late_print_semantics`; T026, T033. | PENDING — keep original |
| `test_approval_snapshot_rows_and_run_plan_show_gate_state` | 11 | Snapshot and plan expose exact approval-gate state. | `hedge_fund/web/test_services.py::test_snapshot_exposes_approval_identity_and_gate`; `frontend/src/pages/paper.test.tsx::approvalSnapshotMatchesReviewedPlan`; T028, T039, T065, T069. | PENDING — keep original |
| `test_next_run_names_the_expired_decision_until_a_new_decision_exists` | 4 | Expired decision remains visible until replaced by a new record. | `hedge_fund/paper/test_tick.py::test_lapsed_decision_remains_visible_until_new_record`; `hedge_fund/runtime/test_defaults.py::test_schedule_projection_keeps_lapsed_decision`; T008, T026, T033. | PENDING — keep original |
| `test_live_rows_value_the_book_at_the_latest_prints` | 8 | Current-value rows use latest prints and display runner status. | `hedge_fund/web/test_valuation.py::test_estimate_uses_explicit_quote_capture`; `frontend/src/components/valuation-panel.test.tsx::partialAndFreshMarksStayEstimated`; T109, T114, T115, T120. | PENDING — keep original |
| `test_minute_fund_rows_are_pure` | 19 | Minute read projection is deterministic and provider-free. | `hedge_fund/runtime/test_defaults.py::test_minute_read_projection_is_pure`; `hedge_fund/web/test_observer.py::test_get_does_not_construct_provider_or_write`; T008, T078. | PENDING — keep original |

## `hedge_fund/tui/test_report.py`

| Existing test | Direct asserts | Assertion semantics | Planned neutral/web replacement | Status |
| --- | ---: | --- | --- | --- |
| `test_jev_results_show_stored_direction_and_separate_confidence` | 16 | Stored direction and confidence render separately. | `hedge_fund/llm/test_client.py::test_native_signal_metadata_round_trips_in_headless_report`; `hedge_fund/reporting/test_reports.py::test_signal_report_separates_direction_and_confidence`; T111, T119. | PENDING — keep original |
| `test_abstention_overrides_stored_direction` | 2 | Abstention state overrides direction text. | `hedge_fund/llm/test_contract.py::test_abstention_overrides_stored_direction`; `hedge_fund/reporting/test_reports.py::test_abstention_report_is_not_directional`; T111, T119. | PENDING — keep original |
| `test_chat_rendering_and_quantitative_fallback_are_preserved` | 6 | Chat result and quantitative fallback remain distinguishable. | `hedge_fund/reporting/test_reports.py::test_chat_and_quant_fallback_are_rendered_without_tui`; T111, T119. | PENDING — keep original |
| `test_portfolio_report_explains_rounding_scaling_and_flat_strategies` | 8 | Portfolio report explains rounding, scaling and flat composition. | `hedge_fund/reporting/test_reports.py::test_portfolio_report_explains_rounding_scaling_and_flat_strategies`; T008, T111, T119. | PENDING — keep original |
| `test_portfolio_report_formats_fractional_shares` | 1 | Fractional share values retain precision. | `hedge_fund/reporting/test_reports.py::test_portfolio_report_preserves_fractional_shares`; T008, T111, T119. | PENDING — keep original |
| `test_orders_report_shows_the_fill_beside_the_mark_and_what_it_cost` | 4 | Orders report shows mark, fill, and costs together. | `hedge_fund/reporting/test_reports.py::test_order_report_shows_mark_fill_and_cost`; `hedge_fund/web/test_reports.py::test_order_download_preserves_cost_fields`; T111, T119, T122. | PENDING — keep original |
| `test_cost_line_reads_as_bps_of_what_was_traded` | 2 | Cost line uses traded notional as basis-point denominator. | `hedge_fund/reporting/test_console.py::test_cost_line_uses_traded_notional_bps`; T008, T013, T111. | EXPECTED-RED TEST ADDED — helper module absent; original retained |

## `hedge_fund/tui/test_scorecard_view.py`

| Existing test | Direct asserts | Assertion semantics | Planned neutral/web replacement | Status |
| --- | ---: | --- | --- | --- |
| `test_analyst_table_shows_rates_with_their_counts` | 4 | Analyst rates retain sample counts and period labels. | `hedge_fund/reporting/test_console.py::test_analyst_scorecard_preserves_counts_rates_and_row_order`; `hedge_fund/web/test_reports.py::test_analyst_scorecard_download_preserves_counts`; T008, T111, T119. | EXPECTED-RED TEST ADDED — helper module absent; original retained |
| `test_strategy_table_reports_the_unattributed_gap` | 2 | Strategy scorecard reports unexplained/unattributed gap. | `hedge_fund/reporting/test_console.py::test_strategy_scorecard_reports_signed_precision_and_unattributed_gap`; T008, T111, T119. | EXPECTED-RED TEST ADDED — helper module absent; original retained |
| `test_empty_scorecard_says_why` | 3 | Empty scorecard explains absence of gradeable data. | `hedge_fund/reporting/test_console.py::test_empty_scorecard_explains_missing_gradeable_data`; T008, T013, T111. | EXPECTED-RED TEST ADDED — helper module absent; original retained |

## External tests importing TUI

These are not in `hedge_fund/tui`; they still block helper or Textual retirement while
the import edge remains. The Saxo adapter tests use fake transport only; no real brokerage
is permitted.

### `hedge_fund/test_run.py`

`test_run.py` imports `hedge_fund.run`; `run.py` imports TUI helpers at module load. Retain
headless assertions after neutral extraction. Replace the TUI default-launch expectation.

| Existing test | Direct asserts | Assertion semantics | Planned neutral/web replacement | Status |
| --- | ---: | --- | --- | --- |
| `test_cli_rejects_invalid_configuration_before_clients` | 6 | Invalid mandate fails before fund/provider/deployment effects and leaves source bytes unchanged. | Retain `hedge_fund/test_run.py::test_cli_rejects_invalid_configuration_before_clients`; add import-closure check; T013, T040, T077. | PENDING — keep original |
| `test_no_arguments_launches_the_app` | 0 | Existing no-argument TUI launch expectation. | Replace with `hedge_fund/test_run.py::test_no_arguments_launches_web_desk_without_textual`; T077, T080, T093. | PENDING — keep original until replacement |
| `test_backtest_prints_json_and_files_a_research_copy` | 9 | Headless backtest prints canonical JSON, persists research copy, and does not touch paper root. | Retain same test after neutral import closure; `hedge_fund/test_run.py::test_backtest_prints_json_and_files_a_research_copy`; T013, T077. | PENDING — keep original |
| `test_backtest_defaults_end_to_the_latest_completed_session` | 1 | Backtest default end is latest completed session. | Retain same test after neutral import closure; T008, T013, T077. | PENDING — keep original |
| `test_backtest_without_rebalance_key_defaults_to_weekly` | 3 | Missing cadence defaults weekly and serialization hash stays fixed. | Retain same test with fixed code stamp; `hedge_fund/runtime/test_defaults.py::test_backtest_defaults_match_headless_contract`; T008, T013. | PENDING — keep original |
| `test_backtest_rebalance_override_changes_monthly_cycle_count` | 4 | Explicit cadence override changes cycle count without changing mandate bytes. | Retain same test after neutral import closure; T013, T077. | PENDING — keep original |
| `test_paper_create_rebalance_override_is_frozen_and_reported` | 4 | Paper deployment freezes override and reports it. | Retain same test after shared admission/capture; T016, T021, T036, T077. | PENDING — keep original |
| `test_invalid_rebalance_override_is_usage_error_before_engine_work` | 5 | Invalid override exits before constructing engine dependencies. | Retain same test after neutral import closure; T013, T036, T077. | PENDING — keep original |
| `test_paper_create_overrides_minute_to_daily_without_minute_fields` | 5 | Day cadence removes minute-only fields before validation. | Retain same test; `hedge_fund/fund/test_spec.py::test_day_grid_removes_minute_fields`; T046, T056, T077. | PENDING — keep original |
| `test_paper_create_overrides_day_grid_to_minute_with_standard_defaults` | 6 | Minute cadence restores valid standard interval/window defaults. | Retain same test; `hedge_fund/fund/test_spec.py::test_minute_grid_restores_valid_defaults`; T046, T056, T077. | PENDING — keep original |
| `test_deployed_fund_commands_do_not_accept_rebalance_override` | 2 | Deployed snapshot cannot be mutated by CLI override. | Retain same test after neutral import closure; T036, T077. | PENDING — keep original |
| `test_paper_flow_create_tick_status_halt_resume` | 16 | Headless create/tick/status/Halt/Resume use canonical ledger and explicit states. | Retain same test after shared admission and reconciliation; T021, T036, T067–T070, T077. | PENDING — keep original |
| `test_paper_minute_fund_ticks_and_runs_like_a_daily_one` | 12 | Minute tick/run uses canonical bar schedule and display labels. | Retain same test; `hedge_fund/paper/test_tick.py::test_minute_schedule_and_cutoff_matrix`; T026, T036, T077. | PENDING — keep original |
| `test_paper_create_approval_and_approve_commands_show_status` | 7 | Create and approval commands expose gate/verdict status. | Retain same test with durable decision identity; T063, T069, T070, T077. | PENDING — keep original |
| `test_paper_approve_now_executes_when_a_session_is_due` | 4 | Explicit headless approve-now executes only when due. | Retain same test with reviewed expected head/due-set; T033, T036, T070, T077. | PENDING — keep original |
| `test_paper_approve_now_without_a_due_session_schedules_next_close` | 3 | No due session schedules next close rather than immediate execution. | Retain same test; `hedge_fund/paper/test_tick.py::test_nothing_due_records_no_execution`; T026, T033, T036. | PENDING — keep original |
| `test_paper_reject_records_verdict_and_event` | 3 | Reject records canonical verdict and event. | Retain same test with timestamp/source-hash identity; T063, T069, T070, T077. | PENDING — keep original |
| `test_paper_approval_commands_refuse_when_gate_is_off` | 2 | Approval commands deny when mandate gate is off. | Retain same test after neutral import closure; T063, T070, T077. | PENDING — keep original |
| `test_paper_approval_commands_refuse_when_nothing_is_pending` | 2 | Approval commands deny without pending decision. | Retain same test after neutral import closure; T063, T070, T077. | PENDING — keep original |
| `test_paper_approval_commands_refuse_halted_funds_without_touching_control` | 4 | Halted fund refuses verdict and leaves control bytes unchanged. | Retain same test with reconciliation-bound Resume; T064, T067–T070, T077. | PENDING — keep original |

### `hedge_fund/llm/test_client.py`

| Existing test | Direct asserts | Assertion semantics | Planned neutral replacement | Status |
| --- | ---: | --- | --- | --- |
| `test_cli_jev_cycle_and_saved_replay` | 17 | CLI backtest preserves provider cycle, serialized result, prompt-cache replay, and no second provider call; test imports `hedge_fund.tui.keys` only for credential-path setup. | Keep test in `hedge_fund/llm/test_client.py`; replace TUI key helper with `hedge_fund/runtime/test_credentials.py::test_root_scoped_credential_path_and_cli_replay`; T013. | PENDING — keep original |

### `hedge_fund/paper/test_saxo_e2e.py`

| Existing test | Direct asserts | Assertion semantics | Planned neutral replacement | Status |
| --- | ---: | --- | --- | --- |
| `test_cutoff_records_completed_fills_and_re_evaluates_unsubmitted_orders_next_bar` | 18 | Submitted fake fills persist; cutoff orders are reconsidered next bar. | `hedge_fund/paper/test_tick.py::test_fake_sim_cutoff_journals_fills_and_reevaluates_next_bar`; T026, T070. | PENDING — keep original |
| `test_cutoff_re_evaluation_requires_a_new_approval` | 8 | Re-evaluated work requires a fresh approval. | `hedge_fund/paper/test_tick.py::test_fake_sim_cutoff_reevaluation_requires_new_vote`; T063, T070. | PENDING — keep original |
| `test_confirmed_external_fill_is_journaled_if_later_order_fails` | 5 | Confirmed fake fill is journaled before later order failure. | `hedge_fund/runtime/test_reconciliation.py::test_confirmed_fill_is_journaled_before_later_order_failure`; T064, T068. | PENDING — keep original |
| `test_confirmed_fills_are_journaled_if_later_assessment_fails` | 3 | Confirmed fills remain journaled when later assessment fails. | `hedge_fund/runtime/test_reconciliation.py::test_confirmed_fills_remain_journaled_when_assessment_fails`; T064, T068. | PENDING — keep original |
| `test_fill_journal_failure_still_halts_after_an_external_fill` | 3 | Append failure after external fill remains halted and ambiguous. | `hedge_fund/runtime/test_reconciliation.py::test_append_failure_after_fill_remains_ambiguous`; T064, T068, T072. | PENDING — keep original |
| `test_real_saxo_client_deferral_reaches_the_session_ledger` | 7 | Fake Saxo deferred submission is recorded without assuming execution. | `hedge_fund/paper/test_tick.py::test_fake_saxo_deferral_reaches_session_ledger`; T026, T070. | PENDING — keep original |
| `test_saxo_external_adapter_records_order_fill_in_ledger` | 20 | Fake adapter fill and reconciliation use canonical ledger. | `hedge_fund/brokers/test_saxo_e2e.py::test_fake_saxo_fill_uses_canonical_ledger`; T070, T072. | PENDING — keep original |

### Web test import closure

The web tests import `hedge_fund.web.app` or `hedge_fund.web.services`; `web/services.py`
currently imports `hedge_fund.tui.keys`. Their web assertions remain in place. T013 must
remove that import edge, and the same tests must pass without importing any `hedge_fund.tui`
module. Current affected modules: `hedge_fund/test_acceptance_isolation.py`,
`hedge_fund/web/test_app.py`, `test_actions.py`, `test_jobs.py`, `test_services.py`,
`test_settings.py`, `test_launcher.py`, and `test_main.py`.

## Required semantic coverage before retirement

| Behavior | Planned replacement assertion | Status |
| --- | --- | --- |
| Schedule defaults, cadence identity, minute labels, one-second floor, window, and SIM cutoff. | `hedge_fund/runtime/test_defaults.py::test_minute_schedule_labels_keep_interval_and_timezone_output`; `hedge_fund/paper/test_tick.py::test_cadence_and_cutoff_matrix`; T008, T026, T013. | EXPECTED-RED LABEL TEST ADDED; cadence/cutoff pending |
| Progress, warming, stage order, cancellation boundary, and final report status. | `hedge_fund/runtime/test_defaults.py::test_warm_progress_defaults_keep_order_and_bound_chunks`; `hedge_fund/web/test_jobs.py::test_cancel_boundary_is_durable`; T008, T034, T110, T116, T117. | EXPECTED-RED WARMING TEST ADDED; stage/cancel pending |
| Backtest default values and serialization omissions. | `hedge_fund/runtime/test_defaults.py::test_backtest_defaults_preserve_window_and_capital_values`; `hedge_fund/backtesting/test_fund.py::test_backtest_defaults_are_stable`; T008, T013, T110. | EXPECTED-RED DEFAULT TEST ADDED; serialization omission pending |
| Cost line, report/scorecard ordering, signed/fractional precision, and inert text. | `hedge_fund/reporting/test_console.py::test_cost_line_uses_traded_notional_bps`; `test_analyst_scorecard_preserves_counts_rates_and_row_order`; `test_strategy_scorecard_reports_signed_precision_and_unattributed_gap`; `test_signed_fractional_share_format_keeps_precision`; `hedge_fund/reporting/test_reports.py::test_untrusted_text_stays_inert`; T008, T111, T119. | EXPECTED-RED CONSOLE TESTS ADDED; browser/inert report tests pending |
| CLI stdout and output-file workflows without Textual or Node. | `hedge_fund/test_run.py::test_headless_report_stdout_and_output_file_without_textual`; `hedge_fund/web/test_distribution.py::test_clean_install_runs_without_node`; T077, T080, T093. | PENDING |

## Retirement rule

Do not delete or weaken any inventoried test until its named replacement exists, passes
against the candidate artifact, and is linked to a closed acceptance row. Headless
compatibility is not a browser parity claim; G4 SIM denials and the F13 daily-grid
limitation remain explicit.
