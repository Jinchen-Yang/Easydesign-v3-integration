from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

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
from easydesign.orchestration.stage01_sources import execute_stage01_source
from easydesign.orchestration.workspace import initialize_run_workspace
from easydesign.stages.s01_target_preparation import TargetBundle

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
    latest_name = prepared.workspace.latest_manifest_pointer.read_text(
        encoding="utf-8"
    ).strip()
    run = load_model(
        prepared.workspace.run_root / "manifests" / latest_name,
        RunManifest,
    )
    assert attempt.status == "failed"
    assert stage.status == "failed"
    assert run.status == "failed"
    assert attempt.log_artifacts[0].verify(prepared.workspace.run_root).is_file()
