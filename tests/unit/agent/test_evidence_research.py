"""Synthetic source responses exercise real transport/cache/artifact and opinion boundaries."""

from types import SimpleNamespace
from typing import Any

import httpx
import pytest

from easydesign.agent.contracts import AgentBoundaryError
from easydesign.agent.evidence_corpus import EvidenceCorpus, RetrieveEvidence, SelectEvidence
from easydesign.agent.evidence_research import (
    EvidenceResearch,
    ResearchConclusion,
    ResearchHttpClient,
    ResearchQuery,
)
from easydesign.agent.phase2 import Phase2Bridge
from easydesign.agent.session_store import SessionStore
from easydesign.core import ArtifactIntegrityError


@pytest.fixture
def research(tmp_path: Any) -> Any:
    store = SessionStore(tmp_path)
    bridge = SimpleNamespace(
        project=tmp_path,
        thread="research-owner",
        store=store,
        binding=lambda: {"target": "synthetic-target"},
    )
    bridge.persist = lambda kind, payload: Phase2Bridge.persist(bridge, kind, payload)
    bridge.document = lambda ref: Phase2Bridge.document(bridge, ref)
    store.begin_execution(bridge.thread, "Explore the functional epitope")
    worker = EvidenceResearch(bridge)
    yield worker
    store.close()


def transport(
    worker: Any, monkeypatch: Any, response: dict[str, Any] | None = None, status: int = 200
) -> list[Any]:
    requests: list[Any] = []

    def handler(request: Any) -> Any:
        requests.append(request)
        return httpx.Response(status, json=response or {"resultList": {"result": []}})

    monkeypatch.setattr(
        worker,
        "client",
        lambda directory: ResearchHttpClient(
            evidence_dir=directory,
            cache_root=worker.bridge.project / "http-cache",
            max_attempts=1,
            client=httpx.Client(transport=httpx.MockTransport(handler)),
        ),
    )
    return requests


def query(topic: str = "function", **kwargs: Any) -> ResearchQuery:
    return ResearchQuery.model_validate(
        {
            "topic": topic,
            "question": "Does binding inhibit the enzyme?",
            "operation": "literature-search",
            "query": "synthetic enzyme inhibition",
            **kwargs,
        }
    )


def select(worker: Any, identifier: str, need: str = "FUNCTIONAL_MECHANISM") -> None:
    EvidenceCorpus(worker.bridge).select(
        SelectEvidence.model_validate(
            {
                "provider": "EuropePMC",
                "identifier": identifier,
                "need": need,
                "selection": "SELECTED",
                "reason": "Inspect primary experimental report",
            }
        )
    )


def test_rcsb_chain_inventory_keeps_entities_separate_and_preserves_sources(
    research: Any, monkeypatch: Any
) -> None:
    import json

    entry = {
        "rcsb_id": "1ABC",
        "rcsb_entry_container_identifiers": {"polymer_entity_ids": ["1", "2"]},
    }
    entities = {
        str(i): {
            "rcsb_id": f"1ABC_{i}",
            "rcsb_polymer_entity": {"pdbx_description": description},
            "rcsb_polymer_entity_container_identifiers": {
                "asym_ids": [label],
                "auth_asym_ids": [auth],
            },
            "entity_poly": {"pdbx_seq_one_letter_code_can": "A" * (100 + i)},
        }
        for i, description, label, auth in [
            (1, "Synthetic target", "C", "L"),
            (2, "Synthetic partner", "A", "H"),
        ]
    }
    responses = []

    def handler(request: Any) -> Any:
        body = (
            entry
            if "/entry/" in request.url.path
            else entities[request.url.path.rsplit("/", 1)[-1]]
        )
        response = httpx.Response(200, json=body)
        responses.append(response.content)
        return response

    monkeypatch.setattr(
        research,
        "client",
        lambda directory: ResearchHttpClient(
            evidence_dir=directory,
            max_attempts=1,
            client=httpx.Client(transport=httpx.MockTransport(handler)),
        ),
    )
    corpus = EvidenceCorpus(research.bridge)
    corpus.select(
        SelectEvidence(
            provider="RCSB",
            identifier="1ABC",
            need="PPI_INTERFACE",
            selection="SELECTED",
            reason="Inspect distinct synthetic partner chains",
        )
    )
    acquired = research.acquire(
        ResearchQuery(
            operation="structure-record",
            identifier="1ABC",
            topic="structure-complex",
            question="Inspect polymer chain inventory",
        ),
        role="target",
    )
    page = corpus.retrieve(
        RetrieveEvidence(
            need="PPI_INTERFACE",
            source_id="RCSB:1ABC",
            question="polymer entity identity chain inventory",
            page_size=3,
        )
    )
    # Ranked inventory passages are complete source objects, with no partner/target splice.
    facts = [json.loads(card["passage"]) for card in page["cards"]]
    assert len(facts) == 2
    assert {f["entity_id"]: (f["auth_asym_ids"], f["asym_ids"]) for f in facts} == {
        "1ABC_1": (["L"], ["C"]),
        "1ABC_2": (["H"], ["A"]),
    }
    assert all("mapping requires" in f["scope"] for f in facts)
    refs = acquired["cards"][0]["source_refs"]
    saved = [(research.bridge.project / ref["relative_path"]).read_bytes() for ref in refs]
    assert all(raw in saved for raw in responses)


def read_primary(worker: Any, identifier: str) -> dict[str, Any]:
    select(worker, identifier)
    worker.acquire(query(operation="primary-record", identifier=identifier), role="site")
    return EvidenceCorpus(worker.bridge).retrieve(
        RetrieveEvidence(
            need="FUNCTIONAL_MECHANISM",
            question="enzyme inhibition",
            source_id="EuropePMC:" + identifier,
        )
    )["cards"][0]


def test_not_searched_empty_search_and_network_failure_are_distinct(
    research: Any, monkeypatch: Any
) -> None:
    assert research.snapshot()["topics"]["function"] == "NOT_SEARCHED"
    calls = transport(research, monkeypatch)
    result = research.acquire(query(), role="site")
    assert result["status"] == "SEARCHED_NO_EVIDENCE" and not result["errors"]
    assert research.acquire(query(), role="target") == result and len(calls) == 1
    transport(research, monkeypatch, status=503)
    result = research.acquire(query("competition"), role="site")
    assert result["status"] == "UNRESOLVED" and result["errors"]
    with pytest.raises(AgentBoundaryError, match="source failure"):
        research.validate_conclusions(
            [
                ResearchConclusion(
                    topic="competition",
                    status="SEARCHED_NO_EVIDENCE",
                    limitations=["Service failed"],
                )
            ]
        )


def test_source_identity_passage_and_conflict_contract(research: Any, monkeypatch: Any) -> None:
    transport(
        research,
        monkeypatch,
        {
            "resultList": {
                "result": [
                    {
                        "id": "12345",
                        "source": "MED",
                        "title": "Synthetic primary record",
                        "doi": "10.test/synthetic",
                        "pubYear": "2020",
                        "pubTypeList": {"pubType": ["Journal Article"]},
                        "abstractText": (
                            "The synthetic antibody inhibited enzyme activity in a purified assay."
                        ),
                    }
                ]
            }
        },
    )
    result = research.acquire(query(), role="site")
    assert result["cards"][0]["primary_eligible"] is False
    card = read_primary(research, "12345")
    source_card = research.snapshot()["queries"][1]["cards"][0]
    assert card["source_verified"] and source_card["source_refs"]
    use = {
        "card_id": card["card_id"],
        "excerpt": "inhibited enzyme activity in a purified assay",
        "claim": "Inhibition was reported in this synthetic fixture",
        "relation": "supports",
        "strength": "E1",
        "transfer_limit": "Synthetic fixture, no claim about a real target",
    }
    conclusion = ResearchConclusion.model_validate(
        {
            "topic": "function",
            "status": "VERIFIED",
            "evidence": [use],
            "limitations": ["Only the reported assay"],
        }
    )
    assert research.validate_conclusions([conclusion])["source_refs"]
    with pytest.raises(AgentBoundaryError, match="retrieved passage"):
        research.validate_conclusions(
            [
                conclusion.model_copy(
                    update={
                        "evidence": [
                            conclusion.evidence[0].model_copy(
                                update={"excerpt": "did not inhibit activity"}
                            )
                        ]
                    }
                )
            ]
        )
    with pytest.raises(AgentBoundaryError, match="both supporting"):
        research.validate_conclusions(
            [conclusion.model_copy(update={"status": "CONFLICTING_EVIDENCE"})]
        )
    # One invalid submission can have independent ID, status and quotation errors.
    # Report them together within the same bounded correction, without accepting or
    # rewriting the opinion. The already-read original passage makes quote repair possible
    # even when discovery tools are no longer offered.
    invalid = conclusion.model_copy(
        update={
            "query_ids": ["truncated-query"],
            "status": "CONFLICTING_EVIDENCE",
            "evidence": [
                conclusion.evidence[0].model_copy(update={"excerpt": "did not inhibit activity"})
            ],
        }
    )
    unsupported = conclusion.model_copy(update={"evidence": []})
    before = [item.model_dump(mode="json") for item in [invalid, unsupported]]
    with pytest.raises(AgentBoundaryError) as rejected:
        research.validate_conclusions([invalid, unsupported])
    diagnostic = str(rejected.value)
    assert "Unknown evidence query IDs" in diagnostic
    assert "conclusion[0] (function): Conflict requires both supporting" in diagnostic
    assert "conclusion[1] (function): Scientific support/conflict requires" in diagnostic
    assert "CITATION_MISMATCH" in diagnostic
    assert card["passage"] in diagnostic
    assert result["query_id"] in diagnostic
    assert before == [item.model_dump(mode="json") for item in [invalid, unsupported]]
    # Integrity/foreign identity errors still fail immediately, rather than being
    # converted into an ordinary correctable opinion problem.
    foreign = invalid.model_copy(
        update={"evidence": [invalid.evidence[0].model_copy(update={"card_id": "foreign-passage"})]}
    )
    with pytest.raises(AgentBoundaryError, match="not retrieved in this thread"):
        research.validate_conclusions([foreign, unsupported])
    # Persisted query snapshots do not excuse tampering with original source artifacts.
    path = research.bridge.project / source_card["source_refs"][0]["relative_path"]
    path.write_text("tampered")
    with pytest.raises(ArtifactIntegrityError):
        research.snapshot()


def test_wrong_pmid_and_review_never_become_primary_evidence(
    research: Any, monkeypatch: Any
) -> None:
    transport(research, monkeypatch, {"resultList": {"result": [{"id": "999", "source": "MED"}]}})
    select(research, "12345")
    result = research.acquire(query(operation="primary-record", identifier="12345"), role="target")
    assert result["status"] == "UNRESOLVED" and "identity mismatch" in result["errors"][0]
    transport(
        research,
        monkeypatch,
        {
            "resultList": {
                "result": [
                    {
                        "id": "55",
                        "source": "MED",
                        "pubTypeList": {"pubType": ["Review"]},
                        "abstractText": (
                            "A synthetic review discusses enzyme inhibition mechanisms."
                        ),
                    }
                ]
            }
        },
    )
    review = research.acquire(query(query="different review search"), role="site")["cards"][0]
    assert review["primary_eligible"] is False
    conclusion = ResearchConclusion.model_validate(
        {
            "topic": "function",
            "status": "VERIFIED",
            "limitations": ["Review is a discovery lead"],
            "evidence": [
                {
                    "card_id": review["card_id"],
                    "excerpt": "discusses enzyme inhibition mechanisms",
                    "claim": "Synthetic review claim",
                    "relation": "supports",
                    "strength": "E1",
                    "transfer_limit": "Unverified transfer",
                }
            ],
        }
    )
    with pytest.raises(AgentBoundaryError, match="discovery lead/review"):
        research.validate_conclusions([conclusion])
    with pytest.raises(AgentBoundaryError, match="Only Target or Site"):
        research.acquire(query(), role="coordinator")
    with pytest.raises(ValueError):
        query(operation="primary-fulltext", identifier="https://evil.example")


def test_request_ceiling_is_per_execution_and_resume_does_not_reset_it(
    research: Any, monkeypatch: Any
) -> None:
    calls = transport(research, monkeypatch)
    for n in range(12):
        research.acquire(query(query=f"synthetic query {n}"), role="site")
    with pytest.raises(AgentBoundaryError, match="12 bounded"):
        research.acquire(query(query="one too many"), role="site")
    research.bridge.store.begin_execution(research.bridge.thread, "Follow up", followup=True)
    research.acquire(query(query="one too many"), role="site")
    assert len(calls) == 13


def test_material_not_searched_question_requires_acquisition(research: Any) -> None:
    with pytest.raises(AgentBoundaryError, match="NOT_SEARCHED"):
        research.validate_conclusions(
            [
                ResearchConclusion(
                    topic="epitope", status="UNRESOLVED", limitations=["Not yet searched"]
                )
            ]
        )


def test_literature_candidate_alone_remains_visible_and_bound_to_judge(
    site_bridge: Any, monkeypatch: Any
) -> None:
    from tests.unit.agent.test_site_runtime import propose, site_intent

    site_bridge.store.begin_execution(site_bridge.thread, "Explore literature and structure")
    worker = EvidenceResearch(site_bridge)
    transport(
        worker,
        monkeypatch,
        {
            "resultList": {
                "result": [
                    {
                        "id": "123",
                        "source": "MED",
                        "abstractText": "Synthetic mapped surface patch evidence.",
                    }
                ]
            }
        },
    )
    source = worker.acquire(query(topic="epitope"), role="site")["cards"][0]
    intent = site_intent()
    intent = intent.model_copy(
        update={
            "selected_site": intent.selected_site.model_copy(
                update={"origin": "literature-derived", "evidence_card_ids": [source["card_id"]]}
            )
        }
    )
    propose(site_bridge, intent)
    evidence = site_bridge.judge_evidence()
    assert evidence["research_evidence"]["source_cards"][0]["card_id"] == source["card_id"]
    (site_bridge.project / source["source_refs"][0]["relative_path"]).write_text("tampered")
    with pytest.raises(ArtifactIntegrityError):
        site_bridge.judge_evidence()


@pytest.mark.parametrize("id_type", ["pmc", "pmcid"])
@pytest.mark.parametrize(
    "article_type,eligible", [("research-article", True), ("review-article", False)]
)
def test_fulltext_binds_enclosing_article_not_citations(
    research: Any, monkeypatch: Any, id_type: str, article_type: str, eligible: bool
) -> None:
    def handler(request: Any) -> Any:
        return httpx.Response(
            200,
            content=(
                f'<article article-type="{article_type}"><front><article-meta>'
                f'<article-id pub-id-type="{id_type}">PMC123</article-id>'
                "</article-meta></front><body><p>"
                "Measured inhibition in a purified enzyme assay.</p>"
                '</body><back><article-id pub-id-type="pmcid">PMC999</article-id></back></article>'
            ).encode(),
        )

    monkeypatch.setattr(
        research,
        "client",
        lambda directory: ResearchHttpClient(
            evidence_dir=directory,
            cache_root=research.bridge.project / "http-cache",
            max_attempts=1,
            client=httpx.Client(transport=httpx.MockTransport(handler)),
        ),
    )
    select(research, "PMC123")
    result = research.acquire(query(operation="primary-fulltext", identifier="PMC123"), role="site")
    assert not result["errors"]
    assert result["cards"][0]["primary_eligible"] is eligible
    assert "Measured inhibition" in result["cards"][0]["passage"]
    select(research, "PMC999")
    wrong = research.acquire(query(operation="primary-fulltext", identifier="PMC999"), role="site")
    assert wrong["status"] == "UNRESOLVED" and "identity mismatch" in wrong["errors"][0]


@pytest.mark.asyncio
async def test_explicit_query_binding_reuses_cross_topic_evidence_without_taxonomy_search(
    research: Any,
    monkeypatch: Any,
) -> None:
    import json

    from easydesign.agent.evidence_research import research_tool

    calls = transport(research, monkeypatch)
    # The tool constructs a fresh worker; give it the same synthetic transport.
    monkeypatch.setattr(
        EvidenceResearch, "client", lambda _self, directory: research.client(directory)
    )
    tool = research_tool(research.bridge, "site")
    result = json.loads(await tool.ainvoke(query().model_dump(mode="json")))
    assert result["query_id"] == research.snapshot()["queries"][0]["query_id"]
    conclusion = ResearchConclusion(
        topic="epitope",
        query_ids=[result["query_id"]],
        status="UNRESOLVED",
        limitations=[
            "SYNTHETIC functional search informs epitope uncertainty; the answer stays unresolved."
        ],
    )
    verified = research.validate_conclusions([conclusion])
    assert len(calls) == 1
    assert verified["source_snapshot"]["topics"]["epitope"] == "NOT_SEARCHED"
    assert verified["conclusions"][0]["query_ids"] == [result["query_id"]]
    with pytest.raises(AgentBoundaryError, match="Unknown evidence query"):
        research.validate_conclusions(
            [conclusion.model_copy(update={"query_ids": ["foreign-query"]})]
        )
    with pytest.raises(AgentBoundaryError, match="NOT_SEARCHED"):
        research.validate_conclusions([conclusion.model_copy(update={"query_ids": []})])


def test_acquisition_is_not_an_empty_search_and_failed_search_can_remain_unresolved(
    research: Any,
    monkeypatch: Any,
) -> None:
    calls = transport(research, monkeypatch)
    select(research, "12345")
    acquisition = research.acquire(
        query(operation="primary-record", identifier="12345"), role="site"
    )
    c = ResearchConclusion(
        topic="function",
        status="SEARCHED_NO_EVIDENCE",
        query_ids=[acquisition["query_id"]],
        limitations=["SYNTHETIC acquisition only."],
    )
    with pytest.raises(AgentBoundaryError, match="not SEARCHED_NO_EVIDENCE"):
        research.validate_conclusions([c])
    transport(research, monkeypatch, status=503)
    failed = research.acquire(query(query="synthetic opposing evidence"), role="site")
    c = c.model_copy(update={"query_ids": [failed["query_id"]], "status": "UNRESOLVED"})
    result = research.validate_conclusions([c])
    assert result["conclusions"][0]["status"] == "UNRESOLVED"
    assert len(calls) == 1
