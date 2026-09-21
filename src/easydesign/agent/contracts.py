"""Small agent DTOs. Scientific identities remain owned by the v2 contracts."""

from __future__ import annotations

import json
from typing import Annotated, Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    SerializerFunctionWrapHandler,
    StrictBool,
    model_serializer,
    model_validator,
)

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


class TargetInterpretation(StrictDTO):
    """Model opinion only. Runtime attaches identity, facts, options and source refs."""

    interpretation: list[ShortText] = Field(min_length=1, max_length=8)
    unresolved_identity: list[ShortText] = Field(max_length=8)
    limitations: list[ShortText] = Field(min_length=1, max_length=8)
    recommended_option: Identifier | None = None
    recommended_action: ShortText


class TargetChainFacts(StrictDTO):
    auth_chain: str
    label_chain: str | None = None
    construct_length: int | None = Field(default=None, ge=1)
    observed_length: int = Field(ge=0)
    mapping_status: str | None = None
    relationship: str | None = None
    missing_construct_positions: list[int] = Field(default_factory=list)


class TargetFacts(StrictDTO):
    canonical_accession: str | None = None
    canonical_length: int | None = Field(default=None, ge=1)
    chains: list[TargetChainFacts] = Field(default_factory=list, max_length=32)
    selected_chain: str | None = None
    authority: str = "Verified source and unchanged deterministic identity/mapping services"


class TargetAssessment(StrictDTO):
    """Runtime-produced envelope, never exposed as a model submission schema."""

    hard_facts: TargetFacts
    interpretation: TargetInterpretation
    source_evidence_id: str
    evidence_refs: list[str]
    selectable_options: list[str]


GateType = Literal[
    "target-structure", "site-hotspot", "design-specification", "pilot-promotion", "wet-lab-handoff"
]
ScientificStatus = Literal["SUPPORTED", "DISCOURAGED", "BLOCKED"]
DecisionAction = Literal["APPROVE", "REVISE", "REJECT", "OVERRIDE"]


class OptionRecommendation(StrictDTO):
    """A scientific opinion about one option; only runtime can establish hard blocks."""

    option_id: Identifier = Field(
        description="Scientific Gate option ID: use 'site' for Site/Hotspot, 'design' for Design, "
        "or an actual supplied chain option for Target. Never use a candidate/site-region ID."
    )
    status: Literal["SUPPORTED", "DISCOURAGED"]
    warnings: list[ShortText] = Field(default_factory=list, max_length=4)
    alternative: ShortText | None = None

    @model_validator(mode="after")
    def explain_discouragement(self) -> OptionRecommendation:
        if self.status == "DISCOURAGED" and (not self.warnings or not self.alternative):
            raise ValueError("DISCOURAGED requires warnings and a recommended alternative")
        return self


class SiteClaimCorrection(StrictDTO):
    """Independent qualification of an overstatement, never a replacement hard fact."""

    claim: str = Field(
        min_length=1,
        max_length=500,
        description="Exact excerpt from the current Site interpretation.",
    )
    qualification: str = Field(
        min_length=1,
        max_length=800,
        description="Corrected, evidence-proportionate interpretation and remaining risk or "
        "downstream validation. Do not waive a factual error or hard constraint.",
    )


class JudgeFactClaim(StrictDTO):
    """An optional exact assertion about an addressed runtime fact, never a fact update."""

    fact_ref: str = Field(min_length=1, max_length=128)
    field: str | None = Field(
        default=None,
        max_length=128,
        description="One direct field of the referenced object, e.g. canonical_occurrences "
        "or location. Null means the whole value. No JSON paths or nested indices.",
    )
    value: JsonValue = Field(description="Exact JSON value of that field or whole fact.")


class JudgeVerdict(StrictDTO):
    """Scientific opinion only; deterministic bindings never come from the model."""

    verdict: Literal["ready-to-ask", "insufficient", "reject", "assessed"] = Field(
        description="Check selected and alternative claims. Reject hard factual contradictions "
        "or invalid sites. At Site Gate 2, correctable overstatement and unperformed downstream "
        "binder validation alone do not require reject: use ready-to-ask with explicit "
        "site_claim_corrections, risks and limitations if the hotspot remains reasonable. "
        "Use insufficient only when missing evidence prevents a meaningful decision at the "
        "current Gate. assessed is only for a completed Target-only bundle."
    )
    reasons: list[ShortText] = Field(min_length=1, max_length=8)
    limitations: list[ShortText] = Field(min_length=1, max_length=8)
    recommendation: OptionRecommendation | None = None
    site_claim_corrections: list[SiteClaimCorrection] = Field(
        default_factory=list,
        max_length=8,
        description="Site Gate 2 only: explicit non-blocking corrections to unsupported "
        "absolute access/causal claims. Preserve original claims for audit; these independent "
        "qualifications accompany the human card and downstream warnings. Empty if unnecessary.",
    )

    fact_refs: list[str] = Field(
        default_factory=list,
        max_length=8,
        description="Site packets only: supplied revision:kind:index fact references.",
    )
    fact_claims: list[JudgeFactClaim] = Field(
        default_factory=list,
        max_length=4,
        description="Site packets only: optional exact factual assertions, checked against "
        "runtime values. Prefer references alone when interpreting evidence.",
    )


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
    assessment_id: Identifier | None = None
    option_id: Identifier
    review_failure_id: Identifier | None = None
    review_not_requested: StrictBool = False

    @model_validator(mode="after")
    def one_review_record(self) -> ApplyDecision:
        supplied = sum(
            (
                self.assessment_id is not None,
                self.review_failure_id is not None,
                self.review_not_requested,
            )
        )
        if supplied != 1:
            raise ValueError(
                "Provide exactly one assessment, review failure, or explicit optional-review record"
            )
        site_only_review = self.review_failure_id is not None or self.review_not_requested
        if site_only_review and self.option_id != "site":
            raise ValueError("Optional or unavailable review belongs only to Site Gate 2")
        return self


class EvidenceQuery(StrictDTO):
    run_id: Identifier | None = None


class EmptyArguments(StrictDTO):
    pass


class DecisionProposal(StrictDTO):
    """Common scientific decision semantics shared by domain-specific adapters."""

    gate_type: GateType = "target-structure"
    owner_specialist: str = "target-intelligence"
    judge_status: ScientificStatus | None = "SUPPORTED"
    warnings: list[ShortText] = Field(default_factory=list, max_length=24)
    alternative: ShortText | None = None
    parent_card_id: Identifier | None = None


class DecisionCard(DecisionProposal):
    card_id: Identifier
    assessment_id: Identifier | None
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

    @model_validator(mode="after")
    def review_identity(self) -> DecisionCard:
        if self.assessment_id is None:
            review = self.scientific_summary.get("independent_review", {})
            if (
                self.gate_type in {"pilot-promotion", "wet-lab-handoff"}
                and self.judge_status in {None, "BLOCKED"}
                and isinstance(review, dict)
                and review.get("availability") == "not-requested"
                and review.get("optional") is True
            ):
                return self
            if (
                self.gate_type == "site-hotspot"
                and self.judge_status is None
                and isinstance(review, dict)
                and review.get("availability") == "not-requested"
                and review.get("optional") is True
                and review.get("policy_id")
            ):
                return self
            if (
                self.gate_type not in {"site-hotspot", "pilot-promotion", "wet-lab-handoff"}
                or (
                    self.judge_status is not None
                    and not (
                        self.gate_type in {"pilot-promotion", "wet-lab-handoff"}
                        and self.judge_status == "BLOCKED"
                    )
                )
                or not isinstance(review, dict)
                or review.get("availability") != "unavailable"
                or not review.get("failure_record_id")
            ):
                raise ValueError(
                    "Missing assessment requires an explicit independent review failure"
                )
        elif self.judge_status is None:
            raise ValueError("A completed Judge assessment requires its scientific status")
        return self


class DecisionOutcome(StrictDTO):
    """Persisted human input, constructed at the CLI boundary, never model-authored."""

    card_id: Identifier
    action: DecisionAction
    human_actor: ShortText
    human_instruction: ShortText | None = None
    revision_gate: GateType | None = None
    optional_reason: ShortText | None = None
    explicit_acknowledgement: ShortText | None = None
    selected_option_id: Identifier | None = None
    recorded_warnings: list[ShortText] = Field(default_factory=list, max_length=24)
    source_role: Literal["human-cli"] = "human-cli"

    @model_serializer(mode="wrap")
    def serialize_choice(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        value: dict[str, Any] = handler(self)
        if self.selected_option_id is None:
            value.pop("selected_option_id", None)
        return value

    @model_validator(mode="after")
    def validate_steering(self) -> DecisionOutcome:
        if self.selected_option_id is not None and self.action not in {"APPROVE", "OVERRIDE"}:
            raise ValueError("Option selection accompanies APPROVE or OVERRIDE only")
        if not self.human_actor.strip():
            raise ValueError("An identified human is required")
        if self.action == "REVISE":
            if not self.human_instruction or not self.human_instruction.strip():
                raise ValueError("REVISE requires a human_instruction")
        elif self.human_instruction is not None:
            raise ValueError("Only REVISE accepts a human_instruction")
        if self.revision_gate is not None and self.action != "REVISE":
            raise ValueError("Only REVISE accepts an explicit revision Gate")
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

    category = "HARD_BOUNDARY_VIOLATION"


class TargetJobTerminalFailure(AgentBoundaryError):
    """A bound Target worker ended unsuccessfully; its persisted failure is authoritative."""

    category = "TARGET_JOB_TERMINAL_FAILURE"

    def __init__(self, failure: dict[str, Any]) -> None:
        self.failure = dict(failure)
        super().__init__(
            "TARGET_JOB_TERMINAL_FAILURE: "
            + json.dumps(self.failure, ensure_ascii=False, sort_keys=True)
        )


class ResearchConclusionMismatch(AgentBoundaryError):
    """A proposed evidence status conflicts with actual research state, not authority."""


class ResearchQuestionBindingMismatch(ResearchConclusionMismatch):
    """A question status is inconsistent with its Runtime-issued query bindings."""


class TargetRecommendationMismatch(AgentBoundaryError):
    """A typed Target opinion omitted or misnamed a Runtime-offered eligible option."""


class EvidenceRoleMismatch(ResearchConclusionMismatch):
    """A known source was assigned a claim strength above its Runtime-owned ceiling."""


class JudgeStageMismatch(AgentBoundaryError):
    """A typed Judge result is inadmissible for its current runtime-bound stage."""


class EvidenceCitationMismatch(AgentBoundaryError):
    """A known owned source was cited with the wrong passage or excerpt; no authority granted.

    ``repair_keys`` are Runtime-created identities for focused, already-read passage cards. They
    are deliberately independent of the model's bad excerpt so changing a typo cannot evade the
    one-repair-per-card boundary. Other citation failures remain unkeyed and retain the legacy
    single repair slot.
    """

    def __init__(self, message: str, *, repair_keys: list[str] | tuple[str, ...] = ()) -> None:
        self.repair_keys = tuple(sorted(set(repair_keys)))
        super().__init__(message)


class CanonicalReferenceMismatch(RuntimeError):
    """A verified inactive UniProt record names bounded replacement leads."""

    category = "RECOVERABLE_PREREQUISITE"

    def __init__(
        self,
        accession: str,
        reason_type: str,
        replacement_accessions: list[str] | tuple[str, ...],
    ) -> None:
        self.accession = accession
        self.reason_type = reason_type
        self.replacement_accessions = tuple(replacement_accessions)
        super().__init__(
            f"UniProt accession {accession} is inactive ({reason_type}) and cannot be used "
            "as a canonical reference."
        )

    def result(self) -> dict[str, Any]:
        return {
            "status": "REQUIRES_ACTION",
            "category": self.category,
            "error_code": "INACTIVE_CANONICAL_REFERENCE",
            "required_action": "research_evidence",
            "inactive_accession": self.accession,
            "identifier_resolution": {
                "status": "inactive",
                "type": self.reason_type,
                "replacement_accessions": list(self.replacement_accessions),
            },
            "message": (
                str(self)
                + " These replacement accessions are leads, not an automatic identity choice. "
                "Use deposited structure, species or strain evidence to disambiguate them, then "
                "select, acquire and read the chosen active UniProt record before proposing its "
                "exact source card. No configuration was changed and no successor was selected."
            ),
        }


class SourceSelectionRequired(RuntimeError):
    """One valid acquisition needs an explicit source selection before any I/O."""

    category = "RECOVERABLE_PREREQUISITE"

    def __init__(self, provider: str, identifier: str, evidence_need: str) -> None:
        super().__init__("Select this source for the current evidence need before deep acquisition")
        self.provider = provider
        self.identifier = identifier
        self.evidence_need = evidence_need

    def result(self) -> dict[str, str]:
        return {
            "status": "REQUIRES_ACTION",
            "category": self.category,
            "error_code": "SOURCE_NOT_SELECTED",
            "required_action": "select_evidence",
            "provider": self.provider,
            "identifier": self.identifier,
            "source_id": f"{self.provider}:{self.identifier.upper()}",
            "evidence_need": self.evidence_need,
            "message": (
                "Acquisition was not executed. If this source is relevant, call select_evidence "
                "with this provider/identifier, need=evidence_need, selection=SELECTED and your "
                "scientific reason; then retry acquisition. Otherwise leave it unacquired."
            ),
        }


class InvalidFieldProjection(RuntimeError):
    """Invalid navigation of an already authorized and verified evidence result."""

    category = "RECOVERABLE_TOOL_ARGUMENT"

    def result(self) -> dict[str, str]:
        return {
            "status": "REQUIRES_ACTION",
            "category": self.category,
            "error_code": "INVALID_FIELD_PROJECTION",
            "required_action": "read_evidence_result",
            "message": (
                f"{self} Use exactly one selector: field='key' for a top-level field, "
                "fields=['a','b'] for sibling fields, or path=['a','b'] for nested traversal. "
                "Choose existing keys from the supplied view; no evidence was changed."
            ),
        }


class ResearchQueryMismatch(InvalidFieldProjection):
    """Malformed research-tool arguments, before selection/acquisition or network IO."""

    def result(self) -> dict[str, str]:
        return {
            "status": "REQUIRES_ACTION",
            "category": self.category,
            "error_code": "INVALID_RESEARCH_QUERY",
            "required_action": "research_evidence",
            "message": str(self),
        }


class UnknownEvidenceResult(InvalidFieldProjection):
    """An unissued reference returns navigation only, never evidence or authority."""

    def __init__(self, handles: list[dict[str, str]], *, more_available: bool) -> None:
        super().__init__("Unknown result reference; no source content was read.")
        self.handles = handles
        self.more_available = more_available

    def result(self) -> dict[str, Any]:
        return {
            "status": "REQUIRES_ACTION",
            "category": self.category,
            "error_code": "UNKNOWN_EVIDENCE_RESULT",
            "required_action": "read_evidence_result",
            "available_result_refs": [h["original_ref"] for h in self.handles],
            "available_result_handles": self.handles,
            "more_results_available": self.more_available,
            "message": str(self)
            + " Use a short handle from available_result_handles as ref='result:N', "
            "instead of retyping the long ID. Handles identify immutable issuance records "
            "in this project; only the current role and execution can read them. "
            "The list contains recent owned references only, not suggested replacements. "
            "If the needed result is absent, repeat its original scientific read. "
            "Do not reconstruct IDs from memory; every new read still checks authority and hash.",
        }


class EvidenceRetrievalQueryMismatch(InvalidFieldProjection):
    """Malformed read-only retrieval syntax; no source view was consumed."""

    def result(self) -> dict[str, str]:
        return {
            "status": "REQUIRES_ACTION",
            "category": self.category,
            "error_code": "INVALID_RETRIEVAL_QUERY",
            "required_action": "retrieve_evidence",
            "message": str(self),
        }


class SiteResidueQueryMismatch(AgentBoundaryError, InvalidFieldProjection):
    """Unavailable labels in a read-only query; no hotspot is validated or changed."""

    category = "RECOVERABLE_TOOL_ARGUMENT"

    def result(self) -> dict[str, str]:
        return {
            "status": "REQUIRES_ACTION",
            "category": self.category,
            "error_code": "OBSERVED_DESIGN_LABEL_REQUIRED",
            "required_action": "read_site_evidence",
            "message": str(self),
        }


class SourceCardArgumentMismatch(InvalidFieldProjection):
    """An accession was supplied where a retrieved source-card identity is required."""

    def result(self) -> dict[str, str]:
        return {
            "status": "REQUIRES_ACTION",
            "category": self.category,
            "error_code": "SOURCE_CARD_REQUIRED",
            "required_action": "research_evidence",
            "message": str(self),
        }


class EvidenceCursorQueryMismatch(InvalidFieldProjection):
    """A verified current-thread cursor was used with a reworded question only."""

    def result(self) -> dict[str, str]:
        return {
            "status": "REQUIRES_ACTION",
            "category": self.category,
            "error_code": "CURSOR_QUERY_MISMATCH",
            "required_action": "retrieve_evidence",
            "message": str(self),
        }


class StaleEvidenceCursor(AgentBoundaryError, InvalidFieldProjection):
    """A known owned cursor is refused after its target/source selection changes."""

    category = "RECOVERABLE_TOOL_ARGUMENT"

    def result(self) -> dict[str, str]:
        return {
            "status": "REQUIRES_ACTION",
            "category": self.category,
            "error_code": "STALE_EVIDENCE_CURSOR",
            "required_action": "retrieve_evidence",
            "message": (
                "The target or selected evidence changed; this old cursor was rejected. "
                "No stale evidence was delivered. Omit cursor to start a current view, and "
                "select the source for the current need if the view requires selection. "
                "A prior selection is not current scientific authority."
            ),
        }


class ReconciliationRequired(AgentBoundaryError):
    """An uncertain old-world submission must not be replayed automatically."""
