"""Small agent DTOs. Scientific identities remain owned by the v2 contracts."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, model_validator

ShortText = Annotated[str, Field(min_length=1, max_length=1500)]
Identifier = Annotated[str, Field(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,127}$")]


class StrictDTO(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class TargetTask(StrictDTO):
    question: ShortText
    user_goal: ShortText
    current_user_message: ShortText
    current_revision_instruction: ShortText | None = None
    revision_of_card_id: Identifier | None = None
    project_id: Identifier
    run_id: Identifier | None = None
    evidence_id: Identifier | None = None
    evidence_refs: list[str] = Field(default_factory=list, max_length=64)


class TargetAssessment(StrictDTO):
    observed_facts: list[ShortText] = Field(max_length=12)
    unresolved_identity: list[ShortText] = Field(max_length=8)
    selectable_options: list[Identifier] = Field(max_length=32)
    evidence_refs: list[str] = Field(max_length=64)
    limitations: list[ShortText] = Field(min_length=1, max_length=8)
    recommended_action: ShortText


GateType = Literal[
    "target-structure", "site-hotspot", "design-specification", "pilot-promotion", "wet-lab-handoff"
]
ScientificStatus = Literal["SUPPORTED", "DISCOURAGED", "BLOCKED"]
DecisionAction = Literal["APPROVE", "REVISE", "REJECT", "OVERRIDE"]


class OptionRecommendation(StrictDTO):
    """A scientific opinion about one option; only runtime can establish hard blocks."""

    option_id: Identifier
    status: Literal["SUPPORTED", "DISCOURAGED"]
    warnings: list[ShortText] = Field(default_factory=list, max_length=4)
    alternative: ShortText | None = None

    @model_validator(mode="after")
    def explain_discouragement(self) -> OptionRecommendation:
        if self.status == "DISCOURAGED" and (not self.warnings or not self.alternative):
            raise ValueError("DISCOURAGED requires warnings and a recommended alternative")
        return self


class JudgeVerdict(StrictDTO):
    """Scientific opinion only; deterministic bindings never come from the model."""

    verdict: Literal["ready-to-ask", "insufficient", "reject", "assessed"]
    reasons: list[ShortText] = Field(min_length=1, max_length=8)
    limitations: list[ShortText] = Field(min_length=1, max_length=8)
    recommendation: OptionRecommendation | None = None


class EvidenceBinding(StrictDTO):
    evidence_id: Identifier
    request_identity: str | None = Field(default=None, max_length=64)
    evidence_refs: tuple[str, ...] = Field(min_length=1, max_length=64)


class EvidenceAssessment(JudgeVerdict, EvidenceBinding):
    assessment_id: Identifier
    source_role: Literal["evidence-judge"] = "evidence-judge"


class TargetProvenance(StrictDTO):
    origin: ShortText | None = None
    source: ShortText | None = None
    selected_chain: ShortText | None = None
    fallback_used: StrictBool | None = None


class ApplyDecision(StrictDTO):
    assessment_id: Identifier
    option_id: Identifier


class EvidenceQuery(StrictDTO):
    run_id: Identifier | None = None


class EmptyArguments(StrictDTO):
    pass


class DecisionProposal(StrictDTO):
    """Common scientific decision semantics shared by domain-specific adapters."""

    gate_type: GateType = "target-structure"
    owner_specialist: str = "target-intelligence"
    judge_status: ScientificStatus = "SUPPORTED"
    warnings: list[ShortText] = Field(default_factory=list, max_length=24)
    alternative: ShortText | None = None
    parent_card_id: Identifier | None = None


class DecisionCard(DecisionProposal):
    card_id: Identifier
    assessment_id: Identifier
    project_id: Identifier
    run_id: Identifier
    request_identity: str
    evidence_id: Identifier
    question: str
    option_id: Identifier
    options: list[dict[str, object]]
    evidence_refs: list[str]
    limitations: list[str]
    scientific_summary: dict[str, object] = Field(default_factory=dict)
    action: str = "Approve the selected chain and resume target preparation in the same run."


class DecisionOutcome(StrictDTO):
    """Persisted human input, constructed at the CLI boundary, never model-authored."""

    card_id: Identifier
    action: DecisionAction
    human_actor: ShortText
    human_instruction: ShortText | None = None
    optional_reason: ShortText | None = None
    explicit_acknowledgement: ShortText | None = None
    recorded_warnings: list[ShortText] = Field(default_factory=list, max_length=24)
    source_role: Literal["human-cli"] = "human-cli"

    @model_validator(mode="after")
    def validate_steering(self) -> DecisionOutcome:
        if not self.human_actor.strip():
            raise ValueError("An identified human is required")
        if self.action == "REVISE":
            if not self.human_instruction or not self.human_instruction.strip():
                raise ValueError("REVISE requires a human_instruction")
        elif self.human_instruction is not None:
            raise ValueError("Only REVISE accepts a human_instruction")
        if self.action == "OVERRIDE":
            if not self.explicit_acknowledgement or not self.explicit_acknowledgement.strip():
                raise ValueError("OVERRIDE requires explicit acknowledgement of the warnings")
            if not self.optional_reason or not self.optional_reason.strip():
                raise ValueError("OVERRIDE requires a recorded human rationale")
            if not self.recorded_warnings:
                raise ValueError("OVERRIDE requires recorded warnings")
        elif self.explicit_acknowledgement is not None:
            raise ValueError("Only OVERRIDE accepts explicit acknowledgement")
        return self


class AgentBoundaryError(RuntimeError):
    """A rejected action, incompatible session, or evidence boundary violation."""


class ReconciliationRequired(AgentBoundaryError):
    """An uncertain old-world submission must not be replayed automatically."""
