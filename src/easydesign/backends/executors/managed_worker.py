"""File-backed managed compute queue for trusted EasyDesign workers.

The worker accepts only validated :class:`RemoteJobBundle` documents.  It does
not expose a generic shell command field.  Queue and job lifecycle records are
append-only and protected by ``flock``.
"""

from __future__ import annotations

import fcntl
import hashlib
import os
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Literal, Self, cast

from pydantic import BaseModel, ConfigDict, Field, model_validator

from easydesign.core import BackendContractError, ConfigurationError
from easydesign.core.artifacts import ID_PATTERN

if TYPE_CHECKING:
    from easydesign.orchestration.execution_targets import (
        GpuLeaseRevision,
        GpuLeaseStore,
    )

MANAGED_WORKER_ROOT = Path("/data/easydesign/managed-worker")
ManagedJobStatus = Literal[
    "queued",
    "waiting-resource",
    "admitting",
    "running",
    "drain-requested",
    "succeeded",
    "failed",
]


def _hash_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _write_new(path: Path, payload: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(payload)
        if not payload.endswith("\n"):
            handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())


class RemoteJobInput(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    relative_path: str = Field(min_length=1)
    size_bytes: int = Field(ge=1)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    role: str = Field(min_length=1)

    @model_validator(mode="after")
    def safe_relative_path(self) -> Self:
        path = Path(self.relative_path)
        if path.is_absolute() or ".." in path.parts or self.relative_path in {"", "."}:
            raise ValueError("RemoteJobInput 必须使用安全相对路径")
        return self


class RemoteJobBundle(BaseModel):
    """Immutable submission contract; intentionally has no command field."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: str = "0.2"
    job_id: str = Field(pattern=ID_PATTERN)
    controller_id: str = Field(pattern=ID_PATTERN)
    controller_key_fingerprint: str = Field(min_length=8, max_length=256)
    project_id: str = Field(pattern=ID_PATTERN)
    run_id: str = Field(pattern=ID_PATTERN)
    submitted_at: datetime
    stage_range: tuple[Literal[4, 5, 6, 7], ...]
    candidate_budget: int = Field(ge=1)
    backend_id: Literal["boltzgen-0.3.2"] = "boltzgen-0.3.2"
    easydesign_version: str = Field(min_length=1)
    config_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    upstream_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    inputs: tuple[RemoteJobInput, ...]
    source_run_mode: Literal["uploaded-closure", "managed-run"] = (
        "uploaded-closure"
    )
    managed_source_run: str | None = None
    maximum_gpus: int | None = Field(default=None, ge=1, le=8)
    requested_sync_mode: Literal["metadata", "review", "complete"] = "review"
    maximum_attempts: int = Field(default=3, ge=1, le=10)

    @model_validator(mode="after")
    def validate_stage_range(self) -> Self:
        if self.stage_range not in {(4,), (4, 5), (6,), (6, 7)}:
            raise ValueError("managed job 只允许 Stage 04→05 或 Stage 06→07")
        paths = [item.relative_path for item in self.inputs]
        if not paths or len(paths) != len(set(paths)):
            raise ValueError("RemoteJobBundle inputs 必须非空且路径唯一")
        if self.source_run_mode == "uploaded-closure":
            if self.managed_source_run is not None:
                raise ValueError("uploaded-closure 不得声明 managed_source_run")
            if not any(path.startswith("source-run/") for path in paths):
                raise ValueError("uploaded-closure 必须包含 source-run manifest 闭包")
        else:
            if self.managed_source_run is None:
                raise ValueError("managed-run 必须声明 managed_source_run")
            source = Path(self.managed_source_run)
            if (
                source.is_absolute()
                or ".." in source.parts
                or len(source.parts) != 3
                or source.parts[0] != "runs"
            ):
                raise ValueError(
                    "managed_source_run 必须是 runs/<project_id>/<run_id>"
                )
            if source.parts[1:] != (self.project_id, self.run_id):
                raise ValueError("managed_source_run 与 project/run identity 不一致")
            if any(path.startswith("source-run/") for path in paths):
                raise ValueError("managed-run 不得重复上传 source-run 闭包")
        return self

    @property
    def identity_sha256(self) -> str:
        canonical = self.model_dump_json(exclude_none=False).encode("utf-8")
        return _hash_bytes(canonical)


class ManagedJobRevision(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: str = "0.1"
    revision: int = Field(ge=1)
    job_id: str = Field(pattern=ID_PATTERN)
    bundle_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    status: ManagedJobStatus
    queued_at: datetime
    updated_at: datetime
    assigned_devices: tuple[int, ...] = ()
    worker_pid: int | None = Field(default=None, ge=1)
    lease_ids: tuple[str, ...] = ()
    attempt: int = Field(default=0, ge=0)
    error_code: str | None = None
    error_message: str | None = Field(default=None, max_length=4096)
    previous_revision_sha256: str | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{64}$",
    )

    @model_validator(mode="after")
    def validate_running_state(self) -> Self:
        if self.status in {"running", "drain-requested"}:
            if not self.assigned_devices or self.worker_pid is None:
                raise ValueError("running managed job 必须记录 GPU 与 PID")
            if len(self.assigned_devices) != len(self.lease_ids):
                raise ValueError("managed job GPU 与 lease 数量不一致")
        return self


class ManagedWorkerProbe(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: str = "0.1"
    observed_at: datetime
    service_version: str
    managed_root: str
    gpu_count: int = Field(ge=0)
    queue_depth: int = Field(ge=0)
    running_jobs: int = Field(ge=0)
    filesystem_total_bytes: int = Field(ge=1)
    filesystem_available_bytes: int = Field(ge=0)


class ManagedWorkerLayout:
    """Exact persistent layout; never touches sibling historical directories."""

    def __init__(self, root: Path = MANAGED_WORKER_ROOT) -> None:
        if not root.is_absolute():
            raise ValueError("managed worker root 必须是绝对路径")
        self.root = root.resolve(strict=False)

    @property
    def queue(self) -> Path:
        return self.root / "queue"

    @property
    def jobs(self) -> Path:
        return self.root / "jobs"

    @property
    def runs(self) -> Path:
        return self.root / "runs"

    @property
    def runtime(self) -> Path:
        return self.root / "runtime"

    def ensure(self) -> None:
        for relative in (
            "service",
            "config",
            "runtime/envs",
            "runtime/models",
            "runtime/state",
            "runtime/logs",
            "runtime/tmp",
            "runtime/cache",
            "runtime/quarantine",
            "queue",
            "jobs",
            "runs",
            "archives",
        ):
            (self.root / relative).mkdir(parents=True, exist_ok=True)


class ManagedQueue:
    def __init__(self, layout: ManagedWorkerLayout) -> None:
        self.layout = layout

    @contextmanager
    def _locked(self) -> Iterator[None]:
        self.layout.ensure()
        lock = self.layout.runtime / "state" / "managed-queue.lock"
        with lock.open("a+b") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    def _bundle_path(self, job_id: str) -> Path:
        return self.layout.queue / "submissions" / job_id / "bundle.json"

    def _revision_paths(self, job_id: str) -> tuple[Path, ...]:
        return tuple(sorted((self.layout.jobs / job_id / "revisions").glob("*.json")))

    def bundle(self, job_id: str) -> RemoteJobBundle:
        path = self._bundle_path(job_id)
        if not path.is_file():
            raise ConfigurationError(f"managed job bundle 不存在: {job_id}")
        return RemoteJobBundle.model_validate_json(path.read_text(encoding="utf-8"))

    def latest(self, job_id: str) -> ManagedJobRevision:
        paths = self._revision_paths(job_id)
        if not paths:
            raise ConfigurationError(f"managed job state 不存在: {job_id}")
        return ManagedJobRevision.model_validate_json(paths[-1].read_text(encoding="utf-8"))

    def _append(
        self,
        *,
        previous: ManagedJobRevision | None,
        status: ManagedJobStatus,
        now: datetime,
        bundle: RemoteJobBundle,
        assigned_devices: tuple[int, ...] = (),
        worker_pid: int | None = None,
        lease_ids: tuple[str, ...] = (),
        attempt: int = 0,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> ManagedJobRevision:
        paths = self._revision_paths(bundle.job_id)
        previous_path = paths[-1] if paths else None
        revision = ManagedJobRevision(
            revision=1 if previous is None else previous.revision + 1,
            job_id=bundle.job_id,
            bundle_sha256=bundle.identity_sha256,
            status=status,
            queued_at=now if previous is None else previous.queued_at,
            updated_at=now,
            assigned_devices=assigned_devices,
            worker_pid=worker_pid,
            lease_ids=lease_ids,
            attempt=attempt,
            error_code=error_code,
            error_message=error_message,
            previous_revision_sha256=(
                None
                if previous_path is None
                else _hash_bytes(previous_path.read_bytes())
            ),
        )
        destination = (
            self.layout.jobs
            / bundle.job_id
            / "revisions"
            / f"revision-{revision.revision:06d}.json"
        )
        _write_new(destination, revision.model_dump_json(indent=2))
        return revision

    def enqueue(self, bundle: RemoteJobBundle) -> ManagedJobRevision:
        with self._locked():
            destination = self._bundle_path(bundle.job_id)
            if destination.exists() or self._revision_paths(bundle.job_id):
                raise ConfigurationError(
                    f"managed job_id 已存在，禁止覆盖: {bundle.job_id}"
                )
            _write_new(destination, bundle.model_dump_json(indent=2))
            return self._append(
                previous=None,
                status="queued",
                now=bundle.submitted_at,
                bundle=bundle,
            )

    def list_latest(self) -> tuple[ManagedJobRevision, ...]:
        if not self.layout.jobs.is_dir():
            return ()
        return tuple(
            self.latest(path.name)
            for path in sorted(self.layout.jobs.iterdir())
            if path.is_dir() and self._revision_paths(path.name)
        )

    def claim(
        self,
        job_id: str,
        *,
        devices: tuple[int, ...],
        worker_pid: int,
        leases: tuple[GpuLeaseRevision, ...],
        now: datetime | None = None,
    ) -> ManagedJobRevision:
        timestamp = datetime.now(UTC) if now is None else now
        with self._locked():
            bundle = self.bundle(job_id)
            current = self.latest(job_id)
            if current.status != "admitting":
                raise BackendContractError(
                    f"managed job 当前状态不可 claim: {current.status}"
                )
            if tuple(item.device for item in leases) != devices:
                raise BackendContractError("managed job devices 与 lease 不一致")
            return self._append(
                previous=current,
                status="running",
                now=timestamp,
                bundle=bundle,
                assigned_devices=devices,
                worker_pid=worker_pid,
                lease_ids=tuple(item.lease_id for item in leases),
                attempt=current.attempt + 1,
            )

    def reserve_next(
        self,
        *,
        resources_available: bool,
        now: datetime | None = None,
    ) -> ManagedJobRevision | None:
        """Atomically reserve the oldest runnable job for one admission loop.

        Merely listing queue revisions and claiming after process launch leaves
        a race in which two service loops can launch the same job.  The
        ``admitting`` revision is an append-only reservation made while the
        queue flock is held.  It intentionally carries no PID or GPU identity;
        those are published only after leases and the fixed worker process are
        both established.
        """

        timestamp = datetime.now(UTC) if now is None else now
        with self._locked():
            candidates: list[tuple[ManagedJobRevision, RemoteJobBundle]] = []
            for current in self.list_latest():
                if current.status not in {"queued", "waiting-resource", "failed"}:
                    continue
                bundle = self.bundle(current.job_id)
                if current.attempt < bundle.maximum_attempts:
                    candidates.append((current, bundle))
            if not candidates:
                return None
            current, bundle = sorted(
                candidates,
                key=lambda item: (item[0].queued_at, item[0].job_id),
            )[0]
            if not resources_available:
                if current.status == "waiting-resource":
                    return current
                return self._append(
                    previous=current,
                    status="waiting-resource",
                    now=timestamp,
                    bundle=bundle,
                    attempt=current.attempt,
                )
            return self._append(
                previous=current,
                status="admitting",
                now=timestamp,
                bundle=bundle,
                attempt=current.attempt,
            )

    def transition(
        self,
        job_id: str,
        *,
        status: Literal[
            "waiting-resource",
            "drain-requested",
            "succeeded",
            "failed",
        ],
        now: datetime | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> ManagedJobRevision:
        timestamp = datetime.now(UTC) if now is None else now
        with self._locked():
            bundle = self.bundle(job_id)
            current = self.latest(job_id)
            assigned = (
                current.assigned_devices
                if status == "drain-requested"
                else ()
            )
            return self._append(
                previous=current,
                status=status,
                now=timestamp,
                bundle=bundle,
                assigned_devices=assigned,
                worker_pid=current.worker_pid if status == "drain-requested" else None,
                lease_ids=current.lease_ids if status == "drain-requested" else (),
                attempt=current.attempt,
                error_code=error_code,
                error_message=error_message,
            )

    def heartbeat(
        self,
        job_id: str,
        *,
        worker_pid: int,
        leases: tuple[GpuLeaseRevision, ...],
        now: datetime | None = None,
    ) -> ManagedJobRevision:
        """Append a running-state heartbeat without rewriting queue history."""

        timestamp = datetime.now(UTC) if now is None else now
        with self._locked():
            bundle = self.bundle(job_id)
            current = self.latest(job_id)
            if current.status not in {"running", "drain-requested"}:
                raise BackendContractError(
                    f"managed job 当前状态不能 heartbeat: {current.status}"
                )
            if current.worker_pid != worker_pid:
                raise BackendContractError("managed job heartbeat PID 与当前 worker 不一致")
            if tuple(item.lease_id for item in leases) != current.lease_ids:
                raise BackendContractError("managed job heartbeat lease identity 不一致")
            return self._append(
                previous=current,
                status=current.status,
                now=timestamp,
                bundle=bundle,
                assigned_devices=current.assigned_devices,
                worker_pid=current.worker_pid,
                lease_ids=current.lease_ids,
                attempt=current.attempt,
            )


class ManagedWorker:
    """Admission controller; launch callback is fixed by the service deployment."""

    def __init__(
        self,
        *,
        layout: ManagedWorkerLayout,
        queue: ManagedQueue | None = None,
        lease_store: GpuLeaseStore,
    ) -> None:
        self.layout = layout
        self.queue = ManagedQueue(layout) if queue is None else queue
        self.leases = lease_store

    def admit_one(
        self,
        *,
        eligible_devices: tuple[int, ...],
        launcher: Callable[[RemoteJobBundle, tuple[int, ...]], int],
        now: datetime | None = None,
    ) -> ManagedJobRevision | None:
        timestamp = datetime.now(UTC) if now is None else now
        selected = self.queue.reserve_next(
            resources_available=bool(eligible_devices),
            now=timestamp,
        )
        if selected is None or selected.status == "waiting-resource":
            return selected
        bundle = self.queue.bundle(selected.job_id)
        maximum = bundle.maximum_gpus or len(eligible_devices)
        devices = eligible_devices[:maximum]
        try:
            leases = self.leases.acquire(
                devices,
                owner_id=bundle.controller_id,
                job_id=bundle.job_id,
                run_id=bundle.run_id,
                stage_number=cast(Literal[4, 6], bundle.stage_range[0]),
                now=timestamp,
            )
        except BackendContractError:
            return self.queue.transition(
                bundle.job_id,
                status="waiting-resource",
                now=timestamp,
                error_code="gpu-lease-race",
                error_message="GPU 在队列预留后被其他 EasyDesign 任务获取，继续等待",
            )
        try:
            pid = launcher(bundle, devices)
            if pid < 1:
                raise BackendContractError("managed launcher 没有返回有效 PID")
            leases = self.leases.assign_pid(leases, pid=pid, now=timestamp)
            return self.queue.claim(
                bundle.job_id,
                devices=devices,
                worker_pid=pid,
                leases=leases,
                now=timestamp,
            )
        except Exception as error:
            self.leases.release(leases, now=timestamp)
            self.queue.transition(
                bundle.job_id,
                status="failed",
                now=timestamp,
                error_code="managed-launch-failed",
                error_message=str(error)[:4096] or type(error).__name__,
            )
            raise
