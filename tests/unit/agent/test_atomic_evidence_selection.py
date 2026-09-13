"""Select and read a named durable source without a separate ordering dependency."""

from typing import Any

import pytest
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.memory import MemorySaver
from pydantic import ValidationError

from easydesign.agent.contracts import EvidenceRetrievalQueryMismatch, SourceSelectionRequired
from easydesign.agent.evidence_corpus import EvidenceCorpus, RetrieveEvidence
from easydesign.agent.evidence_research import EvidenceResearch, ResearchQuery
from easydesign.agent.harness import create_harness
from easydesign.agent.phase2 import Phase2Bridge
from easydesign.agent.phase2_tools import PHASE2_ALLOWED
from easydesign.core import ArtifactIntegrityError
from tests.agent_support import scripted_config
from tests.unit.agent.test_prerequisite_recovery import (
    ACQUIRE,
    RAW,
    RecoveryModel,
    assert_inspection_stopped,
    source_transport,
)

READ = {
    "need": "KNOWN_EPITOPE",
    "question": "assay control",
    "source_id": "EuropePMC:PMC123",
}
REASON = "Read the same assay for epitope transfer limits, without claiming a mapped epitope"


@pytest.fixture
def corpus(bridge: Any, monkeypatch: Any) -> Any:
    b = Phase2Bridge(bridge.project, bridge.thread, bridge.store)
    b.store.begin_execution(b.thread, "Inspect a saved source")
    requests = source_transport(b, monkeypatch)
    EvidenceResearch(b).acquire(
        ResearchQuery.model_validate({**ACQUIRE, "selection_reason": "Read primary assay"}),
        role="target",
    )
    yield EvidenceCorpus(b), requests


def test_new_need_is_explicit_and_reuses_exact_bytes_without_network(corpus: Any) -> None:
    c, requests = corpus
    with pytest.raises(SourceSelectionRequired):
        c.retrieve(RetrieveEvidence.model_validate(READ))
    value = c.retrieve(RetrieveEvidence.model_validate({**READ, "selection_reason": REASON}))
    assert value["cards"] and len(requests) == 1
    assert all(card["selection_provenance"]["reason"] == REASON for card in value["cards"])
    document = c.documents()[0]
    assert (c.bridge.project / document["source_refs"][0]["relative_path"]).read_bytes() == RAW
    assert c.selections()["EuropePMC:PMC123:FUNCTIONAL_MECHANISM"]["reason"] == "Read primary assay"
    assert c.selections()["EuropePMC:PMC123:KNOWN_EPITOPE"]["reason"] == REASON
    assert not c.bridge._jobs()


def test_selection_remains_thread_need_and_binding_scoped(corpus: Any) -> None:
    c, _ = corpus
    c.retrieve(RetrieveEvidence.model_validate({**READ, "selection_reason": REASON}))
    other = EvidenceCorpus(Phase2Bridge(c.bridge.project, "other-thread", c.bridge.store))
    assert not other.selections()
    with pytest.raises(SourceSelectionRequired):
        other.retrieve(RetrieveEvidence.model_validate(READ))
    with pytest.raises(SourceSelectionRequired):
        c.retrieve(RetrieveEvidence.model_validate({**READ, "need": "STRUCTURE_STATE"}))
    c.bridge.binding = lambda: {"target": "changed-target"}
    with pytest.raises(SourceSelectionRequired):
        c.retrieve(RetrieveEvidence.model_validate(READ))


@pytest.mark.parametrize("source_id", ["EuropePMC:PMC999", "EuropePMC:PMC12", "RCSB:PMC123"])
def test_unknown_or_different_source_does_not_select(corpus: Any, source_id: str) -> None:
    c, _ = corpus
    before = c.selections()
    with pytest.raises(EvidenceRetrievalQueryMismatch, match="exact acquired"):
        c.retrieve(
            RetrieveEvidence.model_validate(
                {**READ, "source_id": source_id, "selection_reason": REASON}
            )
        )
    assert c.selections() == before


@pytest.mark.parametrize("ref_key", ["source_refs", "corpus_ref"])
def test_tampered_source_or_corpus_cannot_be_selected_or_read(corpus: Any, ref_key: str) -> None:
    c, _ = corpus
    doc = c.documents()[0]
    ref = doc[ref_key][0] if ref_key == "source_refs" else doc[ref_key]
    (c.bridge.project / ref["relative_path"]).write_bytes(b"synthetic tamper")
    before = c.selections()
    with pytest.raises(ArtifactIntegrityError):
        c.retrieve(RetrieveEvidence.model_validate({**READ, "selection_reason": REASON}))
    assert c.selections() == before


@pytest.mark.parametrize(
    "override", [{"source_id": ""}, {"cursor": "issued-token"}, {"selection_reason": "  "}]
)
def test_selection_requires_named_source_new_query_and_nonblank_reason(override: Any) -> None:
    with pytest.raises(ValidationError):
        RetrieveEvidence.model_validate({**READ, "selection_reason": REASON, **override})


class AtomicSelectionModel(RecoveryModel):
    def answer(self, messages: Any) -> AIMessage:
        response = super().answer(messages)
        for call in response.tool_calls:
            if call["name"] == "research_evidence":
                call["args"]["selection_reason"] = "Read primary assay"
            elif call["name"] == "retrieve_evidence":
                call["args"].update(READ, selection_reason=REASON)
        return response


@pytest.mark.asyncio
async def test_actual_harness_acquires_then_reads_new_need_with_no_repairs(
    bridge: Any, monkeypatch: Any
) -> None:
    b = Phase2Bridge(bridge.project, bridge.thread, bridge.store)
    requests = source_transport(b, monkeypatch)
    goal = "Inspect PMC123 without approving science"
    execution = b.store.begin_execution(b.thread, goal)["execution_id"]
    models = {role: AtomicSelectionModel(role=role) for role in PHASE2_ALLOWED}
    graph = create_harness(
        b, models, scripted_config(), MemorySaver(), goal, execution_id=execution
    )
    result = await graph.ainvoke(
        {"messages": [HumanMessage(content=goal)]}, {"configurable": {"thread_id": b.thread}}
    )
    assert_inspection_stopped(b, result)
    assert len(requests) == 1 and not models["target"].repairs
    assert not any("repair" in e["kind"] for e in b.store.events(b.thread))
    assert EvidenceCorpus(b).selections()["EuropePMC:PMC123:KNOWN_EPITOPE"]["reason"] == REASON
