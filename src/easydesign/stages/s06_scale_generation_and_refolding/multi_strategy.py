"""Stage 06 v0.2 multi-strategy allocation, shards, and coverage contracts."""

from __future__ import annotations

from datetime import datetime
from typing import Final, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from easydesign.core import ArtifactRef, ManifestStateError
from easydesign.core.artifacts import ID_PATTERN, SHA256_PATTERN
from easydesign.stages.s04_pilot_generation import CandidateRecord
from easydesign.stages.s05_pilot_filtering import StrategyPromotionRecord

from .models import ScaleProfile

ALLOCATION_POLICY: Final[Literal["equal-across-promoted-v1"]] = (
    "equal-across-promoted-v1"
)


class StrategyAllocation(BaseModel):
    """One promoted strategy's exact share of the global candidate budget."""

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    strategy_id: str = Field(pattern=ID_PATTERN)
    promotion_rank: int = Field(ge=1, le=3)
    score_yaml: float = Field(ge=0, le=1)
    requested_candidates: int = Field(ge=1)


class MultiStrategyScaleShard(BaseModel):
    """A resumable shard with ordinals local to one strategy."""

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    shard_id: str = Field(pattern=ID_PATTERN)
    task_id: str = Field(pattern=ID_PATTERN)
    strategy_id: str = Field(pattern=ID_PATTERN)
    strategy_ordinal_start: int = Field(ge=1)
    strategy_ordinal_end: int = Field(ge=1)
    requested_candidates: int = Field(ge=1)

    @model_validator(mode="after")
    def validate_range(self) -> Self:
        if self.strategy_ordinal_end < self.strategy_ordinal_start:
            raise ValueError("multi-strategy shard ordinal range 倒置")
        if (
            self.strategy_ordinal_end - self.strategy_ordinal_start + 1
            != self.requested_candidates
        ):
            raise ValueError("multi-strategy shard range 与 requested count 不一致")
        return self


class MultiStrategyScaleAuthorization(BaseModel):
    """Explicit high-cost authority for all v1.6 promoted strategies."""

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    schema_version: Literal["0.2"] = "0.2"
    mode: Literal["stage05-v1.6-promotions"] = "stage05-v1.6-promotions"
    authorized_at: datetime
    authorized_by: str = Field(min_length=1, max_length=256)
    reason: str = Field(min_length=1, max_length=4096)
    source_stage05_bundle_sha256: str = Field(pattern=SHA256_PATTERN)
    promoted_strategy_ids: tuple[str, ...] = Field(min_length=1, max_length=3)
    total_candidate_budget: int = Field(ge=1)
    acknowledge_high_cost_generation: bool

    @model_validator(mode="after")
    def validate_authorization(self) -> Self:
        if len(self.promoted_strategy_ids) != len(set(self.promoted_strategy_ids)):
            raise ValueError("scale authorization strategy_id 不能重复")
        if not self.acknowledge_high_cost_generation:
            raise ValueError("高成本 Stage 06 必须显式确认预算")
        return self


class ScalePlanV0_2(BaseModel):
    """Global plan for one to three promoted strategies."""

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    schema_version: Literal["0.2"] = "0.2"
    generated_at: datetime
    profile: ScaleProfile
    total_candidate_budget: int = Field(ge=1)
    preauthorized_candidate_limit: int = Field(ge=1)
    allocation_policy: Literal["equal-across-promoted-v1"] = ALLOCATION_POLICY
    strategy_bundle_sha256: str = Field(pattern=SHA256_PATTERN)
    stage05_bundle_sha256: str = Field(pattern=SHA256_PATTERN)
    strategy_authorization: MultiStrategyScaleAuthorization
    strategy_allocations: tuple[StrategyAllocation, ...] = Field(
        min_length=1,
        max_length=3,
    )
    design_specifications: tuple[ArtifactRef, ...] = Field(
        min_length=1,
        max_length=3,
    )
    devices: tuple[int, ...] = Field(min_length=1)
    workers_per_device: Literal[1] = 1
    shards: tuple[MultiStrategyScaleShard, ...] = Field(min_length=1)
    resource_report: ArtifactRef
    execution_authorized: bool

    @model_validator(mode="after")
    def validate_plan(self) -> Self:
        fixed_count = self.profile.fixed_candidate_count
        if fixed_count is not None and self.total_candidate_budget != fixed_count:
            raise ValueError("ScalePlanV0_2 total 与 profile 不一致")
        if self.total_candidate_budget > self.preauthorized_candidate_limit:
            raise ValueError("ScalePlanV0_2 超过预授权 candidate limit")
        if len(self.devices) != len(set(self.devices)):
            raise ValueError("ScalePlanV0_2 GPU device 不能重复")
        allocation_ids = tuple(item.strategy_id for item in self.strategy_allocations)
        if len(allocation_ids) != len(set(allocation_ids)):
            raise ValueError("strategy allocation identity 不能重复")
        expected_ranks = tuple(range(1, len(self.strategy_allocations) + 1))
        if tuple(item.promotion_rank for item in self.strategy_allocations) != expected_ranks:
            raise ValueError("strategy allocation 必须按 promotion rank 排列")
        if (
            sum(item.requested_candidates for item in self.strategy_allocations)
            != self.total_candidate_budget
        ):
            raise ValueError("strategy allocation 总数与 global budget 不一致")
        if self.strategy_authorization.promoted_strategy_ids != allocation_ids:
            raise ValueError("authorization strategy 集合或顺序不一致")
        if (
            self.strategy_authorization.total_candidate_budget
            != self.total_candidate_budget
        ):
            raise ValueError("authorization budget 与 scale plan 不一致")
        if self.strategy_authorization.source_stage05_bundle_sha256 != (
            self.stage05_bundle_sha256
        ):
            raise ValueError("authorization Stage 05 identity 不一致")
        design_ids = tuple(item.artifact_id for item in self.design_specifications)
        if len(design_ids) != len(set(design_ids)):
            raise ValueError("design specification ArtifactRef 不能重复")
        if len(design_ids) != len(allocation_ids):
            raise ValueError("每个 strategy 必须有一个 design specification")
        expected_design_ids = tuple(
            f"strategy-{strategy_id}" for strategy_id in allocation_ids
        )
        if design_ids != expected_design_ids:
            raise ValueError(
                "design specification 必须按晋级顺序与 strategy identity 一一对应"
            )
        shard_ids = [item.shard_id for item in self.shards]
        task_ids = [item.task_id for item in self.shards]
        if len(shard_ids) != len(set(shard_ids)):
            raise ValueError("ScalePlanV0_2 shard_id 不能重复")
        if len(task_ids) != len(set(task_ids)):
            raise ValueError("ScalePlanV0_2 task_id 不能重复")
        shards_by_strategy: dict[str, list[MultiStrategyScaleShard]] = {
            strategy_id: [] for strategy_id in allocation_ids
        }
        for shard in self.shards:
            if shard.strategy_id not in shards_by_strategy:
                raise ValueError("scale shard 来自未晋级 strategy")
            shards_by_strategy[shard.strategy_id].append(shard)
        allocations = {
            item.strategy_id: item.requested_candidates
            for item in self.strategy_allocations
        }
        for strategy_id, strategy_shards in shards_by_strategy.items():
            expected_start = 1
            for shard in sorted(
                strategy_shards,
                key=lambda item: item.strategy_ordinal_start,
            ):
                if shard.strategy_ordinal_start != expected_start:
                    raise ValueError("strategy shard ordinal 必须连续无缺口")
                expected_start = shard.strategy_ordinal_end + 1
            if expected_start - 1 != allocations[strategy_id]:
                raise ValueError("strategy shard 总数与 allocation 不一致")
        return self


class StrategyScaleCoverage(BaseModel):
    """Exact coverage for one strategy's local ordinal space."""

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    strategy_id: str = Field(pattern=ID_PATTERN)
    requested_candidates: int = Field(ge=1)
    complete_candidates: int = Field(ge=1)
    candidate_ids_unique: bool
    ordinal_min: int = Field(ge=1)
    ordinal_max: int = Field(ge=1)
    ordinal_gaps: tuple[int, ...] = ()

    @model_validator(mode="after")
    def validate_coverage(self) -> Self:
        if self.complete_candidates != self.requested_candidates:
            raise ValueError("strategy coverage 必须精确完成 requested candidates")
        if not self.candidate_ids_unique:
            raise ValueError("strategy candidate identity 必须唯一")
        if self.ordinal_min != 1 or self.ordinal_max != self.requested_candidates:
            raise ValueError("strategy ordinal 边界不完整")
        if self.ordinal_gaps:
            raise ValueError("strategy ordinal 不允许缺口")
        return self


class ScaleCoverageReportV0_2(BaseModel):
    """Per-strategy and global exact merge coverage."""

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    schema_version: Literal["0.2"] = "0.2"
    allocation_policy: Literal["equal-across-promoted-v1"] = ALLOCATION_POLICY
    total_requested_candidates: int = Field(ge=1)
    total_complete_candidates: int = Field(ge=1)
    global_candidate_ids_unique: bool
    strategy_coverage: tuple[StrategyScaleCoverage, ...] = Field(
        min_length=1,
        max_length=3,
    )
    status: Literal["complete"] = "complete"

    @model_validator(mode="after")
    def validate_global_coverage(self) -> Self:
        strategy_ids = [item.strategy_id for item in self.strategy_coverage]
        if len(strategy_ids) != len(set(strategy_ids)):
            raise ValueError("coverage strategy_id 不能重复")
        if not self.global_candidate_ids_unique:
            raise ValueError("global candidate identity 必须唯一")
        if self.total_complete_candidates != self.total_requested_candidates:
            raise ValueError("global coverage 必须精确完成 total budget")
        if (
            sum(item.requested_candidates for item in self.strategy_coverage)
            != self.total_requested_candidates
        ):
            raise ValueError("per-strategy requested 总数不一致")
        if (
            sum(item.complete_candidates for item in self.strategy_coverage)
            != self.total_complete_candidates
        ):
            raise ValueError("per-strategy complete 总数不一致")
        return self


class MultiStrategyCandidateIndex(BaseModel):
    """Candidate index with unequal per-strategy allocations."""

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    schema_version: Literal["0.2"] = "0.2"
    generated_at: datetime
    strategy_bundle_sha256: str = Field(pattern=SHA256_PATTERN)
    strategy_allocations: tuple[StrategyAllocation, ...] = Field(
        min_length=1,
        max_length=3,
    )
    candidates: tuple[CandidateRecord, ...]

    @model_validator(mode="after")
    def validate_candidates(self) -> Self:
        candidate_ids = [item.candidate_id for item in self.candidates]
        if len(candidate_ids) != len(set(candidate_ids)):
            raise ValueError("MultiStrategyCandidateIndex candidate_id 不能重复")
        allocations = {
            item.strategy_id: item.requested_candidates
            for item in self.strategy_allocations
        }
        by_strategy: dict[str, list[int]] = {
            strategy_id: [] for strategy_id in allocations
        }
        for candidate in self.candidates:
            if candidate.strategy_id not in by_strategy:
                raise ValueError("candidate 来自未晋级 strategy")
            by_strategy[candidate.strategy_id].append(
                candidate.ordinal_within_strategy
            )
        for strategy_id, requested in allocations.items():
            ordinals = sorted(by_strategy[strategy_id])
            if ordinals != list(range(1, requested + 1)):
                raise ValueError(
                    f"{strategy_id} candidate ordinal 有缺口、重复或数量不完整"
                )
        return self


class ScaleBundleV0_2(BaseModel):
    """Immutable Stage 06 handoff for a shared multi-strategy population."""

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    schema_version: Literal["0.2"] = "0.2"
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
    allocation_policy: Literal["equal-across-promoted-v1"] = ALLOCATION_POLICY
    total_candidate_budget: int = Field(ge=1)
    strategy_allocations: tuple[StrategyAllocation, ...] = Field(
        min_length=1,
        max_length=3,
    )
    complete_new_candidates: int = Field(ge=1)
    shard_count: int = Field(ge=1)
    status: Literal["succeeded"] = "succeeded"

    @model_validator(mode="after")
    def validate_counts(self) -> Self:
        fixed_count = self.profile.fixed_candidate_count
        if fixed_count is not None and self.total_candidate_budget != fixed_count:
            raise ValueError("ScaleBundleV0_2 profile count 不一致")
        if self.complete_new_candidates != self.total_candidate_budget:
            raise ValueError("ScaleBundleV0_2 必须精确完成 global budget")
        if (
            sum(item.requested_candidates for item in self.strategy_allocations)
            != self.total_candidate_budget
        ):
            raise ValueError("ScaleBundleV0_2 allocation 总数不一致")
        return self


def allocate_equal_candidate_budget(
    *,
    promoted_strategies: tuple[StrategyPromotionRecord, ...],
    total_candidate_budget: int,
) -> tuple[StrategyAllocation, ...]:
    """Split one global budget equally; remainder follows F_YAML promotion rank."""

    if not 1 <= len(promoted_strategies) <= 3:
        raise ManifestStateError("Stage 06 v0.2 只接受 1–3 个 promoted strategy")
    if total_candidate_budget < len(promoted_strategies):
        raise ManifestStateError("global candidate budget 不能小于 strategy 数")
    ordered = tuple(
        sorted(promoted_strategies, key=lambda item: item.promotion_rank)
    )
    expected_ranks = tuple(range(1, len(ordered) + 1))
    if tuple(item.promotion_rank for item in ordered) != expected_ranks:
        raise ManifestStateError("promotion rank 必须按 1..N 连续")
    if len({item.strategy_id for item in ordered}) != len(ordered):
        raise ManifestStateError("promoted strategy_id 不能重复")
    base, remainder = divmod(total_candidate_budget, len(ordered))
    return tuple(
        StrategyAllocation(
            strategy_id=item.strategy_id,
            promotion_rank=item.promotion_rank,
            score_yaml=item.score_yaml,
            requested_candidates=base + (1 if index < remainder else 0),
        )
        for index, item in enumerate(ordered)
    )


def build_multi_strategy_shards(
    *,
    strategy_allocations: tuple[StrategyAllocation, ...],
    shard_size: int,
) -> tuple[MultiStrategyScaleShard, ...]:
    """Create contiguous local ordinals; the last shard may be smaller."""

    if shard_size < 1:
        raise ManifestStateError("shard_size 必须为正整数")
    shards: list[MultiStrategyScaleShard] = []
    global_shard_number = 0
    for allocation in strategy_allocations:
        ordinal_start = 1
        strategy_shard_number = 0
        while ordinal_start <= allocation.requested_candidates:
            strategy_shard_number += 1
            global_shard_number += 1
            ordinal_end = min(
                ordinal_start + shard_size - 1,
                allocation.requested_candidates,
            )
            shards.append(
                MultiStrategyScaleShard(
                    shard_id=f"scale-shard-{global_shard_number:04d}",
                    task_id=f"scale-task-{global_shard_number:04d}",
                    strategy_id=allocation.strategy_id,
                    strategy_ordinal_start=ordinal_start,
                    strategy_ordinal_end=ordinal_end,
                    requested_candidates=ordinal_end - ordinal_start + 1,
                )
            )
            ordinal_start = ordinal_end + 1
    return tuple(shards)


def scale_candidate_id(strategy_id: str, strategy_ordinal: int) -> str:
    """Return an identity that retains source strategy and local ordinal."""

    if strategy_ordinal < 1:
        raise ManifestStateError("strategy ordinal 必须从 1 开始")
    candidate_id = f"{strategy_id}-scale-{strategy_ordinal:06d}"
    if len(candidate_id) > 128:
        raise ManifestStateError("strategy ID 过长，无法生成规范 candidate ID")
    return candidate_id
