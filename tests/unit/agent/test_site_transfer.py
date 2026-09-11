"""Trusted developer recovery preserves a completed unreviewed scientific proposal."""

from typing import Any

import pytest

from easydesign.agent.contracts import AgentBoundaryError
from easydesign.agent.phase2 import Phase2Bridge
from tests.unit.agent.test_site_runtime import propose, reviewed_card


def prepare(source: Any) -> tuple[Any, dict[str, Any]]:
    source.store.thread(source.thread, "source-code-version", "Same biological goal")
    source.store.begin_execution(source.thread, "Same biological goal")
    propose(source)
    proposal = source.current_site()
    destination = Phase2Bridge(source.project, "review-recovery", source.store)
    destination.store.thread(destination.thread, "patched-code-version", "Same biological goal")
    return destination, proposal


def test_explicit_site_transfer_preserves_snapshot_jobs_and_original_history(
    site_bridge: Any,
) -> None:
    source = site_bridge
    destination, proposal = prepare(source)
    snapshot = source.site_snapshot(proposal)
    jobs = source.controller.list(project_id=source.project_id)
    old_execution = source.store.latest_execution(source.thread)
    fingerprints = [tuple(r) for r in source.store.db.execute("SELECT * FROM threads ORDER BY id")]
    assert destination.current_site() is None
    result = destination.transfer_unreviewed_site(
        source.thread, expected_proposal_id=proposal["proposal_id"]
    )
    assert result == snapshot
    assert destination.current_site()["owner_thread"] == source.thread
    assert destination.current_site()["job_id"] == proposal["job_id"]
    assert source.current_site() is None
    assert source.thread_latest("site-proposal")["proposal_id"] == proposal["proposal_id"]
    assert source.store.latest_execution(source.thread) == old_execution
    assert fingerprints == [
        tuple(r) for r in source.store.db.execute("SELECT * FROM threads ORDER BY id")
    ]
    assert source.controller.list(project_id=source.project_id) == jobs
    assert (
        destination.transfer_unreviewed_site(
            source.thread, expected_proposal_id=proposal["proposal_id"]
        )
        == snapshot
    )
    assert destination.approved_site() is None
    assert destination.terminal_result("not approved")["status"] == "incomplete-turn"

    # Fresh independent Judge and the original Gate 2 service remain required.
    card = reviewed_card(destination)
    with pytest.raises(AgentBoundaryError, match="human"):
        destination.apply_decision(card)
    destination.store.respond(destination.thread, card.card_id, "approve", "synthetic-scientist")
    assert destination.apply_decision(card)["status"] == "hotspot-approved"
    assert source.approved_site()["hotspots"]["hotspot_sets"][0]["label_seq_ids"] == [1, 2, 3]
    assert {j.job_id for j in source.controller.list(project_id=source.project_id)} == {
        j.job_id for j in jobs
    }


@pytest.mark.parametrize("fault", ["wrong-id", "reviewed", "foreign", "used-destination", "stale"])
def test_site_transfer_rejects_unsafe_or_unscoped_continuity(site_bridge: Any, fault: str) -> None:
    source = site_bridge
    destination, proposal = prepare(source)
    source_thread = source.thread
    expected = proposal["proposal_id"]
    if fault == "wrong-id":
        expected = "different-proposal"
    elif fault == "reviewed":
        reviewed_card(source)
    elif fault == "foreign":
        source_thread = "not-a-thread-in-this-project"
    elif fault == "used-destination":
        destination.store.begin_execution(destination.thread, "Existing conversation")
    elif fault == "stale":
        source.store.event(source.thread, "site-invalidated", {"reason": "Changed biology"})
    before = len(source.store.events(destination.thread))
    with pytest.raises(AgentBoundaryError):
        destination.transfer_unreviewed_site(source_thread, expected_proposal_id=expected)
    assert len(source.store.events(destination.thread)) == before
    assert not source.thread_latest("site-proposal-transferred")
