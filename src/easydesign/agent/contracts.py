"""Small agent DTOs. Scientific identities remain owned by the v2 contracts."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

ShortText = Annotated[str, Field(min_length=1, max_length=1500)]
Identifier = Annotated[str, Field(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,127}$")]


class StrictDTO(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class TargetTask(StrictDTO):
    question: ShortText
    user_goal: ShortText
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


class JudgeVerdict(StrictDTO):
    """Model-produced fields; runtime supplies assessment ID and source role."""

    evidence_id: Identifier
    request_identity: str | None = Field(default=None, max_length=64)
    evidence_refs: list[str] = Field(min_length=1, max_length=64)
    verdict: Literal["ready-to-ask", "insufficient", "reject", "assessed"]
    reasons: list[ShortText] = Field(min_length=1, max_length=8)
    limitations: list[ShortText] = Field(min_length=1, max_length=8)


class EvidenceAssessment(JudgeVerdict):
    assessment_id: Identifier


class ApplyDecision(StrictDTO):
    assessment_id: Identifier
    option_id: Identifier


class EvidenceQuery(StrictDTO):
    run_id: Identifier | None = None


class EmptyArguments(StrictDTO):
    pass


class DecisionCard(StrictDTO):
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
    action: str = "Approve the selected chain and resume target preparation in the same run."


class AgentBoundaryError(RuntimeError):
    """A rejected action, incompatible session, or evidence boundary violation."""


class ReconciliationRequired(AgentBoundaryError):
    """An uncertain old-world submission must not be replayed automatically."""
