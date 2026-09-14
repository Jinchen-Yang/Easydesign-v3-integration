"""Thin state/evidence bridge for the downstream v3 scientific loops."""

from __future__ import annotations

from typing import Any, TypeVar

from pydantic import BaseModel

from easydesign.core import canonical_model_sha256

from .contracts import AgentBoundaryError, DecisionCard, DecisionOutcome
from .design import DesignBridge
from .phase34_contracts import (
    Gate4PromotionAuthority,
    Gate5ApprovalAuthority,
    PilotEvidenceDossier,
    ValidationExecutionAuthority,
)
from .session_store import identity

ContractT = TypeVar("ContractT", bound=BaseModel)


class Phase34Bridge(DesignBridge):
    """Reuse the Phase 2 project artifacts and SessionStore for Phases 3/4."""

    def publish_contract(
        self,
        *,
        kind: str,
        contract: BaseModel,
        dependencies: dict[str, str],
    ) -> dict[str, Any]:
        """Publish one immutable contract and append one idempotent dependency event."""

        if not kind.startswith("phase34-"):
            raise AgentBoundaryError("downstream evidence kind must use the phase34 namespace")
        ref = self.persist(kind, contract.model_dump(mode="json"))
        current = self.project_latest(kind)
        event_payload = {
            "contract_type": type(contract).__name__,
            "contract_sha256": canonical_model_sha256(contract),
            "dependencies": dict(sorted(dependencies.items())),
            "ref": ref,
        }
        if current is not None and all(
            current.get(key) == value for key, value in event_payload.items()
        ):
            return ref
        self.store.event(self.thread, kind, event_payload)
        return ref

    def load_contract(
        self,
        *,
        kind: str,
        contract_type: type[ContractT],
        expected_sha256: str | None = None,
    ) -> ContractT:
        """Load the latest exact project contract through its verified ArtifactRef."""

        event = self.project_latest(kind)
        if event is None:
            raise AgentBoundaryError(f"No published downstream contract: {kind}")
        if event["contract_type"] != contract_type.__name__:
            raise AgentBoundaryError("downstream contract type changed")
        if expected_sha256 is not None and event["contract_sha256"] != expected_sha256:
            raise AgentBoundaryError("downstream contract identity is stale")
        contract = contract_type.model_validate(self.document(event["ref"]))
        if canonical_model_sha256(contract) != event["contract_sha256"]:
            raise AgentBoundaryError("published downstream contract hash changed")
        return contract

    def publish_gate_card(
        self,
        *,
        card: DecisionCard,
        evidence_contract: BaseModel,
    ) -> dict[str, Any]:
        """Persist a Gate 4/5 card in both the artifact and human-response ledgers."""

        if card.gate_type not in {"pilot-promotion", "wet-lab-handoff"}:
            raise AgentBoundaryError("Phase 3/4 bridge accepts only Gate 4 or Gate 5 cards")
        evidence_sha256 = canonical_model_sha256(evidence_contract)
        if card.request_identity != evidence_sha256 or card.evidence_id != evidence_sha256:
            raise AgentBoundaryError("downstream Gate card is not bound to its evidence")
        self.store.save_card(self.thread, card)
        return self.publish_contract(
            kind=f"phase34-{card.gate_type}-card",
            contract=card,
            dependencies={"evidence": evidence_sha256},
        )

    def decision_for(self, card: DecisionCard) -> DecisionOutcome | None:
        response = self.store.response(self.thread, card.card_id)
        return None if response is None else DecisionOutcome.model_validate(response["outcome"])

    def gate4_promotion_authority(
        self,
        *,
        dossier: PilotEvidenceDossier,
        card: DecisionCard,
        selected_strategy_ids: tuple[str, ...],
    ) -> Gate4PromotionAuthority:
        """Project an accepted PROMOTE card without expanding its compute authority."""

        dossier_sha256 = canonical_model_sha256(dossier)
        if card.gate_type != "pilot-promotion" or card.evidence_id != dossier_sha256:
            raise AgentBoundaryError("Gate 4 card is not bound to this Pilot dossier")
        outcome = self.decision_for(card)
        if outcome is None or outcome.action not in {"APPROVE", "OVERRIDE"}:
            raise AgentBoundaryError("Gate 4 promotion lacks an accepted Scientist response")
        selected_option = outcome.selected_option_id or card.option_id
        if selected_option != "PROMOTE_TO_SCALE":
            raise AgentBoundaryError("Scientist did not select PROMOTE_TO_SCALE")
        arm_ids = {item.strategy_id for item in dossier.measurement.arms}
        if not selected_strategy_ids or not set(selected_strategy_ids).issubset(arm_ids):
            raise AgentBoundaryError("Gate 4 promotion selects an unmeasured Pilot strategy")
        if selected_strategy_ids != dossier.proposed_interpretation.selected_strategy_ids:
            raise AgentBoundaryError("Scale strategies differ from the reviewed Gate 4 proposal")
        requested_scale_candidates = dossier.proposed_interpretation.requested_scale_candidates
        if requested_scale_candidates is None:
            raise AgentBoundaryError("Reviewed Gate 4 promotion has no Scale production intent")
        test_only = isinstance(dossier.execution_authority, ValidationExecutionAuthority)
        scale_intent = card.scientific_summary.get("scale_execution_intent")
        compute_authorized = isinstance(scale_intent, dict) and scale_intent == {
            "strategy_allocations": dossier.proposed_interpretation.production_strategy_allocations,
            "all_candidates_independently_predicted": True,
            "inherits_approved_design_and_pilot_backend_policy": True,
            "authorizes_production_compute_on_approve": True,
        }
        return Gate4PromotionAuthority(
            authority_id=identity(
                {
                    "card": card.card_id,
                    "outcome": outcome.model_dump(mode="json"),
                    "strategies": selected_strategy_ids,
                }
            ),
            gate4_card_id=card.card_id,
            pilot_dossier_sha256=dossier_sha256,
            selected_strategy_ids=selected_strategy_ids,
            requested_scale_candidates=requested_scale_candidates,
            production_strategy_allocations=(
                dossier.proposed_interpretation.production_strategy_allocations
            ),
            authority_scope=("test-only-control-flow" if test_only else "scientist-approved"),
            human_actor=outcome.human_actor,
            authorizes_scientific_scale=not test_only,
            authorizes_production_compute=not test_only and compute_authorized,
        )

    def gate4_route(self, card: DecisionCard) -> str:
        """Return the exact accepted Gate 4 route, including an eligible alternative."""

        if card.gate_type != "pilot-promotion":
            raise AgentBoundaryError("Gate 4 routing requires a Pilot promotion card")
        outcome = self.decision_for(card)
        if outcome is None or outcome.action not in {"APPROVE", "OVERRIDE"}:
            raise AgentBoundaryError("Gate 4 route lacks an accepted Scientist response")
        selected = outcome.selected_option_id or card.option_id
        allowed = {
            "PROMOTE_TO_SCALE",
            "RUN_ANOTHER_PILOT",
            "REVISE_DESIGN",
            "REVISE_SITE",
            "STOP",
        }
        if selected not in allowed:
            raise AgentBoundaryError("Gate 4 selected an unknown scientific route")
        return selected

    def gate5_approval_authority(
        self,
        *,
        final_review_dossier_sha256: str,
        card: DecisionCard,
        primary_candidate_ids: tuple[str, ...],
        backup_candidate_ids: tuple[str, ...],
    ) -> Gate5ApprovalAuthority:
        """Project the exact reviewed panel from an accepted Gate 5 response."""

        if card.gate_type != "wet-lab-handoff" or (card.evidence_id != final_review_dossier_sha256):
            raise AgentBoundaryError("Gate 5 card is not bound to this final review")
        outcome = self.decision_for(card)
        if outcome is None or outcome.action not in {"APPROVE", "OVERRIDE"}:
            raise AgentBoundaryError("Gate 5 handoff lacks an accepted Scientist response")
        selected_option = outcome.selected_option_id or card.option_id
        if selected_option != "wet-lab-panel":
            raise AgentBoundaryError("Scientist did not select the reviewed Wet-lab panel")
        summary = card.scientific_summary
        proposal = summary.get("proposed_selection")
        if (
            not isinstance(proposal, dict)
            or tuple(proposal.get("primary_candidate_ids", ())) != primary_candidate_ids
            or tuple(proposal.get("backup_candidate_ids", ())) != backup_candidate_ids
        ):
            raise AgentBoundaryError("Gate 5 response panel differs from independent review")
        test_only = summary.get("test_only_control_flow_fixture") is True
        return Gate5ApprovalAuthority(
            authority_id=identity(
                {
                    "card": card.card_id,
                    "outcome": outcome.model_dump(mode="json"),
                    "primary": primary_candidate_ids,
                    "backup": backup_candidate_ids,
                }
            ),
            gate5_card_id=card.card_id,
            final_review_dossier_sha256=final_review_dossier_sha256,
            primary_candidate_ids=primary_candidate_ids,
            backup_candidate_ids=backup_candidate_ids,
            authority_scope=("test-only-control-flow" if test_only else "scientist-approved"),
            human_actor=outcome.human_actor,
            authorizes_wet_lab_handoff=not test_only,
        )

    def gate5_route(self, card: DecisionCard) -> str:
        """Return the exact accepted Gate 5 route without granting handoff authority."""

        if card.gate_type != "wet-lab-handoff":
            raise AgentBoundaryError("Gate 5 routing requires a Wet-lab Handoff card")
        outcome = self.decision_for(card)
        if outcome is None or outcome.action not in {"APPROVE", "OVERRIDE"}:
            raise AgentBoundaryError("Gate 5 route lacks an accepted Scientist response")
        selected = outcome.selected_option_id or card.option_id
        routes = {
            "wet-lab-panel": "APPROVE_WET_LAB_HANDOFF",
            "revise-final-selection": "REVISE_FINAL_SELECTION",
            "stop": "STOP",
        }
        if selected not in routes:
            raise AgentBoundaryError("Gate 5 selected an unknown scientific route")
        return routes[selected]

    def downstream_state(self) -> dict[str, Any]:
        """Read-only recovery view; execution remains in deterministic stage services."""

        kinds = (
            "phase34-pilot-measurement",
            "phase34-pilot-dossier",
            "phase34-pilot-promotion-card",
            "phase34-scale-campaign",
            "phase34-global-candidate-pool",
            "phase34-review-shortlist",
            "phase34-final-review-dossier",
            "phase34-wet-lab-handoff-card",
            "phase34-wet-lab-handoff",
        )
        artifacts = {
            kind: event["contract_sha256"]
            for kind in kinds
            if (event := self.project_latest(kind)) is not None
        }
        pending_gate = None
        for kind in (
            "phase34-wet-lab-handoff-card",
            "phase34-pilot-promotion-card",
        ):
            event = self.project_latest(kind)
            if event is None:
                continue
            card = DecisionCard.model_validate(self.document(event["ref"]))
            if self.store.response(event["thread"], card.card_id) is None:
                pending_gate = card.gate_type
                break
        return {
            "artifacts": artifacts,
            "pending_gate": pending_gate,
            "status": (
                "handoff-published"
                if "phase34-wet-lab-handoff" in artifacts
                else "awaiting-human-approval"
                if pending_gate is not None
                else "in-progress"
            ),
        }
