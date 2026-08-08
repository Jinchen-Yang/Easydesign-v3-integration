from __future__ import annotations

import json
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
from easydesign.reporting import build_evidence_bundle, verify_evidence_bundle

NOW = datetime(2026, 7, 27, 8, 0, tzinfo=UTC)


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def _fixture_run(tmp_path: Path) -> Path:
    run_root = tmp_path / "source" / "target-alpha" / "run-001"
    run_root.mkdir(parents=True)
    config_path = run_root / "config-snapshot" / "resolved-config.json"
    _write_json(config_path, {"schema_version": "0.7"})
    config = ArtifactRef.from_file(
        run_root=run_root,
        relative_path="config-snapshot/resolved-config.json",
        artifact_id="resolved-config",
        role="resolved-config",
        file_format="json",
    )
    artifact_path = (
        run_root
        / str(StageId.TARGET_PREPARATION)
        / "attempt-0001"
        / "artifacts"
        / "target-bundle.json"
    )
    _write_json(artifact_path, {"target_id": "target-alpha"})
    artifact = ArtifactRef.from_file(
        run_root=run_root,
        relative_path=artifact_path.relative_to(run_root).as_posix(),
        artifact_id="target-bundle",
        role="target-bundle",
        file_format="json",
        producer_stage=str(StageId.TARGET_PREPARATION),
        producer_attempt="attempt-0001",
    )
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
    stage = StageManifest(
        stage_id=StageId.TARGET_PREPARATION,
        contract_version="0.1",
        status=ExecutionStatus.SUCCEEDED,
        created_at=NOW,
        completed_at=NOW,
        output_artifacts=(artifact,),
        attempts=(attempt,),
        selected_attempt_id=attempt.attempt_id,
    )
    stage_path = run_root / "manifests" / f"{StageId.TARGET_PREPARATION}.json"
    dump_model(stage, stage_path)
    stage_ref = ArtifactRef.from_file(
        run_root=run_root,
        relative_path=stage_path.relative_to(run_root).as_posix(),
        artifact_id="stage01-manifest",
        role="stage-manifest",
        file_format="json",
        producer_stage=str(StageId.TARGET_PREPARATION),
        producer_attempt="attempt-0001",
    )
    manifest = RunManifest(
        schema_version="1.0",
        revision=1,
        project_id="target-alpha",
        run_id="run-001",
        easydesign_version="0.1.0.dev10",
        code_commit="a" * 40,
        status=ExecutionStatus.SUCCEEDED,
        evidence_status=EvidenceStatus.IMPLEMENTED,
        created_at=NOW,
        updated_at=NOW,
        completed_at=NOW,
        config_snapshot=config,
        stage_manifest_refs=(stage_ref,),
    )
    latest = run_root / "manifests" / "run-manifest-0001.json"
    dump_model(manifest, latest)
    (run_root / "manifests" / "LATEST").write_text(
        "run-manifest-0001.json\n",
        encoding="utf-8",
    )
    heavy = (
        run_root
        / str(StageId.TARGET_PREPARATION)
        / "attempt-0001"
        / "tasks"
        / "backend"
        / "large.bin"
    )
    heavy.parent.mkdir(parents=True)
    heavy.write_bytes(b"x" * 1024)
    return run_root


def test_builds_manifest_complete_bundle_without_backend_intermediates(
    tmp_path: Path,
) -> None:
    source = _fixture_run(tmp_path)
    output = tmp_path / "bundle"

    outcome = build_evidence_bundle(source, output, generated_at=NOW)
    verified = verify_evidence_bundle(output)

    assert outcome.run_root == (
        output / "evidence-runs" / "target-alpha" / "run-001"
    )
    assert verified.run_root == outcome.run_root
    assert (output / "evidence-runs" / "run-index.json").is_file()
    assert (
        outcome.run_root
        / str(StageId.TARGET_PREPARATION)
        / "attempt-0001"
        / "artifacts"
        / "target-bundle.json"
    ).is_file()
    assert not (
        outcome.run_root
        / str(StageId.TARGET_PREPARATION)
        / "attempt-0001"
        / "tasks"
    ).exists()


def test_verify_rejects_tampered_bundle_file(tmp_path: Path) -> None:
    source = _fixture_run(tmp_path)
    output = tmp_path / "bundle"
    outcome = build_evidence_bundle(source, output, generated_at=NOW)
    target = outcome.run_root / "config-snapshot" / "resolved-config.json"
    target.write_text("tampered", encoding="utf-8")

    with pytest.raises(ValueError, match="文件大小不一致|SHA-256 不一致"):
        verify_evidence_bundle(output)
