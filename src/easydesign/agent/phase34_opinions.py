"""Small scientific opinions; no model-written execution or approval fields."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field, model_validator

from .contracts import Identifier, JudgeFactClaim, StrictDTO
from .phase34_contracts import Gate4Outcome

Brief = Annotated[str, Field(min_length=1, max_length=450)]


class ArmHypothesisFinding(StrictDTO):
    arm_id: Identifier
    hypothesis_support: Literal["SUPPORTED", "PARTIALLY_SUPPORTED", "WEAKENED", "UNRESOLVED"]
    observations: list[Brief] = Field(min_length=1, max_length=3)
    interpretation: Brief
    alternative_explanation: Brief


class PilotDiagnosisOpinion(StrictDTO):
    key_observations: list[Brief] = Field(min_length=1, max_length=5)
    arm_findings: list[ArmHypothesisFinding] = Field(min_length=1, max_length=21)
    arm_comparisons: list[Brief] = Field(min_length=1, max_length=4)
    operational_confounders: list[Brief] = Field(min_length=1, max_length=4)
    uncertainty: list[Brief] = Field(min_length=1, max_length=4)
    next_discriminating_experiment: list[Brief] = Field(min_length=1, max_length=3)
    recommended_action: Gate4Outcome
    selected_strategy_ids: list[Identifier] = Field(default_factory=list, max_length=21)
    scale_allocations: dict[str, int] = Field(default_factory=dict)
    supporting_candidate_ids: list[Identifier] = Field(default_factory=list, max_length=30)
    rationale: Brief

    @model_validator(mode="after")
    def unique_arm_findings(self) -> PilotDiagnosisOpinion:
        ids = [f.arm_id for f in self.arm_findings]
        if len(ids) != len(set(ids)):
            raise ValueError("Each Design arm must have a single hypothesis finding")
        if self.recommended_action != "PROMOTE_TO_SCALE" and (
            self.selected_strategy_ids or self.scale_allocations
        ):
            raise ValueError("Only a Scale recommendation carries a proposed allocation")
        return self


class FinalSelectionOpinion(StrictDTO):
    primary_candidate_ids: list[Identifier] = Field(min_length=1, max_length=30)
    backup_candidate_ids: list[Identifier] = Field(default_factory=list, max_length=30)
    selection_rationale: list[Brief] = Field(min_length=1, max_length=5)
    major_risks: list[Brief] = Field(min_length=1, max_length=4)
    diversity_coverage: list[Brief] = Field(min_length=1, max_length=4)
    unresolved_questions: list[Brief] = Field(min_length=1, max_length=4)
    selection_gap_reason: Brief | None = None


class DownstreamJudgeOpinion(StrictDTO):
    """Critique the submitted interpretation/panel, without selecting or reranking."""

    review: Literal["NO_MATERIAL_ISSUE", "CONCERNS"]
    brief_rationale: Brief
    warnings: list[Brief] = Field(default_factory=list, max_length=3)
    uncertainties: list[Brief] = Field(min_length=1, max_length=3)
    overclaim_corrections: list[Brief] = Field(default_factory=list, max_length=3)
    fact_refs: list[str] = Field(default_factory=list, max_length=5)
    fact_claims: list[JudgeFactClaim] = Field(default_factory=list, max_length=4)


class DownstreamReviewFailure(StrictDTO):
    record_id: Identifier
    input_binding: Identifier
    gate: Literal["pilot-promotion", "wet-lab-handoff"]
    availability: Literal["unavailable"] = "unavailable"
    retained_warnings: list[str] = Field(default_factory=list)
    attempts: int = Field(ge=1, le=3)
    categories: list[Literal["MAX_TOKENS", "NO_SUBMISSION", "SCHEMA_ERROR", "PROVIDER_UNAVAILABLE"]]
    warning: str = (
        "Independent review unavailable; the Scientist must review the supplied evidence."
    )
