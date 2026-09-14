from __future__ import annotations

from typing import Any

import pytest

from easydesign.agent.contracts import AgentBoundaryError, DecisionCard
from easydesign.agent.phase4 import build_gate5_card
from easydesign.agent.phase34_bridge import Phase34Bridge
from easydesign.agent.phase34_contracts import Gate5JudgeAssessment
from easydesign.core import canonical_model_sha256
from tests.unit.agent.test_phase4_pool import _final_review


def test_downstream_bridge_reuses_immutable_project_evidence(design_bridge: Any) -> None:
    bridge = Phase34Bridge(design_bridge.project, design_bridge.thread, design_bridge.store)
    _, _, dossiers, review = _final_review()
    ref = bridge.publish_contract(
        kind="phase34-final-review-dossier",
        contract=review,
        dependencies={"global-pool": review.global_pool_sha256},
    )
    repeated = bridge.publish_contract(
        kind="phase34-final-review-dossier",
        contract=review,
        dependencies={"global-pool": review.global_pool_sha256},
    )
    assert repeated == ref
    loaded = bridge.load_contract(
        kind="phase34-final-review-dossier",
        contract_type=type(review),
        expected_sha256=canonical_model_sha256(review),
    )
    assert loaded == review
    events = [
        item
        for item in bridge.store.events(bridge.thread)
        if item["kind"] == "phase34-final-review-dossier"
    ]
    assert len(events) == 1
    assert len(dossiers) == 3


def test_gate5_response_projects_validation_only_authority(design_bridge: Any) -> None:
    bridge = Phase34Bridge(design_bridge.project, design_bridge.thread, design_bridge.store)
    _, _, dossiers, review = _final_review()
    assessment = Gate5JudgeAssessment(
        assessment_id="bridge-gate5-judge",
        final_review_dossier_sha256=canonical_model_sha256(review),
        verdict="ready-to-ask",
        recommendation="APPROVE_WET_LAB_HANDOFF",
        candidate_findings=tuple(
            {
                "candidate_id": item.candidate.lineage.candidate_id,
                "status": "SUPPORTED",
                "reasons": ("Development evidence is internally consistent.",),
                "concerns": ("Experimental behavior is unknown.",),
            }
            for item in dossiers
        ),
        reasons=("The validation panel is internally consistent.",),
        limitations=("This fixture provides no biological validation.",),
        evidence_refs=("validation:gate5-judge",),
    )
    card = build_gate5_card(dossier=review, assessment=assessment)
    bridge.publish_gate_card(card=card, evidence_contract=review)
    bridge.store.respond(bridge.thread, card.card_id, "approve", "validation-scientist")
    authority = bridge.gate5_approval_authority(
        final_review_dossier_sha256=canonical_model_sha256(review),
        card=card,
        primary_candidate_ids=review.proposed_selection.primary_candidate_ids,
        backup_candidate_ids=review.proposed_selection.backup_candidate_ids,
    )
    assert authority.authority_scope == "test-only-control-flow"
    assert not authority.authorizes_wet_lab_handoff
    state = bridge.downstream_state()
    assert state["pending_gate"] is None


def test_gate4_records_an_explicit_alternative_route(design_bridge: Any) -> None:
    bridge = Phase34Bridge(design_bridge.project, design_bridge.thread, design_bridge.store)
    options = ("PROMOTE_TO_SCALE", "RUN_ANOTHER_PILOT", "REVISE_DESIGN", "REVISE_SITE", "STOP")
    card = DecisionCard(
        gate_type="pilot-promotion",
        card_id="gate4-alternative-card",
        assessment_id="gate4-alternative-judge",
        project_id=bridge.project_id,
        run_id="pilot-alternative-run",
        request_identity="a" * 64,
        evidence_id="a" * 64,
        question="Choose the next Pilot route.",
        option_id="PROMOTE_TO_SCALE",
        options=[{"option_id": option, "label": option, "eligible": True} for option in options],
        evidence_refs=("validation:gate4",),
        limitations=("Synthetic routing test.",),
    )
    bridge.store.save_card(bridge.thread, card)
    bridge.store.respond(
        bridge.thread,
        card.card_id,
        "approve",
        "validation-scientist",
        selected_option_id="REVISE_SITE",
    )
    assert bridge.gate4_route(card) == "REVISE_SITE"


def test_gate5_alternative_cannot_create_handoff_authority(design_bridge: Any) -> None:
    bridge = Phase34Bridge(design_bridge.project, design_bridge.thread, design_bridge.store)
    _, _, dossiers, review = _final_review()
    assessment = Gate5JudgeAssessment(
        assessment_id="bridge-gate5-alternative-judge",
        final_review_dossier_sha256=canonical_model_sha256(review),
        verdict="ready-to-ask",
        recommendation="REVISE_FINAL_SELECTION",
        candidate_findings=tuple(
            {
                "candidate_id": item.candidate.lineage.candidate_id,
                "status": "SUPPORTED",
                "reasons": ("The deterministic evidence is readable.",),
                "concerns": ("The proposed panel needs revision.",),
            }
            for item in dossiers
        ),
        reasons=("Exercise the explicit Gate 5 revision route.",),
        limitations=("Synthetic routing test.",),
        evidence_refs=("validation:gate5-alternative",),
    )
    card = build_gate5_card(dossier=review, assessment=assessment)
    bridge.publish_gate_card(card=card, evidence_contract=review)
    bridge.store.respond(
        bridge.thread,
        card.card_id,
        "approve",
        "validation-scientist",
        selected_option_id="revise-final-selection",
    )
    assert bridge.gate5_route(card) == "REVISE_FINAL_SELECTION"
    with pytest.raises(AgentBoundaryError, match="did not select"):
        bridge.gate5_approval_authority(
            final_review_dossier_sha256=canonical_model_sha256(review),
            card=card,
            primary_candidate_ids=review.proposed_selection.primary_candidate_ids,
            backup_candidate_ids=review.proposed_selection.backup_candidate_ids,
        )
