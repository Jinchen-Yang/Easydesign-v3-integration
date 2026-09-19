"""Stable full sources across canonical configuration; current views remain explicitly scoped."""

import base64
import json
from typing import Any

import httpx
import pytest

from easydesign.agent.contracts import (
    AgentBoundaryError,
    EvidenceRetrievalQueryMismatch,
    SourceSelectionRequired,
    StaleEvidenceCursor,
)
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
    assert EvidenceCorpus(b).retrieve(focus())["cards"]
    result = propose_canonical(
        b,
        CanonicalProposal(
            uniprot_card_id=queries["P00698"]["cards"][0]["card_id"],
            reason="Use the verified supplied accession before deterministic comparison",
        ),
    )
    assert result["status"] == "canonical-reference-configured"


def test_canonical_revision_keeps_exact_source_and_scoped_cards(acquired: Any) -> None:
    b, calls, queries = acquired
    corpus = EvidenceCorpus(b)
    before = corpus.retrieve(focus())
    documents = {d["source_id"]: d for d in corpus.documents()}
    assert before["cards"] and len(calls) == 2
    revise(b, queries)
    assert before["next_cursor"]
    with pytest.raises(StaleEvidenceCursor, match="another question/thread") as rejected:
        corpus.retrieve(focus().model_copy(update={"cursor": before["next_cursor"]}))
    assert rejected.value.result()["error_code"] == "STALE_EVIDENCE_CURSOR"
    assert "No stale evidence was delivered" in rejected.value.result()["message"]
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
    with pytest.raises(SourceSelectionRequired):
        corpus.retrieve(focus("UniProt:P12345"))
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
    execution_id = b.store.latest_execution(b.thread)["execution_id"]
    scoped_ids = {
        c["identifier"]
        for q in EvidenceResearch(b).snapshot(execution_id=execution_id)["queries"]
        for c in q["cards"]
    }
    assert scoped_ids == ids
    research_events = [e for e in b.store.events(b.thread) if e["kind"] == "evidence-research"]
    assert research_events
    assert all(e["payload"].get("execution_id") == execution_id for e in research_events)
    assert all(e["payload"].get("role") == "target" for e in research_events)
    assert not b._jobs()


def test_identity_passage_keeps_source_lengths_and_processing_coordinates_together(
    acquired: Any,
) -> None:
    import json

    b, _, _ = acquired
    page = EvidenceCorpus(b).retrieve(
        RetrieveEvidence(
            need="TARGET_IDENTITY",
            source_id="UniProt:P00698",
            question="What are the precursor and mature chain boundaries, signal peptide range, "
            "and mature protein residue numbering for hen egg-white lysozyme?",
        )
    )
    first = page["cards"][0]
    facts = json.loads(first["passage"])
    truth = golden_truth()["soluble"]
    assert facts["accession"] == "P00698"
    assert facts["source_sequence_length"] == len(truth["canonical_sequence"]) == 147
    assert facts["processing_features"] == [
        f for f in truth["features"] if f.get("type") in {"Signal", "Propeptide", "Chain"}
    ]
    assert "not structure numbering" in facts["numbering_scope"]
    assert first["source_status"] == "VERIFIED"


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
        assert corpus.documents()
        with pytest.raises(SourceSelectionRequired):
            corpus.retrieve(q)
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
        with pytest.raises(SourceSelectionRequired):  # No identity selection in this thread.
            corpus.retrieve(focus())
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


def test_explicit_feature_scope_uses_verified_original_types_and_preserves_passages(
    acquired: Any,
) -> None:
    b, calls, _ = acquired
    corpus = EvidenceCorpus(b)
    original = {d["source_id"]: d for d in corpus.documents()}["UniProt:P00698"]
    chunks = b.document(original["corpus_ref"])["chunks"]
    query = focus().model_copy(update={"feature_types": ["Signal", "Chain"], "page_size": 1})
    first = corpus.retrieve(query)
    assert first["matching_chunks"] == 2 and first["next_cursor"]
    with pytest.raises(StaleEvidenceCursor):
        corpus.retrieve(
            query.model_copy(update={"feature_types": ["Chain"], "cursor": first["next_cursor"]})
        )
    second = corpus.retrieve(query.model_copy(update={"cursor": first["next_cursor"]}))
    assert second["next_cursor"] == ""
    cards = first["cards"] + second["cards"]
    assert {json.loads(c["passage"])["type"] for c in cards} == {"Signal", "Chain"}
    assert all(c["passage"] == chunks[c["chunk"]]["text"] for c in cards)
    mismatch = corpus.retrieve(query.model_copy(update={"feature_types": ["Signal peptide"]}))
    assert not mismatch["cards"]
    scope = mismatch["feature_scope"]["UniProt:P00698"]
    assert set(scope["available_types"]) == {"Signal", "Chain"}
    assert scope["unmatched_requested_types"] == ["Signal peptide"]
    assert "not biological absence" in scope["note"]
    assert len(calls) == 2  # Initial two acquired references; no additional source request.


@pytest.mark.asyncio
async def test_acquisition_receipt_exposes_literal_types_without_refetching(acquired: Any) -> None:
    from easydesign.agent.evidence_research import research_tool

    b, calls, _ = acquired
    result = json.loads(
        await research_tool(b, "site").ainvoke(
            {
                "topic": "identity",
                "operation": "uniprot-record",
                "identifier": "P00698",
                "question": "Read source processing annotations",
                "selection_reason": "Inspect literal annotation types",
            }
        )
    )
    assert result["cards"][0]["feature_types_available"] == ["Chain", "Signal"]
    assert len(calls) == 2 and not b._jobs()


def test_altered_owned_cursor_returns_no_evidence_and_foreign_view_stays_fatal(
    acquired: Any,
) -> None:
    b, calls, _ = acquired
    corpus = EvidenceCorpus(b)
    query = focus().model_copy(update={"feature_types": ["Signal", "Chain"], "page_size": 1})
    first = corpus.retrieve(query)
    decoded = json.loads(base64.urlsafe_b64decode(first["next_cursor"]))
    decoded["offset"] = 0
    altered = base64.urlsafe_b64encode(json.dumps(decoded).encode()).decode()
    before = len(b.store.events(b.thread))
    for question in [query.question, "A new annotation question"]:
        with pytest.raises(EvidenceRetrievalQueryMismatch, match="never issued"):
            corpus.retrieve(query.model_copy(update={"cursor": altered, "question": question}))
    assert len(b.store.events(b.thread)) == before
    decoded["view"] = "0" * 64
    foreign = base64.urlsafe_b64encode(json.dumps(decoded).encode()).decode()
    with pytest.raises(AgentBoundaryError, match="another question/thread"):
        corpus.retrieve(query.model_copy(update={"cursor": foreign}))
    second = corpus.retrieve(query.model_copy(update={"cursor": first["next_cursor"]}))
    assert second["cards"][0]["card_id"] != first["cards"][0]["card_id"]
    assert not second["next_cursor"] and len(calls) == 2 and not b._jobs()


@pytest.mark.asyncio
async def test_reused_receipt_distinguishes_current_selection_from_acquisition_history(
    acquired: Any,
) -> None:
    from easydesign.agent.evidence_research import research_tool
    from easydesign.core import ArtifactRef

    b, calls, queries = acquired
    original = json.loads(json.dumps(queries["P00698"]["cards"][0]))
    refs = [original["corpus_ref"], *original["source_refs"]]
    source_bytes = {
        ArtifactRef.model_validate(ref).verify(b.project): ArtifactRef.model_validate(ref)
        .verify(b.project)
        .read_bytes()
        for ref in refs
    }
    other = Phase2Bridge(b.project, "same-source-different-purpose", b.store)
    other.store.begin_execution(other.thread, "Read an existing source for a new evidence need")
    corpus = EvidenceCorpus(other)
    with pytest.raises(SourceSelectionRequired):
        corpus.retrieve(focus())
    result = json.loads(
        await research_tool(other, "site").ainvoke(
            {
                "topic": "state",
                "operation": "uniprot-record",
                "identifier": "P00698",
                "question": "Read the retained Chain and Signal annotations as context",
                "selection_reason": "Inspect existing source context for this separate question",
            }
        )
    )
    card = result["cards"][0]
    assert result["need"] == card["retrieval_need"] == "STRUCTURE_STATE"
    assert card["original_acquisition_need"] == "TARGET_IDENTITY"
    assert "need" not in card
    assert card["card_id"] == original["card_id"]
    page = corpus.retrieve(focus().model_copy(update={"need": card["retrieval_need"]}))
    assert page["cards"]
    # Historical source purpose cannot grant the new thread another current selection.
    with pytest.raises(SourceSelectionRequired):
        corpus.retrieve(focus())
    assert queries["P00698"]["cards"][0] == original
    assert all(path.read_bytes() == data for path, data in source_bytes.items())
    assert len(calls) == 2 and not b._jobs()
