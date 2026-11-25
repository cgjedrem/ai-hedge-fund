# Feature Specification: Discovery Snapshot Contract

**Feature Branch**: `cgjedrem-evaluate-alphasift-integration` (app-managed worktree; branch creation skipped, numbering applied as `010-discovery-snapshot-contract`)

**Created**: 2026-11-25

**Status**: Draft

**Input**: User description: "Define a versioned, validated discovery-snapshot contract for stock ranking. Specify required and optional fields, data types, units, currency/exchange metadata, snapshot timestamps, missing-data behavior, and field-level validation errors. Include representative offline fixtures for valid data and edge cases such as missing values, duplicates, suspended instruments, stale snapshots, and extreme values. Ticker handling must be compatible with existing universe canonicalization. This feature is entirely offline and excludes live providers, persistence, and ranking implementation."

## Clarifications

### Session 2026-11-25

- Q: What should a “canonical snapshot” mean for validation results and offline fixtures? → A: JSON-compatible values compared by field content; only explicitly declared normalization applies, unavailable optional fields are emitted as null, and whitespace/key order are not contractual.
- Q: Which timestamp representations should the snapshot contract accept? → A: RFC 3339 timestamp strings with an explicit offset or `Z`; reject numeric timestamps, naive timestamps, and named time zones.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Reject unreliable candidate data (Priority: P1)

As a fund operator, I want every candidate snapshot checked against one explicit contract so malformed or ambiguous data cannot silently influence later research.

**Why this priority**: A shared, trustworthy input boundary is the foundation for offline ranking, future providers, and reproducible review. Without it, missing values, unit mismatches, and duplicate instruments can produce misleading candidates.

**Independent Test**: Validate the representative valid and malformed fixtures without any ranking or external service. Every fixture must produce its declared outcome, normalized tickers, and field-specific issues.

**Acceptance Scenarios**:

1. **Given** a complete valid snapshot containing active instruments, **When** it is validated, **Then** it is accepted and all declared values, units, statuses, and metadata remain explicit.
2. **Given** a snapshot with a missing required field, an invalid value, an unknown field, or a blank ticker, **When** it is validated, **Then** no partially valid snapshot is returned and each detected issue identifies its exact field and reason.
3. **Given** tickers such as `aapl`, ` MSFT `, and `BRK.B`, **When** they are canonicalized, **Then** they become `AAPL`, `MSFT`, and `BRK.B`, matching existing universe trimming and uppercase behavior without changing embedded separators.
4. **Given** two rows whose tickers become identical after canonicalization, **When** the snapshot is validated, **Then** it is rejected as ambiguous and both duplicate locations are identified rather than silently deduplicated.
5. **Given** a suspended instrument with otherwise valid data, **When** the snapshot is validated, **Then** it is accepted with its suspended status preserved and is never relabeled as active.
6. **Given** optional metrics that are absent or explicitly unavailable, **When** the snapshot is validated, **Then** they remain unavailable and are not silently replaced with zero or another invented value.

---

### User Story 2 - Replay historical snapshots safely (Priority: P2)

As a fund operator, I want source and observation-time metadata plus deterministic freshness checks so I can replay an old snapshot without mistaking it for current market data.

**Why this priority**: Offline research is useful only when provenance and age are visible and reproducible. Historical fixtures must remain usable without depending on the current wall clock.

**Independent Test**: Validate the same recorded snapshot with explicit reference times and freshness limits. Compare the resulting acceptance or stale/future-dated issues without accessing a provider or clock.

**Acceptance Scenarios**:

1. **Given** a valid historical snapshot and no freshness policy, **When** it is validated for structural correctness, **Then** it is accepted while its original source, observation time, and retrieval time remain visible.
2. **Given** an explicit reference time and maximum permitted age, **When** snapshot age exceeds that limit, **Then** validation reports a stale-snapshot issue at the observation-time field; age equal to the limit remains acceptable.
3. **Given** an observation time later than the supplied reference time, **When** freshness is evaluated, **Then** validation reports a future-dated snapshot rather than accepting look-ahead data.
4. **Given** identical snapshot content and validation inputs, **When** validation is repeated, **Then** canonical results and ordered issues are identical.

---

### User Story 3 - Evolve the contract without silent breakage (Priority: P3)

As a maintainer, I want an explicit schema version and compatibility baseline so changes to snapshot semantics cannot be mistaken for valid existing data.

**Why this priority**: Ranking and provider work will depend on this contract. Versioned compatibility prevents a field rename, unit change, or new requirement from silently invalidating recorded research.

**Independent Test**: Validate the current-version baseline and unsupported-version fixtures, then review the documented compatibility policy against a simulated breaking change.

**Acceptance Scenarios**:

1. **Given** a snapshot declaring the supported schema version, **When** all other requirements are satisfied, **Then** it is accepted under that version's rules.
2. **Given** a missing, malformed, or unsupported schema version, **When** validation occurs, **Then** it fails at the schema-version field with a clear compatibility reason.
3. **Given** a proposed field removal, rename, unit change, meaning change, or newly required value, **When** compatibility is reviewed, **Then** the change is treated as breaking and requires a new schema version while the prior baseline remains available.

---

### Edge Cases

- Empty instrument collections and snapshots containing only suspended instruments remain structurally valid if all fields are valid; whether they yield candidates is a later ranking concern.
- Null, absent, blank, numeric-string, boolean-as-number, NaN, and infinite values are distinguished according to the field rules; required numeric values must be actual finite numbers.
- Zero is valid for trading value, market capitalization, and non-negative optional ratios where meaningful; negative prices and negative trading values are invalid.
- Negative valuation ratios remain valid because loss-making or negative-book-value companies can produce them. Finite extreme values are preserved without clipping; no arbitrary upper bound is imposed.
- Mixed currencies are representable because every instrument declares its own currency. The contract neither converts values nor compares monetary amounts across currencies.
- Duplicate detection occurs after ticker canonicalization. Exchange metadata does not make duplicate canonical tickers safe to merge.
- Staleness is evaluated only when both a reference time and maximum age are supplied. No universal freshness limit is inferred for historical fixtures, weekends, or different markets.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST define one discovery snapshot with exactly these top-level fields: integer `schema_version`, `snapshot_at`, `retrieved_at`, `source`, and an `instruments` collection containing zero or more records.
- **FR-002**: The initial supported schema version MUST be integer `1`. Validation MUST reject missing, non-integer, or unsupported versions and MUST NOT attempt silent migration.
- **FR-003**: `source` MUST be an object containing only `provider`, a non-empty provider or fixture identifier after trimming. `snapshot_at` and `retrieved_at` MUST be RFC 3339 timestamp strings with an explicit offset or `Z`; numeric timestamps, naive timestamps, and named time zones MUST be rejected. Canonical output MUST use RFC 3339 UTC strings ending in `Z`, preserving input fractional-second precision without rounding or padding; retrieval MUST NOT precede observation.
- **FR-004**: Every instrument MUST contain the required fields below. Optional keys MAY be absent or null, and both forms MUST produce the same unavailable-value semantics.

| Field | Presence | Type and unit | Validation and meaning |
|---|---|---|---|
| `code` | Required | Text; canonical ticker | Trim surrounding whitespace, uppercase, preserve all other characters, and require a non-empty result |
| `name` | Required | Text | Non-empty after trimming; no inferred name |
| `exchange` | Required | Text; exchange identifier | Non-empty after trimming; preserved without silently mapping to another venue |
| `currency` | Required | Three-letter currency code | Uppercase ISO 4217 alphabetic code; applies to `price`, `amount`, and `total_mv` |
| `trading_status` | Required | `active` or `suspended` | No other status or missing status may be assumed to mean active |
| `price` | Required | Number; currency units per share | Finite and greater than zero |
| `change_pct` | Required | Decimal ratio, not percentage points | Finite; `0.0125` means a 1.25% increase; MUST be at least `-1.0` |
| `amount` | Required | Number; currency units reported for the observation session | Finite and non-negative; not expressed in thousands or millions; partial-session values retain the observation timestamp |
| `total_mv` | Required | Number; total market value in currency units | Finite and non-negative; not expressed in thousands or millions |
| `pe_ratio` | Optional/nullable | Finite ratio | Price-to-earnings multiple; negative values permitted; unavailable is not zero |
| `pb_ratio` | Optional/nullable | Finite ratio | Price-to-book multiple; negative values permitted; unavailable is not zero |
| `volume_ratio` | Optional/nullable | Finite non-negative ratio | Relative trading volume; unavailable is not zero |
| `turnover_rate` | Optional/nullable | Finite non-negative decimal ratio | `0.025` means 2.5%; values above `1.0` are permitted |
| `industry` | Optional/nullable | Text | Blank text is treated as unavailable; no industry is inferred from the ticker |
| `avg_amount_usd` | Optional/nullable | Finite non-negative number in US dollars | Average daily trading value for strategies that require a USD-denominated liquidity measure; not inferred from `amount` |
| `avg_amount_usd_window_days` | Optional/nullable | Positive whole number of trading sessions | Required when `avg_amount_usd` is available; MUST be unavailable when that average is unavailable |

- **FR-005**: The system MUST reject unknown fields at snapshot, source, and instrument levels so misspelled fields cannot be ignored. A field-set change therefore requires a compatibility review and a new version when existing consumers would reject it.
- **FR-006**: Ticker canonicalization MUST match existing universe normalization: trim surrounding whitespace, uppercase, and preserve order and embedded characters. Unlike universe list normalization, snapshot validation MUST reject duplicate canonical tickers rather than silently deduplicating them.
- **FR-007**: Validation MUST return either a complete canonical snapshot as JSON-compatible values or a failure containing all independently detectable issues. It MUST NOT return a partially validated snapshot. Canonical comparison MUST use field content rather than serialized bytes; object key order and insignificant whitespace are not contractual. Only normalization explicitly declared by this specification is applied, and every unavailable optional instrument field MUST be represented as null in canonical output even when its input key was absent.
- **FR-008**: Every validation issue MUST include a stable machine-readable reason, a human-readable explanation, and an exact location such as `instruments[2].price`; duplicate issues MUST identify both conflicting rows. The documented reason vocabulary MUST distinguish `missing_field`, `null_value`, `invalid_type`, `invalid_value`, `unknown_field`, `duplicate_code`, `unsupported_schema_version`, `invalid_timestamp_order`, `stale_snapshot`, `future_snapshot`, and `inconsistent_optional_fields`.
- **FR-009**: Optional missing values MUST remain explicitly unavailable. Required-field absence, null required values, wrong data types, invalid numeric values, and unavailable optional values MUST be distinguishable in validation results.
- **FR-010**: Suspended instruments MUST remain in the validated snapshot with their status intact. Eligibility, filtering, scoring, and ranking are outside this feature.
- **FR-011**: Freshness validation MUST accept an explicit reference time using the same RFC 3339 representation as snapshot timestamps and a non-negative whole-number maximum age in seconds. Both MUST be supplied together or neither supplied. Validation MUST use only those inputs rather than the current wall clock and MUST reject future-dated or over-age snapshots with field-specific issues.
- **FR-012**: The feature MUST include deterministic synthetic offline fixtures with expected outcomes for: a valid multi-instrument snapshot; absent and null optional metrics; lowercase and padded tickers; a suspended instrument; an empty universe; missing and null required fields; unknown fields; duplicate canonical tickers; invalid timestamps and source metadata; stale and future-dated snapshots under explicit policies; unsupported schema versions; negative and non-finite numbers; and valid extreme finite values.
- **FR-013**: Every malformed fixture MUST declare its expected field locations and reasons. Every valid fixture MUST declare its expected canonical representation so tests verify semantics rather than merely acceptance.
- **FR-014**: The current-version valid fixture MUST serve as a compatibility baseline. Breaking changes—including renames, removals, unit or meaning changes, and newly required values—MUST increment the schema version and preserve the prior baseline for compatibility testing.
- **FR-015**: All fixture validation MUST run without network access, live providers, persistence, language models, ranking, or changes to existing funds and trading workflows.

### Key Entities *(include if feature involves data)*

- **Discovery Snapshot**: One versioned observation of a candidate pool. It contains source metadata, observation and retrieval timestamps, and instrument records. It is an input to research, not evidence of investment suitability.
- **Instrument Record**: One uniquely identified security within a snapshot, including canonical ticker, display name, exchange, currency, trading status, core market fields, and optional ranking metrics.
- **Validation Policy**: Optional explicit reference time and maximum age used for deterministic freshness evaluation; it does not alter the recorded snapshot timestamps.
- **Validation Issue**: A stable reason, exact field location, and readable explanation. Issues are ordered deterministically by their location and reason so replay results can be compared.
- **Offline Fixture**: Synthetic snapshot content with provenance, expected canonical output or expected issues, and no dependency on a live service.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of valid representative fixtures pass with their declared canonical output, and 100% of deliberately malformed fixtures fail with every declared field location and reason.
- **SC-002**: Every malformed fixture produces at least one issue containing an exact field location, stable reason, and readable explanation; no malformed fixture yields a partial snapshot.
- **SC-003**: Repeating validation of each fixture with identical inputs produces identical canonical content and ordered issues in 100% of runs, with no network access or wall-clock dependence.
- **SC-004**: The fixture suite covers all valid and malformed cases enumerated in FR-012, including both sides of the freshness boundary and both valid and invalid extreme numeric values.
- **SC-005**: Compatibility checks accept the version-1 baseline and reject 100% of missing, malformed, and unsupported version fixtures with a schema-version-specific reason.

## Assumptions

- This is an MVP-only contract and fixture suite. It establishes the offline input boundary needed before ranking; production operations, external integrations, persistence, live providers, and broader migration tooling remain deferred to later features.
- Initial representative fixtures use US-listed equity examples, but the data contract retains exchange and per-instrument currency metadata rather than claiming all markets are supported by a provider.
- Fixtures are synthetic rather than recorded upstream samples, making their provenance and expected values explicit and avoiding dependence on upstream availability or licensing of market data.
- Historical snapshots are valid research inputs when structurally correct. Freshness rejection requires an explicit policy because no single age limit fits historical replay, market closures, and all future providers.
- The MVP timestamp parser validates ordinary representable calendar instants and rejects leap-second `:60`, year 0000, and UTC conversions outside years 0001–9999; no leap-second or extended-calendar infrastructure is introduced.
- The existing universe canonicalization behavior is the authority for ticker trimming and casing. Provider-specific symbol translation and ambiguous cross-listing resolution are outside this contract.
- An empty or entirely suspended snapshot can be valid data even though it produces no usable research candidates; later ranking behavior must not be hidden inside contract validation.
- Schema version 1 establishes the baseline only. No migration from an earlier discovery-snapshot format exists because this is the first such contract.
- This feature has no feature dependencies. Its only reused behavior is the repository's existing ticker trimming, uppercase conversion, and embedded-character preservation.
