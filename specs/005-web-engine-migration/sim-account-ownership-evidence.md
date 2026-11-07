# SIM account ownership: bounded fail-closed evidence

**Disposition:** incoming T096 fake-policy checkbox retained; T099, production
ownership and migration acceptance remain incomplete. PR8's actual current task
count is **21/148**; this integration completes no additional task.

## Verified starting source and decision

- PR8 was open on `cgjedrem-vigilant-robot` at
  `16369e9ee93801a2ef7abcd3b02604f1c3b12866`; REST/CLI PR inspection,
  `git ls-remote`, fetch and local HEAD agreed at
  `2026-11-03T01:14:22.3003536+01:00`.
- This slice started from a clean dedicated worktree at that commit. No prior
  implementation or progress from an unpublished ownership branch is claimed.
- User direction explicitly permits permanent fail-closed unsupported identity
  when global account-control proof is impossible.
- `RootContext` has private-storage and canonical I/O primitives, and
  `handover.write_authority` classifies root authority. Neither proves complete
  cross-root inventory or excludes manually configured/out-of-band Saxo clients.
  A3 is not waived by enrollment, ACLs, locks or operator attestation.
- PR8 advanced during work to `294f9db8e943c16bb45185acfece0f97daa60028`,
  verified at `2026-11-03T01:51:40.9240002+01:00`. That commit independently
  added the same-path fake HMAC registry/tests and checked T096. Both bodies of
  work were preserved, and the unpublished tracked guards were rebased with
  autostash onto that head at `2026-11-03T01:56:22.1748035+01:00`.
  The production guard tests now live in adjacent `test_account_binding_guards.py`;
  the incoming policy tests remain in `test_account_binding.py`. No forced
  publication or prior-progress claim is made.
- PR8 advanced again to `b36da7107700332d99a4cfccc8dfeb2d4a159aa7`,
  with REST PR head and remote ref agreeing at
  `2026-11-03T02:23:27.8597492+01:00`. The incoming recorded-session-day/
  operation-coordination/data-default/legacy-backtest changes did not collide
  with this slice. Autostash integration completed at
  `2026-11-03T02:24:29.5962246+01:00`; incoming TUI changes are preserved,
  not attributed to or extended by this task.
- A third REST/ref check at `2026-11-03T03:08:53+01:00` agreed on
  `042cfbc47b4a7221f0359a129767a26b48cd71a1`. Its incoming capacity,
  restart-provenance and owned-runner-reattachment work affected 33 files,
  including production runtime modules. That work is preserved, not authored
  by this slice. Autostash integration completed at
  `2026-11-03T03:10:34.4514244+01:00`; no slice files collided.
  The older full Python run, started at
  `2026-11-03T02:51:03.5309096+01:00`, was explicitly canceled before
  that integration, after progress reached 80%. It has no final pass count
  or successful exit and is not full-suite evidence. Its partial raw log
  remains `files/sim-full-python.log`.
- PR8 next advanced to `9c5f49165ec172e6605ac5c4b8dadf6b167f2d62`,
  adding owned test-harness/frontend evidence, including Windows asyncio
  proactor socket denial. Autostash integration completed at
  `2026-11-03T03:38:09.3889558+01:00`; the 16 authored Python hashes
  were unchanged by this integration. The `042cfbc` full run was canceled
  without a passing result (`files/sim-full-final.log`).
- The next open/unmerged PR head was
  `b6a8a5b2086ebba1fe7cce7c82b943b49eeb5a8a`, read at
  `2026-11-03T03:48:54.9075674+01:00`. Incoming T021 authority-recheck,
  writer-map and race/unlink work affected 15 files. Integration completed
  at `2026-11-03T03:51:04.7542486+01:00`, preserving its deployment/tick
  effects and this slice's early ownership guards. The intervening combined
  selection started at `2026-11-03T03:44:54.5472309+01:00` on `9c5f491`
  and was canceled after 50% progress; `files/sim-focused-integration-9c5.log`
  has no final passing count. Its conditional full-suite stage has no verified
  start. Neither canceled run is substituted for current validation.

## Implemented and deliberately unsupported

`SIMAccountRegistry.inspect()` returns a typed redacted unavailable-authority
view. Bind/release/transfer and the shared ownership requirement always raise
`SIMOwnershipUnknown` (`OwnershipUnknown`, code `ownership-unknown`).
This production seam creates or trusts no identities, account hashes, keys,
registry files, or release/transfer records. No provider/global account lookup is
attempted. It has no environment, caller-proof or fake-dependency bypass.

The distinct incoming `AccountRegistry` policy simulation retains its random
32-byte private HMAC key, canonical atomic state, private-storage checks,
root/deployment/runner admission, duplicate exclusion and explicit release/
transfer provenance. Access now requires the canonical checkout-owned synthetic
test namespace through the existing isolation validators. Custom custody and
quiescence callbacks cannot enable ordinary registry initialization, reads or
mutation. This confinement is not global proof, and no simulated receipt grants
production binding, provisioning or execution. No raw account identity is stored.
Untrusted environment repr and custody-denial reasons are redacted. Every
simulation receipt/view is explicitly `policy_only: true` and reports global
custody as `ownership-unknown`, including positive fake-policy results.
Namespace validation does not itself install or attest a socket network guard.
Callbacks are trusted fake-policy inputs, never provider/account-control proof;
the pytest harness separately installs non-loopback denial. Historical adapter
fixture helpers additionally require the installed guard marker.

Factory construction, deployment and both public/headless OAuth entries deny
before credential/environment access or mutation. Local-paper construction and
deployment remain supported. Historical SIM snapshots remain readable; lower-level
adapter/reconciliation/cutoff behavior is exercised with isolated fakes, not
admitted SIM ownership or successful provisioning.
Review-driven guards also reject CLI SIM create/tick/replay/approve-now before root writer admission,
preserving `ownership-unknown` instead of relabelling it as lock contention, and
reject a library SIM tick under its existing admission before constructing the
ledger or consuming/journalling controls.
The existing public legacy runner entrypoints already deny unconditionally;
their private fake-loop algorithm coverage is preserved, not runner authorization.
Plain CLI approve/reject still record admitted local verdicts on historical SIM
records. TUI verdict writes are denied by `paper_write_denial()` in every root state.
CLI verdicts grant no account authority or execution permission;
complete ownership-gated SIM control parity remains T070/T099 work.

The prior positive OAuth assertions (PKCE challenge/method/verifier, registered
redirect equivalence, callback state/path validation, and refresh-lock-protected
token write-back) no longer execute because provisioning is deliberately disabled.
They are not retirement/ownership acceptance and need restoring if a defensible
provisioning authority is introduced. Current tests assert no browser, prompt,
lock, exchange or token write-back instead. Secret-reference non-disclosure now
checks supplied sentinels are not echoed, not a reference-reading redaction path.

Production root, admission, handover, ledger and cache modules are unchanged
by this slice relative to the integrated published base; incoming changes to
those modules are preserved and are not attributed to this work.
One existing `runtime/test_write_authority.py` fixture now seeds historical SIM
records through a test-only helper because production SIM deployment is denied.
The helper requires test-owned paths and an installed non-loopback network guard;
the fake broker helper rejects actual transport/secret-provider implementations.
This slice removes or changes no TUI files.

## Observed red-green behavior

The tool transcript records discriminating red before implementation at each
new public seam: factory read credential configuration; deploy created a snapshot;
OAuth opened the browser; headless OAuth read ambient credentials; registry bind,
inspection, release and transfer seams were missing. The corresponding green
runs passed after their bounded implementations.

Two harness limitations were observed, not hidden: the system interpreter lacked
`pandas`, so declared dependencies were restored into this worktree's ignored
`venv`; and Windows byte-range locks prevented reading an empty lock file during
snapshot comparison. The snapshot now records lock identity/size/mtime while
comparing all other file bytes. No production exception was suppressed.

An earlier ownership-module selection passed **17 tests** before integration, including:
unconditional denial in same-root/across-root repeated-account setups;
unknown/closed/unverifiable root denial without probes; unconditional denial
for live/real inputs; redacted errors and inspection; linked caller claims that
cannot enable the production seam (the claimed provenance is not read);
release denial both with and without an active reservation under actual
root/sorted deployment admission; unconditional denial under concurrent
transfer/replay calls without manufactured provenance; and zero
factory/OAuth/deploy effects. The production guard module has **19 cases**, including two
explicit-fake-dependency fallback regressions; fresh integrated results are recorded below.
These production cases exercise a permanently unsupported boundary, not a
duplicate, quiescence or replay-policy algorithm. The separate fake-policy
module provides the positive/negative policy coverage.

After the concurrent PR8 advance, eight discriminating confinement/redaction
cases failed on the incoming policy source: production-mode initialization/open/
inspection reached path reads; custom custody enabled bind/release without test
mode; an unverifiable test namespace reached path access; custody reasons and
environment repr echoed fake account sentinels. At
`2026-11-03T02:02:01.6835262+01:00` to `02:02:18.8383840+01:00`,
the result was **8 failed, 42 deselected in 12.38 seconds**, exit 1, artifact
`files/sim-registry-confinement-red.log`. The earlier three-case gate run is
`files/sim-registry-gate-red.log`. No real provider or credentials were used.

The first integrated selection at `2026-11-03T02:08:20.8079949+01:00` to
`02:11:10.8960438+01:00` recorded **77 passed, 1 failed in 166.38 seconds**,
exit 1 (`files/sim-integrated-focused.log`). The failure was an overstrict
fixture snapshot: existing execution admission legitimately creates
`.paper-execution.lock` before the confined library guard. The fixture now
acquires/releases that real admission before its baseline snapshot rather than
moving the guard ahead of confinement or hiding arbitrary file changes.

CLI execution fixtures initially hit two existing safety gates: broker-backed
legacy relocation is forbidden, and enrolled ledger initialization requires
held admission. Those failures are preserved in `files/sim-cli-execution-red.log`
and `files/sim-cli-execution-red-boundary.log`; neither is claimed as a
discriminating boundary red. The fixture now enrolls first and creates its
historical fake SIM snapshot under real deployment admission and an exact
published inventory transition. At `2026-11-03T02:18:55.0905378+01:00` to
`02:19:10.8600772+01:00`, all three tick/replay/approve-now cases then failed
at forbidden admission/ledger setup (**3 failed in 8.92 seconds**, exit 1,
`files/sim-cli-execution-red-admitted.log`). The shared CLI guard now denies
before those stages, including the internal CLI tick helper.

The CLI/library correction selection passed at
`2026-11-03T02:21:48.5773077+01:00` to `02:21:58.0409505+01:00`:
**5 passed in 6.47 seconds**, exit 0, with Black 420/isort/flake8/diff checks
passing for 16 Python files (`files/sim-cli-tick-green.log`). This predates the
second rebase and is not inherited as final-source validation.

The explicit policy-only/global-custody output-shape regression was observed
red at `2026-11-03T02:27:42.2240878+01:00` to
`02:27:54.3866100+01:00`: **1 failed in 7.40 seconds**, exit 1,
`files/sim-global-custody-shape-red.log`. Public simulated results now carry
the required qualifiers rather than presenting an unqualified active binding.

## Timed focused integration evidence

Command (dotenv off, plugin autoload off, repository isolation conftest):

```powershell
.\venv\Scripts\python.exe -m pytest hedge_fund\brokers\test_account_binding.py hedge_fund\brokers\test_saxo_auth.py hedge_fund\paper\test_deployed_broker.py hedge_fund\paper\test_saxo_e2e.py hedge_fund\paper\test_runner.py hedge_fund\secrets\test_saxo_secrets.py hedge_fund\runtime\test_write_authority.py -q --tb=short
```

- Start: `2026-11-03T01:29:03.5628845+01:00`.
- End: `2026-11-03T01:29:54.9996792+01:00`.
- Result: **79 passed**, pytest runtime **41.44 seconds**, exit 0.
- Raw artifact: session `files/sim-focused-01.log`.
- This run precedes the later barrier-strengthening/formatter changes; final
  source-bound validation is recorded below rather than inherited from it.

## Isolation timeout diagnosis and environment remediation

- `files/sim-isolation-02.log`, `2026-11-03T01:33:35.9918999+01:00` to
  `01:34:33.4684983+01:00`: **68 passed, 1 failed**. The unchanged
  `test_spawned_python_inherits_network_and_credential_guards` hit its
  10-second guarded-child import timeout. A targeted unchanged rerun at
  `01:34:52.8120607` to `01:35:15.9092646` failed identically.
- An owned diagnostic ran the guarded import to completion, without services or
  provider calls, on current modules and trusted base versions of the three
  changed broker/deployment modules loaded from Git. Current import:
  **27.5565696 seconds** (total child **28.9631894 seconds**); base import:
  **16.0245430 seconds** (total child **17.6456156 seconds**). Both returned 0
  and verified non-loopback denial. Yfinance/data/backtesting imports dominated.
  This establishes that the 10-second limit also fails with base source in this
  environment; the single pair is not proof of exact performance parity.
- Initial `uv` installation had not precompiled dependency bytecode; tests
  correctly forbid writing it during imports. Only this worktree's dependency
  `venv/Lib/site-packages` was compiled, finishing
  `2026-11-03T01:48:15.1037113+01:00`. No repository source, timeout or guard
  was changed for this environment remediation.
- The unchanged 10-second child test then passed: start
  `2026-11-03T01:48:42.0270152+01:00`, end `01:48:59.8705381+01:00`,
  **1 passed in 10.79 seconds** (whole pytest case, not child timeout).
  Artifact: `files/sim-isolation-bytecode.log`.
- Diagnostic artifacts are session-local:
  `files/sim-current-import.json`, `files/sim-baseline-import.json` and their
  `sim-*-importtime.log` traces. They are not installed-package or global account
  proof. Final validation records any remaining timing failures explicitly.

## Previous integrated validation snapshot (before final correction/rebase)

That earlier frozen execution-source digest was
`74b78ef4ffd584bd697eedbd62ca6df8b97a33bb862dd3b4eb2df64a4cd794bb`
on worktree HEAD `b36da7107700332d99a4cfccc8dfeb2d4a159aa7` with this slice
uncommitted. `files/sim-source-before.json` was captured at
`2026-11-03T02:34:37.075735+01:00`: 241 nonignored tracked/untracked package
files plus dependency manifests, text CRLF normalized to LF, and 19 changed
repository files. It records per-file raw/normalized hashes, Python 3.13.7 and
actual installed distribution versions. Declared dependencies were restored
after missing-dependency failure, not synchronized exactly to the lockfile.

| Selection | Start / end (UTC+01:00) | Actual result | Raw artifact |
| --- | --- | --- | --- |
| Fake policy, production guards, deployment, CLI create/tick/replay/approve-now | `2026-11-03T02:34:37.1927800` / `02:36:38.9572655` | **82 passed in 118.53 s**, exit 0 | `files/sim-focused-current.log` |
| Remaining broker/SIM adapter/runner/secrets, root authority, full CLI/isolation and web SIM denial | `2026-11-03T02:40:06.8213204` / `02:46:48.4386881` | **278 passed in 396.42 s**, exit 0 | `files/sim-integration-current.log` |

The focused selection's policy module has 51 cases and the separate production
guard module has 19. Integration intentionally excludes those two already-run
modules. The integration run emitted one existing Starlette/anyio deprecation
warning; no safety guard or timeout was relaxed. It includes no-effect SIM API
denial, not a real browser/packaged artifact claim.

`files/sim-source-after-integration.json`, captured at
`2026-11-03T02:46:57.464760+01:00`, matches the frozen source digest exactly.
Black 420, isort, flake8 and `git diff --check` pass across the 16 changed Python
files. These results precede the third rebase and fake-schema correction;
they are historical, not final-source/full-suite acceptance.

## Review-driven generation correction and previous `042cfbc` source

Thirteen canonical-state corruption regressions demonstrated the review finding:
zero/negative/future bound generations, release before/at bind or beyond state,
and nonpositive/future/reordered/duplicate or stale-current transfer generations.
The incoming validator accepted each, reaching mutation instead of
`ownership-unknown`. At `2026-11-03T03:12:56.5231985+01:00` to
`03:13:43.2077005+01:00`, the result was **13 failed, 51 deselected in
43.57 seconds**, exit 1 (`files/sim-generation-red.log`).

The validator now bounds records by state generation, requires release strictly
after binding, and orders positive transfer generations through the exact current
binding generation. The corruption tests also compare all registry file bytes
after denied bind/release/inspect/open. The transfer race has a bounded barrier
and an explicit peer-startup-failure case; that additional timeout case has no
claimed discriminating red. Production guard naming/docstrings now explicitly
describe unconditional denial rather than policy acceptance.

One lint invocation omitted the repository's 420-column setting and reported
existing E501 violations at flake8's default 79 columns. Its output is preserved
as `files/sim-flake8-default-config-failure.log`; no code or policy was weakened
to satisfy that accidental setting. The corrected checks explicitly use
Black/flake8 420 and configured isort. At `2026-11-03T03:17:36.1260816+01:00`
to `03:17:39.2619054+01:00`, all 16 changed Python files passed Black
check, isort check, flake8 and diff whitespace, exit 0
(`files/sim-style-final.log`).

That execution-source digest was
`25d5c34f3759585882069e936d72c6e57fb043da260753f69183be37533fc904`,
captured at `2026-11-03T03:17:45.593269+01:00` in
`files/sim-source-final-before.json`, HEAD `042cfbc47b4a7221f0359a129767a26b48cd71a1`.
It binds 242 package/dependency files and 19 changed repository files.

| `042cfbc` source selection | Start / end (UTC+01:00) | Actual result | Raw artifact |
| --- | --- | --- | --- |
| All fake policy/production guards, deployed broker and complete CLI tests | `2026-11-03T03:17:45.6991385` / `03:24:09.6179448` | **164 passed in 381.37 s**, exit 0 | `files/sim-focused-final.log` |
| Remaining brokers, fake SIM end-to-end/runner/secrets, native write-authority fixture, acceptance isolation and web API | `2026-11-03T03:26:59.9591657` / `03:27:37.0524782` | **249 passed, 1 warning in 34.33 s**, exit 0 | `files/sim-integration-final.log` |

At that stage the fake-policy module had 65 cases, including the 13 corruption regressions
and bounded peer-startup-failure case; the production guard module has 19.
Integration excludes both already-run account modules. Its warning is the
existing Starlette/anyio alias deprecation. The two after-run manifests,
`files/sim-source-final-after-focused.json` (`03:24:10.312322+01:00`) and
`files/sim-source-final-after-integration.json` (`03:27:37.680072+01:00`),
match the frozen execution-source digest exactly. The previous 82/278 counts
are not substituted. Full Python-suite execution started at
`2026-11-03T03:27:37.7510672+01:00` and was subsequently canceled for
the `9c5f491` integration, without a passing result.

## Independent reviews and dispositions

The first independent reviewer examined the initial guards read-only and found
no Critical findings. Its CLI error-label and ledger/control ordering concerns
were repaired with discriminating CLI/library regressions before the fresh
integrated runs above. Its session report is `files/review-report-one.md`.

The second independent reviewer examined the integrated implementation and
returned pass-with-caveats, with no Critical/Important high-confidence findings.
It independently read central production code and most tests/docs; some middle
fake-policy tests and remaining end-to-end tests were only indexed/spot-checked.
It ran no shell, tests, source hashes or Git/publication verification. This is a
static review, not independent reproduction of the validation results.
Its report/disposition summary is `files/review-report-two.md`.

The namespace/network-guard distinction, historical verdict-control limit,
target-versus-shipped headless contract and unconditional-denial coverage wording
are now explicit. The reviewer also found insufficient generation bounds in
the fake-state schema. The corruption regressions and tightly coupled repair
above address it; the `042cfbc` focused/integration validation was green
as recorded above. The later final-review correction and its current-source
validation are recorded below; canceled runs supply no full-suite acceptance.

Existing GitHub bot reviews were fetched and triaged at
`2026-11-03T03:25:17+01:00` to `03:28:01+01:00`; the newest bot review is
COMMENTED on the earlier `16369e9` source, not this slice. All six historical
findings have upstream fix replies and current-code verification; this slice
does not reapply or claim those fixes. The decision table is
`files/sim-github-review-triage.md`. A Copilot-bot collaborator API probe returned
HTTP 404, so no API reviewer request is available on that evidence; a current
review must be requested through GitHub's supported UI. No bot or human
approval of this slice is claimed.

## Final-review cross-record correction

The final static reviewer found two additional fake-state consistency gaps:
multiple active accounts could share an owner/deployment, and distinct records
could claim the same generation event. Four canonical corruption regressions
demonstrated acceptance before the repair: **4 failed, 65 deselected in 13.51 s**,
exit 1, from `2026-11-03T03:42:14.8873270+01:00` to
`03:42:31.2327444+01:00` (`files/sim-cross-record-red.log`).

The validator now requires active-only owner/deployment uniqueness and
cross-record generation-event uniqueness. Within each record it deduplicates
the current binding/final provenance hop as the same event. Released owners
may be reused and legitimate generation gaps remain valid. A positive
interleaved two-account bind/release/transfer case checks reuse, case-folded
idempotency without mutation and discarded historical release-generation gaps.
There are now **70 fake-policy cases and 19 production-denial cases**.

The incoming writer map initially referenced the old competing-transfer test
name: **108 passed, 1 failed in 2.07 s**, exit 1, from
`2026-11-03T03:52:08.4306085+01:00` to `03:52:12.6103590+01:00`
(`files/sim-writer-map-integration.log`). Only that test-node pointer and
directly related synthetic-policy wording were repaired. The AST writer inventory
and real-test-node assertions remain strict; no production runtime primitive
was changed.

## Current frozen source and validation

The current execution-source digest is
`9a1ed424d10168e5b0ecf0c22ef56d8485c2a445c61b0fdcb0644a7069d815e7`,
captured at `2026-11-03T03:56:08.781670+01:00` in
`files/sim-source-b6-final-before.json`, on integrated HEAD
`b6a8a5b2086ebba1fe7cce7c82b943b49eeb5a8a` with this slice uncommitted.
It binds **245 package/dependency files and 20 changed repository files**.
It records raw and CRLF-to-LF-normalized hashes, Python 3.13.7, Windows and
actual installed dependency versions. Dependencies were restored from declared
requirements after a missing-package failure, not synchronized exactly to the
lockfile; these results do not establish lockfile-exact or packaged acceptance.

Black 420, configured isort, flake8 with explicit `--max-line-length 420`
and `git diff --check` passed **17 changed Python files**, exit 0, from
`2026-11-03T03:56:01.8874759+01:00` to `03:56:07.3102381+01:00`
(`files/sim-style-b6.log`).

The coupled writer-map and new cross-record negative/positive selection:

```powershell
.\venv\Scripts\python.exe -m pytest hedge_fund\runtime\test_writer_map.py hedge_fund\brokers\test_account_binding.py -q --tb=short -k 'writer_map or cross_record_corruption or interleaved_accounts'
```

passed **114 tests, 65 deselected in 22.51 s**, exit 0, from
`2026-11-03T03:56:09.0167246+01:00` to `03:56:34.5558176+01:00`
(`files/sim-cross-record-map-green.log`). The after-run manifest,
`files/sim-source-b6-after-targeted.json`, captured at
`03:56:45.822216+01:00`, matches the frozen execution digest.

Full isolated Python-suite validation started at
`2026-11-03T03:56:45.9662557+01:00` with dotenv and pytest plugin autoload
disabled, bytecode writes disabled and the repository isolation conftest:

```powershell
.\venv\Scripts\python.exe -m pytest hedge_fund -q --tb=short -ra
```

It completed at `2026-11-03T04:37:05.3015591+01:00`: **2325 passed,
51 skipped, 1 warning in 2414.55 s (40:14)**, exit 0. All 70 fake-policy and
19 production-denial cases, complete CLI, fake adapter/runner/secrets, deployed
broker, root authority/admission/writer-map/race/unlink, paper ledger/tick and
web API cases are included. The 51 skips are **36 live Financial Datasets
credential-required smoke cases and 15 POSIX/Linux-only cases**; no credentials
were supplied to enable them. The warning is the existing Starlette/anyio alias
deprecation. These skips are not Linux, live-provider or packaged acceptance.

Raw output is `files/sim-full-b6.log`. The after-run manifest,
`files/sim-source-b6-after-full.json`, captured at
`2026-11-03T04:37:10.594073+01:00`, matches the frozen execution digest exactly.
Earlier 82/278 and 164/249 results remain explicitly historical, not substitutes
for this current cross-record/incoming-T021 green result. Current-source
validation is complete; publication receipts are recorded separately after
the final ancestry/head checks and local commit.

The resumed final independent reviewer returned **pass-with-caveats, no Critical
or Important findings** for this frozen code. It re-read the complete account
module, the cross-record cases, merged guard boundaries, strict map pointer and
Windows network/namespace guard sections. Some unchanged test bodies were
carried forward from its earlier read or indexed, not freshly read in full.
It executed no shell, tests, hashes or Git checks, and did not read the incoming
T021 admission diff; it verified the surrounding guard order only.
Its code verdict is static, not independent reproduction
of the parent-run results. The persisted summary and exact read limitations
are `files/review-report-three.md`; original responses remain in the session
tool transcript.

The reviewer corrected its earlier TUI claim: `_record_approval` returns through
`_deny_paper_write()`, and `paper_write_denial()` denies every root state, so TUI
verdict recording is unreachable. The inaccurate evidence/contract sentences
were corrected without changing TUI code. Plain CLI verdict recording remains
the accurately scoped control-parity limitation.

## Authored manifest

This slice changes **20 files: 6 production Python, 11 test/helper Python and
3 Spec005 documents**. The incoming fake registry is preserved and hardened,
not falsely attributed as an entirely new implementation.

```text
hedge_fund\brokers\account_binding.py
hedge_fund\brokers\factory.py
hedge_fund\brokers\saxo_auth.py
hedge_fund\paper\deployed.py
hedge_fund\paper\tick.py
hedge_fund\run.py
hedge_fund\brokers\test_account_binding.py
hedge_fund\brokers\test_account_binding_guards.py
hedge_fund\brokers\test_saxo_auth.py
hedge_fund\brokers\test_saxo_doubles.py
hedge_fund\paper\test_deployed_broker.py
hedge_fund\paper\test_runner.py
hedge_fund\paper\test_saxo_e2e.py
hedge_fund\runtime\test_write_authority.py
hedge_fund\runtime\test_writer_map.py
hedge_fund\secrets\test_saxo_secrets.py
hedge_fund\test_run.py
specs\005-web-engine-migration\contracts\headless-and-deployment.md
specs\005-web-engine-migration\tasks.md
specs\005-web-engine-migration\sim-account-ownership-evidence.md
```

## Isolation and scope limits

All fixtures are checkout-owned synthetic roots/HOME/USERPROFILE/TEMP. The
repository harness clears credential/provider/proxy environment, disables
dotenv, denies non-loopback socket operations and guards owned child processes.
No real broker, credential, provider, account lookup, fund or runner is used.
No services are started by this slice and no existing services/processes or
other session worktrees are inspected. No SIM browser mutation is added.

Positive owned-quiescent release and replay-safe transfer provenance are policy
simulation cases only; production release/transfer and successful headless SIM
provisioning remain **blocked**, not accepted. The permanent production denial
is not a durable global-exclusive registry or complete cross-root inventory/race
proof. NTFS/ext4 root primitives and historical platform counts are not global
account-control evidence. T015/T021, complete US4 lifecycle/account acceptance,
web parity, packaging/platform acceptance and the TUI-retirement gate remain open.
