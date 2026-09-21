"""No absent-job polling and lossless size-aware passage delivery; synthetic sources."""

import json
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from types import SimpleNamespace
from typing import Any

import pytest
from langchain_core.messages import AIMessage, SystemMessage, ToolMessage
from pydantic import ValidationError

from easydesign.agent.contracts import (
    AgentBoundaryError,
    EvidenceCitationMismatch,
    EvidenceRoleMismatch,
)
from easydesign.agent.evidence_corpus import EvidenceCorpus, RetrieveEvidence, SelectEvidence
from easydesign.agent.evidence_output import output_message, scientific_projection
from easydesign.agent.evidence_research import EvidenceResearch, ResearchQuery
from easydesign.agent.harness import SITE_RESEARCH_MODEL_CALL_LIMIT, RoleBoundary
from easydesign.agent.phase2 import Phase2Bridge
from easydesign.agent.phase2_tools import phase2_tools
from easydesign.agent.session_store import SessionStore, compact
from easydesign.agent.tools import build_tools
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
        model = SimpleNamespace(profile={})

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


@pytest.mark.asyncio
async def test_successful_skill_reads_are_durable_across_summarized_history(bridge: Any) -> None:
    """A compacted checkpoint must not make a specialist reload immutable Skills."""
    from langchain_core.tools import StructuredTool

    b = Phase2Bridge(bridge.project, bridge.thread, bridge.store)
    execution_id = b.store.begin_execution(b.thread, "Inspect site")["execution_id"]
    guard = RoleBoundary(b, "site", scripted_config(), "Inspect site", execution_id=execution_id)
    skill_paths = guard._skill_paths()

    class Request(SimpleNamespace):
        model = SimpleNamespace(profile={})

        def override(self, **kwargs: Any) -> Any:
            return Request(**{**vars(self), **kwargs})

    async def tool_handler(request: Any) -> ToolMessage:
        return ToolMessage(
            name="read_file",
            tool_call_id=request.tool_call["id"],
            content=f"Loaded {request.tool_call['args']['file_path']}",
        )

    for index, path in enumerate(skill_paths):
        await guard.awrap_tool_call(
            Request(
                tool_call={
                    "name": "read_file",
                    "id": f"skill-{index}",
                    "args": {"file_path": path},
                }
            ),
            tool_handler,
        )

    rows = b.store.db.execute(
        "SELECT json_extract(payload,'$.path') FROM events "
        "WHERE thread=? AND kind='skill-read' ORDER BY seq",
        (b.thread,),
    ).fetchall()
    assert [row[0] for row in rows] == skill_paths

    tools = phase2_tools(b, "site") + [
        StructuredTool.from_function(lambda file_path: "", name="read_file", description="Skill")
    ]

    async def model_handler(request: Any) -> Any:
        assert "read_file" not in {tool.name for tool in request.tools}
        assert "every required Skill file" in request.system_message.text
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
    await guard.awrap_model_call(request, model_handler)


@pytest.mark.asyncio
async def test_stage1_target_skill_read_is_recorded_and_not_reoffered(
    bridge: Any, monkeypatch: Any
) -> None:
    """The Stage 1 TargetBridge must not loop over its immutable Skill."""
    from langchain_core.tools import StructuredTool

    execution_id = bridge.store.begin_execution(bridge.thread, "Prepare target")["execution_id"]
    guard = RoleBoundary(
        bridge,
        "target",
        scripted_config(),
        "Prepare target",
        execution_id=execution_id,
    )
    skill_path = "/skills/target-intelligence/SKILL.md"

    class Request(SimpleNamespace):
        model = SimpleNamespace(profile={})

        def override(self, **kwargs: Any) -> Any:
            return Request(**{**vars(self), **kwargs})

    async def tool_handler(request: Any) -> ToolMessage:
        return ToolMessage(
            name="read_file",
            tool_call_id=request.tool_call["id"],
            content="Loaded Target Skill",
        )

    await guard.awrap_tool_call(
        Request(
            tool_call={
                "name": "read_file",
                "id": "stage1-skill",
                "args": {"file_path": skill_path},
            }
        ),
        tool_handler,
    )
    assert guard._loaded_skill_paths() == {skill_path}

    tools = build_tools(bridge, "target") + [
        StructuredTool.from_function(lambda file_path: "", name="read_file", description="Skill")
    ]

    offered: list[set[str]] = []

    async def model_handler(request: Any) -> Any:
        names = {tool.name for tool in request.tools}
        offered.append(names)
        assert "read_file" not in names
        assert "every required Skill file" in request.system_message.text
        return SimpleNamespace(
            result=[
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "prepare_target"
                            if "prepare_target" in names
                            else "read_target_evidence",
                            "args": {},
                            "id": "next",
                        }
                    ],
                )
            ],
            structured_response=None,
        )

    request = Request(tools=tools, messages=[], system_message=SystemMessage(content="Prepare"))
    await guard.awrap_model_call(request, model_handler)
    assert "prepare_target" in offered[-1] and "get_job_status" not in offered[-1]

    monkeypatch.setattr(
        bridge,
        "get_job_status",
        lambda: {"status": "awaiting-human-approval", "job_id": "job-test"},
    )
    await guard.awrap_model_call(request, model_handler)
    assert "prepare_target" not in offered[-1] and "get_job_status" not in offered[-1]
    assert "read_target_evidence" in offered[-1]


@pytest.mark.asyncio
async def test_stage1_structure_decision_packet_remains_inline(
    bridge: Any, monkeypatch: Any
) -> None:
    """Stage 1 has no result navigator, so a rich Gate 1 packet must stay readable."""
    packet = {
        "status": "awaiting-human-approval",
        "run_id": "run-test",
        "options": [
            {
                "option_id": f"candidate-{index}",
                "description": "verified construct and state facts " + "x" * 2400,
            }
            for index in range(6)
        ],
    }
    monkeypatch.setattr(
        "easydesign.agent.tools.resolve_project_run",
        lambda *_args, **_kwargs: SimpleNamespace(run_id="run-test"),
    )
    monkeypatch.setattr(
        bridge,
        "get_job_status",
        lambda: {"status": "awaiting-human-approval", "job_id": "job-test"},
    )
    monkeypatch.setattr(bridge, "read_evidence", lambda _run_id=None: packet)
    reader = next(
        tool
        for tool in build_tools(bridge, "target")
        if tool.name == "read_target_evidence"
    )

    result = json.loads(await reader.ainvoke({}))

    assert result == packet
    assert "ref" not in result


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
@pytest.mark.parametrize("role", ["judge", "coordinator"])
async def test_judge_retains_complete_current_evidence_under_shared_input_policy(
    bridge: Any, include_snapshot: bool, role: str
) -> None:
    b = Phase2Bridge(bridge.project, bridge.thread, bridge.store)
    execution = b.store.begin_execution(b.thread, "Compare complete option facts")
    guard = RoleBoundary(
        b, role, scripted_config(), "Compare facts", execution_id=execution["execution_id"]
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
                    "value": {"scientific_fact": field, "evidence": "x" * 6000},
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
        model = SimpleNamespace(profile={})

        def override(self, **kwargs: Any) -> Any:
            return Request(**{**vars(self), **kwargs})

    async def handler(request: Any) -> Any:
        visible = [json.loads(m.content) for m in request.messages]
        expected = ["old", "options", "identity", "interpretation", "options", "hard_facts"]
        assert [v["path"][0] for v in visible if "value" in v] == expected
        if include_snapshot:
            assert visible[0]["complete_snapshot"]["limitations"] == ["retained counterevidence"]
        assert not any("archived_result" in v for v in visible)
        assert 32000 < len(compact(visible)) < 60000
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

    tools = [
        StructuredTool.from_function(
            lambda file_path: "",
            name=name,
            description="SYNTHETIC context-only tool; never executed",
        )
        for name in guard.allowed
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


def test_reference_comparison_rejects_nonprotein_auth_chain(
    bridge: Any,
    monkeypatch: Any,
) -> None:
    from easydesign.agent.evidence_research import ReferenceComparison
    from easydesign.backends.target_sources.structure import (
        ChainInventory,
        StructureInventory,
    )

    b = Phase2Bridge(bridge.project, bridge.thread, bridge.store)
    research = EvidenceResearch(b)
    record = {
        "primaryAccession": "P12345",
        "organism": {"taxonId": 9606},
        "sequence": {"value": "AGSLVK"},
    }
    monkeypatch.setattr(
        research,
        "snapshot",
        lambda: {
            "queries": [
                {
                    "cards": [
                        {
                            "card_id": "source-protein",
                            "provider": "UniProt",
                            "identifier": "P12345",
                            "source_refs": ["record-ref"],
                        }
                    ]
                }
            ]
        },
    )
    monkeypatch.setattr(b, "document", lambda _ref: record)
    protein = ChainInventory(
        author_chain_id="A",
        label_chain_id="A",
        residue_count=6,
        canonical_residue_count=6,
        sequence="AGSLVK",
        deposited_sequence="AGSLVK",
        coordinate_label_seq_ids=(1, 2, 3, 4, 5, 6),
        ca_label_seq_ids=(1, 2, 3, 4, 5, 6),
        model_ids=("1",),
        ligand_names=(),
        water_count=0,
        altloc_atom_count=0,
    )
    glycan = ChainInventory(
        author_chain_id="D",
        label_chain_id="D",
        residue_count=1,
        canonical_residue_count=0,
        sequence="",
        deposited_sequence=None,
        coordinate_label_seq_ids=(),
        ca_label_seq_ids=(),
        model_ids=("1",),
        ligand_names=("NAG",),
        water_count=0,
        altloc_atom_count=0,
    )
    monkeypatch.setattr(
        "easydesign.agent.evidence_research.inventory_structure",
        lambda _path: StructureInventory(
            model_ids=("1",),
            chains=(protein, glycan),
            protein_chain_ids=("A",),
            ligand_names=("NAG",),
            water_count=0,
        ),
    )

    with pytest.raises(AgentBoundaryError, match="protein auth chain"):
        research.compare_reference(
            ReferenceComparison(uniprot_card_id="source-protein", auth_chain="D")
        )
    assert not any(
        event["kind"] == "reference-identity-comparison" for event in b.store.events(b.thread)
    )


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
        model = SimpleNamespace(profile={})

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
    assert snapshots[1][0].model_validate({"label_seq_ids": [4, 7]}).label_seq_ids == [
        4,
        7,
    ]
    assert '"used_scientific_model_calls":0' in snapshots[0][1]
    assert '"used_scientific_model_calls":1' in snapshots[1][1]
    assert not b._jobs()


@pytest.mark.asyncio
@pytest.mark.parametrize("defect", ["citation", "not-searched", "false-empty"])
async def test_known_source_citation_is_repaired_before_site_registration(
    bridge: Any, monkeypatch: Any, defect: str
) -> None:
    from langchain_core.tools import StructuredTool

    from easydesign.agent.evidence_corpus import RetrieveEvidence
    from easydesign.agent.evidence_research import ResearchAssessment

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
        return ResearchAssessment.model_validate(
            {
                "query_ids": [page["query_id"]],
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

    bad, good = opinion(source["card_id"]), opinion(passage["card_id"])
    if defect != "citation":
        change = (
            {"query_ids": []} if defect == "not-searched" else {"status": "SEARCHED_NO_EVIDENCE"}
        )
        bad = good.model_copy(update=change)
    # Source-assessment validation belongs at Handoff, not in final SiteIntent.
    from tests.unit.agent.test_site_dossier import handoff

    original_good, original_bad = good, bad
    good, bad = handoff(), handoff().model_copy(update={"stopping_reason": "SYNTHETIC bad source"})

    def validate_handoff(_bridge: Any, value: Any) -> Any:
        return worker.validate_questions(
            [original_bad if value.stopping_reason == bad.stopping_reason else original_good]
        )

    monkeypatch.setattr("easydesign.agent.harness.site_dossier", validate_handoff)
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
        model = SimpleNamespace(profile={})

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
                        {
                            "name": "SiteResearchHandoff",
                            "args": value.model_dump(mode="json"),
                            "id": "final",
                        }
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
    assert diagnostic in seen[1] and '"used_scientific_model_calls":1' in seen[1]
    assert len([e for e in b.store.events(b.thread) if e["kind"] == "contract-repair"]) == 1
    assert not [e for e in b.store.events(b.thread) if e["kind"] == "site-proposal"]
    if defect == "citation":
        focused_bad = original_good.evidence[0].model_copy(
            update={"excerpt": "A non-verbatim focused passage paraphrase."}
        )
        mixed = original_good.model_copy(
            update={"evidence": [original_bad.evidence[0], focused_bad]}
        )
        with pytest.raises(EvidenceCitationMismatch) as mixed_error:
            worker.validate_questions([mixed])
        assert mixed_error.value.repair_keys == ()
    with pytest.raises(AgentBoundaryError, match="not retrieved"):
        worker.validate_questions([opinion("foreign-source")])
    assert not b._jobs()


@pytest.mark.asyncio
@pytest.mark.parametrize("later_sources", [False, True])
@pytest.mark.parametrize("scoped_read", [False, True])
async def test_site_boundary_preserves_native_history_for_framework_memory(
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
        model = SimpleNamespace(profile={})

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
        assert (
            "cursor"
            not in convert_to_openai_tool(retrieval)["function"]["parameters"]["properties"]
        )
        continuation = next(t for t in request.tools if t.name == "continue_evidence")
        cursor_schema = convert_to_openai_tool(continuation)["function"]["parameters"][
            "properties"
        ]["cursor"]
        assert set(cursor_schema["enum"]) == {
            "exact-source-cursor-0",
            "exact-source-cursor-1",
            "exact-source-cursor-2",
        }
        # Generic history fitting belongs to DeepAgents, not RoleBoundary. Raw
        # observations (including duplicates/adverse facts) must survive unchanged.
        assert [m.content for m in request.messages] == original
        assert len(retained) == len(messages)
        assert len([x for x in retained if x.get("cards")]) == (4 if later_sources else 3)
        assert [x["geometry"] for x in retained if "geometry" in x] == [
            f"geometry-{i}" for i in range(12)
        ]
        if scoped_read:
            assert json.loads(request.messages[-1].content)["value"] == 2
            assert json.loads(request.messages[-2].content)["warnings"] == [
                "Keep adverse exposure evidence"
            ]
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


def test_site_submission_rejects_obsolete_topic_authority(bridge: Any) -> None:
    from easydesign.agent.site_contracts import SiteIntent
    from tests.unit.agent.test_site_runtime import site_intent

    b = Phase2Bridge(bridge.project, bridge.thread, bridge.store)
    value = site_intent([1, 2]).model_dump(mode="json")
    with pytest.raises(ValidationError, match="Extra inputs"):
        SiteIntent.model_validate({**value, "material_questions": ["epitope"]})
    with pytest.raises(AgentBoundaryError, match="current execution dossier"):
        b.validate_site_research(SiteIntent.model_validate({**value, "scope": "mechanistic"}))
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

    b = Phase2Bridge(bridge.project, bridge.thread, bridge.store)
    eid = b.store.begin_execution(b.thread, "Inspect receptor context")["execution_id"]
    guard = RoleBoundary(b, "site", scripted_config(), "Inspect", execution_id=eid)
    cards = []
    monkeypatch.setattr(
        EvidenceResearch,
        "snapshot",
        lambda self, **_kwargs: {"queries": [{"cards": cards}]},
    )
    tools = phase2_tools(b, "site") + [
        StructuredTool.from_function(lambda file_path: "", name="read_file", description="Skill")
    ]
    seen = []

    class Request(SimpleNamespace):
        model = SimpleNamespace(profile={})

        def override(self, **kwargs: Any) -> Any:
            return Request(**{**vars(self), **kwargs})

    async def handler(request: Any) -> Any:
        analysis = [t for t in request.tools if t.name == "analyze_receptor_context"]
        seen.append(analysis)
        return SimpleNamespace(
            result=[
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "analyze_receptor_context"
                            if analysis
                            else "read_site_evidence",
                            "args": {
                                "gpcrdb_card_id": "source-context",
                                "auth_chain": "A",
                            }
                            if analysis
                            else {},
                            "id": "inspect",
                        }
                    ],
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
    # Kernel computation remains tied to a complete GPCRdb context, but delivery is
    # now a Runtime projection rather than a model-selected navigation tool.
    assert not seen[0] and not seen[1] and not seen[2]
    assert not b._jobs()


@pytest.mark.asyncio
async def test_focused_residue_rows_fit_without_repeating_large_approved_background(
    bridge: Any,
) -> None:
    from easydesign.agent.evidence_output import verified_result
    from easydesign.agent.site_contracts import FocusedSiteQuery

    b = Phase2Bridge(bridge.project, bridge.thread, bridge.store)
    eid = b.store.begin_execution(b.thread, "Compare exact residues")["execution_id"]
    rows = [
        {
            "mapping": {
                "label_seq_id": i,
                "canonical_position": i + 18,
                "source_author_chain_id": "L",
                "source_author_residue_id": str(i),
                "mapping_status": "review-required",
                "insertion_code": None,
            },
            "rsasa": 0.6,
            "raw_sasa": 52.83,
            "declared_topology": None,
        }
        for i in range(1, 13)
    ]
    original = {
        "query_scope": "focused-residues",
        "requested_labels": list(range(1, 13)),
        "facts": rows,
        "offset": 0,
        "next_offset": None,
        "page_total": 12,
        "approved_target": {"large_verified_background": "x" * 9000},
        "candidate_patches": [{"other_patch": "y" * 7000}],
        "limitations": ["Conditional mapping; no binding or efficacy claim"],
    }
    message = output_message(
        b,
        "site",
        eid,
        ToolMessage(name="read_site_evidence", content=compact(original), tool_call_id="focused"),
    )
    page = json.loads(message.content)
    assert page["requested_residue_rows_complete"] and page["facts_table"]["row_count"] == 12
    assert page["next_offset"] is None and page["limitations"] == original["limitations"]
    assert len(compact(page)) < 6000 and "approved_target" not in page
    table = page["facts_table"]
    n = len(table["mapping_columns"])
    restored = [
        {
            "mapping": dict(zip(table["mapping_columns"], r[:n], strict=True)),
            **dict(zip(table["metric_columns"], r[n:], strict=True)),
        }
        for r in table["rows"]
    ]
    assert restored == rows and verified_result(b, "site", page["full_result"]) == original
    assert set(FocusedSiteQuery.model_fields) == {"label_seq_ids"}
    with pytest.raises(ValidationError):
        FocusedSiteQuery(label_seq_ids=list(range(1, 42)))
    with pytest.raises(ValidationError):
        FocusedSiteQuery(label_seq_ids=[1, 2], offset=1)
    assert not b._jobs()


@pytest.mark.asyncio
async def test_site_research_call_ceiling_forces_handoff_before_global_budget(
    site_bridge: Any,
) -> None:
    from langchain_core.tools import StructuredTool

    from tests.unit.agent.test_site_dossier import bind, handoff

    b = site_bridge
    cfg = scripted_config()
    eid = b.store.begin_execution(b.thread, "Bounded site research")["execution_id"]
    guard = RoleBoundary(b, "site", cfg, "Research", execution_id=eid, site_stage="research")
    for _ in range(SITE_RESEARCH_MODEL_CALL_LIMIT - 1):
        b.store.reserve_model_call(b.thread, "site", cfg.max_model_calls, eid)

    class Request(SimpleNamespace):
        model = SimpleNamespace(profile={})

        def override(self, **kwargs: Any) -> Any:
            return Request(**{**vars(self), **kwargs})

    tools = phase2_tools(b, "site") + [
        StructuredTool.from_function(lambda file_path: "", name="read_file", description="Skill")
    ]

    async def handler(request: Any) -> Any:
        assert request.tools == []
        assert "bounded Site reading budget is complete" in request.system_message.text
        return SimpleNamespace(
            result=[
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "SiteResearchHandoff",
                            "args": handoff().model_dump(mode="json"),
                            "id": "handoff",
                        }
                    ],
                )
            ],
            structured_response=handoff(),
        )

    request = Request(
        tools=tools,
        messages=[],
        model_settings={},
        system_message=SystemMessage(content="Research"),
    )
    token = bind(b)
    try:
        result = await guard.awrap_model_call(request, handler)
    finally:
        from easydesign.agent.phase2 import SITE_EVIDENCE

        SITE_EVIDENCE.reset(token)
    assert result.structured_response == handoff()
    context = [
        event["payload"] for event in b.store.events(b.thread) if event["kind"] == "model-context"
    ]
    assert context[-1]["site_research_finalization_reason"] == "model-call-budget"


@pytest.mark.asyncio
async def test_research_query_ceiling_returns_finalization_diagnostic_without_fetch(
    site_bridge: Any, monkeypatch: Any
) -> None:
    from easydesign.agent.evidence_research import RESEARCH_QUERY_LIMIT

    b = site_bridge
    eid = b.store.begin_execution(b.thread, "Finish bounded Site research")["execution_id"]
    for index in range(RESEARCH_QUERY_LIMIT):
        b.store.event(
            b.thread,
            "research-reservation",
            {"execution_id": eid, "query_id": f"synthetic-{index}"},
        )
    guard = RoleBoundary(b, "site", scripted_config(), "Research", execution_id=eid)
    worker = EvidenceResearch(b)
    monkeypatch.setattr(
        worker,
        "client",
        lambda _: pytest.fail("The query ceiling must be checked before any network client"),
    )
    value = ResearchQuery(
        topic="function",
        question="Does the bounded evidence support inhibition?",
        operation="literature-search",
        query="synthetic bounded evidence",
    )
    request = SimpleNamespace(
        tool_call={
            "name": "research_evidence",
            "id": "over-budget",
            "args": value.model_dump(mode="json"),
        }
    )

    async def handler(current: Any) -> Any:
        return worker.acquire(ResearchQuery.model_validate(current.tool_call["args"]), role="site")

    result = await guard.awrap_tool_call(request, handler)
    diagnostic = json.loads(result.content)
    assert result.status == "error"
    assert diagnostic["error_code"] == "RESEARCH_QUERY_BUDGET_COMPLETE"
    assert diagnostic["used_queries"] == diagnostic["query_limit"] == RESEARCH_QUERY_LIMIT
    assert diagnostic["required_action"] == "submit_site_research_handoff"
    events = b.store.events(b.thread)
    assert (
        len(
            [
                event
                for event in events
                if event["kind"] == "research-reservation"
                and event["payload"]["execution_id"] == eid
            ]
        )
        == RESEARCH_QUERY_LIMIT
    )
    assert not [event for event in events if event["kind"] == "tool-argument-repair"]


@pytest.mark.asyncio
async def test_site_query_ceiling_forces_typed_handoff_from_existing_evidence(
    site_bridge: Any,
) -> None:
    from langchain_core.tools import StructuredTool

    from easydesign.agent.harness import SITE_RESEARCH_QUERY_LIMIT
    from tests.unit.agent.test_site_dossier import bind, handoff

    b = site_bridge
    eid = b.store.begin_execution(b.thread, "Finalize bounded Site research")["execution_id"]
    for index in range(SITE_RESEARCH_QUERY_LIMIT):
        b.store.event(
            b.thread,
            "research-reservation",
            {"execution_id": eid, "query_id": f"synthetic-{index}"},
        )
    guard = RoleBoundary(
        b,
        "site",
        scripted_config(),
        "Research",
        execution_id=eid,
        site_stage="research",
    )

    class Request(SimpleNamespace):
        model = SimpleNamespace(profile={})

        def override(self, **kwargs: Any) -> Any:
            return Request(**{**vars(self), **kwargs})

    tools = phase2_tools(b, "site") + [
        StructuredTool.from_function(lambda file_path: "", name="read_file", description="Skill")
    ]
    calls = []

    async def handler(current: Any) -> Any:
        calls.append(current)
        assert current.tools == []
        assert "bounded Site reading budget is complete" in current.system_message.text
        assert any(
            "Submit SiteResearchHandoff now from delivered evidence" in str(message.content)
            for message in current.messages
        )
        return SimpleNamespace(
            result=[
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "SiteResearchHandoff",
                            "args": handoff().model_dump(mode="json"),
                            "id": "handoff",
                        }
                    ],
                )
            ],
            structured_response=handoff(),
        )

    request = Request(
        tools=tools,
        messages=[],
        model_settings={},
        system_message=SystemMessage(content="Research"),
    )
    token = bind(b)
    try:
        result = await guard.awrap_model_call(request, handler)
    finally:
        from easydesign.agent.phase2 import SITE_EVIDENCE

        SITE_EVIDENCE.reset(token)
    assert result.structured_response == handoff()
    assert len(calls) == 1
    context = [
        event["payload"] for event in b.store.events(b.thread) if event["kind"] == "model-context"
    ]
    assert context[-1]["tool_mode"] == "site-research-finalization"
    assert context[-1]["offered_action_tools"] == []


@pytest.mark.asyncio
async def test_unknown_model_tool_is_recorded_and_rejected_before_execution(bridge: Any) -> None:
    from langchain_core.tools import StructuredTool

    b = Phase2Bridge(bridge.project, bridge.thread, bridge.store)
    eid = b.store.begin_execution(b.thread, "Diagnose malformed tool choice")["execution_id"]
    guard = RoleBoundary(b, "site", scripted_config(), "Research", execution_id=eid)

    class Request(SimpleNamespace):
        model = SimpleNamespace(profile={})

        def override(self, **kwargs: Any) -> Any:
            return Request(**{**vars(self), **kwargs})

    async def handler(request: Any) -> Any:
        return SimpleNamespace(
            result=[
                AIMessage(
                    content="",
                    tool_calls=[{"name": "unavailable_scientific_tool", "id": "bad", "args": {}}],
                )
            ],
            structured_response=None,
        )

    tools = phase2_tools(b, "site") + [
        StructuredTool.from_function(lambda file_path: "", name="read_file", description="Skill")
    ]
    with pytest.raises(AgentBoundaryError, match="unavailable_scientific_tool"):
        await guard.awrap_model_call(
            Request(tools=tools, messages=[], system_message=SystemMessage(content="Research")),
            handler,
        )
    event = [e for e in b.store.events(b.thread) if e["kind"] == "rejected-tool-name"][-1]
    assert event["payload"]["executed"] is False
    assert event["payload"]["tool_names"] == ["unavailable_scientific_tool"]
    assert not b._jobs() and b.current_site() is None


def test_cursor_only_continuation_restores_verified_query_and_retains_hard_boundaries(
    bridge: Any, monkeypatch: Any
) -> None:
    import base64

    from easydesign.agent.contracts import EvidenceRetrievalQueryMismatch, StaleEvidenceCursor
    from easydesign.agent.evidence_corpus import ContinueEvidence

    b = Phase2Bridge(bridge.project, bridge.thread, bridge.store)
    b.store.begin_execution(b.thread, "Read consecutive source passages")
    fetches = source_transport(b, monkeypatch)
    EvidenceResearch(b).acquire(
        ResearchQuery.model_validate(
            {**ACQUIRE, "selection_reason": "Read complete assay conditions and counterevidence"}
        ),
        role="site",
    )
    corpus = EvidenceCorpus(b)
    query = RetrieveEvidence(
        need="FUNCTIONAL_MECHANISM",
        question="assay control",
        source_id="EuropePMC:PMC123",
        page_size=3,
    )
    first = corpus.retrieve(query)
    before_fetches = len(fetches)
    second = corpus.continue_page(ContinueEvidence(cursor=first["next_cursor"]))
    exact = corpus.retrieve(query.model_copy(update={"cursor": first["next_cursor"]}))
    assert (
        second == exact
        and second["question"] == query.question
        and second["source_id"] == query.source_id
    )
    assert not ({c["card_id"] for c in first["cards"]} & {c["card_id"] for c in second["cards"]})
    assert len(fetches) == before_fetches and not b._jobs()
    with pytest.raises(ValidationError):
        ContinueEvidence(cursor=first["next_cursor"], question="Different")
    other = EvidenceCorpus(Phase2Bridge(b.project, "foreign-view", b.store))
    with pytest.raises(AgentBoundaryError, match="foreign"):
        other.continue_page(ContinueEvidence(cursor=first["next_cursor"]))
    decoded = json.loads(base64.urlsafe_b64decode(first["next_cursor"]))
    decoded["offset"] = 100000
    altered = base64.urlsafe_b64encode(compact(decoded).encode()).decode()
    count = len([e for e in b.store.events(b.thread) if e["kind"] == "evidence-view"])
    with pytest.raises(EvidenceRetrievalQueryMismatch, match="Unissued"):
        corpus.continue_page(ContinueEvidence(cursor=altered))
    assert len([e for e in b.store.events(b.thread) if e["kind"] == "evidence-view"]) == count
    corpus.select(
        SelectEvidence(
            provider="EuropePMC",
            identifier="PMC123",
            need=query.need,
            selection="EXCLUDED",
            reason="Source no longer selected for this view",
        )
    )
    with pytest.raises(StaleEvidenceCursor):
        corpus.continue_page(ContinueEvidence(cursor=first["next_cursor"]))
    assert len(fetches) == before_fetches and not b._jobs()


@pytest.mark.asyncio
async def test_acquired_source_for_another_need_is_not_reported_as_empty_evidence(
    bridge: Any, monkeypatch: Any
) -> None:
    b = Phase2Bridge(bridge.project, bridge.thread, bridge.store)
    eid = b.store.begin_execution(b.thread, "Read known epitope evidence")["execution_id"]
    fetches = source_transport(b, monkeypatch)
    EvidenceResearch(b).acquire(
        ResearchQuery.model_validate(
            {**ACQUIRE, "selection_reason": "Read primary functional evidence"}
        ),
        role="site",
    )
    corpus = EvidenceCorpus(b)
    query = RetrieveEvidence(
        need="KNOWN_EPITOPE", question="assay control", source_id="EuropePMC:PMC123"
    )
    guard = RoleBoundary(b, "site", scripted_config(), "Compare epitope", execution_id=eid)

    async def handler(request: Any) -> Any:
        return ToolMessage(
            name="retrieve_evidence", tool_call_id="read", content=compact(corpus.retrieve(query))
        )

    request = SimpleNamespace(
        tool_call={"name": "retrieve_evidence", "id": "read", "args": query.model_dump()}
    )
    result = await guard.awrap_tool_call(request, handler)
    diagnostic = json.loads(result.content)
    assert result.status == "error" and diagnostic["error_code"] == "SOURCE_NOT_SELECTED"
    assert diagnostic["evidence_need"] == "KNOWN_EPITOPE" and "not absence" in diagnostic["message"]
    assert not [e for e in b.store.events(b.thread) if e["kind"] == "evidence-view"]
    assert len(fetches) == 1
    corpus.select(
        SelectEvidence(
            provider="EuropePMC",
            identifier="PMC123",
            need="KNOWN_EPITOPE",
            selection="SELECTED",
            reason="Assess the same primary source for epitope limitations",
        )
    )
    result = await guard.awrap_tool_call(request, handler)
    assert result.status == "success" and json.loads(result.content)["cards"]
    assert len(fetches) == 1 and not b._jobs()



@pytest.mark.asyncio
async def test_site_role_mismatch_has_one_semantic_repair_after_shape_repairs(
    site_bridge: Any, monkeypatch: Any
) -> None:
    from langchain_core.messages import HumanMessage

    from tests.unit.agent.test_site_dossier import bind, handoff

    b = site_bridge
    cfg = scripted_config()
    eid = b.store.begin_execution(b.thread, "Repair a known evidence-role mismatch")[
        "execution_id"
    ]
    for _ in range(SITE_RESEARCH_MODEL_CALL_LIMIT - 1):
        b.store.reserve_model_call(b.thread, "site", cfg.max_model_calls, eid)
    for index in range(2):
        b.store.reserve_contract_repair(
            b.thread,
            "site",
            eid,
            f"Synthetic prior shape error {index}",
            contract="SiteResearchHandoff",
        )

    guard = RoleBoundary(
        b,
        "site",
        cfg,
        "Synthetic Site research",
        execution_id=eid,
        site_stage="research",
        domain_skills=False,
    )
    attempts = 0

    def validate(*_args: Any) -> dict[str, Any]:
        if attempts == 1:
            raise EvidenceRoleMismatch(
                "EVIDENCE_ROLE_MISMATCH: passage-review is primary_eligible=false "
                "but was assigned strength=E2."
            )
        return {}

    monkeypatch.setattr("easydesign.agent.harness.site_dossier", validate)
    monkeypatch.setattr(
        "easydesign.agent.harness.site_research_packet_message",
        lambda *args, **kwargs: HumanMessage(
            content='{"runtime_site_research_packet":"semantic-repair"}'
        ),
    )

    class Request(SimpleNamespace):
        model = SimpleNamespace(profile={})

        def override(self, **kwargs: Any) -> Any:
            return Request(**{**vars(self), **kwargs})

    async def handler(current: Any) -> Any:
        nonlocal attempts
        attempts += 1
        if attempts == 2:
            assert "EVIDENCE_ROLE_MISMATCH" in current.system_message.text
        value = handoff()
        return SimpleNamespace(
            result=[
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "SiteResearchHandoff",
                            "args": value.model_dump(mode="json"),
                            "id": f"handoff-{attempts}",
                        }
                    ],
                )
            ],
            structured_response=value,
        )

    request = Request(
        tools=phase2_tools(b, "site"),
        messages=[],
        model_settings={},
        system_message=SystemMessage(content="Finalize Site research"),
    )
    token = bind(b)
    try:
        result = await guard.awrap_model_call(request, handler)
    finally:
        from easydesign.agent.phase2 import SITE_EVIDENCE

        SITE_EVIDENCE.reset(token)

    assert result.structured_response == handoff()
    assert attempts == 2
    repairs = [
        event["payload"]
        for event in b.store.events(b.thread)
        if event["kind"] == "contract-repair"
    ]
    assert [repair["contract"] for repair in repairs] == [
        "SiteResearchHandoff",
        "SiteResearchHandoff",
        "SiteResearchHandoff:evidence-role",
    ]
    assert repairs[-1]["repair_limit"] == 1


@pytest.mark.asyncio
async def test_site_citation_repair_slot_is_durable_and_exhausts_fatally(
    site_bridge: Any, monkeypatch: Any
) -> None:
    from tests.unit.agent.test_site_dossier import handoff

    b = site_bridge
    cfg = scripted_config()
    eid = b.store.begin_execution(b.thread, "Reject repeated known-source citation mismatch")[
        "execution_id"
    ]
    for index in range(2):
        b.store.reserve_contract_repair(
            b.thread,
            "site",
            eid,
            f"Synthetic prior shape error {index}",
            contract="SiteResearchHandoff",
        )

    guard = RoleBoundary(
        b,
        "site",
        cfg,
        "Synthetic Site research",
        execution_id=eid,
        site_stage="research",
        domain_skills=False,
    )
    attempts = 0

    def reject_citation(*_args: Any) -> dict[str, Any]:
        raise EvidenceCitationMismatch(
            "CITATION_MISMATCH for known source passage-synthetic: use the exact passage."
        )

    monkeypatch.setattr("easydesign.agent.harness.site_dossier", reject_citation)

    class Request(SimpleNamespace):
        model = SimpleNamespace(profile={})

        def override(self, **kwargs: Any) -> Any:
            return Request(**{**vars(self), **kwargs})

    async def handler(current: Any) -> Any:
        nonlocal attempts
        attempts += 1
        if attempts == 2:
            assert "CITATION_MISMATCH" in current.system_message.text
        value = handoff()
        return SimpleNamespace(
            result=[
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "SiteResearchHandoff",
                            "args": value.model_dump(mode="json"),
                            "id": f"handoff-{attempts}",
                        }
                    ],
                )
            ],
            structured_response=value,
        )

    request = Request(
        tools=phase2_tools(b, "site"),
        messages=[],
        model_settings={},
        system_message=SystemMessage(content="Finalize Site research"),
    )
    with pytest.raises(AgentBoundaryError, match="repair budget exhausted"):
        await guard.awrap_model_call(request, handler)

    assert attempts == 2
    repairs = [
        event["payload"]
        for event in b.store.events(b.thread)
        if event["kind"] == "contract-repair"
    ]
    assert [repair["contract"] for repair in repairs] == [
        "SiteResearchHandoff",
        "SiteResearchHandoff",
        "SiteResearchHandoff:evidence-citation",
    ]
    assert repairs[-1]["repair_limit"] == 1
    reopened = SessionStore(b.project)
    try:
        with pytest.raises(AgentBoundaryError, match="repair budget exhausted"):
            reopened.reserve_contract_repair(
                b.thread,
                "site",
                eid,
                "CITATION_MISMATCH after restart",
                contract="SiteResearchHandoff:evidence-citation",
                max_repairs=1,
            )
    finally:
        reopened.close()


@pytest.mark.asyncio
async def test_site_distinct_focused_citation_cards_converge_within_two_rounds(
    site_bridge: Any, monkeypatch: Any
) -> None:
    from tests.unit.agent.test_site_dossier import handoff

    b = site_bridge
    eid = b.store.begin_execution(b.thread, "Repair two distinct focused citations")[
        "execution_id"
    ]
    for index in range(2):
        b.store.reserve_contract_repair(
            b.thread,
            "site",
            eid,
            f"Synthetic prior shape error {index}",
            contract="SiteResearchHandoff",
        )
    guard = RoleBoundary(
        b,
        "site",
        scripted_config(),
        "Synthetic Site research",
        execution_id=eid,
        site_stage="research",
        domain_skills=False,
    )
    validations = 0

    def validate_citations(*_args: Any) -> dict[str, Any]:
        nonlocal validations
        validations += 1
        if validations <= 2:
            card = f"passage-distinct-{validations}"
            raise EvidenceCitationMismatch(
                f"CITATION_MISMATCH for known source {card}: use the exact passage.",
                repair_keys=(f"known-source:{card}",),
            )
        return {}

    monkeypatch.setattr("easydesign.agent.harness.site_dossier", validate_citations)

    class Request(SimpleNamespace):
        model = SimpleNamespace(profile={})

        def override(self, **kwargs: Any) -> Any:
            return Request(**{**vars(self), **kwargs})

    attempts = 0

    async def handler(current: Any) -> Any:
        nonlocal attempts
        attempts += 1
        if attempts > 1:
            assert "CITATION_MISMATCH" in current.system_message.text
        value = handoff()
        return SimpleNamespace(
            result=[
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "SiteResearchHandoff",
                            "args": value.model_dump(mode="json"),
                            "id": f"handoff-{attempts}",
                        }
                    ],
                )
            ],
            structured_response=value,
        )

    result = await guard.awrap_model_call(
        Request(
            tools=phase2_tools(b, "site"),
            messages=[],
            model_settings={},
            system_message=SystemMessage(content="Finalize Site research"),
        ),
        handler,
    )

    assert result.structured_response == handoff()
    assert attempts == validations == 3
    repairs = [
        event["payload"]
        for event in b.store.events(b.thread)
        if event["kind"] == "contract-repair"
    ]
    assert [repair["contract"] for repair in repairs] == [
        "SiteResearchHandoff",
        "SiteResearchHandoff",
        "SiteResearchHandoff:evidence-citation",
        "SiteResearchHandoff:evidence-citation",
    ]
    assert [repair["attempt"] for repair in repairs[-2:]] == [1, 2]
    assert [repair["repair_keys"] for repair in repairs[-2:]] == [
        ["known-source:passage-distinct-1"],
        ["known-source:passage-distinct-2"],
    ]
    assert all(repair["repair_limit"] == 2 for repair in repairs[-2:])
    assert len(
        [
            event
            for event in b.store.events(b.thread)
            if event["kind"] == "model-call"
            and event["payload"]["execution_id"] == eid
        ]
    ) == 3


def test_keyed_citation_repair_is_per_card_bounded_and_restart_durable(
    site_bridge: Any,
) -> None:
    b = site_bridge
    eid = b.store.begin_execution(b.thread, "Persist focused citation repair keys")[
        "execution_id"
    ]
    contract = "SiteResearchHandoff:evidence-citation"
    assert (
        b.store.reserve_keyed_contract_repair(
            b.thread,
            "site",
            eid,
            "first card",
            contract=contract,
            repair_keys=("known-source:passage-a",),
        )
        == 1
    )
    reopened = SessionStore(b.project)
    try:
        with pytest.raises(AgentBoundaryError, match="same evidence card"):
            reopened.reserve_keyed_contract_repair(
                b.thread,
                "site",
                eid,
                "same card with a different bad excerpt",
                contract=contract,
                repair_keys=("known-source:passage-a",),
            )
        assert (
            reopened.reserve_keyed_contract_repair(
                b.thread,
                "site",
                eid,
                "second card",
                contract=contract,
                repair_keys=("known-source:passage-b",),
            )
            == 2
        )
        with pytest.raises(AgentBoundaryError, match="2 rounds"):
            reopened.reserve_keyed_contract_repair(
                b.thread,
                "site",
                eid,
                "third card",
                contract=contract,
                repair_keys=("known-source:passage-c",),
            )
    finally:
        reopened.close()


def test_keyed_citation_batch_consumes_each_card_and_legacy_is_fail_closed(
    site_bridge: Any,
) -> None:
    b = site_bridge
    contract = "SiteResearchHandoff:evidence-citation"
    eid = b.store.begin_execution(b.thread, "Persist a citation repair batch")["execution_id"]
    assert (
        b.store.reserve_keyed_contract_repair(
            b.thread,
            "site",
            eid,
            "two cards in one rejected submission",
            contract=contract,
            repair_keys=("known-source:passage-b", "known-source:passage-a"),
        )
        == 1
    )
    event = [
        event["payload"]
        for event in b.store.events(b.thread)
        if event["kind"] == "contract-repair"
    ][-1]
    assert event["repair_keys"] == [
        "known-source:passage-a",
        "known-source:passage-b",
    ]
    with pytest.raises(AgentBoundaryError, match="same evidence card"):
        b.store.reserve_keyed_contract_repair(
            b.thread,
            "site",
            eid,
            "repeat one card from the batch",
            contract=contract,
            repair_keys=("known-source:passage-b", "known-source:passage-c"),
        )

    legacy_eid = b.store.begin_execution(b.thread, "Conservatively retain a legacy repair")[
        "execution_id"
    ]
    b.store.reserve_contract_repair(
        b.thread,
        "site",
        legacy_eid,
        "legacy unkeyed citation mismatch",
        max_repairs=1,
    )
    with pytest.raises(AgentBoundaryError, match="unkeyed repair"):
        b.store.reserve_keyed_contract_repair(
            b.thread,
            "site",
            legacy_eid,
            "new keyed mismatch after legacy state",
            contract=contract,
            repair_keys=("known-source:passage-new",),
        )


def test_concurrent_keyed_citation_reservation_is_fail_closed(site_bridge: Any) -> None:
    b = site_bridge
    eid = b.store.begin_execution(b.thread, "Race one focused citation repair")["execution_id"]
    contract = "SiteResearchHandoff:evidence-citation"
    barrier = Barrier(2)

    def reserve() -> int | str:
        store = SessionStore(b.project)
        try:
            barrier.wait()
            return store.reserve_keyed_contract_repair(
                b.thread,
                "site",
                eid,
                "concurrent same-card mismatch",
                contract=contract,
                repair_keys=("known-source:passage-race",),
            )
        except AgentBoundaryError as error:
            return str(error)
        finally:
            store.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(lambda _index: reserve(), range(2)))

    assert outcomes.count(1) == 1
    assert len([outcome for outcome in outcomes if isinstance(outcome, str)]) == 1
    repairs = [
        event["payload"]
        for event in b.store.events(b.thread)
        if event["kind"] == "contract-repair"
        and event["payload"].get("execution_id") == eid
        and event["payload"].get("contract") == contract
    ]
    assert len(repairs) == 1
    assert repairs[0]["repair_keys"] == ["known-source:passage-race"]
