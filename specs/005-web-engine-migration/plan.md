# Implementation Plan: Complete web-only engine migration

**Branch:** `cgjedrem-vigilant-robot` | **Date:** 2026-10-31 | **Spec:** [spec.md](spec.md)
**Input:** Historical spec005 plus [forward contract](../../docs/governance/web-migration-contract.md).
**Source:** `24fbf1ff3eda4b92e0097859ec2279ef6ba49a79`; discovery/main baseline
`6443490db64056742fbbe6a18abf92c903c10861`. Implementation pending; no tasks generated.

`setup-plan.ps1 -Json` resolved feature pointer005 and returned logical BRANCH
`005-web-engine-migration`; Git remains `cgjedrem-vigilant-robot`, not renamed.
This is a newly created Phase 0/1 plan consuming completed forward red-team resolutions,
not a rewrite of an earlier historical plan during red-team resolution.

## Summary

Make the existing React/shadcn desk the sole supported interactive engine surface, preserving
terminal-inspired presentation and canonical domain behavior. First establish fixed-root,
all-writer cross-process admission, verified detached runner ownership, private frozen
configuration, durable operation/confirmation sidecars and reconciliation-aware recovery.
Then add local-paper execution/lifecycle, full validated editor, authorized valuation,
research progress/reporting and packaging before retiring TUI and Docker ttyd.

The host is writable driver; container is read-only observer, with no cross-namespace mutation.
SIM web control is expressly exempted; non-TUI headless SIM remains under exclusive account
binding. Free default is an intentional compatibility change. Cloud/paid scheduled loops
stay prohibited; bounded free/local scheduled paper is authorized by the user-directed
constitution amendment. All 15 [red-team findings](red-team-findings-2026-10-31.md) have
normative forward resolutions, not implemented/runtime closure.

## Technical Context

**Language/Version:** Python ^3.11, TypeScript ^5.8, React ^19.1.
**Primary Dependencies:** Existing Poetry/Pydantic/PyYAML/Rich/domain engines; FastAPI ^0.115,
Uvicorn ^0.34, yfinance extra, React Router/shadcn-Radix/Tailwind/Recharts/Vite.
Remove Textual/textual-dev only after replacement assertions and packaging acceptance.
**Storage:** Existing byte-stable hash-chain/YAML; versioned root-private JSON snapshots/
journals and OS locks. Local NTFS/ext4 only, no shared namespace/network filesystem.
**Testing:** Co-located pytest; existing frontend Vitest/Testing Library/Playwright scripts
and TypeScript build; black 420/isort/flake8; synthetic fakes beneath production guards.
**Target Platform:** Windows/Linux hosts; read-only host-loopback-mapped container observer.
Both host platforms require actual runtime evidence, never inferred from static source.
**Project Type:** Local Python CLI/web server plus packaged React SPA.
**Performance Goals:** SC-009 local acknowledgment/status ≤2 seconds in ≥95% synthetic
observations excluding provider computation; bounded jobs, diagnostics and polling.
**Constraints:** No real brokerage/protected roots/runners/8765/paid calls in validation;
offline observation, immutable deployments/ledger bytes, no automatic runner starts/retries
or bounded-job resumption. Unknown/absent OS primitives fail closed.
**Scale/Scope:** One trusted local operator/root; 74 capabilities/six journeys; independent
deployments, finite scheduled authorizations and bounded backtests.
No unresolved design clarification remains; runtime risks are evidence gates, not passes.

## Constitution Check

Pre-research check performed after forward amendment/resolution; re-evaluated after design.
No draft-constitution exception is used.

| Principle / gate | Pre-research decision | Post-design obligation |
| --- | --- | --- |
| I Ledger integrity | PASS design | Sidecars only; pin `SessionRecord.code_version` for byte parity; canonical cash/replay/votes/redo. |
| II Paper/provider safety | PASS after express doc amendment | Free/local finite scheduled exception only; no paid/cloud loops, operation-specific paid cap, no paid tests. |
| III Co-located/full suite | PASS documentation scope, not runtime pass | Individually reproduce unchanged baseline failures; full suite plus Windows/Linux lifecycle before retirement. |
| IV Determinism | PASS design | Fake/recorded clocks, frozen captures; provenance does not fabricate ledger effects. |
| V Surface consistency | PASS React amendment | Full editor/domain/CLI agreement; explicit SIM browser exemption. |
| VI Style | PASS documentation scope | UTF-8 without BOM; existing lint/style conventions unchanged. |
| Governance | PASS planning amendment pathway | New open main plan-review PR; implementation pending; never merge. |
| Adversarial gate | PASS design resolution | Three sequential QA lenses, 15 forward fixes; runtime closure pending. |
| Retirement FR-062 | BLOCKED intentionally | No implemented parity, fresh TUI-free package/browser or platform lifecycle evidence yet. |

The old amendment/full-suite dependency is explicitly amended, not bypassed by blanket
baseline exemptions. Required platform/inconclusive suite rows never pass by assumption.
Autonomous authority covers planning/amendment/PR only; no future implementation approval.

## Project Structure

### Documentation (this feature)

```text
specs\005-web-engine-migration\
  plan.md
  research.md
  data-model.md
  quickstart.md
  contracts\
    runtime-api.md
    headless-and-deployment.md
  red-team-findings-2026-10-31.md
docs\governance\web-migration-contract.md
.specify\memory\constitution.md
```

No `tasks.md` created. Historical spec/discovery/checklist retained unchanged.

### Source Code (repository root; proposed implementation locations)

```text
hedge_fund\
  run.py, paths.py             # existing CLI/root seams
  runtime\                    # planned neutral admission/config/ownership/journal
  web\                        # existing guarded adapter/services/jobs/static bundle
  paper\, pipeline\, brokers\ # canonical execution/replay/reconciliation/scheduler
  fund\, data\, llm\          # authoritative rules and controlled providers
  backtesting\                # canonical research/results/progress
  reporting\                  # planned neutral console helpers
  tui\                        # move assertions before retiring
frontend\src\                 # existing components/pages/hooks
Dockerfile, Dockerfile.web, docker-compose*.yml, Makefile, pyproject.toml
```

**Structure Decision:** Extend existing Python/React split. `runtime`/`reporting` are
proposed neutral seams, not source added in this PR. Domain algorithms stay authoritative;
adapters do not reimplement scheduling/sizing/reconciliation/serialization.

## Complexity Tracking

| Explicit change / mechanism | Why needed | Simpler alternative rejected |
| --- | --- | --- |
| User-directed doc amendment before runtime full suite | Resolve TUI/runner governance deadlock | Old wording blocks target design; blanket failure waiver destroys evidence. |
| OS locks + reservation + durable journal | All-writer ownership and crash ambiguity | Web mutex/PID/TTL cannot fence CLI, PID reuse or partial effects. |
| Host writer/read-only container; SIM browser exemption | Namespace/account control cannot be inferred | Shared writable compose and claimed SIM parity conceal unsupported mutation. |

## Design sequence (not an executable task list)

1. Extract neutral TUI helpers and fixed-root/capability/provider bootstrap before execution
   routes; version private settings/credentials and complete domain editor validation.
2. Establish shared admission/controlled legacy handover, owner handshake/durable journals;
   independent-fund/emergency-control behavior, crash recovery and exclusive account binding.
3. Add preview/digest/idempotent local-paper manual/runner/stop/recovery/verdict/redo;
   exact due-set/finite backlog and reconciliation of ambiguous post-fill halts.
4. Add reversible lifecycle under shared leases, complete custom roster/editor, authorized
   valuation and bounded research/reporting/cancellation/interrupted status.
5. Package default desk/headless assets, migrate all assertions and remove TUI/ttyd/auto-
   runner compose only after replacement evidence; fresh Windows/Linux/browser acceptance,
   multiple independent QA and final source-bound re-review after fixes.

Interfaces: [runtime API](contracts/runtime-api.md), [headless/topology](contracts/headless-and-deployment.md);
state: [data model](data-model.md); decisions: [research](research.md);
validation: [quickstart](quickstart.md). Forward G/R/A/O/C clauses govern all LM/LB/HM fixes.

## Retirement and moved-assertion inventory

This supplements omissions in discovery, not a rewrite of its historical table.

| Existing surface/assertions | Required replacement evidence before removal |
| --- | --- |
| `run.py`, `tui\__main__.py`, `tui\app.py`; `test_run.py` | Default desk/actionable asset failure; every headless command imports without Textual. |
| `tui\keys.py`; `web\services.py`, `check_stock.py`, `llm\test_client.py` imports | Neutral set/delete/provenance/private-permission tests below guards. |
| CLI imports of `tui\shared.py`, `report.py`, `scorecard_view.py` | Neutral defaults/schedule/console precision/order/scorecards. |
| `tui\test_home.py`, `test_keys.py` | Web/runtime overview/catalog/config/non-echo/private store/default entry assertions. |
| `tui\test_builder.py`, `test_builder_broker.py`, `test_funds.py` | Full round-trip/cadence/custom identity/universe/protected collision/archive; SIM exemption explicit. |
| `tui\test_paper.py`, `test_paper_view.py` | Canonical progress/schedule/votes/redo/recovery/valuation and actual owned Windows/Linux runner lifecycle. |
| `tui\test_backtest.py`, `test_report.py`, `test_scorecard_view.py` | Research review/stage/cancel/interruption/report/console signed fractional precision. |
| `paper\test_saxo_e2e.py` Textual imports | Non-TUI fake SIM provisioning/account-binding/readiness/headless behavior, not browser control parity. |
| `pyproject.toml`, lockfile Textual/textual-dev | Clean dependency/import closure, wheel/sdist without Textual/runtime Node. |
| `Dockerfile` ttyd download/default TUI; `Dockerfile.web` | Packaged observer, no ttyd/Textual/default runner, actionable asset failure. |
| `docker-compose.yml`, `docker-compose.linux.yml` TUI/ttyd/writable runners/autorestart | Host writer/read-only observer, loopback publication, no secret mount/cross-namespace mutation/automatic upgraded runner start. |
| `Makefile` dev/console; root/package READMEs | Supported desk/headless targets, explicit roots, safe synthetic names/ports/topology. |

Every individual retired assertion needs a named replacement test and source-bound evidence,
not just file mapping. All 74 IDs retain FR/test/status links; explicit SIM exemption does
not excuse local-paper parity. Synthetic protected-name fixtures prove denial before any
access/provider/process effect; never fingerprint real funds.

## Evidence state and handoff

Phase 0/1 design complete, no template placeholders. Before/after-plan Git commit hooks
are optional and auto-commit disabled; no mandatory plan hook or target-branch config exists.
Explicit target main fetched as baseline above and verified ancestor; recheck before push/PR.
Only documentation/static source and three QA reports validated now. Frontend manifest
declares Vitest/Playwright, not their installed/runtime readiness. Linux runtime not established;
actual evidence required if available, otherwise blocked. No tests/Docker/browser/providers/
funds/credentials/creator port used.

**Decision:** proceed to open main-targeting plan review only. Implementation pending;
no tasks or implementation. Retirement remains blocked until full required evidence passes.
