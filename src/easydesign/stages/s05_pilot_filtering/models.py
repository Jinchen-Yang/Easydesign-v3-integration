"""Nanobody Filter Standard v1.5 的机器契约。"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from easydesign.backends.structure_prediction.contracts import TargetStructureCondition
from easydesign.core import ArtifactRef, ProgressSnapshot, TaskRecord
from easydesign.core.artifacts import ID_PATTERN, SHA256_PATTERN
from easydesign.stages.s04_pilot_generation import CandidateRecord


class StrategyTier(StrEnum):
    A = "tier-a"
    B = "tier-b"
    C = "tier-c"
    D = "tier-d"


class ScientificStopCode(StrEnum):
    NO_TIER_A = "stopped-no-tier-a"
    NO_SCALE_WINNER = "stopped-no-scale-winner"
    NO_FINAL_CANDIDATE = "stopped-no-final-candidate"


class FilterMetric(BaseModel):
    """一个有定义、单位和来源的候选指标。"""

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    metric_id: str = Field(pattern=ID_PATTERN)
    value: float | int | bool | str | None
    unit: str | None = Field(default=None, max_length=64)
    source: Literal["boltzgen", "easydesign-structure", "derived"]
    definition_version: str = Field(min_length=1, max_length=64)
    available: bool = True
    missing_reason: str | None = Field(default=None, max_length=1024)

    @model_validator(mode="after")
    def validate_availability(self) -> Self:
        if self.available:
            if self.value is None or self.missing_reason is not None:
                raise ValueError("available metric 必须有值且不能有 missing_reason")
        elif self.value is not None or self.missing_reason is None:
            raise ValueError("unavailable metric 必须无值并声明 missing_reason")
        return self


class FilterDecision(BaseModel):
    """一个硬门或去重规则的逐候选处置。"""

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    rule_id: str = Field(pattern=ID_PATTERN)
    metric_id: str = Field(pattern=ID_PATTERN)
    operator: Literal["eq", "ge", "le", "unique"]
    threshold: float | int | bool | str
    observed: float | int | bool | str | None
    passed: bool
    reason: str = Field(min_length=1, max_length=1024)


class CandidateFilterRecord(BaseModel):
    """Stage 04 candidate 的完整 pilot 筛选审计记录。"""

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    schema_version: Literal["0.1"] = "0.1"
    candidate_id: str = Field(pattern=ID_PATTERN)
    strategy_id: str = Field(pattern=ID_PATTERN)
    sequence: str = Field(pattern=r"^[ACDEFGHIKLMNPQRSTVWY]+$")
    sequence_sha256: str = Field(pattern=SHA256_PATTERN)
    metrics: tuple[FilterMetric, ...]
    hard_gate_decisions: tuple[FilterDecision, ...]
    hard_gate_pass: bool
    duplicate_of: str | None = Field(default=None, pattern=ID_PATTERN)
    eligible_unique_pass: bool
    score_screen: float = Field(ge=0, le=1)
    normalization_group: str = Field(pattern=ID_PATTERN)

    @model_validator(mode="after")
    def validate_record(self) -> Self:
        metric_ids = [metric.metric_id for metric in self.metrics]
        if len(metric_ids) != len(set(metric_ids)):
            raise ValueError("candidate metric_id 不能重复")
        rule_ids = [decision.rule_id for decision in self.hard_gate_decisions]
        if len(rule_ids) != len(set(rule_ids)):
            raise ValueError("candidate rule_id 不能重复")
        if self.hard_gate_pass != all(
            decision.passed
            for decision in self.hard_gate_decisions
            if decision.operator != "unique"
        ):
            raise ValueError("hard_gate_pass 与逐规则结果不一致")
        expected_eligible = self.hard_gate_pass and self.duplicate_of is None
        if self.eligible_unique_pass != expected_eligible:
            raise ValueError("eligible_unique_pass 与 hard gate/去重结果不一致")
        return self


class StrategyFilterSummary(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    strategy_id: str = Field(pattern=ID_PATTERN)
    candidate_count: int = Field(ge=1)
    unique_sequence_count: int = Field(ge=1)
    boltzgen_hard_pass_count: int = Field(ge=0)
    final_gate_pass_count: int = Field(ge=0)
    final_gate_pass_rate: float = Field(ge=0, le=1)
    score_screen_top_quartile_mean: float = Field(ge=0, le=1)
    score_screen_all_median: float = Field(ge=0, le=1)
    score_yaml: float = Field(ge=0, le=1)
    tier: StrategyTier
    selected_for_expansion: bool = False

    @model_validator(mode="after")
    def validate_counts(self) -> Self:
        if self.unique_sequence_count > self.candidate_count:
            raise ValueError("unique sequence 数不能超过 candidate 数")
        if self.boltzgen_hard_pass_count > self.unique_sequence_count:
            raise ValueError("BoltzGen hard-pass 数不能超过 unique sequence 数")
        if self.final_gate_pass_count > self.unique_sequence_count:
            raise ValueError("final gate 数不能超过 unique sequence 数")
        expected_tier = (
            StrategyTier.A
            if self.final_gate_pass_count >= 2
            else (
                StrategyTier.B
                if self.final_gate_pass_count == 1
                else (
                    StrategyTier.C
                    if self.boltzgen_hard_pass_count >= 2
                    else StrategyTier.D
                )
            )
        )
        if self.tier is not expected_tier:
            raise ValueError("strategy tier 与通过数不一致")
        if self.selected_for_expansion and self.tier is not StrategyTier.A:
            raise ValueError("只有 Tier A strategy 可以进入扩展")
        return self


class PilotFilterReport(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    schema_version: Literal["0.1"] = "0.1"
    generated_at: datetime
    profile_id: Literal["nanobody-filter-standard-v1.5"] = (
        "nanobody-filter-standard-v1.5"
    )
    profile_sha256: str = Field(pattern=SHA256_PATTERN)
    candidate_index_sha256: str = Field(pattern=SHA256_PATTERN)
    candidate_records: tuple[CandidateFilterRecord, ...] = Field(min_length=1)
    strategy_summaries: tuple[StrategyFilterSummary, ...] = Field(min_length=1)
    selected_strategy_ids: tuple[str, ...] = ()
    status: Literal["tier-a-selected", "stopped-no-tier-a"]

    @model_validator(mode="after")
    def validate_report(self) -> Self:
        candidate_ids = [record.candidate_id for record in self.candidate_records]
        strategy_ids = [summary.strategy_id for summary in self.strategy_summaries]
        if len(candidate_ids) != len(set(candidate_ids)):
            raise ValueError("PilotFilterReport candidate_id 不能重复")
        if len(strategy_ids) != len(set(strategy_ids)):
            raise ValueError("PilotFilterReport strategy_id 不能重复")
        selected = tuple(
            summary.strategy_id
            for summary in self.strategy_summaries
            if summary.selected_for_expansion
        )
        if self.selected_strategy_ids != selected:
            raise ValueError("selected_strategy_ids 与 strategy summary 不一致")
        if self.status == "stopped-no-tier-a" and selected:
            raise ValueError("scientific stop 不得包含扩展 strategy")
        if self.status == "tier-a-selected" and not selected:
            raise ValueError("tier-a-selected 必须包含 strategy")
        return self


class PilotFilterReportV1_6(BaseModel):
    """v1.6 pilot report; gates stay identical while promotion semantics change."""

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    schema_version: Literal["0.2"] = "0.2"
    generated_at: datetime
    profile_id: Literal[
        "nanobody-filter-standard-v1.6",
        "nanobody-filter-standard-v1.7",
    ] = (
        "nanobody-filter-standard-v1.6"
    )
    profile_sha256: str = Field(pattern=SHA256_PATTERN)
    candidate_index_sha256: str = Field(pattern=SHA256_PATTERN)
    candidate_records: tuple[CandidateFilterRecord, ...] = Field(min_length=1)
    strategy_summaries: tuple[StrategyFilterSummary, ...] = Field(min_length=1)
    promoted_strategy_ids: tuple[str, ...] = Field(max_length=3)
    status: Literal["strategies-promoted", "stopped-no-tier-a"]

    @model_validator(mode="after")
    def validate_report(self) -> Self:
        candidate_ids = [record.candidate_id for record in self.candidate_records]
        strategy_ids = [summary.strategy_id for summary in self.strategy_summaries]
        if len(candidate_ids) != len(set(candidate_ids)):
            raise ValueError("PilotFilterReportV1_6 candidate_id 不能重复")
        if len(strategy_ids) != len(set(strategy_ids)):
            raise ValueError("PilotFilterReportV1_6 strategy_id 不能重复")
        selected = tuple(
            summary.strategy_id
            for summary in sorted(
                (
                    summary
                    for summary in self.strategy_summaries
                    if summary.selected_for_expansion
                ),
                key=lambda summary: (-summary.score_yaml, summary.strategy_id),
            )
        )
        if self.promoted_strategy_ids != selected:
            raise ValueError("promoted_strategy_ids 必须按 F_YAML 排名覆盖 Tier A")
        if self.status == "stopped-no-tier-a" and selected:
            raise ValueError("scientific stop 不得包含 promoted strategy")
        if self.status == "strategies-promoted" and not selected:
            raise ValueError("strategies-promoted 必须包含 Tier A strategy")
        return self


class ScientificStop(BaseModel):
    """成功执行得到的科学负结果，不是 operational failure。"""

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    schema_version: Literal["0.1"] = "0.1"
    stage_id: str = Field(pattern=r"^0[1-7]-[a-z0-9-]+$")
    code: ScientificStopCode
    occurred_at: datetime
    message: str = Field(min_length=1, max_length=4096)
    evidence_artifact_sha256: tuple[str, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_hashes(self) -> Self:
        for value in self.evidence_artifact_sha256:
            if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
                raise ValueError("scientific stop evidence 必须是 SHA-256")
        return self


class ExpansionCandidateRecord(BaseModel):
    """One candidate in a selected strategy's 100-candidate local evaluation."""

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    candidate_id: str = Field(pattern=ID_PATTERN)
    strategy_id: str = Field(pattern=ID_PATTERN)
    sequence: str = Field(pattern=r"^[ACDEFGHIKLMNPQRSTVWY]+$")
    sequence_sha256: str = Field(pattern=SHA256_PATTERN)
    local_gate_decisions: tuple[FilterDecision, ...]
    local_gate_pass: bool
    score_expand_structure: float = Field(ge=0, le=1)
    selected_for_full_target: bool = False

    @model_validator(mode="after")
    def validate_gate(self) -> Self:
        if self.local_gate_pass != all(
            decision.passed for decision in self.local_gate_decisions
        ):
            raise ValueError("local_gate_pass 与逐规则结果不一致")
        if self.selected_for_full_target and not self.local_gate_pass:
            raise ValueError("失败候选不能进入 full-target prediction")
        return self


class FullTargetPredictionRecord(BaseModel):
    """Stage 05 model-neutral target+binder result and structural gate audit."""

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    candidate_id: str = Field(pattern=ID_PATTERN)
    strategy_id: str = Field(pattern=ID_PATTERN)
    seed: Literal[101] = 101
    samples_per_seed: int = Field(default=1, ge=1)
    recycles: int = Field(default=10, ge=1)
    scientific_mode: Literal["de-novo", "target-conditioned"] = "de-novo"
    template_mode: Literal["disabled", "precomputed"] = "disabled"
    screening_profile_id: Literal[
        "nanobody-filter-standard-v1.7",
        "target-conditioned-evidence-v1",
    ] = "nanobody-filter-standard-v1.7"
    target_condition_sha256: str | None = Field(default=None, pattern=SHA256_PATTERN)
    target_condition_source_origin: Literal[
        "experimental", "imported", "predicted"
    ] | None = None
    target_condition_self_conditioned: bool = False
    parameter_profile: Literal["model-default"] = "model-default"
    msa_provider: str = "precomputed"
    msa_endpoint: str | None = None
    target_unpaired_msa_mode: Literal["disabled", "remote", "precomputed"] = (
        "precomputed"
    )
    target_paired_msa_mode: Literal["disabled", "remote", "precomputed"] = (
        "precomputed"
    )
    binder_unpaired_msa_mode: Literal["disabled", "remote", "precomputed"] = (
        "precomputed"
    )
    binder_paired_msa_mode: Literal["disabled", "remote", "precomputed"] = (
        "precomputed"
    )
    target_template_data_sha256: str | None = Field(
        default=None,
        pattern=SHA256_PATTERN,
    )
    binder_template_data_sha256: str | None = Field(
        default=None,
        pattern=SHA256_PATTERN,
    )
    backend_identity: str = "protenix-v2@2.0.0"
    model_identity: str = "protenix-v2"
    confidence_metric_definition_version: str = (
        "protenix-v2-complex-confidence-v1"
    )
    raw_checkpoint_sha256: str | None = Field(default=None, pattern=SHA256_PATTERN)
    converted_weight_sha256: str | None = Field(default=None, pattern=SHA256_PATTERN)
    wheel_sha256: str | None = Field(default=None, pattern=SHA256_PATTERN)
    runner_commit: str | None = None
    release_identity: dict[str, str] = Field(default_factory=dict)
    predicted_structure: ArtifactRef
    summary_confidence: ArtifactRef
    full_confidence: ArtifactRef
    pairwise_iptm: float
    minimum_interface_pae_angstrom: float = Field(ge=0)
    binder_ptm: float
    binder_pose_rmsd_angstrom: float = Field(ge=0)
    target_ca_rmsd_angstrom: float = Field(ge=0)
    severe_clash_count: int = Field(ge=0)
    moderate_clash_count: int = Field(ge=0)
    structure_gate_decisions: tuple[FilterDecision, ...]
    structure_gate_pass: bool
    confidence_reference_pass: bool
    confidence_label: Literal["reference-supported", "low-confidence"]

    @model_validator(mode="after")
    def validate_gate(self) -> Self:
        if (self.target_condition_sha256 is None) != (
            self.target_condition_source_origin is None
        ):
            raise ValueError("target condition SHA/source origin 必须同时存在或缺失")
        if self.target_condition_self_conditioned and self.target_condition_sha256 is None:
            raise ValueError("self-conditioned prediction 必须记录 condition identity")
        if self.backend_identity.startswith("openfold3-af3-jax@") and len(
            self.release_identity
        ) != 13:
            raise ValueError("AFO full-target record 缺少完整 release identity")
        if self.structure_gate_pass != all(
            decision.passed for decision in self.structure_gate_decisions
        ):
            raise ValueError("full-target structure gate 与逐规则结果不一致")
        expected = (
            "reference-supported"
            if self.confidence_reference_pass
            else "low-confidence"
        )
        if self.confidence_label != expected:
            raise ValueError("confidence label 与 reference 指标不一致")
        return self


class StrategyExpansionSummary(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    strategy_id: str = Field(pattern=ID_PATTERN)
    complete_candidate_count: int = Field(ge=1)
    local_gate_pass_count: int = Field(ge=0)
    selected_for_full_target_count: int = Field(ge=0)
    full_target_pass_count: int = Field(ge=0)
    full_target_pass_rate: float = Field(ge=0, le=1)
    median_passing_binder_pose_rmsd_angstrom: float | None = Field(
        default=None,
        ge=0,
    )
    mean_selected_score_expand_structure: float = Field(ge=0, le=1)
    eligible_for_scale: bool
    winner: bool = False

    @model_validator(mode="after")
    def validate_counts(self) -> Self:
        if self.local_gate_pass_count > self.complete_candidate_count:
            raise ValueError("local gate 通过数不能超过完整候选数")
        if self.selected_for_full_target_count > self.local_gate_pass_count:
            raise ValueError("full-target 选择数不能超过 local gate 通过数")
        if self.full_target_pass_count > self.selected_for_full_target_count:
            raise ValueError("full-target 通过数不能超过预测数")
        if self.eligible_for_scale != (self.full_target_pass_count >= 1):
            raise ValueError("scale eligibility 必须等于至少一个 full-target pass")
        if self.winner and not self.eligible_for_scale:
            raise ValueError("winner 必须通过 full-target validation")
        return self


class ExpansionValidationReport(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    schema_version: Literal["0.1"] = "0.1"
    generated_at: datetime
    expanded_total_per_strategy: int = Field(ge=1)
    full_target_refold_top_n: int = Field(ge=1)
    candidates: tuple[ExpansionCandidateRecord, ...] = Field(min_length=1)
    predictions: tuple[FullTargetPredictionRecord, ...]
    strategies: tuple[StrategyExpansionSummary, ...] = Field(min_length=1)
    winner_strategy_id: str | None = Field(default=None, pattern=ID_PATTERN)
    status: Literal["winner-selected", "stopped-no-scale-winner"]

    @model_validator(mode="after")
    def validate_winner(self) -> Self:
        winners = tuple(item.strategy_id for item in self.strategies if item.winner)
        if self.status == "winner-selected":
            if len(winners) != 1 or self.winner_strategy_id != winners[0]:
                raise ValueError("winner-selected 必须且只能声明一个 winner")
        elif winners or self.winner_strategy_id is not None:
            raise ValueError("scientific stop 不得声明 winner")
        return self


class Stage05Bundle(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    schema_version: Literal["0.1"] = "0.1"
    generated_at: datetime
    pilot_bundle: ArtifactRef
    strategy_bundle: ArtifactRef
    filter_profile: ArtifactRef
    pilot_filter_report: ArtifactRef
    expansion_candidate_index: ArtifactRef | None = None
    expansion_validation_report: ArtifactRef | None = None
    target_conditioned_evidence: ArtifactRef | None = None
    progress_final: ArtifactRef
    task_events: ArtifactRef
    scientific_stop: ArtifactRef | None = None
    winner_strategy_id: str | None = Field(default=None, pattern=ID_PATTERN)
    status: Literal[
        "winner-selected",
        "stopped-no-tier-a",
        "stopped-no-scale-winner",
    ]

    @model_validator(mode="after")
    def validate_status(self) -> Self:
        if self.status == "winner-selected":
            if (
                self.winner_strategy_id is None
                or self.expansion_candidate_index is None
                or self.expansion_validation_report is None
                or self.scientific_stop is not None
            ):
                raise ValueError("winner-selected Stage05Bundle artifact 不完整")
        elif self.status == "stopped-no-tier-a":
            if (
                self.scientific_stop is None
                or self.winner_strategy_id is not None
                or self.expansion_candidate_index is not None
                or self.expansion_validation_report is not None
            ):
                raise ValueError("stopped-no-tier-a 不得伪造 expansion artifact")
        elif (
            self.scientific_stop is None
            or self.winner_strategy_id is not None
            or self.expansion_candidate_index is None
            or self.expansion_validation_report is None
        ):
            raise ValueError(
                "stopped-no-scale-winner 必须保留完整 expansion evidence 且不得有 winner"
            )
        return self


class Stage05Warning(BaseModel):
    """A non-blocking scientific warning produced by v1.6 diagnostics."""

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    warning_id: str = Field(pattern=ID_PATTERN)
    strategy_id: str = Field(pattern=ID_PATTERN)
    code: Literal[
        "full-target-structure-gate-zero-pass",
        "full-target-confidence-low",
    ]
    message: str = Field(min_length=1, max_length=4096)
    evidence_candidate_ids: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_candidate_ids(self) -> Self:
        if len(self.evidence_candidate_ids) != len(set(self.evidence_candidate_ids)):
            raise ValueError("warning evidence candidate_id 不能重复")
        for candidate_id in self.evidence_candidate_ids:
            if not candidate_id:
                raise ValueError("warning evidence candidate_id 不能为空")
        return self


class StrategyPromotionRecord(BaseModel):
    """Tier A promotion fixed before the diagnostic 100-candidate expansion."""

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    strategy_id: str = Field(pattern=ID_PATTERN)
    promotion_rank: int = Field(ge=1, le=3)
    score_yaml: float = Field(ge=0, le=1)
    pilot_candidate_count: int = Field(ge=1)
    unique_sequence_count: int = Field(ge=1)
    boltzgen_hard_pass_count: int = Field(ge=0)
    final_gate_pass_count: int = Field(ge=2)
    final_gate_pass_rate: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def validate_counts(self) -> Self:
        if self.unique_sequence_count > self.pilot_candidate_count:
            raise ValueError("promotion unique sequence 数不能超过 pilot candidate 数")
        if self.boltzgen_hard_pass_count > self.unique_sequence_count:
            raise ValueError("promotion hard-pass 数不能超过 unique sequence 数")
        if self.final_gate_pass_count > self.unique_sequence_count:
            raise ValueError("promotion final-gate 数不能超过 unique sequence 数")
        expected_rate = self.final_gate_pass_count / self.pilot_candidate_count
        if abs(self.final_gate_pass_rate - expected_rate) > 1e-12:
            raise ValueError("promotion final-gate pass rate 与计数不一致")
        return self


class AdvisoryStrategySummary(BaseModel):
    """Diagnostic expansion evidence that never revokes Tier A promotion."""

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    strategy_id: str = Field(pattern=ID_PATTERN)
    promotion_rank: int = Field(ge=1, le=3)
    score_yaml: float = Field(ge=0, le=1)
    complete_candidate_count: int = Field(ge=1)
    local_gate_pass_count: int = Field(ge=0)
    selected_for_full_target_count: int = Field(ge=0)
    full_target_prediction_count: int = Field(ge=0)
    full_target_structure_pass_count: int = Field(ge=0)
    full_target_structure_pass_rate: float = Field(ge=0, le=1)
    minimum_binder_pose_rmsd_angstrom: float | None = Field(default=None, ge=0)
    median_binder_pose_rmsd_angstrom: float | None = Field(default=None, ge=0)
    mean_selected_score_expand_structure: float = Field(ge=0, le=1)
    advisory_status: Literal["advisory-supported", "advisory-warning"]

    @model_validator(mode="after")
    def validate_counts(self) -> Self:
        if self.local_gate_pass_count > self.complete_candidate_count:
            raise ValueError("advisory local-gate 数不能超过完整候选数")
        if self.selected_for_full_target_count > self.local_gate_pass_count:
            raise ValueError("advisory selected 数不能超过 local-gate 数")
        if self.full_target_prediction_count != self.selected_for_full_target_count:
            raise ValueError("diagnostic prediction 必须覆盖全部 selected candidate")
        if self.full_target_structure_pass_count > self.full_target_prediction_count:
            raise ValueError("advisory structure-pass 数不能超过 prediction 数")
        expected_rate = (
            self.full_target_structure_pass_count / self.full_target_prediction_count
            if self.full_target_prediction_count
            else 0.0
        )
        if abs(self.full_target_structure_pass_rate - expected_rate) > 1e-12:
            raise ValueError("advisory structure-pass rate 与计数不一致")
        expected_status = (
            "advisory-supported"
            if self.full_target_structure_pass_count > 0
            else "advisory-warning"
        )
        if self.advisory_status != expected_status:
            raise ValueError("advisory status 与 structure-pass 数不一致")
        if self.full_target_prediction_count == 0:
            if (
                self.minimum_binder_pose_rmsd_angstrom is not None
                or self.median_binder_pose_rmsd_angstrom is not None
            ):
                raise ValueError("无 prediction 时不能声明 binder pose RMSD")
        elif (
            self.minimum_binder_pose_rmsd_angstrom is None
            or self.median_binder_pose_rmsd_angstrom is None
        ):
            raise ValueError("有 prediction 时必须声明 binder pose RMSD 摘要")
        return self


class AdvisoryValidationReport(BaseModel):
    """Stage 05 v1.6 expansion evidence; scientific negatives are warnings."""

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    schema_version: Literal["0.2"] = "0.2"
    generated_at: datetime
    profile_id: Literal[
        "nanobody-filter-standard-v1.6",
        "nanobody-filter-standard-v1.7",
    ] = (
        "nanobody-filter-standard-v1.6"
    )
    expanded_total_per_strategy: int = Field(ge=1)
    full_target_refold_top_n: int = Field(ge=1)
    promoted_strategies: tuple[StrategyPromotionRecord, ...] = Field(
        min_length=1,
        max_length=3,
    )
    candidates: tuple[ExpansionCandidateRecord, ...] = Field(min_length=1)
    predictions: tuple[FullTargetPredictionRecord, ...]
    strategies: tuple[AdvisoryStrategySummary, ...] = Field(
        min_length=1,
        max_length=3,
    )
    warnings: tuple[Stage05Warning, ...] = ()
    status: Literal["diagnostics-complete"] = "diagnostics-complete"

    @model_validator(mode="after")
    def validate_report(self) -> Self:
        promoted_ids = tuple(item.strategy_id for item in self.promoted_strategies)
        summary_ids = tuple(item.strategy_id for item in self.strategies)
        if len(promoted_ids) != len(set(promoted_ids)):
            raise ValueError("promoted strategy_id 不能重复")
        if len(summary_ids) != len(set(summary_ids)):
            raise ValueError("advisory strategy_id 不能重复")
        if set(promoted_ids) != set(summary_ids):
            raise ValueError("advisory summary 必须精确覆盖 promoted strategy")
        ranks = tuple(item.promotion_rank for item in self.promoted_strategies)
        if ranks != tuple(range(1, len(ranks) + 1)):
            raise ValueError("promotion rank 必须按 1..N 连续排序")
        if tuple(item.strategy_id for item in self.promoted_strategies) != tuple(
            item.strategy_id
            for item in sorted(
                self.promoted_strategies,
                key=lambda item: item.promotion_rank,
            )
        ):
            raise ValueError("promoted strategy 必须按 promotion rank 排列")
        candidate_ids = [item.candidate_id for item in self.candidates]
        prediction_ids = [item.candidate_id for item in self.predictions]
        if len(candidate_ids) != len(set(candidate_ids)):
            raise ValueError("advisory candidate_id 不能重复")
        if len(prediction_ids) != len(set(prediction_ids)):
            raise ValueError("advisory prediction candidate_id 不能重复")
        if any(item.strategy_id not in promoted_ids for item in self.candidates):
            raise ValueError("advisory candidate 来自未晋级 strategy")
        if any(item.strategy_id not in promoted_ids for item in self.predictions):
            raise ValueError("advisory prediction 来自未晋级 strategy")
        warning_strategy_ids = {item.strategy_id for item in self.warnings}
        if not warning_strategy_ids.issubset(set(promoted_ids)):
            raise ValueError("warning 来自未晋级 strategy")
        expected_warning_ids = {
            item.strategy_id
            for item in self.strategies
            if item.advisory_status == "advisory-warning"
        }
        if not expected_warning_ids.issubset(warning_strategy_ids):
            raise ValueError("advisory-warning strategy 必须有结构化 warning")
        return self


class Stage05BundleV0_2(BaseModel):
    """v1.6 handoff: up to three Tier A strategies, never a single winner."""

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    schema_version: Literal["0.2"] = "0.2"
    generated_at: datetime
    pilot_bundle: ArtifactRef
    strategy_bundle: ArtifactRef
    filter_profile: ArtifactRef
    pilot_filter_report: ArtifactRef
    expansion_candidate_index: ArtifactRef | None = None
    advisory_validation_report: ArtifactRef | None = None
    target_conditioned_evidence: ArtifactRef | None = None
    progress_final: ArtifactRef
    task_events: ArtifactRef
    scientific_stop: ArtifactRef | None = None
    promoted_strategy_ids: tuple[str, ...] = Field(max_length=3)
    promotion_rank: tuple[StrategyPromotionRecord, ...] = Field(max_length=3)
    warnings: tuple[Stage05Warning, ...] = ()
    status: Literal["strategies-promoted", "stopped-no-tier-a"]

    @model_validator(mode="after")
    def validate_status(self) -> Self:
        promotion_ids = tuple(item.strategy_id for item in self.promotion_rank)
        if self.promoted_strategy_ids != promotion_ids:
            raise ValueError("promoted_strategy_ids 与 promotion rank 不一致")
        if self.status == "strategies-promoted":
            if (
                not self.promoted_strategy_ids
                or self.expansion_candidate_index is None
                or self.advisory_validation_report is None
                or self.scientific_stop is not None
            ):
                raise ValueError("strategies-promoted Stage05Bundle artifact 不完整")
        elif (
            self.promoted_strategy_ids
            or self.promotion_rank
            or self.expansion_candidate_index is not None
            or self.advisory_validation_report is not None
            or self.warnings
            or self.scientific_stop is None
        ):
            raise ValueError("stopped-no-tier-a 不得伪造 promotion/diagnostic evidence")
        return self


class ExpansionExecutionState(BaseModel):
    """Mutable-by-atomic-replace resume snapshot; terminal evidence is separate."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["0.1"] = "0.1"
    created_at: datetime
    updated_at: datetime
    strategy_bundle_sha256: str = Field(pattern=SHA256_PATTERN)
    tasks: tuple[TaskRecord, ...] = Field(min_length=1)
    new_candidates: tuple[CandidateRecord, ...] = ()
    progress: ProgressSnapshot


class FullTargetExecutionState(BaseModel):
    """Resumable Stage 05 Protenix candidate-validation state."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["0.1"] = "0.1"
    created_at: datetime
    updated_at: datetime
    target_msa_sha256: str = Field(pattern=SHA256_PATTERN)
    selected_candidate_ids: tuple[str, ...] = Field(min_length=1)
    scientific_mode: Literal["de-novo", "target-conditioned"] = "de-novo"
    target_condition_sha256: str | None = Field(default=None, pattern=SHA256_PATTERN)
    tasks: tuple[TaskRecord, ...] = Field(min_length=1)
    predictions: tuple[FullTargetPredictionRecord, ...] = ()
    progress: ProgressSnapshot

    @model_validator(mode="after")
    def validate_identity(self) -> Self:
        if (self.scientific_mode == "de-novo") != (
            self.target_condition_sha256 is None
        ):
            raise ValueError("full-target state scientific mode/condition 不一致")
        if len(self.selected_candidate_ids) != len(set(self.selected_candidate_ids)):
            raise ValueError("selected_candidate_ids 不能重复")
        task_ids = {task.strategy_id for task in self.tasks}
        if task_ids != set(self.selected_candidate_ids):
            raise ValueError("full-target task identity 与 selected candidate 不一致")
        prediction_ids = [item.candidate_id for item in self.predictions]
        if len(prediction_ids) != len(set(prediction_ids)):
            raise ValueError("full-target prediction identity 不能重复")
        if not set(prediction_ids).issubset(set(self.selected_candidate_ids)):
            raise ValueError("full-target prediction 不在选择集合")
        return self


class TargetConditionedStage05Evidence(BaseModel):
    """Advisory target-conditioned evidence; it cannot revoke de-novo gates."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["0.1"] = "0.1"
    generated_at: datetime
    screening_profile_id: Literal["target-conditioned-evidence-v1"] = (
        "target-conditioned-evidence-v1"
    )
    selection_authority: Literal["advisory-only"] = "advisory-only"
    target_condition: TargetStructureCondition
    predictions: tuple[FullTargetPredictionRecord, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_predictions(self) -> Self:
        if any(item.scientific_mode != "target-conditioned" for item in self.predictions):
            raise ValueError("conditioned evidence 含 de-novo prediction")
        if any(
            item.target_condition_sha256 != self.target_condition.template_data_sha256
            for item in self.predictions
        ):
            raise ValueError("conditioned evidence prediction/condition identity 不一致")
        return self
