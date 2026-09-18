"""Parallel prerequisite failures share a correction opportunity, never source authority."""

import asyncio
import json
from types import SimpleNamespace
from typing import Any

import pytest
from langchain.tools.tool_node import ToolCallRequest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from easydesign.agent.contracts import AgentBoundaryError
from easydesign.agent.evidence_research import EvidenceResearch, ResearchQuery
from easydesign.agent.harness import RoleBoundary
from easydesign.agent.phase2 import Phase2Bridge
from easydesign.agent.session_store import SessionStore
from tests.agent_support import scripted_config
from tests.unit.agent.test_prerequisite_recovery import source_transport


@pytest.mark.asyncio
async def test_parallel_source_diagnostics_all_reach_model_before_round_budget(
    bridge: Any, monkeypatch: Any
) -> None:
    bridge = Phase2Bridge(bridge.project, bridge.thread, bridge.store)
    execution = bridge.store.begin_execution(bridge.thread, "Inspect five sources")["execution_id"]
    requests = source_transport(bridge, monkeypatch)
    guard = RoleBoundary(bridge, "target", scripted_config(), "Inspect", execution_id=execution)
    research = EvidenceResearch(bridge)
    calls = [
        {
            "id": f"call-{n}",
            "name": "research_evidence",
            "type": "tool_call",
            "args": {
                "operation": "primary-fulltext",
                "identifier": f"PMC{123 + n}",
                "topic": "function",
                "question": "What was experimentally measured?",
            },
        }
        for n in range(5)
    ]
    state = {
        "messages": [
            HumanMessage(content="Inspect sources"),
            AIMessage(content="", id="batch-1", tool_calls=calls),
        ]
    }

    async def acquire(request: Any) -> Any:
        value = research.acquire(
            ResearchQuery.model_validate(request.tool_call["args"]), role="target"
        )
        return ToolMessage(
            content=json.dumps(value),
            tool_call_id=request.tool_call["id"],
            name="research_evidence",
        )

    results = await asyncio.gather(
        *[
            guard.awrap_tool_call(
                ToolCallRequest(tool_call=call, tool=None, state=state, runtime=SimpleNamespace()),
                acquire,
            )
            for call in calls
        ]
    )
    assert requests == []  # No source acquisition or implicit selection occurred.
    assert len(results) == 5 and all(v.status == "error" for v in results)
    errors = [json.loads(v.content) for v in results]
    assert {v["repair_attempt"] for v in errors} == {1}
    assert len({v["source_id"] for v in errors}) == 5
    assert all(v["required_action"] == "select_evidence" for v in errors)
    events = [
        e["payload"]
        for e in bridge.store.events(bridge.thread)
        if e["kind"] == "prerequisite-repair"
    ]
    assert len(events) == 5 and len({e["round_id"] for e in events}) == 1
    assert not any(e["kind"] == "evidence-selection" for e in bridge.store.events(bridge.thread))
    # A real new model message is a new opportunity, even for the same source arguments.
    new_state = {
        "messages": [
            *state["messages"],
            *results,
            AIMessage(content="", id="batch-2", tool_calls=calls),
        ]
    }
    result = await guard.awrap_tool_call(
        ToolCallRequest(tool_call=calls[0], tool=None, state=new_state, runtime=SimpleNamespace()),
        acquire,
    )
    assert json.loads(result.content)["repair_attempt"] == 2


def test_repair_rounds_preserve_legacy_counts_and_replay_across_restart(bridge: Any) -> None:
    store = bridge.store
    execution = store.begin_execution(bridge.thread, "Inspect")["execution_id"]
    assert store.reserve_tool_argument_repair(bridge.thread, "target", execution) == 1
    assert (
        store.reserve_prerequisite_repair(
            bridge.thread, "site", execution, "one", round_id="batch-a"
        )
        == 2
    )
    assert (
        store.reserve_tool_argument_repair(bridge.thread, "site", execution, round_id="batch-a")
        == 2
    )
    reopened = SessionStore(bridge.project)
    try:
        assert (
            reopened.reserve_prerequisite_repair(
                bridge.thread, "site", execution, "two", round_id="batch-a"
            )
            == 2
        )
        assert (
            reopened.reserve_tool_argument_repair(
                bridge.thread, "target", execution, round_id="batch-a"
            )
            == 3
        )
        assert (
            reopened.reserve_tool_argument_repair(
                bridge.thread, "site", execution, round_id="batch-b"
            )
            == 4
        )
        with pytest.raises(AgentBoundaryError, match="budget exhausted"):
            reopened.reserve_tool_argument_repair(
                bridge.thread, "site", execution, round_id="batch-c"
            )
        # Replay of an already delivered native batch is still the same opportunity.
        assert (
            reopened.reserve_tool_argument_repair(
                bridge.thread, "site", execution, round_id="batch-a"
            )
            == 2
        )
        current = reopened.begin_execution(bridge.thread, "Explicit follow-up", followup=True)[
            "execution_id"
        ]
        with pytest.raises(AgentBoundaryError, match="not bound"):
            reopened.reserve_tool_argument_repair(
                bridge.thread, "site", execution, round_id="batch-a"
            )
        assert (
            reopened.reserve_tool_argument_repair(
                bridge.thread, "site", current, round_id="batch-a"
            )
            == 1
        )
    finally:
        reopened.close()


def test_scoped_repairs_do_not_share_one_execution_budget(bridge: Any) -> None:
    store = bridge.store
    execution = store.begin_execution(bridge.thread, "Inspect independent tools")["execution_id"]

    for index in range(7):
        assert (
            store.reserve_tool_argument_repair(
                bridge.thread,
                "site",
                execution,
                round_id=f"batch-{index}",
                scope=f"tool-{index}",
            )
            == 1
        )


def test_scoped_repair_streak_resets_after_success_and_survives_restart(bridge: Any) -> None:
    store = bridge.store
    execution = store.begin_execution(bridge.thread, "Repair one tool")["execution_id"]
    def reserve(batch: str) -> int:
        return store.reserve_tool_argument_repair(
            bridge.thread,
            "site",
            execution,
            round_id=batch,
            scope="retrieve_evidence",
        )

    assert reserve("batch-a") == 1
    assert reserve("batch-b") == 2
    assert reserve("batch-b") == 2

    reopened = SessionStore(bridge.project)
    try:
        assert (
            reopened.reserve_tool_argument_repair(
                bridge.thread,
                "site",
                execution,
                round_id="batch-c",
                scope="retrieve_evidence",
            )
            == 3
        )
        reopened.mark_tool_repair_success(
            bridge.thread,
            "site",
            execution,
            "retrieve_evidence",
            round_id="batch-success",
        )
        for attempt, batch in enumerate(("batch-d", "batch-e", "batch-f", "batch-g"), 1):
            assert (
                reopened.reserve_tool_argument_repair(
                    bridge.thread,
                    "site",
                    execution,
                    round_id=batch,
                    scope="retrieve_evidence",
                )
                == attempt
            )
        with pytest.raises(AgentBoundaryError, match="consecutive rounds"):
            reopened.reserve_tool_argument_repair(
                bridge.thread,
                "site",
                execution,
                round_id="batch-h",
                scope="retrieve_evidence",
            )
        assert (
            reopened.reserve_prerequisite_repair(
                bridge.thread,
                "site",
                execution,
                "GPCRdb:TACR2_HUMAN",
                round_id="batch-other",
                scope="research_evidence",
            )
            == 1
        )
    finally:
        reopened.close()
