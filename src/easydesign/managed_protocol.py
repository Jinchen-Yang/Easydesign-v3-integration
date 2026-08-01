"""Versioned controller/Manager protocol shared by independent repositories.

The ProteinDigger EasyDesign repository is the authority for these wire models.
The Suzhou2 Manager imports them from an exact EasyDesign wheel and must not
copy or reinterpret their schemas.  The submission contract intentionally has
no command or shell field.
"""

from __future__ import annotations

import hashlib
from datetime import datetime
from pathlib import Path
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from easydesign.core.artifacts import ID_PATTERN

MANAGED_WORKER_ROOT = Path("/data/easydesign/managed-worker")
MANAGED_BUNDLE_SCHEMA_VERSION = "0.2"
MANAGED_PROBE_SCHEMA_VERSION = "0.2"
REQUIRED_MANAGED_STAGE_RANGES: tuple[tuple[int, ...], ...] = ((4, 5), (6, 7))
REQUIRED_MANAGED_BACKENDS: tuple[str, ...] = (
    "boltzgen",
    "protenix-v2",
    "tnp",
)
REQUIRED_MANAGED_GPU_COUNT = 8
MINIMUM_MANAGED_AVAILABLE_BYTES = 5 * 1024**3

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
    """Immutable managed submission; linked filtering always stays remote."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["0.2"] = "0.2"
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
    source_run_mode: Literal["uploaded-closure", "managed-run"] = "uploaded-closure"
    managed_source_run: str | None = None
    maximum_gpus: int | None = Field(default=None, ge=1, le=8)
    requested_sync_mode: Literal["metadata", "review", "complete"] = "review"
    maximum_attempts: int = Field(default=3, ge=1, le=10)

    @model_validator(mode="after")
    def validate_contract(self) -> Self:
        if self.stage_range not in {(4, 5), (6, 7)}:
            raise ValueError("managed job 只允许连续 Stage 04→05 或 Stage 06→07")
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
                raise ValueError("managed_source_run 必须是 runs/<project_id>/<run_id>")
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

    schema_version: Literal["0.1"] = "0.1"
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


class ManagedBackendReadiness(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    backend_id: Literal["boltzgen", "protenix-v2", "tnp"]
    ready: bool
    detail: str = Field(min_length=1, max_length=4096)


class ManagedWorkerProbe(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["0.2"] = "0.2"
    observed_at: datetime
    manager_version: str = Field(min_length=1)
    easydesign_version: str = Field(min_length=1)
    supported_stage_ranges: tuple[tuple[Literal[4, 5, 6, 7], ...], ...]
    backends: tuple[ManagedBackendReadiness, ...]
    managed_root: str
    gpu_count: int = Field(ge=0)
    queue_depth: int = Field(ge=0)
    running_jobs: int = Field(ge=0)
    filesystem_total_bytes: int = Field(ge=1)
    filesystem_available_bytes: int = Field(ge=0)

    @model_validator(mode="after")
    def unique_capabilities(self) -> Self:
        ranges = tuple(tuple(item) for item in self.supported_stage_ranges)
        if len(ranges) != len(set(ranges)):
            raise ValueError("supported_stage_ranges 不能重复")
        backend_ids = tuple(item.backend_id for item in self.backends)
        if len(backend_ids) != len(set(backend_ids)):
            raise ValueError("backends 不能重复")
        return self

    @property
    def ready(self) -> bool:
        ranges = {tuple(item) for item in self.supported_stage_ranges}
        required_ranges = set(REQUIRED_MANAGED_STAGE_RANGES)
        states: dict[str, bool] = {
            item.backend_id: item.ready for item in self.backends
        }
        return (
            required_ranges.issubset(ranges)
            and all(states.get(backend_id, False) for backend_id in REQUIRED_MANAGED_BACKENDS)
            and self.gpu_count == REQUIRED_MANAGED_GPU_COUNT
            and self.filesystem_available_bytes >= MINIMUM_MANAGED_AVAILABLE_BYTES
        )


__all__ = [
    "MANAGED_BUNDLE_SCHEMA_VERSION",
    "MANAGED_PROBE_SCHEMA_VERSION",
    "MANAGED_WORKER_ROOT",
    "MINIMUM_MANAGED_AVAILABLE_BYTES",
    "ManagedBackendReadiness",
    "ManagedJobRevision",
    "ManagedJobStatus",
    "ManagedWorkerProbe",
    "REQUIRED_MANAGED_BACKENDS",
    "REQUIRED_MANAGED_GPU_COUNT",
    "REQUIRED_MANAGED_STAGE_RANGES",
    "RemoteJobBundle",
    "RemoteJobInput",
]
