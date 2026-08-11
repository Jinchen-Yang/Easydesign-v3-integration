"""Nanobody Final v1.5 audit records and human review-package contracts."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from easydesign.backends.structure_prediction.contracts import TargetStructureCondition
from easydesign.core import ArtifactRef, ProgressSnapshot, TaskRecord
from easydesign.core.artifacts import ID_PATTERN, SHA256_PATTERN
from easydesign.stages.s05_pilot_filtering import FilterDecision, FilterMetric


class DevelopabilityRisk(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class OperationalFailure(BaseModel):
    """Structured, retry-aware evidence for a failed Stage 07 execution call."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["0.1"] = "0.1"
    stage_id: Literal["07-final-filtering-and-selection"] = "07-final-filtering-and-selection"
    occurred_at: datetime
    code: str = Field(pattern=ID_PATTERN)
    error_type: str = Field(min_length=1, max_length=256)
    message: str = Field(min_length=1, max_length=4096)
    retryable: bool
    planned_tasks: int | None = Field(default=None, ge=0)
    completed_tasks: int | None = Field(default=None, ge=0)
    required_tool: str | None = Field(default=None, max_length=256)


class SequenceLiability(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    liability_id: str = Field(pattern=ID_PATTERN)
    name: str = Field(min_length=1, max_length=256)
    sequence_start: int = Field(ge=1)
    sequence_end: int = Field(ge=1)
    matched_sequence: str = Field(min_length=1)
    evidence_scope: Literal["full-sequence-warning", "tnp-cdr-or-vernier"]
    numbering: Literal["sequence", "imgt"] = "sequence"
    chain: str | None = Field(default=None, pattern=r"^[A-Za-z0-9]{1,4}$")
    numbering_label: str | None = Field(default=None, pattern=r"^[0-9]+[A-Za-z]?$")

    @model_validator(mode="after")
    def validate_range(self) -> Self:
        if self.sequence_end < self.sequence_start:
            raise ValueError("liability sequence range 倒置")
        if (
            self.numbering == "sequence"
            and len(self.matched_sequence) != self.sequence_end - self.sequence_start + 1
        ):
            raise ValueError("liability sequence range 与 motif 长度不一致")
        if self.numbering == "imgt" and self.chain is None:
            raise ValueError("IMGT liability 必须声明 chain")
        if self.numbering == "imgt" and self.numbering_label is None:
            raise ValueError("IMGT liability 必须保留含 insertion code 的 numbering label")
        if self.numbering == "sequence" and self.numbering_label is not None:
            raise ValueError("sequence-numbered liability 不得声明 IMGT numbering label")
        return self


class SequencePrefilterRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    candidate_id: str = Field(pattern=ID_PATTERN)
    strategy_id: str = Field(pattern=ID_PATTERN)
    sequence: str = Field(min_length=1)
    sequence_sha256: str = Field(pattern=SHA256_PATTERN)
    design_sequence: str = Field(min_length=1)
    unknown_residue_count: int = Field(ge=0)
    unpaired_new_cysteine_residue_ids: tuple[int, ...] = ()
    liabilities: tuple[SequenceLiability, ...] = ()
    duplicate_of: str | None = Field(default=None, pattern=ID_PATTERN)
    decisions: tuple[FilterDecision, ...]
    hard_pass: bool
    score_refold: float = Field(ge=0, le=1)
    selected_for_deep: bool = False

    @model_validator(mode="after")
    def validate_record(self) -> Self:
        if self.hard_pass != all(item.passed for item in self.decisions):
            raise ValueError("sequence prefilter hard_pass 与逐规则结果不一致")
        if self.selected_for_deep and not self.hard_pass:
            raise ValueError("sequence prefilter 失败候选不能进入 deep evaluation")
        return self


class DeepFilterRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    candidate_id: str = Field(pattern=ID_PATTERN)
    metrics: tuple[FilterMetric, ...]
    decisions: tuple[FilterDecision, ...]
    absolute_gate_pass: bool
    score_deep: float = Field(ge=0, le=1)
    selected_for_seed101: bool = False

    @model_validator(mode="after")
    def validate_record(self) -> Self:
        if self.absolute_gate_pass != all(
            item.passed for item in self.decisions if item.operator != "unique"
        ):
            raise ValueError("deep absolute gate 与逐规则结果不一致")
        if self.selected_for_seed101 and not self.absolute_gate_pass:
            raise ValueError("deep gate 失败候选不能进入 Protenix")
        return self


class FinalPredictionRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    candidate_id: str = Field(pattern=ID_PATTERN)
    seed: Literal[101, 202, 303, 404, 505]
    prediction_phase: str = "legacy-multi-seed"
    sample_index: int = Field(default=0, ge=0)
    samples_per_seed: int = Field(default=1, ge=1)
    recycles: int = Field(default=10, ge=1)
    template_mode: Literal["disabled"] = "disabled"
    parameter_profile: Literal["model-default"] = "model-default"
    msa_provider: str = "precomputed"
    msa_endpoint: str | None = None
    ranking_score: float = 0.0
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
    hotspot_coverage: float = Field(ge=0, le=1)
    contacted_hotspot_residue_ids: tuple[int, ...] = ()
    severe_clash_count: int = Field(ge=0)
    moderate_clash_count: int = Field(ge=0)
    metrics: tuple[FilterMetric, ...]
    seed101_gate_decisions: tuple[FilterDecision, ...]
    seed101_gate_pass: bool
    consensus_gate_decisions: tuple[FilterDecision, ...]
    consensus_seed_pass: bool
    score_full: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def validate_record(self) -> Self:
        if self.backend_identity.startswith("openfold3-af3-jax@") and len(
            self.release_identity
        ) != 13:
            raise ValueError("AFO final prediction 缺少完整 release identity")
        if self.seed101_gate_pass != all(item.passed for item in self.seed101_gate_decisions):
            raise ValueError("seed101 gate 与逐规则结果不一致")
        if self.consensus_seed_pass != all(item.passed for item in self.consensus_gate_decisions):
            raise ValueError("consensus seed gate 与逐规则结果不一致")
        if (
            tuple(sorted(set(self.contacted_hotspot_residue_ids)))
            != self.contacted_hotspot_residue_ids
        ):
            raise ValueError("contacted hotspot residue identity 必须升序唯一")
        return self


class RawFinalPrediction(BaseModel):
    """A complete model-neutral product before population-normalized S_full."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    candidate_id: str = Field(pattern=ID_PATTERN)
    seed: Literal[101, 202, 303, 404, 505]
    prediction_phase: str = "legacy-multi-seed"
    sample_index: int = Field(default=0, ge=0)
    samples_per_seed: int = Field(default=1, ge=1)
    recycles: int = Field(default=10, ge=1)
    scientific_mode: Literal["de-novo", "target-conditioned"] = "de-novo"
    template_mode: Literal["disabled", "precomputed"] = "disabled"
    screening_profile_id: Literal[
        "nanobody-final-v1.5",
        "nanobody-final-v1.6",
        "target-conditioned-evidence-v1",
    ] = "nanobody-final-v1.5"
    target_condition_sha256: str | None = Field(default=None, pattern=SHA256_PATTERN)
    target_condition_source_origin: Literal[
        "experimental", "imported", "predicted"
    ] | None = None
    target_condition_self_conditioned: bool = False
    parameter_profile: Literal["model-default"] = "model-default"
    msa_provider: str = "precomputed"
    msa_endpoint: str | None = None
    ranking_score: float = 0.0
    is_seed_representative: bool = True
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
    contacted_hotspot_residue_ids: tuple[int, ...] = ()
    hotspot_coverage: float = Field(ge=0, le=1)
    hotspot_count: int = Field(ge=1)
    binder_contact_coverage: float = Field(ge=0, le=1)
    cdr_dominance: float = Field(ge=0, le=1)
    cdr_utilization: float = Field(ge=0, le=1)
    residue_pair_contact_count: int = Field(ge=0)
    atom_contact_count: int = Field(ge=0)
    severe_clash_count: int = Field(ge=0)
    moderate_clash_count: int = Field(ge=0)
    hydrogen_bond_count: int = Field(ge=0)
    salt_bridge_count: int = Field(ge=0)
    polar_contact_fraction: float = Field(ge=0, le=1)
    interface_bsa_angstrom2: float = Field(ge=0)

    @model_validator(mode="after")
    def validate_contacts(self) -> Self:
        if self.scientific_mode == "de-novo":
            if (
                self.template_mode != "disabled"
                or self.target_condition_sha256 is not None
                or self.target_condition_source_origin is not None
                or self.target_condition_self_conditioned
            ):
                raise ValueError("de-novo raw prediction 不能声明 target condition")
        elif (
            self.template_mode != "precomputed"
            or self.screening_profile_id != "target-conditioned-evidence-v1"
            or self.target_condition_sha256 is None
            or self.target_condition_source_origin is None
        ):
            raise ValueError("target-conditioned raw prediction condition evidence 不完整")
        if self.backend_identity.startswith("openfold3-af3-jax@") and len(
            self.release_identity
        ) != 13:
            raise ValueError("AFO raw prediction 缺少完整 release identity")
        if (
            tuple(sorted(set(self.contacted_hotspot_residue_ids)))
            != self.contacted_hotspot_residue_ids
        ):
            raise ValueError("raw prediction contacted hotspots 必须升序唯一")
        return self


class SeedPairConsistency(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    first_seed: Literal[101, 202, 303, 404, 505]
    second_seed: Literal[101, 202, 303, 404, 505]
    binder_ca_rmsd_angstrom: float = Field(ge=0)
    hotspot_contact_jaccard: float = Field(ge=0, le=1)
    passed: bool

    @model_validator(mode="after")
    def validate_pair(self) -> Self:
        if self.first_seed >= self.second_seed:
            raise ValueError("seed pair 必须按升序保存且不能相同")
        expected = self.binder_ca_rmsd_angstrom <= 3.0 and self.hotspot_contact_jaccard >= 0.50
        if self.passed != expected:
            raise ValueError("seed pair pass 与 RMSD/Jaccard 门不一致")
        return self


class MultiSeedConsensusRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    candidate_id: str = Field(pattern=ID_PATTERN)
    available_seeds: tuple[Literal[101, 202, 303, 404, 505], ...]
    individually_passing_seeds: tuple[Literal[101, 202, 303, 404, 505], ...]
    consistent_seed_pairs: tuple[SeedPairConsistency, ...]
    consensus_seed_ids: tuple[Literal[101, 202, 303, 404, 505], ...]
    required_individually_passing_seeds: int = Field(default=2, ge=2, le=5)
    consensus_pass: bool
    score_final: float | None = Field(default=None, ge=0, le=1)
    median_score_full: float | None = Field(default=None, ge=0, le=1)
    score_deep: float = Field(ge=0, le=1)
    median_pairwise_iptm: float | None = None

    @model_validator(mode="after")
    def validate_consensus(self) -> Self:
        for values in (
            self.available_seeds,
            self.individually_passing_seeds,
            self.consensus_seed_ids,
        ):
            if tuple(sorted(set(values))) != values:
                raise ValueError("multi-seed identity 必须升序唯一")
        expected_pass = (
            len(self.individually_passing_seeds)
            >= self.required_individually_passing_seeds
            and len(self.consensus_seed_ids)
            >= self.required_individually_passing_seeds
        )
        if self.consensus_pass != expected_pass:
            raise ValueError("consensus pass 与所需独立通过且一致的 seed 数不一致")
        if expected_pass:
            if (
                self.score_final is None
                or self.median_score_full is None
                or self.median_pairwise_iptm is None
            ):
                raise ValueError("consensus pass 必须包含完整 score 汇总")
        elif any(
            value is not None
            for value in (
                self.score_final,
                self.median_score_full,
                self.median_pairwise_iptm,
            )
        ):
            raise ValueError("consensus fail 不得伪造 final score")
        return self


class TnpCandidateRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    candidate_id: str = Field(pattern=ID_PATTERN)
    total_cdr_length: int = Field(ge=0)
    cdr3_length: int = Field(ge=0)
    cdr3_compactness: float
    psh: float
    ppc: float
    pnc: float
    flags: dict[
        Literal["L", "L3", "C", "PSH", "PPC", "PNC"],
        Literal["green", "amber", "red"],
    ]
    red_flag_count: int = Field(ge=0)
    amber_flag_count: int = Field(ge=0)
    cdr_vernier_liabilities: tuple[SequenceLiability, ...] = ()
    risk: DevelopabilityRisk

    @model_validator(mode="after")
    def validate_risk(self) -> Self:
        if set(self.flags) != {"L", "L3", "C", "PSH", "PPC", "PNC"}:
            raise ValueError("TNP flags 必须包含固定六项")
        if self.red_flag_count != sum(value == "red" for value in self.flags.values()):
            raise ValueError("TNP red flag count 不一致")
        if self.amber_flag_count != sum(value == "amber" for value in self.flags.values()):
            raise ValueError("TNP amber flag count 不一致")
        liability_count = len(self.cdr_vernier_liabilities)
        expected = (
            DevelopabilityRisk.HIGH
            if self.red_flag_count >= 1 or liability_count >= 2
            else (
                DevelopabilityRisk.MEDIUM
                if self.amber_flag_count >= 2 or liability_count == 1
                else DevelopabilityRisk.LOW
            )
        )
        if self.risk is not expected:
            raise ValueError("TNP developability risk 与 v1.5 规则不一致")
        return self


class TnpReport(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["0.1"] = "0.1"
    generated_at: datetime
    source_commit: Literal["29dcac72f1380e8538e8870f45a699d3c6156162"] = (
        "29dcac72f1380e8538e8870f45a699d3c6156162"
    )
    source_license: Literal["BSD-3-Clause"] = "BSD-3-Clause"
    executable_identity: dict[str, str]
    raw_result: ArtifactRef
    candidates: tuple[TnpCandidateRecord, ...] = Field(min_length=1)


class Stage07PredictionState(BaseModel):
    """Atomic resume state for one model-neutral prediction phase."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["0.1"] = "0.1"
    created_at: datetime
    updated_at: datetime
    target_msa_sha256: str = Field(pattern=SHA256_PATTERN)
    scientific_mode: Literal["de-novo", "target-conditioned"] = "de-novo"
    target_condition_sha256: str | None = Field(default=None, pattern=SHA256_PATTERN)
    planned_prediction_keys: tuple[str, ...]
    tasks: tuple[TaskRecord, ...]
    predictions: tuple[RawFinalPrediction, ...] = ()
    sample_predictions: tuple[RawFinalPrediction, ...] = ()
    seed101_normalization: dict[str, tuple[float, ...]] = Field(default_factory=dict)
    progress: ProgressSnapshot

    @model_validator(mode="after")
    def validate_state(self) -> Self:
        if (self.scientific_mode == "de-novo") != (
            self.target_condition_sha256 is None
        ):
            raise ValueError("Stage 07 state scientific mode/condition 不一致")
        if tuple(sorted(set(self.planned_prediction_keys))) != (self.planned_prediction_keys):
            raise ValueError("Stage 07 prediction key 必须升序唯一")
        task_keys = tuple(sorted(item.strategy_id for item in self.tasks))
        if task_keys != self.planned_prediction_keys:
            raise ValueError("Stage 07 prediction task identity 与计划不一致")
        prediction_keys = tuple(
            sorted(f"{item.candidate_id}-seed-{item.seed}" for item in self.predictions)
        )
        if len(prediction_keys) != len(set(prediction_keys)):
            raise ValueError("Stage 07 prediction identity 不能重复")
        if not set(prediction_keys).issubset(self.planned_prediction_keys):
            raise ValueError("Stage 07 prediction 不在任务计划")
        sample_keys = tuple(
            sorted(
                f"{item.candidate_id}-seed-{item.seed}-sample-{item.sample_index}"
                for item in self.sample_predictions
            )
        )
        if len(sample_keys) != len(set(sample_keys)):
            raise ValueError("Stage 07 sample prediction identity 不能重复")
        representative_keys = {
            f"{item.candidate_id}-seed-{item.seed}-sample-{item.sample_index}"
            for item in self.predictions
        }
        if not representative_keys.issubset(set(sample_keys)) and self.sample_predictions:
            raise ValueError("Stage 07 seed representative 必须来自完整 sample evidence")
        return self


class Seed101Normalization(BaseModel):
    """Frozen empirical reference used by seed 101 and all additional seeds."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["0.1"] = "0.1"
    generated_at: datetime
    source_seed: Literal[101] = 101
    source_candidate_ids: tuple[str, ...] = Field(min_length=1)
    metric_reference_values: dict[str, tuple[float, ...]]

    @model_validator(mode="after")
    def validate_reference(self) -> Self:
        if tuple(sorted(set(self.source_candidate_ids))) != self.source_candidate_ids:
            raise ValueError("seed101 normalization candidate identity 必须升序唯一")
        if not self.metric_reference_values:
            raise ValueError("seed101 normalization 不能为空")
        expected_length = len(self.source_candidate_ids)
        if any(len(values) != expected_length for values in self.metric_reference_values.values()):
            raise ValueError("seed101 normalization 各 metric 长度必须等于 source pool")
        return self


class FinalSelectionRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    candidate_id: str = Field(pattern=ID_PATTERN)
    selection_class: Literal["primary", "backup"]
    selection_rank: int = Field(ge=1)
    gain: float = Field(ge=0, le=1)
    maximum_identity_to_previously_selected: float = Field(ge=0, le=1)
    score_final: float = Field(ge=0, le=1)
    developability_risk: DevelopabilityRisk
    median_pairwise_iptm: float


class FinalCandidate(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    candidate_id: str = Field(pattern=ID_PATTERN)
    strategy_id: str = Field(pattern=ID_PATTERN)
    sequence: str = Field(pattern=r"^[ACDEFGHIKLMNPQRSTVWY]+$")
    design_sequence: str = Field(pattern=r"^[ACDEFGHIKLMNPQRSTVWY]+$")
    source_refolded_structure: ArtifactRef
    prediction_structures: tuple[ArtifactRef, ...] = Field(min_length=2)
    score_refold: float = Field(ge=0, le=1)
    score_deep: float = Field(ge=0, le=1)
    score_final: float = Field(ge=0, le=1)
    consensus: MultiSeedConsensusRecord
    tnp: TnpCandidateRecord
    selection: FinalSelectionRecord
    warnings: tuple[str, ...] = ()


class FinalFilterReport(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["0.1"] = "0.1"
    generated_at: datetime
    profile_id: Literal[
        "nanobody-final-v1.5",
        "nanobody-final-v1.6",
    ] = "nanobody-final-v1.5"
    profile_sha256: str = Field(pattern=SHA256_PATTERN)
    scale_candidate_index_sha256: str = Field(pattern=SHA256_PATTERN)
    sequence_prefilter: tuple[SequencePrefilterRecord, ...] = Field(min_length=1)
    deep_filter: tuple[DeepFilterRecord, ...]
    predictions: tuple[FinalPredictionRecord, ...]
    sample_predictions: tuple[RawFinalPrediction, ...] = ()
    consensus: tuple[MultiSeedConsensusRecord, ...]
    selections: tuple[FinalSelectionRecord, ...]
    status: Literal["candidates-selected", "stopped-no-final-candidate"]


class TargetConditionedStage07Evidence(BaseModel):
    """Dual-track Stage 07 evidence that never participates in de-novo selection."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["0.1"] = "0.1"
    generated_at: datetime
    screening_profile_id: Literal["target-conditioned-evidence-v1"] = (
        "target-conditioned-evidence-v1"
    )
    selection_authority: Literal["advisory-only"] = "advisory-only"
    target_condition: TargetStructureCondition
    predictions: tuple[RawFinalPrediction, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_predictions(self) -> Self:
        if any(item.scientific_mode != "target-conditioned" for item in self.predictions):
            raise ValueError("Stage 07 conditioned evidence 含 de-novo prediction")
        if any(
            item.target_condition_sha256 != self.target_condition.template_data_sha256
            for item in self.predictions
        ):
            raise ValueError("Stage 07 conditioned prediction/condition identity 不一致")
        return self


class FinalCandidatePackage(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["0.1"] = "0.1"
    generated_at: datetime
    package_type: Literal[
        "smoke-review-package",
        "draft-order-package",
        "empty-review-package",
    ]
    scale_profile: Literal[
        "user-defined-v1",
        "smoke-1000",
        "production-50000",
    ]
    primary: tuple[FinalCandidate, ...] = ()
    backup: tuple[FinalCandidate, ...] = ()
    requested_primary_count: int = Field(ge=0)
    requested_backup_count: int = Field(ge=0)
    human_review_status: Literal["awaiting-human-review"] = "awaiting-human-review"
    biosafety_review_status: Literal["not-required", "pending"]
    ordering_status: Literal["not-ordered"] = "not-ordered"
    status: Literal["candidates-selected", "stopped-no-final-candidate"]

    @model_validator(mode="after")
    def validate_package(self) -> Self:
        identities = [item.candidate_id for item in self.primary + self.backup]
        if len(identities) != len(set(identities)):
            raise ValueError("primary/backup candidate 不能重复")
        if len(self.primary) > self.requested_primary_count:
            raise ValueError("primary 超过请求上限")
        if len(self.backup) > self.requested_backup_count:
            raise ValueError("backup 超过请求上限")
        if self.status == "stopped-no-final-candidate":
            if self.primary or self.backup or self.package_type != "empty-review-package":
                raise ValueError("empty scientific stop 不得包含候选")
        elif not self.primary and not self.backup:
            raise ValueError("candidates-selected 必须包含至少一个候选")
        return self


class Stage07Bundle(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["0.1"] = "0.1"
    generated_at: datetime
    scale_bundle: ArtifactRef
    filter_profile: ArtifactRef
    final_filter_report: ArtifactRef
    final_candidate_package: ArtifactRef
    target_conditioned_evidence: ArtifactRef | None = None
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
