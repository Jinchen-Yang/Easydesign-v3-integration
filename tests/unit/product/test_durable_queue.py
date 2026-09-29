"""Persistent admission tests; synthetic workspaces, no models or GPU execution."""

from __future__ import annotations

import fcntl
import json
import os
import select
import sqlite3
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import UUID

import pytest

from easydesign.backends.executors.local_multi_gpu import GpuResourceSnapshot
from easydesign.product.accounts import AccountStore, ResourceLimits
from easydesign.product.artifacts import immutable_json
from easydesign.product.contracts import CreateProject, ProductError
from easydesign.product.domain import NativeGateway
from easydesign.product.rabbit_chat import RabbitChatService
from easydesign.product.resource_control import ResourceLedger
from easydesign.product.resource_supervisor import ResourceSupervisor, process_identity
from easydesign.product.tenancy import MultiUserRuntime
from easydesign.workspace_context import WorkspaceContext


@pytest.fixture
def queue(tmp_path, monkeypatch):
    (tmp_path / "easydesign-workspace.yaml").write_text('schema_version: "0.1"\n')
    (tmp_path / "models.yaml").write_text(
        "default:\n  provider: openai\n  model: fixture\n"
        "  secret_env: EASYDESIGN_QUEUE_FIXTURE_KEY\n"
    )
    monkeypatch.delenv("EASYDESIGN_QUEUE_FIXTURE_KEY", raising=False)
    context = WorkspaceContext.from_root(tmp_path)
    context.ensure_layout()
    accounts = AccountStore(context.runtime_root / "state/accounts/accounts.sqlite")
    password = "Queue-fixture-password-2026!"
    admin = accounts.bootstrap_admin("admin", password, "Admin")
    alice = accounts.register("alice", password, "Alice")
    bob = accounts.register("bob", password, "Bob")
    for user in (alice, bob):
        accounts.update_user(admin, user.id, status="active")
    runtime = MultiUserRuntime(
        context, accounts, lambda c: NativeGateway(c, tmp_path / "models.yaml")
    )

    class Busy:
        def snapshots(self):
            return ()

    control = ResourceSupervisor(runtime, probe=Busy())
    runtime.launcher = control.launch
    return runtime, control, accounts, admin, alice, bob


def create(runtime, user, request_id="durable-request-0001"):
    with runtime.bind(user, user.id) as service:
        return service.create(
            CreateProject(request_id=request_id, title="Queue fixture", goal="A synthetic target")
        )


def prepared_admission(runtime, user, request_id):
    """A real durable intent, before launch and without a held command flock."""
    with runtime.bind(user, user.id) as service:
        admission, _ = runtime.resources.reserve(
            user,
            user.id,
            request_id,
            {"operation": "create"},
            dispatch_channel="scoped_worker",
        )
        journal = service.journal()
        try:
            journal.reserve("fixture-project", {"request_id": request_id, "operation": "create"})
        finally:
            journal.close()
    return admission


def launch_direct(runtime, control, user, admission):
    with runtime.bind(user, user.id) as service:
        control.launch(admission, service)


def test_unrelated_direct_launch_finishes_while_another_config_is_published(queue, monkeypatch):
    runtime, control, _accounts, _admin, alice, bob = queue
    from easydesign.product import resource_control, resource_supervisor

    # Stable, different stripe inputs: no probabilistic UUID collision in this test.
    identities = iter((UUID(int=1), UUID(int=2)))
    monkeypatch.setattr(resource_control, "uuid4", lambda: next(identities))
    first = prepared_admission(runtime, alice, "direct-first-request-01")
    second = prepared_admission(runtime, bob, "direct-second-request-1")
    published, finish_first = threading.Event(), threading.Event()
    publish = resource_supervisor.immutable_json

    def paused_publication(path, value):
        publish(path, value)
        if path.name == first.id + ".json" and path.parent.name == "worker-config":
            published.set()
            assert finish_first.wait(10), "Fixture launch was not released"

    monkeypatch.setattr(resource_supervisor, "immutable_json", paused_publication)
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: pytest.fail("Scientific spawn"))
    with ThreadPoolExecutor(max_workers=2) as pool:
        preparing = pool.submit(launch_direct, runtime, control, alice, first)
        try:
            assert published.wait(10)
            assert runtime.resources.get(first.id).state == "reserved"
            independent = pool.submit(launch_direct, runtime, control, bob, second)
            independent.result(timeout=3)
            assert runtime.resources.get(second.id).state == "queued"
            assert not preparing.done()
        finally:
            finish_first.set()
        preparing.result(timeout=10)
    assert runtime.resources.get(first.id).state == "queued"


def test_direct_launch_fences_duplicate_and_tick_until_the_queued_commit(queue, monkeypatch):
    runtime, control, _accounts, _admin, alice, _bob = queue
    from easydesign.product import resource_supervisor

    admission = prepared_admission(runtime, alice, "direct-same-grant-window")
    published, finish_first = threading.Event(), threading.Event()
    duplicate_started, tick_started = threading.Event(), threading.Event()
    publish = resource_supervisor.immutable_json
    active = runtime.resources.active
    publications, spawns = [], []

    def paused_publication(path, value):
        publish(path, value)
        if path.name == admission.id + ".json" and path.parent.name == "worker-config":
            publications.append(path.read_bytes())
            published.set()
            assert finish_first.wait(10), "Fixture launch was not released"

    def duplicate():
        duplicate_started.set()
        launch_direct(runtime, control, alice, admission)

    def observed_active():
        tick_started.set()
        return active()

    class Free:
        def snapshots(self):
            return (
                GpuResourceSnapshot(
                    device=0,
                    name="fixture",
                    uuid="GPU-fixture",
                    memory_total_mib=40000,
                    memory_used_mib=0,
                    utilization_percent=0,
                ),
            )

    class NoScientificProcess:
        def __init__(self, argv, **kwargs):
            spawns.append(argv)
            self.pid = os.getpid()  # A live identity, without executing any worker/model.

    control.probe = Free()
    monkeypatch.setattr(resource_supervisor, "immutable_json", paused_publication)
    monkeypatch.setattr(runtime.resources, "active", observed_active)
    monkeypatch.setattr(subprocess, "Popen", NoScientificProcess)
    with ThreadPoolExecutor(max_workers=3) as pool:
        preparing = pool.submit(launch_direct, runtime, control, alice, admission)
        try:
            assert published.wait(10)
            repeated = pool.submit(duplicate)
            ticking = pool.submit(control.tick)
            assert duplicate_started.wait(10) and tick_started.wait(10)
            with pytest.raises(TimeoutError):
                repeated.result(timeout=0.2)
            with pytest.raises(TimeoutError):
                ticking.result(timeout=0.2)
            assert runtime.resources.get(admission.id).state == "reserved"
            assert not spawns
        finally:
            finish_first.set()
        preparing.result(timeout=10)
        repeated.result(timeout=10)
        ticking.result(timeout=10)
    assert len(publications) == 1 and len(spawns) == 1
    running = runtime.resources.get(admission.id)
    assert running.state == "running" and running.worker_pid == os.getpid()
    control.tick()
    assert runtime.resources.get(admission.id).state == "running"
    assert len(spawns) == 1


@pytest.mark.parametrize("fail_first", [False, True])
def test_stripe_collision_only_serializes_and_preparation_errors_release_the_lock(
    queue, monkeypatch, fail_first
):
    runtime, control, _accounts, _admin, alice, bob = queue
    from easydesign.product import resource_supervisor

    first = prepared_admission(runtime, alice, "collision-first-request")
    second = prepared_admission(runtime, bob, "collision-second-request")
    # Deliberately force a collision, without replacing either public operation.
    collision = threading.RLock()
    monkeypatch.setattr(control, "_grant_locks", (collision,) * 128)
    published, finish_first, second_started = (threading.Event() for _ in range(3))
    publish = resource_supervisor.immutable_json
    first_prepared = False

    def paused_publication(path, value):
        nonlocal first_prepared
        publish(path, value)
        if (
            not first_prepared
            and path.name == first.id + ".json"
            and path.parent.name == "worker-config"
        ):
            first_prepared = True
            published.set()
            assert finish_first.wait(10), "Fixture launch was not released"
            if fail_first:
                raise OSError("fixture failure after publication")

    def second_launch():
        second_started.set()
        launch_direct(runtime, control, bob, second)

    monkeypatch.setattr(resource_supervisor, "immutable_json", paused_publication)
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: pytest.fail("Scientific spawn"))
    with ThreadPoolExecutor(max_workers=2) as pool:
        preparing = pool.submit(launch_direct, runtime, control, alice, first)
        try:
            assert published.wait(10)
            colliding = pool.submit(second_launch)
            assert second_started.wait(10)
            with pytest.raises(TimeoutError):
                colliding.result(timeout=0.2)
            assert runtime.resources.get(second.id).state == "reserved"
        finally:
            finish_first.set()
        if fail_first:
            with pytest.raises(OSError, match="fixture failure"):
                preparing.result(timeout=10)
        else:
            preparing.result(timeout=10)
        colliding.result(timeout=10)
        # A new thread can acquire the same stripe even after the first raises.
        pool.submit(launch_direct, runtime, control, alice, first).result(timeout=10)
    assert runtime.resources.get(first.id).state == "queued"
    assert runtime.resources.get(second.id).state == "queued"


@pytest.mark.parametrize("change", ["cancel", "revoke"])
def test_direct_launch_does_not_undo_cancellation_or_revocation_while_preparing(
    queue, monkeypatch, change
):
    runtime, control, accounts, admin, alice, _bob = queue
    from easydesign.product import resource_supervisor

    admission = prepared_admission(runtime, alice, "direct-authority-window")
    published, finish_first = threading.Event(), threading.Event()
    publish = resource_supervisor.immutable_json

    def paused_publication(path, value):
        publish(path, value)
        if path.name == admission.id + ".json" and path.parent.name == "worker-config":
            published.set()
            assert finish_first.wait(10), "Fixture launch was not released"

    monkeypatch.setattr(resource_supervisor, "immutable_json", paused_publication)
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: pytest.fail("Scientific spawn"))
    with ThreadPoolExecutor(max_workers=1) as pool:
        preparing = pool.submit(launch_direct, runtime, control, alice, admission)
        try:
            assert published.wait(10)
            if change == "cancel":
                with runtime.bind(alice, alice.id) as service:
                    service.cancel_queued(admission.request_id)
            else:
                accounts.update_user(admin, alice.id, status="suspended")
        finally:
            finish_first.set()
        if change == "cancel":
            with pytest.raises(ProductError) as terminal:
                preparing.result(timeout=10)
            assert terminal.value.code == "admission_terminal"
        else:
            preparing.result(timeout=10)
    control.tick()
    current = runtime.resources.get(admission.id)
    expected = "queue_cancelled" if change == "cancel" else "authorization_revoked"
    assert current.state == "cancelled" and current.worker_pid is None
    assert current.reason == expected
    with runtime.bind(admin, alice.id) as observer:
        request = observer.request(admission.request_id)
    assert request["state"] == "failed" and request["result"]["code"] == expected


def test_unavailable_gpu_persists_queue_without_starting_a_process(queue, monkeypatch):
    runtime, control, accounts, _admin, alice, _bob = queue
    from easydesign.product import resource_supervisor

    def unexpected_spawn(*args, **kwargs):
        pytest.fail("A queued request must not start a waiting process")

    monkeypatch.setattr(resource_supervisor.subprocess, "Popen", unexpected_spawn)
    accepted = create(runtime, alice)
    admission = runtime.resources.latest(alice.id, accepted["id"])
    assert admission.state == "queued" and admission.worker_pid is None
    # Queue waiting is not worker startup/execution time, even beyond one hour.
    monkeypatch.setattr(accounts, "clock", lambda: time.time() + 7200)
    with runtime.bind(alice, alice.id) as service:
        journal = service.journal()
        journal.db.execute("UPDATE requests SET updated=updated-7200")
        journal.db.commit()
        journal.close()
        control.tick()
        row = service.request(accepted["id"])
        snapshot = service.snapshot(accepted["project"])
    assert row["state"] == "accepted"
    assert row["result"]["queue"]["state"] == "queued"
    assert row["result"]["queue"]["position"] == 1
    assert snapshot["requests"][0]["result"]["queue"] == row["result"]["queue"]
    assert runtime.resources.get(admission.id).state == "queued"


def test_tick_reuses_one_scoped_service_but_rechecks_authority_on_the_next_tick(queue, monkeypatch):
    runtime, control, accounts, admin, alice, _bob = queue
    accepted = create(runtime, alice)
    grant = runtime.resources.latest(alice.id, accepted["id"])
    constructions = []
    make_service = control._service

    def observed_service(admission):
        constructions.append(admission.id)
        return make_service(admission)

    monkeypatch.setattr(control, "_service", observed_service)
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: pytest.fail("Scientific spawn"))
    control.tick()
    assert constructions == [grant.id]
    assert runtime.resources.get(grant.id).state == "queued"
    accounts.update_user(admin, alice.id, status="suspended")
    control.tick()
    assert constructions == [grant.id, grant.id]
    assert runtime.resources.get(grant.id).state == "cancelled"
    assert runtime.resources.get(grant.id).reason == "authorization_revoked"


def test_another_admission_can_finish_enqueue_between_tick_items(queue, monkeypatch):
    runtime, control, accounts, admin, alice, bob = queue
    accounts.set_limits(admin, alice.id, ResourceLimits(max_active_jobs=2, max_gpu_devices=2))
    create(runtime, alice)
    create(runtime, alice, "alice-second-request-01")
    active = runtime.resources.active
    between, finish_tick = threading.Event(), threading.Event()
    observed = []
    initial = [admission.id for admission in active()]

    class BetweenItems(list):
        def __iter__(self):
            for index, admission in enumerate(super().__iter__()):
                if index == 1:
                    between.set()
                    assert finish_tick.wait(10), "Fixture tick was not released"
                observed.append(admission.id)
                yield admission

    class EmptyProbe:
        calls = 0

        def snapshots(self):
            self.calls += 1
            return ()

    probe = EmptyProbe()
    control.probe = probe
    monkeypatch.setattr(runtime.resources, "active", lambda: BetweenItems(active()))
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: pytest.fail("Scientific spawn"))
    with ThreadPoolExecutor(max_workers=2) as pool:
        ticking = pool.submit(control.tick)
        try:
            assert between.wait(10), "Tick did not reach the between-admission boundary"
            enqueue = pool.submit(create, runtime, bob, "bob-interleaved-request")
            accepted = enqueue.result(timeout=3)
            assert accepted["state"] == "accepted"
            assert not ticking.done()
        finally:
            finish_tick.set()
        ticking.result(timeout=10)
    assert observed == initial  # A new admission joins the next ordered snapshot.
    assert probe.calls == 1
    control.tick()
    assert probe.calls == 2  # Observations must not survive into another tick.
    assert runtime.resources.latest(bob.id, accepted["id"]).state == "queued"


def test_tick_keeps_same_instance_and_other_controller_exclusion_between_items(queue, monkeypatch):
    runtime, control, accounts, admin, alice, _bob = queue
    accounts.set_limits(admin, alice.id, ResourceLimits(max_active_jobs=2, max_gpu_devices=2))
    create(runtime, alice)
    create(runtime, alice, "alice-second-request-01")
    between, finish_tick = threading.Event(), threading.Event()
    manual_started, manual_entered = threading.Event(), threading.Event()
    active = runtime.resources.active

    class PausedBackground(list):
        def __iter__(self):
            for index, admission in enumerate(super().__iter__()):
                if index == 1:
                    between.set()
                    assert finish_tick.wait(10), "Fixture background tick was not released"
                yield admission

    def observed_active():
        name = threading.current_thread().name
        if name == "account-resource-admission":
            return PausedBackground(active())
        if name.startswith("manual-tick"):
            manual_entered.set()
        return active()

    def manual_tick():
        manual_started.set()
        control.tick()

    monkeypatch.setattr(runtime.resources, "active", observed_active)
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: pytest.fail("Scientific spawn"))
    control.poll_seconds = 60
    other = ResourceSupervisor(runtime, probe=control.probe)
    control.start()
    try:
        assert between.wait(10), "Background tick did not reach the between-admission boundary"
        with ThreadPoolExecutor(max_workers=1, thread_name_prefix="manual-tick") as pool:
            pending = pool.submit(manual_tick)
            try:
                assert manual_started.wait(10)
                assert not manual_entered.wait(0.2), "Same-instance tick rounds overlapped"
                assert not pending.done()
                with pytest.raises(ProductError) as busy:
                    other.tick()
                assert busy.value.code == "controller_busy"
            finally:
                finish_tick.set()
            pending.result(timeout=10)
        assert manual_entered.is_set()
    finally:
        finish_tick.set()
        control.close()
    other.tick()  # Whole-controller ownership is released only after clean shutdown.


@pytest.mark.parametrize("change", ["cancel", "revoke"])
def test_tick_rechecks_cancel_and_revocation_after_its_admission_snapshot(
    queue, monkeypatch, change
):
    runtime, control, accounts, admin, alice, bob = queue
    first = create(runtime, alice)
    second = create(runtime, bob, "bob-snapshot-race-001")
    between, finish_tick = threading.Event(), threading.Event()
    active = runtime.resources.active

    class BetweenItems(list):
        def __iter__(self):
            for index, admission in enumerate(super().__iter__()):
                if index == 1:
                    between.set()
                    assert finish_tick.wait(10), "Fixture tick was not released"
                yield admission

    monkeypatch.setattr(runtime.resources, "active", lambda: BetweenItems(active()))
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: pytest.fail("Scientific spawn"))
    with ThreadPoolExecutor(max_workers=1) as pool:
        ticking = pool.submit(control.tick)
        try:
            assert between.wait(10), "Tick did not reach the between-admission boundary"
            if change == "cancel":
                with runtime.bind(bob, bob.id) as service:
                    service.cancel_queued(second["id"])
            else:
                accounts.update_user(admin, bob.id, status="suspended")
        finally:
            finish_tick.set()
        ticking.result(timeout=10)
    assert runtime.resources.latest(alice.id, first["id"]).state == "queued"
    cancelled = runtime.resources.latest(bob.id, second["id"])
    assert cancelled.state == "cancelled" and cancelled.worker_pid is None
    expected = "queue_cancelled" if change == "cancel" else "authorization_revoked"
    assert cancelled.reason == expected
    with runtime.bind(admin, bob.id) as observer:
        row = observer.request(second["id"])
    assert row["state"] == "failed" and row["result"]["code"] == expected


def test_queued_request_reports_global_position_without_loading_all_admissions(queue, monkeypatch):
    runtime, _control, _accounts, _admin, alice, bob = queue
    create(runtime, alice)
    accepted = create(runtime, bob, "durable-request-0002")

    def unexpected_full_projection():
        pytest.fail("One queue position must not load every active admission")

    monkeypatch.setattr(runtime.resources, "active", unexpected_full_projection)
    with runtime.bind(bob, bob.id) as service:
        row = service.request(accepted["id"])
    assert row["result"]["queue"] == {
        "state": "queued",
        "position": 2,
        "reason": "waiting_for_resources",
        "cancellable": True,
    }


def test_queue_position_preserves_kind_channel_and_rowid_tie_order(queue, monkeypatch):
    runtime, _control, accounts, admin, alice, bob = queue
    for user in (alice, bob):
        accounts.set_limits(
            admin, user.id, ResourceLimits(max_active_jobs=8, max_active_chats=8, max_gpu_devices=8)
        )
    entries = [
        (alice, "scientific", "legacy", "queued", 100.0),
        (bob, "conversation", "legacy", "queued", 100.0),
        (bob, "scientific", "scoped_worker", "queued", 100.0),
        (alice, "conversation", "web_stream", "queued", 100.0),
        (alice, "scientific", "scoped_worker", "queued", 90.0),
        (bob, "conversation", "scoped_worker", "queued", 90.0),
        (bob, "scientific", "legacy", "running", 80.0),
        (alice, "conversation", "web_stream", "running", 80.0),
    ]
    grants = []
    for index, (user, kind, channel, state, created) in enumerate(entries):
        monkeypatch.setattr(accounts, "clock", lambda now=created: now)
        grant, _ = runtime.resources.reserve(
            user,
            user.id,
            f"rank-mixed-request-{index:02d}",
            {},
            kind=kind,
            dispatch_channel=channel,
        )
        grants.append(runtime.resources.transition(grant.id, state))
    assert [runtime.resources.queue_position(grant.id) for grant in grants] == [
        2,
        2,
        3,
        3,
        1,
        1,
        None,
        None,
    ]
    # This is the previous public projection's ordering, including legacy/Web rows.
    previous = runtime.resources.active()
    for grant in grants:
        waiting = [row.id for row in previous if row.state == "queued" and row.kind == grant.kind]
        expected = waiting.index(grant.id) + 1 if grant.id in waiting else None
        assert runtime.resources.queue_position(grant.id) == expected


def test_queue_position_rechecks_membership_and_returns_no_rank_for_nonqueued_targets(queue):
    runtime, _control, _accounts, _admin, alice, _bob = queue
    assert runtime.resources.queue_position("missing-admission") is None
    for index, terminal in enumerate(("released", "failed", "cancelled")):
        grant, _ = runtime.resources.reserve(
            alice, alice.id, f"rank-membership-request-{index:02d}", {}
        )
        assert runtime.resources.queue_position(grant.id) is None
        runtime.resources.transition(grant.id, "queued")
        assert runtime.resources.queue_position(grant.id) == 1
        for state in ("starting", "running", "held", terminal):
            runtime.resources.transition(grant.id, state)
            assert runtime.resources.queue_position(grant.id) is None


def test_queue_position_uses_existing_active_index_with_large_terminal_history(queue, monkeypatch):
    runtime, _control, accounts, _admin, alice, bob = queue
    first = create(runtime, alice)
    second = create(runtime, bob, "rank-index-request-002")
    first_grant = runtime.resources.latest(alice.id, first["id"])
    second_grant = runtime.resources.latest(bob.id, second["id"])
    # Retained terminal history is a valid legacy fixture, not 9,000 native jobs.
    with accounts.db(write=True) as db:
        db.executemany(
            "INSERT INTO compute_commands(scope_id,request_id,actor_id,kind,payload_hash,"
            "created_at) VALUES(?,?,?,'scientific','fixture',0)",
            [(alice.id, f"historical-request-{index}", alice.id) for index in range(9000)],
        )
        db.executemany(
            "INSERT INTO admissions(id,scope_id,request_id,actor_id,scientific_actor_id,"
            "kind,state,gpu_slots,max_candidates,devices_json,created_at,updated_at) "
            "VALUES(?,?,?,?,?,'scientific','released',1,50,'[]',0,0)",
            [
                (
                    f"historical-grant-{index}",
                    alice.id,
                    f"historical-request-{index}",
                    alice.id,
                    alice.id,
                )
                for index in range(9000)
            ],
        )
    statements = []
    connect = sqlite3.connect

    def traced_connection(*args, **kwargs):
        db = connect(*args, **kwargs)
        db.set_trace_callback(statements.append)
        return db

    with monkeypatch.context() as capture:
        capture.setattr(sqlite3, "connect", traced_connection)
        assert runtime.resources.queue_position(second_grant.id) == 2
    query = next(statement for statement in statements if statement.startswith("SELECT"))
    with accounts.db() as db:
        plan = [str(row[3]) for row in db.execute("EXPLAIN QUERY PLAN " + query)]
    assert any("waiting USING INDEX one_active_admission" in detail for detail in plan), plan
    assert runtime.resources.queue_position(first_grant.id) == 1
    runtime.resources.transition(first_grant.id, "released")
    assert runtime.resources.queue_position(first_grant.id) is None
    assert runtime.resources.queue_position(second_grant.id) == 1


def test_request_rechecks_authority_before_opening_the_journal(queue, monkeypatch):
    runtime, _control, accounts, admin, alice, _bob = queue
    accepted = create(runtime, alice)
    with runtime.bind(alice, alice.id) as service:
        accounts.update_user(admin, alice.id, status="suspended")

        def unexpected_journal():
            pytest.fail("Revoked authority must be rejected before opening the request journal")

        monkeypatch.setattr(service, "journal", unexpected_journal)
        with pytest.raises(ProductError) as rejected:
            service.request(accepted["id"])
    assert rejected.value.code == "unauthorized"


def test_request_repair_rechecks_latest_grant_after_waiting_for_command_lock(queue, monkeypatch):
    runtime, _control, _accounts, _admin, alice, _bob = queue
    accepted = create(runtime, alice)
    old = runtime.resources.cancel_queued(alice, alice.id, accepted["id"])
    waiting = threading.Event()
    flock = fcntl.flock

    def observed_flock(handle, operation):
        if (
            threading.current_thread().name.startswith("request-repair")
            and operation == fcntl.LOCK_EX
        ):
            waiting.set()
        return flock(handle, operation)

    def read_request():
        with runtime.bind(alice, alice.id) as reader:
            return reader.request(accepted["id"])

    monkeypatch.setattr(fcntl, "flock", observed_flock)
    with runtime.bind(alice, alice.id) as service:
        journal = service.journal()
        try:
            payload = journal.get(accepted["id"])["payload"]
        finally:
            journal.close()
        lock = service.root / "commands" / (accepted["id"] + ".lock")
        with (
            lock.open("a") as owner,
            ThreadPoolExecutor(max_workers=1, thread_name_prefix="request-repair") as pool,
        ):
            flock(owner, fcntl.LOCK_EX)
            pending = pool.submit(read_request)
            try:
                assert waiting.wait(10), "Reader did not reach the held command lock"
                replacement, created = runtime.resources.reserve(
                    alice,
                    alice.id,
                    accepted["id"],
                    payload,
                    retry=True,
                    dispatch_channel="scoped_worker",
                )
                assert created and replacement.id != old.id
                runtime.resources.transition(replacement.id, "queued")
            finally:
                flock(owner, fcntl.LOCK_UN)
            row = pending.result(timeout=10)
        assert row["state"] == "accepted" and row["result"]["queue"]["state"] == "queued"
        journal = service.journal()
        try:
            assert journal.get(accepted["id"])["state"] == "accepted"
        finally:
            journal.close()
    assert runtime.resources.get(old.id).state == "cancelled"
    assert runtime.resources.get(replacement.id).state == "queued"


@pytest.mark.parametrize("phase", ["reserved", "running"])
def test_live_web_stream_is_neither_dispatched_nor_expired_by_scientific_supervisor(
    queue, monkeypatch, phase
):
    runtime, control, accounts, _admin, alice, _bob = queue
    admission, _ = runtime.resources.reserve(
        alice,
        alice.id,
        "web-stream-request-001",
        {"web": "stream"},
        kind="conversation",
        dispatch_channel="web_stream",
    )
    assert admission.worker_pid == os.getpid()
    assert admission.worker_start == process_identity(os.getpid())
    if phase == "running":
        runtime.resources.transition(admission.id, "running")

    def unexpected_spawn(*args, **kwargs):
        pytest.fail("Scientific supervisor must not dispatch Web streams")

    monkeypatch.setattr(subprocess, "Popen", unexpected_spawn)
    monkeypatch.setattr(accounts, "clock", lambda: time.time() + 7200)
    control.tick()
    assert runtime.resources.get(admission.id).state == phase
    assert not control.pool.assignment_path(admission.id).exists()


def test_web_owner_pid_reuse_releases_old_admission_without_killing_process(queue, monkeypatch):
    runtime, control, _accounts, _admin, alice, _bob = queue
    grant, _ = runtime.resources.reserve(
        alice,
        alice.id,
        "reused-pid-request-001",
        {},
        kind="conversation",
        dispatch_channel="web_stream",
    )
    runtime.resources.transition(grant.id, "running", worker_pid=os.getpid(), worker_start="0")

    def unexpected_kill(*args, **kwargs):
        pytest.fail("Owner reconciliation must not signal a reused process")

    monkeypatch.setattr(os, "kill", unexpected_kill)
    control.tick()
    assert runtime.resources.get(grant.id).reason == "web_owner_lost"
    assert runtime.resources.get(grant.id).state == "failed"


@pytest.mark.parametrize("observation", ["permission_denied", "malformed", "proc_unavailable"])
def test_unverifiable_web_owner_is_not_reaped(queue, monkeypatch, observation):
    runtime, control, accounts, _admin, alice, _bob = queue
    grant, _ = runtime.resources.reserve(
        alice,
        alice.id,
        "unknown-owner-request-001",
        {},
        kind="conversation",
        dispatch_channel="web_stream",
    )
    read_text = Path.read_text

    def unreadable(path, *args, **kwargs):
        if path == Path(f"/proc/{os.getpid()}/stat"):
            if observation == "permission_denied":
                raise PermissionError("fixture observation denied")
            if observation == "proc_unavailable":
                raise FileNotFoundError("fixture proc unavailable")
            return "malformed fixture"
        return read_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", unreadable)
    monkeypatch.setattr(accounts, "clock", lambda: time.time() + 7200)
    control.tick()
    assert runtime.resources.get(grant.id) == grant


def test_legacy_ownerless_web_admission_stays_visible_without_guessing_death(queue, monkeypatch):
    runtime, control, accounts, admin, alice, _bob = queue
    grant, _ = runtime.resources.reserve(
        alice,
        alice.id,
        "ownerless-web-request-001",
        {},
        kind="conversation",
        dispatch_channel="web_stream",
    )
    # Synthetic legacy row from before ownership was persisted atomically.
    with accounts.db(write=True) as db:
        db.execute(
            "UPDATE admissions SET worker_pid=NULL,worker_start=NULL WHERE id=?", (grant.id,)
        )
    monkeypatch.setattr(accounts, "clock", lambda: time.time() + 7200)
    control.tick()
    retained = runtime.resources.get(grant.id)
    assert retained.state == "reserved" and retained.worker_pid is None
    visible = next(row for row in runtime.resources.all_admissions(admin) if row["id"] == grant.id)
    assert visible["dispatch_channel"] == "web_stream" and visible["worker_start"] is None


def test_start_recovers_web_quota_before_ready_without_waiting_for_gpu_probe(queue):
    runtime, _control, accounts, admin, alice, _bob = queue
    accounts.set_limits(admin, alice.id, ResourceLimits(max_active_chats=1))
    create(runtime, alice)  # Older scientific queue entry is observed first by the background loop.
    grant, _ = runtime.resources.reserve(
        alice,
        alice.id,
        "web-startup-barrier-01",
        {},
        kind="conversation",
        dispatch_channel="web_stream",
    )
    runtime.resources.transition(grant.id, "running", worker_start="0")
    probing, finish_probe, ready = threading.Event(), threading.Event(), threading.Event()

    class SlowProbe:
        def snapshots(self):
            probing.set()
            assert finish_probe.wait(10), "Fixture GPU probe was not released"
            return ()

    restarted = ResourceSupervisor(runtime, probe=SlowProbe())

    def start():
        restarted.start()
        ready.set()

    starter = threading.Thread(target=start)
    starter.start()
    try:
        assert ready.wait(5), "Web recovery must not synchronously probe GPU resources"
        assert probing.wait(5)
        assert runtime.resources.get(grant.id).state == "failed"
        replacement, created = runtime.resources.reserve(
            alice,
            alice.id,
            "web-after-startup-001",
            {},
            kind="conversation",
            dispatch_channel="web_stream",
        )
        assert created and replacement.state == "reserved"
    finally:
        finish_probe.set()
        starter.join(timeout=10)
        restarted.close()


@pytest.mark.parametrize("phase", ["reserved", "running"])
def test_crashed_web_owner_releases_chat_quota_without_replaying_ai(
    queue, tmp_path, phase, monkeypatch
):
    runtime, control, accounts, admin, alice, _bob = queue
    accounts.set_limits(admin, alice.id, ResourceLimits(max_active_chats=1))
    team = accounts.create_team(alice, "Recovery team")["id"]
    accounts.set_limits(admin, team, ResourceLimits(max_active_chats=1))
    chat_path = tmp_path / "web-chat.sqlite"
    request_id = "crashed-web-request-001"
    payload = {
        "locale": "en",
        "messages": [{"role": "user", "content": "Synthetic chat"}],
        "context": {"stage": "Idle", "status": "idle", "goal": ""},
    }
    child = subprocess.Popen(
        [
            sys.executable,
            "-c",
            "import json, os, sys\n"
            "from pathlib import Path\n"
            "from easydesign.product.accounts import AccountStore\n"
            "from easydesign.product.resource_control import ResourceLedger\n"
            "from easydesign.product.resource_supervisor import process_identity\n"
            "from easydesign.product.rabbit_chat import RabbitChatService\n"
            "accounts = AccountStore(Path(sys.argv[1]))\n"
            "resources = ResourceLedger(accounts)\n"
            "actor = accounts.user(sys.argv[2])\n"
            "scope, request_id, phase = sys.argv[3:6]\n"
            "payload = json.loads(sys.argv[7])\n"
            "def provider(request):\n"
            "    yield {'type':'delta', 'text':'synthetic'}\n"
            "    yield {'type':'done'}\n"
            "chat = RabbitChatService(provider, ledger_path=Path(sys.argv[6]))\n"
            "grant, _ = resources.reserve(actor, scope, request_id, payload, "
            "kind='conversation', dispatch_channel='web_stream')\n"
            "stream = chat.events(payload, actor_id=actor.id, scope_id=scope, "
            "request_id=request_id)\n"
            "if phase == 'running':\n"
            "    resources.transition(grant.id, 'running', worker_pid=os.getpid(), "
            "worker_start=process_identity(os.getpid()))\n"
            "    next(stream)\n"
            "    next(stream)\n"
            "print(grant.id, flush=True)\n"
            "sys.stdin.readline()\n"
            "os._exit(57)\n",
            str(accounts.path),
            alice.id,
            team,
            request_id,
            phase,
            str(chat_path),
            json.dumps(payload),
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        assert select.select([child.stdout], [], [], 20)[0], "Fixture owner did not start"
        grant_id = child.stdout.readline().strip()
        assert grant_id.startswith("grant-")
        before = runtime.resources.get(grant_id)
        with pytest.raises(ProductError) as full:
            runtime.resources.reserve(
                alice,
                team,
                "second-web-request-001",
                payload,
                kind="conversation",
                dispatch_channel="web_stream",
            )
        assert full.value.code == "quota_exceeded"
        monkeypatch.setattr(accounts, "clock", lambda: time.time() + 7200)
        control.tick()
        assert runtime.resources.get(grant_id).state == phase
        assert child.poll() is None  # Even a long-lived real queued/streaming owner is kept.
        child.communicate("crash\n", timeout=10)
        assert child.returncode == 57
        # A fresh supervisor observes the lost owner, not the provider outcome.
        restarted = ResourceSupervisor(runtime, probe=control.probe)
        restarted.tick()
        after = runtime.resources.get(grant_id)
        assert after.state == "failed" and after.reason == "web_owner_lost"
        assert before.worker_pid == child.pid and before.worker_start is not None
        replacement, created = runtime.resources.reserve(
            alice,
            team,
            "second-web-request-001",
            payload,
            kind="conversation",
            dispatch_channel="web_stream",
        )
        assert created and replacement.state == "reserved"
        calls = []

        def unexpected_provider(request):
            calls.append(request)
            yield {"type": "done"}

        restored = RabbitChatService(unexpected_provider, ledger_path=chat_path)
        try:
            with pytest.raises(ProductError) as repeated:
                restored.events(payload, actor_id=alice.id, scope_id=team, request_id=request_id)
            assert repeated.value.code == "request_already_processed"
            status = restored.request_status(
                actor_id=alice.id, scope_id=team, request_id=request_id
            )
            assert status["code"] == ("outcome_unknown" if phase == "running" else "interrupted")
            assert calls == []
        finally:
            restored.close()
    finally:
        if child.poll() is None:
            child.terminate()
        child.communicate(timeout=10)


def test_bounded_queue_cancellation_frees_capacity_and_is_idempotent(queue):
    runtime, control, accounts, _admin, alice, bob = queue
    runtime.resources = ResourceLedger(accounts, max_active_admissions=1)
    control.ledger = runtime.resources
    accepted = create(runtime, alice)
    assert create(runtime, alice)["id"] == accepted["id"]
    with pytest.raises(ProductError) as full:
        create(runtime, bob, "bob-queued-request-01")
    assert full.value.code == "queue_full" and full.value.status == 429
    with runtime.bind(alice, alice.id) as service:
        cancelled = service.cancel_queued(accepted["id"])
        assert cancelled["state"] == "failed"
        assert cancelled["result"]["code"] == "queue_cancelled"
        assert service.cancel_queued(accepted["id"])["result"] == cancelled["result"]
    control.tick()
    assert create(runtime, bob, "bob-queued-request-01")["state"] == "accepted"


def test_revocation_cancels_waiting_without_spawning_or_waiting_for_free_gpu(queue, monkeypatch):
    runtime, control, accounts, admin, alice, _bob = queue
    from easydesign.product import resource_supervisor

    accepted = create(runtime, alice)
    accounts.update_user(admin, alice.id, status="suspended")
    monkeypatch.setattr(
        resource_supervisor.subprocess, "Popen", lambda *a, **k: pytest.fail("spawn")
    )
    control.tick()
    admission = runtime.resources.latest(alice.id, accepted["id"])
    assert admission.state == "cancelled" and admission.reason == "authorization_revoked"
    # Check the real scoped journal without relying on the now-revoked HTTP identity.
    _, service = control._service(admission)
    journal = service.journal()
    try:
        assert journal.get(accepted["id"])["result"]["code"] == "authorization_revoked"
    finally:
        journal.close()


def test_cancellation_and_dispatch_claim_have_one_atomic_winner(queue):
    runtime, _control, _accounts, _admin, alice, _bob = queue
    accepted = create(runtime, alice)
    grant = runtime.resources.latest(alice.id, accepted["id"])
    barrier = threading.Barrier(2)

    def cancel():
        barrier.wait()
        try:
            return runtime.resources.cancel_queued(alice, alice.id, accepted["id"]).state
        except ProductError as error:
            return error.code

    def claim():
        barrier.wait()
        admission = runtime.resources.claim_start(grant.id, max_conversation_workers=8)
        return admission.state if admission is not None else "not_claimed"

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(cancel), pool.submit(claim)]
        results = {future.result() for future in futures}
    assert results in ({"cancelled", "not_claimed"}, {"queue_not_cancellable", "starting"})


def test_startup_timeout_begins_at_claim_not_at_queue_creation(queue, monkeypatch):
    runtime, control, accounts, _admin, alice, _bob = queue
    accepted = create(runtime, alice)
    admission = runtime.resources.latest(alice.id, accepted["id"])
    now = admission.created_at + 7200
    monkeypatch.setattr(accounts, "clock", lambda: now)
    runtime.resources.claim_start(admission.id, max_conversation_workers=8)
    control.tick()
    assert runtime.resources.get(admission.id).state == "starting"
    now += 31
    control.tick()
    failed = runtime.resources.get(admission.id)
    assert failed.state == "failed" and failed.reason == "worker_start_timeout"
    with runtime.bind(alice, alice.id) as service:
        row = service.request(accepted["id"])
        assert row["state"] == "failed" and row["result"]["code"] == "worker_start_timeout"


def test_manual_tick_cannot_bypass_another_running_supervisor(queue):
    runtime, control, *_ = queue
    other = ResourceSupervisor(runtime, probe=control.probe)
    control.start()
    try:
        with pytest.raises(ProductError) as busy:
            other.tick()
        assert busy.value.code == "controller_busy"
    finally:
        control.close()
    other.tick()  # The controller's clean stop releases ownership.


def test_restart_finishes_enqueue_after_config_before_queue_marker(queue, monkeypatch):
    runtime, control, _accounts, _admin, alice, _bob = queue
    request_id = "enqueue-window-request"
    original = runtime.resources.transition

    def crash(grant, state, **kwargs):
        if state == "queued":
            raise RuntimeError("crash after durable config")
        return original(grant, state, **kwargs)

    with runtime.bind(alice, alice.id) as service:
        admission, _ = runtime.resources.reserve(
            alice, alice.id, request_id, {"operation": "create"}, dispatch_channel="scoped_worker"
        )
        journal = service.journal()
        journal.reserve("fixture-project", {"request_id": request_id, "operation": "create"})
        journal.close()
        monkeypatch.setattr(runtime.resources, "transition", crash)
        with pytest.raises(RuntimeError, match="durable config"):
            control.launch(admission, service)
    monkeypatch.setattr(runtime.resources, "transition", original)
    ResourceSupervisor(runtime, probe=control.probe).tick()
    recovered = runtime.resources.get(admission.id)
    assert recovered.state == "queued" and recovered.worker_pid is None


def test_old_worker_request_lock_prevents_duplicate_dispatch(queue, monkeypatch):
    runtime, control, _accounts, _admin, alice, _bob = queue
    accepted = create(runtime, alice)
    from easydesign.product import resource_supervisor

    class Free:
        def snapshots(self):
            return (
                GpuResourceSnapshot(
                    device=0,
                    name="fixture",
                    uuid="GPU-fixture",
                    memory_total_mib=40000,
                    memory_used_mib=0,
                    utilization_percent=0,
                ),
            )

    control.probe = Free()
    monkeypatch.setattr(
        resource_supervisor.subprocess, "Popen", lambda *a, **k: pytest.fail("spawn")
    )
    with runtime.bind(alice, alice.id) as service:
        path = service.root / "workers" / (accepted["id"] + ".lock")
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a") as old_worker:
            fcntl.flock(old_worker, fcntl.LOCK_EX)
            control.tick()
    assert runtime.resources.latest(alice.id, accepted["id"]).state == "queued"


def test_full_scientific_queue_does_not_block_web_chat_or_authenticated_reads(queue):
    runtime, control, accounts, _admin, alice, _bob = queue
    runtime.resources = ResourceLedger(accounts, max_active_admissions=1)
    control.ledger = runtime.resources
    accepted = create(runtime, alice)
    web, created = runtime.resources.reserve(
        alice,
        alice.id,
        "independent-web-chat",
        {"message": "fixture"},
        kind="conversation",
        dispatch_channel="web_stream",
    )
    assert created and web.state == "reserved"
    with runtime.bind(alice, alice.id) as service:
        assert service.request(accepted["id"])["state"] == "accepted"


def test_password_change_revokes_the_queued_authorization_epoch(queue):
    runtime, control, accounts, _admin, alice, _bob = queue
    accepted = create(runtime, alice)
    accounts.change_password(
        alice, "Queue-fixture-password-2026!", "Changed-fixture-password-2026!"
    )
    control.tick()
    admission = runtime.resources.latest(alice.id, accepted["id"])
    assert admission.state == "cancelled" and admission.reason == "authorization_revoked"


def test_cancel_commit_before_journal_update_recovers_and_can_retry(queue):
    runtime, _control, _accounts, _admin, alice, _bob = queue
    accepted = create(runtime, alice)
    cancelled = runtime.resources.cancel_queued(alice, alice.id, accepted["id"])
    with runtime.bind(alice, alice.id) as service:
        row = service.request(accepted["id"])
        assert row["state"] == "failed" and row["result"]["code"] == "queue_cancelled"
        retried = service.retry(accepted["id"])
        assert retried["state"] == "accepted" and retried["result"]["queue"]["state"] == "queued"
    assert runtime.resources.latest(alice.id, accepted["id"]).id != cancelled.id


def test_conversation_worker_claims_are_bounded_independently_of_web_stream(queue):
    runtime, _control, _accounts, _admin, alice, bob = queue
    grants = []
    for user in (alice, bob):
        admission, _ = runtime.resources.reserve(
            user,
            user.id,
            "chat-worker-" + user.username * 5,
            {"message": "fixture"},
            kind="conversation",
            dispatch_channel="scoped_worker",
        )
        grants.append(runtime.resources.transition(admission.id, "queued"))
    first = runtime.resources.claim_start(grants[0].id, max_conversation_workers=1)
    assert first is not None and first.state == "starting"
    assert runtime.resources.claim_start(grants[1].id, max_conversation_workers=1) is None
    assert runtime.resources.get(grants[1].id).state == "queued"


def test_partial_intent_before_journal_does_not_become_an_executable_command(queue, monkeypatch):
    runtime, control, accounts, _admin, alice, _bob = queue
    admission, _ = runtime.resources.reserve(
        alice,
        alice.id,
        "incomplete-intent-01",
        {"operation": "create"},
        dispatch_channel="scoped_worker",
    )
    monkeypatch.setattr(accounts, "clock", lambda: admission.created_at + 31)
    control.tick()
    failed = runtime.resources.get(admission.id)
    assert failed.state == "failed" and failed.reason == "submission_incomplete"
    assert failed.worker_pid is None


def test_removed_team_member_cannot_dispatch_a_previously_queued_request(queue):
    runtime, control, accounts, _admin, alice, bob = queue
    team = accounts.create_team(alice, "Queue team")
    invite = accounts.invite(alice, team["id"], "bob", role="admin")
    accounts.respond_invitation(bob, invite["id"], accept=True)
    request_id = "team-queued-request-01"
    with runtime.bind(bob, team["id"]) as service:
        service.create(CreateProject(request_id=request_id, title="Fixture", goal="Fixture target"))
    accounts.set_member(alice, team["id"], bob.id, remove=True)
    control.tick()
    admission = runtime.resources.latest(team["id"], request_id)
    assert admission.state == "cancelled" and admission.worker_pid is None


def test_forged_worker_receipt_cannot_adopt_an_unrelated_process(queue):
    runtime, control, _accounts, _admin, alice, _bob = queue
    accepted = create(runtime, alice)
    admission = runtime.resources.latest(alice.id, accepted["id"])
    runtime.resources.claim_start(admission.id, max_conversation_workers=8)
    with runtime.bind(alice, alice.id) as service:
        immutable_json(
            service.root / "workers" / (admission.id + ".started.json"),
            {
                "grant_id": admission.id,
                "request_id": accepted["id"],
                "pid": os.getpid(),
                "start": process_identity(os.getpid()),
            },
        )
    control.tick()
    quarantined = runtime.resources.get(admission.id)
    assert quarantined.state == "held" and quarantined.worker_pid is None
    assert not control.pool.assignment_path(admission.id).exists()
