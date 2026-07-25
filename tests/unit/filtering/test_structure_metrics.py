from __future__ import annotations

from pathlib import Path

import gemmi
import pytest

from easydesign.core import ManifestStateError
from easydesign.filtering import (
    compute_full_target_structure_metrics,
    compute_interface_metrics,
    parse_protein_chain,
)


def _pdb_line(
    serial: int,
    *,
    chain: str,
    residue: int,
    x: float,
    y: float,
    z: float,
) -> str:
    return (
        f"ATOM  {serial:5d}  CA  ALA {chain}{residue:4d}    "
        f"{x:8.3f}{y:8.3f}{z:8.3f}  1.00 20.00           C  \n"
    )


def _complex_cif(tmp_path: Path) -> Path:
    pdb = tmp_path / "complex.pdb"
    lines = [
        _pdb_line(1, chain="A", residue=1, x=0, y=0, z=0),
        _pdb_line(2, chain="A", residue=2, x=10, y=0, z=0),
        _pdb_line(3, chain="A", residue=3, x=20, y=0, z=0),
        _pdb_line(4, chain="B", residue=1, x=0, y=4, z=0),
        _pdb_line(5, chain="B", residue=2, x=10, y=4, z=0),
        _pdb_line(6, chain="B", residue=3, x=30, y=4, z=0),
        "TER\n",
        "END\n",
    ]
    pdb.write_text("".join(lines), encoding="ascii")
    structure = gemmi.read_structure(str(pdb))
    for chain in structure[0]:
        for label_seq_id, residue in enumerate(chain, start=1):
            residue.label_seq = label_seq_id
    cif = tmp_path / "complex.cif"
    structure.make_mmcif_document().write_file(str(cif))
    return cif


def test_interface_metrics_use_label_chains_and_explicit_thresholds(
    tmp_path: Path,
) -> None:
    cif = _complex_cif(tmp_path)
    reference = parse_protein_chain(cif, "A")

    metrics = compute_interface_metrics(
        candidate_structure=cif,
        reference_target=reference,
        hotspot_residue_ids=(1, 2, 3),
        cdr_residue_ids=(1, 2),
    )

    assert metrics.target_ca_rmsd_angstrom == pytest.approx(0.0, abs=1e-6)
    assert metrics.hotspot_coverage == pytest.approx(2 / 3)
    assert metrics.binder_contact_coverage == pytest.approx(2 / 3)
    assert metrics.cdr_dominance == pytest.approx(1.0)
    assert metrics.cdr_utilization == pytest.approx(1.0)
    assert metrics.residue_pair_contact_count == 2
    assert metrics.atom_contact_count == 2
    assert metrics.severe_clash_count == 0
    assert metrics.moderate_clash_count == 0
    assert metrics.interface_bsa_angstrom2 is not None


def test_full_target_pose_uses_target_aligned_binder_frame(tmp_path: Path) -> None:
    cif = _complex_cif(tmp_path)
    reference = parse_protein_chain(cif, "A")

    metrics = compute_full_target_structure_metrics(
        designed_complex=cif,
        predicted_complex=cif,
        reference_target=reference,
    )

    assert metrics.binder_pose_rmsd_angstrom == pytest.approx(0.0, abs=1e-6)
    assert metrics.target_ca_rmsd_angstrom == pytest.approx(0.0, abs=1e-6)
    assert metrics.severe_clash_count == 0


def test_rejects_missing_label_identity_and_target_sequence_mismatch(
    tmp_path: Path,
) -> None:
    cif = _complex_cif(tmp_path)
    reference = parse_protein_chain(cif, "A")
    structure = gemmi.read_structure(str(cif))
    structure[0]["A"][0].label_seq = None
    missing = tmp_path / "missing-label.cif"
    structure.make_mmcif_document().write_file(str(missing))
    with pytest.raises(ManifestStateError, match="label_seq_id"):
        parse_protein_chain(missing, "A")

    structure = gemmi.read_structure(str(cif))
    structure[0]["A"][1].name = "VAL"
    mismatch = tmp_path / "mismatch.cif"
    structure.make_mmcif_document().write_file(str(mismatch))
    with pytest.raises(ManifestStateError, match="residue identity"):
        compute_interface_metrics(
            candidate_structure=mismatch,
            reference_target=reference,
            hotspot_residue_ids=(1, 2),
            cdr_residue_ids=(1, 2),
        )
