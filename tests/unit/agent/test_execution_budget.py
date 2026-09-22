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

from easydesign.agent.context_policy import (
    SummaryAccounting,
    context_usage,
    input_context_tokens,
    research_memory,
)
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
        assert config.hard_input_chars == 250000
        assert config.max_input_chars == 120000
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
        # Summary 33 is charged once in the total provider ledger without consuming
        # the scientific-call allowance.
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
        auxiliary = [e["payload"] for e in events if e["kind"] == "auxiliary-model-call"]
        assert [c["call"] for c in calls] == list(range(1, 64))
        assert [c["lifetime_call"] for c in calls] == [*range(1, 33), *range(34, 65)]
        assert [c["provider_call"] for c in auxiliary] == [33]
        assert {c["execution_id"] for c in calls} == {eid}
        expected = Counter(roles[i % len(roles)] for i in [*range(32), *range(33, 64)])
        assert Counter(c["role"] for c in calls) == expected
        assert len([e for e in events if e["kind"] == "framework-summary-call"]) == 1
        assert len([e for e in events if e["kind"] == "framework-summary-response"]) == 1
        for role in roles:
            with pytest.raises(AgentBoundaryError, match="provider-call safeguard"):
                store.reserve_model_call(thread, role, config.max_model_calls, eid)
        b.store = store
        restarted_callback = SummaryAccounting(
            b, config, "site", eid, SimpleNamespace(profile=None)
        )
        with pytest.raises(AgentBoundaryError, match="provider-call safeguard"):
            await restarted_callback.on_chat_model_start(
                {}, [[HumanMessage(content="Must not run")]], run_id="65"
            )
        assert store.events(thread) == events
    finally:
        store.close()


def test_research_memory_does_not_treat_hidden_reasoning_as_replayed_context(
    tmp_path: Path,
) -> None:
    config = scripted_config()
    store = SessionStore(tmp_path)
    bridge = SimpleNamespace(store=store, thread="reported-token-control")
    execution = store.begin_execution(bridge.thread, "Synthetic reported-token control")
    model = FakeListChatModel(responses=["unused"])
    memory = research_memory(
        bridge,
        config,
        model,
        FilesystemBackend(root_dir=tmp_path / "history", virtual_mode=True),
        execution["execution_id"],
    )
    messages = [
        HumanMessage(content="Short request context."),
        AIMessage(
            content="Short response.",
            usage_metadata={
                "input_tokens": 100,
                "output_tokens": 50000,
                "total_tokens": 50100,
            },
            response_metadata={"model_provider": "openai"},
        ),
    ]
    try:
        total = input_context_tokens(messages)
        assert total < 100
        assert memory._should_summarize(messages, total) is False
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
@pytest.mark.parametrize(
    "rounds,chars_over_soft_target,summaries",
    [(2, 0, 0), (2, 20000, 1), (6, 4000, 1), (2, 40000, 1)],
)
async def test_native_summary_preserves_one_large_batch_of_guard_headroom(
    tmp_path: Path, rounds: int, chars_over_soft_target: int, summaries: int
) -> None:
    config = scripted_config()
    chars = config.max_input_chars + chars_over_soft_target
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
        assert len([e for e in events if e["kind"] == "model-call"]) == 1
        assert len([e for e in events if e["kind"] == "auxiliary-model-call"]) == summaries
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
    messages = history(6, config.max_input_chars + 4000)
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
        assert [c["call"] for c in calls] == [1, 2]
        assert len([e for e in events if e["kind"] == "auxiliary-model-call"]) == 1
        assert {c["execution_id"] for c in calls} == {eid}
    finally:
        store.close()


@pytest.mark.asyncio
async def test_large_completed_batch_is_summarized_before_guard_without_losing_trace(
    tmp_path: Path,
) -> None:
    config = scripted_config()
    project = tmp_path / "project"
    project.mkdir()
    store = SessionStore(project)
    bridge = SimpleNamespace(store=store, thread="large-completed-batch")
    eid = store.begin_execution(bridge.thread, "Synthetic large batch")["execution_id"]
    model = FakeListChatModel(
        responses=["Synthetic memory: preserve source-A counterevidence and unresolved access."]
    )
    backend = FilesystemBackend(root_dir=tmp_path / "history", virtual_mode=True)
    messages = history(4, 40000)
    batch = [
        AIMessage(
            content=[
                {
                    "type": "thinking",
                    "thinking": "synthetic " * (config.hard_input_chars // len("synthetic ") + 1),
                    "signature": "test",
                }
            ],
            tool_calls=[
                {"name": "read_evidence", "args": {}, "id": f"large-{i}"} for i in range(6)
            ],
        ),
        *[
            ToolMessage(
                content=f"source-A counterevidence {i}: " + "x" * 3800,
                name="read_evidence",
                tool_call_id=f"large-{i}",
            )
            for i in range(6)
        ],
    ]
    messages.extend(batch)
    original = [message.model_dump() for message in messages]
    system = SystemMessage(content="Synthetic runtime context. " + "s" * 30000)
    with pytest.raises(AgentBoundaryError, match="hard context guard"):
        context_usage(model, config, "site", [system, *batch])
    received = []

    async def handler(request: Any) -> Any:
        received.append(request.messages)
        context_usage(model, config, "site", [request.system_message, *request.messages])
        store.reserve_model_call(bridge.thread, "site", config.max_model_calls, eid)
        return ModelResponse(result=[AIMessage(content="Synthetic continuation")])

    try:
        result = await research_memory(bridge, config, model, backend, eid).awrap_model_call(
            ModelRequest(
                model=model,
                system_message=system,
                messages=messages,
                state={"messages": messages},
                tools=[],
            ),
            handler,
        )
        event = result.command.update["_summarization_event"]
        assert event["cutoff_index"] == len(messages)
        assert received == [[event["summary_message"]]]
        archive = tmp_path / "history" / event["file_path"].lstrip("/")
        for i in range(6):
            assert f"source-A counterevidence {i}: " + "x" * 3800 in archive.read_text()
        assert [message.model_dump() for message in messages] == original
        events = store.events(bridge.thread)
        assert sum(e["kind"] == "framework-summary-call" for e in events) == 1
        assert sum(e["kind"] == "model-call" for e in events) == 1
        assert sum(e["kind"] == "auxiliary-model-call" for e in events) == 1
    finally:
        store.close()


@pytest.mark.asyncio
async def test_complete_agent_summary_keeps_new_tool_results_and_checkpoint_tail(
    tmp_path: Path, monkeypatch: Any
) -> None:
    import deepagents.graph as factory
    from deepagents.middleware.summarization import SummarizationMiddleware
    from langchain.agents.middleware.types import AgentMiddleware
    from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
    from langchain_core.outputs import ChatGeneration, ChatResult
    from langchain_core.tools import tool
    from langgraph.checkpoint.memory import InMemorySaver

    class ContinuationModel(FakeMessagesListChatModel):
        def bind_tools(self, tools: Any, **kwargs: Any) -> Any:
            return self

        def _generate(
            self, messages: Any, stop: Any = None, run_manager: Any = None, **kwargs: Any
        ) -> Any:
            if any(isinstance(c, SummaryAccounting) for c in self.callbacks or []):
                return ChatResult(
                    generations=[
                        ChatGeneration(
                            message=AIMessage(
                                content=(
                                    "Synthetic summary: source-A counterevidence "
                                    "remains unresolved."
                                )
                            )
                        )
                    ]
                )
            return super()._generate(messages, stop=stop, run_manager=run_manager, **kwargs)

    @tool
    def read_new_evidence() -> str:
        """Read a synthetic source after summary creation."""
        return "NEW-SOURCE: exposure does not establish whole-binder accessibility."

    config = scripted_config()
    project = tmp_path / "project"
    project.mkdir()
    store = SessionStore(project)
    bridge = SimpleNamespace(store=store, thread="assembled-research-memory")
    eid = store.begin_execution(bridge.thread, "Synthetic assembled memory")["execution_id"]
    received: list[list[Any]] = []

    class Boundary(AgentMiddleware):
        async def awrap_model_call(self, request: Any, handler: Any) -> Any:
            received.append(list(request.messages))
            context_usage(
                request.model, config, "site", [request.system_message, *request.messages]
            )
            calls = {
                call["id"]
                for m in request.messages
                if isinstance(m, AIMessage)
                for call in m.tool_calls
            }
            assert all(
                m.tool_call_id in calls for m in request.messages if isinstance(m, ToolMessage)
            ), "Summary split a tool transaction"
            store.reserve_model_call(bridge.thread, "site", config.max_model_calls, eid)
            return await handler(request)

    model = ContinuationModel(
        responses=[
            AIMessage(
                content="Read the next source",
                tool_calls=[{"name": "read_new_evidence", "args": {}, "id": "fresh-call"}],
            ),
            AIMessage(content="New evidence retained; access remains uncertain."),
            AIMessage(content="Checkpoint follow-up retains the same source."),
        ]
    )
    backend = FilesystemBackend(root_dir=tmp_path / "history", virtual_mode=True)
    memory = research_memory(bridge, config, model, backend, eid)
    original_factory = factory.create_agent
    assembled = []

    def capture_factory(*args: Any, **kwargs: Any) -> Any:
        if kwargs.get("name") == "research-memory-regression":
            assembled.extend(kwargs["middleware"])
        return original_factory(*args, **kwargs)

    monkeypatch.setattr(factory, "create_agent", capture_factory)
    graph = factory.create_deep_agent(
        model=model,
        tools=[read_new_evidence],
        backend=backend,
        middleware=[memory, Boundary()],
        checkpointer=InMemorySaver(),
        system_prompt="Synthetic research context. " + "s" * 30000,
        name="research-memory-regression",
    )
    messages = history(4, 40000)
    messages.extend(
        [
            AIMessage(
                content=[
                    {"type": "thinking", "thinking": "synthetic " * 6000, "signature": "test"}
                ],
                tool_calls=[{"name": "read_evidence", "args": {}, "id": "large"}],
            ),
            ToolMessage(
                content="source-A counterevidence: " + "x" * 22000,
                tool_call_id="large",
                name="read_evidence",
            ),
        ]
    )
    for i, message in enumerate(messages):
        message.id = f"initial-{i}"
    original = [m.model_dump() for m in messages]
    run_config = {"configurable": {"thread_id": bridge.thread}}
    try:
        result = await graph.ainvoke({"messages": messages}, run_config)
        assert len(received) == 2
        assert any(
            isinstance(m, ToolMessage)
            and m.tool_call_id == "fresh-call"
            and m.content.startswith("NEW-SOURCE:")
            for m in received[-1]
        )
        assert [m for m in assembled if isinstance(m, SummarizationMiddleware)] == [memory]
        event = (await graph.aget_state(run_config)).values["_summarization_event"]
        assert event["cutoff_index"] == len(messages)
        archive = tmp_path / "history" / event["file_path"].lstrip("/")
        saved = archive.read_bytes()
        assert b"source-A counterevidence" in saved
        assert [m.model_dump() for m in messages] == original
        store.close()
        bridge.store = store = SessionStore(project)
        await graph.ainvoke(
            {"messages": [HumanMessage(content="Continue from checkpoint.")]}, run_config
        )
        assert received[-1] == [
            event["summary_message"],
            *result["messages"][event["cutoff_index"] :],
            received[-1][-1],
        ]
        assert received[-1][-1].content == "Continue from checkpoint."
        assert any(
            isinstance(m, ToolMessage) and m.tool_call_id == "fresh-call" for m in received[-1]
        )
        assert archive.read_bytes() == saved
        events = store.events(bridge.thread)
        assert sum(e["kind"] == "framework-summary-call" for e in events) == 1
        assert sum(e["kind"] == "model-call" for e in events) == 3
        assert sum(e["kind"] == "auxiliary-model-call" for e in events) == 1
    finally:
        store.close()


@pytest.mark.parametrize("tail_kind", ["missing", "duplicate", "orphan", "new-user-message"])
def test_tail_retention_does_not_hide_incomplete_calls_or_new_user_input(
    tmp_path: Path, tail_kind: str
) -> None:
    messages: list[Any] = [
        AIMessage(
            content="synthetic " * 6000,
            tool_calls=[{"name": "read", "args": {}, "id": "a"}],
        ),
        ToolMessage(content="Source result", tool_call_id="a"),
    ]
    if tail_kind == "missing":
        messages.pop()
    elif tail_kind == "duplicate":
        messages.append(ToolMessage(content="Duplicate result", tool_call_id="a"))
    elif tail_kind == "orphan":
        messages.append(ToolMessage(content="Unpaired result", tool_call_id="b"))
    else:
        messages.append(HumanMessage(content="A new explicit constraint must remain visible."))
    memory = research_memory(
        SimpleNamespace(),
        scripted_config(),
        FakeListChatModel(responses=["unused"]),
        FilesystemBackend(root_dir=tmp_path / "history", virtual_mode=True),
        "unused",
    )
    assert memory._determine_cutoff_index(messages) < len(messages)


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
