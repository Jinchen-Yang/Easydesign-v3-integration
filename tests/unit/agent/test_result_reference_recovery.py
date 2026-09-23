"""An unknown ID can be repaired without granting or widening evidence access."""

import json
from types import SimpleNamespace
from typing import Any

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.checkpoint.memory import MemorySaver

from easydesign.agent.contracts import AgentBoundaryError, UnknownEvidenceResult
from easydesign.agent.design import DesignBridge
from easydesign.agent.evidence_output import result_tool, verified_result
from easydesign.agent.harness import RoleBoundary, create_harness
from easydesign.agent.phase2 import Phase2Bridge
from easydesign.agent.phase2_tools import PHASE2_ALLOWED
from tests.agent_support import scripted_config
from tests.unit.agent.test_prerequisite_recovery import assert_inspection_stopped
from tests.unit.agent.test_tool_argument_recovery import (
    KEYS,
    SNAPSHOT,
    ProjectionModel,
    guarded_read,
    offload,
)

UNKNOWN = "/result-deadbeef.json"


@pytest.mark.asyncio
async def test_unissued_reference_lists_only_current_owned_ids_then_checks_exact_read(
    bridge: Any,
) -> None:
    b = Phase2Bridge(bridge.project, bridge.thread, bridge.store)
    old = b.store.begin_execution(b.thread, "Before follow-up")["execution_id"]
    old_ref = offload(b, old)
    current = b.store.begin_execution(b.thread, "Follow-up", followup=True)["execution_id"]
    own = offload(b, current)
    foreign = offload(b, current, role="site")
    error = json.loads((await guarded_read(b, current, ref=UNKNOWN, fields=KEYS)).content)
    assert error["error_code"] == "UNKNOWN_EVIDENCE_RESULT"
    assert error["available_result_refs"] == [own]
    assert error["more_results_available"] is False
    assert "value" not in error and "chains" not in error["message"]
    assert error["repair_attempt"] == 1
    short = error["available_result_handles"][0]["ref"]
    assert short.startswith("result:")
    for denied in (old_ref, foreign):
        with pytest.raises(AgentBoundaryError, match="not supplied"):
            await guarded_read(b, current, ref=denied, fields=KEYS)
    read = json.loads((await guarded_read(b, current, ref=short, fields=KEYS)).content)
    assert read["value"] == {key: SNAPSHOT[key] for key in KEYS}
    assert len([e for e in b.store.events(b.thread) if e["kind"] == "tool-argument-repair"]) == 1


class ReferenceRepairModel(ProjectionModel):
    def answer(self, messages: Any) -> AIMessage:
        reads = [
            m for m in messages if isinstance(m, ToolMessage) and m.name == "read_evidence_result"
        ]
        if self.role == "target" and reads and reads[-1].status == "error":
            error = json.loads(reads[-1].content)
            assert error["error_code"] == "UNKNOWN_EVIDENCE_RESULT"
            self.repairs.append(error)
            self.result_ref = error["available_result_handles"][0]["ref"]
            return self.call("read_evidence_result", ref=self.result_ref, fields=KEYS)
        return super().answer(messages)


@pytest.mark.asyncio
@pytest.mark.parametrize("reference_kind", ["unknown-id", "hash-as-handle"])
async def test_actual_harness_recovers_unissued_id_with_explicit_authorized_read(
    bridge: Any,
    reference_kind: str,
) -> None:
    b = Phase2Bridge(bridge.project, bridge.thread, bridge.store)
    goal = "Inspect the existing evidence only"
    execution = b.store.begin_execution(b.thread, goal)["execution_id"]
    ref = offload(b, execution)
    requested = (
        "result:" + ref.removeprefix("/result-").removesuffix(".json")
        if reference_kind == "hash-as-handle"
        else UNKNOWN
    )
    models = {
        role: ReferenceRepairModel(role=role, result_ref=requested, bad_selector={"fields": KEYS})
        for role in PHASE2_ALLOWED
    }
    graph = create_harness(
        b, models, scripted_config(), MemorySaver(), goal, execution_id=execution
    )
    result = await graph.ainvoke(
        {"messages": [HumanMessage(content=goal)]}, {"configurable": {"thread_id": b.thread}}
    )
    assert_inspection_stopped(b, result)
    assert models["target"].repairs[0]["available_result_handles"][0]["original_ref"] == ref
    assert models["target"].result_ref.startswith("result:")
    assert len(models["target"].repairs) == 1
    assert models["target"].observed == {key: SNAPSHOT[key] for key in KEYS}
    assert not b._jobs()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "reference_kind", ["hash-as-handle", "literal-display-label", "missing-reference"]
)
async def test_binder_repairs_malformed_reference_with_current_owned_reference(
    bridge: Any, reference_kind: str
) -> None:
    b = DesignBridge(bridge.project, bridge.thread, bridge.store)
    execution = b.store.begin_execution(b.thread, "Inspect design evidence")["execution_id"]
    original = offload(b, execution, role="binder")
    malformed = {
        "hash-as-handle": "result:" + original.removeprefix("/result-").removesuffix(".json"),
        "literal-display-label": "full_result",
        "missing-reference": None,
    }[reference_kind]
    guard = RoleBoundary(
        b, "binder", scripted_config(), "Inspect design evidence", execution_id=execution
    )

    async def call(ref: str | None) -> ToolMessage:
        request = SimpleNamespace(
            tool_call={
                "name": "read_evidence_result",
                "args": {} if ref is None else {"ref": ref, "fields": KEYS},
                "id": "read",
            }
        )

        async def handler(request: Any) -> ToolMessage:
            return ToolMessage(
                content=await result_tool(b, "binder").ainvoke(request.tool_call["args"]),
                name="read_evidence_result",
                tool_call_id="read",
            )

        return await guard.awrap_tool_call(request, handler)

    repair = await call(malformed)
    payload = json.loads(repair.content)
    assert repair.status == "error"
    assert payload["error_code"] == "UNKNOWN_EVIDENCE_RESULT"
    assert payload["available_result_refs"] == [original]
    handle = payload["available_result_handles"][0]["ref"]
    assert handle.startswith("result:") and handle != malformed

    read = await call(handle)
    assert read.status == "success"
    assert json.loads(read.content)["value"] == {key: SNAPSHOT[key] for key in KEYS}
    assert len([e for e in b.store.events(b.thread) if e["kind"] == "tool-argument-repair"]) == 1


@pytest.mark.asyncio
async def test_unknown_reference_uses_existing_shared_repair_budget(bridge: Any) -> None:
    b = Phase2Bridge(bridge.project, bridge.thread, bridge.store)
    execution = b.store.begin_execution(b.thread, "Inspect")["execution_id"]
    b.store.reserve_prerequisite_repair(b.thread, "site", execution, "UniProt:P00698")
    for attempt in range(2, 5):
        error = json.loads((await guarded_read(b, execution, ref=UNKNOWN)).content)
        assert error["repair_attempt"] == attempt and error["available_result_refs"] == []
    with pytest.raises(AgentBoundaryError, match="repair budget exhausted"):
        await guarded_read(b, execution, ref=UNKNOWN)


def test_navigation_is_bounded_and_never_softens_unregistered_files_or_judge(bridge: Any) -> None:
    execution = bridge.store.begin_execution(bridge.thread, "Inspect")["execution_id"]
    refs = [offload(bridge, execution) for _ in range(22)]
    with pytest.raises(UnknownEvidenceResult) as caught:
        verified_result(bridge, "target", UNKNOWN, execution_id=execution)
    assert caught.value.result()["available_result_refs"] == list(reversed(refs[-20:]))
    assert caught.value.result()["more_results_available"] is True
    with pytest.raises(AgentBoundaryError):
        verified_result(bridge, "judge", UNKNOWN, execution_id=execution)
    path = bridge.store.root / "agent-work" / bridge.thread / UNKNOWN[1:]
    path.write_text('{"unregistered":true}')
    with pytest.raises(AgentBoundaryError):
        verified_result(bridge, "target", UNKNOWN, execution_id=execution)


@pytest.mark.asyncio
async def test_full_repair_catalog_stays_inline_without_creating_an_evidence_result(
    bridge: Any,
) -> None:
    b = Phase2Bridge(bridge.project, bridge.thread, bridge.store)
    execution = b.store.begin_execution(b.thread, "Inspect")["execution_id"]
    for _ in range(22):
        offload(b, execution)
    error = await guarded_read(b, execution, ref=UNKNOWN)
    payload = json.loads(error.content)
    assert error.status == "error" and payload["error_code"] == "UNKNOWN_EVIDENCE_RESULT"
    assert len(payload["available_result_handles"]) == 20
    assert "full_result" not in payload
    assert len([e for e in b.store.events(b.thread) if e["kind"] == "tool-view"]) == 22


@pytest.mark.parametrize("violation", ["role", "thread", "execution", "tamper"])
def test_short_handle_retains_original_authority_and_integrity(bridge: Any, violation: str) -> None:
    from easydesign.core import ArtifactIntegrityError

    execution = bridge.store.begin_execution(bridge.thread, "Inspect")["execution_id"]
    ref = offload(bridge, execution)
    event = next(e for e in bridge.store.events(bridge.thread) if e["kind"] == "tool-view")
    handle = f"result:{event['seq']}"
    role = "target"
    if violation == "role":
        role = "site"
    elif violation == "thread":
        bridge = Phase2Bridge(bridge.project, "other-reader", bridge.store)
        execution = bridge.store.begin_execution(bridge.thread, "Inspect")["execution_id"]
    elif violation == "execution":
        execution = bridge.store.begin_execution(bridge.thread, "Follow-up", followup=True)[
            "execution_id"
        ]
    else:
        (bridge.store.root / "agent-work" / bridge.thread / ref[1:]).write_text("{}")
    with pytest.raises((AgentBoundaryError, ArtifactIntegrityError)):
        verified_result(bridge, role, handle, execution_id=execution)
