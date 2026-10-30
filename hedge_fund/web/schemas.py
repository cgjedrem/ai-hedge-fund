"""Validated API request models."""

from __future__ import annotations

from datetime import date
from typing import Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
    SecretStr,
)


class RequestModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class MandateCreateRequest(RequestModel):
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


class ModelRequest(RequestModel):
    model: str = Field(min_length=1, max_length=120)


class CredentialRequest(RequestModel):
    provider: str = Field(min_length=1, max_length=32)
    value: SecretStr = Field(min_length=1, max_length=4096)


class CapabilitiesResponse(BaseModel):
    mode: Literal["live", "demo"]
    read_only: bool
    writes: bool
    network: bool
    protected_names: list[str]
    mutation_token: str | None
    deferred_actions: dict[str, str]
