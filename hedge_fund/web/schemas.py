"""Validated API request models."""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal
from typing import Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
    SecretStr,
    StrictBool,
    StrictFloat,
    StrictInt,
)

ErrorCode = Literal[
    "invalid-request",
    "capability-denied",
    "read-only",
    "broker-not-web-supported",
    "not-found",
    "stale-preview",
    "request-conflict",
    "writer-conflict",
    "ownership-unknown",
    "halted",
    "replay-corrupt",
    "reconciliation-required",
    "expired-confirmation",
    "capacity-denied",
    "payload-too-large",
    "observation-conflict",
    "assets-unavailable",
    "internal-error",
]
RetryPolicy = Literal["none", "review-again", "reload", "inspect-status", "retry-later", "retry-read-only"]

_DEFAULT_ERROR_CODES: dict[int, str] = {
    400: "invalid-request",
    403: "capability-denied",
    404: "not-found",
    405: "invalid-request",
    409: "request-conflict",
    410: "expired-confirmation",
    413: "payload-too-large",
    422: "invalid-request",
    423: "halted",
    429: "capacity-denied",
    503: "assets-unavailable",
}
_ERROR_RETRY_POLICIES: dict[str, str] = {
    "stale-preview": "review-again",
    "expired-confirmation": "review-again",
    "request-conflict": "reload",
    "writer-conflict": "retry-later",
    "capacity-denied": "retry-later",
    "ownership-unknown": "inspect-status",
    "replay-corrupt": "inspect-status",
    "reconciliation-required": "inspect-status",
    "observation-conflict": "retry-read-only",
    "assets-unavailable": "retry-read-only",
    "internal-error": "retry-read-only",
}
_REFRESH_REQUIRED_CODES = frozenset({"stale-preview", "expired-confirmation", "ownership-unknown"})
_ERROR_CODES = frozenset(ErrorCode.__args__)


class ErrorResponse(BaseModel):
    """Common safe error envelope; ``detail`` is kept for older clients."""

    model_config = ConfigDict(extra="forbid")

    detail: str | list[dict[str, Any]]
    code: ErrorCode
    message: str
    refresh_required: bool
    retry_policy: RetryPolicy


def error_code_for(status_code: int, code: str | None = None) -> str:
    if code is not None:
        if code not in _ERROR_CODES:
            raise ValueError(f"unknown error code: {code}")
        return code
    if status_code >= 500 and status_code != 503:
        return "internal-error"
    return _DEFAULT_ERROR_CODES.get(status_code, "invalid-request")


def error_payload(status_code: int, detail: str | list[dict[str, Any]], *, code: str | None = None) -> dict[str, Any]:
    resolved = error_code_for(status_code, code)
    message = detail if isinstance(detail, str) else "Invalid request."
    return ErrorResponse(
        detail=detail,
        code=resolved,
        message=message,
        refresh_required=resolved in _REFRESH_REQUIRED_CODES,
        retry_policy=_ERROR_RETRY_POLICIES.get(resolved, "none"),
    ).model_dump()


class RequestModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class MandateCreateRequest(RequestModel):
    spec: dict[str, Any]


class MandateRevisionRequest(RequestModel):
    expected_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    spec: dict[str, Any]


class DeployRequest(RequestModel):
    universe: list[str] = Field(min_length=1, max_length=25)

    @field_validator("universe")
    @classmethod
    def _valid_universe(cls, value: list[str]) -> list[str]:
        if any(not ticker or len(ticker) > 16 or not ticker.isascii() for ticker in value):
            raise ValueError("universe entries must be short ASCII ticker names")
        if len({ticker.upper() for ticker in value}) != len(value):
            raise ValueError("universe entries must be unique")
        return value


class ApprovalRequest(RequestModel):
    verdict: Literal["approve", "reject"]
    decision_as_of: str = Field(min_length=1, max_length=32)
    source_record_hash: str = Field(pattern=r"^[0-9a-f]{64}$")


class ValuationRefreshRequest(RequestModel):
    expected_head: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")


class HaltRequest(RequestModel):
    reason: str = Field(min_length=1, max_length=240)

    @field_validator("reason")
    @classmethod
    def _no_controls(cls, value: str) -> str:
        if any(ord(char) < 32 or ord(char) == 127 for char in value):
            raise ValueError("reason cannot contain control characters")
        return value


class BacktestRequest(RequestModel):
    fund: str = Field(min_length=1, max_length=64)
    universe: list[str] = Field(min_length=1, max_length=20)
    start: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    end: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    provider: str = Field(pattern=r"^[a-z0-9_-]{1,32}$")
    model: str = Field(min_length=1, max_length=120)
    mandate_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    authorize_paid_provider: StrictBool = False
    confirm_fd_self_service_pricing: StrictBool = False
    cost_model_id: str | None = Field(default=None, pattern=r"^[a-z0-9._-]{1,64}$")
    cost_model_version: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}-v\d+$")
    paid_max_calls: StrictInt | None = Field(default=None, ge=1, le=10000)
    paid_max_cost_usd: str | None = Field(
        default=None,
        pattern=r"^(?:0|[1-9]\d{0,2})(?:\.\d{1,6})?$",
    )
    paid_max_attempt_cost_usd: str | None = Field(
        default=None,
        pattern=r"^(?:0|[1-9]\d{0,1})(?:\.\d{1,6})?$",
    )

    @field_validator("universe")
    @classmethod
    def _valid_universe(cls, value: list[str]) -> list[str]:
        if any(not ticker or len(ticker) > 16 or not ticker.isascii() for ticker in value):
            raise ValueError("universe entries must be short ASCII ticker names")
        if len({ticker.upper() for ticker in value}) != len(value):
            raise ValueError("universe entries must be unique")
        return value

    @model_validator(mode="after")
    def _bounded_dates(self) -> BacktestRequest:
        start = date.fromisoformat(self.start)
        end = date.fromisoformat(self.end)
        if end < start:
            raise ValueError("end must not precede start")
        if (end - start).days > 730:
            raise ValueError("backtest range cannot exceed 730 calendar days")
        budget_values = (
            self.paid_max_calls,
            self.paid_max_cost_usd,
            self.paid_max_attempt_cost_usd,
        )
        if self.authorize_paid_provider:
            if any(value is None for value in budget_values):
                raise ValueError("paid authorization requires finite call and cost bounds")
            total_cost = Decimal(self.paid_max_cost_usd)
            attempt_cost = Decimal(self.paid_max_attempt_cost_usd)
            if total_cost <= 0 or attempt_cost <= 0 or attempt_cost > total_cost or total_cost > Decimal("100") or attempt_cost > Decimal("10"):
                raise ValueError("paid authorization cost bounds are outside the allowed range")
        elif any(value is not None for value in budget_values):
            raise ValueError("paid cost bounds require explicit paid authorization")
        if self.confirm_fd_self_service_pricing and (not self.authorize_paid_provider or self.provider != "fd"):
            raise ValueError("Financial Datasets pricing confirmation does not match the request")
        return self


class OperationPreviewRequest(RequestModel):
    action: Literal["backtest"]
    subject_id: str = Field(min_length=1, max_length=64)
    expected_head: str = Field(pattern=r"^[0-9a-f]{64}$")
    payload: BacktestRequest


class OperationAcceptRequest(RequestModel):
    request_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
    action: Literal["backtest"]
    subject_id: str = Field(min_length=1, max_length=64)
    preview_id: str = Field(pattern=r"^[a-f0-9]{32}$")
    preview_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    confirmation_token: str = Field(min_length=32, max_length=512)
    expected_head: str = Field(pattern=r"^[0-9a-f]{64}$")
    due_set: list[str] = Field(default_factory=list, max_length=10000)
    payload: BacktestRequest


class OperationCancelRequest(RequestModel):
    request_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


class PaperTickPreviewRequest(RequestModel):
    expected_head: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")


class RunnerPreviewRequest(RequestModel):
    expected_head: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    max_sessions: StrictInt = Field(default=1, ge=1, le=100)
    max_runtime_minutes: StrictInt = Field(default=60, ge=1, le=1440)


class PaperOperationAcceptRequest(RequestModel):
    request_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
    preview_id: str = Field(pattern=r"^[a-f0-9]{32}$")
    preview_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    confirmation_token: str = Field(min_length=32, max_length=512)
    expected_head: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    due_set: list[str] = Field(default_factory=list, max_length=1)

    @field_validator("due_set")
    @classmethod
    def _valid_due_set(cls, value: list[str]) -> list[str]:
        if any(not re.fullmatch(r"\d{4}-\d{2}-\d{2}(?:T\d{2}:\d{2}:\d{2})?", item) for item in value):
            raise ValueError("due-set entries must be paper session keys")
        return value


class PaperTickAcceptRequest(PaperOperationAcceptRequest):
    due_set: list[str] = Field(min_length=1, max_length=1)


class RunnerStartAcceptRequest(PaperOperationAcceptRequest):
    max_sessions: StrictInt = Field(ge=1, le=100)
    max_runtime_minutes: StrictInt = Field(ge=1, le=1440)


class ModelRequest(RequestModel):
    model: str = Field(min_length=1, max_length=120)
    expected_version: int = Field(ge=0, le=2**31 - 1)


class RuntimeSettingsRequest(RequestModel):
    data_provider: Literal["fd", "yfinance"]
    model: str = Field(min_length=1, max_length=256)
    endpoint: str | None = Field(default=None, max_length=2048)
    timeout_seconds: float = Field(strict=True, gt=0, le=300)
    parameters: dict[str, StrictInt | StrictFloat] = Field(default_factory=dict)
    expected_version: StrictInt = Field(ge=0, le=2**31 - 1)


class CredentialRequest(RequestModel):
    provider: str = Field(min_length=1, max_length=32)
    value: SecretStr = Field(min_length=1, max_length=4096)
    expected_version: int = Field(ge=0, le=2**31 - 1)


class CapabilitiesResponse(BaseModel):
    mode: Literal["live", "demo"]
    read_only: bool
    writes: bool
    network: bool
    local_operator_only: bool
    csrf_authenticates_users: Literal[False]
    container_observer: bool
    enrollment_state: Literal["unenrolled", "enrolled", "invalid", "drift"]
    write_unavailable_reason: str | None
    protected_names: list[str]
    mutation_token: str | None
    deferred_actions: dict[str, str]
