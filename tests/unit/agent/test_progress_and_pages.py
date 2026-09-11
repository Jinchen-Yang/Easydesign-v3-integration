"""No absent-job polling and lossless size-aware passage delivery; synthetic sources."""

import json
from types import SimpleNamespace
from typing import Any

import pytest
from langchain_core.messages import AIMessage, SystemMessage, ToolMessage
from pydantic import ValidationError

from easydesign.agent.contracts import AgentBoundaryError
from easydesign.agent.evidence_corpus import EvidenceCorpus, RetrieveEvidence, SelectEvidence
from easydesign.agent.evidence_output import output_message, scientific_projection
from easydesign.agent.evidence_research import EvidenceResearch, ResearchQuery
from easydesign.agent.harness import RoleBoundary
from easydesign.agent.phase2 import Phase2Bridge
from easydesign.agent.phase2_tools import phase2_tools
from easydesign.agent.session_store import compact
from tests.agent_support import scripted_config
from tests.unit.agent.test_prerequisite_recovery import ACQUIRE, source_transport


@pytest.mark.asyncio
async def test_status_tool_follows_runtime_receipt_without_creating_work(
    bridge: Any, monkeypatch: Any
) -> None:
    b = Phase2Bridge(bridge.project, bridge.thread, bridge.store)
    execution = b.store.begin_execution(b.thread, "Inspect target")
    guard = RoleBoundary(
        b, "target", scripted_config(), "Inspect target", execution_id=execution["execution_id"]
    )
    names: list[set[str]] = []
    own_ref = None

    class Request(SimpleNamespace):
        def override(self, **kwargs: Any) -> Any:
            return Request(**{**vars(self), **kwargs})

    async def handler(request: Any) -> Any:
        names.append({t.name for t in request.tools})
        from langchain_core.utils.function_calling import convert_to_openai_tool

        skill = next(t for t in request.tools if t.name == "read_file")
        schema = convert_to_openai_tool(skill)["function"]["parameters"]
        assert schema["properties"]["file_path"]["enum"] == ["/skills/target-intelligence/SKILL.md"]
        if "read_evidence_result" in names[-1]:
            reader = next(t for t in request.tools if t.name == "read_evidence_result")
            schema = convert_to_openai_tool(reader)["function"]["parameters"]
            assert schema["properties"]["ref"]["enum"] == [own_ref]
        return SimpleNamespace(
            result=[
                AIMessage(
                    content="",
                    tool_calls=[{"name": "read_target_evidence", "args": {}, "id": "inspect"}],
                )
            ],
            structured_response=None,
        )

    tools = phase2_tools(b, "target")
    tools.append(SimpleNamespace(name="read_file"))
    # read_file must have a real schema for context accounting.
    from langchain_core.tools import StructuredTool

    tools[-1] = StructuredTool.from_function(
        lambda file_path: "", name="read_file", description="Read own Skill"
    )
    request = Request(tools=tools, messages=[], system_message=SystemMessage(content="Inspect"))
    await guard.awrap_model_call(request, handler)
    assert "get_job_status" not in names[-1]
    assert "prepare_target" not in names[-1] and "select_evidence" in names[-1]
    assert not b._jobs()
    request = request.override(
        messages=[ToolMessage(name="read_file", tool_call_id="skill", content="Loaded own Skill")]
    )
    await guard.awrap_model_call(request, handler)
    assert "prepare_target" in names[-1] and "get_job_status" not in names[-1]
    monkeypatch.setattr(b, "get_job_status", lambda: {"status": "running", "job_id": "bound"})
    await guard.awrap_model_call(request, handler)
    assert "get_job_status" in names[-1]
    assert names[-1] - names[0] == {"get_job_status", "prepare_target"}
    assert not b._jobs()
    assert "read_evidence_result" not in names[-1]
    raw = ToolMessage(
        name="read_target_evidence",
        tool_call_id="view",
        content=compact({"rows": list(range(1000))}),
    )
    output_message(b, "coordinator", execution["execution_id"], raw)
    await guard.awrap_model_call(request, handler)
    assert "read_evidence_result" not in names[-1]
    own_ref = json.loads(output_message(b, "target", execution["execution_id"], raw).content)[
        "full_result"
    ]
    await guard.awrap_model_call(request, handler)
    assert "read_evidence_result" in names[-1]


def test_passage_pages_fit_adapter_and_cursor_never_skips_or_truncates(
    bridge: Any, monkeypatch: Any
) -> None:
    b = Phase2Bridge(bridge.project, bridge.thread, bridge.store)
    execution = b.store.begin_execution(b.thread, "Inspect controlled assay")
    calls = source_transport(b, monkeypatch)
    corpus = EvidenceCorpus(b)
    corpus.select(
        SelectEvidence(
            provider="EuropePMC",
            identifier="PMC123",
            need="FUNCTIONAL_MECHANISM",
            selection="SELECTED",
            reason="Read actual assay and counterevidence",
        )
    )
    EvidenceResearch(b).acquire(ResearchQuery.model_validate(ACQUIRE), role="target")
    request = RetrieveEvidence(
        need="FUNCTIONAL_MECHANISM",
        question="assay control",
        source_id="EuropePMC:PMC123",
        page_size=3,
    )
    document = b.document(corpus.documents()[0]["corpus_ref"])
    delivered = []
    page_counts = []
    while True:
        page = corpus.retrieve(request)
        assert page["cards"]
        assert len(compact(scientific_projection(page))) <= 6000
        message = ToolMessage(name="retrieve_evidence", tool_call_id="page", content=compact(page))
        result = json.loads(output_message(b, "target", execution["execution_id"], message).content)
        assert result["cards"]
        assert len(result["cards"]) == len(page["cards"])
        page_counts.append(len(result["cards"]))
        for card in result["cards"]:
            assert card["passage"] == document["chunks"][card["chunk"]]["text"]
            assert card["source_status"] == "VERIFIED" and card["project_evidence_id"]
            delivered.append(card["chunk"])
        if not page["next_cursor"]:
            break
        request = request.model_copy(update={"cursor": page["next_cursor"]})
    assert len(delivered) == len(set(delivered)) == len(document["chunks"])
    assert set(delivered) == set(range(len(document["chunks"])))
    assert min(page_counts) < 3 and len(calls) == 1


@pytest.mark.asyncio
async def test_reworded_question_is_bounded_repair_but_foreign_cursor_is_fatal(
    bridge: Any, monkeypatch: Any
) -> None:
    b = Phase2Bridge(bridge.project, bridge.thread, bridge.store)
    execution = b.store.begin_execution(b.thread, "Read selected source")
    source_transport(b, monkeypatch)
    corpus = EvidenceCorpus(b)
    corpus.select(
        SelectEvidence(
            provider="EuropePMC",
            identifier="PMC123",
            need="FUNCTIONAL_MECHANISM",
            selection="SELECTED",
            reason="Inspect assay evidence",
        )
    )
    EvidenceResearch(b).acquire(ResearchQuery.model_validate(ACQUIRE), role="target")
    query = RetrieveEvidence(
        need="FUNCTIONAL_MECHANISM", question="assay control", source_id="EuropePMC:PMC123"
    )
    first = corpus.retrieve(query)
    changed = query.model_copy(update={"question": "new phrasing", "cursor": first["next_cursor"]})
    guard = RoleBoundary(
        b,
        "target",
        scripted_config(),
        "Read selected source",
        execution_id=execution["execution_id"],
    )

    async def handler(request: Any) -> Any:
        return compact(corpus.retrieve(RetrieveEvidence.model_validate(request.tool_call["args"])))

    request = SimpleNamespace(
        tool_call={"name": "retrieve_evidence", "id": "mismatch", "args": changed.model_dump()}
    )
    for attempt in (1, 2, 3, 4):
        response = await guard.awrap_tool_call(request, handler)
        value = json.loads(response.content)
        assert response.status == "error" and value["error_code"] == "CURSOR_QUERY_MISMATCH"
        assert "assay control" in value["message"] and value["repair_attempt"] == attempt
    with pytest.raises(AgentBoundaryError, match="repair budget"):
        await guard.awrap_tool_call(request, handler)
    exact = corpus.retrieve(query.model_copy(update={"cursor": first["next_cursor"]}))
    assert exact["cards"][0]["card_id"] != first["cards"][0]["card_id"]
    other = EvidenceCorpus(Phase2Bridge(b.project, "another-thread", b.store))
    with pytest.raises(AgentBoundaryError, match="another question/thread"):
        other.retrieve(changed)
    assert not b._jobs()


def test_explicit_pdb_alias_cannot_silently_change_source_identity() -> None:
    value = ResearchQuery(
        operation="structure-record",
        topic="structure-complex",
        question="Inspect chain inventory",
        pdb_id="1mel",
    )
    assert value.identifier == "1MEL"
    with pytest.raises(ValidationError, match="different structures"):
        ResearchQuery(
            operation="structure-record",
            topic="structure-complex",
            question="Inspect chain inventory",
            identifier="3P0G",
            pdb_id="1MEL",
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("include_snapshot", [False, True])
async def test_judge_can_compare_distinct_fields_in_one_bounded_working_set(
    bridge: Any, include_snapshot: bool
) -> None:
    b = Phase2Bridge(bridge.project, bridge.thread, bridge.store)
    execution = b.store.begin_execution(b.thread, "Compare complete option facts")
    guard = RoleBoundary(
        b, "judge", scripted_config(), "Compare facts", execution_id=execution["execution_id"]
    )
    source = "/result-" + "a" * 32 + ".json"
    messages = [
        ToolMessage(
            name="read_evidence_result",
            tool_call_id=str(i),
            content=compact(
                {
                    "full_result": source,
                    "path": [field],
                    "value": {"scientific_fact": field},
                    "next_offset": None,
                }
            ),
        )
        for i, field in enumerate(
            ["old", "options", "identity", "interpretation", "options", "hard_facts"]
        )
    ]

    if include_snapshot:
        messages.insert(
            0,
            ToolMessage(
                name="read_scientific_evidence",
                tool_call_id="snapshot",
                content=compact(
                    {
                        "full_result": source,
                        "complete_snapshot": {
                            "facts": "all alternatives",
                            "opinion": "source-bound",
                            "limitations": ["retained counterevidence"],
                        },
                    }
                ),
            ),
        )

    class Request(SimpleNamespace):
        def override(self, **kwargs: Any) -> Any:
            return Request(**{**vars(self), **kwargs})

    async def handler(request: Any) -> Any:
        visible = [json.loads(m.content) for m in request.messages]
        expected = (
            ["interpretation", "options", "hard_facts"]
            if include_snapshot
            else ["identity", "interpretation", "options", "hard_facts"]
        )
        assert [v["path"][0] for v in visible if "value" in v] == expected
        if include_snapshot:
            assert visible[0]["complete_snapshot"]["limitations"] == ["retained counterevidence"]
        assert all(v["archived_result"] == source for v in visible if "archived_result" in v)
        assert len(compact(visible)) < 32000
        return SimpleNamespace(
            result=[
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "read_scientific_evidence",
                            "args": {},
                            "id": "review",
                        }
                    ],
                )
            ],
            structured_response=None,
        )

    from langchain_core.tools import StructuredTool

    tools = phase2_tools(b, "judge") + [
        StructuredTool.from_function(
            lambda file_path: "", name="read_file", description="Read own Skill"
        )
    ]
    await guard.awrap_model_call(
        Request(tools=tools, messages=messages, system_message=SystemMessage(content="Review")),
        handler,
    )
    # Context projection is not a mutation of the checkpoint messages.
    assert all(
        "value" in json.loads(m.content) or "complete_snapshot" in json.loads(m.content)
        for m in messages
    )


def test_small_target_fact_snapshot_keeps_all_alternative_chains(bridge: Any) -> None:
    b = Phase2Bridge(bridge.project, bridge.thread, bridge.store)
    execution = b.store.begin_execution(b.thread, "Compare chain alternatives")
    chains = [
        {
            "auth_chain": name,
            "relationship": "exact_subsequence",
            "construct_length": 129,
            "observed_length": 127,
            "missing_construct_positions": [128, 129],
        }
        for name in ["A", "B", "L", "M"]
    ]
    facts = {
        "hard_facts": {"canonical_accession": "P00698", "canonical_length": 147, "chains": chains},
        "options": [
            {
                "option_id": "chain-" + c["auth_chain"].lower(),
                "description": "Retain every eligible alternative " * 8,
            }
            for c in chains
        ],
    }
    rendered = json.loads(
        output_message(
            b,
            "target",
            execution["execution_id"],
            ToolMessage(content=compact(facts), name="read_target_evidence", tool_call_id="facts"),
        ).content
    )
    assert rendered["hard_facts"] == facts["hard_facts"]
    assert rendered["options"] == facts["options"]


@pytest.mark.asyncio
async def test_coordinator_refreshes_runtime_progress_without_rewriting_history(
    bridge: Any, monkeypatch: Any
) -> None:
    from langchain_core.tools import StructuredTool

    b = Phase2Bridge(bridge.project, bridge.thread, bridge.store)
    execution = b.store.begin_execution(b.thread, "Continue through Site review")
    guard = RoleBoundary(
        b,
        "coordinator",
        scripted_config(),
        "Continue through Site review",
        execution_id=execution["execution_id"],
    )

    class Request(SimpleNamespace):
        def override(self, **kwargs: Any) -> Any:
            return Request(**{**vars(self), **kwargs})

    seen = []

    async def handler(request: Any) -> Any:
        seen.append(request)
        return SimpleNamespace(result=[AIMessage(content="Observed current progress")])

    tools = phase2_tools(b, "coordinator")
    tools.append(
        StructuredTool.from_function(
            lambda description, subagent_type: "", name="task", description="Delegate science"
        )
    )
    tools.append(
        StructuredTool.from_function(
            lambda file_path: "", name="read_file", description="Read own Skill"
        )
    )
    historical = [
        ToolMessage(
            name="read_target_evidence",
            tool_call_id="old",
            content='{"selected_chain":null,"status":"pending"}',
        )
    ]
    request = Request(
        tools=tools, messages=historical, system_message=SystemMessage(content="Coordinate")
    )
    current = {
        "scientific_state": "site-not-proposed",
        "gate_type": "site-hotspot",
        "next_specialist": "site-mechanism",
        "private_payload": "not-in-summary",
    }
    monkeypatch.setattr(b, "scientific_state", lambda: current)
    await guard.awrap_model_call(request, handler)
    assert '"scientific_state":"site-not-proposed"' in seen[-1].system_message.text
    assert '"next_specialist":"site-mechanism"' in seen[-1].system_message.text
    assert "not-in-summary" not in seen[-1].system_message.text
    names = {t.name for t in seen[-1].tools}
    assert "task" in names and "read_scientific_state" in names
    assert not names & {"read_target_evidence", "read_evidence_result"}
    assert seen[-1].messages == historical == request.messages
    assert request.system_message.text == "Coordinate"
    output_message(
        b,
        "coordinator",
        execution["execution_id"],
        ToolMessage(
            name="read_target_evidence",
            tool_call_id="current-view",
            content=compact({"rows": list(range(1000))}),
        ),
    )
    current.update(scientific_state="hotspot-approved", next_specialist="none")
    await guard.awrap_model_call(request, handler)
    assert '"next_specialist":"none"' in seen[-1].system_message.text
    assert "read_evidence_result" in {t.name for t in seen[-1].tools}
    assert '"scientific_state":"site-not-proposed"' not in seen[-1].system_message.text
    assert not b._jobs()
    assert b.store.db.execute("SELECT count(*) FROM cards").fetchone()[0] == 0


def test_site_page_preserves_all_mapping_and_metric_values_in_compact_table() -> None:
    from easydesign.agent.evidence_output import site_page_projection

    facts = [
        {
            "mapping": {
                "label_seq_id": i,
                "canonical_position": i + 18,
                "source_author_chain_id": "L",
                "source_author_residue_id": str(i),
                "insertion_code": None,
                "mapping_status": "review-required",
            },
            "raw_sasa": i * 1.135793,
            "rsasa": 0.123456789,
            "surface_eligible": i % 2 == 0,
            "declared_topology": None,
        }
        for i in range(1, 13)
    ]
    original = {
        "facts": facts,
        "next_offset": 12,
        "limitations": ["No affinity claim"],
        "candidate_patches": [{"name": "actual-patch", "label_seq_ids": [2, 4, 6]}],
    }
    page = site_page_projection(original)
    table = page["facts_table"]
    assert len(table["rows"]) == table["row_count"] == 12
    reconstructed = []
    n = len(table["mapping_columns"])
    for row in table["rows"]:
        reconstructed.append(
            {
                "mapping": dict(zip(table["mapping_columns"], row[:n], strict=True)),
                **dict(zip(table["metric_columns"], row[n:], strict=True)),
            }
        )
    assert reconstructed == facts
    assert page["next_offset"] == 12 and page["limitations"] == original["limitations"]
    assert page["candidate_patches"] == original["candidate_patches"]
    assert len(compact(page)) < len(compact(original))
    assert original["facts"] == facts
    facts[0]["mapping"].pop("canonical_position")
    assert site_page_projection(original) == scientific_projection(original)


def test_site_display_page_cannot_skip_rows_hidden_by_size_limit() -> None:
    from easydesign.agent.evidence_output import site_page_projection

    rows = [
        {"mapping": {"label_seq_id": i, "source_author_residue_id": "x" * 500}, "rsasa": i / 30}
        for i in range(24)
    ]
    delivered = []
    offset = 0
    while True:
        raw = {
            "facts": rows[offset : offset + 12],
            "offset": offset,
            "page_total": len(rows),
            "next_offset": offset + 12 if offset + 12 < len(rows) else None,
        }
        page = site_page_projection(raw)
        assert len(compact(page)) <= 5500
        delivered.extend(row[0] for row in page["facts_table"]["rows"])
        if page["next_offset"] is None:
            break
        assert page["next_offset"] == len(delivered)
        offset = page["next_offset"]
    assert delivered == list(range(24))


@pytest.mark.asyncio
async def test_accession_in_source_card_argument_is_bounded_without_exposing_foreign_cards(
    bridge: Any,
) -> None:
    from easydesign.agent.contracts import InvalidFieldProjection
    from easydesign.agent.evidence_research import ReferenceComparison

    b = Phase2Bridge(bridge.project, bridge.thread, bridge.store)
    research = EvidenceResearch(b)
    execution = b.store.begin_execution(b.thread, "Compare an acquired source")
    guard = RoleBoundary(
        b,
        "site",
        scripted_config(),
        "Compare an acquired source",
        execution_id=execution["execution_id"],
    )

    async def handler(request: Any) -> Any:
        return research.compare_reference(ReferenceComparison(**request.tool_call["args"]))

    request = SimpleNamespace(
        tool_call={
            "name": "compare_reference_identity",
            "id": "bad",
            "args": {"uniprot_card_id": "P00698", "auth_chain": "L"},
        }
    )
    for count in range(1, 5):
        result = await guard.awrap_tool_call(request, handler)
        payload = json.loads(result.content)
        assert result.status == "error" and payload["repair_attempt"] == count
        assert "not an accession" in payload["message"]
        assert payload["error_code"] == "SOURCE_CARD_REQUIRED"
        assert payload["required_action"] == "research_evidence"
    with pytest.raises(AgentBoundaryError, match="repair budget"):
        await guard.awrap_tool_call(request, handler)
    with pytest.raises(AgentBoundaryError) as error:
        research.compare_reference(
            ReferenceComparison(uniprot_card_id="source-foreign", auth_chain="L")
        )
    assert not isinstance(error.value, InvalidFieldProjection)
    assert not any(e["kind"] == "reference-identity-comparison" for e in b.store.events(b.thread))
    assert not b._jobs()


@pytest.mark.asyncio
async def test_file_reader_result_alias_only_indexes_current_authorized_artifact(
    bridge: Any,
) -> None:
    b = Phase2Bridge(bridge.project, bridge.thread, bridge.store)
    execution = b.store.begin_execution(b.thread, "Inspect site")
    eid = execution["execution_id"]
    guard = RoleBoundary(b, "site", scripted_config(), "Inspect site", execution_id=eid)
    message = output_message(
        b,
        "site",
        eid,
        ToolMessage(
            name="evaluate_candidate_site",
            tool_call_id="source",
            content=compact({"facts": ["private-value" * 200], "mapping": {"observed": True}}),
        ),
    )
    ref = json.loads(message.content)["full_result"]
    request = SimpleNamespace(
        tool_call={"name": "read_file", "id": "index", "args": {"file_path": ref}}
    )

    async def forbidden_handler(request: Any) -> Any:
        raise AssertionError("Filesystem reader must never receive an evidence path")

    result = await guard.awrap_tool_call(request, forbidden_handler)
    value = json.loads(result.content)
    assert value["status"] == "scoped-result-index"
    assert set(value["available_fields"]) == {"facts", "mapping"}
    assert "private-value" not in result.content and not b._jobs()
    foreign_role = RoleBoundary(b, "target", scripted_config(), "Inspect site", execution_id=eid)
    with pytest.raises(AgentBoundaryError, match="not supplied"):
        await foreign_role.awrap_tool_call(request, forbidden_handler)
    path = b.store.root / "agent-work" / b.thread / ref.lstrip("/")
    original = path.read_bytes()
    path.write_bytes(original + b" ")
    with pytest.raises(Exception, match="Artifact .*不一致"):
        await guard.awrap_tool_call(request, forbidden_handler)
    path.write_bytes(original)
    b.store.begin_execution(b.thread, "Another execution")
    with pytest.raises(AgentBoundaryError, match="current execution"):
        await guard.awrap_tool_call(request, forbidden_handler)


def test_explicit_selection_and_acquisition_share_the_existing_corpus(
    bridge: Any, monkeypatch: Any
) -> None:
    from easydesign.agent.contracts import SourceSelectionRequired

    b = Phase2Bridge(bridge.project, bridge.thread, bridge.store)
    b.store.begin_execution(b.thread, "Research mechanism")
    calls = source_transport(b, monkeypatch)
    worker = EvidenceResearch(b)
    query = ResearchQuery.model_validate(ACQUIRE)
    with pytest.raises(SourceSelectionRequired):
        worker.acquire(query, role="site")
    assert not calls
    query = query.model_copy(
        update={"selection_reason": "Primary mechanistic evidence and its assay controls"}
    )
    result = worker.acquire(query, role="site")
    assert result["cards"] and len(calls) == 1
    selections = EvidenceCorpus(b).selections()
    selection = selections["EuropePMC:PMC123:FUNCTIONAL_MECHANISM"]
    assert selection["selection"] == "SELECTED" and selection["reason"] == query.selection_reason
    worker.acquire(query, role="site")
    assert len(calls) == 1 and not b._jobs()
    with pytest.raises(AgentBoundaryError):
        worker.acquire(query, role="judge")


@pytest.mark.asyncio
async def test_site_followup_reads_require_focus_and_share_existing_call_budget(
    bridge: Any,
) -> None:
    from langchain_core.tools import StructuredTool

    b = Phase2Bridge(bridge.project, bridge.thread, bridge.store)
    execution = b.store.begin_execution(b.thread, "Compare mechanistic sites")
    guard = RoleBoundary(
        b, "site", scripted_config(), "Compare sites", execution_id=execution["execution_id"]
    )
    tools = phase2_tools(b, "site") + [
        StructuredTool.from_function(
            lambda file_path: "", name="read_file", description="Read Skill"
        )
    ]
    snapshots = []

    class Request(SimpleNamespace):
        def override(self, **kwargs: Any) -> Any:
            return Request(**{**vars(self), **kwargs})

    async def handler(request: Any) -> Any:
        tool = next(t for t in request.tools if t.name == "read_site_evidence")
        snapshots.append((tool.args_schema, request.system_message.text))
        return SimpleNamespace(
            result=[
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "read_site_evidence",
                            "args": {"label_seq_ids": [1, 2]},
                            "id": "read",
                        }
                    ],
                )
            ],
            structured_response=None,
        )

    request = Request(tools=tools, messages=[], system_message=SystemMessage(content="Investigate"))
    await guard.awrap_model_call(request, handler)
    assert snapshots[0][0].model_validate({}).label_seq_ids == []
    request = request.override(
        messages=[
            ToolMessage(
                name="read_site_evidence", tool_call_id="overview", content="Overview supplied"
            )
        ]
    )
    await guard.awrap_model_call(request, handler)
    with pytest.raises(ValidationError):
        snapshots[1][0].model_validate({"offset": 8})
    assert snapshots[1][0].model_validate({"label_seq_ids": [4, 7], "offset": 1}).label_seq_ids == [
        4,
        7,
    ]
    assert '"used_model_calls":0' in snapshots[0][1]
    assert '"used_model_calls":1' in snapshots[1][1]
    assert not b._jobs()


@pytest.mark.asyncio
@pytest.mark.parametrize("defect", ["citation", "not-searched", "false-empty"])
async def test_known_source_citation_is_repaired_before_site_registration(
    bridge: Any, monkeypatch: Any, defect: str
) -> None:
    from langchain_core.tools import StructuredTool

    from easydesign.agent.evidence_corpus import RetrieveEvidence
    from easydesign.agent.evidence_research import ResearchConclusion
    from tests.unit.agent.test_site_runtime import site_intent

    b = Phase2Bridge(bridge.project, bridge.thread, bridge.store)
    execution = b.store.begin_execution(b.thread, "Explain source support")
    source_transport(b, monkeypatch)
    worker = EvidenceResearch(b)
    acquired = worker.acquire(
        ResearchQuery.model_validate(
            {**ACQUIRE, "selection_reason": "Inspect direct assay evidence"}
        ),
        role="site",
    )
    source = acquired["cards"][0]
    page = EvidenceCorpus(b).retrieve(
        RetrieveEvidence(
            need="FUNCTIONAL_MECHANISM",
            question="assay inhibition",
            source_id="EuropePMC:PMC123",
            page_size=1,
        )
    )
    passage = page["cards"][0]

    def opinion(card_id: str) -> Any:
        intent = site_intent()
        conclusion = ResearchConclusion.model_validate(
            {
                "topic": "function",
                "status": "VERIFIED",
                "limitations": ["Synthetic controlled assay only"],
                "evidence": [
                    {
                        "card_id": card_id,
                        "excerpt": "The assay showed inhibition under controlled conditions.",
                        "claim": "The assay reports inhibition in its specified conditions.",
                        "relation": "supports",
                        "strength": "E2",
                        "transfer_limit": "No in vivo extrapolation",
                    }
                ],
            }
        )
        return intent.model_copy(update={"research_conclusions": [conclusion]})

    bad, good = opinion(source["card_id"]), opinion(passage["card_id"])
    if defect != "citation":
        change = (
            {"topic": "state"} if defect == "not-searched" else {"status": "SEARCHED_NO_EVIDENCE"}
        )
        bad = good.model_copy(
            update={
                "research_conclusions": [good.research_conclusions[0].model_copy(update=change)]
            }
        )
    from easydesign.agent.contracts import TargetFacts

    monkeypatch.setattr(
        b,
        "target_submission_evidence",
        lambda: {"hard_facts": TargetFacts().model_dump(mode="json")},
    )
    guard = RoleBoundary(
        b,
        "site",
        scripted_config(),
        "Explain source support",
        execution_id=execution["execution_id"],
    )
    tools = phase2_tools(b, "site") + [
        StructuredTool.from_function(lambda file_path: "", name="read_file", description="Skill")
    ]

    class Request(SimpleNamespace):
        def override(self, **kwargs: Any) -> Any:
            return Request(**{**vars(self), **kwargs})

    seen = []

    async def handler(request: Any) -> Any:
        seen.append(request.system_message.text)
        value = bad if len(seen) == 1 else good
        return SimpleNamespace(
            result=[
                AIMessage(
                    content="",
                    tool_calls=[
                        {"name": "SiteIntent", "args": value.model_dump(mode="json"), "id": "final"}
                    ],
                )
            ],
            structured_response=value,
        )

    result = await guard.awrap_model_call(
        Request(tools=tools, messages=[], system_message=SystemMessage(content="Investigate")),
        handler,
    )
    assert result.structured_response == good and len(seen) == 2
    diagnostic = (
        "CITATION_MISMATCH"
        if defect == "citation"
        else "NOT_SEARCHED"
        if defect == "not-searched"
        else "SEARCHED_NO_EVIDENCE"
    )
    assert diagnostic in seen[1] and '"used_model_calls":1' in seen[1]
    assert len([e for e in b.store.events(b.thread) if e["kind"] == "contract-repair"]) == 1
    assert not [e for e in b.store.events(b.thread) if e["kind"] == "site-proposal"]
    with pytest.raises(AgentBoundaryError, match="not retrieved"):
        b.validate_site_research(opinion("foreign-source"))
    assert not b._jobs()


@pytest.mark.asyncio
@pytest.mark.parametrize("later_sources", [False, True])
@pytest.mark.parametrize("scoped_read", [False, True])
async def test_site_keeps_distinct_source_passages_when_geometry_views_advance(
    bridge: Any, later_sources: bool, scoped_read: bool
) -> None:
    from langchain_core.tools import StructuredTool

    b = Phase2Bridge(bridge.project, bridge.thread, bridge.store)
    execution = b.store.begin_execution(b.thread, "Compare mechanism and geometry")
    guard = RoleBoundary(
        b,
        "site",
        scripted_config(),
        "Compare mechanism and geometry",
        execution_id=execution["execution_id"],
    )
    tools = phase2_tools(b, "site") + [
        StructuredTool.from_function(lambda file_path: "", name="read_file", description="Skill")
    ]
    messages = []
    for i, source in enumerate(["UniProt:TEST", "EuropePMC:123", "RCSB:TEST"]):
        messages.append(
            ToolMessage(
                name="retrieve_evidence",
                tool_call_id=f"source{i}",
                content=compact(
                    {
                        "full_result": f"/result-{i:x}.json",
                        "cards": [{"source_id": source, "passage": f"evidence-{i} " * 200}],
                        "next_cursor": f"exact-source-cursor-{i}",
                    }
                ),
            )
        )
    for i in range(12):
        messages.append(
            ToolMessage(
                name="read_site_evidence",
                tool_call_id=f"geometry{i}",
                content=compact(
                    {"full_result": f"/result-{i + 10:x}.json", "geometry": f"geometry-{i}"}
                ),
            )
        )
    if later_sources:
        messages = (
            messages[3:]
            + messages[:3]
            + [messages[0].model_copy(update={"tool_call_id": "reread"})]
        )
    if scoped_read:
        messages.extend(
            [
                ToolMessage(
                    name="evaluate_candidate_site",
                    tool_call_id="evaluation",
                    content=compact(
                        {
                            "full_result": "/result-eval.json",
                            "warnings": ["Keep adverse exposure evidence"],
                        }
                    ),
                ),
                ToolMessage(
                    name="read_evidence_result",
                    tool_call_id="scoped-read",
                    content=compact(
                        {
                            "full_result": "/result-eval.json",
                            "path": ["spatial_components"],
                            "value": 2,
                        }
                    ),
                ),
            ]
        )
    original = [m.content for m in messages]

    class Request(SimpleNamespace):
        def override(self, **kwargs: Any) -> Any:
            return Request(**{**vars(self), **kwargs})

    async def handler(request: Any) -> Any:
        retained = [json.loads(m.content) for m in request.messages if '"full_result"' in m.content]
        from langchain_core.utils.function_calling import convert_to_openai_tool

        skill = next(t for t in request.tools if t.name == "read_file")
        schema = convert_to_openai_tool(skill)["function"]["parameters"]
        assert set(schema["properties"]["file_path"]["enum"]) == {
            "/skills/site-mechanism/SKILL.md",
            "/skills/site-mechanism/references/research.md",
            "/skills/site-mechanism/references/membrane.md",
            "/skills/site-mechanism/references/shielding.md",
        }
        retrieval = next(t for t in request.tools if t.name == "retrieve_evidence")
        cursor_schema = convert_to_openai_tool(retrieval)["function"]["parameters"]["properties"][
            "cursor"
        ]
        assert set(cursor_schema["enum"]) == {
            "",
            "exact-source-cursor-0",
            "exact-source-cursor-1",
            "exact-source-cursor-2",
        }
        assert len(retained) == (6 if scoped_read else 4)
        assert len([x for x in retained if x.get("cards")]) == 3
        assert [x["geometry"] for x in retained if "geometry" in x] == ["geometry-11"]
        if scoped_read:
            assert json.loads(request.messages[-1].content)["value"] == 2
            assert json.loads(request.messages[-2].content)["warnings"] == [
                "Keep adverse exposure evidence"
            ]
        assert (
            sum(len(m.content) for m in request.messages if '"full_result"' in m.content) <= 32000
        )
        return SimpleNamespace(
            result=[
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "evaluate_candidate_site",
                            "args": {"label_seq_ids": [1, 2]},
                            "id": "check",
                        }
                    ],
                )
            ],
            structured_response=None,
        )

    await guard.awrap_model_call(
        Request(
            tools=tools, messages=messages, system_message=SystemMessage(content="Investigate")
        ),
        handler,
    )
    assert [m.content for m in messages] == original


@pytest.mark.asyncio
async def test_scoped_list_end_distinguishes_index_from_target_residue_number(bridge: Any) -> None:
    from easydesign.agent.evidence_output import result_tool

    b = Phase2Bridge(bridge.project, bridge.thread, bridge.store)
    eid = b.store.begin_execution(b.thread, "Read a page")["execution_id"]
    msg = output_message(
        b,
        "site",
        eid,
        ToolMessage(
            name="evaluate_candidate_site",
            tool_call_id="source",
            content=compact({"facts": [1, 2, 3], "padding": "x" * 2000}),
        ),
    )
    ref = json.loads(msg.content)["full_result"]
    result = json.loads(
        await result_tool(b, "site").ainvoke({"ref": ref, "field": "facts", "offset": 33})
    )
    assert result["status"] == "end-of-scoped-list" and result["total_items"] == 3
    assert result["value"] == [] and result["next_offset"] is None
    assert "not residue numbering" in result["instruction"] and result["full_result"] == ref
    assert not b._jobs()


@pytest.mark.asyncio
async def test_offset_cannot_silently_repeat_an_object_or_scalar(bridge: Any) -> None:
    from easydesign.agent.contracts import InvalidFieldProjection
    from easydesign.agent.evidence_output import result_tool

    b = Phase2Bridge(bridge.project, bridge.thread, bridge.store)
    eid = b.store.begin_execution(b.thread, "Read exact geometry")["execution_id"]
    message = output_message(
        b,
        "site",
        eid,
        ToolMessage(
            name="evaluate_candidate_site",
            tool_call_id="geometry",
            content=compact(
                {
                    "facts_table": {"rows": [[23, None], [25, 0.31]], "row_count": 2},
                    "spatial_components": 1,
                    "padding": "x" * 2000,
                }
            ),
        ),
    )
    ref = json.loads(message.content)["full_result"]
    read = result_tool(b, "site")
    for path in [["facts_table"], ["spatial_components"]]:
        with pytest.raises(InvalidFieldProjection, match="Offset applies only"):
            await read.ainvoke({"ref": ref, "path": path, "offset": 12})
    page = json.loads(
        await read.ainvoke({"ref": ref, "path": ["facts_table", "rows"], "offset": 1})
    )
    assert page["value"] == [[25, 0.31]] and page["next_offset"] is None
    assert not b._jobs()


@pytest.mark.asyncio
async def test_retrieval_offset_uses_bounded_repair_and_framework_error_is_not_json(
    bridge: Any,
) -> None:
    b = Phase2Bridge(bridge.project, bridge.thread, bridge.store)
    eid = b.store.begin_execution(b.thread, "Read focused source evidence")["execution_id"]
    guard = RoleBoundary(b, "site", scripted_config(), "Inspect", execution_id=eid)
    invoked = []
    query = {
        "need": "TARGET_IDENTITY",
        "question": "Read source topology",
        "source_id": "UniProt:TEST",
    }

    async def handler(request: Any) -> Any:
        invoked.append(request.tool_call["args"])
        return ToolMessage(
            name="retrieve_evidence",
            tool_call_id="read",
            status="error",
            content="Framework tool argument error: no evidence returned",
        )

    bad = SimpleNamespace(
        tool_call={"name": "retrieve_evidence", "id": "read", "args": {**query, "offset": 0}}
    )
    first = await guard.awrap_tool_call(bad, handler)
    diagnostic = json.loads(first.content)
    assert (
        diagnostic["error_code"] == "INVALID_RETRIEVAL_QUERY" and diagnostic["repair_attempt"] == 1
    )
    assert not invoked
    good = SimpleNamespace(tool_call={"name": "retrieve_evidence", "id": "read", "args": query})
    result = await guard.awrap_tool_call(good, handler)
    assert (
        result.status == "error"
        and result.content == "Framework tool argument error: no evidence returned"
    )
    assert invoked == [query]
    for attempt in range(2, 5):
        assert (
            json.loads((await guard.awrap_tool_call(bad, handler)).content)["repair_attempt"]
            == attempt
        )
    with pytest.raises(AgentBoundaryError, match="repair budget"):
        await guard.awrap_tool_call(bad, handler)
    assert not b._jobs() and not EvidenceCorpus(b).documents()


@pytest.mark.asyncio
async def test_completed_target_cannot_be_redelegated_as_pending_site_work(
    bridge: Any, monkeypatch: Any
) -> None:
    b = Phase2Bridge(bridge.project, bridge.thread, bridge.store)
    eid = b.store.begin_execution(b.thread, "Continue after Target approval")["execution_id"]
    monkeypatch.setattr(
        b,
        "scientific_state",
        lambda: {"scientific_state": "site-not-proposed", "next_specialist": "site-mechanism"},
    )
    guard = RoleBoundary(
        b, "coordinator", scripted_config(), "Continue after Target approval", execution_id=eid
    )

    async def handler(request: Any) -> Any:
        raise AssertionError("Inapplicable specialist must not execute")

    for specialist in ("target-intelligence", "evidence-judge"):
        request = SimpleNamespace(
            tool_call={
                "name": "task",
                "id": specialist,
                "args": {"subagent_type": specialist, "description": "Continue research"},
            }
        )
        result = await guard.awrap_tool_call(request, handler)
        assert result.status == "error"
        value = json.loads(result.content)
        assert value["status"] == "NOT_APPLICABLE" and value["next_specialist"] == "site-mechanism"
    assert len([e for e in b.store.events(b.thread) if e["kind"] == "delegation-prerequisite"]) == 2
    assert not b._jobs()


@pytest.mark.asyncio
async def test_invalid_site_read_is_bounded_query_repair_without_validating_a_hotspot(
    bridge: Any,
) -> None:
    from easydesign.agent.site_evidence import summarize_site_facts

    b = Phase2Bridge(bridge.project, bridge.thread, bridge.store)
    eid = b.store.begin_execution(b.thread, "Inspect an observed region")["execution_id"]
    guard = RoleBoundary(b, "site", scripted_config(), "Inspect", execution_id=eid)
    analysis = {
        "derived_metrics": {
            "sasa": {"residues": [{"residue": {"label_seq_id": i}} for i in [23, 24, 25, 394, 395]]}
        }
    }
    before = compact(analysis)

    async def handler(request: Any) -> Any:
        return summarize_site_facts(analysis, labels=request.tool_call["args"]["label_seq_ids"])

    request = SimpleNamespace(
        tool_call={
            "id": "query",
            "name": "read_site_evidence",
            "args": {"label_seq_ids": [10011, 10012]},
        }
    )
    for attempt in range(1, 5):
        result = await guard.awrap_tool_call(request, handler)
        value = json.loads(result.content)
        assert result.status == "error" and value["repair_attempt"] == attempt
        assert value["error_code"] == "OBSERVED_DESIGN_LABEL_REQUIRED"
        assert "[[23,25],[394,395]]" in value["message"]
    with pytest.raises(AgentBoundaryError, match="repair budget"):
        await guard.awrap_tool_call(request, handler)
    assert compact(analysis) == before and not b._jobs()
    assert b.store.db.execute("SELECT count(*) FROM cards").fetchone()[0] == 0


def test_site_submission_names_missing_conclusion_and_still_requires_real_research(
    bridge: Any,
) -> None:
    from easydesign.agent.contracts import ResearchConclusionMismatch
    from easydesign.agent.site_contracts import SiteIntent
    from tests.unit.agent.test_site_runtime import site_intent

    b = Phase2Bridge(bridge.project, bridge.thread, bridge.store)
    value = site_intent([1, 2]).model_dump(mode="json")
    value.update(
        scope="mechanistic",
        material_questions=["epitope", "state"],
        research_conclusions=[
            {
                "topic": "state",
                "status": "UNRESOLVED",
                "evidence": [],
                "limitations": ["State remains unknown"],
            }
        ],
    )
    with pytest.raises(ValidationError, match="Missing research_conclusions for topics: epitope"):
        SiteIntent.model_validate(value)
    value["research_conclusions"].append(
        {
            "topic": "epitope",
            "status": "UNRESOLVED",
            "evidence": [],
            "limitations": ["Epitope remains unknown"],
        }
    )
    valid = SiteIntent.model_validate(value)
    with pytest.raises(ResearchConclusionMismatch, match="NOT_SEARCHED"):
        b.validate_site_research(valid)
    assert not b._jobs() and b.current_site() is None


@pytest.mark.asyncio
async def test_missing_research_identifier_is_bounded_before_any_fetch(bridge: Any) -> None:
    b = Phase2Bridge(bridge.project, bridge.thread, bridge.store)
    eid = b.store.begin_execution(b.thread, "Acquire receptor context")["execution_id"]
    guard = RoleBoundary(b, "site", scripted_config(), "Acquire", execution_id=eid)
    query = {
        "topic": "state",
        "operation": "gpcrdb-context",
        "query": "adrb2_human",
        "question": "Read the receptor context",
        "pdb_id": "3P0G",
    }
    called = []

    async def handler(request: Any) -> Any:
        called.append(request.tool_call["args"])
        return ToolMessage(
            name="research_evidence",
            tool_call_id="research",
            content='{"cards":[],"errors":[],"status":"UNRESOLVED"}',
        )

    bad = SimpleNamespace(tool_call={"name": "research_evidence", "id": "research", "args": query})
    for attempt in range(1, 5):
        result = await guard.awrap_tool_call(bad, handler)
        diagnostic = json.loads(result.content)
        assert result.status == "error" and diagnostic["repair_attempt"] == attempt
        assert (
            diagnostic["error_code"] == "INVALID_RESEARCH_QUERY"
            and "requires identifier" in diagnostic["message"]
        )
    with pytest.raises(AgentBoundaryError, match="repair budget"):
        await guard.awrap_tool_call(bad, handler)
    assert not called and not EvidenceCorpus(b).documents() and not b._jobs()
    good = SimpleNamespace(
        tool_call={
            "name": "research_evidence",
            "id": "research",
            "args": {**query, "identifier": "adrb2_human"},
        }
    )
    await guard.awrap_tool_call(good, handler)
    assert len(called) == 1


@pytest.mark.asyncio
async def test_receptor_analysis_model_surface_requires_a_complete_context_card(
    bridge: Any, monkeypatch: Any
) -> None:
    from langchain_core.tools import StructuredTool
    from langchain_core.utils.function_calling import convert_to_openai_tool

    b = Phase2Bridge(bridge.project, bridge.thread, bridge.store)
    eid = b.store.begin_execution(b.thread, "Inspect receptor context")["execution_id"]
    guard = RoleBoundary(b, "site", scripted_config(), "Inspect", execution_id=eid)
    cards = []
    monkeypatch.setattr(EvidenceResearch, "snapshot", lambda self: {"queries": [{"cards": cards}]})
    tools = phase2_tools(b, "site") + [
        StructuredTool.from_function(lambda file_path: "", name="read_file", description="Skill")
    ]
    seen = []

    class Request(SimpleNamespace):
        def override(self, **kwargs: Any) -> Any:
            return Request(**{**vars(self), **kwargs})

    async def handler(request: Any) -> Any:
        analysis = [t for t in request.tools if t.name == "analyze_receptor_context"]
        seen.append(analysis)
        if analysis:
            assert convert_to_openai_tool(analysis[0])["function"]["parameters"]["properties"][
                "gpcrdb_card_id"
            ]["enum"] == ["source-context"]
        return SimpleNamespace(
            result=[
                AIMessage(
                    content="",
                    tool_calls=[{"name": "read_site_evidence", "args": {}, "id": "inspect"}],
                )
            ],
            structured_response=None,
        )

    request = Request(tools=tools, messages=[], system_message=SystemMessage(content="Inspect"))
    await guard.awrap_model_call(request, handler)
    cards.append({"provider": "GPCRdb", "card_id": "source-incomplete"})
    await guard.awrap_model_call(request, handler)
    cards.append(
        {
            "provider": "GPCRdb",
            "card_id": "source-context",
            "context_ref": {"synthetic_verified_snapshot": True},
        }
    )
    await guard.awrap_model_call(request, handler)
    assert not seen[0] and not seen[1] and len(seen[2]) == 1
    assert not b._jobs()
