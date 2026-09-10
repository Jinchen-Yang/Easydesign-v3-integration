"""Versioned first-pilot and scale arithmetic contracts."""

from __future__ import annotations

import math
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from easydesign.core import ConfigurationError

FIRST_PILOT_PROTOCOL_ID = "first-pilot-vhh7-40-v1"
FIRST_PILOT_SCAFFOLD_COUNT = 7
FIRST_PILOT_CANDIDATES_PER_SCAFFOLD = 40
FIRST_PILOT_CANDIDATES_PER_CONDITION = 280
DEFAULT_SCALE_CANDIDATE_COUNT = 50_000
SCALE_SHARD_SIZE: Literal[2500] = 2_500


class ExperimentalCondition(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    condition_id: str = Field(min_length=1)
    scaffold_ids: tuple[str, ...]
    candidates_per_scaffold: int = Field(ge=1)


class FirstPilotProtocolSummary(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    protocol_id: str = FIRST_PILOT_PROTOCOL_ID
    experimental_condition_ids: tuple[str, ...]
    experimental_condition_count: int = Field(ge=1)
    scaffold_count_per_condition: int = FIRST_PILOT_SCAFFOLD_COUNT
    candidates_per_scaffold: int = FIRST_PILOT_CANDIDATES_PER_SCAFFOLD
    candidates_per_condition: int = FIRST_PILOT_CANDIDATES_PER_CONDITION
    total_candidates: int = Field(ge=FIRST_PILOT_CANDIDATES_PER_CONDITION)


class StrategyAllocation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    strategy_id: str = Field(min_length=1)
    candidate_count: int = Field(ge=0)
    shard_count: int = Field(ge=0)


class ScaleProtocolSummary(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    profile: str = "user-defined-v1"
    total_candidate_count: int = Field(ge=1)
    default_candidate_count: int = DEFAULT_SCALE_CANDIDATE_COUNT
    allocation_policy: str = "equal-across-promoted-v1"
    shard_size: Literal[2500] = SCALE_SHARD_SIZE
    total_shards: int = Field(ge=1)
    allocation: tuple[StrategyAllocation, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_exact_totals(self) -> Self:
        if sum(item.candidate_count for item in self.allocation) != self.total_candidate_count:
            raise ValueError("scale allocation 必须精确等于 total candidate count")
        expected_shards = tuple(
            math.ceil(item.candidate_count / self.shard_size)
            for item in self.allocation
        )
        if tuple(item.shard_count for item in self.allocation) != expected_shards:
            raise ValueError("scale shard count 与 exact allocation 不一致")
        if sum(expected_shards) != self.total_shards:
            raise ValueError("scale total_shards 与 allocation 不一致")
        return self


def validate_first_pilot_protocol(
    *,
    conditions: tuple[ExperimentalCondition, ...],
    official_scaffold_ids: tuple[str, ...],
) -> FirstPilotProtocolSummary:
    """Require every explicitly frozen first-pilot condition to be 7 × 40."""

    if (
        len(official_scaffold_ids) != FIRST_PILOT_SCAFFOLD_COUNT
        or len(set(official_scaffold_ids)) != FIRST_PILOT_SCAFFOLD_COUNT
    ):
        raise ConfigurationError(
            "official-vhh7-v1 registry 必须精确包含 7 个唯一 scaffold"
        )
    if not conditions:
        raise ConfigurationError("first pilot 必须显式冻结至少一个实验 condition")
    identifiers = [condition.condition_id for condition in conditions]
    if len(identifiers) != len(set(identifiers)):
        raise ConfigurationError("first-pilot condition identity 不能重复")
    official = set(official_scaffold_ids)
    for condition in conditions:
        if (
            len(condition.scaffold_ids) != FIRST_PILOT_SCAFFOLD_COUNT
            or set(condition.scaffold_ids) != official
        ):
            missing = sorted(official - set(condition.scaffold_ids))
            extra = sorted(set(condition.scaffold_ids) - official)
            raise ConfigurationError(
                "每个 first-pilot condition 缺少 official-vhh7-v1 scaffold 或包含额外项；"
                f"condition={condition.condition_id}, missing={missing}, extra={extra}"
            )
        if condition.candidates_per_scaffold != FIRST_PILOT_CANDIDATES_PER_SCAFFOLD:
            raise ConfigurationError(
                "每个 first-pilot condition 的每个 scaffold 必须生成 40 candidates（恰好）；"
                f"condition={condition.condition_id}, "
                f"actual={condition.candidates_per_scaffold}"
            )
    count = len(conditions)
    return FirstPilotProtocolSummary(
        experimental_condition_ids=tuple(identifiers),
        experimental_condition_count=count,
        total_candidates=FIRST_PILOT_CANDIDATES_PER_CONDITION * count,
    )


def scale_protocol_summary(
    *,
    total_candidate_count: int,
    strategy_ids: tuple[str, ...],
) -> ScaleProtocolSummary:
    """Build the exact equal allocation for any positive user scale count."""

    if total_candidate_count < 1:
        raise ConfigurationError("scale count 必须为正整数")
    if not strategy_ids or len(strategy_ids) != len(set(strategy_ids)):
        raise ConfigurationError("scale strategy IDs 必须非空且唯一")
    quotient, remainder = divmod(total_candidate_count, len(strategy_ids))
    allocation = tuple(
        StrategyAllocation(
            strategy_id=strategy_id,
            candidate_count=quotient + (1 if index < remainder else 0),
            shard_count=math.ceil(
                (quotient + (1 if index < remainder else 0)) / SCALE_SHARD_SIZE
            ),
        )
        for index, strategy_id in enumerate(strategy_ids)
    )
    return ScaleProtocolSummary(
        total_candidate_count=total_candidate_count,
        total_shards=sum(item.shard_count for item in allocation),
        allocation=allocation,
    )


__all__ = [
    "DEFAULT_SCALE_CANDIDATE_COUNT",
    "FIRST_PILOT_CANDIDATES_PER_CONDITION",
    "FIRST_PILOT_CANDIDATES_PER_SCAFFOLD",
    "FIRST_PILOT_PROTOCOL_ID",
    "FIRST_PILOT_SCAFFOLD_COUNT",
    "SCALE_SHARD_SIZE",
    "ExperimentalCondition",
    "FirstPilotProtocolSummary",
    "ScaleProtocolSummary",
    "StrategyAllocation",
    "scale_protocol_summary",
    "validate_first_pilot_protocol",
]
