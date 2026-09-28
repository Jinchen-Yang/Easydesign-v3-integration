"""Persistent admission tests; synthetic workspaces, no models or GPU execution."""

from __future__ import annotations

import fcntl
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from easydesign.backends.executors.local_multi_gpu import GpuResourceSnapshot
from easydesign.product.accounts import AccountStore
from easydesign.product.artifacts import immutable_json
from easydesign.product.contracts import CreateProject, ProductError
from easydesign.product.domain import NativeGateway
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


def test_web_stream_admission_is_not_owned_by_scientific_supervisor(queue, monkeypatch):
    runtime, control, accounts, _admin, alice, _bob = queue
    admission, _ = runtime.resources.reserve(
        alice,
        alice.id,
        "web-stream-request-001",
        {"web": "stream"},
        kind="conversation",
        dispatch_channel="web_stream",
    )
    monkeypatch.setattr(accounts, "clock", lambda: time.time() + 120)
    control.tick()
    assert runtime.resources.get(admission.id).state == "reserved"
    assert not control.pool.assignment_path(admission.id).exists()


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
