from typing import Any

import pytest

from easydesign.agent.contracts import (
    AgentBoundaryError,
    ApplyDecision,
    EvidenceBinding,
    JudgeVerdict,
)
from easydesign.agent.phase2 import SITE_EVIDENCE, Phase2Bridge
from easydesign.agent.site_contracts import SiteIntent, SiteQuery
from easydesign.agent.tools import JUDGE_EVIDENCE
from tests.agent_support import make_project, terminal


def site_intent(labels: list[int] | None = None) -> SiteIntent:
    return SiteIntent.model_validate(
        {
            "selected_site": {
                "name": "Exposed structural patch",
                "hotspot_label_seq_ids": labels or [1, 2, 3],
                "rationale": "A compact mapped region for an exploratory structural test.",
            },
            "positive_evidence": [
                "Existing kernel reports surface exposure and coordinate presence."
            ],
            "mechanistic_rationale": "Explore engagement without claiming a functional epitope.",
            "accessibility_rationale": "A compact exposed patch in the isolated prepared chain.",
            "binder_approach": "Approach from solvent; whole-VHH docking clearance is untested.",
            "risks": [],
            "uncertainty": ["Biological function and conformational specificity are unconfirmed."],
            "alternatives": [],
            "recommendation": "SUPPORTED",
        }
    )


def propose(bridge: Any, intent: SiteIntent | None = None, revision: Any = None) -> dict[str, Any]:
    evidence = bridge.read_site_evidence()
    token = SITE_EVIDENCE.set(
        EvidenceBinding.model_validate({k: evidence[k] for k in EvidenceBinding.model_fields})
    )
    try:
        return bridge.register_site(intent or site_intent(), revision)
    finally:
        SITE_EVIDENCE.reset(token)


def reviewed_card(bridge: Any) -> Any:
    snapshot = bridge.judge_evidence()
    token = JUDGE_EVIDENCE.set(
        EvidenceBinding.model_validate({k: snapshot[k] for k in EvidenceBinding.model_fields})
    )
    try:
        assessment = bridge.register_judge(
            JudgeVerdict(
                verdict="ready-to-ask",
                reasons=["Mapped structural proposal is reviewable within its limitations."],
                limitations=["No biological binding validation."],
            )
        )
    finally:
        JUDGE_EVIDENCE.reset(token)
    return bridge.decision_card(
        ApplyDecision(assessment_id=assessment.assessment_id, option_id="site")
    )


def test_real_site_tools_gate_and_old_hotspot_approval(site_bridge: Any) -> None:
    bridge = site_bridge
    target_before = bridge.target_state()["binding"]
    facts = bridge.read_site_evidence()
    assert facts["facts"][0]["mapping"]["label_seq_id"] == 1
    assert facts["facts"][0]["raw_sasa"] > 0
    assert bridge.evaluate_candidate(SiteQuery(label_seq_ids=[1, 2, 3]))["status"] == "SUPPORTED"
    result = propose(bridge)
    assert result["evaluation"]["status"] == "SUPPORTED"
    assert bridge.terminal_result("finished")["status"] == "incomplete-turn"
    card = reviewed_card(bridge)
    assert card.gate_type == "site-hotspot"
    assert bridge.approved_site() is None
    with pytest.raises(AgentBoundaryError, match="human"):
        bridge.apply_decision(card)
    bridge.store.respond(bridge.thread, card.card_id, "approve", "synthetic-human")
    assert bridge.apply_decision(card)["status"] == "hotspot-approved"
    assert bridge.target_state()["binding"] == target_before
    approved = bridge.approved_site()
    assert approved["hotspots"]["hotspot_sets"][0]["label_seq_ids"] == [1, 2, 3]
    assert bridge.terminal_result("site complete")["status"] == "finished"
    assert bridge.apply_decision(card)["status"] == "hotspot-approved"


def test_hard_mapping_block_has_no_scientific_submission(site_bridge: Any) -> None:
    bridge = site_bridge
    before = len(bridge.controller.list(project_id=bridge.project_id))
    result = propose(bridge, site_intent([999]))
    assert result["evaluation"]["status"] == "BLOCKED"
    card = reviewed_card(bridge)
    assert card.judge_status == "BLOCKED"
    with pytest.raises(AgentBoundaryError, match="BLOCKED"):
        bridge.store.respond(
            bridge.thread,
            card.card_id,
            "override",
            "synthetic-human",
            optional_reason="Exploratory",
            explicit_acknowledgement="I see the warning",
        )
    assert len(bridge.controller.list(project_id=bridge.project_id)) == before
    assert bridge.terminal_result("finished")["status"] == "incomplete-turn"


def test_real_glycan_warning_requires_human_override(site_bridge: Any, tmp_path: Any) -> None:
    import yaml

    bridge = site_bridge
    path = tmp_path / "biology.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "target_auth_chain": "A",
                "target_kind": "soluble",
                "features": [
                    {
                        "kind": "glycan",
                        "label_seq_ids": [2],
                        "description": "Possible shielding from a supplied annotation",
                        "source": "synthetic user annotation",
                    }
                ],
            }
        )
    )
    bridge.import_biology(path)
    snapshot = propose(bridge)
    assert snapshot["evaluation"]["status"] == "DISCOURAGED"
    assert "glycan" in " ".join(snapshot["evaluation"]["warnings"]).lower()
    card = reviewed_card(bridge)
    assert card.judge_status == "DISCOURAGED" and card.alternative
    with pytest.raises(AgentBoundaryError, match="OVERRIDE"):
        bridge.store.respond(bridge.thread, card.card_id, "approve", "synthetic-scientist")
    bridge.store.respond(
        bridge.thread,
        card.card_id,
        "override",
        "synthetic-scientist",
        explicit_acknowledgement="I reviewed the shielding warning",
        optional_reason="Test an accessible route as an exploratory hypothesis",
    )
    assert bridge.apply_decision(card)["status"] == "hotspot-approved"
    approved = bridge.approved_site()
    assert approved["outcome"]["action"] == "OVERRIDE"
    assert approved["outcome"]["recorded_warnings"] == card.warnings
    assert (
        "explicit human override" in approved["hotspots"]["hotspot_sets"][0]["biological_rationale"]
    )


def test_gpcr_geometry_and_glycan_limitations_are_grounded(tmp_path: Any, monkeypatch: Any) -> None:
    import yaml

    import tests.agent_support as support
    from tests.agent_phase2_support import gpcr_like_structure

    structure, biology = gpcr_like_structure()
    monkeypatch.setattr(support, "structure", lambda _chains: structure)
    target = make_project(tmp_path, monkeypatch, chains="A")
    try:
        target.prepare_target()
        terminal(target)
        bridge = Phase2Bridge(target.project, target.thread, target.store)
        path = tmp_path / "context.yaml"
        path.write_text(yaml.safe_dump(biology))
        bridge.import_biology(path)
        evidence = bridge.read_site_evidence()
        assert evidence["membrane_geometry"]["reliable"]
        assert evidence["membrane_geometry"]["helix_count"] == 7
        assert evidence["biology"]["structural_state"] == biology["structural_state"]
        assert evidence["sequence_motifs"]
        tm = bridge.evaluate_candidate(SiteQuery(label_seq_ids=[4, 5, 6]))
        assert tm["status"] == "DISCOURAGED" and "TM1" in tm["declared_segments"]
        motif_labels = biology["features"][0]["label_seq_ids"]
        glycan = bridge.evaluate_candidate(SiteQuery(label_seq_ids=motif_labels))
        assert glycan["motif_warnings"] and glycan["status"] == "DISCOURAGED"
        assert "occupancy" in " ".join(glycan["warnings"])
        assert {row["label_seq_id"] for row in glycan["mapped_residues"]} == set(motif_labels)
    finally:
        target.store.close()


def test_site_dispatch_replay_reattaches_original_job(site_bridge: Any) -> None:
    from tests.unit.agent.test_command_recovery import Crash, crash_at

    bridge = site_bridge
    crash_at(bridge, "after_site_dispatch")
    with pytest.raises(Crash):
        propose(bridge)
    bridge.failpoint = lambda _: None
    result = propose(bridge)
    assert result["status"] == "awaiting-human-approval"
    assert (
        len([j for j in bridge.controller.list(project_id=bridge.project_id) if j.step == 2]) == 1
    )


def test_source_author_numbering_is_not_invented(tmp_path: Any, monkeypatch: Any) -> None:
    import tests.agent_support as support

    original = support.structure("A")
    rows = []
    for line in original.splitlines():
        if line.startswith("ATOM"):
            number = int(line[22:26])
            line = line[:22] + f"{number + 100:4d}" + ("B" if number == 3 else " ") + line[27:]
        rows.append(line)
    monkeypatch.setattr(support, "structure", lambda _chains: "\n".join(rows) + "\n")
    target = make_project(tmp_path, monkeypatch, chains="A")
    try:
        target.prepare_target()
        terminal(target)
        bridge = Phase2Bridge(target.project, target.thread, target.store)
        mapping = [row["mapping"] for row in bridge.read_site_evidence()["facts"]]
        assert [row["label_seq_id"] for row in mapping] == list(range(1, 7))
        assert [row["source_author_residue_id"] for row in mapping] == [
            str(n) for n in range(101, 107)
        ]
        assert mapping[2]["insertion_code"] == "B"
        assert all(row["canonical_position"] is None for row in mapping)
        assert bridge.evaluate_candidate(SiteQuery(label_seq_ids=[101]))["status"] == "BLOCKED"
        assert (
            bridge.evaluate_candidate(SiteQuery(label_seq_ids=[1, 2, 3]))["status"] == "SUPPORTED"
        )
    finally:
        target.store.close()


def test_context_change_invalidates_site_without_repreparing_target(
    site_bridge: Any, tmp_path: Any
) -> None:
    import yaml

    bridge = site_bridge
    propose(bridge)
    card = reviewed_card(bridge)
    bridge.store.respond(bridge.thread, card.card_id, "approve", "synthetic-human")
    bridge.apply_decision(card)
    target_before = bridge.target_state()["binding"]
    path = tmp_path / "revised-context.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "target_auth_chain": "A",
                "target_kind": "soluble",
                "limitations": [
                    "The biological objective now requires re-evaluation of shielding."
                ],
            }
        )
    )
    bridge.import_biology(path)
    assert bridge.target_state()["binding"] == target_before
    assert bridge.current_site() is None and bridge.approved_site() is None
    assert bridge.terminal_result("done")["status"] == "incomplete-turn"
    with pytest.raises(AgentBoundaryError, match="changed"):
        bridge.apply_decision(card)
    assert len(bridge._jobs()) == 1


def test_discouraged_ready_hypothesis_is_not_a_mapping_block(site_bridge: Any) -> None:
    bridge = site_bridge
    propose(bridge)
    snapshot = bridge.judge_evidence()
    token = JUDGE_EVIDENCE.set(
        EvidenceBinding.model_validate({k: snapshot[k] for k in EvidenceBinding.model_fields})
    )
    try:
        assessment = bridge.register_judge(
            JudgeVerdict.model_validate(
                {
                    "verdict": "ready-to-ask",
                    "reasons": ["Functional relevance is weak."],
                    "limitations": ["Only structural accessibility is supported."],
                    "recommendation": {
                        "option_id": "site",
                        "status": "DISCOURAGED",
                        "warnings": ["Function has not been established."],
                        "alternative": "Supply functional evidence or treat this as exploratory.",
                    },
                }
            )
        )
    finally:
        JUDGE_EVIDENCE.reset(token)
    card = bridge.decision_card(
        ApplyDecision(assessment_id=assessment.assessment_id, option_id="site")
    )
    assert card.judge_status == "DISCOURAGED"
    bridge.store.respond(
        bridge.thread,
        card.card_id,
        "override",
        "synthetic-human",
        optional_reason="A testable structural hypothesis",
        explicit_acknowledgement="I acknowledge the functional uncertainty",
    )
    assert bridge.apply_decision(card)["status"] == "hotspot-approved"
