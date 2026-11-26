# Contract: Discovery Snapshot Validator v1

**Status**: Planned | **Spec**: [../spec.md](../spec.md) | **Data model**: [../data-model.md](../data-model.md)

This is a synchronous Python library contract for the later offline ranking core. It is not an HTTP endpoint, CLI, provider interface, persistence format, or ranking API.

## Public entry point

```python
def validate_snapshot(
    raw: object,
    *,
    reference_time: str | None = None,
    max_age_seconds: int | None = None,
) -> SnapshotValidationResult:
    ...
```

Import from `hedge_fund.discovery`. The function accepts Python field content rather than a JSON document or byte stream. Callers remain responsible for any parsing. Expected data-validation failures return a failure result; they do not expose Pydantic exceptions.

The two freshness arguments are both absent or both present. Their incomplete/invalid behavior is defined in [Data model — Freshness policy](../data-model.md#freshness-policy-not-part-of-canonical-output).

## Result contract

`SnapshotValidationResult` has exactly these public attributes:

| Attribute | Type | Invariant |
|---|---|---|
| `snapshot` | `dict[str, object] \| None` | Complete canonical snapshot on success; always `None` on failure |
| `issues` | `tuple[ValidationIssue, ...]` | Empty on success; non-empty on failure |

`ValidationIssue` has exactly these public attributes:

| Attribute | Type | Meaning |
|---|---|---|
| `location` | `str` | Exact root/field location |
| `reason` | `str` | Stable machine-readable reason |
| `message` | `str` | Deterministic human-readable explanation |
| `related_locations` | `tuple[str, ...]` | Other conflicting locations; empty unless applicable |

Success means `snapshot is not None` and `issues == ()`. Failure means `snapshot is None` and `issues` is non-empty. Callers must test the result rather than treating a partial dictionary as usable.

## Input and canonical snapshot

The complete field schema, constraints, optional-field behavior, and timestamp boundaries are defined in [data-model.md](../data-model.md). The contract's compatibility-sensitive guarantees are:

1. Only schema version integer `1` is supported. Unsupported integer versions fail explicitly; no migration occurs.
2. Unknown fields are rejected at the snapshot, source, and instrument levels.
3. Required values may not be null. Optional instrument values emit explicit nulls in canonical output.
4. Numeric inputs remain built-in integers/floats with their values unchanged; booleans, numeric strings, NaN, and infinity are rejected.
5. Instrument order is preserved. Canonical codes use existing `normalize_ticker` behavior, and duplicates are rejected.
6. Valid timestamps canonicalize to UTC RFC 3339 strings ending in `Z` while preserving supplied fraction digits.
7. Canonical output is compared by JSON-compatible field content. Byte serialization, object-key order, and insignificant whitespace are not contractual.
8. A successful result contains the five top-level fields and every declared instrument/source field; a failed result contains no partial snapshot.
9. Currency identifiers contain exactly three uppercase ASCII letters. Validation is format-only and does not claim ISO 4217 assigned-code membership.

## Freshness contract

Freshness is opt-in and deterministic:

- No policy: validate structure and timestamp order only, including for arbitrarily historical snapshots.
- Complete policy: reject future observations and ages strictly greater than `max_age_seconds`.
- Exact age boundary: accept.
- Invalid/incomplete policy: report policy argument issues, never silently use the wall clock or disable an enabled check.

The freshness arguments and policy issues are not added to canonical snapshot content.

## Reasons and locations

The stable reason set is:

```text
missing_field
null_value
invalid_type
invalid_value
unknown_field
duplicate_code
unsupported_schema_version
invalid_timestamp_order
stale_snapshot
future_snapshot
inconsistent_optional_fields
```

Use `$` for a root type error. Use dotted object fields and bracketed zero-based indices elsewhere, for example `source.provider`, `instruments[0].code`, `reference_time`, and `max_age_seconds`.

Locations are encoded from structured segments so arbitrary unknown keys cannot collide. Object keys matching `[A-Za-z_][A-Za-z0-9_]*` use dotted notation. Every other key uses a bracketed JSON-string segment with standard JSON escaping for quotes, backslashes, and control characters; prefix `$` when the first segment requires brackets. A top-level unknown key `source.extra` therefore renders as `$["source.extra"]`, while an unknown `extra` key inside `source` renders as `source.extra`. An unknown `bad.key` on the first instrument renders as `instruments[0]["bad.key"]`. Sorting uses the structured segments before this rendering.

A malformed `schema_version` uses `invalid_type` at `schema_version`; a missing version uses `missing_field`; an integer other than 1 uses `unsupported_schema_version`. Location plus reason is the compatibility contract; human messages are not intended for parsing.

For duplicate canonical codes, every conflicting row receives an issue at its own `code` location and lists every other conflicting row in `related_locations`.

## Aggregation and ordering

All independently detectable issues are returned together. Checks with invalid prerequisites do not invent dependent issues. Identical issues are deduplicated, then sorted by structured location (numeric array indices), reason, related locations, and message.

Pydantic exception types, messages, URLs, and raw error locations are internal implementation details and are not public compatibility guarantees.

## Consumer example

```python
result = validate_snapshot(
    synthetic_input,
    reference_time="2026-01-02T00:00:00Z",
    max_age_seconds=3600,
)

if result.snapshot is None:
    report(result.issues)
else:
    consume_offline(result.snapshot)
```

`report` and `consume_offline` represent caller operations, not additional feature-010 APIs. No network or current-time lookup occurs in either validation path.

## Versioning

The input `schema_version` governs snapshot field compatibility. Adding fields, changing normalization, changing reasons/locations, or weakening validation requires an explicit contract/specification update. Later provider, ranking, web, and persistence features must adapt to this seam rather than silently changing it.
