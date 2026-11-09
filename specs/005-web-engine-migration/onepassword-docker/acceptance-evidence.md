# Acceptance evidence: 1Password Docker extension

**Current state**: Cycle-two parser/status repairs are committed. Windows focused tests and
Linux test-owned-root admission/IPC tests pass. Production-container trust, full-suite evidence,
final-artifact rescanning and independent QA remain incomplete. Provider mappings stay empty.
No vault/item/provider credential was read.

## Current identity and environment — 2026-11-09

- Source revision: `9d23a1c79ce40b3e53c4bd495ae8f1b23478e594`; parent:
  `7bb12216564477068f720598b0eedaf407b3188f`; tree:
  `2c7e3a97642448d97e84a6fead8936a752e441f0`.
- Source commit patch: 16,583 bytes; SHA-256
  `2365965edd5aaa4c94f6632d1f72c4f6ce39ab4cdec8e8268e35c7eaa8f1b544`.
- The prior sentinel-scanned application image was built from `7bb1221`, not this source
  revision. Cycle-two Linux tests mounted current source read-only; no production image
  rebuild or final-revision layer scan occurred.
- Cycle-two test image: `sha256:5bde5cd27f7e3f8507f81fa1f98214b223a83e4e7ac897f389777117cc4ba025`;
  local test image, based on `aihf-web` image `sha256:ededc795ef56179fc923a28043a3e00d424558b5f06bc20d0f2e43f0716c430e`,
  with pytest 7.4.4/httpx 0.27.2. Created `2026-11-09T13:15:52.688116025Z`;
  removed after testing.
- Platform: Windows 11 host; Docker Desktop context `desktop-linux`; Docker server
  29.9.2, Linux/amd64; Compose 5.6.1; overlayfs. Task-owned `/data` named volume reported
  `ext4` through `/proc/self/mountinfo`.
- Cycle-one test environment: Python 3.11.15, pytest 7.4.4. Its selected suite ran from
  `2026-11-09T13:01:27.7092464Z` to `13:02:02.1413475Z` (34.432 s wall time).
- Evidence scope: source commit and artifact mapping above. The working tree contained only
  documentation edits after the code commit; no source code changed after the test/build.
  Final documentation commit will be separate from the artifact source revision.

## Current acceptance rows

| Row | Requirements | Scenario and measurable acceptance | Mode | Status |
| --- | --- | --- | --- | --- |
| OP-A01 | OP-FR-001, OP-FR-014 | Keyless disabled/missing/locked states: 0 resolver/paid-provider calls; normal free/local work | Unit/fake | INCONCLUSIVE |
| OP-A02 | OP-FR-004 | Final image archive metadata/config/history and every decompressed layer: 0 synthetic sentinel occurrences | Artifact/runtime | INCONCLUSIVE |
| OP-A03 | OP-FR-004, OP-FR-010 | Rendered Compose, Docker config/argv/env, logs, browser traffic/storage and exports: 0 sentinel occurrences | Artifact/runtime/browser | INCONCLUSIVE |
| OP-A04 | OP-FR-005, OP-FR-012 | Only intended fake consumer holds value; observer, TUI path, runner, unrelated child and vault authority inheritance denied | Unit/fake + runtime fake | INCONCLUSIVE |
| OP-A05 | OP-FR-002, OP-FR-003, OP-FR-012 | Wrong root/target/role/provider/endpoint, lost authority: denial before resolution/effects | Unit/fake | INCONCLUSIVE |
| OP-A06 | OP-FR-008, OP-FR-011 | CAS conflict, wrong boot, replay, malformed/partial/oversized frame; ambiguous ack explicit | Unit/fake + Linux IPC | PASS |
| OP-A07 | OP-FR-006, OP-FR-010, OP-FR-011 | Missing/denied/timeout/malformed CLI; <=60s; no fallback; sanitized errors | Unit/fake | PASS |
| OP-A08 | OP-FR-007, OP-FR-013 | Synthetic backend restart: no durable sentinel; stale handles denied; fresh delivery required | Unit/fake + container restart | INCONCLUSIVE |
| OP-A09 | OP-FR-008, OP-FR-009 | Refresh, failed refresh, revoke/dispatch fence, fixed capture and no automatic restart | Unit/fake | PASS |
| OP-A10 | OP-FR-012, OP-FR-013 | Windows LinuxKit/ext4 production topology; production artifact authority/private IPC/W07 and negative states | Platform/runtime | BLOCKED |

OP-A10 remains BLOCKED: the actual application admission callback passed with the approved
test-owned synthetic root, but no production `/data` root trust/enrollment or production
operator artifact was activated. OP-A02 is INCONCLUSIVE for revision `9d23a1c`: prior image
scans bind to `7bb1221`. OP-A06/A07/A09 PASS claims apply only to their listed tests and
artifact scenarios. No evidence establishes production readiness, memory secrecy or
malicious-administrator resistance.

### Cycle-two tests — source revision `9d23a1c`

Windows selection ran on Python 3.11.15 / pytest 7.4.4:

```powershell
& 'C:\Users\ChristianGjedrem\AppData\Local\pypoetry\Cache\virtualenvs\aihf-4l3vIF0x-py3.11\Scripts\python.exe' -m pytest hedge_fund/runtime/test_external_credentials.py hedge_fund/secrets/test_docker_delivery.py hedge_fund/web/test_settings.py -q --tb=short
```

Result: **111 passed, 10 skipped in 16.04 s**, exit 0; wall time **19.289 s** from
`2026-11-09T13:19:33.6636027Z` to `13:19:52.9526396Z`. Skips include Unix socket tests and
the Linux-only receiver integration.

Linux IPC and service-admission tests ran in one disposable container:

```powershell
docker run --rm --name aihf-cycle2-admission-final-20261109 --network none --read-only `
  --tmpfs /tmp:rw,nosuid,nodev,size=256m `
  --mount "type=bind,source=<worktree>\hedge_fund,target=/workspace/hedge_fund,readonly" `
  --mount type=volume,source=aihf-cycle2-test-output-20261109,target=/workspace/outputs `
  --env PYTHONDONTWRITEBYTECODE=1 --workdir /workspace --entrypoint python `
  aihf-cycle2-linux-tests:20261109 -m pytest -p no:cacheprovider `
  hedge_fund/runtime/test_external_credentials.py::test_delivery_json_converts_integer_limit_value_error_to_protocol_error `
  hedge_fund/runtime/test_external_credentials.py::test_delivery_server_survives_deep_frame_and_handles_next_status `
  hedge_fund/runtime/test_external_credentials.py::test_delivery_server_survives_huge_integer_frame_and_handles_next_status `
  hedge_fund/runtime/test_external_credentials.py::test_closed_runtime_status_reports_closed_before_provider_allowlist `
  hedge_fund/secrets/test_docker_delivery.py::test_host_maps_huge_integer_reply_to_outcome_unknown `
  hedge_fund/web/test_settings.py::test_runtime_delivery_uses_service_admission_and_real_receiver_process `
  -q --tb=short
```

Result: **6 passed in 10.01 s**, exit 0; wall time **15.582 s** from
`2026-11-09T13:20:30.2134927Z` to `13:20:45.7956470Z`. Test image digest:
`sha256:5bde5cd27f7e3f8507f81fa1f98214b223a83e4e7ac897f389777117cc4ba025`.
The source bind was read-only; `outputs` was the task-created local volume
`aihf-cycle2-test-output-20261109` (created `2026-11-09T13:17:46Z`). `/proc/self/mountinfo`
reported `ext4`; container network was disabled and rootfs read-only.

The integration enrolled only a pytest-owned root beneath that marked outputs root with
`HEDGE_FUND_TEST_MODE=1`. `DeskService(allow_writes=True)` started its real admission-wired
receiver; a separately spawned, guarded `--receive` process published and read status
`available`, generation 1. Closing the synthetic root-owner lease caused the next publication
to return value-free `delivery-denied`; in-memory generation stayed 1. No `/data` production
trust, production enrollment, existing volume, provider call or secret value was used.

Cycle-two static checks ran from `2026-11-09T13:25:17.6673494Z` to
`13:25:21.1260429Z` (3.459 s): Black `--check --line-length 420` passed on the five changed
runtime/secrets Python files. `web/test_settings.py` retains two Black diff hunks; the
same expressions were present at base `a3a93531` in `git show ... | black --diff`. isort `--check-only
--profile black`, flake8 `--max-line-length=420` on all six changed Python files, and
`git show --check` plus `git diff --check` passed.

Red evidence before repairs: **3 failed, 1 skipped** in 1.09 s: two 5000-digit JSON values
escaped as plain `ValueError`, and closed-store status reported `provider-not-allowed`.
After repair, the Windows selection passed above. The first Linux attempt used tmpfs for
`outputs` and failed setup with `UnsupportedFilesystemError`; the test harness requires
NTFS/ext4. A broader Linux module run then reported **27 failed, 75 passed in 8.37 s**:
the host fake-docker suite assumes a Windows named-pipe context, and its direct subprocess
did not use the test isolation launcher. The final bounded Linux selection above uses the
guarded child launcher and ext4 volume. Those cross-platform fixture failures are not
classified as source regressions or as suite passes.
The first Docker test-image build syntax attempted stdin for both Dockerfile and context and
failed with `can't use stdin for both build context and dockerfile`; retry with a unique empty
context built the task-owned image successfully. The image and volume were removed after
evidence collection.

### Cycle-one selected tests (revision `7bb1221`, historical)

```powershell
& 'C:\Users\ChristianGjedrem\AppData\Local\pypoetry\Cache\virtualenvs\aihf-4l3vIF0x-py3.11\Scripts\python.exe' -m pytest hedge_fund/runtime/test_external_credentials.py hedge_fund/secrets/test_docker_delivery.py hedge_fund/secrets/test_op_runtime_compose.py hedge_fund/runtime/test_dispatch.py hedge_fund/web/test_app.py hedge_fund/web/test_settings.py::test_external_runtime_status_is_disabled_and_never_exposes_mapping hedge_fund/web/test_settings.py::test_runtime_revoke_maps_invalid_provider_closed_store_and_generation_cas hedge_fund/web/test_settings.py::test_external_capture_consumes_only_its_live_process_lease hedge_fund/web/test_settings.py::test_missing_durable_capture_does_not_fall_back_to_ambient_credentials hedge_fund/web/test_jobs.py::test_external_runtime_backtest_captures_fake_value_revoke_and_restart_denial hedge_fund/web/test_jobs.py::test_external_capture_released_when_worker_submit_fails hedge_fund/web/test_jobs.py::test_external_runtime_selection_fails_closed_with_empty_allowlist_and_durable_key
```

Result: **185 passed, 8 skipped in 31.56 s**; PowerShell wall time **34.432 s**;
exit 0; Windows 11 / Python 3.11.15 / pytest 7.4.4. Eight skips are Unix socket tests
on Windows. Equivalent deep-frame/server-survival and stale-socket-recovery cases ran in the
task-owned Linux container. No real provider/model/broker call.

### Cycle-one static checks (revision `7bb1221`, historical)

- Black `--check --line-length 420`: 11 changed Python files passed. `web/test_settings.py`
  was excluded because two formatting differences also exist in the pre-task base
  `a3a93531ff6f7f8beac4945a235694d5e80bf294` (base Black diff ranges 198-202 and 358-362).
  No unrelated formatting was applied.
- isort `--check-only --profile black`: all 12 changed Python files passed.
- flake8 `--max-line-length=420`: all 12 changed Python files passed.
- `git diff --check`: passed.
- Observation window: `2026-11-09T13:02:12.3963225Z`-`13:02:15.6365866Z`.

### Cycle-one artifact/runtime observations (image source `7bb1221`, historical)

Final build used revision `7bb12216564477068f720598b0eedaf407b3188f` and package digest
`9cb26c1e6d55e053148d65426c6f18336ee66b8e34c5ea68f9514679166b5abc`. A unique project
`aihf-op-cycle1-final-20261109` used only the task-created container and named volume
`aihf-op-cycle1-volume-final-20261109`; both were removed with the image tag after testing.
The deployment set `HEDGE_FUND_RUNTIME_PROVIDERS=openai` only for this synthetic fake
consumer. Host mappings remained absent. `COMPOSE_DISABLE_ENV_FILE=true`.

Observed container settings: `Privileged=false`, `ReadonlyRootfs=true`,
`NetworkMode=none`, `CapDrop=ALL`, `SecurityOpt=no-new-privileges:true`, `PidMode` empty,
`IpcMode=private`, no devices, and exactly one local named volume mounted at `/data`.
`/proc/self/mountinfo` reported `/data` as `ext4`. No host port was published.

A test-only fake in-memory store/receiver ran inside this newly created container under the
same UID boundary. The host `DockerCredentialDelivery` used a fake resolver, resolved one
synthetic value in memory, and delivered it through Docker exec stdin and the receiver's
owner-only Unix socket. The backend status/result was value-free. The same receiver recovered
an owned stale socket, denied a deeply nested malformed frame with `protocol-error`, then
served a valid `requires-auth` status. This fake receiver did not use the application's root
admission callback.

The final sentinel scan reported zero matches in rendered Compose, streamed Docker image
archive metadata/config, decompressed image layers, Docker history, container inspect config,
logs, exec argv/env, `/data`, `/tmp`, and container process argv/env. The image archive was
streamed; no sentinel value or secret-bearing scan output was retained. A container restart
was followed by a value-free receiver status: `denied:transport-unavailable`; resolver call
count did not increase. This is fail-closed restart evidence, not proof of the trusted app
lease server's restart state. Browser traffic/storage and export endpoints were not exercised.

Image creation was `2026-11-09T12:57:15Z`; post-restart container `StartedAt` was
`2026-11-09T13:00:03.000161994Z`. Runtime scans ran after image creation and before that
restart; exact scan command start/end and duration were not captured. Their source/artifact
identity is retained above; missing timing precision keeps browser/platform rows incomplete.

### Repair-cycle evidence

- Actual inspect returned `IpcMode=private`; admission initially rejected it as non-empty.
  The checker now accepts Docker's private IPC namespace and still rejects `host`.
  The 62-test host delivery module passed; final integrated tests also pass.
- The first final W07/web-origin run reported **87 passed, 1 failed** because a generic
  revoke denial used `409 runtime-credential-denied`, absent from the error-code contract.
  Changed generic denial to `403 capability-denied`, added a test, and reran the final
  combined suite successfully.
- The first Compose sentinel harness used a minimized Docker child environment and returned
  exit 125, `unknown shorthand flag: 'p' in -p`. A discriminating `docker compose config -q`
  check with the normal local Docker context returned 0; the final sentinel scan used the
  normal Compose environment and passed. No secret value was present in that failed output.

### Remaining evidence and stop conditions

- OP-A01/A03/A04/A05/A08 remain INCONCLUSIVE: full free/local runner, browser/export,
  observer/TUI/runner isolation, and application-owned lease-service restart were not
  exercised end-to-end. Synthetic service admission/publish/status is covered by cycle-two
  Linux tests.
- OP-A10 is BLOCKED until production `/data` root trust and final production artifact
  authority are explicitly authorized and tested. No production trust was activated.
- Full repository pytest was not run. Earlier adjacent **194 passed, 7 failed, 1 skipped**
  evidence is not proven unchanged baseline and remains unresolved. Do not call it baseline.
- Independent QA of commit `9d23a1c` and this evidence update is pending. No push, merge,
  real `op read`, provider call, Saxo auth or fund operation occurred.

## Historical pre-implementation checkpoint — superseded by current evidence above

- Source revision: `15fc2d9c62c73e5eb40aec3c0a3a46022a82287c`.
- Source parent: `19b49134f88e9752eda16f1d1b78a2b23d1e9e6e`; committed source tree:
  `5c35e703ecdd592571849156610ec2533814ba14`.
- Source/test diff identity: SHA-256
  `b9c005969127a269aeb70470cdcab4946f915cf166396817c2863450ec9d58b3` over the
  133,271-byte `git diff --binary HEAD^ HEAD` patch. The 255-test run preceded the local
  source commit, but the tested source files were committed unchanged at this revision.
  Documentation evidence was edited after that run; no executable source is dirty.
- Host: Windows 11 worktree; Python 3.11.15; pytest 7.4.4.
- Test dependencies use fakes only. No live provider/model/broker call.
- No image/build digest or loaded artifact exists. No container, named volume, inspect,
  exec, or browser runtime acceptance was performed.
- Evidence below distinguishes static review, focused fake tests, adjacent regression
  tests, a user-authorized host CLI identity check, and missing runtime acceptance.

| Row | Requirements | Scenario and measurable acceptance | Mode | Status |
| --- | --- | --- | --- | --- |
| OP-A01 | OP-FR-001, OP-FR-014 | Keyless disabled/missing/locked states: 0 resolver/paid-provider calls; normal free/local work | Unit/fake + runtime fake | INCONCLUSIVE |
| OP-A02 | OP-FR-004 | Export final image; examine history/config and every decompressed/reassembled layer: 0 sentinel occurrences | Built artifact | BLOCKED |
| OP-A03 | OP-FR-004, OP-FR-010 | Rendered Compose, Docker image/container/exec config, argv/env, logs/errors, browser network/storage and exports: 0 sentinel occurrences | Artifact/runtime/browser | BLOCKED |
| OP-A04 | OP-FR-005, OP-FR-012 | Only intended fake consumer holds value; observer, TUI path, runner, unrelated child and vault authority inheritance denied | Unit/fake + runtime fake | INCONCLUSIVE |
| OP-A05 | OP-FR-002, OP-FR-003, OP-FR-012 | Wrong root/target/role/provider/endpoint, lost authority: 0 resolver calls before initial denial, 0 publication/dispatch/effects after recheck denial | Unit/fake + runtime fake | INCONCLUSIVE |
| OP-A06 | OP-FR-008, OP-FR-011 | CAS conflict, wrong boot, replay, malformed/partial/oversized frame: 0 partial publication; ambiguous ack explicit | Unit/fake + runtime fake | INCONCLUSIVE |
| OP-A07 | OP-FR-006, OP-FR-010, OP-FR-011 | Locked/absent/denied/timeout/malformed CLI; <=60s; 0 fallback/dispatch; sanitized errors, no raw stderr | Unit/fake + runtime fake | INCONCLUSIVE |
| OP-A08 | OP-FR-007, OP-FR-013 | Synthetic backend stop/recreate and interrupted work: 0 durable sentinel occurrences, stale handles denied, requires-auth | Windows runtime fake | BLOCKED |
| OP-A09 | OP-FR-008, OP-FR-009 | A-to-B refresh, failed refresh, concurrent revoke/admit/dispatch: fixed capture, correct CAS, next dispatch denied after revoke, no auto restart | Unit/fake + runtime fake | INCONCLUSIVE |
| OP-A10 | OP-FR-012, OP-FR-013 | Actual Windows LinuxKit/ext4 topology; final artifact authority/private IPC/W07 adjacent denials and supported negative platform states | Windows runtime fake | BLOCKED |

`BLOCKED` rows lack the required artifact/runtime capability. `INCONCLUSIVE` rows have
partial unit evidence but do not cover the full stated scenario. No test result proves secret
absence from memory, Docker internals, image layers or an untested consumer.

## Executed evidence

### Focused runtime/transport/capture/web tests

Command, run in one pytest process:

```powershell
& 'C:\Users\ChristianGjedrem\AppData\Local\pypoetry\Cache\virtualenvs\aihf-4l3vIF0x-py3.11\Scripts\python.exe' -m pytest hedge_fund/secrets/test_docker_delivery.py hedge_fund/runtime/test_external_credentials.py hedge_fund/runtime/test_capture.py hedge_fund/runtime/test_credentials.py hedge_fund/web/test_settings.py -q --tb=short
```

Final run: **98 passed, 1 skipped in 19.08 s**; process wall time **21.507 s**;
2026-11-09 11:01:52Z. The skip is the Unix socket ownership test on Windows.
Fakes cover empty allowlist denial, private frame/receiver, invalid and oversized values,
CAS/replay/rotation/revoke, stale instance, capture metadata without value, captured runtime
source no-fallback, denied admission, fake target checks, sanitized resolver failures,
private stdin, lost acknowledgement reconciliation, and filtering of secret-named
environment variables from child processes. No provider is called.

Red/green note: the first run after child-environment hardening found one failing direct
resolver test (97 passed, 1 failed, 1 skipped in 19.32 s): direct resolver invocation did
not filter the synthetic `OPENAI_API_KEY`. The resolver boundary was tightened, then the
full focused command above passed. The failure exposed a testable boundary issue; it is not
counted as final PASS evidence.

### Preserved Spec005 W07-adjacent regressions

```powershell
& 'C:\Users\ChristianGjedrem\AppData\Local\pypoetry\Cache\virtualenvs\aihf-4l3vIF0x-py3.11\Scripts\python.exe' -m pytest hedge_fund/runtime/test_dispatch.py hedge_fund/web/test_app.py -q --tb=short
```

Result: **88 passed in 14.85 s**; process wall time **17.174 s**;
2026-11-09 11:02:27Z. Covers existing dispatch endpoint/redirect boundaries and same-origin,
Host/Origin/CSRF behavior. This is unit-test evidence only; no live Ollama request or
container network test occurred.

### Integrated delivery, web-service and W07 selection

Ran all affected focused, web-service and W07 selections in one pytest process:

```powershell
& 'C:\Users\ChristianGjedrem\AppData\Local\pypoetry\Cache\virtualenvs\aihf-4l3vIF0x-py3.11\Scripts\python.exe' -m pytest hedge_fund/secrets/test_docker_delivery.py hedge_fund/runtime/test_external_credentials.py hedge_fund/runtime/test_capture.py hedge_fund/runtime/test_credentials.py hedge_fund/web/test_settings.py hedge_fund/runtime/test_dispatch.py hedge_fund/web/test_app.py hedge_fund/web/test_services.py -q --tb=short
```

Result: **252 passed, 1 skipped in 218.10 s**; process wall time **220.493 s**;
2026-11-09 11:18:14Z. Skip: Unix socket ownership test on Windows. This includes the public
config/CLI fake delivery, operator allowlist, runtime/web capture, service, dispatch and
browser-origin regressions. Later target-allowlist and durable no-fallback tests were added;
the final integrated run below includes them.

After config nesting hardening, final config/allowlist/status selection:

```powershell
& 'C:\Users\ChristianGjedrem\AppData\Local\pypoetry\Cache\virtualenvs\aihf-4l3vIF0x-py3.11\Scripts\python.exe' -m pytest hedge_fund/secrets/test_docker_delivery.py hedge_fund/runtime/test_external_credentials.py hedge_fund/web/test_settings.py -q --tb=short
```

Result: **83 passed, 1 skipped in 6.81 s**; process wall time **9.187 s**;
2026-11-09 11:20:19Z. After later import-order/format-only edits, a focused final wiring
selection passed **6 tests in 0.98 s**, wall time **3.106 s**, at 2026-11-09 11:21:29Z.

Final integrated run after the target-allowlist and durable no-fallback tests:

```powershell
& 'C:\Users\ChristianGjedrem\AppData\Local\pypoetry\Cache\virtualenvs\aihf-4l3vIF0x-py3.11\Scripts\python.exe' -m pytest hedge_fund/secrets/test_docker_delivery.py hedge_fund/runtime/test_external_credentials.py hedge_fund/runtime/test_capture.py hedge_fund/runtime/test_credentials.py hedge_fund/web/test_settings.py hedge_fund/runtime/test_dispatch.py hedge_fund/web/test_app.py hedge_fund/web/test_services.py -q --tb=short
```

Result: **255 passed, 1 skipped in 178.94 s**; process wall time **181.461 s**;
2026-11-09T11:27:31.7859045Z. Source content is bound to revision
`15fc2d9c62c73e5eb40aec3c0a3a46022a82287c` and the patch digest above. Python 3.11.15 /
pytest 7.4.4 on Windows. The skip is
the Unix socket ownership test. This selection includes CLI/config, process-local leases,
capture, services, W07 dispatch and browser-origin tests. No provider, model or broker was
called. The exact source commit and dirty-diff identity are recorded after local commit below.

### Public CLI process-boundary check

Ran `python -m hedge_fund.secrets.docker_delivery --config <absent temporary path> --provider openai`
in a child process at **2026-11-09T11:28:52.9090344Z**. It exited **2** in **0.729 s**
with one sanitized stdout line, `delivery=denied reason=provider-not-allowed`, and empty
stderr. The CLI missing-config fake test
(`test_missing_host_mapping_config_is_empty_and_never_resolves`) asserts no dependency
calls. This process smoke supplied no mapping and did not invoke `op read`.
`pyproject.toml` entry-point and base Compose YAML were parsed;
`HEDGE_FUND_RUNTIME_PROVIDERS` is empty by default and appears only on `web-operator`.
No secret-bearing output was retained.

### Static checks

- Black `--check`: 8 changed Python files passed at 2026-11-09 11:21:21Z.
  `hedge_fund/web/test_settings.py` was
  excluded because Black reports two pre-existing formatting hunks at unchanged lines;
  no unrelated reformat was made.
- isort `--check-only`: all 9 modified Python files passed at 11:21:21Z.
- flake8 `--max-line-length=420`: all 9 modified Python files passed at 11:21:21Z.
- An initial formatting check failed on two indentation lines in the new Docker module and
  import ordering; those were corrected before the final test run. The two Black findings in
  `test_settings.py` are unchanged baseline code.

### Broader adjacent regression run

A prior adjacent web/dispatch/runner selection reported **194 passed, 7 failed, 1 skipped
in 405.98 s**. The seven failures occurred in unchanged runner/ledger tests. The
malformed-approval-audit failure reproduced alone (**1 failed in 3.92 s**). The precise
combined command and source revision/diff identity were not retained in the current
execution record, and that run preceded the latest host target/environment edits; classify
it as prior regression evidence, not final-artifact evidence or an independently verified
baseline. No repair was attempted. Full suite was not run.

### Bounded real host identity checks

1. User-authorized `op whoami` ran at **2026-11-09 11:27:18 +01:00**; result:
   **unauthenticated**, **0.093 seconds**, CLI **2.34.1**, sanitized reason
   `desktop-integration-unavailable`. Connect/service-account variables were absent.
2. At 12:18 +01:00 the user reported desktop CLI integration was on. This is an attributed
   user report, not a local settings observation. One follow-up `op whoami` ran at
   **2026-11-09 12:19:34 +01:00**; result: **unauthenticated**, **1.070 seconds**,
   sanitized reason `desktop-account-not-signed-in`. The executable resolved from a
   user-local AppData location, Authenticode status `Valid`; file-version metadata was
   unavailable in this check (earlier CLI report: 2.34.1). The `op` executable ran as a
   hidden, no-window child with stdout/stderr redirected; the parent shell was interactive.
   Nine 1Password processes were present in the same Windows session (session ID 5).
   Connect, service-account and `OP_SESSION_*` presence checks were false.

No prompt activity was recorded in either check; prompt display/interaction is unverified.
Raw stdout/stderr, account metadata and app settings were not retained or inspected. No
`op read`, vault/item access, credential resolution, Docker delivery or provider call
occurred. The sanitized CLI reason is not independent proof that the desktop app is signed
out. Path of Practice's `docs/secrets.md:33-38` documents `op whoami` from an attached
interactive terminal and biometric unlock; `scripts/dev-backend.ps1:62-85` launches `op`
from PowerShell without hiding/redirection. The hidden invocation here is a plausible
prompt-related difference, not a confirmed cause. Smallest discriminating local action:
run `op whoami` directly in an attached PowerShell/Windows Terminal; do not read a vault.

## Historical unexecuted evidence at 15fc2d9 (superseded by current evidence above)

- No built image, image/layer/config/history scan, Compose render, container inspect/exec,
  logs/browser/export scan or durable synthetic-volume sentinel scan exists.
- No actual Windows Docker Desktop LinuxKit/ext4 named-volume acceptance occurred. The
  current Compose operator uses a bind mount; the host launcher deliberately rejects it.
  Windows Docker Desktop CLI presence or a prior read-only version/context observation is
  not runtime acceptance.
- The default DeskService runtime allowlist and default host mapping set are empty. Public
  CLI/configuration path is fake-tested; no real mapping was configured and no `op read`
  occurred. Live delivery remains unavailable with the current Compose bind mount.
- Read-only Path of Practice comparison: `docs/secrets.md:6-16,33-38` and
  `scripts/dev-backend.ps1:62-85` use host `op run` process-environment injection;
  `docker-compose.yml:1-7,35-41` forwards those values into the backend container
  environment. Its Windows Compose launch is not evidence for this task's private IPC
  boundary or Docker Desktop ext4 named-volume acceptance, and its environment-injection
  design is outside the approved security contract. No Path of Practice files were changed;
  no `.env`, `.env.op`, or credential value was read.
- No concurrency race test or observer/TUI/runner end-to-end attempt was performed.
- No real provider mapping/user credential workflow or real-key smoke was enabled.

Linux/native authentication behavior is not inferred from Windows. Existing Spec005 Linux
regressions remain applicable; no new host-Linux 1Password authentication support is
claimed. Windows containers, remote daemon contexts, missing peer-auth primitives and old
images must fail closed. Runtime/platform acceptance remains BLOCKED until an isolated
synthetic project, root, named ext4 volume and final artifact are available.
