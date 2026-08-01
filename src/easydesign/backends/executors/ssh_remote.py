"""Explicit SSH transport for staging and launching a whole EasyDesign run."""

from __future__ import annotations

import json
import shlex
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Self
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from easydesign.core import BackendContractError, ProgressSnapshot
from easydesign.core.artifacts import ID_PATTERN
from easydesign.workspace_context import WorkspaceContext


class SshRemoteProbe(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    probed_at: datetime
    hostname: str = Field(min_length=1)
    easydesign_version: str = Field(min_length=1)
    gpu_count: int = Field(ge=0)
    filesystem_total_bytes: int = Field(ge=1)
    filesystem_available_bytes: int = Field(ge=0)


class SshRemoteSubmission(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: str = "0.1"
    executor_id: str = Field(pattern=ID_PATTERN)
    job_id: str = Field(pattern=ID_PATTERN)
    submitted_at: datetime
    unit_name: str = Field(pattern=ID_PATTERN)
    remote_job_root: str = Field(min_length=1)
    remote_source_run: str | None = Field(default=None, min_length=1)
    remote_config: str = Field(min_length=1)
    remote_run_root: str = Field(min_length=1)
    project_id: str = Field(pattern=ID_PATTERN)
    run_id: str = Field(pattern=ID_PATTERN)
    source_run_manifest_sha256: str | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{64}$",
    )
    config_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    launcher_output: str = Field(min_length=1, max_length=4096)
    status: str = "submitted"


class SshRemoteJobRecord(BaseModel):
    """控制端保存的远程任务定位记录；科学事实仍由远端 run 发布。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: str = "0.2"
    submission: SshRemoteSubmission
    active_unit_name: str = Field(pattern=ID_PATTERN)
    unit_history: tuple[str, ...]
    resume_count: int = Field(default=0, ge=0)
    updated_at: datetime

    @model_validator(mode="after")
    def validate_units(self) -> Self:
        if not self.unit_history or self.active_unit_name != self.unit_history[-1]:
            raise ValueError("远程任务 active unit 必须是 unit_history 末项")
        if len(self.unit_history) != self.resume_count + 1:
            raise ValueError("远程任务 unit_history 与 resume_count 不一致")
        return self


class SshRemoteStatus(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    checked_at: datetime
    unit_name: str
    active_state: str
    sub_state: str
    exec_main_status: int | None = None


class SshRemoteObservation(BaseModel):
    """远端 worker 与 run 进度的一致快照。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    executor_id: str = Field(pattern=ID_PATTERN)
    job_id: str = Field(pattern=ID_PATTERN)
    checked_at: datetime
    remote_run_root: str
    worker: SshRemoteStatus
    progress: ProgressSnapshot | None = None
    progress_error: str | None = None


class SshRemoteSyncReport(BaseModel):
    """一次 manifest 驱动的控制端只读镜像同步证据。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: str = "0.1"
    executor_id: str = Field(pattern=ID_PATTERN)
    job_id: str = Field(pattern=ID_PATTERN)
    mode: str = Field(pattern=r"^(metadata|review|complete)$")
    synced_at: datetime
    destination: Path
    remote_run_root: str
    file_count: int = Field(ge=0)
    size_bytes: int = Field(ge=0)
    run_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    completed_artifact_closure: bool


class SshRemoteFileIdentity(BaseModel):
    """Checksum and size observed in place without downloading a remote artifact."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    remote_path: str = Field(min_length=1)
    size_bytes: int = Field(ge=1)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


@dataclass(frozen=True, slots=True)
class SshRemoteConnection:
    executor_id: str
    host: str
    user: str
    port: int
    identity_file: Path
    known_hosts_file: Path
    ssh_executable: Path
    rsync_executable: Path
    remote_work_root: Path
    remote_runs_root: Path
    remote_easydesign_executable: Path
    remote_profile: Path
    connect_timeout_seconds: int


@dataclass(frozen=True, slots=True)
class SshRemoteExecutor:
    connection: SshRemoteConnection
    command_timeout_seconds: float = 120.0

    @property
    def destination(self) -> str:
        return f"{self.connection.user}@{self.connection.host}"

    def _ssh_prefix(self) -> tuple[str, ...]:
        connection = self.connection
        return (
            str(connection.ssh_executable),
            "-i",
            str(connection.identity_file),
            "-p",
            str(connection.port),
            "-o",
            "BatchMode=yes",
            "-o",
            "IdentitiesOnly=yes",
            "-o",
            "StrictHostKeyChecking=yes",
            "-o",
            f"UserKnownHostsFile={connection.known_hosts_file}",
            "-o",
            f"ConnectTimeout={connection.connect_timeout_seconds}",
            "-o",
            "ControlMaster=auto",
            "-o",
            "ControlPersist=120",
            "-o",
            f"ControlPath=/tmp/easydesign-ssh-{connection.executor_id}-%C",
            self.destination,
        )

    def _run_remote(
        self,
        argv: tuple[str, ...],
        *,
        timeout_seconds: float | None = None,
    ) -> subprocess.CompletedProcess[str]:
        command = (*self._ssh_prefix(), shlex.join(argv))
        try:
            completed = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
                timeout=timeout_seconds or self.command_timeout_seconds,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise BackendContractError(f"SSH remote command 失败: {error}") from error
        if completed.returncode != 0:
            detail = (completed.stderr.strip() or completed.stdout.strip())[:4096]
            raise BackendContractError(
                f"SSH remote command exit={completed.returncode}: {detail}"
            )
        return completed

    @staticmethod
    def _safe_relative_path(value: str) -> str:
        relative = Path(value)
        if value in {"", "."} or relative.is_absolute() or ".." in relative.parts:
            raise BackendContractError(f"SSH sync 路径不是安全相对路径: {value}")
        return relative.as_posix()

    def read_text(self, remote_path: Path) -> str:
        if not remote_path.is_absolute():
            raise BackendContractError("SSH remote read 必须使用绝对路径")
        return self._run_remote(("cat", str(remote_path))).stdout

    def is_file(self, remote_path: Path) -> bool:
        if not remote_path.is_absolute():
            raise BackendContractError("SSH remote file probe 必须使用绝对路径")
        command = (*self._ssh_prefix(), shlex.join(("test", "-f", str(remote_path))))
        try:
            completed = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
                timeout=self.command_timeout_seconds,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise BackendContractError(f"SSH remote file probe 失败: {error}") from error
        if completed.returncode not in {0, 1}:
            detail = (completed.stderr.strip() or completed.stdout.strip())[:4096]
            raise BackendContractError(
                f"SSH remote file probe exit={completed.returncode}: {detail}"
            )
        return completed.returncode == 0

    def read_versioned_pointer(self, remote_path: Path) -> tuple[str, tuple[Path, ...]]:
        """Read the newest append-only pointer revision and return its evidence paths."""

        if not remote_path.is_absolute():
            raise BackendContractError("SSH remote pointer 必须使用绝对路径")
        evidence = [remote_path]
        revision_root = remote_path.with_name(f"{remote_path.name}.revisions")
        for revision in range(1, 100_001):
            candidate = revision_root / f"revision-{revision:06d}.txt"
            if not self.is_file(candidate):
                break
            evidence.append(candidate)
        else:  # pragma: no cover - defensive bound for corrupt remote state
            raise BackendContractError("SSH remote pointer revision 数量异常")
        selected = evidence[-1]
        lines = [
            line.strip()
            for line in self.read_text(selected).splitlines()
            if line.strip()
        ]
        if not lines:
            raise BackendContractError(f"SSH remote pointer 没有有效 revision: {selected}")
        return lines[-1], tuple(evidence)

    def file_identity(self, remote_path: Path) -> SshRemoteFileIdentity:
        """Read an immutable file identity in place; never copies or modifies it."""

        if not remote_path.is_absolute():
            raise BackendContractError("SSH remote identity 必须使用绝对路径")
        digest_columns = self._run_remote(
            ("sha256sum", "--", str(remote_path))
        ).stdout.split()
        if len(digest_columns) < 2:
            raise BackendContractError("SSH remote sha256sum 输出不完整")
        size_text = self._run_remote(
            ("stat", "--format=%s", "--", str(remote_path))
        ).stdout.strip()
        try:
            size_bytes = int(size_text)
        except ValueError as error:
            raise BackendContractError("SSH remote stat 输出不是整数") from error
        return SshRemoteFileIdentity(
            remote_path=remote_path.as_posix(),
            size_bytes=size_bytes,
            sha256=digest_columns[0],
        )

    def _rsync(
        self,
        source: Path,
        remote_destination: Path,
        *,
        destination_is_directory: bool,
    ) -> None:
        connection = self.connection
        ssh_transport = shlex.join(self._ssh_prefix()[:-1])
        source_argument = str(source)
        if source.is_dir():
            source_argument += "/"
        remote_text = remote_destination.as_posix()
        if destination_is_directory:
            remote_text += "/"
        destination = f"{self.destination}:{remote_text}"
        command = (
            str(connection.rsync_executable),
            "--archive",
            "--partial",
            "--protect-args",
            "--rsh",
            ssh_transport,
            source_argument,
            destination,
        )
        try:
            completed = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
                timeout=86_400,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise BackendContractError(f"SSH rsync staging 失败: {error}") from error
        if completed.returncode != 0:
            detail = (completed.stderr.strip() or completed.stdout.strip())[:4096]
            raise BackendContractError(
                f"SSH rsync staging exit={completed.returncode}: {detail}"
            )

    def push_files(
        self,
        *,
        local_root: Path,
        relative_paths: tuple[str, ...],
        remote_root: Path,
    ) -> None:
        """Push an explicit immutable file list without scanning or deleting remotely."""

        source_root = local_root.expanduser().resolve()
        if not source_root.is_dir():
            raise BackendContractError(f"SSH staging source 不存在: {source_root}")
        if not remote_root.is_absolute():
            raise BackendContractError("SSH staging remote root 必须是绝对路径")
        selected = tuple(
            dict.fromkeys(self._safe_relative_path(value) for value in relative_paths)
        )
        if not selected:
            raise BackendContractError("SSH staging 文件清单不能为空")
        for relative in selected:
            source = (source_root / relative).resolve()
            if not source.is_relative_to(source_root) or not source.is_file():
                raise BackendContractError(f"SSH staging 本地文件不存在: {relative}")
        context = WorkspaceContext.discover()
        context.ensure_layout()
        files_from = (
            context.runtime_root
            / "tmp"
            / f"easydesign-remote-push-{uuid4().hex}.txt"
        )
        context.assert_write_path(files_from)
        with files_from.open("x", encoding="utf-8") as handle:
            handle.write("\n".join(selected) + "\n")
        connection = self.connection
        ssh_transport = shlex.join(self._ssh_prefix()[:-1])
        self._run_remote(("mkdir", "-p", str(remote_root)))
        command = (
            str(connection.rsync_executable),
            "--archive",
            "--partial",
            "--protect-args",
            "--files-from",
            str(files_from),
            "--rsh",
            ssh_transport,
            f"{source_root.as_posix().rstrip('/')}/",
            f"{self.destination}:{remote_root.as_posix().rstrip('/')}/",
        )
        try:
            completed = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
                timeout=86_400,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise BackendContractError(f"SSH manifest staging 失败: {error}") from error
        if completed.returncode != 0:
            detail = (completed.stderr.strip() or completed.stdout.strip())[:4096]
            raise BackendContractError(
                f"SSH manifest staging exit={completed.returncode}: {detail}"
            )

    def push_file(self, *, source: Path, remote_path: Path) -> None:
        """Push one explicitly selected file to a new remote location."""

        selected = source.expanduser().resolve()
        if not selected.is_file() or not remote_path.is_absolute():
            raise BackendContractError("SSH single-file staging 路径无效")
        self._run_remote(("mkdir", "-p", str(remote_path.parent)))
        self._rsync(selected, remote_path, destination_is_directory=False)

    def managed_worker_json(
        self,
        *arguments: str,
        timeout_seconds: float | None = None,
    ) -> dict[str, object]:
        """Invoke only the fixed managed-worker CLI and parse its JSON response."""

        completed = self._run_remote(
            (
                str(self.connection.remote_easydesign_executable),
                "managed-worker",
                *arguments,
                "--config",
                str(self.connection.remote_work_root / "config" / "worker.yaml"),
                "--json",
            ),
            timeout_seconds=timeout_seconds,
        )
        try:
            payload = json.loads(completed.stdout)
        except json.JSONDecodeError as error:
            raise BackendContractError("managed worker 返回了无效 JSON") from error
        if not isinstance(payload, dict):
            raise BackendContractError("managed worker 返回值必须是 object")
        return payload

    def probe(self) -> SshRemoteProbe:
        hostname = self._run_remote(("hostname",)).stdout.strip()
        version = self._run_remote(
            (str(self.connection.remote_easydesign_executable), "--version")
        ).stdout.strip()
        gpu_lines = self._run_remote(
            (
                "nvidia-smi",
                "--query-gpu=index",
                "--format=csv,noheader,nounits",
            )
        ).stdout.splitlines()
        disk = self._run_remote(
            (
                "df",
                "-B1",
                "--output=size,avail",
                str(self.connection.remote_runs_root),
            )
        ).stdout.splitlines()
        if len(disk) < 2:
            raise BackendContractError("SSH remote df 输出不完整")
        columns = disk[-1].split()
        if len(columns) != 2:
            raise BackendContractError("SSH remote df 输出列数不符合契约")
        return SshRemoteProbe(
            probed_at=datetime.now(UTC),
            hostname=hostname,
            easydesign_version=version,
            gpu_count=len([line for line in gpu_lines if line.strip()]),
            filesystem_total_bytes=int(columns[0]),
            filesystem_available_bytes=int(columns[1]),
        )

    def submit(
        self,
        *,
        job_id: str,
        project_id: str,
        run_id: str,
        source_run: Path,
        source_run_manifest_sha256: str,
        config_path: Path,
        config_sha256: str,
    ) -> SshRemoteSubmission:
        connection = self.connection
        job_root = connection.remote_work_root / "jobs" / job_id
        source_destination = job_root / "source-run"
        input_destination = job_root / "input"
        remote_config = input_destination / "easydesign.yaml"
        remote_run = connection.remote_runs_root / project_id / run_id
        unit_name = f"easydesign-{job_id}"
        self._run_remote(
            (
                "test",
                "!",
                "-e",
                str(job_root),
            )
        )
        self._run_remote(
            (
                "mkdir",
                "-p",
                str(source_destination),
                str(input_destination),
                str(connection.remote_runs_root),
            )
        )
        self._rsync(
            source_run,
            source_destination,
            destination_is_directory=True,
        )
        self._rsync(
            config_path,
            remote_config,
            destination_is_directory=False,
        )
        command = (
            "systemd-run",
            f"--unit={unit_name}",
            "--property=Type=exec",
            f"--working-directory={job_root}",
            f"--setenv=EASYDESIGN_REMOTE_EXECUTOR_ID={connection.executor_id}",
            "--setenv=PYTHONUNBUFFERED=1",
            str(connection.remote_easydesign_executable),
            "run",
            str(remote_config),
            "--profile",
            str(connection.remote_profile),
            "--runs-root",
            str(connection.remote_runs_root),
            "--run-id",
            run_id,
            "--from-run",
            str(source_destination),
            "--json",
        )
        launched = self._run_remote(command)
        return SshRemoteSubmission(
            executor_id=connection.executor_id,
            job_id=job_id,
            submitted_at=datetime.now(UTC),
            unit_name=unit_name,
            remote_job_root=str(job_root),
            remote_source_run=str(source_destination),
            remote_config=str(remote_config),
            remote_run_root=str(remote_run),
            project_id=project_id,
            run_id=run_id,
            source_run_manifest_sha256=source_run_manifest_sha256,
            config_sha256=config_sha256,
            launcher_output=launched.stdout.strip() or "systemd-run submitted",
        )

    def submit_project(
        self,
        *,
        job_id: str,
        project_id: str,
        run_id: str,
        project_root: Path,
        config_relative_path: Path,
        config_sha256: str,
    ) -> SshRemoteSubmission:
        """提交一个从 Stage 01 开始的新项目，并冻结其输入目录。"""

        connection = self.connection
        if config_relative_path.is_absolute() or ".." in config_relative_path.parts:
            raise BackendContractError("远程项目 config_relative_path 必须安全且相对")
        job_root = connection.remote_work_root / "jobs" / job_id
        input_destination = job_root / "input"
        remote_config = input_destination / config_relative_path
        remote_run = connection.remote_runs_root / project_id / run_id
        unit_name = f"easydesign-{job_id}"
        self._run_remote(("test", "!", "-e", str(job_root)))
        self._run_remote(
            (
                "mkdir",
                "-p",
                str(input_destination),
                str(connection.remote_runs_root),
            )
        )
        self._rsync(
            project_root,
            input_destination,
            destination_is_directory=True,
        )
        self._run_remote(
            (
                str(connection.remote_easydesign_executable),
                "config",
                "validate",
                str(remote_config),
                "--profile",
                str(connection.remote_profile),
                "--json",
            ),
            timeout_seconds=300,
        )
        self._run_remote(
            (
                str(connection.remote_easydesign_executable),
                "doctor",
                "--config",
                str(remote_config),
                "--profile",
                str(connection.remote_profile),
                "--json",
            ),
            timeout_seconds=900,
        )
        command = (
            "systemd-run",
            f"--unit={unit_name}",
            "--property=Type=exec",
            f"--working-directory={input_destination}",
            f"--setenv=EASYDESIGN_REMOTE_EXECUTOR_ID={connection.executor_id}",
            "--setenv=PYTHONUNBUFFERED=1",
            str(connection.remote_easydesign_executable),
            "run",
            str(remote_config),
            "--profile",
            str(connection.remote_profile),
            "--runs-root",
            str(connection.remote_runs_root),
            "--run-id",
            run_id,
            "--json",
        )
        launched = self._run_remote(command)
        return SshRemoteSubmission(
            executor_id=connection.executor_id,
            job_id=job_id,
            submitted_at=datetime.now(UTC),
            unit_name=unit_name,
            remote_job_root=str(job_root),
            remote_source_run=None,
            remote_config=str(remote_config),
            remote_run_root=str(remote_run),
            project_id=project_id,
            run_id=run_id,
            source_run_manifest_sha256=None,
            config_sha256=config_sha256,
            launcher_output=launched.stdout.strip() or "systemd-run submitted",
        )

    def progress(self, remote_run_root: Path) -> ProgressSnapshot:
        if not remote_run_root.is_absolute():
            raise BackendContractError("SSH remote run root 必须是绝对路径")
        completed = self._run_remote(
            (
                str(self.connection.remote_easydesign_executable),
                "runs",
                "watch",
                str(remote_run_root),
                "--once",
                "--json",
            )
        )
        try:
            return ProgressSnapshot.model_validate_json(completed.stdout)
        except ValueError as error:
            raise BackendContractError(f"SSH remote progress 无效: {error}") from error

    def resume(self, *, remote_run_root: Path, unit_name: str) -> str:
        if not remote_run_root.is_absolute():
            raise BackendContractError("SSH remote resume run root 必须是绝对路径")
        command = (
            "systemd-run",
            f"--unit={unit_name}",
            "--property=Type=exec",
            f"--working-directory={remote_run_root}",
            f"--setenv=EASYDESIGN_REMOTE_EXECUTOR_ID={self.connection.executor_id}",
            "--setenv=PYTHONUNBUFFERED=1",
            str(self.connection.remote_easydesign_executable),
            "runs",
            "resume",
            str(remote_run_root),
            "--profile",
            str(self.connection.remote_profile),
            "--json",
        )
        launched = self._run_remote(command)
        return launched.stdout.strip() or "systemd-run resume submitted"

    def pull_files(
        self,
        *,
        remote_root: Path,
        relative_paths: tuple[str, ...],
        destination: Path,
    ) -> None:
        """只拉取调用者提供的 manifest-derived 文件清单。"""

        if not remote_root.is_absolute():
            raise BackendContractError("SSH sync remote root 必须是绝对路径")
        selected = tuple(
            dict.fromkeys(self._safe_relative_path(value) for value in relative_paths)
        )
        if not selected:
            raise BackendContractError("SSH sync 文件清单不能为空")
        context = WorkspaceContext.discover()
        context.ensure_layout()
        destination = context.require_write_path(
            destination,
            purpose="SSH manifest 文件同步",
        )
        destination.mkdir(parents=True, exist_ok=True)
        connection = self.connection
        ssh_transport = shlex.join(self._ssh_prefix()[:-1])
        files_from = (
            context.runtime_root
            / "tmp"
            / f"easydesign-remote-files-{uuid4().hex}.txt"
        )
        context.assert_write_path(files_from)
        try:
            with files_from.open("x", encoding="utf-8") as handle:
                handle.write("\n".join(selected) + "\n")
            command = (
                str(connection.rsync_executable),
                "--archive",
                "--partial",
                "--protect-args",
                "--files-from",
                str(files_from),
                "--rsh",
                ssh_transport,
                f"{self.destination}:{remote_root.as_posix().rstrip('/')}/",
                f"{destination}/",
            )
            completed = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
                timeout=86_400,
            )
            if completed.returncode != 0:
                detail = (completed.stderr.strip() or completed.stdout.strip())[:4096]
                raise BackendContractError(
                    f"SSH rsync pull exit={completed.returncode}: {detail}"
                )
        except (OSError, subprocess.TimeoutExpired, BackendContractError) as error:
            if files_from.exists():
                context.quarantine(
                    files_from,
                    operation="ssh-files-from",
                    reason=f"SSH manifest 文件同步未完成: {error}",
                )
            if isinstance(error, BackendContractError):
                raise
            raise BackendContractError(f"SSH rsync pull 失败: {error}") from error

    def status(self, unit_name: str) -> SshRemoteStatus:
        completed = self._run_remote(
            (
                "systemctl",
                "show",
                unit_name,
                "--property=ActiveState",
                "--property=SubState",
                "--property=ExecMainStatus",
            )
        )
        values: dict[str, str] = {}
        for line in completed.stdout.splitlines():
            key, separator, value = line.partition("=")
            if separator:
                values[key] = value
        raw_status = values.get("ExecMainStatus", "")
        return SshRemoteStatus(
            checked_at=datetime.now(UTC),
            unit_name=unit_name,
            active_state=values.get("ActiveState", "unknown"),
            sub_state=values.get("SubState", "unknown"),
            exec_main_status=int(raw_status) if raw_status.isdigit() else None,
        )
