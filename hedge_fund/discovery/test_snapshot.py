"""Contract tests for offline discovery snapshot validation."""

import json
import sys
import time
from copy import deepcopy
from dataclasses import FrozenInstanceError

import pytest
from pydantic import ValidationError

import hedge_fund.discovery.snapshot as snapshot_module
from hedge_fund.discovery import validate_snapshot
from hedge_fund.discovery.fixtures import (
    US1_FIXTURES,
    US2_FIXTURES,
    US3_FIXTURES,
    VALID_V1_CANONICAL,
    VALID_V1_RAW,
)
from hedge_fund.discovery.models import (
    _StrictModel,
    SnapshotValidationResult,
    ValidationIssue,
)
from hedge_fund.discovery.snapshot import (
    _adapt_pydantic_errors,
    _IssueDraft,
    _ordered_issues,
    _parse_timestamp,
    _render_location,
)


def test_result_records_are_frozen():
    issue = ValidationIssue(location="schema_version", reason="missing_field", message="Required field is missing.", related_locations=())
    result = SnapshotValidationResult(snapshot={"schema_version": 1}, issues=())

    with pytest.raises(FrozenInstanceError):
        issue.reason = "invalid_value"
    with pytest.raises(FrozenInstanceError):
        result.snapshot = None


def test_shared_pydantic_base_is_strict_for_types_extras_and_non_finite_numbers():
    class Probe(_StrictModel):
        count: int
        ratio: float

    with pytest.raises(ValidationError):
        Probe.model_validate({"count": True, "ratio": 1.0})
    with pytest.raises(ValidationError):
        Probe.model_validate({"count": 1, "ratio": float("inf")})
    with pytest.raises(ValidationError):
        Probe.model_validate({"count": 1, "ratio": 1.0, "unknown": 2})


def test_pydantic_error_adapter_uses_stable_reasons_and_escaped_locations():
    class Probe(_StrictModel):
        count: int

    raw = {"count": "not-an-int", "top.key": 1}
    with pytest.raises(ValidationError) as caught:
        Probe.model_validate(raw)

    issues = _ordered_issues(_adapt_pydantic_errors(raw, caught.value))

    assert [(issue.location, issue.reason) for issue in issues] == [
        ("count", "invalid_type"),
        ('$["top.key"]', "unknown_field"),
    ]
    assert all("Input should" not in issue.message for issue in issues)


@pytest.mark.parametrize(
    "value,canonical",
    [
        ("2026-01-02t03:04:05.000+01:00", "2026-01-02T02:04:05.000Z"),
        ("2026-01-02T03:04:05z", "2026-01-02T03:04:05Z"),
        ("2026-01-02T03:04:05.1234567-02:30", "2026-01-02T05:34:05.1234567Z"),
    ],
)
def test_timestamp_parser_canonicalizes_utc_without_fraction_changes(value, canonical):
    observed, _ = _parse_timestamp(value)

    assert observed == canonical


def test_timestamp_parser_keeps_exact_fraction_and_offset_instant():
    whole, whole_instant = _parse_timestamp("2026-01-02T03:04:05Z")
    fractional, fractional_instant = _parse_timestamp("2026-01-02T04:04:05.1234567+01:00")
    offset, offset_instant = _parse_timestamp("2026-01-02T00:04:05-03:00")

    assert whole == "2026-01-02T03:04:05Z"
    assert fractional == "2026-01-02T03:04:05.1234567Z"
    assert snapshot_module._compare_instants(fractional_instant, whole_instant) > 0
    assert snapshot_module._compare_instants(offset_instant, whole_instant) == 0


@pytest.mark.parametrize(
    "value",
    [
        1_767_320_645,
        "2026-01-02T03:04:05",
        "2026-01-02 03:04:05Z",
        "2026-01-02T03:04Z",
        "2026-01-02T03:04:05,1Z",
        "2026-01-02T03:04:05+0100",
        "2026-01-02T03:04:60Z",
        "0000-01-02T03:04:05Z",
        "2026-02-30T03:04:05Z",
        "0001-01-01T00:00:00+23:59",
        "9999-12-31T23:59:59-23:59",
    ],
)
def test_timestamp_parser_rejects_non_rfc3339_or_unrepresentable_values(value):
    with pytest.raises(ValueError):
        _parse_timestamp(value)


def test_location_renderer_escapes_keys_without_collisions():
    assert _render_location(()) == "$"
    assert _render_location(("source.extra",)) == '$["source.extra"]'
    assert _render_location(("source", "extra")) == "source.extra"
    assert _render_location(("instruments", 0, "bad.key")) == 'instruments[0]["bad.key"]'
    assert _render_location(('quote"key',)) == '$["quote\\"key"]'
    assert _render_location(("slash\\key",)) == '$["slash\\\\key"]'
    assert _render_location(("control\nkey",)) == '$["control\\nkey"]'
    assert _render_location(("\ud800",)) == '$["\\ud800"]'
    assert _render_location(("bad[bracket]",)) == '$["bad[bracket]"]'


def test_unknown_key_with_brackets_uses_unambiguous_location():
    raw = deepcopy(VALID_V1_RAW)
    raw["bad[key]"] = 1

    result = validate_snapshot(raw)

    assert _issue_signature(result.issues) == (('$["bad[key]"]', "unknown_field", ()),)


def test_issue_order_uses_numeric_array_indices_before_rendering():
    issues = _ordered_issues(
        [
            _IssueDraft(("instruments", 10, "price"), "invalid_type", "wrong type"),
            _IssueDraft(("instruments", 2, "price"), "invalid_type", "wrong type"),
        ]
    )

    assert [issue.location for issue in issues] == ["instruments[2].price", "instruments[10].price"]


def _issue_signature(issues):
    return tuple((issue.location, issue.reason, issue.related_locations) for issue in issues)


@pytest.mark.parametrize("name", sorted(US1_FIXTURES))
def test_us1_fixture_has_exact_canonical_content_or_ordered_issues(name):
    fixture = US1_FIXTURES[name]
    result = validate_snapshot(deepcopy(fixture["raw"]))

    assert _issue_signature(result.issues) == fixture["expected_issues"]
    if fixture["expected_issues"]:
        assert result.snapshot is None
        assert all(issue.message for issue in result.issues)
    else:
        assert result.snapshot == fixture["expected_snapshot"]
        assert result.issues == ()

    repeated = validate_snapshot(deepcopy(fixture["raw"]))
    assert repeated.snapshot == result.snapshot
    assert repeated.issues == result.issues


def test_issue_locations_sort_instrument_indices_numerically():
    raw = deepcopy(VALID_V1_RAW)
    template = deepcopy(raw["instruments"][0])
    raw["instruments"] = [deepcopy(template) for _ in range(11)]
    for index, instrument in enumerate(raw["instruments"]):
        instrument["code"] = f"S{index:03d}"
    raw["instruments"][2]["price"] = "invalid"
    raw["instruments"][10]["change_pct"] = True

    result = validate_snapshot(raw)

    assert _issue_signature(result.issues) == (
        ("instruments[2].price", "invalid_type", ()),
        ("instruments[10].change_pct", "invalid_type", ()),
    )
    assert result.snapshot is None


@pytest.mark.parametrize("raw", [None, [], "not-an-object"])
def test_non_mapping_snapshot_root_is_an_invalid_type(raw):
    result = validate_snapshot(raw)

    assert result.snapshot is None
    assert _issue_signature(result.issues) == (("$", "invalid_type", ()),)


def test_cyclic_python_input_is_rejected_without_partial_output():
    raw = deepcopy(VALID_V1_RAW)
    raw["instruments"].append(raw)

    result = validate_snapshot(raw)

    assert result.snapshot is None
    assert _issue_signature(result.issues) == (("instruments[2]", "invalid_type", ()),)


def test_deeply_nested_json_input_returns_invalid_type_without_partial_output():
    raw = deepcopy(VALID_V1_RAW)
    nested = []
    for _ in range(1500):
        nested = [nested]
    raw["unexpected"] = nested

    result = validate_snapshot(raw)

    assert result.snapshot is None
    assert _issue_signature(result.issues) == (("unexpected", "unknown_field", ()),)


def test_deeply_nested_json_result_is_independent_of_recursion_limit():
    raw = deepcopy(VALID_V1_RAW)
    nested = []
    for _ in range(1500):
        nested = [nested]
    raw["unexpected"] = nested
    original_limit = sys.getrecursionlimit()

    try:
        sys.setrecursionlimit(5000)
        result = validate_snapshot(raw)
    finally:
        sys.setrecursionlimit(original_limit)

    assert result.snapshot is None
    assert _issue_signature(result.issues) == (("unexpected", "unknown_field", ()),)


def test_validation_result_is_equivalent_with_100_caller_frames():
    raw = deepcopy(VALID_V1_RAW)
    nested = []
    for _ in range(900):
        nested = [nested]
    raw["unexpected"] = nested

    def wrapped(frames):
        if frames == 0:
            return validate_snapshot(raw)
        return wrapped(frames - 1)

    direct = validate_snapshot(raw)
    indirect = wrapped(100)

    assert _issue_signature(direct.issues) == (("unexpected", "unknown_field", ()),)
    assert indirect == direct


def test_valid_baseline_comparison_ignores_mapping_key_order():
    raw = deepcopy(VALID_V1_RAW)
    raw = dict(reversed(tuple(raw.items())))
    raw["instruments"] = [dict(reversed(tuple(instrument.items()))) for instrument in reversed(raw["instruments"])]
    expected = deepcopy(VALID_V1_CANONICAL)

    result = validate_snapshot(raw)

    expected["instruments"].reverse()
    assert result.snapshot == expected
    assert result.issues == ()


def test_canonical_comparison_uses_json_field_content_not_serialized_bytes():
    result = validate_snapshot(deepcopy(VALID_V1_RAW))
    pretty = json.dumps(result.snapshot, indent=2, sort_keys=True)
    compact = json.dumps(result.snapshot, separators=(",", ":"), sort_keys=False)

    assert pretty != compact
    assert json.loads(pretty) == json.loads(compact) == result.snapshot


@pytest.mark.parametrize("name", sorted(US2_FIXTURES))
def test_us2_fixture_has_exact_replay_or_freshness_issues(name):
    fixture = US2_FIXTURES[name]
    policy = {key: fixture[key] for key in ("reference_time", "max_age_seconds") if fixture[key] is not None}
    result = validate_snapshot(deepcopy(fixture["raw"]), **policy)

    assert _issue_signature(result.issues) == fixture["expected_issues"]
    if fixture["expected_issues"]:
        assert result.snapshot is None
    else:
        assert result.snapshot == fixture["expected_snapshot"]
        assert result.issues == ()

    repeated = validate_snapshot(deepcopy(fixture["raw"]), **policy)
    assert repeated.snapshot == result.snapshot
    assert repeated.issues == result.issues


@pytest.mark.parametrize(
    "value",
    [
        "2026-01-02T03:04:05",
        "2026-01-02 03:04:05Z",
        "2026-01-02T03:04Z",
        "2026-01-02T03:04:05,1Z",
        "2026-01-02T03:04:05+0100",
        "2026-02-30T03:04:05Z",
        "2026-01-02T03:04:60Z",
        "0000-01-02T03:04:05Z",
        "2026-01-02T03:04:05 PST",
    ],
)
def test_public_timestamp_boundary_rejects_malformed_snapshot_times(value):
    raw = deepcopy(VALID_V1_RAW)
    raw["snapshot_at"] = value

    result = validate_snapshot(raw)

    assert result.snapshot is None
    assert _issue_signature(result.issues) == (("snapshot_at", "invalid_value", ()),)


@pytest.mark.parametrize("field", ["snapshot_at", "retrieved_at"])
def test_public_timestamp_boundary_rejects_numeric_time_at_its_field(field):
    raw = deepcopy(VALID_V1_RAW)
    raw[field] = 1_767_320_645

    result = validate_snapshot(raw)

    assert result.snapshot is None
    assert _issue_signature(result.issues) == ((field, "invalid_type", ()),)


def test_historical_validation_never_reads_wall_clock(monkeypatch):
    real_datetime = snapshot_module.datetime

    class ClockTrap:
        def __new__(cls, *args, **kwargs):
            return real_datetime(*args, **kwargs)

        @staticmethod
        def now(*args, **kwargs):
            raise AssertionError("wall clock read")

    monkeypatch.setattr(snapshot_module, "datetime", ClockTrap)

    result = validate_snapshot(deepcopy(US2_FIXTURES["historical_without_policy"]["raw"]))

    assert result.snapshot == US2_FIXTURES["historical_without_policy"]["expected_snapshot"]
    assert result.issues == ()


def test_freshness_policy_never_reads_wall_clock(monkeypatch):
    real_datetime = snapshot_module.datetime

    class ClockTrap:
        def __new__(cls, *args, **kwargs):
            return real_datetime(*args, **kwargs)

        @staticmethod
        def now(*args, **kwargs):
            raise AssertionError("wall clock read")

    monkeypatch.setattr(snapshot_module, "datetime", ClockTrap)
    result = validate_snapshot(
        deepcopy(VALID_V1_RAW),
        reference_time="2026-11-25T09:16:00.1234567Z",
        max_age_seconds=60,
    )

    assert result.snapshot == VALID_V1_CANONICAL
    assert result.issues == ()


@pytest.mark.parametrize("name", sorted(US3_FIXTURES))
def test_us3_compatibility_fixture_preserves_v1_without_silent_migration(name):
    fixture = US3_FIXTURES[name]
    result = validate_snapshot(deepcopy(fixture["raw"]))

    assert _issue_signature(result.issues) == fixture["expected_issues"]
    assert fixture["compatibility_expectation"] == ("version-1-baseline" if fixture["change_kind"] == "baseline" else "new-schema-version-required")
    if fixture["expected_issues"]:
        assert result.snapshot is None
    else:
        assert result.snapshot == fixture["expected_snapshot"]
        assert result.snapshot["schema_version"] == 1
        assert result.issues == ()

    if fixture["change_kind"] in ("unit-change", "meaning-change"):
        assert fixture["raw"]["schema_version"] == 2
        assert _issue_signature(result.issues) == (("schema_version", "unsupported_schema_version", ()),)
    if fixture["change_kind"] == "unit-change":
        assert fixture["raw"]["instruments"][0]["amount"] == 1_000.0
        assert fixture["raw"]["instruments"][0]["amount"] != VALID_V1_RAW["instruments"][0]["amount"]
    if fixture["change_kind"] == "meaning-change":
        assert fixture["raw"]["instruments"][0]["change_pct"] == 1.25
        assert fixture["raw"]["instruments"][0]["change_pct"] != VALID_V1_RAW["instruments"][0]["change_pct"]

    repeated = validate_snapshot(deepcopy(fixture["raw"]))
    assert repeated.snapshot == result.snapshot
    assert repeated.issues == result.issues


@pytest.mark.parametrize(
    "value",
    [True, 20.0, "20"],
)
def test_average_amount_window_rejects_non_strict_integers(value):
    raw = deepcopy(VALID_V1_RAW)
    raw["instruments"][0]["avg_amount_usd_window_days"] = value

    result = validate_snapshot(raw)

    assert _issue_signature(result.issues) == (("instruments[0].avg_amount_usd_window_days", "invalid_type", ()),)


@pytest.mark.parametrize(
    "value,expected",
    [
        ("2026-01-02T03:04:05.5Z", "2026-01-02T03:04:05.5Z"),
        ("2026-01-02T03:04:05.120Z", "2026-01-02T03:04:05.120Z"),
        ("2026-01-02T03:04:05-00:00", "2026-01-02T03:04:05Z"),
    ],
)
def test_timestamp_precision_and_unknown_offset_form_are_preserved(value, expected):
    raw = deepcopy(VALID_V1_RAW)
    raw["snapshot_at"] = value
    raw["retrieved_at"] = value

    result = validate_snapshot(raw)

    assert result.snapshot is not None
    assert result.snapshot["snapshot_at"] == expected


@pytest.mark.parametrize(
    "value",
    [
        "2026-01-02T03:04:05+24:00",
        "2026-01-02T24:00:00Z",
    ],
)
def test_timestamp_rejects_out_of_range_offset_and_hour(value):
    raw = deepcopy(VALID_V1_RAW)
    raw["snapshot_at"] = value

    result = validate_snapshot(raw)

    assert _issue_signature(result.issues) == (("snapshot_at", "invalid_value", ()),)


def test_three_way_duplicate_codes_report_each_other_row():
    raw = deepcopy(VALID_V1_RAW)
    template = raw["instruments"][0]
    raw["instruments"] = [dict(template, code="DUP") for _ in range(3)]

    result = validate_snapshot(raw)

    assert _issue_signature(result.issues) == (
        ("instruments[0].code", "duplicate_code", ("instruments[1].code", "instruments[2].code")),
        ("instruments[1].code", "duplicate_code", ("instruments[0].code", "instruments[2].code")),
        ("instruments[2].code", "duplicate_code", ("instruments[0].code", "instruments[1].code")),
    )


def test_duplicate_related_locations_are_bounded_with_remainder_count():
    raw = deepcopy(VALID_V1_RAW)
    template = raw["instruments"][0]
    raw["instruments"] = [dict(template, code="DUP") for _ in range(12)]

    result = validate_snapshot(raw)
    first = result.issues[0]

    assert first.location == "instruments[0].code"
    assert first.related_locations == tuple(f"instruments[{index}].code" for index in range(1, 11))
    assert "1 related locations omitted" in first.message


def test_ten_thousand_duplicate_rows_have_bounded_output_and_linear_runtime():
    raw = deepcopy(VALID_V1_RAW)
    template = raw["instruments"][0]
    count = 10_000
    raw["instruments"] = [dict(template, code="DUP") for _ in range(count)]
    started = time.perf_counter()

    result = validate_snapshot(raw)

    elapsed = time.perf_counter() - started
    assert elapsed < 5
    assert result.snapshot is None
    assert len(result.issues) == count
    assert sum(len(issue.related_locations) for issue in result.issues) == count * 10
    for index, issue in enumerate(result.issues):
        assert issue.location == f"instruments[{index}].code"
        candidates = range(11) if index <= 10 else range(10)
        expected = tuple(f"instruments[{other}].code" for other in candidates if other != index)[:10]
        assert issue.related_locations == expected
        assert "9989 related locations omitted" in issue.message


def test_huge_timestamp_fractions_compare_exactly_without_integer_conversion(monkeypatch):
    def fail_fraction_conversion(_digits):
        raise AssertionError("fraction digits converted to an integer")

    monkeypatch.setattr(snapshot_module, "_fraction_digits", fail_fraction_conversion, raising=False)
    snapshot_fraction = "1" * 49_999 + "0"
    reference_fraction = "1" * 49_999 + "1"
    raw = deepcopy(VALID_V1_RAW)
    raw["snapshot_at"] = f"2026-01-02T03:04:05.{snapshot_fraction}Z"
    raw["retrieved_at"] = raw["snapshot_at"]
    reference_time = f"2026-01-02T03:04:06.{reference_fraction}Z"

    result = validate_snapshot(raw, reference_time=reference_time, max_age_seconds=1)

    assert _issue_signature(result.issues) == (("snapshot_at", "stale_snapshot", ()),)
    assert result.snapshot is None


def test_unbounded_integer_validates_without_json_serialization_bound():
    raw = deepcopy(VALID_V1_RAW)
    huge_integer = 10**5000
    raw["instruments"][0]["price"] = huge_integer

    result = validate_snapshot(raw)

    assert result.snapshot is not None
    assert type(result.snapshot["instruments"][0]["price"]) is int
    assert result.snapshot["instruments"][0]["price"] == huge_integer
    with pytest.raises(ValueError):
        json.dumps(result.snapshot)


def test_shared_references_are_rejected_without_expanding_exponentially():
    shared = []
    for _ in range(16):
        shared = [shared, shared]
    raw = deepcopy(VALID_V1_RAW)
    raw["unexpected"] = shared
    started = time.perf_counter()

    result = validate_snapshot(raw)

    elapsed = time.perf_counter() - started
    structural_issues = [issue for issue in result.issues if issue.reason == "invalid_type"]
    assert elapsed < 5
    assert result.snapshot is None
    assert _issue_signature(result.issues)[0] == ("unexpected", "unknown_field", ())
    assert len(structural_issues) == 16
    assert all(issue.location.startswith("unexpected[") for issue in structural_issues)


@pytest.mark.parametrize(
    "field,value,reason",
    [
        ("code", 7, "invalid_type"),
        ("name", 7, "invalid_type"),
        ("exchange", 7, "invalid_type"),
        ("industry", 7, "invalid_type"),
    ],
)
def test_instrument_text_fields_reject_non_string_values(field, value, reason):
    raw = deepcopy(VALID_V1_RAW)
    raw["instruments"][0][field] = value

    result = validate_snapshot(raw)

    assert _issue_signature(result.issues) == ((f"instruments[0].{field}", reason, ()),)


@pytest.mark.parametrize("field", ["name", "exchange"])
def test_instrument_name_and_exchange_reject_blank_text(field):
    raw = deepcopy(VALID_V1_RAW)
    raw["instruments"][0][field] = "   "

    result = validate_snapshot(raw)

    assert _issue_signature(result.issues) == ((f"instruments[0].{field}", "invalid_value", ()),)


@pytest.mark.parametrize(
    "value,reason",
    [
        (None, "null_value"),
        ([], "invalid_type"),
    ],
)
def test_source_rejects_null_or_non_object(value, reason):
    raw = deepcopy(VALID_V1_RAW)
    raw["source"] = value

    result = validate_snapshot(raw)

    assert _issue_signature(result.issues) == (("source", reason, ()),)


@pytest.mark.parametrize(
    "value,reason",
    [
        (None, "null_value"),
        ("not-an-object", "invalid_type"),
    ],
)
def test_instrument_rows_reject_null_or_non_object_values(value, reason):
    raw = deepcopy(VALID_V1_RAW)
    raw["instruments"] = [value]

    result = validate_snapshot(raw)

    assert _issue_signature(result.issues) == ((("instruments[0]"), reason, ()),)


def test_schema_version_null_is_null_value():
    raw = deepcopy(VALID_V1_RAW)
    raw["schema_version"] = None

    result = validate_snapshot(raw)

    assert _issue_signature(result.issues) == (("schema_version", "null_value", ()),)


def test_invalid_snapshot_timestamp_suppresses_freshness_claims():
    raw = deepcopy(VALID_V1_RAW)
    raw["snapshot_at"] = "not-a-timestamp"

    result = validate_snapshot(raw, reference_time="2100-01-01T00:00:00Z", max_age_seconds=0)

    assert _issue_signature(result.issues) == (("snapshot_at", "invalid_value", ()),)


def test_freshness_none_arguments_are_disabled_even_when_explicit():
    raw = deepcopy(US2_FIXTURES["historical_without_policy"]["raw"])

    omitted = validate_snapshot(raw)
    explicit = validate_snapshot(raw, reference_time=None, max_age_seconds=None)

    assert explicit == omitted
    assert explicit.snapshot is not None
    assert explicit.issues == ()


def test_freshness_argument_locations_do_not_collide_with_snapshot_fields():
    raw = deepcopy(VALID_V1_RAW)
    raw["max_age_seconds"] = 1

    result = validate_snapshot(raw, reference_time="2026-11-25T09:16:00Z")

    assert _issue_signature(result.issues) == (
        ("argument.max_age_seconds", "missing_field", ()),
        ("max_age_seconds", "unknown_field", ()),
    )


def test_surrogate_unknown_key_does_not_mask_independent_issues():
    raw = deepcopy(VALID_V1_RAW)
    raw["schema_version"] = 2
    raw["instruments"][0]["price"] = -1
    raw["\ud800"] = "unknown"

    result = validate_snapshot(raw)

    assert _issue_signature(result.issues) == (
        ("instruments[0].price", "invalid_value", ()),
        ("schema_version", "unsupported_schema_version", ()),
        ('$["\\ud800"]', "unknown_field", ()),
    )


def test_invalid_object_subclasses_never_reach_pydantic_getters():
    calls = []

    class RuntimeErrorGetter(dict):
        def get(self, *args, **kwargs):
            calls.append("get")
            raise RuntimeError("getter called")

        def items(self):
            calls.append("items")
            raise RuntimeError("items called")

    source = RuntimeErrorGetter()
    dict.__setitem__(source, "provider", "synthetic-fixture")
    raw = deepcopy(VALID_V1_RAW)
    raw["source"] = source

    result = validate_snapshot(raw)

    assert calls == []
    assert _issue_signature(result.issues) == (("source", "invalid_type", ()),)


def test_list_and_integer_subclasses_are_deterministic_invalid_types():
    class RuntimeErrorList(list):
        def __iter__(self):
            raise RuntimeError("iterator called")

        def __getitem__(self, _index):
            raise RuntimeError("getter called")

    class RuntimeErrorInt(int):
        def __int__(self):
            raise RuntimeError("integer conversion called")

    instruments = RuntimeErrorList()
    list.extend(instruments, deepcopy(VALID_V1_RAW["instruments"]))
    list_raw = deepcopy(VALID_V1_RAW)
    list_raw["instruments"] = instruments
    list_result = validate_snapshot(list_raw)

    int_raw = deepcopy(VALID_V1_RAW)
    int_raw["instruments"][0]["price"] = RuntimeErrorInt(12)
    int_result = validate_snapshot(int_raw)

    assert _issue_signature(list_result.issues) == (("instruments", "invalid_type", ()),)
    assert _issue_signature(int_result.issues) == (("instruments[0].price", "invalid_type", ()),)
