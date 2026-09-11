"""Stable full sources across canonical configuration; current views remain explicitly scoped."""

from typing import Any

import httpx
import pytest

from easydesign.agent.contracts import AgentBoundaryError, SourceSelectionRequired
from easydesign.agent.evidence_corpus import EvidenceCorpus, RetrieveEvidence, SelectEvidence
from easydesign.agent.evidence_research import EvidenceResearch, ResearchHttpClient, ResearchQuery
from easydesign.agent.phase2 import Phase2Bridge
from easydesign.agent.session_store import SessionStore
from easydesign.agent.target_identity import CanonicalProposal, propose_canonical
from easydesign.core import ArtifactIntegrityError
from tests.agent_golden_support import golden_truth
from tests.agent_support import make_project


@pytest.fixture
def acquired(bridge: Any, monkeypatch: Any) -> Any:
    b = Phase2Bridge(bridge.project, bridge.thread, bridge.store)
    b.store.begin_execution(b.thread, "Resolve lysozyme canonical identity")
    truth = golden_truth()["soluble"]
    calls = []

    def respond(request: Any) -> httpx.Response:
        calls.append(str(request.url))
        accession = request.url.path.rsplit("/", 1)[-1].removesuffix(".json")
        return httpx.Response(
            200,
            json={
                "primaryAccession": accession,
                "entryType": "UniProtKB reviewed (Swiss-Prot)",
                "organism": {"taxonId": truth["taxon_id"]},
                "sequence": {"value": truth["canonical_sequence"]},
                "features": truth["features"],
            },
        )

    monkeypatch.setattr(
        EvidenceResearch,
        "client",
        lambda self, directory: ResearchHttpClient(
            evidence_dir=directory,
            max_attempts=1,
            client=httpx.Client(transport=httpx.MockTransport(respond)),
        ),
    )
    corpus = EvidenceCorpus(b)
    queries = {}
    for accession in ("P00698", "P12345"):
        corpus.select(
            SelectEvidence(
                provider="UniProt",
                identifier=accession,
                need="TARGET_IDENTITY",
                selection="SELECTED",
                reason="Compare candidate canonical references",
            )
        )
        query = ResearchQuery(
            topic="identity",
            question="Identify the precursor and mature chain",
            operation="uniprot-record",
            identifier=accession,
        )
        queries[accession] = EvidenceResearch(b).acquire(query, role="target")
    return b, calls, queries


def focus(source: str = "UniProt:P00698") -> RetrieveEvidence:
    return RetrieveEvidence(
        need="TARGET_IDENTITY", question="Signal Chain precursor mature", source_id=source
    )


def revise(b: Any, queries: Any) -> None:
    propose_canonical(
        b,
        CanonicalProposal(
            uniprot_card_id=queries["P00698"]["cards"][0]["card_id"],
            reason="Use the verified supplied accession before deterministic comparison",
        ),
    )


def test_canonical_revision_keeps_exact_source_and_scoped_cards(acquired: Any) -> None:
    b, calls, queries = acquired
    corpus = EvidenceCorpus(b)
    before = corpus.retrieve(focus())
    documents = {d["source_id"]: d for d in corpus.documents()}
    assert before["cards"] and len(calls) == 2
    revise(b, queries)
    assert before["next_cursor"]
    with pytest.raises(AgentBoundaryError, match="another question/thread"):
        corpus.retrieve(focus().model_copy(update={"cursor": before["next_cursor"]}))
    after = corpus.retrieve(focus())
    assert after["cards"]
    assert before["cards"][0]["passage"] == after["cards"][0]["passage"]
    assert before["cards"][0]["project_evidence_id"] == after["cards"][0]["project_evidence_id"]
    context = after["cards"][0]["binding_context"]
    assert context["relation"] == "current-canonical-reference"
    assert context["current_binding"] != context["acquired_binding"]
    assert after["cards"][0]["source_status"] == "VERIFIED"
    assert after["cards"][0]["selection_provenance"] == before["cards"][0]["selection_provenance"]
    assert {d["source_id"]: d["corpus_ref"] for d in corpus.documents()} == {
        key: d["corpus_ref"] for key, d in documents.items()
    }
    replayed = EvidenceResearch(b).acquire(
        ResearchQuery(
            topic="identity",
            question="Read signal peptide limits again without downloading",
            operation="uniprot-record",
            identifier="P00698",
        ),
        role="target",
    )
    assert replayed["reused_verified_source"] and len(calls) == 2
    assert replayed["cards"][0]["corpus_ref"] == documents["UniProt:P00698"]["corpus_ref"]
    assert not corpus.retrieve(focus("UniProt:P12345"))["cards"]
    with pytest.raises(SourceSelectionRequired):
        EvidenceResearch(b).acquire(
            ResearchQuery(
                topic="identity",
                question="Read unrelated source",
                operation="uniprot-record",
                identifier="P12345",
            ),
            role="target",
        )
    ids = {c["identifier"] for q in EvidenceResearch(b).snapshot()["queries"] for c in q["cards"]}
    assert ids == {"P00698"}
    assert not b._jobs()


def test_restart_new_thread_and_new_need_reuse_source_only_after_selection(acquired: Any) -> None:
    b, calls, queries = acquired
    revise(b, queries)
    store = SessionStore(b.project)
    other = Phase2Bridge(b.project, "independent-thread", store)
    store.begin_execution(other.thread, "Inspect state in another thread")
    try:
        corpus = EvidenceCorpus(other)
        q = RetrieveEvidence(
            need="STRUCTURE_STATE", question="Signal Chain", source_id="UniProt:P00698"
        )
        assert corpus.documents() and not corpus.retrieve(q)["cards"]
        corpus.select(
            SelectEvidence(
                provider="UniProt",
                identifier="P00698",
                need="STRUCTURE_STATE",
                selection="SELECTED",
                reason="Assess relevant state annotations independently",
            )
        )
        result = EvidenceResearch(other).acquire(
            ResearchQuery(
                topic="state",
                question="Inspect current state evidence",
                operation="uniprot-record",
                identifier="P00698",
            ),
            role="site",
        )
        assert result["reused_verified_source"] and len(calls) == 2
        assert corpus.retrieve(q)["cards"]
        assert not corpus.retrieve(focus())["cards"]  # No identity selection in this thread.
    finally:
        store.close()


def test_foreign_project_cannot_read_source_or_cursor(
    acquired: Any, tmp_path: Any, monkeypatch: Any
) -> None:
    b, _, _ = acquired
    before = EvidenceCorpus(b).retrieve(focus())
    other_root = tmp_path / "isolated-project-workspace"
    other_root.mkdir()
    other = make_project(other_root, monkeypatch)
    foreign = Phase2Bridge(other.project, other.thread, other.store)
    foreign.store.begin_execution(foreign.thread, "Unrelated project")
    try:
        corpus = EvidenceCorpus(foreign)
        corpus.select(
            SelectEvidence(
                provider="UniProt",
                identifier="P00698",
                need="TARGET_IDENTITY",
                selection="SELECTED",
                reason="Independent source selection",
            )
        )
        assert not corpus.documents() and not corpus.retrieve(focus())["cards"]
        if before["next_cursor"]:
            with pytest.raises(AgentBoundaryError, match="another question/thread"):
                corpus.retrieve(focus().model_copy(update={"cursor": before["next_cursor"]}))
    finally:
        foreign.store.close()


def test_canonical_carry_forward_cannot_hide_source_tampering(acquired: Any) -> None:
    b, _, queries = acquired
    revise(b, queries)
    ref = queries["P00698"]["cards"][0]["source_refs"][0]
    (b.project / ref["relative_path"]).write_text("{}")
    with pytest.raises(ArtifactIntegrityError):
        EvidenceCorpus(b).retrieve(focus())
