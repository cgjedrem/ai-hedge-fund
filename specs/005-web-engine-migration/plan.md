# Implementation Plan: Complete web-only engine migration

**Branch:** `cgjedrem-vigilant-robot` | **Date:** 2026-10-31 | **Spec:** [spec.md](spec.md)
**Input:** Historical spec005 plus [forward contract](../../docs/governance/web-migration-contract.md).
**Source:** Planning baseline `24fbf1ff3eda4b92e0097859ec2279ef6ba49a79`; discovery/main baseline
`6443490db64056742fbbe6a18abf92c903c10861`. Implementation continues in PR #8 on the
existing `cgjedrem-vigilant-robot` branch. Current execution scope is T015, T019, T020,
T021, T024 and T027 in `tasks.md`.

`setup-plan.ps1 -Json` resolved feature pointer005 and returned logical BRANCH
`005-web-engine-migration`; Git remains `cgjedrem-vigilant-robot`, not renamed.
This is a newly created Phase 0/1 plan consuming completed forward red-team resolutions,
not a rewrite of an earlier historical plan during red-team resolution.

## Release 1 scope revision (2026-11-04, user-directed)

The user approved narrowing Spec005 to Release 1: one trusted local operator running the
paper-only `watchtower` and `watchtower-weekly` funds from the React/shadcn desk, reusing
the canonical engine. The TUI is **retained as a fallback**. This revision supersedes the
earlier "current execution scope" line above and any conflicting retirement sequencing below.
The historical plan remains the design reference for deferred work.

- **Release 1 architecture:** reuse the existing fixed-root admission, operation preview and
  accept, durable jobs, verdict binding, Halt and paper ledger. No new storage or
  architecture is introduced for Release 1.
- **Retained safety:** shared admission still fences cooperating writers. FR-063 trusted
  single-writer acknowledgement is operator trust, not OS isolation. Legacy home roots stay
  read-only; cutover is an operator-only offline handover. Ambiguous fills fail closed.
  Loopback/Host/Origin/CSRF/path guards, secret non-disclosure and the free-data default stay.
- **Deferred, not complete:** TUI/Textual/ttyd retirement; a separate immutable
  host-writer/container-observer snapshot architecture; dual-platform native distributions; SIM custody and provisioning;
  archive/restore/replace; large catalogs and exhaustive exports; repeated overlapping review gates.
- **Acceptance:** Release 1 capabilities R1-01 to R1-09 in `spec.md`, closed through the
  bounded backlog RB-1 to RB-7 in `tasks.md`. The user selected one writable, single-user
  Docker web desk for RB-5. Compose now separates read-only inspection from explicit
  operator writes and selects Linux host networking. The final image was exercised on
  disposable synthetic ext4 volumes; observed runtime outcomes are recorded, but the
  formal evidence row is INCONCLUSIVE because the exact runtime timestamp and full
  invocation were not retained. Existing protected-name operation, Windows NTFS relocation
  and container-replacement workflow remain blocked.
- **Gate deviation:** no new red-team or plan-review gate was run for this narrowing. It is
  user-directed and recorded here and in the PR body.

## Docker choice and current blockers (2026-11-05)

The user selected a writable, single-user Docker paper desk, host-loopback access, and the
retained TUI fallback. Read-only inspection is the default profile; `web-operator` explicitly
enables writes/network capability and is supported only with the Linux host-network overlay.
The package-source digest is recomputed and verified before baking. The revision is an
operator-supplied, format-checked Git object ID; it is not checked against the source tree.
Root enrollment, offline operator trust and cooperating-writer admission remain mandatory;
neither a mount nor a Compose profile grants authority. The operator-only cutover remains
unperformed.

Final image `aihf-web-spec005-r1-cad96a0-8875cf1` is
`sha256:21582eeedfa316925b6656f4eedcb4dfd0b999062af3d3aa72f84ceaaa9597b6`, built from
source revision `cad96a05875efe13d229a8a079d2348ed6d0cf95` with baked package digest
`8875cf13798d0b6f8468bba97ab3e7f4a21eb48ccd1f61f951b30cd94026d815`. Bounded synthetic
ext4 observations include successful service/API startup, trusted write after explicit
offline acknowledgement, same-container restart retaining namespace identity, and a new
container failing closed as read-only. The image was also used for synthetic write, lock,
secret-boundary and sequential TUI checks. Runtime timestamps and the full invocation were
not retained in the current evidence record; its formal result is INCONCLUSIVE.

In the current Windows Docker Desktop 29.9.2 Linux/amd64 environment, a temporary synthetic
Windows bind mounted at `/data` reports filesystem type `9p` and `fstatfs` magic
`0x01021997`; `RootContext.open('/data')` denies it because only local NTFS or ext4 is
supported. A Docker Desktop ext4 named volume is permitted for disposable synthetic runtime
validation only, not as evidence for NTFS-to-ext4 migration. The Linux host-network/browser/
Ollama topology was checked as Compose configuration only; it was not exercised end-to-end.
Identity changes remain fail-closed, with no approved rebind or upgrade workflow.

FR-044 still denies `watchtower` and `watchtower-weekly` in root and web guards. Target-fund
operation remains **BLOCKED** pending an explicit user decision; no fixture/agent exception
or guard removal is authorized. No real funds, legacy roots or cutover have been used.

## Summary

Make the existing React/shadcn desk the sole supported interactive engine surface, preserving
terminal-inspired presentation and canonical domain behavior. First establish fixed-root,
participating-writer cross-process admission, verified detached runner ownership, private frozen
configuration, durable operation/confirmation sidecars and reconciliation-aware recovery.
Then add local-paper execution/lifecycle, full validated editor, authorized valuation,
research progress/reporting and packaging before retiring TUI and Docker ttyd.

The host-writer/read-only-observer split is the historical full-migration target, not the
selected Release 1 deployment. Release 1 selects one writable, identity-bound Docker web
desk; cross-namespace runner stop/adoption remains unsupported. SIM web control is expressly
exempted; non-TUI headless SIM remains under exclusive account binding. Free default is an
intentional compatibility change. Cloud/paid scheduled loops stay prohibited; bounded
free/local scheduled paper is authorized by the user-directed constitution amendment. All
15 [red-team findings](red-team-findings-2026-10-31.md) have normative forward resolutions,
not implemented/runtime closure.

## Technical Context

**Language/Version:** Python ^3.11, TypeScript ^5.8, React ^19.1.
**Primary Dependencies:** Existing Poetry/Pydantic/PyYAML/Rich/domain engines; FastAPI ^0.115,
Uvicorn ^0.34, yfinance extra, React Router/shadcn-Radix/Tailwind/Recharts/Vite.
Remove Textual/textual-dev only after replacement assertions and packaging acceptance.
**Storage:** Existing byte-stable hash-chain/YAML; versioned root-private JSON snapshots/
journals and participating-writer OS locks. Local NTFS/ext4 only, no shared
namespace/network filesystem. OS locks do not exclude unaware writers.
**Testing:** Co-located pytest; existing frontend Vitest/Testing Library/Playwright scripts
and TypeScript build; black 420/isort/flake8; synthetic fakes beneath production guards.
**Target Platform:** Windows/Linux hosts; one host-loopback-published writable Docker desk
only on a root filesystem accepted by `RootContext`. Current Windows Docker Desktop bind
mount evidence is `9p` and denied; synthetic ext4 runtime was exercised, while host-network/
browser/Ollama and existing-fund lifecycle acceptance remain unrun.
**Project Type:** Local Python CLI/web server plus packaged React SPA.
**Performance Goals:** SC-009 local acknowledgment/status ≤2 seconds in ≥95% synthetic
observations excluding provider computation; bounded jobs, diagnostics and polling.
**Constraints:** No real brokerage/protected roots/runners/8765/paid calls in validation;
offline observation, immutable deployments/ledger bytes, no automatic runner starts/retries
or bounded-job resumption. Unknown/absent OS primitives fail closed.
**Scale/Scope:** One trusted local operator/root; 74 capabilities/six journeys; independent
deployments, finite scheduled authorizations and bounded backtests.
No unresolved design clarification remains; runtime risks are evidence gates, not passes.

## A3 decision supersession (2026-11-04)

The user explicitly accepted trusted single-writer operation for deliberately enabled
production writes. An operator must use an offline, root-specific acknowledgement tied to
the current enrollment/build and reviewed inventory. Fresh enrollment, existing-data
migration, relocation, environment defaults, PID/TTL values, cooperative locks and web
flags do not grant write authority. Missing, invalid, stale or revoked acknowledgement,
unsafe/mismatched roots, and known or unverified active legacy participants remain
read-only.

The operator takes responsibility for stopping and excluding other programs that can
reach the root: old CLI versions, cron, services, writable containers, scripts and other
processes. This is a declared trust assumption, not OS-enforced exclusion. Protocol locks,
leases and ownership checks still serialize cooperating participants; they do not fence
unaware or malicious same-account writers. Do not claim otherwise. Existing funds remain
read-only by default; migration is a supported read-only preparation path until the
separate acknowledgement is deliberately recorded.

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
| OS locks + reservation + durable journal | Cooperating-writer ownership and crash ambiguity; explicit operator trust handles unaware writers | Web mutex/PID/TTL cannot fence CLI, PID reuse or partial effects; no OS-enforcement claim is made for trusted single-writer mode. |
| Host writer/read-only container; SIM browser exemption | Namespace/account control cannot be inferred | Shared writable compose and claimed SIM parity conceal unsupported mutation. |

## Design sequence (not an executable task list)

1. Extract neutral TUI helpers and fixed-root/capability/provider bootstrap before execution
   routes; version private settings/credentials and complete domain editor validation.
2. Establish shared admission, explicit trusted-single-writer handover, owner handshake/durable journals;
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

**Historical planning decision (2026-10-31):** proceed to open main-targeting plan review.
Implementation continuation was explicitly authorized on 2026-11-04. Retirement remains
blocked until full required evidence passes; completing this continuation does not imply
retirement acceptance.
