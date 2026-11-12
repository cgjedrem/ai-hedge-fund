# Implementation Plan: Native Single-User Writable Access for Existing Funds

**Branch**: `cgjedrem-cautious-spork` (app-managed worktree; computed feature name `007-windows-writable-access`) | **Date**: 2026-11-12 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/007-windows-writable-access/spec.md`

## Summary

Grant the operator a supported, auditable single-user writable path for the existing paper-fund root, delivered through the native TUI, with the data relocated by copy-then-verify from the legacy path `C:\Users\ChristianGjedrem\.hedge-fund` to `C:\Users\ChristianGjedrem\aihf-data`. Discovery (verified at commit `b6aefe5`) found the fail-closed blockers; plan-review then found three deeper authorization gaps now incorporated into scope:

1. **Windows trusted-single-writer identity** — `_runtime_scope_identity` (`hedge_fund/runtime/handover.py:202-235`) currently disables Windows outright; add a Windows runtime-scope identity so the existing `trust-single-writer` ceremony can grant authority natively.
2. **Legacy-layout-path denial** — resolved by operator-approved relocation using the existing `relocate-from` mechanism (`handover.py:971-1149`), extended to preserve runtime settings, which it does not transfer today.
3. **Inventory blockers** — attestation-based retirement of stale `runner.pid` markers and explicit per-fund attestation for the protected names `umbrella`, `watchtower`, `watchtower-weekly`. Attestations are **destination-bound**: source inspection is strictly read-only, evidence is stored outside the source tree, and attestation + marker retirement happen on the verified destination copy BEFORE target inventory validation/enrollment (which otherwise rejects them, `handover.py:1033-1045`).
4. **Root-layer name authorization (review finding)**: `RootContext` I/O rejects protected names through `_relative_parts` (`hedge_fund/runtime/root.py:238-270,489-511`) and admission resource validation reaches the same check (`hedge_fund/runtime/admission.py:956-962`). The plan therefore adds root-bound, attestation-aware authorization in BOTH layers — preserving default denial and alias checks — so attested protected funds can actually be relocated and written, with coverage for relocation and subsequent writes. An inventory exception alone is insufficient.
5. **TUI write path (review finding)**: root trust alone cannot enable the native TUI — `hedge_fund/tui/funds.py:34-45` rejects enrolled-root paper writes and `hedge_fund/tui/paper.py:511-516` rejects execution even past that guard. Scope includes admitted TUI operations: owner/lane acquisition and operation-bound authorization wired through the existing admission machinery, with updated regression coverage — not merely removing the guards.

## Technical Context

**Language/Version**: Python 3.11 (Poetry)
**Primary Dependencies**: existing `hedge_fund/runtime/` handover/admission/root modules; Textual TUI (`hedge_fund/tui/`); no new third-party dependencies planned
**Storage**: JSON artifacts under the destination root's `runtime/private/v1/`; hash-chained paper ledgers under `paper/`; attestation evidence bundle stored outside the source tree
**Testing**: pytest, tests co-located under `hedge_fund/` (`poetry run pytest hedge_fund -q`); synthetic test-owned roots only (`outputs/spec005-test-*` pattern + `.test-owned`), never the real root
**Target Platform**: Native Windows 11, NTFS, single operator account
**Project Type**: CLI/TUI application
**Performance Goals**: N/A (correctness and auditability dominate); enablement ceremony excluding operator reading < 30 min (SC-002)
**Constraints**: fail-closed admission preserved; no ledger rewrite/re-hash; no disabling of admission checks; no paid providers, no live orders, no unattended loops (Constitution II); writer-map AST scan (`hedge_fund/runtime/test_writer_map.py`) must accept any new raw writes; source root tree is never mutated by the procedure (FR-007)
**Scale/Scope**: one machine, one operator, ~4 funds, ~2592 root entries (snapshot observed during prior read-only inspection)

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Verdict | Basis |
|-----------|---------|-------|
| I. Ledger integrity (MUST) | PASS | No existing record is rewritten or re-serialized; relocation is verified copy with ledger-head and hash comparison; FR-002/FR-009 |
| II. Paper only (MUST) | PASS | No live orders, no paid providers, no unattended loops introduced; enablement changes admission, not trading scope |
| III. Tests co-located and green (MUST) | PASS with obligation | New behavior gets co-located tests on synthetic roots; acceptance requires full suite plus per-failure baseline evidence; Windows runtime evidence is required, not waivable |
| IV. Determinism (SHOULD) | PASS | No changes to replay/clock semantics |
| V. Consistent surfaces (SHOULD) | PASS | TUI remains the supported surface; no mandate-schema change |
| VI. Style (MUST) | PASS | black 420 / isort / flake8; no BOM in spec/plan files |

No violations; Complexity Tracking table not required.

## Project Structure

### Documentation (this feature)

```text
specs/007-windows-writable-access/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output (CLI contract for handover subcommands)
└── tasks.md             # Phase 2 output (/speckit-tasks — NOT created here)
```

### Source Code (repository root)

```text
hedge_fund/
├── runtime/
│   ├── handover.py            # Windows scope identity; destination-bound attestation; marker retirement at destination; relocate settings extension
│   ├── root.py                # attestation-aware protected-name authorization in _relative_parts (default denial + alias checks preserved)
│   ├── admission.py           # attestation-aware resource validation (~956-962); enforcement points otherwise reused
│   ├── test_handover.py / test_write_authority.py / test_root.py   # extended, co-located
│   └── test_writer_map.py     # WRITER_MAP entries for any new artifact writes
├── tui/
│   ├── funds.py               # admitted enrolled-root paper writes via owner/lane acquisition (34-45)
│   ├── paper.py               # operation-bound execution authorization (511-516)
│   └── test_admission_regressions.py + related   # updated regression coverage
└── run.py                     # CLI wiring for new/extended handover subcommands only
```

**Structure Decision**: Single existing Python package; changes confined to the admission/handover/root layers, the two TUI write guards, and CLI wiring. No new projects, no Docker work, no web-surface changes.

## Phases

- **Phase 0 — Research**: see [research.md](research.md). All technical unknowns resolved; no NEEDS CLARIFICATION remains.
- **Phase 1 — Design**: see [data-model.md](data-model.md), [contracts/handover-cli.md](contracts/handover-cli.md), [quickstart.md](quickstart.md).

## Cutover Gate (out of scope for implementation tasks)

Actual migration of the real root is a separate, explicitly authorized operation AFTER implementation + QA: quiesce verified writers, non-destructive backup with identity manifest and hashes, copy (never move), verify ledger heads and manifest hashes, synthetic-fund smoke first, then real-root enablement, with the source left intact until the operator authorizes retirement. Implementation tasks must not touch `C:\Users\ChristianGjedrem\.hedge-fund`.