from __future__ import annotations

import importlib.util
import json
import shutil
from datetime import UTC, datetime
from pathlib import Path

import pytest

from easydesign.core import (
    ArtifactRef,
    Attempt,
    EvidenceStatus,
    ExecutionStatus,
    RunManifest,
    StageId,
    StageManifest,
    dump_model,
)
from easydesign.stages.s03_boltzgen_configuration import (
    ScaffoldAsset,
    StrategyBundle,
    StrategyRecord,
)
from easydesign.stages.s04_pilot_generation import CandidateIndex, CandidateRecord
from easydesign.stages.s05_pilot_filtering import (
    CandidateFilterRecord,
    FilterDecision,
    FilterMetric,
    PilotFilterReportV1_6,
    StrategyFilterSummary,
    StrategyTier,
)

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / ".agents/skills/easydesign-result-review/scripts/build_result_review.py"
SPEC = importlib.util.spec_from_file_location("easydesign_result_review", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)

NOW = datetime(2026, 8, 13, 8, 0, tzinfo=UTC)
SHA = "a" * 64


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _artifact(
    run_root: Path,
    path: Path,
    artifact_id: str,
    role: str,
    file_format: str,
    stage: StageId,
) -> ArtifactRef:
    return ArtifactRef.from_file(
        run_root=run_root,
        relative_path=path.relative_to(run_root).as_posix(),
        artifact_id=artifact_id,
        role=role,
        file_format=file_format,
        producer_stage=str(stage),
        producer_attempt="attempt-0001",
    )


def _candidate(
    run_root: Path,
    *,
    candidate_id: str,
    ordinal: int,
    strategy_id: str,
) -> CandidateRecord:
    original = run_root / "04-pilot-generation/attempt-0001/artifacts" / f"{candidate_id}-o.cif"
    refolded = run_root / "04-pilot-generation/attempt-0001/artifacts" / f"{candidate_id}-r.cif"
    structure = (
        ROOT
        / "examples/apoe-ui-demo/evidence-runs/apoe-s02-006-pse"
        / "20260726-004-stage05-pilot-filter/03-boltzgen-configuration"
        / "attempt-0001/artifacts/assets/scaffolds/7eow.cif"
    )
    original.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(structure, original)
    shutil.copy2(structure, refolded)
    return CandidateRecord(
        candidate_id=candidate_id,
        backend_candidate_id=candidate_id,
        strategy_id=strategy_id,
        task_id=f"task-{strategy_id}",
        task_attempt_number=1,
        ordinal_within_strategy=ordinal,
        original_structure=_artifact(
            run_root,
            original,
            f"{candidate_id}-original",
            "boltzgen-original-complex",
            "mmcif",
            StageId.PILOT_GENERATION,
        ),
        refolded_structure=_artifact(
            run_root,
            refolded,
            f"{candidate_id}-refolded",
            "boltzgen-refolded-complex",
            "mmcif",
            StageId.PILOT_GENERATION,
        ),
        metrics={"pass_filters": True},
        pass_filters=True,
    )


def _filtered(
    *, candidate_id: str, strategy_id: str, passed: bool, score: float, missing: bool = False
) -> CandidateFilterRecord:
    return CandidateFilterRecord(
        candidate_id=candidate_id,
        strategy_id=strategy_id,
        sequence="ACDEFGHIKLMNPQRSTVWY" + ("A" if candidate_id.endswith("1") else "C"),
        sequence_sha256=("b" if candidate_id.endswith("1") else "c") * 64,
        metrics=(
            FilterMetric(
                metric_id="hotspot-coverage",
                value=None if missing else (0.7 if passed else 0.2),
                source="easydesign-structure",
                definition_version="interface-geometry-v1",
                available=not missing,
                missing_reason="fixture-missing" if missing else None,
            ),
        ),
        hard_gate_decisions=(
            FilterDecision(
                rule_id="require-hotspot-coverage",
                metric_id="hotspot-coverage",
                operator="ge",
                threshold=0.4,
                observed=0.7 if passed else 0.2,
                passed=passed,
                reason="fixture",
            ),
        ),
        hard_gate_pass=passed,
        duplicate_of=None,
        eligible_unique_pass=passed,
        score_screen=score,
        normalization_group=strategy_id,
    )


def _stage(
    run_root: Path,
    stage_id: StageId,
    artifacts: tuple[ArtifactRef, ...],
) -> ArtifactRef:
    attempt = Attempt(
        attempt_id="attempt-0001",
        status=ExecutionStatus.SUCCEEDED,
        created_at=NOW,
        started_at=NOW,
        ended_at=NOW,
        backend_name="fixture",
        backend_version="1",
        executor_name="fixture",
    )
    manifest = StageManifest(
        stage_id=stage_id,
        contract_version="0.1",
        status=ExecutionStatus.SUCCEEDED,
        created_at=NOW,
        completed_at=NOW,
        output_artifacts=artifacts,
        attempts=(attempt,),
        selected_attempt_id=attempt.attempt_id,
    )
    path = run_root / "manifests" / f"{stage_id}.json"
    dump_model(manifest, path)
    return ArtifactRef.from_file(
        run_root=run_root,
        relative_path=path.relative_to(run_root).as_posix(),
        artifact_id=f"stage-{str(stage_id)[:2]}-manifest",
        role="stage-manifest",
        file_format="json",
        producer_stage=str(stage_id),
        producer_attempt="attempt-0001",
    )


def _fixture(tmp_path: Path) -> tuple[Path, Path]:
    repo = tmp_path / "repo"
    run_root = repo / "workspace/runs/project-a/run-001"
    run_root.mkdir(parents=True)
    _write(
        repo / "easydesign-workspace.yaml",
        "schema_version: '0.1'\n"
        "workspace_id: fixture\n"
        "runtime_root: runtime\n"
        "projects_root: workspace/projects\n"
        "runs_root: workspace/runs\n"
        "archives_root: workspace/archives\n",
    )
    (repo / "runtime/tmp").mkdir(parents=True)
    viewer_assets = ROOT / "src/easydesign/reporting/static/target_viewer/vendor/molstar"
    fixture_assets = repo / "src/easydesign/reporting/static/target_viewer/vendor/molstar"
    fixture_assets.mkdir(parents=True)
    for name in ("molstar.js", "molstar.css", "LICENSE"):
        shutil.copy2(viewer_assets / name, fixture_assets / name)
    config_path = run_root / "config-snapshot/resolved-config.json"
    _write(config_path, "{}\n")
    config = ArtifactRef.from_file(
        run_root=run_root,
        relative_path="config-snapshot/resolved-config.json",
        artifact_id="resolved-config",
        role="resolved-config",
        file_format="json",
    )
    strategy_id = "baseline-7eow"
    scaffold = ScaffoldAsset(
        scaffold_id="7eow",
        specification_path="assets/7eow.yaml",
        specification_sha256="d" * 64,
        structure_path="assets/7eow.cif",
        structure_sha256="e" * 64,
        source_repository="https://example.test/boltzgen",
        source_commit="f" * 40,
    )
    strategy = StrategyRecord(
        strategy_id=strategy_id,
        region_id="primary",
        source_hotspot_set_id="hs-primary",
        scaffold_id="7eow",
        binding_label_seq_ids=(10, 12),
        candidates_per_strategy=3,
        design_specification_path="design.yaml",
        design_specification_sha256="1" * 64,
        hypothesis_id="h-baseline",
        role="baseline",
        evidence_refs=("run:foundation",),
        changed_factors=("scaffold_id",),
        held_constant=("target_context",),
        rationale="fixture baseline",
        expected_result="fixture expected",
        failure_interpretation="fixture failure",
    )
    bundle = StrategyBundle(
        generated_at=NOW,
        project_id="project-a",
        run_id="run-001",
        target_id="target-a",
        target_structure_sha256=SHA,
        target_bundle_sha256=SHA,
        hotspots_sha256=SHA,
        source_stage02_manifest_sha256=SHA,
        validation_report_sha256=SHA,
        scaffold_assets=(scaffold,),
        strategies=(strategy,),
    )
    strategy_path = (
        run_root / "03-boltzgen-configuration/attempt-0001/artifacts/strategy-bundle.json"
    )
    dump_model(bundle, strategy_path)
    strategy_ref = _artifact(
        run_root,
        strategy_path,
        "strategy-bundle",
        "strategy-bundle",
        "json",
        StageId.BOLTZGEN_CONFIGURATION,
    )
    stage03 = _stage(run_root, StageId.BOLTZGEN_CONFIGURATION, (strategy_ref,))

    candidates = tuple(
        _candidate(
            run_root, candidate_id=f"candidate-{index}", ordinal=index, strategy_id=strategy_id
        )
        for index in (1, 2, 3)
    )
    index = CandidateIndex(
        generated_at=NOW,
        strategy_bundle_sha256=strategy_ref.sha256,
        required_per_strategy=3,
        candidates=candidates,
    )
    index_path = run_root / "04-pilot-generation/attempt-0001/artifacts/candidate-index.json"
    dump_model(index, index_path)
    index_ref = _artifact(
        run_root, index_path, "candidate-index", "candidate-index", "json", StageId.PILOT_GENERATION
    )
    stage04 = _stage(run_root, StageId.PILOT_GENERATION, (index_ref,))

    records = (
        _filtered(candidate_id="candidate-1", strategy_id=strategy_id, passed=True, score=0.9),
        _filtered(
            candidate_id="candidate-2",
            strategy_id=strategy_id,
            passed=True,
            score=0.6,
            missing=True,
        ),
        _filtered(candidate_id="candidate-3", strategy_id=strategy_id, passed=False, score=0.3),
    )
    report = PilotFilterReportV1_6(
        generated_at=NOW,
        profile_sha256="2" * 64,
        candidate_index_sha256=index_ref.sha256,
        candidate_records=records,
        strategy_summaries=(
            StrategyFilterSummary(
                strategy_id=strategy_id,
                candidate_count=3,
                unique_sequence_count=3,
                boltzgen_hard_pass_count=2,
                final_gate_pass_count=2,
                final_gate_pass_rate=2 / 3,
                score_screen_top_quartile_mean=0.9,
                score_screen_all_median=0.6,
                score_yaml=0.75,
                tier=StrategyTier.A,
                selected_for_expansion=True,
            ),
        ),
        promoted_strategy_ids=(strategy_id,),
        status="strategies-promoted",
    )
    report_path = run_root / "05-pilot-filtering/attempt-0001/artifacts/pilot-filter-report.json"
    dump_model(report, report_path)
    report_ref = _artifact(
        run_root,
        report_path,
        "pilot-filter-report",
        "pilot-filter-report",
        "json",
        StageId.PILOT_FILTERING,
    )
    stage05 = _stage(run_root, StageId.PILOT_FILTERING, (report_ref,))
    run = RunManifest(
        revision=1,
        project_id="project-a",
        run_id="run-001",
        easydesign_version="0.1.0.dev1",
        code_commit="a" * 40,
        status=ExecutionStatus.SUCCEEDED,
        evidence_status=EvidenceStatus.IMPLEMENTED,
        created_at=NOW,
        updated_at=NOW,
        completed_at=NOW,
        config_snapshot=config,
        stage_manifest_refs=(stage03, stage04, stage05),
    )
    manifest_path = run_root / "manifests/run-manifest.v0001.json"
    dump_model(run, manifest_path)
    _write(run_root / "manifests/LATEST", "run-manifest.v0001.json\n")
    return run_root, repo / "runtime/tmp/review-001"


def test_builds_complete_read_only_pilot_review(tmp_path: Path) -> None:
    run_root, output = _fixture(tmp_path)
    html_path = MODULE.build_pilot_review(run_root, output)
    data = json.loads((output / "review-data.json").read_text(encoding="utf-8"))
    manifest = json.loads((output / "review-manifest.json").read_text(encoding="utf-8"))

    assert html_path == output / "index.html"
    assert data["denominator"] == {
        "planned": 3,
        "generated": 3,
        "evaluable": 3,
        "hard_gate_pass": 2,
        "eligible_unique_pass": 2,
        "missing_metric_cells": 1,
    }
    assert len(data["candidates"]) == 3
    assert {role for item in data["structures"] for role in item["roles"]} == {
        "best-pass",
        "typical-pass",
        "representative-failure",
    }
    assert manifest["read_only"] is True
    assert manifest["scientific_artifact"] is False
    assert all(
        not Path(item["path"]).is_absolute() for item in manifest["source_artifacts"].values()
    )
    assert {
        "assets/molstar.js",
        "assets/molstar.css",
        "assets/LICENSE",
    }.issubset({item["relative_path"] for item in manifest["files"]})
    assert "https://" not in html_path.read_text(encoding="utf-8")
    rendered = html_path.read_text(encoding="utf-8").lower()
    assert "molstar.viewer.create" in rendered
    assert "下一开发迭代" not in rendered
    assert str(tmp_path) not in rendered
    assert "--confirm" not in rendered
    assert 'type="submit"' not in rendered


def test_rejects_tampered_manifest_declared_artifact(tmp_path: Path) -> None:
    run_root, output = _fixture(tmp_path)
    report = run_root / "05-pilot-filtering/attempt-0001/artifacts/pilot-filter-report.json"
    report.write_text("{}\n", encoding="utf-8")

    with pytest.raises(Exception, match="大小不一致|SHA-256 不一致"):
        MODULE.build_pilot_review(run_root, output)
    assert not output.exists()


def test_rejects_output_outside_workspace(tmp_path: Path) -> None:
    run_root, _output = _fixture(tmp_path)
    with pytest.raises(Exception, match="工作区外"):
        MODULE.build_pilot_review(run_root, tmp_path / "external-review")


def test_rejects_even_empty_existing_output(tmp_path: Path) -> None:
    run_root, output = _fixture(tmp_path)
    output.mkdir(parents=True)

    with pytest.raises(Exception, match="必须不存在"):
        MODULE.build_pilot_review(run_root, output)


def test_scale_mode_fails_closed() -> None:
    with pytest.raises(SystemExit):
        MODULE.main(
            [
                "--run-root",
                "/tmp/not-used",
                "--output-root",
                "/tmp/not-used-output",
                "--mode",
                "scale-selection-review",
            ]
        )
