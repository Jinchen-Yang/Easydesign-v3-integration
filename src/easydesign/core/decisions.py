"""跨阶段科学选择点的不可变、可审计契约。"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .artifacts import ID_PATTERN, SHA256_PATTERN
from .timestamps import normalize_aware_datetime


class DecisionAuthority(StrEnum):
    HUMAN = "human"
    DETERMINISTIC_POLICY = "deterministic-policy"


class DecisionStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"


class DecisionOption(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    option_id: str = Field(pattern=ID_PATTERN)
    label: str = Field(min_length=1, max_length=256)
    description: str = Field(min_length=1, max_length=4096)
    payload: dict[str, Any] = {}
    evidence_sha256: tuple[str, ...] = ()
    eligible: bool = True
    rejection_reasons: tuple[str, ...] = ()

    @field_validator("evidence_sha256")
    @classmethod
    def validate_hashes(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        for value in values:
            if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
                raise ValueError("evidence_sha256 必须是小写 SHA-256")
        return values


class DecisionRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: str = Field(default="0.1", pattern=r"^0\.1$")
    decision_id: str = Field(pattern=ID_PATTERN)
    stage_id: str = Field(pattern=r"^0[1-7]-[a-z0-9-]+$")
    gate: str = Field(pattern=ID_PATTERN)
    revision: int = Field(default=1, ge=1)
    status: DecisionStatus = DecisionStatus.PENDING
    created_at: datetime
    message: str = Field(min_length=1, max_length=4096)
    options: tuple[DecisionOption, ...] = Field(min_length=1)
    source_artifact_sha256: tuple[str, ...] = ()

    @field_validator("created_at")
    @classmethod
    def normalize_datetime(cls, value: datetime) -> datetime:
        return normalize_aware_datetime(value)

    @model_validator(mode="after")
    def validate_options(self) -> Self:
        identifiers = [option.option_id for option in self.options]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("Decision option_id 不能重复")
        for value in self.source_artifact_sha256:
            if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
                raise ValueError("source_artifact_sha256 必须是小写 SHA-256")
        return self


class DecisionRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: str = Field(default="0.1", pattern=r"^0\.1$")
    decision_id: str = Field(pattern=ID_PATTERN)
    request_revision: int = Field(ge=1)
    request_sha256: str = Field(pattern=SHA256_PATTERN)
    authority: DecisionAuthority
    selected_option_ids: tuple[str, ...] = Field(min_length=1)
    approved_at: datetime
    approved_by: str = Field(min_length=1, max_length=256)
    policy_id: str | None = Field(default=None, pattern=ID_PATTERN)
    acknowledgement: str | None = Field(default=None, max_length=4096)

    @field_validator("approved_at")
    @classmethod
    def normalize_datetime(cls, value: datetime) -> datetime:
        return normalize_aware_datetime(value)

    @model_validator(mode="after")
    def validate_authority(self) -> Self:
        if len(self.selected_option_ids) != len(set(self.selected_option_ids)):
            raise ValueError("selected_option_ids 不能重复")
        if self.authority is DecisionAuthority.DETERMINISTIC_POLICY:
            if self.policy_id is None:
                raise ValueError("deterministic-policy 必须记录 policy_id")
        elif self.policy_id is not None:
            raise ValueError("human DecisionRecord 不得伪造 policy_id")
        return self
