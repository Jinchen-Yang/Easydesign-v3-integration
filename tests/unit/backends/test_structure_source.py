from __future__ import annotations

from pathlib import Path

import gemmi

from easydesign.backends.target_sources.structure import (
    build_experimental_target_bundle,
    choose_chain,
    inventory_structure,
)
from easydesign.core import load_model
from easydesign.stages.s01_target_preparation import ResidueMapping

MULTI_MODEL_PDB = """MODEL        1
ATOM      1  N   ALA X  10       0.000   0.000   0.000  1.00 20.00           N
ATOM      2  CA  ALA X  10       1.000   0.000   0.000  1.00 20.00           C
ATOM      3  N   CYS X  11       2.000   0.000   0.000  1.00 20.00           N
ATOM      4  CA  CYS X  11       3.000   0.000   0.000  1.00 20.00           C
ENDMDL
MODEL        2
ATOM      5  N   ALA X  10       0.000   1.000   0.000  1.00 20.00           N
ATOM      6  CA  ALA X  10       1.000   1.000   0.000  1.00 20.00           C
ENDMDL
END
"""


def test_multimodel_structure_preserves_ensemble_and_presence(tmp_path: Path) -> None:
    source = tmp_path / "ensemble.pdb"
    source.write_text(MULTI_MODEL_PDB, encoding="utf-8")
    inventory = inventory_structure(source)

    assert inventory.model_ids == ("1", "2")
    assert choose_chain(inventory, explicit_chain=None, expected_sequence="AC") == "X"

    result = build_experimental_target_bundle(
        run_root=tmp_path / "run",
        attempt_id="attempt-0001",
        target_id="ensemble",
        source_path=source,
        source_format="pdb",
        selected_chain="X",
        expected_scope_sequence="AC",
        reference_sequence="AC",
        reference_start=1,
        identity_report={"status": "test"},
        scope_report={"type": "full-sequence"},
        candidates=[],
        quality_report={"eligibility": "eligible"},
        provenance={"source": "unit-test"},
        retrieval_records=[],
        preserve_source_context=True,
    )

    assert result.built_bundle.bundle.coordinate_ensemble is not None
    assert result.built_bundle.bundle.coordinate_ensemble.model_ids == ("1", "2")
    mapping = load_model(
        result.built_bundle.bundle.residue_mapping.verify(tmp_path / "run"),
        ResidueMapping,
    )
    assert mapping.entries[0].model_presence == ("1", "2")
    assert mapping.entries[1].model_presence == ("1",)
    assert mapping.entries[0].source_author_chain_id == "X"
    assert mapping.entries[0].author_chain_id == "A"


def test_altloc_uses_highest_occupancy_and_label_chain_maps_to_author(
    tmp_path: Path,
) -> None:
    source = tmp_path / "altloc.pdb"
    source.write_text(
        """ATOM      1  N   ALA A   1       0.000   0.000   0.000  1.00 20.00           N
ATOM      2  CA AALA A   1       1.000   0.000   0.000  0.40 20.00           C
ATOM      3  CA BALA A   1       9.000   0.000   0.000  0.60 20.00           C
END
""",
        encoding="utf-8",
    )
    structure = gemmi.read_structure(str(source))
    structure[0][0][0].subchain = "LABEL_A"
    cif = tmp_path / "altloc.cif"
    cif.write_text(
        structure.make_mmcif_document().as_string(),
        encoding="utf-8",
    )
    inventory = inventory_structure(cif)

    assert inventory.chains[0].label_chain_id == "LABEL_A"
    assert (
        choose_chain(
            inventory,
            explicit_chain="LABEL_A",
            expected_sequence=None,
            chain_namespace="label",
        )
        == "A"
    )

    result = build_experimental_target_bundle(
        run_root=tmp_path / "run",
        attempt_id="attempt-0001",
        target_id="altloc",
        source_path=cif,
        source_format="mmcif",
        selected_chain="A",
        expected_scope_sequence="A",
        reference_sequence="A",
        reference_start=1,
        identity_report={"status": "test"},
        scope_report={"type": "full-sequence"},
        candidates=[],
        quality_report={"eligibility": "eligible"},
        provenance={"source": "unit-test"},
        retrieval_records=[],
        preserve_source_context=False,
    )
    normalized = gemmi.read_structure(
        str(result.built_bundle.bundle.target_structure.verify(tmp_path / "run"))
    )
    ca = next(atom for atom in normalized[0][0][0] if atom.name.strip() == "CA")
    assert ca.pos.x == 9.0
    assert ca.altloc == "\x00"
