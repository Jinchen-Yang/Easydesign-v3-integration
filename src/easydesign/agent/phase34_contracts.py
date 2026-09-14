"""Agent-facing Phase 3/4 contracts built on deterministic Stage 04-07 artifacts.

These models do not replace the existing execution manifests.  They make the
scientific meaning of development-scale execution, measurements and Gate 4
steering explicit without turning legacy filter thresholds into v3 truth.
"""

from __future__ import annotations

import hashlib
from datetime import datetime
from enum import StrEnum
from typing import Any, Literal, Self, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, model_validator

from easydesign.core import ArtifactRef, canonical_model_sha256
from easydesign.core.artifacts import ID_PATTERN, SHA256_PATTERN
from easydesign.stages.s04_pilot_generation import CandidateRecord

from .phase34_plan import (
    ApprovedGate3Context,
    BoundPilotPlan,
    PilotArmIntent,
    ValidatedDesignContext,
)


class FrozenContract(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)


class ExecutionMode(StrEnum):
    PRODUCTION = "production"
    FORMAL_PILOT = "formal-pilot"
    VALIDATION_MICRO = "validation-micro"
    SYNTHETIC_STRESS = "synthetic-stress"


class ExecutionProjection(FrozenContract):
    """Keep approved production intent distinct from a cheaper validation run."""

    mode: ExecutionMode
    requested_production_candidates: int = Field(ge=1)
    execution_candidates: int = Field(ge=1)
    uses_real_generation_backend: bool
    uses_real_prediction_backend: bool
    purpose: str = Field(min_length=1, max_length=1024)

    @model_validator(mode="after")
    def validate_projection(self) -> Self:
        if self.mode in {ExecutionMode.PRODUCTION, ExecutionMode.FORMAL_PILOT}:
            if self.execution_candidates != self.requested_production_candidates:
                raise ValueError("production execution must preserve the exact approved count")
        elif self.mode is ExecutionMode.VALIDATION_MICRO:
            if self.execution_candidates > self.requested_production_candidates:
                raise ValueError("validation execution cannot exceed production intent")
        else:
            if self.execution_candidates > self.requested_production_candidates:
                raise ValueError("synthetic stress cannot exceed production intent")
            if self.uses_real_generation_backend or self.uses_real_prediction_backend:
                raise ValueError("synthetic stress cannot claim a real scientific backend")
        return self


class AcceptedGate3Fixture(FrozenContract):
    """Read-only projection of an independently accepted, still-pending Gate 3 card."""

    fixture_id: str = Field(pattern=ID_PATTERN)
    case_id: Literal["case-4-standard", "case-5-native"]
    strategy_source: Literal["standard", "expert-native"]
    source_commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    milestone_tag: str = Field(min_length=1, max_length=256)
    gate3_card_id: str = Field(pattern=SHA256_PATTERN)
    gate3_request_identity: str = Field(pattern=SHA256_PATTERN)
    gate3_snapshot_sha256: str = Field(pattern=SHA256_PATTERN)
    target_identity: str = Field(min_length=1, max_length=256)
    target_bundle_sha256: str = Field(pattern=SHA256_PATTERN)
    site_intent_sha256: str = Field(pattern=SHA256_PATTERN)
    review_request_sha256: str = Field(pattern=SHA256_PATTERN)
    review_receipt_sha256: str = Field(pattern=SHA256_PATTERN)
    review_decision: Literal["PASS"] = "PASS"
    gate3_status: Literal["awaiting-human-approval"] = "awaiting-human-approval"
    strategy_sha256: str = Field(pattern=SHA256_PATTERN)
    compiled_manifest_sha256: str = Field(pattern=SHA256_PATTERN)
    execution_plan_sha256: str = Field(pattern=SHA256_PATTERN)
    planned_candidates: int = Field(ge=1)
    generation_started: Literal[False] = False
    acceptance_scope: str = Field(min_length=1, max_length=2048)
    evidence_refs: tuple[str, ...] = Field(min_length=1)


class ValidationExecutionAuthority(FrozenContract):
    """A development-only overlay; never a scientific Gate 3 approval."""

    authority_id: str = Field(pattern=ID_PATTERN)
    fixture_id: str = Field(pattern=ID_PATTERN)
    authority_scope: Literal["test-only-control-flow"] = "test-only-control-flow"
    authorized_mode: Literal[ExecutionMode.VALIDATION_MICRO] = ExecutionMode.VALIDATION_MICRO
    authorizes_scientific_pilot: Literal[False] = False
    authorizes_production_compute: Literal[False] = False
    authorizes_biological_claims: Literal[False] = False
    reason: str = Field(min_length=1, max_length=1024)
    pilot_plan: BoundPilotPlan | None = None


class ScientistPilotAuthority(FrozenContract):
    """Exact Scientist Gate 3 outcome authorizing one scientific Pilot."""

    authority_id: str = Field(pattern=ID_PATTERN)
    upstream_gate3_card_id: str = Field(pattern=SHA256_PATTERN)
    source_design_card_id: str | None = Field(default=None, pattern=SHA256_PATTERN)
    gate3_outcome_id: str = Field(pattern=ID_PATTERN)
    authority_scope: Literal["scientist-approved"] = "scientist-approved"
    outcome: Literal["APPROVE", "OVERRIDE"]
    human_actor: str = Field(min_length=1, max_length=256)
    approved_at: datetime
    authorizes_scientific_pilot: Literal[True] = True
    authorizes_full_pilot: Literal[True] = True
    authorizes_scale: Literal[False] = False
    pilot_plan: BoundPilotPlan | None = None

    @model_validator(mode="after")
    def validate_bound_scope(self) -> Self:
        if self.pilot_plan is not None and self.pilot_plan.mode != "formal-pilot":
            raise ValueError("Scientific Pilot authority requires a formal Pilot plan")
        return self


PilotExecutionAuthority: TypeAlias = ValidationExecutionAuthority | ScientistPilotAuthority


MetricScalar = bool | int | float | str | None


class MetricObservation(FrozenContract):
    metric_id: str = Field(pattern=ID_PATTERN)
    value: MetricScalar
    unit: str | None = Field(default=None, max_length=64)
    available: bool
    missing_reason: str | None = Field(default=None, max_length=1024)
    source: str = Field(min_length=1, max_length=128)
    definition_version: str = Field(min_length=1, max_length=128)

    @model_validator(mode="after")
    def validate_availability(self) -> Self:
        if self.available and (self.value is None or self.missing_reason is not None):
            raise ValueError("an available metric needs a value and no missing reason")
        if not self.available and (self.value is not None or not self.missing_reason):
            raise ValueError("an unavailable metric needs a missing reason and no value")
        return self


class LegacyPolicyAnnotation(FrozenContract):
    """Historical threshold output retained as evidence, not v3 scientific authority."""

    rule_id: str = Field(pattern=ID_PATTERN)
    metric_id: str = Field(pattern=ID_PATTERN)
    passed: bool
    reason: str = Field(min_length=1, max_length=1024)
    governing_v3_scientific_policy: Literal[False] = False


class PilotCandidateLineage(FrozenContract):
    candidate_id: str = Field(pattern=ID_PATTERN)
    strategy_id: str = Field(pattern=ID_PATTERN)
    task_id: str = Field(pattern=ID_PATTERN)
    task_attempt_number: int = Field(ge=1)
    ordinal_within_strategy: int = Field(ge=1)
    backend_candidate_id: str = Field(min_length=1, max_length=512)
    sequence_sha256: str = Field(pattern=SHA256_PATTERN)
    original_structure: ArtifactRef
    refolded_structure: ArtifactRef
    design_mask_source: ArtifactRef | None = None
    designed_binder_residue_ids: tuple[int, ...] = ()

    @model_validator(mode="after")
    def validate_design_mask(self) -> Self:
        if (self.design_mask_source is None) == bool(self.designed_binder_residue_ids):
            raise ValueError("design mask reference and residue identities must appear together")
        return self


class PilotCandidateObservation(FrozenContract):
    lineage: PilotCandidateLineage
    metrics: tuple[MetricObservation, ...]
    legacy_policy_annotations: tuple[LegacyPolicyAnnotation, ...]
    legacy_policy_pass: bool
    valid_execution_product: Literal[True] = True
    development_score: float = Field(ge=0, le=1)
    development_rank_global: int = Field(ge=1)
    development_rank_within_strategy: int = Field(ge=1)
    ranking_semantics: Literal["development-ordering-not-biological-fitness"] = (
        "development-ordering-not-biological-fitness"
    )

    @model_validator(mode="after")
    def unique_metrics_and_rules(self) -> Self:
        metric_ids = [item.metric_id for item in self.metrics]
        rule_ids = [item.rule_id for item in self.legacy_policy_annotations]
        if len(metric_ids) != len(set(metric_ids)):
            raise ValueError("candidate metric identities must be unique")
        if len(rule_ids) != len(set(rule_ids)):
            raise ValueError("candidate policy rule identities must be unique")
        return self


class PilotArmDenominator(FrozenContract):
    strategy_id: str = Field(pattern=ID_PATTERN)
    planned_candidates: int = Field(ge=1)
    generated_candidates: int = Field(ge=0)
    valid_execution_products: int = Field(ge=0)
    predicted_candidates: int = Field(ge=0)
    metric_evaluable_candidates: int = Field(ge=0)
    unique_sequences: int = Field(ge=0)
    legacy_policy_pass_count: int = Field(ge=0)
    operational_failure_count: int = Field(ge=0)
    failed_generation_attempts: int = Field(default=0, ge=0)
    failed_prediction_attempts: int = Field(default=0, ge=0)
    missing_by_metric: dict[str, int] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_counts(self) -> Self:
        counts = (
            self.generated_candidates,
            self.valid_execution_products,
            self.predicted_candidates,
            self.metric_evaluable_candidates,
            self.unique_sequences,
            self.legacy_policy_pass_count,
        )
        if any(value > self.planned_candidates for value in counts):
            raise ValueError("pilot denominator exceeds planned candidates")
        if self.valid_execution_products > self.generated_candidates:
            raise ValueError("valid products cannot exceed generated candidates")
        if self.predicted_candidates > self.valid_execution_products:
            raise ValueError("predictions cannot exceed valid products")
        if self.metric_evaluable_candidates > self.valid_execution_products:
            raise ValueError("metric-evaluable count cannot exceed valid products")
        if self.unique_sequences > self.valid_execution_products:
            raise ValueError("unique sequences cannot exceed valid products")
        if self.legacy_policy_pass_count > self.metric_evaluable_candidates:
            raise ValueError("legacy passes cannot exceed metric-evaluable products")
        # A generated candidate may subsequently fail prediction. These populations overlap.
        if self.operational_failure_count > self.planned_candidates:
            raise ValueError("operational failures exceed planned candidate slots")
        if any(
            value < 0 or value > self.valid_execution_products
            for value in self.missing_by_metric.values()
        ):
            raise ValueError("missing metric counts must fit the valid product denominator")
        return self


class PilotMeasurement(FrozenContract):
    schema_version: Literal["0.1"] = "0.1"
    execution: ExecutionProjection
    source_candidate_index_sha256: str = Field(pattern=SHA256_PATTERN)
    source_filter_report_sha256: str | None = Field(default=None, pattern=SHA256_PATTERN)
    source_candidate_index_kind: Literal[
        "candidate-index", "partial-generation-state", "generation-failure-receipt"
    ] = "candidate-index"
    unmeasured_candidates: tuple[CandidateRecord, ...] = ()
    candidates: tuple[PilotCandidateObservation, ...]
    arms: tuple[PilotArmDenominator, ...] = Field(min_length=1)
    scientific_policy: Literal["measure-and-rank-first-filter-calibration-pending"] = (
        "measure-and-rank-first-filter-calibration-pending"
    )

    @model_validator(mode="after")
    def validate_population(self) -> Self:
        ids = [item.lineage.candidate_id for item in self.candidates]
        if len(ids) != len(set(ids)):
            raise ValueError("pilot candidate identities must be globally unique")
        strategy_ids = [item.strategy_id for item in self.arms]
        if len(strategy_ids) != len(set(strategy_ids)):
            raise ValueError("pilot arm identities must be unique")
        if sum(item.planned_candidates for item in self.arms) != (
            self.execution.execution_candidates
        ):
            raise ValueError("pilot arm plans must equal the execution projection")
        observed = {strategy_id: 0 for strategy_id in strategy_ids}
        for candidate in self.candidates:
            if candidate.lineage.strategy_id not in observed:
                raise ValueError("candidate belongs to an undeclared pilot arm")
            observed[candidate.lineage.strategy_id] += 1
        for unmeasured in self.unmeasured_candidates:
            if unmeasured.candidate_id in ids or unmeasured.strategy_id not in observed:
                raise ValueError("Unmeasured candidate is duplicate or belongs to another arm")
            ids.append(unmeasured.candidate_id)
            observed[unmeasured.strategy_id] += 1
        if (
            self.unmeasured_candidates
            and self.source_candidate_index_kind != "partial-generation-state"
        ):
            raise ValueError("Unmeasured products must retain their partial execution provenance")
        for arm in self.arms:
            if arm.valid_execution_products != observed[arm.strategy_id]:
                raise ValueError("arm denominator does not match retained candidate observations")
        ranks = sorted(item.development_rank_global for item in self.candidates)
        if ranks != list(range(1, len(ranks) + 1)):
            raise ValueError("global development ranks must be contiguous")
        return self


PilotDiagnosisCategory = Literal[
    "generation-failure",
    "design-or-conditioning-failure",
    "binder-geometry-failure",
    "site-level-problem",
    "target-integrity-problem",
    "prediction-uncertainty",
    "execution-or-backend-defect",
    "insufficient-evidence",
]


class PilotArmSummary(FrozenContract):
    """Observed arm population summary; no production selection cutoff is implied."""

    strategy_id: str = Field(pattern=ID_PATTERN)
    planned_candidates: int = Field(ge=1)
    valid_execution_products: int = Field(ge=0)
    predicted_candidates: int = Field(ge=0)
    unique_sequences: int = Field(ge=0)
    operational_failure_count: int = Field(ge=0)
    legacy_policy_pass_count: int = Field(ge=0)
    development_score_median: float | None = Field(default=None, ge=0, le=1)
    development_score_top_quartile_mean: float | None = Field(default=None, ge=0, le=1)
    missing_by_metric: dict[str, int]
    interpretation_scope: Literal["descriptive-no-calibrated-cutoff"] = (
        "descriptive-no-calibrated-cutoff"
    )


class PilotDiagnosisHypothesis(FrozenContract):
    category: PilotDiagnosisCategory
    status: Literal["SUPPORTED", "PLAUSIBLE", "NOT_SUPPORTED", "UNRESOLVED"]
    observations: tuple[str, ...] = Field(min_length=1)
    implications: tuple[str, ...] = Field(min_length=1)
    evidence_refs: tuple[str, ...] = Field(min_length=1)


class PilotDiagnosis(FrozenContract):
    """Evidence-proportionate diagnosis supplied to an independent Gate 4 Judge."""

    schema_version: Literal["0.1"] = "0.1"
    measurement_sha256: str = Field(pattern=SHA256_PATTERN)
    arm_summaries: tuple[PilotArmSummary, ...] = Field(min_length=1)
    hypotheses: tuple[PilotDiagnosisHypothesis, ...] = Field(min_length=1)
    conclusion: tuple[str, ...] = Field(min_length=1)
    uncertainties: tuple[str, ...] = Field(min_length=1)
    evidence_refs: tuple[str, ...] = Field(min_length=1)
    confidence: Literal["BOUNDED", "INCONCLUSIVE"]
    design_arms: tuple[PilotArmIntent, ...] = ()
    arm_comparisons: tuple[str, ...] = ()
    alternative_explanations: tuple[str, ...] = ()
    operational_confounders: tuple[str, ...] = ()
    next_discriminating_experiment: tuple[str, ...] = ()
    arm_hypothesis_findings: tuple[dict[str, Any], ...] = ()

    @model_validator(mode="after")
    def validate_hypotheses(self) -> Self:
        categories = [item.category for item in self.hypotheses]
        if len(categories) != len(set(categories)):
            raise ValueError("Pilot diagnosis categories must be unique")
        if self.confidence == "INCONCLUSIVE" and not any(
            item.category == "insufficient-evidence" for item in self.hypotheses
        ):
            raise ValueError("an inconclusive Pilot diagnosis must name insufficient evidence")
        return self


Gate4Outcome = Literal[
    "PROMOTE_TO_SCALE",
    "RUN_ANOTHER_PILOT",
    "REVISE_DESIGN",
    "REVISE_SITE",
    "STOP",
]


class Gate4Recommendation(FrozenContract):
    """Scientific steering proposal; test-only promotion is structurally unmistakable."""

    outcome: Gate4Outcome
    selected_strategy_ids: tuple[str, ...] = ()
    requested_scale_candidates: int | None = Field(default=None, ge=1)
    production_strategy_allocations: dict[str, int] = Field(default_factory=dict)
    evidence_sufficiency: Literal["SUFFICIENT_FOR_STEERING", "INCONCLUSIVE"]
    scientific_supporting_candidate_count: int = Field(ge=0)
    observations: tuple[str, ...] = Field(min_length=1)
    interpretations: tuple[str, ...] = Field(min_length=1)
    alternative_explanations: tuple[str, ...] = Field(min_length=1)
    uncertainties: tuple[str, ...] = Field(min_length=1)
    falsifiers_or_next_measurements: tuple[str, ...] = Field(min_length=1)
    evidence_refs: tuple[str, ...] = Field(min_length=1)
    test_only_control_flow_fixture: bool = False

    @model_validator(mode="after")
    def validate_promotion_claim(self) -> Self:
        if len(self.selected_strategy_ids) != len(set(self.selected_strategy_ids)):
            raise ValueError("Gate 4 recommendation contains duplicate strategy identities")
        if self.outcome == "PROMOTE_TO_SCALE" and not self.selected_strategy_ids:
            raise ValueError("Gate 4 promotion must name the exact selected strategies")
        if self.outcome == "PROMOTE_TO_SCALE":
            if self.requested_scale_candidates is None:
                raise ValueError("Gate 4 promotion must state the production Scale intent")
            if set(self.production_strategy_allocations) != set(self.selected_strategy_ids):
                raise ValueError("Gate 4 Scale allocations must cover the selected strategies")
            if (
                any(value < 1 for value in self.production_strategy_allocations.values())
                or sum(self.production_strategy_allocations.values())
                != self.requested_scale_candidates
            ):
                raise ValueError("Gate 4 Scale allocations must equal the requested count")
        elif (
            self.selected_strategy_ids
            or self.requested_scale_candidates is not None
            or self.production_strategy_allocations
        ):
            raise ValueError("Only Gate 4 promotion may define a Scale campaign intent")
        if self.test_only_control_flow_fixture:
            if self.outcome != "PROMOTE_TO_SCALE" or self.evidence_sufficiency != "INCONCLUSIVE":
                raise ValueError(
                    "a test-only Gate 4 fixture is an inconclusive PROMOTE control path"
                )
        elif self.outcome == "PROMOTE_TO_SCALE" and (
            self.evidence_sufficiency != "SUFFICIENT_FOR_STEERING"
            or self.scientific_supporting_candidate_count == 0
        ):
            raise ValueError(
                "scientific promotion needs sufficient evidence and supporting candidates"
            )
        if (
            self.scientific_supporting_candidate_count == 0
            and not self.test_only_control_flow_fixture
        ):
            if self.evidence_sufficiency != "INCONCLUSIVE":
                raise ValueError(
                    "zero supporting candidates must remain scientifically inconclusive"
                )
        return self


class PilotEvidenceDossier(FrozenContract):
    """Trusted Pilot facts plus a clearly bounded scientific interpretation."""

    schema_version: Literal["0.1"] = "0.1"
    project_id: str = Field(pattern=ID_PATTERN)
    pilot_run_id: str = Field(pattern=ID_PATTERN)
    upstream_fixture: AcceptedGate3Fixture | ApprovedGate3Context | ValidatedDesignContext
    execution_authority: PilotExecutionAuthority
    measurement: PilotMeasurement
    diagnosis: PilotDiagnosis
    proposed_interpretation: Gate4Recommendation
    evidence_refs: tuple[str, ...] = Field(min_length=1)
    hard_fact_authority: Literal["trusted-runtime-and-verified-artifacts"] = (
        "trusted-runtime-and-verified-artifacts"
    )

    @model_validator(mode="after")
    def validate_authority_and_scope(self) -> Self:
        authority = self.execution_authority
        product_context = isinstance(self.upstream_fixture, ApprovedGate3Context)
        if product_context:
            context = self.upstream_fixture
            assert isinstance(context, ApprovedGate3Context)
            if self.project_id != context.project_id or authority.pilot_plan != context.plan:
                raise ValueError("Pilot authority belongs to a different project or plan")
            if self.diagnosis.design_arms != context.plan.arms:
                raise ValueError("Pilot diagnosis lost the approved Design arm hypotheses")
            if self.measurement.execution.execution_candidates != sum(
                context.plan.execution_allocations.values()
            ) or {a.strategy_id: a.planned_candidates for a in self.measurement.arms} != (
                context.plan.execution_allocations
            ):
                raise ValueError("Measured Pilot scope differs from the authorized allocation")
        if self.diagnosis.measurement_sha256 != canonical_model_sha256(self.measurement):
            raise ValueError("Pilot diagnosis is bound to a different measurement")
        if self.measurement.execution.requested_production_candidates != (
            self.upstream_fixture.planned_candidates
        ):
            raise ValueError("Pilot execution changed the approved production intent")
        if isinstance(authority, ValidationExecutionAuthority):
            fixture_id = (
                self.upstream_fixture.plan.design_proposal_id
                if isinstance(self.upstream_fixture, ApprovedGate3Context)
                else self.upstream_fixture.fixture_id
            )
            if authority.fixture_id != fixture_id:
                raise ValueError("validation authority belongs to a different Gate 3 fixture")
            if self.measurement.execution.mode is not ExecutionMode.VALIDATION_MICRO:
                raise ValueError("validation-only authority can execute only validation-micro")
        else:
            if authority.upstream_gate3_card_id != self.upstream_fixture.gate3_card_id:
                raise ValueError("Scientist Pilot authority belongs to a different Gate 3 card")
            if self.measurement.execution.mode is ExecutionMode.SYNTHETIC_STRESS:
                raise ValueError("Scientist Pilot authority is not consumed by synthetic stress")
        if self.proposed_interpretation.test_only_control_flow_fixture and not isinstance(
            authority, ValidationExecutionAuthority
        ):
            raise ValueError("test-only Gate 4 promotion requires validation-only authority")
        if self.measurement.execution.mode is ExecutionMode.VALIDATION_MICRO and (
            self.diagnosis.confidence != "INCONCLUSIVE"
            or self.proposed_interpretation.evidence_sufficiency != "INCONCLUSIVE"
        ):
            raise ValueError("validation-micro evidence is scientifically INCONCLUSIVE")
        if self.proposed_interpretation.scientific_supporting_candidate_count > len(
            self.measurement.candidates
        ):
            raise ValueError("scientific supporting count exceeds the measured population")
        return self


class PilotJudgeAssessment(FrozenContract):
    """Independent critique bound to one exact Pilot dossier."""

    assessment_id: str = Field(pattern=ID_PATTERN)
    dossier_sha256: str = Field(pattern=SHA256_PATTERN)
    verdict: Literal["ready-to-ask", "insufficient", "reject"]
    recommendation: Gate4Outcome
    reasons: tuple[str, ...] = Field(min_length=1)
    limitations: tuple[str, ...] = Field(min_length=1)
    critical_counterevidence: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = Field(min_length=1)
    source_role: Literal["evidence-judge"] = "evidence-judge"

    @model_validator(mode="after")
    def validate_recommendation(self) -> Self:
        if self.verdict != "ready-to-ask" and self.recommendation == "PROMOTE_TO_SCALE":
            raise ValueError("an insufficient or rejected dossier cannot recommend promotion")
        return self


class Gate4PromotionAuthority(FrozenContract):
    """Exact Gate 4 authority consumed by one Scale campaign."""

    authority_id: str = Field(pattern=ID_PATTERN)
    gate4_card_id: str = Field(pattern=SHA256_PATTERN)
    pilot_dossier_sha256: str = Field(pattern=SHA256_PATTERN)
    selected_strategy_ids: tuple[str, ...] = Field(min_length=1)
    requested_scale_candidates: int = Field(ge=1)
    production_strategy_allocations: dict[str, int] = Field(min_length=1)
    outcome: Literal["PROMOTE_TO_SCALE"] = "PROMOTE_TO_SCALE"
    authority_scope: Literal["scientist-approved", "test-only-control-flow"]
    human_actor: str = Field(min_length=1, max_length=256)
    authorizes_scientific_scale: bool
    authorizes_production_compute: bool

    @model_validator(mode="after")
    def validate_scope(self) -> Self:
        if len(self.selected_strategy_ids) != len(set(self.selected_strategy_ids)):
            raise ValueError("promoted strategy identities must be unique")
        if set(self.production_strategy_allocations) != set(self.selected_strategy_ids):
            raise ValueError("approved Scale allocations must cover promoted strategies")
        if (
            any(value < 1 for value in self.production_strategy_allocations.values())
            or sum(self.production_strategy_allocations.values()) != self.requested_scale_candidates
        ):
            raise ValueError("approved Scale allocations must equal the requested count")
        if self.authority_scope == "test-only-control-flow":
            if self.authorizes_scientific_scale or self.authorizes_production_compute:
                raise ValueError("test-only Gate 4 authority cannot authorize scientific Scale")
        elif not self.authorizes_scientific_scale:
            raise ValueError("Scientist Gate 4 promotion must authorize scientific Scale")
        return self


class ScaleCampaignSpecification(FrozenContract):
    schema_version: Literal["0.1"] = "0.1"
    campaign_id: str = Field(pattern=ID_PATTERN)
    promotion_authority: Gate4PromotionAuthority
    execution: ExecutionProjection
    strategy_allocations: dict[str, int] = Field(min_length=1)
    generation_backend: str = Field(min_length=1, max_length=128)
    prediction_backend: str = Field(min_length=1, max_length=128)
    allocation_policy: str = Field(min_length=1, max_length=128)

    @model_validator(mode="after")
    def validate_campaign(self) -> Self:
        if self.execution.requested_production_candidates != (
            self.promotion_authority.requested_scale_candidates
        ):
            raise ValueError("Scale campaign changed the Gate 4 production intent")
        if set(self.strategy_allocations) != set(self.promotion_authority.selected_strategy_ids):
            raise ValueError("Scale allocations must exactly cover promoted strategies")
        if any(value < 1 for value in self.strategy_allocations.values()):
            raise ValueError("Scale allocations must be positive")
        if sum(self.strategy_allocations.values()) != self.execution.execution_candidates:
            raise ValueError("Scale allocations must equal the execution projection")
        if (
            self.execution.mode is ExecutionMode.PRODUCTION
            and not self.promotion_authority.authorizes_production_compute
        ):
            raise ValueError("production execution lacks explicit Gate 4 authority")
        if (
            self.promotion_authority.authority_scope == "test-only-control-flow"
            and self.execution.mode
            not in {ExecutionMode.VALIDATION_MICRO, ExecutionMode.SYNTHETIC_STRESS}
        ):
            raise ValueError(
                "test-only promotion can execute only validation-micro or synthetic Scale"
            )
        return self


class ScaleCandidateValidity(StrEnum):
    VALID_EVALUATED = "valid-evaluated"
    INVALID_EXECUTION_PRODUCT = "invalid-execution-product"
    UNEVALUABLE = "unevaluable"


class DiversityContext(FrozenContract):
    sequence_cluster_id: str | None = Field(default=None, pattern=ID_PATTERN)
    pose_cluster_id: str | None = Field(default=None, pattern=ID_PATTERN)
    method: str | None = Field(default=None, max_length=256)
    interpretation: Literal["advisory-only"] = "advisory-only"


class ScaleCandidateLineageV3(FrozenContract):
    campaign_id: str = Field(pattern=ID_PATTERN)
    source_run_id: str | None = Field(default=None, pattern=ID_PATTERN)
    batch_id: str = Field(pattern=ID_PATTERN)
    shard_id: str = Field(pattern=ID_PATTERN)
    candidate_id: str = Field(pattern=ID_PATTERN)
    strategy_id: str = Field(pattern=ID_PATTERN)
    strategy_ordinal: int = Field(ge=1)
    generation_task_id: str = Field(pattern=ID_PATTERN)
    generation_attempt: int = Field(ge=1)
    backend_candidate_id: str | None = Field(default=None, max_length=512)
    prediction_id: str | None = Field(default=None, pattern=ID_PATTERN)
    prediction_seed: int | None = Field(default=None, ge=0)
    prediction_ids: tuple[str, ...] = ()
    prediction_seeds: tuple[int, ...] = ()
    sequence_sha256: str = Field(pattern=SHA256_PATTERN)
    artifact_refs: tuple[ArtifactRef, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_predictions(self) -> Self:
        if len(self.prediction_ids) != len(self.prediction_seeds):
            raise ValueError("prediction identities and seeds must have equal coverage")
        if len(self.prediction_ids) != len(set(self.prediction_ids)):
            raise ValueError("prediction identities must be unique")
        if (self.prediction_id is None) != (self.prediction_seed is None):
            raise ValueError("primary prediction identity and seed must appear together")
        if self.prediction_id is not None and self.prediction_id not in self.prediction_ids:
            raise ValueError("primary prediction must be included in prediction lineage")
        return self


class ScaleCandidateObservation(FrozenContract):
    lineage: ScaleCandidateLineageV3
    validity: ScaleCandidateValidity
    metrics: tuple[MetricObservation, ...] = ()
    legacy_policy_annotations: tuple[LegacyPolicyAnnotation, ...] = ()
    legacy_policy_pass: bool | None = None
    development_score: float | None = Field(default=None, ge=0, le=1)
    global_development_rank: int | None = Field(default=None, ge=1)
    failure_reason: str | None = Field(default=None, max_length=2048)
    diversity: DiversityContext = DiversityContext()
    evaluation_level: Literal["refold", "deep", "multi-seed", "unavailable"] = "unavailable"
    ranking_semantics: Literal["development-ordering-not-biological-fitness"] = (
        "development-ordering-not-biological-fitness"
    )

    @model_validator(mode="after")
    def validate_rankability(self) -> Self:
        rankable = self.validity is ScaleCandidateValidity.VALID_EVALUATED
        if rankable and (self.development_score is None or self.failure_reason is not None):
            raise ValueError("valid evaluated candidates need a score and no failure reason")
        if not rankable and (
            self.development_score is not None
            or self.global_development_rank is not None
            or not self.failure_reason
        ):
            raise ValueError("invalid or unevaluable products are retained but never ranked")
        metric_ids = [item.metric_id for item in self.metrics]
        if len(metric_ids) != len(set(metric_ids)):
            raise ValueError("scale candidate metric identities must be unique")
        rule_ids = [item.rule_id for item in self.legacy_policy_annotations]
        if len(rule_ids) != len(set(rule_ids)):
            raise ValueError("scale candidate legacy rule identities must be unique")
        if any(item.governing_v3_scientific_policy for item in self.legacy_policy_annotations):
            raise ValueError("legacy Scale rules cannot become v3 scientific policy")
        return self


class GlobalCandidatePool(FrozenContract):
    schema_version: Literal["0.1"] = "0.1"
    campaign: ScaleCampaignSpecification
    source_candidate_index_sha256: str = Field(pattern=SHA256_PATTERN)
    source_metric_report_sha256: str = Field(pattern=SHA256_PATTERN)
    planned_batches: int = Field(ge=1)
    completed_batch_ids: tuple[str, ...] = ()
    failed_batch_ids: tuple[str, ...] = ()
    resumable_batch_ids: tuple[str, ...] = ()
    candidates: tuple[ScaleCandidateObservation, ...]
    global_ranking_candidate_ids: tuple[str, ...]
    full_pool_preserved: Literal[True] = True
    batch_selection_policy: Literal["global-ranking-not-per-batch-top-n"] = (
        "global-ranking-not-per-batch-top-n"
    )

    @model_validator(mode="after")
    def validate_pool(self) -> Self:
        batch_states = (
            self.completed_batch_ids,
            self.failed_batch_ids,
            self.resumable_batch_ids,
        )
        flattened = [item for group in batch_states for item in group]
        if len(flattened) != len(set(flattened)):
            raise ValueError("a Scale batch cannot have multiple terminal/recovery states")
        if len(flattened) > self.planned_batches:
            raise ValueError("Scale batch states exceed the campaign plan")
        candidate_ids = [item.lineage.candidate_id for item in self.candidates]
        if len(candidate_ids) != len(set(candidate_ids)):
            raise ValueError("Scale candidate identities must be globally unique")
        declared_batches = set(flattened)
        observed_by_strategy = {
            strategy_id: 0 for strategy_id in self.campaign.strategy_allocations
        }
        for candidate in self.candidates:
            if candidate.lineage.campaign_id != self.campaign.campaign_id:
                raise ValueError("Scale candidate belongs to a different campaign")
            if candidate.lineage.batch_id not in declared_batches:
                raise ValueError("Scale candidate belongs to an undeclared batch")
            if candidate.lineage.strategy_id not in observed_by_strategy:
                raise ValueError("Scale candidate belongs to an unapproved strategy")
            observed_by_strategy[candidate.lineage.strategy_id] += 1
        for strategy_id, observed in observed_by_strategy.items():
            if observed > self.campaign.strategy_allocations[strategy_id]:
                raise ValueError("Scale observations exceed the strategy allocation")
        campaign_fully_complete = (
            len(self.completed_batch_ids) == self.planned_batches
            and not self.failed_batch_ids
            and not self.resumable_batch_ids
        )
        if campaign_fully_complete and (
            len(self.candidates) != self.campaign.execution.execution_candidates
        ):
            raise ValueError("a complete Scale campaign must retain every allocated candidate")
        ranked = [
            item
            for item in self.candidates
            if item.validity is ScaleCandidateValidity.VALID_EVALUATED
        ]
        ranked.sort(key=lambda item: item.global_development_rank or 0)
        if [item.global_development_rank for item in ranked] != list(range(1, len(ranked) + 1)):
            raise ValueError("global Scale ranks must be contiguous")
        if self.global_ranking_candidate_ids != tuple(item.lineage.candidate_id for item in ranked):
            raise ValueError("global ranking index does not match candidate observations")
        return self


class ReviewShortlistEntry(FrozenContract):
    candidate_id: str = Field(pattern=ID_PATTERN)
    global_development_rank: int = Field(ge=1)
    review_role: Literal["ranked-lead", "diversity-representative"]
    reason: str = Field(min_length=1, max_length=1024)


class ReviewShortlist(FrozenContract):
    schema_version: Literal["0.1"] = "0.1"
    global_pool_sha256: str = Field(pattern=SHA256_PATTERN)
    requested_count: int = Field(ge=1)
    entries: tuple[ReviewShortlistEntry, ...]
    sequence_cluster_cap: int | None = Field(default=None, ge=1)
    full_ranked_pool_preserved: Literal[True] = True
    selection_semantics: Literal["review-priority-not-scientific-hard-filter"] = (
        "review-priority-not-scientific-hard-filter"
    )
    shortfall_reason: str | None = Field(default=None, max_length=1024)

    @model_validator(mode="after")
    def validate_shortlist(self) -> Self:
        ids = [item.candidate_id for item in self.entries]
        if len(ids) != len(set(ids)):
            raise ValueError("shortlist candidates must be unique")
        if len(ids) > self.requested_count:
            raise ValueError("shortlist exceeds the requested count")
        if len(ids) < self.requested_count and not self.shortfall_reason:
            raise ValueError("a short shortlist must explain its shortfall")
        if len(ids) == self.requested_count and self.shortfall_reason is not None:
            raise ValueError("a complete shortlist cannot claim a shortfall")
        return self


class ScientificContextReferences(FrozenContract):
    """Exact upstream scientific identities; large artifacts remain referenced."""

    target_identity: str = Field(min_length=1, max_length=256)
    target_snapshot_sha256: str = Field(pattern=SHA256_PATTERN)
    site_intent_sha256: str = Field(pattern=SHA256_PATTERN)
    design_specification_sha256: str = Field(pattern=SHA256_PATTERN)
    pilot_dossier_sha256: str = Field(pattern=SHA256_PATTERN)
    evidence_refs: tuple[str, ...] = Field(min_length=4)


class FinalCandidateDossier(FrozenContract):
    """Review projection for one candidate with complete lineage and no artifact copies."""

    schema_version: Literal["0.1"] = "0.1"
    global_pool_sha256: str = Field(pattern=SHA256_PATTERN)
    review_shortlist_sha256: str = Field(pattern=SHA256_PATTERN)
    context: ScientificContextReferences
    candidate: ScaleCandidateObservation
    sequence: str = Field(pattern=r"^[ACDEFGHIKLMNPQRSTVWY]+$")
    known_concerns: tuple[str, ...] = Field(min_length=1)
    uncertainties: tuple[str, ...] = Field(min_length=1)
    provenance_refs: tuple[str, ...] = Field(min_length=1)
    scientific_claim_scope: Literal[
        "development-evidence-only", "scientist-approved-scale-evidence"
    ]

    @model_validator(mode="after")
    def validate_candidate(self) -> Self:
        sequence_sha256 = hashlib.sha256(self.sequence.encode()).hexdigest()
        if sequence_sha256 != self.candidate.lineage.sequence_sha256:
            raise ValueError("candidate dossier sequence does not match its lineage hash")
        if self.candidate.validity is not ScaleCandidateValidity.VALID_EVALUATED:
            raise ValueError("only valid evaluated candidates can enter final review")
        if self.candidate.global_development_rank is None:
            raise ValueError("final review candidate lacks a global development rank")
        return self


class FinalSelectionProposal(FrozenContract):
    """A review proposal, never an automatic scientific acceptance policy."""

    primary_candidate_ids: tuple[str, ...] = Field(min_length=1)
    backup_candidate_ids: tuple[str, ...] = ()
    requested_primary_count: int = Field(ge=1)
    requested_backup_count: int = Field(ge=0)
    rationale: tuple[str, ...] = Field(min_length=1)
    selection_gap_reason: str | None = Field(default=None, max_length=2048)
    major_risks: tuple[str, ...] = ()
    diversity_coverage: tuple[str, ...] = ()
    unresolved_questions: tuple[str, ...] = ()
    selection_semantics: Literal["proposal-for-scientist-review"] = "proposal-for-scientist-review"

    @model_validator(mode="after")
    def validate_counts(self) -> Self:
        primary = self.primary_candidate_ids
        backup = self.backup_candidate_ids
        if len(primary) != len(set(primary)) or len(backup) != len(set(backup)):
            raise ValueError("final selection candidate identities must be unique")
        if set(primary) & set(backup):
            raise ValueError("primary and backup final selections must be disjoint")
        if len(primary) > self.requested_primary_count:
            raise ValueError("primary selection exceeds the requested panel size")
        if len(backup) > self.requested_backup_count:
            raise ValueError("backup selection exceeds the requested panel size")
        has_gap = (
            len(primary) < self.requested_primary_count or len(backup) < self.requested_backup_count
        )
        if has_gap != (self.selection_gap_reason is not None):
            raise ValueError("final panel count gaps must be explained exactly when present")
        return self


class FinalSelectionInput(FrozenContract):
    project_id: str = Field(pattern=ID_PATTERN)
    global_pool_sha256: str = Field(pattern=SHA256_PATTERN)
    review_shortlist_sha256: str = Field(pattern=SHA256_PATTERN)
    candidate_dossiers: tuple[FinalCandidateDossier, ...] = Field(min_length=1)
    primary_count: int = Field(ge=1, le=30)
    backup_count: int = Field(ge=0, le=30)

    @model_validator(mode="after")
    def exact_inputs(self) -> Self:
        if any(
            d.global_pool_sha256 != self.global_pool_sha256
            or d.review_shortlist_sha256 != self.review_shortlist_sha256
            for d in self.candidate_dossiers
        ):
            raise ValueError("Selection input contains a stale candidate dossier")
        return self


class FinalReviewDossier(FrozenContract):
    """Evidence-bound candidate set and proposed panel consumed by the final Judge."""

    selection_revision_id: str | None = Field(default=None, pattern=SHA256_PATTERN)
    schema_version: Literal["0.1"] = "0.1"
    project_id: str = Field(pattern=ID_PATTERN)
    campaign_id: str = Field(pattern=ID_PATTERN)
    global_pool_sha256: str = Field(pattern=SHA256_PATTERN)
    review_shortlist_sha256: str = Field(pattern=SHA256_PATTERN)
    candidate_dossiers: tuple[FinalCandidateDossier, ...] = Field(min_length=1)
    proposed_selection: FinalSelectionProposal
    evidence_refs: tuple[str, ...] = Field(min_length=1)
    full_ranked_pool_preserved: Literal[True] = True
    filtering_policy: Literal["calibration-pending"] = "calibration-pending"

    @model_validator(mode="after")
    def validate_review_set(self) -> Self:
        candidate_ids = [item.candidate.lineage.candidate_id for item in self.candidate_dossiers]
        if len(candidate_ids) != len(set(candidate_ids)):
            raise ValueError("final review candidate dossiers must be unique")
        for dossier in self.candidate_dossiers:
            if dossier.global_pool_sha256 != self.global_pool_sha256:
                raise ValueError("candidate dossier belongs to a different global pool")
            if dossier.review_shortlist_sha256 != self.review_shortlist_sha256:
                raise ValueError("candidate dossier belongs to a different review shortlist")
            if dossier.candidate.lineage.campaign_id != self.campaign_id:
                raise ValueError("candidate dossier belongs to a different Scale campaign")
            if dossier.context != self.candidate_dossiers[0].context:
                raise ValueError("final review candidates do not share one scientific context")
            if dossier.scientific_claim_scope != self.candidate_dossiers[0].scientific_claim_scope:
                raise ValueError("final review candidates do not share one authority scope")
        selected = set(self.proposed_selection.primary_candidate_ids) | set(
            self.proposed_selection.backup_candidate_ids
        )
        if not selected.issubset(candidate_ids):
            raise ValueError("final selection refers to a candidate outside final review")
        return self


Gate5Outcome = Literal[
    "APPROVE_WET_LAB_HANDOFF",
    "REVISE_FINAL_SELECTION",
    "STOP",
]


class FinalCandidateJudgeFinding(FrozenContract):
    candidate_id: str = Field(pattern=ID_PATTERN)
    status: Literal["SUPPORTED", "DISCOURAGED", "BLOCKED"]
    reasons: tuple[str, ...] = Field(min_length=1)
    concerns: tuple[str, ...] = Field(min_length=1)


class Gate5JudgeAssessment(FrozenContract):
    """Independent final review of the candidate set, beyond its rank scores."""

    assessment_id: str = Field(pattern=ID_PATTERN)
    final_review_dossier_sha256: str = Field(pattern=SHA256_PATTERN)
    verdict: Literal["ready-to-ask", "insufficient", "reject"]
    recommendation: Gate5Outcome
    candidate_findings: tuple[FinalCandidateJudgeFinding, ...] = Field(min_length=1)
    reasons: tuple[str, ...] = Field(min_length=1)
    limitations: tuple[str, ...] = Field(min_length=1)
    critical_counterevidence: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = Field(min_length=1)
    source_role: Literal["evidence-judge"] = "evidence-judge"

    @model_validator(mode="after")
    def validate_recommendation(self) -> Self:
        candidate_ids = [item.candidate_id for item in self.candidate_findings]
        if len(candidate_ids) != len(set(candidate_ids)):
            raise ValueError("Gate 5 Judge candidate findings must be unique")
        if self.verdict != "ready-to-ask" and (self.recommendation == "APPROVE_WET_LAB_HANDOFF"):
            raise ValueError("insufficient or rejected evidence cannot recommend handoff")
        return self


class Gate5ApprovalAuthority(FrozenContract):
    """Exact Scientist response consumed to assemble one Wet-lab Handoff."""

    authority_id: str = Field(pattern=ID_PATTERN)
    gate5_card_id: str = Field(pattern=SHA256_PATTERN)
    final_review_dossier_sha256: str = Field(pattern=SHA256_PATTERN)
    primary_candidate_ids: tuple[str, ...] = Field(min_length=1)
    backup_candidate_ids: tuple[str, ...] = ()
    authority_scope: Literal["scientist-approved", "test-only-control-flow"]
    human_actor: str = Field(min_length=1, max_length=256)
    authorizes_wet_lab_handoff: bool

    @model_validator(mode="after")
    def validate_authority(self) -> Self:
        selected = self.primary_candidate_ids + self.backup_candidate_ids
        if len(selected) != len(set(selected)):
            raise ValueError("Gate 5 authority contains duplicate candidate identities")
        if self.authority_scope == "test-only-control-flow":
            if self.authorizes_wet_lab_handoff:
                raise ValueError("test-only Gate 5 authority cannot authorize experiments")
        elif not self.authorizes_wet_lab_handoff:
            raise ValueError("Scientist Gate 5 approval must authorize the handoff")
        return self


class WetLabHandoffItem(FrozenContract):
    candidate_id: str = Field(pattern=ID_PATTERN)
    selection_class: Literal["primary", "backup"]
    selection_rank: int = Field(ge=1)
    sequence: str = Field(pattern=r"^[ACDEFGHIKLMNPQRSTVWY]+$")
    candidate_dossier_sha256: str = Field(pattern=SHA256_PATTERN)
    global_development_rank: int = Field(ge=1)
    metrics: tuple[MetricObservation, ...]
    artifact_refs: tuple[ArtifactRef, ...] = Field(min_length=1)
    known_concerns: tuple[str, ...] = Field(min_length=1)
    uncertainties: tuple[str, ...] = Field(min_length=1)


class WetLabHandoffPackage(FrozenContract):
    """Auditable experimental-planning handoff; it never records an order."""

    schema_version: Literal["0.1"] = "0.1"
    project_id: str = Field(pattern=ID_PATTERN)
    campaign_id: str = Field(pattern=ID_PATTERN)
    final_review_dossier_sha256: str = Field(pattern=SHA256_PATTERN)
    approval_authority: Gate5ApprovalAuthority
    context: ScientificContextReferences
    candidates: tuple[WetLabHandoffItem, ...] = Field(min_length=1)
    evidence_refs: tuple[str, ...] = Field(min_length=1)
    handoff_status: Literal[
        "ready-for-downstream-experimental-planning",
        "validation-only-not-authorized-for-experiment",
    ]
    ordering_status: Literal["not-ordered"] = "not-ordered"
    full_ranked_pool_preserved: Literal[True] = True

    @model_validator(mode="after")
    def validate_handoff(self) -> Self:
        authority = self.approval_authority
        if authority.final_review_dossier_sha256 != self.final_review_dossier_sha256:
            raise ValueError("Wet-lab Handoff authority is bound to a different review")
        expected = authority.primary_candidate_ids + authority.backup_candidate_ids
        observed = tuple(item.candidate_id for item in self.candidates)
        if observed != expected:
            raise ValueError("Wet-lab Handoff candidate order differs from Gate 5 authority")
        primary_ranks = [
            item.selection_rank for item in self.candidates if item.selection_class == "primary"
        ]
        backup_ranks = [
            item.selection_rank for item in self.candidates if item.selection_class == "backup"
        ]
        if primary_ranks != list(range(1, len(primary_ranks) + 1)):
            raise ValueError("Wet-lab primary ranks must be contiguous")
        if backup_ranks != list(range(1, len(backup_ranks) + 1)):
            raise ValueError("Wet-lab backup ranks must be contiguous")
        expected_status = (
            "ready-for-downstream-experimental-planning"
            if authority.authorizes_wet_lab_handoff
            else "validation-only-not-authorized-for-experiment"
        )
        if self.handoff_status != expected_status:
            raise ValueError("Wet-lab Handoff status contradicts its authority")
        return self
