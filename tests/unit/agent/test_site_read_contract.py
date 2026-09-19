"""Synthetic exact-label reads stay complete and stable across framework summaries."""

import copy
import json
from typing import Any

import pytest
from langchain.agents.middleware.types import ModelRequest, ModelResponse
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import StructuredTool
from langchain_core.utils.function_calling import convert_to_openai_tool
from pydantic import ValidationError

from easydesign.agent.evidence_output import output_message, verified_result
from easydesign.agent.harness import RoleBoundary
from easydesign.agent.phase2_tools import phase2_tools
from easydesign.agent.site_contracts import FocusedSiteQuery, SiteQuery
from tests.agent_support import ScriptedModel, scripted_config


@pytest.mark.asyncio
async def test_site_patch_returns_all_requested_rows_and_rejects_stale_offset(
    site_bridge: Any, monkeypatch: Any
) -> None:
    b = site_bridge
    execution = b.store.begin_execution(b.thread, "SYNTHETIC complete patch read")
    target, original, _ = b.site_facts()
    facts = copy.deepcopy(original)
    mapping = facts["observed_facts"]["mapping"][0]
    sasa = facts["derived_metrics"]["sasa"]["residues"][0]
    facts["observed_facts"]["mapping"] = [
        {
            **mapping,
            "label_seq_id": n,
            "canonical_position": None if n == 40 else n + 100,
            "mapping_status": "review-required",
            "mapping_qualification": "SYNTHETIC ambiguous correspondence; " + "qualification " * 15,
        }
        for n in range(1, 41)
    ]
    facts["derived_metrics"]["sasa"]["residues"] = [
        {**sasa, "residue": {**sasa["residue"], "label_seq_id": n}} for n in range(1, 41)
    ]
    ref = b.persist("synthetic-forty-row-evidence", facts)
    monkeypatch.setattr(b, "site_facts", lambda: (target, facts, ref))
    activity = b.read_site_evidence(FocusedSiteQuery())["research"]
    assert activity["queried_topics"] == {} and "topics" not in activity
    assert "NOT_SEARCHED" not in json.dumps(activity)
    read = next(t for t in phase2_tools(b, "site") if t.name == "read_site_evidence")
    raw = await read.ainvoke({"label_seq_ids": list(range(1, 41))})
    shown = output_message(
        b,
        "site",
        execution["execution_id"],
        ToolMessage(name=read.name, content=raw, tool_call_id="complete-patch"),
    )
    page = json.loads(shown.content)
    assert 6000 < len(shown.content) < 32000
    assert page["requested_residue_rows_complete"] and page["next_offset"] is None
    assert page["facts_table"]["row_count"] == 40
    stored = verified_result(b, "site", page["full_result"], execution_id=execution["execution_id"])
    assert [r["mapping"]["label_seq_id"] for r in stored["facts"]] == list(range(1, 41))
    assert stored["facts"][-1]["mapping"]["canonical_position"] is None
    assert all(r["mapping"]["mapping_status"] == "review-required" for r in stored["facts"])
    before = b.store.db.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    with pytest.raises(ValidationError, match="offset"):
        await read.ainvoke({"label_seq_ids": [25, 26, 27], "offset": 24})
    assert b.store.db.execute("SELECT COUNT(*) FROM events").fetchone()[0] == before
    # Legacy bridge pagination is still available to existing internal callers.
    legacy = b.read_site_evidence(SiteQuery(label_seq_ids=list(range(1, 41)), offset=24))
    assert [r["mapping"]["label_seq_id"] for r in legacy["facts"]] == list(range(25, 37))
    assert b.current_site() is None


@pytest.mark.asyncio
async def test_site_read_schema_is_stable_before_and_after_history_summarization(
    site_bridge: Any,
) -> None:
    b = site_bridge
    execution = b.store.begin_execution(b.thread, "SYNTHETIC stable tool schema")
    guard = RoleBoundary(
        b,
        "site",
        scripted_config(),
        "Inspect a mapped patch",
        execution_id=execution["execution_id"],
        site_stage="research",
    )
    tools = [
        *phase2_tools(b, "site"),
        StructuredTool.from_function(
            lambda file_path: None,
            name="read_file",
            description="Synthetic Skill loader; never executed.",
        ),
    ]
    schemas = []

    async def handler(request: Any) -> Any:
        read = next(t for t in request.tools if t.name == "read_site_evidence")
        schemas.append(convert_to_openai_tool(read)["function"]["parameters"])
        return ModelResponse(
            result=[
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "id": "read",
                            "name": "read_site_evidence",
                            "args": {"label_seq_ids": [1, 2, 3]},
                        }
                    ],
                )
            ]
        )

    for messages in [
        [],
        [
            AIMessage(
                content="", tool_calls=[{"id": "past", "name": "read_site_evidence", "args": {}}]
            ),
            ToolMessage(content="{}", name="read_site_evidence", tool_call_id="past"),
        ],
        [
            HumanMessage(
                content="SYNTHETIC framework working summary; original tool history offloaded."
            )
        ],
    ]:
        await guard.awrap_model_call(
            ModelRequest(
                model=ScriptedModel(role="site"),
                tools=tools,
                messages=messages,
                system_message=SystemMessage(content="Synthetic Site research"),
            ),
            handler,
        )
    assert schemas[0] == schemas[1] == schemas[2]
    assert set(schemas[0]["properties"]) == {"label_seq_ids"}
    assert schemas[0]["properties"]["label_seq_ids"]["maxItems"] == 40
    assert FocusedSiteQuery().label_seq_ids == []
    assert b.current_site() is None


@pytest.mark.asyncio
async def test_site_overview_is_complete_without_a_residue_pagination_trap(
    site_bridge: Any,
) -> None:
    b = site_bridge
    execution = b.store.begin_execution(b.thread, "SYNTHETIC candidate overview")
    legacy = b.read_site_evidence(SiteQuery())
    read = next(t for t in phase2_tools(b, "site") if t.name == "read_site_evidence")
    raw = await read.ainvoke({})
    result = json.loads(raw)
    assert result["candidate_patches"] == legacy["candidate_patches"]
    assert result["approved_target"] == legacy["approved_target"]
    assert result["limitations"] == legacy["limitations"]
    assert result["query_scope"] == "overview" and result["declared_scope_complete"]
    assert not {"facts", "offset", "next_offset", "page_total"}.intersection(result)
    shown = output_message(
        b,
        "site",
        execution["execution_id"],
        ToolMessage(name=read.name, content=raw, tool_call_id="overview"),
    )
    view = json.loads(shown.content)
    assert view["scientific_content_complete"] and view["declared_scope_complete"]
    assert not view["partial"] and "facts_table" not in view
    assert view["candidate_patches"] == result["candidate_patches"]
    # The independent focused read still supplies all exact requested mapping rows.
    labels = [row["mapping"]["label_seq_id"] for row in legacy["facts"]][:3]
    focused = json.loads(await read.ainvoke({"label_seq_ids": labels}))
    assert [row["mapping"]["label_seq_id"] for row in focused["facts"]] == labels
    assert b.current_site() is None


def test_receptor_candidates_supply_runtime_design_membership_without_source_offset() -> None:
    from easydesign.agent.evidence_output import receptor_overview_projection

    source = {
        "candidates": {
            "inhibit": [
                {
                    "id": "inhibit.synthetic",
                    "residues": [
                        {"gpcrdb_sequence_number": 286, "label_seq_id": 294, "auth_seq_id": 901},
                        {"gpcrdb_sequence_number": 287, "label_seq_id": 295, "auth_seq_id": 902},
                        {"gpcrdb_sequence_number": 999, "label_seq_id": 1007, "auth_seq_id": 1901},
                        {"gpcrdb_sequence_number": None, "label_seq_id": 1008, "auth_seq_id": 1902},
                    ],
                }
            ]
        },
        "approved_design_mapping": {
            "facts": [
                {
                    "mapping": {
                        "canonical_position": 286,
                        "label_seq_id": 414,
                        "mapping_status": "ambiguous",
                    },
                    "coordinate_observed": True,
                },
                {
                    "mapping": {
                        "canonical_position": 287,
                        "label_seq_id": 415,
                        "mapping_status": "ambiguous",
                    },
                    "coordinate_observed": False,
                },
                {
                    "mapping": {
                        "canonical_position": 294,
                        "label_seq_id": 422,
                        "mapping_status": "ambiguous",
                    },
                    "coordinate_observed": True,
                },
            ]
        },
    }
    before = copy.deepcopy(source)
    candidate = receptor_overview_projection(source)["candidate_overview"]["inhibit"][0]
    mapping = candidate["approved_design_membership"]
    assert mapping["hotspot_label_seq_ids"] == [414]
    assert mapping["unobserved_or_unmapped_canonical_positions"] == [287, 999]
    assert mapping["source_members_without_canonical_position"] == 1
    assert mapping["mapping_statuses"] == ["ambiguous"]
    assert candidate["id"] == "inhibit.synthetic"
    columns = candidate["residue_table"]["columns"]
    assert candidate["residue_table"]["rows"][0][columns.index("source_label_seq_id")] == 294
    assert source == before


def test_complete_receptor_membership_is_not_replaced_by_a_tool_size_preview(
    site_bridge: Any,
) -> None:
    from easydesign.agent.context_policy import context_usage
    from easydesign.agent.contracts import AgentBoundaryError
    from easydesign.agent.evidence_output import receptor_overview_projection

    bridge = site_bridge
    execution = bridge.store.begin_execution(bridge.thread, "SYNTHETIC complete receptor view")
    value = {
        "identity": {"accession": "SYNTHETIC", "receptor_chain": "A"},
        "candidates": {
            "inhibit": [
                {
                    "id": "inhibit.synthetic",
                    "counterevidence": ["Important synthetic counterevidence " * 1050],
                    "residues": [{"gpcrdb_sequence_number": 286, "label_seq_id": 294}],
                }
            ]
        },
        "approved_design_mapping": {
            "facts": [
                {
                    "mapping": {
                        "canonical_position": 286,
                        "label_seq_id": 414,
                        "mapping_status": "conditional",
                    },
                    "coordinate_observed": True,
                }
            ]
        },
    }
    ref = bridge.persist("synthetic-receptor-analysis", value)
    shown = output_message(
        bridge,
        "site",
        execution["execution_id"],
        ToolMessage(
            name="analyze_receptor_context",
            content=json.dumps({"analysis_ref": ref}),
            tool_call_id="complete-receptor",
        ),
    )
    page = json.loads(shown.content)
    assert len(shown.content) > 32000 and page["declared_scope_complete"]
    expected = receptor_overview_projection(value)["candidate_overview"]["inhibit"][0]
    candidate = page["candidate_overview"]["inhibit"][0]
    assert candidate["approved_design_membership"] == expected["approved_design_membership"]
    assert candidate["approved_design_membership"]["hotspot_label_seq_ids"] == [414]
    assert candidate["counterevidence"]
    assert candidate["full_residues_path"] == ["candidates", "inhibit", 0, "residues"]
    stored = verified_result(
        bridge, "site", page["full_result"], execution_id=execution["execution_id"]
    )
    assert stored == value
    # Retaining the complete answer never bypasses final model admission.
    config = scripted_config().model_copy(update={"hard_input_chars": 32000})
    with pytest.raises(AgentBoundaryError, match="hard context guard"):
        context_usage(ScriptedModel(role="site"), config, "site", [shown])


@pytest.mark.asyncio
async def test_completed_atomic_gpcr_analysis_hides_duplicate_analysis_tool(
    site_bridge: Any, monkeypatch: Any
) -> None:
    from easydesign.agent.evidence_research import EvidenceResearch

    bridge = site_bridge
    execution = bridge.store.begin_execution(bridge.thread, "SYNTHETIC atomic GPCR context")
    monkeypatch.setattr(
        EvidenceResearch,
        "snapshot",
        lambda _self: {
            "queries": [
                {
                    "query_id": "gpcr-query",
                    "question": "SYNTHETIC receptor context",
                    "status": "VERIFIED",
                    "errors": [],
                    "query": {"operation": "gpcrdb-context"},
                    "cards": [
                        {
                            "card_id": "gpcr-card",
                            "provider": "GPCRdb",
                            "context_ref": "synthetic-context-ref",
                        },
                        {
                            "card_id": "kernel-card",
                            "provider": "EasyDesign GPCR kernel",
                        },
                    ],
                }
            ]
        },
    )
    guard = RoleBoundary(
        bridge,
        "site",
        scripted_config(),
        "Inspect a GPCR site",
        execution_id=execution["execution_id"],
        site_stage="research",
        preloaded_domain_skills=True,
    )
    tools = phase2_tools(bridge, "site")
    offered: set[str] = set()

    class ObservedTools(Exception):
        pass

    async def handler(request: Any) -> Any:
        offered.update(tool.name for tool in request.tools)
        raise ObservedTools

    with pytest.raises(ObservedTools):
        await guard.awrap_model_call(
            ModelRequest(
                model=ScriptedModel(role="site"),
                tools=tools,
                messages=[],
                system_message=SystemMessage(content="Synthetic Site research"),
            ),
            handler,
        )
    assert "analyze_receptor_context" not in offered
    assert "research_evidence" in offered
