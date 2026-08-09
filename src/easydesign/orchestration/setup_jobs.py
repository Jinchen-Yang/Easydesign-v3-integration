"""Persistent repository-local setup jobs for the local runtime CLI.

Long scientific backend installations must survive an SSH terminal or browser
session closing.  The launcher therefore starts a session-detached worker and
records immutable request, process and result documents below ``runtime/``.
"""

from __future__ import annotations

import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, ValidationError

from easydesign.core import ConfigurationError, dump_model, load_model
from easydesign.workspace_context import WorkspaceContext

from .runtime_setup import (
    DEFAULT_PIP_INDEX_URL,
    SETUP_COMPONENT_IDS,
    SetupSummary,
    validate_pip_index_url,
)


class SetupJobRequest(BaseModel):
    """Immutable input consumed by one detached setup worker."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["0.1"] = "0.1"
    job_id: str
    worker_token: str
    minimal: bool
    component: str | None = None
    accepted_license_ids: tuple[str, ...] = ()
    conda_executable: Path | None = None
    pip_index_url: str = DEFAULT_PIP_INDEX_URL
    started_at: datetime
    stdout_relative_path: Path
    stderr_relative_path: Path


class SetupJobProcess(BaseModel):
    """Process identity published after a worker is successfully started."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["0.1"] = "0.1"
    job_id: str
    pid: int
    worker_token: str
    recorded_at: datetime


class LegacySetupJobRequest(BaseModel):
    """Read-only compatibility for setup jobs created before dev23."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["0.1"] = "0.1"
    job_id: str
    command: tuple[str, ...]
    minimal: bool
    component: str | None = None
    accepted_license_ids: tuple[str, ...] = ()
    pid: int
    started_at: datetime
    stdout: Path
    stderr: Path


class SetupJobResult(BaseModel):
    """Terminal result written by the worker exactly once."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["0.1"] = "0.1"
    job_id: str
    status: Literal["succeeded", "incomplete", "failed"]
    return_code: int
    completed_at: datetime
    summary: SetupSummary | None = None
    error: str | None = None


class SetupJobProjection(BaseModel):
    """Read-only status returned to the CLI and local workbench."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["0.1"] = "0.1"
    job_id: str
    status: Literal["running", "succeeded", "incomplete", "failed", "interrupted"]
    pid: int | None = None
    started_at: datetime
    completed_at: datetime | None = None
    minimal: bool
    component: str | None = None
    accepted_license_ids: tuple[str, ...] = ()
    return_code: int | None = None
    pip_index_url: str = DEFAULT_PIP_INDEX_URL
    stdout_relative_path: Path
    stderr_relative_path: Path
    error: str | None = None


def setup_job_root(context: WorkspaceContext) -> Path:
    root = context.runtime_root / "state" / "setup-jobs"
    context.assert_write_path(root)
    return root


def launch_setup_job(
    context: WorkspaceContext,
    *,
    minimal: bool,
    component: str | None,
    accepted_license_ids: set[str],
    conda_executable: Path | None = None,
    pip_index_url: str = DEFAULT_PIP_INDEX_URL,
) -> SetupJobProjection:
    """Launch one detached worker without shell or global configuration writes."""

    if minimal and component is not None:
        raise ConfigurationError("--minimal 与 --component 不能同时使用")
    if component is not None and component not in SETUP_COMPONENT_IDS:
        raise ConfigurationError(f"未知安装组件: {component}")
    context.ensure_layout()
    selected_pip_index = validate_pip_index_url(pip_index_url)
    root = setup_job_root(context)
    root.mkdir(parents=True, exist_ok=True)
    now = datetime.now(tz=UTC)
    job_id = f"setup-{now.strftime('%Y%m%dT%H%M%SZ')}-{uuid4().hex[:10]}"
    worker_token = uuid4().hex
    job_directory = root / job_id
    context.assert_write_path(job_directory)
    job_directory.mkdir(exist_ok=False)
    logs = context.runtime_root / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    stdout_path = logs / f"{job_id}.stdout.log"
    stderr_path = logs / f"{job_id}.stderr.log"
    request = SetupJobRequest(
        job_id=job_id,
        worker_token=worker_token,
        minimal=minimal,
        component=component,
        accepted_license_ids=tuple(sorted(accepted_license_ids)),
        conda_executable=conda_executable,
        pip_index_url=selected_pip_index,
        started_at=now,
        stdout_relative_path=stdout_path.relative_to(context.root),
        stderr_relative_path=stderr_path.relative_to(context.root),
    )
    request_path = dump_model(request, job_directory / "request.json")
    command = (
        sys.executable,
        "-m",
        "easydesign.setup_worker",
        "--workspace",
        str(context.root),
        "--request",
        str(request_path),
        "--worker-token",
        worker_token,
    )
    with (
        stdout_path.open("xb") as stdout_handle,
        stderr_path.open("xb") as stderr_handle,
    ):
        process = subprocess.Popen(
            command,
            cwd=context.root,
            env={**os.environ, **context.child_environment()},
            stdin=subprocess.DEVNULL,
            stdout=stdout_handle,
            stderr=stderr_handle,
            shell=False,
            start_new_session=True,
        )
    process_record = SetupJobProcess(
        job_id=job_id,
        pid=process.pid,
        worker_token=worker_token,
        recorded_at=datetime.now(tz=UTC),
    )
    dump_model(process_record, job_directory / "process.json")
    return SetupJobProjection(
        job_id=job_id,
        status="running",
        pid=process.pid,
        started_at=now,
        minimal=minimal,
        component=component,
        accepted_license_ids=request.accepted_license_ids,
        pip_index_url=request.pip_index_url,
        stdout_relative_path=request.stdout_relative_path,
        stderr_relative_path=request.stderr_relative_path,
    )


def list_setup_jobs(context: WorkspaceContext) -> tuple[SetupJobProjection, ...]:
    """Read all immutable setup job records without changing workspace state."""

    root = setup_job_root(context)
    if not root.is_dir():
        return ()
    jobs = [
        _project_setup_job(context, job_directory)
        for job_directory in sorted(root.glob("setup-*"), reverse=True)
        if (job_directory / "request.json").is_file()
    ]
    return tuple(jobs)


def read_setup_job(context: WorkspaceContext, job_id: str) -> SetupJobProjection:
    if "/" in job_id or "\\" in job_id or not job_id.startswith("setup-"):
        raise ConfigurationError("Setup job ID 格式无效")
    job_directory = setup_job_root(context) / job_id
    try:
        job_directory.resolve().relative_to(setup_job_root(context).resolve())
    except ValueError as error:
        raise ConfigurationError("Setup job ID 逃出状态目录") from error
    if not (job_directory / "request.json").is_file():
        raise ConfigurationError(f"Setup job 不存在: {job_id}")
    return _project_setup_job(context, job_directory)


def _project_setup_job(
    context: WorkspaceContext,
    job_directory: Path,
) -> SetupJobProjection:
    request_path = job_directory / "request.json"
    request_text = request_path.read_text(encoding="utf-8")
    legacy_process: SetupJobProcess | None = None
    try:
        request = SetupJobRequest.model_validate_json(request_text)
    except ValidationError:
        legacy = LegacySetupJobRequest.model_validate_json(request_text)
        request = SetupJobRequest(
            job_id=legacy.job_id,
            worker_token="legacy-unavailable",
            minimal=legacy.minimal,
            component=legacy.component,
            accepted_license_ids=legacy.accepted_license_ids,
            pip_index_url=DEFAULT_PIP_INDEX_URL,
            started_at=legacy.started_at,
            stdout_relative_path=legacy.stdout,
            stderr_relative_path=legacy.stderr,
        )
        legacy_process = SetupJobProcess(
            job_id=legacy.job_id,
            pid=legacy.pid,
            worker_token="legacy-unavailable",
            recorded_at=legacy.started_at,
        )
    process_path = job_directory / "process.json"
    result_path = job_directory / "result.json"
    process = (
        load_model(process_path, SetupJobProcess)
        if process_path.is_file()
        else legacy_process
    )
    result = (
        load_model(result_path, SetupJobResult)
        if result_path.is_file()
        else None
    )
    status: Literal[
        "running",
        "succeeded",
        "incomplete",
        "failed",
        "interrupted",
    ]
    if result is not None:
        status = result.status
    elif process is not None and _worker_is_alive(process, request):
        status = "running"
    else:
        status = "interrupted"
    return SetupJobProjection(
        job_id=request.job_id,
        status=status,
        pid=None if process is None else process.pid,
        started_at=request.started_at,
        completed_at=None if result is None else result.completed_at,
        minimal=request.minimal,
        component=request.component,
        accepted_license_ids=request.accepted_license_ids,
        return_code=None if result is None else result.return_code,
        pip_index_url=request.pip_index_url,
        stdout_relative_path=request.stdout_relative_path,
        stderr_relative_path=request.stderr_relative_path,
        error=None if result is None else result.error,
    )


def _worker_is_alive(
    process: SetupJobProcess,
    request: SetupJobRequest,
) -> bool:
    try:
        os.kill(process.pid, 0)
    except OSError:
        return False
    command_line = Path(f"/proc/{process.pid}/cmdline")
    if command_line.is_file():
        try:
            values = command_line.read_bytes().replace(b"\0", b" ")
        except OSError:
            return False
        return (
            request.job_id.encode("utf-8") in values
            and process.worker_token.encode("utf-8") in values
        )
    return True
