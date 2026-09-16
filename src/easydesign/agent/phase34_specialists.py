"""Two bounded cognitive nodes and a lightweight critic in the existing graph."""

from __future__ import annotations

from typing import Any, Literal

from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda

from easydesign.core import canonical_model_sha256

from .contracts import AgentBoundaryError
from .models import ModelConfig
from .phase34_cards import final_card, pilot_card
from .phase34_contracts import PilotEvidenceDossier
from .phase34_model import StructuredOpinionUnavailable, structured_opinion
from .phase34_opinions import (
    DownstreamJudgeOpinion,
    DownstreamReviewFailure,
    FinalSelectionOpinion,
    PilotDiagnosisOpinion,
)
from .phase34_science import bind_pilot_opinion, bind_selection_opinion
from .session_store import compact, identity


def downstream_specialist(
    bridge: Any,
    model: Any,
    config: ModelConfig,
    execution_id: str | None,
    role: str,
    goal: str,
) -> Any:
    """A compiled node has one submission schema, no action tools, no workflow vote."""

    async def run(_state: Any) -> dict[str, Any]:
        if execution_id is None:
            raise AgentBoundaryError("Scientific interpretation requires a current execution")
        from .harness import skill_root

        packet = bridge.downstream_packet(role)
        input_identity = packet["evidence_id"]
        packet["user_goal"] = goal

        def still_current() -> None:
            if bridge.downstream_packet(role)["evidence_id"] != input_identity:
                raise AgentBoundaryError(
                    "Downstream evidence changed while the opinion was running"
                )

        if role == "pilot-diagnosis":
            measurement, context, authority = bridge.pilot_inputs()
            refs = tuple(packet["evidence_refs"])

            def validate_pilot(opinion: PilotDiagnosisOpinion) -> Any:
                return bind_pilot_opinion(
                    measurement, context.plan.arms, opinion, evidence_refs=refs
                )

            prompt = (skill_root() / "pilot-diagnosis/SKILL.md").read_text()
            if measurement.native_evidence is not None:
                from .phase3_capacity import ranking_decision_view

                packet = ranking_decision_view(packet)
                prompt += (
                    "\n"
                    + (
                        skill_root() / "pilot-diagnosis/references/boltzgen-pilot-ranking.md"
                    ).read_text()
                )
            opinion = await structured_opinion(
                bridge=bridge,
                model=model,
                config=config,
                execution_id=execution_id,
                role="pilot-diagnosis",
                schema=PilotDiagnosisOpinion,
                packet=packet,
                prompt=prompt,
                validate=validate_pilot,
                delta_repair=measurement.native_evidence is not None,
            )
            diagnosis, recommendation = validate_pilot(opinion)
            still_current()
            dossier = PilotEvidenceDossier(
                project_id=bridge.project_id,
                pilot_run_id=packet["run_id"],
                upstream_fixture=context,
                execution_authority=authority,
                measurement=measurement,
                diagnosis=diagnosis,
                proposed_interpretation=recommendation,
                evidence_refs=refs,
            )
            bridge.publish_contract(
                kind="phase34-pilot-dossier",
                contract=dossier,
                dependencies={
                    "measurement": canonical_model_sha256(measurement),
                    "authority": authority.authority_id,
                },
            )
            # The Scientist can review immediately; a critic is an optional supplement.
            bridge.publish_gate_card(card=pilot_card(dossier), evidence_contract=dossier)
            result = {
                "status": "diagnosis-ready",
                "diagnosis": diagnosis.model_dump(mode="json", exclude={"design_arms"}),
                "recommendation": recommendation.model_dump(mode="json"),
            }
        elif role == "final-selection":
            from .phase4 import build_final_review_dossier

            pool, shortlist, inputs = bridge.selection_inputs()

            def validate_selection(opinion: FinalSelectionOpinion) -> Any:
                return bind_selection_opinion(
                    opinion,
                    inputs.candidate_dossiers,
                    primary_count=inputs.primary_count,
                    backup_count=inputs.backup_count,
                )

            selected = await structured_opinion(
                bridge=bridge,
                model=model,
                config=config,
                execution_id=execution_id,
                role="final-selection",
                schema=FinalSelectionOpinion,
                packet=packet,
                prompt=(skill_root() / "final-selection/SKILL.md").read_text(),
                validate=validate_selection,
            )
            proposal = validate_selection(selected)
            still_current()
            final = build_final_review_dossier(
                selection_revision_id=packet.get("scientist_revision_card_id"),
                project_id=bridge.project_id,
                pool=pool,
                shortlist=shortlist,
                candidate_dossiers=inputs.candidate_dossiers,
                proposed_selection=proposal,
                evidence_refs=tuple(packet["evidence_refs"]),
            )
            bridge.publish_contract(
                kind="phase34-final-review-dossier",
                contract=final,
                dependencies={
                    "pool": canonical_model_sha256(pool),
                    "shortlist": canonical_model_sha256(shortlist),
                },
            )
            result = {
                "status": "panel-ready",
                "proposal": proposal.model_dump(mode="json"),
            }
        elif role == "judge":
            reviewed = bridge.current_final_dossier() or bridge.current_pilot_dossier()
            if reviewed is None:
                raise AgentBoundaryError("No current downstream interpretation exists for review")
            gate: Literal["pilot-promotion", "wet-lab-handoff"] = (
                "pilot-promotion"
                if isinstance(reviewed, PilotEvidenceDossier)
                else "wet-lab-handoff"
            )
            review: DownstreamJudgeOpinion | DownstreamReviewFailure
            try:
                review = await structured_opinion(
                    bridge=bridge,
                    model=model,
                    config=config,
                    execution_id=execution_id,
                    role="judge",
                    schema=DownstreamJudgeOpinion,
                    packet=packet,
                    prompt="Provide a concise independent second opinion through "
                    "DownstreamJudgeOpinion immediately. No preamble. Check obvious overclaims, "
                    "neglected confounders, risk and diversity interpretation. Do not recompute "
                    "metrics, redo diagnosis, rerank the panel or select a workflow route. "
                    "Runtime facts own exact values; cite fact_refs. Normal scientific language "
                    "is allowed. Keep each field short; this is not a manuscript review.",
                )
            except StructuredOpinionUnavailable as failure:
                binding = canonical_model_sha256(reviewed)
                review = DownstreamReviewFailure.model_validate(
                    dict(
                        record_id=identity(
                            {
                                "dossier": binding,
                                "failures": failure.categories,
                                "execution": execution_id,
                            }
                        ),
                        input_binding=binding,
                        gate=gate,
                        categories=failure.categories,
                        retained_warnings=failure.retained_warnings,
                        attempts=len(failure.categories),
                    )
                )
            still_current()
            builder = pilot_card if isinstance(reviewed, PilotEvidenceDossier) else final_card
            card = builder(reviewed, review)
            bridge.publish_gate_card(card=card, evidence_contract=reviewed)
            result = {
                "status": "scientist-review-ready",
                "card_id": card.card_id,
                "independent_review": card.scientific_summary["independent_review"],
            }
        else:
            raise AgentBoundaryError("Unregistered downstream cognitive role")
        return {"messages": [AIMessage(content=compact(result))]}

    return RunnableLambda(run)


def downstream_aware_judge(
    bridge: Any,
    model: Any,
    config: ModelConfig,
    execution_id: str | None,
    goal: str,
    upstream: Any,
) -> Any:
    compact_judge = downstream_specialist(bridge, model, config, execution_id, "judge", goal)

    async def route(state: Any, config: Any = None) -> Any:
        action = bridge.next_downstream_action()
        runnable = (
            compact_judge
            if action and action.stage in {"pilot-review", "final-review"}
            else upstream
        )
        return await runnable.ainvoke(state, config=config)

    return RunnableLambda(route)
