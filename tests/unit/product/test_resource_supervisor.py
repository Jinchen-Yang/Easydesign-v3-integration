from __future__ import annotations

import json
import os

import pytest

from easydesign.backends.executors.local_multi_gpu import GpuResourceSnapshot
from easydesign.core import BackendContractError, ConfigurationError
from easydesign.execution_scope import ExecutionScope, load_scope, read_device_allocations
from easydesign.orchestration.execution_targets import GpuLeaseStore, LocalCurrentHostTarget
from easydesign.product.accounts import AccountStore
from easydesign.product.artifacts import immutable_json
from easydesign.product.domain import NativeGateway
from easydesign.product.resource_supervisor import ResourceSupervisor, process_identity
from easydesign.product.tenancy import MultiUserRuntime
from easydesign.workspace_context import WorkspaceContext


@pytest.fixture
def supervisor(tmp_path):
    (tmp_path / "easydesign-workspace.yaml").write_text('schema_version: "0.1"\n')
    context = WorkspaceContext.from_root(tmp_path)
    context.ensure_layout()
    store = AccountStore(context.runtime_root / "state/accounts/accounts.sqlite")
    password = "Fixture-password-2026!"
    admin = store.bootstrap_admin("admin", password, "管理员")
    alice = store.register("alice", password, "Alice")
    bob = store.register("bob", password, "Bob")
    for user in (alice, bob):
        store.update_user(admin, user.id, status="active")
    snapshots = tuple(
        GpuResourceSnapshot(
            device=d,
            name="fixture",
            uuid=f"GPU-{d}",
            memory_total_mib=40000,
            memory_used_mib=0,
            utilization_percent=0,
        )
        for d in (0, 1)
    )

    class Probe:
        def snapshots(self):
            return snapshots

    runtime = MultiUserRuntime(context, store, lambda c: NativeGateway(c, tmp_path / "models.yaml"))
    control = ResourceSupervisor(runtime, probe=Probe())
    return control, store, admin, alice, bob, snapshots


def queued(control, user, request, kind="scientific"):
    grant, _ = control.ledger.reserve(user, user.id, request, {"fixture": request}, kind=kind)
    return control.ledger.transition(
        grant.id, "queued", worker_pid=os.getpid(), worker_start=process_identity(os.getpid())
    )


def test_two_users_receive_distinct_devices_and_native_leases_respect_reservations(supervisor):
    control, _store, _admin, alice, bob, snapshots = supervisor
    a = queued(control, alice, "alice-request-0001")
    b = queued(control, bob, "bob-request-000001")
    control.tick()
    assert control.ledger.get(a.id).devices == (0,)
    assert control.ledger.get(b.id).devices == (1,)
    ordinary = GpuLeaseStore(context=control.context)
    assert (
        ordinary.inventory(
            snapshots,
            target=LocalCurrentHostTarget(),
            max_memory_used_mib=2048,
            max_utilization_percent=10,
        ).selected_devices
        == ()
    )
    with pytest.raises(BackendContractError):
        ordinary.acquire(
            (0,), owner_id="outside", job_id="outside", run_id="outside", stage_number=4
        )
    assignment = json.loads(control.pool.assignment_path(a.id).read_text())
    scope = load_scope(
        runtime_root=control.context.runtime_root,
        declaration_path=control.context.declaration_path,
        path=control.context.root / assignment["scope_file"],
    )
    native = GpuLeaseStore(context=control.context.with_execution_scope(scope))
    leases = native.acquire(
        (0,), owner_id="native", job_id="native", run_id="native", stage_number=4
    )
    native.release(leases)
    control.pool.release(a.id)
    with pytest.raises(ConfigurationError):
        native.acquire((0,), owner_id="stale", job_id="stale", run_id="stale", stage_number=4)


def test_suspended_account_is_cancelled_before_device_admission(supervisor):
    control, store, admin, alice, _bob, _snapshots = supervisor
    admission = queued(control, alice, "cancel-request-0001")
    store.update_user(admin, alice.id, status="suspended")
    control.tick()
    assert control.ledger.get(admission.id).state == "cancelled"
    assert json.loads(control.pool.assignment_path(admission.id).read_text())["cancelled"]
    assert read_device_allocations(control.pool.root) == ()


def test_gpu_probe_failure_does_not_block_cpu_only_conversations(supervisor):
    control, _store, _admin, alice, bob, _snapshots = supervisor
    scientific = queued(control, alice, "science-request-001")
    conversation = queued(control, bob, "conversation-00001", "conversation")

    class Unavailable:
        def snapshots(self):
            raise BackendContractError("fixture GPU unavailable")

    control.probe = Unavailable()
    control.tick()
    assert control.ledger.get(scientific.id).state == "queued"
    assert control.ledger.get(conversation.id).state == "running"
    assert control.ledger.get(conversation.id).devices == ()


def test_published_assignment_is_reconciled_after_controller_restart(supervisor):
    control, store, admin, alice, _bob, snapshots = supervisor
    admission = queued(control, alice, "restart-request-001")
    allocation = control.pool.allocate(admission, snapshots)
    scope = control.context.with_execution_scope(
        ExecutionScope(
            scope_id=alice.id,
            actor_id=alice.id,
            grant_id=admission.id,
            purpose="scientific",
            devices=allocation.devices,
        )
    )
    path = control.pool.assignment_path(admission.id)
    immutable_json(
        path,
        {
            "grant_id": admission.id,
            "scope_file": str(scope.execution_scope_path.relative_to(control.context.root)),
        },
    )
    before = path.read_bytes()
    store.update_user(admin, alice.id, status="suspended")
    control.tick()
    assert path.read_bytes() == before
    assert control.ledger.get(admission.id).state == "running"


def test_lost_transport_worker_does_not_release_a_running_native_job(supervisor, monkeypatch):
    from easydesign.product import resource_supervisor

    control, _store, _admin, alice, _bob, snapshots = supervisor
    admission = queued(control, alice, "held-request-000001")
    control.pool.allocate(admission, snapshots)
    monkeypatch.setattr(resource_supervisor, "process_identity", lambda _pid: None)
    monkeypatch.setattr(resource_supervisor, "native_active", lambda *_args: True)
    control.tick()
    assert control.ledger.get(admission.id).state == "held"
    assert read_device_allocations(control.pool.root)[0].status == "reserved"
    monkeypatch.setattr(resource_supervisor, "native_active", lambda *_args: False)
    control.tick()
    assert control.ledger.get(admission.id).state == "failed"
    assert read_device_allocations(control.pool.root)[0].status == "released"
