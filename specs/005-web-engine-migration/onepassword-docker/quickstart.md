# Validation runbook: proposed 1Password Docker connection

**Validation guide.** Provider mappings remain empty. One bounded host identity check was
authorized and attempted; no vault/item read, real credential delivery, provider call or
existing-fund change is authorized by this guide.

## Prerequisites for later synthetic validation

1. Implementation authorization and runtime-only source compatibility recorded.
2. Supported Python/Poetry tools and final built image identity recorded by the execution owner.
3. Separate synthetic Docker project, unused loopback port and ext4 named volume; isolated
   HOME/root and fake provider/resolver adapters. No protected/home project root mounts.
4. Actual Windows Docker Desktop Linux-container runtime evidence, including engine/context,
   OS versions, container/root identities and image digest. CLI presence alone is insufficient.
5. Operator and observer roles kept separate; no automatic runner start or host fund restart.

## Safe checks available now

From this worktree, the planning pointer selects the nested extension:

```powershell
& .\.specify\scripts\powershell\check-prerequisites.ps1 -Json -RequireSpec -RequireTasks -IncludeTasks
git --no-pager diff --check
git --no-pager status --short
```

These are documentation checks, not secret-integration acceptance.

## Synthetic scenarios after implementation

| Step | Action | Required observation |
| --- | --- | --- |
| 1 | Run keyless fake operation with integration disabled and fake CLI missing/locked | Zero resolver/paid-provider calls; normal free/local behavior |
| 2 | Generate a unique harmless sentinel in the isolated test controller; deliver through fake resolver to one allowed backend | Selected fake consumer confirms equality internally; result records only boolean/count, never the value |
| 3 | Inspect exported image history and every layer, rendered Compose, container/image/exec config, process argv/environment, logs, browser traffic/storage and durable files | Zero sentinel occurrences; log only surface name/count; decode/reassemble archive/config formats rather than grep compressed bytes |
| 4 | Attempt observer, wrong-root, stale-boot, unauthorized provider/endpoint and unenrolled target delivery | Denial before resolution/effects; no authority gained |
| 5 | Run free/local runner and unrelated child with decoy keys/tokens in parent | Neither credential nor vault authority inherited; dotenv decoys ignored |
| 6 | Exercise missing CLI, denial, timeout, empty/large/control-character output, malformed/partial/replayed frames and stream loss | Sanitized errors, <=60-second bound, no fallback; ambiguous publication explicitly reported |
| 7 | Capture A, refresh B, revoke, attempt new and previously admitted dispatch | Immutable generation capture; revocation blocks new/next dispatch; no silent automatic restart |
| 8 | Restart/recreate only synthetic backend | Requires-auth; no value in ext4 data, writable layer or recovered snapshots; stale captures denied |
| 9 | Re-run observer, root authority and W07 endpoint/network denial regressions | Existing boundaries unchanged; credential delivery never validates/calls a provider |

Attach outcomes to [acceptance-evidence.md](acceptance-evidence.md). Runtime suites use
fake `op` and fake providers; never real LLM/data/Saxo calls. Existing tests from the
reconciled Spec005 implementation should be selected with the new co-located tests in a
single pytest run, then escalated according to repository acceptance obligations.

## Bounded host authentication observation

Installed CLI: **2.34.1**; no install or upgrade was performed. The user-authorized
`op whoami` check ran once at **2026-11-09 11:27:18 +01:00**, returned **unauthenticated**
in **0.093 seconds**, and produced sanitized reason `desktop-integration-unavailable`.
Connect/service-account auth variables were absent. No prompt activity was recorded; whether
a prompt could appear is unverified. No raw identity metadata or stderr is retained; no
vault/item value was read.

After the user reported the desktop CLI integration was on, one more bounded check ran at
**2026-11-09 12:19:34 +01:00**. It returned **unauthenticated** in **1.070 seconds** with
sanitized reason `desktop-account-not-signed-in`. The executable resolved in user-local
AppData with valid Authenticode status; file-version metadata was unavailable (earlier
version: 2.34.1). The `op` process was hidden with stdout/stderr redirected, although its
parent shell was interactive; 9 1Password processes were in the same Windows session.
Connect, service-account and session-token variables were absent. Prompt activity is
unverified. The sanitized reason does not independently prove the desktop app is signed out.

Path of Practice documents `op whoami` from an attached interactive terminal with biometric
unlock (`docs/secrets.md:33-38`); its backend launcher runs `op` from PowerShell without
hidden/redirected streams (`scripts/dev-backend.ps1:62-85`). This invocation difference
could explain absent prompt activity, but is not a confirmed cause. Smallest discriminating
local action: run `op whoami` directly in an attached PowerShell/Windows Terminal. This
runbook does not invoke `op read`, configure a Connect/service-account token or promise a
desktop prompt. Do not paste account/vault details or secrets into chat. Unattended auth remains out of scope.

## Local mapping metadata and command

The public host command is `aihf-op-deliver --provider <provider-id> [--config <path>]`.
Default config path: `%USERPROFILE%\.hedge-fund\op-runtime-mappings.json`. Missing file is
equivalent to an empty mapping set. Schema version 1 uses `{"schema":1,"mappings":[]}` as
the disabled form. A mapping row has only `provider_id`, `reference`, `destination`,
`root_id`, `container_id`, `image_id`, `revision`, `source_sha256` and `volume_name`.
`reference` is an `op://` field reference, not its value. Unknown/duplicate fields and
duplicate provider mappings are rejected. The loader caps config at 1 MiB and never echoes
its content.

The operator backend allowlist is configured separately as comma-separated application
provider IDs in `HEDGE_FUND_RUNTIME_PROVIDERS`; unset/empty means no allowed provider. This
value carries IDs only, not references or credentials. Host mapping provider, backend
allowlist, and target destination must match. A real command invocation with a valid mapping
would call `op read`; that was not run or authorized for this implementation session. Tests
use fake resolver and fake Docker receiver only.

The CLI/config path is functional under fakes, but live delivery remains unavailable with
the current Compose bind-mounted root: the launcher denies it before resolution. No
synthetic Docker artifact/runtime acceptance has been performed. Do not configure real
mappings, authenticate Saxo, import existing `.env`, restart the current TUI or connect this
flow to an existing fund.

## Final fake test selection

Python 3.11.15 / pytest 7.4.4 on Windows; selected modules ran sequentially in one pytest
process. Final command:

```powershell
& 'C:\Users\ChristianGjedrem\AppData\Local\pypoetry\Cache\virtualenvs\aihf-4l3vIF0x-py3.11\Scripts\python.exe' -m pytest hedge_fund/secrets/test_docker_delivery.py hedge_fund/runtime/test_external_credentials.py hedge_fund/runtime/test_capture.py hedge_fund/runtime/test_credentials.py hedge_fund/web/test_settings.py hedge_fund/runtime/test_dispatch.py hedge_fund/web/test_app.py hedge_fund/web/test_services.py -q --tb=short
```

Result at 11:18: **252 passed, 1 skipped in 218.10 s**; command wall time **220.493 s**.
The final integrated run at **2026-11-09T11:27:31.7859045Z** passed **255 tests, 1 skipped
in 178.94 s**; process wall time **181.461 s**. It includes the later provider-allowlist
target denial and durable no-fallback tests. The Unix socket ownership test is skipped on
Windows. Tested source was committed unchanged as `15fc2d9c62c73e5eb40aec3c0a3a46022a82287c`;
SHA-256 of its 133,271-byte binary commit diff is
`b9c005969127a269aeb70470cdcab4946f915cf166396817c2863450ec9d58b3`. No live
provider/model/broker call occurred.

After config parser nesting hardening, final config/allowlist/status selection:

```powershell
& 'C:\Users\ChristianGjedrem\AppData\Local\pypoetry\Cache\virtualenvs\aihf-4l3vIF0x-py3.11\Scripts\python.exe' -m pytest hedge_fund/secrets/test_docker_delivery.py hedge_fund/runtime/test_external_credentials.py hedge_fund/web/test_settings.py -q --tb=short
```

Result: **83 passed, 1 skipped in 6.81 s**; command wall time **9.187 s**;
2026-11-09 11:20:19Z. Later import-order/format-only edits passed a 6-node final config
and service-wiring selection (**6 passed in 0.98 s**, wall time **3.106 s** at 11:21:29Z).

### New test node IDs

The following are exact newly added test nodes. Parameter variants are listed separately.

```text
hedge_fund/secrets/test_docker_delivery.py::test_delivery_frame_round_trip_contains_value_only_in_private_payload
hedge_fund/secrets/test_docker_delivery.py::test_delivery_frame_rejects_empty_partial_and_oversized_input[empty]
hedge_fund/secrets/test_docker_delivery.py::test_delivery_frame_rejects_empty_partial_and_oversized_input[partial-header]
hedge_fund/secrets/test_docker_delivery.py::test_delivery_frame_rejects_empty_partial_and_oversized_input[partial-body]
hedge_fund/secrets/test_docker_delivery.py::test_delivery_frame_rejects_empty_partial_and_oversized_input[oversized-frame]
hedge_fund/secrets/test_docker_delivery.py::test_delivery_frame_rejects_trailing_records_and_unknown_fields
hedge_fund/secrets/test_docker_delivery.py::test_delivery_frame_rejects_invalid_secret_values[empty]
hedge_fund/secrets/test_docker_delivery.py::test_delivery_frame_rejects_invalid_secret_values[whitespace]
hedge_fund/secrets/test_docker_delivery.py::test_delivery_frame_rejects_invalid_secret_values[newline]
hedge_fund/secrets/test_docker_delivery.py::test_delivery_frame_rejects_invalid_secret_values[carriage-return]
hedge_fund/secrets/test_docker_delivery.py::test_delivery_frame_rejects_invalid_secret_values[nul]
hedge_fund/secrets/test_docker_delivery.py::test_delivery_frame_rejects_invalid_secret_values[oversized-value]
hedge_fund/secrets/test_docker_delivery.py::test_backend_preflight_denies_empty_allowlist_without_secret_resolution
hedge_fund/secrets/test_docker_delivery.py::test_backend_publishes_fake_value_only_to_allowed_runtime_lease
hedge_fund/secrets/test_docker_delivery.py::test_backend_authority_denial_precedes_status_or_publication
hedge_fund/secrets/test_docker_delivery.py::test_host_delivery_refuses_empty_source_mapping_before_docker_or_resolver
hedge_fund/secrets/test_docker_delivery.py::test_source_mapping_requires_one_explicit_secret_field[whole-item]
hedge_fund/secrets/test_docker_delivery.py::test_source_mapping_requires_one_explicit_secret_field[query]
hedge_fund/secrets/test_docker_delivery.py::test_source_mapping_requires_one_explicit_secret_field[authority]
hedge_fund/secrets/test_docker_delivery.py::test_source_mapping_requires_one_explicit_secret_field[wrong-scheme]
hedge_fund/secrets/test_docker_delivery.py::test_host_target_denial_precedes_resolver[remote-daemon]
hedge_fund/secrets/test_docker_delivery.py::test_host_target_denial_precedes_resolver[host-bind-root]
hedge_fund/secrets/test_docker_delivery.py::test_host_mapping_binds_exact_root_and_container_before_resolution
hedge_fund/secrets/test_docker_delivery.py::test_host_delivery_uses_private_stdin_and_only_selected_fake_consumer_receives_value
hedge_fund/secrets/test_docker_delivery.py::test_host_child_processes_do_not_inherit_secret_environment_variables
hedge_fund/secrets/test_docker_delivery.py::test_target_rejects_op_session_environment_before_resolver
hedge_fund/secrets/test_docker_delivery.py::test_target_rejects_invalid_provider_allowlist_before_resolver
hedge_fund/secrets/test_docker_delivery.py::test_target_rejects_invalid_provider_allowlist_before_resolver
hedge_fund/secrets/test_docker_delivery.py::test_default_resolver_bounds_stdout_and_filters_child_environment
hedge_fund/secrets/test_docker_delivery.py::test_invalid_resolver_output_never_reaches_docker_publication[empty]
hedge_fund/secrets/test_docker_delivery.py::test_invalid_resolver_output_never_reaches_docker_publication[blank]
hedge_fund/secrets/test_docker_delivery.py::test_invalid_resolver_output_never_reaches_docker_publication[newline]
hedge_fund/secrets/test_docker_delivery.py::test_invalid_resolver_output_never_reaches_docker_publication[nul]
hedge_fund/secrets/test_docker_delivery.py::test_invalid_resolver_output_never_reaches_docker_publication[oversized]
hedge_fund/secrets/test_docker_delivery.py::test_resolver_failures_are_sanitized_and_never_fall_back
hedge_fund/secrets/test_docker_delivery.py::test_host_rejects_conflicting_auth_and_never_resolves_or_retries_lost_ack
hedge_fund/secrets/test_docker_delivery.py::test_docker_cli_overrides_fail_closed_before_any_inspection
hedge_fund/secrets/test_docker_delivery.py::test_missing_host_mapping_config_is_empty_and_never_resolves
hedge_fund/secrets/test_docker_delivery.py::test_host_mapping_config_drives_fake_cli_delivery_without_echoing_reference_or_value
hedge_fund/secrets/test_docker_delivery.py::test_host_mapping_config_rejects_ambiguous_or_secret_fields[unknown-secret-field]
hedge_fund/secrets/test_docker_delivery.py::test_host_mapping_config_rejects_ambiguous_or_secret_fields[bool-schema]
hedge_fund/secrets/test_docker_delivery.py::test_host_mapping_config_rejects_ambiguous_or_secret_fields[duplicate-provider]
hedge_fund/secrets/test_docker_delivery.py::test_host_mapping_config_is_bounded_and_never_echoes_contents
hedge_fund/secrets/test_docker_delivery.py::test_host_mapping_config_rejects_duplicate_json_fields
hedge_fund/secrets/test_docker_delivery.py::test_host_mapping_config_sanitizes_excessive_json_nesting
hedge_fund/runtime/test_external_credentials.py::test_external_runtime_allowlist_defaults_empty_and_denies_before_publication
hedge_fund/runtime/test_external_credentials.py::test_external_runtime_rejects_invalid_values_without_generation[empty]
hedge_fund/runtime/test_external_credentials.py::test_external_runtime_rejects_invalid_values_without_generation[whitespace]
hedge_fund/runtime/test_external_credentials.py::test_external_runtime_rejects_invalid_values_without_generation[newline]
hedge_fund/runtime/test_external_credentials.py::test_external_runtime_rejects_invalid_values_without_generation[carriage-return]
hedge_fund/runtime/test_external_credentials.py::test_external_runtime_rejects_invalid_values_without_generation[nul]
hedge_fund/runtime/test_external_credentials.py::test_external_runtime_rejects_invalid_values_without_generation[too-many-bytes]
hedge_fund/runtime/test_external_credentials.py::test_external_runtime_rejects_invalid_values_without_generation[multibyte-too-large]
hedge_fund/runtime/test_external_credentials.py::test_rotation_keeps_frozen_generation_and_never_exposes_values_in_status
hedge_fund/runtime/test_external_credentials.py::test_failed_refresh_cas_and_replayed_delivery_leave_active_generation_unchanged
hedge_fund/runtime/test_external_credentials.py::test_revoke_fences_existing_and_new_dispatches_and_drops_active_lease
hedge_fund/runtime/test_external_credentials.py::test_closed_runtime_store_drops_generations_and_rejects_reuse
hedge_fund/runtime/test_external_credentials.py::test_delivery_server_does_not_unlink_an_unowned_socket
hedge_fund/runtime/test_external_credentials.py::test_restart_instance_rejects_stale_runtime_handle
hedge_fund/runtime/test_external_credentials.py::test_release_discards_rotated_generation_after_last_capture
hedge_fund/runtime/test_external_credentials.py::test_operator_provider_allowlist_defaults_empty[unset]
hedge_fund/runtime/test_external_credentials.py::test_operator_provider_allowlist_defaults_empty[empty]
hedge_fund/runtime/test_external_credentials.py::test_operator_provider_allowlist_is_explicit_and_normalized
hedge_fund/runtime/test_external_credentials.py::test_operator_provider_allowlist_rejects_ambiguous_values[leading-space]
hedge_fund/runtime/test_external_credentials.py::test_operator_provider_allowlist_rejects_ambiguous_values[empty-entry]
hedge_fund/runtime/test_external_credentials.py::test_operator_provider_allowlist_rejects_ambiguous_values[duplicate]
hedge_fund/runtime/test_external_credentials.py::test_operator_provider_allowlist_rejects_ambiguous_values[broker-provider]
hedge_fund/runtime/test_external_credentials.py::test_operator_provider_allowlist_rejects_ambiguous_values[newline]
hedge_fund/runtime/test_external_credentials.py::test_operator_provider_allowlist_rejects_ambiguous_values[oversized]
hedge_fund/runtime/test_capture.py::test_external_runtime_handle_is_instance_bound_in_capture_and_snapshot
hedge_fund/runtime/test_capture.py::test_external_runtime_handle_requires_instance_and_destination
hedge_fund/web/test_settings.py::test_external_runtime_status_is_disabled_and_never_exposes_mapping
hedge_fund/web/test_settings.py::test_external_capture_consumes_only_its_live_process_lease
hedge_fund/web/test_settings.py::test_operator_allowlist_comes_from_provider_ids_and_stays_value_free
hedge_fund/web/test_settings.py::test_operator_delivery_role_keeps_provider_allowlist_empty_by_default
hedge_fund/web/test_settings.py::test_missing_durable_capture_does_not_fall_back_to_ambient_credentials
```

The selection also ran existing credential-store/capture/settings tests plus W07 dispatch
and web-origin tests; exact totals are in [acceptance-evidence.md](acceptance-evidence.md).
