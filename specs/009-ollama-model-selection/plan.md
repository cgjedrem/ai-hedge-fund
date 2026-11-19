# Implementation Plan: Ollama Model Selection

**Branch**: `cgjedrem-cuddly-winner` (session worktree branch; spec-kit feature directory `specs/009-ollama-model-selection`) | **Date**: 2026-11-17 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/009-ollama-model-selection/spec.md`

## Summary

The Ollama provider accepts only `gemma3:4b` because three independent validation layers (static catalog, runtime configuration whitelist, policy/endpoint allowlists) each hardcode it. This feature adds operator-approved tags — target `kimi-k3:cloud` — to a single-sourced catalog carrying capability (`chat`/`embedding`/`ocr`) and cost-class (`local`/`paid-cloud`) metadata, aligns all validation layers with it, makes every rejection explicit (no silent `gemma3:4b` substitution, including the TUI preset fallback), and keeps cloud-labelled tags under paid/cloud governance: no scheduled loops, one-shot only with explicit per-operation authorization, enforced budget, and a verified cost model. Availability source is a static operator-approved list (operator decision); no live daemon discovery. All endpoint/network guardrails and non-Ollama providers remain unchanged.

## Technical Context

**Language/Version**: Python 3.11 (Poetry); React/TypeScript web desk

**Primary Dependencies**: langchain_ollama (`ChatOllama`), FastAPI-style web layer, existing runtime policy/endpoint machinery

**Storage**: `hedge_fund/llm/api_models.json` (static catalog); `runtime/private/v1/settings.json` (persisted selection)

**Testing**: `poetry run pytest hedge_fund -q` — tests co-located under `hedge_fund/` (Principle III)

**Target Platform**: Windows + Linux dev; host Ollama daemon on loopback

**Project Type**: single Python package + React frontend

**Performance Goals**: N/A — configuration/validation paths only

**Constraints**: offline-capable validation (static list); loopback-only endpoints; no paid-provider spend in tests; no silent model substitution; no credential material in errors

**Scale/Scope**: ~8 source files touched (see Project Structure), plus co-located tests; no new services, no new network endpoints

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Verdict | Notes |
|---|---|---|
| I. Ledger integrity | PASS | No ledger serialization or replay paths touched |
| II. Paper only, no unattended live risk | PASS with design obligation | Cloud tags stay paid/cloud class: scheduled loops refuse them; one-shot requires explicit per-operation authorization + enforced budget + verified cost model (D7). Credential presence never authorizes. Tests use mocked metadata only |
| III. Tests co-located and green | PASS | New tests co-located; full suite required green before acceptance |
| IV. Determinism | PASS | Static catalog keeps validation deterministic; no live discovery |
| V. Surfaces stay consistent | PASS | FR-002 mandates CLI/env/persisted/web parity; picker reflects catalog |
| VI. Style | PASS | black 420, isort, flake8; no BOM in YAML/spec files |

*Post-Phase-1 re-check: no design element introduced a violation. No complexity justifications required.*

**Gate extensions note**: the red-team gate (Principle VIII) is NOT adopted in this repo's constitution and NOT wired in `.specify/extensions.yml`; the spec does match the `ai_llm` trigger informally. The paid/cloud authorization surface is the sensitive area; a red-team run is offered as an operator option, not required by the adopted constitution. The plan-review-gate extension is likewise not configured in this repo; Gate 1 user approval (this pipeline) is the operative pre-implementation gate.

## Project Structure

### Documentation (this feature)

```text
specs/009-ollama-model-selection/
├── plan.md              # This file
├── research.md          # Phase 0 output — root cause, decisions D1-D7
├── data-model.md        # Phase 1 output — catalog entry / selection entities
├── quickstart.md        # Phase 1 output — validation scenarios V1-V8
├── contracts/
│   └── contracts.md     # Phase 1 output — C1-C5 API/CLI/TUI contracts
├── checklists/
│   └── requirements.md  # Spec quality checklist (all passing)
└── tasks.md             # Phase 2 output (/speckit-tasks — after Gate 1 approval)
```

### Source Code (repository root)

```text
hedge_fund/
├── llm/
│   ├── api_models.json          # add kimi-k3:cloud with capability/cost_class metadata
│   ├── registry.py              # expose classifiers; keep provider resolution
│   ├── client.py                # unchanged wire path; classifiers inform dispatch gating
│   └── test_client.py           # extended: new-tag construction, capability rejection
├── runtime/
│   ├── configuration.py         # whitelist derives from catalog; explicit reject reasons
│   ├── policy.py                # paid-cloud classification keyed on cost_class metadata
│   ├── endpoints.py             # guardrails unchanged (verify-only)
│   ├── costs.py                 # Ollama cloud cost-model entry (operator input, D7)
│   ├── test_capture.py          # precedence + consistency + explicit-rejection tests
│   ├── test_policy.py           # cloud classification, scheduled refusal, one-shot authz
│   └── test_dispatch.py         # loopback transport unchanged; gated dispatch tests
├── web/
│   ├── services.py              # settings/catalog responses carry classifiers; error contract C2
│   ├── app.py                   # pass-through (verify-only)
│   └── test_settings.py         # picker data + rejection contract tests
├── tui/
│   └── home.py                  # no silent preset substitution; explicit notice
└── run.py                       # CLI model-validation error surfacing (no masking)

frontend/
└── src/pages/settings.tsx       # picker renders capability/cost_class; paid-cloud indicator
```

**Structure Decision**: Existing single-package layout with co-located tests; React settings page is the only frontend touchpoint. No new projects or services.

## Complexity Tracking

No constitution violations requiring justification.
