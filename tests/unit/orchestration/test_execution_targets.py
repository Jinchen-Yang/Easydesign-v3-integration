from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from easydesign.backends.executors import GpuResourceSnapshot
from easydesign.core import BackendContractError, ManifestStateError
from easydesign.orchestration.execution_targets import (
    GpuLeaseStore,
    LocalCurrentHostTarget,
    ManagedSshTarget,
    local_target_with_runtime_limit,
    resolve_managed_execution_devices,
)
from easydesign.workspace_context import WorkspaceContext


def _context(tmp_path: Path) -> WorkspaceContext:
    (tmp_path / "easydesign-workspace.yaml").write_text(
        'schema_version: "0.1"\nworkspace_id: test\n',
        encoding="utf-8",
    )
    return WorkspaceContext.discover(tmp_path)


def _gpu(
    device: int,
    *,
    memory: int = 0,
    utilization: int = 0,
    pids: tuple[int, ...] = (),
) -> GpuResourceSnapshot:
    return GpuResourceSnapshot(
        device=device,
        name="A100",
        uuid=f"GPU-{device}",
        memory_total_mib=80_000,
        memory_used_mib=memory,
        utilization_percent=utilization,
        compute_process_pids=pids,
    )


def test_execution_target_is_not_scientific_config() -> None:
    assert LocalCurrentHostTarget(maximum_devices=2).type == "local-current-host"
    assert ManagedSshTarget(executor_id="suzhou2").executor_id == "suzhou2"


def test_local_runtime_gpu_limit_is_applied_without_changing_scientific_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("EASYDESIGN_LOCAL_MAXIMUM_GPUS", "2")
    target = local_target_with_runtime_limit(
        allowed_devices=None,
        configured_maximum_devices=8,
    )
    assert target.maximum_devices == 2
    assert target.allowed_devices is None


def test_new_managed_plan_uses_central_devices_not_controller_indices() -> None:
    assert resolve_managed_execution_devices(
        managed_devices=(6,),
        requested_devices=(0,),
        frozen_plan=False,
        stage_number=4,
    ) == (6,)


def test_managed_resume_rejects_a_different_frozen_device_allocation() -> None:
    with pytest.raises(ManifestStateError, match="frozen plan"):
        resolve_managed_execution_devices(
            managed_devices=(6,),
            requested_devices=(7,),
            frozen_plan=True,
            stage_number=6,
        )


def test_local_execution_does_not_override_requested_devices() -> None:
    assert (
        resolve_managed_execution_devices(
            managed_devices=None,
            requested_devices=(0,),
            frozen_plan=False,
            stage_number=4,
        )
        is None
    )


def test_inventory_excludes_external_processes_and_honours_limit(
    tmp_path: Path,
) -> None:
    store = GpuLeaseStore(context=_context(tmp_path), host="test-host")
    inventory = store.inventory(
        (_gpu(0), _gpu(1, pids=(100,)), _gpu(2)),
        target=LocalCurrentHostTarget(maximum_devices=1),
        max_memory_used_mib=1024,
        max_utilization_percent=10,
    )
    assert inventory.selected_devices == (0,)
    assert inventory.devices[1].reasons == ("external-compute-process",)


def test_gpu_lease_is_append_only_and_prevents_double_assignment(
    tmp_path: Path,
) -> None:
    store = GpuLeaseStore(context=_context(tmp_path), host="test-host")
    acquired = store.acquire(
        (0,),
        owner_id="controller-a",
        job_id="job-a",
        run_id="run-a",
        stage_number=4,
        pid=999_999,
    )
    with pytest.raises(BackendContractError, match="已由 EasyDesign"):
        store.acquire(
            (0,),
            owner_id="controller-b",
            job_id="job-b",
            run_id="run-b",
            stage_number=6,
            pid=999_998,
        )
    heartbeat = store.heartbeat(acquired)
    released = store.release(heartbeat)
    assert released[0].status == "released"
    paths = sorted(
        (tmp_path / "runtime/state/gpu-leases/test-host/gpu-000").glob(
            "revision-*.json"
        )
    )
    assert len(paths) == 3
    assert paths[0].read_bytes()


def test_abandoned_stale_lease_expires_without_deleting_history(
    tmp_path: Path,
) -> None:
    store = GpuLeaseStore(
        context=_context(tmp_path),
        host="test-host",
        stale_after_seconds=1,
    )
    started = datetime(2026, 8, 1, tzinfo=UTC)
    store.acquire(
        (0,),
        owner_id="controller-a",
        job_id="job-a",
        run_id="run-a",
        stage_number=4,
        pid=999_999,
        now=started,
    )
    inventory = store.inventory(
        (_gpu(0),),
        target=LocalCurrentHostTarget(),
        max_memory_used_mib=1024,
        max_utilization_percent=10,
        now=started + timedelta(seconds=2),
    )
    assert inventory.selected_devices == (0,)
    assert store.latest(0) is not None
    assert store.latest(0).status == "expired"  # type: ignore[union-attr]
