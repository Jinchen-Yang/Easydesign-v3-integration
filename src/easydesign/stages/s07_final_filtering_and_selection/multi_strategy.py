"""Stage 07 v0.2 scale-input normalization and strategy-lineage contracts."""

from __future__ import annotations

from collections import Counter
from datetime import datetime
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from easydesign.core import ArtifactRef, ManifestStateError
from easydesign.core.artifacts import ID_PATTERN, SHA256_PATTERN
from easydesign.stages.s06_scale_generation_and_refolding import (
    ScaleBundle,
    ScaleBundleV0_2,
)

from .models import FinalCandidate


class Stage07StrategyAllocation(BaseModel):
    """Normalized allocation accepted from ScaleBundle 0.1 or 0.2."""

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    strategy_id: str = Field(pattern=ID_PATTERN)
    requested_candidates: int = Field(ge=1)
    promotion_rank: int | None = Field(default=None, ge=1, le=3)


class Stage07ScaleInput(BaseModel):
    """The exact candidate population Stage 07 is authorized to consume."""

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    schema_version: Literal["0.2"] = "0.2"
    source_scale_bundle_schema: Literal["0.1", "0.2"]
    source_scale_bundle_sha256: str = Field(pattern=SHA256_PATTERN)
    candidate_index_sha256: str = Field(pattern=SHA256_PATTERN)
    allocation_policy: Literal[
        "legacy-single-strategy",
        "equal-across-promoted-v1",
    ]
    total_candidate_budget: int = Field(ge=1)
    strategy_allocations: tuple[Stage07StrategyAllocation, ...] = Field(
        min_length=1,
        max_length=3,
    )

    @model_validator(mode="after")
    def validate_input(self) -> Self:
        strategy_ids = [item.strategy_id for item in self.strategy_allocations]
        if len(strategy_ids) != len(set(strategy_ids)):
            raise ValueError("Stage 07 input strategy_id 不能重复")
        if (
            sum(item.requested_candidates for item in self.strategy_allocations)
            != self.total_candidate_budget
        ):
            raise ValueError("Stage 07 input allocations 与 total budget 不一致")
        if self.source_scale_bundle_schema == "0.1":
            if (
                self.allocation_policy != "legacy-single-strategy"
                or len(self.strategy_allocations) != 1
                or self.strategy_allocations[0].promotion_rank is not None
            ):
                raise ValueError("ScaleBundle 0.1 必须规范化为 legacy single strategy")
        elif self.allocation_policy != "equal-across-promoted-v1":
            raise ValueError("ScaleBundle 0.2 必须保留 equal allocation policy")
        return self


class ScaleCandidateLineage(BaseModel):
    """Candidate identity used for global deduplication without losing source YAML."""

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    candidate_id: str = Field(pattern=ID_PATTERN)
    strategy_id: str = Field(pattern=ID_PATTERN)
    strategy_ordinal: int = Field(ge=1)
    sequence_sha256: str = Field(pattern=SHA256_PATTERN)


class StrategySourceDistribution(BaseModel):
    """Final package source counts; it is descriptive, never a quota."""

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    strategy_id: str = Field(pattern=ID_PATTERN)
    primary_count: int = Field(ge=0)
    backup_count: int = Field(ge=0)
    total_selected_count: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_count(self) -> Self:
        if self.total_selected_count != self.primary_count + self.backup_count:
            raise ValueError("strategy source distribution 总数不一致")
        return self


class FinalCandidatePackageV0_2(BaseModel):
    """Global selection across all YAMLs with complete source distribution."""

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    schema_version: Literal["0.2"] = "0.2"
    generated_at: datetime
    package_type: Literal[
        "smoke-review-package",
        "draft-order-package",
        "empty-review-package",
    ]
    scale_profile: Literal["smoke-1000", "production-50000"]
    selection_scope: Literal["global-across-strategies"] = (
        "global-across-strategies"
    )
    primary: tuple[FinalCandidate, ...] = ()
    backup: tuple[FinalCandidate, ...] = ()
    requested_primary_count: int = Field(ge=0)
    requested_backup_count: int = Field(ge=0)
    source_distribution: tuple[StrategySourceDistribution, ...] = ()
    human_review_status: Literal["awaiting-human-review"] = (
        "awaiting-human-review"
    )
    biosafety_review_status: Literal["not-required", "pending"]
    ordering_status: Literal["not-ordered"] = "not-ordered"
    status: Literal["candidates-selected", "stopped-no-final-candidate"]

    @model_validator(mode="after")
    def validate_package(self) -> Self:
        selected = self.primary + self.backup
        identities = [item.candidate_id for item in selected]
        if len(identities) != len(set(identities)):
            raise ValueError("primary/backup candidate 不能重复")
        if len(self.primary) > self.requested_primary_count:
            raise ValueError("primary 超过请求上限")
        if len(self.backup) > self.requested_backup_count:
            raise ValueError("backup 超过请求上限")
        distribution_ids = [item.strategy_id for item in self.source_distribution]
        if len(distribution_ids) != len(set(distribution_ids)):
            raise ValueError("source distribution strategy_id 不能重复")
        expected_primary = Counter(item.strategy_id for item in self.primary)
        expected_backup = Counter(item.strategy_id for item in self.backup)
        distribution = {item.strategy_id: item for item in self.source_distribution}
        expected_ids = set(expected_primary) | set(expected_backup)
        if set(distribution) != expected_ids:
            raise ValueError("source distribution 必须精确覆盖 selected strategy")
        for strategy_id in expected_ids:
            item = distribution[strategy_id]
            if (
                item.primary_count != expected_primary[strategy_id]
                or item.backup_count != expected_backup[strategy_id]
            ):
                raise ValueError("source distribution 与最终候选不一致")
        if self.status == "stopped-no-final-candidate":
            if selected or self.source_distribution or self.package_type != (
                "empty-review-package"
            ):
                raise ValueError("empty scientific stop 不得包含候选或来源")
        elif not selected:
            raise ValueError("candidates-selected 必须包含至少一个候选")
        return self


class Stage07BundleV0_2(BaseModel):
    """Stage 07 handoff preserving normalized scale input and YAML lineage."""

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    schema_version: Literal["0.2"] = "0.2"
    generated_at: datetime
    scale_bundle: ArtifactRef
    scale_input: ArtifactRef
    filter_profile: ArtifactRef
    final_filter_report: ArtifactRef
    final_candidate_package: ArtifactRef
    seed101_normalization: ArtifactRef | None = None
    tnp_report: ArtifactRef | None = None
    progress_final: ArtifactRef
    task_events: ArtifactRef
    operational_failures: ArtifactRef | None = None
    scientific_stop: ArtifactRef | None = None
    status: Literal["candidates-selected", "stopped-no-final-candidate"]

    @model_validator(mode="after")
    def validate_bundle(self) -> Self:
        if self.status == "candidates-selected":
            if self.tnp_report is None or self.scientific_stop is not None:
                raise ValueError("最终候选包必须包含 TNP 且不能包含 scientific stop")
        elif self.scientific_stop is None:
            raise ValueError("empty final result 必须包含 scientific stop")
        return self


def normalize_scale_bundle_for_stage07(
    *,
    scale_bundle: ScaleBundle | ScaleBundleV0_2,
    scale_bundle_sha256: str,
    candidate_index_sha256: str,
) -> Stage07ScaleInput:
    """Accept immutable v0.1 history and v0.2 multi-strategy bundles."""

    if isinstance(scale_bundle, ScaleBundleV0_2):
        allocations = tuple(
            Stage07StrategyAllocation(
                strategy_id=item.strategy_id,
                requested_candidates=item.requested_candidates,
                promotion_rank=item.promotion_rank,
            )
            for item in scale_bundle.strategy_allocations
        )
        return Stage07ScaleInput(
            source_scale_bundle_schema="0.2",
            source_scale_bundle_sha256=scale_bundle_sha256,
            candidate_index_sha256=candidate_index_sha256,
            allocation_policy=scale_bundle.allocation_policy,
            total_candidate_budget=scale_bundle.total_candidate_budget,
            strategy_allocations=allocations,
        )
    return Stage07ScaleInput(
        source_scale_bundle_schema="0.1",
        source_scale_bundle_sha256=scale_bundle_sha256,
        candidate_index_sha256=candidate_index_sha256,
        allocation_policy="legacy-single-strategy",
        total_candidate_budget=scale_bundle.requested_new_candidates,
        strategy_allocations=(
            Stage07StrategyAllocation(
                strategy_id=scale_bundle.strategy_id,
                requested_candidates=scale_bundle.requested_new_candidates,
            ),
        ),
    )


def validate_scale_candidate_lineage(
    *,
    scale_input: Stage07ScaleInput,
    candidates: tuple[ScaleCandidateLineage, ...],
) -> None:
    """Reject strategy mismatch, global duplicates, and per-strategy ordinal gaps."""

    if len(candidates) != scale_input.total_candidate_budget:
        raise ManifestStateError("Stage 07 candidate 总数与 scale input 不一致")
    candidate_ids = [item.candidate_id for item in candidates]
    if len(candidate_ids) != len(set(candidate_ids)):
        raise ManifestStateError("Stage 07 candidate identity 全局重复")
    allocations = {
        item.strategy_id: item.requested_candidates
        for item in scale_input.strategy_allocations
    }
    by_strategy: dict[str, list[ScaleCandidateLineage]] = {
        strategy_id: [] for strategy_id in allocations
    }
    for candidate in candidates:
        if candidate.strategy_id not in by_strategy:
            raise ManifestStateError("Stage 07 candidate 来自未授权 strategy")
        by_strategy[candidate.strategy_id].append(candidate)
    for strategy_id, requested in allocations.items():
        group = by_strategy[strategy_id]
        if len(group) != requested:
            raise ManifestStateError("Stage 07 per-strategy candidate 数量不一致")
        ordinals = sorted(item.strategy_ordinal for item in group)
        if ordinals != list(range(1, requested + 1)):
            raise ManifestStateError("Stage 07 per-strategy ordinal 有重复或缺口")


def summarize_selected_sources(
    *,
    primary: tuple[FinalCandidate, ...],
    backup: tuple[FinalCandidate, ...],
) -> tuple[StrategySourceDistribution, ...]:
    """Describe global-selection provenance without reserving per-YAML slots."""

    primary_counts = Counter(item.strategy_id for item in primary)
    backup_counts = Counter(item.strategy_id for item in backup)
    return tuple(
        StrategySourceDistribution(
            strategy_id=strategy_id,
            primary_count=primary_counts[strategy_id],
            backup_count=backup_counts[strategy_id],
            total_selected_count=(
                primary_counts[strategy_id] + backup_counts[strategy_id]
            ),
        )
        for strategy_id in sorted(set(primary_counts) | set(backup_counts))
    )
