"""Immutable cross-run evidence links without machine paths or artifact copies."""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .artifacts import ID_PATTERN, SHA256_PATTERN, ArtifactRef


class RunEvidenceLink(BaseModel):
    """A checksum-bound reference to evidence owned by another immutable run."""

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    schema_version: Literal["0.1"] = "0.1"
    source_project_id: str = Field(pattern=ID_PATTERN)
    source_run_id: str = Field(pattern=ID_PATTERN)
    source_run_manifest_sha256: str = Field(pattern=SHA256_PATTERN)
    source_artifact: ArtifactRef
    executor_id: str = Field(pattern=ID_PATTERN)
    artifact_sha256: str = Field(pattern=SHA256_PATTERN)
    artifact_size_bytes: int = Field(ge=1)

    @model_validator(mode="after")
    def validate_artifact_identity(self) -> Self:
        if self.artifact_sha256 != self.source_artifact.sha256:
            raise ValueError("RunEvidenceLink artifact SHA-256 与 ArtifactRef 不一致")
        if self.artifact_size_bytes != self.source_artifact.size_bytes:
            raise ValueError("RunEvidenceLink artifact size 与 ArtifactRef 不一致")
        return self


class ReevaluatedStrategy(BaseModel):
    """One unchanged pilot strategy viewed under a newer policy."""

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    strategy_id: str = Field(pattern=ID_PATTERN)
    tier: Literal["tier-a", "tier-b", "tier-c", "tier-d"]
    score_yaml: float = Field(ge=0, le=1)
    old_selected_for_expansion: bool
    new_promoted: bool
    promotion_rank: int | None = Field(default=None, ge=1, le=3)

    @model_validator(mode="after")
    def validate_rank(self) -> Self:
        if self.new_promoted != (self.promotion_rank is not None):
            raise ValueError("PolicyReevaluation promotion rank 与 promoted 状态不一致")
        if self.new_promoted and self.tier != "tier-a":
            raise ValueError("PolicyReevaluation 不能晋级非 Tier A strategy")
        return self


class PolicyReevaluationRecord(BaseModel):
    """Explicitly re-evaluate frozen pilot evidence without rewriting history."""

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    schema_version: Literal["0.1"] = "0.1"
    generated_at: datetime
    source_stage05_bundle: RunEvidenceLink
    source_profile_id: Literal["nanobody-filter-standard-v1.5"] = (
        "nanobody-filter-standard-v1.5"
    )
    target_profile_id: Literal["nanobody-filter-standard-v1.6"] = (
        "nanobody-filter-standard-v1.6"
    )
    source_stage05_status: Literal[
        "winner-selected",
        "stopped-no-tier-a",
        "stopped-no-scale-winner",
    ]
    pilot_gates_identical: Literal[True] = True
    tier_definitions_identical: Literal[True] = True
    score_yaml_identical: Literal[True] = True
    strategies: tuple[ReevaluatedStrategy, ...] = Field(min_length=1)
    promoted_strategy_ids: tuple[str, ...] = Field(max_length=3)
    status: Literal["strategies-promoted", "stopped-no-tier-a"]

    @model_validator(mode="after")
    def validate_reevaluation(self) -> Self:
        strategy_ids = [item.strategy_id for item in self.strategies]
        if len(strategy_ids) != len(set(strategy_ids)):
            raise ValueError("PolicyReevaluation strategy_id 不能重复")
        promoted = tuple(
            item.strategy_id
            for item in sorted(
                (item for item in self.strategies if item.new_promoted),
                key=lambda item: item.promotion_rank or 0,
            )
        )
        if promoted != self.promoted_strategy_ids:
            raise ValueError("PolicyReevaluation promoted strategy 顺序不一致")
        if self.status == "strategies-promoted" and not promoted:
            raise ValueError("strategies-promoted 必须包含 strategy")
        if self.status == "stopped-no-tier-a" and promoted:
            raise ValueError("stopped-no-tier-a 不得包含 strategy")
        return self


class ScaleEvidenceAdoptionRecord(BaseModel):
    """Authorize Stage 07 to read a verified historical Stage 06 population in place."""

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    schema_version: Literal["0.1"] = "0.1"
    generated_at: datetime
    policy_reevaluation_sha256: str = Field(pattern=SHA256_PATTERN)
    source_scale_bundle: RunEvidenceLink
    source_scale_bundle_schema: Literal["0.1"] = "0.1"
    adopted_for_profile: Literal["nanobody-filter-standard-v1.6"] = (
        "nanobody-filter-standard-v1.6"
    )
    strategy_ids: tuple[str, ...] = Field(min_length=1, max_length=3)
    shard_count: int = Field(ge=1)
    candidate_count: int = Field(ge=1)
    expected_candidate_count: int = Field(ge=1)
    candidate_ids_unique: Literal[True] = True
    ordinals_contiguous: Literal[True] = True
    checksums_verified: Literal[True] = True
    status: Literal["adopted"] = "adopted"

    @model_validator(mode="after")
    def validate_adoption(self) -> Self:
        if len(self.strategy_ids) != len(set(self.strategy_ids)):
            raise ValueError("ScaleEvidenceAdoption strategy_id 不能重复")
        if self.candidate_count != self.expected_candidate_count:
            raise ValueError("历史 scale evidence candidate 数量不完整")
        return self
