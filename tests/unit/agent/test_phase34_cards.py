import pytest

from easydesign.agent.contracts import AgentBoundaryError
from easydesign.agent.phase34_cards import final_card, pilot_card
from easydesign.agent.phase34_opinions import DownstreamJudgeOpinion, DownstreamReviewFailure
from easydesign.agent.session_store import SessionStore
from easydesign.core import canonical_model_sha256
from tests.unit.agent.test_phase4_pool import _final_review
from tests.unit.agent.test_phase34_contracts import _pilot_dossier


def failure(dossier, gate):
    return DownstreamReviewFailure(
        record_id="unavailable-review",
        input_binding=canonical_model_sha256(dossier),
        gate=gate,
        attempts=3,
        categories=["MAX_TOKENS"] * 3,
        retained_warnings=["A material uncertainty remains."],
    )


def test_judge_cannot_change_gate4_recommendation_or_hide_arm_diagnosis():
    dossier = _pilot_dossier()
    critique = DownstreamJudgeOpinion(
        review="CONCERNS",
        brief_rationale="The sample is small.",
        warnings=["Do not infer binding."],
        uncertainties=["Biology untested."],
    )
    card = pilot_card(dossier, critique)
    assert card.option_id == dossier.proposed_interpretation.outcome
    assert card.scientific_summary["diagnosis"] == dossier.diagnosis.model_dump(mode="json")
    assert "Do not infer binding." in card.warnings


@pytest.mark.parametrize("gate", ["pilot-promotion", "wet-lab-handoff"])
def test_unavailable_judge_keeps_card_and_allows_explicit_scientist_selection(tmp_path, gate):
    dossier = _pilot_dossier() if gate == "pilot-promotion" else _final_review()[-1]
    builder = pilot_card if gate == "pilot-promotion" else final_card
    card = builder(dossier, failure(dossier, gate))
    assert card.assessment_id is None and card.judge_status is None
    assert card.scientific_summary["independent_review"]["availability"] == "unavailable"
    assert "A material uncertainty remains." in card.warnings
    store = SessionStore(tmp_path)
    try:
        store.thread("scientist", "test", "Synthetic review")
        store.save_card("scientist", card)
        response = store.respond("scientist", card.card_id, "approve", "synthetic-human")
        assert response["outcome"]["selected_option_id"] == card.option_id
        assert card.scientific_summary["test_only_control_flow_fixture"] is True
    finally:
        store.close()


@pytest.mark.parametrize("gate", ["pilot-promotion", "wet-lab-handoff"])
def test_runtime_hard_error_is_not_bypassed_by_unavailable_review(tmp_path, gate):
    dossier = _pilot_dossier() if gate == "pilot-promotion" else _final_review()[-1]
    builder = pilot_card if gate == "pilot-promotion" else final_card
    card = builder(dossier, failure(dossier, gate), hard_errors=("Runtime constraint conflict.",))
    blocked = "PROMOTE_TO_SCALE" if gate == "pilot-promotion" else "wet-lab-panel"
    store = SessionStore(tmp_path)
    try:
        store.thread("scientist", "test", "Synthetic review")
        store.save_card("scientist", card)
        with pytest.raises(AgentBoundaryError, match="not eligible"):
            store.respond(
                "scientist", card.card_id, "approve", "synthetic-human", selected_option_id=blocked
            )
        store.respond(
            "scientist",
            card.card_id,
            "approve",
            "synthetic-human",
            selected_option_id="STOP" if gate == "pilot-promotion" else "stop",
        )
    finally:
        store.close()


def test_stale_review_failure_cannot_make_a_new_gate_card():
    dossier = _pilot_dossier()
    stale = failure(dossier, "pilot-promotion").model_copy(update={"input_binding": "a" * 64})
    with pytest.raises(AgentBoundaryError, match="different Gate dossier"):
        pilot_card(dossier, stale)


def test_gate5_without_judge_keeps_exact_panel_and_scientist_authority(tmp_path):
    dossier = _final_review()[-1]
    card = final_card(dossier)
    assert card.scientific_summary["independent_review"] == {
        "availability": "not-requested",
        "optional": True,
    }
    assert card.scientific_summary["proposed_selection"] == dossier.proposed_selection.model_dump(
        mode="json"
    )
    assert card.judge_status is None and card.assessment_id is None
    store = SessionStore(tmp_path)
    try:
        store.thread("validation", "test", "Synthetic Gate 5 without review")
        store.save_card("validation", card)
        assert store.response("validation", card.card_id) is None
        store.respond("validation", card.card_id, "approve", "validation-human")
        assert store.response("validation", card.card_id)["outcome"]["selected_option_id"] == (
            "wet-lab-panel"
        )
    finally:
        store.close()
