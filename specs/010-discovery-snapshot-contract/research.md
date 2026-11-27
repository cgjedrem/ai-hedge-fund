# Phase 0 Research: Discovery Snapshot Contract

**Date**: 2026-11-25 | **Feature**: [spec.md](spec.md)

No technical unknowns remain. The design uses only the repository's existing Python and Pydantic dependencies. Research probes covered the locked Pydantic 2.13.4 and the latest patch releases of Pydantic 2.4–2.14; ordinary tests must pin the behaviors on which the contract relies because the declared range permits later v2 releases.

## D1 — Use a small module inside the existing Python package

**Decision**: Add `hedge_fund/discovery/` with strict input models, one validation pipeline, synthetic fixtures, and co-located tests. Do not add a service, CLI, web route, storage layer, or dependency.

**Rationale**: The feature is a reusable data contract for offline feature 011. Existing project conventions already supply Pydantic modeling, pytest discovery, network isolation, and formatting. `hedge_fund/features/snapshot.py` represents analyst fundamentals, so a separate discovery namespace avoids overloading that concept.

**Alternatives considered**: Extending `FundamentalsSnapshot` was rejected because it models filed fundamentals, not market-universe observations. A JSON Schema runtime and standalone validation service add machinery without satisfying an MVP requirement.

**Sources**: `pyproject.toml`; `poetry.lock`; `hedge_fund/features/snapshot.py`; `hedge_fund/conftest.py`.

## D2 — Configure every Pydantic model explicitly

**Decision**: Use a shared base model with `ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)`. Keep timestamp fields as strings. Validate schema version with `StrictInt` plus an explicit value check, not `Literal[1]`.

**Rationale**: Pydantic aggregates field errors and supports required fields, exact unknown-field locations, strict strings/lists, optional nulls, and constraints. Model configuration does not reliably propagate through nested configuration boundaries, so every model must inherit the same base. Probes found version-dependent `Literal[1]` handling of booleans; `StrictInt` avoids it.

**Alternatives considered**: Unconfigured nested models and per-call `extra=` options are inconsistent across the supported version range. Manual-only shape validation would duplicate Pydantic's useful structural checks.

**Sources**: [Strict mode](https://docs.pydantic.dev/2.13/concepts/strict_mode/); [model configuration](https://docs.pydantic.dev/2.13/concepts/config/); [models and extra fields](https://docs.pydantic.dev/2.13/concepts/models/#extra-fields); `hedge_fund/fund/spec.py`.

## D3 — Preserve JSON numeric values with explicit guards

**Decision**: Add a small exact JSON-type precheck and custom numeric validators. Numeric fields accept only built-in `int` or `float`, reject booleans and non-finite floats, enforce their bounds, and return the original number unchanged. A missing optional number becomes `None`; a supplied integer is not converted to float.

**Rationale**: Strict Pydantic floats still accept integers and can silently lose integer precision. They also admit some non-JSON Python numeric types. The clarification permits only declared normalization, which names ticker and timestamp normalization but not numeric coercion. Custom validators produce one stable error per numeric field and avoid noisy union errors.

**Alternatives considered**: Declaring every number as float is simpler but changes values and violates the normalization boundary. `StrictInt | FiniteFloat` preserves values but requires collapsing version-dependent union locations and errors. A third-party JSON validator is unnecessary.

**Sources**: [Conversion table](https://pydantic.dev/docs/validation/latest/concepts/conversion_table/); [Pydantic numeric types](https://docs.pydantic.dev/2.13/api/types/); [validation errors](https://docs.pydantic.dev/2.13/errors/validation_errors/).

## D4 — Adapt internal errors to the public issue contract

**Decision**: Translate Pydantic error `type` and structured `loc`, never its message or documentation URL, into `ValidationIssue(location, reason, message, related_locations)`. Render root as `$` and nested fields as paths such as `instruments[0].price`. Use dotted segments only for object keys matching `[A-Za-z_][A-Za-z0-9_]*`; encode every other key as a bracketed JSON string, with `$` prefixing a bracketed root key. Deduplicate identical issues and sort structured object keys lexicographically and array indices numerically before rendering.

**Rationale**: Pydantic messages and URLs can vary by release. The specification owns the stable reason vocabulary and deterministic ordering. A malformed schema version therefore yields `invalid_type` at `schema_version`; a missing one yields `missing_field`; a valid non-1 integer yields `unsupported_schema_version`.

**Alternatives considered**: Returning `ValidationError` directly exposes unstable implementation details. Fail-fast validation violates the all-independently-detectable-issues requirement. Sorting rendered paths is rejected because index 10 would sort before index 2.

**Sources**: [Error handling](https://docs.pydantic.dev/2.13/concepts/models/#error-handling); [custom errors](https://docs.pydantic.dev/2.13/errors/errors/); [validators](https://docs.pydantic.dev/2.13/concepts/validators/).

## D5 — Run independent semantic checks over raw input

**Decision**: Supplement model validation with a second pass for duplicate canonical codes, optional-pair consistency, timestamp ordering, policy completeness, and freshness. Each pass guards its own prerequisites and contributes issues even when another pass fails. Return no canonical snapshot if any issue exists.

**Rationale**: Pydantic may skip after-validators when an inner field fails. Independent raw-input checks are required to report, for example, a price type error, duplicate codes, and timestamp order together. These checks are small and deterministic.

**Alternatives considered**: Model-level after-validators alone cannot meet aggregation semantics. Continuing with a partially validated model risks incomplete or misleading canonical output.

**Sources**: [Pydantic validator behavior](https://docs.pydantic.dev/2.13/concepts/validators/); specification FR-005, FR-010, FR-011, FR-014.

## D6 — Validate and canonicalize timestamps outside Pydantic datetime

**Decision**: Carry timestamps as strings. A full-match ASCII parser accepts RFC 3339 `T`/`t`, `Z`/`z`, explicit numeric offsets, and arbitrary nonzero-length dot fractions. Standard-library `datetime` validates the representable calendar date and converts whole seconds to UTC; the original fraction digits are appended unchanged and the output uses uppercase `T` and trailing `Z`.

**Rationale**: Pydantic datetime accepts non-RFC forms, truncates fractions beyond six digits, drops zero-only fractions, and pads other fractions during serialization. Whole-minute offset conversion does not alter fractional digits, so a string-based canonicalizer satisfies the clarified contract without a new dependency.

**Alternatives considered**: Pydantic datetime and Python `fromisoformat` are too permissive and lossy. Restricting fractions to six digits contradicts the accepted clarification. A general date-time library is unnecessary.

**MVP boundary**: Reject leap-second `:60`, year 0000, and UTC conversions outside years 0001–9999 as `invalid_value`; the standard-library calendar cannot represent them. Accept RFC 3339 `-00:00` as the same instant as UTC while canonicalizing to `Z`.

**Sources**: [RFC 3339 grammar and offset semantics](https://www.rfc-editor.org/rfc/rfc3339.txt); [Pydantic datetime types](https://docs.pydantic.dev/2.13/api/standard_library_types/#datetime-types); [Python datetime](https://docs.python.org/3.11/library/datetime.html).

## D7 — Use exact arithmetic for ordering and freshness

**Decision**: Parse each valid timestamp into whole UTC seconds plus its original fraction-digit string. Compare whole seconds first, then compare fractional digits exactly with zero extension; compare age by adding integer `max_age_seconds` to the observation whole seconds. Keep canonical text separately. Do not convert fraction digits to integers or floats.

**Rationale**: Decimal-string comparison preserves arbitrary precision with linear work. It supports timestamp order, future detection, and exact freshness boundaries without changing canonical text or imposing a digit cap.

**Alternatives considered**: Datetime microseconds and floats can change boundary outcomes. Decimal arithmetic needs a deliberately managed precision context for arbitrary fractions. Lexicographic timestamp comparison alone does not calculate age.

**Sources**: [Python fractions](https://docs.python.org/3.11/library/fractions.html); specification FR-003, FR-011, and the timestamp clarification.

## D8 — Reuse ticker normalization, not universe-list semantics

**Decision**: Extract `normalize_ticker` from the existing `normalize_universe` loop, export it, and use it for each valid instrument code. Keep `normalize_universe` responsible for order-preserving list deduplication and its existing empty-universe exception.

**Rationale**: Snapshot codes need the exact same `strip().upper()` behavior, but empty snapshots are valid and duplicate rows must be reported rather than silently deduplicated. Calling `normalize_universe` for the whole instrument list would impose the wrong semantics.

**Alternatives considered**: Duplicating the expression risks drift. Pydantic string constraints differ from Python stripping for some control characters. Calling `normalize_universe` on the full list would hide duplicates and reject empty snapshots.

**Sources**: `hedge_fund/fund/spec.py`; `hedge_fund/fund/test_spec.py`; specification FR-006 and FR-010.

## D9 — Validate with deterministic in-memory fixtures

**Decision**: Store named synthetic dictionaries and expected snapshots/issues in `fixtures.py`. Tests deep-copy inputs, assert exact outcomes, and replay them. Freshness always receives an explicit reference timestamp and age.

**Rationale**: This proves end-to-end contract behavior without files, network, credentials, providers, or wall-clock state. Expected issues compare locations and reasons; canonical snapshots compare complete field content, including null optional fields.

**Alternatives considered**: Live provider samples and persisted fixture files add unrelated I/O. Numeric score expectations belong to feature 011, not this contract.

## D10 — Keep currency validation format-only for the MVP

**Decision**: Require exactly three uppercase ASCII letters for `currency`, without checking membership in an ISO 4217 registry. Accept a synthetic `ZZZ` fixture as format-valid and reject lowercase or non-ASCII forms.

**Rationale**: Version 1 needs a stable syntactic identifier, not a maintained currency reference dataset. Format-only validation keeps the feature offline, deterministic, and dependency-free while making the limited guarantee explicit.

**Alternatives considered**: An embedded ISO 4217 allowlist would reject unassigned codes but introduce a curated dataset and update policy unrelated to the snapshot-validation MVP. A new registry dependency is outside the approved scope.

**Sources**: specification FR-004 and Assumptions; `data-model.md`.
