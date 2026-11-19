# Phase 1 Data Model: Ollama Model Selection

**Date**: 2026-11-17 | **Spec**: [spec.md](spec.md) | **Research**: [research.md](research.md)

## Entities

### Model Catalog Entry (extended)

Existing catalog entries (`llm/api_models.json`) gain two classifier fields; all other providers' entries remain byte-identical in meaning (FR-011).

| Field | Type | Values | Notes |
|---|---|---|---|
| `id` | string | e.g. `gemma3:4b`, `kimi-k3:cloud` | Exact Ollama tag; never invented |
| `provider` | string | `ollama` | Registry key |
| `capability` | enum | `chat`, `embedding`, `ocr` | FR-006: only `chat` selectable for analysis |
| `cost_class` | enum | `local`, `paid-cloud` | FR-007: `:cloud`-suffixed tags are `paid-cloud` |
| `display_name` | string | human label | picker rendering |

**Validation rules**
- A tag with `cost_class: paid-cloud` is catalog-visible but dispatch-gated (FR-007).
- A tag with `capability != chat` is rejected for analysis selection with a capability-specific reason (FR-006).
- Unknown tags (not in catalog) are rejected with an explicit reason on every surface (FR-002, FR-003).

**Initial Ollama entries**

| id | capability | cost_class |
|---|---|---|
| `gemma3:4b` | chat | local |
| `kimi-k3:cloud` | chat | paid-cloud |
| `kimi-k3.1-pro:cloud` | chat | paid-cloud |

(Operator target as of 2026-11-18: `kimi-k3.1-pro:cloud`. Additional daemon-listed tags — `glm-5.3:cloud`, `glm-5.3-flash:cloud`, `minimax-m3:cloud` — are NOT added unless the operator approves them; `nomic-embed-text:latest` and `glm-ocr:latest` are non-chat capabilities and excluded from the chat catalog.)

### Model Selection (existing, behavior specified)

| Field | Values |
|---|---|
| `model` | catalog entry id |
| `source` | `launch` / `environment` / `persisted` / `default` |
| `validation` | `accepted` / `rejected(reason)` — reason is explicit, credential-free |

Precedence (unchanged): launch > environment > persisted > default. Persisted selections survive restart (FR-005).

### Availability State (presentation only, no live discovery)

| State | Meaning |
|---|---|
| `approved` | In the static approved list (offline-safe baseline) |
| `dispatch-gated` | `paid-cloud` entry: selectable for configuration, requires per-operation authorization + verified cost model to run |

Since D1 chose a static list, availability states derive from catalog metadata only; no daemon round-trip is introduced.

## State Transitions

Selection validation is stateless per surface; the only transition that matters:

```
configured(model) -> validate(model) -> accepted            (chat-capable, in catalog)
                                     -> rejected(reason)    (unknown / non-chat / policy-refused)
```

A rejected validation NEVER transitions to a substituted model (FR-003); the prior effective selection remains.
