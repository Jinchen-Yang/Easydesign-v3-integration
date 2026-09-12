"""Parallel scientific answers must all reach their first model read."""

import json
from typing import Any

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from tests.agent_support import ScriptedModel, scripted_config


@pytest.mark.asyncio
@pytest.mark.parametrize("reasoning", [False, True])
async def test_site_boundary_delivers_whole_latest_batch_under_total_budget(
    site_bridge: Any, reasoning: bool
) -> None:
    from langchain.agents.middleware.types import ModelRequest, ModelResponse
    from langchain_core.tools import StructuredTool

    from easydesign.agent.harness import RoleBoundary
    from easydesign.agent.session_store import compact

    execution = site_bridge.store.begin_execution(site_bridge.thread, "SYNTHETIC batch delivery")
    config = scripted_config()
    config = config.model_copy(
        update={
            "roles": {
                "site": config.default.model_copy(
                    update={"reasoning_effort": "low" if reasoning else "none"}
                )
            }
        }
    )
    guard = RoleBoundary(
        site_bridge,
        "site",
        config,
        "Inspect every requested answer.",
        execution_id=execution["execution_id"],
    )
    messages: list[Any] = [HumanMessage(content="Original goal " + "g" * 18000)]

    def result(name: str, call_id: str, chars: int, source: str) -> ToolMessage:
        return ToolMessage(
            name=name,
            tool_call_id=call_id,
            content=compact(
                {
                    "full_result": f"/result-{int(call_id):x}.json",
                    "stored_fields": ["cards", "facts"],
                    "projection_aliases": ["candidate_overview", "topology_summary"],
                    "cards": [{"source_id": source, "passage": "p" * chars}],
                    "facts": {"mapping_status": "ambiguous", "glycan_occupancy": None},
                }
            ),
        )

    for index, (name, chars) in enumerate(
        [
            ("analyze_receptor_context", 26000),
            ("read_site_evidence", 6000),
            ("retrieve_evidence", 5000),
            ("retrieve_evidence", 5000),
            ("retrieve_evidence", 5000),
        ],
        start=1,
    ):
        call_id = str(index)
        messages.extend(
            [
                AIMessage(content="", tool_calls=[{"id": call_id, "name": name, "args": {}}]),
                result(name, call_id, chars, "old-" + call_id),
            ]
        )
    calls = [
        {"id": str(index + 10), "name": name, "args": {"question": "current-" + str(index)}}
        for index, name in enumerate(
            [
                "read_canonical_mapping",
                "read_canonical_mapping",
                "retrieve_evidence",
                "retrieve_evidence",
            ]
        )
    ]
    messages.append(AIMessage(content="", tool_calls=calls))
    latest = [
        result(c["name"], c["id"], size, "current-" + c["id"])
        for c, size in zip(calls, [3103, 4738, 4813, 4864], strict=True)
    ]
    messages.extend(latest)
    original = [m.model_dump() for m in messages]
    tools = [
        StructuredTool.from_function(
            lambda: None, name=name, description="SYNTHETIC context-only placeholder; not executed."
        )
        for name in guard.allowed
    ]
    request = ModelRequest(
        model=ScriptedModel(role="site"),
        messages=messages,
        tools=tools,
        system_message=SystemMessage(content="s" * 15000),
    )
    received = []

    async def handler(projected: Any) -> Any:
        received.append(projected)
        if reasoning:
            records = json.loads(projected.messages[1].content)["runtime_history"]
            results = {
                r["tool_call_id"]: r["content"] for r in records if r["kind"] == "tool-result"
            }
        else:
            results = {
                m.tool_call_id: json.loads(m.content)
                for m in projected.messages
                if isinstance(m, ToolMessage)
            }
        archived = [v for v in results.values() if isinstance(v, dict) and "archived_result" in v]
        assert archived and all(
            v["projection_aliases"] == ["candidate_overview", "topology_summary"] for v in archived
        )
        for message in latest:
            expected = json.loads(message.content)
            delivered = results[message.tool_call_id]
            assert delivered == expected
        return ModelResponse(
            result=[
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "id": "next",
                            "name": "read_site_evidence",
                            "args": {},
                        }
                    ],
                )
            ]
        )

    await guard.awrap_model_call(request, handler)
    assert len(received) == 1
    assert [m.model_dump() for m in messages] == original
    events = site_bridge.store.events(site_bridge.thread)
    assert any(e["kind"] == "context-compaction" for e in events)
    context = [e["payload"] for e in events if e["kind"] == "model-context"]
    assert len(context) == 1 and context[0]["context_chars"] <= 60000
