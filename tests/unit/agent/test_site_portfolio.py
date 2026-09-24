"""Ranked Gate 2 selects exact kernel residues; fixtures are not biological validation."""

from copy import deepcopy
from typing import Any

import pytest

from easydesign.agent.contracts import (
    AgentBoundaryError,
    ApplyDecision,
    EvidenceBinding,
    JudgeVerdict,
    OptionRecommendation,
)
from easydesign.agent.phase2 import SITE_EVIDENCE, Phase2Bridge
from easydesign.agent.session_store import identity
from easydesign.agent.site_decision import (
    RankedSiteDecision,
    compile_site_decision,
    verified_location_conflict,
)
from easydesign.agent.site_dossier import persist_dossier
from easydesign.agent.site_judge import SiteJudgeUnavailable, create_site_judge
from easydesign.agent.tools import JUDGE_EVIDENCE
from tests.agent_support import scripted_config
from tests.unit.agent.test_site_dossier import bind, handoff
from tests.unit.agent.test_site_judge import CompactJudgeModel


def ranked_decision(candidate_ids: list[str]) -> RankedSiteDecision:
    return RankedSiteDecision(
        candidates=[
            {
                "candidate_id": candidate_id,
                "why_ranked": f"Relative priority {index + 1}; uncertain function.",
                "mechanistic_rationale": f"Mechanism hypothesis for {candidate_id}.",
                "approach_rationale": "Extracellular access and whole-binder clearance "
                "require validation.",
                "supporting_evidence": [
                    f"Candidate-specific supplied evidence for {candidate_id}."
                ],
                "major_risks": [f"Candidate-specific risk for {candidate_id}."],
                "uncertainty": [f"Binding untested for {candidate_id}."],
                "confidence": "low",
            }
            for index, candidate_id in enumerate(candidate_ids)
        ]
    )


def test_explicit_objective_and_verified_sidedness_block_only_hard_compartment_conflicts():
    from easydesign.agent.site_dossier import explicit_site_compartment

    assert explicit_site_compartment("为 NK2R 开展胞外抑制性 VHH 设计") == "extracellular"
    assert (
        explicit_site_compartment("Design an intracellular nanobody against the receptor")
        == "intracellular"
    )
    assert explicit_site_compartment("Compare extracellular and intracellular evidence") is None

    inner = {
        "segments": ["TM2", "TM3", "TM7"],
        "sequence_topology": [
            {
                "canonical_position": 68,
                "annotations": [{"type": "Topological domain", "description": "Cytoplasmic"}],
            }
        ],
        "membrane_geometry": [
            {"region": "inner_pore", "axial_distance": value}
            for value in (-18.8, -11.9, -10.5)
        ],
    }
    outer_pore = {
        "segments": ["TM2", "TM6", "TM7"],
        "sequence_topology": [],
        "membrane_geometry": [
            {"region": "outer_pore", "axial_distance": value}
            for value in (7.1, 10.2, 17.3)
        ],
    }
    ambiguous = {
        "segments": ["TM3"],
        "sequence_topology": [],
        "membrane_geometry": [{"region": "inner_pore", "axial_distance": -12.0}],
    }
    mixed_inner = {
        "segments": ["TM5", "ICL3", "TM6"],
        "sequence_topology": [
            {
                "canonical_position": position,
                "annotations": [
                    {"type": "Topological domain", "description": "Cytoplasmic"}
                ],
            }
            for position in (227, 228, 229)
        ],
        "membrane_geometry": [
            {"region": region, "axial_distance": axial}
            for region, axial in (
                ("inner_pore", -26.8),
                ("intracellular_tm_surface", -31.1),
                ("intracellular", -38.9),
            )
        ],
    }
    assert verified_location_conflict(inner, "extracellular") == (
        "verified-compartment-conflict"
    )
    assert verified_location_conflict(outer_pore, "extracellular") is None
    assert verified_location_conflict(ambiguous, "extracellular") is None
    assert verified_location_conflict(mixed_inner, "extracellular") == (
        "verified-compartment-conflict"
    )
    assert verified_location_conflict(inner, None) is None


def test_runtime_compartment_block_is_removed_from_abc_but_retained_for_audit(site_bridge):
    case = setup_portfolio(site_bridge)
    dossier = deepcopy(case["dossier"])
    blocked_id = dossier["candidate_comparison"][0]["candidate_id"]
    dossier["candidate_comparison"][0]["runtime_eligibility"] = {
        "status": "BLOCKED",
        "cause": "verified-compartment-conflict",
        "required_site_compartment": "extracellular",
    }
    intent = compile_site_decision(dossier, case["decision"])
    blocked = next(entry for entry in intent.portfolio if entry.candidate_id == blocked_id)
    assert blocked.rank is None
    assert not blocked.selectable
    assert blocked.hard_block == "verified-compartment-conflict"
    assert [entry.rank for entry in intent.portfolio] == ["A", "B", None]


def test_extracellular_deep_orthosteric_gpcr_candidate_must_rank_a(site_bridge):
    case = setup_portfolio(site_bridge)
    dossier = deepcopy(case["dossier"])
    dossier["objective_requirements"] = {
        "required_site_compartment": "extracellular",
    }
    dossier["receptor_context"] = [
        {
            "identity": {"status": "resolved"},
            "membrane": {"status": "resolved", "reliable": True},
        }
    ]
    dossier["approach_validation"] = {"status": "not-performed"}
    shallow, deep = dossier["candidate_comparison"][:2]
    shallow["research_hypothesis"]["name"] = "Peripheral ECL-only surface"
    shallow["research_hypothesis"]["rationale"] = (
        "Extracellular but does not form the orthosteric entrance."
    )
    shallow["location"] = {
        "membrane_geometry": [
            {
                "region": "outer_vestibule",
                "pore_lining": False,
                "axial_distance": 28.0,
            }
        ]
    }
    deep["research_hypothesis"]["name"] = "Deep extracellular orthosteric entrance"
    deep["research_hypothesis"]["rationale"] = (
        "Extends along the orthosteric outer pore; whole-VHH clearance is untested."
    )
    deep["location"] = {
        "membrane_geometry": [
            {
                "region": "outer_pore",
                "pore_lining": True,
                "axial_distance": 9.0,
            },
            {
                "region": "outer_pore",
                "pore_lining": True,
                "axial_distance": 16.0,
            },
        ]
    }

    with pytest.raises(AgentBoundaryError, match="GPCR_ORTHOSTERIC_A_REQUIRED"):
        compile_site_decision(dossier, case["decision"])

    corrected = case["decision"].model_copy(
        update={
            "candidates": [
                case["decision"].candidates[1],
                case["decision"].candidates[0],
                *case["decision"].candidates[2:],
            ]
        }
    )
    intent = compile_site_decision(dossier, corrected)
    assert intent.portfolio[0].candidate_id == deep["candidate_id"]
    assert intent.portfolio[0].rank == "A"


def test_ranked_advisory_avoidance_cannot_block_hard_valid_alternative(site_bridge):
    case = setup_portfolio(site_bridge)
    dossier = deepcopy(case["dossier"])
    valid_alternative = dossier["candidate_comparison"][1]
    blocked_candidate = dossier["candidate_comparison"][2]
    blocked_candidate["runtime_eligibility"] = {
        "status": "BLOCKED",
        "cause": "verified-compartment-conflict",
        "required_site_compartment": "extracellular",
    }
    constraint_ids = {
        item["design_label"]: item["residue_id"]
        for item in dossier["residue_constraints"]
    }
    valid_label = valid_alternative["research_hypothesis"]["hotspot_label_seq_ids"][0]
    blocked_label = blocked_candidate["research_hypothesis"]["hotspot_label_seq_ids"][0]
    decision = case["decision"].model_copy(
        update={
            "avoid_residue_ids": [
                constraint_ids[valid_label],
                constraint_ids[blocked_label],
            ]
        }
    )

    intent = compile_site_decision(dossier, decision)

    assert [entry.rank for entry in intent.portfolio] == ["A", "B", None]
    alternative = next(
        entry
        for entry in intent.portfolio
        if entry.candidate_id == valid_alternative["candidate_id"]
    )
    assert alternative.selectable
    assert alternative.hard_block is None
    assert intent.avoid_label_seq_ids == [blocked_label]


def test_phase2_registration_preserves_runtime_compartment_block(site_bridge):
    bridge = site_bridge
    bridge.store.thread(
        bridge.thread, "synthetic-runtime-blocked-portfolio", "SYNTHETIC structural exploration"
    )
    execution = bridge.store.begin_execution(bridge.thread, "SYNTHETIC runtime block review")
    token = bind(bridge)
    try:
        selection = handoff()
        selection = selection.model_copy(
            update={
                "candidates": [
                    selection.candidates[0].model_copy(
                        update={"hotspot_label_seq_ids": members}
                    )
                    for members in ([1, 2], [3, 4], [5, 6])
                ]
            }
        )
        dossier = deepcopy(persist_dossier(bridge, selection, execution["execution_id"]))
        blocked_id = dossier["candidate_comparison"][0]["candidate_id"]
        dossier["candidate_comparison"][0]["runtime_eligibility"] = {
            "status": "BLOCKED",
            "cause": "verified-compartment-conflict",
            "required_site_compartment": "extracellular",
        }
        ref = bridge.persist("site-evidence-dossier", dossier)
        bridge.store.event(
            bridge.thread,
            "site-evidence-dossier",
            {
                "execution_id": execution["execution_id"],
                "target_binding": dossier["target_binding"],
                "dossier_id": identity(dossier),
                "ref": ref,
                "chars": len(str(dossier)),
                "passage_count": len(dossier["focused_passages"]),
            },
        )
        decision = ranked_decision(
            [candidate["candidate_id"] for candidate in dossier["candidate_comparison"]]
        )
        intent = compile_site_decision(dossier, decision)
        bridge.store.event(
            bridge.thread,
            "site-decision",
            {
                "execution_id": execution["execution_id"],
                "decision": decision.model_dump(mode="json"),
                "dossier_ref": ref,
                "hydrated_intent_sha256": identity(intent.model_dump(mode="json")),
            },
        )
        bridge.register_site(intent, None)
        proposal = bridge.current_site()
        blocked = next(
            entry for entry in proposal["intent"]["portfolio"]
            if entry["candidate_id"] == blocked_id
        )
        assert blocked["rank"] is None
        assert not blocked["selectable"]
        assert blocked["hard_block"] == "verified-compartment-conflict"
        assert proposal["portfolio_evaluations"][blocked_id]["status"] == "BLOCKED"
    finally:
        SITE_EVIDENCE.reset(token)


def setup_portfolio(bridge: Any, labels: list[list[int]] | None = None) -> dict[str, Any]:
    bridge.store.thread(
        bridge.thread, "synthetic-ranked-portfolio", "SYNTHETIC structural exploration"
    )
    execution = bridge.store.begin_execution(bridge.thread, "SYNTHETIC ranked review")
    token = bind(bridge)
    try:
        selection = handoff()
        selection = selection.model_copy(
            update={
                "candidates": [
                    selection.candidates[0].model_copy(update={"hotspot_label_seq_ids": members})
                    for members in (labels or [[1, 2], [3, 4], [5, 6]])
                ]
            }
        )
        dossier = persist_dossier(bridge, selection, execution["execution_id"])
        decision = ranked_decision(
            [candidate["candidate_id"] for candidate in dossier["candidate_comparison"]]
        )
        intent = compile_site_decision(dossier, decision)
        bridge.store.event(
            bridge.thread,
            "site-decision",
            {
                "execution_id": execution["execution_id"],
                "decision": decision.model_dump(mode="json"),
                "dossier_ref": bridge.thread_latest("site-evidence-dossier")["ref"],
                "hydrated_intent_sha256": identity(intent.model_dump(mode="json")),
            },
        )
        bridge.register_site(intent, None)
        return {"dossier": dossier, "decision": decision, "intent": intent, "execution": execution}
    finally:
        SITE_EVIDENCE.reset(token)


def review_card(bridge: Any, verdict: str = "reject") -> Any:
    packet = bridge.judge_evidence()
    token = JUDGE_EVIDENCE.set(
        EvidenceBinding.model_validate({key: packet[key] for key in EvidenceBinding.model_fields})
    )
    try:
        assessment = bridge.register_judge(
            JudgeVerdict.model_validate(
                {
                    "verdict": verdict,
                    "reasons": [
                        "Ranking remains uncertain; poor exposure is a scientific concern."
                    ],
                    "limitations": ["No experimental binding evidence."],
                    "recommendation": OptionRecommendation(
                        option_id="site",
                        status="DISCOURAGED",
                        warnings=["All candidates have substantial scientific risk."],
                        alternative="Scientist may choose B for a different mechanism.",
                    ),
                }
            )
        )
    finally:
        JUDGE_EVIDENCE.reset(token)
    return bridge.decision_card(
        ApplyDecision(assessment_id=assessment.assessment_id, option_id="site")
    )


@pytest.mark.parametrize("rank", ["A", "B", "C"])
def test_any_valid_rank_approves_exact_kernel_residues_and_downstream_context(site_bridge, rank):
    bridge = site_bridge
    case = setup_portfolio(bridge)
    original = deepcopy(bridge.current_site())
    card = review_card(bridge)
    assert [option["rank"] for option in card.options] == ["A", "B", "C"]
    assert all(option["eligible"] for option in card.options)
    assert card.scientific_summary["independent_review"]["verdict"] == "reject"
    chosen = next(option for option in card.options if option["rank"] == rank)
    assert bridge.approved_site() is None  # Highlighting A is not approval.
    bridge.store.respond(
        bridge.thread,
        card.card_id,
        "approve",
        "synthetic-scientist",
        selected_option_id=chosen["option_id"],
    )
    result = bridge.apply_decision(card)
    assert result["site"]["hotspot_label_seq_ids"] == chosen["design_labels"]
    restarted = Phase2Bridge(bridge.project, bridge.thread, bridge.store)
    assert restarted.apply_decision(card) == result
    approved = restarted.approved_site()
    assert approved["hotspots"]["hotspot_sets"][0]["label_seq_ids"] == chosen["design_labels"]
    assert approved["hotspots"]["hotspot_sets"][0]["id"] == rank
    assert approved["proposal"]["intent"]["mechanistic_rationale"] == chosen["mechanism"]
    assert (
        approved["proposal"]["intent"]["risks"]
        == case["intent"].portfolio["ABC".index(rank)].major_risks
    )
    from easydesign.agent.site_contracts import SiteIntent

    SiteIntent.model_validate(approved["proposal"]["intent"])
    assert chosen["uncertainty"][0] in approved["limitations"]
    for option in card.options:
        if option["option_id"] != chosen["option_id"]:
            assert option["uncertainty"][0] not in approved["limitations"]
    assert bridge.current_site() == original
    from easydesign.agent.design import DesignBridge

    downstream = DesignBridge(
        bridge.project, "synthetic-downstream", bridge.store
    ).read_design_evidence()
    assert downstream["approved_hotspots"][0]["label_seq_ids"] == chosen["design_labels"]
    assert downstream["site_rationale"]["positive_evidence"] == chosen["supporting_evidence"]
    assert downstream["site_rationale"]["risks"] == approved["proposal"]["intent"]["risks"]
    assert {
        tuple(alternative["hotspot_label_seq_ids"])
        for alternative in downstream["site_rationale"]["alternatives"]
    } == {
        tuple(option["design_labels"])
        for option in card.options
        if option["option_id"] != chosen["option_id"]
    }
    with pytest.raises(AgentBoundaryError, match="Conflicting duplicate"):
        other = next(option for option in card.options if option["rank"] != rank)
        bridge.store.respond(
            bridge.thread,
            card.card_id,
            "approve",
            "synthetic-scientist",
            selected_option_id=other["option_id"],
        )


def test_invalid_candidate_is_disabled_without_poisoning_valid_candidates(site_bridge):
    setup_portfolio(site_bridge, [[999], [3, 4], [5, 6]])
    original = deepcopy(site_bridge.current_site())
    card = review_card(site_bridge)
    assert [option["rank"] for option in card.options] == ["A", "B", None]
    assert card.options[-1]["design_labels"] == [999]
    assert card.options[-1]["runtime_residue_facts"] == []
    for candidate in ["invented", card.options[-1]["option_id"]]:
        with pytest.raises(AgentBoundaryError, match="selectable candidate"):
            site_bridge.store.respond(
                site_bridge.thread,
                card.card_id,
                "approve",
                "synthetic-scientist",
                selected_option_id=candidate,
            )
    selected = card.options[1]
    site_bridge.store.respond(
        site_bridge.thread,
        card.card_id,
        "approve",
        "synthetic-scientist",
        selected_option_id=selected["option_id"],
    )
    assert site_bridge.apply_decision(card)["site"]["hotspot_label_seq_ids"] == [5, 6]
    from easydesign.agent.design import DesignBridge
    from easydesign.agent.site_contracts import SiteIntent

    downstream = DesignBridge(
        site_bridge.project, "synthetic-blocked-backup", site_bridge.store
    ).read_design_evidence()
    assert downstream["approved_hotspots"][0]["label_seq_ids"] == [5, 6]
    assert [
        alternative["hotspot_label_seq_ids"]
        for alternative in downstream["site_rationale"]["alternatives"]
    ] == [[3, 4]]
    assert all(
        alternative["role"] == "backup"
        for alternative in downstream["site_rationale"]["alternatives"]
    )
    SiteIntent.model_validate(downstream["site_rationale"])
    approved = site_bridge.approved_site()
    assert approved["proposal"]["ranked_portfolio"] == original["intent"]["portfolio"]
    blocked = approved["proposal"]["ranked_portfolio"][-1]
    assert blocked["site"]["hotspot_label_seq_ids"] == [999]
    assert not blocked["selectable"] and blocked["hard_block"]
    assert site_bridge.current_site() == original


def test_omitting_candidate_or_forging_structured_facts_is_rejected(site_bridge):
    case = setup_portfolio(site_bridge)
    decision = case["decision"].model_copy(update={"candidates": case["decision"].candidates[:1]})
    with pytest.raises(AgentBoundaryError, match="every supplied candidate"):
        compile_site_decision(case["dossier"], decision)
    from easydesign.agent.contracts import JudgeFactClaim
    from easydesign.agent.site_fact_integrity import validate_fact_fields

    packet = site_bridge.judge_evidence()
    with pytest.raises(AgentBoundaryError):
        validate_fact_fields(
            [], [JudgeFactClaim(fact_ref="candidate:0", field="design_labels", value=[999])], packet
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("failures", [0, 1, 3])
async def test_compact_review_recovery_and_unavailable_preserve_ranking(site_bridge, failures):
    from langchain_core.messages import HumanMessage

    case = setup_portfolio(site_bridge)
    before = deepcopy(site_bridge.current_site()["intent"]["portfolio"])
    packet = site_bridge.judge_evidence()
    token = JUDGE_EVIDENCE.set(
        EvidenceBinding.model_validate({key: packet[key] for key in EvidenceBinding.model_fields})
    )
    model = CompactJudgeModel(role="judge", failures=failures)
    try:
        judge = create_site_judge(
            site_bridge, model, scripted_config(), case["execution"]["execution_id"]
        )
        if failures == 3:
            with pytest.raises(SiteJudgeUnavailable):
                await judge.ainvoke({"messages": [HumanMessage(content="Review portfolio.")]})
            from easydesign.agent.site_review_availability import record_unavailable

            failure = record_unavailable(site_bridge, case["execution"]["execution_id"])
            args = ApplyDecision(review_failure_id=failure["record_id"], option_id="site")
        else:
            await judge.ainvoke({"messages": [HumanMessage(content="Review portfolio.")]})
            assessment = site_bridge.thread_latest("judge-assessment")
            args = ApplyDecision(assessment_id=assessment["assessment_id"], option_id="site")
    finally:
        JUDGE_EVIDENCE.reset(token)
    card = site_bridge.decision_card(args)
    assert site_bridge.current_site()["intent"]["portfolio"] == before
    assert model.calls == min(failures + 1, 3)
    assert (card.assessment_id is None) == (failures == 3)
    chosen = card.options[1]
    site_bridge.store.respond(
        site_bridge.thread,
        card.card_id,
        "approve",
        "synthetic-scientist",
        selected_option_id=chosen["option_id"],
    )
    assert site_bridge.apply_decision(card)["site"]["hotspot_label_seq_ids"] == [3, 4]


def test_all_invalid_candidates_produce_a_disabled_portfolio_without_jobs(site_bridge, capsys):
    from easydesign.agent.cli import _display

    before = len(site_bridge.controller.list(project_id=site_bridge.project_id))
    setup_portfolio(site_bridge, [[998], [999]])
    card = review_card(site_bridge, "insufficient")
    assert all(not option["eligible"] and option["rank"] is None for option in card.options)
    assert len(site_bridge.controller.list(project_id=site_bridge.project_id)) == before
    _display({"status": "awaiting-human-approval", "card": card.model_dump(mode="json")})
    assert '"default_option": null' in capsys.readouterr().out
    with pytest.raises(AgentBoundaryError):
        site_bridge.store.respond(
            site_bridge.thread, card.card_id, "approve", "synthetic-scientist"
        )


def test_explicit_compartment_and_exclusion_block_only_affected_candidate(site_bridge, tmp_path):
    import yaml

    context = tmp_path / "explicit-biology.yaml"
    context.write_text(
        yaml.safe_dump(
            {
                "target_auth_chain": "A",
                "target_kind": "gpcr",
                "required_site_compartment": "extracellular",
                "topology": [
                    {"label_seq_id": 1, "segment": "ICL1"},
                    {"label_seq_id": 2, "segment": "ICL1"},
                ],
                "features": [
                    {
                        "kind": "exclude",
                        "label_seq_ids": [3],
                        "description": "Explicit excluded scope",
                        "source": "SYNTHETIC user input",
                    }
                ],
            }
        )
    )
    site_bridge.import_biology(context)
    setup_portfolio(site_bridge)
    card = review_card(site_bridge)
    assert [option["design_labels"] for option in card.options if option["eligible"]] == [[5, 6]]
    assert {option["hard_block"] for option in card.options if not option["eligible"]} == {
        "explicit-compartment-conflict",
        "explicit-excluded-region",
    }
    site_bridge.store.respond(site_bridge.thread, card.card_id, "approve", "synthetic-scientist")
    assert site_bridge.apply_decision(card)["site"]["hotspot_label_seq_ids"] == [5, 6]


def test_ranked_negative_review_routes_to_scientist_and_stale_context_blocks_approval(
    site_bridge, tmp_path
):
    import yaml

    from easydesign.agent.control_flow import next_action

    setup_portfolio(site_bridge)
    card = review_card(site_bridge, "insufficient")
    assert next_action(site_bridge).stage == "scientist-gate"
    selected = card.options[1]
    site_bridge.store.respond(
        site_bridge.thread,
        card.card_id,
        "approve",
        "synthetic-scientist",
        selected_option_id=selected["option_id"],
    )
    context = tmp_path / "new-biology.yaml"
    context.write_text(
        yaml.safe_dump({"target_auth_chain": "A", "limitations": ["SYNTHETIC changed context"]})
    )
    site_bridge.import_biology(context)
    with pytest.raises(AgentBoundaryError, match="changed"):
        site_bridge.apply_decision(card)
    assert site_bridge.approved_site() is None


@pytest.mark.parametrize("point", ["before_site_approval", "after_site_approval"])
def test_rank_b_resume_after_approval_crash_does_not_duplicate_or_switch_candidate(
    site_bridge, monkeypatch, point
):
    setup_portfolio(site_bridge)
    card = review_card(site_bridge)
    selected = card.options[1]
    site_bridge.store.respond(
        site_bridge.thread,
        card.card_id,
        "approve",
        "synthetic-scientist",
        selected_option_id=selected["option_id"],
    )

    def crash(name):
        if name == point:
            raise RuntimeError("SYNTHETIC crash")

    monkeypatch.setattr(site_bridge, "failpoint", crash)
    with pytest.raises(RuntimeError, match="SYNTHETIC crash"):
        site_bridge.apply_decision(card)
    resumed = Phase2Bridge(site_bridge.project, site_bridge.thread, site_bridge.store)
    if point == "before_site_approval":
        from easydesign.agent.contracts import ReconciliationRequired

        with pytest.raises(ReconciliationRequired):
            resumed.apply_decision(card)
        assert resumed.approved_site() is None
        assert (
            resumed.store.response(resumed.thread, card.card_id)["outcome"]["selected_option_id"]
            == selected["option_id"]
        )
        return
    result = resumed.apply_decision(card)
    assert result["site"]["hotspot_label_seq_ids"] == [3, 4]
    assert resumed.apply_decision(card) == result
    assert (
        len(
            [
                event
                for event in resumed.store.events(resumed.thread)
                if event["kind"] == "site-approved"
            ]
        )
        == 1
    )


def test_reordering_preserves_candidate_ids_and_invalidates_old_card(site_bridge):
    from easydesign.agent.site_decision import hydrate_site_decision

    case = setup_portfolio(site_bridge)
    old_card = review_card(site_bridge)
    decision = case["decision"].model_copy(
        update={"candidates": list(reversed(case["decision"].candidates))}
    )
    token = bind(site_bridge)
    try:
        intent = hydrate_site_decision(site_bridge, decision, case["execution"]["execution_id"])
        site_bridge.store.event(
            site_bridge.thread,
            "site-decision",
            {
                "execution_id": case["execution"]["execution_id"],
                "decision": decision.model_dump(mode="json"),
                "dossier_ref": site_bridge.thread_latest("site-evidence-dossier")["ref"],
                "hydrated_intent_sha256": identity(intent.model_dump(mode="json")),
            },
        )
        site_bridge.register_site(intent, None)
    finally:
        SITE_EVIDENCE.reset(token)
    new_card = review_card(site_bridge)
    assert [option["option_id"] for option in new_card.options] == list(
        reversed([option["option_id"] for option in old_card.options])
    )
    assert new_card.request_identity != old_card.request_identity
    site_bridge.store.respond(
        site_bridge.thread, old_card.card_id, "approve", "synthetic-scientist"
    )
    with pytest.raises(AgentBoundaryError, match="changed"):
        site_bridge.apply_decision(old_card)
    assert site_bridge.approved_site() is None


def test_justified_tie_is_explicit_without_omitting_candidates(site_bridge):
    case = setup_portfolio(site_bridge)
    value = case["decision"].model_dump(mode="json")
    value["candidates"][1].update(
        tied_with_previous=True,
        tie_reason="SYNTHETIC missing comparable orientation measurement separates neither site.",
    )
    intent = compile_site_decision(case["dossier"], RankedSiteDecision.model_validate(value))
    assert [entry.rank for entry in intent.portfolio] == ["A", "B", "C"]
    assert [entry.preference_group for entry in intent.portfolio] == [1, 1, 2]
    assert intent.portfolio[1].tied_with_candidate_id == intent.portfolio[0].candidate_id
    assert all(entry.selectable for entry in intent.portfolio)
    from pydantic import ValidationError

    value["candidates"][1]["tie_reason"] = None
    with pytest.raises(ValidationError, match="missing discriminator"):
        RankedSiteDecision.model_validate(value)


@pytest.mark.parametrize("rank", ["B", "C"])
def test_alternative_selection_reaches_real_strategy_compiler(
    site_bridge, monkeypatch, tmp_path, rank
):
    import yaml

    from easydesign.agent.design import DesignBridge
    from tests.agent_phase2_support import configure_offline_validation
    from tests.unit.agent.test_design_runtime import propose_design

    setup_portfolio(site_bridge)
    card = review_card(site_bridge)
    chosen = next(option for option in card.options if option["rank"] == rank)
    site_bridge.store.respond(
        site_bridge.thread,
        card.card_id,
        "approve",
        "synthetic-scientist",
        selected_option_id=chosen["option_id"],
    )
    site_bridge.apply_decision(card)
    configure_offline_validation(monkeypatch, tmp_path)
    downstream = DesignBridge(site_bridge.project, "synthetic-compiler", site_bridge.store)
    result = propose_design(downstream)
    assert result["evaluation"]["status"] == "SUPPORTED"
    proposal = downstream.current_design()
    strategy = downstream.document(proposal["spec_ref"])
    assert strategy  # Artifact is read through its verified binding.
    yaml_strategy = yaml.safe_load(
        (downstream.project / proposal["strategy_ref"]["relative_path"]).read_text()
    )
    assert all(variant["hotspot_set_id"] == rank for variant in yaml_strategy["variants"])
    designs = [
        ref
        for ref in downstream.document(proposal["compiled_ref"])
        if ref["relative_path"].endswith("/design.yaml")
    ]
    assert len(designs) == 7
    for ref in designs:
        payload = yaml.safe_load((downstream.project / ref["relative_path"]).read_text())
        bindings = []

        def collect(value):
            found = []
            if isinstance(value, dict):
                if "binding" in value:
                    found.append(value["binding"])
                for child in value.values():
                    found.extend(collect(child))
            elif isinstance(value, list):
                for child in value:
                    found.extend(collect(child))
            return found

        bindings = collect(payload)
        assert bindings == [",".join(map(str, chosen["design_labels"]))]
    assert downstream.approved_design() is None  # No Gate 3 approval or generation.


def test_ranked_site_can_reach_scientist_gate_without_routine_judge(
    site_bridge: Any, monkeypatch: Any
) -> None:
    bridge = site_bridge
    setup_portfolio(bridge)
    from easydesign.agent import site_review_policy
    from easydesign.agent.control_flow import next_action

    policy = {
        "policy_id": site_review_policy.SITE_REVIEW_POLICY,
        "required": False,
        "reasons": [],
    }
    monkeypatch.setattr(site_review_policy, "site_review_requirement", lambda *_: policy)
    action = next_action(bridge)
    assert action.tool == "request_scientific_decision"
    assert action.arguments == {"review_not_requested": True, "option_id": "site"}
    card = bridge.decision_card(ApplyDecision(**action.arguments))
    review = card.scientific_summary["independent_review"]
    assert card.assessment_id is None
    assert card.judge_status is None
    assert review == {
        **review,
        "availability": "not-requested",
        "optional": True,
        "policy_id": site_review_policy.SITE_REVIEW_POLICY,
    }
    assert [option["rank"] for option in card.options] == ["A", "B", "C"]
