# Data Model: Discovery Snapshot Contract

**Date**: 2026-11-25 | **Spec**: [spec.md](spec.md) | **Research**: [research.md](research.md)

All persisted-looking structures below are in-memory only. The public canonical snapshot contains JSON-compatible dictionaries, lists, strings, built-in integers/floats, booleans, and nulls; it has no database or file representation in this feature.

## Snapshot envelope

| Field | Input rule | Canonical output |
|---|---|---|
| `schema_version` | Required built-in integer equal to 1; booleans and floats are invalid | Integer `1` |
| `snapshot_at` | Required RFC 3339 string with explicit `Z`/offset | UTC string ending `Z` |
| `retrieved_at` | Required RFC 3339 string with explicit `Z`/offset | UTC string ending `Z` |
| `source` | Required source object | Source object |
| `instruments` | Required list of instrument objects; may be empty | List in input order |

Only these five top-level fields are accepted.

### Timestamp value semantics

- Accept uppercase or lowercase RFC 3339 `T` and `Z`; reject spaces, naive values, numeric values/strings, named zones, missing seconds, comma fractions, and offsets without a colon.
- Validate calendar fields and offsets with Python `datetime`; the MVP rejects leap-second `:60`, year 0000, and UTC conversions outside years 0001–9999.
- Normalize the whole-second portion to UTC, preserve every supplied fraction digit verbatim, and emit uppercase `T` and trailing `Z`. Do not round, pad, or add a zero fraction.
- Treat `-00:00` as the same instant as UTC for this instant-only contract.
- Keep an exact `Fraction` representation separately for comparisons; it is never emitted.

## Source

| Field | Input rule | Canonical output |
|---|---|---|
| `provider` | Required string, non-empty after trimming | Original string, without trimming or case conversion |

No other source fields are accepted in version 1.

## Instrument

| Field | Required | Rule |
|---|---:|---|
| `code` | Yes | String; apply shared `normalize_ticker` (`strip().upper()`); canonical result must be non-empty |
| `name` | Yes | String, non-empty after trimming; preserve original text |
| `exchange` | Yes | String, non-empty after trimming; preserve original text |
| `currency` | Yes | Exactly three uppercase ASCII letters; preserve original text |
| `trading_status` | Yes | Exactly `active` or `suspended` |
| `price` | Yes | Built-in finite int/float greater than zero |
| `change_pct` | Yes | Built-in finite int/float greater than or equal to -1; values above 1 are permitted |
| `amount` | Yes | Built-in finite int/float greater than or equal to zero |
| `total_mv` | Yes | Built-in finite int/float greater than or equal to zero |
| `pe_ratio` | No | Built-in finite int/float or null; any finite sign is allowed |
| `pb_ratio` | No | Built-in finite int/float or null; any finite sign is allowed |
| `volume_ratio` | No | Built-in finite int/float greater than or equal to zero, or null |
| `turnover_rate` | No | Built-in finite int/float greater than or equal to zero, or null |
| `industry` | No | String or null; blank after trimming is unavailable |
| `avg_amount_usd` | No | Built-in finite int/float greater than or equal to zero, or null |
| `avg_amount_usd_window_days` | No | Built-in positive integer or null; booleans and floats are invalid |

Rules applying to every instrument:

- Reject unknown fields. Emit all seven optional fields explicitly, using null when absent or null in input. A blank `industry` also canonicalizes to null; preserve nonblank industry text.
- Preserve numeric type and value; do not convert integers to floats, clip extremes, or replace unavailable values with zero.
- `avg_amount_usd` and `avg_amount_usd_window_days` must both be present and non-null or both be absent/null. One without the other yields `inconsistent_optional_fields` at `avg_amount_usd_window_days`.
- After code normalization, duplicate codes are invalid. Emit one `duplicate_code` issue for every conflicting row; each issue's `related_locations` contains the other rows' code locations.
- Suspension and an empty instrument list affect no structural validity rule. Ranking eligibility belongs to feature 011.

## Freshness policy (not part of canonical output)

Freshness is represented by the validator's two keyword arguments:

| Argument | Rule when policy is enabled |
|---|---|
| `reference_time` | RFC 3339 string under the same parser and exact-instant semantics as snapshot timestamps |
| `max_age_seconds` | Built-in integer greater than or equal to zero; booleans and floats are invalid |

The arguments must be supplied together. If one is absent, report `missing_field` at that argument name. Invalid supplied values use `invalid_type` or `invalid_value` at the argument name; no new reason is introduced.

With no policy, perform no age or future check and never read the wall clock. With a complete valid policy and valid snapshot timestamps:

- `snapshot_at > reference_time` yields `future_snapshot` at `snapshot_at`.
- Otherwise, `reference_time - snapshot_at > max_age_seconds` yields `stale_snapshot` at `snapshot_at`.
- Exact equality with the maximum age is valid.
- Invalid policy inputs do not produce freshness claims.

## Validation result

`SnapshotValidationResult` is an immutable result record:

| Attribute | Success | Failure |
|---|---|---|
| `snapshot` | Complete canonical dictionary | `None` |
| `issues` | Empty tuple | Non-empty tuple of `ValidationIssue` |

There is no partial success state. An empty snapshot dictionary is never a valid success result because the five top-level fields remain required; an empty `instruments` list is valid.

## Validation issue

`ValidationIssue` is immutable and contains:

| Field | Meaning |
|---|---|
| `location` | `$` for the root; otherwise a dotted field path with numeric list indices, such as `instruments[0].price` |
| `reason` | One stable value from the vocabulary below |
| `message` | Deterministic human-readable explanation; consumers must not parse it |
| `related_locations` | Tuple of other relevant locations; normally empty, populated for duplicate rows |

### Reason vocabulary

| Reason | Trigger |
|---|---|
| `missing_field` | Required field or one member of an explicitly enabled policy is absent |
| `null_value` | A required non-null value is null |
| `invalid_type` | Value has the wrong strict JSON/Python type |
| `invalid_value` | Value violates format, finiteness, range, or non-empty constraints |
| `unknown_field` | Input contains an undeclared field |
| `duplicate_code` | Canonical ticker occurs on multiple rows |
| `unsupported_schema_version` | `schema_version` is a valid integer other than 1 |
| `invalid_timestamp_order` | `retrieved_at` is earlier than `snapshot_at` |
| `stale_snapshot` | Snapshot age exceeds the explicit maximum |
| `future_snapshot` | Snapshot observation is later than the explicit reference time |
| `inconsistent_optional_fields` | The average-amount value/window pair is incomplete |

## Aggregation and deterministic ordering

1. Run exact JSON-type checks and strict structural validation.
2. Independently run every semantic check whose own prerequisites are valid, even if another check failed.
3. Deduplicate identical issues.
4. Sort by structured location, reason, related locations, and message. Object keys sort lexicographically; array indices sort numerically, so index 2 precedes index 10.
5. Render locations and return the result. Any issue forces `snapshot=None`.

## State transitions

None. Validation does not persist, approve, rank, schedule, or mutate a snapshot. Repeating validation with equal field content produces the same canonical content and ordered issues.
