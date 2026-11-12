# Quickstart Validation: Native Single-User Writable Access

Validation uses synthetic test-owned roots only until the separately authorized real cutover. Never run these steps against `C:\Users\ChristianGjedrem\.hedge-fund` during development.

## Prerequisites

- Repo at the feature branch; `poetry install`; Python 3.11
- Synthetic roots created via the existing test-owned-root enrollment (`enroll_synthetic_root`, TEST_MODE, `outputs/spec005-test-*` pattern + `.test-owned` marker)

## Scenario A — Unit/integration suite (development gate)

1. `poetry run pytest hedge_fund/runtime -q` — focused handover/admission/root tests
2. `poetry run pytest hedge_fund -q` — full suite; any failure individually evidenced per Constitution III
3. Expected: all new behavior covered: Windows scope grant/deny, scope-mismatch denial, marker retirement (success, live-process refusal, missing marker), protected-fund attestation (success, unknown name, rename-evasion impossibility), relocate with settings (success, digest mismatch, interrupted copy), full denial matrix

## Scenario B — End-to-end synthetic rehearsal (pre-cutover gate)

On synthetic fixtures replicating the real root's shape (three protected-named funds, two stale `runner.pid` markers, settings file):

1. `aihf --root SYNTH_SRC handover inspect-source` → inventory lists 3 protected funds + 2 markers as blockers
2. `handover attest-stale-marker` ×2 → artifacts recorded; live-process refusal path exercised separately with a real dummy process
3. `handover attest-protected-fund` ×3 → artifacts recorded; original names kept
4. `aihf --root SYNTH_DST handover relocate-from SYNTH_SRC --content-digest D` → copy verified incl. settings; ledger heads match
5. `aihf --root SYNTH_DST handover inspect` → challenge issued
6. `handover trust-single-writer --inventory-digest D --operator-acknowledgement "EXACT"` → trust recorded with Windows scope
7. Launch native TUI on SYNTH_DST → write op succeeds; prior history replays byte-identically
8. Negative checks: second writer process → denied; tampered scope (different account) → denied; trust from SYNTH_SRC presented at SYNTH_DST → denied
9. Interruption drill: kill mid-relocate → source untouched; target marked incomplete; rerun succeeds

## Scenario C — Real cutover (separate explicit authorization required)

Mirror of Scenario B against the real root, preceded by non-destructive backup + identity manifest + hashes, and followed by operator-supervised verification. Source `C:\Users\ChristianGjedrem\.hedge-fund` stays intact until the operator authorizes retirement. Detailed runbook is produced at implementation time and approved before execution.

## Expected outcome

SC-001..SC-005 demonstrated: all funds writable under original names, 100% history hash match, every denial path exercised with clear messages, all grants reconstructible from on-disk artifacts.