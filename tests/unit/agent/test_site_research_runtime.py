import json
from pathlib import Path
from typing import Any

import pytest
from deepagents.backends import FilesystemBackend
from langchain.agents.middleware import ModelRequest, ModelResponse
from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from easydesign.agent.context_policy import (
    admit_site_research_request,
    context_usage,
    research_memory,
)
from easydesign.agent.evidence_research import EvidenceResearch
from easydesign.agent.harness import RoleBoundary
from easydesign.agent.phase2_tools import phase2_tools
from easydesign.agent.session_store import SessionStore, compact
from easydesign.agent.site_research_runtime import (
    _compact_receptor_kernel,
    _evidence_card_view,
    receptor_kernel_message,
    refresh_site_research_activity,
    site_handoff_repair_outline,
    site_research_packet_message,
    site_research_state,
)
from tests.agent_support import scripted_config


def _empty_research() -> dict[str, Any]:
    return {
        "queries": [],
        "topics": {},
        "authority": "Synthetic durable research fixture.",
    }


def _kernel_research(site_bridge: Any) -> dict[str, Any]:
    binding = site_bridge.target_state()["binding"]
    value = {
        "identity": {"entry_name": "synthetic_human", "receptor_chain": "A"},
        "state": {"class": "inactive"},
        "membrane": {"method": "synthetic"},
        "topology": {"segments": ["ECL2"]},
        "chain_graph": {"target": "A"},
        "candidates": {"outer-pore": []},
        "warnings": ["Synthetic unit fixture"],
        "avoid": [],
        "approved_design_mapping": {"target_binding": binding},
    }
    ref = site_bridge.persist("research-receptor-analysis", value)
    return {
        "queries": [
            {
                "query_id": "synthetic-gpcr",
                "topic": "structure-complex",
                "question": "Synthetic receptor context",
                "status": "UNRESOLVED",
                "errors": [],
                "query": {"operation": "gpcrdb-context"},
                "cards": [
                    {
                        "card_id": "receptor-synthetic",
                        "provider": "EasyDesign GPCR kernel",
                        "source_refs": [ref],
                    }
                ],
            }
        ],
        "topics": {},
        "authority": "Synthetic durable research fixture.",
    }


def test_site_handoff_repair_outline_preserves_choices_without_rejected_prose() -> None:
    long_text = "unsupported prose " * 1000
    value = {
        "candidates": [
            {
                "name": "outer vestibule",
                "role": "primary",
                "origin": "scan-derived",
                "hotspot_label_seq_ids": [175, 176, 281],
                "evidence_card_ids": ["receptor-1"],
                "rationale": long_text,
            }
        ],
        "decision_questions": [
            {
                "question": "Which site blocks ligand entry?",
                "status": "UNRESOLVED",
                "query_ids": ["query-1"],
                "decision_impact": long_text,
                "evidence": [
                    {
                        "card_id": "passage-1",
                        "relation": "supports",
                        "strength": "E2",
                        "claim": long_text,
                        "excerpt": long_text,
                    }
                ],
                "limitations": [long_text],
            }
        ],
        "contradiction_search_query_ids": ["query-2"],
        "unresolved_questions": ["Whole-VHH clearance remains unresolved."],
        "stopping_reason": long_text,
    }
    outline = site_handoff_repair_outline(value)
    assert outline is not None
    assert outline["candidates"][0]["hotspot_label_seq_ids"] == [175, 176, 281]
    assert outline["decision_questions"][0]["evidence_refs"] == [
        {"card_id": "passage-1", "relation": "supports", "strength": "E2"}
    ]
    assert "Preserve valid candidate choices, unaffected questions" in outline["instruction"]
    assert "genuinely relevant issued query IDs" in outline["instruction"]
    assert "Never invent an ID" in outline["instruction"]
    assert "Preserve these exact choices" not in outline["instruction"]
    assert "unsupported prose" not in compact(outline)
    assert len(compact(outline)) < 2000


def test_kernel_projection_is_runtime_owned_idempotent_and_restart_safe(
    site_bridge: Any, monkeypatch: Any
) -> None:
    research = _kernel_research(site_bridge)
    monkeypatch.setattr(EvidenceResearch, "snapshot", lambda _self, **_kwargs: research)
    execution = site_bridge.store.begin_execution(site_bridge.thread, "Synthetic Site lifecycle")
    eid = execution["execution_id"]

    first = receptor_kernel_message(site_bridge, eid)
    second = receptor_kernel_message(site_bridge, eid)
    assert first is not None and second is not None
    assert '"runtime_receptor_kernel"' in first.content
    assert '"card_id":"receptor-synthetic"' in first.content
    assert first.content == second.content

    state = refresh_site_research_activity(site_bridge, eid)
    assert state.kernel_card_id == "receptor-synthetic"
    assert "receptor-kernel-ready" in state.milestones
    assert "receptor-kernel-projected" in state.milestones
    events = site_bridge.store.events(site_bridge.thread)
    assert sum(
        event["kind"] == "tool-view"
        and event["payload"].get("tool_call_id") == "runtime-receptor-kernel-projection"
        for event in events
    ) == 1
    assert sum(
        event["kind"] == "site-research-lifecycle"
        and event["payload"].get("milestone") == "receptor-kernel-projected"
        for event in events
    ) == 1

    reopened = SessionStore(site_bridge.project)
    try:
        from easydesign.agent.phase2 import Phase2Bridge

        resumed = Phase2Bridge(site_bridge.project, site_bridge.thread, reopened)
        resumed_state = site_research_state(resumed, eid)
        assert resumed_state.kernel_card_id == state.kernel_card_id
        assert resumed_state.milestones == state.milestones
    finally:
        reopened.close()


def test_lifecycle_does_not_count_gate1_passages_as_site_reading(
    site_bridge: Any, monkeypatch: Any
) -> None:
    prior_thread_evidence = {
        "queries": [
            {
                "query_id": "gate1-passage",
                "query": {"operation": "primary-fulltext"},
                "cards": [{"card_id": "passage-gate1", "passage": "Target identity text"}],
            }
        ],
        "topics": {},
        "authority": "Synthetic Gate 1 evidence",
    }
    observed_execution_ids: list[str | None] = []

    def snapshot(_self: Any, *, execution_id: str | None = None) -> dict[str, Any]:
        observed_execution_ids.append(execution_id)
        return _empty_research() if execution_id is not None else prior_thread_evidence

    monkeypatch.setattr(EvidenceResearch, "snapshot", snapshot)
    eid = site_bridge.store.begin_execution(site_bridge.thread, "Fresh Site execution")[
        "execution_id"
    ]

    state = refresh_site_research_activity(site_bridge, eid)
    assert observed_execution_ids and all(item == eid for item in observed_execution_ids)
    assert state.focused_passage_count == 0
    assert "decision-relevant-reading" not in state.milestones


def test_compact_kernel_preserves_candidate_rows_and_scientific_fields() -> None:
    columns = ["gpcrdb_sequence_number", "source_label_seq_id", "mapping_status"]
    projection = {
        "card_id": "receptor-test",
        "identity": {
            "accession": "P21452",
            "receptor_chain": "R",
            "chains": [{"id": str(i), "description": "x" * 100} for i in range(20)],
        },
        "approved_design_mapping": {
            "canonical_accession": "P21452",
            "target_binding": "target-binding",
            "limitations": ["review-required mapping"],
            "facts_table": {"columns": ["x"], "rows": [["y" * 1000]]},
        },
        "candidate_overview": {
            "inhibit": [
                {
                    "id": "outer-pore",
                    "hypothesis": "Block the extracellular vestibule.",
                    "risks": ["Whole-VHH access remains unverified."],
                    "approved_design_membership": {
                        "hotspot_label_seq_ids": [183, 184],
                        "mapping_statuses": ["review-required"],
                        "authority": "Repeated mapping authority " * 20,
                    },
                    "residue_table": {
                        "columns": columns,
                        "rows": [[175, 183, "exact"], [176, 184, "exact"]],
                        "encoding": "Repeated table explanation " * 20,
                    },
                    "kernel_claims": [
                        {
                            "id": "claim-1",
                            "claim": "Extracellular mouth geometry.",
                            "detail": "Extracellular mouth geometry.",
                            "source": "local structure analysis",
                        }
                    ],
                    "citable_evidence_card_ids": ["receptor-test"],
                }
            ]
        },
        "citation_contract": {"citable_evidence_card_ids": ["receptor-test"]},
    }

    compacted = _compact_receptor_kernel(projection)

    assert "chains" not in compacted["identity"]
    assert "facts_table" not in compacted["approved_design_mapping"]
    assert compacted["candidate_residue_columns"] == columns[:2]
    assert compacted["candidate_residue_constants"] == {"mapping_status": "exact"}
    candidate = compacted["candidate_overview"]["inhibit"][0]
    assert candidate["residue_table"]["rows"] == [
        [175, 183],
        [176, 184],
    ]
    assert candidate["approved_design_membership"]["hotspot_label_seq_ids"] == [183, 184]
    assert candidate["hypothesis"] == "Block the extracellular vestibule."
    assert candidate["risks"] == ["Whole-VHH access remains unverified."]
    assert candidate["kernel_claims"][0]["claim"] == "Extracellular mouth geometry."
    assert "detail" not in candidate["kernel_claims"][0]
    assert "citable_evidence_card_ids" not in candidate
    assert compacted["citation_contract"]["citable_evidence_card_ids"] == ["receptor-test"]
    assert len(compact(compacted)) < len(compact(projection)) * 0.6


def test_working_packet_keeps_all_search_leads_without_replaying_snippets(
    site_bridge: Any, monkeypatch: Any
) -> None:
    research = {
        "queries": [
            {
                "query_id": "literature-leads",
                "topic": "site-mechanism",
                "question": "Which evidence can change candidate order?",
                "status": "RESOLVED",
                "errors": [],
                "query": {"operation": "literature-search"},
                "cards": [
                    {
                        "card_id": f"lead-{index}",
                        "provider": "PubMed",
                        "identifier": str(1000 + index),
                        "title": f"Decision-relevant lead {index}",
                        "year": 2020 + index,
                        "passage": f"Search snippet {index} " + "x" * 5000,
                        "limitations": ["Discovery result; acquire before citing."],
                    }
                    for index in range(5)
                ],
            }
        ],
        "topics": {},
        "authority": "Synthetic durable research fixture.",
    }
    monkeypatch.setattr(EvidenceResearch, "snapshot", lambda _self, **_kwargs: research)
    eid = site_bridge.store.begin_execution(site_bridge.thread, "Compact search leads")[
        "execution_id"
    ]

    packet = json.loads(
        site_research_packet_message(site_bridge, eid, [], reading_closed=False).content
    )

    inquiry = packet["research_inquiries"][0]
    assert inquiry["discovery_lead_count"] == 5
    assert inquiry["evidence_card_ids"] == [
        "lead-0",
        "lead-1",
        "lead-2",
        "lead-3",
        "lead-4",
    ]
    lead_table = packet["discovery_lead_table"]
    assert len(lead_table["rows"]) == 5
    assert [row[0] for row in lead_table["rows"]] == inquiry["evidence_card_ids"]
    assert "passage" not in lead_table["columns"]
    assert "limitations" not in lead_table["columns"]
    assert packet["evidence_card_catalog"] == []
    assert packet["packet_chars"] < 10000


def test_existing_runtime_packet_is_not_reprojected_or_double_counted(
    site_bridge: Any, monkeypatch: Any
) -> None:
    monkeypatch.setattr(
        EvidenceResearch, "snapshot", lambda _self, **_kwargs: _empty_research()
    )
    config = scripted_config()
    eid = site_bridge.store.begin_execution(site_bridge.thread, "Single admission")[
        "execution_id"
    ]
    model = FakeListChatModel(responses=["unused"])
    request = ModelRequest(
        model=model,
        system_message=SystemMessage(content="Synthetic Site research"),
        messages=[HumanMessage(content="x" * 100500)],
        state={"messages": []},
        tools=[],
    )

    first = admit_site_research_request(
        request,
        bridge=site_bridge,
        config=config,
        role="site",
        execution_id=eid,
        tool_chars=0,
    )
    second = admit_site_research_request(
        first,
        bridge=site_bridge,
        config=config,
        role="site",
        execution_id=eid,
        tool_chars=0,
    )

    assert second.messages == first.messages
    assert sum(
        event["kind"] == "site-research-context-admission"
        for event in site_bridge.store.events(site_bridge.thread)
    ) == 1


@pytest.mark.asyncio
async def test_site_context_admission_builds_runtime_packet_before_summary_guard(
    site_bridge: Any, monkeypatch: Any, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        EvidenceResearch, "snapshot", lambda _self, **_kwargs: _empty_research()
    )
    config = scripted_config()
    execution = site_bridge.store.begin_execution(site_bridge.thread, "Synthetic admission")
    eid = execution["execution_id"]
    model = FakeListChatModel(responses=["Unused summary response"])
    memory = research_memory(
        site_bridge,
        config,
        model,
        FilesystemBackend(root_dir=tmp_path / "history", virtual_mode=True),
        eid,
    )
    messages = [HumanMessage(content="x" * 76000)]
    received: list[Any] = []

    async def handler(request: Any) -> Any:
        received.extend(request.messages)
        context_usage(model, config, "site", [request.system_message, *request.messages])
        site_bridge.store.reserve_model_call(
            site_bridge.thread, "site", config.max_model_calls, eid
        )
        return ModelResponse(result=[AIMessage(content="Continue")])

    await memory.awrap_model_call(
        ModelRequest(
            model=model,
            system_message=SystemMessage(content="Synthetic Site research"),
            messages=messages,
            state={"messages": messages},
            tools=[],
        ),
        handler,
    )
    assert len(received) == 1
    assert '"runtime_site_research_packet":"v1"' in received[0].content
    events = site_bridge.store.events(site_bridge.thread)
    assert sum(e["kind"] == "site-research-context-admission" for e in events) == 1
    assert not [e for e in events if e["kind"] == "framework-summary-call"]
    assert len([e for e in events if e["kind"] == "model-call"]) == 1
    assert not [e for e in events if e["kind"] == "auxiliary-model-call"]


@pytest.mark.asyncio
@pytest.mark.parametrize("tool_count", [1, 3])
async def test_persisted_summary_cutoff_precedes_site_runtime_projection_without_orphans(
    site_bridge: Any,
    monkeypatch: Any,
    tmp_path: Path,
    caplog: Any,
    tool_count: int,
) -> None:
    monkeypatch.setattr(
        EvidenceResearch, "snapshot", lambda _self, **_kwargs: _empty_research()
    )
    config = scripted_config()
    eid = site_bridge.store.begin_execution(
        site_bridge.thread, "Synthetic summarized admission"
    )["execution_id"]
    model = FakeListChatModel(responses=["unused"])
    memory = research_memory(
        site_bridge,
        config,
        model,
        FilesystemBackend(root_dir=tmp_path / "history", virtual_mode=True),
        eid,
    )
    # Exercise application of an already-persisted event without creating a new
    # summary in this call. The effective tail remains large enough for Runtime
    # admission to replace it with its durable packet.
    monkeypatch.setattr(memory, "_should_summarize", lambda _messages, _tokens: False)

    messages: list[Any] = [
        HumanMessage(content="Original request"),
        AIMessage(
            content="",
            tool_calls=[{"id": "prefix", "name": "read_site_evidence", "args": {}}],
        ),
        ToolMessage(
            content="{}",
            name="read_site_evidence",
            tool_call_id="prefix",
        ),
        AIMessage(content="Prefix evidence consumed."),
        HumanMessage(content="Oversized transient history " + "x" * 70000),
    ]
    calls = [
        {"id": f"current-{index}", "name": "retrieve_evidence", "args": {}}
        for index in range(tool_count)
    ]
    messages.append(AIMessage(content="", tool_calls=calls))
    messages.extend(
        ToolMessage(
            content=f'{{"result":"current-{index}"}}',
            name="retrieve_evidence",
            tool_call_id=call["id"],
        )
        for index, call in enumerate(calls)
    )
    summary = HumanMessage(content="Fallible summary of the first four state messages.")
    received: list[Any] = []

    async def handler(request: Any) -> Any:
        received.extend(request.messages)
        return ModelResponse(result=[AIMessage(content="Continue")])

    await memory.awrap_model_call(
        ModelRequest(
            model=model,
            system_message=SystemMessage(content="Synthetic Site research"),
            messages=messages,
            state={
                "messages": messages,
                "_summarization_event": {
                    "cutoff_index": 4,
                    "summary_message": summary,
                    "file_path": "/conversation_history/synthetic.md",
                },
            },
            tools=[],
        ),
        handler,
    )

    call_ids = [call["id"] for call in calls]
    assert len(received) == tool_count + 2
    assert '"runtime_site_research_packet":"v1"' in received[0].content
    assert isinstance(received[1], AIMessage)
    assert [call["id"] for call in received[1].tool_calls] == call_ids
    assert [
        message.tool_call_id for message in received[2:] if isinstance(message, ToolMessage)
    ] == call_ids
    assert "Summarization cutoff_index" not in caplog.text
    admission = [
        event["payload"]
        for event in site_bridge.store.events(site_bridge.thread)
        if event["kind"] == "site-research-context-admission"
    ]
    assert len(admission) == 1
    assert admission[0]["preserved_latest_tool_batch_calls"] == tool_count


@pytest.mark.asyncio
async def test_site_role_boundary_admits_oversized_first_request_before_hard_guard(
    site_bridge: Any, monkeypatch: Any
) -> None:
    monkeypatch.setattr(
        EvidenceResearch, "snapshot", lambda _self, **_kwargs: _empty_research()
    )
    config = scripted_config()
    eid = site_bridge.store.begin_execution(site_bridge.thread, "Oversized first Site call")[
        "execution_id"
    ]
    model = FakeListChatModel(responses=["unused"])
    boundary = RoleBoundary(
        site_bridge,
        "site",
        config,
        "Synthetic Site research",
        execution_id=eid,
        site_stage="research",
        preloaded_domain_skills=True,
    )
    # This test targets pre-provider admission rather than structured submission parsing.
    boundary.structured_output = False
    boundary.output_schema = None
    received: list[Any] = []

    async def handler(request: Any) -> ModelResponse:
        received.extend(request.messages)
        context_usage(
            model,
            config,
            "site",
            [request.system_message, *request.messages],
        )
        return ModelResponse(result=[AIMessage(content="Continue")])

    await boundary.awrap_model_call(
        ModelRequest(
            model=model,
            system_message=SystemMessage(content="Synthetic Site research"),
            messages=[HumanMessage(content="x" * 100500)],
            state={"messages": []},
            tools=phase2_tools(site_bridge, "site"),
        ),
        handler,
    )

    assert len(received) == 1
    assert '"runtime_site_research_packet":"v1"' in received[0].content
    admission = [
        event["payload"]
        for event in site_bridge.store.events(site_bridge.thread)
        if event["kind"] == "site-research-context-admission"
    ]
    assert len(admission) == 1
    assert admission[0]["original_input_chars_with_schemas"] > config.hard_input_chars
    assert admission[0]["projected_input_chars_with_schemas"] < config.hard_input_chars


def test_finalization_packet_does_not_replay_prior_tool_calls(
    site_bridge: Any, monkeypatch: Any
) -> None:
    monkeypatch.setattr(
        EvidenceResearch, "snapshot", lambda _self, **_kwargs: _empty_research()
    )
    eid = site_bridge.store.begin_execution(site_bridge.thread, "Synthetic finalization")[
        "execution_id"
    ]
    messages = [
        AIMessage(
            content="Candidate interpretation remains provisional.",
            tool_calls=[{"name": "research_evidence", "args": {"query": "old"}, "id": "old"}],
        ),
        ToolMessage(
            content=compact({"status": "complete", "raw": "x" * 20000}),
            name="research_evidence",
            tool_call_id="old",
        ),
    ]
    packet = site_research_packet_message(
        site_bridge, eid, messages, reading_closed=True
    )
    value = packet.content
    assert '"reading_closed":true' in value
    assert "Candidate interpretation remains provisional." in value
    assert "Every decision_questions item must include" in value
    assert "unresolved_questions is a list of plain strings" in value
    assert '"name":"research_evidence"' not in value
    assert '"args":{"query":"old"}' not in value
    assert len(value) < 60000



def test_evidence_card_view_exposes_runtime_owned_strength_ceiling() -> None:
    direct = _evidence_card_view(
        {
            "card_id": "passage-direct",
            "primary_eligible": True,
            "passage": "Direct deposited coordinate evidence for the synthetic interface.",
        },
        operation="structure-record",
    )
    review = _evidence_card_view(
        {
            "card_id": "passage-review",
            "primary_eligible": False,
            "passage": "A review summarizes the synthetic interface literature.",
        },
        operation="primary-record",
    )

    assert direct["allowed_strengths"] == ["E1", "E2", "E3", "E4"]
    assert review["allowed_strengths"] == ["E3", "E4"]
