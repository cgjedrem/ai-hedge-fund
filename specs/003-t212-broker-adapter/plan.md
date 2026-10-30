# Implementation Plan: Trading 212 Broker Adapter

**Branch**: `003-t212-broker-adapter` (worktree branch: `cgjedrem-yfinance-provider-setup`) | **Date**: 2026-10-30 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/003-t212-broker-adapter/spec.md`

## Summary

Add Trading 212 as a pluggable execution broker for paper funds, targeting T212's **demo** environment only. A new `T212Broker` implements the existing three-method `Broker` protocol (`positions()`, `cash()`, `place_order()` — fill-completely-or-raise) against T212's REST API with HTTP Basic auth. API credentials are resolved at startup from 1Password via `op://` secret references (plaintext env values remain supported); secrets are never persisted or logged. Broker selection becomes a per-fund mandate setting (`broker: paper | t212`), byte-compatible with existing deployed funds. The external broker's reported book is authoritative and reconciled before every session; the redo path is refused for externally-brokered funds.

## Technical Context

**Language/Version**: Python 3.11 (Poetry)

**Primary Dependencies**: `requests` ^2.32.0 (already a dependency — no new packages), `pydantic` (models), 1Password CLI (`op`) as an external subprocess for secret resolution

**Storage**: No new storage. T212 funds reuse the existing deployed-fund layout (`fund.yaml`, `ledger/`, `events.jsonl`); `broker.json` is not used for T212 funds (the broker's own books are authoritative). Instruments list cached in memory (~1h TTL).

**Testing**: pytest, co-located (`hedge_fund/brokers/test_t212.py`, `hedge_fund/secrets/test_secrets.py`, ...). All HTTP interactions via a fake transport + recorded JSON fixtures — **no test ever touches the network** (constitution II).

**Target Platform**: Windows host + Docker runner (Linux container). The 1Password CLI must be reachable in both contexts: desktop-app unlock interactively on the host, service-account token (`OP_SERVICE_ACCOUNT_TOKEN`) unattended in Docker.

**Project Type**: library + CLI + TUI (existing single-package app `hedge_fund/`)

**Performance Goals**: One session's rebalance (<= ~20 orders) completes within the existing tick budget; per-order fill polling respects T212's 1 req/s order-status limit.

**Constraints**: T212 API is **beta** and **non-idempotent** for order placement (blind retries can duplicate orders); per-account rate limits (market orders 50/min, order status 1/s, positions 1/s, account summary 1/5s, instruments 1/50s); quantities carry at most 4 decimals; demo CSV export is unavailable; live (real-money) environment is hard-out-of-scope.

**Scale/Scope**: One user, a handful of funds, 9-ticker universe, daily cadence. Small surface: one adapter module, one secrets module, spec/CLI/TUI wiring.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Ledger integrity first | PASS | Fills recorded in the existing hash-chained ledger with actual broker prices; external book is authoritative and reconciled before trading (FR-005); redo path refuses external brokers (cannot rewrite a book we don't own); never-overshoot-cash sizing unchanged. New fund.yaml key `broker` is popped from serialization when it equals the default `"paper"`, preserving byte-compat with existing deployed funds (same pattern as `approval_required`). |
| II. Paper only, no unattended live risk | PASS | Adapter targets `https://demo.trading212.com` only; the live base URL is not constructible through configuration (demo-only constant). No paid data providers touched; yfinance path unchanged; tests are network-free. |
| III. Tests co-located and green | PASS | New tests co-located under `hedge_fund/`; suite must stay green apart from the 6 documented Windows baseline failures. |
| IV. Determinism and reproducibility | PASS | All adapter logic tested against recorded fixtures with a fake clock; live fills are recorded in the ledger like any other fill, so sessions remain replayable from the ledger. |
| V. User-visible surfaces stay consistent | PASS | `broker` is settable in the mandate, validated in `FundSpec`, honored by the scheduler/tick, and displayed in TUI fund detail + status output. |
| VI. Style | PASS | black line-length 420, isort black profile, flake8; no BOM in YAML/spec files. |

**Post-design re-check (Phase 1)**: Still passes — see Complexity Tracking (empty; no violations).

## Project Structure

### Documentation (this feature)

```text
specs/003-t212-broker-adapter/
├── plan.md              # This file
├── research.md          # Phase 0 output: T212 API reference + design decisions
├── data-model.md        # Phase 1 output: entities, config shapes, state machines
├── quickstart.md        # Phase 1 output: end-to-end validation guide
├── contracts/
│   └── t212-adapter.md  # Phase 1 output: Broker protocol contract + T212 API surface + secrets contract
└── tasks.md             # Phase 2 output (/speckit-tasks)
```

### Source Code (repository root)

```text
hedge_fund/
├── brokers/
│   ├── protocol.py        # unchanged — T212Broker satisfies it structurally
│   ├── models.py          # unchanged — Order/Fill/Position reused as-is
│   ├── t212.py            # NEW: T212Broker + T212Client (requests-based) + ticker mapping + polling
│   ├── test_t212.py       # NEW: unit + contract tests over fake transport/fixtures
│   └── __init__.py        # export T212Broker
├── secrets/
│   ├── __init__.py        # NEW: resolve_secret() — op:// references via 1Password CLI, plaintext passthrough
│   └── test_secrets.py    # NEW
├── fund/
│   └── spec.py            # FundSpec: add `broker: Literal["paper","t212"] = "paper"` (popped when default)
├── paper/
│   ├── deployed.py        # broker factory: build the right broker from the deployed spec
│   └── tick.py            # use the factory; refuse redo for external brokers
├── tui/
│   └── paper_view.py      # show broker name on fund detail
└── run.py                 # status output shows broker name
```

**Structure Decision**: Single-package layout unchanged; the adapter lives beside `sim.py`/`paper.py` in `hedge_fund/brokers/`, and secret resolution is a small standalone module (`hedge_fund/secrets/`) so it is reusable and independently testable. No new top-level directories.

## Complexity Tracking

> No constitution violations — table intentionally empty.

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|