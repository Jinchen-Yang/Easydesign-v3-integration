"""Transport-neutral, immutable execution scopes published by the local controller.

This module carries resource/data confinement, not user authentication or scientific
approval. Only the trusted controller publishes scope files; workers can read them.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from easydesign.core import ConfigurationError, PathPolicyError

EXECUTION_SCOPE_ENV = "EASYDESIGN_EXECUTION_SCOPE"


class ExecutionScope(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["0.1"] = "0.1"
    scope_id: str = Field(pattern=r"^(user|team)-[0-9a-f]{32}$")
    actor_id: str = Field(pattern=r"^user-[0-9a-f]{32}$")
    purpose: Literal["interactive", "scientific", "conversation"] = "interactive"
    grant_id: str | None = Field(default=None, pattern=r"^grant-[0-9a-f]{32}$")
    devices: tuple[Annotated[int, Field(strict=True, ge=0)], ...] = ()
    max_gpu_devices: int = Field(default=1, ge=1, le=64)
    max_candidates_per_job: int = Field(default=50_000, ge=1, le=1_000_000)

    @model_validator(mode="after")
    def valid_allocation(self) -> Self:
        if len(set(self.devices)) != len(self.devices) or len(self.devices) > self.max_gpu_devices:
            raise ValueError("Invalid scoped GPU allocation")
        if self.purpose == "scientific" and (not self.grant_id or not self.devices):
            raise ValueError("Scientific execution requires an explicit GPU allocation")
        if self.purpose != "scientific" and self.devices:
            raise ValueError("Non-scientific execution cannot allocate GPUs")
        return self


class DeviceAllocation(BaseModel):
    """Control-plane GPU reservation; deliberately not a scientific Stage lease."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    schema_version: Literal["0.1"] = "0.1"
    grant_id: str = Field(pattern=r"^grant-[0-9a-f]{32}$")
    scope_id: str = Field(pattern=r"^(user|team)-[0-9a-f]{32}$")
    actor_id: str = Field(pattern=r"^user-[0-9a-f]{32}$")
    devices: tuple[Annotated[int, Field(strict=True, ge=0)], ...]
    status: Literal["reserved", "released"]
    revision: int = Field(ge=1)
    created_at: float


def read_device_allocations(root: Path) -> tuple[DeviceAllocation, ...]:
    records: list[DeviceAllocation] = []
    for directory in sorted(root.glob("grant-*")):
        if directory.is_symlink() or not directory.is_dir():
            raise PathPolicyError("Invalid device allocation registry entry")
        valid = None
        for path in reversed(sorted(directory.glob("revision-*.json"))):
            try:
                candidate = DeviceAllocation.model_validate_json(path.read_text())
                if (
                    candidate.grant_id != directory.name
                    or path.name != f"revision-{candidate.revision:06d}.json"
                ):
                    continue
                valid = candidate
                break
            except (ValueError, OSError):
                continue
        if valid is None:
            raise ConfigurationError("Device allocation has no valid revision")
        records.append(valid)
    return tuple(records)


def require_active_allocation(scope: ExecutionScope, root: Path) -> None:
    if scope.purpose != "scientific":
        return
    record = next((r for r in read_device_allocations(root) if r.grant_id == scope.grant_id), None)
    if (
        record is None
        or record.status != "reserved"
        or record.scope_id != scope.scope_id
        or record.actor_id != scope.actor_id
        or record.devices != scope.devices
    ):
        raise ConfigurationError("当前执行身份没有有效的显卡资源预留")


def enforce_scoped_generation_budget(requested_candidates: int, run_root: Path) -> None:
    """Apply an execution ceiling without changing a frozen scientific budget."""
    import socket

    from easydesign.workspace_context import WorkspaceContext

    if not WorkspaceContext.scope_active():
        return
    context = WorkspaceContext.discover(run_root)
    scope = context.execution_scope
    if scope is None or scope.purpose != "scientific":
        raise ConfigurationError("科学生成缺少已授权的执行身份")
    require_active_allocation(
        scope,
        context.shared_runtime_root / "state/product-device-allocations" / socket.gethostname(),
    )
    if requested_candidates > scope.max_candidates_per_job:
        raise ConfigurationError(
            f"科学计划请求 {requested_candidates} 个候选，超过当前执行额度 "
            f"{scope.max_candidates_per_job}；计划未被自动缩减"
        )


def publish_scope(
    *, root: Path, runtime_root: Path, declaration_path: Path, scope: ExecutionScope
) -> Path:
    """Append a content-addressed control-plane record, never rewrite a scope."""
    parent = runtime_root / "state/execution-scopes"
    if not parent.resolve().is_relative_to(root.resolve()):
        raise PathPolicyError("Execution scope registry escaped the workspace")
    parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "workspace_sha256": hashlib.sha256(declaration_path.read_bytes()).hexdigest(),
        "scope": scope.model_dump(mode="json"),
    }
    data = (json.dumps(payload, sort_keys=True, ensure_ascii=False) + "\n").encode()
    path = parent / (hashlib.sha256(data).hexdigest() + ".json")
    if path.is_symlink():
        raise PathPolicyError("Execution scope records cannot be symlinks")
    fd, temporary_name = tempfile.mkstemp(prefix=".scope-", dir=parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError:
            if path.read_bytes() != data:
                raise ConfigurationError("Execution scope record identity conflict") from None
    finally:
        temporary.unlink()
    return path


def load_scope(*, runtime_root: Path, declaration_path: Path, path: Path) -> ExecutionScope:
    parent = (runtime_root / "state/execution-scopes").resolve()
    if path.is_symlink() or not path.resolve().is_relative_to(parent):
        raise PathPolicyError("Execution scope record is not controller-owned")
    data = path.read_bytes()
    if path.name != hashlib.sha256(data).hexdigest() + ".json":
        raise ConfigurationError("Execution scope checksum mismatch")
    payload = json.loads(data)
    if payload.get("workspace_sha256") != hashlib.sha256(declaration_path.read_bytes()).hexdigest():
        raise ConfigurationError("Workspace declaration changed after scope authorization")
    return ExecutionScope.model_validate(payload["scope"])
