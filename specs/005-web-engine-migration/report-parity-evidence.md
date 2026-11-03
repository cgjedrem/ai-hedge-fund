# Bounded read-only session-report parity evidence

## Scope and provenance

This slice is based on published PR8 source
`5f3f909c4f9151d531b571dd37bdebe368ee127c`, verified against GitHub and the remote head
before implementation, with the remote head rechecked at 2026-11-02T23:24:52Z. It adds no trading, sizing,
valuation, scorecard or risk computation. TUI code, writer/admission/runner/lifecycle
implementation, approval/source-hash/CSRF policy, dependencies and live roots are unchanged.
The isolated branch is `cgjedrem-report-clamp-parity`; the resulting commit and any later
publication are identified separately in the final handoff.

The verified persisted-data gap was the omission of proposed decision clamps from the
web projection, alongside a UI column that called post-risk weights "Target weight".
The bounded implementation now:

- Projects stored proposed clamps, mandate limits and risk scale factor, separately from
  recorded execution clamps/limits.
- Labels requested pre-risk and final post-risk weights explicitly, including signed values,
  absent map entries and distinct missing-decision versus empty-clamp states.
- Provides keyboard-scrollable risk/weight tables and a native, keyboard-accessible
  canonical JSON download bound to the displayed record hash.

The implemented routes and error semantics are recorded in
`contracts\runtime-api.md`. Export uses the exact `SessionRecord` captured by successful
full ledger replay and its existing `model_dump_json(indent=2)` serializer. It is not the
presentation projection, and the browser does not parse/rebuild the authoritative JSON.
Byte equality is proved for the canonical synthetic persisted serialization, not arbitrary
historical JSON whitespace layouts.

## Reproducible synthetic acceptance

From `frontend`, run:

```powershell
$env:AIHF_E2E_PYTHON='<existing complete Python interpreter>'
node .\e2e\run-owned.mjs --reports reports.spec.ts
```

The checked-in report mode prepares the entire owned fixture before starting a non-demo,
read-only server on 127.0.0.1:8876. It refuses an occupied port, never reuses another server,
cannot combine with lifecycle-write acceptance, and scrubs inherited fixture selectors.
Existing isolation helpers relocate HOME/USERPROFILE/TEMP, remove provider/credential/proxy
settings, disable dotenv and deny nonloopback access. Preparation is confined to admitted
synthetic roots; observation does not claim write authority.

`seed_clamped_report()` pins stored `code_version` to `report-parity-synthetic-v1` and
recomputes the synthetic chain. Its proposed AAPL position changes from 0.4 to 0.25 while
MSFT remains -0.125. Persisted position/gross limits are 0.25/1.0. Inert malicious reasoning
is rendered as text. Browser tests use the real API; request routing only denies external
access and never fulfills API data. The download is compared with the preseeded canonical
file bytes. A second test verifies contained keyboard scrolling at a 360-pixel viewport.

The final run's full file-path/content tree SHA-256 was
`745646c6606d8bfe7d9fc5ac3cdbf9617dd147ce5e0418cb822bc012fc03418b`
before and after browser reads. The owned server PID was 10916; the runner released 8876
and removed its owned fixture before exiting successfully. No creator 8765 or old 49292
preview was contacted or stopped.

## Final runtime/test source receipt

Normalized source SHA-256:
`903fb19d5f1d03ce04b5f721a573d15475b876d7b4c22d8bcb5d1ce48ac479e7`.

For each path below in order, hash its slash-normalized relative path, NUL, UTF-8 content
with CRLF normalized to LF, then NUL. This covers all eleven changed runtime/test source
files. Documentation is excluded to avoid self-reference; unchanged inherited source is
bound by the base commit above.

```text
frontend\e2e\reports.spec.ts
frontend\e2e\run-owned.mjs
frontend\playwright.config.ts
frontend\scripts\run-owned.test.mjs
frontend\src\App.test.tsx
frontend\src\lib\types.ts
frontend\src\pages\paper.test.tsx
frontend\src\pages\paper.tsx
hedge_fund\web\app.py
hedge_fund\web\services.py
hedge_fund\web\test_reports.py
```

All final checks below used that same source receipt. Timestamps are UTC.
Python was 3.13.7 and Node was v22.13.1; the existing complete virtualenv was reused without
modifying it. Missing frontend dependencies were restored from the local offline npm cache
with install scripts disabled; manifests/lockfiles were not changed.

| Check | Start | End | Result |
|---|---|---|---|
| Report/API/service/console pytest selection | 2026-11-02T23:30:45.168Z | 2026-11-02T23:34:41.559Z | 99 passed |
| Full frontend Vitest source suite | 2026-11-02T23:30:45.180Z | 2026-11-02T23:31:40.361Z | 112 passed, 8 files |
| Owned report browser, TypeScript and production build | 2026-11-02T23:30:45.164Z | 2026-11-02T23:31:42.701Z | 2 browser tests passed; tsc/build passed |
| Owned-harness Node safety tests | 2026-11-02T23:30:45.235Z | 2026-11-02T23:30:46.676Z | 8 passed |
| Black check | 2026-11-02T23:30:45.217Z | 2026-11-02T23:30:48.204Z | 3 files unchanged |
| Isort check | 2026-11-02T23:30:49.246Z | 2026-11-02T23:30:49.986Z | passed |
| Full configured Flake8 on touched Python files | 2026-11-02T23:30:51.044Z | 2026-11-02T23:30:54.113Z | passed |

The backend selectors were `hedge_fund\web\test_reports.py`, `test_app.py`,
`test_services.py` and `hedge_fund\reporting\test_console.py`. Frontend selection was
`vitest run src --maxWorkers=1 --testTimeout=30000`; safety selection was
`node --test scripts\run-owned.test.mjs`. Python checks used the existing fail-closed
network/test-root environment through the retained session `report-check.mjs` wrapper.
Style used `black --check`, `isort --check-only`, and
`flake8 --max-line-length=420 --extend-ignore=E203,W503` on the three changed Python files.
`git diff --check` also passed.

`runFrontendBuild()` runs `tsc --noEmit` before Vite. Production artifact SHA-256:
`5a0726a66473ae7c1eba0db37e0a2dc6f7ac36c82b59429297960967c930b357`
(three files, 1,017,394 bytes). Vite 6.4.5 emitted the existing nonfatal >500 kB chunk
warning; no warning suppression or bundle-splitting change was introduced.

Final desktop/mobile screenshots are retained in the isolated worktree's
`screenshots` directory and copied to session evidence, not shipped as runtime assets:

| Screenshot | SHA-256 |
|---|---|
| `report-clamps-desktop.png` | `e9fe5c90e1883cd909b07adcaa94c0c8cfe12571a316c46fe167a89b08c01c78` |
| `report-clamps-mobile.png` | `5ab5f8bd59a54bc3ff08aca1a755e660c8ad9089f9a2bb29c11fce73f059ffe9` |

## Independent review and failure disposition

The initial read-only `code-review` was blocked by two Important findings:

1. A replay-identity regression monkeypatched ledger reads before app startup, allowing
   startup inventory verification to consume the first read. App construction now precedes
   the patch; the discriminating backend regression and final selection pass.
2. The checked-in browser runner did not select a preseeded clamped fixture. The new
   checked-in `--reports` mode, selector-scrubbing safety regressions and populated real-API
   browser proof resolve this. The initial session-only browser attempt passed assertions
   but failed immediate port cleanup and is explicitly not accepted evidence.

The initial backend batch also exposed an unchanged console-import test failure caused
by using `-S` in the temporary parent wrapper on Python 3.13: nested guarded children derived
base-interpreter rather than virtualenv site-packages and could not import installed Rich.
Normal virtualenv startup with the existing fail-closed `sitecustomize` guard resolves it.
No repository isolation mechanism was weakened. Subsequent Black/isort-only formatting was
followed by the final source-bound checks above.

Final independent read-only `code-review` approved this bounded source with no significant
findings and independently reproduced the eleven-file source hash. Both initial findings
were confirmed resolved at `test_reports.py:126-138` and `run-owned.mjs:586-598`.
This is static approval, not independently rerun test evidence, GitHub approval, merge
authorization, or permission to publish to another child's branch. Initial/final review
reports and exact final check logs are retained as session evidence.

## Integration onto the T145 settings-provenance head

The sections above are pre-T145 evidence for original commit
`5441dcd314c946d941d791bd1983809fa582cf27` (child of `5f3f909`) and are not inherited as
integration acceptance. The slice was re-applied as a new child of PR8 head
`07f6d8bdb2540db38d113eb62c9993a0736e1c19` (settings configuration provenance, T145
partial), verified locally and against GitHub PR8 `headRefOid` at 2026-11-02T23:54Z.
The original commit object was verified locally; no other branch or worktree was modified.

`git cherry-pick --no-commit 5441dcd` auto-merged `App.test.tsx`, `types.ts` and
`services.py` without textual conflicts; `tasks.md` and this evidence file were not touched
by the settings commit. Semantic review confirmed T145 settings provenance types, fixtures,
service methods and routes are unchanged, and the report's `SessionReport` fixture fields
are additive. No manual conflict resolution was required.

Integrated eleven-file source SHA-256 (same algorithm; reproduced `903fb19…` for the
original commit before use):
`b807fef3063cb6960e62c6072d8a75c4370586c10eb7b4f156da586c6b6cb9a0`.

Locked dependencies were restored only into this isolated worktree (`poetry install` with
an in-project `.venv`, `npm ci`); manifests/lockfiles unchanged. Python 3.13.7, Node
v22.13.1. Checks ran with credential/provider/proxy variables scrubbed and dotenv disabled,
plus the repository's fail-closed test isolation. Timestamps are UTC.

| Check | Start | End | Result |
|---|---|---|---|
| Report+settings/API/service/console pytest | 2026-11-02T23:56:22Z | 2026-11-03T00:02:01Z | 106 passed |
| Full frontend Vitest source suite | 2026-11-02T23:56:22Z | 2026-11-02T23:57:57Z | 119 passed, 9 files |
| Owned-harness Node safety tests (sequential after Vitest, same shell) | after Vitest | 2026-11-02T23:57:57Z | 8 passed |
| Owned report browser (`--reports`), tsc+Vite build | 2026-11-02T23:58:01Z | 2026-11-02T23:58:47Z | 2 passed |
| Standalone `tsc --noEmit` | 2026-11-02T23:58:54Z | 2026-11-02T23:59:05Z | passed |
| Black/isort/Flake8 on three Python files, `git diff --check` | 2026-11-02T23:56:34Z | 2026-11-02T23:56:40Z | passed |

Backend selectors: `hedge_fund\web\test_reports.py`, `test_settings_provenance.py`,
`test_app.py`, `test_services.py`, `hedge_fund\reporting\test_console.py`.
Production artifact SHA-256 `94ed54b9c4df269e99879b2849e73f4bb3c00b1db3f0bc6e2fb7b596647673fc`
(three files, 1,025,450 bytes; includes T145 settings UI). Browser read-only fixture tree
SHA-256 `be289330f245bc14e844d9f5b03621edc1772e93f38fa4ac1ce63e2f5fc72c36` unchanged before
and after reads; server PID 28488 on 127.0.0.1:8876, released afterwards. Screenshots
(gitignored): `report-clamps-desktop.png`
`e9fe5c90e1883cd909b07adcaa94c0c8cfe12571a316c46fe167a89b08c01c78` (identical to pre-T145),
`report-clamps-mobile.png` `4449576bc90fe47078d29f4ee00e882b130c648857d93a4d4a5310fce5553dc5`.
Vite's existing nonfatal >500 kB chunk warning remains.

Independent read-only `code-review` of the staged integration reported no significant
findings (route shadowing, safe-GET/CSRF, stale-hash 409, fixture typing, import reorders).
It observed `hedge_fund\web\test_actions.py::test_web_halt_does_not_wait_for_fund_work_lock`
failing; it also fails on unmodified `07f6d8b` (2026-11-03T00:04:31Z), so it is a
pre-existing, out-of-scope timing failure, not accepted or repaired here. Ports 8765 and
49292, real funds, runners, Watchtower, providers, LLMs, brokers and secrets were not used.

## Remaining scope

This is partial T111/T112/T113/T119/T122/T146 evidence only. All report/story checkboxes
remain unchecked and the Spec005 task total remains 20/148. Research scorecards/drilldowns,
full allocation/book/orders/fills/tape detail, every report format/headless export criterion,
full Python/platform/package/retirement acceptance, and the complete React migration remain
open. No external provider, paid model, broker or live-runner validation was performed or
claimed. PR8 remains open; there is no duplicate PR, merge or cross-session branch edit.
