"""Explicit SSH transport for staging and launching a whole EasyDesign run."""

from __future__ import annotations

import shlex
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from easydesign.core import BackendContractError
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
    remote_source_run: str = Field(min_length=1)
    remote_config: str = Field(min_length=1)
    remote_run_root: str = Field(min_length=1)
    project_id: str = Field(pattern=ID_PATTERN)
    run_id: str = Field(pattern=ID_PATTERN)
    source_run_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    config_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    launcher_output: str = Field(min_length=1, max_length=4096)
    status: str = "submitted"


class SshRemoteStatus(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    checked_at: datetime
    unit_name: str
    active_state: str
    sub_state: str
    exec_main_status: int | None = None


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
