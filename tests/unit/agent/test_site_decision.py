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
        assert (
            working["unresolved_research_questions"]
            == dossier["research_opinions"]["unresolved_questions"]
        )
        assert working["candidates"][0]["candidate_id"] == chosen.selected_candidate_id
        assert "trusted_residue_facts" not in working
        assert "research_outcomes" not in working
        assert "hotspot_label_seq_ids" not in str(working)
        assert working["candidates"][0]["residue_facts"][0]["rsasa"] is not None
        snap = b.register_site(intent, None)
        assert snap["proposal"]["selected_site"]["hotspot_label_seq_ids"] == [1, 2, 3]
        assert snap["target_facts"] == b.read_evidence()["hard_facts"]
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
    }
    with pytest.raises(AgentBoundaryError, match="Compare at least one"):
        compile_site_decision(dossier, decision())
    selected = decision().model_copy(update={"alternative_candidate_ids": ["site-rejected"]})
    intent = compile_site_decision(dossier, selected)
    assert intent.selected_site.hotspot_label_seq_ids == [414]
    assert intent.alternatives[0].hotspot_label_seq_ids == [418]
    assert intent.alternatives[0].role == "avoid"
