# Discovery: Complete Web Engine Migration

**Recorded**: 2026-10-31
**Verified discovery baseline**: `main` at `6443490db64056742fbbe6a18abf92c903c10861`, merged PR #7; current app-managed branch `cgjedrem-vigilant-robot`.
**Source**: Coordinator-provided read-only discovery report, supplied explicitly for this execution. This durable summary preserves its complete capability inventory, evidence pointers, risks and limitations; it is not fresh runtime inspection.
**Feature allocation**: Coordinator completed the mandatory git-feature hook with `-NoBranch`, receipt `005`. No branch creation or new number allocation is performed here.
**Related specification**: [spec.md](spec.md).

## Evidence boundaries

Discovery inspected code and historical artifacts only. It ran no tests/builds/servers/provider calls/fund operations and accessed no real funds, runners, credentials or creator preview `8765`. Specify execution reads templates, constitution, memory and the supplied report, then writes only this feature's specification/checklist/discovery and `.specify/feature.json`. No source/tests/scripts, constitution amendment, plan, tasks, PR or branch is created.

Reported facts below belong to baseline `6443490`; future acceptance must bind new evidence to its actual source/build. Proposed behavior in the disposition column is a specification decision, not existing implementation.

## Architecture and reusable domain authority

- `hedge_fund\run.py:86-196`: CLI commands and default no-argument Textual launch; imports credential, report, scorecard and backtest-default helpers from TUI.
- `hedge_fund\web\app.py:135-255`, `web\services.py:65-106,132-450`: loopback adapter, existing read/configuration/approval/backtest actions and configured-root seams; runner/manual/live/destructive operations explicitly disabled.
- `frontend\src\App.tsx:31-239`: React routes, responsive navigation and command palette; pages provide established settings, builder, backtests, paper and reports.
- `fund\spec.py:95-254,338-379`, `fund\storage.py:22-37`: authoritative validated mandate fields, registries, discovery and serialization.
- `paper\deployed.py:31-98`: immutable deployed `fund.yaml` snapshot, not an editable template.
- `paper\tick.py:172-374`: canonical replay/due/gate/redo/execution/append/audit sequence. Fills may precede append; failure cannot be treated as rolled-back work.
- `paper\ledger.py:112-410`, `pipeline\session.py:66-213`: hash-chain replay, controls, approval identity, reconcile/execute/value/assess/record and sizing invariants.
- `paper\runner.py:63-193,207-287`: injected scheduler loop versus signal-registering process wrapper; check-then-write PID admission and PID-only stop are not shared ownership.
- `paths.py:24-67`: home-derived defaults and atomic writes. Child CWD does not override CLI root resolution.
- `backtesting\fund.py:86-199`, `backtesting\research.py:18-78`: canonical replay/results; minute mandates use daily-grid historical replay.
- `data\__init__.py:44-66`, `data\cached.py:47-80,123-160`: pluggable providers, current paid default, explicit cache root and uncached snapshots.
- `llm\client.py:240-327`, `brokers\factory.py:13-56`, `brokers\saxo_auth.py:22-119`: process-environment clients, retained runner models, injectable SIM transport/secrets and separate OAuth provisioning.

Domain logic remains authoritative. Neutral credential/default/report/scorecard/schedule/progress helpers must be separated from TUI before retirement; this document chooses no extraction module architecture.

## Complete capability disposition

**Baseline legend**: Present = existing web behavior; Partial = material parity gap; Missing = absent web route/control; Extended = supported domain/headless configuration beyond the old builder.
**Disposition legend**: Migrate = required browser parity; Retain = existing behavior plus specified integration/regression; Exception = explicit supported non-TUI path or bounded engine exclusion. Every ID maps to normative requirements in spec.md; this is scope traceability, not a test-pass matrix.

### A. Entry, navigation, workspace and recovery (7)

| ID | Capability / baseline | Evidence | Required disposition / FR |
| --- | --- | --- | --- |
| A01 | Default interactive launch; Missing | `run.py:92-115` | Migrate default entry to desk, no TUI fallback; FR-001,005. |
| A02 | Direct TUI launch; separate web launcher | `tui\__main__.py:1-7`; `web\__main__.py:1-108` | Retire supported TUI entry only after acceptance; FR-001,062. |
| A03 | Overview; Present | `tui\home.py:24-126`; `web\services.py:132-372` | Retain recorded/offline/error provenance and corrupt-entry visibility; FR-003,028. |
| A04 | Keyboard/back/navigation; Present | `tui\home.py:30-34`; `frontend\src\App.tsx:41-239` | Extend keyboard, mobile, focus and palette to all controls; preserve terminal appearance; FR-002. |
| A05 | Operational refresh; Partial | `tui\paper.py:197-227`; `frontend\src\lib\hooks.tsx:1-82` | Migrate active runner/approval/valuation status without navigation; FR-003,009,035,045. |
| A06 | Unreadable-control recovery; Partial | `specs\004-react-web-ui\qa-final.md:13` | Migrate safe emergency Halt, verified Resume; FR-037. |
| A07 | Built packaged startup; assets absent locally | `web\__main__.py:1-108`; `pyproject.toml` | Node-free packaged runtime, actionable missing-assets failure; FR-005,062. |

### B. Provider, model and credential configuration (12)

| ID | Capability / baseline | Evidence | Required disposition / FR |
| --- | --- | --- | --- |
| B01 | Model catalog/grouping; Present | `tui\home.py:74-115,176-239`; `web\app.py:135-255` | Retain supported-provider validation and effective model display; FR-018. |
| B02 | Model change; process-only | `web\services.py:351-372`; prior parity row 17 | Persist next-operation choices; show active capture; FR-018,023. |
| B03 | Write-only key entry; Present | `frontend\src\pages\settings.tsx:19-194` | Retain non-echo and add redacted provenance/readiness; FR-021,024. |
| B04 | Surgical key persistence; TUI dependency | `tui\keys.py:33-70`; `web\services.py:42` | Neutral private atomic credentials and precedence; FR-021,022,056. |
| B05 | Missing-key run gating; Partial | `tui\home.py:243`; `tui\backtest.py:44`; `tui\paper.py:43` | Unified frozen preflight before providers/side effects; FR-024. |
| B06 | Market-data selector; Missing | `data\__init__.py:44-66` | Migrate explicit normalized persistent selection, free default; FR-019. |
| B07 | Credential-free data; environment-selected | `data\__init__.py:50-63` | Retain yfinance zero-key path and non-point-in-time research caveat; FR-019,024,047. |
| B08 | Local endpoint/context/timeout; Extended | `llm\client.py:294-323` | Complete editable supported runtime configuration, no cloud-key demand; FR-020,024. |
| B09 | Remote endpoint overrides; Extended | `llm\client.py:280-305` | Complete validated overrides, reject secret URLs; FR-020,054. |
| B10 | Active settings mutation; lifetime gap | `paper\runner.py:87-89` | Frozen next-operation contract; explicit runner restart, no hot swap; FR-023. |
| B11 | Restart-persistent effective config; Partial | prior parity row 17 | Persist choices/provenance and display override precedence; FR-018,022,023. |
| B12 | Saxo references/OAuth; Missing web setup | `brokers\factory.py:28-49`; `saxo_auth.py:99-119` | Exception: supported headless non-TUI provisioning; migrate desk SIM readiness. Separate rotating-token lifecycle justifies exception; FR-027. |

### C. Mandates and full configuration (18)

| ID | Capability / baseline | Evidence | Required disposition / FR |
| --- | --- | --- | --- |
| C01 | Canonical list/detail/errors; Present | `tui\funds.py:34-166`; `web\services.py:132-372` | Retain YAML/YML canonical discovery/collision behavior; FR-028. |
| C02 | Create; Present | `tui\builder.py:123-239,296-605`; `frontend\src\pages\builder.tsx:19-516` | Retain validated duplicate/protected guards; FR-028,030. |
| C03 | Strategy library; Present | prior parity row 10 | Retain canonical strategy identity, explicit custom conversion; FR-031. |
| C04 | Roster/subsets; Partial | `tui\builder.py:296-501`; prior parity row 10 | Migrate validated supported analyst subsets and weights; FR-029,031. |
| C05 | Capital/universe/deploy; Present | `tui\builder.py:123-239,501-605` | Retain separate template and deployment universe; FR-029,034,040. |
| C06 | Daily/weekly/monthly/minute; Present subset | `fund\spec.py:169-190`; prior parity row 10 | Round-trip all supported cadence values; FR-032. |
| C07 | Interval/window validation; Present subset | `fund\spec.py:207-225`; `tui\builder.py:659-704` | Preserve one-second floor, ET/window and SIM restrictions; FR-032. |
| C08 | Approval requirement; Present | `fund\spec.py:168`; `tui\builder.py:123-239` | Retain default-off omission and deployed gate display; FR-029,033,035. |
| C09 | Paper/SIM broker; operational parity unproven | `tui\builder.py:123-239`; `fund\spec.py:190-217` | Complete broker editor/readiness with fake transport acceptance; FR-027,029. |
| C10 | Risk/sleeve weights; Present subset | prior parity row 10 | Complete every supported field through ordinary/advanced editor; FR-029,030. |
| C11 | Model weights/constructor params; Extended | `fund\spec.py:95-104`; prior parity row 10 | Full validated parameters, no arbitrary code; FR-029,030,031. |
| C12 | Blend/gross/dollar neutrality; Partial | `fund\spec.py:111-147`; prior parity row 10 | Complete explicit policy editing without silent inference; FR-029,031. |
| C13 | Transaction costs; Extended | `brokers\costs.py:24-56`; `fund\spec.py:160-167` | Complete spread/commission/minimum/default omissions; FR-029,033. |
| C14 | Minimum order equity/benchmark; Extended | `fund\spec.py:164-190` | Complete field coverage and execution validation; FR-029,030. |
| C15 | Existing edit; Missing | prior parity rows 10,22 | Revision-bound template edit, immutable deployment; FR-028,033. |
| C16 | Clone/rename; Extended | scoped route inventory | Required lifecycle with new canonical/collision-checked identity; FR-028. |
| C17 | Builder to deploy/run/backtest; Partial | `tui\builder.py:501-605` | Complete reviewed end-to-end next actions; FR-034. |
| C18 | Template deletion/history wipe; Missing | `tui\funds.py:164-318` | Replace broad deletion with separately scoped reversible archival; FR-041,043. |

### D. Runner, manual execution and lifecycle (16)

| ID | Capability / baseline | Evidence | Required disposition / FR |
| --- | --- | --- | --- |
| D01 | Recorded paper list/detail/NAV/history; Present | `tui\paper_view.py:59-355`; `web\services.py:132-372` | Retain verified snapshots and independent errors/halt/pending/schedule; FR-003,050. |
| D02 | Runner status; Missing/unknown | `paper\runner.py:234-247`; `web\services.py:798-803` | Migrate verified lifecycle/ownership states; FR-008,009. |
| D03 | Start; Missing | `tui\paper.py:276-303`; `paper\runner.py:261-275` | Explicit start, shared admission, root/config and readiness; FR-006,007,010. |
| D04 | Graceful stop; Missing | `paper\runner.py:249-257` | Owned cross-platform stop with safe-boundary evidence; FR-008,011,062. |
| D05 | UI-closure survival; contract missing | `paper\runner.py:261-265` | Browser closure unchanged; restart reattach only verified live owner; FR-012. |
| D06 | Daily catch-up; forecast only | `paper\runner.py:92-117` | Preserve oldest-first/hourly-midnight scheduling and display backlog; FR-009,014. |
| D07 | Minute gaps/holiday/lateness/SIM cutoff; forecast only | `paper\runner.py:120-193` | Preserve execution semantics and show skips/events, no fabricated bars; FR-014. |
| D08 | Manual next session; Missing | `tui\paper.py:363-644`; `paper\tick.py:172-216` | Canonical manual job with shared admission/frozen preflight; FR-007,014,015,024. |
| D09 | Due/no-work/explicit date; Missing | `paper\tick.py:104-131`; `run.py:165-167` | Browser reviewed dates/backfill plus retained headless semantics; FR-004,014. |
| D10 | Latest redo; Missing | `paper\tick.py:224-267`; `run.py:309-311` | Head-bound exclusive local-paper redo, retained superseded history; FR-038. |
| D11 | Manual progress/warming/report; Missing | `tui\paper.py:438-644` | Migrate progress/report and replay-safe recovery; FR-015,017,050. |
| D12 | Halt; Present | `ledger.py:246-248`; `tui\paper.py:229-356` | Retain immediate stop-new-admission and safe corrupt-control recovery; FR-013,037. |
| D13 | Resume; Present | `ledger.py:250-252` | Verified replay only, never implicit start/run; FR-036. |
| D14 | Deployment wipe; Missing | `tui\paper.py:229-356`; `tui\funds.py:164-318` | Reversible archive, stopped/quiescent owner, identity/head checks; FR-041,042. |
| D15 | Replace/redeploy; Missing | prior parity row 22 | New linked deployment identity, no snapshot overwrite; FR-043. |
| D16 | Logs/startup/gap diagnostics; Partial | `paper\runner.py:128-132,258-275`; `ledger.py:402-410` | Bounded redacted owned diagnostics; FR-009,021. |

### E. Live valuation and approvals (8)

| ID | Capability / baseline | Evidence | Required disposition / FR |
| --- | --- | --- | --- |
| E01 | Live refresh; Missing | `tui\paper_view.py:356-374`; prior parity row 24 | Explicit operation/network authorization, never page-mount calls; FR-025,045. |
| E02 | Estimated versus recorded NAV; estimate missing | `tui\paper_view.py:59-169,356-481` | Separate source/time/coverage and no recorded contamination; FR-045,046. |
| E03 | Quote freshness; live absent | `pipeline\session.py:104-107`; `data\cached.py:78-80` | Per-ticker freshness, no stale cached-as-current claim; FR-045,046. |
| E04 | Approve/reject; Present stricter preflight | `ledger.py:358-376`; prior parity row 16 | Retain timestamp/source-hash identity and canonical replacement; FR-035. |
| E05 | Stale/consumed/expired display; Partial integration | existing web checks | Live status/conflict refresh, never automatic retarget; FR-003,035. |
| E06 | Approve and run; Missing combined journey | `run.py:377-404` | Separate explicit execution authorization, not approval side effect; FR-036. |
| E07 | Source/execution redo votes; domain present | `paper\tick.py:244-267`; `ledger.py:299-339` | Preserve source invalidation and consumed replay; FR-038. |
| E08 | Fills before append failure; no web execution yet | `paper\tick.py:321-341` | Halt/audit ambiguous state, no repeated side effects; FR-017,039. |

### F. Backtests, research and reports (13)

| ID | Capability / baseline | Evidence | Required disposition / FR |
| --- | --- | --- | --- |
| F01 | Dates/universe/validation; Present | `tui\backtest.py:160-237`; `frontend\src\pages\backtests.tsx:28-404` | Retain explicit reviewed defaults and validation; FR-047. |
| F02 | Confirmation/provider/model/mandate; Present | prior parity row 15 | Shared captured preflight/config/cost contract; FR-023,024,047. |
| F03 | Warming/per-agent progress; Partial | `tui\backtest.py:267-360` | Stage/agent/thesis progress without TUI renderables; FR-048,056. |
| F04 | Replay/NAV/benchmark/metrics/scorecards; Present | `tui\backtest.py:368-457` | Retain provenance/units/cents/fractional precision; FR-050,055. |
| F05 | Cancel/navigation/reload; Present | `web\jobs.py:1-130`; `backtests.tsx:28-404` | Clear boundaries and no resubmission; FR-016,017,048. |
| F06 | Restart durability; Missing | `web\jobs.py:1-130` | Recover status, unfinished jobs interrupted not resumed; FR-016. |
| F07 | Saved research; Present, limit 100 | `backtesting\research.py:18-78`; `web\services.py:132-372` | Stable bounded pagination/search and malformed-record visibility; FR-049. |
| F08 | Session/day detail; Present | `tui\paper.py:647-801` | Complete proposed/executed information-level parity; FR-050. |
| F09 | Risk/clamps/orders/fills/weights/tape/theses; broad present | `tui\report.py:53-630` | Enumerated drilldown/cost/precision acceptance, not just page load; FR-050,054. |
| F10 | Analyst/strategy scorecards; Present | `tui\scorecard_view.py:21-116` | Retain canonical browser and non-interactive headless rendering; FR-004,050,056. |
| F11 | Research deletion; Missing | prior parity row 22 | Scoped reversible archive with job/reference coordination; FR-041,043. |
| F12 | Export/output; headless present, browser unproven | `run.py:257-272,310-312,365-370` | Migrate browser canonical downloads; exception: retain headless stdout/output-file automation, no TUI required; FR-004,051. |
| F13 | Intraday backtest; daily grid | `backtesting\fund.py:172-180` | Exception: preserve labelled daily replay; true historical intraday simulation is separate engine scope, not UI parity; FR-052. |

**Inventory total**: 7 + 12 + 18 + 16 + 8 + 13 = **74 capabilities**. Each baseline gap is required or explicitly bounded above; exceptions are B12, retained headless aspects of D09/F10/F12, and the historical-intraday exclusion F13. None excuses ordinary desk operation/configuration/retirement parity.

## Foundational risks and settled specification defaults

1. **Shared writer admission**: existing atomic ledger replacement and web-local locks are not cross-process transactions. FR-007 covers headless/browser runner/manual/redo/lifecycle together; approval and emergency Halt must remain responsive.
2. **Ownership**: `is_running` probes a PID and `stop_runner` signals it. FR-008 prohibits PID-only adoption/kill; root/fund/process incarnation are required, mechanism deferred.
3. **Root propagation**: spawned child invokes CLI using global `PAPER_DIR`, regardless of fund CWD, and CLI loads credentials/initializes mandates before dispatch. FR-006 requires explicit containment for all entrypoints/caches/configuration/children.
4. **Long-lived versus bounded work**: signal-registering `serve()` is not a drop-in threaded job. FR-013 separates behavioral capacity and safety; supervision architecture is deferred.
5. **Configuration**: model selection is process-scoped and runner retains models. FR-018-024 choose persisted safe choices, explicit precedence, private keys, frozen operation captures and deliberate runner restart.
6. **Paid/unattended conflict**: data defaults to paid `fd`; constitution forbids paid defaults and unattended live-data loops. FR-019 fixes target default; FR-025/026/061 require explicit authorization and governance resolution, not silent reinterpretation.
7. **Mandates**: deployed `fund.yaml` is a snapshot. Full domain configuration coverage exceeds the old builder; FR-029/030 choose complete validated ordinary/advanced editing, FR-033 forbids deployed mutation.
8. **Lifecycle**: deletion/replacement/redo require quiescent shared admission and exact revision/head. Archive replaces broad wipe; new deployment identity replaces overwrite; no irreversible purge added.
9. **Valuation**: live snapshots bypass disk cache; estimated NAV must be observational with per-ticker coverage, never contaminate records.
10. **Crash/retry**: execution precedes append; cancellation occurs at boundaries. FR-016/017/039 choose interrupted bounded jobs, no auto-resume/retry/rollback claim.
11. **Retirement**: PR7's deferred operations were why external-writer risk was previously accepted. That acceptance must reopen; TUI removal requires new accepted implemented parity, not a feature flag or historical test count.

## Memory and governance constraints

- `.specify\memory\constitution.md`: ledger integrity/paper-only/provider safety, co-located passing tests, style and amendment/full-suite/main-target governance bind this feature.
- Current preamble/Principle V explicitly name Textual/TUI and Principle II forbids unattended live-data loops. FR-061 records an amendment proposal for the plan; no constitution file is changed now.
- `memory.md`: pin `SessionRecord.code_version` for cross-commit byte parity; preserve default-off approval serialization, source-hash vote identity and cadence field omission rules.
- Memory also records root-scoped shell-over-dotenv precedence, canonical YAML/YML/case identity, explicit unreadable halt state, paired verified snapshots and delayed job-list response hazards; these are retained requirements.
- TUI external-import retirement inventory: `run.py:86-112`, `web\services.py:42`, `check_stock.py:31`, `llm\test_client.py:296`, `test_run.py:110`, `paper\test_saxo_e2e.py:26-27`. Assertions migrate before helpers/tests/dependency removal.
- No unrelated ledger/schema/style repair is authorized. Existing platform anomalies must be distinguished from new failures; an anomalous exit or cleanup interruption is not automatically a pass.

## Tooling and historical evidence limitations

- Resolved active spec/checklist templates retain scenarios, functional requirements, entities, success criteria and assumptions. Generic tasks call tests optional, but the constitution requires them.
- `.specify\extensions.yml` actively registers Git hooks only. Mandatory before-specify hook is already completed with `-NoBranch`; after-specify commit is optional and auto-commit configuration is disabled. The requested explicit four-path commit is separate.
- Plan-review/red-team skills are available but not automatically enforced by the installed Git hook registry. FR-060 makes the user's intended sequence explicit.
- Trace-build defaults to `REQ-XXX` while spec uses `FR-XXX`; future trace work must configure/map identifiers and record every capability.
- Discovery found Python/Node/npm/git/gh/docker commands, but no Poetry/make on PATH, no checkout-local frontend Playwright/Vitest dependencies and no built static index. Chromium/Docker Engine readiness and Linux runtime were not verified.
- Historical PR7 Linux evidence reported 1,134 passed/37 skipped at a prior revision with `COLUMNS=240`; later affected/shared suites and Windows redo anomalies were recorded at other revisions. POSIX permission checks remained blocked and follow-up full-suite evidence inconclusive. These counts do not establish acceptance at `6443490` or for this migration.
- Previous acceptance admitted real-root read mistakes and protected-root identity inconclusive evidence. Future validation must not fingerprint/inspect real funds to compensate.

## Required future acceptance and handoff

Current document is ready for assumptions clarification, **not plan execution**. Next: clarify assumptions, adversarial ledger/money + local-boundary + human/model-control review, resolve findings, plan with governance proposal, open main plan-review PR before tasks, test-first implementation/convergence, multiple independent QA and final review, then a new main implementation PR that is never merged by the workflow.

Acceptance must use synthetic isolated HOME/USERPROFILE/root, dotenv disabled and credential variables cleared before imports; deny external requests, fake brokers/secrets/process/signals/clocks below real guards, use owned ports other than `8765`, and clean only exact test-owned processes. No paid/network calls or uncontrolled loops are authorized.

Discriminating coverage must include cross-process admission, unrelated PID survival, configured-root/decoy-home containment, frozen settings and secret non-echo, daily/minute runner lifecycle, manual due/no-work/stale confirmations, post-fill failure, approvals/redo, archive/replacement races, live partial/stale valuation, backtest interruption/reload, complete editor round-trip and proposed/executed report precision.

Retirement additionally requires clean no-Textual packaged/headless entrypoint evidence, browser keyboard/mobile/terminal-appearance evidence, Windows and Linux lifecycle results, moved-test accounting and no required blocked/inconclusive rows. Unavailable Linux is **blocked**, not passed. New evidence must identify source/build/time/environment/provenance and reopen after fixes.
