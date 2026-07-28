from __future__ import annotations

import base64
import hashlib
import json
import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from easydesign.core import (
    ArtifactRef,
    Attempt,
    EvidenceStatus,
    ExecutionStatus,
    PathPolicyError,
    ProgressSnapshot,
    RunManifest,
    StageId,
    StageManifest,
    TaskHeartbeat,
    dump_model,
    load_model,
)
from easydesign.orchestration import (
    RunIndex,
    RunIndexEntry,
    select_project_primary_run,
    upsert_run_index_entries,
)
from easydesign.safe_writes import read_last_text_line
from easydesign.ui import (
    UiRunRegistry,
    create_demo_replay,
    create_draft_order_package,
    create_ui_app,
    get_execution_progress,
    get_project_projection,
    get_run_projection,
)
from easydesign.ui.security import ArtifactTokenSigner

NOW = datetime(2026, 7, 26, 12, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _declare_test_workspace(tmp_path: Path) -> None:
    (tmp_path / "easydesign-workspace.yaml").write_text(
        "\n".join(
            (
                'schema_version: "0.1"',
                "workspace_id: test-workspace",
                "runtime_root: runtime",
                "projects_root: projects",
                "runs_root: runs",
                "archives_root: archives",
                "",
            )
        ),
        encoding="utf-8",
    )


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
            _artifact(
                root,
                stage=StageId.BOLTZGEN_CONFIGURATION,
                artifact_id="strategy-bundle",
                value={
                    "strategies": [
                        {
                            "strategy_id": "patch-1__scaffold-x",
                            "region_id": "patch-1",
                            "source_hotspot_set_id": "patch-1",
                            "scaffold_id": "scaffold-x",
                            "candidates_per_strategy": 4,
                            "binding_label_seq_ids": [1, 2, 3],
                            "hotspot_strategy": "H_all",
                            "crop_enabled": False,
                            "crop_strategy": "C_full",
                            "neutral_residue_policy": "unmarked",
                            "design_specification_sha256": None,
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
                    "schema_version": "0.1",
                    "stage_id": "04-pilot-generation",
                    "updated_at": NOW.isoformat(),
                    "status": "succeeded",
                    "total_tasks": 1,
                    "pending_tasks": 0,
                    "waiting_tasks": 0,
                    "running_tasks": 0,
                    "planned_candidates": 4,
                    "collected_candidates": 4,
                    "succeeded_tasks": 1,
                    "failed_tasks": 0,
                    "per_device": {},
                    "elapsed_seconds": 60,
                    "throughput_candidates_per_hour": 240,
                    "estimated_remaining_seconds": 0,
                    "recent_errors": [],
                },
            ),
            _artifact(
                root,
                stage=StageId.PILOT_GENERATION,
                artifact_id="pilot-task-table",
                value={
                    "schema_version": "0.1",
                    "generated_at": NOW.isoformat(),
                    "tasks": [
                        {
                            "task_id": "pilot-patch-1-scaffold-x",
                            "strategy_id": "patch-1-scaffold-x",
                            "status": "succeeded",
                            "requested_candidates": 4,
                            "collected_candidates": 4,
                            "candidate_ids": [
                                "candidate-1",
                                "candidate-2",
                                "candidate-3",
                                "candidate-4",
                            ],
                            "attempts": [
                                {
                                    "attempt_number": 1,
                                    "status": "succeeded",
                                    "requested_candidates": 4,
                                    "collected_candidates": 4,
                                    "device": 0,
                                    "command_sha256": "a" * 64,
                                    "output_relative_path": "backend-output",
                                    "started_at": NOW.isoformat(),
                                    "ended_at": NOW.isoformat(),
                                    "return_code": 0,
                                    "error": None,
                                }
                            ],
                            "current_device": None,
                        }
                    ],
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
                    "candidate_records": [
                        {
                            "candidate_id": "candidate-pilot-1",
                            "strategy_id": "patch-1__scaffold-x",
                            "sequence": "AAAA",
                            "eligible_unique_pass": True,
                            "score_screen": 0.8,
                            "hard_gate_decisions": [],
                            "metrics": [
                                {"metric_id": "hotspot-coverage", "value": 0.5},
                                {"metric_id": "design-to-target-iptm", "value": 0.6},
                            ],
                        }
                    ],
                    "strategy_summaries": [
                        {
                            "strategy_id": "patch-1__scaffold-x",
                            "candidate_count": 1,
                            "unique_sequence_count": 1,
                            "boltzgen_hard_pass_count": 1,
                            "final_gate_pass_count": 1,
                            "final_gate_pass_rate": 1.0,
                            "tier": "tier-b",
                            "score_screen_all_median": 0.8,
                            "score_screen_top_quartile_mean": 0.8,
                            "score_yaml": 0.8,
                            "selected_for_expansion": True,
                        }
                    ],
                    "selected_strategy_ids": ["patch-1__scaffold-x"],
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


def test_project_primary_run_is_explicit_and_does_not_follow_newest_branch(
    tmp_path: Path,
) -> None:
    primary_root = _audited_run(tmp_path)
    newer_root = tmp_path / "runs" / "target-alpha" / "run-newer-stage02"
    shutil.copytree(primary_root, newer_root)
    latest_name = read_last_text_line(newer_root / "manifests" / "LATEST")
    newer_manifest = load_model(newer_root / "manifests" / latest_name, RunManifest)
    newer_manifest_name = "run-manifest-0002.json"
    dump_model(
        newer_manifest.model_copy(
            update={
                "run_id": "run-newer-stage02",
                "updated_at": NOW + timedelta(hours=1),
                "completed_at": NOW + timedelta(hours=1),
            }
        ),
        newer_root / "manifests" / newer_manifest_name,
    )
    (newer_root / "manifests" / "LATEST").write_text(
        f"{newer_manifest_name}\n",
        encoding="utf-8",
    )
    _write_json(
        tmp_path / "runs",
        "run-index.json",
        {
            "schema_version": "0.1",
            "generated_at": NOW.isoformat(),
            "entries": [
                {
                    "category": "project-run",
                    "path": "target-alpha/run-scientific-stop",
                    "layout_version": "0.2",
                    "status": "succeeded",
                    "project_id": "target-alpha",
                    "run_id": "run-scientific-stop",
                    "notes": [],
                },
                {
                    "category": "project-run",
                    "path": "target-alpha/run-newer-stage02",
                    "layout_version": "0.2",
                    "status": "succeeded",
                    "project_id": "target-alpha",
                    "run_id": "run-newer-stage02",
                    "notes": [],
                },
                {
                    "category": "project-run",
                    "path": "other-target/run-primary",
                    "layout_version": "0.2",
                    "status": "succeeded",
                    "project_id": "other-target",
                    "run_id": "run-primary",
                    "is_project_primary": True,
                    "notes": [],
                },
            ],
        },
    )
    registry = UiRunRegistry(tmp_path / "runs")
    signer = ArtifactTokenSigner(b"test-secret")

    before = get_project_projection(
        "target-alpha",
        registry=registry,
        signer=signer,
    )
    assert before.latest_run is not None
    assert before.latest_run.run_id == "run-newer-stage02"

    outcome = select_project_primary_run(
        tmp_path / "runs",
        project_id="target-alpha",
        run_id="run-scientific-stop",
        changed_at=NOW + timedelta(hours=2),
    )
    after = get_project_projection(
        "target-alpha",
        registry=registry,
        signer=signer,
    )
    index = load_model(tmp_path / "runs" / "run-index.json", RunIndex)

    assert outcome.run_id == "run-scientific-stop"
    assert after.latest_run is not None
    assert after.latest_run.run_id == "run-scientific-stop"
    assert after.runs[0].run_id == "run-newer-stage02"
    assert {
        (entry.project_id, entry.run_id)
        for entry in index.entries
        if entry.is_project_primary
    } == {
        ("target-alpha", "run-scientific-stop"),
        ("other-target", "run-primary"),
    }

    upsert_run_index_entries(
        tmp_path / "runs",
        (
            RunIndexEntry(
                category="project-run",
                path="target-alpha/run-scientific-stop",
                layout_version="0.2",
                status="succeeded",
                project_id="target-alpha",
                run_id="run-scientific-stop",
                notes=("Updated without changing the project display selection.",),
            ),
        ),
        generated_at=NOW + timedelta(hours=3),
    )
    preserved = load_model(tmp_path / "runs" / "run-index.json", RunIndex)
    selected_entry = next(
        entry
        for entry in preserved.entries
        if entry.project_id == "target-alpha"
        and entry.run_id == "run-scientific-stop"
    )
    assert selected_entry.is_project_primary is True


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


def test_live_execution_projection_uses_structured_runtime_state(
    tmp_path: Path,
) -> None:
    run_root = _audited_run(tmp_path)
    historical = RunManifest.model_validate_json(
        (run_root / "manifests" / "run-manifest-0001.json").read_text(
            encoding="utf-8"
        )
    )
    active = historical.model_copy(
        update={
            "status": ExecutionStatus.RUNNING,
            "completed_at": None,
            "stage_manifest_refs": historical.stage_manifest_refs[:3],
        }
    )
    manifest_path = run_root / "manifests" / "run-manifest-0001.json"
    manifest_path.rename(manifest_path.with_name(f"{manifest_path.name}.missing"))
    dump_model(active, manifest_path)
    runtime = run_root / "04-pilot-generation" / "attempt-0001" / "runtime"
    _write_json(
        run_root,
        str(runtime.relative_to(run_root) / "task-state.json"),
        {
            "schema_version": "0.1",
            "generated_at": NOW.isoformat(),
            "tasks": [
                {
                    "task_id": "pilot-live",
                    "strategy_id": "patch-1__scaffold-x",
                    "status": "running",
                    "requested_candidates": 4,
                    "collected_candidates": 2,
                    "candidate_ids": ["candidate-1", "candidate-2"],
                    "attempts": [
                        {
                            "attempt_number": 1,
                            "status": "running",
                            "requested_candidates": 4,
                            "collected_candidates": 2,
                            "device": 1,
                            "command_sha256": "b" * 64,
                            "output_relative_path": "backend-output",
                            "started_at": NOW.isoformat(),
                            "ended_at": None,
                            "return_code": None,
                            "error": None,
                        }
                    ],
                    "current_device": 1,
                }
            ],
        },
    )
    snapshot = ProgressSnapshot(
        stage_id="04-pilot-generation",
        updated_at=NOW,
        status="running",
        total_tasks=1,
        pending_tasks=0,
        waiting_tasks=0,
        running_tasks=1,
        planned_candidates=4,
        collected_candidates=2,
        succeeded_tasks=0,
        failed_tasks=0,
        per_device={"1": "patch-1__scaffold-x"},
        elapsed_seconds=30,
        throughput_candidates_per_hour=240,
        estimated_remaining_seconds=30,
        task_heartbeats=(
            TaskHeartbeat(
                task_id="pilot-live",
                strategy_id="patch-1__scaffold-x",
                device=1,
                attempt_number=1,
                phase="boltzgen-running",
                updated_at=NOW,
                elapsed_seconds=29,
                message="BoltzGen process is still running.",
            ),
        ),
    )

    projection = get_execution_progress(
        run_root,
        4,
        runtime_snapshot=snapshot,
    )

    assert projection.status == "running"
    assert projection.collected_candidates == 2
    assert projection.device_history_status == "available"
    assert projection.devices[0].device == 1
    assert projection.devices[0].current_task_id == "pilot-live"
    assert projection.devices[0].assigned_task_count == 1
    assert projection.devices[0].attempt_count == 1
    assert projection.devices[0].heartbeat_elapsed_seconds == 29
    assert projection.devices[0].tasks[0].latest_heartbeat_at == NOW


def test_gateway_only_serves_verified_registered_artifacts(tmp_path: Path) -> None:
    run_root = _audited_run(tmp_path)
    app = create_ui_app(
        runs_root=tmp_path / "runs",
        projects_root=tmp_path / "projects",
        job_root=tmp_path / "runtime" / "state" / "ui" / "jobs",
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
        assert "connect-src 'self' data: blob:" in health.headers[
            "content-security-policy"
        ]
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
        strategies = client.get(
            f"/api/v1/runs/{projection.run_key}/stages/5/strategies"
        )
        assert strategies.status_code == 200
        assert strategies.json()[0]["region_id"] == "patch-1"
        assert strategies.json()[0]["scaffold_id"] == "scaffold-x"
        aggregate = next(
            item
            for item in strategies.json()[0]["metric_aggregates"]
            if item["metric_id"] == "hotspot-coverage"
        )
        assert aggregate["observed_count"] == 1
        assert aggregate["missing_count"] == 0
        assert aggregate["mean"] == 0.5
        execution = client.get(
            f"/api/v1/runs/{projection.run_key}/stages/4/execution"
        )
        assert execution.status_code == 200
        device = execution.json()["devices"][0]
        assert device["device"] == 0
        assert device["assigned_task_count"] == 1
        assert device["succeeded_task_count"] == 1
        assert device["attempt_count"] == 1
        assert device["failed_attempt_count"] == 0
        assert device["collected_candidates"] == 4
        assert device["busy_seconds"] == 0
        assert device["tasks"][0]["retry_count"] == 0
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


def test_gateway_registers_verified_runs_before_first_project_request(
    tmp_path: Path,
) -> None:
    run_root = _audited_run(tmp_path)
    _write_json(
        tmp_path / "runs",
        "run-index.json",
        {
            "schema_version": "0.1",
            "generated_at": NOW.isoformat(),
            "entries": [
                {
                    "category": "project-run",
                    "path": "target-alpha/run-scientific-stop",
                    "layout_version": "0.2",
                    "status": "succeeded",
                    "project_id": "target-alpha",
                    "run_id": "run-scientific-stop",
                    "notes": [],
                }
            ],
        },
    )
    registry = UiRunRegistry(tmp_path / "runs")
    run_key = registry.register(run_root)
    app = create_ui_app(
        runs_root=tmp_path / "runs",
        projects_root=tmp_path / "projects",
        job_root=tmp_path / "runtime" / "state" / "ui" / "jobs",
    )

    with TestClient(app) as client:
        response = client.get(f"/api/v1/runs/{run_key}")

    assert response.status_code == 200
    assert response.json()["run_key"] == run_key


def test_uploaded_target_has_identity_and_is_consumed_by_project_draft(
    tmp_path: Path,
) -> None:
    app = create_ui_app(
        runs_root=tmp_path / "runs",
        projects_root=tmp_path / "projects",
        job_root=tmp_path / "runtime" / "state" / "ui" / "jobs",
    )
    content = b">target\nACDEFGHIKLMNPQRSTVWY\n"
    with TestClient(app) as client:
        receipt_response = client.post(
            "/api/v1/uploads",
            json={
                "filename": "target.fasta",
                "content_base64": base64.b64encode(content).decode("ascii"),
            },
        )
        assert receipt_response.status_code == 200
        receipt = receipt_response.json()
        assert receipt["filename"] == "target.fasta"
        assert receipt["size_bytes"] == len(content)
        assert receipt["sha256"] == hashlib.sha256(content).hexdigest()

        project_response = client.post(
            "/api/v1/projects",
            json={
                "project_id": "target-demo",
                "source_type": "local-file",
                "source_value": receipt["upload_token"],
                "execution_mode": "review-gated",
                "design_intent": "detection",
                "stop_after_stage": 1,
            },
        )
        assert project_response.status_code == 200
        config = project_response.json()["config"]
        assert "intent: detection" in config
        assert "path: inputs/target.fasta" in config
        assert (
            tmp_path / "projects" / "target-demo" / "inputs" / "target.fasta"
        ).read_bytes() == content

        reused = client.post(
            "/api/v1/projects",
            json={
                "project_id": "target-demo-reused",
                "source_type": "local-file",
                "source_value": receipt["upload_token"],
                "stop_after_stage": 1,
            },
        )
        assert reused.status_code == 400
        assert "已失效" in reused.json()["detail"]

        empty = client.post(
            "/api/v1/uploads",
            json={"filename": "empty.pse", "content_base64": ""},
        )
        assert empty.status_code == 400
        assert "空文件" in empty.json()["detail"]


def test_raw_upload_stream_has_terminal_receipt_and_preserves_bytes(
    tmp_path: Path,
) -> None:
    app = create_ui_app(
        runs_root=tmp_path / "runs",
        projects_root=tmp_path / "projects",
        job_root=tmp_path / "runtime" / "state" / "ui" / "jobs",
    )
    content = b"fixture-pse-binary\\x00\\x01\\x02"

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/uploads/raw",
            params={"filename": "target.pse"},
            content=content,
            headers={"Content-Type": "application/octet-stream"},
        )
        assert response.status_code == 200
        receipt = response.json()
        assert receipt["filename"] == "target.pse"
        assert receipt["size_bytes"] == len(content)
        assert receipt["sha256"] == hashlib.sha256(content).hexdigest()

        project = client.post(
            "/api/v1/projects",
            json={
                "project_id": "raw-pse-demo",
                "source_type": "local-file",
                "source_value": receipt["upload_token"],
                "execution_mode": "review-gated",
                "design_intent": "exploratory",
                "stop_after_stage": 1,
                "design_mode": "stepwise",
            },
        )
        assert project.status_code == 200
        assert (
            tmp_path / "projects" / "raw-pse-demo" / "inputs" / "target.pse"
        ).read_bytes() == content

        empty = client.post(
            "/api/v1/uploads/raw",
            params={"filename": "empty.pse"},
            content=b"",
            headers={"Content-Type": "application/octet-stream"},
        )
        assert empty.status_code == 400
        assert "空文件" in empty.json()["detail"]


def test_gateway_lists_only_profile_declared_remote_executor_ids(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "easydesign.ui.app.list_remote_executor_ids",
        lambda **_: ("suzhou2-a100x8",),
    )
    app = create_ui_app(
        runs_root=tmp_path / "runs",
        projects_root=tmp_path / "projects",
        job_root=tmp_path / "runtime" / "state" / "ui" / "jobs",
    )

    with TestClient(app) as client:
        response = client.get("/api/v1/remote-executors")

    assert response.status_code == 200
    assert response.json() == {
        "executors": [
            {
                "executor_id": "suzhou2-a100x8",
                "label": "suzhou2-a100x8",
            }
        ]
    }
