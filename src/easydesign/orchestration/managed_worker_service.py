"""Suzhou2 managed-worker service and fixed job runner.

The queue document never contains a command.  A trusted service deployment
always launches the same ``easydesign managed-worker execute`` entry point and
passes only a validated job identity plus centrally assigned GPU devices.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

import yaml  # type: ignore[import-untyped]
from pydantic import BaseModel, ConfigDict, Field, model_validator

import easydesign
from easydesign.backends.executors.local_multi_gpu import NvidiaSmiProbe
from easydesign.backends.executors.managed_worker import (
    MANAGED_WORKER_ROOT,
    ManagedJobRevision,
    ManagedQueue,
    ManagedWorker,
    ManagedWorkerLayout,
    RemoteJobBundle,
)
from easydesign.core import BackendContractError, ConfigurationError, sha256_file

from .application import execute_pipeline
from .execution_targets import GpuLeaseStore, LocalCurrentHostTarget


class ManagedWorkerConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: str = "0.1"
    service_id: str = "suzhou2"
    managed_root: Path = MANAGED_WORKER_ROOT
    easydesign_executable: Path
    runtime_profile: Path
    nvidia_smi_executable: Path = Path("/usr/bin/nvidia-smi")
    expected_gpu_count: int = Field(default=8, ge=1)
    maximum_memory_used_mib: int = Field(default=2048, ge=0)
    maximum_utilization_percent: int = Field(default=10, ge=0, le=100)
    poll_seconds: float = Field(default=15.0, ge=1.0, le=300.0)

    @model_validator(mode="after")
    def absolute_paths(self) -> ManagedWorkerConfig:
        for value, label in (
            (self.managed_root, "managed_root"),
            (self.easydesign_executable, "easydesign_executable"),
            (self.runtime_profile, "runtime_profile"),
            (self.nvidia_smi_executable, "nvidia_smi_executable"),
        ):
            if not value.is_absolute():
                raise ValueError(f"{label} 必须是绝对路径")
        return self


class ManagedJobExecutionResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: str = "0.1"
    revision: int = Field(ge=1)
    job_id: str = Field(min_length=1)
    attempt: int = Field(ge=1)
    status: Literal["succeeded", "operational-failed"]
    started_at: datetime
    completed_at: datetime
    run_root: Path | None = None
    pipeline_status: str | None = None
    error_code: str | None = None
    error_message: str | None = Field(default=None, max_length=4096)


def load_managed_worker_config(path: Path) -> ManagedWorkerConfig:
    if not path.is_file():
        raise ConfigurationError(f"managed worker 配置不存在: {path}")
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ConfigurationError("managed worker 配置必须是 YAML object")
    return ManagedWorkerConfig.model_validate(payload)


def _write_new_text(path: Path, payload: str, *, mode: int = 0o644) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(payload)
        if not payload.endswith("\n"):
            handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())


def _result_paths(layout: ManagedWorkerLayout, job_id: str) -> tuple[Path, ...]:
    return tuple(
        sorted((layout.jobs / job_id / "execution-results").glob("revision-*.json"))
    )


def read_latest_execution_result(
    layout: ManagedWorkerLayout,
    job_id: str,
) -> ManagedJobExecutionResult | None:
    paths = _result_paths(layout, job_id)
    if not paths:
        return None
    return ManagedJobExecutionResult.model_validate_json(
        paths[-1].read_text(encoding="utf-8")
    )


def _publish_execution_result(
    layout: ManagedWorkerLayout,
    result: ManagedJobExecutionResult,
) -> Path:
    path = (
        layout.jobs
        / result.job_id
        / "execution-results"
        / f"revision-{result.revision:06d}.json"
    )
    _write_new_text(path, result.model_dump_json(indent=2))
    return path


def verify_managed_job_inputs(
    *,
    layout: ManagedWorkerLayout,
    bundle: RemoteJobBundle,
) -> Path:
    """Verify only the immutable input list declared by the controller."""

    input_root = (layout.jobs / bundle.job_id / "input").resolve()
    if not input_root.is_dir():
        raise BackendContractError(f"managed job input 目录不存在: {input_root}")
    for item in bundle.inputs:
        path = (input_root / item.relative_path).resolve()
        if not path.is_relative_to(input_root):
            raise BackendContractError("managed job input 路径逃逸")
        if not path.is_file():
            raise BackendContractError(
                f"managed job input 缺失: {item.relative_path}"
            )
        if path.stat().st_size != item.size_bytes or sha256_file(path) != item.sha256:
            raise BackendContractError(
                f"managed job input 完整性校验失败: {item.relative_path}"
            )
    return input_root


def resolve_managed_source_run(
    *,
    layout: ManagedWorkerLayout,
    bundle: RemoteJobBundle,
    input_root: Path,
) -> Path:
    """Resolve one immutable upstream without scanning or copying large runs."""

    if bundle.source_run_mode == "uploaded-closure":
        source_run = (input_root / "source-run").resolve()
        if not source_run.is_relative_to(input_root) or not source_run.is_dir():
            raise BackendContractError("managed job 缺少已上传的 source-run 闭包")
    else:
        assert bundle.managed_source_run is not None
        source_run = (layout.root / bundle.managed_source_run).resolve()
        if not source_run.is_relative_to(layout.runs.resolve()):
            raise BackendContractError("managed source run 逃逸受管 runs 边界")
        if not source_run.is_dir():
            raise BackendContractError("managed source run 不存在")
    pointer = source_run / "manifests" / "LATEST"
    if not pointer.is_file():
        raise BackendContractError("managed source run 缺少 manifests/LATEST")
    latest = pointer.read_text(encoding="utf-8").strip()
    latest_path = Path(latest)
    if (
        latest in {"", "."}
        or latest_path.is_absolute()
        or ".." in latest_path.parts
        or len(latest_path.parts) != 1
    ):
        raise BackendContractError("managed source run LATEST 内容不安全")
    manifest_path = source_run / "manifests" / latest
    if not manifest_path.is_file():
        raise BackendContractError("managed source run 最新 manifest 不存在")
    if sha256_file(manifest_path) != bundle.upstream_manifest_sha256:
        raise BackendContractError("managed source run 最新 manifest SHA-256 不匹配")
    return source_run


def execute_managed_job(
    *,
    job_id: str,
    config: ManagedWorkerConfig,
) -> ManagedJobExecutionResult:
    """Execute one validated job with the production orchestration API."""

    layout = ManagedWorkerLayout(config.managed_root)
    queue = ManagedQueue(layout)
    bundle = queue.bundle(job_id)
    current = queue.latest(job_id)
    attempt_text = os.environ.get("EASYDESIGN_MANAGED_ATTEMPT")
    attempt = current.attempt if attempt_text is None else int(attempt_text)
    if attempt < 1:
        raise BackendContractError("managed job 尚未被中央队列 claim")
    input_root = verify_managed_job_inputs(layout=layout, bundle=bundle)
    config_path = input_root / "easydesign.yaml"
    if not config_path.is_file():
        raise BackendContractError("managed job 缺少 config")
    source_run = resolve_managed_source_run(
        layout=layout,
        bundle=bundle,
        input_root=input_root,
    )
    started = datetime.now(UTC)
    result_paths = _result_paths(layout, job_id)
    revision = len(result_paths) + 1
    try:
        execution = execute_pipeline(
            config_path,
            profile_path=config.runtime_profile,
            runs_root=layout.runs,
            run_id=bundle.run_id,
            continue_from_run=source_run,
        )
        result = ManagedJobExecutionResult(
            revision=revision,
            job_id=job_id,
            attempt=attempt,
            status="succeeded",
            started_at=started,
            completed_at=datetime.now(UTC),
            run_root=execution.run_root,
            pipeline_status=execution.status,
        )
    except Exception as error:
        result = ManagedJobExecutionResult(
            revision=revision,
            job_id=job_id,
            attempt=attempt,
            status="operational-failed",
            started_at=started,
            completed_at=datetime.now(UTC),
            error_code="managed-pipeline-failed",
            error_message=str(error)[:4096] or type(error).__name__,
        )
        _publish_execution_result(layout, result)
        raise
    _publish_execution_result(layout, result)
    return result


class ManagedWorkerService:
    """One admission/reconciliation loop for the Suzhou2 central queue."""

    def __init__(self, config: ManagedWorkerConfig) -> None:
        self.config = config
        self.layout = ManagedWorkerLayout(config.managed_root)
        self.layout.ensure()
        self.queue = ManagedQueue(self.layout)
        self.worker = ManagedWorker(
            layout=self.layout,
            queue=self.queue,
            lease_store=GpuLeaseStore(
                lease_root=self.layout.runtime / "state" / "gpu-leases"
            ),
        )
        self.probe = NvidiaSmiProbe(executable=config.nvidia_smi_executable)

    @staticmethod
    def _pid_exists(pid: int) -> bool:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        return True

    def _release_job_leases(self, record: ManagedJobRevision) -> None:
        leases = self.worker.leases.active_for_job(
            record.job_id,
            devices=record.assigned_devices,
        )
        if leases:
            self.worker.leases.release(leases)

    def reconcile(self) -> tuple[ManagedJobRevision, ...]:
        updates: list[ManagedJobRevision] = []
        for record in self.queue.list_latest():
            if record.status == "admitting":
                # The service may have stopped after the append-only queue
                # reservation but before publishing a PID-backed running
                # revision.  No child can be trusted in this state, so record
                # a retryable operational failure and let the next admission
                # pass reserve it again.
                updates.append(
                    self.queue.transition(
                        record.job_id,
                        status="failed",
                        error_code="admission-interrupted",
                        error_message="worker 在 GPU 租约与子进程发布前中断，已转为可恢复重试",
                    )
                )
                continue
            if record.status not in {"running", "drain-requested"}:
                continue
            result = read_latest_execution_result(self.layout, record.job_id)
            if result is not None and result.attempt == record.attempt:
                self._release_job_leases(record)
                updates.append(
                    self.queue.transition(
                        record.job_id,
                        status=(
                            "succeeded"
                            if result.status == "succeeded"
                            else "failed"
                        ),
                        error_code=result.error_code,
                        error_message=result.error_message,
                    )
                )
                continue
            assert record.worker_pid is not None
            if not self._pid_exists(record.worker_pid):
                self._release_job_leases(record)
                updates.append(
                    self.queue.transition(
                        record.job_id,
                        status="failed",
                        error_code="worker-exited-without-result",
                        error_message="managed worker 子进程结束但没有终态执行记录",
                    )
                )
                continue
            leases = self.worker.leases.active_for_job(
                record.job_id,
                devices=record.assigned_devices,
            )
            if len(leases) != len(record.assigned_devices):
                raise BackendContractError("managed worker 运行中 GPU lease 不完整")
            leases = self.worker.leases.heartbeat(leases)
            updates.append(
                self.queue.heartbeat(
                    record.job_id,
                    worker_pid=record.worker_pid,
                    leases=leases,
                )
            )
        return tuple(updates)

    def _launch(self, bundle: RemoteJobBundle, devices: tuple[int, ...]) -> int:
        current = self.queue.latest(bundle.job_id)
        next_attempt = current.attempt + 1
        log_path = (
            self.layout.runtime
            / "logs"
            / bundle.job_id
            / f"attempt-{next_attempt:04d}.log"
        )
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_handle = log_path.open("xb")
        environment = os.environ.copy()
        environment.update(
            {
                "CUDA_VISIBLE_DEVICES": ",".join(str(item) for item in devices),
                "EASYDESIGN_ASSIGNED_GPU_DEVICES": ",".join(
                    str(item) for item in devices
                ),
                "EASYDESIGN_MANAGED_JOB_ID": bundle.job_id,
                "EASYDESIGN_MANAGED_ATTEMPT": str(next_attempt),
                "EASYDESIGN_UI_DRAIN_FILE": str(
                    self.layout.jobs / bundle.job_id / "control" / "drain.requested"
                ),
                "PYTHONUNBUFFERED": "1",
            }
        )
        try:
            process = subprocess.Popen(
                (
                    str(self.config.easydesign_executable),
                    "managed-worker",
                    "execute",
                    bundle.job_id,
                    "--config",
                    str(self.layout.root / "config" / "worker.yaml"),
                ),
                cwd=self.layout.jobs / bundle.job_id,
                env=environment,
                stdin=subprocess.DEVNULL,
                stdout=log_handle,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        finally:
            log_handle.close()
        return process.pid

    def run_once(self) -> ManagedJobRevision | None:
        self.reconcile()
        snapshots = self.probe.snapshots()
        inventory = self.worker.leases.inventory(
            snapshots,
            target=LocalCurrentHostTarget(maximum_devices=self.config.expected_gpu_count),
            max_memory_used_mib=self.config.maximum_memory_used_mib,
            max_utilization_percent=self.config.maximum_utilization_percent,
        )
        return self.worker.admit_one(
            eligible_devices=inventory.selected_devices,
            launcher=self._launch,
        )

    def run_forever(self) -> None:
        while True:
            self.run_once()
            time.sleep(self.config.poll_seconds)

    def probe_status(self) -> dict[str, object]:
        snapshots = self.probe.snapshots()
        usage = shutil.disk_usage(self.layout.root)
        rows = self.queue.list_latest()
        return {
            "schema_version": "0.1",
            "observed_at": datetime.now(UTC).isoformat(),
            "service_version": easydesign.__version__,
            "managed_root": str(self.layout.root),
            "gpu_count": len(snapshots),
            "queue_depth": sum(
                item.status in {"queued", "waiting-resource", "admitting", "failed"}
                and item.attempt < self.queue.bundle(item.job_id).maximum_attempts
                for item in rows
            ),
            "running_jobs": sum(
                item.status in {"running", "drain-requested"} for item in rows
            ),
            "filesystem_total_bytes": usage.total,
            "filesystem_available_bytes": usage.free,
        }


def write_managed_worker_bootstrap(
    *,
    config: ManagedWorkerConfig,
) -> tuple[Path, Path]:
    """Create new worker config and a systemd unit proposal without installing it."""

    layout = ManagedWorkerLayout(config.managed_root)
    layout.ensure()
    declaration = layout.root / "easydesign-workspace.yaml"
    if not declaration.exists():
        _write_new_text(
            declaration,
            'schema_version: "0.1"\nworkspace_id: suzhou2-managed-worker\n',
        )
    config_path = layout.root / "config" / "worker.yaml"
    if config_path.exists():
        existing = load_managed_worker_config(config_path)
        if existing != config:
            raise ConfigurationError("managed worker 配置已存在且内容不同，拒绝覆盖")
    else:
        _write_new_text(
            config_path,
            yaml.safe_dump(
                config.model_dump(mode="json"),
                allow_unicode=True,
                sort_keys=False,
            ),
            mode=0o600,
        )
    unit_path = layout.root / "service" / "easydesign-managed-worker.service"
    unit = "\n".join(
        (
            "[Unit]",
            "Description=EasyDesign Suzhou2 managed GPU worker",
            "After=network-online.target",
            "",
            "[Service]",
            "Type=simple",
            f"WorkingDirectory={layout.root}",
            f"ExecStart={config.easydesign_executable} managed-worker serve --config {config_path}",
            "Restart=on-failure",
            "RestartSec=5",
            "",
            "[Install]",
            "WantedBy=multi-user.target",
            "",
        )
    )
    if unit_path.exists():
        if unit_path.read_text(encoding="utf-8") != unit:
            raise ConfigurationError("systemd unit proposal 已存在且内容不同，拒绝覆盖")
    else:
        _write_new_text(unit_path, unit)
    return config_path, unit_path
