"""Persistent repository-local setup jobs for the local runtime CLI.

Long scientific backend installations must survive the invoking terminal
closing.  The launcher therefore starts a session-detached worker and
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
    SetupProgressUpdate,
    SetupSummary,
    validate_pip_index_url,
)
from .source_policy import SourcePolicy


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
    source_policy: SourcePolicy = "official"
    pip_index_url: str | None = None
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


class SetupJobProgress(BaseModel):
    """Atomically replaceable operational projection for one setup worker."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["0.1"] = "0.1"
    job_id: str
    phase: str
    message: str
    completed_steps: int
    total_steps: int
    current_item: str | None = None
    current_step_fraction: float = 0.0
    bytes_completed: int | None = None
    bytes_total: int | None = None
    bytes_per_second: float | None = None
    eta_seconds: float | None = None
    updated_at: datetime


class SetupProgressRecorder:
    """Persist throttled progress without mutating request or result evidence."""

    def __init__(
        self,
        context: WorkspaceContext,
        request: SetupJobRequest,
    ) -> None:
        self._context = context
        self._request = request
        self._path = setup_job_root(context) / request.job_id / "progress.json"
        context.assert_write_path(self._path)
        self._byte_item: str | None = None
        self._byte_started_at: datetime | None = None
        self._byte_started_value = 0
        self._last_update: SetupProgressUpdate | None = None

    def __call__(self, update: SetupProgressUpdate) -> None:
        self._last_update = update
        speed: float | None = None
        eta: float | None = None
        if update.bytes_completed is not None:
            if self._byte_item != update.current_item:
                self._byte_item = update.current_item
                self._byte_started_at = update.recorded_at
                self._byte_started_value = update.bytes_completed
            elif self._byte_started_at is not None:
                elapsed = (update.recorded_at - self._byte_started_at).total_seconds()
                transferred = update.bytes_completed - self._byte_started_value
                if elapsed > 0 and transferred >= 0:
                    speed = transferred / elapsed
                    if (
                        speed > 0
                        and update.bytes_total is not None
                        and update.bytes_total >= update.bytes_completed
                    ):
                        eta = (update.bytes_total - update.bytes_completed) / speed
        progress = SetupJobProgress(
            job_id=self._request.job_id,
            phase=update.phase,
            message=update.message,
            completed_steps=update.completed_steps,
            total_steps=update.total_steps,
            current_item=update.current_item,
            current_step_fraction=update.current_step_fraction,
            bytes_completed=update.bytes_completed,
            bytes_total=update.bytes_total,
            bytes_per_second=speed,
            eta_seconds=eta,
            updated_at=update.recorded_at,
        )
        temporary = self._path.with_name(f"progress-{uuid4().hex}.tmp")
        with temporary.open("x", encoding="utf-8") as handle:
            handle.write(progress.model_dump_json(indent=2) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, self._path)

    def fail(self, message: str) -> None:
        previous = self._last_update
        self(
            SetupProgressUpdate(
                phase="failed",
                message=message,
                completed_steps=0 if previous is None else previous.completed_steps,
                total_steps=1 if previous is None else previous.total_steps,
                current_item=(
                    self._request.component
                    if previous is None
                    else previous.current_item
                ),
                current_step_fraction=(
                    0.0 if previous is None else previous.current_step_fraction
                ),
                bytes_completed=(
                    None if previous is None else previous.bytes_completed
                ),
                bytes_total=None if previous is None else previous.bytes_total,
                recorded_at=datetime.now(tz=UTC),
            )
        )


class SetupJobProjection(BaseModel):
    """Read-only status returned to the local runtime CLI."""

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
    source_policy: SourcePolicy = "official"
    pip_index_url: str | None = None
    stdout_relative_path: Path
    stderr_relative_path: Path
    progress: SetupJobProgress | None = None
    error: str | None = None


def setup_job_root(context: WorkspaceContext) -> Path:
    root = context.runtime_root / "state" / "setup-jobs"
    context.assert_write_path(root)
    return root


def launch_setup_job(
    context: WorkspaceContext,
    *,
    component: str,
    accepted_license_ids: set[str],
    conda_executable: Path | None = None,
    pip_index_url: str | None = None,
    source_policy: SourcePolicy = "auto",
) -> SetupJobProjection:
    """Launch one detached worker without shell or global configuration writes."""

    if component not in SETUP_COMPONENT_IDS:
        raise ConfigurationError(f"未知安装组件: {component}")
    active = next(
        (job for job in list_setup_jobs(context) if job.status == "running"),
        None,
    )
    if active is not None:
        raise ConfigurationError(
            f"已有运行中的安装任务 {active.job_id} ({active.component})；"
            "拒绝并发启动。请运行 "
            f"easydesign runtime jobs --job-id {active.job_id} --watch"
        )
    context.ensure_layout()
    selected_pip_index = (
        None if pip_index_url is None else validate_pip_index_url(pip_index_url)
    )
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
        minimal=False,
        component=component,
        accepted_license_ids=tuple(sorted(accepted_license_ids)),
        conda_executable=conda_executable,
        source_policy=source_policy,
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
            env=context.subprocess_environment(),
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
        minimal=False,
        component=component,
        accepted_license_ids=request.accepted_license_ids,
        source_policy=request.source_policy,
        pip_index_url=request.pip_index_url,
        stdout_relative_path=request.stdout_relative_path,
        stderr_relative_path=request.stderr_relative_path,
        progress=None,
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
            source_policy="official",
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
    progress_path = job_directory / "progress.json"
    progress = (
        load_model(progress_path, SetupJobProgress)
        if progress_path.is_file()
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
        source_policy=request.source_policy,
        pip_index_url=request.pip_index_url,
        stdout_relative_path=request.stdout_relative_path,
        stderr_relative_path=request.stderr_relative_path,
        progress=progress,
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
