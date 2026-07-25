from __future__ import annotations

from pathlib import Path

import pytest

from easydesign.core import ArtifactRef, ManifestStateError, dump_model
from easydesign.stages.s01_target_preparation import (
    CoordinateEnsemble,
    ResidueMapping,
    ResidueMappingEntry,
    TargetBundle,
)
from easydesign.stages.s02_hotspot_discovery import load_structure_context


def _artifact(
    run_root: Path,
    path: Path,
    artifact_id: str,
    file_format: str,
) -> ArtifactRef:
    return ArtifactRef.from_file(
        run_root=run_root,
        relative_path=path.relative_to(run_root).as_posix(),
        artifact_id=artifact_id,
        role=artifact_id,
        file_format=file_format,
        producer_stage="01-target-preparation",
        producer_attempt="attempt-0001",
    )


def _atom_rows(
    *,
    model_id: str,
    label: int,
    residue: str,
    x: float,
) -> list[str]:
    result = []
    for atom_index, (atom, element, offset) in enumerate(
        (
            ("N", "N", -1.2),
            ("CA", "C", 0.0),
            ("C", "C", 1.2),
            ("O", "O", 1.8),
            ("CB", "C", 0.0),
        ),
        start=1,
    ):
        result.append(
            f"ATOM {atom_index} {element} {atom} {residue} A {label} A "
            f"{label} {x + offset:.3f} 0.000 "
            f"{1.5 if atom == 'CB' else 0.0:.3f} 1.00 {model_id}"
        )
    return result


def _write_bundle(
    tmp_path: Path,
    *,
    model_rows: list[str],
    model_ids: tuple[str, ...] = ("1", "2"),
) -> tuple[Path, Path]:
    run_root = tmp_path / "run"
    artifacts = run_root / "01-target-preparation/attempt-0001/artifacts"
    artifacts.mkdir(parents=True)
    cif = artifacts / "target.cif"
    cif.write_text(
        """data_target
loop_
_atom_site.group_PDB
_atom_site.id
_atom_site.type_symbol
_atom_site.label_atom_id
_atom_site.label_comp_id
_atom_site.label_asym_id
_atom_site.label_seq_id
_atom_site.auth_asym_id
_atom_site.auth_seq_id
_atom_site.Cartn_x
_atom_site.Cartn_y
_atom_site.Cartn_z
_atom_site.occupancy
_atom_site.pdbx_PDB_model_num
"""
        + "\n".join(model_rows)
        + "\n#\n",
        encoding="utf-8",
    )
    sequence = artifacts / "sequence.fasta"
    sequence.write_text(">target\nAA\n", encoding="utf-8")
    mapping_path = artifacts / "residue-mapping.json"
    mapping = ResidueMapping(
        target_id="target",
        sequence_sha256="a" * 64,
        entries=(
            ResidueMappingEntry(
                sequence_index=1,
                amino_acid="A",
                label_chain_id="A",
                label_seq_id=1,
                author_chain_id="A",
                author_residue_id="1",
            ),
            ResidueMappingEntry(
                sequence_index=2,
                amino_acid="A",
                label_chain_id="A",
                label_seq_id=2,
                author_chain_id="A",
                author_residue_id="2",
            ),
        ),
    )
    dump_model(mapping, mapping_path)
    quality = artifacts / "quality.json"
    quality.write_text("{}\n", encoding="utf-8")
    provenance = artifacts / "provenance.json"
    provenance.write_text("{}\n", encoding="utf-8")
    bundle = TargetBundle(
        target_id="target",
        origin="experimental",
        sequence_length=2,
        sequence_sha256="a" * 64,
        producer_attempt="attempt-0001",
        target_structure=_artifact(run_root, cif, "target-structure", "mmcif"),
        sequence=_artifact(run_root, sequence, "target-sequence", "fasta"),
        residue_mapping=_artifact(
            run_root,
            mapping_path,
            "residue-mapping",
            "json",
        ),
        quality_report=_artifact(
            run_root,
            quality,
            "structure-quality",
            "json",
        ),
        provenance=_artifact(
            run_root,
            provenance,
            "target-provenance",
            "json",
        ),
        coordinate_ensemble=CoordinateEnsemble(
            model_count=len(model_ids),
            model_ids=model_ids,
            representative_model_id="1",
        ),
    )
    bundle_path = artifacts / "target-bundle.json"
    dump_model(bundle, bundle_path)
    return run_root, bundle_path


def test_context_loads_declared_ensemble_and_allows_missing_residue(
    tmp_path: Path,
) -> None:
    rows = (
        _atom_rows(model_id="1", label=1, residue="ALA", x=0.0)
        + _atom_rows(model_id="1", label=2, residue="ALA", x=10.0)
        + _atom_rows(model_id="2", label=1, residue="ALA", x=0.5)
    )
    run_root, bundle_path = _write_bundle(tmp_path, model_rows=rows)

    _bundle, context = load_structure_context(
        run_root=run_root,
        target_bundle_path=bundle_path,
    )

    assert context.model_ids == ("1", "2")
    assert set(context.residues) == {1, 2}
    assert set(context.models["2"].residues) == {1}


def test_context_rejects_residue_type_conflict_across_models(
    tmp_path: Path,
) -> None:
    rows = (
        _atom_rows(model_id="1", label=1, residue="ALA", x=0.0)
        + _atom_rows(model_id="1", label=2, residue="ALA", x=10.0)
        + _atom_rows(model_id="2", label=1, residue="CYS", x=0.5)
        + _atom_rows(model_id="2", label=2, residue="ALA", x=10.5)
    )
    run_root, bundle_path = _write_bundle(tmp_path, model_rows=rows)

    with pytest.raises(ManifestStateError, match="多个 residue name"):
        load_structure_context(
            run_root=run_root,
            target_bundle_path=bundle_path,
        )


def test_context_rejects_undeclared_model_id(tmp_path: Path) -> None:
    rows = (
        _atom_rows(model_id="1", label=1, residue="ALA", x=0.0)
        + _atom_rows(model_id="1", label=2, residue="ALA", x=10.0)
        + _atom_rows(model_id="3", label=1, residue="ALA", x=0.5)
        + _atom_rows(model_id="3", label=2, residue="ALA", x=10.5)
    )
    run_root, bundle_path = _write_bundle(tmp_path, model_rows=rows)

    with pytest.raises(ManifestStateError, match="coordinate_ensemble"):
        load_structure_context(
            run_root=run_root,
            target_bundle_path=bundle_path,
        )
