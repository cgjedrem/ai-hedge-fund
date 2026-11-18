# Phase 0 Research: Ollama Model Selection

**Date**: 2026-11-17 | **Spec**: [spec.md](spec.md) | **Baseline**: `e6f04d2` (+ spec commits)

All findings below come from read-only discovery on the pinned baseline; no live Ollama inference or paid-provider calls were made.

## Root Cause (verified)

Three stacked validation layers each independently restrict Ollama to `gemma3:4b`:

1. **Static catalog** — `hedge_fund/llm/api_models.json:47-50` lists only `gemma3:4b` for Ollama; `llm/registry.py:48-67` resolves providers by exact model ID from that file.
2. **Runtime configuration whitelist** — `hedge_fund/runtime/configuration.py:29-37,526-541` maintains a separate model-to-provider whitelist; unknown IDs raise `model is not in the supported catalog`.
3. **Policy/endpoint allowlists** — `hedge_fund/runtime/policy.py:36,270-273` and `runtime/endpoints.py:132-151` approve only `gemma3:4b` as a local Ollama model. Adding a catalog row alone cannot make another tag callable.

Cloud-labelled Ollama tags are deliberately classified paid/cloud even via loopback (`policy.py:270-273,500-502`; `docs/governance/web-migration-contract.md:20-27`). The verified paid cost models currently exclude Ollama (`runtime/costs.py:22-28`).

## Decisions

### D1: Availability source = static operator-approved tag list

- **Decision**: Extend the static catalog/allowlists with operator-approved tags; no live `/api/tags` discovery in this feature.
- **Rationale**: Operator decision 2026-11-17 ("we just add the model to a static list"). Offline-safe, smallest change, no new network surface (FR-008).
- **Alternatives considered**: live daemon discovery (rejected — new network operation, offline-fallback complexity); hybrid (deferred as possible follow-up).

### D2: Cloud tags in scope as governed one-shot selections

- **Decision**: `kimi-k3:cloud` enters the approved list classified paid/cloud. Scheduled/unattended use stays prohibited; one-shot use requires explicit per-operation authorization and an enforced budget per existing policy machinery.
- **Rationale**: Operator decision 2026-11-17 ("we go full cloud now kimi k3:cloud"), bounded by Constitution Principle II.
- **Alternatives considered**: local-only scope (rejected by operator); ungoverned cloud use (constitutionally prohibited).

### D3: Unify the three validation layers via the catalog as single source

- **Decision**: Extend `api_models.json` entries with capability class (chat/embedding/OCR) and cost class (local/paid-cloud) metadata; make `configuration.py` whitelist and `policy.py`/`endpoints.py` allowlists derive from (or be mechanically consistent with) the catalog instead of maintaining parallel literals.
- **Rationale**: The defect exists precisely because three lists must be edited in lockstep; single-sourcing prevents recurrence and satisfies FR-002 consistency.
- **Alternatives considered**: editing each list manually (rejected — proven fragile; the current bug is the evidence).

### D4: No silent substitution anywhere

- **Decision**: Rejected selections raise/return explicit reasons on every surface. The TUI preset fallback (`tui/home.py:58-70`, which silently replaces an unknown preset with a catalog default) is changed to an explicit rejection/notice.
- **Rationale**: FR-003; silent fallback is how misconfiguration becomes invisible spend.
- **Alternatives considered**: keep TUI fallback (rejected — violates FR-003).

### D5: Target identifier = `kimi-k3.1-pro:cloud` (Ollama), not Moonshot `kimi-k3`

- **Decision (2026-11-18, supersedes the 2026-11-17 choice of `kimi-k3:cloud`)**: The operator's target is the Ollama cloud tag `kimi-k3.1-pro:cloud` (Kimi K3.1 Pro). `kimi-k3:cloud` stays in the approved catalog; the Moonshot provider's `kimi-k3` remains out of scope.
- **Rationale**: Operator decision 2026-11-18 — K3.1 Pro is the model the operator originally meant by "Kimi K3.1" and is cheaper for their use.
- **Note**: the exact daemon tag must exist on the host daemon (earlier metadata listed `kimi-k3:cloud` but not `kimi-k3.1-pro:cloud`; the operator may need to pull it).

### D7: Ollama cloud cost model — operator-supplied pricing (2026-11-18)

- **Decision**: add the cost-model entry for `kimi-k3.1-pro:cloud` with operator-declared pricing sourced from the Ollama model page: $2.00 per 1M input tokens, $0.20 per 1M cached-input tokens, $10.00 per 1M output tokens; 1M-token context. Record it as operator-declared with that provenance and date. Entry for `kimi-k3.1-pro:cloud` only; other cloud tags remain without verified cost models and keep refusing dispatch.
- **Consequence (QA caveat M-7)**: adding a verified cost model makes authorized one-shot dispatch technically reachable; the transport/authorization/budget path and `llm/client.py:308` authorization propagation MUST be re-reviewed together before this is considered enabled.
- **Recorded assumption (QA delta review I-2, 2026-11-18)**: the $3.31072 upper bound assumes the Ollama cloud service enforces `num_predict` as the billed output cap for `:cloud` models, and that reasoning/thinking tokens are billed within it. Neither is verified against the live service. Mitigation: hard per-attempt and per-operation budget caps apply regardless; if Ollama bills beyond `num_predict`, the bound underestimates. Operator accepts this assumption pending live observation.
- **Superseded text (2026-11-17)**: pricing unavailable at planning time; refusal mechanism required until operator supplies it.

### D6: Prior art — extend within policy, never restore pre-4177741 behavior

- **Decision**: Commit `3f7bea8` (tree contained the four Ollama cloud tags) and `487091d`/`70da073` (ChatOllama integration, empty-content retry) are reference patterns. `4177741` removed cloud tags to enforce provider dispatch authority with verified cost models — this feature re-adds cloud tags **with** cost-class metadata and policy gating, reconciling rather than reverting.
- **Rationale**: Preserves the dispatch-authority invariant that `4177741` established.

### D7-original (2026-11-17): Ollama cloud cost model is an operator-input dependency — SUPERSEDED by D7 (2026-11-18) above

- **Decision (historical)**: `runtime/costs.py` currently has no verified Ollama cost model, and paid dispatch is limited to verified cost models (per `4177741`). Enabling authorized one-shot dispatch of `kimi-k3:cloud` requires a cost-model entry. Pricing cannot be verified from source alone; the implementation MUST either (a) add the entry with operator-declared pricing recorded as such, or (b) keep cloud-tag dispatch refused with a clear "no verified cost model" reason until the operator supplies it. Configuration acceptance (catalog/settings/picker) does not depend on this.
- **Rationale**: No implicit paid fallback; no invented pricing.
- **Resolution (2026-11-18)**: the operator supplied pricing for `kimi-k3.1-pro:cloud`; see D7 above.

## Configuration Precedence (verified, to preserve)

Launch override (`--model`) > process environment (`HEDGE_FUND_LLM_MODEL`/`_PROVIDER`/`_ENDPOINT`) > persisted root settings (`runtime/private/v1/settings.json`) > defaults (`gemma3:4b`/Ollama). Root `.env` loading is opt-in via `--load-dotenv`; its allowlist includes the model but not provider/endpoint (`paths.py:32-37`). CLI masks config errors as `captured runtime settings are unavailable` (`run.py:979-980`); web writes return HTTP 400 `Model is not in the supported provider catalog.` (`web/services.py:2430-2451`); `make_llm` raises `LLM model provider is unknown` (`llm/client.py:295-298`).

## Guardrails to Preserve (verified)

- Loopback-only endpoint literals, pinned destinations, denied async transport/redirects, disabled ambient proxies: `runtime/endpoints.py:117-151,157-192,195-208`; `llm/client.py:403-414`.
- Writer map AST scan (`runtime/test_writer_map.py`) — any new raw write needs a WRITER_MAP entry.
- No credential material in any error/log path (FR-010).

## Unverified

- Host daemon's actual tag list and cloud billing/capabilities (source-only discovery; assignment forbids live probing for research).
- Installed `langchain_ollama` wire format (package source unavailable to the explorer).
- Ollama cloud pricing (operator input required — D7).
