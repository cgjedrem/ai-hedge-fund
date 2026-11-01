# QA2 Direct-Writer Findings Disposition — 2026-11-01

## Evidence identity

- Base revision: `865429c0d1a64e4b15e1b55361f6c96f4fb6af36`, branch `cgjedrem-vigilant-robot`.
- Current source/test dirty-diff identity: SHA-256 `0748800c49f610e48de174356ac90381b8df9cbd173e2bf72a412c775e8f2352`; 40 tracked source/test paths / 280,850 binary diff bytes plus 10 untracked source/test files. Hash input uses length-prefixed `git diff --binary --full-index HEAD` plus sorted untracked path/content records.
- Current source/test snapshot: 50 changed source/test paths / 1,131,093 bytes, SHA-256 `4f482e6e789aea5b966f30eb8542f2740de2a9b9c4738eaa7141aa7b17ec9a4e`.
- Evidence collection: `2026-11-01T07:16:36.2950172+01:00` → `07:16:36.6667427+01:00`; Windows 11 Enterprise build 26200, C: NTFS. Exact final test timestamps, commands and durations are recorded in `implementation-evidence.md`.
- QA2 source: user-provided summary of the second QA review. No independent QA2 review was run for this disposition; this report is implementation-owner follow-up, not a QA sign-off.

## Findings and disposition

### C1 — web writes admitted without explicit root enrollment

**Reported blocker:** `DeskService` treated an existing root as write-capable when the owner lease could be acquired; lease presence alone did not prove offline handover.

**Disposition:** current `hedge_fund/web/services.py` requires valid enrolled-root status with inventory verification, explicit write capability, and the shared participant lease before enabling web writes. Web routes do not enroll roots. `hedge_fund/web/demo.py` enrolls only an empty explicit demo root before seed writes. Fresh enrollment rejects nonempty roots; migration requires exact inventory digest and operator attestation, and refuses every `runner.pid`.

**Evidence:** `hedge_fund/runtime/handover.py`, `hedge_fund/runtime/test_handover.py`, `hedge_fund/web/test_services.py`, `hedge_fund/web/test_paper_operations.py`; final focused backend slice **99 passed in 52.62 s**. Actual enrollment functions run in tests; no mocked enrollment flag substitutes for enrollment.

**Residual:** an attestation records operator exclusion; it does not OS-fence an unaware legacy binary or an out-of-band writer. T015 remains partial. Do not treat an enrolled marker as proof that an external writer is stopped.

### C2 — same-build paper writers bypass shared admission

**Reported blocker:** CLI, runner, tick and TUI paths did not use a common admission protocol, permitting same-build concurrent ledger writers.

**Disposition:** enrolled CLI create/deploy, tick/redo, approval, halt and resume paths use the relevant per-fund deployment, manual-session or bounded-control lane, or deny before effects. `hedge_fund/paper/tick.py` verifies inventory before mutation; legacy `hedge_fund/paper/runner.py` entrypoints deny enrolled roots; TUI paper mutations fail closed without admission. Web paper operations use the same root and per-fund lanes. Tests cover exclusive migration versus shared participants, runner/manual conflicts, independent funds, stale-head rejection, drift denial before data access, bounded stop/control, and no duplicate append.

**Evidence:** `hedge_fund/runtime/admission.py`, `hedge_fund/runtime/test_admission.py`, `hedge_fund/paper/{deployed.py,ledger.py,runner.py,tick.py}`, `hedge_fund/test_run.py`, `hedge_fund/tui/paper.py`, `hedge_fund/web/services.py`; focused backend slice **99 passed in 52.62 s**, CLI selection **17 passed / 24 deselected in 7.66 s**, web boundary/actions/settings **45 passed in 41.32 s**, TUI paper controls **28 passed in 16.64 s**.

**Residual:** `hedge_fund/fund/storage.py` and `hedge_fund/backtesting/research.py` are not integrated. Some low-level `Ledger` mutation methods rely on top-level inventory/admission preflight. There is no exhaustive writer-race matrix covering every direct caller, archive path or out-of-band process. T021 remains partial; the code does not establish that every same-build or external writer is fenced.

### C3 — implementation-owner self-review: orphan admission state without handover

**Finding:** self-review found that missing `handover.json` with leftover private owner/admission artifacts could be treated as genuinely unenrolled. The legacy runner and TUI deletion path could then remain writable.

**Disposition:** `enrollment_status()` reports invalid when the handover is absent but owner/admission artifacts exist or cannot be verified. CLI writer admission, the legacy runner and TUI deletion deny before effects. Explicit offline `handover inspect` can inventory the state under the migration lock for deliberate recovery.

**Evidence:** expected-red regression set **4 failed in 1.65 s**; focused orphan/recovery regressions after repair **18 passed in 4.99 s**. Exact wall-clock timestamps for these two runs were not retained; final backend slice, CLI selection and TUI tests above have timed evidence. This was implementation-owner self-review, not a QA2 assertion or independent review.

### I1 — deployment admission

Enrolled deployment paths acquire a per-fund deployment lane; handover-head updates use the registry lane. Cross-process synthetic Windows/NTFS lock tests cover deployment/manual conflict. This is a scoped implementation result, not Linux/ext4 acceptance.

### I2 — shared root participation and migration exclusion

`RootOwnerLease` is shared among participating processes; `RootMigrationLease` is exclusive during offline enrollment. Acquisition failure closes/releases the held OS resource. Tests cover shared/exclusive conflict and no lease leak on copied/malformed record rejection. Neither lock coordinates an unaware legacy binary or external writer.

## User-visible write state and shutdown correction

- `frontend/src/pages/paper.tsx` displays enrollment state and `write_unavailable_reason`; write controls are disabled when capability is absent. The stopped-runner badge is not green. Vitest reported **19 tests passed**, but its wall-clock timestamp was not retained and its formal evidence row is **INCONCLUSIVE**. Owned browser E2E passed **10 tests** using fake API routes. Browser results do not prove backend manual/runner execution.
- `OperationJobRegistry.close()` persists durable cancellation requests before exposing local shutdown. Earlier failures observed `INTERRUPTED` instead of `CANCELLED` and a test-barrier race where completion could beat persisted cancellation. The test now waits for `original_request_cancel()` to return before releasing the worker. Final full `hedge_fund/web/test_jobs.py`: **18 passed in 66.55 s**; final targeted regression: **1 passed, 17 deselected in 3.79 s**.

## Acceptance boundary

**T018 PASS for implementation/test criteria only. T015/T021 PARTIAL.** Manual tick and owned-runner paths were tested with synthetic roots, fake/local analysts and bounded owned-child controls. Browser build/E2E: Vite transformed **2,307 modules**, **23.12 s**, bundle SHA-256 `787e53b0bc4fc9b6017456a9f8057c0662a2ca86e7975cf10846f3f4f3303171`; Playwright **10 passed in 18.9 s** using fake API routes, not backend mutation. No paid provider call or unknown-process signal was made. Owned root `outputs/spec005-test-e2e-53280-a11fedad` and exact server PID `54196` were absent; bind to `127.0.0.1:8876` succeeded. The full Python suite remains **INCONCLUSIVE**. Linux/ext4 and actual NTFS DACL enforcement are **BLOCKED**; no final wheel/container artifact was built. Existing-root deployment, stale-reservation recovery, unaware-writer exclusion, TUI retirement and broader US1 acceptance remain open.

See `implementation-evidence.md` for exact commands, test durations, artifact/screenshot hashes, environment and evidence limitations. Keep T015/T021 unchecked until their remaining source integration and native/exclusion evidence exist.
