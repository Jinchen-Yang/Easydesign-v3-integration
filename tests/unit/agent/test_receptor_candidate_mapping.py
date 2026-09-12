"""Synthetic nonuniform numbering, missingness and source-identity regression."""

from copy import deepcopy
from typing import Any

import pytest

from easydesign.agent.contracts import AgentBoundaryError
from easydesign.agent.evidence_output import receptor_overview_projection
from easydesign.agent.site_evidence import receptor_candidate_mapping


def examples() -> tuple[dict[str, Any], dict[str, Any]]:
    rows = [
        {
            "canonical_position": canonical,
            "label_seq_id": design,
            "construct_position": construct,
            "canonical_residue": "N",
            "amino_acid": residue,
            "mapping_status": "ambiguous",
            "edit_type": "native" if residue == "N" else "substitution",
            "model_presence": ["1"] if present else [],
            "source_author_residue_id": None,
            "insertion_code": None,
        }
        for canonical, design, construct, residue, present in [
            (10, 10, 18, "N", True),
            (20, 148, 156, "E", True),
            (21, 149, 157, "N", False),
            (22, 150, 158, "N", True),
            (22, 151, 159, "N", False),
        ]
    ]
    facts = {
        "observed_facts": {"mapping": rows},
        "derived_metrics": {
            "sasa": {"residues": [{"residue": {"label_seq_id": n}} for n in [10, 148, 150]]}
        },
    }
    receptor = {
        "identity": {"accession": "SYNTHETIC", "receptor_chain": "A"},
        "candidates": {
            "inhibit": [
                {
                    "id": "synthetic-candidate",
                    "limitations": ["No functional evidence"],
                    "residues": [
                        {"gpcrdb_sequence_number": p, "label_seq_id": p + 8, "observed": True}
                        for p in [10, 20, 21, 22, 30]
                    ],
                }
            ],
            "activate": [],
        },
    }
    return facts, receptor


def test_approved_candidate_mapping_preserves_nonuniform_and_nonunique_rows() -> None:
    facts, receptor = examples()
    before = deepcopy((facts, receptor))
    mapping = receptor_candidate_mapping(
        facts, receptor, approved_accession="SYNTHETIC", approved_auth_chain="A"
    )
    assert (facts, receptor) == before
    assert [row["mapping"] for row in mapping["facts"]] == facts["observed_facts"]["mapping"]
    assert [row["coordinate_observed"] for row in mapping["facts"]] == [
        True,
        True,
        False,
        True,
        False,
    ]
    assert mapping["unmapped_canonical_positions"] == [30]
    assert mapping["facts"][1]["mapping"]["label_seq_id"] == 148
    assert mapping["facts"][1]["mapping"]["edit_type"] == "substitution"
    projected = receptor_overview_projection({**receptor, "approved_design_mapping": mapping})
    table = projected["approved_design_mapping"]["facts_table"]
    names = table["mapping_columns"]
    decoded = [dict(zip(names, row[: len(names)], strict=True)) for row in table["rows"]]
    assert decoded == facts["observed_facts"]["mapping"]
    source = projected["candidate_overview"]["inhibit"][0]["residue_table"]
    assert "source_label_seq_id" in source["columns"]
    assert source["rows"][1][source["columns"].index("source_label_seq_id")] == 28
    assert all(row["mapping_status"] == "ambiguous" for row in decoded)


@pytest.mark.parametrize("accession,chain", [("FOREIGN", "A"), ("SYNTHETIC", "B"), (None, "A")])
def test_candidate_mapping_rejects_foreign_or_unresolved_identity(
    accession: str | None, chain: str
) -> None:
    facts, receptor = examples()
    with pytest.raises(AgentBoundaryError, match="differs from the approved Target"):
        receptor_candidate_mapping(
            facts, receptor, approved_accession=accession, approved_auth_chain=chain
        )
