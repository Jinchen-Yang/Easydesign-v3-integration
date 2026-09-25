from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from easydesign.core import ExecutionStatus, TargetInputError
from easydesign.local_worker import _failure_status, _resume_until_boundary
from easydesign.orchestration.local_jobs import (
    LocalStepJob,
    LocalStepJobController,
    wait_or_detach,
)
from easydesign.workspace_context import WorkspaceContext


def _workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> WorkspaceContext:
    (tmp_path / "easydesign-workspace.yaml").write_text(
        'schema_version: "0.1"\nworkspace_id: local-job-test\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("EASYDESIGN_WORKSPACE", str(tmp_path))
    context = WorkspaceContext.from_root(tmp_path)
    context.ensure_layout()
    return context


def _job(
    context: WorkspaceContext,
    *,
    process_id: int | None = None,
    step: int = 4,
) -> LocalStepJob:
    now = datetime.now(UTC)
    return LocalStepJob(
        job_id="job-semanticlocal01",
        operation="run",
        status="running",
        project_id="example",
        project_root=context.projects_root / "example",
        step=step,
        config_path=context.projects_root / "example/config.yaml",
        process_id=process_id,
        branch="easydesign-local",
        log_path=context.runtime_root / "logs/job.log",
        drain_path=context.runtime_root / "state/local-jobs/job.drain",
        created_at=now,
        updated_at=now,
    )


def test_worker_loss_is_an_explicit_operational_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    context = _workspace(tmp_path, monkeypatch)
    controller = LocalStepJobController(context)
    controller.update(_job(context, process_id=999_999_999))

    loaded = controller.load("job-semanticlocal01")

    assert loaded.status == "operational-failed"
    assert loaded.error == "local-worker-exited-without-terminal-receipt"


def test_worker_launch_detaches_and_uses_local_writable_roots(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    context = _workspace(tmp_path, monkeypatch)
    controller = LocalStepJobController(context)
    project = context.projects_root / "example"
    project.mkdir()
    config = project / "config.yaml"
    config.write_text("schema_version: '0.8'\n", encoding="utf-8")
    captured: dict[str, Any] = {}

    class Process:
        pid = 424242

    def fake_popen(command: list[str], **kwargs: Any) -> Process:
        captured["command"] = command
        captured.update(kwargs)
        return Process()

    monkeypatch.setattr("easydesign.orchestration.local_jobs.subprocess.Popen", fake_popen)
    monkeypatch.setattr(
        "easydesign.orchestration.local_jobs._branch", lambda _context: "easydesign-local"
    )

    job = controller.launch(
        operation="run",
        project_id="example",
        project_root=project,
        step=4,
        config_path=config,
    )

    assert job.process_id == 424242
    assert captured["start_new_session"] is True
    environment = captured["env"]
    assert environment["HOME"] == str(context.runtime_root / "home")
    assert environment["HF_HUB_OFFLINE"] == "1"
    assert environment["PYTHONDONTWRITEBYTECODE"] == "1"


def test_preflight_failure_retries_same_job_and_preserves_failed_revision(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    context = _workspace(tmp_path, monkeypatch)
    controller = LocalStepJobController(context)
    project = context.projects_root / "example"
    project.mkdir()
    config = project / "config.yaml"
    config.write_text("schema_version: '0.9'\n", encoding="utf-8")
    failed = _job(context, step=3).model_copy(
        update={
            "status": "operational-failed",
            "process_id": None,
            "run_id": "pilot-exact-run",
            # Stage 3 continuation retains the verified foundation as run_root;
            # the requested Pilot run itself has not been published.
            "run_root": context.runs_root / "example/foundation",
            "run_manifest": None,
            "error": "ConfigurationError: backend not registered",
        }
    )
    controller.update(failed)
    failed.log_path.parent.mkdir(parents=True, exist_ok=True)
    failed.log_path.write_text("first failure\n", encoding="utf-8")
    captured: dict[str, Any] = {}

    class Process:
        pid = 515151

    def fake_popen(command: list[str], **kwargs: Any) -> Process:
        captured["command"] = command
        captured.update(kwargs)
        return Process()

    monkeypatch.setattr("easydesign.orchestration.local_jobs.subprocess.Popen", fake_popen)

    retried = controller.retry_preflight_failure(failed.job_id)

    assert retried.job_id == failed.job_id
    assert retried.run_id == "pilot-exact-run"
    assert retried.status == "running"
    assert retried.process_id == 515151
    assert retried.error is None
    assert "retrying exact preflight-failed worker" in failed.log_path.read_text()
    stored_revisions = sorted(
        controller.path(failed.job_id)
        .with_name(f"{failed.job_id}.json.revisions")
        .glob("revision-*.json")
    )
    assert stored_revisions
    assert any(
        "operational-failed" in path.read_text()
        for path in (controller.path(failed.job_id), *stored_revisions)
    )
    assert captured["start_new_session"] is True


def test_ctrl_c_detaches_observer_without_stopping_worker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    context = _workspace(tmp_path, monkeypatch)
    job = _job(context, process_id=777)

    class Controller:
        def wait(self, _job_id: str) -> LocalStepJob:
            raise KeyboardInterrupt

        def load(self, _job_id: str) -> LocalStepJob:
            return job

    observed = wait_or_detach(Controller(), job, detach=False)  # type: ignore[arg-type]

    assert observed.status == "detached"
    assert observed.process_id == 777
    assert job.status == "running"


def test_drain_only_writes_safe_checkpoint_request(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    context = _workspace(tmp_path, monkeypatch)
    controller = LocalStepJobController(context)
    controller.update(_job(context))

    drained = controller.request_drain("job-semanticlocal01")

    assert drained.status == "drain-requested"
    assert drained.drain_path.is_file()


def test_pilot_job_accepts_drain_before_internal_generation_starts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    context = _workspace(tmp_path, monkeypatch)
    controller = LocalStepJobController(context)
    controller.update(_job(context, step=3))

    drained = controller.request_drain("job-semanticlocal01")

    assert drained.status == "drain-requested"
    assert drained.drain_path.is_file()


def test_scientific_and_operational_failures_remain_distinct() -> None:
    assert _failure_status(TargetInputError("strict scientific gate")) == "scientific-failed"
    assert _failure_status(OSError("disk unavailable")) == "operational-failed"


def test_resume_continues_from_generation_through_frozen_pilot_boundary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    outcomes = iter(
        (
            SimpleNamespace(status="succeeded", identity="stage04"),
            SimpleNamespace(status="succeeded", identity="stage05"),
        )
    )
    manifests = iter((tmp_path / "v4.json", tmp_path / "v5.json"))
    statuses = iter((ExecutionStatus.RUNNING, ExecutionStatus.SUCCEEDED))
    monkeypatch.setattr("easydesign.local_worker.resume_pipeline", lambda _root: next(outcomes))
    monkeypatch.setattr(
        "easydesign.local_worker._manifest_identity",
        lambda _root: ("pilot-run", next(manifests)),
    )
    monkeypatch.setattr(
        "easydesign.local_worker.load_model",
        lambda _path, _model: SimpleNamespace(status=next(statuses)),
    )

    outcome = _resume_until_boundary(tmp_path / "run")

    assert outcome.identity == "stage05"
