from collections import Counter
from typing import Any

import pytest
from langchain_core.messages import AIMessage, HumanMessage
from pydantic import Field

from easydesign.agent.cli import run_session
from easydesign.agent.contracts import AgentBoundaryError, TargetTask
from easydesign.agent.session_store import SessionStore
from easydesign.agent.tools import TargetBridge
from tests.agent_support import ScriptedModel, scripted_config


class RecordingModel(ScriptedModel):
    tasks: list[dict[str, Any]] = Field(default_factory=list)
    human_histories: list[list[str]] = Field(default_factory=list)

    def answer(self, messages: Any) -> AIMessage:
        humans = [m for m in messages if isinstance(m, HumanMessage)]
        self.human_histories.append([m.text for m in humans])
        if self.role != "coordinator":
            self.tasks.append(TargetTask.model_validate_json(humans[0].text).model_dump())
        else:
            # Script each new turn while verifying that LangGraph supplied the full history.
            start = max(i for i, m in enumerate(messages) if isinstance(m, HumanMessage))
            messages = messages[start:]
        return super().answer(messages)


@pytest.mark.asyncio
async def test_same_thread_followups_preserve_goal_and_renew_only_turn_budget(bridge: Any) -> None:
    # A deliberately smaller test ceiling makes lifetime usage exceed one turn.
    config = scripted_config().model_copy(update={"max_model_calls": 24})
    models = {r: RecordingModel(role=r) for r in ("coordinator", "target", "judge")}
    goal = "Prepare local chain A as a structural target; biological identity stays unconfirmed."
    pending = await run_session(bridge, config, models, goal)
    first_execution = bridge.store.latest_execution(bridge.thread)
    assert first_execution is not None
    calls_before = [e for e in bridge.store.events(bridge.thread) if e["kind"] == "model-call"]

    reopened = SessionStore(bridge.project)
    resumed = TargetBridge(bridge.project, bridge.thread, reopened)
    try:
        preview = await run_session(resumed, config, models, goal)
        assert preview["card"] == pending["card"]
        assert len([e for e in reopened.events(bridge.thread) if e["kind"] == "model-call"]) == len(
            calls_before
        )
        assert reopened.latest_execution(bridge.thread) == first_execution
        done = await run_session(
            resumed,
            config,
            models,
            goal,
            decision="approve",
            card_id=pending["card"]["card_id"],
            user="synthetic-multiturn-user",
        )
        assert done["status"] == "finished"
        assert reopened.latest_execution(bridge.thread) == first_execution
        followups = ["Explain the identity limitations.", "Review mapping consistency for chain A."]
        for message in followups:
            done = await run_session(resumed, config, models, goal, new_message=message)
            assert done["status"] == "finished"
            assert done["scientific_state"] == "succeeded"
            assert done["job"]["status"] == "succeeded"
            assert (
                reopened.thread(
                    bridge.thread,
                    reopened.db.execute(
                        "SELECT fingerprint FROM threads WHERE id=?",
                        (bridge.thread,),
                    ).fetchone()[0],
                )
                == goal
            )

        events = reopened.events(bridge.thread)
        executions = [e["payload"] for e in events if e["kind"] == "agent-execution"]
        calls = [e["payload"] for e in events if e["kind"] == "model-call"]
        assert [e["current_user_message"] for e in executions] == [goal, *followups]
        counts = Counter(c["execution_id"] for c in calls)
        assert len(counts) == 3
        assert len(calls) > config.max_model_calls
        assert max(counts.values()) <= config.max_model_calls
        assert [c["lifetime_call"] for c in calls] == list(range(1, len(calls) + 1))
        for role in ("target", "judge"):
            assert {t["user_goal"] for t in models[role].tasks} == {goal}
            assert {t["current_user_message"] for t in models[role].tasks} == {goal, *followups}
        assert models["coordinator"].human_histories[-1] == [goal, *followups]
        assert len(resumed._jobs()) == 2  # Follow-up inspection did not submit new scientific work.
        with pytest.raises(AgentBoundaryError, match="immutable"):
            await run_session(resumed, config, models, "Replace the original research goal")
    finally:
        reopened.close()


class LoopModel(ScriptedModel):
    def answer(self, messages: Any) -> AIMessage:
        return self.call("read_target_evidence")


@pytest.mark.asyncio
async def test_resume_cannot_reset_an_exhausted_execution(bridge: Any) -> None:
    config = scripted_config().model_copy(update={"max_model_calls": 2})
    models = {r: LoopModel(role=r) for r in ("coordinator", "target", "judge")}
    with pytest.raises(AgentBoundaryError, match="budget"):
        await run_session(bridge, config, models, "Inspect this target")
    execution = bridge.store.latest_execution(bridge.thread)
    reopened = SessionStore(bridge.project)
    resumed = TargetBridge(bridge.project, bridge.thread, reopened)
    try:
        with pytest.raises(AgentBoundaryError, match="budget"):
            await run_session(resumed, config, models, "Inspect this target")
        with pytest.raises(AgentBoundaryError, match="unfinished"):
            await run_session(
                resumed, config, models, "Inspect this target", new_message="Try again"
            )
        assert reopened.latest_execution(bridge.thread) == execution
        assert len([e for e in reopened.events(bridge.thread) if e["kind"] == "model-call"]) == 2
        assert not resumed._jobs()
    finally:
        reopened.close()


class ReplyModel(ScriptedModel):
    def answer(self, messages: Any) -> AIMessage:
        return AIMessage(content="Clarification noted; the research goal is retained.")


@pytest.mark.asyncio
async def test_followup_intent_survives_a_crash_before_checkpoint(bridge: Any) -> None:
    from tests.unit.agent.test_command_recovery import Crash, crash_at

    config = scripted_config()
    models = {r: ReplyModel(role=r) for r in ("coordinator", "target", "judge")}
    await run_session(bridge, config, models, "Inspect local chain A")
    crash_at(bridge, "after_execution_intent")
    with pytest.raises(Crash):
        await run_session(
            bridge, config, models, "Inspect local chain A", new_message="Explain limits"
        )
    pending_execution = bridge.store.latest_execution(bridge.thread)
    bridge.failpoint = lambda _: None
    with pytest.raises(AgentBoundaryError, match="unfinished"):
        await run_session(
            bridge, config, models, "Inspect local chain A", new_message="Replace intent"
        )
    done = await run_session(bridge, config, models, "Inspect local chain A")
    assert done["status"] == "incomplete-turn"
    assert done["scientific_state"] == "not-prepared"
    assert bridge.store.latest_execution(bridge.thread) == pending_execution
    calls = [e for e in bridge.store.events(bridge.thread) if e["kind"] == "model-call"]
    assert len(calls) == 2
    await run_session(bridge, config, models, "Inspect local chain A")
    assert len([e for e in bridge.store.events(bridge.thread) if e["kind"] == "model-call"]) == 2
