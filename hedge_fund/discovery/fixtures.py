"""Synthetic, in-memory discovery snapshot fixtures."""

from copy import deepcopy
from decimal import Decimal

VALID_V1_RAW = {
    "schema_version": 1,
    "snapshot_at": "2026-11-25t10:15:30.1200+01:00",
    "retrieved_at": "2026-11-25T10:16:00.1234567+01:00",
    "source": {"provider": " synthetic-fixture "},
    "instruments": [
        {
            "code": " aapl ",
            "name": "Synthetic Alpha",
            "exchange": "XNAS",
            "currency": "USD",
            "trading_status": "active",
            "price": 12.5,
            "change_pct": 0.0125,
            "amount": 1_000_000,
            "total_mv": 9_876_543.21,
            "pe_ratio": 20.0,
            "pb_ratio": None,
            "volume_ratio": 1.5,
            "turnover_rate": 0.025,
            "industry": "Synthetic Technology",
            "avg_amount_usd": 250_000.0,
            "avg_amount_usd_window_days": 20,
        },
        {
            "code": " msft ",
            "name": "Synthetic Beta",
            "exchange": "XNAS",
            "currency": "USD",
            "trading_status": "active",
            "price": 5,
            "change_pct": -0.5,
            "amount": 0,
            "total_mv": 0,
        },
    ],
}


VALID_V1_CANONICAL = {
    "schema_version": 1,
    "snapshot_at": "2026-11-25T09:15:30.1200Z",
    "retrieved_at": "2026-11-25T09:16:00.1234567Z",
    "source": {"provider": " synthetic-fixture "},
    "instruments": [
        {
            "code": "AAPL",
            "name": "Synthetic Alpha",
            "exchange": "XNAS",
            "currency": "USD",
            "trading_status": "active",
            "price": 12.5,
            "change_pct": 0.0125,
            "amount": 1_000_000,
            "total_mv": 9_876_543.21,
            "pe_ratio": 20.0,
            "pb_ratio": None,
            "volume_ratio": 1.5,
            "turnover_rate": 0.025,
            "industry": "Synthetic Technology",
            "avg_amount_usd": 250_000.0,
            "avg_amount_usd_window_days": 20,
        },
        {
            "code": "MSFT",
            "name": "Synthetic Beta",
            "exchange": "XNAS",
            "currency": "USD",
            "trading_status": "active",
            "price": 5,
            "change_pct": -0.5,
            "amount": 0,
            "total_mv": 0,
            "pe_ratio": None,
            "pb_ratio": None,
            "volume_ratio": None,
            "turnover_rate": None,
            "industry": None,
            "avg_amount_usd": None,
            "avg_amount_usd_window_days": None,
        },
    ],
}

OPTIONAL_FIELDS = (
    "pe_ratio",
    "pb_ratio",
    "volume_ratio",
    "turnover_rate",
    "industry",
    "avg_amount_usd",
    "avg_amount_usd_window_days",
)


def _raw_baseline():
    return deepcopy(VALID_V1_RAW)


def _canonical_baseline():
    return deepcopy(VALID_V1_CANONICAL)


def _issue(location, reason, related=()):
    return location, reason, tuple(related)


def _case(raw, expected_snapshot=None, expected_issues=(), reference_time=None, max_age_seconds=None):
    return {
        "raw": raw,
        "expected_snapshot": expected_snapshot,
        "expected_issues": tuple(expected_issues),
        "reference_time": reference_time,
        "max_age_seconds": max_age_seconds,
    }


_optional_null = _raw_baseline()
for _field in OPTIONAL_FIELDS:
    _optional_null["instruments"][1][_field] = None

_blank_industry = _raw_baseline()
_blank_industry["instruments"][1]["industry"] = "   "

_empty_universe = _raw_baseline()
_empty_universe["instruments"] = []
_empty_universe_canonical = _canonical_baseline()
_empty_universe_canonical["instruments"] = []

_all_suspended = _raw_baseline()
_all_suspended["instruments"] = [_all_suspended["instruments"][0]]
_all_suspended["instruments"][0]["trading_status"] = "suspended"
_all_suspended_canonical = _canonical_baseline()
_all_suspended_canonical["instruments"] = [_all_suspended_canonical["instruments"][0]]
_all_suspended_canonical["instruments"][0]["trading_status"] = "suspended"

_currency_zzz = _raw_baseline()
_currency_zzz["instruments"][1]["currency"] = "ZZZ"
_currency_zzz_canonical = _canonical_baseline()
_currency_zzz_canonical["instruments"][1]["currency"] = "ZZZ"

_zero_optional = _raw_baseline()
_zero_optional["instruments"][1].update(
    {
        "pe_ratio": 0,
        "pb_ratio": 0.0,
        "volume_ratio": 0,
        "turnover_rate": 0.0,
        "avg_amount_usd": 0,
        "avg_amount_usd_window_days": 1,
    }
)
_zero_optional_canonical = _canonical_baseline()
_zero_optional_canonical["instruments"][1].update(
    {
        "pe_ratio": 0,
        "pb_ratio": 0.0,
        "volume_ratio": 0,
        "turnover_rate": 0.0,
        "avg_amount_usd": 0,
        "avg_amount_usd_window_days": 1,
    }
)

_change_floor = _raw_baseline()
_change_floor["instruments"][1]["change_pct"] = -1.0
_change_floor_canonical = _canonical_baseline()
_change_floor_canonical["instruments"][1]["change_pct"] = -1.0

_extreme = _raw_baseline()
_extreme["instruments"][0].update(
    {
        "price": 1e308,
        "change_pct": 1e308,
        "amount": 10**1000,
        "total_mv": 10**1000,
        "pe_ratio": -1e308,
        "pb_ratio": -1e308,
        "volume_ratio": 1e308,
        "turnover_rate": 1e308,
        "avg_amount_usd": 1e308,
        "avg_amount_usd_window_days": 1,
    }
)
_extreme_canonical = _canonical_baseline()
_extreme_canonical["instruments"][0].update(_extreme["instruments"][0])
_extreme_canonical["instruments"][0]["code"] = "AAPL"
_extreme_canonical["instruments"][0]["industry"] = "Synthetic Technology"

_missing_name = _raw_baseline()
_missing_name["instruments"][0].pop("name")

_blank_ticker = _raw_baseline()
_blank_ticker["instruments"][0]["code"] = "   "

_null_price = _raw_baseline()
_null_price["instruments"][0]["price"] = None

_unknown_fields = _raw_baseline()
_unknown_fields["source.extra"] = "top-level collision"
_unknown_fields["extra_top"] = True
_unknown_fields["source"]["extra"] = "nested collision"
_unknown_fields["source"]["bad.key"] = 1
_unknown_fields["instruments"][0]['bad"\\key'] = 1

_duplicate_codes = _raw_baseline()
_duplicate_codes["instruments"][1]["code"] = " AAPL "

_optional_pair = _raw_baseline()
_optional_pair["instruments"][0].pop("avg_amount_usd_window_days")
_optional_pair["instruments"][1]["avg_amount_usd_window_days"] = 20

_wrong_types = _raw_baseline()
_wrong_types["instruments"][0].update({"price": "12.5", "volume_ratio": True, "trading_status": 1})

_invalid_status = _raw_baseline()
_invalid_status["instruments"][0]["trading_status"] = "unknown"

_non_finite = _raw_baseline()
_non_finite["instruments"][0].update({"price": float("nan"), "pe_ratio": float("inf")})

_numeric_bounds = _raw_baseline()
_numeric_bounds["instruments"][0].update(
    {
        "price": -1,
        "change_pct": -1.01,
        "amount": -1,
        "total_mv": -1,
        "volume_ratio": -1,
        "turnover_rate": -1,
        "avg_amount_usd": -1,
        "avg_amount_usd_window_days": 0,
    }
)

_zero_price = _raw_baseline()
_zero_price["instruments"][0]["price"] = 0

_bad_currency = _raw_baseline()
_bad_currency["instruments"][0]["currency"] = "usd"
_bad_currency["instruments"][1]["currency"] = "USÄ"

_invalid_metadata = _raw_baseline()
_invalid_metadata["snapshot_at"] = "2026-11-25 09:15:30"
_invalid_metadata["retrieved_at"] = 123
_invalid_metadata["source"]["provider"] = "   "

_non_json_value = _raw_baseline()
_non_json_value["instruments"][0]["price"] = Decimal("12.5")

_non_string_key = _raw_baseline()
_non_string_key[99] = "not a JSON object key"

_tuple_instruments = _raw_baseline()
_tuple_instruments["instruments"] = tuple(_tuple_instruments["instruments"])

_combined_invalid = _raw_baseline()
_combined_invalid["extra"] = "undeclared"
_combined_invalid["source"]["bad.key"] = "undeclared"
_combined_invalid["instruments"][0].pop("name")
_combined_invalid["instruments"][0].update({"price": None, "change_pct": "0.1", "pe_ratio": float("nan"), "avg_amount_usd": 1})
_combined_invalid["instruments"][0].pop("avg_amount_usd_window_days")
_combined_invalid["instruments"][0]["x.y"] = True
_combined_invalid["instruments"][1].update({"code": " AAPL ", "total_mv": -1})

_missing_version = _raw_baseline()
_missing_version.pop("schema_version")
_boolean_version = _raw_baseline()
_boolean_version["schema_version"] = True
_float_version = _raw_baseline()
_float_version["schema_version"] = 1.0
_string_version = _raw_baseline()
_string_version["schema_version"] = "1"
_unsupported_version = _raw_baseline()
_unsupported_version["schema_version"] = 2

US1_FIXTURES = {
    "valid_v1_baseline": _case(_raw_baseline(), _canonical_baseline()),
    "optional_absent": _case(_raw_baseline(), _canonical_baseline()),
    "optional_explicit_null": _case(_optional_null, _canonical_baseline()),
    "blank_industry_unavailable": _case(_blank_industry, _canonical_baseline()),
    "empty_universe": _case(_empty_universe, _empty_universe_canonical),
    "all_suspended": _case(_all_suspended, _all_suspended_canonical),
    "format_only_currency_zzz": _case(_currency_zzz, _currency_zzz_canonical),
    "valid_zero_optional_metrics": _case(_zero_optional, _zero_optional_canonical),
    "valid_change_floor": _case(_change_floor, _change_floor_canonical),
    "valid_extreme_finite_values": _case(_extreme, _extreme_canonical),
    "missing_required_field": _case(_missing_name, expected_issues=(_issue("instruments[0].name", "missing_field"),)),
    "blank_ticker": _case(_blank_ticker, expected_issues=(_issue("instruments[0].code", "invalid_value"),)),
    "null_required_value": _case(_null_price, expected_issues=(_issue("instruments[0].price", "null_value"),)),
    "unknown_fields_and_escaped_locations": _case(
        _unknown_fields,
        expected_issues=(
            _issue("extra_top", "unknown_field"),
            _issue('instruments[0]["bad\\"\\\\key"]', "unknown_field"),
            _issue('source["bad.key"]', "unknown_field"),
            _issue("source.extra", "unknown_field"),
            _issue('$["source.extra"]', "unknown_field"),
        ),
    ),
    "duplicate_canonical_codes": _case(
        _duplicate_codes,
        expected_issues=(
            _issue("instruments[0].code", "duplicate_code", ("instruments[1].code",)),
            _issue("instruments[1].code", "duplicate_code", ("instruments[0].code",)),
        ),
    ),
    "inconsistent_optional_pair": _case(
        _optional_pair,
        expected_issues=(
            _issue("instruments[0].avg_amount_usd_window_days", "inconsistent_optional_fields"),
            _issue("instruments[1].avg_amount_usd_window_days", "inconsistent_optional_fields"),
        ),
    ),
    "wrong_field_types": _case(
        _wrong_types,
        expected_issues=(
            _issue("instruments[0].price", "invalid_type"),
            _issue("instruments[0].trading_status", "invalid_type"),
            _issue("instruments[0].volume_ratio", "invalid_type"),
        ),
    ),
    "invalid_trading_status": _case(_invalid_status, expected_issues=(_issue("instruments[0].trading_status", "invalid_value"),)),
    "non_finite_values": _case(
        _non_finite,
        expected_issues=(
            _issue("instruments[0].pe_ratio", "invalid_value"),
            _issue("instruments[0].price", "invalid_value"),
        ),
    ),
    "numeric_bounds": _case(
        _numeric_bounds,
        expected_issues=(
            _issue("instruments[0].amount", "invalid_value"),
            _issue("instruments[0].avg_amount_usd", "invalid_value"),
            _issue("instruments[0].avg_amount_usd_window_days", "invalid_value"),
            _issue("instruments[0].change_pct", "invalid_value"),
            _issue("instruments[0].price", "invalid_value"),
            _issue("instruments[0].total_mv", "invalid_value"),
            _issue("instruments[0].turnover_rate", "invalid_value"),
            _issue("instruments[0].volume_ratio", "invalid_value"),
        ),
    ),
    "zero_price_invalid": _case(_zero_price, expected_issues=(_issue("instruments[0].price", "invalid_value"),)),
    "invalid_currency_formats": _case(
        _bad_currency,
        expected_issues=(
            _issue("instruments[0].currency", "invalid_value"),
            _issue("instruments[1].currency", "invalid_value"),
        ),
    ),
    "invalid_source_and_timestamps": _case(
        _invalid_metadata,
        expected_issues=(
            _issue("retrieved_at", "invalid_type"),
            _issue("snapshot_at", "invalid_value"),
            _issue("source.provider", "invalid_value"),
        ),
    ),
    "non_json_python_value": _case(_non_json_value, expected_issues=(_issue("instruments[0].price", "invalid_type"),)),
    "non_string_object_key": _case(_non_string_key, expected_issues=(_issue("$", "invalid_type"),)),
    "tuple_instruments_rejected": _case(_tuple_instruments, expected_issues=(_issue("instruments", "invalid_type"),)),
    "combined_independent_errors": _case(
        _combined_invalid,
        expected_issues=(
            _issue("extra", "unknown_field"),
            _issue("instruments[0].avg_amount_usd_window_days", "inconsistent_optional_fields"),
            _issue("instruments[0].change_pct", "invalid_type"),
            _issue("instruments[0].code", "duplicate_code", ("instruments[1].code",)),
            _issue("instruments[0].name", "missing_field"),
            _issue("instruments[0].pe_ratio", "invalid_value"),
            _issue("instruments[0].price", "null_value"),
            _issue('instruments[0]["x.y"]', "unknown_field"),
            _issue("instruments[1].code", "duplicate_code", ("instruments[0].code",)),
            _issue("instruments[1].total_mv", "invalid_value"),
            _issue('source["bad.key"]', "unknown_field"),
        ),
    ),
    "missing_schema_version": _case(_missing_version, expected_issues=(_issue("schema_version", "missing_field"),)),
    "boolean_schema_version": _case(_boolean_version, expected_issues=(_issue("schema_version", "invalid_type"),)),
    "float_schema_version": _case(_float_version, expected_issues=(_issue("schema_version", "invalid_type"),)),
    "string_schema_version": _case(_string_version, expected_issues=(_issue("schema_version", "invalid_type"),)),
    "unsupported_schema_version": _case(_unsupported_version, expected_issues=(_issue("schema_version", "unsupported_schema_version"),)),
}

_historical = _raw_baseline()
_historical["snapshot_at"] = "2000-01-02T09:00:00Z"
_historical["retrieved_at"] = "2000-01-02T09:01:00Z"
_historical_canonical = _canonical_baseline()
_historical_canonical["snapshot_at"] = "2000-01-02T09:00:00Z"
_historical_canonical["retrieved_at"] = "2000-01-02T09:01:00Z"

_equal_timestamps = _raw_baseline()
_equal_timestamps["retrieved_at"] = _equal_timestamps["snapshot_at"]
_equal_timestamps_canonical = _canonical_baseline()
_equal_timestamps_canonical["retrieved_at"] = _equal_timestamps_canonical["snapshot_at"]

_earlier_retrieval = _raw_baseline()
_earlier_retrieval["retrieved_at"] = "2026-11-25T09:15:30.1199Z"

_future_snapshot = _raw_baseline()
_future_snapshot["snapshot_at"] = "2026-11-25T09:20:00Z"
_future_snapshot["retrieved_at"] = "2026-11-25T09:21:00Z"

_invalid_policy_historical = deepcopy(_historical)
_future_with_invalid_policy = deepcopy(_future_snapshot)

US2_FIXTURES = {
    "historical_without_policy": _case(_historical, _historical_canonical),
    "exact_max_age_boundary": _case(
        _raw_baseline(),
        _canonical_baseline(),
        reference_time="2026-11-25T09:16:30.1200Z",
        max_age_seconds=60,
    ),
    "fractionally_over_max_age": _case(
        _raw_baseline(),
        expected_issues=(_issue("snapshot_at", "stale_snapshot"),),
        reference_time="2026-11-25T09:16:30.120000000000000001Z",
        max_age_seconds=60,
    ),
    "future_snapshot_not_stale": _case(
        _future_snapshot,
        expected_issues=(_issue("snapshot_at", "future_snapshot"),),
        reference_time="2026-11-25T09:19:59Z",
        max_age_seconds=0,
    ),
    "equal_observation_and_retrieval": _case(_equal_timestamps, _equal_timestamps_canonical),
    "retrieval_before_observation": _case(
        _earlier_retrieval,
        expected_issues=(_issue("retrieved_at", "invalid_timestamp_order"),),
    ),
    "policy_missing_max_age": _case(
        _raw_baseline(),
        expected_issues=(_issue("argument.max_age_seconds", "missing_field"),),
        reference_time="2026-11-25T09:16:00Z",
    ),
    "policy_missing_reference": _case(_raw_baseline(), expected_issues=(_issue("argument.reference_time", "missing_field"),), max_age_seconds=60),
    "policy_invalid_reference": _case(
        _raw_baseline(),
        expected_issues=(_issue("argument.reference_time", "invalid_value"),),
        reference_time="not-a-timestamp",
        max_age_seconds=60,
    ),
    "policy_reference_wrong_type": _case(
        _raw_baseline(),
        expected_issues=(_issue("argument.reference_time", "invalid_type"),),
        reference_time=123,
        max_age_seconds=60,
    ),
    "policy_negative_age": _case(
        _raw_baseline(),
        expected_issues=(_issue("argument.max_age_seconds", "invalid_value"),),
        reference_time="2026-11-25T09:16:00Z",
        max_age_seconds=-1,
    ),
    "policy_boolean_age": _case(
        _raw_baseline(),
        expected_issues=(_issue("argument.max_age_seconds", "invalid_type"),),
        reference_time="2026-11-25T09:16:00Z",
        max_age_seconds=True,
    ),
    "policy_float_age": _case(
        _raw_baseline(),
        expected_issues=(_issue("argument.max_age_seconds", "invalid_type"),),
        reference_time="2026-11-25T09:16:00Z",
        max_age_seconds=60.0,
    ),
    "invalid_policy_suppresses_staleness": _case(
        _invalid_policy_historical,
        expected_issues=(_issue("argument.max_age_seconds", "invalid_value"),),
        reference_time="2026-11-25T09:16:00Z",
        max_age_seconds=-1,
    ),
    "invalid_policy_suppresses_future_claim": _case(
        _future_with_invalid_policy,
        expected_issues=(_issue("argument.reference_time", "invalid_value"),),
        reference_time="not-a-timestamp",
        max_age_seconds=0,
    ),
}

_renamed_field = _raw_baseline()
_renamed_name = _renamed_field["instruments"][0].pop("name")
_renamed_field["instruments"][0]["display_name"] = _renamed_name

_removed_field = _raw_baseline()
_removed_field["instruments"][0].pop("total_mv")

_unit_change = _raw_baseline()
_unit_change["schema_version"] = 2
_unit_change["instruments"][0]["amount"] = 1_000.0

_meaning_change = _raw_baseline()
_meaning_change["schema_version"] = 2
_meaning_change["instruments"][0]["change_pct"] = 1.25


def _compatibility_case(raw, expected_snapshot=None, expected_issues=(), change_kind="baseline"):
    case = _case(raw, expected_snapshot, expected_issues)
    case["change_kind"] = change_kind
    case["compatibility_expectation"] = "new-schema-version-required" if change_kind != "baseline" else "version-1-baseline"
    return case


US3_FIXTURES = {
    "version_1_compatibility_baseline": _compatibility_case(_raw_baseline(), _canonical_baseline()),
    "field_rename_is_not_migrated": _compatibility_case(
        _renamed_field,
        expected_issues=(
            _issue("instruments[0].display_name", "unknown_field"),
            _issue("instruments[0].name", "missing_field"),
        ),
        change_kind="field-rename",
    ),
    "field_removal_is_not_migrated": _compatibility_case(
        _removed_field,
        expected_issues=(_issue("instruments[0].total_mv", "missing_field"),),
        change_kind="field-removal",
    ),
    "unit_change_requires_new_version": _compatibility_case(
        _unit_change,
        expected_issues=(_issue("schema_version", "unsupported_schema_version"),),
        change_kind="unit-change",
    ),
    "meaning_change_requires_new_version": _compatibility_case(
        _meaning_change,
        expected_issues=(_issue("schema_version", "unsupported_schema_version"),),
        change_kind="meaning-change",
    ),
}
