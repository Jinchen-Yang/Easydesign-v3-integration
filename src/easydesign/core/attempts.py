"""Attempt 执行状态、错误和终态不可变契约。"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .artifacts import ATTEMPT_PATTERN, ID_PATTERN, ArtifactRef
from .timestamps import normalize_aware_datetime


class ExecutionStatus(StrEnum):
    """一次执行或阶段的运行状态，不表示科学成熟度。"""

    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"

    @property
    def is_terminal(self) -> bool:
        return self in {self.SUCCEEDED, self.FAILED, self.CANCELLED}


class ErrorInfo(BaseModel):
    """可序列化、可分类的执行错误。"""

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    code: str = Field(pattern=ID_PATTERN)
    message: str = Field(min_length=1, max_length=4096)
    retryable: bool = False


class Attempt(BaseModel):
    """一个阶段的一次具体执行尝试。"""

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    attempt_id: str = Field(pattern=ATTEMPT_PATTERN)
    status: ExecutionStatus
    created_at: datetime
    started_at: datetime | None = None
    ended_at: datetime | None = None
    backend_name: str = Field(pattern=ID_PATTERN)
    backend_version: str | None = Field(default=None, min_length=1, max_length=128)
    executor_name: str = Field(pattern=ID_PATTERN)
    seed: int | None = Field(default=None, ge=0)
    log_artifacts: tuple[ArtifactRef, ...] = ()
    error: ErrorInfo | None = None

    @field_validator("created_at", "started_at", "ended_at")
    @classmethod
    def normalize_datetime(cls, value: datetime | None) -> datetime | None:
        return None if value is None else normalize_aware_datetime(value)

    @model_validator(mode="after")
    def validate_state(self) -> Self:
        if self.started_at is not None and self.started_at < self.created_at:
            raise ValueError("attempt 开始时间不能早于创建时间")

        if self.status is ExecutionStatus.PENDING:
            if self.started_at is not None or self.ended_at is not None or self.error is not None:
                raise ValueError("pending attempt 不能有开始/结束时间或错误")
        elif self.status is ExecutionStatus.RUNNING:
            if self.started_at is None or self.ended_at is not None or self.error is not None:
                raise ValueError("running attempt 必须已开始且尚未结束、没有终态错误")
        else:
            if self.started_at is None or self.ended_at is None:
                raise ValueError("终态 attempt 必须有开始和结束时间")
            if self.ended_at < self.started_at:
                raise ValueError("attempt 结束时间不能早于开始时间")

        if self.status is ExecutionStatus.FAILED and self.error is None:
            raise ValueError("failed attempt 必须记录 error")
        if self.status is ExecutionStatus.SUCCEEDED and self.error is not None:
            raise ValueError("succeeded attempt 不能记录 error")

        artifact_ids = [artifact.artifact_id for artifact in self.log_artifacts]
        if len(artifact_ids) != len(set(artifact_ids)):
            raise ValueError("attempt log artifact_id 不能重复")
        return self
