"""Stage 04 pilot plan、candidate lineage 与 bundle 契约。"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from easydesign.core import ArtifactRef, ProgressSnapshot, TaskRecord
from easydesign.core.artifacts import ID_PATTERN, SHA256_PATTERN

MetricValue = bool | int | float | str | None


class PilotBackendParameters(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    protocol: Literal["nanobody-anything"] = "nanobody-anything"
    inverse_fold_num_sequences: Literal[1] = 1
    checkpoint_policy: Literal["boltzgen-0.3.2-default-pair"] = "boltzgen-0.3.2-default-pair"
    budget: Literal[30] = 30
    alpha: float = Field(default=0.001, ge=0, le=1)
    filter_biased: Literal[True] = True
    random_seed_status: Literal["unsupported-by-boltzgen-0.3.2"] = "unsupported-by-boltzgen-0.3.2"

    @model_validator(mode="after")
    def validate_alpha(self) -> Self:
        if self.alpha != 0.001:
            raise ValueError("Stage 04 v0.1 alpha 固定为 0.001")
        return self


class PilotStrategyPlan(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    task_id: str = Field(pattern=ID_PATTERN)
    strategy_id: str = Field(pattern=ID_PATTERN)
    design_specification: ArtifactRef
    required_complete_candidates: int = Field(ge=1)


class PilotPlan(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["0.1"] = "0.1"
    generated_at: datetime
    strategy_bundle_sha256: str = Field(pattern=SHA256_PATTERN)
    backend: Literal["boltzgen-0.3.2"] = "boltzgen-0.3.2"
    executor: Literal["local-multi-gpu"] = "local-multi-gpu"
    devices: tuple[int, ...] = Field(min_length=1)
    workers_per_device: Literal[1] = 1
    parameters: PilotBackendParameters = PilotBackendParameters()
    strategies: tuple[PilotStrategyPlan, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_plan(self) -> Self:
        task_ids = [item.task_id for item in self.strategies]
        strategy_ids = [item.strategy_id for item in self.strategies]
        if len(task_ids) != len(set(task_ids)):
            raise ValueError("PilotPlan task_id 不能重复")
        if len(strategy_ids) != len(set(strategy_ids)):
            raise ValueError("PilotPlan strategy_id 不能重复")
        if len(self.devices) != len(set(self.devices)):
            raise ValueError("PilotPlan device 不能重复")
        return self


class CandidateRecord(BaseModel):
    """一个完整、可评估且能回溯到 task attempt 的候选。"""

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    candidate_id: str = Field(pattern=ID_PATTERN)
    backend_candidate_id: str = Field(min_length=1, max_length=512)
    strategy_id: str = Field(pattern=ID_PATTERN)
    task_id: str = Field(pattern=ID_PATTERN)
    task_attempt_number: int = Field(ge=1)
    ordinal_within_strategy: int = Field(ge=1)
    original_structure: ArtifactRef
    refolded_structure: ArtifactRef
    design_mask_source: ArtifactRef | None = None
    designed_binder_residue_ids: tuple[int, ...] = ()
    metrics: dict[str, MetricValue]
    pass_filters: bool | None = None

    @model_validator(mode="before")
    @classmethod
    def reject_nested_metrics(cls, value: Any) -> Any:
        if isinstance(value, dict):
            metrics = value.get("metrics")
            if isinstance(metrics, dict) and any(
                isinstance(item, (dict, list, tuple)) for item in metrics.values()
            ):
                raise ValueError("CandidateRecord metrics 只接受 JSON scalar")
        return value

    @model_validator(mode="after")
    def validate_design_mask_evidence(self) -> Self:
        has_source = self.design_mask_source is not None
        has_residues = bool(self.designed_binder_residue_ids)
        if has_source != has_residues:
            raise ValueError("design mask source 与 designed residue identity 必须同时存在")
        if self.designed_binder_residue_ids and (
            tuple(sorted(set(self.designed_binder_residue_ids))) != self.designed_binder_residue_ids
        ):
            raise ValueError("designed_binder_residue_ids 必须升序且唯一")
        return self


class CandidateIndex(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["0.1", "0.2"] = "0.1"
    generated_at: datetime
    strategy_bundle_sha256: str = Field(pattern=SHA256_PATTERN)
    required_per_strategy: int = Field(ge=1)
    required_by_strategy: dict[str, int] | None = None
    candidates: tuple[CandidateRecord, ...]

    @model_validator(mode="after")
    def validate_candidates(self) -> Self:
        candidate_ids = [candidate.candidate_id for candidate in self.candidates]
        if len(candidate_ids) != len(set(candidate_ids)):
            raise ValueError("CandidateIndex candidate_id 不能重复")
        backend_identity = [
            (
                candidate.strategy_id,
                candidate.task_id,
                candidate.task_attempt_number,
                candidate.backend_candidate_id,
            )
            for candidate in self.candidates
        ]
        if len(backend_identity) != len(set(backend_identity)):
            raise ValueError("CandidateIndex backend candidate lineage 不能重复")
        per_strategy: dict[str, list[int]] = {}
        for candidate in self.candidates:
            per_strategy.setdefault(candidate.strategy_id, []).append(
                candidate.ordinal_within_strategy
            )
        for strategy_id, ordinals in per_strategy.items():
            if sorted(ordinals) != list(range(1, len(ordinals) + 1)):
                raise ValueError(f"{strategy_id} ordinal_within_strategy 必须连续")
            required = (
                self.required_per_strategy
                if self.required_by_strategy is None
                else self.required_by_strategy.get(strategy_id)
            )
            if required is None or len(ordinals) != required:
                raise ValueError(f"{strategy_id} 未达到 required candidates={required}")
        if self.required_by_strategy is not None:
            if self.schema_version != "0.2":
                raise ValueError("required_by_strategy 只属于 CandidateIndex 0.2")
            if set(self.required_by_strategy) != set(per_strategy):
                raise ValueError("required_by_strategy 必须精确覆盖 candidate strategies")
            if any(value < 1 for value in self.required_by_strategy.values()):
                raise ValueError("required_by_strategy budget 必须为正整数")
        return self


class PilotBundle(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["0.1", "0.2"] = "0.1"
    generated_at: datetime
    strategy_bundle: ArtifactRef
    pilot_plan: ArtifactRef
    task_table: ArtifactRef
    candidate_index: ArtifactRef
    progress_final: ArtifactRef
    task_events: ArtifactRef
    backend_environment: ArtifactRef
    strategy_count: int = Field(ge=1)
    complete_candidate_count: int = Field(ge=1)
    complete_candidates_per_strategy: int = Field(ge=1)
    complete_candidates_by_strategy: dict[str, int] | None = None
    status: Literal["succeeded"] = "succeeded"

    @model_validator(mode="after")
    def validate_count(self) -> Self:
        expected = (
            self.strategy_count * self.complete_candidates_per_strategy
            if self.complete_candidates_by_strategy is None
            else sum(self.complete_candidates_by_strategy.values())
        )
        if self.complete_candidate_count != expected:
            raise ValueError("PilotBundle complete candidate 总数不一致")
        if self.complete_candidates_by_strategy is not None:
            if self.schema_version != "0.2":
                raise ValueError("variable pilot budget 只属于 PilotBundle 0.2")
            if len(self.complete_candidates_by_strategy) != self.strategy_count:
                raise ValueError("variable pilot budget 必须覆盖全部 strategy")
            if any(value < 1 for value in self.complete_candidates_by_strategy.values()):
                raise ValueError("variable pilot budget 必须为正整数")
        return self


class TaskTable(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["0.1"] = "0.1"
    generated_at: datetime
    tasks: tuple[TaskRecord, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_tasks(self) -> Self:
        task_ids = [task.task_id for task in self.tasks]
        strategies = [task.strategy_id for task in self.tasks]
        if len(task_ids) != len(set(task_ids)):
            raise ValueError("TaskTable task_id 不能重复")
        if len(strategies) != len(set(strategies)):
            raise ValueError("TaskTable strategy_id 不能重复")
        return self


class PilotExecutionState(BaseModel):
    """运行中的可恢复快照；终态由 TaskTable/PilotBundle 固化。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["0.1"] = "0.1"
    created_at: datetime
    updated_at: datetime
    plan_sha256: str = Field(pattern=SHA256_PATTERN)
    tasks: tuple[TaskRecord, ...] = Field(min_length=1)
    candidates: tuple[CandidateRecord, ...] = ()
    progress: ProgressSnapshot
