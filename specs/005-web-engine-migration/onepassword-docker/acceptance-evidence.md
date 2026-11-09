# Acceptance evidence: 1Password Docker extension

**State**: Partial implementation; no artifact/platform acceptance. No image built, no
container changed, no secret resolved. No acceptance row is PASS.

## Evidence identity and environment

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

## Unexecuted / blocked evidence

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
