"""Real DeepAgents loops with synthetic evidence; no scientific approval or network."""

import json
from types import SimpleNamespace
from typing import Any

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.checkpoint.memory import MemorySaver
from pydantic import Field, ValidationError

from easydesign.agent.contracts import AgentBoundaryError, InvalidFieldProjection
from easydesign.agent.evidence_output import output_message, result_tool
from easydesign.agent.harness import RoleBoundary, create_harness
from easydesign.agent.phase2 import Phase2Bridge
from easydesign.agent.phase2_tools import PHASE2_ALLOWED
from easydesign.agent.session_store import SessionStore
from easydesign.core import ArtifactIntegrityError
from tests.agent_support import scripted_config
from tests.unit.agent.test_prerequisite_recovery import RecoveryModel, assert_inspection_stopped

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
    assert_inspection_stopped(bridge, result)
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
    assert nested["value"] == SNAPSHOT["identity_evidence"]["canonical"]
    with pytest.raises(ValidationError):
        await read.ainvoke({"ref": ref, "field": path})
    with pytest.raises(ValidationError):
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
async def test_rendered_projection_keeps_original_navigation_root_and_actionable_keys(
    bridge: Any,
) -> None:
    b = Phase2Bridge(bridge.project, bridge.thread, bridge.store)
    execution = b.store.begin_execution(b.thread, "Inspect distinct source fields")["execution_id"]
    ref = offload(b, execution)
    first = json.loads((await guarded_read(b, execution, ref=ref, field="long_text")).content)
    assert first["full_result"] == ref and first["value"] == "x" * 3000
    second = json.loads(
        (await guarded_read(b, execution, ref=first["full_result"], field="options")).content
    )
    assert second["value"] == SNAPSHOT["options"] and second["full_result"] == ref
    invalid = await guarded_read(b, execution, ref=second["full_result"], field="proposal")
    error = json.loads(invalid.content)
    assert invalid.status == "error"
    assert '"identity_evidence"' in error["message"] and '"options"' in error["message"]
    assert '"long_text"' in error["message"] and "xxxxx" not in error["message"]
    repaired = json.loads(
        (await guarded_read(b, execution, ref=ref, field="identity_evidence")).content
    )
    assert repaired["value"] == SNAPSHOT["identity_evidence"]
    # A read of the original source must not register the reader wrapper as a new artifact.
    assert len([e for e in b.store.events(b.thread) if e["kind"] == "tool-view"]) == 1


@pytest.mark.asyncio
async def test_shared_four_repairs_survive_restart_resume_and_reset_only_for_followup(
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
        assert (
            reopened.reserve_prerequisite_repair(bridge.thread, "target", execution, "RCSB:1MEL")
            == 3
        )
        error = json.loads((await guarded_read(resumed, execution, ref=ref, field=KEYS)).content)
        assert error["repair_attempt"] == error["repair_limit"] == 4
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


@pytest.mark.asyncio
async def test_unambiguous_path_spellings_and_display_aliases_preserve_source(bridge: Any) -> None:
    from easydesign.agent.evidence_output import ModelEvidenceScope

    execution = bridge.store.begin_execution(bridge.thread, "Read exact displayed facts")[
        "execution_id"
    ]
    original = {
        "facts": [
            {"mapping": {"label_seq_id": i, "canonical_position": i + 18}, "rsasa": i / 20}
            for i in range(12)
        ],
        "large": "x" * 2000,
    }
    msg = output_message(
        bridge,
        "target",
        execution,
        ToolMessage(
            name="read_site_evidence",
            content=json.dumps(original),
            tool_call_id="source",
        ),
    )
    ref = json.loads(msg.content)["full_result"]
    read = result_tool(bridge, "target")
    # One explicit selector has one meaning; redundant spellings are not normalized.
    with pytest.raises(InvalidFieldProjection, match="mutually exclusive"):
        await read.ainvoke({"ref": ref, "field": "facts", "path": ["facts"], "limit": 12})
    page = json.loads(await read.ainvoke({"ref": ref, "path": ["facts"], "limit": 12}))
    assert page["value"] == original["facts"][:8] and page["next_offset"] == 8
    value = json.loads(await read.ainvoke({"ref": ref, "path": ["facts", 5, "mapping"]}))
    assert value["value"] == original["facts"][5]["mapping"]
    table = json.loads(await read.ainvoke({"ref": ref, "path": ["facts_table"]}))["value"]
    assert table["row_count"] == 12
    assert [r[0] for r in table["rows"]] == list(range(12))
    with pytest.raises(InvalidFieldProjection, match="mutually exclusive"):
        await read.ainvoke({"ref": ref, "field": "facts", "path": ["large"]})
    assert set(ModelEvidenceScope.model_fields) == {"ref", "fields", "path", "offset", "limit"}
    assert not bridge._jobs()


@pytest.mark.asyncio
async def test_large_existing_receptor_artifact_is_scoped_without_summary_copy(bridge: Any) -> None:
    b = Phase2Bridge(bridge.project, bridge.thread, bridge.store)
    eid = b.store.begin_execution(b.thread, "Inspect receptor geometry")["execution_id"]
    full = {
        "identity": {"entry": "TEST"},
        "state": {"status": "unresolved"},
        "candidates": [{"labels": [1, 2], "score": 0.3}],
        "chain_graph": "x" * 300000,
        "warnings": ["Do not infer efficacy"],
    }
    ref = b.persist("research-receptor-analysis", full)
    with pytest.raises(AgentBoundaryError, match="too large"):
        b.store.offload(b.thread, full)
    result = json.loads(
        output_message(
            b,
            "site",
            eid,
            ToolMessage(
                name="analyze_receptor_context",
                tool_call_id="analysis",
                content=json.dumps({"analysis_ref": ref}),
            ),
        ).content
    )
    assert len(json.dumps(result)) < 6600 and result["partial"]
    assert result["identity"] == full["identity"]
    readable = result["full_result"]
    page = json.loads(
        await result_tool(b, "site").ainvoke({"ref": readable, "path": ["candidates"]})
    )
    assert page["value"] == full["candidates"]
    with pytest.raises(AgentBoundaryError, match="not supplied"):
        await result_tool(b, "target").ainvoke({"ref": readable, "path": ["identity"]})
    assert b.document(ref) == full
    row = b.store.events(b.thread)[-1]
    assert row["kind"] == "tool-view" and row["payload"]["artifact"] == ref
    (b.project / ref["relative_path"]).write_text("{}")
    with pytest.raises(ArtifactIntegrityError):
        await result_tool(b, "site").ainvoke({"ref": readable, "path": ["identity"]})


def test_model_result_scope_disambiguates_siblings_without_reinterpreting_paths() -> None:
    from pydantic import ValidationError

    from easydesign.agent.evidence_output import ModelEvidenceScope, read_query, scoped_value

    value = {"hard_constraints": "passed", "status": "evaluated", "warnings": ["State unknown"]}
    ref = "/result-abcd.json"
    with pytest.raises(InvalidFieldProjection, match="top-level sibling keys; call fields"):
        scoped_value(value, read_query({"ref": ref, "path": list(value)}))
    query = ModelEvidenceScope(ref=ref, fields=list(value))
    assert scoped_value(value, read_query(query.model_dump(exclude_none=True)))[0] == value
    with pytest.raises(ValidationError, match="at most one selector"):
        ModelEvidenceScope(ref=ref, fields=["status"], path=["warnings"])
    assert ModelEvidenceScope(ref=ref).fields is None
    # When a valid nested path also names root keys, traversal retains its meaning.
    nested = {"a": {"b": "nested"}, "b": "root"}
    assert scoped_value(nested, read_query({"ref": ref, "path": ["a", "b"]}))[0] == "nested"


@pytest.mark.asyncio
async def test_saved_result_navigation_distinguishes_counts_cards_and_source_pagination(
    bridge: Any,
) -> None:
    from easydesign.agent.evidence_output import ModelEvidenceScope

    b = Phase2Bridge(bridge.project, bridge.thread, bridge.store)
    eid = b.store.begin_execution(b.thread, "Inspect saved retrieval and residue results")[
        "execution_id"
    ]
    source = {
        "status": "RETRIEVED",
        "query_id": "saved-query",
        "matching_chunks": 15,
        "next_cursor": "opaque-original-cursor",
        "errors": [],
        "cards": [{"card_id": "passage-A", "passage": "Exact counterevidence. " * 90}],
    }
    rendered = json.loads(
        output_message(
            b,
            "target",
            eid,
            ToolMessage(
                name="retrieve_evidence", tool_call_id="source", content=json.dumps(source)
            ),
        ).content
    )
    ref = rendered["full_result"]
    nav = rendered["navigation"]
    assert nav["field_types"]["matching_chunks"] == "integer"
    assert nav["field_types"]["cards"] == "array"
    assert "facts" not in nav["field_types"]
    assert nav["array_lengths"]["cards"] == 1
    assert nav["retrieval_page"]["continue"] == {
        "tool": "continue_evidence",
        "arguments": {"cursor": source["next_cursor"]},
    }
    assert rendered["cards"] == source["cards"]
    args = ModelEvidenceScope(ref=ref).model_dump(exclude_none=True)
    inspected = json.loads((await guarded_read(b, eid, **args)).content)
    assert inspected["status"] == "result-navigation" and "value" not in inspected
    assert inspected["navigation"] == nav and "Exact counterevidence" not in json.dumps(inspected)
    read = result_tool(b, "target")
    page = json.loads(await read.ainvoke({"ref": ref, "path": ["cards"]}))
    assert page["value"] == source["cards"] and page["next_offset"] is None
    # The end of a stored page is not the end of retrieval; its cursor stays separate.
    again = json.loads((await guarded_read(b, eid, ref=ref)).content)
    assert (
        again["navigation"]["retrieval_page"]["continue"]["arguments"]["cursor"]
        == source["next_cursor"]
    )
    for selector in ({"path": ["facts"]}, {"fields": ["status", "warnings"]}):
        with pytest.raises(InvalidFieldProjection):
            await read.ainvoke({"ref": ref, **selector})
    with pytest.raises(InvalidFieldProjection, match="Selected type: integer") as error:
        await read.ainvoke({"ref": ref, "path": ["matching_chunks"], "offset": 2})
    assert '"cards":"array"' in str(error.value)
    assert not [e for e in b.store.events(b.thread) if "repair" in e["kind"]]
    assert not b._jobs()


@pytest.mark.asyncio
@pytest.mark.parametrize("violation", ["role", "execution", "tamper"])
async def test_navigation_without_selector_still_requires_current_verified_artifact(
    bridge: Any, violation: str
) -> None:
    b = Phase2Bridge(bridge.project, bridge.thread, bridge.store)
    eid = b.store.begin_execution(b.thread, "Inspect")["execution_id"]
    ref = offload(b, eid, role="site" if violation == "role" else "target")
    if violation == "execution":
        b.store.begin_execution(b.thread, "Follow-up", followup=True)
    elif violation == "tamper":
        row = next(e["payload"] for e in b.store.events(b.thread) if e["kind"] == "tool-view")
        (b.project / row["artifact"]["relative_path"]).write_text("{}")
    with pytest.raises((AgentBoundaryError, ArtifactIntegrityError)):
        await result_tool(b, "target").ainvoke({"ref": ref})
    assert not [e for e in b.store.events(b.thread) if "repair" in e["kind"]]


class NavigationModel(ProjectionModel):
    def answer(self, messages: Any) -> AIMessage:
        reads = [
            m for m in messages if isinstance(m, ToolMessage) and m.name == "read_evidence_result"
        ]
        if self.role != "coordinator" and reads and reads[-1].status == "success":
            value = json.loads(reads[-1].content)
            if value.get("status") == "result-navigation":
                assert value["navigation"]["field_types"]["chains"] == "array"
                assert value["navigation"]["field_types"]["identity_evidence"] == "object"
                assert "value" not in value
                return self.call("read_evidence_result", ref=self.result_ref, fields=KEYS)
        return super().answer(messages)


@pytest.mark.asyncio
async def test_actual_harness_can_inspect_then_read_without_guessing_schema(bridge: Any) -> None:
    b = Phase2Bridge(bridge.project, bridge.thread, bridge.store)
    goal = "Inspect the existing evidence only"
    eid = b.store.begin_execution(b.thread, goal)["execution_id"]
    ref = offload(b, eid)
    models = {
        role: NavigationModel(role=role, result_ref=ref, bad_selector={}) for role in PHASE2_ALLOWED
    }
    graph = create_harness(b, models, scripted_config(), MemorySaver(), goal, execution_id=eid)
    result = await graph.ainvoke(
        {"messages": [HumanMessage(content=goal)]}, {"configurable": {"thread_id": b.thread}}
    )
    assert_inspection_stopped(b, result)
    assert models["target"].observed == {key: SNAPSHOT[key] for key in KEYS}
    assert not [e for e in b.store.events(b.thread) if "repair" in e["kind"]]
    assert not b._jobs()


@pytest.mark.asyncio
async def test_successful_tool_call_resets_only_its_consecutive_repair_streak(
    bridge: Any,
) -> None:
    bridge = Phase2Bridge(bridge.project, bridge.thread, bridge.store)
    execution = bridge.store.begin_execution(bridge.thread, "Repair, succeed, continue")[
        "execution_id"
    ]
    ref = offload(bridge, execution)

    first = json.loads(
        (await guarded_read(bridge, execution, ref=ref, field="missing")).content
    )
    second = json.loads(
        (await guarded_read(bridge, execution, ref=ref, field="still_missing")).content
    )
    assert (first["repair_attempt"], second["repair_attempt"]) == (1, 2)

    valid = await guarded_read(bridge, execution, ref=ref, field="options")
    assert valid.status != "error"

    after_success = json.loads(
        (await guarded_read(bridge, execution, ref=ref, field="missing_again")).content
    )
    assert after_success["repair_attempt"] == 1
    assert after_success["repair_unit"] == "consecutive-tool-operation"
