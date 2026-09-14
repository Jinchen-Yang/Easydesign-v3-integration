"""Saved live187 regressions; fixtures do not authorize scientific acceptance."""

import json
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from easydesign.agent.contracts import ResearchConclusionMismatch
from easydesign.agent.harness import skill_root
from easydesign.agent.phase2 import SITE_EVIDENCE
from easydesign.agent.site_authority import disulfide_assignments, sequence_topology
from easydesign.agent.site_decision import compile_site_decision, decision_working_set
from easydesign.agent.site_dossier import persist_dossier
from tests.agent_support import scripted_config
from tests.unit.agent.test_site_decision import decision
from tests.unit.agent.test_site_dossier import bind, handoff


@pytest.mark.asyncio
@pytest.mark.parametrize("exhausted", [False, True])
@pytest.mark.parametrize("native_error", [False, True])
async def test_saved_replay_bounds_incomplete_output_without_promoting_it_to_evidence(
    exhausted, native_error
):
    from easydesign.agent.contracts import AgentBoundaryError
    from easydesign.agent.site_decision import SiteDecision
    from scripts.replay_site_decision import ReplayBoundary

    class Request(SimpleNamespace):
        def override(self, **values):
            return Request(**{**vars(self), **values})

    messages = [HumanMessage(content="SYNTHETIC fixed scientific evidence")]
    request = Request(
        model=SimpleNamespace(profile={}),
        messages=messages,
        system_message=SystemMessage(content="SYNTHETIC typed decision"),
    )
    boundary = ReplayBoundary(SiteDecision, scripted_config(), "site", None)
    calls = []

    async def handler(current):
        calls.append(current)
        assert current.messages == messages
        if exhausted or len(calls) == 1:
            return SimpleNamespace(
                result=[
                    AIMessage(content="x" * 80000, response_metadata={"stop_reason": "max_tokens"})
                ]
                + (
                    [ToolMessage(content="SYNTHETIC schema error", tool_call_id="bad")]
                    if native_error
                    else []
                ),
                structured_response=None,
            )
        return SimpleNamespace(result=[AIMessage(content="")], structured_response=decision())

    if exhausted:
        with pytest.raises(AgentBoundaryError, match="two contract corrections"):
            await boundary.awrap_model_call(request, handler)
        assert len(calls) == 3
    else:
        result = await boundary.awrap_model_call(request, handler)
        assert result.structured_response == decision()
        assert len(calls) == 2
        assert "Correction required" in calls[1].system_message.text


@pytest.mark.asyncio
@pytest.mark.parametrize("exhausted", [False, True])
async def test_native_synthesis_schema_repair_keeps_dossier_and_original_budget(
    site_bridge, exhausted
):
    from easydesign.agent.contracts import AgentBoundaryError
    from easydesign.agent.harness import RoleBoundary
    from easydesign.agent.session_store import compact
    from tests.unit.agent.test_site_portfolio import ranked_decision

    bridge = site_bridge
    execution = bridge.store.begin_execution(bridge.thread, "SYNTHETIC isolated native repair")
    token = bind(bridge)
    try:
        dossier = persist_dossier(bridge, handoff(), execution["execution_id"])
        chosen = ranked_decision([dossier["candidate_comparison"][0]["candidate_id"]])
        guard = RoleBoundary(
            bridge,
            "site",
            scripted_config(),
            "SYNTHETIC choose supplied site",
            execution_id=execution["execution_id"],
            site_stage="synthesis",
        )

        class Request(SimpleNamespace):
            def override(self, **values):
                return Request(**{**vars(self), **values})

        messages = [HumanMessage(content=compact(decision_working_set(dossier)))]
        request = Request(
            model=SimpleNamespace(profile={}),
            tools=[],
            messages=messages,
            model_settings={},
            system_message=SystemMessage(content="SYNTHETIC synthesis"),
        )
        calls = []

        async def handler(current):
            calls.append(current)
            assert current.messages[: len(messages)] == messages
            assert all(isinstance(message, HumanMessage) for message in current.messages)
            assert all("x" * 80000 not in message.content for message in current.messages)
            if exhausted or len(calls) == 1:
                diagnostic = guard.contract_error("SYNTHETIC missing RankedSiteDecision fields")
                return SimpleNamespace(
                    result=[
                        AIMessage(
                            content="x" * 80000,
                            tool_calls=[{"name": "RankedSiteDecision", "args": {}, "id": "bad"}],
                            response_metadata={"stop_reason": "max_tokens"},
                        ),
                        ToolMessage(content=diagnostic, tool_call_id="bad"),
                    ],
                    structured_response=None,
                )
            return SimpleNamespace(
                result=[
                    AIMessage(
                        content="",
                        tool_calls=[
                            {
                                "name": "RankedSiteDecision",
                                "args": chosen.model_dump(),
                                "id": "good",
                            }
                        ],
                    )
                ],
                structured_response=chosen,
            )

        if exhausted:
            with pytest.raises(AgentBoundaryError, match="repair budget exhausted"):
                await guard.awrap_model_call(request, handler)
            assert len(calls) == 3
        else:
            assert (await guard.awrap_model_call(request, handler)).structured_response == chosen
            assert len(calls) == 2
        events = bridge.store.events(bridge.thread)
        assert len([e for e in events if e["kind"] == "contract-repair"]) == (2 if exhausted else 1)
        assert len([e for e in events if e["kind"] == "model-call"]) == len(calls)
        assert bridge.current_site() is None
    finally:
        SITE_EVIDENCE.reset(token)


def saved_annotations() -> dict[str, Any]:
    path = Path(__file__).parents[2] / "fixtures/agent/phase2_live187_contract_evidence.json"
    return json.loads(path.read_text())


def test_live187_compatible_disulfides_are_not_conflicting_facts() -> None:
    record = saved_annotations()
    result = disulfide_assignments(record["features"])
    assert result["pairs"] == [[106, 191], [184, 190]]
    assert result["multiple_partner_annotations"] == {}
    alternate = deepcopy(next(f for f in record["features"] if f["type"] == "Disulfide bond"))
    alternate["location"]["end"]["value"] = 184
    conflicting = disulfide_assignments([*record["features"], alternate])
    assert conflicting["multiple_partner_annotations"]["106"] == [184, 191]


def test_live187_intracellular_domain_cannot_be_relabelled_by_scan_name() -> None:
    rows = sequence_topology([223, 227, 266, 274, 299, 304], [saved_annotations()])
    assert [r["annotations"][0]["description"] for r in rows] == [
        "Cytoplasmic",
        "Cytoplasmic",
        "Cytoplasmic",
        "Cytoplasmic",
        "Extracellular",
        "Extracellular",
    ]
    assert sequence_topology([None], [saved_annotations()])[0]["annotations"] == []


def test_unperformed_whole_vhh_validation_remains_unresolved_at_judge(site_bridge: Any) -> None:
    b = site_bridge
    execution = b.store.begin_execution(b.thread, "SYNTHETIC whole-VHH boundary")
    token = bind(b)
    try:
        dossier = persist_dossier(b, handoff(), execution["execution_id"])
        working = decision_working_set(dossier)
        assert working["approach_validation"]["status"] == "not-performed"
        assert working["approach_validation"]["scientific_status"] == "UNRESOLVED"
        intent = compile_site_decision(
            dossier, decision(dossier["candidate_comparison"][0]["candidate_id"])
        )
        snapshot = b.register_site(intent, None)
        assert (
            snapshot["site_dossier_facts"]["approach_validation"] == dossier["approach_validation"]
        )
        # Judge must receive the calculation boundary and explicit qualification instruction,
        # rather than a deterministic parser purporting to prove arbitrary scientific prose.
        prompt = (skill_root() / "evidence-judge/SKILL.md").read_text()
        assert "site_claim_corrections" in prompt
        assert "without automatically blocking" in prompt
        assert "point exposure or pore geometry" in prompt
        assert "reference_annotations" in prompt
        assert "distinct" in prompt.lower()
    finally:
        SITE_EVIDENCE.reset(token)


def test_selected_hotspot_conflicts_with_declared_avoid_residues(site_bridge: Any) -> None:
    b = site_bridge
    execution = b.store.begin_execution(b.thread, "SYNTHETIC mutually exclusive selection")
    token = bind(b)
    try:
        dossier = persist_dossier(b, handoff(), execution["execution_id"])
        selected = decision(dossier["candidate_comparison"][0]["candidate_id"])
        excluded = dossier["residue_constraints"][0]["residue_id"]
        selected = selected.model_copy(update={"avoid_residue_ids": [excluded]})
        with pytest.raises(ResearchConclusionMismatch, match="conflicts with declared avoid"):
            compile_site_decision(dossier, selected)
        assert b.current_site() is None
    finally:
        SITE_EVIDENCE.reset(token)


def test_research_preference_and_topic_are_not_rehydrated_authority(site_bridge: Any) -> None:
    b = site_bridge
    execution = b.store.begin_execution(b.thread, "SYNTHETIC ownership")
    token = bind(b)
    try:
        preliminary = handoff().model_copy(
            update={
                "research_notes": [
                    "UNACCEPTED marker: sasa-candidate-0002 is extracellular ECL3/TM5-top"
                ],
                "unresolved_questions": ["UNACCEPTED marker: incompatible disulfide pairs"],
            }
        )
        dossier = persist_dossier(b, preliminary, execution["execution_id"])
        chosen = decision(dossier["candidate_comparison"][0]["candidate_id"])
        original = compile_site_decision(dossier, chosen).model_dump(mode="json")
        hypothesis = dossier["candidate_comparison"][0]["research_hypothesis"]
        hypothesis.update(
            name="WRONG intracellular called extracellular", rationale="WRONG", role="avoid"
        )
        assert compile_site_decision(dossier, chosen).model_dump(mode="json") == original
        assert not {"material_questions", "research_conclusions"} & original.keys()
        intent = compile_site_decision(dossier, chosen)
        snapshot = b.register_site(intent, None)
        assert "UNACCEPTED marker" not in json.dumps(snapshot)
        retained = b.document(b.thread_latest("site-evidence-dossier")["ref"])
        assert "UNACCEPTED marker" in json.dumps(retained["research_opinions"])
        research = b.document(b.current_site()["research_ref"])
        assert "decision_basis" not in research and "conclusions" not in research
    finally:
        SITE_EVIDENCE.reset(token)


def test_rejected_scientific_premise_cannot_become_gate_readiness(site_bridge: Any) -> None:
    from easydesign.agent.contracts import (
        AgentBoundaryError,
        ApplyDecision,
        EvidenceBinding,
        JudgeVerdict,
    )
    from easydesign.agent.tools import JUDGE_EVIDENCE
    from tests.unit.agent.test_site_runtime import propose

    b = site_bridge
    propose(b)
    snapshot = b.judge_evidence()
    token = JUDGE_EVIDENCE.set(
        EvidenceBinding.model_validate({key: snapshot[key] for key in EvidenceBinding.model_fields})
    )
    try:
        assessment = b.register_judge(
            JudgeVerdict(
                verdict="reject",
                reasons=["SYNTHETIC unsupported categorical access claim"],
                limitations=["Whole-binder clearance was not performed"],
                recommendation={
                    "option_id": "site",
                    "status": "DISCOURAGED",
                    "warnings": ["False premise needs correction"],
                    "alternative": "Revise the interpretation",
                },
            )
        )
    finally:
        JUDGE_EVIDENCE.reset(token)
    with pytest.raises(AgentBoundaryError, match="reviewable Site question"):
        b.decision_card(ApplyDecision(assessment_id=assessment.assessment_id, option_id="site"))
    assert b.approved_site() is None
