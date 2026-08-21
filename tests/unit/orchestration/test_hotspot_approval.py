from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml

from easydesign.core import (
    ArtifactRef,
    Attempt,
    CodeIdentity,
    CodeIdentitySource,
    EvidenceStatus,
    ExecutionStatus,
    ManifestStateError,
    RunManifest,
    StageId,
    StageManifest,
    WorkflowState,
    WorkflowStateType,
    dump_model,
    load_model,
)
from easydesign.orchestration.config import (
    EasyDesignRunConfig,
    Stage01Config,
    Stage02Config,
    Stage02Method,
    TargetSourceConfig,
    WorkflowConfig,
)
from easydesign.orchestration.hotspots import (
    approve_hotspots,
    export_hotspot_review,
)
from easydesign.orchestration.workspace import ResolvedRunConfig
from easydesign.safe_writes import read_last_text_line
from easydesign.stages.s01_target_preparation import (
    CoordinateEnsemble,
    ResidueMapping,
    ResidueMappingEntry,
    TargetBundle,
)
from easydesign.stages.s02_hotspot_discovery import (
    AnnotationReport,
    AnnotationStatus,
    ApprovalRecord,
    CandidateSurfaceRegion,
    EvidenceLevel,
    HotspotsFile,
    RecommendedRegionSet,
    RegionMethod,
    RegionMetrics,
    RegionReviewStatus,
    ResidueIdentity,
)

NOW = datetime(2026, 7, 25, 10, 0, tzinfo=UTC)


def _artifact(
    root: Path,
    path: Path,
    artifact_id: str,
    role: str,
    file_format: str,
    *,
    stage: StageId | None = None,
    attempt: str | None = None,
) -> ArtifactRef:
    return ArtifactRef.from_file(
        run_root=root,
        relative_path=path.relative_to(root).as_posix(),
        artifact_id=artifact_id,
        role=role,
        file_format=file_format,
        producer_stage=str(stage) if stage is not None else None,
        producer_attempt=attempt,
    )


def _region(index: int, labels: tuple[int, ...]) -> CandidateSurfaceRegion:
    members = tuple(
        ResidueIdentity(
            sequence_index=label,
            amino_acid="A",
            label_asym_id="A",
            label_seq_id=label,
            auth_asym_id="A",
            auth_seq_id=str(label + 20),
            source_auth_asym_id="X",
            source_auth_seq_id=str(label + 20),
        )
        for label in labels
    )
    return CandidateSurfaceRegion(
        region_id=f"sasa-candidate-{index:04d}",
        method=RegionMethod.SASA_SURFACE_DIVERSITY,
        seed_label_seq_id=labels[0],
        members=members,
        centroid_angstrom=(float(index * 20), 0.0, 0.0),
        ranking_score=1.0 - index / 10,
        metrics=RegionMetrics(
            mean_rsasa=0.5,
            q25_rsasa=0.4,
            graph_density=0.8,
            compactness_score=0.7,
            radius_gyration_angstrom=4.0,
        ),
    )


def _prepared_run(tmp_path: Path) -> Path:
    root = tmp_path / "runs/demo/run-001"
    stage01_root = root / "01-target-preparation/attempt-0001/artifacts"
    stage02_root = root / "02-hotspot-discovery/attempt-0001/artifacts"
    manifests = root / "manifests"
    stage01_root.mkdir(parents=True)
    stage02_root.mkdir(parents=True)
    manifests.mkdir()
    (root / "config-snapshot").mkdir()

    target = stage01_root / "target.cif"
    target.write_text("data_target\n#\n", encoding="utf-8")
    sequence = stage01_root / "sequence.fasta"
    sequence.write_text(">target\n" + "A" * 15 + "\n", encoding="utf-8")
    mapping_path = stage01_root / "residue-mapping.json"
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
            )
            for index in range(1, 16)
        ),
    )
    dump_model(mapping, mapping_path)
    quality = stage01_root / "quality.json"
    quality.write_text("{}\n", encoding="utf-8")
    provenance = stage01_root / "provenance.json"
    provenance.write_text("{}\n", encoding="utf-8")
    stage01_refs = (
        _artifact(
            root,
            target,
            "target-structure",
            "normalized-target-structure",
            "mmcif",
            stage=StageId.TARGET_PREPARATION,
            attempt="attempt-0001",
        ),
        _artifact(
            root,
            sequence,
            "target-sequence",
            "normalized-target-sequence",
            "fasta",
            stage=StageId.TARGET_PREPARATION,
            attempt="attempt-0001",
        ),
        _artifact(
            root,
            mapping_path,
            "residue-mapping",
            "residue-numbering-map",
            "json",
            stage=StageId.TARGET_PREPARATION,
            attempt="attempt-0001",
        ),
        _artifact(
            root,
            quality,
            "structure-quality",
            "structure-quality-report",
            "json",
            stage=StageId.TARGET_PREPARATION,
            attempt="attempt-0001",
        ),
        _artifact(
            root,
            provenance,
            "target-provenance",
            "target-provenance",
            "json",
            stage=StageId.TARGET_PREPARATION,
            attempt="attempt-0001",
        ),
    )
    bundle = TargetBundle(
        target_id="target",
        origin="imported",
        sequence_length=15,
        sequence_sha256="a" * 64,
        producer_attempt="attempt-0001",
        target_structure=stage01_refs[0],
        sequence=stage01_refs[1],
        residue_mapping=stage01_refs[2],
        quality_report=stage01_refs[3],
        provenance=stage01_refs[4],
        coordinate_ensemble=CoordinateEnsemble(
            model_count=1,
            model_ids=("1",),
            representative_model_id="1",
        ),
    )
    bundle_path = dump_model(bundle, stage01_root / "target-bundle.json")
    bundle_ref = _artifact(
        root,
        bundle_path,
        "target-bundle",
        "target-bundle",
        "json",
        stage=StageId.TARGET_PREPARATION,
        attempt="attempt-0001",
    )
    attempt1 = Attempt(
        attempt_id="attempt-0001",
        status=ExecutionStatus.SUCCEEDED,
        created_at=NOW,
        started_at=NOW,
        ended_at=NOW,
        backend_name="test",
        executor_name="test",
    )
    stage01 = StageManifest(
        stage_id=StageId.TARGET_PREPARATION,
        contract_version="0.3",
        status=ExecutionStatus.SUCCEEDED,
        created_at=NOW,
        completed_at=NOW,
        output_artifacts=stage01_refs + (bundle_ref,),
        attempts=(attempt1,),
        selected_attempt_id="attempt-0001",
    )
    stage01_path = dump_model(stage01, stage01_root / "stage-manifest.json")

    recommended = RecommendedRegionSet(
        method=RegionMethod.SASA_SURFACE_DIVERSITY,
        status=RegionReviewStatus.NEEDS_HUMAN_VISUAL_CONFIRMATION,
        requested_region_count=3,
        minimum_region_count=2,
        regions=(
            _region(1, (1, 2, 3, 4, 5)),
            _region(2, (6, 7, 8, 9, 10)),
            _region(3, (11, 12, 13, 14, 15)),
        ),
    )
    regions_path = dump_model(
        recommended,
        stage02_root / "recommended-regions.json",
    )
    annotation = AnnotationReport(
        status=AnnotationStatus.NOT_REQUESTED,
        evidence_level=EvidenceLevel.STRUCTURAL_ONLY,
        identity_resolution="not_attempted",
    )
    annotation_path = dump_model(
        annotation,
        stage02_root / "annotation-report.json",
    )
    stage02_outputs = (
        _artifact(
            root,
            regions_path,
            "sasa-recommended-regions",
            "recommended-region-set",
            "json",
            stage=StageId.HOTSPOT_DISCOVERY,
            attempt="attempt-0001",
        ),
        _artifact(
            root,
            annotation_path,
            "stage02-annotation-report",
            "scientific-annotation",
            "json",
            stage=StageId.HOTSPOT_DISCOVERY,
            attempt="attempt-0001",
        ),
    )
    stage02 = StageManifest(
        stage_id=StageId.HOTSPOT_DISCOVERY,
        contract_version="0.2",
        status=ExecutionStatus.SUCCEEDED,
        created_at=NOW,
        completed_at=NOW,
        input_artifacts=(bundle_ref, stage01_refs[0], stage01_refs[2]),
        output_artifacts=stage02_outputs,
        attempts=(attempt1,),
        selected_attempt_id="attempt-0001",
    )
    stage02_path = dump_model(stage02, stage02_root / "stage-manifest.json")

    source = root / "input.pse"
    source.write_bytes(b"pse")
    config_snapshot = root / "config-snapshot/easydesign.yaml"
    config_snapshot.write_text("schema_version: '0.3'\n", encoding="utf-8")
    input_snapshot = root / "input-snapshot.pse"
    input_snapshot.write_bytes(b"pse")
    config_ref = _artifact(
        root,
        config_snapshot,
        "config-snapshot",
        "run-configuration",
        "yaml",
    )
    input_ref = _artifact(
        root,
        input_snapshot,
        "input-snapshot",
        "target-input",
        "pse",
    )
    user_config = EasyDesignRunConfig(
        project_id="demo",
        workflow=WorkflowConfig(stop_after_stage=2),
        stage01=Stage01Config(
            target=TargetSourceConfig(id="target", source=source),
        ),
        stage02=Stage02Config(methods=(Stage02Method.SASA,)),
    )
    resolved = ResolvedRunConfig(
        project_id="demo",
        run_id="run-001",
        user_config=user_config,
        detected_input_format="pse",
        input_snapshot=input_ref,
        stop_after_stage=2,
    )
    dump_model(resolved, root / "config-snapshot/resolved-config.json")
    stage01_manifest_ref = _artifact(
        root,
        stage01_path,
        "stage-01-manifest",
        "stage-manifest",
        "json",
        stage=StageId.TARGET_PREPARATION,
        attempt="attempt-0001",
    )
    stage02_manifest_ref = _artifact(
        root,
        stage02_path,
        "stage-02-manifest",
        "stage-manifest",
        "json",
        stage=StageId.HOTSPOT_DISCOVERY,
        attempt="attempt-0001",
    )
    run = RunManifest(
        schema_version="1.2",
        revision=1,
        project_id="demo",
        run_id="run-001",
        easydesign_version="0.1.0.dev2",
        code_identity=CodeIdentity(
            version="0.1.0.dev2",
            source=CodeIdentitySource.GIT,
            git_commit="1" * 40,
            dirty=False,
        ),
        workflow_state=WorkflowState(
            state=WorkflowStateType.AWAITING_HUMAN_APPROVAL,
            stage_id=StageId.HOTSPOT_DISCOVERY,
            action="approve-hotspots",
            message="approval required",
        ),
        status=ExecutionStatus.RUNNING,
        evidence_status=EvidenceStatus.IMPLEMENTED,
        created_at=NOW,
        updated_at=NOW,
        config_snapshot=config_ref,
        stage_manifest_refs=(stage01_manifest_ref, stage02_manifest_ref),
    )
    run_path = dump_model(run, manifests / "run-manifest.v0001.json")
    assert run_path.is_file()
    (manifests / "LATEST").write_text(
        "run-manifest.v0001.json\n",
        encoding="utf-8",
    )
    return root


def _fill_review(path: Path, *, acknowledge: bool) -> None:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    payload["approved_by"] = "scientist@example.org"
    payload["acknowledge_evidence_limitations"] = acknowledge
    for selection in payload["selections"]:
        selection["biological_rationale"] = "Chosen for the declared design intent."
        selection["structural_rationale"] = "Compact exposed structural region."
    path.write_text(
        yaml.safe_dump(payload, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )


def test_structural_only_review_requires_acknowledgement_then_publishes(
    tmp_path: Path,
) -> None:
    root = _prepared_run(tmp_path)
    review = tmp_path / "hotspots-review.yaml"
    export_hotspot_review(
        root,
        method=RegionMethod.SASA_SURFACE_DIVERSITY,
        output=review,
    )
    _fill_review(review, acknowledge=False)

    with pytest.raises(ManifestStateError, match="acknowledge"):
        approve_hotspots(root, input_path=review)

    _fill_review(review, acknowledge=True)
    hotspots_path = approve_hotspots(
        root,
        input_path=review,
        approved_at=datetime(2026, 7, 25, 10, 1, tzinfo=UTC),
    )
    hotspots = HotspotsFile.model_validate(
        yaml.safe_load(hotspots_path.read_text(encoding="utf-8"))
    )

    assert hotspots.selection_basis is EvidenceLevel.STRUCTURAL_ONLY
    assert hotspots.ready_for_stage03 is True
    assert [item.id for item in hotspots.hotspot_sets] == ["A", "B", "C"]
    assert hotspots.hotspot_sets[0].auth_residues == (
        "X:21", "X:22", "X:23", "X:24", "X:25"
    )
    assert hotspots.hotspot_sets[0].label_seq_ids == (1, 2, 3, 4, 5)
    assert hotspots.hotspot_sets[0].label_ranges == "1..5"
    latest = read_last_text_line(root / "manifests/LATEST")
    run = load_model(root / "manifests" / latest, RunManifest)
    assert run.status is ExecutionStatus.SUCCEEDED
    assert run.workflow_state is None
    stage02_ref = next(
        ref
        for ref in run.stage_manifest_refs
        if ref.producer_stage == str(StageId.HOTSPOT_DISCOVERY)
    )
    stage02 = load_model(stage02_ref.verify(root), StageManifest)
    assert stage02.selected_attempt_id == "attempt-0002"
    assert stage02.require_output("hotspots").verify(root) == hotspots_path
    approval_record = load_model(
        root
        / "02-hotspot-discovery/attempt-0002/artifacts/approval-record.json",
        ApprovalRecord,
    )
    assert approval_record.acknowledge_evidence_limitations is True


def test_review_rejects_region_from_another_method_or_revision(
    tmp_path: Path,
) -> None:
    root = _prepared_run(tmp_path)
    review = tmp_path / "hotspots-review.yaml"
    export_hotspot_review(
        root,
        method=RegionMethod.SASA_SURFACE_DIVERSITY,
        output=review,
    )
    payload = yaml.safe_load(review.read_text(encoding="utf-8"))
    payload["approved_by"] = "scientist"
    payload["acknowledge_evidence_limitations"] = True
    payload["selections"][0]["source_region_id"] = "scannet-candidate-0001"
    for selection in payload["selections"]:
        selection["biological_rationale"] = "biological rationale"
        selection["structural_rationale"] = "structural rationale"
    review.write_text(
        yaml.safe_dump(payload, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )

    with pytest.raises(ManifestStateError, match="完整区域"):
        approve_hotspots(root, input_path=review)
