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

    class Request(SimpleNamespace):
        def override(self, **kwargs: Any) -> Any:
            return Request(**{**vars(self), **kwargs})

    async def handler(request: Any) -> Any:
        names.append({t.name for t in request.tools})
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
    assert "prepare_target" in names[-1] and "select_evidence" in names[-1]
    assert not b._jobs()
    monkeypatch.setattr(b, "get_job_status", lambda: {"status": "running", "job_id": "bound"})
    await guard.awrap_model_call(request, handler)
    assert "get_job_status" in names[-1]
    assert names[-1] - names[0] == {"get_job_status"}
    assert not b._jobs()


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
    for attempt in (1, 2):
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
