"""Deterministic shared budget and native summary feasibility regressions."""

from collections import Counter
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
import yaml
from deepagents.backends import FilesystemBackend
from langchain.agents.middleware.types import ModelRequest, ModelResponse
from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from easydesign.agent.context_policy import SummaryAccounting, research_memory
from easydesign.agent.contracts import AgentBoundaryError
from easydesign.agent.models import PHASE2_MODEL_CALL_LIMIT, ModelConfig
from easydesign.agent.session_store import SessionStore
from tests.agent_support import scripted_config


def test_phase2_default_and_template_have_one_effective_64_call_budget() -> None:
    template = Path(__file__).resolve().parents[3] / "config/llm.template.yaml"
    for config in (
        scripted_config(),
        ModelConfig.model_validate(yaml.safe_load(template.read_text())),
    ):
        assert config.max_model_calls == PHASE2_MODEL_CALL_LIMIT == 64
        assert config.hard_input_chars == 100000
        assert config.max_input_chars == 60000
    # Keep a single default; the shipped template must not shadow it.
    assert "max_model_calls" not in yaml.safe_load(template.read_text())


@pytest.mark.asyncio
async def test_reopened_execution_crosses_32_with_summary_and_all_roles(tmp_path: Path) -> None:
    config = scripted_config()
    store = SessionStore(tmp_path)
    thread = "synthetic-budget"
    eid = store.begin_execution(thread, "Synthetic scientific execution")["execution_id"]
    roles = ["coordinator", "target", "site", "binder", "judge"]
    for i in range(32):
        store.reserve_model_call(thread, roles[i % len(roles)], config.max_model_calls, eid)
    store.close()
    store = SessionStore(tmp_path)
    b = SimpleNamespace(store=store, thread=thread)
    callback = SummaryAccounting(b, config, "site", eid, SimpleNamespace(profile=None))
    try:
        # Summary 33 is charged once in the same ledger, separately observable.
        await callback.on_chat_model_start(
            {}, [[HumanMessage(content="Synthetic summary")]], run_id="33"
        )
        await callback.on_llm_end(SimpleNamespace(generations=[]), run_id="33")
        assert store.latest_execution(thread)["execution_id"] == eid
        store.close()
        store = SessionStore(tmp_path)
        for i in range(33, 64):
            store.reserve_model_call(thread, roles[i % len(roles)], config.max_model_calls, eid)
        events = store.events(thread)
        calls = [e["payload"] for e in events if e["kind"] == "model-call"]
        assert [c["call"] for c in calls] == list(range(1, 65))
        assert [c["lifetime_call"] for c in calls] == list(range(1, 65))
        assert {c["execution_id"] for c in calls} == {eid}
        expected = Counter(roles[i % len(roles)] for i in range(64))
        expected[roles[32 % len(roles)]] -= 1
        expected["site"] += 1
        assert Counter(c["role"] for c in calls) == expected
        assert len([e for e in events if e["kind"] == "framework-summary-call"]) == 1
        assert len([e for e in events if e["kind"] == "framework-summary-response"]) == 1
        for role in roles:
            with pytest.raises(AgentBoundaryError, match="model-call budget"):
                store.reserve_model_call(thread, role, config.max_model_calls, eid)
        b.store = store
        restarted_callback = SummaryAccounting(
            b, config, "site", eid, SimpleNamespace(profile=None)
        )
        with pytest.raises(AgentBoundaryError, match="model-call budget"):
            await restarted_callback.on_chat_model_start(
                {}, [[HumanMessage(content="Must not run")]], run_id="65"
            )
        assert store.events(thread) == events
    finally:
        store.close()


def history(rounds: int, total_chars: int) -> list[Any]:
    messages: list[Any] = [HumanMessage(content="Synthetic evidence; preserve original payloads.")]
    for i in range(rounds):
        messages.extend(
            [
                AIMessage(
                    content="", tool_calls=[{"name": "read_evidence", "args": {}, "id": str(i)}]
                ),
                ToolMessage(
                    content="x" * (total_chars // rounds), name="read_evidence", tool_call_id=str(i)
                ),
            ]
        )
    return messages


@pytest.mark.asyncio
@pytest.mark.parametrize("rounds,chars,summaries", [(2, 82000, 0), (6, 82000, 1), (2, 94000, 1)])
async def test_native_summary_waits_for_more_history_unless_near_guard(
    tmp_path: Path, rounds: int, chars: int, summaries: int
) -> None:
    config = scripted_config()
    (tmp_path / "project").mkdir(exist_ok=True)
    store = SessionStore(tmp_path / "project")
    b = SimpleNamespace(store=store, thread="synthetic-memory")
    eid = store.begin_execution(b.thread, "Synthetic memory threshold")["execution_id"]
    model = FakeListChatModel(
        responses=["Fallible summary. Original sources remain authoritative."]
    )
    backend = FilesystemBackend(root_dir=tmp_path / "history", virtual_mode=True)
    memory = research_memory(b, config, model, backend, eid)
    messages = history(rounds, chars)
    original = [m.model_dump() for m in messages]
    received = []

    async def handler(request: Any) -> Any:
        received.extend(request.messages)
        store.reserve_model_call(b.thread, "site", config.max_model_calls, eid)
        return ModelResponse(result=[AIMessage(content="Synthetic research continuation")])

    try:
        await memory.awrap_model_call(
            ModelRequest(
                model=model,
                system_message=SystemMessage(content="Synthetic research"),
                messages=messages,
                state={"messages": messages},
                tools=[],
            ),
            handler,
        )
        events = store.events(b.thread)
        assert len([e for e in events if e["kind"] == "framework-summary-call"]) == summaries
        assert len([e for e in events if e["kind"] == "model-call"]) == 1 + summaries
        assert [m.model_dump() for m in messages] == original
        if not summaries:
            assert received == messages
    finally:
        store.close()


@pytest.mark.asyncio
async def test_native_summary_checkpoint_reopen_keeps_cutoff_and_small_tail(tmp_path: Path) -> None:
    config = scripted_config()
    (tmp_path / "project").mkdir(exist_ok=True)
    store = SessionStore(tmp_path / "project")
    b = SimpleNamespace(store=store, thread="synthetic-restart")
    eid = store.begin_execution(b.thread, "Synthetic summary restart")["execution_id"]
    model = FakeListChatModel(responses=["Fallible synthetic summary of archived evidence."])
    backend = FilesystemBackend(root_dir=tmp_path / "history", virtual_mode=True)
    messages = history(6, 82000)
    received = []

    async def handler(request: Any) -> Any:
        received.append(request.messages)
        b.store.reserve_model_call(b.thread, "site", config.max_model_calls, eid)
        return ModelResponse(result=[AIMessage(content="Synthetic continuation")])

    def request(state: dict[str, Any]) -> ModelRequest:
        return ModelRequest(
            model=model,
            system_message=SystemMessage(content="Synthetic"),
            messages=messages,
            state=state,
            tools=[],
        )

    try:
        result = await research_memory(b, config, model, backend, eid).awrap_model_call(
            request({"messages": messages}), handler
        )
        event = result.command.update["_summarization_event"]
        original_file = tmp_path / "history" / event["file_path"].lstrip("/")
        saved_bytes = original_file.read_bytes()
        store.close()
        store = SessionStore(tmp_path / "project")
        b.store = store
        messages.append(HumanMessage(content="One small follow-up question; sources unchanged."))
        await research_memory(b, config, model, backend, eid).awrap_model_call(
            request({"messages": messages, **result.command.update}), handler
        )
        assert received[-1] == [event["summary_message"], *messages[event["cutoff_index"] :]]
        assert original_file.read_bytes() == saved_bytes
        events = store.events(b.thread)
        assert len([e for e in events if e["kind"] == "framework-summary-call"]) == 1
        calls = [e["payload"] for e in events if e["kind"] == "model-call"]
        assert [c["call"] for c in calls] == [1, 2, 3]
        assert {c["execution_id"] for c in calls} == {eid}
    finally:
        store.close()


@pytest.mark.asyncio
async def test_cli_graph_steps_do_not_preempt_the_64_call_ledger(
    bridge: Any, monkeypatch: Any
) -> None:
    from langgraph.graph import START, MessagesState, StateGraph

    from easydesign.agent import harness
    from easydesign.agent.cli import run_session

    config = scripted_config()

    def synthetic_graph(b, models, cfg, saver, goal, **kwargs):
        async def model_step(state):
            eid = b.store.latest_execution(b.thread)["execution_id"]
            b.store.reserve_model_call(b.thread, "site", cfg.max_model_calls, eid)
            return {"messages": [AIMessage(content="Synthetic model step; no scientific output.")]}

        graph = StateGraph(MessagesState)
        graph.add_node("model", model_step)
        graph.add_node("tools", lambda state: {})
        graph.add_edge(START, "model")
        graph.add_edge("model", "tools")
        graph.add_edge("tools", "model")
        return graph.compile(checkpointer=saver)

    monkeypatch.setattr(harness, "create_harness", synthetic_graph)
    with pytest.raises(AgentBoundaryError, match="model-call budget"):
        await run_session(bridge, config, {}, "Synthetic 64-round graph admission")
    calls = [e["payload"] for e in bridge.store.events(bridge.thread) if e["kind"] == "model-call"]
    assert [c["call"] for c in calls] == list(range(1, 65))
    assert len({c["execution_id"] for c in calls}) == 1
    assert not bridge._jobs()
