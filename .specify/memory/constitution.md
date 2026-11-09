# ai-hedge-fund Constitution

## Preamble

This repo is a personal paper-trading hedge-fund engine (Python 3.11 + Poetry, React web desk,
hash-chained paper ledgers). The constitution binds every feature, bugfix, and refactor.
Non-negotiable principles are marked MUST; everything else is SHOULD with judgment allowed.

## Principles

### I. Ledger integrity first (MUST)

Session records, checkpoints, and broker books are hash-chained. New code MUST keep old
records replayable byte-identically: never change serialization of existing fields without a
documented migration, never rewrite history except through the explicit redo path
(`paper tick --again`), and never break the never-overshoot-cash invariant in sizing.

### II. Paper only, no unattended live risk (MUST)

The engine trades paper. No feature may place real orders or call paid providers by default.
Free yfinance data MUST work with zero credentials. Explicit operator authorization MAY
permit scheduled paper runners using free data and genuinely local models, scoped to one
deployment and frozen configuration with finite expiry, session and resource bounds.
Unbounded unattended data loops and all scheduled paid-data or cloud-LLM loops are prohibited.
Cloud-labelled/keyless hosted models are in the paid/cloud class, not a local-model exception.
Paid one-shot operations and backtests require explicit per-operation authorization and an
enforced budget; environment variables and credential presence never constitute authorization.
Tests and development loops MUST NOT spend paid-provider credits.

### III. Tests co-located and green (MUST)

Tests live next to code under `hedge_fund/` and run with `poetry run pytest hedge_fund -q`.
A change is done when the full suite passes, or every remaining failure is individually
evidenced as unchanged baseline with exact test ID, expected/observed result, source/build,
platform, recorded time, fixture provenance and reproduction on the pre-change revision.
Historically reported Windows strftime, redo rename, signal and file-mode anomalies are
candidates to reproduce, not blanket exemptions. Interrupted/inconclusive suites are not
passes. No new failure is excused; do not repair unrelated baseline defects.
Required platform/runtime evidence that is blocked remains blocked.

### IV. Determinism and reproducibility (SHOULD)

Prefer recorded clocks, seeded randomness, and cacheable LLM calls so any session can be
replayed. Side effects (fills, costs, NAV) must be derivable from the ledger alone.

### V. User-visible surfaces stay consistent (SHOULD)

CLI (`run.py`), React web desk, and mandate YAML must agree on fund configuration. A setting
is only "configurable" when it is settable in the mandate, validated in the spec, honored by
the scheduler, and visible/editable in the supported web editor. Explicit headless exceptions
must be documented; they are not claims of browser control parity.

### VI. Style (MUST)

black with line-length 420 (deliberate — do not reformat), isort (black profile), flake8.
Never write UTF-8 BOM into YAML or spec files.

## Governance

Amendments require a spec under `specs/` and full-suite evidence under Principle III.
All PRs target `main`.

### User-directed migration amendment — 2026-10-31

The operator expressly authorized this documentation-only migration amendment now,
addressing `specs/005-web-engine-migration/spec.md` FR-026/061 and the governance deadlock
identified as HM1. For this amendment only, the prior requirement to run a full runtime
suite before changing governance is replaced by documentation validation and an open
main-targeting plan-review PR. This is an explicit governance-path amendment, not a
retroactive claim that a suite passed or that the historical spec allowed it.

The preamble and Principle V name the target supported React surface; existing TUI
support is not retired until FR-062 acceptance. Principle II preserves paper-only risk
and grants only the bounded free/local scheduled exception above. Principle III preserves
individual baseline and platform evidence obligations. Future code acceptance still requires
the full suite and fresh Windows/Linux evidence; this amendment waives neither.

The forward-facing normative resolution is `docs/governance/web-migration-contract.md`.
Historical spec005 records remain unchanged. Autonomous decisions authorize planning
and this amendment, never real-fund access, paid testing, implementation or PR merging.