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
            lambda: None, name="read_file", description="Synthetic Skill loader; never executed."
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
