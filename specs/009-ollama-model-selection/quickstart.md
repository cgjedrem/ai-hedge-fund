# Quickstart Validation: Ollama Model Selection

**Date**: 2026-11-17 | **Spec**: [spec.md](../spec.md) | **Contracts**: [contracts/contracts.md](contracts/contracts.md)

All validation uses mocked model metadata. No live Ollama inference, no paid-provider credits, no real funds (Constitution II/III).

## Prerequisites

- Repo worktree on the feature branch; `poetry install` already satisfied.
- Tests: `poetry run pytest hedge_fund -q` (full suite must stay green — Principle III).

## Validation Scenarios

### V1 — Configuration acceptance consistency (FR-001, FR-002, SC-001)

1. Select `kimi-k3:cloud` via each source in turn: `--model` flag, `HEDGE_FUND_LLM_MODEL` env, persisted settings write, web settings API write.
2. **Expected**: identical acceptance on every surface; effective model recorded as `kimi-k3:cloud` with correct source attribution.
3. Select an unknown tag (e.g. `kimi-k3.1:latest`) via each surface.
4. **Expected**: identical explicit rejection on every surface; prior effective selection unchanged; no substitution.

### V2 — No silent substitution (FR-003, SC-002)

1. Persist an unknown/invalid preset, then mount the TUI home screen.
2. **Expected**: explicit notice of the invalid preset; the effective model is NOT silently replaced.

### V3 — Capability filtering (FR-006)

1. Attempt to select an embedding-only tag (`nomic-embed-text:latest`) or OCR tag (`glm-ocr:latest`).
2. **Expected**: rejection with a capability-specific reason on all surfaces.

### V4 — Paid/cloud governance (FR-007)

1. Configure `kimi-k3:cloud` and attempt a scheduled/unattended run.
2. **Expected**: refusal naming the scheduled-cloud prohibition, regardless of environment credentials.
3. Attempt a one-shot operation without explicit authorization.
4. **Expected**: refusal naming the authorization requirement.
5. (Operator-dependent, D7) With explicit per-operation authorization, a verified cost model, and an enforced budget: one-shot dispatch is permitted; without a verified cost model it remains refused with that exact reason.

### V5 — Picker presentation (FR-004)

1. `GET /api/settings` and `GET /api/catalog`.
2. **Expected**: Ollama entries carry `capability` and `cost_class`; the settings page renders `kimi-k3:cloud` as selectable-but-dispatch-gated (paid/cloud indicator), never as a free local model.

### V6 — Precedence and persistence (FR-005)

1. Set differing models in persisted settings, environment, and launch flag.
2. **Expected**: launch wins over environment wins over persisted wins over default.
3. Persist `kimi-k3:cloud`, restart the app process.
4. **Expected**: selection survives restart.

### V7 — Safe failure, no secrets (FR-008, FR-010)

1. Point the endpoint override at a non-loopback host (test fixture only).
2. **Expected**: endpoint policy refusal; error text contains the model id at most — no credential material, no derived endpoint.

### V8 — Existing providers unchanged (FR-011, SC-005)

1. Run the full suite; spot-check OpenAI/Moonshot catalog entries and validation outcomes against baseline.
2. **Expected**: byte-identical catalog semantics for non-Ollama providers; suite green.

## Live bounded test (deferred, operator-gated)

A live `kimi-k3:cloud` inference check happens only after: (a) implementation merged, (b) operator supplies/approves the cost-model input (D7), (c) explicit per-operation authorization with a stated budget. It is NOT part of this feature's test suite.
