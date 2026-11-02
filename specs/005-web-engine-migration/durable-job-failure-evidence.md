# Durable job failure investigation

## Disposition and scope

**Current disposition:** the repair is merged locally with PR8 head `1fb15be` and
the final full Python suite passed **1657 tests, 42 skipped** on the merged
artifact. The combined runtime/web suite passed **482 tests, 4 skipped**. A
missed durable `apply_if_current` lock-acquisition retry was found by independent
QA, reproduced red with a deterministic regression, and fixed with a paired
non-retry test for `OperationBusy` raised by the effect itself. This single
Python runtime/test slice is not migration or merge acceptance. Deliberate
four-reader saturation evidence below predates the merge/retry change and is not
a supported-load claim.
Execution owner: repository `python-dev` persona. Initial independent QA blocked
publication on the missed retry and stale evidence; the code and provenance
updates are complete. Final independent static QA returned **PASS** with no
blocking findings; the reviewer attributed, but did not rerun, the reported
tests. No manifest changes or real fund/provider/broker operations. Publication
to the existing PR remains pending.

Starting revision: `d5858e4ae425a22c810e2315a16e4552fc1e0e2c`.
The inherited `1551 passed, 42 skipped, 2 failed in 526.58 s` report is an input,
not a reproduced pass. The two requested symbols are:

- `hedge_fund\web\test_jobs.py::test_reviewed_operation_preview_accept_persists_capture_and_report`
- `hedge_fund\web\test_jobs.py::test_reviewed_backtest_cancellation_closes_fake_client_and_freezes_model`

Read: repository Python agent, constitution, forward migration contract,
Spec005 spec/plan/tasks, implementation evidence/progress, final evidence and
QA disposition. Scope remains paper-only, fake-only, fixed-root and fail-closed.

## Findings, discrimination and repair sequence

### 1. Status monitoring can overtake a waiting worker

**Confirmed concurrency defect:** each registry read and worker transition acquired
the same exclusive native lock through independent nonblocking retry loops.
There was no process-local arrival ordering. A newly arriving status reader could
acquire before a previously waiting worker; repeated short holders could consume
the entire existing five-second admission budget. This is starvation, not proof
of one permanently held lock or a corrupted report.

Evidence before the first runtime repair:

- Original two tests alone: **2 passed in 28.03 s**. This did not close the issue.
- Representative combined runtime/TUI/backtesting/web selection: **1 failed,
  497 passed, 4 skipped in 491.20 s**. The adjacent durable-worker test
  `test_operation_job_registry_persists_progress_and_result` failed reading its
  result: `OperationError` caused by `WriterConflict`, through
  `OperationStore._read_snapshot -> AdmissionCoordinator.registry_read_lock ->
  _acquire_os_lock`. No provider was involved.
- Four bounded synthetic status readers against the requested jobs reproduced
  a preview test failure. Safe native-lock evidence at
  `2026-11-01T20:24:17.534821+00:00` recorded **5.0005772 s** waiting while the
  current registry holder was only **0.1726671 s** old. The holder was the worker's
  cancellation-boundary read. Other readers and shutdown were in the same native
  acquisition path. Longest individual exclusive hold in that run: **2.0244202 s**.
  The requested preview remained `running` at its existing observation deadline;
  cleanup then cooperatively cancelled it. This trace does **not** claim that
  this particular preview attempt produced `worker-failed`.
- Deterministic red:
  `test_registry_waiting_writer_cannot_be_overtaken_by_status_reader` pauses a
  writer immediately before its native acquisition and introduces a later reader
  through a separate coordinator for the same root. Before repair, that reader
  enters first: **1 failed in 1.49 s**. Synchronization is event-based; the
  bounded quiet observation is not used to advance either worker.

Repair: a process-local FIFO ticket queue keyed by native root identity and lane
filename orders contenders **before** opening/acquiring their native lock.
The native OS lock still grants authority; private-storage, root-identity,
enrollment, owner and sidecar checks remain intact. Waiting consumes the existing
budget; this FIFO change did not increase its timeout or admission bound.
Tickets are keyed by root identity and lane, so independent lanes/roots do not
share a queue; no FIFO-specific independence regression was added. Tickets are
removed on success, timeout and exceptions.

The FIFO regression passed in the first focused **4 passed in 10.57 s** run.
An adjacent regression verifies that an expired local waiter does not release
the active holder, that nested snapshot reads retain the held lane, and that the
ticket queue is removed after release.

**Attribution limit:** the inherited full-suite report omitted the worker cause.
It cannot establish that both historical failures had the same exception.
The observed starvation defect, exact native acquisition failure and deterministic
arrival-order regression establish this defect independently.

### 2. Cancellation test's fake backtest advances without cancellation

**New discriminating evidence obtained before the second repair.** FIFO alone did
not establish closure: the four-reader saturation experiment still exceeded the
preview test's twenty-second observation deadline, now without a native
acquisition failure. Its cleanup produced `WorkerFenced`/`JobCancelled`, not
proof of the historical hidden worker exception. No second runtime optimization
was guessed from this result.

A runtime-only cached-Windows-API experiment also failed the preview observation
under saturation (**1 failed, 1 passed in 45.00 s**). Caching was **not** committed
or included in the implementation. A separate synthetic unfair-lock replay
completed after **80.7512891 s**; this negative result is retained rather than
represented as a deterministic reproduction.

The cancellation fake had a separate, exact fixture failure path:
`release.wait(timeout=2)` ignored its false return, advanced to the second
valuation and returned `None`. Under delayed parent settings work, the worker
therefore tried to save `None` as a validated backtest report. The production
type guard correctly raised `TypeError`; the registry converted it into the
previously opaque `worker-failed`.

Discrimination on the first repair artifact, before changing the fixture. The
inherited full-suite report did not preserve the original exception, so this
reproduction does **not** prove that the historical cancellation failure was
this exact `TypeError`:

- An owned, runtime-only three-second delay in active-job model-setting work
  reproduced the requested cancellation symbol: **1 failed in 9.82 s**.
  Its active capture was already absent.
- Safe worker trace at `2026-11-01T20:40:10.152319+00:00`:
  `TypeError -> DeskService._execute_captured_backtest ->
  OperationJobRegistry.apply_if_current -> OperationStore.apply_if_current ->
  backtesting.research.save_result:35`.
- Repository logger emitted only bounded metadata:
  `phase=work type=TypeError cause_type=TypeError errno=None winerror=None`
  plus trusted module/function/line locations. No exception message or report,
  model, configuration, prompt, root path or credential contents were logged.
- Deterministic red:
  `test_reviewed_backtest_pause_requires_explicit_release` makes any timed wait
  expire immediately and orders model-setting work after the fake's wait call.
  The unchanged fake advances and fails with the same `TypeError`:
  **1 failed in 7.89 s**.

Second repair: paused fake workers now wait for the explicit release event rather
than a wall-clock expiry. This is a handshake correction, not a longer timeout.
The existing parent observation bounds and unconditional `finally: release.set()`
cleanup remain; the accept call also releases/closes if submission raises before
the main `try/finally`. The release-wait regression injects an instrumented event
only into that fake instead of replacing `threading.Event` process-wide. The same
correction applies to the two adjacent durable-registry progress/cancellation fake
workers with identical premature-advance behavior.
No production report type guard, cancellation fence or provider guard was relaxed.

The deterministic fixture regression, original cancellation, safe diagnostics and
adjacent progress/cancellation tests passed together: **7 passed in 36.46 s**.

### 3. Windows native ABI type-retention defect

**Fresh discrimination before the third runtime repair:** neither FIFO nor the
fixture correction closed the combined suites. The first-repair combined run
failed `test_paid_fd_web_backtest_uses_guarded_real_client_and_fake_transport`
at worker claim. Safe logging showed `OperationError -> WriterConflict` at
`_local_lane`; **1 failed, 502 passed, 4 skipped in 478.95 s**. This test uses
the real guarded client with a fake transport, not a paid call.
The next combined attempt failed durable cancellation and owned-child observation:
**2 failed, 267 passed, 4 skipped in 392.99 s**. These are failed repairs,
not baseline exemptions.

Safe live stack sampling repeatedly placed worker and status-reader threads in
`root._nt_open_child`, root revalidation and private-storage verification while
they were traversing the durable operation snapshot/transition path.
Inspection found an allocation-retention defect below those unchanged guards:
Windows child-open, token, ACL and rename helpers declared new `ctypes.Structure`
classes on every call, then passed them to `ctypes.POINTER`. CPython retains
pointer types keyed by class identity for the life of the process. These were
not transient allocations that garbage collection could reclaim.

**Native discriminating measurement before repair**, timestamp
`2026-11-01T21:49:16.4988617+01:00`, same checkout-owned deep synthetic root:

- Exactly **100 root revalidations**, **1000 `_nt_open_child` calls**.
- `ctypes._pointer_type_cache`: **113 -> 3113 -> 3113 after `gc.collect()`**.
- **78** collections during the bounded measurement; **0.1115136001 s** in
  collections; **0.6014598000 s** total wall time.
- The retained-type growth was **3000** entries for just 100 root checks.
  Repeated snapshots, ACL checks and sidecar writes multiply those retained
  identities over a long process lifetime. This is a plausible contributor to
  progressive load sensitivity, not proof that it caused either historical
  worker failure. No provider error was involved in this measured native probe.

Deterministic red covers **revalidation, private ACL verification and atomic
write/read**, each warmed once and repeated three times:
`test_windows_root_guards_do_not_retain_new_pointer_types_per_call[...]`.
All three saw newly retained root-module pointer types:
**3 failed in 0.69 s**.

Third repair: move the exact Windows ABI structures to module scope and reuse
their class identities. Child-open, token, ACL, rename and delete helpers still
make the same native calls with the same field layouts, flags, permissions,
lengths and status handling. No root identity, ACL result, admission decision,
provider authorization or report value is cached. There is **no DLL/API caching
implementation**, no timeout increase, and no Windows `OpenProcess` change.

Post-repair native measurement kept the same **100 root revalidations and
1000 child opens**, with pointer cache **26 -> 26 -> 26 after collection**.
Wall **0.1979000000 s**; **46** collections, **0.0518600000 s** collection time.
The claim is bounded class retention, not a statistical performance guarantee.

The first green attempt also exposed an accidentally displaced existing test-tail
assertion; the retention assertions themselves passed, but unrelated `b"second"`
file assertions had landed at the end of the new test. Those existing assertions
were moved back to their original atomic-write test without altering them.
The corrected final artifact passed **11 focused regressions in 24.13 s**:
all three native retention scenarios, FIFO/timeout cleanup, both original symbols,
explicit cancellation release, and all safe-failure diagnostic phases.

Independent review found the same dynamic ABI class pattern in
`runtime/ownership.py::_windows_process_identity`, outside those three root guards.
Before changing it, a credential/proxy-scrubbed, dotenv-disabled probe queried only
the current test process through `current_process_identity()` 25 times. At
`2026-11-02T08:13:40.246751Z`–`08:13:40.248933Z`, its module-owned pointer-type
cache grew from **0 to 25**; no process was signalled and no network/provider call
was made. Pre-fix `ownership.py` SHA-256:
`25636b43652f2129dc29c7c5b60b33fd275cf4da7211e9b5918e84fd93775196`.
The new Windows-only regression then failed first as intended:
`2026-11-02T08:14:15.724159Z`–`08:14:16.888449Z`, **1 failed, 2 deselected
in 0.11 s**, specifically retaining three new local pointer classes on three calls.
Moving the unchanged `_FileTime` layout to module scope made the regression pass
at `2026-11-02T08:14:39.9927002Z`–`08:14:41.0479304Z` (**1 passed, 2 deselected**).
The complete ownership module passed **3 tests** at
`2026-11-02T08:14:48.9148903Z`–`08:14:50.1184451Z`. A post-fix isolated probe
made 25 current-process identity reads and retained **1 stable pointer type**
(`0 -> 1`, no new types after the baseline).

### Diagnostic errors do not block durable worker state

Independent review also identified that a failing log handler could interrupt the
worker before `interrupt()` or `fail()` persisted its terminal state. A new
synthetic-only regression first failed for all three phases (claim, work and
completion): **3 failed, 24 deselected in 6.64 s**, observed
`2026-11-02T08:16:33.8273352Z`–`08:16:45.4017411Z`; each operation remained
`accepted` or `running` after the diagnostic raised. The worker now attempts the
durable transition before logging its primary failure. The same three cases then
passed (**3 passed, 24 deselected in 5.07 s**,
`2026-11-02T08:17:06.1179337Z`–`08:17:13.6382337Z`); the injected diagnostic
exception remains visible to the Future rather than being swallowed.

### 4. Safe worker diagnostics

`hedge_fund.web.jobs` now uses the repository logging convention already used for
operation-sidecar repair: exception **types and numeric OS codes**, never exception
text or `logger.exception`/`exc_info`.

The implementation adds fixed failure phases for submission, claim, work,
completion, failure persistence, interruption and cancellation cleanup. It follows
at most four exception objects, detects cycles, limits source locations to eight,
accepts only trusted repository module/function identifiers, and represents
external exception types as `ExternalError`. Numeric codes must be actual integers.
No frame object, locals, source text, payload, operation request, configuration,
provider response or credential is attached to a log record or public API.
Existing public `worker-failed` remains unchanged.

Deterministic diagnostics red: injected chained synthetic `RuntimeError` /
`OSError(5, <sentinel>)` at claim/work/completion produced the correct durable
states but no diagnostic: **3 failed in 10.60 s**. Green verifies phases, cause
type/errno, absence of sentinel/root contents, no `exc_info`/`stack_info`, and no
sentinel in the public operation view.

## Isolation and artifact identity

All application imports and tests use the existing repository test isolation:
checkout-owned, marked `outputs\spec005-test-*` roots; synthetic fresh enrollment;
HOME/USERPROFILE/TEMP/TMP/APPDATA/XDG redirection; dotenv disabled; provider,
credential, root, model and proxy variables scrubbed; test network sentinels and
fake transports. Web jobs inject fake data clients and fake analysts. There are
no real market-data, LLM, paid-provider or broker calls.

Only synthetic fixture-owned child processes/locks are used by native tests.
No creator server on 8765, existing preview on 60639/PID45300, real funds/runners
or unrelated process/worktree was controlled. Application source comes from this
checkout. Bytecode/user-site/cache writes are disabled or isolated.

Merged-head tests use Windows Python **3.13.7**, pytest **7.4.4** from the
existing LocalAppData Poetry environment
`%LOCALAPPDATA%\pypoetry\Cache\virtualenvs\aihf-Tbl0PwyA-py3.13\Scripts\python.exe`.
The first full run exposed that this environment lacked locked `curl_cffi==0.16.3`.
The interpreter was repaired without network access or manifest changes: the
cached Windows wheel's SHA-256 matched the exact `poetry.lock` hash
`fe87b66e324ed7318166698e02169f3208dbda32b872a27d2bc61a9c19b335eb`, then it
was installed with `pip --no-deps --no-index`. `cffi`, `certifi` and `pycparser`
were already present. The initial missing-dependency run is not test evidence.

The six-path pre-follow-up tracked code/test diff was measured with
`git diff --binary -- hedge_fund/runtime/admission.py hedge_fund/runtime/test_admission.py hedge_fund/runtime/root.py hedge_fund/runtime/test_root.py hedge_fund/web/jobs.py hedge_fund/web/test_jobs.py`:
**31,291 bytes**, SHA-256
`d2d4dff1691cf44bc5c07f48e25cd4fd7dec768e036823721c1abcc749d198cb`.
This identity excludes the later ownership regression, this evidence document
and ignored local experiment files.

| Pre-merge source/test path (historical, superseded) | SHA-256 of exact working bytes |
| --- | --- |
| `hedge_fund\runtime\admission.py` | `1693ffdceed6a097ffa3b158fd3e0cef3b09f96529d9abdd3d8251930f06b1c6` |
| `hedge_fund\runtime\test_admission.py` | `013aa83f4914828138deef244fd540efb248f9e0958c3ff0ad64433829bb3d22` |
| `hedge_fund\runtime\root.py` | `599a67df58f86e792cd4dce817e94c3aef3bcea308b1b7aed140c016061b6235` |
| `hedge_fund\runtime\test_root.py` | `2619dff25f2691f2b694d25b958d85a0153d979c58bbe54a7fa8cb551bf4a679` |
| `hedge_fund\web\jobs.py` | `59d1c5d51f2bab428687649534eea7c5e4d34337c042f23e740806ee211f7bf5` |
| `hedge_fund\web\test_jobs.py` | `ec75f4a988ccd933a745171ea54d357bcf640d84f77e2e363db7aafaaac91f47` |

Existing NTFS ACL/ext4 evidence documents are not edited. Root native ABI
definitions are now reused, but native guard conditions are unchanged.
Windows `OpenProcess` observation code is not edited. `runtime\ownership.py` is
changed only to reuse its existing `_FileTime` layout; its pre-fix SHA-256 was
`25636b43652f2129dc29c7c5b60b33fd275cf4da7211e9b5918e84fd93775196`.
The following are **pre-merge working-file SHA-256 values**, not Git blob IDs,
and are not claims about the merged artifact:
`paper\runner.py` (`b771877fa955b9ef0151ca8b86996ea5df37d603ae297cbf13b68e71da2326c3`),
`runtime\operations.py` (`283cd6af28a1e5f2370eaefb06e09fa1e5ccfe12254a21721a4ded204c89c317`).
Historical native evidence remains historical; it is not rebound to a new
artifact by this document.

## Pre-merge commands, windows and results (historical)

The measurements in this section were made before integrating PR8 head
`1fb15be`. They describe the earlier repair artifact only; they are not final
merged-head confirmation.

`H(label, options, paths)` below means the **exact command form**:

```powershell
$env:PYTHON_DOTENV_DISABLED='1'
$env:PYTHONDONTWRITEBYTECODE='1'
& 'C:\Users\ChristianGjedrem\source\repos\copilot-worktrees\ai-hedge-fund\cgjedrem-vigilant-robot\outputs\spec005-poetry-envs\aihf-Tbl0PwyA-py3.13\Scripts\python.exe' outputs\run_job_evidence.py LABEL OPTIONS PATHS
```

The owned harness adds `-p no:cacheprovider -q --tb=short`. It records UTC start/end,
exact source hashes, scoped diff SHA-256, executable/version, scenario flags,
exit code and elapsed wall time to `outputs\job-LABEL.json`. PowerShell redirected
outputs use `*> outputs\job-LABEL.log` (UTF-16 on this host). Safe diagnostic probes
record only exception types/codes and repository filename/function/line locations,
not locals or exception text. A bounded heartbeat does the same for live threads.
All owned poller/watchdog threads are joined; marked synthetic homes are cleaned.

| Label / evidence tier | UTC window, 2026-11-01 | Exact result / pytest duration; harness wall |
| --- | --- | --- |
| `isolated-before` / fake API | 20:10:21.536796–20:10:50.568783 | 2 passed, 18 deselected / 28.03 s; 29.0280238 s |
| `combined-before` / combined fake/native | 20:11:16.533525–20:19:28.464408 | 1 failed, 497 passed, 4 skipped / 491.20 s; 491.9270875 s |
| `full-before` / original imported runtime | 20:21:58.641322–20:31:52.306205 | 1 failed, 1552 passed, 42 skipped / 592.97 s; 593.6616420 s |
| `diagnostics-red` / injected unit failure | 20:23:04.941632–20:23:17.679351 | 3 failed, 20 deselected / 10.60 s; 12.7352175 s |
| `poll-before` / synthetic status load | 20:23:49.552335–20:24:43.754818 | 1 failed, 1 passed, 21 deselected / 53.51 s; 54.1978433 s |
| `starvation-red` / controlled native ordering | 20:26:33.041679–20:26:36.623623 | 1 failed, 21 deselected / 1.49 s; 3.5774130 s |
| `focused-green` / first repair | 20:27:48.724809–20:28:01.582135 | 4 passed, 41 deselected / 10.57 s; 12.8537691 s |
| `poll-after` / first repair saturation | 20:28:21.641038–20:29:16.843627 | 1 failed, 1 passed, 21 deselected / 54.44 s; 55.2003300 s |
| `cache-experiment` / uncommitted runtime experiment | 20:30:19.265301–20:31:04.954204 | 1 failed, 1 passed, 21 deselected / 45.00 s; 45.6854998 s |
| `harness-green` / isolation and first repair | 20:34:38.957965–20:35:16.075581 | 24 passed, 18 deselected / 36.08 s; 37.1174954 s |
| `cancellation-discrimination` / new safe cause | 20:40:00.760920–20:40:11.594030 | 1 failed, 22 deselected / 9.82 s; 10.8330156 s |
| `pause-red` / deterministic second-cause unit | 20:41:14.524534–20:41:23.459838 | 1 failed, 23 deselected / 7.89 s; 8.9352278 s |
| `pause-green` / final artifact unit/fake | 20:41:51.145797–20:42:28.632062 | 7 passed, 17 deselected / 36.46 s; 37.4861337 s |
| `combined-final` / first repair, invalidated | 20:35:44.930498–20:43:44.847069 | 1 failed, 502 passed, 4 skipped / 478.95 s; 479.9159243 s |
| `combined-confirmation` / fixture repair, invalidated | 20:43:56.035671–20:50:30.134848 | 2 failed, 267 passed, 4 skipped / 392.99 s; 394.0986368 s |
| `native-retention-red` / native root regression | 20:49:48.119048–20:49:49.748588 | 3 failed, 44 deselected / 0.69 s; 1.6294457 s |
| `native-retention-green` / misplaced test-tail, not a pass | 20:50:39.197560–20:50:40.523492 | 3 failed, 44 deselected / 0.66 s; 1.3258487 s |
| `all-root-regressions-green` / final artifact | 20:51:17.306517–20:51:43.227454 | 11 passed, 83 deselected / 24.13 s; 25.9208277 s |
| `combined-fixed` / final artifact combined | 20:52:08.209628–20:55:43.126703 | 272 passed, 4 skipped / 213.82 s; 214.9167386 s |
| `poll-final` / deliberate four-reader saturation | 20:54:06.102597–20:54:42.335065 | 1 failed, 1 passed, 22 deselected / 35.41 s; 36.2323544 s |
| `native-final` / actual NTFS locks, ACL, owned processes | 20:57:43.794150–20:58:00.918505 | 10 passed, 3 skipped / 16.38 s; 17.1242694 s |
| `full-final` / pre-merge final candidate | 20:56:36.093505–21:02:11.972004 | 1562 passed, 42 skipped / 335.34 s; 335.8780349 s |

These are historical concurrent probes, not independent samples:
`combined-fixed` overlaps the deliberately loading `poll-final`, and `full-final`
overlaps `native-final`. The later merged-head final runtime/web and full-suite
confirmations were run sequentially and are recorded separately below.

Exact selectors:

```text
isolated-before --probe hedge_fund\web\test_jobs.py -k "reviewed_operation_preview_accept or reviewed_backtest_cancellation"
combined-before --probe hedge_fund\runtime hedge_fund\tui hedge_fund\backtesting hedge_fund\web
full-before --probe hedge_fund
diagnostics-red hedge_fund\web\test_jobs.py -k worker_failures_log_safe_cause
poll-before --probe --poll-load hedge_fund\web\test_jobs.py -k "reviewed_operation_preview_accept or reviewed_backtest_cancellation"
starvation-red hedge_fund\runtime\test_admission.py -k cannot_be_overtaken
focused-green hedge_fund\runtime\test_admission.py hedge_fund\web\test_jobs.py -k "cannot_be_overtaken or worker_failures_log_safe_cause"
poll-after --probe --poll-load hedge_fund\web\test_jobs.py -k "reviewed_operation_preview_accept or reviewed_backtest_cancellation"
cache-experiment --probe --poll-load --cache-kernel32 hedge_fund\web\test_jobs.py -k "reviewed_operation_preview_accept or reviewed_backtest_cancellation"
harness-green hedge_fund\test_acceptance_isolation.py hedge_fund\web\test_jobs.py -k "acceptance_isolation or reviewed_operation_preview_accept or reviewed_backtest_cancellation or worker_failures_log_safe_cause"
cancellation-discrimination --probe --slow-model-update hedge_fund\web\test_jobs.py -k reviewed_backtest_cancellation
pause-red hedge_fund\web\test_jobs.py -k pause_requires_explicit_release
pause-green hedge_fund\web\test_jobs.py -k "pause_requires_explicit_release or reviewed_backtest_cancellation or worker_failures_log_safe_cause or persists_progress_and_result or cancellation_stops_at_boundary"
combined-confirmation hedge_fund\web hedge_fund\runtime\test_admission.py hedge_fund\runtime\test_operations.py hedge_fund\runtime\test_root.py hedge_fund\runtime\test_ownership.py hedge_fund\runtime\test_native_primitives.py hedge_fund\runtime\test_native_credentials.py hedge_fund\backtesting\test_research.py hedge_fund\tui\test_admission_regressions.py
native-retention-red hedge_fund\runtime\test_root.py -k retain_new_pointer_types
native-retention-green hedge_fund\runtime\test_root.py -k retain_new_pointer_types
all-root-regressions-green hedge_fund\runtime\test_root.py hedge_fund\runtime\test_admission.py hedge_fund\web\test_jobs.py -k "retain_new_pointer_types or cannot_be_overtaken or timed_out_local or reviewed_operation_preview_accept or reviewed_backtest_cancellation or pause_requires_explicit_release or worker_failures_log_safe_cause"
combined-fixed hedge_fund\web hedge_fund\runtime\test_admission.py hedge_fund\runtime\test_operations.py hedge_fund\runtime\test_root.py hedge_fund\runtime\test_ownership.py hedge_fund\runtime\test_native_primitives.py hedge_fund\runtime\test_native_credentials.py hedge_fund\backtesting\test_research.py hedge_fund\tui\test_admission_regressions.py
poll-final --probe --poll-load hedge_fund\web\test_jobs.py -k "reviewed_operation_preview_accept or reviewed_backtest_cancellation"
native-final hedge_fund\runtime\test_native_primitives.py hedge_fund\runtime\test_native_credentials.py -rs
full-final hedge_fund
```

Final harness SHA-256:
`9e3ebf9f5514468296bd118f67352082058bd58faa0cbfb7f6a25de3fb7e558e`.
`combined-fixed`, `poll-final`, `native-final` and final full confirmation use this
same harness and the final six-file diff/source identity above. No source edits
occur during these confirmation runs.
Harness wall is the timed pytest/cleanup portion; Python launch and pre-test
import/isolation setup are outside that measurement. It is not whole-command
PowerShell elapsed time.

Pre-merge full suite exit **0**: **1562 passed, 42 skipped in 335.34 s**. The
original 1553 non-skipped tests plus nine new parameterized regression cases
account for that historical count. Both originally requested symbols pass on
that pre-merge artifact. This result is superseded for publication by merged-head
confirmation.
One `PytestAssertRewriteWarning` for pre-imported AnyIO accompanies the safe
pre-import harness; it is not a test failure. No root guard, timeout, consent or
full-suite selector was weakened to obtain green. Pytest's cache plugin was
disabled and real provider network calls were blocked consistently in this safe
isolated harness, not selectively removed after a failing run.

The preceding statements describe the **pre-merge repair artifact only**. PR8's
merged source already contains the bounded 30-second, busy-only operation retry;
this follow-up did not raise that bound and uses it for the previously omitted
`apply_if_current` acquisition.

`native-final` observes actual NTFS file identity, cross-process lock exclusion,
atomic replacement/reader bytes, non-delete-sharing denial, root-handle binding,
owned-child process identity expiry, credential-version atomicity and private ACL
owner/inheritance. Its three skips are exactly Linux ext4 primitive verification,
Linux POSIX credential modes and Linux ext4 credential verification. These
Windows observations do not certify a new Linux/ext4 execution.

The first `full-before` harness configured two sibling synthetic roots, causing
the explicit synthetic dotenv positive test to fail closed through both wrappers.
This was a **harness defect**, not a repository repair. The corrected harness
imports `hedge_fund.conftest` once before application imports and reuses that
single marked root. Its acceptance-isolation suite passed in `harness-green`.
The original production modules and original test suite had already been imported
for `full-before`; later edits during that run do not make it final-artifact
confirmation. Both requested symbols passed in that original-runtime run.

One final-combined command selection accidentally named the unimplemented
`hedge_fund\runtime\test_processes.py`: **exit 4**, no tests run, **1.1563366 s**
wall, 20:43:10.165940–20:43:11.322356 UTC. It is not a pass. The corrected selection
uses the actual `test_ownership.py`.

## Portable safe reproduction without the local evidence harness

Run from this checkout with an existing environment containing project/test
dependencies. This uses repository isolation before importing application code:

```powershell
$py = 'C:\path\to\existing\environment\Scripts\python.exe'
$env:PYTHON_DOTENV_DISABLED='1'
$env:PYTHONDONTWRITEBYTECODE='1'
$env:PYTHONNOUSERSITE='1'
@'
from hedge_fund import conftest  # Single owned root before application imports.
import pytest
raise SystemExit(pytest.main([
    "hedge_fund\\runtime\\test_admission.py",
    "hedge_fund\\web\\test_jobs.py",
    "-p", "no:cacheprovider", "-q", "--tb=short",
]))
'@ | & $py -
```

For full confirmation, replace the two paths with `"hedge_fund"`. Do not enable
dotenv, real provider endpoints, paid consent or real-root arguments.

## Manifest, review and remaining risk

- `hedge_fund\runtime\admission.py`: bounded local FIFO; unchanged native authority.
- `hedge_fund\runtime\test_admission.py`: deterministic overtaking and timeout cleanup.
- `hedge_fund\runtime\root.py`: stable Windows native ABI identities; unchanged checks.
- `hedge_fund\runtime\test_root.py`: native retained-type regressions for three paths.
- `hedge_fund\runtime\ownership.py`: stable Windows process-time ABI identity.
- `hedge_fund\runtime\test_ownership.py`: current-process pointer-retention regression.
- `hedge_fund\web\jobs.py`: safe bounded failure metadata, unchanged public errors.
- `hedge_fund\web\test_jobs.py`: safe diagnostic regressions, persist-before-log
  contract, explicit fake release handshake and deterministic auto-expiry regression.
- This evidence file. Ignored `outputs` contain owned harnesses/raw synthetic
  evidence only, not shipped application or installed-package changes.

Pre-merge static style (historical): **PASS** on the then-changed six Python paths, without modifying source:
Black `--check` exit 0 (**1.609876 s**), isort `--check-only` exit 0
(**0.460119 s**), flake8 `--max-line-length=420 --extend-ignore=E203,W503` exit 0
(**2.703872 s**), `git diff --check` exit 0. The three tool processes used
`child_test_environment()` inside the single marked checkout-owned isolation root.
UTC window **20:55:26.910925–20:55:31.693347**, 2026-11-01;
raw output `outputs\job-static-final.log`. Static checks are not runtime evidence.
Native ABI fields and guard conditions are preserved, queue cleanup is explicitly
tested, and diagnostic records have no exception/frame attachments. The merged-head
static verification recorded in the current validation section applies to the
final repair files.

No installed-wheel, browser, production provider, real runner, bare-metal Linux
or current ext4 FIFO observation is claimed. Native fixture tests are distinguished
from actual production use. FIFO cannot make unbounded reader saturation cheap:
the deliberately excessive four-reader scenario exceeded the unchanged
twenty-second test observation window on the **intermediate** FIFO-only artifact.
The last recorded pre-merge saturation run also exceeded that observation window:
the preview remained running and was cooperatively cancelled by test cleanup.
That probe recorded **no acquisition failure or hidden worker exception**, only
expected `JobCancelled`; longest individual exclusive hold was **0.2193930 s**.
It has not been rerun with the merged 30-second busy retry, so it must not be
described as a current-head result.
This negative load scenario is not promoted to PASS or represented as evidence
that arbitrary monitoring pressure is supported. It is distinct from the now-green
representative combined suite and the eliminated retained-type growth.
Cross-process OS-lock fairness is still
the OS's responsibility; native locks/denials remain authoritative.

## Merged-head confirmation (current repair)

PR8's verified head before this integration was
`1fb15be7c3f6368e333e5fdb62cb26fc2ec6f269`. The worktree merge uses this commit
as `MERGE_HEAD`; no PR8 head advance was observed at the merge point. The
pre-merge rows above do not establish results for this combined artifact.

The original two inherited web-job failures did not retain their underlying
worker exceptions, so their exact historical trigger remains unattributed. The
current code-level defect was discriminated separately: the worker passed
`OperationStore.apply_if_current` directly to work callbacks, unlike other
durable store transitions. A bounded registry-lock timeout raised `OperationBusy`,
which escaped the work phase and was recorded as `worker-failed`. A regression
that raises `OperationBusy` before the callback first failed (`FAILED` rather
than `COMPLETED`); after the fix it passed by retrying before the effect. Its
paired test raises the same exception from inside the effect and verifies there
is no second effect attempt. The wrapper marks the effect as started before
invoking it, and `_retry_busy` retries this call only while that marker remains
false. The established bounded retry duration remains 30 seconds; no admission,
approval, cancellation or public error behavior was weakened.

Validation on Windows, Python 3.13.7 / pytest 7.4.4, with synthetic roots and
fake transports only. `PYTHON_DOTENV_DISABLED=1`; provider, credential, broker
and proxy environment variables were removed for pytest. No live provider,
paid, broker or runner operation was made.

| Validation | Result |
| --- | --- |
| New regression before fix | **1 failed, 1 passed, 34 deselected in 3.76 s**, exit 1; the pre-effect busy case persisted `FAILED`. |
| Final focused job regressions | **4 passed, 32 deselected in 21.11 s**, exit 0; UTC `2026-11-02T09:52:41.5786857Z`–`2026-11-02T09:53:05.0157623Z`. Selector: `hedge_fund/web/test_jobs.py -k 'busy_apply_if_current_retries_before_effect or busy_from_apply_if_current_effect_is_not_retried or reviewed_operation_preview_accept or reviewed_backtest_cancellation'`. |
| YFinance mocked client tests after environment repair | **79 passed in 0.19 s**, exit 0; UTC `2026-11-02T09:53:05.0285965Z`–`2026-11-02T09:53:07.1069339Z`. |
| Combined `hedge_fund/runtime hedge_fund/web` | **482 passed, 4 skipped in 474.59 s**, exit 0; UTC `2026-11-02T09:53:07.1069339Z`–`2026-11-02T10:01:04.0439346Z`. |
| Final full suite, first attempt | **1 failed, 1656 passed, 42 skipped in 543.51 s**, exit 1; UTC `2026-11-02T09:26:18.8376407Z`–`2026-11-02T09:35:24.6598171Z`. `test_archive_interruption_is_explicitly_recoverable` encountered Windows `PermissionError [WinError 5]` during the unrelated native directory rename; the exact test passed alone in 1.98 s. This single failure is not attributed to the repair and the isolated pass is not considered resolution. |
| Final full suite, confirmation | **1657 passed, 42 skipped in 593.22 s**, exit 0; UTC `2026-11-02T10:01:16.8652921Z`–`2026-11-02T10:11:12.2579461Z`. Command: `python -m pytest -q --disable-warnings --tb=short`. |

The initial merged-artifact full-suite attempt before dependency repair was not
valid test evidence: **64 failed, 1590 passed, 43 skipped**; all 64
`test_yfinance_client.py` cases failed because the existing test interpreter
lacked required, lockfile-pinned yfinance packages
(`yfinance`, `curl_cffi`, Beautiful Soup, lxml, multitasking, peewee and
SoupSieve). Their cached wheel hashes were checked against `poetry.lock` and
installed offline without dependency or manifest changes. `pip check` then
reported no broken requirements; the 79-test mocked YFinance module passed
without network access.

The final repair's eight focused Python source/test files have these exact
working-byte SHA-256 values:

| Path | SHA-256 |
| --- | --- |
| `hedge_fund/runtime/admission.py` | `7d4085166f17272d7207eab974177fd73764cc04d502cfa7ccbced14150cd00e` |
| `hedge_fund/runtime/test_admission.py` | `8fcc54404b72cb29de9fc3b32ffcdc837c80a11c3fd3314f202b36908857da7e` |
| `hedge_fund/runtime/root.py` | `4ca9239d86c8908c705b23023d0691c75f3b53df6f3679263b6412f305861f6c` |
| `hedge_fund/runtime/test_root.py` | `ea774aef573945dbce2429b85c2ad3c49079a06f5d0d95b4eff2a6c95d045b69` |
| `hedge_fund/runtime/ownership.py` | `bb0b60f760c81bbc58ecb3bf1bf7f7634a0dbcacf36bfe75cb783b7d66cee9b4` |
| `hedge_fund/runtime/test_ownership.py` | `9917d5145204d6618844aa9670aac4944c2ef8d5d1767d93460727a9c5b68bb8` |
| `hedge_fund/web/jobs.py` | `d387f7c78d53ee857d8a9c2b7c086c0b52230bd04733a9de3b806bd2abf21903` |
| `hedge_fund/web/test_jobs.py` | `d16df82d6e56024a675121afc9a5cf6e3cbacf599fa865b0b3b50ccf35de8acb` |

Complete merged source/test identity: **284 tracked paths**, covering all files
under `hedge_fund/` and `frontend/`, plus `pyproject.toml` and `poetry.lock`;
paths are Git-sorted and the SHA-256 digest incorporates each UTF-8 path, NUL,
exact working bytes and NUL. Digest:
`492e8c39edae09777ced371a8e0c7ee9895db94856de18e9491828f3748ccdce`. This binds
the final full-suite source, including merged PR8 files such as `web/services.py`;
only this evidence markdown changed after that run.

Final scoped static verification on those same eight paths: Black
`--check`, isort `--check-only`, and flake8
`--max-line-length=420 --extend-ignore=E203,W503` all exited 0; whole staged
plus unstaged `git diff --check HEAD --` exited 0. No source was modified by
these checks.

Merged-head pytest used the existing Poetry interpreter
`C:\Users\ChristianGjedrem\AppData\Local\pypoetry\Cache\virtualenvs\aihf-Tbl0PwyA-py3.13\Scripts\python.exe`.
Before pytest, a PowerShell loop removed inherited environment variables whose
names matched `(?i)(API[_-]?KEY|TOKEN|SECRET|PROVIDER|BROKER|PROXY)`, then set
`PYTHON_DOTENV_DISABLED=1` and `PYTHONDONTWRITEBYTECODE=1`. The focus selector,
mocked Yahoo tests and combined runtime/web suite above used this same isolation.
The full suite also passed once earlier at `09:36:43Z`–`09:46:24Z`
(1657 passed, 42 skipped); the later final run confirms the test-helper-only
change and is the current evidence.

Final independent QA: **PASS, no blocking findings**. The reviewer verified the
pre-effect-only retry, the no-retry-from-effect regression, FIFO/native safety
and redacted diagnostics by source inspection. The reviewer did not execute
tests or verify hashes; test and hash rows above are execution-owner evidence.
The exact historical worker exceptions from the two inherited failures remain
unavailable, so the defect fixed here is the reproduced code-level failure
class, not a proven attribution of both old failures.

These results complete only the durable-job failure repair slice. Spec005
remains **20/148 tasks complete**; no migration-wide, production, browser,
installed-artifact or bare-metal Linux acceptance is implied. Deliberate
four-reader saturation has not been rerun with the merged 30-second busy retry
and remains an unaccepted load scenario.
