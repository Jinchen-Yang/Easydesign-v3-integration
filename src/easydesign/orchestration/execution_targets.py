"""Non-scientific execution placement and workspace-local GPU leases.

The scientific run configuration describes what to calculate.  These models
describe where that calculation is allowed to run.  Lease history is
append-only so a service restart can reconstruct ownership without deleting or
overwriting earlier evidence.
"""

from __future__ import annotations

import fcntl
import json
import os
import socket
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Annotated, Literal, Self
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, model_validator

from easydesign.backends.executors.local_multi_gpu import GpuResourceSnapshot
from easydesign.core import (
    BackendContractError,
    ConfigurationError,
    ManifestStateError,
)
from easydesign.core.artifacts import ID_PATTERN
from easydesign.workspace_context import WorkspaceContext


class LocalCurrentHostTarget(BaseModel):
    """Run on eligible GPUs visible to the current host."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    type: Literal["local-current-host"] = "local-current-host"
    maximum_devices: int | None = Field(default=None, ge=1)
    allowed_devices: tuple[int, ...] | None = None

    @model_validator(mode="after")
    def validate_devices(self) -> Self:
        if self.allowed_devices is not None:
            if not self.allowed_devices:
                raise ValueError("allowed_devices 不能是空列表")
            if any(item < 0 for item in self.allowed_devices):
                raise ValueError("allowed_devices 必须是非负 GPU 编号")
            if len(self.allowed_devices) != len(set(self.allowed_devices)):
                raise ValueError("allowed_devices 不能重复")
        return self


class ManagedSshTarget(BaseModel):
    """Submit to an explicitly paired managed SSH executor."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    type: Literal["managed-ssh"] = "managed-ssh"
    executor_id: str = Field(pattern=ID_PATTERN)


ExecutionTarget = Annotated[
    LocalCurrentHostTarget | ManagedSshTarget,
    Field(discriminator="type"),
]
EXECUTION_TARGET_ADAPTER: TypeAdapter[ExecutionTarget] = TypeAdapter(ExecutionTarget)


def local_target_with_runtime_limit(
    *,
    allowed_devices: tuple[int, ...] | None,
    configured_maximum_devices: int | None,
) -> LocalCurrentHostTarget:
    """Resolve a local target with the controller's non-scientific GPU cap.

    The UI launcher passes the cap only to the child process.  It therefore
    does not enter the canonical scientific YAML and cannot change scoring or
    candidate semantics.  Once a Stage plan exists its concrete devices remain
    frozen and take precedence during resume.
    """

    raw_limit = os.environ.get("EASYDESIGN_LOCAL_MAXIMUM_GPUS")
    runtime_limit: int | None = None
    if raw_limit is not None:
        try:
            runtime_limit = int(raw_limit)
        except ValueError as error:
            raise ConfigurationError(
                "EASYDESIGN_LOCAL_MAXIMUM_GPUS 必须是正整数"
            ) from error
        if runtime_limit < 1:
            raise ConfigurationError(
                "EASYDESIGN_LOCAL_MAXIMUM_GPUS 必须是正整数"
            )
    configured_limit = (
        len(allowed_devices)
        if allowed_devices is not None
        else configured_maximum_devices
    )
    maximum = runtime_limit if runtime_limit is not None else configured_limit
    if configured_limit is not None and runtime_limit is not None:
        maximum = min(configured_limit, runtime_limit)
    return LocalCurrentHostTarget(
        allowed_devices=allowed_devices,
        maximum_devices=maximum,
    )


class GpuEligibility(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    snapshot: GpuResourceSnapshot
    eligible: bool
    reasons: tuple[str, ...] = ()
    active_lease_id: str | None = None


class GpuInventory(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: str = "0.1"
    observed_at: datetime
    host: str
    devices: tuple[GpuEligibility, ...]
    selected_devices: tuple[int, ...]
    waiting_for_resources: bool


class GpuLeaseRevision(BaseModel):
    """One immutable revision in a device lease lifecycle."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: str = "0.1"
    revision: int = Field(ge=1)
    lease_id: str = Field(pattern=ID_PATTERN)
    host: str = Field(min_length=1)
    device: int = Field(ge=0)
    owner_id: str = Field(pattern=ID_PATTERN)
    job_id: str = Field(pattern=ID_PATTERN)
    run_id: str = Field(pattern=ID_PATTERN)
    stage_number: Literal[4, 6]
    task_id: str | None = Field(default=None, pattern=ID_PATTERN)
    pid: int = Field(ge=1)
    status: Literal["active", "released", "expired"]
    acquired_at: datetime
    heartbeat_at: datetime
    updated_at: datetime
    previous_revision_sha256: str | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{64}$",
    )


def _sha256(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_new_json(path: Path, model: BaseModel) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(model.model_dump_json(indent=2))
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())


class GpuLeaseStore:
    """Append-only, flock-protected GPU leases for one EasyDesign workspace."""

    def __init__(
        self,
        *,
        context: WorkspaceContext | None = None,
        lease_root: Path | None = None,
        host: str | None = None,
        stale_after_seconds: float = 120.0,
    ) -> None:
        if context is not None and lease_root is not None:
            raise ValueError("context 与 lease_root 不能同时提供")
        self.context = (
            WorkspaceContext.discover()
            if context is None and lease_root is None
            else context
        )
        self.host = socket.gethostname() if host is None else host
        if stale_after_seconds <= 0:
            raise ValueError("stale_after_seconds 必须大于 0")
        self.stale_after = timedelta(seconds=stale_after_seconds)
        if lease_root is None:
            assert self.context is not None
            self.root = (
                self.context.runtime_root / "state" / "gpu-leases" / self.host
            )
            self.context.assert_write_path(self.root)
        else:
            if not lease_root.is_absolute():
                raise ValueError("managed lease_root 必须是绝对路径")
            self.root = lease_root.resolve(strict=False) / self.host

    @contextmanager
    def _locked(self) -> Iterator[None]:
        lock_path = self.root / "lease.lock"
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        with lock_path.open("a+b") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    def _device_root(self, device: int) -> Path:
        return self.root / f"gpu-{device:03d}"

    def _revision_paths(self, device: int) -> tuple[Path, ...]:
        return tuple(sorted(self._device_root(device).glob("revision-*.json")))

    def latest(self, device: int) -> GpuLeaseRevision | None:
        paths = self._revision_paths(device)
        if not paths:
            return None
        return GpuLeaseRevision.model_validate_json(
            paths[-1].read_text(encoding="utf-8")
        )

    @staticmethod
    def _pid_exists(pid: int) -> bool:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        return True

    def _append(
        self,
        *,
        previous: GpuLeaseRevision | None,
        previous_path: Path | None,
        status: Literal["active", "released", "expired"],
        now: datetime,
        lease_id: str,
        device: int,
        owner_id: str,
        job_id: str,
        run_id: str,
        stage_number: Literal[4, 6],
        task_id: str | None,
        pid: int,
        acquired_at: datetime,
    ) -> GpuLeaseRevision:
        revision_number = 1 if previous is None else previous.revision + 1
        model = GpuLeaseRevision(
            revision=revision_number,
            lease_id=lease_id,
            host=self.host,
            device=device,
            owner_id=owner_id,
            job_id=job_id,
            run_id=run_id,
            stage_number=stage_number,
            task_id=task_id,
            pid=pid,
            status=status,
            acquired_at=acquired_at,
            heartbeat_at=now,
            updated_at=now,
            previous_revision_sha256=(
                None if previous_path is None else _sha256(previous_path)
            ),
        )
        path = self._device_root(device) / f"revision-{revision_number:06d}.json"
        _write_new_json(path, model)
        return model

    def _expire_if_abandoned(
        self,
        device: int,
        *,
        now: datetime,
    ) -> GpuLeaseRevision | None:
        paths = self._revision_paths(device)
        if not paths:
            return None
        latest_path = paths[-1]
        latest = GpuLeaseRevision.model_validate_json(
            latest_path.read_text(encoding="utf-8")
        )
        if latest.status != "active":
            return latest
        if now - latest.heartbeat_at <= self.stale_after:
            return latest
        if self._pid_exists(latest.pid):
            return latest
        return self._append(
            previous=latest,
            previous_path=latest_path,
            status="expired",
            now=now,
            lease_id=latest.lease_id,
            device=device,
            owner_id=latest.owner_id,
            job_id=latest.job_id,
            run_id=latest.run_id,
            stage_number=latest.stage_number,
            task_id=latest.task_id,
            pid=latest.pid,
            acquired_at=latest.acquired_at,
        )

    def inventory(
        self,
        snapshots: tuple[GpuResourceSnapshot, ...],
        *,
        target: LocalCurrentHostTarget,
        max_memory_used_mib: int,
        max_utilization_percent: int,
        now: datetime | None = None,
    ) -> GpuInventory:
        observed_at = datetime.now(UTC) if now is None else now
        allowed = None if target.allowed_devices is None else set(target.allowed_devices)
        rows: list[GpuEligibility] = []
        selected: list[int] = []
        with self._locked():
            for snapshot in sorted(snapshots, key=lambda item: item.device):
                reasons: list[str] = []
                if allowed is not None and snapshot.device not in allowed:
                    reasons.append("not-allowed")
                if snapshot.compute_process_pids:
                    reasons.append("external-compute-process")
                if snapshot.memory_used_mib > max_memory_used_mib:
                    reasons.append("memory-threshold")
                if snapshot.utilization_percent > max_utilization_percent:
                    reasons.append("utilization-threshold")
                lease = self._expire_if_abandoned(snapshot.device, now=observed_at)
                if lease is not None and lease.status == "active":
                    reasons.append("easydesign-lease")
                eligible = not reasons
                if eligible and (
                    target.maximum_devices is None
                    or len(selected) < target.maximum_devices
                ):
                    selected.append(snapshot.device)
                rows.append(
                    GpuEligibility(
                        snapshot=snapshot,
                        eligible=eligible,
                        reasons=tuple(reasons),
                        active_lease_id=(
                            lease.lease_id
                            if lease is not None and lease.status == "active"
                            else None
                        ),
                    )
                )
        return GpuInventory(
            observed_at=observed_at,
            host=self.host,
            devices=tuple(rows),
            selected_devices=tuple(selected),
            waiting_for_resources=not selected,
        )

    def acquire(
        self,
        devices: tuple[int, ...],
        *,
        owner_id: str,
        job_id: str,
        run_id: str,
        stage_number: Literal[4, 6],
        task_id: str | None = None,
        pid: int | None = None,
        now: datetime | None = None,
    ) -> tuple[GpuLeaseRevision, ...]:
        if not devices or len(devices) != len(set(devices)):
            raise ConfigurationError("GPU lease 需要非空且不重复的 device")
        timestamp = datetime.now(UTC) if now is None else now
        process_id = os.getpid() if pid is None else pid
        leases: list[GpuLeaseRevision] = []
        with self._locked():
            for device in devices:
                current = self._expire_if_abandoned(device, now=timestamp)
                if current is not None and current.status == "active":
                    raise BackendContractError(
                        f"GPU {device} 已由 EasyDesign lease={current.lease_id} 占用"
                    )
            for device in devices:
                paths = self._revision_paths(device)
                previous_path = paths[-1] if paths else None
                previous = (
                    None
                    if previous_path is None
                    else GpuLeaseRevision.model_validate_json(
                        previous_path.read_text(encoding="utf-8")
                    )
                )
                leases.append(
                    self._append(
                        previous=previous,
                        previous_path=previous_path,
                        status="active",
                        now=timestamp,
                        lease_id=f"lease-{uuid4().hex}",
                        device=device,
                        owner_id=owner_id,
                        job_id=job_id,
                        run_id=run_id,
                        stage_number=stage_number,
                        task_id=task_id,
                        pid=process_id,
                        acquired_at=timestamp,
                    )
                )
        return tuple(leases)

    def heartbeat(
        self,
        leases: tuple[GpuLeaseRevision, ...],
        *,
        now: datetime | None = None,
    ) -> tuple[GpuLeaseRevision, ...]:
        timestamp = datetime.now(UTC) if now is None else now
        updated: list[GpuLeaseRevision] = []
        with self._locked():
            for lease in leases:
                paths = self._revision_paths(lease.device)
                if not paths:
                    raise ConfigurationError("GPU lease revision 丢失")
                latest_path = paths[-1]
                latest = GpuLeaseRevision.model_validate_json(
                    latest_path.read_text(encoding="utf-8")
                )
                if latest.lease_id != lease.lease_id or latest.status != "active":
                    raise BackendContractError("GPU lease 已不是当前 active revision")
                updated.append(
                    self._append(
                        previous=latest,
                        previous_path=latest_path,
                        status="active",
                        now=timestamp,
                        lease_id=latest.lease_id,
                        device=latest.device,
                        owner_id=latest.owner_id,
                        job_id=latest.job_id,
                        run_id=latest.run_id,
                        stage_number=latest.stage_number,
                        task_id=latest.task_id,
                        pid=latest.pid,
                        acquired_at=latest.acquired_at,
                    )
                )
        return tuple(updated)

    def active_for_job(
        self,
        job_id: str,
        *,
        devices: tuple[int, ...] | None = None,
    ) -> tuple[GpuLeaseRevision, ...]:
        """Return the current active leases owned by one managed job.

        This is used by a managed worker child to prove that the central queue
        already reserved its devices.  It never treats an unrelated active
        lease as reusable.
        """

        selected = None if devices is None else set(devices)
        rows: list[GpuLeaseRevision] = []
        if not self.root.is_dir():
            return ()
        for device_root in sorted(self.root.glob("gpu-*")):
            if not device_root.is_dir():
                continue
            try:
                device = int(device_root.name.removeprefix("gpu-"))
            except ValueError:
                continue
            if selected is not None and device not in selected:
                continue
            latest = self.latest(device)
            if latest is not None and latest.status == "active" and latest.job_id == job_id:
                rows.append(latest)
        return tuple(sorted(rows, key=lambda item: item.device))

    def assign_pid(
        self,
        leases: tuple[GpuLeaseRevision, ...],
        *,
        pid: int,
        now: datetime | None = None,
    ) -> tuple[GpuLeaseRevision, ...]:
        """Bind an admission reservation to the launched worker PID."""

        if pid < 1:
            raise ConfigurationError("GPU lease worker PID 必须是正整数")
        timestamp = datetime.now(UTC) if now is None else now
        updated: list[GpuLeaseRevision] = []
        with self._locked():
            for lease in leases:
                paths = self._revision_paths(lease.device)
                if not paths:
                    raise ConfigurationError("GPU lease revision 丢失")
                latest_path = paths[-1]
                latest = GpuLeaseRevision.model_validate_json(
                    latest_path.read_text(encoding="utf-8")
                )
                if latest.lease_id != lease.lease_id or latest.status != "active":
                    raise BackendContractError("GPU lease 已不是当前 active revision")
                updated.append(
                    self._append(
                        previous=latest,
                        previous_path=latest_path,
                        status="active",
                        now=timestamp,
                        lease_id=latest.lease_id,
                        device=latest.device,
                        owner_id=latest.owner_id,
                        job_id=latest.job_id,
                        run_id=latest.run_id,
                        stage_number=latest.stage_number,
                        task_id=latest.task_id,
                        pid=pid,
                        acquired_at=latest.acquired_at,
                    )
                )
        return tuple(updated)

    def release(
        self,
        leases: tuple[GpuLeaseRevision, ...],
        *,
        now: datetime | None = None,
    ) -> tuple[GpuLeaseRevision, ...]:
        timestamp = datetime.now(UTC) if now is None else now
        released: list[GpuLeaseRevision] = []
        with self._locked():
            for lease in leases:
                paths = self._revision_paths(lease.device)
                if not paths:
                    raise ConfigurationError("GPU lease revision 丢失")
                latest_path = paths[-1]
                latest = GpuLeaseRevision.model_validate_json(
                    latest_path.read_text(encoding="utf-8")
                )
                if latest.lease_id != lease.lease_id:
                    raise BackendContractError("拒绝释放其他任务的 GPU lease")
                if latest.status != "active":
                    released.append(latest)
                    continue
                released.append(
                    self._append(
                        previous=latest,
                        previous_path=latest_path,
                        status="released",
                        now=timestamp,
                        lease_id=latest.lease_id,
                        device=latest.device,
                        owner_id=latest.owner_id,
                        job_id=latest.job_id,
                        run_id=latest.run_id,
                        stage_number=latest.stage_number,
                        task_id=latest.task_id,
                        pid=latest.pid,
                        acquired_at=latest.acquired_at,
                    )
                )
        return tuple(released)


def load_execution_target(path: Path) -> ExecutionTarget:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return EXECUTION_TARGET_ADAPTER.validate_python(payload)


def managed_preallocated_devices() -> tuple[str, tuple[int, ...]] | None:
    """Read the central-worker allocation passed to a fixed child process."""

    job_id = os.environ.get("EASYDESIGN_MANAGED_JOB_ID")
    raw_devices = os.environ.get("EASYDESIGN_ASSIGNED_GPU_DEVICES")
    if job_id is None and raw_devices is None:
        return None
    if not job_id or not raw_devices:
        raise ConfigurationError("managed worker GPU allocation 环境不完整")
    values = tuple(item.strip() for item in raw_devices.split(",") if item.strip())
    try:
        devices = tuple(int(item) for item in values)
    except ValueError as error:
        raise ConfigurationError("managed worker GPU allocation 不是有效编号") from error
    if (
        not devices
        or any(item < 0 for item in devices)
        or len(devices) != len(set(devices))
    ):
        raise ConfigurationError("managed worker GPU allocation 必须非空、非负且唯一")
    return job_id, devices


def verify_managed_preallocation(
    *,
    lease_store: GpuLeaseStore,
    stage_number: Literal[4, 6],
) -> tuple[int, ...] | None:
    allocation = managed_preallocated_devices()
    if allocation is None:
        return None
    job_id, devices = allocation
    leases = lease_store.active_for_job(job_id, devices=devices)
    if tuple(item.device for item in leases) != devices:
        raise BackendContractError("managed worker 中央 GPU lease 与子任务分配不一致")
    if any(item.stage_number != stage_number for item in leases):
        raise BackendContractError("managed worker GPU lease 的 Stage identity 不一致")
    return devices


def resolve_managed_execution_devices(
    *,
    managed_devices: tuple[int, ...] | None,
    requested_devices: tuple[int, ...] | None,
    frozen_plan: bool,
    stage_number: Literal[4, 6],
) -> tuple[int, ...] | None:
    """Resolve physical devices after a central Manager allocation.

    Scientific configuration may name devices for direct execution on the
    current host.  Those physical indices are not portable to a managed host,
    so a new managed plan records the Manager allocation instead.  Once a plan
    exists, however, its recorded devices are immutable and must exactly match
    the allocation used to resume it.
    """

    if managed_devices is None:
        return None
    if (
        frozen_plan
        and requested_devices is not None
        and requested_devices != managed_devices
    ):
        raise ManifestStateError(
            f"Stage {stage_number:02d} frozen plan 与 managed worker GPU allocation 不一致"
        )
    return managed_devices


def gpu_lease_store_for_run(run_root: Path) -> GpuLeaseStore:
    """Resolve the workspace lease store, retaining read/write compatibility
    with historical runs that were explicitly located outside a workspace.
    """

    root = run_root.resolve()
    try:
        return GpuLeaseStore(context=WorkspaceContext.discover(root))
    except ConfigurationError:
        base = root.parents[2] if len(root.parents) >= 3 else root.parent
        return GpuLeaseStore(
            lease_root=(base / "runtime" / "state" / "gpu-leases").resolve()
        )


def wait_for_eligible_gpus(
    *,
    probe: object,
    lease_store: GpuLeaseStore,
    target: LocalCurrentHostTarget,
    max_memory_used_mib: int,
    max_utilization_percent: int,
    timeout_seconds: float,
    poll_seconds: float,
    require_all_allowed: bool = False,
    on_wait: Callable[[GpuInventory], None] | None = None,
) -> GpuInventory:
    """Wait without taking over external GPU processes.

    The probe is intentionally structural (``snapshots()``) so deterministic
    test probes and the real ``NvidiaSmiProbe`` use the same scheduling path.
    """

    snapshots_method = getattr(probe, "snapshots", None)
    if not callable(snapshots_method):
        raise TypeError("GPU probe 必须提供 snapshots()")
    deadline = time.monotonic() + timeout_seconds
    while True:
        snapshots = tuple(snapshots_method())
        inventory = lease_store.inventory(
            snapshots,
            target=target,
            max_memory_used_mib=max_memory_used_mib,
            max_utilization_percent=max_utilization_percent,
        )
        ready = bool(inventory.selected_devices)
        if require_all_allowed:
            requested = target.allowed_devices or ()
            ready = set(inventory.selected_devices) == set(requested)
        if ready:
            return inventory
        if on_wait is not None:
            on_wait(inventory)
        if time.monotonic() >= deadline:
            details = "; ".join(
                f"gpu={item.snapshot.device},reasons={','.join(item.reasons) or 'eligible'}"
                for item in inventory.devices
            )
            raise BackendContractError(
                f"GPU 在有界等待后仍不可用: {details or 'no devices'}"
            )
        time.sleep(poll_seconds)
