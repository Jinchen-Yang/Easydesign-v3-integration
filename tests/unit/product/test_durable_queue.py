"""Persistent admission tests; synthetic workspaces, no models or GPU execution."""

from __future__ import annotations

import fcntl
import json
import os
import select
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

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
