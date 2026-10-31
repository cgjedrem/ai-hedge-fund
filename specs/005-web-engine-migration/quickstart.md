# Quickstart validation guide

**Not run.** This is the post-implementation acceptance guide, not a working-feature claim.
Current PR changes documentation/governance only. Proposed flags/interfaces in
[contracts](contracts/headless-and-deployment.md) must first be implemented.
No paid calls, live funds/runners, credentials or creator preview may be used.

## Prerequisites and safety gate

Use an isolated checkout-owned fixture directory, synthetic HOME/USERPROFILE and explicit
root; disable dotenv and clear provider credentials before any project imports. Deny all
external network at the harness boundary. Data/LLM/broker/secret/process/clock fakes must sit
below real root/auth/admission guards. No production credential or root copy is permitted.
Run full-suite commands only after the harness proves all selected tests use these boundaries.
Do not run current compose services or global CLI defaults; they still include real-name/
home/root and automatic runner behavior. Never touch creator port 8765.

Example PowerShell fixture setup (only after the isolated harness is implemented):

```powershell
$fixture = Join-Path (Get-Location) 'acceptance-fixtures\web-migration'
New-Item -ItemType Directory -Force -Path "$fixture\home", "$fixture\root" | Out-Null
$env:HOME = "$fixture\home"
$env:USERPROFILE = "$fixture\home"
$env:PYTHON_DOTENV_DISABLED = '1'
# Harness additionally clears every declared provider credential and denies external I/O.
# All invoked children must receive --root "$fixture\root" explicitly.
```

The environment flag is only a harness signal; the harness must independently prevent
dotenv loading rather than assume the pinned dotenv dependency honors that flag.
This does not itself establish isolation; verify guard sentinels before tests and use only
test-owned process IDs/ports (e.g. 8876), never name-based process cleanup. No temporary
directory outside checkout. Delete only exact fixture-owned artifacts after verification.

## Smallest-to-full validation commands

Use existing runners after safe harness setup; these commands are prospective, not results:

```powershell
poetry run pytest hedge_fund\web hedge_fund\paper -q
if ($LASTEXITCODE -eq 0) { npm --prefix frontend test }
if ($LASTEXITCODE -eq 0) { npm --prefix frontend run build }
if ($LASTEXITCODE -eq 0) { npm --prefix frontend run e2e }
# Run once safe affected checks pass, preserving each failure/interrupt as evidence:
poetry run pytest hedge_fund -q
```

Expand affected scope to neutral runtime/credential/report/fund/data/LLM/backtest tests as
those seams change. Lint changed source only using existing black/isort/flake8 conventions.
If Poetry/browser/test dependencies are missing, record blockage or install only in the
authorized implementation environment after actual missing-dependency failure. Do not
claim declared frontend scripts are installed/runnable. Clean package validation must use
wheel/sdist assets and a TUI-free installation; Node is build-time only, never runtime.

## Discriminating scenarios and expected outcomes

All listed outcomes are expected, not observed. Each needs exact FR/SC criterion and named
replacement assertions recorded with actual source/build/time/platform/fixture provenance.

| Scenario / linked requirement | Procedure | Expected outcome |
| --- | --- | --- |
| Fixed-root and protected denial FR-006/044/058; LB1/5 | Synthetic root, decoy home/CWD/parent dotenv; injected env/root/capability; aliases/reparse/race/network filesystem | Denied before access; no real fallback, child root unchanged, unsupported filesystem blocked. Synthetic protected-name fixtures only, never real protected objects. |
| Cross-process admission FR-007/008; LM1/2 | Concurrent upgraded CLI/web/runner/manual/redo/archive on one synthetic fund, second independent fund; legacy nonparticipant marker/unknown owner | One conflicting writer or denial, zero duplicate effects; independent fund works; legacy uncertainty denies mutation; no cross-namespace signal. |
| Host runner lifecycle FR-009–013; HM4 | Fake clock/provider, bounded free/local authorization, verified start/handshake; browser/server close; stop at in-flight boundary | Owned runner survives browser/server; no auto-start/restart; stop requested differs from quiescent; unrelated PID survives; Windows and Linux actual runtime required. |
| Manual/backlog FR-014/017/042; LM4/HM5 | Preview exact head/due-set, change head/clock, expire/reuse confirmation, restore backlog, runner active | Conflict not retarget, no duplicate effects; restored stopped; finite reviewed catch-up; manual denied not queued during runner lifetime. |
| Frozen config/keys FR-018–025; LB3/4/HM2 | Full settings/edit/delete/capture; fake secret sentinel; local versus cloud-labelled model, remote URL/DNS/redirect cases | No network validation/secret echo; active capture stable; deleted new version absent; Windows ACL/POSIX mode evidenced or blocked; host-bound endpoint deny; no paid auth from key/env. |
| Budget FR-025/026/047; HM3 | Fake free/local schedule reaches expiry/session/call bound; fake paid one-shot/backtest denied or capped | No paid/cloud loops; estimate visible; cap stops before next call, no real paid calls; credentials never authorize alone. |
| Mandate parity FR-028–034 | Round-trip all weights/params/risk/cost/threshold/benchmark/cadence/approval/broker values and omissions, custom identity, universe | No value loss; registry validation; immutable deployment/pending state; stale edit/rename conflict. |
| Approval/recovery FR-035–039; LM3/HM5 | Matching/stale/consumed/source/execution redo, corrupt controls, append failure after fake fills | Active-runner warning; separate Run; emergency Halt responsive; replay alone cannot Resume ambiguity; reconciliation sidecar required; no fabricated record/retry. |
| Lifecycle FR-040–043; LM5 | Exact synthetic archive/restore/replace and research refs, crash phases; duplicate fake SIM account across roots | Scope retained/no broad deletion; stopped/collision-checked restore; new linked replacement; SIM web mutation denied and exclusive headless binding required. |
| Valuation/report FR-045–052 | Explicit fake refresh partial/stale/signed/fractional marks; malicious text; bounded research pagination/progress/cancel | Estimate/coverage distinct, recorded values unchanged, inert text/precision, daily-replay/non-point-in-time labels; interrupted no auto-resume. |
| Durable jobs FR-015–017; HM4/5 | Double-click/lost response/reload/server crash, same ID/different payload, surviving bounded worker | Durable existing status returned; payload conflict; interrupted/fenced worker, never repeat/resume automatically; result discoverable. |
| TUI-free package/topology FR-001/004/005/056/062 | Clean wheel/sdist, no Textual/Node runtime; default desk/headless; asset missing; container observer denied mutation | No terminal fallback/import, all moved assertions covered; observer no credentials/writes/calls; loopback mapping; no ttyd/TUI/autorestart. |
| Browser FR-002/003, SC-008/009 | Keyboard-only six journeys, 360px viewport, focus/contrast/numeric screenshots, fake progress timestamps | Terminal appearance retained; no clipped critical values; correct newer identity; latency bound measured not guessed. |

## Platform and baseline evidence

Run actual Linux lifecycle/packaged acceptance only on an available authorized Linux runtime;
otherwise mark required rows BLOCKED. Static Docker availability or historical PR7 output
is not Linux runtime evidence. Windows signal/incarnation/ACL primitives need native evidence.
If an OS primitive is unsupported, deny capability and preserve blocked retirement state.

For each full-suite failure, retain exact test ID/output/environment/revision and reproduce
on the pre-feature revision with the same isolated fixture. Only individually evidenced
unchanged failures may be baseline. Interruptions/inconclusive cleanup cannot be waived;
new failures remain failures. Do not "fix" unrelated baseline defects to obtain a count.

Use the acceptance template's criterion/source, expected/observed, revision/build, actual
timestamp/environment/fixture/exclusions/status. Append revalidation after changes and reopen
affected rows. Map every A01–F13 capability to FR/test evidence; SIM browser control has an
explicit no-parity exemption, not a pass. Complete plan retirement inventory (Docker/Make/
imports/dependencies and each old assertion) in addition to product rows.

**Current gate:** plan review only; all runtime scenarios above unexecuted, retirement blocked.
No setup/test/package/container/browser commands in this guide were run by this planning session.
