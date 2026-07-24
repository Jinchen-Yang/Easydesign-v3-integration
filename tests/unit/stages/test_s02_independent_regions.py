from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from Bio.PDB.Atom import Atom
from Bio.PDB.Chain import Chain
from Bio.PDB.Model import Model
from Bio.PDB.Residue import Residue
from Bio.PDB.Structure import Structure

from easydesign.core import ConfigurationError
from easydesign.stages.s02_hotspot_discovery import (
    ManualRegionProvider,
    PseAnnotationRegionProvider,
    RegionMethod,
    RegionParameters,
    StructureContext,
    compare_independent_methods,
    run_sasa_surface_diversity,
    run_scannet_region_proposals,
)
from easydesign.stages.s02_hotspot_discovery.geometry import (
    AtomCoordinate,
    ResidueGeometry,
)
from easydesign.stages.s02_hotspot_discovery.models import ResidueIdentity


def synthetic_context() -> StructureContext:
    structure = Structure("synthetic")
    model = Model(0)
    chain = Chain("A")
    model.add(chain)
    structure.add(model)
    geometries: dict[int, ResidueGeometry] = {}
    label = 1
    for cluster_index, origin_x in enumerate((0.0, 30.0, 60.0)):
        for member_index in range(6):
            angle = member_index * np.pi / 3
            center = (
                origin_x + 3.0 * float(np.cos(angle)),
                3.0 * float(np.sin(angle)),
                0.5 * cluster_index,
            )
            atom_rows = (
                AtomCoordinate("N", "N", (center[0] - 1.2, center[1], center[2]), 1.0),
                AtomCoordinate("CA", "C", center, 1.0),
                AtomCoordinate("C", "C", (center[0] + 1.2, center[1], center[2]), 1.0),
                AtomCoordinate("O", "O", (center[0] + 1.8, center[1], center[2]), 1.0),
                AtomCoordinate("CB", "C", (center[0], center[1], center[2] + 1.5), 1.0),
            )
            identity = ResidueIdentity(
                sequence_index=label,
                amino_acid="A",
                label_asym_id="Axp",
                label_seq_id=label,
                auth_asym_id="A",
                auth_seq_id=str(label + 22),
            )
            geometries[label] = ResidueGeometry(
                identity=identity,
                residue_name="ALA",
                atoms=atom_rows,
                center=atom_rows[-1].xyz,
            )
            bio_residue = Residue((" ", label, " "), "ALA", "")
            for serial, atom in enumerate(atom_rows, start=1):
                bio_residue.add(
                    Atom(
                        atom.name,
                        np.asarray(atom.xyz),
                        0.0,
                        1.0,
                        " ",
                        f"{atom.name:>4}"[-4:],
                        serial,
                        element=atom.element,
                    )
                )
            chain.add(bio_residue)
            label += 1
    return StructureContext(
        target_id="synthetic",
        target_structure=Path("/tmp/synthetic.cif"),
        target_structure_sha256="0" * 64,
        mapping_path=Path("/tmp/residue-mapping.json"),
        label_asym_id="Axp",
        residues=geometries,
        bio_structure=structure,
    )


def parameters() -> RegionParameters:
    return RegionParameters(
        requested_region_count=3,
        target_member_count=6,
        minimum_member_count=6,
    )


def test_sasa_and_scannet_outputs_remain_method_separated() -> None:
    context = synthetic_context()
    sasa_evidence, sasa_pool, sasa_recommended = run_sasa_surface_diversity(
        context=context,
        region_parameters=parameters(),
    )
    probabilities = {
        label: 0.95 - 0.01 * ((label - 1) % 6)
        for label in context.residues
    }
    scannet_evidence, scannet_pool, scannet_recommended = (
        run_scannet_region_proposals(
            context=context,
            probabilities=probabilities,
            method_version="test-scannet",
            region_parameters=parameters(),
        )
    )

    assert sasa_evidence.method is RegionMethod.SASA_SURFACE_DIVERSITY
    assert scannet_evidence.method is RegionMethod.SCANNET_EPITOPE_NO_MSA
    assert all(item.scannet_probability is None for item in sasa_evidence.residues)
    assert all(item.rsasa is None for item in scannet_evidence.residues)
    assert len(sasa_pool.candidates) >= 3
    assert len(scannet_pool.candidates) >= 3
    assert len(sasa_recommended.regions) == 3
    assert len(scannet_recommended.regions) == 3
    assert all(
        region.metrics.mean_scannet_probability is None
        for region in sasa_recommended.regions
    )
    assert all(
        region.metrics.mean_rsasa is None
        for region in scannet_recommended.regions
    )

    comparison = compare_independent_methods(
        context=context,
        sasa=sasa_recommended,
        scannet=scannet_recommended,
    )
    assert comparison.fused_score is None
    assert comparison.winner is None
    assert len(comparison.overlaps) == 9
    assert len(comparison.best_matches) == 3


def test_scannet_requires_complete_residue_probability_mapping() -> None:
    context = synthetic_context()
    with pytest.raises(ValueError, match="residue 集合不完整"):
        run_scannet_region_proposals(
            context=context,
            probabilities={1: 0.5},
            method_version="test-scannet",
            region_parameters=parameters(),
        )


def test_unimplemented_region_sources_fail_without_fallback() -> None:
    with pytest.raises(ConfigurationError, match="PSE 染色区域导入尚未实现"):
        PseAnnotationRegionProvider().propose()
    with pytest.raises(ConfigurationError, match="人工区域上传尚未实现"):
        ManualRegionProvider().propose()
