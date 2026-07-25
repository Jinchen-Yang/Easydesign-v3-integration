"""跨后端的任务、进度和结构化执行事件契约。"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .artifacts import ID_PATTERN, SHA256_PATTERN
from .attempts import ErrorInfo
from .timestamps import normalize_aware_datetime


class TaskStatus(StrEnum):
    """执行器任务状态；不表示候选的科学质量。"""

    PENDING = "pending"
    WAITING_RESOURCE = "waiting-resource"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"

    @property
    def is_terminal(self) -> bool:
        return self in {self.SUCCEEDED, self.FAILED}


class TaskAttemptRecord(BaseModel):
    """一个任务的一次不可覆盖后端执行。"""

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    attempt_number: int = Field(ge=1)
    status: TaskStatus
    requested_candidates: int = Field(ge=1)
    collected_candidates: int = Field(default=0, ge=0)
    device: int = Field(ge=0)
    command_sha256: str = Field(pattern=SHA256_PATTERN)
    output_relative_path: str = Field(min_length=1)
    started_at: datetime
    ended_at: datetime | None = None
    return_code: int | None = None
    error: ErrorInfo | None = None

    @field_validator("started_at", "ended_at")
    @classmethod
    def normalize_datetime(cls, value: datetime | None) -> datetime | None:
        return None if value is None else normalize_aware_datetime(value)

    @model_validator(mode="after")
    def validate_terminal_state(self) -> Self:
        if self.status is TaskStatus.RUNNING:
            if self.ended_at is not None or self.return_code is not None or self.error is not None:
                raise ValueError("running task attempt 不能包含终态字段")
        elif self.status.is_terminal:
            if self.ended_at is None or self.return_code is None:
                raise ValueError("终态 task attempt 必须记录结束时间和 return code")
            if self.ended_at < self.started_at:
                raise ValueError("task attempt 结束时间不能早于开始时间")
            if self.status is TaskStatus.SUCCEEDED:
                if self.return_code != 0 or self.error is not None:
                    raise ValueError("succeeded task attempt 必须 return_code=0 且无错误")
            elif self.error is None:
                raise ValueError("failed task attempt 必须包含结构化错误")
        else:
            raise ValueError("TaskAttemptRecord 只接受 running/succeeded/failed")
        if self.collected_candidates > self.requested_candidates:
            raise ValueError("单次 attempt 收集数不能大于本次请求数")
        return self


class TaskRecord(BaseModel):
    """一个稳定 strategy task 及其全部执行 attempt。"""

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    task_id: str = Field(pattern=ID_PATTERN)
    strategy_id: str = Field(pattern=ID_PATTERN)
    status: TaskStatus = TaskStatus.PENDING
    requested_candidates: int = Field(ge=1)
    collected_candidates: int = Field(default=0, ge=0)
    candidate_ids: tuple[str, ...] = ()
    attempts: tuple[TaskAttemptRecord, ...] = ()
    current_device: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_record(self) -> Self:
        attempt_numbers = [attempt.attempt_number for attempt in self.attempts]
        if attempt_numbers != list(range(1, len(attempt_numbers) + 1)):
            raise ValueError("task attempt number 必须从 1 连续递增")
        if len(self.candidate_ids) != len(set(self.candidate_ids)):
            raise ValueError("TaskRecord candidate identity 不能重复")
        if len(self.candidate_ids) != self.collected_candidates:
            raise ValueError("candidate_ids 数量必须等于 collected_candidates")
        if self.collected_candidates > self.requested_candidates:
            raise ValueError("task 收集数不能超过请求数")
        if self.status is TaskStatus.SUCCEEDED:
            if self.collected_candidates != self.requested_candidates:
                raise ValueError("succeeded task 必须达到精确候选预算")
            if not self.attempts or self.attempts[-1].status is not TaskStatus.SUCCEEDED:
                raise ValueError("succeeded task 的末次 attempt 必须成功")
        if self.status is TaskStatus.RUNNING:
            if self.current_device is None:
                raise ValueError("running task 必须声明 current_device")
            if not self.attempts or self.attempts[-1].status is not TaskStatus.RUNNING:
                raise ValueError("running task 的末次 attempt 必须运行中")
        elif self.current_device is not None:
            raise ValueError("非 running task 不得声明 current_device")
        return self


class TaskEvent(BaseModel):
    """append-only task event 的单行 schema。"""

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    schema_version: str = "0.1"
    sequence: int = Field(ge=1)
    occurred_at: datetime
    event_type: str = Field(pattern=ID_PATTERN)
    task_id: str | None = Field(default=None, pattern=ID_PATTERN)
    strategy_id: str | None = Field(default=None, pattern=ID_PATTERN)
    task_attempt_number: int | None = Field(default=None, ge=1)
    device: int | None = Field(default=None, ge=0)
    from_status: TaskStatus | None = None
    to_status: TaskStatus | None = None
    message: str = Field(min_length=1, max_length=4096)
    error: ErrorInfo | None = None

    @field_validator("occurred_at")
    @classmethod
    def normalize_datetime(cls, value: datetime) -> datetime:
        return normalize_aware_datetime(value)


class ProgressSnapshot(BaseModel):
    """供 CLI/UI 读取的原子进度快照。"""

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    schema_version: str = "0.1"
    stage_id: str = Field(pattern=ID_PATTERN)
    updated_at: datetime
    status: str = Field(pattern=ID_PATTERN)
    total_tasks: int = Field(ge=0)
    pending_tasks: int = Field(ge=0)
    waiting_tasks: int = Field(ge=0)
    running_tasks: int = Field(ge=0)
    succeeded_tasks: int = Field(ge=0)
    failed_tasks: int = Field(ge=0)
    planned_candidates: int = Field(ge=0)
    collected_candidates: int = Field(ge=0)
    per_device: dict[str, str | None] = Field(default_factory=dict)
    elapsed_seconds: float = Field(default=0, ge=0)
    throughput_candidates_per_hour: float | None = Field(default=None, ge=0)
    estimated_remaining_seconds: float | None = Field(default=None, ge=0)
    recent_errors: tuple[str, ...] = ()

    @field_validator("updated_at")
    @classmethod
    def normalize_datetime(cls, value: datetime) -> datetime:
        return normalize_aware_datetime(value)

    @model_validator(mode="after")
    def validate_totals(self) -> Self:
        observed = (
            self.pending_tasks
            + self.waiting_tasks
            + self.running_tasks
            + self.succeeded_tasks
            + self.failed_tasks
        )
        if observed != self.total_tasks:
            raise ValueError("progress task 状态计数之和必须等于 total_tasks")
        if self.collected_candidates > self.planned_candidates:
            raise ValueError("progress collected_candidates 不能超过 planned_candidates")
        return self
