"""Stage 06 sharded scale-generation plans, resume state, and handoff bundle."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from easydesign.core import ArtifactRef, ProgressSnapshot, TaskRecord
from easydesign.core.artifacts import ID_PATTERN, SHA256_PATTERN
from easydesign.stages.s04_pilot_generation import CandidateRecord


class ScaleProfile(StrEnum):
    SMOKE_1000 = "smoke-1000"
    PRODUCTION_50000 = "production-50000"

    @property
    def requested_candidates(self) -> int:
        return 1_000 if self is self.SMOKE_1000 else 50_000

    @property
    def shard_size(self) -> int:
        return 500 if self is self.SMOKE_1000 else 2_500


class ScaleShard(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    shard_id: str = Field(pattern=ID_PATTERN)
    task_id: str = Field(pattern=ID_PATTERN)
    strategy_id: str = Field(pattern=ID_PATTERN)
    ordinal_start: int = Field(ge=1)
    ordinal_end: int = Field(ge=1)
    requested_candidates: int = Field(ge=1)

    @model_validator(mode="after")
    def validate_range(self) -> Self:
        if self.ordinal_end < self.ordinal_start:
            raise ValueError("ScaleShard ordinal range 倒置")
        if self.ordinal_end - self.ordinal_start + 1 != self.requested_candidates:
            raise ValueError("ScaleShard ordinal range 与 requested_candidates 不一致")
        return self


class ScaleResourceReport(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["0.1"] = "0.1"
    measured_at: datetime
    measurement_source: Literal["stage04-declared-candidate-artifacts"] = (
        "stage04-declared-candidate-artifacts"
    )
    measured_candidate_count: int = Field(ge=1)
    measured_candidate_bytes: int = Field(ge=1)
    measured_bytes_per_candidate: float = Field(gt=0)
    storage_safety_multiplier: Literal[20] = 20
    estimated_peak_bytes: int = Field(ge=1)
    filesystem_total_bytes: int = Field(ge=1)
    filesystem_free_bytes: int = Field(ge=0)
    required_reserve_fraction: float = Field(default=0.25, ge=0, le=1)
    projected_free_bytes: int = Field(ge=0)
    passed: bool
    reason: str = Field(min_length=1, max_length=2048)

    @model_validator(mode="after")
    def validate_projection(self) -> Self:
        if self.required_reserve_fraction != 0.25:
            raise ValueError("Stage 06 v0.1 disk reserve 固定为 25%")
        expected = self.filesystem_free_bytes - self.estimated_peak_bytes
        if expected < 0:
            expected = 0
        if self.projected_free_bytes != expected:
            raise ValueError("ScaleResourceReport projected free bytes 不一致")
        expected_pass = (
            self.filesystem_free_bytes >= self.estimated_peak_bytes
            and self.projected_free_bytes
            >= int(self.filesystem_total_bytes * self.required_reserve_fraction)
        )
        if self.passed != expected_pass:
            raise ValueError("ScaleResourceReport pass 与 25% reserve 规则不一致")
        return self


class ScaleStrategyAuthorization(BaseModel):
    """Authority and scientific boundary for the strategy selected for scale."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        str_strip_whitespace=True,
    )

    schema_version: Literal["0.1"] = "0.1"
    mode: Literal["stage05-winner", "manual-stage05-stop-override"]
    strategy_id: str = Field(pattern=ID_PATTERN)
    authorized_at: datetime
    authorized_by: str = Field(min_length=1, max_length=256)
    reason: str = Field(min_length=1, max_length=4096)
    source_stage05_status: Literal[
        "winner-selected",
        "stopped-no-scale-winner",
    ]
    source_stage05_bundle_sha256: str = Field(pattern=SHA256_PATTERN)
    acknowledge_stage05_scientific_stop: bool = False
    acknowledge_not_scientifically_eligible: bool = False

    @model_validator(mode="after")
    def validate_authority(self) -> Self:
        if self.mode == "stage05-winner":
            if self.source_stage05_status != "winner-selected":
                raise ValueError("Stage 05 winner authorization 必须来自 winner-selected")
            if (
                self.acknowledge_stage05_scientific_stop
                or self.acknowledge_not_scientifically_eligible
            ):
                raise ValueError(
                    "正常 winner authorization 不得伪造 scientific-stop acknowledgement"
                )
        else:
            if self.source_stage05_status != "stopped-no-scale-winner":
                raise ValueError("manual override 只接受 stopped-no-scale-winner")
            if not (
                self.acknowledge_stage05_scientific_stop
                and self.acknowledge_not_scientifically_eligible
            ):
                raise ValueError("manual override 必须确认 scientific stop 与科学不合格边界")
        return self


class ScalePlan(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["0.1"] = "0.1"
    generated_at: datetime
    profile: ScaleProfile
    strategy_id: str = Field(pattern=ID_PATTERN)
    strategy_bundle_sha256: str = Field(pattern=SHA256_PATTERN)
    stage05_bundle_sha256: str = Field(pattern=SHA256_PATTERN)
    strategy_authorization: ScaleStrategyAuthorization
    design_specification: ArtifactRef
    requested_new_candidates: int = Field(ge=1)
    preauthorized_candidate_limit: int = Field(ge=1)
    devices: tuple[int, ...] = Field(min_length=1)
    workers_per_device: Literal[1] = 1
    shards: tuple[ScaleShard, ...] = Field(min_length=1)
    resource_report: ArtifactRef
    execution_authorized: bool

    @model_validator(mode="after")
    def validate_plan(self) -> Self:
        if self.requested_new_candidates != self.profile.requested_candidates:
            raise ValueError("ScalePlan count 与 profile 不一致")
        if self.requested_new_candidates > self.preauthorized_candidate_limit:
            raise ValueError("ScalePlan 超过预授权 candidate limit")
        if len(self.devices) != len(set(self.devices)):
            raise ValueError("ScalePlan GPU device 不能重复")
        shard_ids = [item.shard_id for item in self.shards]
        task_ids = [item.task_id for item in self.shards]
        if len(shard_ids) != len(set(shard_ids)) or len(task_ids) != len(set(task_ids)):
            raise ValueError("ScalePlan shard/task identity 不能重复")
        if any(item.strategy_id != self.strategy_id for item in self.shards):
            raise ValueError("ScalePlan shard strategy 不一致")
        if self.strategy_authorization.strategy_id != self.strategy_id:
            raise ValueError("ScalePlan strategy authorization 与 strategy 不一致")
        ordered = sorted(self.shards, key=lambda item: item.ordinal_start)
        expected_start = 1
        for shard in ordered:
            if shard.ordinal_start != expected_start:
                raise ValueError("ScalePlan shard ordinal 必须连续无缺口")
            expected_start = shard.ordinal_end + 1
        if expected_start - 1 != self.requested_new_candidates:
            raise ValueError("ScalePlan shard candidate 总数不一致")
        return self


class ScaleTaskTable(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["0.1"] = "0.1"
    generated_at: datetime
    tasks: tuple[TaskRecord, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_tasks(self) -> Self:
        task_ids = [item.task_id for item in self.tasks]
        if len(task_ids) != len(set(task_ids)):
            raise ValueError("ScaleTaskTable task_id 不能重复")
        return self


class ScaleCoverageReport(BaseModel):
    """Exact merge coverage for the new Stage 06 candidate population."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["0.1"] = "0.1"
    strategy_id: str = Field(pattern=ID_PATTERN)
    requested_new_candidates: int = Field(ge=1)
    complete_new_candidates: int = Field(ge=1)
    candidate_ids_unique: bool
    ordinal_min: int = Field(ge=1)
    ordinal_max: int = Field(ge=1)
    ordinal_gaps: tuple[int, ...] = ()
    status: Literal["complete"] = "complete"

    @model_validator(mode="after")
    def validate_coverage(self) -> Self:
        if self.complete_new_candidates != self.requested_new_candidates:
            raise ValueError("ScaleCoverageReport 必须精确完成 requested candidates")
        if not self.candidate_ids_unique:
            raise ValueError("ScaleCoverageReport candidate identity 必须唯一")
        if self.ordinal_min != 1 or self.ordinal_max != self.requested_new_candidates:
            raise ValueError("ScaleCoverageReport ordinal 边界不完整")
        if self.ordinal_gaps:
            raise ValueError("ScaleCoverageReport 不允许 ordinal 缺口")
        return self


class ScaleExecutionState(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["0.1"] = "0.1"
    created_at: datetime
    updated_at: datetime
    plan_sha256: str = Field(pattern=SHA256_PATTERN)
    tasks: tuple[TaskRecord, ...] = Field(min_length=1)
    candidates: tuple[CandidateRecord, ...] = ()
    progress: ProgressSnapshot


class ScaleBundle(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["0.1"] = "0.1"
    generated_at: datetime
    stage05_bundle: ArtifactRef
    strategy_bundle: ArtifactRef
    strategy_authorization: ArtifactRef
    scale_plan: ArtifactRef
    resource_report: ArtifactRef
    task_table: ArtifactRef
    candidate_index: ArtifactRef
    coverage_report: ArtifactRef
    progress_final: ArtifactRef
    task_events: ArtifactRef
    backend_environment: ArtifactRef
    profile: ScaleProfile
    strategy_id: str = Field(pattern=ID_PATTERN)
    requested_new_candidates: int = Field(ge=1)
    complete_new_candidates: int = Field(ge=1)
    shard_count: int = Field(ge=1)
    status: Literal["succeeded"] = "succeeded"

    @model_validator(mode="after")
    def validate_counts(self) -> Self:
        if self.requested_new_candidates != self.profile.requested_candidates:
            raise ValueError("ScaleBundle profile count 不一致")
        if self.complete_new_candidates != self.requested_new_candidates:
            raise ValueError("ScaleBundle 必须精确完成 requested new candidates")
        return self
