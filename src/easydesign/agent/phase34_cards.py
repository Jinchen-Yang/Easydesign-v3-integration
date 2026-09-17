"""Scientist-visible downstream Gates with independent, degradable review."""

from __future__ import annotations

from typing import Any, Literal

from easydesign.core import canonical_model_sha256

from .contracts import AgentBoundaryError, DecisionCard, ScientificStatus
from .phase34_contracts import (
    FinalReviewDossier,
    PilotEvidenceDossier,
    ValidationExecutionAuthority,
)
from .phase34_opinions import DownstreamJudgeOpinion, DownstreamReviewFailure
from .session_store import identity


def _review(
    review: DownstreamJudgeOpinion | DownstreamReviewFailure,
    binding: str,
    gate: Literal["pilot-promotion", "wet-lab-handoff"],
) -> tuple[str | None, dict[str, Any], list[str], list[str]]:
    if isinstance(review, DownstreamReviewFailure):
        if review.input_binding != binding or review.gate != gate:
            raise AgentBoundaryError(
                "Unavailable review record belongs to a different Gate dossier"
            )
        return (
            None,
            {
                "availability": "unavailable",
                "failure_record_id": review.record_id,
                "attempts": review.attempts,
                "categories": review.categories,
            },
            [review.warning, *review.retained_warnings],
            [review.warning],
        )
    return (
        identity({"binding": binding, "opinion": review.model_dump(mode="json")}),
        {
            "availability": "completed",
            **review.model_dump(mode="json"),
        },
        list(review.warnings),
        list(review.uncertainties),
    )


def pilot_card(
    dossier: PilotEvidenceDossier,
    review: DownstreamJudgeOpinion | DownstreamReviewFailure | None = None,
    *,
    hard_errors: tuple[str, ...] = (),
    validation_only: bool = False,
) -> DecisionCard:
    binding = canonical_model_sha256(dossier)
    warnings: list[str]
    if review is None:
        assessment, review_state = None, {"availability": "not-requested", "optional": True}
        warnings, limitations = [], ["Optional independent second opinion was not requested."]
    else:
        assessment, review_state, warnings, limitations = _review(
            review, binding, "pilot-promotion"
        )
    proposal = dossier.proposed_interpretation
    test_only = validation_only or isinstance(
        dossier.execution_authority, ValidationExecutionAuthority
    )
    promote = proposal.outcome == "PROMOTE_TO_SCALE" and not hard_errors
    descriptions = {
        "PROMOTE_TO_SCALE": "Scale the exact reviewed strategies and allocation.",
        "RUN_ANOTHER_PILOT": "Prepare one new Pilot plan for explicit Scientist approval.",
        "REVISE_DESIGN": "Return to Design / Gate 3 with this diagnosis.",
        "REVISE_SITE": "Return to Site / Gate 2 while preserving verified Target evidence.",
        "STOP": "Stop this scientific campaign and retain its evidence.",
    }
    if test_only:
        warnings.insert(
            0, "Validation-only steering; no scientific promotion or production compute."
        )
    warnings.extend(hard_errors)
    # Only the runtime marks hard-invalid execution. The critic never chooses the route.
    status: ScientificStatus | None = (
        "BLOCKED" if hard_errors else "SUPPORTED" if assessment else None
    )
    default = "STOP" if hard_errors else proposal.outcome
    return DecisionCard(
        gate_type="pilot-promotion",
        owner_specialist="pilot-diagnosis",
        card_id=identity(
            {
                "dossier": binding,
                "review": review.model_dump(mode="json") if review else None,
                "hard": hard_errors,
                **({"validation_only": True} if validation_only else {}),
            }
        ),
        assessment_id=assessment,
        project_id=dossier.project_id,
        run_id=dossier.pilot_run_id,
        request_identity=binding,
        evidence_id=binding,
        question="根据 Pilot evidence，下一轮怎么走？",
        option_id=default,
        judge_status=status,
        warnings=warnings,
        limitations=limitations,
        evidence_refs=list(dossier.evidence_refs),
        options=[
            {
                "option_id": route,
                "label": route,
                "description": description,
                "eligible": promote
                if route == "PROMOTE_TO_SCALE"
                else (not hard_errors or route in {"REVISE_DESIGN", "REVISE_SITE", "STOP"}),
                "judge_status": "BLOCKED"
                if route == "PROMOTE_TO_SCALE" and not promote
                else "SUPPORTED",
            }
            for route, description in descriptions.items()
        ],
        scientific_summary={
            "independent_review": review_state,
            "diagnosis": dossier.diagnosis.model_dump(mode="json"),
            "arm_denominators": [a.model_dump(mode="json") for a in dossier.measurement.arms],
            "proposed_interpretation": proposal.model_dump(mode="json"),
            **(
                {"ranked_pilot": dossier.diagnosis.ranked_pilot}
                if dossier.diagnosis.ranked_pilot is not None
                else {}
            ),
            "scale_execution_intent": {
                "strategy_allocations": proposal.production_strategy_allocations,
                **(
                    {
                        "all_candidates_independently_predicted": False,
                        "independent_prediction": "optional-enrichment",
                        "scale_evidence_policy": "boltzgen-native-v1",
                    }
                    if dossier.measurement.native_evidence is not None
                    else {"all_candidates_independently_predicted": True}
                ),
                "inherits_approved_design_and_pilot_backend_policy": True,
                "authorizes_production_compute_on_approve": bool(promote and not test_only),
            },
            "execution_mode": dossier.measurement.execution.mode.value,
            "test_only_control_flow_fixture": test_only,
            "hard_errors": list(hard_errors),
        },
        action="Select one reviewed route. Recommendations do not execute transitions. "
        "Another Pilot requires a new explicit plan approval.",
    )


def final_card(
    dossier: FinalReviewDossier,
    review: DownstreamJudgeOpinion | DownstreamReviewFailure | None = None,
    *,
    hard_errors: tuple[str, ...] = (),
) -> DecisionCard:
    binding = canonical_model_sha256(dossier)
    warnings: list[str]
    if review is None:
        assessment, review_state = None, {"availability": "not-requested", "optional": True}
        warnings, limitations = [], ["Optional independent second opinion was not requested."]
    else:
        assessment, review_state, warnings, limitations = _review(
            review, binding, "wet-lab-handoff"
        )
    test_only = all(
        d.scientific_claim_scope == "development-evidence-only" for d in dossier.candidate_dossiers
    )
    if test_only:
        warnings.insert(0, "Validation-only panel; no experiment or ordering is authorized.")
    warnings.extend(hard_errors)
    status: ScientificStatus | None = (
        "BLOCKED" if hard_errors else "SUPPORTED" if assessment else None
    )
    return DecisionCard(
        gate_type="wet-lab-handoff",
        owner_specialist="final-selection",
        card_id=identity(
            {
                "dossier": binding,
                "review": review.model_dump(mode="json") if review else None,
                "hard": hard_errors,
            }
        ),
        assessment_id=assessment,
        project_id=dossier.project_id,
        run_id=dossier.campaign_id,
        request_identity=binding,
        evidence_id=binding,
        question="哪些最终候选进入 Wet Lab？",
        option_id="stop" if hard_errors else "wet-lab-panel",
        judge_status=status,
        warnings=warnings,
        limitations=limitations,
        evidence_refs=list(dossier.evidence_refs),
        options=[
            {
                "option_id": route,
                "label": label,
                "description": description,
                "eligible": not hard_errors or route != "wet-lab-panel",
                "judge_status": "BLOCKED"
                if hard_errors and route == "wet-lab-panel"
                else "SUPPORTED",
            }
            for route, label, description in (
                (
                    "wet-lab-panel",
                    "Approve primary and backup panel",
                    "Approve the exact displayed panel.",
                ),
                (
                    "revise-final-selection",
                    "Revise final selection",
                    "Revise panel membership or scientific rationale.",
                ),
                ("stop", "Stop", "Retain evidence without creating a handoff."),
            )
        ],
        scientific_summary={
            "independent_review": review_state,
            "proposed_selection": dossier.proposed_selection.model_dump(mode="json"),
            "filtering_policy": dossier.filtering_policy,
            "candidate_dossiers": [d.model_dump(mode="json") for d in dossier.candidate_dossiers],
            "test_only_control_flow_fixture": test_only,
            "hard_errors": list(hard_errors),
        },
        action="Select the exact primary/backup panel or request revision. "
        "Validation approval remains validation-only; no orders are placed.",
    )
