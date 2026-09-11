"""Real DeepAgents loops with synthetic evidence; no scientific approval or network."""

import json
from types import SimpleNamespace
from typing import Any

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.checkpoint.memory import MemorySaver
from pydantic import Field

from easydesign.agent.contracts import AgentBoundaryError, InvalidFieldProjection
from easydesign.agent.evidence_output import output_message, result_tool
from easydesign.agent.harness import RoleBoundary, create_harness
from easydesign.agent.phase2 import Phase2Bridge
from easydesign.agent.phase2_tools import PHASE2_ALLOWED
from easydesign.agent.session_store import SessionStore
from easydesign.core import ArtifactIntegrityError
from tests.agent_support import scripted_config
from tests.unit.agent.test_prerequisite_recovery import RecoveryModel

KEYS = ["chains", "identity_evidence", "options", "limitations"]
SNAPSHOT = {
    "chains": [{"chain": "L", "length": 129}],
    "identity_evidence": {"canonical": {"accession": "P00698", "length": 147}},
    "options": ["chain-l"],
    "limitations": ["Construct and canonical differ; this synthetic fixture is not approval"],
    "long_text": "x" * 5000,
    "rows": [{"index": n, "counterevidence": "z" * 900} for n in range(9)],
}


def offload(bridge: Any, execution_id: str, role: str = "target") -> str:
    result = output_message(
        bridge,
        role,
        execution_id,
        ToolMessage(
            content=json.dumps(SNAPSHOT), tool_call_id="source", name="read_target_evidence"
        ),
    )
    return str(json.loads(result.content)["full_result"])


class ProjectionModel(RecoveryModel):
    result_ref: str = ""
    bad_selector: dict[str, Any] = Field(default_factory=lambda: {"field": KEYS})
    observed: dict[str, Any] = Field(default_factory=dict)

    def answer(self, messages: Any) -> AIMessage:
        if self.role == "coordinator":
            return super().answer(messages)
        results = [m for m in messages if isinstance(m, ToolMessage)]
        if not results:
            return self.call("read_file", file_path="/skills/target-intelligence/SKILL.md")
        reads = [m for m in results if m.name == "read_evidence_result"]
        if not reads or self.repeat_error:
            return self.call("read_evidence_result", ref=self.result_ref, **self.bad_selector)
        last = reads[-1]
        if last.status == "error":
            error = json.loads(last.content)
            assert error["error_code"] == "INVALID_FIELD_PROJECTION"
            self.repairs.append(error)
            return self.call("read_evidence_result", ref=self.result_ref, fields=KEYS)
        self.observed.update(json.loads(last.content)["value"])
        return self.call(
            "TargetInterpretation",
            **{
                "interpretation": ["Read the bound snapshot"],
                "unresolved_identity": ["No canonical target was approved"],
                "limitations": ["Synthetic evidence does not establish biological validity"],
                "recommended_action": "Report the scoped evidence only",
            },
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "bad",
    [
        {"field": KEYS},
        {"fields": "chains"},
        {"field": "absent"},
        {"field": "chains", "fields": ["options"]},
    ],
)
async def test_actual_harness_corrects_projection_and_preserves_facts(
    bridge: Any, bad: Any
) -> None:
    bridge = Phase2Bridge(bridge.project, bridge.thread, bridge.store)
    goal = "Inspect the existing evidence only"
    execution = bridge.store.begin_execution(bridge.thread, goal)["execution_id"]
    ref = offload(bridge, execution)
    models = {
        role: ProjectionModel(role=role, result_ref=ref, bad_selector=bad)
        for role in PHASE2_ALLOWED
    }
    graph = create_harness(
        bridge, models, scripted_config(), MemorySaver(), goal, execution_id=execution
    )
    result = await graph.ainvoke(
        {"messages": [HumanMessage(content=goal)]}, {"configurable": {"thread_id": bridge.thread}}
    )
    assert result["messages"][-1].text.startswith("Evidence inspection ended")
    assert models["target"].observed == {key: SNAPSHOT[key] for key in KEYS}
    assert len(models["target"].repairs) == 1
    repairs = [e for e in bridge.store.events(bridge.thread) if e["kind"] == "tool-argument-repair"]
    assert repairs[0]["payload"]["attempt"] == 1
    assert not bridge._jobs()


@pytest.mark.asyncio
async def test_explicit_selectors_legacy_traversal_and_lossless_pagination(bridge: Any) -> None:
    execution = bridge.store.begin_execution(bridge.thread, "Inspect evidence")["execution_id"]
    ref = offload(bridge, execution)
    read = result_tool(bridge, "target")
    single = json.loads(await read.ainvoke({"ref": ref, "field": "identity_evidence"}))
    assert single["value"] == SNAPSHOT["identity_evidence"]
    projection = json.loads(await read.ainvoke({"ref": ref, "fields": KEYS}))
    assert projection["value"] == {key: SNAPSHOT[key] for key in KEYS}
    path = ["identity_evidence", "canonical"]
    nested = json.loads(await read.ainvoke({"ref": ref, "path": path}))
    legacy = json.loads(await read.ainvoke({"ref": ref, "field": path}))
    assert nested["value"] == legacy["value"] == SNAPSHOT["identity_evidence"]["canonical"]
    assert legacy["field"] == path and "deprecation" in legacy and "deprecation" not in nested
    with pytest.raises(InvalidFieldProjection):
        await read.ainvoke({"ref": ref, "field": KEYS})  # Never silently treat as siblings.
    for selector in (
        {"fields": ["chains", "absent"]},
        {"path": ["chains", "-1"]},
        {"path": ["chains", "99"]},
        {"fields": ["chains", "chains"]},
    ):
        with pytest.raises(InvalidFieldProjection):
            await read.ainvoke({"ref": ref, **selector})
    offset, rows = 0, []
    while offset is not None:
        page = json.loads(
            await read.ainvoke({"ref": ref, "field": "rows", "offset": offset, "limit": 8})
        )
        rows.extend(page["value"])
        offset = page["next_offset"]
    assert rows == SNAPSHOT["rows"]
    first = json.loads(await read.ainvoke({"ref": ref, "field": "long_text"}))
    second = json.loads(
        await read.ainvoke({"ref": ref, "field": "long_text", "offset": first["next_offset"]})
    )
    assert first["value"] + second["value"] == SNAPSHOT["long_text"]


async def guarded_read(bridge: Any, execution: str, **args: Any) -> Any:
    guard = RoleBoundary(bridge, "target", scripted_config(), "Inspect", execution_id=execution)
    request = SimpleNamespace(
        tool_call={"name": "read_evidence_result", "args": args, "id": "read"}
    )

    async def handler(request: Any) -> Any:
        return ToolMessage(
            content=await result_tool(bridge, "target").ainvoke(request.tool_call["args"]),
            name="read_evidence_result",
            tool_call_id="read",
        )

    return await guard.awrap_tool_call(request, handler)


@pytest.mark.asyncio
async def test_shared_two_repairs_survive_restart_resume_and_reset_only_for_followup(
    bridge: Any,
) -> None:
    bridge = Phase2Bridge(bridge.project, bridge.thread, bridge.store)
    execution = bridge.store.begin_execution(bridge.thread, "Inspect")["execution_id"]
    ref = offload(bridge, execution)
    bridge.store.reserve_prerequisite_repair(bridge.thread, "site", execution, "UniProt:P00698")
    error = json.loads((await guarded_read(bridge, execution, ref=ref, field=KEYS)).content)
    assert error["repair_attempt"] == 2  # Shared across roles and error categories.
    reopened = SessionStore(bridge.project)
    try:
        resumed = Phase2Bridge(bridge.project, bridge.thread, reopened)
        with pytest.raises(AgentBoundaryError, match="repair budget exhausted"):
            await guarded_read(resumed, execution, ref=ref, field=KEYS)
        with pytest.raises(AgentBoundaryError, match="repair budget exhausted"):
            reopened.reserve_prerequisite_repair(
                bridge.thread, "target", execution, "UniProt:P00698"
            )
        new = reopened.begin_execution(bridge.thread, "Follow-up", followup=True)["execution_id"]
        with pytest.raises(AgentBoundaryError, match="not bound"):
            await guarded_read(resumed, execution, ref=ref, field=KEYS)
        current_ref = offload(resumed, new)
        error = json.loads((await guarded_read(resumed, new, ref=current_ref, field=KEYS)).content)
        assert error["repair_attempt"] == 1
    finally:
        reopened.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("violation", ["role", "thread", "execution", "tamper", "path"])
async def test_bad_projection_never_softens_artifact_boundary(bridge: Any, violation: str) -> None:
    bridge = Phase2Bridge(bridge.project, bridge.thread, bridge.store)
    execution = bridge.store.begin_execution(bridge.thread, "Inspect")["execution_id"]
    ref = offload(bridge, execution, role="judge" if violation == "role" else "target")
    if violation == "thread":
        bridge = Phase2Bridge(bridge.project, "other-reader", bridge.store)
        execution = bridge.store.begin_execution(bridge.thread, "Inspect")["execution_id"]
    elif violation == "execution":
        execution = bridge.store.begin_execution(bridge.thread, "Follow-up", followup=True)[
            "execution_id"
        ]
    elif violation == "tamper":
        (bridge.store.root / "agent-work" / bridge.thread / ref[1:]).write_text("{}")
    elif violation == "path":
        ref = "/../foreign-project/private.json"
    with pytest.raises((AgentBoundaryError, ArtifactIntegrityError)):
        await guarded_read(bridge, execution, ref=ref, fields="invalid")
    assert not any(e["kind"] == "tool-argument-repair" for e in bridge.store.events(bridge.thread))
    assert not issubclass(InvalidFieldProjection, AgentBoundaryError)
