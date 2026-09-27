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
