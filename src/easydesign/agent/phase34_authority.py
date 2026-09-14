"""Runtime Gate 3 -> Pilot authority; LLMs never call these approval producers."""

from __future__ import annotations

from typing import Any, Literal

from easydesign.core import (
    ArtifactRef,
    DecisionRecord,
    canonical_model_sha256,
    load_model,
    sha256_file,
)
from easydesign.orchestration.config import PredictionBackend
from easydesign.orchestration.research import load_strategy

from .contracts import AgentBoundaryError, DecisionCard, DecisionOutcome
from .design import DesignBridge
from .phase34_contracts import ScientistPilotAuthority
from .phase34_plan import (
    ApprovedGate3Context,
    BoundPilotPlan,
    compiled_records,
    project_arm_intents,
)
from .session_store import identity


def plan_for_design(
    bridge: Any,
    proposal: dict[str, Any],
    *,
    prediction_backend: PredictionBackend,
    mode: Literal["formal-pilot", "validation-micro"] = "formal-pilot",
    execution_allocations: dict[str, int] | None = None,
    parent_gate4_card_id: str | None = None,
) -> BoundPilotPlan:
    snapshot = bridge.design_snapshot(proposal)
    if proposal["evaluation"]["status"] == "BLOCKED":
        raise AgentBoundaryError("Hard-invalid Design cannot authorize Pilot")
    strategy = load_strategy(
        bridge.project, ArtifactRef.model_validate(proposal["strategy_ref"]).verify(bridge.project)
    )
    records = compiled_records(bridge, proposal)
    site = bridge.approved_site()
    if site is None:
        raise AgentBoundaryError("Pilot requires the current approved Site")
    production = {r.strategy_id: r.candidates_per_strategy for r in records}
    if mode == "validation-micro" and execution_allocations is None:
        raise AgentBoundaryError("Micro validation needs an explicit bounded allocation")
    target_context = {
        "objective": snapshot["proposal"]["objective"],
        "context_rationale": snapshot["proposal"]["context_rationale"],
        "scaffold_cdr_rationale": snapshot["proposal"]["scaffold_cdr_rationale"],
        "selected_site": site["proposal"]["intent"],
        "gpcr_exclusions": snapshot["upstream"].get("gpcr_exclusions"),
    }
    return BoundPilotPlan(
        project_id=bridge.project_id,
        project_binding=identity(bridge.binding()),
        target_binding=bridge.target_state()["binding"],
        hotspot_sha256=site["hotspots_sha256"],
        design_proposal_id=proposal["proposal_id"],
        design_snapshot_sha256=snapshot["evidence_id"],
        strategy_sha256=proposal["strategy_ref"]["sha256"],
        compiled_manifest_sha256=proposal["compiled_ref"]["sha256"],
        prediction_backend=prediction_backend,
        mode=mode,
        production_allocations=production,
        execution_allocations=execution_allocations or production,
        arms=project_arm_intents(strategy, records, target_context=target_context),
        parent_gate4_card_id=parent_gate4_card_id,
        validation_only=mode == "validation-micro",
    )


def pilot_review_card(bridge: Any, design_card: DecisionCard, plan: BoundPilotPlan) -> DecisionCard:
    """Add the executable Pilot scope to this Gate 3, not an extra scientific Gate."""
    if design_card.gate_type != "design-specification" or (
        design_card.project_id != plan.project_id
        or design_card.evidence_id != plan.design_snapshot_sha256
    ):
        raise AgentBoundaryError("Pilot plan belongs to a different Design card")
    if plan.mode != "formal-pilot":
        raise AgentBoundaryError("Micro validation cannot masquerade as scientific Gate 3 approval")
    digest = canonical_model_sha256(plan)
    card = design_card.model_copy(
        update={
            "card_id": identity({"design_card": design_card.card_id, "pilot_plan": digest}),
            "scientific_summary": {
                **design_card.scientific_summary,
                "pilot_plan": plan.model_dump(mode="json"),
                "pilot_plan_sha256": digest,
            },
            "action": "Approve this exact Design and Pilot plan to authorize one formal Pilot, "
            "or revise/reject. No Scale or wet-lab work is authorized.",
        }
    )
    bridge.store.save_card(bridge.thread, card)
    return card


def accept_pilot_plan(bridge: Any, card: DecisionCard) -> ScientistPilotAuthority:
    """Verify current facts, apply existing Design freeze, then publish bound authority."""
    with bridge.store.writer():
        if bridge.store.card(bridge.thread, card.card_id) != card:
            raise AgentBoundaryError("Pilot card differs from its runtime copy")
        response = bridge.store.response(bridge.thread, card.card_id)
        if response is None:
            raise AgentBoundaryError(
                "Pilot authority requires an explicit Scientist Gate 3 decision"
            )
        outcome = DecisionOutcome.model_validate(response["outcome"])
        if outcome.action not in {"APPROVE", "OVERRIDE"}:
            raise AgentBoundaryError("This Gate 3 response does not authorize Pilot")
        plan = BoundPilotPlan.model_validate(card.scientific_summary.get("pilot_plan"))
        if card.scientific_summary.get("pilot_plan_sha256") != canonical_model_sha256(plan):
            raise AgentBoundaryError("Pilot plan changed after review")
        proposal = bridge.current_design()
        if proposal is None:
            approved = bridge.approved_design()
            proposal = approved["proposal"] if approved else None
        if (
            proposal is None
            or plan_for_design(
                bridge,
                proposal,
                prediction_backend=plan.prediction_backend,
                parent_gate4_card_id=plan.parent_gate4_card_id,
            )
            != plan
        ):
            raise AgentBoundaryError("Pilot plan is stale or belongs to another Target/Site/Design")
        # The original Phase 2 adapter independently verifies and applies the exact human outcome.
        # Its existing command journal owns freeze recovery.
    DesignBridge.apply_decision(bridge, card)
    approved = bridge.approved_design()
    if approved is None or approved["card_id"] != card.card_id:
        raise AgentBoundaryError("Pilot requires the applied current Gate 3 approval")
    record = load_model(
        ArtifactRef.model_validate(approved["approval_ref"]).verify(bridge.project), DecisionRecord
    )
    authority = ScientistPilotAuthority(
        authority_id=identity(
            {
                "gate3": card.card_id,
                "outcome": outcome.model_dump(mode="json"),
                "plan": canonical_model_sha256(plan),
            }
        ),
        upstream_gate3_card_id=card.card_id,
        gate3_outcome_id=identity(outcome.model_dump(mode="json")),
        outcome=outcome.action,
        human_actor=outcome.human_actor,
        approved_at=record.approved_at,
        pilot_plan=plan,
    )
    context = ApprovedGate3Context(
        project_id=bridge.project_id,
        gate3_card_id=card.card_id,
        gate3_outcome_sha256=authority.gate3_outcome_id,
        target_identity=plan.target_binding,
        target_bundle_sha256=sha256_file(bridge.target_state()["bundle_path"]),
        site_intent_sha256=identity(bridge.approved_site()["proposal"]["intent"]),
        strategy_sha256=plan.strategy_sha256,
        compiled_manifest_sha256=plan.compiled_manifest_sha256,
        execution_plan_sha256=canonical_model_sha256(plan),
        planned_candidates=sum(plan.production_allocations.values()),
        plan=plan,
        evidence_refs=tuple(card.evidence_refs),
    )
    bridge.publish_contract(
        kind="phase34-approved-gate3", contract=context, dependencies={"gate3": card.card_id}
    )
    bridge.publish_contract(
        kind="phase34-pilot-authority",
        contract=authority,
        dependencies={"context": canonical_model_sha256(context)},
    )
    return authority


def verify_pilot_authority(bridge: Any, authority: ScientistPilotAuthority) -> BoundPilotPlan:
    """Call again immediately before execution; a saved DTO alone is not authority."""
    plan = authority.pilot_plan
    if plan is None or plan.project_id != bridge.project_id:
        raise AgentBoundaryError("Pilot authority lacks a bound current project/plan")
    approved = bridge.approved_design()
    if approved is None or approved["card_id"] != authority.upstream_gate3_card_id:
        raise AgentBoundaryError("Pilot authority no longer matches current Gate 3")
    response = bridge.store.response(approved["thread"], authority.upstream_gate3_card_id)
    if (
        response is None
        or not response["delivered"]
        or (identity(response["outcome"]) != authority.gate3_outcome_id)
    ):
        raise AgentBoundaryError("Pilot authority has no matching applied human outcome")
    published = bridge.load_contract(
        kind="phase34-pilot-authority", contract_type=ScientistPilotAuthority
    )
    if (
        published != authority
        or plan_for_design(
            bridge,
            approved["proposal"],
            prediction_backend=plan.prediction_backend,
            parent_gate4_card_id=plan.parent_gate4_card_id,
        )
        != plan
    ):
        raise AgentBoundaryError("Pilot execution changed its approved Design arms or scope")
    return plan
