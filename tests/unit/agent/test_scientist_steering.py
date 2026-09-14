import json
from typing import Any

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from pydantic import Field

from easydesign.agent.cli import parser, run_session
from easydesign.agent.contracts import (
    AgentBoundaryError,
    ApplyDecision,
    EvidenceBinding,
    JudgeVerdict,
    OptionRecommendation,
    TargetTask,
)
from easydesign.agent.session_store import SessionStore, identity
from easydesign.agent.tools import JUDGE_EVIDENCE, TargetBridge
from tests.agent_support import ScriptedModel, scripted_config, terminal
from tests.unit.agent.test_command_recovery import Crash, crash_at


class RevisionModel(ScriptedModel):
    tasks: list[dict[str, Any]] = Field(default_factory=list)

    def answer(self, messages: Any) -> AIMessage:
        revised = False
        if self.role == "coordinator":
            # A trusted resumed tool response is part of graph history; do not erase it in runtime.
            for i, m in reversed(list(enumerate(messages))):
                if isinstance(m, ToolMessage) and m.text.startswith("{"):
                    value = json.loads(m.text)
                    if value.get("status") == "revision-requested":
                        assert value["steering"]["source_role"] == "human-cli"
                        messages = messages[i + 1 :]
                        revised = True
                        break
        else:
            human = next(m for m in messages if isinstance(m, HumanMessage))
            task = TargetTask.model_validate_json(human.text)
            self.tasks.append(task.model_dump())
            revised = task.current_revision_instruction is not None
        answer = super().answer(messages)
        if self.role == "coordinator" and revised and answer.tool_calls:
            for call in answer.tool_calls:
                if call["name"] == "apply_target_decision":
                    call["args"]["option_id"] = "chain-b"
        if self.role == "target" and revised and not answer.tool_calls:
            value = json.loads(answer.text)
            value["recommended_action"] = (
                "Reassess Chain B with Judge; the earlier A preference conflicts with "
                "the revised choice, not a proved biological identity."
            )
            answer = AIMessage(content=json.dumps(value))
        return answer


def models() -> dict[str, RevisionModel]:
    return {r: RevisionModel(role=r) for r in ("coordinator", "target", "judge")}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "crash", ["after_response_intent", "after_revision_execution_intent", "after_steering_delivery"]
)
async def test_revision_is_durable_local_steering_with_new_proposal(
    bridge: Any, crash: str
) -> None:
    goal = "Prepare a structural target from this input; my initial preference is Chain A."
    instruction = "请重新评估 Chain B，并说明为什么原推荐可能不适合我的目标。"
    config = scripted_config()
    pending = await run_session(bridge, config, models(), goal)
    old = pending["card"]
    before = bridge.read_evidence()
    crash_at(bridge, crash)
    with pytest.raises(Crash):
        await run_session(
            bridge,
            config,
            models(),
            goal,
            decision="revise",
            card_id=old["card_id"],
            user="synthetic-human",
            human_instruction=instruction,
        )
    reopened = SessionStore(bridge.project)
    try:
        resumed = TargetBridge(bridge.project, bridge.thread, reopened)
        agents = models()
        fresh = await run_session(resumed, config, agents, goal)
        assert fresh["status"] == "awaiting-human-approval", fresh
        card = fresh["card"]
        assert card["card_id"] != old["card_id"] and card["assessment_id"] != old["assessment_id"]
        assert card["option_id"] == "chain-b" and card["parent_card_id"] == old["card_id"]
        assert card["request_identity"] == old["request_identity"]
        assert card["evidence_refs"] == old["evidence_refs"]
        assert resumed.read_evidence() == before
        assert len(resumed._jobs()) == 1
        root, _ = resumed.run()
        assert not list(root.glob("decisions/*/record.*.json"))
        tasks = agents["target"].tasks
        assert tasks and all(t["user_goal"] == goal for t in tasks)
        assert all(t["current_user_message"] == goal for t in tasks)
        assert all(t["current_revision_instruction"] == instruction for t in tasks)
        assert all(t["revision_of_card_id"] == old["card_id"] for t in tasks)
        assert all(
            t["run_id"] == before["run_id"] and t["evidence_refs"] == before["evidence_refs"]
            for t in tasks
        )
        response = reopened.response(bridge.thread, old["card_id"])
        assert response["delivered"] and response["outcome"]["human_instruction"] == instruction
        execution = reopened.latest_execution(bridge.thread)
        assert execution["revision"] == response["outcome"]
        preview = await run_session(resumed, config, agents, goal)
        assert preview["card"] == card
        assert reopened.latest_execution(bridge.thread) == execution
        with pytest.raises(AgentBoundaryError, match="fresh owner and Judge"):
            resumed.decision_card(
                ApplyDecision(assessment_id=old["assessment_id"], option_id="chain-b")
            )
        with pytest.raises(AgentBoundaryError):
            await run_session(
                resumed,
                config,
                agents,
                goal,
                decision="approve",
                card_id=old["card_id"],
                user="synthetic-human",
            )
        done = await run_session(
            resumed,
            config,
            agents,
            goal,
            decision="approve",
            card_id=card["card_id"],
            user="synthetic-human",
        )
        assert done["status"] == "finished" and done["scientific_state"] == "succeeded"
        assert resumed.read_evidence()["identity"]["auth_chain"] == "B"
        assert len(resumed._jobs()) == 2
    finally:
        reopened.close()


def discouraged_card(bridge: Any) -> Any:
    evidence = bridge.read_evidence()
    token = JUDGE_EVIDENCE.set(
        EvidenceBinding.model_validate({k: evidence[k] for k in EvidenceBinding.model_fields})
    )
    try:
        assessment = bridge.register_judge(
            JudgeVerdict(
                verdict="reject",
                reasons=["The frozen options support a human choice."],
                limitations=["This mock recommendation is not a biological conclusion."],
                recommendation=OptionRecommendation(
                    option_id="chain-a",
                    status="DISCOURAGED",
                    warnings=["Synthetic test warning: A is less suited to the hypothetical goal."],
                    alternative="Reassess Chain B as the recommended alternative.",
                ),
            )
        )
    finally:
        JUDGE_EVIDENCE.reset(token)
    return bridge.decision_card(
        ApplyDecision(assessment_id=assessment.assessment_id, option_id="chain-a")
    )


def test_discouraged_choice_requires_explicit_recorded_override(bridge: Any) -> None:
    bridge.prepare_target()
    terminal(bridge)
    card = discouraged_card(bridge)
    with pytest.raises(AgentBoundaryError, match="OVERRIDE"):
        bridge.store.respond(bridge.thread, card.card_id, "approve", "scientist")
    with pytest.raises(AgentBoundaryError, match="acknowledgement"):
        bridge.store.respond(bridge.thread, card.card_id, "override", "scientist")
    with pytest.raises(AgentBoundaryError, match="instruction"):
        bridge.store.respond(
            bridge.thread, card.card_id, "revise", "scientist", human_instruction="  "
        )
    assert bridge.store.response(bridge.thread, card.card_id) is None
    intent = bridge.store.respond(
        bridge.thread,
        card.card_id,
        "override",
        "scientist",
        explicit_acknowledgement="I have read the warning and accept this exploratory choice.",
        optional_reason="I want to test this hypothesis with the valid local structure.",
    )
    assert intent["outcome"]["recorded_warnings"] == card.warnings
    bridge.apply_decision(card)
    terminal(bridge)
    from easydesign.orchestration.decisions import load_decision_record_context

    root, _ = bridge.run()
    (record_path,) = root.glob("decisions/*/record.*.json")
    _, record = load_decision_record_context(root, record_path)
    assert record.approved_by == "scientist"
    assert "explicit human override" in record.acknowledgement
    assert identity(intent["outcome"]) in record.acknowledgement
    assert len(bridge._jobs()) == 2


def test_hard_ineligible_option_cannot_be_overridden(bridge: Any) -> None:
    from easydesign.orchestration.decisions import load_pending_decision

    bridge.prepare_target()
    terminal(bridge)
    root, _ = bridge.run()
    request, path = load_pending_decision(root)
    options = tuple(
        o.model_copy(
            update={"eligible": False, "rejection_reasons": ("Synthetic hard constraint",)}
        )
        if o.option_id == "chain-a"
        else o
        for o in request.options
    )
    # Fault injection in this disposable fixture, never a production scientific artifact.
    path.write_text(request.model_copy(update={"options": options}).model_dump_json())
    with pytest.raises(AgentBoundaryError, match="BLOCKED"):
        discouraged_card(bridge)
    assert bridge.store.db.execute("SELECT count(*) FROM responses").fetchone()[0] == 0
    assert not list(root.glob("decisions/*/record.*.json"))
    assert len(bridge._jobs()) == 1


def test_cli_accepts_first_class_revision_fields() -> None:
    args = parser().parse_args(
        [
            "resume",
            "target",
            "--thread",
            "thread-x",
            "--card",
            "card-x",
            "--decision",
            "revise",
            "--instruction",
            "Reassess chain B",
        ]
    )
    assert args.decision == "revise" and args.instruction == "Reassess chain B"


class ProseAfterRevision(RevisionModel):
    def answer(self, messages: Any) -> AIMessage:
        if self.role == "coordinator" and any(
            isinstance(m, ToolMessage) and '"revision-requested"' in m.text for m in messages
        ):
            return AIMessage(content="I will revise later. Finished.")
        return super().answer(messages)


@pytest.mark.asyncio
async def test_unfinished_revision_retains_steering_during_explicit_repair(bridge: Any) -> None:
    goal, instruction = "Prepare local chain A as a structural target", "Reassess Chain B"
    config = scripted_config()
    pending = await run_session(bridge, config, models(), goal)
    prose = {r: ProseAfterRevision(role=r) for r in ("coordinator", "target", "judge")}
    result = await run_session(
        bridge,
        config,
        prose,
        goal,
        decision="revise",
        card_id=pending["card"]["card_id"],
        user="synthetic-human",
        human_instruction=instruction,
    )
    assert result["status"] == "incomplete-turn"
    crash_at(bridge, "after_execution_intent")
    with pytest.raises(Crash):
        await run_session(
            bridge, config, models(), goal, new_message="Please produce the reviewed card"
        )
    bridge.failpoint = lambda _: None
    agents = models()
    resumed = await run_session(bridge, config, agents, goal)
    assert resumed["status"] == "awaiting-human-approval"
    assert resumed["card"]["option_id"] == "chain-b"
    assert all(t["current_revision_instruction"] == instruction for t in agents["target"].tasks)
    assert all(
        t["current_user_message"] == "Please produce the reviewed card"
        for t in agents["target"].tasks
    )
    assert len(bridge._jobs()) == 1


def test_cli_accepts_a_downstream_option_alias() -> None:
    args = parser().parse_args(
        [
            "resume",
            "target",
            "--thread",
            "thread-x",
            "--card",
            "card-x",
            "--decision",
            "approve",
            "--option",
            "REVISE_SITE",
        ]
    )
    assert args.candidate == "REVISE_SITE"
