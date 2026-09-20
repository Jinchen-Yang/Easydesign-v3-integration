from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import gemmi
import pytest
import yaml

from easydesign.backends.target_sources.structure import (
    build_experimental_target_bundle,
)
from easydesign.core import (
    Attempt,
    RunManifest,
    StageManifest,
    TargetInputError,
    load_model,
    sha256_file,
)
from easydesign.orchestration.project import initialize_project
from easydesign.orchestration.stage01_sources import (
    _candidate,
    _search_matches,
    _structure_selection_option,
    _uniprot_identity,
    execute_stage01_source,
)
from easydesign.orchestration.workspace import initialize_run_workspace
from easydesign.safe_writes import read_last_text_line
from easydesign.stages.s01_target_preparation import TargetBundle
from easydesign.stages.s02_hotspot_discovery import load_structure_context

SEQUENCE = "ACDEFGHIKLMNPQRSTVWY"
RESIDUE_NAMES = (
    "ALA",
    "CYS",
    "ASP",
    "GLU",
    "PHE",
    "GLY",
    "HIS",
    "ILE",
    "LYS",
    "LEU",
    "MET",
    "ASN",
    "PRO",
    "GLN",
    "ARG",
    "SER",
    "THR",
    "VAL",
    "TRP",
    "TYR",
)


def _partial_mmcif(path: Path) -> None:
    structure = gemmi.Structure()
    structure.name = "partial-candidate"
    model = gemmi.Model(1)
    chain = gemmi.Chain("X")
    for label_seq_id, residue_name in ((1, "ALA"), (3, "ASP"), (4, "GLU")):
        residue = gemmi.Residue()
        residue.name = residue_name
        residue.seqid = gemmi.SeqId(label_seq_id, " ")
        residue.subchain = "A"
        residue.label_seq = label_seq_id
        atom = gemmi.Atom()
        atom.name = "CA"
        atom.element = gemmi.Element("C")
        atom.pos = gemmi.Position(float(label_seq_id), 0.0, 0.0)
        residue.add_atom(atom)
        chain.add_residue(residue)
    model.add_chain(chain)
    structure.add_model(model)
    structure.setup_entities()
    structure.entities[0].full_sequence = ["ALA", "CYS", "ASP", "GLU"]
    structure.assign_label_seq_id()
    path.write_text(structure.make_mmcif_document().as_string(), encoding="utf-8")


def _single_chain_pdb() -> str:
    rows = []
    atom_id = 1
    for residue_id, residue_name in enumerate(RESIDUE_NAMES, start=1):
        for atom_name, offset, element in (("N", 0.0, "N"), ("CA", 1.0, "C")):
            x = residue_id * 3.0 + offset
            rows.append(
                f"ATOM  {atom_id:5d} {atom_name:^4s} {residue_name} A"
                f"{residue_id:4d}    {x:8.3f}{0.0:8.3f}{0.0:8.3f}"
                f"  1.00 20.00          {element:>2s}"
            )
            atom_id += 1
    return "\n".join(rows) + "\nEND\n"


@pytest.mark.parametrize(
    ("entry_type", "expected"),
    [
        ("UniProtKB reviewed (Swiss-Prot)", True),
        ("reviewed", True),
        ("UniProtKB unreviewed (TrEMBL)", False),
        (None, False),
    ],
)
def test_uniprot_identity_distinguishes_reviewed_from_unreviewed(
    entry_type: str | None,
    expected: bool,
) -> None:
    _, _, report = _uniprot_identity(
        {
            "primaryAccession": "P00001",
            "sequence": {"value": "ACDE"},
            "organism": {"taxonId": 9606},
            "entryType": entry_type,
        }
    )

    assert report["reviewed"] is expected


def test_uniprot_search_does_not_promote_unreviewed_result() -> None:
    matches = _search_matches(
        {
            "results": [
                {
                    "primaryAccession": "A0A000",
                    "uniProtkbId": "GENE_SPECIES",
                    "entryType": "UniProtKB unreviewed (TrEMBL)",
                    "genes": [{"geneName": {"value": "GENE"}}],
                    "proteinDescription": {},
                }
            ]
        },
        "GENE",
    )

    assert matches[0]["exact"] is True
    assert matches[0]["reviewed"] is False


def test_rcsb_candidate_keeps_identity_eligible_when_coordinates_are_partial(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    structure_path = tmp_path / "partial.cif"
    _partial_mmcif(structure_path)
    monkeypatch.setattr(
        "easydesign.orchestration.stage01_sources.rcsb_entry",
        lambda *_: SimpleNamespace(
            json=lambda: {
                "exptl": [{"method": "X-RAY DIFFRACTION"}],
                "rcsb_entry_info": {"resolution_combined": [2.0]},
                "struct": {"title": "Deposited target in a bound active-state complex"},
                "struct_keywords": {"text": "TARGET, ACTIVE STATE"},
                "citation": [
                    {
                        "rcsb_is_primary": "Y",
                        "title": "Primary structure report",
                        "pdbx_database_id_DOI": "10.1000/example",
                    }
                ],
            }
        ),
    )
    monkeypatch.setattr(
        "easydesign.orchestration.stage01_sources.rcsb_polymer_entity",
        lambda *_: SimpleNamespace(
            json=lambda: {
                "entity_poly": {"pdbx_seq_one_letter_code_can": "ACDE"},
                "rcsb_polymer_entity_container_identifiers": {
                    "auth_asym_ids": ["X"],
                    "uniprot_ids": ["P00001"],
                    "reference_sequence_identifiers": [
                        {
                            "database_name": "UniProt",
                            "database_accession": "P00001",
                            "entity_sequence_coverage": 1.0,
                            "reference_sequence_coverage": 1.0,
                            "provenance_source": "SIFTS",
                        }
                    ],
                },
                "rcsb_polymer_entity": {
                    "pdbx_description": "Deposited target entity",
                    "rcsb_multiple_source_flag": "N",
                    "rcsb_source_part_count": 1,
                },
            }
        ),
    )
    monkeypatch.setattr(
        "easydesign.orchestration.stage01_sources.rcsb_mmcif",
        lambda *_: SimpleNamespace(artifact_path=structure_path),
    )

    candidate, selected_path = _candidate(
        client=object(),  # type: ignore[arg-type]
        pdb_id="TEST",
        entity_id="1",
        expected_scope="ACDE",
    )

    assert selected_path == structure_path
    assert candidate["eligible"] is True
    assert candidate["scope_identity"] == 1.0
    assert candidate["scope_coordinate_coverage"] == 0.75
    assert candidate["warnings"] == ["scope-coordinate-coverage-partial"]
    assert candidate["missing_coordinate_ranges"] == [
        {"start": 2, "end": 2, "kind": "internal"}
    ]
    assert candidate["deposited_title"] == "Deposited target in a bound active-state complex"
    assert candidate["deposited_keywords"] == "TARGET, ACTIVE STATE"
    assert candidate["entity_description"] == "Deposited target entity"
    assert candidate["uniprot_ids"] == ["P00001"]
    assert candidate["reference_sequence_identifiers"][0][
        "reference_sequence_coverage"
    ] == 1.0
    option = _structure_selection_option(candidate)
    assert "canonical_alignment_coverage=1.0" in option.description
    assert "coordinate_coverage=0.75" in option.description
    assert "deposited_title=Deposited target" in option.description
    assert option.payload["candidate_summary"]["entity_description"] == (
        "Deposited target entity"
    )
    assert option.payload["candidate_summary"]["reference_sequence_identifiers"] == [
        {
            "database_accession": "P00001",
            "entity_sequence_coverage": 1.0,
            "reference_sequence_coverage": 1.0,
            "provenance_source": "SIFTS",
        }
    ]


def test_target_bundle_reimport_preserves_optional_evidence(tmp_path: Path) -> None:
    source_structure = tmp_path / "source.pdb"
    source_structure.write_text(
        """ATOM      1  N   ALA X  10       0.000   0.000   0.000  1.00 20.00           N
ATOM      2  CA  ALA X  10       1.000   0.000   0.000  1.00 20.00           C
END
""",
        encoding="utf-8",
    )
    source_run = tmp_path / "source-run"
    source_bundle = build_experimental_target_bundle(
        run_root=source_run,
        attempt_id="attempt-0001",
        target_id="bundle-target",
        source_path=source_structure,
        source_format="pdb",
        selected_chain="X",
        expected_scope_sequence="A",
        reference_sequence="A",
        reference_start=1,
        identity_report={"status": "resolved", "accession": "P00001"},
        scope_report={"type": "full-sequence"},
        candidates=[{"pdb_id": "TEST", "eligible": True, "reasons": []}],
        quality_report={"eligibility": True},
        provenance={"source": "unit-test"},
        retrieval_records=[],
        preserve_source_context=True,
    ).built_bundle
    project = tmp_path / "project"
    project.mkdir()
    config = project / "easydesign.yaml"
    config.write_text(
        yaml.safe_dump(
            {
                "schema_version": "0.4",
                "project_id": "bundle-import",
                "workflow": {
                    "execution_mode": "review-gated",
                    "stop_after_stage": 1,
                    "cache_mode": "offline",
                },
                "stage01": {
                    "target": {
                        "id": "bundle-target",
                        "source": {
                            "type": "target-bundle",
                            "path": str(source_bundle.bundle_path),
                            "source_run_root": str(source_run),
                        },
                        "scope": {"type": "full-sequence"},
                    },
                    "structure_prediction": None,
                },
                "stage02": None,
                "stage03": None,
                "stage04": None,
                "stage05": None,
                "stage06": None,
                "stage07": None,
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    prepared = initialize_run_workspace(
        config_path=config,
        runs_root=tmp_path / "runs",
        easydesign_version="0.1.0.dev2",
        code_commit="abcdef0",
        run_id="bundle-reimport",
    )

    outcome = execute_stage01_source(prepared)

    assert outcome.status == "succeeded"
    assert outcome.built_bundle is not None
    imported = load_model(
        outcome.built_bundle.bundle_path,
        TargetBundle,
    )
    assert imported.schema_version == "0.4"
    assert imported.identity_report is not None
    assert imported.scope_report is not None
    assert imported.structure_candidates is not None
    assert imported.source_context is not None
    assert imported.target_pdb is not None
    assert sha256_file(imported.target_structure.verify(outcome.run_root)) == sha256_file(
        source_bundle.bundle.target_structure.verify(source_run)
    )


def test_fasta_uses_rcsb_experimental_first_before_prediction(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fasta = tmp_path / "target.fasta"
    fasta.write_text(f">target\n{SEQUENCE}\n", encoding="utf-8")
    experimental = tmp_path / "experimental.pdb"
    experimental.write_text(_single_chain_pdb(), encoding="utf-8")
    initialized = initialize_project(
        project_root=tmp_path / "sequence-project",
        target=fasta,
    )
    prepared = initialize_run_workspace(
        config_path=initialized.config_path,
        runs_root=tmp_path / "runs",
        easydesign_version="0.1.0.dev2",
        code_commit="abcdef0",
        run_id="sequence-experimental-first",
    )

    class FakeClient:
        records: list[object] = []

        def __init__(self, **_: object) -> None:
            pass

        def __enter__(self) -> FakeClient:
            return self

        def __exit__(self, *_: object) -> None:
            pass

    monkeypatch.setattr(
        "easydesign.orchestration.stage01_sources.ScientificHttpClient",
        FakeClient,
    )
    monkeypatch.setattr(
        "easydesign.orchestration.stage01_sources.rcsb_sequence_search",
        lambda *_: SimpleNamespace(
            json=lambda: {"result_set": [{"identifier": "TEST_1"}]}
        ),
    )
    monkeypatch.setattr(
        "easydesign.orchestration.stage01_sources._candidate",
        lambda **_: (
            {
                "pdb_id": "TEST",
                "entity_id": "1",
                "chain": "A",
                "method": "X-RAY DIFFRACTION",
                "resolution_angstrom": 2.0,
                "entity_sequence_length": len(SEQUENCE),
                "scope_coverage": 1.0,
                "scope_identity": 1.0,
                "eligible": True,
                "review_eligible": False,
                "reasons": [],
            },
            experimental,
        ),
    )

    outcome = execute_stage01_source(prepared)

    assert outcome.status == "succeeded"
    assert outcome.built_bundle is not None
    assert outcome.built_bundle.bundle.origin == "experimental"
    assert outcome.built_bundle.bundle.sequence_length == len(SEQUENCE)
    _, context = load_structure_context(
        run_root=outcome.run_root,
        target_bundle_path=outcome.built_bundle.bundle_path,
    )
    assert context.label_asym_id == "A"
    assert len(context.residues) == len(SEQUENCE)


def test_structural_only_local_range_is_rejected_as_ambiguous(
    tmp_path: Path,
) -> None:
    structure = tmp_path / "target.pdb"
    structure.write_text(_single_chain_pdb(), encoding="utf-8")
    initialized = initialize_project(
        project_root=tmp_path / "local-range",
        target=structure,
        scope_range=(1, 10),
    )
    prepared = initialize_run_workspace(
        config_path=initialized.config_path,
        runs_root=tmp_path / "runs",
        easydesign_version="0.1.0.dev2",
        code_commit="abcdef0",
        run_id="local-range",
    )

    with pytest.raises(
        TargetInputError,
        match="structural-only 本地结构只能使用 full-sequence",
    ):
        execute_stage01_source(prepared)

    attempt = load_model(
        prepared.workspace.attempt_root(
            "01-target-preparation",
            "attempt-0001",
        )
        / "attempt-manifest.json",
        Attempt,
    )
    stage = load_model(
        prepared.workspace.stage_root("01-target-preparation")
        / "stage-manifest.v0001.json",
        StageManifest,
    )
    latest_name = read_last_text_line(prepared.workspace.latest_manifest_pointer)
    run = load_model(
        prepared.workspace.run_root / "manifests" / latest_name,
        RunManifest,
    )
    assert attempt.status == "failed"
    assert stage.status == "failed"
    assert run.status == "failed"
    assert attempt.log_artifacts[0].verify(prepared.workspace.run_root).is_file()
