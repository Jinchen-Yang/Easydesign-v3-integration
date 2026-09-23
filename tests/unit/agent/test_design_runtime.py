from typing import Any

import pytest
import yaml

from easydesign.agent.contracts import (
    AgentBoundaryError,
    ApplyDecision,
    EvidenceBinding,
    JudgeVerdict,
)
from easydesign.agent.design import BINDER_EVIDENCE, DesignBridge
from easydesign.agent.design_contracts import BinderIntent
from easydesign.agent.session_store import SessionStore, identity
from easydesign.agent.tools import JUDGE_EVIDENCE


def binder_intent(**arm_changes: Any) -> BinderIntent:
    arm = {
        "name": "focused",
        "hypothesis": "Approved hotspot conditioning provides a geometric starting hypothesis.",
        "rationale": "Test one focused condition without claiming biological success.",
        "expected_result": (
            "Later pilot will test whether candidates retain the intended contact region."
        ),
        "failure_interpretation": (
            "A failed later pilot could challenge approach or generator "
            "compatibility, not prove no binding."
        ),
        "role": "baseline",
        "changed_factors": ["Approved hotspot conditioning"],
        "held_constant": [
            "Approved target/site",
            "All seven official VHH scaffolds",
            "40 candidates per scaffold",
        ],
        **arm_changes,
    }
    return BinderIntent.model_validate(
        {
            "binder": "VHH",
            "objective": "Freeze one exploratory VHH design strategy",
            "approach_rationale": (
                "Solvent-facing approach is a hypothesis, not a verified docking trajectory."
            ),
            "context_rationale": "Retain the full prepared target to avoid adding crop termini.",
            "scaffold_cdr_rationale": (
                "Retain official template and CDR settings across all seven scaffolds."
            ),
            "arms": [arm],
            "risks": [],
            "uncertainty": ["No candidate or binding result exists yet."],
            "recommendation": "SUPPORTED",
        }
    )


def propose_design(
    bridge: Any, intent: BinderIntent | None = None, revision: Any = None
) -> dict[str, Any]:
    evidence = bridge.read_design_evidence()
    token = BINDER_EVIDENCE.set(
        EvidenceBinding.model_validate({k: evidence[k] for k in EvidenceBinding.model_fields})
    )
    try:
        return bridge.register_design(intent or binder_intent(), revision)
    finally:
        BINDER_EVIDENCE.reset(token)


def design_card(bridge: Any) -> Any:
    evidence = bridge.judge_evidence()
    token = JUDGE_EVIDENCE.set(
        EvidenceBinding.model_validate({k: evidence[k] for k in EvidenceBinding.model_fields})
    )
    try:
        assessment = bridge.register_judge(
            JudgeVerdict(
                verdict="ready-to-ask",
                reasons=["Compiler-validated scientific hypothesis is reviewable."],
                limitations=["Validation is not experimental binding evidence."],
            )
        )
    finally:
        JUDGE_EVIDENCE.reset(token)
    return bridge.decision_card(
        ApplyDecision(assessment_id=assessment.assessment_id, option_id="design")
    )


def test_binder_and_judge_require_delegated_snapshot(design_bridge: Any) -> None:
    bridge = design_bridge
    with pytest.raises(AgentBoundaryError, match="runtime-delegated"):
        bridge.register_design(binder_intent())
    with pytest.raises(AgentBoundaryError):
        bridge.register_judge(
            JudgeVerdict(
                verdict="ready-to-ask",
                reasons=["Forged coordinator pass"],
                limitations=["Unbound opinion"],
            )
        )
    with pytest.raises(AgentBoundaryError):
        bridge.decision_card(ApplyDecision(assessment_id="invented", option_id="design"))
    assert bridge.current_design() is None


def test_approved_site_exclusions_bind_and_survive_downstream_compilation(
    design_bridge, monkeypatch
):
    from copy import deepcopy

    bridge = design_bridge
    original = bridge.read_design_evidence()["evidence_id"]
    approved = deepcopy(bridge.approved_site())
    approved["proposal"]["intent"]["avoid_label_seq_ids"] = [5]
    monkeypatch.setattr(bridge, "approved_site", lambda: approved)
    current = bridge.read_design_evidence()
    assert current["evidence_id"] != original
    assert current["approved_exclusions"] == [5]
    result = propose_design(bridge)
    assert result["evaluation"]["status"] == "SUPPORTED", result["evaluation"]
    proposal = bridge.current_design()
    specification = bridge.document(proposal["spec_ref"])
    assert specification["intent"]["arms"][0]["avoid_label_seq_ids"] == [5]
    strategy = yaml.safe_load(
        (bridge.project / proposal["strategy_ref"]["relative_path"]).read_text()
    )
    assert all(variant["avoid_label_seq_ids"] == [5] for variant in strategy["variants"])


def test_existing_compiler_and_freeze_service_no_pilot(
    design_bridge: Any, monkeypatch: Any, capsys: Any
) -> None:
    import json

    from easydesign.agent.cli import _display

    bridge = design_bridge
    constraints = bridge.read_design_evidence()["constraints"]
    assert constraints["scaffold_evidence_authority"]["official_asset_checksums_verified"] is True
    assert set(constraints["supports"]) == {"binding", "not_binding", "target_crop", "cdr_override"}
    original_target = bridge.target_state()["binding"]
    original_site = bridge.approved_site()["hotspots_sha256"]
    target, _, facts_ref = bridge.site_facts()
    assert bridge.read_design_evidence()["evidence_id"] == identity(
        {"target": target["binding"], "hotspot": original_site, "facts": facts_ref}
    )
    result = propose_design(bridge, binder_intent(name="Focused-HotspotA"))
    assert result["evaluation"]["status"] == "SUPPORTED", result["evaluation"]
    assert result["evaluation"]["compiled_strategy_count"] == 7
    proposal = bridge.current_design()
    strategy = yaml.safe_load(
        (bridge.project / proposal["strategy_ref"]["relative_path"]).read_text()
    )
    assert strategy["variants"][0]["id"] == "arm-1"
    refs = bridge.document(proposal["compiled_ref"])
    designs = [r for r in refs if r["relative_path"].endswith("/design.yaml")]
    assert len(designs) == 7
    for ref in designs:
        payload = yaml.safe_load((bridge.project / ref["relative_path"]).read_text())
        assert payload
    assert bridge.terminal_result("done")["status"] == "incomplete-turn"
    card = design_card(bridge)
    before = card.model_dump(mode="json")
    for technical in (False, True):
        _display(
            {"status": "awaiting-human-approval", "card": before}, technical_details=technical
        )
        displayed = json.loads(capsys.readouterr().out)
        assert displayed["status"] == "awaiting-human-approval"
        assert displayed["card"]["options"] == [{"label": card.options[0]["label"]}]
        assert displayed["card"]["human_actions"] == ["approve", "revise", "reject"]
        assert displayed["card"]["scientific_summary"] == card.scientific_summary
    assert card.model_dump(mode="json") == before
    with pytest.raises(AgentBoundaryError, match="human"):
        bridge.apply_decision(card)
    bridge.store.respond(bridge.thread, card.card_id, "approve", "synthetic-scientist")
    assert bridge.apply_decision(card)["status"] == "design-frozen"
    assert bridge.apply_decision(card)["status"] == "design-frozen"
    assert bridge.terminal_result("Frozen for review")["status"] == "finished"
    assert bridge.target_state()["binding"] == original_target
    assert bridge.approved_site()["hotspots_sha256"] == original_site
    assert len(list((bridge.project / "strategies").glob("strategy-r*.yaml"))) == 1
    assert all(j.step <= 2 for j in bridge.controller.list(project_id=bridge.project_id))

    # A different verified Target identity invalidates both dependent layers immediately.
    target_state = bridge.target_state()
    monkeypatch.setattr(bridge, "target_state", lambda: {**target_state, "binding": "new-target"})
    assert bridge.current_site() is None and bridge.approved_site() is None
    assert bridge.current_design() is None and bridge.approved_design() is None
    assert bridge.project_latest("design-approved") is not None  # history, not authority


@pytest.mark.parametrize(
    "changes",
    [
        {"binding_label_seq_ids": [999]},
        {"avoid_label_seq_ids": [1]},
        {"target_crop": {"start": 4, "end": 6}},
        {"candidates_per_scaffold": 20},
        {
            "cdr_overrides": [
                {"cdr": 3, "design_res_index": "1..3", "insertion_num_residues": "1..3"}
            ]
        },
    ],
)
def test_design_hard_constraints_cannot_be_overridden(
    design_bridge: Any, changes: dict[str, Any]
) -> None:
    bridge = design_bridge
    result = propose_design(bridge, binder_intent(**changes))
    assert result["evaluation"]["status"] == "BLOCKED"
    assert "plan_ref" not in bridge.current_design()
    card = design_card(bridge)
    with pytest.raises(AgentBoundaryError, match="BLOCKED"):
        bridge.store.respond(
            bridge.thread,
            card.card_id,
            "override",
            "synthetic-scientist",
            optional_reason="Try anyway",
            explicit_acknowledgement="I acknowledge",
        )
    assert bridge.approved_design() is None
    assert bridge.terminal_result("finished")["status"] == "incomplete-turn"


def test_design_crop_discouragement_allows_normal_approval(design_bridge: Any) -> None:
    bridge = design_bridge
    result = propose_design(bridge, binder_intent(target_crop={"start": 1, "end": 4}))
    assert result["evaluation"]["status"] == "DISCOURAGED", result["evaluation"]
    card = design_card(bridge)
    bridge.store.respond(
        bridge.thread,
        card.card_id,
        "approve",
        "synthetic-scientist",
    )
    assert bridge.apply_decision(card)["status"] == "design-frozen"
    assert bridge.approved_design()["outcome"]["recorded_warnings"] == card.warnings


def test_design_review_unavailable_reaches_normal_gate(design_bridge: Any) -> None:
    from easydesign.agent.review_availability import record_design_unavailable

    bridge = design_bridge
    propose_design(bridge)
    failure = record_design_unavailable(
        bridge,
        "judge-execution",
        failure_code="OUTPUT_VALIDATION_EXHAUSTED",
        diagnostic="Judge exhausted typed-output repairs",
    )
    card = bridge.decision_card(
        ApplyDecision(review_failure_id=failure["record_id"], option_id="design")
    )
    assert card.assessment_id is None
    assert card.judge_status is None
    assert card.scientific_summary["independent_review"] == {
        "availability": "unavailable",
        "failure_code": "OUTPUT_VALIDATION_EXHAUSTED",
        "failure_record_id": failure["record_id"],
    }
    bridge.store.respond(bridge.thread, card.card_id, "approve", "synthetic-scientist")
    assert bridge.apply_decision(card)["status"] == "design-frozen"


def test_design_review_unavailable_does_not_bypass_hard_invalidity(
    design_bridge: Any,
) -> None:
    from easydesign.agent.review_availability import record_design_unavailable

    bridge = design_bridge
    result = propose_design(bridge, binder_intent(binding_label_seq_ids=[999]))
    assert result["evaluation"]["status"] == "BLOCKED"
    failure = record_design_unavailable(
        bridge,
        "judge-execution",
        failure_code="PROVIDER_UNAVAILABLE",
        diagnostic="synthetic provider outage",
    )
    card = bridge.decision_card(
        ApplyDecision(review_failure_id=failure["record_id"], option_id="design")
    )
    assert card.judge_status == "BLOCKED"
    with pytest.raises(AgentBoundaryError, match="BLOCKED"):
        bridge.store.respond(bridge.thread, card.card_id, "approve", "synthetic-scientist")
    assert bridge.approved_design() is None


@pytest.mark.asyncio
async def test_design_judge_boundary_records_classified_unavailability(design_bridge: Any) -> None:
    from easydesign.agent.control_flow import next_action
    from easydesign.agent.review_availability import ReviewUnavailable
    from easydesign.agent.site_judge import create_site_aware_judge
    from tests.agent_support import scripted_config

    class BrokenLegacyJudge:
        async def ainvoke(self, state: Any, config: Any) -> Any:
            raise ReviewUnavailable(
                "STRUCTURED_OUTPUT_REPAIR_EXHAUSTED", "synthetic invalid Judge output"
            )

    bridge = design_bridge
    propose_design(bridge)
    agent = create_site_aware_judge(
        bridge,
        object(),
        scripted_config(),
        "judge-execution",
        BrokenLegacyJudge(),
    )
    await agent.ainvoke({"messages": []})
    action = next_action(bridge)
    assert action.stage == "scientist-gate"
    assert action.arguments["option_id"] == "design"
    assert action.arguments["review_failure_id"].startswith("review-unavailable-")


def test_design_judge_reject_is_advisory_when_runtime_is_valid(design_bridge: Any) -> None:
    bridge = design_bridge
    propose_design(bridge)
    evidence = bridge.judge_evidence()
    token = JUDGE_EVIDENCE.set(
        EvidenceBinding.model_validate({k: evidence[k] for k in EvidenceBinding.model_fields})
    )
    try:
        assessment = bridge.register_judge(
            JudgeVerdict.model_validate(
                {
                    "verdict": "reject",
                    "reasons": ["The mechanism remains an untested structural-transfer claim."],
                    "limitations": ["No binding or inhibition result exists."],
                    "recommendation": {
                        "option_id": "design",
                        "status": "DISCOURAGED",
                        "warnings": ["Mechanistic confidence is low."],
                        "alternative": "Revise the arm or approve it as an exploratory design.",
                    },
                }
            )
        )
    finally:
        JUDGE_EVIDENCE.reset(token)
    card = bridge.decision_card(
        ApplyDecision(assessment_id=assessment.assessment_id, option_id="design")
    )
    assert card.judge_status == "DISCOURAGED"
    assert "The mechanism remains an untested structural-transfer claim." in card.warnings
    bridge.store.respond(bridge.thread, card.card_id, "approve", "synthetic-scientist")
    assert bridge.apply_decision(card)["status"] == "design-frozen"


def test_restart_after_old_strategy_freeze_does_not_duplicate(design_bridge: Any) -> None:
    from tests.unit.agent.test_command_recovery import Crash, crash_at

    bridge = design_bridge
    propose_design(bridge)
    card = design_card(bridge)
    bridge.store.respond(bridge.thread, card.card_id, "approve", "synthetic-scientist")
    crash_at(bridge, "after_design_freeze")
    with pytest.raises(Crash):
        bridge.apply_decision(card)
    store = SessionStore(bridge.project)
    try:
        resumed = DesignBridge(bridge.project, bridge.thread, store)
        assert resumed.apply_decision(card)["status"] == "design-frozen"
        assert len(list((bridge.project / "strategies").glob("strategy-r*.yaml"))) == 1
    finally:
        store.close()


def test_cdr3_revision_uses_all_seven_existing_scaffold_templates(design_bridge: Any) -> None:
    bridge = design_bridge
    result = propose_design(
        bridge,
        binder_intent(
            cdr_overrides=[
                {
                    "cdr": 3,
                    "design_res_index": "100..105",
                    "insertion_num_residues": "1..3",
                }
            ]
        ),
    )
    assert result["evaluation"]["status"] == "DISCOURAGED", result["evaluation"]
    verified = result["evaluation"]["cdr_template_validation"]
    assert len(verified) == 1
    assert verified[0]["within_declared_loop_of_all_seven_scaffolds"] is True
    assert verified[0]["design_res_index"] == "100..105"
    assert bridge.judge_evidence()["evaluation"]["cdr_template_validation"] == verified
    refs = bridge.document(bridge.current_design()["compiled_ref"])
    scaffolds = [r for r in refs if r["relative_path"].endswith("/scaffold.yaml")]
    assert len(scaffolds) == 7
    for ref in scaffolds:
        spec = yaml.safe_load((bridge.project / ref["relative_path"]).read_text())
        assert spec["design"][0]["chain"]["res_index"].split(",")[-1] == "100..105"
        assert spec["design_insertions"][-1]["insertion"]["num_residues"] == "1..3"
        assert "structure_groups" in spec
