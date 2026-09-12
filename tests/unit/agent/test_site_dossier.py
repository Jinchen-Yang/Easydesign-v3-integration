"""Dossier authority and framework memory tests; all evidence here is synthetic."""

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from deepagents.backends import FilesystemBackend
from langchain.agents.middleware.types import ModelRequest, ModelResponse
from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from easydesign.agent.context_policy import context_usage, research_memory
from easydesign.agent.contracts import AgentBoundaryError, EvidenceBinding
from easydesign.agent.phase2 import SITE_EVIDENCE
from easydesign.agent.session_store import identity
from easydesign.agent.site_contracts import SiteQuery
from easydesign.agent.site_dossier import (
    DecisionEvidenceQuestion,
    SiteResearchHandoff,
    persist_dossier,
    site_dossier,
    validate_dossier_intent,
)
from easydesign.core import ArtifactIntegrityError
from tests.agent_support import scripted_config


def handoff() -> SiteResearchHandoff:
    return SiteResearchHandoff(
        candidates=[
            {
                "name": "Synthetic structural candidate",
                "hotspot_label_seq_ids": [1, 2, 3],
                "rationale": "Test the scientific boundary, not biological efficacy.",
            }
        ],
        stopping_reason="SYNTHETIC structural exploration only; no functional claim.",
        unresolved_questions=["No actual binding or functional experiment was performed."],
    )


def decision_scope(
    bridge: Any, selection: SiteResearchHandoff, topic: str, query_id: str
) -> SiteResearchHandoff:
    search = {
        "query_id": "synthetic-contradiction-search",
        "topic": topic,
        "question": "SYNTHETIC could a competing mechanism invalidate the current ranking?",
        "query": {"operation": "literature-search", "query": "synthetic alternative mechanism"},
        "status": "SEARCHED_NO_EVIDENCE",
        "cards": [],
        "errors": [],
    }
    ref = bridge.persist("evidence-research", search)
    bridge.store.event(
        bridge.thread,
        "evidence-research",
        {"target_binding": identity(bridge.binding()), "ref": ref},
    )
    question = DecisionEvidenceQuestion.model_validate(
        {
            "topic": topic,
            "query_ids": list(dict.fromkeys([query_id, search["query_id"]])),
            "question": "SYNTHETIC does the available evidence distinguish candidate mechanisms?",
            "status": "UNRESOLVED",
            "evidence": [],
            "limitations": ["SYNTHETIC bounded evidence does not establish biological efficacy."],
            "decision_impact": "SYNTHETIC ranking provisional; no need for more topics.",
        }
    )
    return selection.model_copy(
        update={
            "decision_questions": [question],
            "contradiction_search_query_ids": [search["query_id"]],
            "stopping_reason": "SYNTHETIC check done; function remains unresolved.",
        }
    )


def bind(bridge: Any) -> Any:
    evidence = bridge.read_site_evidence()
    return SITE_EVIDENCE.set(
        EvidenceBinding.model_validate({key: evidence[key] for key in EvidenceBinding.model_fields})
    )


def test_dossier_keeps_opposing_passages_failures_and_original_bytes(site_bridge: Any) -> None:
    b = site_bridge
    source = b.persist("synthetic-source", {"text": "Synthetic source, no scientific acceptance"})
    cards = [
        {
            "card_id": "passage-" + name,
            "provider": "Europe PMC",
            "identifier": name,
            "passage": text,
            "source_refs": [source],
            "source_verified": True,
            "selection_provenance": {"reason": "SYNTHETIC control metadata"},
            "binding_context": {
                "acquired_binding": "SYNTHETIC hash",
                "relation": "current-state-selection",
                "relevance": "unresolved",
            },
            "partial": True,
            "limitations": ["Abstract only; no quantitative efficacy data."],
            "evidence_level": "primary-abstract",
            "primary_eligible": True,
            "does_not_support": ["Binding efficacy or exact epitope"],
        }
        for name, text in [
            ("support", "Synthetic positive evidence for hypothesis A."),
            ("opposition", "Synthetic evidence contradicting hypothesis A."),
        ]
    ]
    query = {
        "query_id": "synthetic-query",
        "topic": "function",
        "status": "UNRESOLVED",
        "question": "Synthetic assay evidence",
        "cards": cards,
        "errors": [{"reason": "full text unavailable", "status": 404}],
    }
    ref = b.persist("evidence-research", query)
    b.store.event(b.thread, "evidence-view", {"target_binding": identity(b.binding()), "ref": ref})
    source_path = b.project / source["relative_path"]
    before = source_path.read_bytes()
    token = bind(b)
    try:
        selection = handoff()
        alternative = selection.candidates[0].model_copy(
            update={"name": "SYNTHETIC competing mechanism at shared residues"}
        )
        selection = selection.model_copy(
            update={"candidates": [*selection.candidates, alternative]}
        )
        selection = decision_scope(b, selection, "function", query["query_id"])
        critical = selection.decision_questions[0]
        critical = DecisionEvidenceQuestion.model_validate(
            {
                **critical.model_dump(mode="json"),
                "evidence": [
                    {
                        "card_id": "passage-opposition",
                        "excerpt": "evidence contradicting hypothesis A.",
                        "claim": "SYNTHETIC opposing result must reach the independent Judge.",
                        "relation": "contradicts",
                        "strength": "E3",
                        "transfer_limit": "Synthetic boundary test only.",
                    }
                ],
            }
        )
        selection = selection.model_copy(update={"decision_questions": [critical]})
        execution = b.store.begin_execution(b.thread, "SYNTHETIC decision sufficiency boundary")
        dossier = persist_dossier(b, selection, execution["execution_id"])
        assert len(dossier["candidate_comparison"]) == 2
        table = dossier["trusted_residue_facts"]["facts_table"]
        n = len(table["mapping_columns"])
        restored = [
            {
                "mapping": dict(zip(table["mapping_columns"], row[:n], strict=True)),
                **dict(zip(table["metric_columns"], row[n:], strict=True)),
            }
            for row in table["rows"]
        ]
        assert restored == b.read_site_evidence(SiteQuery(label_seq_ids=[1, 2, 3]))["facts"]
        assert dossier["runtime_status"]["target_gate"] == "resolved"
        assert (
            dossier["candidate_comparison"][0]["deterministic_evaluation"]
            == (dossier["candidate_comparison"][1]["deterministic_evaluation"])
        )
        assert {c["passage"] for c in dossier["focused_passages"]} == {c["passage"] for c in cards}
        from easydesign.agent.evidence_research import EvidenceResearch

        verified_cards = EvidenceResearch(b).snapshot()["queries"][0]["cards"]
        for projected, original in zip(dossier["focused_passages"], verified_cards, strict=True):
            assert projected["limitations"] == original["limitations"]
            assert projected["does_not_support"] == original["does_not_support"]
            assert projected["primary_eligible"] == original["primary_eligible"]
            assert projected["evidence_level"] == original["evidence_level"]
            assert projected["partial"] is True
            assert projected["source_id"] == original["source_id"]
            assert projected["binding_context"] == {
                key: original["binding_context"][key] for key in ("relation", "relevance")
            }
            assert "source_refs" not in projected and "selection_provenance" not in projected
        assert dossier["research_outcomes"][0]["errors"] == query["errors"]
        assert dossier["approved_target"] == b.read_site_evidence()["approved_target"]
        assert b.current_site() is None and b.approved_site() is None
        assert source_path.read_bytes() == before
        event = b.store.events(b.thread)[-1]["payload"]
        assert b.document(event["ref"]) == dossier
        from easydesign.agent.evidence_research import ResearchConclusion
        from tests.unit.agent.test_site_runtime import site_intent

        intent = site_intent([1, 2, 3])
        with pytest.raises(AgentBoundaryError, match="decision-critical"):
            validate_dossier_intent(b, intent, execution["execution_id"])
        intent = intent.model_copy(
            update={
                "scope": "mechanistic",
                "material_questions": ["function"],
                "research_conclusions": [
                    ResearchConclusion(
                        topic="function",
                        status="UNRESOLVED",
                        query_ids=[query["query_id"]],
                        limitations=["SYNTHETIC no final functional conclusion."],
                    )
                ],
            }
        )
        validate_dossier_intent(b, intent, execution["execution_id"])
        snapshot = b.register_site(intent, None)
        assert (
            snapshot["research_evidence"]["decision_basis"]["stopping_reason"]
            == selection.stopping_reason
        )
        assert "passage-opposition" in {
            c["card_id"] for c in snapshot["research_evidence"]["source_cards"]
        }
        assert not intent.research_conclusions[
            0
        ].evidence  # Judge did not depend on final citation selection.
        assert b.approved_site() is None
        source_path.write_text("SYNTHETIC integrity failure")
        with pytest.raises(ArtifactIntegrityError):
            b.site_snapshot(b.current_site())
        with pytest.raises(ArtifactIntegrityError):
            site_dossier(b, handoff())
    finally:
        SITE_EVIDENCE.reset(token)


def test_dossier_rejects_missing_or_stale_delegation(site_bridge: Any) -> None:
    with pytest.raises(AgentBoundaryError, match="delegated Target binding"):
        site_dossier(site_bridge, handoff())
    token = bind(site_bridge)
    try:
        current = SITE_EVIDENCE.get()
        SITE_EVIDENCE.set(current.model_copy(update={"evidence_id": "other-project"}))
        with pytest.raises(AgentBoundaryError, match="delegated Target binding"):
            site_dossier(site_bridge, handoff())
    finally:
        SITE_EVIDENCE.reset(token)


def test_dossier_keeps_existing_nonprimary_kernel_citation_semantics(site_bridge: Any) -> None:
    import json

    from easydesign.agent.contracts import EvidenceCitationMismatch, ResearchConclusionMismatch
    from tests.unit.agent.test_site_runtime import site_intent

    b = site_bridge
    kernel = {
        "identity": {"scope": "SYNTHETIC receptor fixture"},
        "state": {"state": "unknown"},
        "membrane": {"status": "unresolved"},
        "warnings": ["Synthetic evidence, not a real receptor analysis."],
        "avoid": [],
        "chain_graph": {"edges": []},
        "topology": {"status": "unresolved", "residues": [], "unmapped_residues": []},
    }
    source = b.persist("synthetic-kernel", kernel)
    card = {
        "card_id": "receptor-synthetic",
        "provider": "EasyDesign GPCR kernel",
        "identifier": "SYNTHETIC",
        "passage": json.dumps(kernel),
        "source_refs": [source],
        "source_verified": True,
        "evidence_level": "deterministic-structure-analysis",
        "primary_eligible": False,
        "does_not_support": ["Binding efficacy or primary literature evidence"],
    }
    query = {
        "query_id": "synthetic-kernel-query",
        "topic": "state",
        "status": "UNRESOLVED",
        "question": "Synthetic structural state",
        "cards": [card],
        "errors": [],
    }
    ref = b.persist("evidence-research", query)
    b.store.event(
        b.thread, "evidence-research", {"target_binding": identity(b.binding()), "ref": ref}
    )
    selection = handoff()
    selection = selection.model_copy(
        update={
            "candidates": [
                selection.candidates[0].model_copy(update={"evidence_card_ids": [card["card_id"]]})
            ],
        }
    )
    selection = decision_scope(b, selection, "state", query["query_id"])
    token = bind(b)
    try:
        dossier = persist_dossier(b, selection, "synthetic-execution")
        assert dossier["receptor_context"][0]["primary_eligible"] is False
        assert dossier["receptor_context"][0]["state"] == kernel["state"]
        intent = site_intent([1, 2, 3])
        intent = intent.model_copy(
            update={
                "selected_site": intent.selected_site.model_copy(
                    update={"evidence_card_ids": [card["card_id"]]}
                )
            }
        )
        from easydesign.agent.evidence_research import ResearchConclusion

        intent = intent.model_copy(
            update={
                "material_questions": ["state"],
                "research_conclusions": [
                    ResearchConclusion(
                        topic="state",
                        status="UNRESOLVED",
                        query_ids=[query["query_id"]],
                        limitations=["SYNTHETIC computational state, not functional efficacy."],
                    )
                ],
            }
        )
        validate_dossier_intent(b, intent, "synthetic-execution")
        b.validate_site_research(intent)
        selection = selection.model_copy(
            update={
                "candidates": [
                    selection.candidates[0].model_copy(
                        update={"evidence_card_ids": ["source-unread"]}
                    )
                ],
            }
        )
        with pytest.raises(ResearchConclusionMismatch) as error:
            site_dossier(b, selection)
        assert '"actually_queried_topics":["state"]' in str(error.value)
        assert '"unknown_or_acquisition_citations":["source-unread"]' in str(error.value)
        intent = intent.model_copy(
            update={
                "selected_site": intent.selected_site.model_copy(
                    update={"evidence_card_ids": ["source-unread"]}
                )
            }
        )
        with pytest.raises(EvidenceCitationMismatch):
            validate_dossier_intent(b, intent, "synthetic-execution")
    finally:
        SITE_EVIDENCE.reset(token)


def test_soft_working_target_and_model_aware_hard_guard() -> None:
    config = scripted_config()
    model = SimpleNamespace(profile=None)
    usage = context_usage(model, config, "site", [HumanMessage(content="x" * 67000)])
    assert usage["soft_target_exceeded"] and usage["hard_limit_chars"] == 100000
    with pytest.raises(AgentBoundaryError, match="hard context guard"):
        context_usage(model, config, "site", [HumanMessage(content="x" * 99000)], 1001)
    with pytest.raises(AgentBoundaryError, match="hard context guard"):
        context_usage(
            SimpleNamespace(profile={"max_input_tokens": 4096}),
            config,
            "site",
            [HumanMessage(content="x" * 20000)],
        )


@pytest.mark.asyncio
async def test_framework_summary_preserves_trace_and_consumes_shared_budget(
    bridge: Any,
    tmp_path: Path,
) -> None:
    config = scripted_config().model_copy(
        update={"max_input_chars": 4000, "hard_input_chars": 30000}
    )
    execution = bridge.store.begin_execution(bridge.thread, "Synthetic framework summary")
    model = FakeListChatModel(
        responses=["Fallible synthetic working memory; sources remain authoritative."]
    )
    backend = FilesystemBackend(root_dir=tmp_path / "memory", virtual_mode=True)
    middleware = research_memory(bridge, config, model, backend, execution["execution_id"])
    messages: list[Any] = [HumanMessage(content="Synthetic original goal")]
    for i in range(10):
        messages.extend(
            [
                AIMessage(
                    content="", tool_calls=[{"id": str(i), "name": "read_evidence", "args": {}}]
                ),
                ToolMessage(
                    content=f"SYNTHETIC evidence {i} " + "x" * 1800,
                    name="read_evidence",
                    tool_call_id=str(i),
                ),
            ]
        )
    original = [m.model_dump() for m in messages]
    received = []

    async def handler(request: Any) -> Any:
        received.extend(request.messages)
        bridge.store.reserve_model_call(bridge.thread, "site", 32, execution["execution_id"])
        return ModelResponse(result=[AIMessage(content="Synthetic response")])

    result = await middleware.awrap_model_call(
        ModelRequest(
            model=model,
            system_message=SystemMessage(content="Synthetic research"),
            messages=messages,
            state={"messages": messages},
            tools=[],
        ),
        handler,
    )
    assert [m.model_dump() for m in messages] == original
    assert len(received) < len(messages)
    event = result.command.update["_summarization_event"]
    retained = tmp_path / "memory" / event["file_path"].lstrip("/")
    assert retained.is_file() and "SYNTHETIC evidence 0" in retained.read_text()
    events = bridge.store.events(bridge.thread)
    assert len([e for e in events if e["kind"] == "model-call"]) == 2
    assert len([e for e in events if e["kind"] == "framework-summary-call"]) == 1
    assert len([e for e in events if e["kind"] == "framework-summary-response"]) == 1
    summary_event = next(e for e in events if e["kind"] == "framework-summary-response")
    assert summary_event["payload"]["latency_seconds"] >= 0


@pytest.mark.asyncio
async def test_resume_between_durable_dossier_and_synthesis_reuses_research(
    site_bridge: Any,
    monkeypatch: Any,
) -> None:
    from easydesign.agent import harness
    from easydesign.agent.cli import run_session
    from easydesign.agent.phase2 import Phase2Bridge
    from easydesign.agent.phase2_tools import PHASE2_ALLOWED
    from easydesign.agent.session_store import SessionStore
    from tests.unit.agent.test_command_recovery import Crash
    from tests.unit.agent.test_site_harness import SiteModel

    models = {role: SiteModel(role=role) for role in PHASE2_ALLOWED}
    original = harness.persist_dossier

    def interrupt_after_persistence(*args: Any, **kwargs: Any) -> Any:
        original(*args, **kwargs)
        raise Crash("SYNTHETIC interruption after durable dossier")

    with monkeypatch.context() as patch:
        patch.setattr(harness, "persist_dossier", interrupt_after_persistence)
        with pytest.raises(Crash):
            await run_session(
                site_bridge, scripted_config(), models, "Review a structural hypothesis."
            )
    assert site_bridge.current_site() is None
    before = site_bridge.store.latest_execution(site_bridge.thread)
    assert len(models["site"].tasks) == 1
    first = site_bridge.thread_latest("site-evidence-dossier")
    reopened = SessionStore(site_bridge.project)
    try:
        resumed = Phase2Bridge(site_bridge.project, site_bridge.thread, reopened)
        result = await run_session(
            resumed, scripted_config(), models, "Review a structural hypothesis."
        )
        assert result["status"] == "awaiting-human-approval"
        assert result["card"]["gate_type"] == "site-hotspot"
        assert len(models["site"].tasks) == 1
        assert resumed.store.latest_execution(resumed.thread) == before
        assert resumed.thread_latest("site-evidence-dossier")["ref"] == first["ref"]
        assert len(resumed._jobs()) == 1
    finally:
        reopened.close()


def test_research_handoff_requires_real_contradiction_inquiry_but_accepts_unresolved(
    site_bridge: Any,
) -> None:
    from easydesign.agent.contracts import ResearchConclusionMismatch

    b = site_bridge
    selection = decision_scope(b, handoff(), "function", "synthetic-contradiction-search")
    token = bind(b)
    try:
        with pytest.raises(ResearchConclusionMismatch, match="decision-critical"):
            site_dossier(b, handoff())
        with pytest.raises(ResearchConclusionMismatch, match="actual targeted"):
            site_dossier(b, selection.model_copy(update={"contradiction_search_query_ids": []}))
        with pytest.raises(ResearchConclusionMismatch, match="actual targeted"):
            site_dossier(
                b, selection.model_copy(update={"contradiction_search_query_ids": ["invented-id"]})
            )
        result = site_dossier(b, selection)
        assert result["decision_questions"][0]["status"] == "UNRESOLVED"
        assert result["decision_questions"][0]["query_ids"] == ["synthetic-contradiction-search"]
        assert result["research_opinions"]["stopping_reason"] == selection.stopping_reason
        assert b.current_site() is None
    finally:
        SITE_EVIDENCE.reset(token)
