# Feature Specification: Ollama Model Selection

**Feature Branch**: `cgjedrem-cuddly-winner` (session worktree branch; `before_specify` git-feature hook intentionally not run — worktree sessions must not create branches)

**Created**: 2026-11-17

**Status**: Draft

**Input**: User description: "Ollama runtime model selection rejects the configured model despite Ollama listing it. The Ollama provider catalog accepts only `gemma3:4b`; a configuration selecting another daemon-listed tag (e.g. `kimi-k3:cloud`) fails validation. Permitted user-chosen Ollama models must be selectable consistently across CLI, web UI, and the analysis worker, with no silent fallback to gemma3:4b and no fake model support."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Configure a daemon-available Ollama model (Priority: P1)

The operator configures the engine to use an Ollama model tag other than the single hardcoded default — a tag the host Ollama daemon actually offers — via CLI flag, environment variable, or persisted settings, and the selection is accepted and honored identically by the CLI, the web settings surface, and the analysis worker.

**Why this priority**: This is the reported defect. Today only `gemma3:4b` passes validation, so every non-default selection fails before any inference is attempted. Fixing this restores the basic promise of a configurable local-model provider.

**Independent Test**: Configure a daemon-listed local chat tag through each configuration source (CLI, environment, persisted settings, web settings) and verify the same accept/reject outcome everywhere, with no inference call required to prove configuration acceptance.

**Acceptance Scenarios**:

1. **Given** a chat-capable tag is offered by the host daemon, **When** the operator selects it via CLI flag, environment variable, persisted settings, or the web settings page, **Then** the selection is accepted by every surface and recorded as the effective model.
2. **Given** a tag is not offered by the daemon and not otherwise approved, **When** the operator selects it, **Then** every surface rejects it with a clear reason and the previous/default selection remains in effect.
3. **Given** any rejected selection, **When** validation fails, **Then** the system MUST NOT silently substitute `gemma3:4b` or any other model.

---

### User Story 2 - See what is actually selectable (Priority: P2)

The operator opens the web settings model picker and sees which Ollama models are selectable per the static operator-approved list, with capability and cost-class (local vs paid/cloud, dispatch-gated) clearly indicated.

**Why this priority**: Configuration acceptance without visibility leaves the operator guessing which tags are valid; the picker is where the mismatch was first observed.

**Independent Test**: Open the settings picker and verify the displayed Ollama choices match the approved catalog with capability and paid/cloud indicators; verify unknown or non-chat tags are rejected on save with explicit reasons.

**Operator decision (2026-11-17, QA rework cycle 1):** FR-004, SC-004, and the US2 scenarios are amended to the static-list scope: the picker shows approved-list selectability with capability/cost-class indicators; live availability probing, offline detection, and malformed-metadata handling are out of scope. FR-009 (static approved list, no daemon cross-check) stands as decided. Approved in-session by the operator pending Gate 2 confirmation.

**Acceptance Scenarios**:

1. **Given** the approved static list contains several chat-capable tags, **When** the operator opens the picker, **Then** the selectable Ollama entries correspond to that list with capability and cost-class indicators.
2. **Given** a paid/cloud entry, **When** the operator views it in the picker, **Then** it is visibly marked dispatch-gated (paid/cloud), never presented as a free local model.
3. **Given** an unknown or non-chat tag, **When** the operator attempts to save it, **Then** the surface rejects it with an explicit, credential-free reason.

---

### User Story 3 - Cloud-labelled Ollama tags under explicit policy (Priority: P3)

The operator may select a cloud-labelled Ollama tag (e.g. a `:cloud`-suffixed tag proxied by the host daemon) only under the engine's paid/cloud governance: never in scheduled or unattended loops, and for one-shot operations only with explicit per-operation authorization and an enforced budget.

**Why this priority**: The tag the operator originally wanted is cloud-labelled. Existing policy deliberately classifies cloud-labelled models as paid/cloud even via loopback; this story exists only if the operator confirms that scope.

**Independent Test**: Attempt to use a cloud-labelled tag (a) in a scheduled/unattended run — must be refused — and (b) in a one-shot operation without authorization — must be refused with a clear, credential-free reason.

**Acceptance Scenarios**:

1. **Given** a cloud-labelled tag is configured, **When** any scheduled or unattended path attempts to use it, **Then** it is refused regardless of credentials present in the environment.
2. **Given** a cloud-labelled tag is selected for a one-shot operation without explicit authorization, **When** validation runs, **Then** it is refused with a clear reason naming the authorization requirement.

**Operator decision (2026-11-17):** Cloud-suffixed tags proxied by the host daemon ARE in scope — as governed one-shot selections under this P3 story. The operator's target model is `kimi-k3:cloud`. A paid/cloud authorization design (per-operation authorization + enforced budget, no scheduled loops) is therefore required as part of this feature.

---

### Edge Cases

- Daemon offline or unreachable at selection time and at run time: surfaces must show/refuse with an explicit state, never silently substitute another model.
- Daemon metadata is malformed, empty, or changes between selection and run: configuration acceptance, metadata availability, and inference success are distinct states and must not be conflated.
- Selected tag is embedding-only or OCR-only (not chat-capable): must be rejected for analysis use with a clear capability reason.
- Endpoint policy denial (non-loopback endpoint, redirect, or endpoint text derived from the model name): must be refused by the network policy layer; this feature adds no new endpoint flexibility.
- Authentication failure on a cloud-proxied tag: surfaced as an authorization/availability error containing no credential material.
- Configuration precedence conflicts (CLI flag vs environment vs persisted settings vs defaults): resolution order stays launch > environment > persisted > default, and persisted selections survive restart.
- Existing non-Ollama providers and their catalogs must behave byte-identically to before this feature.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST accept operator-chosen Ollama model tags beyond `gemma3:4b` when the tag is validated as an available, chat-capable offering (per the availability source chosen under FR-009).
- **FR-002**: Model validation MUST produce the same accept/reject outcome across the CLI, environment-based configuration, persisted settings, the web settings write path, and the analysis worker.
- **FR-003**: A rejected selection MUST fail with an explicit, human-readable reason; the system MUST NOT silently substitute `gemma3:4b` or any other model, on any surface (including the TUI preset fallback behavior).
- **FR-004**: The web settings model picker MUST present the selectable Ollama models from the approved static list with their capability and cost-class state (including a paid/cloud dispatch-gated indicator). Live availability probing, offline detection, and malformed-metadata handling are OUT OF SCOPE for this feature (static-list decision, FR-009); the picker presents configured selectability, not daemon-reported availability.
- **FR-005**: Configuration precedence MUST remain launch override > process environment > persisted root settings > defaults, and a persisted selection MUST survive an application restart.
- **FR-006**: Only chat-capable Ollama models MUST be selectable for analysis; embedding-only or OCR-only tags MUST be rejected with a capability-specific reason.
- **FR-007**: Cloud-labelled Ollama tags (including the operator's selected `kimi-k3:cloud`) MUST remain classified as paid/cloud: prohibited in scheduled or unattended loops, and permitted for one-shot operations only with explicit per-operation authorization and an enforced budget. Credential presence in the environment MUST NOT constitute authorization.
- **FR-008**: Existing endpoint/network guardrails MUST be preserved unchanged: loopback-only endpoints, pinned destinations, no ambient proxy use, no endpoint derived from model text, no new network surface for inference.
- **FR-009**: Availability truth is a **static operator-approved tag list** (operator decision, 2026-11-17): approved tags are validated against that list and, when the daemon is reachable, cross-checked against daemon metadata; the list is the offline-safe baseline. Live discovery is out of scope for this feature.
- **FR-010**: Error messages surfaced to the operator MUST NOT contain credential material, API keys, or secret values under any failure mode.
- **FR-011**: Catalogs and behavior of all non-Ollama providers MUST remain unchanged.
- **FR-012**: Configuration acceptance, metadata availability, and inference success MUST be distinguishable outcomes; this feature validates the first two and does not require live inference to prove configuration acceptance.

### Key Entities

- **Model catalog entry**: a selectable model — identifier, provider, capability class (chat/embedding/OCR), cost class (local vs paid/cloud), and availability state (available, unavailable, offline-unknown).
- **Model selection**: the operator's chosen model with its configuration source (launch, environment, persisted, default) and its validation outcome (accepted, rejected-with-reason).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of configuration surfaces (CLI flag, environment, persisted settings, web settings) produce identical accept/reject outcomes for the same model tag.
- **SC-002**: Zero silent model substitutions: every rejected selection yields an explicit reason on every surface, verified by tests covering each surface.
- **SC-003**: An operator can select any catalog-listed local chat-capable model (currently `gemma3:4b`) and have it honored by an analysis run on the first attempt; adding a new approved tag is a one-line catalog entry with no other list edits.
- **SC-004**: With the daemon unreachable, configuration validation still works from the static catalog (offline-safe), and paid/cloud dispatch is refused with an explicit reason; no analysis run ever starts with a substituted model.
- **SC-005**: Full existing test suite remains green; non-Ollama provider behavior is demonstrably unchanged.

## Assumptions

- The supported Ollama endpoint is the host daemon on loopback; non-loopback or direct cloud API endpoints are out of scope unless the operator explicitly expands scope.
- The daemon's model metadata is the natural source of availability truth when reachable; the exact mechanism (static list vs discovery vs hybrid) is an open user decision (FR-009).
- No live inference is required to validate that a configuration is accepted; inference verification is a separate, later, explicitly authorized step.
- The operator's target model identifier is resolved (2026-11-17): `kimi-k3:cloud`, the cloud-labelled tag offered by the host Ollama daemon. It is distinct from `kimi-k3` on the Moonshot provider, which is out of scope.
- Free yfinance data remains the market-data path; this feature touches model selection only, not data providers.
- No real-fund access, no broker orders, no paid-provider spend in development or tests; all new tests use mocked model metadata.
