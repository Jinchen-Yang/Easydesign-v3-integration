from __future__ import annotations

import json
from pathlib import Path

import gemmi
import pytest

from easydesign.backends.target_sources.structure import (
    build_experimental_target_bundle,
    choose_chain,
    inventory_structure,
)
from easydesign.core import TargetInputError, load_model
from easydesign.stages.s01_target_preparation import ResidueMapping

ONE_TO_THREE = {"A": "ALA", "C": "CYS", "D": "ASP", "E": "GLU"}

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


def _write_partial_mmcif(
    path: Path,
    *,
    sequence: str,
    present_label_seq_ids: tuple[int, ...],
) -> None:
    structure = gemmi.Structure()
    structure.name = "partial-target"
    model = gemmi.Model(1)
    chain = gemmi.Chain("X")
    for label_seq_id in present_label_seq_ids:
        residue = gemmi.Residue()
        residue.name = ONE_TO_THREE[sequence[label_seq_id - 1]]
        residue.seqid = gemmi.SeqId(label_seq_id, " ")
        residue.subchain = "A"
        residue.label_seq = label_seq_id
        for atom_name, offset in (("N", 0.0), ("CA", 1.0)):
            atom = gemmi.Atom()
            atom.name = atom_name
            atom.element = gemmi.Element(atom_name[0])
            atom.pos = gemmi.Position(float(label_seq_id), offset, 0.0)
            residue.add_atom(atom)
        chain.add_residue(residue)
    model.add_chain(chain)
    structure.add_model(model)
    structure.setup_entities()
    structure.entities[0].full_sequence = [ONE_TO_THREE[aa] for aa in sequence]
    structure.assign_label_seq_id()
    path.write_text(
        structure.make_mmcif_document().as_string(),
        encoding="utf-8",
    )


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


@pytest.mark.parametrize(
    ("present", "expected_ranges"),
    [
        ((1, 3, 4), [{"start": 2, "end": 2, "kind": "internal"}]),
        (
            (2, 3),
            [
                {"start": 1, "end": 1, "kind": "terminal"},
                {"start": 4, "end": 4, "kind": "terminal"},
            ],
        ),
    ],
)
def test_deposited_sequence_allows_partial_coordinates_without_renumbering(
    tmp_path: Path,
    present: tuple[int, ...],
    expected_ranges: list[dict[str, object]],
) -> None:
    source = tmp_path / "partial.cif"
    _write_partial_mmcif(
        source,
        sequence="ACDE",
        present_label_seq_ids=present,
    )
    inventory = inventory_structure(source)

    assert inventory.chains[0].sequence == "".join(
        "ACDE"[label - 1] for label in present
    )
    assert inventory.chains[0].deposited_sequence == "ACDE"
    assert choose_chain(inventory, explicit_chain=None, expected_sequence="ACDE") == "X"

    run_root = tmp_path / "run"
    result = build_experimental_target_bundle(
        run_root=run_root,
        attempt_id="attempt-0001",
        target_id="partial",
        source_path=source,
        source_format="mmcif",
        selected_chain="X",
        expected_scope_sequence="ACDE",
        reference_sequence="ACDE",
        reference_start=1,
        identity_report={"status": "test"},
        scope_report={"type": "full-sequence"},
        candidates=[],
        quality_report={"eligibility": "eligible"},
        provenance={"source": "unit-test"},
        retrieval_records=[],
        preserve_source_context=True,
    )

    mapping = load_model(
        result.built_bundle.bundle.residue_mapping.verify(run_root),
        ResidueMapping,
    )
    assert mapping.schema_version == "0.3"
    assert [entry.label_seq_id for entry in mapping.entries] == [1, 2, 3, 4]
    assert [entry.coordinate_present for entry in mapping.entries] == [
        label in present for label in range(1, 5)
    ]
    assert [
        entry.model_presence for entry in mapping.entries
    ] == [("1",) if label in present else () for label in range(1, 5)]
    for entry in mapping.entries:
        serialized = entry.model_dump(mode="json")
        if entry.coordinate_present:
            assert "coordinate_present" not in serialized
        else:
            assert serialized["coordinate_present"] is False

    normalized = gemmi.read_structure(
        str(result.built_bundle.bundle.target_structure.verify(run_root))
    )
    assert normalized.entities[0].full_sequence == ["ALA", "CYS", "ASP", "GLU"]
    assert [residue.label_seq for residue in normalized[0][0]] == list(present)

    quality_path = result.built_bundle.bundle.quality_report.verify(run_root)
    quality = json.loads(quality_path.read_text(encoding="utf-8"))
    assert quality["target_structure_status"] == "experimental-partial"
    assert quality["scope_sequence_identity"] == 1.0
    assert quality["scope_coordinate_coverage"] == len(present) / 4
    assert quality["missing_coordinate_ranges"] == expected_ranges


def test_partial_structure_still_rejects_deposited_sequence_identity_mismatch(
    tmp_path: Path,
) -> None:
    source = tmp_path / "partial.cif"
    _write_partial_mmcif(
        source,
        sequence="ACDE",
        present_label_seq_ids=(1, 3, 4),
    )

    with pytest.raises(TargetInputError, match="deposited polymer sequence"):
        build_experimental_target_bundle(
            run_root=tmp_path / "run",
            attempt_id="attempt-0001",
            target_id="partial",
            source_path=source,
            source_format="mmcif",
            selected_chain="X",
            expected_scope_sequence="ACDF",
            reference_sequence="ACDF",
            reference_start=1,
            identity_report={"status": "test"},
            scope_report={"type": "full-sequence"},
            candidates=[],
            quality_report={"eligibility": "eligible"},
            provenance={"source": "unit-test"},
            retrieval_records=[],
            preserve_source_context=True,
        )


def test_altloc_uses_highest_occupancy_and_label_chain_maps_to_author(
    tmp_path: Path,
) -> None:
    source = tmp_path / "altloc.pdb"
    source.write_text(
        """ATOM      1  N   ALA A   1       0.000   0.000   0.000  1.00 20.00           N
ATOM      2  CA AALA A   1       1.000   0.000   0.000  0.40 20.00           C
ATOM      3  CA BALA A   1       9.000   0.000   0.000  0.60 20.00           C
ATOM      4  CB AALA A   1       2.000   0.000   0.000  0.50 20.00           C
ATOM      5  CB BALA A   1       8.000   0.000   0.000  0.50 20.00           C
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
    cb = next(atom for atom in normalized[0][0][0] if atom.name.strip() == "CB")
    assert ca.pos.x == 9.0
    assert ca.altloc == "\x00"
    assert cb.pos.x == 2.0
    assert cb.altloc == "\x00"
