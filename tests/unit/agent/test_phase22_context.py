"""Working evidence is bounded; durable sources and independent views are retained."""

# ruff: noqa: F811
import json
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from langchain_core.messages import ToolMessage

from easydesign.agent.contracts import (
    AgentBoundaryError,
    EvidenceCursorQueryMismatch,
    SourceSelectionRequired,
)
from easydesign.agent.evidence_corpus import EvidenceCorpus, RetrieveEvidence, SelectEvidence
from easydesign.agent.evidence_output import output_message, result_tool
from easydesign.agent.evidence_research import EvidenceResearch, ResearchHttpClient
from easydesign.agent.phase2 import Phase2Bridge
from easydesign.core import ArtifactIntegrityError
from tests.unit.agent.test_evidence_research import query, research, select  # noqa: F401


def test_source_selection_full_retention_scoped_pagination_and_thread_isolation(
    research: Any,
    monkeypatch: Any,  # noqa: F811
) -> None:
    paragraphs = "".join(
        f"<sec><title>Experiment {n}</title><p>Mutation Y185A assay {n} "
        + ("control response " * 150)
        + "</p></sec>"
        for n in range(30)
    )
    raw = (
        '<article article-type="research-article"><front><article-meta>'
        '<article-id pub-id-type="pmcid">PMC123</article-id></article-meta></front><body>'
        + paragraphs
        + "</body></article>"
    ).encode()
    calls = []

    def response(request: Any) -> Any:
        calls.append(request)
        return httpx.Response(200, content=raw)

    monkeypatch.setattr(
        research,
        "client",
        lambda directory: ResearchHttpClient(
            evidence_dir=directory,
            cache_root=research.bridge.project / "cache",
            max_attempts=1,
            client=httpx.Client(transport=httpx.MockTransport(response)),
        ),
    )
    request = query(operation="primary-fulltext", identifier="PMC123")
    with pytest.raises(SourceSelectionRequired, match="Select this source"):
        research.acquire(request, role="site")
    select(research, "PMC123")
    source = research.acquire(request, role="site")["cards"][0]
    assert (research.bridge.project / source["source_refs"][0]["relative_path"]).read_bytes() == raw
    assert source["chunk_count"] > 30
    corpus = EvidenceCorpus(research.bridge)
    q = RetrieveEvidence(
        need="FUNCTIONAL_MECHANISM", question="Y185A assay", source_id="EuropePMC:PMC123"
    )
    first = corpus.retrieve(q)
    assert 0 < len(first["cards"]) <= q.page_size and first["next_cursor"]
    assert len(json.dumps(first)) < 6500
    assert first["cards"][0]["location"].startswith("body/Experiment")
    second = corpus.retrieve(q.model_copy(update={"cursor": first["next_cursor"]}))
    assert first["cards"][0]["card_id"] != second["cards"][0]["card_id"]
    assert len(calls) == 1
    with pytest.raises(EvidenceCursorQueryMismatch, match="exact question"):
        corpus.retrieve(
            q.model_copy(update={"question": "another question", "cursor": first["next_cursor"]})
        )
    b = SimpleNamespace(**vars(research.bridge))
    b.thread = "thread-b"
    b.persist = lambda kind, payload: Phase2Bridge.persist(b, kind, payload)
    b.document = lambda ref: Phase2Bridge.document(b, ref)
    other = EvidenceCorpus(b)
    assert other.documents()
    with pytest.raises(SourceSelectionRequired):
        other.retrieve(q)
    other.select(
        SelectEvidence(
            provider="EuropePMC",
            identifier="PMC123",
            need="FUNCTIONAL_MECHANISM",
            selection="SELECTED",
            reason="Independent current question",
        )
    )
    assert other.retrieve(q)["cards"]
    assert not EvidenceResearch(b).snapshot()["queries"][0].get("query")
    with pytest.raises(AgentBoundaryError):
        other.retrieve(q.model_copy(update={"cursor": first["next_cursor"]}))
    research.bridge.store.begin_execution(
        research.bridge.thread, "Follow-up question", followup=True
    )
    again = corpus.retrieve(q)
    assert again["cards"] == first["cards"] and len(calls) == 1
    assert len(corpus.documents()) == 1


@pytest.mark.asyncio
async def test_output_offload_has_role_bound_scoped_read_and_verifies_bytes(bridge: Any) -> None:
    execution = bridge.store.begin_execution(bridge.thread, "Inspect selected evidence")
    value = {
        "proposal": {"fallback_used": False},
        "rows": [{"residue": n, "measurement": "a" * 200} for n in range(50)],
    }
    rendered = output_message(
        bridge,
        "site",
        execution["execution_id"],
        ToolMessage(
            content=json.dumps(value), tool_call_id="source-tool", name="read_site_evidence"
        ),
    )
    view = json.loads(rendered.content)
    assert len(rendered.content) < 6000 and view["proposal"]["fallback_used"] is False
    full = bridge.store.root / "agent-work" / bridge.thread / view["full_result"][1:]
    assert json.loads(full.read_text()) == value
    result = json.loads(
        await result_tool(bridge, "site").ainvoke(
            {"ref": view["full_result"], "field": ["rows"], "offset": 45, "limit": 5}
        )
    )
    assert result["value"][0]["residue"] == 45 and result["next_offset"] is None
    with pytest.raises(AgentBoundaryError, match="not supplied"):
        await result_tool(bridge, "judge").ainvoke({"ref": view["full_result"], "field": ["rows"]})
    full.write_text("{}")
    with pytest.raises(ArtifactIntegrityError):
        await result_tool(bridge, "site").ainvoke({"ref": view["full_result"], "field": ["rows"]})


@pytest.mark.asyncio
async def test_judge_projection_retains_counterevidence_and_exact_delegation(bridge: Any) -> None:
    from easydesign.agent.contracts import EvidenceBinding
    from easydesign.agent.tools import JUDGE_EVIDENCE

    execution = bridge.store.begin_execution(bridge.thread, "Assess a scoped proposal")
    binding = EvidenceBinding(evidence_id="proposal-one", evidence_refs=("frozen-source",))
    value = {
        "proposal": {"claim": "Mutation supports the mechanism"},
        "supporting_evidence": [{"claim": "support", "passage": "s" * 900}],
        "contradictory_evidence": [
            {"claim": "counterevidence", "passage": str(i) + "c" * 900} for i in range(5)
        ],
        "limitations": ["Fallback was not used", "Approval lineage is not in this snapshot"],
        "provenance": {"fallback_used": False},
        "evidence_refs": ["frozen-source"],
    }
    token = JUDGE_EVIDENCE.set(binding)
    try:
        message = output_message(
            bridge,
            "judge",
            execution["execution_id"],
            ToolMessage(
                content=json.dumps(value),
                name="read_scientific_evidence",
                tool_call_id="judge-view",
            ),
        )
        view = json.loads(message.content)
        assert view["contradictory_evidence"] == value["contradictory_evidence"]
        assert view["supporting_evidence"] == value["supporting_evidence"]
        assert view["limitations"] == value["limitations"]
        assert view["provenance"]["fallback_used"] is False
        assert "evidence_refs" not in view
        original = json.loads(
            await result_tool(bridge, "judge").ainvoke(
                {"ref": view["full_result"], "field": ["contradictory_evidence"], "limit": 5}
            )
        )
        remainder = json.loads(
            await result_tool(bridge, "judge").ainvoke(
                {
                    "ref": view["full_result"],
                    "field": ["contradictory_evidence"],
                    "offset": original["next_offset"],
                    "limit": 5,
                }
            )
        )
        assert original["value"] + remainder["value"] == value["contradictory_evidence"]
        assert remainder["next_offset"] is None
        JUDGE_EVIDENCE.set(binding.model_copy(update={"evidence_id": "proposal-two"}))
        with pytest.raises(AgentBoundaryError, match="another delegated"):
            await result_tool(bridge, "judge").ainvoke(
                {"ref": view["full_result"], "field": ["supporting_evidence"]}
            )
    finally:
        JUDGE_EVIDENCE.reset(token)


def test_oversized_judge_snapshot_cannot_hide_counterevidence(bridge: Any) -> None:
    execution = bridge.store.begin_execution(bridge.thread, "Challenge evidence")
    value = {"contradictory_evidence": [{"passage": "counterevidence " * 4000}]}
    with pytest.raises(AgentBoundaryError, match="must not be silently truncated"):
        output_message(
            bridge,
            "judge",
            execution["execution_id"],
            ToolMessage(
                content=json.dumps(value),
                name="read_scientific_evidence",
                tool_call_id="large-judge",
            ),
        )


@pytest.mark.asyncio
async def test_scoped_pages_are_not_truncated_again_after_cursor_advance(bridge: Any) -> None:
    execution = bridge.store.begin_execution(bridge.thread, "Read selected passages")
    value = {"rows": [{"text": str(n) + "x" * 900} for n in range(8)], "text": "z" * 5000}
    source = output_message(
        bridge,
        "site",
        execution["execution_id"],
        ToolMessage(content=json.dumps(value), tool_call_id="source", name="read_site_evidence"),
    )
    ref = json.loads(source.content)["full_result"]
    read = result_tool(bridge, "site")
    raw = await read.ainvoke({"ref": ref, "field": ["rows"], "limit": 8})
    rendered = output_message(
        bridge,
        "site",
        execution["execution_id"],
        ToolMessage(content=raw, tool_call_id="page", name="read_evidence_result"),
    )
    page = json.loads(rendered.content)
    assert 0 < len(page["value"]) < 8
    assert page["value"] == value["rows"][: page["next_offset"]]
    following = json.loads(
        await read.ainvoke(
            {"ref": ref, "field": ["rows"], "offset": page["next_offset"], "limit": 8}
        )
    )
    assert following["value"][0] == value["rows"][page["next_offset"]]
    raw = await read.ainvoke({"ref": ref, "field": ["text"]})
    rendered = output_message(
        bridge,
        "site",
        execution["execution_id"],
        ToolMessage(content=raw, tool_call_id="text", name="read_evidence_result"),
    )
    page = json.loads(rendered.content)
    assert page["value"] == "z" * 3000 and page["next_offset"] == 3000


@pytest.mark.parametrize("name", ["retrieve_evidence", "continue_evidence"])
def test_every_source_page_preserves_full_passage_and_feature_inventory(
    bridge: Any, name: str
) -> None:
    execution = bridge.store.begin_execution(bridge.thread, "Read exact source evidence")
    passage = "Synthetic primary passage. " * 32 + "Counterevidence: function was not tested."
    value = {
        "cards": [
            {
                "card_id": "passage-1",
                "source_id": "UniProt:TEST",
                "passage": passage,
                "limitations": [
                    "unverified binding",
                    "no assay",
                    "no efficacy",
                    "conditional mapping",
                ],
            }
        ],
        "feature_scope": {
            "UniProt:TEST": {
                "available_types": [
                    "Beta strand",
                    "Binding site",
                    "Topological domain",
                    "Transmembrane",
                    "Glycosylation",
                ]
            }
        },
        "next_cursor": "opaque-issued-cursor",
        "matching_chunks": 8,
        "question": "Read the scoped source and its counterevidence. " * 12,
    }
    rendered = output_message(
        bridge,
        "site",
        execution["execution_id"],
        ToolMessage(content=json.dumps(value), tool_call_id="read-source", name=name),
    )
    result = json.loads(rendered.content)
    assert len(rendered.content) < 6000
    assert result["cards"] == value["cards"]
    assert result["feature_scope"] == value["feature_scope"]
    assert result["scientific_content_complete"] is True
    assert result["next_cursor"] == value["next_cursor"]
    full = bridge.store.root / "agent-work" / bridge.thread / result["full_result"][1:]
    assert json.loads(full.read_text()) == value
