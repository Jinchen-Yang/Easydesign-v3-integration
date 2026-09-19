"""SYNTHETIC choice/hydration tests, never biological acceptance."""

from copy import deepcopy
from types import SimpleNamespace
from typing import Any

import pytest
from pydantic import ValidationError

from easydesign.agent.contracts import AgentBoundaryError
from easydesign.agent.phase2 import SITE_EVIDENCE
from easydesign.agent.site_decision import (
    SiteDecision,
    compile_site_decision,
    decision_working_set,
    hydrate_site_decision,
)
from easydesign.agent.site_dossier import persist_dossier
from tests.unit.agent.test_site_dossier import bind, handoff


def decision(candidate_id: str = "site-synthetic") -> SiteDecision:
    return SiteDecision(
        selected_candidate_id=candidate_id,
        recommendation="SUPPORTED",
        why_selected="SYNTHETIC exposed candidate permits a structural exploration only.",
        mechanistic_rationale="SYNTHETIC engagement hypothesis; no functional efficacy claim.",
        approach_rationale="SYNTHETIC solvent approach; whole-binder clearance requires testing.",
        alternative_comparison="SYNTHETIC no additional distinct candidate was supplied.",
        uncertainty=["SYNTHETIC binding, function and conformational specificity are untested."],
    )


@pytest.mark.parametrize(
    "field",
    [
        "hotspot_label_seq_ids",
        "canonical_positions",
        "chain",
        "evidence_card_ids",
        "research_conclusions",
    ],
)
def test_decision_cannot_submit_runtime_facts(field: str) -> None:
    with pytest.raises(ValidationError, match="Extra inputs"):
        SiteDecision.model_validate({**decision().model_dump(), field: [286]})


def test_runtime_hydrates_nonidentity_mapping_without_model_conversion() -> None:
    # Deliberate fixture: canonical 286 corresponds to design 414, never 286.
    dossier = {
        "target_binding": "synthetic-target",
        "owner_thread": "synthetic-thread",
        "candidate_comparison": [
            {
                "candidate_id": "site-synthetic",
                "research_hypothesis": {
                    "name": "SYNTHETIC nonidentity patch",
                    "hotspot_label_seq_ids": [414],
                    "rationale": "SYNTHETIC mapping fixture",
                    "role": "primary",
                    "origin": "scan-derived",
                    "evidence_card_ids": [],
                },
            }
        ],
        "decision_questions": [],
        "residue_constraints": [],
        "focused_passages": [],
        "receptor_context": [],
        "trusted_residue_facts": {
            "facts_table": {
                "mapping_columns": ["label_seq_id", "canonical_position"],
                "metric_columns": [],
                "rows": [[414, 286]],
            }
        },
    }
    bridge = SimpleNamespace(
        thread="synthetic-thread",
        thread_latest=lambda _: {"execution_id": "synthetic-exec", "ref": "synthetic-ref"},
        document=lambda _: deepcopy(dossier),
        target_state=lambda: {"binding": "synthetic-target"},
    )
    original = deepcopy(dossier)
    intent = hydrate_site_decision(bridge, decision(), "synthetic-exec")
    assert intent.selected_site.hotspot_label_seq_ids == [414]
    assert 286 not in intent.selected_site.hotspot_label_seq_ids
    assert dossier == original
    with pytest.raises(AgentBoundaryError, match="candidate IDs"):
        hydrate_site_decision(bridge, decision("site-other-project"), "synthetic-exec")
    dossier["target_binding"] = "synthetic-stale"
    with pytest.raises(AgentBoundaryError, match="stale Target"):
        hydrate_site_decision(bridge, decision(), "synthetic-exec")


def test_real_adapter_hydration_preserves_candidates_and_scoped_facts(site_bridge: Any) -> None:
    b = site_bridge
    execution = b.store.begin_execution(b.thread, "SYNTHETIC bounded Site decision")
    token = bind(b)
    try:
        dossier = persist_dossier(b, handoff(), execution["execution_id"])
        chosen = decision(dossier["candidate_comparison"][0]["candidate_id"])
        intent = hydrate_site_decision(b, chosen, execution["execution_id"])
        assert intent.selected_site.hotspot_label_seq_ids == [1, 2, 3]
        assert b.current_site() is None
        dossier["candidate_comparison"][0]["research_hypothesis"]["rationale"] = (
            "SYNTHETIC stale preliminary candidate preference"
        )
        dossier["research_opinions"]["research_notes"] = ["SYNTHETIC stale research narrative"]
        working = decision_working_set(dossier)
        assert "stale preliminary" not in str(working)
        assert "stale research narrative" not in str(working)
        assert "unresolved_research_questions" not in working
        assert working["kind"] == "site-decision-working-set-v2"
        assert all(
            {"question", "status", "decision_impact", "limitations", "query_ids", "evidence"}
            <= set(question)
            for question in working["research_findings"]
        )
        assert working["approach_validation"]["scientific_status"] == "UNRESOLVED"
        assert working["candidates"][0]["candidate_id"] == chosen.selected_candidate_id
        assert "trusted_residue_facts" not in working
        assert "research_outcomes" not in working
        assert "hotspot_label_seq_ids" not in str(working)
        candidate = working["candidates"][0]
        rsasa_index = candidate["residue_fact_columns"].index("rsasa")
        assert candidate["residue_facts"][0][rsasa_index] is not None
        snap = b.register_site(intent, None)
        assert snap["proposal"]["selected_site"]["hotspot_label_seq_ids"] == [1, 2, 3]
        assert snap["target_facts"] == b.read_evidence()["hard_facts"]
        # Judge receives the verified dossier's facts for every candidate, even
        # though the legacy prepared-chain summary covers only the selected site.
        saved = b.document(b.thread_latest("site-evidence-dossier")["ref"])
        actual = snap["site_dossier_facts"]
        assert actual["trusted_residue_facts"] == saved["trusted_residue_facts"]
        assert actual["receptor_context"] == saved["receptor_context"]
        assert actual["runtime_status"] == saved["runtime_status"]
        assert actual["candidates"][0]["location"] == saved["candidate_comparison"][0]["location"]
        assert actual["candidates"][0]["design_labels"] == [1, 2, 3]
        proposal = b.current_site()
        for changed in ({"owner_thread": "foreign-owner"}, {"target_binding": "stale-target"}):
            with pytest.raises(AgentBoundaryError, match="differs from proposal Target or owner"):
                b.site_snapshot({**proposal, **changed})
    finally:
        SITE_EVIDENCE.reset(token)


def test_whitespace_is_not_a_nonempty_scientific_decision() -> None:
    with pytest.raises(ValidationError):
        SiteDecision.model_validate({**decision().model_dump(), "why_selected": "   "})


def test_comparison_requires_ids_but_does_not_recommend_avoid_candidates() -> None:
    def candidate(candidate_id: str, label: int, role: str) -> dict[str, Any]:
        return {
            "candidate_id": candidate_id,
            "research_hypothesis": {
                "name": "SYNTHETIC " + candidate_id,
                "hotspot_label_seq_ids": [label],
                "rationale": "SYNTHETIC comparison fixture",
                "role": role,
                "origin": "scan-derived",
                "evidence_card_ids": [],
            },
        }

    dossier = {
        "candidate_comparison": [
            candidate("site-synthetic", 414, "primary"),
            candidate("site-rejected", 418, "avoid"),
        ],
        "decision_questions": [],
        "residue_constraints": [],
    }
    with pytest.raises(AgentBoundaryError, match="Compare at least one"):
        compile_site_decision(dossier, decision())
    selected = decision().model_copy(update={"alternative_candidate_ids": ["site-rejected"]})
    intent = compile_site_decision(dossier, selected)
    assert intent.selected_site.hotspot_label_seq_ids == [414]
    assert intent.alternatives[0].hotspot_label_seq_ids == [418]
    assert intent.alternatives[0].role == "backup"


def test_distinct_questions_share_a_topic_without_merging_evidence_states(site_bridge: Any) -> None:
    from easydesign.agent.session_store import identity
    from easydesign.agent.site_dossier import SiteResearchHandoff, site_dossier
    from tests.unit.agent.test_site_dossier import decision_scope

    b = site_bridge
    text = "SYNTHETIC assay supports binding, without establishing absence of activation."
    source = b.persist("synthetic-source", {"text": text})
    query_id = "synthetic-binding-view-0"
    query = {
        "query_id": query_id,
        "topic": "function",
        "question": "SYNTHETIC binding evidence",
        "status": "VERIFIED",
        "cards": [
            {
                "card_id": "passage-synthetic-binding",
                "provider": "EuropePMC",
                "identifier": "synthetic-binding",
                "passage": text,
                "source_refs": [source],
                "evidence_level": "primary-abstract",
                "primary_eligible": True,
                "limitations": ["SYNTHETIC fixture only."],
            }
        ],
        "errors": [],
    }
    ref = b.persist("evidence-research", query)
    b.store.event(b.thread, "evidence-view", {"target_binding": identity(b.binding()), "ref": ref})
    selection = decision_scope(b, handoff(), "function", query_id)
    first = selection.decision_questions[0].model_dump(mode="json")
    first.update(
        question="SYNTHETIC is binding supported?",
        status="VERIFIED",
        query_ids=[query_id],
        evidence=[
            {
                "card_id": "passage-synthetic-binding",
                "excerpt": text,
                "claim": "SYNTHETIC binding support only, not an adverse-effect assessment.",
                "relation": "supports",
                "strength": "E3",
                "transfer_limit": "SYNTHETIC fixture, not biological acceptance.",
            }
        ],
    )
    second = selection.decision_questions[0].model_dump(mode="json")
    second.update(
        question="SYNTHETIC could engagement activate the target?",
        query_ids=selection.contradiction_search_query_ids,
    )
    selection = SiteResearchHandoff.model_validate(
        {**selection.model_dump(mode="json"), "decision_questions": [first, second]}
    )
    token = bind(b)
    try:
        execution = b.store.begin_execution(b.thread, "SYNTHETIC separate decision questions")
        dossier = persist_dossier(b, selection, execution["execution_id"])
        chosen = decision(dossier["candidate_comparison"][0]["candidate_id"])
        intent = hydrate_site_decision(b, chosen, execution["execution_id"])
        assert "material_questions" not in intent.model_dump()
        assert "research_conclusions" not in intent.model_dump()
        assert [q["status"] for q in dossier["decision_questions"]] == ["VERIFIED", "UNRESOLVED"]
        assert dossier["decision_questions"][0]["evidence"][0]["excerpt"] == text
        snapshot = b.register_site(intent, None)
        questions = snapshot["research_evidence"]["decision_questions"]
        assert [q["question"] for q in questions] == [first["question"], second["question"]]
        assert all(set(q) == {"question"} for q in questions)
        bad = selection.model_copy(
            update={
                "decision_questions": [
                    selection.decision_questions[0].model_copy(
                        update={"query_ids": ["synthetic-binding-view"]}
                    ),
                    selection.decision_questions[1],
                ]
            }
        )
        with pytest.raises(AgentBoundaryError, match="Available complete query_ids") as error:
            site_dossier(b, bad)
        assert query_id in str(error.value)
    finally:
        SITE_EVIDENCE.reset(token)


def test_runtime_candidate_name_cannot_promote_research_claim(site_bridge: Any) -> None:
    from easydesign.agent.site_decision import candidate_name

    b = site_bridge
    execution = b.store.begin_execution(b.thread, "SYNTHETIC candidate naming boundary")
    token = bind(b)
    try:
        dossier = persist_dossier(b, handoff(), execution["execution_id"])
        candidate = dossier["candidate_comparison"][0]
        original_id = candidate["candidate_id"]
        candidate["research_hypothesis"]["name"] = "SYNTHETIC database-proven inert epitope"
        candidate["location"]["segments"] = ["extracellular", "transmembrane"]
        original = deepcopy(dossier)
        chosen = decision(original_id)
        working = decision_working_set(dossier)
        intent = compile_site_decision(dossier, chosen)
        assert "database-proven" not in str(working)
        assert "database-proven" not in intent.selected_site.name
        assert intent.selected_site.name == candidate_name(candidate)
        assert intent.selected_site.hotspot_label_seq_ids == [1, 2, 3]
        assert working["candidates"][0]["location"]["segments"] == [
            "extracellular",
            "transmembrane",
        ]
        assert working["candidates"][0]["candidate_id"] == original_id
        assert dossier == original
    finally:
        SITE_EVIDENCE.reset(token)


@pytest.mark.asyncio
async def test_coordinator_reads_progress_without_becoming_site_reviewer(
    site_bridge: Any, monkeypatch: Any
) -> None:
    import json

    from easydesign.agent.phase2_tools import _scientific_tools

    b = site_bridge
    current = {
        "scientific_state": "awaiting-human-approval",
        "gate_type": "site-hotspot",
        "next_specialist": "evidence-judge",
        "proposal": {"rationale": "SYNTHETIC specialist interpretation"},
    }
    original = deepcopy(current)
    monkeypatch.setattr(b, "scientific_state", lambda: current)
    tool = next(t for t in _scientific_tools(b, "coordinator") if t.name == "read_scientific_state")
    shown = json.loads(await tool.ainvoke({}))
    assert shown == {k: v for k, v in original.items() if k != "proposal"}
    assert current == original
