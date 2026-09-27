from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

from easydesign.core import ManifestStateError
from easydesign.orchestration.local_jobs import LocalStepJob
from easydesign.product.projection import job_progress


def _job(runs_root: Path) -> LocalStepJob:
    now = datetime.now(UTC)
    return LocalStepJob(
        job_id="job-progress0001",
        operation="run",
        status="running",
        project_id="project-a",
        project_root=runs_root.parent / "projects/project-a",
        step=3,
        config_path=runs_root.parent / "projects/project-a/config.yaml",
        run_id="pilot-v3-active",
        run_root=runs_root / "project-a/foundation",
        branch="codex/test",
        log_path=runs_root.parent / "runtime/logs/job.log",
        drain_path=runs_root.parent / "runtime/state/job.drain",
        created_at=now,
        updated_at=now,
    )


def test_progress_follows_new_continuation_run_before_worker_returns(
    tmp_path: Path, monkeypatch
) -> None:
    runs_root = tmp_path / "runs"
    active = runs_root / "project-a/pilot-v3-active"
    active.mkdir(parents=True)
    captured: list[Path] = []

    def read(root: Path):
        captured.append(root)
        return SimpleNamespace(
            stage_id="04-pilot-generation",
            status="running",
            collected_candidates=2,
            planned_candidates=28,
            succeeded_tasks=1,
            total_tasks=7,
            running_tasks=6,
            estimated_remaining_seconds=None,
            task_heartbeats=(),
        )

    monkeypatch.setattr("easydesign.product.projection.read_pipeline_progress", read)

    value = job_progress(_job(runs_root), runs_root)

    assert captured == [active.resolve()]
    assert value is not None
    assert value["stage_id"] == "04-pilot-generation"
    assert value["total"] == 28


def test_progress_reports_gpu_wait_before_stage04_plan_exists(
    tmp_path: Path, monkeypatch
) -> None:
    runs_root = tmp_path / "runs"
    active = runs_root / "project-a/pilot-v3-active"
    runtime = active / "04-pilot-generation/attempt-0001/runtime"
    runtime.mkdir(parents=True)
    (runtime / "gpu-inventory.json").write_text(
        json.dumps({"waiting_for_resources": True}), encoding="utf-8"
    )
    matrix = active / "03-boltzgen-configuration/attempt-0001/artifacts/design-matrix.json"
    matrix.parent.mkdir(parents=True)
    matrix.write_text(
        json.dumps(
            {
                "strategies": [
                    {"candidates_per_strategy": 4},
                    {"candidates_per_strategy": 4},
                    {"candidates_per_strategy": 4},
                ]
            }
        ),
        encoding="utf-8",
    )

    def unavailable(_root: Path):
        raise ManifestStateError("progress not published yet")

    monkeypatch.setattr("easydesign.product.projection.read_pipeline_progress", unavailable)

    value = job_progress(_job(runs_root), runs_root)

    assert value is not None
    assert value["status"] == "waiting-resource"
    assert value["substage"] == "waiting-resource"
    assert value["substage_label"] == "Waiting for an available GPU"
    assert value["total"] == 12
    assert value["total_tasks"] == 3


def test_progress_reads_live_boltzgen_substage_when_worker_has_no_heartbeats(
    tmp_path: Path, monkeypatch
) -> None:
    runs_root = tmp_path / "runs"
    active = runs_root / "project-a/pilot-v3-active"
    for task in ("task-a", "task-b"):
        log = active / f"04-pilot-generation/attempt-0001/tasks/{task}/attempt-0001/stdout.log"
        log.parent.mkdir(parents=True)
        log.write_text(
            "[Step 1/5] design - Predicting DataLoader 0: 4/4\r"
            "[Step 2/5] inverse_folding - Predicting DataLoader 0: 4/4\r",
            encoding="utf-8",
        )

    monkeypatch.setattr(
        "easydesign.product.projection.read_pipeline_progress",
        lambda _root: SimpleNamespace(
            stage_id="04-pilot-generation",
            status="running",
            collected_candidates=0,
            planned_candidates=8,
            succeeded_tasks=0,
            total_tasks=2,
            running_tasks=2,
            estimated_remaining_seconds=None,
            task_heartbeats=(),
        ),
    )

    value = job_progress(_job(runs_root), runs_root)

    assert value is not None
    assert value["substage"] == "boltzgen-inverse-fold"
    assert value["substage_label"] == "Inverse fold"
    assert value["substage_completed"] == 8
    assert value["substage_total"] == 8
    assert value["pipeline_step"] == 2
    assert value["pipeline_steps"] == 5
