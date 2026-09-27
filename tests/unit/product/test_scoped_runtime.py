from __future__ import annotations

from pathlib import Path

import pytest

from easydesign.backends.executors.local_multi_gpu import GpuResourceSnapshot
from easydesign.core import BackendContractError, ConfigurationError
from easydesign.execution_scope import ExecutionScope
from easydesign.orchestration.execution_targets import GpuLeaseStore, LocalCurrentHostTarget
from easydesign.orchestration.profile import (
    ProtenixV2Runtime,
    RuntimeBackends,
    RuntimeProfile,
    load_runtime_profile,
)
from easydesign.product.device_pool import ProductDevicePool
from easydesign.product.resource_control import Admission
from easydesign.workspace_context import WorkspaceContext


def context(tmp_path: Path) -> WorkspaceContext:
    (tmp_path / "easydesign-workspace.yaml").write_text('schema_version: "0.1"\n')
    value = WorkspaceContext.from_root(tmp_path)
    value.ensure_layout()
    return value


def execution(
    base: WorkspaceContext, actor: str, grant: str, device: int, *, allocate: bool = True
) -> WorkspaceContext:
    scoped = base.with_execution_scope(
        ExecutionScope(
            scope_id="team-" + "c" * 32,
            actor_id="user-" + actor * 32,
            purpose="scientific",
            grant_id="grant-" + grant * 32,
            devices=(device,),
        )
    )
    if allocate:
        admission = Admission(
            id="grant-" + grant * 32,
            scope_id="team-" + "c" * 32,
            actor_id="user-" + actor * 32,
            scientific_actor_id="user-" + actor * 32,
            request_id="request-fixture-0001",
            kind="scientific",
            state="queued",
            gpu_slots=1,
            max_candidates=2,
            created_at=0,
            updated_at=0,
        )
        snapshot = GpuResourceSnapshot(
            device=device,
            name="fixture",
            uuid=f"GPU-{device}",
            memory_total_mib=40000,
            memory_used_mib=0,
            utilization_percent=0,
        )
        assert ProductDevicePool(base).allocate(admission, (snapshot,)) is not None
    return scoped


def test_scope_profile_keeps_verified_shared_assets_but_uses_own_runs_and_gpu(tmp_path):
    base = context(tmp_path)
    profile = RuntimeProfile(
        profile_id="fixture",
        runs_root=base.runs_root,
        backends=RuntimeBackends(
            protenix_v2=ProtenixV2Runtime(
                executable=base.runtime_root / "envs/protenix/bin/python",
                model_root=base.runtime_root / "models/protenix",
                model_checkpoint=base.runtime_root / "models/protenix/checkpoint.pt",
            )
        ),
    )
    base.profile_path.write_text(profile.model_dump_json())
    original = base.profile_path.read_bytes()
    scoped = execution(base, "a", "a", 2)
    with scoped.activate():
        loaded = load_runtime_profile()
    assert loaded.profile.runs_root == scoped.runs_root
    assert loaded.profile.backends.protenix_v2.model_root == base.runtime_root / "models/protenix"
    assert loaded.profile.backends.protenix_v2.cuda_visible_devices == "2"
    assert base.profile_path.read_bytes() == original
    assert load_runtime_profile(base.profile_path).profile.runs_root == base.runs_root


def test_scoped_profile_cannot_select_a_user_writable_profile(tmp_path):
    base = context(tmp_path)
    profile = RuntimeProfile(profile_id="fixture", runs_root=base.runs_root)
    base.profile_path.write_text(profile.model_dump_json())
    scoped = execution(base, "a", "a", 0)
    scoped.ensure_layout()
    forged = scoped.runtime_root / "forged-profile.yaml"
    forged.write_text(profile.model_dump_json())
    with scoped.activate(), pytest.raises(ConfigurationError, match="controller runtime profile"):
        load_runtime_profile(forged)


def test_scoped_gpu_lease_is_shared_pool_but_cannot_escape_or_release_another_grant(tmp_path):
    base = context(tmp_path)
    alice, bob = execution(base, "a", "a", 0), execution(base, "b", "b", 0, allocate=False)
    a, b = GpuLeaseStore(context=alice), GpuLeaseStore(context=bob)
    assert a.root == b.root == GpuLeaseStore(context=base).root
    snapshots = tuple(
        GpuResourceSnapshot(
            device=device,
            name="fixture",
            uuid=f"GPU-{device}",
            memory_total_mib=40_000,
            memory_used_mib=0,
            utilization_percent=0,
        )
        for device in (0, 1)
    )
    inventory = a.inventory(
        snapshots,
        target=LocalCurrentHostTarget(),
        max_memory_used_mib=100,
        max_utilization_percent=10,
    )
    assert inventory.selected_devices == (0,)
    with pytest.raises(ConfigurationError):
        a.acquire((1,), owner_id="owner", job_id="job", run_id="run", stage_number=4)
    leases = a.acquire((0,), owner_id="owner", job_id="job", run_id="run", stage_number=4)
    with pytest.raises(BackendContractError):
        b.release(leases)
    with pytest.raises(BackendContractError):
        b.heartbeat(leases)
    assert a.release(leases)[0].status == "released"
