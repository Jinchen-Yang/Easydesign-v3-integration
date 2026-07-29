from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
import yaml

from easydesign.core import ConfigurationError, dump_model, load_model
from easydesign.orchestration import setup_jobs
from easydesign.orchestration.setup_jobs import (
    SetupJobProcess,
    SetupJobRequest,
    SetupJobResult,
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
    captured: dict[str, Any] = {}

    def fake_popen(command: tuple[str, ...], **kwargs: Any) -> _FakeProcess:
        captured["command"] = command
        captured.update(kwargs)
        return _FakeProcess()

    monkeypatch.setattr(setup_jobs.subprocess, "Popen", fake_popen)

    projection = launch_setup_job(
        context,
        minimal=False,
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
    assert "--worker-token" in captured["command"]
    job_root = context.runtime_root / "state" / "setup-jobs" / projection.job_id
    request = load_model(job_root / "request.json", SetupJobRequest)
    process = load_model(job_root / "process.json", SetupJobProcess)
    assert process.worker_token == request.worker_token
    assert request.stdout_relative_path.parts[:2] == ("runtime", "logs")
    assert request.stderr_relative_path.parts[:2] == ("runtime", "logs")


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
