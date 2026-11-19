# Contracts: Ollama Model Selection

**Date**: 2026-11-17 | **Spec**: [spec.md](../spec.md)

## C1: GET /api/settings — models array (extended response)

Existing behavior: backend builds `models` from the static registry (`web/app.py:481-487`, `web/services.py:2287-2319`).

**Change**: each Ollama entry in the `models` array carries the new classifier fields so the picker can render capability and cost-class state.

```json
{
  "models": [
    { "id": "gemma3:4b",    "provider": "ollama", "capability": "chat", "cost_class": "local" },
    { "id": "kimi-k3:cloud","provider": "ollama", "capability": "chat", "cost_class": "paid-cloud" }
  ]
}
```

- Non-Ollama providers' entries are unchanged (FR-011).
- The picker MUST visually distinguish `paid-cloud` entries (dispatch-gated) without implying they are free/local.

## C2: PUT/POST settings model write — error contract (clarified)

Existing: HTTP 400 with `Model is not in the supported provider catalog.` (`web/services.py:2430-2451`).

**Change**: rejection reasons become specific and remain credential-free (FR-003, FR-010):

| Condition | Status | Message shape |
|---|---|---|
| Unknown tag | 400 | `Model '<id>' is not in the supported provider catalog.` |
| Non-chat capability | 400 | `Model '<id>' is not chat-capable (<capability>).` |
| Paid-cloud in scheduled/unattended context | 400/403 | `Model '<id>' is paid/cloud and cannot be used in scheduled runs.` |
| Paid-cloud one-shot without authorization | 403 | `Model '<id>' requires explicit per-operation authorization.` |

Messages MUST contain no endpoint internals beyond the model id, and no credential material.

## C3: GET /api/catalog — static catalog (extended)

Same classifier fields as C1; remains static-source (`web/app.py:246-248`, `web/services.py:572-573`). No live `/api/tags` proxy endpoint is added (D1).

## C4: CLI surface (run.py)

- `--model <tag>`: accepts any catalog chat-capable tag; unknown tags fail fast with the catalog reason (no `captured runtime settings are unavailable` masking of model-validation failures — the mask stays only for genuine settings-capture failures).
- Scheduled/unattended entrypoints refuse `paid-cloud` selections before any dispatch (FR-007).

## C5: TUI preset behavior (corrected)

`tui/home.py:58-70` currently replaces an unknown preset with a catalog default on mount. New behavior: unknown persisted preset yields an explicit notice and no silent substitution (FR-003).

## Non-contracts (explicitly unchanged)

- Ollama inference adapter request construction (`llm/client.py:395-416`): model field, base URL default `http://127.0.0.1:11434`, loopback guardrails — unchanged.
- Endpoint policy (`runtime/endpoints.py`): no new endpoint flexibility; no endpoint derived from model text.
