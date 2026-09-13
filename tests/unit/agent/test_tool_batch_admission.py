"""Native tool batches retain complete delivery; the shared model guard owns input admission."""

import asyncio
import json
from types import SimpleNamespace
from typing import Any

import pytest
from langchain.tools.tool_node import ToolCallRequest
from langchain_core.messages import AIMessage, ToolMessage

from easydesign.agent.contracts import AgentBoundaryError
from easydesign.agent.harness import RoleBoundary
from easydesign.agent.phase2 import Phase2Bridge
from tests.agent_support import scripted_config


def request(call: dict[str, Any], calls: list[dict[str, Any]], batch: str) -> ToolCallRequest:
    return ToolCallRequest(
        tool_call=call,
        tool=None,
        state={"messages": [AIMessage(content="", id=batch, tool_calls=calls)]},
        runtime=SimpleNamespace(),
    )


@pytest.mark.asyncio
async def test_native_batch_preserves_complete_first_delivery_without_local_budget(
    bridge: Any,
) -> None:
    bridge = Phase2Bridge(bridge.project, bridge.thread, bridge.store)
    execution = bridge.store.begin_execution(bridge.thread, "Inspect receptor")["execution_id"]
    guard = RoleBoundary(bridge, "site", scripted_config(), "Inspect", execution_id=execution)
    calls = [
        {"id": "analysis", "name": "analyze_receptor_context", "args": {}, "type": "tool_call"},
        {
            "id": "skill",
            "name": "read_file",
            "args": {"file_path": "/skills/site-mechanism/references/membrane.md"},
            "type": "tool_call",
        },
    ]
    executed = []

    async def handler(req: Any) -> ToolMessage:
        executed.append(req.tool_call["id"])
        return ToolMessage(
            content=json.dumps({"scientific_fact": "all retained"}),
            tool_call_id=req.tool_call["id"],
            name=req.tool_call["name"],
        )

    answers = await asyncio.gather(
        *[guard.awrap_tool_call(request(c, calls, "batch-1"), handler) for c in calls]
    )
    assert set(executed) == {"analysis", "skill"}
    assert all(a.status == "success" for a in answers)
    assert all(json.loads(a.content)["scientific_fact"] == "all retained" for a in answers)
    events = bridge.store.events(bridge.thread)
    assert not [e for e in events if e["kind"] == "tool-argument-repair"]
    assert len([e for e in events if e["kind"] == "tool"]) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("foreign", ["file", "result", "tool"])
async def test_oversized_batch_does_not_soften_authority_errors(bridge: Any, foreign: str) -> None:
    bridge = Phase2Bridge(bridge.project, bridge.thread, bridge.store)
    execution = bridge.store.begin_execution(bridge.thread, "Inspect receptor")["execution_id"]
    guard = RoleBoundary(bridge, "site", scripted_config(), "Inspect", execution_id=execution)
    bad = {
        "file": ("read_file", {"file_path": "/skills/binder-strategy/SKILL.md"}),
        "result": ("read_evidence_result", {"ref": "/result-foreign.json", "field": "bad"}),
        "tool": ("prepare_target", {}),
    }[foreign]
    call = {"id": "bad", "name": bad[0], "args": bad[1], "type": "tool_call"}
    calls = [
        {"id": "analysis", "name": "analyze_receptor_context", "args": {}, "type": "tool_call"},
        call,
    ]

    async def forbidden(_: Any) -> Any:
        pytest.fail("Foreign request handler executed")

    with pytest.raises(AgentBoundaryError):
        await guard.awrap_tool_call(request(call, calls, "foreign"), forbidden)
    assert not any(e["kind"] == "tool-argument-repair" for e in bridge.store.events(bridge.thread))


@pytest.mark.asyncio
async def test_short_reference_and_four_receipts_are_not_oversized(bridge: Any) -> None:
    bridge = Phase2Bridge(bridge.project, bridge.thread, bridge.store)
    execution = bridge.store.begin_execution(bridge.thread, "Inspect receptor")["execution_id"]
    guard = RoleBoundary(bridge, "site", scripted_config(), "Inspect", execution_id=execution)
    calls = [
        {
            "id": "reference",
            "name": "read_file",
            "args": {"file_path": "/skills/site-mechanism/references/membrane.md"},
            "type": "tool_call",
        },
        *[
            {
                "id": f"receipt-{n}",
                "name": "research_evidence",
                "type": "tool_call",
                "args": {
                    "operation": "primary-record",
                    "identifier": "21228869",
                    "topic": "function",
                    "question": "What was measured?",
                },
            }
            for n in range(4)
        ],
    ]
    executed = []

    async def handler(req: Any) -> ToolMessage:
        executed.append(req.tool_call["id"])
        return ToolMessage(content='{"status":"fixture"}', tool_call_id=req.tool_call["id"])

    await asyncio.gather(
        *[guard.awrap_tool_call(request(c, calls, "small-pages"), handler) for c in calls]
    )
    assert set(executed) == {c["id"] for c in calls}
    assert not any(e["kind"] == "tool-argument-repair" for e in bridge.store.events(bridge.thread))
