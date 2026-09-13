"""Wrong-stage Judge submissions use bounded correction, never inferred approval."""

from contextlib import closing
from typing import Any

import pytest
from langchain_core.messages import AIMessage

from easydesign.agent.cli import run_session
from easydesign.agent.contracts import (
    AgentBoundaryError,
    EvidenceBinding,
    JudgeStageMismatch,
    JudgeVerdict,
)
from easydesign.agent.judge_packet import validate_judge_stage
from easydesign.agent.phase2 import Phase2Bridge
from easydesign.agent.phase2_tools import DESIGN_ALLOWED, PHASE2_ALLOWED
from easydesign.agent.session_store import SessionStore
from easydesign.agent.tools import JUDGE_EVIDENCE
from tests.agent_support import scripted_config
from tests.unit.agent.test_design_harness import DesignModel


class WrongStageJudge(DesignModel):
    judge_submissions: int = 0
    repeat_bad: bool = False
    judged_option: str = "chain-a"

    def answer(self, messages: Any) -> AIMessage:
        if self.role == "coordinator":
            pytest.fail("Stage correction must not call the Coordinator model")
        result = super().answer(messages)
        if self.role == "judge":
            for call in result.tool_calls:
                if call["name"] == "JudgeVerdict":
                    self.judge_submissions += 1
                    call["args"]["recommendation"] = {
                        "option_id": self.judged_option,
                        "status": "SUPPORTED",
                    }
                    if self.judge_submissions == 1 or self.repeat_bad:
                        call["args"]["verdict"] = "assessed"
        return result


@pytest.mark.asyncio
@pytest.mark.parametrize("gate", ["target-structure", "site-hotspot", "design-specification"])
async def test_actual_harness_repairs_wrong_stage_before_card_without_approval(
    request: Any, gate: str
) -> None:
    if gate == "target-structure":
        original = request.getfixturevalue("bridge")
        bridge = Phase2Bridge(original.project, original.thread, original.store)
    else:
        bridge = request.getfixturevalue(
            "site_bridge" if gate == "site-hotspot" else "design_bridge"
        )
    roles = DESIGN_ALLOWED if gate == "design-specification" else PHASE2_ALLOWED
    option = {
        "target-structure": "chain-a",
        "site-hotspot": "site",
        "design-specification": "design",
    }[gate]
    models = {role: WrongStageJudge(role=role, judged_option=option) for role in roles}
    result = await run_session(
        bridge,
        scripted_config(),
        models,
        "SYNTHETIC prepare chain A and review the current structural proposal; no efficacy claim.",
    )
    assert result["status"] == "awaiting-human-approval", result
    assert result["card"]["gate_type"] == gate
    assert bridge.store.response(bridge.thread, result["card"]["card_id"]) is None
    assert models["judge"].judge_submissions == 2
    events = bridge.store.events(bridge.thread)
    rejected = [e for e in events if e["kind"] == "rejected-submission"]
    accepted = [e for e in events if e["kind"] == "judge-assessment"]
    repairs = [e for e in events if e["kind"] == "contract-repair"]
    assert len(rejected) == len(accepted) == len(repairs) == 1
    assert "JUDGE_STAGE_MISMATCH" in rejected[0]["payload"]["diagnostic"]
    assert rejected[0]["payload"]["submitted_opinion"]["verdict"] == "assessed"
    assert rejected[0]["payload"]["submitted_opinion"]["recommendation"]["status"] == "SUPPORTED"
    assert accepted[0]["payload"]["verdict"] == "ready-to-ask"
    assert rejected[0]["seq"] < repairs[0]["seq"] < accepted[0]["seq"]
    assert not any(e["kind"] == "human-response" for e in events)
    assert not any(
        e["kind"] == "model-call" and e["payload"]["role"] == "coordinator" for e in events
    )
    assert (
        sum(
            e["kind"] == "runtime-dispatch" and e["payload"]["specialist"] == "evidence-judge"
            for e in events
        )
        == 1
    )
    assert all(job.step <= 2 for job in bridge.controller.list(project_id=bridge.project_id))

    # Direct registration cannot bypass the same check after a valid card exists.
    snapshot = bridge.judge_evidence()
    token = JUDGE_EVIDENCE.set(
        EvidenceBinding.model_validate({k: snapshot[k] for k in EvidenceBinding.model_fields})
    )
    try:
        with pytest.raises(JudgeStageMismatch, match="JUDGE_STAGE_MISMATCH"):
            bridge.register_judge(
                JudgeVerdict(
                    verdict="assessed",
                    reasons=["SYNTHETIC positive review is not a completed stage."],
                    limitations=["No Scientist approval exists for this proposal."],
                )
            )
    finally:
        JUDGE_EVIDENCE.reset(token)
    assert (
        len([e for e in bridge.store.events(bridge.thread) if e["kind"] == "judge-assessment"]) == 1
    )
    assert bridge.store.response(bridge.thread, result["card"]["card_id"]) is None


@pytest.mark.asyncio
async def test_repeated_stage_error_exhausts_existing_repairs_without_card(bridge: Any) -> None:
    b = Phase2Bridge(bridge.project, bridge.thread, bridge.store)
    models = {role: WrongStageJudge(role=role, repeat_bad=True) for role in PHASE2_ALLOWED}
    with pytest.raises(AgentBoundaryError, match="repair budget exhausted"):
        await run_session(b, scripted_config(), models, "SYNTHETIC prepare chain A for review.")
    assert models["judge"].judge_submissions == 3
    events = b.store.events(b.thread)
    assert len([e for e in events if e["kind"] == "contract-repair"]) == 2
    assert len([e for e in events if e["kind"] == "rejected-submission"]) == 3
    assert not any(
        e["kind"] in {"judge-assessment", "decision-card", "human-response"} for e in events
    )
    assert b.store.db.execute("SELECT count(*) FROM cards").fetchone()[0] == 0
    assert b.read_evidence()["status"] == "awaiting-human-approval"
    # A process/store reopen does not grant another correction allowance.
    with closing(SessionStore(b.project)) as reopened:
        execution = reopened.latest_execution(b.thread)["execution_id"]
        with pytest.raises(AgentBoundaryError, match="repair budget exhausted"):
            reopened.reserve_contract_repair(
                b.thread, "judge", execution, "JUDGE_STAGE_MISMATCH", contract="JudgeVerdict"
            )


@pytest.mark.parametrize("gate", ["target-structure", "site-hotspot", "design-specification"])
@pytest.mark.parametrize("verdict", ["insufficient", "reject"])
def test_stage_check_preserves_negative_scientific_opinions(gate: str, verdict: str) -> None:
    opinion = JudgeVerdict.model_validate(
        {
            "verdict": verdict,
            "reasons": ["SYNTHETIC evidence prevents a meaningful current decision."],
            "limitations": ["The original scientific objection must remain unchanged."],
        }
    )
    before = opinion.model_dump()
    validate_judge_stage(
        opinion,
        {"gate_type": gate, "status": "awaiting-human-approval", "request_identity": "current"},
    )
    assert opinion.model_dump() == before


@pytest.mark.parametrize("gate", ["site-hotspot", "design-specification"])
def test_assessed_does_not_mean_any_completed_gate(gate: str) -> None:
    with pytest.raises(JudgeStageMismatch):
        validate_judge_stage(
            JudgeVerdict(
                verdict="assessed",
                reasons=["SYNTHETIC completed non-Target view."],
                limitations=["Does not authorize another Gate."],
            ),
            {
                "gate_type": gate,
                "status": "succeeded",
                "request_identity": None,
                "bundle": {"target_id": "synthetic-verified-target"},
            },
        )
