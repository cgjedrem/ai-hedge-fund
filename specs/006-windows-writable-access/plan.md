# Implementation Plan: Native Single-User Writable Access for Existing Funds

**Branch**: `cgjedrem-cautious-spork` (app-managed worktree; computed feature name `006-windows-writable-access`) | **Date**: 2026-11-12 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/006-windows-writable-access/spec.md`

## Summary

Grant the operator a supported, auditable single-user writable path for the existing paper-fund root, delivered through the native TUI, with the data relocated by copy-then-verify from the legacy path `C:\Users\ChristianGjedrem\.hedge-fund` to `C:\Users\ChristianGjedrem\aihf-data`. Discovery (verified at commit `b6aefe5`) found three independent fail-closed blockers, so this feature is a bounded code + governance change in the handover/admission layer plus a separately authorized cutover runbook:

1. **Windows trusted-single-writer identity** — `_runtime_scope_identity` (`hedge_fund/runtime/handover.py:202-235`) currently disables Windows outright; add a Windows runtime-scope identity so the existing `trust-single-writer` ceremony can grant authority natively.
2. **Legacy-layout-path denial** — resolved by operator-approved relocation using the existing `relocate-from` mechanism (`handover.py:971-1149`), extended to preserve runtime settings, which it does not transfer today.
3. **Inventory blockers** — supported, attestation-based retirement of stale `runner.pid` markers and explicit per-fund attestation for the protected names `umbrella`, `watchtower`, `watchtower-weekly` (no renaming, no silent deletion, no check evasion).

## Technical Context

**Language/Version**: Python 3.11 (Poetry)
**Primary Dependencies**: existing `hedge_fund/runtime/` handover/admission/root modules; Textual TUI (`hedge_fund/tui/`); no new third-party dependencies planned
**Storage**: JSON artifacts under the root's `runtime/private/v1/`; hash-chained paper ledgers under `paper/`
**Testing**: pytest, tests co-located under `hedge_fund/` (`poetry run pytest hedge_fund -q`); synthetic test-owned roots only (`outputs/spec005-test-*` pattern + `.test-owned`), never the real root
**Target Platform**: Native Windows 11, NTFS, single operator account
**Project Type**: CLI/TUI application
**Performance Goals**: N/A (correctness and auditability dominate); enablement ceremony excluding operator reading < 30 min (SC-002)
**Constraints**: fail-closed admission preserved; no ledger rewrite/re-hash; no disabling of admission checks; no paid providers, no live orders, no unattended loops (Constitution II); writer-map AST scan (`hedge_fund/runtime/test_writer_map.py`) must accept any new raw writes
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
specs/006-windows-writable-access/
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
│   ├── handover.py            # Windows scope identity; marker retirement; protected-fund attestation; relocate settings extension
│   ├── admission.py           # unchanged enforcement points (reuse)
│   ├── root.py                # unchanged inventory/protected-name validation (attestation plugs in, not bypasses)
│   ├── test_handover.py / test_write_authority.py / test_root.py   # extended, co-located
│   └── test_writer_map.py     # WRITER_MAP entries for any new artifact writes
├── tui/
│   └── (no changes expected — admission is upstream in paths.py/handover.py)
└── run.py                     # CLI wiring for new handover subcommands only
```

**Structure Decision**: Single existing Python package; all changes confined to `hedge_fund/runtime/` admission/handover plus CLI wiring in `run.py`. No new projects, no TUI-internal admission changes, no Docker work.

## Phases

- **Phase 0 — Research**: see [research.md](research.md). All technical unknowns resolved; no NEEDS CLARIFICATION remains.
- **Phase 1 — Design**: see [data-model.md](data-model.md), [contracts/handover-cli.md](contracts/handover-cli.md), [quickstart.md](quickstart.md).

## Cutover Gate (out of scope for implementation tasks)

Actual migration of the real root is a separate, explicitly authorized operation AFTER implementation + QA: quiesce verified writers, non-destructive backup with identity manifest and hashes, copy (never move), verify ledger heads and manifest hashes, synthetic-fund smoke first, then real-root enablement, with the source left intact until the operator authorizes retirement. Implementation tasks must not touch `C:\Users\ChristianGjedrem\.hedge-fund`.