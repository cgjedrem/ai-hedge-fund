# Implementation Plan: Local React Trading Desk

**Branch**: `cgjedrem-fictional-winner` | **Date**: 2026-10-30 | **Spec**: [spec.md](spec.md)
**Authorization**: User expressly requested autonomous implementation and gate decisions. No merge is authorized. This is additive to the TUI.

## Summary

Build a local FastAPI adapter around existing Python domain functions and a Vite React/TypeScript/Tailwind/shadcn frontend. Use a dark desk layout with home, fund browser/builder, paper details, reports, backtests, scorecards, model/key settings and command palette. Do not mount Textual screen instances or duplicate trading logic. Default read-only on the real root; offer isolated deterministic demo mode. Complete broad read parity and safe writes, label deferred destructive or process-owning actions.

## Technical Context

**Language/Version**: Python 3.11+, strict TypeScript, React.
**Primary Dependencies**: FastAPI/Uvicorn, Vite, Tailwind, shadcn/Radix, existing domain packages.
**Storage**: Existing YAML/JSON/hash-chained paper files; no database or format migration.
**Testing**: Co-located pytest; Vitest/Testing Library; production build browser smoke with Playwright.
**Target Platform**: Local Windows/Linux browser, Docker Compose via loopback publication.
**Project Type**: Additive web app plus local API.
**Performance Goals**: Useful local read pages without external-provider latency; background jobs do not block navigation.
**Constraints**: No secret echoes, no automated live calls, no protected-fund mutation. All assets local.
**Scale/Scope**: One user, one server process, eleven screen groups; bounded jobs.

## Constitution Check

| Principle | Pre-design | Post-design constraint |
|-----------|------------|------------------------|
| Ledger integrity | PASS | DTOs separate from persisted schemas; reuse mailbox and replay; no historical format changes |
| Paper/no paid dev loops | PASS | Explicit root/capability boundary; fake providers in tests/demo; real root defaults read-only |
| Tests | PASS | New API/frontend tests plus existing suite with exact documented baseline accounting |
| Determinism | PASS | Fixed fixture clock and fake execution, no data polling in tests |
| Surface consistency | PASS | FundSpec authoritative; TUI/CLI unchanged unless shared root override necessary |
| Style | PASS | black 420/isort/flake8 on changed Python; strict frontend build |

Red-team findings are binding design inputs in [red-team-findings-2026-10-30.md](red-team-findings-2026-10-30.md). Static plan approval is not runtime acceptance.

## Safety and Execution Design

- Server startup fixes capabilities: read-only, writes and network are separate; browsers cannot grant them. Protected names are denied server-side before adapter calls, including normalized case variants.
- Loopback CLI bind only. Exact Host/Origin checks, no permissive CORS, per-launch mutation token and same-origin requests. Container may bind internally only with host publication `127.0.0.1:PORT:PORT`; Linux override retains this boundary without host networking.
- Explicit data-root configuration before imports, inherited by children if any. Pass root arguments into domain helpers. No CLI/TUI startup initialization on real-root reads. Demo creates standalone synthetic data, never imports test fixtures.
- Contained resolved paths, conservative name grammar and symlink rejection. Casefold-colliding deployment targets refused. No replacement, deletion or redo initially unless independently proven safe and reviewed.
- Approval request carries server-served decision timestamp and source record hash. Re-read/replay, compare both, enforce existing expiry, call `Ledger.set_approval`; do not execute. Preserve existing verdict replacement semantics; do not impose an incompatible first-vote-wins engine policy.
- In-process per-fund locks serialize API mutations; this is not a cross-process lock. Engine runs/redo disabled while external ownership exists; if no safe shared lock exists, defer instead of claiming external-writer safety. Mailbox/halt uses existing atomic writes. Repeated verdict requests must not duplicate execution.
- Runner controls must verify ownership, not blindly kill PID-file PIDs. Fixture runner uses a fake adapter. If safe cross-platform ownership is unproven, expose disabled controls with reasons and mark parity gap.
- Bounded jobs, no auto retry; browser disconnect does not repeat/cancel ledger-writing work. Capture provider/model/universe on confirmation; serialize settings against active jobs. Cancel only at safe boundaries; unsupported cancellation explicit.
- Credential variables allowlisted; reject control characters/newlines, use existing persistence atomically, never return stored values or log bodies. Errors never echo input secrets.
- Render model/report strings as escaped React text, no raw HTML, local assets only, strict production CSP.
- Recorded NAV/curves/scorecards derive from records. Live estimates have distinct provenance/time/missing-data state; read-only default does not fetch external quotes. Display ledger verification errors and recorded timestamps.
- Tests deny external network/process adapters and clear provider credentials. Fakes sit below production guards; assertions include denial reason and absence of side effects.

## Project Structure

```text
specs/004-react-web-ui/
  spec.md, plan.md, research.md, data-model.md, quickstart.md
  contracts/http-api.md, tasks.md, acceptance-evidence.md
hedge_fund/web/
  app.py, services.py, schemas.py, __main__.py
  demo.py, test_*.py
frontend/
  package.json, package-lock.json, components.json
  src/components/ui/, src/pages/, src/lib/
  src/**/*.test.tsx, e2e/
Dockerfile.web
```

Keep presentation in frontend and domain adaptation/tests in hedge_fund/web. Package static build through launch/build command and Docker image; Node is a development/build dependency, not a production request dependency.

## Complexity Tracking

No constitution violations approved. User authorized noninteractive gate handling; red-team and plan-review evidence still required. Defer unsafe actions honestly rather than changing engine concurrency guarantees.
