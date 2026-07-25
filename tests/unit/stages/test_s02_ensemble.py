from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from Bio.PDB.Atom import Atom
from Bio.PDB.Chain import Chain
from Bio.PDB.Model import Model
from Bio.PDB.Residue import Residue
from Bio.PDB.Structure import Structure

from easydesign.stages.s02_hotspot_discovery import (
    RegionParameters,
    SasaParameters,
    StructureContext,
    run_sasa_surface_diversity,
    run_scannet_region_proposals,
)
from easydesign.stages.s02_hotspot_discovery.geometry import (
    AtomCoordinate,
    CoordinateModelGeometry,
    ResidueGeometry,
    build_residue_graph,
    center_distance,
    minimum_region_atom_distance,
    shell_overlap,
)
from easydesign.stages.s02_hotspot_discovery.models import ResidueIdentity


def _residue(label: int, x: float) -> tuple[ResidueGeometry, Residue]:
    atoms = (
        AtomCoordinate("N", "N", (x - 1.2, 0.0, 0.0), 1.0),
        AtomCoordinate("CA", "C", (x, 0.0, 0.0), 1.0),
        AtomCoordinate("C", "C", (x + 1.2, 0.0, 0.0), 1.0),
        AtomCoordinate("O", "O", (x + 1.8, 0.0, 0.0), 1.0),
        AtomCoordinate("CB", "C", (x, 0.0, 1.5), 1.0),
    )
    identity = ResidueIdentity(
        sequence_index=label,
        amino_acid="A",
        label_asym_id="A",
        label_seq_id=label,
        auth_asym_id="A",
        auth_seq_id=str(label),
    )
    geometry = ResidueGeometry(
        identity=identity,
        residue_name="ALA",
        atoms=atoms,
        center=atoms[-1].xyz,
    )
    residue = Residue((" ", label, " "), "ALA", "")
    for serial, atom in enumerate(atoms, start=1):
        residue.add(
            Atom(
                atom.name,
                np.asarray(atom.xyz),
                0.0,
                atom.occupancy,
                " ",
                f"{atom.name:>4}"[-4:],
                serial,
                element=atom.element,
            )
        )
    return geometry, residue


def _context(
    coordinates: tuple[dict[int, float], ...],
) -> StructureContext:
    structure = Structure("ensemble")
    models = {}
    for index, coordinate_map in enumerate(coordinates, start=1):
        bio_model = Model(index - 1)
        chain = Chain("A")
        bio_model.add(chain)
        structure.add(bio_model)
        geometries = {}
        for label, x in coordinate_map.items():
            geometry, residue = _residue(label, x)
            geometries[label] = geometry
            chain.add(residue)
        models[str(index)] = CoordinateModelGeometry(
            model_id=str(index),
            residues=geometries,
            bio_model=bio_model,
        )
    representative = models["1"].residues
    return StructureContext(
        target_id="ensemble",
        target_structure=Path("/tmp/ensemble.cif"),
        target_structure_sha256="a" * 64,
        mapping_path=Path("/tmp/mapping.json"),
        label_asym_id="A",
        model_ids=tuple(models),
        representative_model_id="1",
        models=models,
        residues=representative,
        bio_structure=structure,
    )


def test_sasa_presence_and_exposure_use_all_models_as_denominator() -> None:
    coordinates = tuple(
        {
            **({1: 0.0} if index < 7 else {}),
            **({2: 100.0} if index < 6 else {}),
            3: 200.0,
        }
        for index in range(10)
    )
    context = _context(coordinates)

    evidence, _pool, _recommended = run_sasa_surface_diversity(
        context=context,
        region_parameters=RegionParameters(
            requested_region_count=2,
            minimum_region_count=2,
            target_member_count=5,
            minimum_member_count=5,
        ),
        sasa_parameters=SasaParameters(ensemble_consensus_fraction=0.70),
    )

    by_label = {
        item.residue.label_seq_id: item
        for item in evidence.residues
    }
    assert by_label[1].model_presence_fraction == 0.7
    assert by_label[1].exposure_frequency_relaxed == 0.7
    assert by_label[1].eligible is True
    assert by_label[2].model_presence_fraction == 0.6
    assert by_label[2].eligible is False
    assert "insufficient-model-presence" in by_label[2].excluded_reasons
    assert len(by_label[1].model_evidence) == 10


def test_spatial_edge_requires_ceil_consensus_support() -> None:
    seven_support = _context(
        tuple(
            {1: 0.0, 2: 3.0 if index < 7 else 30.0}
            for index in range(10)
        )
    )
    six_support = _context(
        tuple(
            {1: 0.0, 2: 3.0 if index < 6 else 30.0}
            for index in range(10)
        )
    )

    graph_seven = build_residue_graph(
        seven_support,
        {1, 2},
        heavy_atom_distance=5.0,
        anchor_distance=12.0,
        consensus_fraction=0.70,
    )
    graph_six = build_residue_graph(
        six_support,
        {1, 2},
        heavy_atom_distance=5.0,
        anchor_distance=12.0,
        consensus_fraction=0.70,
    )

    assert graph_seven[1] == {2}
    assert graph_six[1] == set()


def test_region_separation_uses_worst_case_model() -> None:
    context = _context(
        (
            {1: 0.0, 2: 30.0},
            {1: 0.0, 2: 5.0},
        )
    )

    assert center_distance(context, (1,), (2,)) == pytest.approx(5.0)
    assert minimum_region_atom_distance(context, (1,), (2,)) < 5.0
    assert shell_overlap(
        context,
        (1,),
        (2,),
        shell_radius=8.0,
    ) == pytest.approx(1.0)


def test_scannet_rejects_ensemble_without_representative_fallback() -> None:
    context = _context(({1: 0.0}, {1: 0.5}))

    with pytest.raises(ValueError, match="unsupported_ensemble"):
        run_scannet_region_proposals(
            context=context,
            probabilities={1: 0.9},
            method_version="test",
        )
