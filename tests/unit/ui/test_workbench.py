from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from easydesign.core import (
    ArtifactRef,
    Attempt,
    EvidenceStatus,
    ExecutionStatus,
    PathPolicyError,
    RunManifest,
    StageId,
    StageManifest,
    dump_model,
)
from easydesign.ui import (
    UiRunRegistry,
    create_demo_replay,
    create_draft_order_package,
    create_ui_app,
    get_run_projection,
)
from easydesign.ui.security import ArtifactTokenSigner

NOW = datetime(2026, 7, 26, 12, 0, tzinfo=UTC)


def _write_json(root: Path, relative: str, value: object) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def _artifact(
    root: Path,
    *,
    stage: StageId,
    artifact_id: str,
    value: object,
) -> ArtifactRef:
    relative = (
        f"{stage}/attempt-0001/artifacts/{artifact_id}.json"
    )
    _write_json(root, relative, value)
    return ArtifactRef.from_file(
        run_root=root,
        relative_path=relative,
        artifact_id=artifact_id,
        role=artifact_id,
        file_format="json",
        producer_stage=str(stage),
        producer_attempt="attempt-0001",
    )


def _stage(
    root: Path,
    *,
    stage: StageId,
    outputs: tuple[ArtifactRef, ...],
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
        stage_id=stage,
        contract_version="0.1",
        status=ExecutionStatus.SUCCEEDED,
        created_at=NOW,
        completed_at=NOW,
        output_artifacts=outputs,
        attempts=(attempt,),
        selected_attempt_id=attempt.attempt_id,
    )
    relative = f"manifests/{stage}.json"
    dump_model(manifest, root / relative)
    return ArtifactRef.from_file(
        run_root=root,
        relative_path=relative,
        artifact_id=f"{stage}-manifest",
        role="stage-manifest",
        file_format="json",
        producer_stage=str(stage),
        producer_attempt="attempt-0001",
    )


def _audited_run(tmp_path: Path) -> Path:
    root = tmp_path / "runs" / "target-alpha" / "run-scientific-stop"
    root.mkdir(parents=True)
    _write_json(root, "config-snapshot/resolved-config.json", {"schema_version": "0.7"})
    config = ArtifactRef.from_file(
        run_root=root,
        relative_path="config-snapshot/resolved-config.json",
        artifact_id="resolved-config",
        role="resolved-config",
        file_format="json",
    )
    stage01 = _stage(
        root,
        stage=StageId.TARGET_PREPARATION,
        outputs=(
            _artifact(
                root,
                stage=StageId.TARGET_PREPARATION,
                artifact_id="target-bundle",
                value={
                    "target_id": "target-alpha",
                    "origin": "imported",
                    "sequence_length": 76,
                    "coordinate_ensemble": {"model_count": 1},
                },
            ),
        ),
    )
    stage02 = _stage(
        root,
        stage=StageId.HOTSPOT_DISCOVERY,
        outputs=(
            _artifact(
                root,
                stage=StageId.HOTSPOT_DISCOVERY,
                artifact_id="hotspots",
                value={
                    "selection_basis": "structural_only",
                    "ready_for_stage03": True,
                    "region_source": {"type": "manual-residue-list"},
                    "hotspot_sets": [
                        {"id": "patch-1", "label_seq_ids": [1, 2, 3], "label_ranges": "1..3"}
                    ],
                },
            ),
        ),
    )
    stage03 = _stage(
        root,
        stage=StageId.BOLTZGEN_CONFIGURATION,
        outputs=(
            _artifact(
                root,
                stage=StageId.BOLTZGEN_CONFIGURATION,
                artifact_id="design-matrix",
                value={
                    "strategies": [
                        {
                            "strategy_id": "patch-1__scaffold-x",
                            "region_id": "patch-1",
                            "scaffold_id": "scaffold-x",
                            "candidates_per_strategy": 4,
                            "neutral_residue_policy": "unconstrained",
                        }
                    ]
                },
            ),
        ),
    )
    stage04 = _stage(
        root,
        stage=StageId.PILOT_GENERATION,
        outputs=(
            _artifact(
                root,
                stage=StageId.PILOT_GENERATION,
                artifact_id="pilot-progress-final",
                value={
                    "planned_candidates": 4,
                    "collected_candidates": 4,
                    "succeeded_tasks": 1,
                    "failed_tasks": 0,
                    "per_device": {"0": {"completed": 1}},
                },
            ),
        ),
    )
    stage05 = _stage(
        root,
        stage=StageId.PILOT_FILTERING,
        outputs=(
            _artifact(
                root,
                stage=StageId.PILOT_FILTERING,
                artifact_id="pilot-filter-report",
                value={
                    "status": "completed",
                    "candidate_records": [],
                    "strategy_summaries": [],
                    "selected_strategy_ids": [],
                },
            ),
            _artifact(
                root,
                stage=StageId.PILOT_FILTERING,
                artifact_id="expansion-validation-report",
                value={
                    "status": "stopped-no-scale-winner",
                    "candidates": [
                        {"candidate_id": "candidate-1", "local_gate_pass": True}
                    ],
                    "predictions": [
                        {
                            "candidate_id": "candidate-1",
                            "target_ca_rmsd_angstrom": 1.4,
                            "binder_pose_rmsd_angstrom": 20.0,
                            "pairwise_iptm": 0.3,
                            "minimum_interface_pae_angstrom": 18.0,
                            "passed": False,
                        }
                    ],
                },
            ),
            _artifact(
                root,
                stage=StageId.PILOT_FILTERING,
                artifact_id="stopped-no-scale-winner-scientific-stop",
                value={"code": "stopped-no-scale-winner"},
            ),
        ),
    )
    manifest = RunManifest(
        schema_version="1.0",
        revision=1,
        project_id="target-alpha",
        run_id="run-scientific-stop",
        easydesign_version="0.1.0.dev7",
        code_commit="a" * 40,
        status=ExecutionStatus.SUCCEEDED,
        evidence_status=EvidenceStatus.IMPLEMENTED,
        created_at=NOW,
        updated_at=NOW,
        completed_at=NOW,
        config_snapshot=config,
        stage_manifest_refs=(stage01, stage02, stage03, stage04, stage05),
    )
    dump_model(manifest, root / "manifests" / "run-manifest-0001.json")
    (root / "manifests" / "LATEST").write_text(
        "run-manifest-0001.json\n",
        encoding="utf-8",
    )
    return root


def test_projection_separates_scientific_stop_from_stage_capability(
    tmp_path: Path,
) -> None:
    run_root = _audited_run(tmp_path)
    registry = UiRunRegistry(tmp_path / "runs")
    projection = get_run_projection(
        run_root,
        registry=registry,
        signer=ArtifactTokenSigner(b"test-secret"),
    )

    assert projection.stages[4].state == "scientific-stop"
    assert projection.stages[4].highlights["local_gate_pass_count"] == 1
    assert projection.stages[5].state == "not-reached"
    assert projection.stages[5].capability.status == "implemented"
    assert projection.stages[6].state == "not-reached"
    assert projection.stages[6].capability.status == "implemented"


def test_replay_is_read_only_and_uses_manifest_scientific_stop(tmp_path: Path) -> None:
    run_root = _audited_run(tmp_path)
    registry = UiRunRegistry(tmp_path / "runs")
    before = (run_root / "manifests" / "run-manifest-0001.json").read_bytes()

    replay = create_demo_replay(run_root, registry=registry)
    outcome = create_draft_order_package(
        run_root,
        registry=registry,
        signer=ArtifactTokenSigner(b"test-secret"),
    )

    assert replay.banner.startswith("DEMO REPLAY")
    assert replay.frames[-3].state == "scientific-stop"
    assert not outcome.allowed
    assert "FinalCandidatePackage" in outcome.reason
    assert (run_root / "manifests" / "run-manifest-0001.json").read_bytes() == before


def test_artifact_token_is_signed_and_expires(tmp_path: Path) -> None:
    run_root = _audited_run(tmp_path)
    registry = UiRunRegistry(tmp_path / "runs")
    run_key = registry.register(run_root)
    signer = ArtifactTokenSigner(b"test-secret", lifetime_seconds=10)
    artifact = ArtifactRef.from_file(
        run_root=run_root,
        relative_path=(
            "01-target-preparation/attempt-0001/artifacts/target-bundle.json"
        ),
        artifact_id="target-bundle",
        role="target-bundle",
        file_format="json",
        producer_stage=str(StageId.TARGET_PREPARATION),
        producer_attempt="attempt-0001",
    )
    token = signer.sign(run_key, artifact, now=0)

    assert signer.verify(token, now=5).run_key == run_key
    with pytest.raises(PathPolicyError, match="过期"):
        signer.verify(token, now=11)
    payload, signature = token.split(".", maxsplit=1)
    changed = ("A" if signature[0] != "A" else "B") + signature[1:]
    with pytest.raises(PathPolicyError, match="签名无效"):
        signer.verify(f"{payload}.{changed}", now=5)


def test_gateway_only_serves_verified_registered_artifacts(tmp_path: Path) -> None:
    run_root = _audited_run(tmp_path)
    app = create_ui_app(
        runs_root=tmp_path / "runs",
        projects_root=tmp_path / "projects",
        job_root=tmp_path / "jobs",
    )
    service = app.state.easydesign
    projection = get_run_projection(
        run_root,
        registry=service.registry,
        signer=service.signer,
    )
    token = projection.stages[0].artifacts[0].token

    with TestClient(app) as client:
        health = client.get("/api/v1/health")
        assert health.status_code == 200
        assert health.headers["content-security-policy"].startswith("default-src")
        assert client.get("/api/v1/health", headers={"host": "example.com"}).status_code == 403
        response = client.get(f"/api/v1/artifacts/{token}")
        assert response.status_code == 200
        overview = client.get(
            f"/api/v1/runs/{projection.run_key}/stages/5/overview"
        )
        assert overview.status_code == 200
        assert overview.json()["counts"]["expanded"] == 1
        assert overview.json()["conclusion_title"] == "当前没有可进入规模化生成的设计策略"
        candidates = client.get(
            f"/api/v1/runs/{projection.run_key}/stages/5/candidates",
            params={"phase": "expansion", "page_size": 1},
        )
        assert candidates.status_code == 200
        assert candidates.json()["total"] == 1
        detail = client.get(
            (
                f"/api/v1/runs/{projection.run_key}/stages/5/candidates/"
                "candidate-1"
            ),
            params={"phase": "expansion"},
        )
        assert detail.status_code == 200
        assert detail.json()["candidate_id"] == "candidate-1"
        catalog = client.get(
            f"/api/v1/runs/{projection.run_key}/stages/5/metrics"
        )
        assert catalog.status_code == 200
        assert len(catalog.json()) >= 20
        invalid_sort = client.get(
            f"/api/v1/runs/{projection.run_key}/stages/5/candidates",
            params={"phase": "pilot", "sort_key": "absolute_path"},
        )
        assert invalid_sort.status_code == 400
        invalid_method = client.get(
            f"/api/v1/runs/{projection.run_key}/hotspots/review?method=winner"
        )
        assert invalid_method.status_code == 400
        unconfirmed = client.post(
            f"/api/v1/runs/{projection.run_key}/hotspots/approve",
            json={"yaml_text": "schema_version: '0.3'", "confirmed": False},
        )
        assert unconfirmed.status_code == 400

    artifact_path = (
        run_root
        / "01-target-preparation"
        / "attempt-0001"
        / "artifacts"
        / "target-bundle.json"
    )
    artifact_path.write_text("tampered", encoding="utf-8")
    with TestClient(app) as client:
        assert client.get(f"/api/v1/artifacts/{token}").status_code == 400
