"""Physical device admission coordinated with the existing native GPU lease lock."""

from __future__ import annotations

import time
from datetime import UTC, datetime
from pathlib import Path

from easydesign.backends.executors.local_multi_gpu import GpuResourceSnapshot
from easydesign.execution_scope import DeviceAllocation, read_device_allocations
from easydesign.orchestration.execution_targets import GpuLeaseStore
from easydesign.workspace_context import WorkspaceContext

from .artifacts import immutable_json
from .contracts import ProductError
from .resource_control import Admission


class ProductDevicePool:
    def __init__(
        self, context: WorkspaceContext, *, allowed_devices: tuple[int, ...] | None = None
    ):
        if context.execution_scope is not None:
            raise ValueError("Device admission requires the unscoped controller")
        self.context = context
        self.native = GpuLeaseStore(context=context)
        self.root = (
            context.shared_runtime_root / "state/product-device-allocations" / self.native.host
        )
        self.allowed = None if allowed_devices is None else set(allowed_devices)

    def allocate(
        self, admission: Admission, snapshots: tuple[GpuResourceSnapshot, ...]
    ) -> DeviceAllocation | None:
        if admission.kind != "scientific":
            return None
        with self.native._locked():
            allocations = read_device_allocations(self.root)
            previous = next((r for r in allocations if r.grant_id == admission.id), None)
            if previous is not None:
                if (
                    previous.status != "reserved"
                    or previous.scope_id != admission.scope_id
                    or previous.actor_id != admission.actor_id
                ):
                    raise ProductError("allocation_conflict", "资源分配记录与当前请求不一致", 409)
                return previous
            occupied = {d for r in allocations if r.status == "reserved" for d in r.devices}
            selected: list[int] = []
            for snapshot in sorted(snapshots, key=lambda value: value.device):
                if self.allowed is not None and snapshot.device not in self.allowed:
                    continue
                if (
                    snapshot.device in occupied
                    or snapshot.compute_process_pids
                    or snapshot.memory_used_mib > 2048
                    or snapshot.utilization_percent > 10
                ):
                    continue
                lease = self.native._expire_if_abandoned(snapshot.device, now=datetime.now(UTC))
                if lease is not None and lease.status == "active":
                    continue
                selected.append(snapshot.device)
                if len(selected) == admission.gpu_slots:
                    break
            if len(selected) < admission.gpu_slots:
                return None
            record = DeviceAllocation(
                grant_id=admission.id,
                scope_id=admission.scope_id,
                actor_id=admission.actor_id,
                devices=tuple(selected),
                status="reserved",
                revision=1,
                created_at=time.time(),
            )
            self._publish(record)
            return record

    def release(self, grant_id: str) -> None:
        with self.native._locked():
            record = next(
                (r for r in read_device_allocations(self.root) if r.grant_id == grant_id), None
            )
            if record is None or record.status == "released":
                return
            self._publish(
                record.model_copy(update={"status": "released", "revision": record.revision + 1})
            )

    def _publish(self, record: DeviceAllocation) -> None:
        path = self.root / record.grant_id / f"revision-{record.revision:06d}.json"
        self.context.assert_write_path(path)
        immutable_json(path, record.model_dump(mode="json"))

    def assignment_path(self, grant_id: str) -> Path:
        return self.context.shared_runtime_root / "state/account-assignments" / (grant_id + ".json")
