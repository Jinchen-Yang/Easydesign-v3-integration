from __future__ import annotations

import base64
import hashlib
import json
import os
import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient

from easydesign.backends.executors import ManagedWorkerProbe
from easydesign.core import (
    ArtifactRef,
    Attempt,
    ConfigurationError,
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
from easydesign.core.evidence_links import (
    AdoptedDeviceExecutionSummary,
    AdoptedScaleExecutionSummary,
    PolicyReevaluationRecord,
    ProjectScaleEvidenceContinuation,
    ReevaluatedStrategy,
    RunEvidenceLink,
    ScaleEvidenceAdoptionRecord,
)
from easydesign.core.hashing import sha256_file
from easydesign.orchestration import (
    RunIndex,
    RunIndexEntry,
    select_project_primary_run,
    upsert_run_index_entries,
)
from easydesign.orchestration.ssh_pairing import (
    RemoteExecutorPairingRevision,
    SshHostIdentity,
    SshPublicKeyInstallResult,
)
from easydesign.orchestration.task_tracking import load_latest_runtime_model
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
from easydesign.ui.app import (
    ProjectCreateRequest,
    RegionRevisionRequest,
    _initial_structure_pml,
    _pairing_projection,
    _regions_from_scene_pml,
    _scientific_analysis_methods,
    _validate_assistant_region_scene,
)
from easydesign.ui.models import (
    ArtifactProjection,
    ProjectMetadata,
    RegionEditorProjection,
    RegionEditorResidue,
)
from easydesign.ui.security import ArtifactTokenSigner
from easydesign.ui.stage05 import get_filter_overview

NOW = datetime(2026, 7, 26, 12, 0, tzinfo=UTC)


def test_stage_one_and_two_structure_pml_color_regions_without_forcing_sticks() -> None:
    projection = SimpleNamespace(
        target_structure_sha256="a" * 64,
        residues=(
            SimpleNamespace(
                label_seq_id=1,
                auth_chain_id="A",
                auth_residue_id="23",
                insertion_code=None,
            ),
        ),
    )
    regions = {"A": (1,)}

    stage_one = _initial_structure_pml(projection, regions, stage_number=1)
    stage_two = _initial_structure_pml(projection, regions, stage_number=2)

    assert "color red, ed_region_A" in stage_one
    assert "color red, ed_region_A" in stage_two
    assert "show sticks, ed_region_A" not in stage_one
    assert "show sticks, ed_region_A" not in stage_two


def test_project_create_request_accepts_exact_stage06_candidate_count() -> None:
    request = ProjectCreateRequest(
        project_id="adjustable-scale",
        source_type="pdb-id",
        source_value="1UBQ",
        stop_after_stage=7,
        stage06_candidate_count=37,
    )

    assert request.stage06_candidate_count == 37


def test_interactive_region_revision_needs_only_regions_and_explicit_submit() -> None:
    request = RegionRevisionRequest(
        session_id="session-stepwise",
        regions=[{"id": "A", "label_seq_ids": [1, 2, 3]}],
        confirmed=True,
    )

    assert request.model_dump() == {
        "session_id": "session-stepwise",
        "regions": [{"id": "A", "label_seq_ids": [1, 2, 3]}],
        "run_id": None,
        "confirmed": True,
    }


def test_pairing_projection_uses_the_same_state_contract_as_execution_targets() -> None:
    record = SimpleNamespace(
        executor_id="suzhou2",
        controller_id="controller-primary",
        state="paired",
        host="suzhou2.example",
        port=22,
        user="root",
        host_identity=SimpleNamespace(fingerprint="SHA256:verified"),
        public_key_fingerprint="SHA256:controller-key",
        managed_worker_root="/data/easydesign/managed-worker",
        updated_at=NOW,
        public_key="ssh-ed25519 AAAATEST",
    )

    projection = _pairing_projection(record)

    assert projection["state"] == "paired"
    assert projection["pairing_state"] == "paired"


def test_execution_targets_projects_managed_idle_gpu_snapshot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record = SimpleNamespace(
        executor_id="suzhou2",
        controller_id="controller-primary",
        state="paired",
        host="suzhou2.example",
        port=22,
        user="root",
        host_identity=SimpleNamespace(fingerprint="SHA256:verified"),
        public_key_fingerprint="SHA256:controller-key",
        managed_worker_root="/data/easydesign/managed-worker",
        updated_at=NOW,
        public_key="ssh-ed25519 AAAATEST",
    )
    probe = ManagedWorkerProbe(
        observed_at=NOW,
        manager_version="0.1.0.dev2",
        easydesign_version="0.1.0.dev47",
        supported_stage_ranges=((4, 5), (6, 7)),
        backends=(
            {"backend_id": "boltzgen", "ready": True, "detail": "ready"},
            {"backend_id": "protenix-v2", "ready": True, "detail": "ready"},
            {"backend_id": "tnp", "ready": True, "detail": "ready"},
        ),
        managed_root="/data/easydesign/managed-worker",
        gpu_count=8,
        eligible_gpu_count=6,
        gpu_devices=tuple(
            {
                "device": device,
                "name": "NVIDIA A100-PCIE-40GB",
                "memory_total_mib": 40960,
                "memory_used_mib": 1024 if device < 6 else 8192,
                "utilization_percent": 0 if device < 6 else 95,
                "compute_process_count": 0 if device < 6 else 1,
                "eligible": device < 6,
                "reasons": () if device < 6 else ("external-compute-process",),
                "active_lease": False,
            }
            for device in range(8)
        ),
        queue_depth=2,
        running_jobs=1,
        filesystem_total_bytes=10 * 1024**3,
        filesystem_available_bytes=9 * 1024**3,
    )

    class FakeRegistry:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            pass

        def list_latest(self) -> tuple[SimpleNamespace, ...]:
            return (record,)

    class FailingLocalProbe:
        def snapshots(self) -> tuple[object, ...]:
            raise RuntimeError("local probe intentionally unavailable")

    monkeypatch.setattr("easydesign.ui.app.RemoteExecutorRegistry", FakeRegistry)
    monkeypatch.setattr("easydesign.ui.app.NvidiaSmiProbe", FailingLocalProbe)
    probe_arguments: dict[str, object] = {}

    def fake_probe(**kwargs: object) -> ManagedWorkerProbe:
        probe_arguments.update(kwargs)
        return probe

    monkeypatch.setattr("easydesign.ui.app.probe_managed_executor", fake_probe)
    app = create_ui_app(
        runs_root=tmp_path / "runs",
        projects_root=tmp_path / "projects",
        job_root=tmp_path / "runtime" / "state" / "ui" / "jobs",
    )

    with TestClient(app) as client:
        response = client.get("/api/v1/execution-targets")

    assert response.status_code == 200
    managed = response.json()["managed"][0]
    assert managed["pairing_state"] == "paired"
    assert managed["status"] == "available"
    assert managed["gpu_count"] == 8
    assert managed["eligible_gpu_count"] == 6
    assert managed["queue_depth"] == 2
    assert len(managed["devices"]) == 8
    assert probe_arguments["timeout_seconds"] == 60.0

    def failing_probe(**_kwargs: object) -> ManagedWorkerProbe:
        raise RuntimeError("secret /root/workspace/id_ed25519")

    monkeypatch.setattr("easydesign.ui.app.probe_managed_executor", failing_probe)
    with TestClient(app) as client:
        unavailable_response = client.get("/api/v1/execution-targets")

    unavailable = unavailable_response.json()["managed"][0]
    assert unavailable["status"] == "unavailable"
    assert unavailable["detail"] == (
        "已配对，但暂时无法读取受管 GPU 状态；"
        "可稍后刷新，或先选择当前机器"
    )
    assert "/root/" not in unavailable["detail"]


def _region_projection_fixture() -> RegionEditorProjection:
    return RegionEditorProjection(
        run_key="demo/run-001",
        target_id="demo-target",
        target_structure_sha256="a" * 64,
        residue_mapping_sha256="b" * 64,
        structure=ArtifactProjection(
            artifact_id="target-structure",
            role="target-structure",
            file_format="mmcif",
            size_bytes=1,
            sha256="a" * 64,
            token="token",
        ),
        source_annotation_status="not_applicable",
        residues=(
            RegionEditorResidue(
                label_seq_id=1,
                amino_acid="A",
                sequence_index=1,
                auth_chain_id="A",
                auth_residue_id="23",
            ),
            RegionEditorResidue(
                label_seq_id=2,
                amino_acid="P",
                sequence_index=2,
                auth_chain_id="A",
                auth_residue_id="24",
            ),
            RegionEditorResidue(
                label_seq_id=3,
                amino_acid="O",
                sequence_index=3,
                auth_chain_id="A",
                auth_residue_id="25A",
                insertion_code="A",
            ),
        ),
    )


def test_managed_pml_regions_round_trip_to_canonical_label_ids() -> None:
    projection = _region_projection_fixture()
    regions = _regions_from_scene_pml(
        "\n".join(
            (
                "select ed_region_A, chain A and resi 23+25A",
                "select ed_region_B, chain A and resi 24",
                "select ed_region_C, none",
                "",
            )
        ),
        projection,
    )
    assert regions == {"A": (1, 3), "B": (2,)}

    with pytest.raises(ConfigurationError, match="不能唯一映射"):
        _regions_from_scene_pml(
            "select ed_region_A, chain A and resi 999\n",
            projection,
        )


def test_assistant_complete_pml_can_clear_multiple_regions() -> None:
    projection = _region_projection_fixture()
    actual = _validate_assistant_region_scene(
        "\n".join(
            (
                "select ed_region_A, chain A and resi 23",
                "select ed_region_B, none",
                "select ed_region_C, none",
                "",
            )
        ),
        projection,
        current_regions={"A": (1,), "B": (2,), "C": (3,)},
        allow_region_changes=True,
    )
    assert actual == {"A": (1,)}


def test_assistant_complete_pml_maps_model_selectors_to_label_ids() -> None:
    projection = _region_projection_fixture()
    actual = _validate_assistant_region_scene(
        "select ed_region_B, chain A and resi 23+25A\n",
        projection,
        current_regions={},
        allow_region_changes=True,
    )
    assert actual == {"B": (1, 3)}


def test_scientific_analysis_assistant_cannot_mutate_regions() -> None:
    projection = _region_projection_fixture()
    with pytest.raises(ConfigurationError, match="待确认计划"):
        _validate_assistant_region_scene(
            "select ed_region_A, chain A and resi 23+24\n",
            projection,
            current_regions={"A": (1,)},
            allow_region_changes=False,
        )
    assert _validate_assistant_region_scene(
        "select ed_region_A, chain A and resi 23\n",
        projection,
        current_regions={"A": (1,)},
        allow_region_changes=False,
    ) == {"A": (1,)}


def test_only_scientific_discovery_requests_create_analysis_plans() -> None:
    assert _scientific_analysis_methods("清空区域 B 和区域 C，只保留区域 A") == ()
    assert _scientific_analysis_methods("寻找最佳 hotspot 区域") == (
        "sasa",
        "scannet",
    )


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
    attempt_number: int = 1,
) -> ArtifactRef:
    relative = f"{stage}/attempt-{attempt_number:04d}/artifacts/{artifact_id}.json"
    _write_json(root, relative, value)
    return ArtifactRef.from_file(
        run_root=root,
        relative_path=relative,
        artifact_id=artifact_id,
        role=artifact_id,
        file_format="json",
        producer_stage=str(stage),
        producer_attempt=f"attempt-{attempt_number:04d}",
    )


def _stage(
    root: Path,
    *,
    stage: StageId,
    outputs: tuple[ArtifactRef, ...],
    attempt_number: int = 1,
    contract_version: str = "0.1",
    manifest_name: str | None = None,
) -> ArtifactRef:
    attempt_id = f"attempt-{attempt_number:04d}"
    attempt = Attempt(
        attempt_id=attempt_id,
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
        contract_version=contract_version,
        status=ExecutionStatus.SUCCEEDED,
        created_at=NOW,
        completed_at=NOW,
        output_artifacts=outputs,
        attempts=(attempt,),
        selected_attempt_id=attempt_id,
    )
    relative = manifest_name or f"manifests/{stage}.json"
    dump_model(manifest, root / relative)
    return ArtifactRef.from_file(
        run_root=root,
        relative_path=relative,
        artifact_id=f"{stage}-manifest",
        role="stage-manifest",
        file_format="json",
        producer_stage=str(stage),
        producer_attempt=attempt_id,
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
                    "candidates": [{"candidate_id": "candidate-1", "local_gate_pass": True}],
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


def _publish_scale_evidence_continuation(
    tmp_path: Path,
    run_root: Path,
) -> ProjectScaleEvidenceContinuation:
    run = load_model(run_root / "manifests" / "run-manifest-0001.json", RunManifest)
    stage05_ref = next(
        item
        for item in run.stage_manifest_refs
        if item.producer_stage == str(StageId.PILOT_FILTERING)
    )
    stage05 = load_model(stage05_ref.verify(run_root), StageManifest)
    pilot_ref = stage05.require_output("pilot-filter-report")

    def link(
        *,
        run_id: str,
        executor_id: str,
        run_sha256: str,
    ) -> RunEvidenceLink:
        return RunEvidenceLink(
            source_project_id=run.project_id,
            source_run_id=run_id,
            source_run_manifest_sha256=run_sha256,
            source_artifact=pilot_ref,
            executor_id=executor_id,
            artifact_sha256=pilot_ref.sha256,
            artifact_size_bytes=pilot_ref.size_bytes,
        )

    local_sha = sha256_file(run_root / "manifests" / "run-manifest-0001.json")
    local_link = link(
        run_id=run.run_id,
        executor_id="local",
        run_sha256=local_sha,
    )
    policy = PolicyReevaluationRecord(
        generated_at=NOW,
        source_stage05_bundle=local_link,
        source_stage05_status="stopped-no-scale-winner",
        strategies=(
            ReevaluatedStrategy(
                strategy_id="patch-1__scaffold-x",
                tier="tier-a",
                score_yaml=0.8,
                old_selected_for_expansion=True,
                new_promoted=True,
                promotion_rank=1,
            ),
        ),
        promoted_strategy_ids=("patch-1__scaffold-x",),
        status="strategies-promoted",
    )
    remote_link = link(
        run_id="remote-scale-run",
        executor_id="suzhou2",
        run_sha256="f" * 64,
    )
    continuation = ProjectScaleEvidenceContinuation(
        continuation_id="remote-scale-adoption",
        generated_at=NOW,
        project_id=run.project_id,
        source_local_run_id=run.run_id,
        source_local_run_manifest_sha256=local_sha,
        policy_reevaluation=policy,
        scale_evidence_adoption=ScaleEvidenceAdoptionRecord(
            generated_at=NOW,
            policy_reevaluation_sha256="e" * 64,
            source_scale_bundle=remote_link,
            strategy_ids=("patch-1__scaffold-x",),
            shard_count=2,
            candidate_count=50_000,
            expected_candidate_count=50_000,
        ),
        source_stage06_manifest=remote_link,
        source_scale_plan=remote_link,
        source_scale_progress=remote_link,
        source_candidate_index=remote_link,
        execution=AdoptedScaleExecutionSummary(
            executor_id="suzhou2",
            strategy_ids=("patch-1__scaffold-x",),
            strategy_candidate_counts={"patch-1__scaffold-x": 50_000},
            strategy_shard_counts={"patch-1__scaffold-x": 2},
            devices=(0, 1),
            shard_count=2,
            succeeded_task_count=2,
            failed_task_count=0,
            candidate_count=50_000,
            elapsed_seconds=3_600,
            completed_at=NOW,
        ),
        device_execution=(
            AdoptedDeviceExecutionSummary(
                device=0,
                task_count=1,
                attempt_count=1,
                failed_attempt_count=0,
                candidate_count=25_000,
                busy_seconds=3_500,
            ),
            AdoptedDeviceExecutionSummary(
                device=1,
                task_count=1,
                attempt_count=1,
                failed_attempt_count=0,
                candidate_count=25_000,
                busy_seconds=3_500,
            ),
        ),
    )
    record_root = (
        tmp_path / "projects" / run.project_id / "evidence-adoptions" / continuation.continuation_id
    )
    dump_model(continuation, record_root / "record.json")
    (record_root.parent / "CURRENT").write_text(
        f"{continuation.continuation_id}/record.json\n",
        encoding="utf-8",
    )
    return continuation


def test_remote_scale_adoption_unlocks_stage06_without_rewriting_history(
    tmp_path: Path,
) -> None:
    run_root = _audited_run(tmp_path)
    continuation = _publish_scale_evidence_continuation(tmp_path, run_root)
    registry = UiRunRegistry(tmp_path / "runs")
    projection = get_run_projection(
        run_root,
        registry=registry,
        signer=ArtifactTokenSigner(b"test-secret"),
        projects_root=tmp_path / "projects",
    )
    execution = get_execution_progress(
        run_root,
        6,
        projects_root=tmp_path / "projects",
    )
    overview = get_filter_overview(
        run_root,
        registry=registry,
        policy_reevaluation=continuation.policy_reevaluation,
    )

    assert projection.stages[4].state == "succeeded"
    assert projection.stages[4].highlights["historical_policy_status"] == ("scientific-stop")
    assert projection.stages[5].state == "succeeded"
    assert projection.stages[5].highlights["collected_candidates"] == 50_000
    assert projection.stages[6].state == "not-reached"
    assert execution.status == "succeeded"
    assert execution.collected_candidates == 50_000
    assert execution.total_tasks == 2
    assert tuple(item.device for item in execution.devices) == (0, 1)
    assert overview.advisory_validation is True
    assert overview.state == "succeeded"
    assert overview.counts["promoted_strategies"] == 1
    assert overview.counts["diagnostic_warnings"] == 1


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
        (entry.project_id, entry.run_id) for entry in index.entries if entry.is_project_primary
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
        if entry.project_id == "target-alpha" and entry.run_id == "run-scientific-stop"
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
        relative_path=("01-target-preparation/attempt-0001/artifacts/target-bundle.json"),
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


def test_artifact_token_secret_persists_across_ui_restarts(tmp_path: Path) -> None:
    run_root = _audited_run(tmp_path)
    registry = UiRunRegistry(tmp_path / "runs")
    run_key = registry.register(run_root)
    artifact = ArtifactRef.from_file(
        run_root=run_root,
        relative_path=("01-target-preparation/attempt-0001/artifacts/target-bundle.json"),
        artifact_id="target-bundle",
        role="target-bundle",
        file_format="json",
        producer_stage=str(StageId.TARGET_PREPARATION),
        producer_attempt="attempt-0001",
    )
    secret_path = tmp_path / "runtime" / "state" / "ui" / "artifact-token-secret.bin"

    first = ArtifactTokenSigner.from_file(secret_path, lifetime_seconds=10)
    token = first.sign(run_key, artifact, now=0)
    second = ArtifactTokenSigner.from_file(secret_path, lifetime_seconds=10)

    assert second.verify(token, now=5).run_key == run_key
    assert secret_path.read_bytes()
    if os.name == "posix":
        assert secret_path.stat().st_mode & 0o077 == 0


def test_live_execution_projection_uses_structured_runtime_state(
    tmp_path: Path,
) -> None:
    run_root = _audited_run(tmp_path)
    historical = RunManifest.model_validate_json(
        (run_root / "manifests" / "run-manifest-0001.json").read_text(encoding="utf-8")
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


def test_stage05_overview_distinguishes_v16_advisory_from_v15_stop(
    tmp_path: Path,
) -> None:
    run_root = _audited_run(tmp_path)
    stage05 = _stage(
        run_root,
        stage=StageId.PILOT_FILTERING,
        attempt_number=2,
        contract_version="0.2",
        manifest_name="manifests/05-pilot-filtering-v0.2.json",
        outputs=(
            _artifact(
                run_root,
                stage=StageId.PILOT_FILTERING,
                artifact_id="pilot-filter-report",
                attempt_number=2,
                value={
                    "status": "strategies-promoted",
                    "candidate_records": [],
                    "strategy_summaries": [
                        {
                            "strategy_id": "patch-1__scaffold-x",
                            "candidate_count": 40,
                            "unique_sequence_count": 40,
                            "boltzgen_hard_pass_count": 6,
                            "final_gate_pass_count": 5,
                            "final_gate_pass_rate": 0.125,
                            "tier": "tier-a",
                            "score_screen_all_median": 0.3,
                            "score_screen_top_quartile_mean": 0.4,
                            "score_yaml": 0.39,
                            "selected_for_expansion": True,
                        }
                    ],
                    "promoted_strategy_ids": ["patch-1__scaffold-x"],
                },
            ),
            _artifact(
                run_root,
                stage=StageId.PILOT_FILTERING,
                artifact_id="advisory-validation-report",
                attempt_number=2,
                value={
                    "profile_id": "nanobody-filter-standard-v1.6",
                    "status": "completed-with-warnings",
                    "promoted_strategies": [
                        {
                            "strategy_id": "patch-1__scaffold-x",
                            "promotion_rank": 1,
                            "advisory_status": "advisory-warning",
                        }
                    ],
                    "warnings": [{"code": "full-target-no-structure-pass"}],
                    "candidates": [],
                    "predictions": [],
                },
            ),
        ),
    )
    manifest_path = run_root / "manifests" / "run-manifest-0001.json"
    manifest = load_model(manifest_path, RunManifest)
    revision_path = run_root / "manifests" / "run-manifest-0002.json"
    dump_model(
        manifest.model_copy(
            update={
                "stage_manifest_refs": (*manifest.stage_manifest_refs[:-1], stage05),
                "revision": 2,
                "previous_manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
                "updated_at": NOW + timedelta(seconds=1),
                "completed_at": NOW + timedelta(seconds=1),
            }
        ),
        revision_path,
    )
    (run_root / "manifests" / "LATEST").write_text(
        f"{revision_path.name}\n",
        encoding="utf-8",
    )

    overview = get_filter_overview(
        run_root,
        registry=UiRunRegistry(tmp_path / "runs"),
    )

    assert overview.advisory_validation is True
    assert overview.counts["promoted_strategies"] == 1
    assert overview.counts["diagnostic_warnings"] == 1
    assert "不会取消晋级" in overview.conclusion_title


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
        assert "connect-src 'self' data: blob:" in health.headers["content-security-policy"]
        assert client.get("/api/v1/health", headers={"host": "example.com"}).status_code == 403
        response = client.get(f"/api/v1/artifacts/{token}")
        assert response.status_code == 200
        overview = client.get(f"/api/v1/runs/{projection.run_key}/stages/5/overview")
        assert overview.status_code == 200
        assert overview.json()["advisory_validation"] is False
        assert overview.json()["counts"]["expanded"] == 1
        assert overview.json()["conclusion_title"] == "当前没有可进入规模化生成的设计策略"
        candidates = client.get(
            f"/api/v1/runs/{projection.run_key}/stages/5/candidates",
            params={"phase": "expansion", "page_size": 1},
        )
        assert candidates.status_code == 200
        assert candidates.json()["total"] == 1
        detail = client.get(
            (f"/api/v1/runs/{projection.run_key}/stages/5/candidates/candidate-1"),
            params={"phase": "expansion"},
        )
        assert detail.status_code == 200
        assert detail.json()["candidate_id"] == "candidate-1"
        catalog = client.get(f"/api/v1/runs/{projection.run_key}/stages/5/metrics")
        assert catalog.status_code == 200
        assert len(catalog.json()) >= 20
        strategies = client.get(f"/api/v1/runs/{projection.run_key}/stages/5/strategies")
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
        execution = client.get(f"/api/v1/runs/{projection.run_key}/stages/4/execution")
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
        strategy_execution = execution.json()["strategies"]
        assert strategy_execution == [
            {
                "strategy_id": "patch-1-scaffold-x",
                "task_count": 1,
                "succeeded_task_count": 1,
                "failed_task_count": 0,
                "requested_candidates": 4,
                "collected_candidates": 4,
            }
        ]
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
        run_root / "01-target-preparation" / "attempt-0001" / "artifacts" / "target-bundle.json"
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


def test_browser_pymol_status_requires_the_complete_verified_offline_runtime(
    tmp_path: Path,
) -> None:
    app = create_ui_app(
        runs_root=tmp_path / "runs",
        projects_root=tmp_path / "projects",
        job_root=tmp_path / "runtime" / "state" / "ui" / "jobs",
    )

    with TestClient(app) as client:
        response = client.get("/api/v1/browser-pymol/status")

    assert response.status_code == 200
    assert response.json()["available"] is True
    assert response.json()["integrity_status"] == "verified"
    assert response.json()["integrity_errors"] == []


def test_structure_assistant_exposes_only_platform_service_status(
    tmp_path: Path,
) -> None:
    secret_path = (
        tmp_path / "runtime" / "secrets" / "structure-assistant" / "platform-provider.yaml"
    )
    secret_path.parent.mkdir(parents=True, exist_ok=True)
    secret_path.write_text(
        "\n".join(
            (
                'schema_version: "0.1"',
                "provider: deepseek",
                "model: deepseek-chat",
                "base_url: https://api.deepseek.com",
                "api_key: owner-secret",
                "",
            )
        ),
        encoding="utf-8",
    )
    secret_path.chmod(0o600)
    app = create_ui_app(
        runs_root=tmp_path / "runs",
        projects_root=tmp_path / "projects",
        job_root=tmp_path / "runtime" / "state" / "ui" / "jobs",
    )

    with TestClient(app) as client:
        response = client.get("/api/v1/structure-assistant/status")
        legacy = client.get("/api/v1/structure-assistant/providers")
        legacy_write = client.post(
            "/api/v1/structure-assistant/providers/deepseek",
            json={
                "model": "other",
                "base_url": "https://example.invalid",
                "api_key": "user-key",
            },
        )

    assert response.status_code == 200
    assert response.json() == {
        "available": True,
        "service_name": "EasyDesign 结构助手",
        "detail": "平台服务已就绪，使用者无需提供 API Key。",
    }
    assert "deepseek" not in response.text
    assert "owner-secret" not in response.text
    assert legacy.status_code == 404
    assert legacy_write.status_code in {404, 405}


def test_continuation_preflight_failure_does_not_advance_session(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    run_root = _audited_run(tmp_path)
    latest_name = read_last_text_line(run_root / "manifests" / "LATEST")
    manifest = load_model(run_root / "manifests" / latest_name, RunManifest)
    stage02_manifest = manifest.model_copy(
        update={
            "stage_manifest_refs": manifest.stage_manifest_refs[:2],
            "updated_at": NOW + timedelta(minutes=1),
            "completed_at": NOW + timedelta(minutes=1),
        }
    )
    dump_model(stage02_manifest, run_root / "manifests" / "run-manifest-stage02.json")
    (run_root / "manifests" / "LATEST").write_text(
        "run-manifest-stage02.json\n",
        encoding="utf-8",
    )
    upsert_run_index_entries(
        tmp_path / "runs",
        (
            RunIndexEntry(
                category="project-run",
                path=run_root.relative_to(tmp_path / "runs").as_posix(),
                layout_version="1",
                status="succeeded",
                project_id="target-alpha",
                run_id="run-scientific-stop",
            ),
        ),
        generated_at=NOW,
    )
    app = create_ui_app(
        runs_root=tmp_path / "runs",
        projects_root=tmp_path / "projects",
        job_root=tmp_path / "runtime" / "state" / "ui" / "jobs",
    )
    service = app.state.easydesign
    run_key = service.registry.register(run_root)
    session = service.sessions.create(
        project_id="target-alpha",
        design_mode="stepwise",
        execution_mode="review-gated",
    )
    service.sessions.attach_run(
        session.session_id,
        run_key=run_key,
        status="succeeded",
        stage_number=2,
    )

    def fail_launch(**_kwargs: Any) -> Any:
        raise ConfigurationError("synthetic preflight failure")

    monkeypatch.setattr(service.jobs, "launch", fail_launch)

    with TestClient(app) as client:
        response = client.post(
            f"/api/v1/runs/{run_key}/continue/3",
            json={
                "session_id": session.session_id,
                "stage_number": 3,
                "execution_mode": "review-gated",
                "options": {
                    "profile": "boltzgen-vhh-basic-v1",
                    "scaffold_registry": "official-vhh7-v1",
                    "scaffold_ids": None,
                    "candidates_per_strategy": 40,
                },
                "confirmed": True,
            },
        )

    assert response.status_code == 400
    restored = service.sessions.load(session.session_id)
    assert [item.stage_number for item in restored.config_revisions] == []
    assert restored.current_stage == 2
    assert not list(
        (service.sessions.root / session.session_id / "config-revisions").glob("stage03-*.yaml")
    )
    assert not (tmp_path / "projects" / "target-alpha" / "easydesign.stage03.rev0001.yaml").exists()


def test_region_revision_rejects_stale_session_run_key(tmp_path: Path) -> None:
    app = create_ui_app(
        runs_root=tmp_path / "runs",
        projects_root=tmp_path / "projects",
        job_root=tmp_path / "runtime" / "state" / "ui" / "jobs",
    )
    service = app.state.easydesign
    session = service.sessions.create(
        project_id="target-alpha",
        design_mode="stepwise",
        execution_mode="review-gated",
    )
    service.sessions.attach_run(
        session.session_id,
        run_key="old-stage01-run-key",
        status="succeeded",
        stage_number=1,
    )
    service.sessions.attach_run(
        session.session_id,
        run_key="new-stage02-run-key",
        status="succeeded",
        stage_number=2,
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/runs/old-stage01-run-key/regions/revise",
            json={
                "session_id": session.session_id,
                "regions": [{"id": "A", "label_seq_ids": [1, 2, 3]}],
                "confirmed": True,
            },
        )

    assert response.status_code == 400
    assert "最新运行" in response.json()["detail"]


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
        published_uploads = client.get("/api/v1/uploads").json()["receipts"]
        published_receipt = next(
            item for item in published_uploads if item["upload_token"] == receipt["upload_token"]
        )
        assert published_receipt["status"] == "published"
        assert published_receipt["path_ref"] == "project://target-demo/inputs/target.fasta"
        audit_events = [
            json.loads(line)
            for log_path in sorted((tmp_path / "runtime" / "logs").glob("ui-operations-*.jsonl"))
            for line in log_path.read_text(encoding="utf-8").splitlines()
        ]
        assert any(
            event["event"] == "upload.received"
            and event["path_ref"].startswith("runtime://tmp/ui-uploads/")
            and event["resolved_path"].startswith(str(tmp_path))
            for event in audit_events
        )
        assert any(
            event["event"] == "project.publish.done"
            and event["to_path_ref"] == "project://target-demo"
            and event["to_resolved_path"] == str(tmp_path / "projects" / "target-demo")
            for event in audit_events
        )
        metadata = load_latest_runtime_model(
            tmp_path / "projects" / "target-demo" / "project-metadata.json",
            ProjectMetadata,
        )
        assert metadata.project_id == "target-demo"
        assert metadata.input_type == "local-file"
        assert metadata.configured_through_stage == 1
        projects = client.get("/api/v1/projects")
        assert projects.status_code == 200
        assert projects.json()["projects"] == []
        assert projects.json()["drafts"][0]["project_id"] == "target-demo"
        assert projects.json()["drafts"][0]["status"] == "draft"

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


def test_project_preflight_rejects_noncanonical_id_before_upload(
    tmp_path: Path,
) -> None:
    app = create_ui_app(
        runs_root=tmp_path / "runs",
        projects_root=tmp_path / "projects",
        job_root=tmp_path / "runtime" / "state" / "ui" / "jobs",
    )
    with TestClient(app) as client:
        preflight = client.get(
            "/api/v1/project-preflight",
            params={"project_id": "Test"},
        )
        assert preflight.status_code == 200
        assert preflight.json() == {
            "available": False,
            "project_id": "Test",
            "reason": (
                "项目名称只能使用小写字母、数字、点、下划线和连字符，并且必须以小写字母或数字开头"
            ),
            "existing_project": None,
            "suggested_project_id": "test",
        }

        direct_create = client.post(
            "/api/v1/projects",
            json={
                "project_id": "Test",
                "source_type": "pdb-id",
                "source_value": "1UBQ",
                "stop_after_stage": 1,
            },
        )
        assert direct_create.status_code == 400
        assert "建议使用：test" in direct_create.json()["detail"]
        assert not (tmp_path / "projects" / "Test").exists()


def test_failed_project_publication_keeps_only_retryable_upload_receipt(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    app = create_ui_app(
        runs_root=tmp_path / "runs",
        projects_root=tmp_path / "projects",
        job_root=tmp_path / "runtime" / "state" / "ui" / "jobs",
    )
    content = b"failed-project-input"
    with TestClient(app, raise_server_exceptions=False) as client:
        receipt = client.post(
            "/api/v1/uploads",
            json={
                "filename": "target.pse",
                "content_base64": base64.b64encode(content).decode("ascii"),
            },
        ).json()

        import easydesign.ui.app as ui_app_module

        def fail_initialize_project(**_kwargs: Any) -> Any:
            raise RuntimeError("intentional transactional failure")

        monkeypatch.setattr(
            ui_app_module,
            "initialize_project",
            fail_initialize_project,
        )
        response = client.post(
            "/api/v1/projects",
            json={
                "project_id": "failed-project",
                "source_type": "local-file",
                "source_value": receipt["upload_token"],
                "stop_after_stage": 1,
                "design_mode": "stepwise",
            },
        )

        uploads = client.get("/api/v1/uploads").json()["receipts"]
        sessions = client.get("/api/v1/design-sessions").json()
        projects = client.get("/api/v1/projects").json()

    assert response.status_code == 500
    assert not (tmp_path / "projects" / "failed-project").exists()
    assert sessions == []
    assert projects["drafts"] == []
    failed = next(item for item in uploads if item["upload_token"] == receipt["upload_token"])
    assert failed["status"] == "failed"
    assert (tmp_path / failed["relative_path"]).read_bytes() == content


def test_project_publication_failure_after_input_move_quarantines_receipt(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    app = create_ui_app(
        runs_root=tmp_path / "runs",
        projects_root=tmp_path / "projects",
        job_root=tmp_path / "runtime" / "state" / "ui" / "jobs",
    )
    content = b"failed-after-input-move"
    with TestClient(app, raise_server_exceptions=False) as client:
        receipt = client.post(
            "/api/v1/uploads",
            json={
                "filename": "target.pse",
                "content_base64": base64.b64encode(content).decode("ascii"),
            },
        ).json()

        import easydesign.ui.app as ui_app_module

        def fail_validate_after_move(*_args: Any, **_kwargs: Any) -> Any:
            raise RuntimeError("intentional validation failure after input move")

        monkeypatch.setattr(
            ui_app_module,
            "validate_run_configuration",
            fail_validate_after_move,
        )
        response = client.post(
            "/api/v1/projects",
            json={
                "project_id": "failed-after-move",
                "source_type": "local-file",
                "source_value": receipt["upload_token"],
                "stop_after_stage": 1,
                "design_mode": "stepwise",
            },
        )
        uploads = client.get("/api/v1/uploads").json()["receipts"]

    assert response.status_code == 500
    assert not (tmp_path / "projects" / "failed-after-move").exists()
    failed = next(item for item in uploads if item["upload_token"] == receipt["upload_token"])
    assert failed["status"] == "failed-quarantined"
    assert failed["path_ref"].startswith("quarantine://")
    quarantined = tmp_path / failed["relative_path"]
    assert quarantined.read_bytes() == content
    assert "/root/autodl-tmp" not in failed["relative_path"]
    assert "/root/autodl-tmp" not in failed["path_ref"]


def test_update_config_validates_project_relative_inputs_from_ui_temp(
    tmp_path: Path,
) -> None:
    app = create_ui_app(
        runs_root=tmp_path / "runs",
        projects_root=tmp_path / "projects",
        job_root=tmp_path / "runtime" / "state" / "ui" / "jobs",
    )
    content = b"pse-config-update-fixture"
    with TestClient(app) as client:
        receipt = client.post(
            "/api/v1/uploads",
            json={
                "filename": "target.pse",
                "content_base64": base64.b64encode(content).decode("ascii"),
            },
        ).json()
        project = client.post(
            "/api/v1/projects",
            json={
                "project_id": "pse-config-demo",
                "source_type": "local-file",
                "source_value": receipt["upload_token"],
                "execution_mode": "review-gated",
                "design_intent": "exploratory",
                "stop_after_stage": 1,
                "design_mode": "stepwise",
            },
        )
        assert project.status_code == 200
        yaml_text = project.json()["config"]
        assert "path: inputs/target.pse" in yaml_text

        update = client.put(
            "/api/v1/projects/pse-config-demo/config",
            json={"yaml_text": yaml_text},
        )

    assert update.status_code == 200
    assert update.json()["config_path"] == (
        "pse-config-demo/config-revisions/easydesign.rev-000001.yaml"
    )
    assert (
        read_last_text_line(tmp_path / "projects" / "pse-config-demo" / "CONFIG_CURRENT")
        == "config-revisions/easydesign.rev-000001.yaml"
    )


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
            params={
                "filename": "target.pse",
                "sha256": hashlib.sha256(content).hexdigest(),
            },
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
            params={
                "filename": "empty.pse",
                "sha256": hashlib.sha256(b"").hexdigest(),
            },
            content=b"",
            headers={"Content-Type": "application/octet-stream"},
        )
        assert empty.status_code == 400
        assert "空文件" in empty.json()["detail"]


def test_gateway_lists_profile_and_first_class_managed_remote_executor_ids(
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
    payload = response.json()
    assert [item["executor_id"] for item in payload["executors"]] == [
        "suzhou2",
        "suzhou2-a100x8",
    ]
    assert payload["executors"][0] == {
        "executor_id": "suzhou2",
        "label": "Suzhou2 公共算力",
        "type": "managed-ssh",
        "pairing_state": "not-paired",
        "controller_id": None,
        "host": None,
        "port": None,
        "user": None,
        "host_fingerprint": None,
        "key_pair_available": False,
    }


def test_gateway_bootstraps_managed_ssh_key_with_memory_only_password(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    private_key = tmp_path / "runtime" / "secrets" / "ssh" / "suzhou2" / "id_ed25519"
    host_identity = SshHostIdentity(
        host="suzhou2.example",
        port=22,
        key_type="ssh-ed25519",
        fingerprint="SHA256:hostfingerprint",
        known_hosts_line="suzhou2.example ssh-ed25519 AAAATEST",
        observed_at=NOW,
    )
    waiting = RemoteExecutorPairingRevision(
        revision=1,
        executor_id="suzhou2",
        controller_id="controller-test",
        state="awaiting-public-key",
        host="suzhou2.example",
        port=22,
        user="root",
        host_identity=host_identity,
        identity_file=private_key,
        public_key_file=private_key.with_suffix(".pub"),
        known_hosts_file=private_key.parent / "known_hosts",
        public_key_fingerprint="SHA256:controllerfingerprint",
        public_key="ssh-ed25519 AAAACONTROLLER easydesign:test",
        created_at=NOW,
        updated_at=NOW,
    )
    paired = waiting.model_copy(
        update={
            "revision": 2,
            "state": "paired",
            "updated_at": NOW + timedelta(seconds=1),
        }
    )

    class FakeRegistry:
        def __init__(self, _workspace: object) -> None:
            pass

        def latest(self, executor_id: str) -> RemoteExecutorPairingRevision | None:
            assert executor_id == "suzhou2"
            return waiting

        def mark_paired(self, executor_id: str) -> RemoteExecutorPairingRevision:
            assert executor_id == "suzhou2"
            return paired

    captured: dict[str, str] = {}

    def fake_install(
        record: RemoteExecutorPairingRevision,
        password: str,
    ) -> SshPublicKeyInstallResult:
        assert record == waiting
        captured["password"] = password
        return SshPublicKeyInstallResult(
            status="installed",
            public_key_fingerprint=record.public_key_fingerprint,
        )

    probe = ManagedWorkerProbe(
        observed_at=NOW,
        manager_version="0.1.0.dev2",
        easydesign_version="0.1.0.dev47",
        supported_stage_ranges=((4, 5), (6, 7)),
        backends=(
            {"backend_id": "boltzgen", "ready": True, "detail": "ready"},
            {"backend_id": "protenix-v2", "ready": True, "detail": "ready"},
            {"backend_id": "tnp", "ready": True, "detail": "ready"},
        ),
        managed_root="/data/easydesign/managed-worker",
        gpu_count=8,
        eligible_gpu_count=8,
        gpu_devices=tuple(
            {
                "device": device,
                "name": "NVIDIA A100-PCIE-40GB",
                "memory_total_mib": 40960,
                "memory_used_mib": 0,
                "utilization_percent": 0,
                "compute_process_count": 0,
                "eligible": True,
            }
            for device in range(8)
        ),
        queue_depth=0,
        running_jobs=0,
        filesystem_total_bytes=1,
        filesystem_available_bytes=1,
    )
    monkeypatch.setattr("easydesign.ui.app.RemoteExecutorRegistry", FakeRegistry)
    monkeypatch.setattr("easydesign.ui.app.install_public_key_with_password", fake_install)
    monkeypatch.setattr("easydesign.ui.app.probe_pending_managed_executor", lambda _: probe)
    app = create_ui_app(
        runs_root=tmp_path / "runs",
        projects_root=tmp_path / "projects",
        job_root=tmp_path / "runtime" / "state" / "ui" / "jobs",
    )

    secret = "one-use-only-secret"
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/remote-executors/suzhou2/pair-password-bootstrap",
            json={"password": secret, "confirmed": True},
        )

    assert response.status_code == 200
    assert response.json()["status"] == "paired"
    assert response.json()["probe"]["gpu_count"] == 8
    assert captured == {"password": secret}
    assert secret not in response.text
