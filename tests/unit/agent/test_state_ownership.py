"""Two conversations share approved science, never each other's pending proposal."""

from typing import Any

import pytest

from easydesign.agent.contracts import AgentBoundaryError
from easydesign.agent.phase2 import Phase2Bridge
from tests.unit.agent.test_site_runtime import propose, reviewed_card, site_intent


def test_pending_site_is_thread_owned_across_followup_and_resume(site_bridge: Any) -> None:
    a = site_bridge
    propose(a)
    card_a = reviewed_card(a)
    original = a.current_site()
    # B creates a different valid proposal through the original Stage 02 service.
    b = Phase2Bridge(a.project, "second-conversation", a.store)
    propose(b, site_intent([4, 5, 6]))
    assert b.current_site()["proposal_id"] != original["proposal_id"]
    a.store.begin_execution(a.thread, "Continue my original site review", followup=True)
    resumed = Phase2Bridge(a.project, a.thread, a.store)
    assert resumed.current_site() == original
    a.store.respond(a.thread, card_a.card_id, "approve", "synthetic-scientist")
    assert resumed.apply_decision(card_a)["status"] == "hotspot-approved"
    assert resumed.approved_site()["hotspots"]["hotspot_sets"][0]["label_seq_ids"] == [1, 2, 3]
    # The other conversation inherits approved science, while retaining its own draft.
    assert b.approved_site()["proposal"]["thread"] == a.thread
    assert b.current_site()["intent"]["selected_site"]["hotspot_label_seq_ids"] == [4, 5, 6]
    assert b.scientific_state()["scientific_state"] == "awaiting-human-approval"
    assert b.terminal_result("done")["status"] == "incomplete-turn"
    assert resumed.scientific_state()["scientific_state"] == "hotspot-approved"


def test_new_binder_thread_inherits_exact_approved_site(design_bridge: Any) -> None:
    b = design_bridge
    assert b.current_site() is None
    evidence = b.read_design_evidence()
    approved = b.approved_site()
    assert evidence["site_rationale"] == approved["proposal"]["intent"]
    assert evidence["approved_hotspots"][0]["label_seq_ids"] == [1, 2, 3]
    assert approved["proposal"]["thread"] != b.thread


def test_new_context_makes_both_threads_stale_without_substitution(
    design_bridge: Any, tmp_path: Any
) -> None:
    b = design_bridge
    a = Phase2Bridge(b.project, b.approved_site()["thread"], b.store)
    target = a.target_state()["binding"]
    path = tmp_path / "new-biology.yaml"
    path.write_text("target_auth_chain: A\nlimitations: [Changed assay context]\n")
    b.import_biology(path)
    assert a.approved_site() is None and b.approved_site() is None
    assert a.target_state()["binding"] == target
    with pytest.raises(AgentBoundaryError, match="Gate 2"):
        b.read_design_evidence()
