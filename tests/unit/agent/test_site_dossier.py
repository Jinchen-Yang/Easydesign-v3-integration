"""Dossier authority and framework memory tests; all evidence here is synthetic."""

import hashlib
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
            update={"name": "SYNTHETIC competing mechanism", "hotspot_label_seq_ids": [1, 2, 4]}
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
        assert restored == b.read_site_evidence(SiteQuery(label_seq_ids=[1, 2, 3, 4]))["facts"]
        assert dossier["runtime_status"]["target_gate"] == "resolved"
        assert len({c["candidate_id"] for c in dossier["candidate_comparison"]}) == 2
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
        from tests.unit.agent.test_site_runtime import site_intent

        intent = site_intent([1, 2, 3])
        validate_dossier_intent(b, intent, execution["execution_id"])
        snapshot = b.register_site(intent, None)
        assert "decision_basis" not in snapshot["research_evidence"]
        assert (
            b.document(event["ref"])["research_opinions"]["stopping_reason"]
            == selection.stopping_reason
        )
        assert "passage-opposition" in {
            c["card_id"] for c in snapshot["research_evidence"]["source_cards"]
        }
        assert "research_conclusions" not in intent.model_dump()
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


def test_handoff_retains_hard_invalid_backup_without_shifting_primary(site_bridge: Any) -> None:
    selection = handoff()
    payload = selection.model_dump(mode="json")
    payload["candidates"].append(
        {
            "name": "Synthetic invalid backup",
            "role": "backup",
            "hotspot_label_seq_ids": [999],
            "rationale": "Deliberately invalid synthetic numbering, not scientific evidence.",
        }
    )
    token = bind(site_bridge)
    try:
        dossier = site_dossier(site_bridge, SiteResearchHandoff.model_validate(payload))
        primary, invalid = dossier["candidate_comparison"]
        assert primary["research_hypothesis"]["hotspot_label_seq_ids"] == [1, 2, 3]
        assert primary["deterministic_evaluation"]["status"] != "BLOCKED"
        assert invalid["research_hypothesis"]["hotspot_label_seq_ids"] == [999]
        assert invalid["deterministic_evaluation"]["cause"] == "invalid-approved-mapping"
        assert selection.candidates[0].hotspot_label_seq_ids == [1, 2, 3]
    finally:
        SITE_EVIDENCE.reset(token)


def test_dossier_keeps_existing_nonprimary_kernel_citation_semantics(site_bridge: Any) -> None:
    import json

    from easydesign.agent.contracts import EvidenceCitationMismatch
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
        with pytest.raises(EvidenceCitationMismatch) as error:
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


def test_dossier_reports_candidate_and_question_citation_defects_atomically(
    site_bridge: Any,
) -> None:
    from easydesign.agent.contracts import EvidenceCitationMismatch

    b = site_bridge
    source = b.persist("synthetic-source", {"text": "SYNTHETIC source material"})
    focused = {
        "card_id": "passage-focused",
        "provider": "Europe PMC",
        "identifier": "SYNTHETIC",
        "passage": "SYNTHETIC exact focused passage for the candidate mechanism.",
        "source_refs": [source],
        "source_verified": True,
        "evidence_level": "primary-abstract",
        "primary_eligible": True,
        "does_not_support": ["Binding efficacy"],
    }
    receipt = {
        "card_id": "source-acquisition-receipt",
        "provider": "Europe PMC",
        "identifier": "SYNTHETIC",
        "passage": "SYNTHETIC acquisition metadata, not focused evidence.",
        "source_refs": [source],
        "source_verified": True,
        "evidence_level": "acquisition-receipt",
        "primary_eligible": False,
        "does_not_support": ["Any scientific claim"],
        "corpus_ref": source,
    }
    query = {
        "query_id": "synthetic-focused-query",
        "topic": "function",
        "status": "UNRESOLVED",
        "question": "SYNTHETIC candidate mechanism",
        "cards": [receipt, focused],
        "errors": [],
    }
    ref = b.persist("evidence-research", query)
    b.store.event(
        b.thread,
        "evidence-view",
        {"target_binding": identity(b.binding()), "ref": ref},
    )
    selection = decision_scope(b, handoff(), "function", query["query_id"])
    candidate = selection.candidates[0].model_copy(
        update={"evidence_card_ids": [receipt["card_id"]]}
    )
    question = DecisionEvidenceQuestion.model_validate(
        {
            **selection.decision_questions[0].model_dump(mode="json"),
            "evidence": [
                {
                    "card_id": focused["card_id"],
                    "excerpt": "A paraphrase rather than exact retrieved text.",
                    "claim": "SYNTHETIC candidate mechanism claim.",
                    "relation": "supports",
                    "strength": "E1",
                    "transfer_limit": "SYNTHETIC boundary test only.",
                }
            ],
        }
    )
    selection = selection.model_copy(
        update={"candidates": [candidate], "decision_questions": [question]}
    )
    token = bind(b)
    try:
        with pytest.raises(EvidenceCitationMismatch) as captured:
            site_dossier(b, selection)
        error = captured.value
        assert error.repair_keys == ("known-source:" + focused["card_id"],)
        assert error.citation_unkeyed is True
        assert error.citation_findings == ((0, focused["card_id"], False),)
        assert receipt["card_id"] in str(error)
        assert focused["passage"] not in str(error)
        assert error.citation_copy_blocks == (
            {
                "card_id": focused["card_id"],
                "passage": focused["passage"],
                "passage_sha256": hashlib.sha256(focused["passage"].encode("utf-8")).hexdigest(),
                "passage_chars": len(focused["passage"]),
                "locations": [{"kind": "decision-question", "question_index": 0}],
            },
        )

        corrected = selection.model_copy(
            update={
                "candidates": [
                    candidate.model_copy(update={"evidence_card_ids": [focused["card_id"]]})
                ],
                "decision_questions": [
                    question.model_copy(
                        update={
                            "evidence": [
                                question.evidence[0].model_copy(
                                    update={"excerpt": "exact focused passage"}
                                )
                            ]
                        }
                    )
                ],
            }
        )
        assert site_dossier(b, corrected)["candidate_comparison"]
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
        bridge.store.reserve_model_call(
            bridge.thread, "site", config.max_model_calls, execution["execution_id"]
        )
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
    assert len([e for e in events if e["kind"] == "model-call"]) == 1
    assert len([e for e in events if e["kind"] == "auxiliary-model-call"]) == 1
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


def test_research_handoff_accepts_sufficient_evidence_without_mandatory_contradiction_search(
    site_bridge: Any,
) -> None:
    from easydesign.agent.contracts import ResearchConclusionMismatch

    b = site_bridge
    selection = decision_scope(b, handoff(), "function", "synthetic-contradiction-search")
    token = bind(b)
    try:
        with pytest.raises(ResearchConclusionMismatch, match="decision-critical"):
            site_dossier(b, handoff())
        without_contradiction = site_dossier(
            b, selection.model_copy(update={"contradiction_search_query_ids": []})
        )
        assert (
            without_contradiction["evidence_selection"]["contradiction_search_performed"] is False
        )
        with pytest.raises(ResearchConclusionMismatch, match="actual literature-search"):
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


def test_acquisition_only_research_retains_questions_without_inventing_search_id(
    site_bridge: Any,
) -> None:
    b = site_bridge
    acquisition = {
        "query_id": "synthetic-uniprot-acquisition",
        "topic": "identity",
        "question": "SYNTHETIC which official identity record applies?",
        "query": {"operation": "uniprot-record", "identifier": "P00000"},
        "status": "UNRESOLVED",
        "cards": [],
        "errors": [],
    }
    ref = b.persist("evidence-research", acquisition)
    b.store.event(
        b.thread,
        "evidence-research",
        {"target_binding": identity(b.binding()), "ref": ref},
    )
    question = DecisionEvidenceQuestion.model_validate(
        {
            "query_ids": [acquisition["query_id"]],
            "question": "SYNTHETIC can the acquired identity resolve the Site mapping?",
            "status": "UNRESOLVED",
            "evidence": [],
            "limitations": ["SYNTHETIC acquisition was not a contradiction search."],
            "decision_impact": "SYNTHETIC ranking remains provisional.",
        }
    )
    selection = handoff().model_copy(
        update={
            "decision_questions": [question],
            "contradiction_search_query_ids": [],
            "stopping_reason": "SYNTHETIC reading budget ended before a contradiction search; "
            "the gap remains unresolved.",
        }
    )
    token = bind(b)
    try:
        from easydesign.agent.contracts import ResearchConclusionMismatch

        with pytest.raises(ResearchConclusionMismatch, match="No literature-search"):
            site_dossier(
                b,
                selection.model_copy(
                    update={"contradiction_search_query_ids": [acquisition["query_id"]]}
                ),
            )
        result = site_dossier(b, selection)
        assert result["decision_questions"][0]["query_ids"] == [acquisition["query_id"]]
        assert result["evidence_selection"]["literature_searches_available"] == 0
        assert result["evidence_selection"]["contradiction_search_performed"] is False
        assert "unresolved evidence gap" in result["evidence_selection"]["contradiction_search_gap"]
    finally:
        SITE_EVIDENCE.reset(token)


def test_zero_query_question_remains_typed_without_contradiction_search_gap(
    site_bridge: Any,
) -> None:
    b = site_bridge
    question = DecisionEvidenceQuestion(
        query_ids=[],
        question="SYNTHETIC is the mapped patch externally supported?",
        status="UNRESOLVED",
        evidence=[],
        limitations=["SYNTHETIC reading closed before any research query was issued."],
        decision_impact="SYNTHETIC treat the patch as structural exploration only.",
    )
    selection = handoff().model_copy(update={"decision_questions": [question]})
    token = bind(b)
    try:
        result = site_dossier(b, selection)
        assert result["decision_questions"] == [question.model_dump(mode="json")]
        assert result["evidence_selection"]["literature_searches_available"] == 0
        assert result["evidence_selection"]["contradiction_search_performed"] is False
        assert result["evidence_selection"]["contradiction_search_gap"] is None
    finally:
        SITE_EVIDENCE.reset(token)


def test_membrane_facts_use_exact_source_identity_not_design_or_canonical_numbers() -> None:
    from copy import deepcopy

    from easydesign.agent.site_dossier import candidate_membrane_facts

    mapping = {
        "label_seq_id": 414,
        "canonical_position": 286,
        "source_author_chain_id": "A",
        "source_author_residue_id": "901",
        "insertion_code": "B",
        "model_presence": ["2"],
    }
    region = {
        "residue": {
            "auth_asym_id": "A",
            "auth_seq_id": 901,
            "insertion_code": "B",
            "model_id": "2",
            "hetero_flag": "ATOM",
        },
        "region": "outer_pore",
        "protein_segment": "TM6",
        "axial_distance": 9.25,
        "radial_distance": 5.5,
        "pore_lining": True,
    }
    decoys = []
    for change in (
        {"auth_seq_id": 414},
        {"auth_seq_id": 286},
        {"auth_asym_id": "B"},
        {"insertion_code": ""},
        {"model_id": "1"},
        {"hetero_flag": "HETATM:LIG"},
    ):
        decoy = deepcopy(region)
        decoy["residue"].update(change)
        decoy["region"] = "SYNTHETIC wrong source must not cross the boundary"
        decoys.append(decoy)
    analyses = [{"card_id": "SYNTHETIC kernel", "residue_regions": [*decoys, region]}]
    original = deepcopy(analyses)
    rows = candidate_membrane_facts([mapping], analyses)
    assert len(rows) == 1
    assert rows[0]["canonical_position"] == 286
    assert rows[0]["region"] == "outer_pore"
    assert rows[0]["axial_distance"] == 9.25
    assert rows[0]["source_model"] == "2"
    assert "label_seq_id" not in rows[0]
    assert analyses == original
    assert candidate_membrane_facts([mapping], []) == []
