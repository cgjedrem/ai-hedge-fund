# Implementation Plan: Saxo Demo Account Connection

**Branch**: `cgjedrem-verbose-winner` | **Date**: 2026-11-09 | **Spec**: [spec.md](spec.md)

**Input**: [Feature specification](spec.md)

## Summary

Add a distinct Saxo SIM credential mode for the vault-held 24-hour token, preserve the existing SIM-only OAuth flow, and provide read-only account inspection and explicit account selection. Fund preparation/execution is separately gated: both application root write admission and verified account-wide Saxo SIM ownership are required. No live-account support is present or implied.

## Technical Context

**Language/Version**: Python 3.11+, Poetry-managed (repository convention)

**Primary Dependencies**: Existing `requests`, `pydantic`, `textual`, and `typer`/CLI infrastructure; no new dependencies planned

**Storage**: Token remains in 1Password and is held in memory only; any future fund data must use a root admitted by the application

**Testing**: Co-located pytest tests under `hedge_fund/`; fake HTTP transport, synthetic vault provider, and synthetic roots only

**Target Platform**: Windows host and supported container deployments

**Docker integration boundary (2026-11-09, revised after explicit user approval)**:
The dated Spec005 1Password OP-FR-002 amendment now permits exactly the standalone
demo bearer for in-app GET-only SIM inspection. The nested
[onepassword-bridge\plan.md](onepassword-bridge/plan.md) defines separate capability,
private delivery and lease consumer; parent caveman review precedes implementation.
OP-FR-007 memory-only retention, the application-provider allowlist and SIM ownership
gate remain unchanged. Host inspection still resolves its own reference; a separate
`docker exec` CLI cannot consume backend memory. No bridge is implemented by this
documentation update. Existing eligible Docker topology is network-none without a
browser port: real in-app platform acceptance remains BLOCKED pending a reviewed
supported topology, not an allowlist tweak or automatic network change.

**Project Type**: Python application with CLI, TUI, broker adapter, and paper-fund runtime

**Performance Goals**: Connection and account inspection are operator-triggered; individual broker HTTP requests retain the existing 15-second timeout; bounded order-fill inspection retains its existing deadline and stops when the operator's run boundary or interruption is reached.

**Constraints**: SIM-only for both demo-token and legacy OAuth modes; OAuth behavior remains unchanged; no live-account support; no secret output; account inspection has no order side effects and requires explicit network consent; no paid-data calls; no unattended loop; root admission and Saxo SIM account ownership are independent gates; first order has separate explicit authorization

**Scale/Scope**: One operator, one explicitly selected Saxo SIM account, one dedicated fund and bounded manual run

## Constitution Check

- **I. Ledger integrity first — PASS**: Preserve ledger serialization and replay; never import or rewrite broker positions to conceal a mismatch.
- **II. Paper only, no unattended live risk — PASS with guardrails**: Use Saxo SIM only, no real endpoint, no schedule/unbounded loop, approval required, and separate first-order confirmation.
- **III. Tests co-located and green — PASS**: Add focused offline tests next to code; do not use paid data/model providers.
- **IV. Determinism and reproducibility — PASS**: Fake transport, synthetic secrets provider, and fake clock for token expiry and execution boundaries.
- **V. User-visible surfaces stay consistent — PASS**: The same explicitly selected account, broker, root, and approval state must be honored by CLI, TUI, and mandate/runtime paths.
- **VI. Style — PASS**: Follow Black line length 420, isort black profile, flake8; UTF-8 without BOM.
- **Write-admission stop condition**: No exception to existing root admission or SIM account-ownership controls is authorized. The target runtime provides root admission, but `require_sim_account_ownership()` fails closed with `ownership-unknown`; fund deployment and SIM mutation are BLOCKED. Deliver only the safe read-only connection surface; do not infer broker authority from local root admission.

## Project Structure

### Documentation

```text
specs/003-saxo-broker-adapter/addenda/demo-token-24h/
├── spec.md
├── plan.md
├── research.md
├── data-model.md
├── contracts/saxo-demo-connection.md
├── quickstart.md
├── acceptance-evidence.md # generated during implementation/evidence capture
└── tasks.md
```

### Source Code

```text
hedge_fund/
├── brokers/
│   ├── saxo.py                  # SIM token path, explicit account binding, read-only inspect
│   ├── factory.py               # explicit credential-mode selection
│   ├── saxo_auth.py             # existing SIM-only OAuth flow remains unchanged
│   ├── test_saxo*.py            # fake transport/token/account tests
│   └── test_factory.py          # mode-conflict and factory routing tests
├── run.py                       # root-independent read-only account inspection and root-bound operations
├── paths.py                     # explicit root selection without bypassing admission
├── paper/
│   ├── deployed.py              # persisted account binding and isolated deployment behavior
│   ├── tick.py                  # reconciliation and explicit execution gate
│   └── test_*.py                 # isolated-root and run-boundary tests
├── fund/
│   └── spec.py                  # validated optional Saxo SIM account binding
└── tui/
    └── builder.py               # consistent user-visible SIM/account/approval configuration
```

**Structure Decision**: Keep the feature in existing broker, fund, runtime, CLI, TUI, and co-located test packages. Do not add a parallel trading implementation or new dependency. Implement only the surfaces required by the approved requirements; if a surface's normal admission contract rejects the operation, do not route around it.

## Phase 0: Research

Completed in [research.md](research.md). The user-provided demo token is treated as an opaque, SIM-only bearer credential; the existing OAuth route is also SIM-only. The exact token provenance and validity still require a later user-authorized local read-only connection check. Legacy OAuth mandates without a bound account retain first-eligible selection; the new demo-token mode requires explicit account binding.

## Phase 1: Design

Completed in [data-model.md](data-model.md), [contracts/saxo-demo-connection.md](contracts/saxo-demo-connection.md), and [quickstart.md](quickstart.md). The credential mode and selected account are explicit; inspection cannot place orders; fund writes use an isolated root under existing admission; initial mismatch, missing permission, or denied admission fails closed.

## Complexity Tracking

| Added complexity | Why needed | Simpler alternative rejected because |
|---|---|---|
| Separate demo-token credential mode | Demo token lifetime and flow differ from existing OAuth | Reusing refresh-token semantics would send the token to the OAuth refresh endpoint and risk write-back corruption |
| Explicit account binding | Multiple compatible SIM accounts must not be silently conflated | First-match discovery does not prove which broker book the user intended |
| Separate root-admission and SIM-ownership gates | Local file authority and account-wide broker custody are independent | Treating local admission as proof of exclusive SIM control could authorize conflicting broker mutations |

## Timeout and bounded-run decision

Reuse Saxo's existing 15-second HTTP request timeout and the adapter's bounded order-fill inspection deadline. Stop on token rejection/expiry, the requested run boundary, or interruption; do not automatically resume or resubmit an uncertain order. Waiting indefinitely or blind-retrying an order was rejected because it violates bounded supervised operation and may duplicate an order that already reached Saxo.
