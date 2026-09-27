"""Genuine detached-worker execution: real subprocesses through the scoped stack.

These tests spawn the actual `easydesign.product.scoped_worker` via
`ResourceSupervisor.launch`. Model credentials are deliberately absent, so the
scientific operation fails honestly (AgentBoundaryError) instead of mocking a
success; the control-plane lifecycle (spawn, assignment, scope, journal,
admission, device release) is what is verified here.
"""

from __future__ import annotations

import json
import os
import signal
import time
from pathlib import Path

import pytest

from easydesign.backends.executors.local_multi_gpu import GpuResourceSnapshot
from easydesign.execution_scope import read_device_allocations
from easydesign.product.accounts import AccountStore
from easydesign.product.contracts import CreateProject
from easydesign.product.domain import NativeGateway
from easydesign.product.resource_supervisor import ResourceSupervisor, process_identity
from easydesign.product.tenancy import MultiUserRuntime
from easydesign.runtime_guard import landlock_abi_version
from easydesign.workspace_context import WorkspaceContext

PASSWORD = "Fixture-password-2026!"
GOAL = "Design a VHH binder against a fixture target with honest failures."
POLL_SECONDS = 0.5
WAIT_SECONDS = 150.0


def wait_until(predicate, *, timeout: float = WAIT_SECONDS, message: str = "condition"):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(POLL_SECONDS)
    raise AssertionError(f"Timed out waiting for {message}")


@pytest.fixture
def detached(tmp_path: Path, monkeypatch):
    try:
        landlock_abi_version()
    except OSError:
        pytest.skip("Host cannot run the Linux Landlock write sandbox")
    (tmp_path / "easydesign-workspace.yaml").write_text('schema_version: "0.1"\n')
    (tmp_path / "models.yaml").write_text(
        "default:\n"
        "  provider: openai\n"
        "  model: fixture-model\n"
        "  secret_env: EASYDESIGN_FIXTURE_KEY\n"
    )
    # The scientific credential is intentionally absent everywhere.
    monkeypatch.delenv("EASYDESIGN_FIXTURE_KEY", raising=False)
    context = WorkspaceContext.from_root(tmp_path)
    context.ensure_layout()
    store = AccountStore(context.runtime_root / "state/accounts/accounts.sqlite")
    admin = store.bootstrap_admin("admin", PASSWORD, "管理员")
    alice = store.register("alice", PASSWORD, "Alice")
    bob = store.register("bob", PASSWORD, "Bob")
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

    runtime = MultiUserRuntime(
        context, store, lambda scoped: NativeGateway(scoped, tmp_path / "models.yaml")
    )
    control = ResourceSupervisor(runtime, probe=Probe())
    runtime.launcher = control.launch
    try:
        yield control, runtime, store, admin, alice, bob, context
    finally:
        for admission in runtime.resources.active():
            pid, start = admission.worker_pid, admission.worker_start
            if pid is not None and start is not None and process_identity(pid) == start:
                try:
                    os.kill(pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass


def scoped_state(context: WorkspaceContext, scope_id: str) -> Path:
    return context.shared_runtime_root / "scopes" / scope_id / "state"


def read_request(runtime: MultiUserRuntime, scope_id: str, request_id: str) -> dict | None:
    """Read the scoped request journal directly; the worker owns its lifecycle."""
    from easydesign.product.journal import RequestJournal

    path = scoped_state(runtime.context, scope_id) / "product/requests.sqlite"
    if not path.is_file():
        return None
    journal = RequestJournal(path)
    try:
        return journal.get(request_id)
    finally:
        journal.close()


def submit_create(runtime: MultiUserRuntime, user, request_id: str):
    with runtime.bind(user, user.id) as service:
        return service.create(
            CreateProject(request_id=request_id, title="Detached worker goal", goal=GOAL)
        )


def test_detached_worker_runs_the_scoped_lifecycle_and_fails_honestly(detached):
    control, runtime, store, admin, alice, _bob, context = detached
    request_id = "lifecycle-request-0001"
    accepted = submit_create(runtime, alice, request_id)
    assert accepted["state"] == "accepted"

    admission = runtime.resources.latest(alice.id, request_id)
    assert admission is not None
    assert admission.state == "queued"
    assert admission.worker_pid not in (None, os.getpid())
    assert process_identity(admission.worker_pid) == admission.worker_start

    control.launch(admission, None)  # idempotent: the live worker blocks a respawn
    assert runtime.resources.latest(alice.id, request_id).worker_pid == admission.worker_pid

    control.tick()
    running = runtime.resources.get(admission.id)
    assert running.state == "running" and running.devices == (0,)
    allocations = read_device_allocations(control.pool.root)
    assert allocations[0].status == "reserved" and allocations[0].devices == (0,)

    wait_until(
        lambda: process_identity(admission.worker_pid) is None,
        message="detached worker to finish",
    )
    row = read_request(runtime, alice.id, request_id)
    assert row is not None and row["state"] == "failed"
    assert row["result"]["code"] == "AgentBoundaryError"  # honest missing credential
    assert row["result"].get("status") is None  # no fabricated scientific success

    control.tick()
    finished = runtime.resources.get(admission.id)
    assert finished.state == "failed"
    assert finished.reason == "worker_finished_without_success"
    assert read_device_allocations(control.pool.root)[0].status == "released"

    log = (
        context.shared_runtime_root / "scopes" / alice.id / "logs/product" / (admission.id + ".log")
    )
    assert log.is_file() and log.stat().st_size > 0

    # The worker wrote only inside its scoped roots.
    project_root = context.projects_root / "scopes" / alice.id / accepted["project"]
    assert (project_root / "metadata").is_dir()
    foreign = context.projects_root / "scopes"
    assert sorted(p.name for p in foreign.iterdir()) == [alice.id]


def test_revocation_before_assignment_stops_the_queued_worker(detached):
    control, runtime, store, admin, alice, _bob, _context = detached
    request_id = "revoked-request-0001"
    submit_create(runtime, alice, request_id)
    admission = runtime.resources.latest(alice.id, request_id)
    assert admission is not None and admission.state == "queued"
    assert process_identity(admission.worker_pid) == admission.worker_start

    store.update_user(admin, alice.id, status="suspended")
    control.tick()
    cancelled = runtime.resources.get(admission.id)
    assert cancelled.state == "cancelled"
    assignment = json.loads(control.pool.assignment_path(admission.id).read_text())
    assert assignment["cancelled"] and assignment["code"] == "authorization_revoked"
    assert read_device_allocations(control.pool.root) == ()

    wait_until(
        lambda: process_identity(admission.worker_pid) is None,
        message="revoked worker to exit",
    )
    row = read_request(runtime, alice.id, request_id)
    assert row is not None and row["state"] == "failed"
    assert row["result"]["code"] == "authorization_revoked"

    control.tick()
    assert runtime.resources.get(admission.id).state == "cancelled"
    # The suspended account never gained a project or a device reservation.
    assert read_device_allocations(control.pool.root) == ()
    row = read_request(runtime, alice.id, request_id)
    assert row is not None and row["result"]["code"] == "authorization_revoked"


def test_controller_crash_after_spawn_abandons_the_worker_cleanly(detached, monkeypatch):
    control, runtime, store, admin, alice, _bob, _context = detached
    real_transition = runtime.resources.transition

    def crash_before_publication(grant_id, state, **kwargs):
        if state == "queued" and kwargs.get("worker_pid") is not None:
            raise RuntimeError("simulated controller crash between Popen and PID publish")
        return real_transition(grant_id, state, **kwargs)

    monkeypatch.setattr(runtime.resources, "transition", crash_before_publication)
    request_id = "crash-request-00000001"
    with runtime.bind(alice, alice.id) as service:
        admission, _ = runtime.resources.reserve(
            alice, alice.id, request_id, {"operation": "create", "title": "t", "goal": GOAL}
        )
        journal = service.journal()
        try:
            journal.reserve(
                "workbench-fixture",
                {"operation": "create", "request_id": request_id, "title": "t", "goal": GOAL},
            )
        finally:
            journal.close()
        try:
            control.launch(admission, service)
        except RuntimeError:
            pass  # the crash we wanted: worker spawned, PID never published
    monkeypatch.undo()
    stranded = runtime.resources.get(admission.id)
    assert stranded.state == "reserved" and stranded.worker_pid is None

    # The orphaned worker is alive: it owns the request lock and reports waiting.
    lock_path = scoped_state(runtime.context, alice.id) / "product/workers" / (request_id + ".lock")
    wait_until(
        lambda: (
            (row := read_request(runtime, alice.id, request_id)) is not None
            and bool((row["result"] or {}).get("resource_waiting"))
        ),
        message="orphaned worker to start waiting",
    )

    control.tick()
    assert runtime.resources.get(admission.id).state == "reserved"
    # The controller publishes no PID; after the bounded 30s window the admission
    # fails while the orphaned worker exits on its own instead of idling an hour.
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        control.tick()
        if runtime.resources.get(admission.id).state == "failed":
            break
        time.sleep(1.0)
    failed = runtime.resources.get(admission.id)
    assert failed.state == "failed" and failed.reason == "worker_not_published"

    import fcntl

    def worker_released() -> bool:
        if not lock_path.is_file():
            return False
        with lock_path.open("a") as handle:
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return False
            fcntl.flock(handle, fcntl.LOCK_UN)
            return True

    wait_until(worker_released, message="orphaned worker to observe the failed admission")
    row = read_request(runtime, alice.id, request_id)
    assert row is not None and row["state"] == "accepted"  # resume path stays available


def test_two_detached_scientific_workers_get_distinct_devices(detached):
    control, runtime, _store, _admin, alice, bob, _context = detached
    alice_id = "parallel-alice-000001"
    bob_id = "parallel-bob-0000001"
    submit_create(runtime, alice, alice_id)
    submit_create(runtime, bob, bob_id)
    first = runtime.resources.latest(alice.id, alice_id)
    second = runtime.resources.latest(bob.id, bob_id)
    assert first is not None and second is not None
    assert process_identity(first.worker_pid) == first.worker_start
    assert process_identity(second.worker_pid) == second.worker_start

    control.tick()
    running_first = runtime.resources.get(first.id)
    running_second = runtime.resources.get(second.id)
    assert running_first.state == "running" and running_second.state == "running"
    assert running_first.devices == (0,) and running_second.devices == (1,)

    for admission in (first, second):
        wait_until(
            lambda admission=admission: process_identity(admission.worker_pid) is None,
            message=f"worker {admission.id} to finish",
        )
    control.tick()
    states = {runtime.resources.get(a.id).state for a in (first, second)}
    assert states == {"failed"}
    released = {r.status for r in read_device_allocations(control.pool.root)}
    assert released == {"released"}
