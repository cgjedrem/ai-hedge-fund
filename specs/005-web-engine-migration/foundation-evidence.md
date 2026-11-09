# Foundation evidence — spec005

## Result and limits

**Historical 2026-11-02 checkpoint: T024 BLOCKED; partial, not migration
acceptance.** At that checkpoint, T015, T019–T021 and T023 were open. T023 has
since been checked, but the remaining prerequisites were not met at that time.
An existing-root attestation and cooperative locks did not prove that legacy or
out-of-band writers had lost access. Later evidence records the explicit
operator-trusted single-writer decision; it does not claim OS enforcement.
Capacity and valuation budget denials were covered, not an exhaustive budget or
writer integration/race matrix. No new host-mutation capability was enabled by
this historical checkpoint.

The baseline backend and native observations below ran against
`32537b23c8428365aa5d39b69e649b2aaeb6b2cc`. The same committed
`hedge_fund` and `pyproject.toml` snapshot was used for the Linux native run;
the reproducible Git archive is 3,194,880 bytes, SHA-256
`69ec95fa695aa51cf7937c5cf6f62ef2f70006e96531c68453da3f22eb00c898`.
This checkpoint changes the web operation lookup and its tests as well as the
frontend. The new, narrower backend and browser observations are identified
separately below; the older results are not a full-suite pass on this source.

## Isolation and platform

Tests ran on Windows 11 / NTFS with Python 3.13.7 and pytest 7.4.4. The
Linux native checks ran as UID 1000 in a Docker Desktop VM on WSL2 kernel
`6.6.87.2-microsoft-standard-WSL2`, on an ext4 named volume, with
`--network none`, dropped capabilities and `no-new-privileges`. The offline
test image was `sha256:f46586c33e835ed3ecf57a9b3199396d0301571007955c87cf69905ac4e67412`.
This is not bare-metal Linux, container-observer, installed-package or
whole-deployment evidence.

The test-owned roots, HOME/USERPROFILE and temporary directories were isolated;
credentials, provider, proxy, root and Python overrides were cleared before
imports; dotenv was disabled; external I/O was denied by the existing isolation
harness. The real-browser harness used its own seeded synthetic root, loopback
port 8876 and fixture-owned build output; it refused reuse of another server.
No real provider, paid service, LLM, broker, protected deployment or existing
compose service was used. The exact test-owned Linux volume, browser server and
browser fixture were removed after their runs.

## Backend and native observations

The Windows selections used the documented isolated Python with
`python -m pytest <selection> -p no:cacheprovider -q --tb=short`; logs are
session-owned artifacts. Times below are UTC and include command startup/teardown.
These are baseline observations for the specified selections only, not the
development red runs and not a full Python suite.

| Selection | Start–end on 2026-11-02 UTC | Observed | Log SHA-256 |
| --- | --- | --- | --- |
| `test_acceptance_isolation.py`; runtime `test_root.py`, `test_admission.py`, `test_handover.py`, `test_capture.py`, `test_policy.py`, `test_operations.py`; web `test_app.py`, `test_actions.py`, `test_jobs.py` | 19:23:43.443–19:28:51.021 | 356 passed, 10 skipped, exit 0 | `b6a86219a68aa4a03db565b04cce51d04a9b188928cf8feccedf2399340a0ec1` |
| `hedge_fund\test_run.py` | 19:30:01.332–19:32:06.959 | 66 passed, exit 0 | `85b670766cf5d0e61f03664725620ee4ecff296ddf90484fce5652c590195815` |
| `paper\test_ledger.py paper\test_tick.py -k "approval or mailbox or expiry or stale"` | 19:33:22.831–19:33:45.417 | 57 passed, 103 deselected, exit 0 | `8f59c726204afbc9fcf01cd1ae4dea793c957b4a39c455e76e28c9ec409cb23b` |
| Windows `runtime\test_native_primitives.py runtime\test_native_credentials.py` | 19:27:58.246–19:28:19.620 | 10 passed, 3 skipped, exit 0 | `9cf0098e7cda05313d3142c53d51ba7e3de7776f05ccc4ad1cb1fc0ac7a2ce87` |
| Linux ext4, same two native files, `-q -p no:cacheprovider` | 19:29:32.775–19:29:42.290 | 9 passed, 4 skipped, exit 0 | `b056cb71e2cd6e822134fbd187bae31ea76adeedb9aaac5c3d7bd81601251050` |

The skipped tests are not counted as passed. The native observations exercise
specific filesystem, lock, identity and credential primitives only; they do
not prove writer exclusion, runtime ownership, deployment readiness or
automatic recovery. `python -m flake8 --select E9,F63,F7,F82` on
`runtime\handover.py`, `runtime\operations.py`, `web\app.py`, `web\jobs.py`
and `web\services.py` exited 0 at 19:30:21 UTC. This is a critical-error
selection, not a full lint pass.

On the current backend source, the isolated selection `web\test_app.py`,
`runtime\test_operations.py`, and four specific `web\test_jobs.py` cases
(request lookup, corrupt lookup, contended status, and reviewed-operation
preview/accept) passed **96 tests** in 524.63 seconds, exit 0, UTC
20:09:04.725–20:18:01.196 on 2026-11-02. Log SHA-256:
`5cc5866d72658b98f377c077cfdd8460d17131e933c90a4a0fddcc7c5fb030f2`.
After collection began, the request-lookup test was strengthened to compare
the complete synthetic runtime tree before and after the GETs; that final test
passed separately (1 test, 10.60 seconds), log SHA-256
`2283f8f3f7f4ae74453a2bb013fd1971f5b673f3ab41114c4d1e39b2c12e4373`.
This verifies the new route's selected cases, not the entire backend or
deployment.

## Coverage of red-team obligations

Statuses here describe only the observations above and this checkpoint's
frontend tests; they do not change the PENDING statuses in
`acceptance-matrix.md`.

| Finding | Current evidence and remaining gap | Status |
| --- | --- | --- |
| LM1 | Cooperative admission and handover regressions pass; unaware writers are not fenced and the all-writer race matrix is not complete. | BLOCKED |
| LM2 | Owned loopback browser fixture only; no host-writer/read-only-container or no-autostart deployment proof. | NOT VERIFIED |
| LM3 | Selected ledger/approval regressions pass; ambiguous post-fill reconciliation and Resume are not fully accepted. | PARTIAL |
| LM4 | Selected stale/approval checks and a synthetic template archive/restore run pass; complete due-set/backlog and stopped deployment restore remain open. | PARTIAL |
| LM5 | Boundary tests do not establish exclusive SIM binding across roots or complete SIM lifecycle denials. | NOT VERIFIED |
| LB1 | Root, capture, isolation and headless selections pass; active-child credential lifecycle and broader writer integration remain open. | PARTIAL |
| LB2 | Selected Host/Origin/CSRF and loopback checks pass; read-only container and every future channel are not proven. | PARTIAL |
| LB3 | No live endpoint/DNS/TLS/redirect test is claimed by this checkpoint. | NOT VERIFIED |
| LB4 | Native private credential primitives pass on the two tested filesystems; complete credential UI and active-capture workflow remain open. | PARTIAL |
| LB5 | Tested NTFS and VM ext4 primitive rows pass; skips, other environments and full deployment remain outside the result. | PARTIAL |
| HM1 | The authorized amendment is recorded without claiming a fresh full-suite or retirement pass. | PARTIAL |
| HM2 | Selected policy tests exercise explicit bounded authorization with fakes; complete provider/UI acceptance is not established. | PARTIAL |
| HM3 | Selected bounded-policy regressions pass; complete scheduled-runner and dispatch acceptance remain open. | PARTIAL |
| HM4 | Selected durable/interruption and fencing tests pass; complete detached-owner/restart and platform lifecycle acceptance remain open. | PARTIAL |
| HM5 | Selected durable confirmation/idempotency and approval boundary tests pass; complete approval provenance and operation UI acceptance remain open. | PARTIAL |

## Frontend acceptance

The partial T023 slice records non-secret request identities before admission
and recovers by read-only request-ID lookup without resubmitting. Recovered
identities are independently monitored, with a 16-monitor cap; active,
unknown, mismatched and unobserved identities block a new admission until a
terminal result is verified or the operator explicitly removes the monitor.
Removal does not cancel the operation or establish its outcome. Polling rejects
stale identity/progress while allowing actual progress despite wall-clock
rollback. No confirmation token or request payload is persisted.

The source/test identity is the published base
`32537b23c8428365aa5d39b69e649b2aaeb6b2cc` plus **19 changed or new files**
under `frontend` and `hedge_fund`, normalized SHA-256
`d1c8865a6db4b03ac30fd73fa0454cf00c5ca36e83cd96264c4fd207d4a75a98`.
To reproduce, sort `git ls-files --modified --others --exclude-standard --
frontend hedge_fund`, hash each file after CRLF-to-LF normalization, and hash
UTF-8 lines `<file-sha256>  <repository-relative-path>\n`. This is a
changed-file manifest, not an installed-package or complete-deployment hash.
Session-owned logs are not included in the repository.

| Selection | Observed on 2026-11-02 UTC | Log SHA-256 |
| --- | --- | --- |
| `vitest run src --maxWorkers=1 --testTimeout=30000` | 107 passed, exit 0; 20:47:51.353–20:48:11.596 | `1e7708ba681238cc5ad7d359b363ad6155c516874566d7d00e388b4896922840` |
| Owned real-API browser harness: `--lifecycle operation-recovery.spec.ts recovery.spec.ts --workers=1` | TypeScript and production build passed; 4 browser tests passed, exit 0; 20:48:30.089–20:49:11.505 | `1f8a1557aec94cc71333f635d5626d6364ddae073cffc4fbb44104797cc19e14` |
| Malformed detail-array regression, before repair | 1 failed with `TypeError`, 19 skipped; exit 1 | `dda79ff91a8e50dfaf3001a716b225b402ab10ef535bbc44ac520c515047bc94` |
| Same regression after repair | 1 passed, 19 skipped; exit 0 | `3f0d976ec91ce8c745bfa44d4d2f040102618f776281f7a1a621c7cc6e3b1eae` |
| Changed web Python files, `flake8 --select E9,F63,F7,F82`; `git diff --check` | Both exit 0; critical-error and whitespace checks only | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |

A preceding frontend run had 103 passes and three failures (log SHA-256
`69c93f04d4909e69b4c5987daa07ce90316f698f365f93c14d5c3aa1b3f99b47`).
Two exposed legacy error-message loss and were repaired; the third timed out
at five seconds. A focused rerun still timed out once, then the four affected
tests passed with one worker and a 30-second timeout (log SHA-256
`4d47386f339d7fdbd08d43ba7d1b097be0e36090bf5700f2d6dfa1c0433ad342`).
The timeout's cause is not established.

An earlier browser attempt on an intermediate source had two timeout failures
and two tests did not run (log SHA-256
`8bd51648e5923e67bdaf34aa02d6c07f702f942b3f29369119b782397cc2ed47`).
The cause is unproven; a later intermediate-source run passed four tests (log
SHA-256 `04ccbdeec44178860393753ed37791742fb0481b6523652909bc9b04cf7f1eff`).
Neither run establishes a flake-free result or represents final-source
acceptance.

The final browser harness produced three build files (1,014,493 bytes),
artifact SHA-256
`0f0da2293f91205e608970dbab8f4f1061ef92391cfb5c3c157835db72626cbe`.
Vite reported a non-fatal bundle-size warning. The harness released owned
loopback port 8876 and left no new browser fixture root.

Two independent reviewers examined the operation slice in three bounded
cycles. Their final targeted re-reviews found no significant blockers after
the reported findings and malformed-detail regression were repaired. This is
not approval of T024, production deployment or full migration.

## Final bounded validation snapshot (2026-11-04)

**T024 BLOCKED; partial evidence only.** Test base:
`146a242610d7ba50c72620db398498d34520cc1d`, branch
`cgjedrem-vigilant-robot`. Final changed source/test diff under `hedge_fund/`
and `frontend/`: 28 files, 142,499 diff bytes, SHA-256
`ee1a9e12939a105805fa329d59d907295e2a28312703c27804f7dfbc01d37f51`;
normalized changed-source manifest 1,434,222 bytes, SHA-256
`dd829f011b549605045aef05df9ae17dc3b1a2590d31abbcf43cdc241b82ad7d`.

| Validation | Exact selection / environment | Result and status |
| --- | --- | --- |
| Non-TUI full Python suite | `python -m pytest -q --tb=short hedge_fund --ignore=hedge_fund/tui`; Windows 11 Enterprise build 26200, NTFS, Python 3.13.7; isolated synthetic roots and fakes | **FAIL**, 14 failed / 2,367 passed / 51 skipped in 5,452.28 s, exit 1. Run `11:35:49.9994857+01:00`–`13:06:45.6327229+01:00`; output SHA-256 `e5434bf3b44037aad9e7ed631c4173c8a5ee01abc37704ff835d5fdd08c83efc`. Exact 14 node IDs and observations in `implementation-evidence.md`. This run predates the final demo-denial wording correction; full suite was not repeated on final source. |
| Final failure reruns | Writer-race file 12 tests; three previously failing `web/test_actions.py` nodes; eight previously failing `web/test_jobs.py` nodes; all serial, synthetic roots/fakes | **PASS focused**: 12 / 3 / 8 passed, respectively. Full-run cause remains unknown; focused passes do not erase full-suite failure. |
| T015 | Handover/authority/CLI/web/peer-recovery selection; synthetic Windows/NTFS, Python 3.13, fake transport | **55 passed in 30.42 s**, exit 0. Existing and relocated roots remain read-only pending exact offline acknowledgement; second service cannot recover the live peer operation. |
| T019/T020 backend | `web/test_app.py`, `test_actions.py`, `test_jobs.py`, `test_valuation.py`, plus `web/test_main.py`; synthetic NTFS, fake transport | **145 passed in 282.76 s** and **12 passed in 4.82 s**, exit 0. Includes common error/status/CSRF/origin/readonly/observation contract and budget-exhausted emitter. |
| T019/T020 frontend/build/browser | Vitest in `frontend/`; TypeScript/Vite; owned real-API browser on loopback 8876 | **13 files / 216 tests passed**; TypeScript + Vite build passed, 3 files / 1,035,387 bytes, artifact SHA-256 `57f1e1c18ab9f70739b8f4ec8e6f958b064a30407ef1664cb403e5e1fb9142e1`; **3 Playwright tests passed in 17.3 s**. Fake/unit, build, and browser are separate evidence types. |
| TUI | All 11 `hedge_fund/tui/test_*.py` files, one process at a time | **90 passed, 0 failed files**, exit 0. Unit/fake tests; no concurrent pytest. |
| Windows native | `runtime/test_native_primitives.py` and `runtime/test_native_credentials.py`; Windows/NTFS | **10 passed, 3 skipped in 10.46 s**, exit 0. Native filesystem/credential primitive row only. |
| Linux native | Same tests; Docker 29.9.2, image `aihf-qa2-pytest:d054b3ae` (SHA-256 `f46586c33e835ed3ecf57a9b3199396d0301571007955c87cf69905ac4e67412`), WSL2 kernel `6.6.87.2-microsoft-standard-WSL2`, ext4 named volume, UID 1000, `--network none` | **9 passed, 4 skipped in 4.74 s**, exit 0. Linux native row only; volume and stage removed. |
| POSIX append boundary | `hedge_fund/runtime/test_root.py::test_handle_relative_append_preserves_bytes_and_rejects_hardlinks`; pinned Linux image, ext4 named volume, UID 1000, `--network none`, read-only source mounts | **1 passed in 0.19 s**, exit 0, host `14:30:09.7656523+01:00`–`14:30:14.5056497+01:00`. Unique volume removed. Selected append boundary only; no broad POSIX writer/race acceptance. |
| Style | Changed Python files, existing isolated Python 3.13 venv; Black 420, isort Black profile, Flake8 420, `git diff --check` | **PASS**: Black 24 files unchanged; isort, Flake8 and diff check exit 0. |

### Current LM/LB/HM disposition

| Obligation | Evidence / remaining acceptance | Status |
| --- | --- | --- |
| LM1 | Root-bound operator trust and cooperative writer tests pass focused; unaware/out-of-band writers remain outside the guarantee and broad T027 failures are unexplained. No OS-enforcement claim. | PARTIAL |
| LM2 | Owned loopback browser recovery passes; host-writer/read-only-container and no-autostart deployment proof absent. | NOT VERIFIED |
| LM3 | Ledger append/fill and selected approval races pass; durable rewind intent and complete post-fill reconciliation remain open. | PARTIAL |
| LM4 | Selected archive/restore and stale-review cases pass; full due-set/backlog and stopped-deployment restore remain open. | PARTIAL |
| LM5 | Synthetic account-binding tests do not establish complete production SIM lifecycle wiring. | NOT VERIFIED |
| LB1 | Root, isolation, headless and writer selections pass; active-child credential lifecycle and complete writer integration remain open. | PARTIAL |
| LB2 | Selected Host/Origin/CSRF and loopback checks pass; read-only-container and future-channel guarantees absent. | PARTIAL |
| LB3 | No live endpoint/DNS/TLS/redirect test is claimed. | NOT VERIFIED |
| LB4 | Windows/NTFS and Linux/ext4 native primitive selections pass with skips; credential UI and active-capture workflow remain open. | PARTIAL |
| LB5 | Native rows pass on tested NTFS and ext4; skipped cases, other filesystems and full deployment remain outside evidence. | PARTIAL |
| HM1 | The full non-TUI suite failed 14 tests; focused reruns pass, root cause unresolved. | PARTIAL |
| HM2 | Selected bounded-policy tests use fakes; complete provider/UI acceptance is not established. | PARTIAL |
| HM3 | Selected bounded-policy regressions pass; scheduled-runner and dispatch acceptance remain open. | PARTIAL |
| HM4 | Selected durable/interruption and fencing tests pass; detached-owner/restart and platform lifecycle acceptance remain open. | PARTIAL |
| HM5 | Selected durable confirmation/idempotency and approval boundary tests pass; complete provenance and operation UI acceptance remain open. | PARTIAL |

T021 remains unchecked for durable rewind intent, mandate rename-plus-rewrite
journaling, identity-fenced POSIX unlink evidence, complete Saxo
credential/demo/bootstrap admission, and exhaustive dynamic/out-of-repository
writer inventory with race-level evidence. The selected POSIX append boundary
passes one ext4 regression but does not establish broad POSIX writer/race
behavior. T024 is blocked by these open
T002–T023 prerequisites and the failed full-suite result. Final task state:
T015, T019 and T020 checked; T021, T024 and T027 unchecked. T027 remains open
because three race-file cases failed in the full run despite passing focused.
T023/T025/T026/T028 checkboxes remain unchanged.
