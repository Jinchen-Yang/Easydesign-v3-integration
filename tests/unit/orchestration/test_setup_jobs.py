from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
import yaml

from easydesign.core import ConfigurationError, dump_model, load_model
from easydesign.orchestration import setup_jobs
from easydesign.orchestration.runtime_setup import SetupProgressUpdate
from easydesign.orchestration.setup_jobs import (
    SetupJobProcess,
    SetupJobRequest,
    SetupJobResult,
    SetupProgressRecorder,
    launch_setup_job,
    list_setup_jobs,
    read_setup_job,
)
from easydesign.workspace_context import WorkspaceContext


def _workspace(tmp_path: Path) -> WorkspaceContext:
    (tmp_path / "easydesign-workspace.yaml").write_text(
        yaml.safe_dump(
            {
                "schema_version": "0.1",
                "workspace_id": "setup-job-test",
                "runtime_root": "runtime",
                "projects_root": "projects",
                "runs_root": "runs",
                "archives_root": "archives",
            }
        ),
        encoding="utf-8",
    )
    return WorkspaceContext.from_root(tmp_path)


class _FakeProcess:
    pid = 424242


def test_detached_setup_job_stays_inside_workspace_and_avoids_shell(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _workspace(tmp_path)
    monkeypatch.setenv("PYTHONPATH", "/outside/pythonpath")
    monkeypatch.setenv("PYTHONHOME", "/outside/pythonhome")
    monkeypatch.setenv("VIRTUAL_ENV", "/outside/venv")
    captured: dict[str, Any] = {}

    def fake_popen(command: tuple[str, ...], **kwargs: Any) -> _FakeProcess:
        captured["command"] = command
        captured.update(kwargs)
        return _FakeProcess()

    monkeypatch.setattr(setup_jobs.subprocess, "Popen", fake_popen)

    projection = launch_setup_job(
        context,
        component="boltzgen",
        accepted_license_ids={"boltzgen-source-a3149cf"},
        pip_index_url="https://pypi.tuna.tsinghua.edu.cn/simple",
    )

    assert projection.status == "running"
    assert projection.component == "boltzgen"
    assert projection.pip_index_url == "https://pypi.tuna.tsinghua.edu.cn/simple"
    assert captured["shell"] is False
    assert captured["start_new_session"] is True
    assert captured["stdin"] is setup_jobs.subprocess.DEVNULL
    assert captured["cwd"] == context.root
    assert captured["env"]["HOME"] == str(context.runtime_root / "home")
    assert captured["env"]["PIP_CACHE_DIR"] == str(context.runtime_root / "cache" / "pip")
    assert Path(captured["env"]["PYTHONPATH"]).is_relative_to(context.runtime_root)
    assert "/outside" not in captured["env"]["PYTHONPATH"]
    assert "PYTHONHOME" not in captured["env"]
    assert "VIRTUAL_ENV" not in captured["env"]
    assert "--worker-token" in captured["command"]
    job_root = context.runtime_root / "state" / "setup-jobs" / projection.job_id
    request = load_model(job_root / "request.json", SetupJobRequest)
    process = load_model(job_root / "process.json", SetupJobProcess)
    assert process.worker_token == request.worker_token
    assert request.stdout_relative_path.parts[:2] == ("runtime", "logs")
    assert request.stderr_relative_path.parts[:2] == ("runtime", "logs")


def test_all_component_launches_one_detached_worker(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _workspace(tmp_path)
    launches: list[tuple[str, ...]] = []

    def fake_popen(command: tuple[str, ...], **_kwargs: Any) -> _FakeProcess:
        launches.append(command)
        return _FakeProcess()

    monkeypatch.setattr(setup_jobs.subprocess, "Popen", fake_popen)

    projection = launch_setup_job(
        context,
        component="all",
        accepted_license_ids=set(),
    )

    assert projection.component == "all"
    assert len(launches) == 1
    request = load_model(
        context.runtime_root
        / "state"
        / "setup-jobs"
        / projection.job_id
        / "request.json",
        SetupJobRequest,
    )
    assert request.component == "all"


def test_launch_refuses_to_compete_with_running_setup_job(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _workspace(tmp_path)
    running = setup_jobs.SetupJobProjection(
        job_id="setup-running-fixture",
        status="running",
        pid=424242,
        started_at=datetime.now(tz=UTC),
        minimal=False,
        component="all",
        stdout_relative_path=Path("runtime/logs/running.stdout.log"),
        stderr_relative_path=Path("runtime/logs/running.stderr.log"),
    )
    monkeypatch.setattr(setup_jobs, "list_setup_jobs", lambda _context: (running,))

    with pytest.raises(ConfigurationError, match="拒绝并发启动"):
        launch_setup_job(
            context,
            component="pymol-pse",
            accepted_license_ids=set(),
        )


def test_terminal_result_survives_launcher_restart(
    tmp_path: Path,
) -> None:
    context = _workspace(tmp_path)
    now = datetime.now(tz=UTC)
    job_id = "setup-20260729T000000Z-fixture0001"
    job_root = context.runtime_root / "state" / "setup-jobs" / job_id
    job_root.mkdir(parents=True)
    dump_model(
        SetupJobRequest(
            job_id=job_id,
            worker_token="fixture-token",
            minimal=False,
            component="boltzgen",
            started_at=now,
            stdout_relative_path=Path("runtime/logs/setup.stdout.log"),
            stderr_relative_path=Path("runtime/logs/setup.stderr.log"),
        ),
        job_root / "request.json",
    )
    dump_model(
        SetupJobProcess(
            job_id=job_id,
            pid=999999,
            worker_token="fixture-token",
            recorded_at=now,
        ),
        job_root / "process.json",
    )
    dump_model(
        SetupJobResult(
            job_id=job_id,
            status="succeeded",
            return_code=0,
            completed_at=now,
        ),
        job_root / "result.json",
    )

    restored = WorkspaceContext.from_root(tmp_path)
    projection = read_setup_job(restored, job_id)

    assert projection.status == "succeeded"
    assert projection.return_code == 0
    assert list_setup_jobs(restored) == (projection,)


def test_progress_is_atomic_and_projects_rate_and_eta(tmp_path: Path) -> None:
    context = _workspace(tmp_path)
    context.ensure_layout()
    now = datetime.now(tz=UTC)
    job_id = "setup-20260810T000000Z-progress001"
    job_root = context.runtime_root / "state" / "setup-jobs" / job_id
    job_root.mkdir(parents=True)
    request = SetupJobRequest(
        job_id=job_id,
        worker_token="progress-token",
        minimal=False,
        component="boltzgen",
        started_at=now,
        stdout_relative_path=Path("runtime/logs/progress.stdout.log"),
        stderr_relative_path=Path("runtime/logs/progress.stderr.log"),
    )
    dump_model(request, job_root / "request.json")
    recorder = SetupProgressRecorder(context, request)
    recorder(
        SetupProgressUpdate(
            phase="asset",
            message="正在下载并校验资产",
            completed_steps=1,
            total_steps=4,
            current_item="fixture-model",
            bytes_completed=0,
            bytes_total=1000,
            recorded_at=now,
        )
    )
    recorder(
        SetupProgressUpdate(
            phase="asset",
            message="正在下载并校验资产",
            completed_steps=1,
            total_steps=4,
            current_item="fixture-model",
            current_step_fraction=0.5,
            bytes_completed=500,
            bytes_total=1000,
            recorded_at=now + timedelta(seconds=2),
        )
    )

    projection = read_setup_job(context, job_id)

    assert projection.progress is not None
    assert projection.progress.bytes_per_second == 250
    assert projection.progress.eta_seconds == 2
    assert projection.progress.current_step_fraction == 0.5
    assert (job_root / "progress.json").is_file()
    assert not tuple(job_root.glob("progress-*.tmp"))


def test_unknown_setup_job_id_is_rejected(tmp_path: Path) -> None:
    context = _workspace(tmp_path)

    with pytest.raises(ConfigurationError, match="格式无效"):
        read_setup_job(context, "../outside")


def test_legacy_ui_setup_request_remains_readable(tmp_path: Path) -> None:
    context = _workspace(tmp_path)
    job_id = "setup-20260728T000000Z-legacy0001"
    job_root = context.runtime_root / "state" / "setup-jobs" / job_id
    job_root.mkdir(parents=True)
    (job_root / "request.json").write_text(
        json.dumps(
            {
                "schema_version": "0.1",
                "job_id": job_id,
                "command": ["./easydesign", "setup", "--component", "pymol-pse"],
                "minimal": False,
                "component": "pymol-pse",
                "accepted_license_ids": [],
                "pid": 999999,
                "started_at": "2026-07-28T00:00:00Z",
                "stdout": "runtime/logs/legacy.stdout.log",
                "stderr": "runtime/logs/legacy.stderr.log",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    projection = read_setup_job(context, job_id)

    assert projection.status == "interrupted"
    assert projection.pid == 999999
    assert projection.stdout_relative_path == Path("runtime/logs/legacy.stdout.log")
