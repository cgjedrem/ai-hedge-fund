"""Validated API request models."""

from __future__ import annotations

import re
from datetime import date
from typing import Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
    SecretStr,
    StrictFloat,
    StrictInt,
)


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
