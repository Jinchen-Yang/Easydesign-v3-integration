"""Explicit SSH transport for staging and launching a whole EasyDesign run."""

from __future__ import annotations

import shlex
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from easydesign.core import BackendContractError, ProgressSnapshot
from easydesign.core.artifacts import ID_PATTERN


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
    mode: str = Field(pattern=r"^(metadata|complete)$")
    synced_at: datetime
    destination: Path
    remote_run_root: str
    file_count: int = Field(ge=0)
    size_bytes: int = Field(ge=0)
    run_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    completed_artifact_closure: bool


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
            "StrictHostKeyChecking=yes",
            "-o",
            f"UserKnownHostsFile={connection.known_hosts_file}",
            "-o",
            f"ConnectTimeout={connection.connect_timeout_seconds}",
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
        destination.mkdir(parents=True, exist_ok=True)
        connection = self.connection
        ssh_transport = shlex.join(self._ssh_prefix()[:-1])
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            prefix="easydesign-remote-files-",
            suffix=".txt",
        ) as handle:
            handle.write("\n".join(selected) + "\n")
            handle.flush()
            command = (
                str(connection.rsync_executable),
                "--archive",
                "--partial",
                "--protect-args",
                "--files-from",
                handle.name,
                "--rsh",
                ssh_transport,
                f"{self.destination}:{remote_root.as_posix().rstrip('/')}/",
                f"{destination}/",
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
                raise BackendContractError(f"SSH rsync pull 失败: {error}") from error
        if completed.returncode != 0:
            detail = (completed.stderr.strip() or completed.stdout.strip())[:4096]
            raise BackendContractError(
                f"SSH rsync pull exit={completed.returncode}: {detail}"
            )

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
