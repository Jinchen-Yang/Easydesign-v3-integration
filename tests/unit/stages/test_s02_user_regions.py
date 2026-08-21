from __future__ import annotations

from pathlib import Path

import pytest

from easydesign.core import ArtifactRef, ManifestStateError, dump_model
from easydesign.stages.s01_target_preparation import (
    ColorCount,
    CoordinateEnsemble,
    PseSourceAnnotations,
    ResidueColorAnnotation,
    ResidueMapping,
    ResidueMappingEntry,
    TargetBundle,
)
from easydesign.stages.s02_hotspot_discovery import (
    StructureContext,
    has_standard_pse_colors,
    load_structure_context,
    normalize_manual_regions,
    normalize_pse_color_regions,
)


def _artifact(
    root: Path,
    path: Path,
    artifact_id: str,
    file_format: str,
) -> ArtifactRef:
    return ArtifactRef.from_file(
        run_root=root,
        relative_path=path.relative_to(root).as_posix(),
        artifact_id=artifact_id,
        role=artifact_id,
        file_format=file_format,
        producer_stage="01-target-preparation",
        producer_attempt="attempt-0001",
    )


def _fixture(
    tmp_path: Path,
    *,
    present_label_seq_ids: tuple[int, ...] = (1, 2, 3, 4),
) -> tuple[Path, TargetBundle, ResidueMapping, StructureContext]:
    root = tmp_path / "run"
    artifacts = root / "01-target-preparation/attempt-0001/artifacts"
    artifacts.mkdir(parents=True)
    cif = artifacts / "target.cif"
    rows: list[str] = []
    serial = 1
    for label in present_label_seq_ids:
        for atom, element, offset in (
            ("N", "N", -1.2),
            ("CA", "C", 0.0),
            ("C", "C", 1.2),
            ("O", "O", 1.8),
            ("CB", "C", 0.0),
        ):
            rows.append(
                f"ATOM {serial} {element} {atom} ALA A {label} A "
                f"{label + 20} {label * 4 + offset:.3f} 0.000 "
                f"{1.5 if atom == 'CB' else 0.0:.3f} 1.00 1"
            )
            serial += 1
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
        + "\n".join(rows)
        + "\n#\n",
        encoding="utf-8",
    )
    sequence = artifacts / "sequence.fasta"
    sequence.write_text(">target\nAAAA\n", encoding="utf-8")
    mapping = ResidueMapping(
        target_id="target",
        sequence_sha256="a" * 64,
        entries=tuple(
            ResidueMappingEntry(
                sequence_index=index,
                amino_acid="A",
                label_chain_id="A",
                label_seq_id=index,
                author_chain_id="A",
                author_residue_id=str(index + 20),
                source_author_chain_id="X",
                source_author_residue_id=str(index + 20),
                reference_position=100 + index,
                coordinate_present=index in present_label_seq_ids,
                model_presence=("1",) if index in present_label_seq_ids else (),
            )
            for index in range(1, 5)
        ),
    )
    mapping_path = dump_model(mapping, artifacts / "residue-mapping.json")
    quality = artifacts / "quality.json"
    quality.write_text("{}\n", encoding="utf-8")
    provenance = artifacts / "provenance.json"
    provenance.write_text("{}\n", encoding="utf-8")
    colors = (
        ("#FF0000", (1.0, 0.0, 0.0), 4),
        ("#00FF00", (0.0, 1.0, 0.0), 3),
        ("#0000FF", (0.0, 0.0, 1.0), 2),
        ("#FFFF00", (1.0, 1.0, 0.0), 6),
    )
    annotation = PseSourceAnnotations(
        residues=tuple(
            ResidueColorAnnotation(
                label_seq_id=index,
                author_chain_id="A",
                author_residue_id=str(index + 20),
                ca_color_index=color[2],
                ca_color_rgb=color[1],
                ca_color_hex=color[0],
            )
            for index, color in enumerate(colors, start=1)
        ),
        color_counts=tuple(
            ColorCount(
                ca_color_index=color[2],
                ca_color_rgb=color[1],
                ca_color_hex=color[0],
                residue_count=1,
            )
            for color in colors
        ),
    )
    annotation_path = dump_model(annotation, artifacts / "source-annotations.json")
    bundle = TargetBundle(
        schema_version="0.4",
        target_id="target",
        origin="imported",
        sequence_length=4,
        sequence_sha256="a" * 64,
        producer_attempt="attempt-0001",
        target_structure=_artifact(root, cif, "target-structure", "mmcif"),
        sequence=_artifact(root, sequence, "target-sequence", "fasta"),
        residue_mapping=_artifact(root, mapping_path, "residue-mapping", "json"),
        quality_report=_artifact(root, quality, "structure-quality", "json"),
        provenance=_artifact(root, provenance, "target-provenance", "json"),
        source_annotations=_artifact(
            root,
            annotation_path,
            "source-annotations",
            "json",
        ),
        coordinate_ensemble=CoordinateEnsemble(
            model_count=1,
            model_ids=("1",),
            representative_model_id="1",
        ),
    )
    bundle_path = dump_model(bundle, artifacts / "target-bundle.json")
    _, context = load_structure_context(
        run_root=root,
        target_bundle_path=bundle_path,
    )
    return root, bundle, mapping, context


def test_pse_fixed_colors_and_manual_auth_normalize_to_same_members(
    tmp_path: Path,
) -> None:
    root, bundle, mapping, context = _fixture(tmp_path)

    assert has_standard_pse_colors(run_root=root, bundle=bundle)
    pse_regions, evidence, validation = normalize_pse_color_regions(
        run_root=root,
        bundle=bundle,
        context=context,
        mapping=mapping,
    )
    manual_regions, _, _ = normalize_manual_regions(
        bundle=bundle,
        context=context,
        mapping=mapping,
        numbering="auth",
        chain="X",
        configured_regions=(
            ("A", ("21",)),
            ("B", ("23",)),
            ("C", ("24",)),
        ),
        input_config_sha256="b" * 64,
    )

    assert [
        tuple(member.label_seq_id for member in region.members)
        for region in pse_regions.regions
    ] == [(1,), (3,), (4,)]
    assert [
        tuple(member.label_seq_id for member in region.members)
        for region in manual_regions.regions
    ] == [(1,), (3,), (4,)]
    assert [
        member.preferred_author_identity
        for region in manual_regions.regions
        for member in region.members
    ] == [("X", "21"), ("X", "23"), ("X", "24")]
    assert evidence.standard_color_counts == {
        "#0000FF": 1,
        "#FF0000": 1,
        "#FFFF00": 1,
    }
    assert evidence.background_color_counts == {"#00FF00": 1}
    assert validation.region_count == 3


def test_manual_numbering_overlap_warns_without_editing_members(
    tmp_path: Path,
) -> None:
    _root, bundle, mapping, context = _fixture(tmp_path)

    regions, _, validation = normalize_manual_regions(
        bundle=bundle,
        context=context,
        mapping=mapping,
        numbering="uniprot",
        chain=None,
        configured_regions=(("A", ("101", "102")), ("C", ("102", "104"))),
        input_config_sha256="c" * 64,
    )

    assert validation.cross_region_overlaps == {"A-C": (2,)}
    assert tuple(member.label_seq_id for member in regions.regions[0].members) == (
        1,
        2,
    )
    assert tuple(member.label_seq_id for member in regions.regions[1].members) == (
        2,
        4,
    )


def test_manual_selector_must_map_uniquely(tmp_path: Path) -> None:
    _root, bundle, mapping, context = _fixture(tmp_path)

    with pytest.raises(ManifestStateError, match="无法唯一映射"):
        normalize_manual_regions(
            bundle=bundle,
            context=context,
            mapping=mapping,
            numbering="label",
            chain=None,
            configured_regions=(("A", ("99",)),),
            input_config_sha256="d" * 64,
        )


def test_source_auth_numbering_preserves_insertion_code_and_normalized_fallback(
    tmp_path: Path,
) -> None:
    _root, bundle, mapping, context = _fixture(tmp_path)
    updated_entries = tuple(
        entry.model_copy(update={"insertion_code": "A"})
        if entry.label_seq_id == 2
        else entry
        for entry in mapping.entries
    )
    updated_mapping = mapping.model_copy(update={"entries": updated_entries})

    source_regions, _, _ = normalize_manual_regions(
        bundle=bundle,
        context=context,
        mapping=updated_mapping,
        numbering="auth",
        chain="X",
        configured_regions=(("A", ("22A",)),),
        input_config_sha256="e" * 64,
    )
    source_member = source_regions.regions[0].members[0]
    assert source_member.label_seq_id == 2
    assert source_member.preferred_author_identity == ("X", "22")

    normalized_regions, _, _ = normalize_manual_regions(
        bundle=bundle,
        context=context,
        mapping=updated_mapping,
        numbering="auth",
        chain="A",
        configured_regions=(("A", ("22A",)),),
        input_config_sha256="f" * 64,
    )
    assert normalized_regions.regions[0].members[0].label_seq_id == 2


def test_partial_mapping_loads_only_coordinate_present_residues(
    tmp_path: Path,
) -> None:
    _root, bundle, mapping, context = _fixture(
        tmp_path,
        present_label_seq_ids=(1, 3, 4),
    )

    assert set(context.residues) == {1, 3, 4}
    with pytest.raises(ManifestStateError, match="不在代表模型"):
        normalize_manual_regions(
            bundle=bundle,
            context=context,
            mapping=mapping,
            numbering="auth",
            chain="X",
            configured_regions=(("A", ("22",)),),
            input_config_sha256="1" * 64,
        )
