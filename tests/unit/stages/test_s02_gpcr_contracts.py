from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
from pathlib import Path

import pytest
from pydantic import ValidationError

from easydesign.stages.s02_hotspot_discovery.gpcr import GpcrSiteAnalysis

STRUCTURE_CONTEXT_BASELINE_SHA256 = (
    "9509c78fe9559792b6b9047e74147c1587a0cb531c579b53dd409966eb823aad"
)
CANDIDATE_GENERATION_BASELINE_SHA256 = (
    "c22bae665bcea529c4d1f444644848604cccc2f618d19fcd7bdd1416bc7961c1"
)


def _analysis() -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "analysis_id": "adrb2-test-analysis",
        "generated_at": "2026-08-19T00:00:00Z",
        "mode": "both",
        "structure": {
            "path": "01-target-preparation/attempt-0001/artifacts/source-context.cif",
            "sha256": "a" * 64,
            "receptor_chain": "A",
        },
        "identity": {"entry_name": "adrb2_human", "status": "resolved"},
        "topology": {"mapping_status": "resolved", "residues": []},
        "state": {"assignment": "inactive"},
        "membrane": {"status": "unresolved"},
        "chain_graph": {"chains": [], "edges": []},
        "decision_context": {"status": "unresolved"},
        "residue_regions": [],
        "candidates": {"inhibit": [], "activate": []},
        "avoid": [],
        "evidence": [],
        "warnings": [],
        "provenance": {"inputs": []},
        "analysis_notes": {"no_fused_score": True},
    }


def _primary_candidate() -> dict[str, object]:
    return {
        "id": "inhibit.orthosteric-rim",
        "mode": "inhibit",
        "classification": "primary",
        "role": "outer-vestibule-blockade",
        "hypothesis": "Occupancy blocks extracellular ligand entry.",
        "functional_site": "extracellular vestibule",
        "residues": [
            {
                "auth_asym_id": "A",
                "auth_seq_id": 113,
                "label_asym_id": "A",
                "label_seq_id": 113,
                "generic_number": "3x32",
            }
        ],
        "target_state": "inactive",
        "counterstate": "active",
        "approach_direction": "extracellular",
        "approach_checks": {"status": "pass", "required": ["framework clearance"]},
        "evidence_tier": "T2",
        "evidence": [],
        "evidence_ids": [],
        "hard_gates": [
            {"name": "exact_residue_mapping", "status": "pass"},
            {"name": "signed_membrane_orientation", "status": "pass"},
        ],
        "risks": [],
        "confidence": "medium",
        "falsifier": "Verified occupancy does not alter ligand response.",
        "assays": ["state-matched signaling inhibition"],
    }


def test_gpcr_analysis_allows_auditable_unresolved_dossier() -> None:
    analysis = GpcrSiteAnalysis.model_validate(_analysis())

    assert analysis.mode == "both"
    assert not analysis.candidates.inhibit
    assert analysis.membrane["status"] == "unresolved"


def test_gpcr_analysis_rejects_primary_when_membrane_is_unresolved() -> None:
    payload = _analysis()
    payload["candidates"] = {"inhibit": [_primary_candidate()], "activate": []}

    with pytest.raises(ValidationError, match="膜方向未解决"):
        GpcrSiteAnalysis.model_validate(payload)


def test_gpcr_analysis_accepts_primary_only_after_all_review_gates() -> None:
    payload = _analysis()
    payload["membrane"] = {"status": "resolved"}
    payload["decision_context"] = {"status": "resolved"}
    payload["candidates"] = {"inhibit": [_primary_candidate()], "activate": []}

    analysis = GpcrSiteAnalysis.model_validate(payload)

    assert analysis.candidates.inhibit[0].classification == "primary"


def test_gpcr_candidate_rejects_fused_score_and_nonpassing_primary_gate() -> None:
    payload = _analysis()
    payload["membrane"] = {"status": "resolved"}
    payload["decision_context"] = {"status": "resolved"}
    candidate = _primary_candidate()
    candidate["fused_score"] = 0.99
    payload["candidates"] = {"inhibit": [candidate], "activate": []}
    with pytest.raises(ValidationError, match="fused_score"):
        GpcrSiteAnalysis.model_validate(payload)

    candidate = deepcopy(_primary_candidate())
    candidate["hard_gates"][0]["status"] = "fail"  # type: ignore[index]
    payload["candidates"] = {"inhibit": [candidate], "activate": []}
    with pytest.raises(ValidationError, match="hard gates"):
        GpcrSiteAnalysis.model_validate(payload)


@pytest.mark.parametrize(
    ("relative_path", "expected"),
    [
        (
            "src/easydesign/stages/s02_hotspot_discovery/gpcr/structure_context.py",
            STRUCTURE_CONTEXT_BASELINE_SHA256,
        ),
        (
            "src/easydesign/stages/s02_hotspot_discovery/gpcr/candidate_generation.py",
            CANDIDATE_GENERATION_BASELINE_SHA256,
        ),
    ],
)
def test_gpcr_scientific_migration_starts_from_byte_exact_baseline(
    relative_path: str,
    expected: str,
) -> None:
    root = Path(__file__).resolve().parents[3]

    assert sha256((root / relative_path).read_bytes()).hexdigest() == expected
