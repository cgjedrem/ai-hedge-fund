"""Strict discovery snapshot models and immutable result records."""

import math
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator, StrictInt
from pydantic_core import PydanticCustomError

from hedge_fund.fund.spec import normalize_ticker


def _custom_error(reason: str, message: str) -> PydanticCustomError:
    return PydanticCustomError(reason, message)


def _validate_number(value: object, minimum: int | float | None = None, exclusive: bool = False, nullable: bool = False) -> object:
    if value is None:
        if nullable:
            return None
        raise _custom_error("null_value", "Required number must not be null.")
    if type(value) not in (int, float):
        raise _custom_error("invalid_type", "Number must be a built-in integer or float.")
    if type(value) is float and not math.isfinite(value):
        raise _custom_error("invalid_value", "Number must be finite.")
    if minimum is not None and (value <= minimum if exclusive else value < minimum):
        raise _custom_error("invalid_value", "Number is below its permitted range.")
    return value


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)


class _SourceModel(_StrictModel):
    provider: str

    @field_validator("provider")
    @classmethod
    def _provider_is_nonblank(cls, value: str) -> str:
        if not value.strip():
            raise _custom_error("invalid_value", "Provider identifier must not be blank.")
        return value


class _InstrumentModel(_StrictModel):
    code: str
    name: str
    exchange: str
    currency: str
    trading_status: str
    price: object
    change_pct: object
    amount: object
    total_mv: object
    pe_ratio: object = None
    pb_ratio: object = None
    volume_ratio: object = None
    turnover_rate: object = None
    industry: str | None = None
    avg_amount_usd: object = None
    avg_amount_usd_window_days: StrictInt | None = None

    @field_validator("code")
    @classmethod
    def _canonical_code(cls, value: str) -> str:
        code = normalize_ticker(value)
        if not code:
            raise _custom_error("invalid_value", "Ticker code must not be blank.")
        return code

    @field_validator("name", "exchange")
    @classmethod
    def _text_is_nonblank(cls, value: str) -> str:
        if not value.strip():
            raise _custom_error("invalid_value", "Text field must not be blank.")
        return value

    @field_validator("currency", mode="before")
    @classmethod
    def _currency_format(cls, value: object) -> str:
        if value is None:
            raise _custom_error("null_value", "Currency must not be null.")
        if type(value) is not str:
            raise _custom_error("invalid_type", "Currency must be text.")
        if len(value) != 3 or any(character < "A" or character > "Z" for character in value):
            raise _custom_error("invalid_value", "Currency must contain three uppercase ASCII letters.")
        return value

    @field_validator("trading_status", mode="before")
    @classmethod
    def _supported_trading_status(cls, value: object) -> str:
        if value is None:
            raise _custom_error("null_value", "Trading status must not be null.")
        if type(value) is not str:
            raise _custom_error("invalid_type", "Trading status must be text.")
        if value not in ("active", "suspended"):
            raise _custom_error("invalid_value", "Trading status must be active or suspended.")
        return value

    @field_validator("price", mode="before")
    @classmethod
    def _positive_price(cls, value: object) -> object:
        return _validate_number(value, minimum=0, exclusive=True)

    @field_validator("change_pct", mode="before")
    @classmethod
    def _bounded_change(cls, value: object) -> object:
        return _validate_number(value, minimum=-1)

    @field_validator("amount", "total_mv", mode="before")
    @classmethod
    def _nonnegative_value(cls, value: object) -> object:
        return _validate_number(value, minimum=0)

    @field_validator("pe_ratio", "pb_ratio", mode="before")
    @classmethod
    def _finite_signed_ratio(cls, value: object) -> object:
        return _validate_number(value, nullable=True)

    @field_validator("volume_ratio", "turnover_rate", "avg_amount_usd", mode="before")
    @classmethod
    def _nonnegative_optional_value(cls, value: object) -> object:
        return _validate_number(value, minimum=0, nullable=True)

    @field_validator("industry", mode="before")
    @classmethod
    def _blank_industry_is_unavailable(cls, value: object) -> str | None:
        if value is None:
            return None
        if type(value) is not str:
            raise _custom_error("invalid_type", "Industry must be text or null.")
        return None if not value.strip() else value

    @field_validator("avg_amount_usd_window_days")
    @classmethod
    def _positive_window(cls, value: int | None) -> int | None:
        if value is not None and value <= 0:
            raise _custom_error("invalid_value", "Average amount window must be a positive integer.")
        return value


class _SnapshotModel(_StrictModel):
    schema_version: StrictInt
    snapshot_at: str
    retrieved_at: str
    source: _SourceModel
    instruments: list[_InstrumentModel]

    @field_validator("schema_version")
    @classmethod
    def _supported_schema_version(cls, value: int) -> int:
        if value != 1:
            raise _custom_error("unsupported_schema_version", "Only schema version 1 is supported.")
        return value


@dataclass(frozen=True)
class ValidationIssue:
    """One deterministic field-level validation issue."""

    location: str
    reason: str
    message: str
    related_locations: tuple[str, ...] = ()

    def __post_init__(self):
        if not isinstance(self.location, str) or not self.location:
            raise ValueError("location must be non-empty text")
        if not isinstance(self.reason, str) or not self.reason:
            raise ValueError("reason must be non-empty text")
        if not isinstance(self.message, str) or not self.message:
            raise ValueError("message must be non-empty text")
        if not isinstance(self.related_locations, tuple) or any(not isinstance(location, str) or not location for location in self.related_locations):
            raise TypeError("related_locations must be a tuple of non-empty text")


@dataclass(frozen=True)
class SnapshotValidationResult:
    """Canonical result; json.dumps may reject ints above Python's default 4,300-digit limit."""

    snapshot: dict[str, Any] | None
    issues: tuple[ValidationIssue, ...]

    def __post_init__(self):
        if self.snapshot is not None and not isinstance(self.snapshot, dict):
            raise TypeError("snapshot must be a dictionary or None")
        if not isinstance(self.issues, tuple) or any(not isinstance(issue, ValidationIssue) for issue in self.issues):
            raise TypeError("issues must be a tuple of ValidationIssue values")
        if (self.snapshot is None) != bool(self.issues):
            raise ValueError("snapshot and issues must describe exactly one result state")
