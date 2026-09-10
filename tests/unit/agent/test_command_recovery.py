from typing import Any

import pytest

from easydesign.agent.contracts import ReconciliationRequired
from tests.agent_support import judge_card, terminal


class Crash(BaseException):
    pass


def crash_at(bridge: Any, point: str) -> None:
    def failpoint(name: str) -> None:
        if name == point:
            raise Crash(point)

    bridge.failpoint = failpoint


@pytest.mark.parametrize(
    "point", ["prepared", "dispatching", "after_dispatch", "after_job_binding"]
)
def test_prepare_crash_does_not_duplicate_scientific_work(bridge: Any, point: str) -> None:
    crash_at(bridge, point)
    with pytest.raises(Crash):
        bridge.prepare_target()
    bridge.failpoint = lambda _: None
    if point == "dispatching":
        with pytest.raises(ReconciliationRequired):
            bridge.prepare_target()
        assert not bridge._jobs()
        return
    bridge.prepare_target()
    terminal(bridge)
    before = bridge.read_evidence()
    bridge.prepare_target()
    assert len(bridge._jobs()) == 1
    assert bridge.read_evidence()["evidence_id"] == before["evidence_id"]


def test_queued_receipt_before_popen_never_relaunches(bridge: Any, monkeypatch: Any) -> None:
    def fail(*a: Any, **k: Any) -> None:
        raise Crash("Popen")

    with monkeypatch.context() as patch:
        patch.setattr("easydesign.orchestration.local_jobs._branch", lambda _: "test-branch")
        patch.setattr("easydesign.orchestration.local_jobs.subprocess.Popen", fail)
        with pytest.raises(Crash):
            bridge.prepare_target()
    resumed = bridge.prepare_target()
    assert resumed["status"] == "queued"
    assert "reconciliation-required" in resumed["recovery"]
    assert len(bridge._jobs()) == 1


@pytest.mark.parametrize("point", ["before_record", "after_decision_dispatch", "after_job_binding"])
def test_approval_replay_has_one_record_and_same_run(bridge: Any, point: str) -> None:
    bridge.prepare_target()
    terminal(bridge)
    card = judge_card(bridge)
    bridge.store.respond(bridge.thread, card.card_id, "approve", "test-human")
    crash_at(bridge, point)
    with pytest.raises(Crash):
        bridge.apply_decision(card)
    bridge.failpoint = lambda _: None
    bridge.apply_decision(card)
    terminal(bridge)
    evidence = bridge.read_evidence()
    bridge.apply_decision(card)
    assert len(bridge._jobs()) == 2
    assert evidence["run_id"] == card.run_id
    assert evidence["bundle"]["producer_attempt"] == "attempt-0002"
    assert bridge.read_evidence()["evidence_id"] == evidence["evidence_id"]


def test_record_written_before_decision_launch_is_reconciled(bridge: Any, monkeypatch: Any) -> None:
    from easydesign.orchestration.local_jobs import LocalStepJobController

    bridge.prepare_target()
    terminal(bridge)
    card = judge_card(bridge)
    bridge.store.respond(bridge.thread, card.card_id, "approve", "test-human")
    real = LocalStepJobController.launch

    def fail(self: Any, **kwargs: Any) -> Any:
        if kwargs["operation"] == "decision":
            raise Crash("record exists, no launch")
        return real(self, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(LocalStepJobController, "launch", fail)
        with pytest.raises(Crash):
            bridge.apply_decision(card)
    assert len(bridge._jobs()) == 1
    bridge.apply_decision(card)
    terminal(bridge)
    assert len(bridge._jobs()) == 2
    assert bridge.read_evidence()["bundle"]["producer_attempt"] == "attempt-0002"


def test_ambiguous_receipts_never_select_by_recency(bridge: Any) -> None:
    crash_at(bridge, "after_dispatch")
    with pytest.raises(Crash):
        bridge.prepare_target()
    bridge.failpoint = lambda _: None
    original = bridge._jobs()[0]
    # A synthetic extra receipt models an overlapping old-CLI submission.
    bridge.controller.update(original.model_copy(update={"job_id": "job-ambiguousfixture"}))
    with pytest.raises(ReconciliationRequired):
        bridge.prepare_target()
    assert len(bridge._jobs()) == 2
