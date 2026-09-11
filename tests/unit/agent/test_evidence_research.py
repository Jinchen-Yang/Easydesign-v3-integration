"""Synthetic source responses exercise real transport/cache/artifact and opinion boundaries."""

from types import SimpleNamespace
from typing import Any

import httpx
import pytest

from easydesign.agent.contracts import AgentBoundaryError
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
    card = result["cards"][0]
    assert card["source_verified"] and card["source_refs"]
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
    # Persisted query snapshots do not excuse tampering with original source artifacts.
    path = research.bridge.project / card["source_refs"][0]["relative_path"]
    path.write_text("tampered")
    with pytest.raises(ArtifactIntegrityError):
        research.snapshot()


def test_wrong_pmid_and_review_never_become_primary_evidence(
    research: Any, monkeypatch: Any
) -> None:
    transport(research, monkeypatch, {"resultList": {"result": [{"id": "999", "source": "MED"}]}})
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
    result = research.acquire(query(operation="primary-fulltext", identifier="PMC123"), role="site")
    assert not result["errors"]
    assert result["cards"][0]["primary_eligible"] is eligible
    assert "Measured inhibition" in result["cards"][0]["passage"]
    wrong = research.acquire(query(operation="primary-fulltext", identifier="PMC999"), role="site")
    assert wrong["status"] == "UNRESOLVED" and "identity mismatch" in wrong["errors"][0]
