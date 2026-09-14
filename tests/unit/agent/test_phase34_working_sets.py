import json

from easydesign.agent.phase34_plan import PilotArmIntent
from easydesign.agent.phase34_science import compact_arm_intent, pilot_working_set
from tests.unit.agent.test_phase34_contracts import _pilot_dossier


def test_scaffold_factorization_preserves_different_constraints_and_scientific_intent():
    references = tuple("project:scientific-evidence-" + str(i) + "#" + "a" * 64 for i in range(30))
    records = tuple(
        {
            "strategy_id": f"arm-a-scaffold-{i}",
            "scaffold_id": f"scaffold-{i}",
            "binding_label_seq_ids": [12, 15] if i != 4 else [15],
            "avoid_label_seq_ids": [30, 31, 32],
            "evidence_refs": list(references),
            "cdr_overrides": [{"cdr": "CDR3", "insertion_num_residues": "3..50"}],
            "candidates_per_strategy": 40,
        }
        for i in range(7)
    )
    arm = PilotArmIntent(
        arm_id="arm-a",
        strategy_ids=tuple(r["strategy_id"] for r in records),
        hypothesis="Reach the approved pocket using the current GPCR prior.",
        rationale="Test geometric reach without changing Site approval.",
        changed_factors=("CDR3 insertion search",),
        held_constant=("Approved Site",),
        expected_result="Measure accessibility and steric cost.",
        failure_interpretation="Missing predictions do not falsify binding.",
        role="primary",
        compiled_settings=records,
        target_context={"target": "test-gpcr"},
        evidence_refs=references,
    )
    original = arm.model_dump(mode="json")
    compact = compact_arm_intent(arm)
    settings = compact["compiled_settings"]
    reconstructed = [{**settings["common"], **record} for record in settings["strategies"]]
    assert reconstructed == original["compiled_settings"]
    assert "binding_label_seq_ids" not in settings["common"]
    assert settings["common"]["avoid_label_seq_ids"] == [30, 31, 32]
    assert settings["common"]["cdr_overrides"][0]["insertion_num_residues"] == "3..50"
    assert all(compact[k] == original[k] for k in original if k != "compiled_settings")
    assert arm.model_dump(mode="json") == original
    assert len(json.dumps(compact)) < len(json.dumps(original)) / 2
    packet = pilot_working_set(_pilot_dossier().measurement, (arm,))
    context_id = packet["facts"]["arm-a"]["design_intent"]["target_context"]["shared_context_id"]
    assert packet["shared_target_contexts"][context_id] == original["target_context"]
