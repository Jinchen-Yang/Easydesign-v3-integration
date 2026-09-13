"""Synthetic Gate 2 semantics and authority tests; no biological acceptance."""

from contextlib import closing
from copy import deepcopy
from typing import Any

import pytest

from easydesign.agent.contracts import (
    AgentBoundaryError,
    ApplyDecision,
    EvidenceBinding,
    JudgeVerdict,
    ResearchConclusionMismatch,
    SiteClaimCorrection,
)
from easydesign.agent.judge_packet import build_judge_packet, validate_judge_corrections
from easydesign.agent.phase2 import SITE_EVIDENCE, Phase2Bridge
from easydesign.agent.session_store import SessionStore, identity
from easydesign.agent.site_decision import compile_site_decision
from easydesign.agent.site_dossier import persist_dossier
from easydesign.agent.tools import JUDGE_EVIDENCE
from tests.unit.agent.test_site_decision import decision
from tests.unit.agent.test_site_dossier import bind, handoff


@pytest.fixture
def packet_case(site_bridge: Any) -> dict[str, Any]:
    b = site_bridge
    b.store.thread(b.thread, "synthetic-packet-contract", "SYNTHETIC structural exploration")
    execution = b.store.begin_execution(b.thread, "SYNTHETIC packet review")
    token = bind(b)
    try:
        dossier = persist_dossier(b, handoff(), execution["execution_id"])
        chosen = decision(dossier["candidate_comparison"][0]["candidate_id"]).model_copy(
            update={
                "why_selected": "SYNTHETIC whole VHH cannot approach the alternative.",
                "major_risks": ["SYNTHETIC cysteine contact proves a trafficking artifact."],
            }
        )
        intent = compile_site_decision(dossier, chosen)
        b.store.event(
            b.thread,
            "site-decision",
            {
                "execution_id": execution["execution_id"],
                "decision": chosen.model_dump(mode="json"),
                "dossier_ref": b.thread_latest("site-evidence-dossier")["ref"],
                "hydrated_intent_sha256": identity(intent.model_dump(mode="json")),
            },
        )
        snapshot = b.register_site(intent, None)
        return {
            "bridge": b,
            "snapshot": snapshot,
            "dossier": dossier,
            "facts": b.site_facts()[1],
            "decision": chosen.model_dump(mode="json"),
        }
    finally:
        SITE_EVIDENCE.reset(token)


def packet(case: dict[str, Any]) -> dict[str, Any]:
    return build_judge_packet(
        case["snapshot"],
        case["dossier"],
        case["facts"],
        goal="SYNTHETIC objective",
        decision=case["decision"],
    )


def test_packet_has_one_fact_owner_and_preserves_opposition_and_uncertainty(packet_case):
    case = packet_case
    dossier = case["dossier"]
    dossier["research_opinions"]["research_notes"] = ["STALE_RESEARCH_OPINION"]
    dossier["focused_passages"] = [
        {
            "card_id": "synthetic-support",
            "passage": "SYNTHETIC support",
            "source_ref": {"sha256": "a"},
            "limitations": ["partial"],
        },
        {
            "card_id": "synthetic-opposition",
            "passage": "SYNTHETIC strongest contradiction",
            "source_ref": {"sha256": "b"},
            "limitations": ["different state"],
        },
    ]
    before = {key: deepcopy(case[key]) for key in ["snapshot", "dossier", "facts", "decision"]}
    # bridge is mutable state; compare the pure scientific inputs only.
    result = packet(case)
    from easydesign.agent.site_fact_integrity import expand_source_passages

    assert expand_source_passages(result) == dossier["focused_passages"]
    assert result["residue_facts"] == dossier["trusted_residue_facts"]
    assert result["final_site_decision"]["interpretation"] == case["decision"]
    for candidate, original in zip(
        result["candidate_facts"], dossier["candidate_comparison"], strict=True
    ):
        assert set(
            result["candidate_evaluation_scope"]["shared_limitations"]
            + candidate["prepared_target_evaluation"]["additional_limitations"]
        ) == set(original["deterministic_evaluation"].get("limitations", []))
    assert result["downstream_validation"]["approach_validation"]["status"] == "not-performed"
    assert "STALE_RESEARCH_OPINION" not in str(result)
    assert not {
        "site_dossier_facts",
        "scientific_context",
        "proposal",
        "evaluation",
        "alternative_evaluations",
    }.intersection(result)
    for key in ["snapshot", "dossier", "facts", "decision"]:
        assert case[key] == before[key]


@pytest.mark.parametrize(
    "fault",
    [
        "mapping",
        "topology",
        "membership",
        "avoid",
        "identity",
        "decision",
        "surface",
        "evaluated_mapping",
    ],
)
def test_deterministic_contradictions_block_before_judge(packet_case, fault):
    case = packet_case
    dossier = case["dossier"]
    if fault == "mapping":
        table = dossier["trusted_residue_facts"]["facts_table"]
        table["rows"][0][table["mapping_columns"].index("canonical_position")] = 999
    elif fault == "topology":
        dossier["candidate_comparison"][0]["location"]["sequence_topology"][0]["annotations"] = [
            {
                "type": "Topological domain",
                "description": "Extracellular",
                "source_sha256": "invented",
            }
        ]
    elif fault == "membership":
        case["snapshot"]["proposal"]["selected_site"]["hotspot_label_seq_ids"] = [999]
    elif fault == "avoid":
        case["snapshot"]["proposal"]["avoid_label_seq_ids"] = [1]
    elif fault == "identity":
        dossier["approved_target"]["hard_facts"]["canonical_accession"] = "WRONG"
    elif fault == "surface":
        dossier["candidate_comparison"][0]["deterministic_evaluation"]["surface_evidence"][0][
            "rsasa"
        ] = 999.0
    elif fault == "evaluated_mapping":
        dossier["candidate_comparison"][0]["deterministic_evaluation"]["mapped_residues"][0][
            "auth_seq_id"
        ] = "999"
    else:
        case["decision"]["mechanistic_rationale"] = "SYNTHETIC different submitted decision"
    with pytest.raises(AgentBoundaryError, match="HARD_FACT_CONTRADICTION"):
        packet(case)


def opinion() -> JudgeVerdict:
    return JudgeVerdict(
        verdict="ready-to-ask",
        reasons=["SYNTHETIC hotspot remains reasonable after qualification."],
        limitations=["SYNTHETIC final affinity and functional effect remain downstream unknowns."],
        site_claim_corrections=[
            SiteClaimCorrection(
                claim="whole VHH cannot approach",
                qualification=(
                    "SYNTHETIC whole-binder access is unresolved; "
                    "later clearance validation is required."
                ),
            ),
            SiteClaimCorrection(
                claim="cysteine contact proves a trafficking artifact",
                qualification=(
                    "SYNTHETIC contact supports a structural-risk warning, "
                    "not a proven trafficking outcome."
                ),
            ),
        ],
    )


def test_corrections_survive_registration_restart_and_warned_gate(packet_case):
    b = packet_case["bridge"]
    snapshot = b.judge_evidence()
    assert snapshot["kind"] == "site-judge-review-packet-v1"
    assert snapshot["final_site_decision"]["interpretation"] == packet_case["decision"]
    token = JUDGE_EVIDENCE.set(
        EvidenceBinding.model_validate({k: snapshot[k] for k in EvidenceBinding.model_fields})
    )
    try:
        assessment = b.register_judge(opinion())
    finally:
        JUDGE_EVIDENCE.reset(token)
    with closing(SessionStore(b.project)) as store:
        restarted = Phase2Bridge(b.project, b.thread, store)
        assert restarted.judge_evidence() == snapshot
        card = restarted.decision_card(
            ApplyDecision(assessment_id=assessment.assessment_id, option_id="site")
        )
        assert card.judge_status == "DISCOURAGED"
        assert len(card.scientific_summary["independent_review"]["claim_corrections"]) == 2
        assert any("later clearance" in warning for warning in card.warnings)
        assert any("not a proven trafficking" in warning for warning in card.warnings)
        assert any("downstream unknowns" in item for item in card.limitations)
        with pytest.raises(AgentBoundaryError):
            store.respond(b.thread, card.card_id, "approve", "synthetic-human")
        assert restarted.current_site()["intent"] == packet_case["snapshot"]["proposal"]
        store.respond(
            b.thread,
            card.card_id,
            "override",
            "synthetic-human",
            explicit_acknowledgement="SYNTHETIC accepts the displayed scientific qualifications",
            optional_reason="SYNTHETIC proceed with this bounded hypothesis",
        )
        restarted.apply_decision(card)
        from easydesign.agent.design import DesignBridge

        downstream = DesignBridge(
            b.project, "synthetic-qualified-design", store
        ).read_design_evidence()
        assert (
            downstream["upstream_decision"]["judge_review"]
            == card.scientific_summary["independent_review"]
        )
        assert downstream["upstream_decision"]["warnings"] == card.warnings
        assert downstream["upstream_decision"]["limitations"] == card.limitations


@pytest.mark.parametrize("verdict", ["reject", "insufficient"])
def test_reject_or_insufficient_cannot_be_promoted_by_warning(packet_case, verdict):
    b = packet_case["bridge"]
    snapshot = b.judge_evidence()
    token = JUDGE_EVIDENCE.set(
        EvidenceBinding.model_validate({k: snapshot[k] for k in EvidenceBinding.model_fields})
    )
    try:
        assessment = b.register_judge(opinion().model_copy(update={"verdict": verdict}))
    finally:
        JUDGE_EVIDENCE.reset(token)
    with pytest.raises(AgentBoundaryError, match="reviewable Site"):
        b.decision_card(ApplyDecision(assessment_id=assessment.assessment_id, option_id="site"))


def test_corrections_cannot_invent_claims_or_leak_to_other_gates(packet_case):
    result = packet(packet_case)
    validate_judge_corrections(opinion(), result)
    bad = opinion().model_copy(
        update={
            "site_claim_corrections": [
                SiteClaimCorrection(
                    claim="fabricated quotation", qualification="SYNTHETIC limitation"
                )
            ]
        }
    )
    with pytest.raises(ResearchConclusionMismatch, match="exact current Site claim"):
        validate_judge_corrections(bad, result)
    with pytest.raises(ResearchConclusionMismatch, match="only to Gate 2"):
        validate_judge_corrections(opinion(), {**result, "gate_type": "target-structure"})
