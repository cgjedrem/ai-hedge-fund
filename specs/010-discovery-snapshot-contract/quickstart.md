# Quickstart Validation: Discovery Snapshot Contract

**Date**: 2026-11-25 | **Spec**: [spec.md](spec.md) | **Contract**: [contracts/discovery-snapshot-v1.md](contracts/discovery-snapshot-v1.md)

These scenarios become runnable after implementation. They use only synthetic in-memory fixtures: no provider, credentials, network, wall clock, real fund, ledger, or model calls.

## Prerequisites

- Work from the repository root on the app-managed feature worktree.
- Python 3.11 and the existing Poetry environment are available. If dependencies are not installed, run `poetry install`.
- No environment credentials or network access are needed. The repository's test setup supplies isolation.

## Commands

Run the focused contract and shared-normalization regression tests:

```powershell
poetry run pytest hedge_fund/discovery/test_snapshot.py hedge_fund/fund/test_spec.py -q
```

Run focused style checks:

```powershell
poetry run black --check hedge_fund/discovery hedge_fund/fund/spec.py hedge_fund/fund/__init__.py hedge_fund/fund/test_spec.py
poetry run isort --check-only hedge_fund/discovery hedge_fund/fund/spec.py hedge_fund/fund/__init__.py hedge_fund/fund/test_spec.py
poetry run flake8 hedge_fund/discovery hedge_fund/fund/spec.py hedge_fund/fund/__init__.py hedge_fund/fund/test_spec.py
```

Before implementation acceptance, run the constitution-required full suite:

```powershell
poetry run pytest hedge_fund -q
```

Expected result for every command: exit code zero. Do not accept the feature using only a narrowed final suite.

## Validation scenarios

### V1 — Valid snapshot canonicalization (US-1, FR-001–FR-007, FR-012)

1. Load the named valid fixture containing two synthetic instruments, lowercase/padded codes, an offset timestamp, a preserved fractional second, and omitted optional fields.
2. Call `validate_snapshot` without freshness arguments.
3. **Expected**: success; no issues; exact schema version 1; instruments retain input order; codes match existing uppercase/trim behavior; timestamps end in `Z` with fraction digits unchanged.
4. Compare complete field content against the expected canonical fixture.
5. **Expected**: every optional field appears explicitly with null when unavailable; no undeclared normalization, zero substitution, clipping, or numeric string conversion occurs.
6. Serialize equivalent canonical values with different key order/whitespace in the test comparison.
7. **Expected**: comparisons depend on field content, not byte formatting.

### V2 — All-or-nothing invalid rejection (US-2, FR-008, FR-010, FR-013–FR-015)

1. Load a combined invalid fixture with independently detectable errors: missing required values, explicit nulls, wrong types, unknown fields, a non-positive price, an out-of-range change, non-finite numbers, an incomplete optional pair, and duplicate canonical codes.
2. Validate once.
3. **Expected**: failure with `snapshot=None`; all independently detectable issues are present with exact locations and reasons; duplicate issues identify every conflicting row.
4. Repeat with a second fixture containing at least ten instruments and errors at indices 2 and 10.
5. **Expected**: index 2 sorts before index 10; issue order and messages are deterministic.
6. Attempt to consume the result as a canonical snapshot.
7. **Expected**: no partial snapshot exists to consume.

### V3 — Strict version and JSON-type boundaries (FR-002, FR-007, FR-010, SC-005)

Exercise each case independently:

| Input | Expected issue |
|---|---|
| Missing `schema_version` | `missing_field` at `schema_version` |
| `schema_version=True` or `1.0` | `invalid_type` at `schema_version` |
| `schema_version=2` | `unsupported_schema_version` at `schema_version` |
| Numeric strings, booleans as numeric fields | `invalid_type` at the exact field |
| NaN or positive/negative infinity | `invalid_value` at the exact field |
| Unknown fields at each object level | `unknown_field` at each exact field |
| Non-string object key or non-JSON Python value | `invalid_type` at the containing/exact location |
| Null required field | `null_value` at the exact field |
| Unsupported unknown fields or versions combined with other errors | All independent issues; no migration or silent field ignoring |

### V4 — Timestamp grammar and canonical precision (FR-003, FR-007, FR-011)

1. Validate equivalent timestamps with explicit offsets and uppercase/lowercase RFC 3339 separators.
2. **Expected**: canonical UTC output with uppercase `T` and trailing `Z`.
3. Exercise fractions `.5`, `.000`, `.120`, and `.1234567` through offset conversion.
4. **Expected**: output retains exactly `.5`, `.000`, `.120`, and `.1234567`; no rounding, padding, truncation, or dropped zero fraction.
5. Exercise numeric timestamps, naive strings, named zones, spaces, missing seconds, comma fractions, non-colon offsets, invalid dates, leap second `:60`, and year 0000.
6. **Expected**: each is rejected at the exact timestamp field; no partial snapshot.
7. Set `retrieved_at` exactly equal to and then earlier than `snapshot_at`.
8. **Expected**: equality succeeds; earlier retrieval returns `invalid_timestamp_order`.

### V5 — Explicit freshness (US-3, FR-004, FR-011)

1. Validate a historical snapshot without policy arguments.
2. **Expected**: historical age alone does not fail; no current-time lookup occurs.
3. Supply `reference_time` and `max_age_seconds` so snapshot age equals the limit exactly.
4. **Expected**: success at the boundary.
5. Increase the reference instant by the smallest fixture fraction beyond the boundary.
6. **Expected**: `stale_snapshot` at `snapshot_at`, using exact arithmetic rather than microsecond rounding.
7. Set `snapshot_at` later than `reference_time`.
8. **Expected**: `future_snapshot`; a future observation is not also reported as stale.
9. Supply only one policy argument, a malformed reference, a negative age, a boolean age, and a float age in separate cases.
10. **Expected**: `missing_field`, `invalid_value`, or `invalid_type` at `reference_time`/`max_age_seconds` as applicable; freshness is neither silently disabled nor evaluated from invalid policy data.

### V6 — Valid structural extremes (FR-005, FR-007, FR-010)

1. Validate snapshots with an empty instrument list, a suspended instrument, zero allowed numeric values, negative valuation ratios, and large finite numbers.
2. **Expected**: structural success with values preserved.
3. **Expected**: no eligibility, ranking, or sampling decision is made by this feature.

### V7 — Shared normalization and deterministic replay (FR-006, FR-014, SC-004)

1. Run existing `normalize_universe` examples, including mixed case, surrounding whitespace, embedded punctuation, duplicates, and empty-universe behavior.
2. **Expected**: existing behavior is unchanged after extracting the shared single-ticker helper.
3. Validate every named fixture twice and compare canonical content/issues.
4. **Expected**: identical results. Instrument-list duplicates remain validation errors rather than inheriting universe-list deduplication.

### V8 — Offline and regression acceptance (SC-001–SC-005)

1. Run the focused tests with provider credentials absent and the existing network guard active.
2. **Expected**: all scenarios pass without network or external state.
3. Run `poetry run pytest hedge_fund -q`.
4. **Expected**: full suite passes; existing fund, ledger, backtest, paper-trading, and UI behavior is unchanged.

Detailed field expectations and reason semantics live in [data-model.md](data-model.md) and the [public contract](contracts/discovery-snapshot-v1.md); this guide intentionally contains no implementation bodies.
