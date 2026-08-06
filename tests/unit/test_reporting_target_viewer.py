from __future__ import annotations

import hashlib
import json
import threading
import urllib.error
import urllib.request
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

import easydesign.reporting.target_viewer as target_viewer_module
from easydesign.backends.structure_prediction import (
    MsaMode,
    PredictionParameterProfile,
    StructurePredictionProduct,
    TemplateMode,
)
from easydesign.backends.target_sources import normalize_raw_sequence
from easydesign.core import (
    ArtifactIntegrityError,
    ArtifactRef,
    Attempt,
    ErrorInfo,
    EvidenceStatus,
    ExecutionStatus,
    RunManifest,
    StageId,
    StageManifest,
    dump_model,
    load_model,
)
from easydesign.reporting import (
    TargetViewerData,
    TargetViewerReportError,
    TargetViewerReportManifest,
    create_target_viewer_server,
    generate_stage01_target_viewer,
    generate_stage01_target_viewer_nonblocking,
    resolve_latest_target_viewer_report,
    verify_target_viewer_report,
)
from easydesign.safe_writes import read_last_text_line
from easydesign.stages.s01_target_preparation import (
    ColorCount,
    PseSourceAnnotations,
    ResidueColorAnnotation,
    build_predicted_target_bundle,
)

NOW = datetime(2026, 7, 24, 12, 0, tzinfo=UTC)
SEQUENCE = "ACDEFGHIKLMNPQRSTVWY"
THREE_LETTER = {
    "A": "ALA",
    "C": "CYS",
    "D": "ASP",
    "E": "GLU",
    "F": "PHE",
    "G": "GLY",
    "H": "HIS",
    "I": "ILE",
    "K": "LYS",
    "L": "LEU",
    "M": "MET",
    "N": "ASN",
    "P": "PRO",
    "Q": "GLN",
    "R": "ARG",
    "S": "SER",
    "T": "THR",
    "V": "VAL",
    "W": "TRP",
    "Y": "TYR",
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _prediction_product(tmp_path: Path) -> StructurePredictionProduct:
    structure = tmp_path / "predicted.cif"
    confidence = tmp_path / "confidence.json"
    lines = [
        "data_target",
        "loop_",
        "_atom_site.group_PDB",
        "_atom_site.label_atom_id",
        "_atom_site.type_symbol",
        "_atom_site.label_comp_id",
        "_atom_site.label_asym_id",
        "_atom_site.label_seq_id",
        "_atom_site.auth_asym_id",
        "_atom_site.auth_seq_id",
        "_atom_site.pdbx_PDB_ins_code",
        "_atom_site.Cartn_x",
        "_atom_site.Cartn_y",
        "_atom_site.Cartn_z",
        "_atom_site.occupancy",
        "_atom_site.pdbx_PDB_model_num",
    ]
    lines.extend(
        f"ATOM CA C {THREE_LETTER[amino_acid]} A {index} A {index} . "
        f"{index * 3.8:.1f} 0.0 0.0 1.0 1"
        for index, amino_acid in enumerate(SEQUENCE, start=1)
    )
    lines.append("#")
    structure.write_text("\n".join(lines) + "\n", encoding="utf-8")
    confidence.write_text("{}\n", encoding="utf-8")
    return StructurePredictionProduct(
        backend_name="protenix",
        backend_version="2.0.0",
        model_name="protenix-v2",
        seed=101,
        sample_index=0,
        structure_path=structure,
        structure_sha256=_sha256(structure),
        confidence_path=confidence,
        confidence_sha256=_sha256(confidence),
        plddt=84.0,
        gpde=3.5,
        ptm=0.65,
        iptm=0.0,
        ranking_score=0.65,
        has_clash=False,
        recycle_count=10,
    )


def _run_with_stage01(
    tmp_path: Path,
    *,
    run_status: ExecutionStatus = ExecutionStatus.SUCCEEDED,
) -> Path:
    run_root = tmp_path / "run"
    target = normalize_raw_sequence(SEQUENCE, target_id="viewer-target")
    built = build_predicted_target_bundle(
        run_root=run_root,
        attempt_id="attempt-0001",
        target=target,
        product=_prediction_product(tmp_path),
        model_checkpoint_sha256="8" * 64,
        msa_mode=MsaMode.DISABLED,
        msa_input_sha256=None,
        msa_server_mode=None,
        template_mode=TemplateMode.DISABLED,
        parameter_profile=PredictionParameterProfile.CUSTOM,
        resolved_cycle_count=1,
        resolved_diffusion_step_count=5,
    )
    attempt = Attempt(
        attempt_id="attempt-0001",
        status=ExecutionStatus.SUCCEEDED,
        created_at=NOW,
        started_at=NOW,
        ended_at=NOW,
        backend_name="protenix",
        backend_version="2.0.0",
        executor_name="local",
        seed=101,
    )
    bundle = built.bundle
    optional_artifacts = tuple(
        artifact
        for artifact in (
            bundle.reference_sequence,
            bundle.residue_mapping_tsv,
            bundle.identity_report,
            bundle.scope_report,
            bundle.structure_candidates,
            bundle.structure_candidates_tsv,
            bundle.retrieval_manifest,
            bundle.prediction_confidence,
            bundle.target_pdb,
        )
        if artifact is not None
    )
    stage = StageManifest(
        stage_id=StageId.TARGET_PREPARATION,
        contract_version="0.4",
        status=ExecutionStatus.SUCCEEDED,
        created_at=NOW,
        completed_at=NOW,
        output_artifacts=(
            bundle.target_structure,
            bundle.sequence,
            bundle.residue_mapping,
            bundle.quality_report,
            bundle.provenance,
            built.bundle_artifact,
        )
        + optional_artifacts,
        attempts=(attempt,),
        selected_attempt_id="attempt-0001",
    )
    stage_path = (
        run_root / "01-target-preparation" / "stage-manifest.v0001.json"
    )
    dump_model(stage, stage_path)
    config_path = run_root / "config-snapshot" / "easydesign.yaml"
    config_path.parent.mkdir(parents=True)
    config_path.write_text("schema_version: '0.1'\n", encoding="utf-8")
    config_ref = ArtifactRef.from_file(
        run_root=run_root,
        relative_path=config_path.relative_to(run_root).as_posix(),
        artifact_id="config-snapshot",
        role="config-snapshot",
        file_format="yaml",
    )
    stage_ref = ArtifactRef.from_file(
        run_root=run_root,
        relative_path=stage_path.relative_to(run_root).as_posix(),
        artifact_id="stage-01-manifest",
        role="stage-manifest",
        file_format="json",
        producer_stage="01-target-preparation",
        producer_attempt="attempt-0001",
    )
    manifest = RunManifest(
        revision=1,
        project_id="viewer-test",
        run_id="viewer-test-run",
        easydesign_version="0.1.0.dev0",
        code_commit="1234567",
        status=run_status,
        evidence_status=EvidenceStatus.IMPLEMENTED,
        created_at=NOW,
        updated_at=NOW,
        completed_at=NOW if run_status.is_terminal else None,
        config_snapshot=config_ref,
        stage_manifest_refs=(stage_ref,),
    )
    manifest_path = run_root / "manifests" / "run-manifest.v0001.json"
    dump_model(manifest, manifest_path)
    (run_root / "manifests" / "LATEST").write_text(
        f"{manifest_path.name}\n",
        encoding="utf-8",
    )
    return run_root


@pytest.mark.parametrize(
    "run_status",
    [ExecutionStatus.RUNNING, ExecutionStatus.SUCCEEDED],
)
def test_generate_portable_report_and_new_immutable_revision(
    tmp_path: Path,
    run_status: ExecutionStatus,
) -> None:
    run_root = _run_with_stage01(tmp_path, run_status=run_status)

    first = generate_stage01_target_viewer(run_root, generated_at=NOW)

    assert first.status is ExecutionStatus.SUCCEEDED
    assert first.report_root.name == "report-0001"
    first_manifest_bytes = first.manifest_path.read_bytes()
    manifest = verify_target_viewer_report(first.report_root)
    assert manifest.viewer_version == "5.11.0"
    data = load_model(first.report_root / "viewer-data.json", TargetViewerData)
    assert data.origin == "predicted"
    assert data.annotation.status == "not_applicable"
    assert data.sequence_length == len(data.residues) == 20
    report_text = (first.report_root / "viewer-data.json").read_text(encoding="utf-8")
    assert str(run_root) not in report_text
    assert ".a3m" not in report_text
    assert "api.colabfold.com" not in report_text
    assert (first.report_root / "data/target.cif").read_bytes() == (
        run_root / "01-target-preparation/attempt-0001/artifacts/target.cif"
    ).read_bytes()

    second = generate_stage01_target_viewer(run_root, generated_at=NOW)

    assert second.status is ExecutionStatus.SUCCEEDED
    assert second.report_root.name == "report-0002"
    assert first.manifest_path.read_bytes() == first_manifest_bytes
    assert read_last_text_line(
        run_root / "results/01-target-preparation/target-viewer/LATEST"
    ) == "report-0002/report-manifest.json"


def test_source_tampering_publishes_failed_revision_without_fallback(
    tmp_path: Path,
) -> None:
    run_root = _run_with_stage01(tmp_path)
    successful = generate_stage01_target_viewer(run_root, generated_at=NOW)
    stage_path = run_root / "01-target-preparation/stage-manifest.v0001.json"
    run_path = run_root / "manifests/run-manifest.v0001.json"
    stage_bytes = stage_path.read_bytes()
    run_bytes = run_path.read_bytes()
    mapping = run_root / (
        "01-target-preparation/attempt-0001/artifacts/residue-mapping.json"
    )
    mapping.write_text(mapping.read_text(encoding="utf-8") + "\n", encoding="utf-8")

    failed = generate_stage01_target_viewer(run_root, generated_at=NOW)

    assert failed.status is ExecutionStatus.FAILED
    assert failed.report_root.name == "report-0002"
    failed_manifest = load_model(
        failed.manifest_path,
        TargetViewerReportManifest,
    )
    assert failed_manifest.error is not None
    assert failed_manifest.error.code == "target-viewer-contract-failed"
    assert stage_path.read_bytes() == stage_bytes
    assert run_path.read_bytes() == run_bytes
    with pytest.raises(TargetViewerReportError, match="failed"):
        resolve_latest_target_viewer_report(run_root)
    assert verify_target_viewer_report(successful.report_root).status == "succeeded"


def test_report_file_tampering_is_rejected(tmp_path: Path) -> None:
    run_root = _run_with_stage01(tmp_path)
    outcome = generate_stage01_target_viewer(run_root, generated_at=NOW)
    (outcome.report_root / "viewer-data.json").write_text("{}\n", encoding="utf-8")

    with pytest.raises(ArtifactIntegrityError):
        verify_target_viewer_report(outcome.report_root)


def test_pse_annotation_mapping_mismatch_publishes_failed_report(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    run_root = _run_with_stage01(tmp_path)
    sources = target_viewer_module._load_sources(run_root)
    annotations = PseSourceAnnotations(
        residues=tuple(
            ResidueColorAnnotation(
                label_seq_id=entry.label_seq_id,
                author_chain_id=entry.author_chain_id,
                author_residue_id=(
                    "999" if entry.label_seq_id == 1 else entry.author_residue_id
                ),
                insertion_code=entry.insertion_code,
                ca_color_index=3,
                ca_color_rgb=(0.0, 1.0, 0.0),
                ca_color_hex="#00FF00",
            )
            for entry in sources.mapping.entries
        ),
        color_counts=(
            ColorCount(
                ca_color_index=3,
                ca_color_rgb=(0.0, 1.0, 0.0),
                ca_color_hex="#00FF00",
                residue_count=len(sources.mapping.entries),
            ),
        ),
    )
    monkeypatch.setattr(
        target_viewer_module,
        "_load_sources",
        lambda _: replace(sources, annotations=annotations),
    )

    outcome = generate_stage01_target_viewer(run_root, generated_at=NOW)

    assert outcome.status is ExecutionStatus.FAILED
    manifest = load_model(outcome.manifest_path, TargetViewerReportManifest)
    assert manifest.error is not None
    assert "residue mapping 身份不一致" in manifest.error.message


def test_failed_run_publishes_failed_report(tmp_path: Path) -> None:
    run_root = _run_with_stage01(
        tmp_path,
        run_status=ExecutionStatus.FAILED,
    )

    outcome = generate_stage01_target_viewer(run_root, generated_at=NOW)

    assert outcome.status is ExecutionStatus.FAILED
    manifest = load_model(outcome.manifest_path, TargetViewerReportManifest)
    assert manifest.error is not None
    assert "running/succeeded" in manifest.error.message


def test_failed_stage_publishes_failed_report(tmp_path: Path) -> None:
    run_root = _run_with_stage01(
        tmp_path,
        run_status=ExecutionStatus.RUNNING,
    )
    stage_path = run_root / "01-target-preparation/stage-manifest.v0001.json"
    run_path = run_root / "manifests/run-manifest.v0001.json"
    run = load_model(run_path, RunManifest)
    stage_path.rename(stage_path.with_name(f"{stage_path.name}.missing"))
    failed_attempt = Attempt(
        attempt_id="attempt-0001",
        status=ExecutionStatus.FAILED,
        created_at=NOW,
        started_at=NOW,
        ended_at=NOW,
        backend_name="protenix",
        backend_version="2.0.0",
        executor_name="local",
        seed=101,
        error=ErrorInfo(
            code="prediction-failed",
            message="synthetic Stage 01 failure",
            retryable=False,
        ),
    )
    failed_stage = StageManifest(
        stage_id=StageId.TARGET_PREPARATION,
        contract_version="0.2",
        status=ExecutionStatus.FAILED,
        created_at=NOW,
        completed_at=NOW,
        attempts=(failed_attempt,),
    )
    dump_model(failed_stage, stage_path)
    stage_ref = ArtifactRef.from_file(
        run_root=run_root,
        relative_path=stage_path.relative_to(run_root).as_posix(),
        artifact_id="stage-01-manifest",
        role="stage-manifest",
        file_format="json",
        producer_stage="01-target-preparation",
        producer_attempt="attempt-0001",
    )
    run_path.rename(run_path.with_name(f"{run_path.name}.missing"))
    failed_stage_run = RunManifest.model_validate(
        {
            **run.model_dump(mode="python"),
            "status": ExecutionStatus.RUNNING,
            "completed_at": None,
            "stage_manifest_refs": (stage_ref,),
        }
    )
    dump_model(failed_stage_run, run_path)

    outcome = generate_stage01_target_viewer(run_root, generated_at=NOW)

    assert outcome.status is ExecutionStatus.FAILED
    manifest = load_model(outcome.manifest_path, TargetViewerReportManifest)
    assert manifest.error is not None
    assert "succeeded Stage 01" in manifest.error.message


def test_local_server_exposes_only_verified_report(tmp_path: Path) -> None:
    run_root = _run_with_stage01(tmp_path)
    outcome = generate_stage01_target_viewer(run_root, generated_at=NOW)
    outside = tmp_path / "outside-secret.txt"
    outside.write_text("must not be served\n", encoding="utf-8")
    (outcome.report_root / "escape.txt").symlink_to(outside)
    server = create_target_viewer_server(outcome.report_root, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with urllib.request.urlopen(server.url, timeout=5) as response:
            assert response.status == 200
            assert response.headers["Content-Security-Policy"]
            assert b"EasyDesign Target Viewer" in response.read()
        with pytest.raises(urllib.error.HTTPError) as captured:
            urllib.request.urlopen(f"{server.url}%2e%2e/pyproject.toml", timeout=5)
        assert captured.value.code == 404
        with pytest.raises(urllib.error.HTTPError) as captured:
            urllib.request.urlopen(f"{server.url}escape.txt", timeout=5)
        assert captured.value.code == 404
    finally:
        server.server.shutdown()
        server.close()
        thread.join(timeout=5)


def test_report_contains_no_unexpected_root_files(tmp_path: Path) -> None:
    run_root = _run_with_stage01(tmp_path)
    outcome = generate_stage01_target_viewer(run_root, generated_at=NOW)

    actual = {
        path.relative_to(outcome.report_root).as_posix()
        for path in outcome.report_root.rglob("*")
        if path.is_file()
    }
    declared = {
        artifact.relative_path
        for artifact in load_model(
            outcome.manifest_path,
            TargetViewerReportManifest,
        ).output_artifacts
    }
    assert actual == declared | {"report-manifest.json"}
    assert not any("log" in path or "a3m" in path for path in actual)
    assert json.loads(
        (outcome.report_root / "viewer-data.json").read_text(encoding="utf-8")
    )["annotation"]["status"] == "not_applicable"


def test_nonblocking_integration_never_changes_scientific_success(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    run_root = _run_with_stage01(tmp_path)
    run_manifest = run_root / "manifests/run-manifest.v0001.json"
    stage_manifest = run_root / "01-target-preparation/stage-manifest.v0001.json"
    original_run = run_manifest.read_bytes()
    original_stage = stage_manifest.read_bytes()

    def catastrophic_failure(*args: object, **kwargs: object) -> None:
        del args, kwargs
        raise OSError("reporting storage unavailable")

    monkeypatch.setattr(
        target_viewer_module,
        "generate_stage01_target_viewer",
        catastrophic_failure,
    )

    outcome = generate_stage01_target_viewer_nonblocking(run_root)

    assert outcome.status is ExecutionStatus.FAILED
    assert outcome.error is not None
    assert outcome.error.code == "target-viewer-unpublished-failure"
    assert run_manifest.read_bytes() == original_run
    assert stage_manifest.read_bytes() == original_stage
