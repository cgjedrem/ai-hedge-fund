"""Deterministic parsing and issue mechanics for discovery snapshots."""

import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Iterable

from pydantic import ValidationError

from hedge_fund.discovery.models import (
    _SnapshotModel,
    SnapshotValidationResult,
    ValidationIssue,
)
from hedge_fund.fund.spec import normalize_ticker

_TIMESTAMP_PATTERN = re.compile(r"(?P<year>[0-9]{4})-(?P<month>[0-9]{2})-(?P<day>[0-9]{2})[Tt]" r"(?P<hour>[0-9]{2}):(?P<minute>[0-9]{2}):(?P<second>[0-9]{2})" r"(?:\.(?P<fraction>[0-9]+))?(?P<zone>[Zz]|[+-][0-9]{2}:[0-9]{2})")
_SAFE_LOCATION_KEY = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_MISSING = object()
_MAX_RELATED_LOCATIONS = 10

_ISSUE_MESSAGES = {
    "missing_field": "Required field is missing.",
    "null_value": "Required value must not be null.",
    "invalid_type": "Value has an invalid type.",
    "invalid_value": "Value violates the field contract.",
    "unknown_field": "Field is not declared by schema version 1.",
    "duplicate_code": "Canonical ticker code conflicts with another instrument.",
    "unsupported_schema_version": "Schema version is not supported.",
    "invalid_timestamp_order": "retrieved_at must not precede snapshot_at.",
    "stale_snapshot": "Snapshot age exceeds the explicit maximum age.",
    "future_snapshot": "Snapshot observation is later than the reference time.",
    "inconsistent_optional_fields": "Average amount and its window must be available together.",
}


@dataclass(frozen=True)
class _ExactInstant:
    whole_seconds: int
    fraction_digits: str


@dataclass(frozen=True)
class _IssueDraft:
    segments: tuple[str | int, ...]
    reason: str
    message: str
    related_segments: tuple[tuple[str | int, ...], ...] = ()


@dataclass(frozen=True)
class _PathRef:
    parent: "_PathRef | None"
    segment: str | int


def _path_segments(path: _PathRef | None) -> tuple[str | int, ...]:
    segments = []
    while path is not None:
        segments.append(path.segment)
        path = path.parent
    return tuple(reversed(segments))


def _compare_fraction_digits(left: str, right: str) -> int:
    left = left.rstrip("0")
    right = right.rstrip("0")
    common_length = min(len(left), len(right))
    left_prefix = left[:common_length]
    right_prefix = right[:common_length]
    if left_prefix != right_prefix:
        return (left_prefix > right_prefix) - (left_prefix < right_prefix)
    return (len(left) > len(right)) - (len(left) < len(right))


def _compare_instants(left: _ExactInstant, right: _ExactInstant) -> int:
    if left.whole_seconds != right.whole_seconds:
        return (left.whole_seconds > right.whole_seconds) - (left.whole_seconds < right.whole_seconds)
    return _compare_fraction_digits(left.fraction_digits, right.fraction_digits)


def _parse_timestamp(value: object) -> tuple[str, _ExactInstant]:
    if type(value) is not str:
        raise ValueError("timestamp must be text")
    match = _TIMESTAMP_PATTERN.fullmatch(value)
    if match is None:
        raise ValueError("timestamp must use RFC 3339 with an explicit offset")

    fields = match.groupdict()
    year, month, day, hour, minute, second = (int(fields[name]) for name in ("year", "month", "day", "hour", "minute", "second"))
    if second == 60:
        raise ValueError("leap seconds are outside the supported calendar")

    zone = fields["zone"]
    if zone.lower() == "z" or zone in ("+00:00", "-00:00"):
        offset = timedelta(0)
    else:
        sign = 1 if zone[0] == "+" else -1
        offset_hours, offset_minutes = int(zone[1:3]), int(zone[4:6])
        if offset_hours > 23 or offset_minutes > 59:
            raise ValueError("UTC offset is outside RFC 3339 bounds")
        offset = sign * timedelta(hours=offset_hours, minutes=offset_minutes)

    try:
        local = datetime(year, month, day, hour, minute, second, tzinfo=timezone(offset))
        utc = local.astimezone(timezone.utc)
    except (OverflowError, ValueError) as exc:
        raise ValueError("timestamp is outside the supported calendar") from exc

    fraction_digits = fields["fraction"]
    whole_seconds = ((utc.toordinal() - 1) * 24 + utc.hour) * 3600 + utc.minute * 60 + utc.second
    fraction_suffix = ""
    if fraction_digits is not None:
        fraction_suffix = f".{fraction_digits}"

    canonical = f"{utc.year:04d}-{utc.month:02d}-{utc.day:02d}T{utc.hour:02d}:{utc.minute:02d}:{utc.second:02d}{fraction_suffix}Z"
    return canonical, _ExactInstant(whole_seconds, fraction_digits or "")


def _render_location(segments: tuple[str | int, ...]) -> str:
    if not segments:
        return "$"

    rendered = ""
    for segment in segments:
        if type(segment) is int:
            if not rendered:
                rendered = "$"
            rendered += f"[{segment}]"
        elif type(segment) is str and _SAFE_LOCATION_KEY.fullmatch(segment):
            rendered += f"{'.' if rendered else ''}{segment}"
        elif type(segment) is str:
            if not rendered:
                rendered = "$"
            rendered += f"[{json.dumps(segment)}]"
        else:
            raise TypeError("location segments must be strings or integer indices")
    return rendered


def _segment_sort_key(segment: str | int) -> tuple[int, str | int]:
    if type(segment) is str:
        return 0, segment
    if type(segment) is int:
        return 1, segment
    raise TypeError("location segments must be strings or integer indices")


def _location_sort_key(segments: tuple[str | int, ...]) -> tuple[tuple[int, str | int], ...]:
    return tuple(_segment_sort_key(segment) for segment in segments)


def _ordered_issues(drafts: Iterable[_IssueDraft]) -> tuple[ValidationIssue, ...]:
    unique = {}
    for draft in drafts:
        related = tuple(sorted(set(draft.related_segments), key=_location_sort_key))
        key = draft.segments, draft.reason, draft.message, related
        unique[key] = _IssueDraft(draft.segments, draft.reason, draft.message, related)

    ordered = sorted(
        unique.values(),
        key=lambda draft: (
            _location_sort_key(draft.segments),
            draft.reason,
            tuple(_location_sort_key(location) for location in draft.related_segments),
            draft.message,
        ),
    )
    return tuple(
        ValidationIssue(
            location=_render_location(draft.segments),
            reason=draft.reason,
            message=draft.message,
            related_locations=tuple(_render_location(location) for location in draft.related_segments),
        )
        for draft in ordered
    )


def _issue_draft(
    segments: tuple[str | int, ...],
    reason: str,
    related: tuple[tuple[str | int, ...], ...] = (),
    *,
    message: str | None = None,
) -> _IssueDraft:
    return _IssueDraft(segments, reason, _ISSUE_MESSAGES[reason] if message is None else message, related)


def _raw_value_at(raw: object, segments: tuple[object, ...]) -> object:
    value = raw
    for segment in segments:
        if type(value) is dict and segment in value:
            value = value[segment]
        elif type(value) is list and type(segment) is int and 0 <= segment < len(value):
            value = value[segment]
        else:
            return _MISSING
    return value


def _adapt_pydantic_errors(raw: object, error: ValidationError, invalid_paths: set[tuple[str | int, ...]] | None = None) -> list[_IssueDraft]:
    drafts = []
    for item in error.errors(include_url=False, include_context=False, include_input=False):
        location = tuple(item.get("loc", ()))
        error_type = item.get("type", "")
        if error_type == "missing":
            reason = "missing_field"
        elif error_type == "extra_forbidden":
            reason = "unknown_field"
        elif error_type in _ISSUE_MESSAGES:
            reason = error_type
        elif error_type in {"string_type", "int_type", "float_type", "bool_type", "list_type", "dict_type", "model_type", "tuple_type"}:
            reason = "null_value" if location and _raw_value_at(raw, location) is None else "invalid_type"
        else:
            reason = "invalid_value"
        if reason in {"null_value", "invalid_type"} and invalid_paths is not None and location in invalid_paths:
            continue
        drafts.append(_issue_draft(location, reason))
    return drafts


def _contains_surrogate(value: str) -> bool:
    return any(0xD800 <= ord(character) <= 0xDFFF for character in value)


def _prewalk_json(value: object) -> tuple[object, list[_IssueDraft], set[tuple[str | int, ...]]]:
    root_path = None
    drafts = []
    invalid_paths = set()
    if type(value) is not dict:
        invalid_paths.add(())
        return None, [_issue_draft((), "invalid_type")], invalid_paths

    sanitized = {}
    seen_containers = {id(value)}

    def dict_entries(container: dict, path: _PathRef | None):
        keys = []
        for key in dict.keys(container):
            if type(key) is not str:
                location = _path_segments(path)
                invalid_paths.add(location)
                drafts.append(_issue_draft(location, "invalid_type"))
            elif _contains_surrogate(key):
                location = _path_segments(_PathRef(path, key))
                drafts.append(_issue_draft(location, "unknown_field"))
            else:
                keys.append(key)
        return iter((key, dict.__getitem__(container, key), _PathRef(path, key)) for key in sorted(keys))

    stack = [(value, sanitized, root_path, dict_entries(value, root_path))]
    while stack:
        container, target, path, entries = stack[-1]
        try:
            item = next(entries)
        except StopIteration:
            stack.pop()
            continue

        if type(container) is dict:
            key, child, child_path = item
        else:
            key, child = item
            child_path = _PathRef(path, key)

        if child is None or type(child) in (str, bool, int, float):
            safe_child = child
        elif type(child) in (dict, list):
            identity = id(child)
            if identity in seen_containers:
                location = _path_segments(child_path)
                invalid_paths.add(location)
                drafts.append(_issue_draft(location, "invalid_type"))
                safe_child = None
            else:
                seen_containers.add(identity)
                safe_child = {} if type(child) is dict else []
                if type(child) is dict:
                    child_entries = dict_entries(child, child_path)
                else:
                    child_entries = iter(enumerate(child))
                stack.append((child, safe_child, child_path, child_entries))
        else:
            location = _path_segments(child_path)
            invalid_paths.add(location)
            drafts.append(_issue_draft(location, "invalid_type"))
            safe_child = None

        if type(target) is dict:
            target[key] = safe_child
        else:
            target.append(safe_child)

    return sanitized, drafts, invalid_paths


def _check_duplicates(raw: object) -> list[_IssueDraft]:
    if type(raw) is not dict:
        return []
    instruments = raw.get("instruments")
    if type(instruments) is not list:
        return []

    rows_by_code = {}
    for index, instrument in enumerate(instruments):
        if type(instrument) is not dict:
            continue
        code = instrument.get("code")
        if type(code) is not str:
            continue
        canonical = normalize_ticker(code)
        if canonical:
            rows_by_code.setdefault(canonical, []).append(index)

    drafts = []
    for indices in rows_by_code.values():
        if len(indices) < 2:
            continue
        for index in indices:
            shown_indices = []
            for other in indices:
                if other != index:
                    shown_indices.append(other)
                    if len(shown_indices) == _MAX_RELATED_LOCATIONS:
                        break
            omitted_count = len(indices) - 1 - len(shown_indices)
            related = tuple(("instruments", other, "code") for other in shown_indices)
            message = _ISSUE_MESSAGES["duplicate_code"]
            if omitted_count:
                message = f"Canonical ticker code conflicts with another instrument; {omitted_count} related locations omitted."
            drafts.append(_issue_draft(("instruments", index, "code"), "duplicate_code", related, message=message))
    return drafts


def _check_optional_pairs(raw: object) -> list[_IssueDraft]:
    if type(raw) is not dict:
        return []
    instruments = raw.get("instruments")
    if type(instruments) is not list:
        return []

    drafts = []
    for index, instrument in enumerate(instruments):
        if type(instrument) is not dict:
            continue
        average = instrument.get("avg_amount_usd", _MISSING)
        window = instrument.get("avg_amount_usd_window_days", _MISSING)
        average_available = average is not _MISSING and average is not None
        window_available = window is not _MISSING and window is not None
        if average_available != window_available:
            drafts.append(_issue_draft(("instruments", index, "avg_amount_usd_window_days"), "inconsistent_optional_fields"))
    return drafts


def _check_timestamps(raw: object) -> tuple[dict[str, tuple[str, _ExactInstant]], list[_IssueDraft]]:
    if type(raw) is not dict:
        return {}, []

    parsed = {}
    drafts = []
    for field in ("snapshot_at", "retrieved_at"):
        value = raw.get(field, _MISSING)
        if type(value) is not str:
            continue
        try:
            parsed[field] = _parse_timestamp(value)
        except ValueError:
            drafts.append(_issue_draft((field,), "invalid_value"))

    observed = parsed.get("snapshot_at")
    retrieved = parsed.get("retrieved_at")
    if observed is not None and retrieved is not None and _compare_instants(retrieved[1], observed[1]) < 0:
        drafts.append(_issue_draft(("retrieved_at",), "invalid_timestamp_order"))
    return parsed, drafts


def _check_freshness(
    snapshot_at: tuple[str, _ExactInstant] | None,
    reference_time: object,
    max_age_seconds: object,
) -> list[_IssueDraft]:
    if reference_time is None and max_age_seconds is None:
        return []

    drafts = []
    reference = None
    age = None
    if reference_time is None:
        drafts.append(_issue_draft(("argument", "reference_time"), "missing_field"))
    elif type(reference_time) is not str:
        drafts.append(_issue_draft(("argument", "reference_time"), "invalid_type"))
    else:
        try:
            reference = _parse_timestamp(reference_time)
        except ValueError:
            drafts.append(_issue_draft(("argument", "reference_time"), "invalid_value"))

    if max_age_seconds is None:
        drafts.append(_issue_draft(("argument", "max_age_seconds"), "missing_field"))
    elif type(max_age_seconds) is not int:
        drafts.append(_issue_draft(("argument", "max_age_seconds"), "invalid_type"))
    elif max_age_seconds < 0:
        drafts.append(_issue_draft(("argument", "max_age_seconds"), "invalid_value"))
    else:
        age = max_age_seconds

    if drafts or snapshot_at is None or reference is None or age is None:
        return drafts

    observation = snapshot_at[1]
    reference_instant = reference[1]
    if _compare_instants(observation, reference_instant) > 0:
        drafts.append(_issue_draft(("snapshot_at",), "future_snapshot"))
    elif _compare_instants(reference_instant, _ExactInstant(observation.whole_seconds + age, observation.fraction_digits)) > 0:
        drafts.append(_issue_draft(("snapshot_at",), "stale_snapshot"))
    return drafts


def validate_snapshot(raw: object, *, reference_time: str | None = None, max_age_seconds: int | None = None) -> SnapshotValidationResult:
    sanitized, drafts, invalid_paths = _prewalk_json(raw)

    try:
        model = _SnapshotModel.model_validate(sanitized)
    except ValidationError as error:
        drafts.extend(_adapt_pydantic_errors(sanitized, error, invalid_paths))
        model = None
    except RecursionError:
        drafts.append(_issue_draft(("instruments",), "invalid_type"))
        model = None

    drafts.extend(_check_duplicates(sanitized))
    drafts.extend(_check_optional_pairs(sanitized))
    parsed_timestamps, timestamp_drafts = _check_timestamps(sanitized)
    drafts.extend(timestamp_drafts)
    drafts.extend(_check_freshness(parsed_timestamps.get("snapshot_at"), reference_time, max_age_seconds))

    issues = _ordered_issues(drafts)
    if issues:
        return SnapshotValidationResult(snapshot=None, issues=issues)

    canonical = model.model_dump(mode="python")
    canonical["snapshot_at"] = parsed_timestamps["snapshot_at"][0]
    canonical["retrieved_at"] = parsed_timestamps["retrieved_at"][0]
    return SnapshotValidationResult(snapshot=canonical, issues=())
