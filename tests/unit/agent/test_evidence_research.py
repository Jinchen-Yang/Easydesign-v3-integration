"""Synthetic source responses exercise real transport/cache/artifact and opinion boundaries."""

from types import SimpleNamespace
from typing import Any

import httpx
import pytest

from easydesign.agent.contracts import AgentBoundaryError
from easydesign.agent.evidence_corpus import EvidenceCorpus, RetrieveEvidence, SelectEvidence
from easydesign.agent.evidence_research import (
    EvidenceResearch,
    ResearchAssessment,
    ResearchHttpClient,
    ResearchQuery,
    _pdb_complex_interface_view,
    _pdb_interface_sections,
)
from easydesign.agent.phase2 import Phase2Bridge
from easydesign.agent.session_store import SessionStore
from easydesign.core import ArtifactIntegrityError, BackendContractError


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


def test_pdb_complex_interface_projects_target_partner_contact_residues(tmp_path: Any) -> None:
    structure = tmp_path / "complex.pdb"
    structure.write_text(
        "\n".join(
            [
                "ATOM      1  N   ALA A  10       0.000   0.000   0.000  1.00 20.00           N",
                "ATOM      2  CA  ALA A  10       1.000   0.000   0.000  1.00 20.00           C",
                "ATOM      3  N   SER A  11       0.000   2.000   0.000  1.00 20.00           N",
                "ATOM      4  CA  SER A  11       1.000   2.000   0.000  1.00 20.00           C",
                "ATOM      5  N   GLY B  20       3.000   0.000   0.000  1.00 20.00           N",
                "ATOM      6  CA  GLY B  20       4.000   0.000   0.000  1.00 20.00           C",
                "ATOM      7  N   TYR B  21       3.000   2.000   0.000  1.00 20.00           N",
                "ATOM      8  CA  TYR B  21       4.000   2.000   0.000  1.00 20.00           C",
                "TER",
                "END",
            ]
        )
        + "\n"
    )
    polymers = [
        {
            "rcsb_id": "1ABC_1",
            "rcsb_polymer_entity": {"pdbx_description": "Synthetic target"},
            "rcsb_polymer_entity_container_identifiers": {
                "auth_asym_ids": ["A"],
                "reference_sequence_identifiers": [
                    {"database_name": "UniProt", "database_accession": "QTARGET-2"}
                ],
            },
        },
        {
            "rcsb_id": "1ABC_2",
            "rcsb_polymer_entity": {"pdbx_description": "Synthetic partner"},
            "rcsb_polymer_entity_container_identifiers": {
                "auth_asym_ids": ["B"],
                "reference_sequence_identifiers": [
                    {"database_name": "UniProt", "database_accession": "QPARTNER"}
                ],
            },
        },
    ]

    analysis = _pdb_complex_interface_view(
        structure,
        pdb_id="1ABC",
        polymers=polymers,
        approved_accession="QTARGET",
    )

    assert analysis["status"] == "observed"
    assert analysis["target_chains"] == ["A"]
    interface = analysis["interfaces"][0]
    assert interface["partner_chain"] == "B"
    assert interface["partner_description"] == "Synthetic partner"
    assert interface["geometry_observed"] is True
    assert [r["auth_seq_id"] for r in interface["target_contact_residues"]] == [10, 11]
    assert [r["auth_seq_id"] for r in interface["partner_contact_residues"]] == [20, 21]
    assert "does not establish" in interface["scope"]
    sections = _pdb_interface_sections(analysis)
    assert any("target-partner interface" in section["location"] for section in sections)
    assert any('"auth_seq_id":10' in section["text"] for section in sections)


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


def test_gpcrdb_missing_entry_falls_back_to_approved_canonical_accession(
    research: Any, monkeypatch: Any
) -> None:
    from easydesign.agent import evidence_research as module

    calls = []
    monkeypatch.setattr(
        research.bridge,
        "site_facts",
        lambda: (
            {"evidence": {"hard_facts": {"canonical_accession": "P21452"}}},
            {},
            {},
        ),
        raising=False,
    )

    class Context:
        status = "resolved"

        @staticmethod
        def legacy_projection() -> dict[str, Any]:
            return {
                "identity": {
                    "status": "resolved",
                    "entry_name": "nk2r_human",
                    "accession": "P21452",
                },
                "topology": {},
            }

    class Adapter:
        def __init__(self, client: Any) -> None:
            pass

        def fetch_receptor_context(self, **kwargs: Any) -> Any:
            calls.append(kwargs)
            if kwargs.get("entry"):
                raise BackendContractError("remote request failed: status=404, body=not found")
            assert kwargs["accession"] == "P21452"
            return Context()

    monkeypatch.setattr(module, "GpcrdbAdapter", Adapter)
    card = research.retrieve(
        SimpleNamespace(),
        ResearchQuery(
            topic="state",
            question="Resolve receptor topology",
            operation="gpcrdb-context",
            identifier="TACR2_HUMAN",
        ),
    )[0]

    assert calls == [
        {"entry": "TACR2_HUMAN", "pdb_code": None},
        {"accession": "P21452", "pdb_code": None},
    ]
    assert card["identifier"] == "TACR2_HUMAN"
    assert card["resolved_identifier"] == "nk2r_human"
    assert card["identifier_resolution"] == {
        "requested_identifier": "TACR2_HUMAN",
        "method": "approved-accession-after-entry-404",
        "approved_accession_fallback": "P21452",
    }


def test_site_runtime_selects_approved_gpcr_context_without_model_reason(
    research: Any, monkeypatch: Any
) -> None:
    monkeypatch.setattr(
        research.bridge,
        "site_facts",
        lambda: (
            {"evidence": {"hard_facts": {"canonical_accession": "P21452"}}},
            {},
            {},
        ),
        raising=False,
    )
    monkeypatch.setattr(
        research,
        "retrieve",
        lambda _client, _query: [
            {
                "provider": "GPCRdb",
                "identifier": "nk2r_human",
                "primary_eligible": True,
                "evidence_level": "curated-receptor-context",
                "passage": '{"identity":{"accession":"P21452"}}',
                "_sections": [],
                "truncated": False,
                "status": "resolved",
            }
        ],
    )
    result = research.acquire(
        ResearchQuery(
            topic="state",
            question="Resolve the approved receptor topology",
            operation="gpcrdb-context",
            identifier="nk2r_human",
            pdb_id="9W2H",
        ),
        role="site",
    )

    assert result["cards"][0]["provider"] == "GPCRdb"
    selection = next(
        event["payload"]
        for event in reversed(research.bridge.store.events(research.bridge.thread))
        if event["kind"] == "evidence-selection"
    )
    assert selection["source_id"] == "GPCRdb:NK2R_HUMAN"
    assert "Runtime-required deterministic GPCR context" in selection["reason"]


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
        research.validate_questions(
            [
                ResearchAssessment(
                    query_ids=[result["query_id"]],
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
    conclusion = ResearchAssessment.model_validate(
        {
            "query_ids": [q["query_id"] for q in research.snapshot()["queries"]],
            "status": "VERIFIED",
            "evidence": [use],
            "limitations": ["Only the reported assay"],
        }
    )
    assert research.validate_questions([conclusion])["source_refs"]
    with pytest.raises(AgentBoundaryError, match="retrieved passage"):
        research.validate_questions(
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
        research.validate_questions(
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
        research.validate_questions([invalid, unsupported])
    diagnostic = str(rejected.value)
    assert "Unknown evidence query IDs" in diagnostic
    assert "question[0]: Conflict requires both supporting" in diagnostic
    assert "question[1]: Scientific support/conflict requires" in diagnostic
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
        research.validate_questions([foreign, unsupported])
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
    conclusion = ResearchAssessment.model_validate(
        {
            "query_ids": [q["query_id"] for q in research.snapshot()["queries"]],
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
        research.validate_questions([conclusion])
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
        research.validate_questions(
            [
                ResearchAssessment(
                    query_ids=["unissued-query"],
                    status="UNRESOLVED",
                    limitations=["Not yet searched"],
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
    conclusion = ResearchAssessment(
        query_ids=[result["query_id"]],
        status="UNRESOLVED",
        limitations=[
            "SYNTHETIC functional search informs epitope uncertainty; the answer stays unresolved."
        ],
    )
    verified = research.validate_questions([conclusion])
    assert len(calls) == 1
    assert verified["source_snapshot"]["topics"]["epitope"] == "NOT_SEARCHED"
    assert verified["source_snapshot"]["queries"][0]["query_id"] == result["query_id"]
    assert "conclusions" not in verified
    with pytest.raises(AgentBoundaryError, match="Unknown evidence query"):
        research.validate_questions(
            [conclusion.model_copy(update={"query_ids": ["foreign-query"]})]
        )
    with pytest.raises(AgentBoundaryError, match="NOT_SEARCHED"):
        research.validate_questions([conclusion.model_copy(update={"query_ids": []})])


@pytest.mark.asyncio
async def test_site_gpcr_context_atomically_runs_deterministic_receptor_analysis(
    research: Any, monkeypatch: Any
) -> None:
    import json

    from easydesign.agent.evidence_research import research_tool

    context_ref = {"artifact_id": "gpcrdb-context", "sha256": "a" * 64}
    source_ref = {"artifact_id": "gpcrdb-source", "sha256": "b" * 64}
    captured = []

    monkeypatch.setattr(
        research.bridge,
        "site_facts",
        lambda: (
            {"evidence": {"hard_facts": {"selected_chain": "R"}}},
            {},
            {"artifact_id": "site-facts", "sha256": "c" * 64},
        ),
        raising=False,
    )
    monkeypatch.setattr(
        EvidenceResearch,
        "acquire",
        lambda self, query, *, role: {
            "query_id": "gpcrdb-query",
            "status": "UNRESOLVED",
            "topic": "structure-complex",
            "cards": [
                {
                    "card_id": "gpcrdb-nk2r",
                    "provider": "GPCRdb",
                    "identifier": "nk2r_human",
                    "context_ref": context_ref,
                    "source_refs": [source_ref],
                }
            ],
            "errors": [],
        },
    )
    monkeypatch.setattr(
        EvidenceResearch,
        "snapshot",
        lambda self, **_kwargs: {
            "queries": [
                {
                    "cards": [
                        {
                            "card_id": "gpcrdb-nk2r",
                            "provider": "GPCRdb",
                            "identifier": "nk2r_human",
                            "context_ref": context_ref,
                            "source_refs": [source_ref],
                        }
                    ]
                }
            ]
        },
    )

    def analyze(self: Any, request: Any) -> dict[str, Any]:
        captured.append(request)
        return {
            "card_id": "receptor-nk2r",
            "analysis_ref": {"artifact_id": "receptor-analysis", "sha256": "d" * 64},
        }

    monkeypatch.setattr(EvidenceResearch, "analyze_receptor", analyze)
    result = json.loads(
        await research_tool(research.bridge, "site").ainvoke(
            {
                "topic": "structure-complex",
                "question": "Resolve the approved receptor context",
                "operation": "gpcrdb-context",
                "identifier": "nk2r_human",
                "pdb_id": "9W2H",
                "selection_reason": "Obtain deterministic receptor topology and candidates",
            }
        )
    )

    assert len(captured) == 1
    assert captured[0].gpcrdb_card_id == "gpcrdb-nk2r"
    assert captured[0].auth_chain == "R"
    assert result["automatic_receptor_analysis"]["card_id"] == "receptor-nk2r"
    assert result["automatic_receptor_analysis"]["reused"] is False
    assert "approval" in result["automatic_receptor_analysis"]["authority"]


def test_acquisition_is_not_an_empty_search_and_failed_search_can_remain_unresolved(
    research: Any,
    monkeypatch: Any,
) -> None:
    calls = transport(research, monkeypatch)
    select(research, "12345")
    acquisition = research.acquire(
        query(operation="primary-record", identifier="12345"), role="site"
    )
    c = ResearchAssessment(
        status="SEARCHED_NO_EVIDENCE",
        query_ids=[acquisition["query_id"]],
        limitations=["SYNTHETIC acquisition only."],
    )
    with pytest.raises(AgentBoundaryError, match="not SEARCHED_NO_EVIDENCE"):
        research.validate_questions([c])
    transport(research, monkeypatch, status=503)
    failed = research.acquire(query(query="synthetic opposing evidence"), role="site")
    c = c.model_copy(update={"query_ids": [failed["query_id"]], "status": "UNRESOLVED"})
    result = research.validate_questions([c])
    assert any(
        q["query_id"] == failed["query_id"] and q["errors"]
        for q in result["source_snapshot"]["queries"]
    )
    assert c.status == "UNRESOLVED" and "conclusions" not in result
    assert len(calls) == 1
