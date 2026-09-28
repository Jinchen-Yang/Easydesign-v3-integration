"""Backend follow-up regressions: link scoping, drafts, retries, audits, admission."""

from __future__ import annotations

import json
import os
import threading
import time
from contextlib import contextmanager
from pathlib import Path

import httpx
import pytest

from easydesign.product.account_server import MultiUserServer, _scoped_urls
from easydesign.product.accounts import AccountStore, ResourceLimits
from easydesign.product.contracts import CreateProject, ProductError
from easydesign.product.project_drafts import ProjectDrafts
from easydesign.product.resource_control import ResourceLedger
from easydesign.product.resource_supervisor import process_identity
from easydesign.product.scoped_worker import SecretFilter, _admission_still_active
from easydesign.product.tenancy import MultiUserRuntime
from easydesign.workspace_context import WorkspaceContext

PASSWORD = "Fixture-password-2026!"


def _workspace(tmp_path: Path) -> WorkspaceContext:
    (tmp_path / "easydesign-workspace.yaml").write_text('schema_version: "0.1"\n')
    context = WorkspaceContext.from_root(tmp_path)
    context.ensure_layout()
    return context


def test_scoped_urls_rewrite_every_declared_link_field():
    scope = "user-" + "a" * 32
    response = {
        "decision": {
            "details_url": "/api/v1/artifacts/abc",
            "summary": "kept",
            "external": "https://Evidence.example/report",
        },
        "candidates": {"url": "/api/v1/projects/workbench-x/candidates", "total": 2},
        "artifacts": [{"url": "/api/v1/artifacts/def", "sha256": "b" * 64}],
        "already_scoped": "/api/v1/scopes/user-%s/requests/id" % ("b" * 32),
        "bytes_like": "not-a-url",
    }
    rendered = _scoped_urls(response, scope)
    assert rendered["decision"]["details_url"] == f"/api/v1/scopes/{scope}/artifacts/abc"
    assert rendered["decision"]["external"] == "https://Evidence.example/report"
    assert (
        rendered["candidates"]["url"] == f"/api/v1/scopes/{scope}/projects/workbench-x/candidates"
    )
    assert rendered["artifacts"][0]["url"] == f"/api/v1/scopes/{scope}/artifacts/def"
    assert rendered["already_scoped"].startswith("/api/v1/scopes/")
    assert response["decision"]["details_url"] == "/api/v1/artifacts/abc"  # input untouched


def test_project_drafts_serialize_concurrent_saves_and_release_connections(tmp_path):
    drafts = ProjectDrafts(tmp_path / "team/drafts.sqlite")
    first = drafts.save("user-" + "a" * 32, {"title": "T", "goal": "G"})
    assert first["revision"] == 1

    outcomes: list[str] = []
    lock = threading.Lock()

    def save(_index: int) -> None:
        try:
            drafts.save(
                "user-" + "b" * 32,
                {"title": "T2", "goal": "G2"},
                identity=first["id"],
                expected_revision=1,
            )
        except ProductError as error:
            with lock:
                outcomes.append(error.code)
            return
        with lock:
            outcomes.append("saved")

    threads = [threading.Thread(target=save, args=(i,)) for i in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    assert outcomes.count("saved") == 1
    assert outcomes.count("stale_draft") == 7
    assert drafts.get(first["id"])["revision"] == 2

    for revision in range(3, 22):
        drafts.save(
            "user-" + "a" * 32,
            {"title": f"T{revision}", "goal": "G"},
            identity=first["id"],
            expected_revision=revision - 1,
        )
    assert drafts.get(first["id"])["revision"] == 21


def test_draft_claim_is_exclusive_and_failure_returns_the_draft(tmp_path):
    drafts = ProjectDrafts(tmp_path / "drafts.sqlite")
    draft = drafts.save("actor-a", {"title": "T", "goal": "G"})

    def claim(request_id: str) -> str:
        try:
            drafts.claim(draft["id"], 1, request_id)
        except ProductError as error:
            return error.code
        return "claimed"

    results = [claim(f"start-request-{i:016d}") for i in range(6)]
    assert results.count("claimed") == 1
    assert results.count("draft_already_started") == 5

    winner = next(f"start-request-{i:016d}" for i, r in enumerate(results) if r == "claimed")
    assert drafts.claim(draft["id"], 1, winner)["state"] == "starting"  # idempotent reclaim
    drafts.finish_start(draft["id"], winner, None)
    assert drafts.get(draft["id"])["state"] == "draft"  # failed start is editable again
    drafts.claim(draft["id"], 1, "start-request-0000002")
    drafts.finish_start(draft["id"], "start-request-0000002", "workbench-project")
    started = drafts.get(draft["id"])
    assert started["state"] == "started" and started["project_id"] == "workbench-project"
    with pytest.raises(ProductError):
        drafts.save(
            "actor-a", {"title": "X", "goal": "Y"}, identity=draft["id"], expected_revision=1
        )


def test_request_ids_are_scope_bound_and_retry_keeps_attribution(tmp_path):
    store = AccountStore(tmp_path / "accounts.sqlite")
    admin = store.bootstrap_admin("admin", PASSWORD, "管理员")
    alice = store.register("alice", PASSWORD, "Alice")
    bob = store.register("bob", PASSWORD, "Bob")
    for user in (alice, bob):
        store.update_user(admin, user.id, status="active")
    team = store.create_team(alice, "Team")
    invitation = store.invite(alice, team["id"], "bob", role="admin")
    store.respond_invitation(bob, invitation["id"], accept=True)
    ledger = ResourceLedger(store)

    request_id = "shared-request-00001"
    personal, _ = ledger.reserve(alice, alice.id, request_id, {"operation": "create"})
    ledger.transition(personal.id, "released")
    team_admission, _ = ledger.reserve(alice, team["id"], request_id, {"operation": "create"})
    assert personal.id != team_admission.id  # identity is scoped, never global

    with pytest.raises(ProductError) as error:
        ledger.reserve(bob, team["id"], request_id, {"operation": "create"})
    assert error.value.code == "idempotency_conflict"

    ledger.transition(team_admission.id, "failed", reason="worker_lost")
    # A team administrator may recover the failed request, but the scientific
    # actor of record must stay the member who originated it.
    recovered, created = ledger.reserve(
        bob, team["id"], request_id, {"operation": "create"}, retry=True
    )
    assert created and recovered.id != team_admission.id
    assert recovered.scientific_actor_id == alice.id
    with store.db() as db:
        events = [
            json.loads(row["details"])
            for row in db.execute(
                "SELECT details FROM audit_events WHERE action='resource.reserve' ORDER BY seq"
            )
        ]
    assert events[-1]["retry"] is True


def test_admin_team_observation_is_audited_but_membership_reads_are_not(tmp_path):
    store = AccountStore(tmp_path / "accounts.sqlite")
    admin = store.bootstrap_admin("admin", PASSWORD, "管理员")
    alice = store.register("alice", PASSWORD, "Alice")
    bob = store.register("bob", PASSWORD, "Bob")
    store.update_user(admin, alice.id, status="active")
    store.update_user(admin, bob.id, status="active")
    team = store.create_team(alice, "Team")

    observed = store.team(admin, team["id"])
    assert observed["id"] == team["id"]
    store.team(alice, team["id"])  # member read stays unaudited
    with pytest.raises(ProductError):
        store.team(bob, team["id"])  # outsider without administration gets 404
    with store.db() as db:
        reads = db.execute(
            "SELECT count(*) FROM audit_events WHERE action='admin.team.read'"
        ).fetchone()[0]
    assert reads == 1


def test_secret_filter_redacts_credential_values(monkeypatch):
    import logging

    secret = "fixture-credential-value-2026"
    monkeypatch.setenv("EASYDESIGN_TEST_SECRET", secret)
    monkeypatch.setenv("EASYDESIGN_SHORT", "abc")  # too short to be a safe marker
    filt = SecretFilter(["EASYDESIGN_TEST_SECRET", "EASYDESIGN_SHORT"])
    record = logging.LogRecord("fixture", logging.ERROR, __file__, 1, f"boom {secret}", None, None)
    assert filt.filter(record)
    assert secret not in record.getMessage() and "[REDACTED]" in record.getMessage()


def test_worker_liveness_probe_fails_closed(tmp_path):
    from easydesign.product.resource_control import ACTIVE_ADMISSIONS

    missing = tmp_path / "missing.sqlite"
    assert _admission_still_active(missing, "grant-1") is True
    store = AccountStore(tmp_path / "accounts.sqlite")
    ledger = ResourceLedger(store)
    admin = store.bootstrap_admin("admin", PASSWORD, "管理员")
    user = store.register("alice", PASSWORD, "Alice")
    store.update_user(admin, user.id, status="active")
    admission, _ = ledger.reserve(user, user.id, "probe-request-00001", {"operation": "create"})
    db_path = tmp_path / "accounts.sqlite"
    assert _admission_still_active(db_path, admission.id) is True
    ledger.transition(admission.id, "failed", reason="worker_not_published")
    assert _admission_still_active(db_path, admission.id) is False
    assert _admission_still_active(db_path, "grant-unknown") is True
    assert "failed" not in ACTIVE_ADMISSIONS


def _runtime(tmp_path: Path, *, clock=None):
    from easydesign.product.domain import NativeGateway
    from easydesign.product.tenancy import MultiUserRuntime

    context = _workspace(tmp_path)
    store = AccountStore(
        context.runtime_root / "state/accounts/accounts.sqlite",
        **({} if clock is None else {"clock": clock}),
    )
    (tmp_path / "models.yaml").write_text(
        "default:\n  provider: openai\n  model: fixture-model\n"
        "  secret_env: EASYDESIGN_FIXTURE_KEY\n"
    )
    runtime = MultiUserRuntime(
        context, store, lambda scoped: NativeGateway(scoped, tmp_path / "models.yaml")
    )
    return context, store, runtime


def _populate(store: AccountStore):
    admin = store.bootstrap_admin("admin", PASSWORD, "管理员")
    alice = store.register("alice", PASSWORD, "Alice")
    store.update_user(admin, alice.id, status="active")
    return admin, alice


def test_retry_reconciles_an_abandoned_accepted_request(tmp_path):
    context, store, runtime = _runtime(tmp_path)
    _admin, alice = _populate(store)
    launched: list[str] = []

    def launcher(admission, service):
        runtime.resources.transition(
            admission.id,
            "queued",
            worker_pid=os.getpid(),
            worker_start=process_identity(os.getpid()),
        )
        launched.append(admission.request_id)

    runtime.launcher = launcher
    request = CreateProject(
        request_id="retry-request-000001",
        title="Abandoned worker",
        goal="Recover a request whose transport worker never reported back.",
    )
    with runtime.bind(alice, alice.id) as service:
        accepted = service.create(request)
        assert accepted["state"] == "accepted" and launched == [request.request_id]

        admission = runtime.resources.latest(alice.id, request.request_id)
        assert admission is not None
        runtime.resources.transition(admission.id, "failed", reason="worker_lost")
        journal = service.journal()
        try:
            journal.db.execute(
                "UPDATE requests SET state='accepted',updated=? WHERE id=?",
                (time.time() - 120, request.request_id),
            )
            journal.db.commit()
        finally:
            journal.close()

        result = service.retry(request.request_id)
        assert result["state"] == "accepted"
        assert (service.context.projects_root / result["project"] / "metadata").is_dir()
    assert launched == [request.request_id] * 2
    latest = runtime.resources.latest(alice.id, request.request_id)
    assert latest is not None and latest.scientific_actor_id == alice.id


def test_worker_not_published_window_follows_the_account_clock(tmp_path):
    from easydesign.backends.executors.local_multi_gpu import GpuResourceSnapshot
    from easydesign.product.resource_supervisor import ResourceSupervisor

    now = [1_000_000.0]
    context, store, runtime = _runtime(tmp_path, clock=lambda: now[0])
    _admin, alice = _populate(store)
    snapshots = tuple(
        GpuResourceSnapshot(
            device=d,
            name="fixture",
            uuid=f"GPU-{d}",
            memory_total_mib=40000,
            memory_used_mib=0,
            utilization_percent=0,
        )
        for d in (0,)
    )

    class Probe:
        def snapshots(self):
            return snapshots

    control = ResourceSupervisor(runtime, probe=Probe())
    admission, _ = runtime.resources.reserve(
        alice, alice.id, "unpublished-request-1", {"operation": "create"}
    )
    control.tick()
    assert runtime.resources.get(admission.id).state == "reserved"
    now[0] += 31
    control.tick()
    failed = runtime.resources.get(admission.id)
    assert failed.state == "failed" and failed.reason == "worker_not_published"
    # Orphaned workers discover the abandonment through this assignment marker.
    marker = json.loads(control.pool.assignment_path(admission.id).read_text())
    assert marker["cancelled"] and marker["code"] == "admission_abandoned"


def test_corrupt_assignment_quarantines_only_its_own_admission(tmp_path):
    from easydesign.backends.executors.local_multi_gpu import GpuResourceSnapshot
    from easydesign.product.artifacts import immutable_json
    from easydesign.product.resource_supervisor import ResourceSupervisor

    context, store, runtime = _runtime(tmp_path)
    admin, alice = _populate(store)
    bob = store.register("bob", PASSWORD, "Bob")
    store.update_user(admin, bob.id, status="active")
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

    control = ResourceSupervisor(runtime, probe=Probe())
    first, _ = runtime.resources.reserve(
        alice, alice.id, "first-request-00001", {"operation": "create"}
    )
    second, _ = runtime.resources.reserve(
        bob, bob.id, "second-request-00001", {"operation": "create"}
    )
    for admission in (first, second):
        runtime.resources.transition(
            admission.id,
            "queued",
            worker_pid=os.getpid(),
            worker_start=process_identity(os.getpid()),
        )
    immutable_json(
        control.pool.assignment_path(first.id),
        {"grant_id": "grant-" + "0" * 32, "scope_file": "runtime/state/execution-scopes/x.json"},
    )
    control.tick()
    quarantined = runtime.resources.get(first.id)
    healthy = runtime.resources.get(second.id)
    assert quarantined.state == "held"
    assert quarantined.reason == "allocation_identity_mismatch"
    assert healthy.state == "running" and healthy.devices == (0,)


@contextmanager
def http_client(server, username: str | None = None):
    origin = f"http://127.0.0.1:{server.server_port}"
    with httpx.Client(
        base_url=origin, headers={"Origin": origin}, timeout=30, trust_env=False
    ) as value:
        if username:
            result = value.post(
                "/api/v1/accounts/login", json={"username": username, "password": PASSWORD}
            )
            assert result.status_code == 200
            value.headers["X-CSRF-Token"] = result.json()["csrf_token"]
        yield value


@pytest.fixture
def http_product(tmp_path: Path):
    from easydesign.product.domain import NativeGateway

    context = _workspace(tmp_path)
    store = AccountStore(context.runtime_root / "state/accounts/accounts.sqlite")
    admin = store.bootstrap_admin("admin", PASSWORD, "管理员")
    alice = store.register("alice", PASSWORD, "Alice")
    store.update_user(admin, alice.id, status="active")
    team = store.create_team(alice, "Team")
    (tmp_path / "models.yaml").write_text(
        "default:\n  provider: openai\n  model: fixture-model\n"
        "  secret_env: EASYDESIGN_FIXTURE_KEY\n"
    )
    launched: list[str] = []

    def launcher(admission, service):
        launched.append(admission.request_id)

    runtime = MultiUserRuntime(
        context,
        store,
        lambda scoped: NativeGateway(scoped, tmp_path / "models.yaml"),
        launcher=launcher,
    )
    server = MultiUserServer(runtime, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server, runtime, store, admin, alice, team["id"], launched
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_conflicting_draft_start_recovers_without_attaching_a_foreign_project(
    http_product,
):
    """HTTP mirror of the QA recovery regression (qa-findings #1).

    The QA fixture keeps every admission active (mocked dispatch), so running a
    second scientific job for alice additionally requires an explicit personal
    quota grant (jobs AND gpu devices); the default personal limit of one active
    GPU-backed job correctly blocks the retry under confirmed product rules.
    """
    server, runtime, store, admin, alice, team, launched = http_product
    store.set_limits(admin, alice.id, ResourceLimits(max_active_jobs=2, max_gpu_devices=2))
    base = f"/api/v1/scopes/{team}"
    with http_client(server, "alice") as owner:
        draft = owner.post(
            base + "/drafts", json={"title": "Recovery draft", "goal": "Synthetic goal."}
        ).json()["draft"]
        seed = owner.post(
            base + "/projects",
            json={
                "request_id": "draft-conflict-seed-01",
                "title": "Existing program",
                "goal": "A different already-accepted create payload.",
                "surface": "easy",
            },
        )
        assert seed.status_code == 202
        conflict = owner.post(
            f"{base}/drafts/{draft['id']}/start",
            json={"revision": 1, "request_id": "draft-conflict-seed-01"},
        )
        assert conflict.status_code == 409
        assert conflict.json()["error"]["code"] == "idempotency_conflict"
        refreshed = owner.get(f"{base}/drafts/{draft['id']}").json()["draft"]
        assert refreshed["state"] == "draft"
        assert refreshed["project_id"] is None  # no unrelated project attached
        started = owner.post(
            f"{base}/drafts/{draft['id']}/start",
            json={"revision": 1, "request_id": "draft-retry-start-0001"},
        )
        assert started.status_code == 202, started.text
        final = owner.get(f"{base}/drafts/{draft['id']}").json()["draft"]
        assert final["state"] == "started"
        assert final["project_id"] == started.json()["project"]
        assert launched == ["draft-conflict-seed-01", "draft-retry-start-0001"]


def test_administration_only_mode_cannot_enqueue_science(http_product):
    server, runtime, store, admin, alice, _team, _launched = http_product
    runtime.launcher = None  # simulate accounts-only startup: no admission launcher
    base = f"/api/v1/scopes/{alice.id}"

    with http_client(server, "alice") as owner:
        config = owner.get("/api/v1/accounts/config").json()
        assert config["compute_available"] is False
        assert owner.get(base + "/projects").status_code == 200  # reads stay useful

        denied_create = owner.post(
            base + "/projects",
            json={
                "request_id": "admin-only-create-001",
                "title": "Blocked",
                "goal": "No compute may be enqueued.",
            },
        )
        assert denied_create.status_code == 503
        assert denied_create.json()["error"]["code"] == "compute_unavailable"

        draft = owner.post(
            base + "/drafts", json={"title": "Editable", "goal": "Drafts still work."}
        ).json()["draft"]
        denied_start = owner.post(
            f"{base}/drafts/{draft['id']}/start",
            json={"revision": 1, "request_id": "admin-only-start-001"},
        )
        assert denied_start.status_code == 503
        assert denied_start.json()["error"]["code"] == "compute_unavailable"
        recovered = owner.get(f"{base}/drafts/{draft['id']}").json()["draft"]
        assert recovered["state"] == "draft" and recovered["project_id"] is None

        chat = owner.post(
            base + "/rabbit/chat",
            headers={"X-Request-ID": "admin-only-chat-0001"},
            json={
                "locale": "zh",
                "messages": [{"role": "user", "content": "你好"}],
                "context": {"stage": "Idle", "status": "idle", "goal": "闲聊"},
            },
        )
        assert chat.status_code == 503  # provider absent; admission failed, retryable
        admission = runtime.resources.latest(alice.id, "admin-only-chat-0001")
        assert admission is not None and admission.state == "failed"
        assert admission.reason == "chat_unavailable"

    # Seed one failed scientific request, then prove resume is also blocked.
    runtime.launcher = lambda *args: None
    with runtime.bind(alice, alice.id) as service:
        service.create(
            CreateProject(
                request_id="admin-only-resume-001",
                title="Resumable",
                goal="A failed request whose resume needs compute.",
            )
        )
    runtime.launcher = None
    with runtime.bind(alice, alice.id) as service:
        journal = service.journal()
        try:
            journal.update(
                "admin-only-resume-001",
                "failed",
                {"code": "fixture", "message": "seeded failure"},
            )
        finally:
            journal.close()
    admission = runtime.resources.latest(alice.id, "admin-only-resume-001")
    assert admission is not None
    runtime.resources.transition(admission.id, "failed", reason="fixture")
    with http_client(server, "alice") as owner:
        denied_resume = owner.post(base + "/requests/admin-only-resume-001/resume", json={})
        assert denied_resume.status_code == 503
        assert denied_resume.json()["error"]["code"] == "compute_unavailable"

    # Account, team and quota administration remain fully usable without compute.
    with http_client(server, "admin") as administrator:
        quota = administrator.post(f"/api/v1/admin/quotas/{alice.id}", json={"max_active_jobs": 3})
        assert quota.status_code == 200
        assert administrator.get("/api/v1/admin/audit").status_code == 200
    with http_client(server, "alice") as owner:
        assert owner.post("/api/v1/teams", json={"name": "Readonly-mode team"}).status_code == 201


class StubChatService:
    """Deterministic chat boundary for delivery-semantics regressions."""

    def __init__(self, events_factory):
        self.events_factory = events_factory

    def status(self) -> dict:
        return {"configured": True, "model": "fixture"}

    def events(self, payload: dict, **_identity):
        return self.events_factory()


class RaisingCloseIterator:
    """Event iterator whose close() always fails; yields embedded exceptions."""

    def __init__(self, items):
        self._iter = iter(items)

    def __iter__(self):
        return self

    def __next__(self):
        item = next(self._iter)
        if isinstance(item, Exception):
            raise item
        return item

    def close(self):
        raise RuntimeError("fixture cleanup exploded")


def _chat_lines(response) -> list[dict]:
    return [json.loads(line) for line in response.text.splitlines() if line.strip()]


def test_chat_delivery_semantics_and_retryability(http_product):
    server, runtime, _store, _admin, alice, _team, _launched = http_product
    base = f"/api/v1/scopes/{alice.id}"
    chat_url = base + "/rabbit/chat"
    payload = {
        "locale": "zh",
        "messages": [{"role": "user", "content": "你好"}],
        "context": {"stage": "Idle", "status": "idle", "goal": "验收"},
    }

    def post(client, request_id):
        return client.post(chat_url, headers={"X-Request-ID": request_id}, json=payload)

    # 1. Clean public done: success and the request id becomes a duplicate.
    server.rabbit_chat = StubChatService(
        lambda: iter([{"type": "delta", "text": "hi"}, {"type": "done"}])
    )
    with http_client(server, "alice") as owner:
        done = post(owner, "chat-done-0000000001")
        assert done.status_code == 200
        assert [e["type"] for e in _chat_lines(done)] == ["delta", "done"]
        assert runtime.resources.latest(alice.id, "chat-done-0000000001").state == "released"
        assert post(owner, "chat-done-0000000001").status_code == 409

    # 2. Public error event: framed to the client, recorded as failure, retryable.
    server.rabbit_chat = StubChatService(
        lambda: iter(
            [{"type": "delta", "text": "partial"}, {"type": "error", "code": "unavailable"}]
        )
    )
    with http_client(server, "alice") as owner:
        error = post(owner, "chat-error-000000001")
        assert error.status_code == 200
        assert _chat_lines(error)[-1]["type"] == "error"
        admission = runtime.resources.latest(alice.id, "chat-error-000000001")
        assert admission.state == "failed" and admission.reason == "chat_failed"
        assert post(owner, "chat-error-000000001").status_code == 200  # same id retried

    # 3. Generator crash mid-stream: headers/delta stand, no second HTTP response,
    #    failure recorded, cleanup explosion cannot mask it or strand quota.
    server.rabbit_chat = StubChatService(
        lambda: RaisingCloseIterator(
            [{"type": "delta", "text": "partial"}, RuntimeError("fixture provider crash")]
        )
    )
    with http_client(server, "alice") as owner:
        crashed = post(owner, "chat-crash-000000001")
        assert crashed.status_code == 200
        assert _chat_lines(crashed) == [{"type": "delta", "text": "partial"}]
        admission = runtime.resources.latest(alice.id, "chat-crash-000000001")
        assert admission.state == "failed" and admission.reason == "chat_failed"
        assert post(owner, "chat-crash-000000001").status_code == 200  # same id retried

    # 4. Pre-stream failure: proper JSON error, admission failed, retryable.
    from easydesign.product.rabbit_chat import RabbitChatService

    server.rabbit_chat = RabbitChatService(None)
    with http_client(server, "alice") as owner:
        unavailable = post(owner, "chat-down-0000000001")
        assert unavailable.status_code == 503
        admission = runtime.resources.latest(alice.id, "chat-down-0000000001")
        assert admission.state == "failed" and admission.reason == "chat_unavailable"
        assert post(owner, "chat-down-0000000001").status_code == 503

    # 5. A done event survives a cleanup explosion: delivery, not cleanup, decides.
    server.rabbit_chat = StubChatService(lambda: RaisingCloseIterator([{"type": "done"}]))
    with http_client(server, "alice") as owner:
        survived = post(owner, "chat-clean-0000000001")
        assert survived.status_code == 200
        assert runtime.resources.latest(alice.id, "chat-clean-0000000001").state == "released"


def test_upload_identity_is_canonical_and_rejections_never_charge(http_product):
    from tests.agent_support import structure

    server, runtime, _store, _admin, alice, _team, _launched = http_product
    base = f"/api/v1/scopes/{alice.id}"

    def upload(client, filename, data):
        return client.post(base + "/inputs", params={"filename": filename}, content=data)

    def stored() -> int:
        return runtime.resources.usage(alice, alice.id)["stored_upload_bytes"]

    payload = structure("A").encode()
    with http_client(server, "alice") as owner:
        first = upload(owner, "target-a.pdb", payload)
        assert first.status_code == 201, first.text
        charge = stored()
        assert charge == len(payload)
        # Same bytes, different filename: one canonical input, one charge.
        second = upload(owner, "renamed-target.pdb", payload)
        assert second.status_code == 201
        assert second.json()["id"] == first.json()["id"]
        assert stored() == charge
        # Rejections before storage never reserve quota.
        assert upload(owner, "notes.txt", b"plaintext").status_code == 400
        assert upload(owner, "empty.pdb", b"").status_code == 400
        assert upload(owner, "huge.pdb", b"x" * (32 * 1024**2 + 1)).status_code == 413
        assert stored() == charge
        # Stored-but-unparseable bytes stay retained and charged (honest input).
        garbage = upload(owner, "garbage.pdb", b"not a structure at all")
        assert garbage.status_code == 400
        assert garbage.json()["error"]["code"] == "invalid_structure"
        assert stored() == charge + len(b"not a structure at all")
        again = upload(owner, "garbage-again.pdb", b"not a structure at all")
        assert again.status_code == 400
        assert stored() == charge + len(b"not a structure at all")  # charged once


def test_admin_management_reads_are_audited(http_product):
    server, runtime, store, admin, alice, team, _launched = http_product
    bob = store.register("bob", PASSWORD, "Bob")
    store.update_user(admin, bob.id, status="active")

    def audit_actions(actor_admin):
        with store.db() as db:
            return [
                row["action"]
                for row in db.execute(
                    "SELECT action FROM audit_events WHERE actor_id=? ORDER BY seq",
                    (admin.id if actor_admin else "user-unknown",),
                )
            ]

    with http_client(server, "alice") as plain:
        assert plain.get("/api/v1/admin/users").status_code == 403
        assert plain.get("/api/v1/admin/teams").status_code == 403
        assert plain.get("/api/v1/admin/admissions").status_code == 403
    assert not any(a.startswith("admin.") for a in audit_actions(True))

    with http_client(server, "admin") as administrator:
        assert administrator.get("/api/v1/admin/users").status_code == 200
        assert administrator.get("/api/v1/admin/teams").status_code == 200
        assert administrator.get("/api/v1/admin/admissions").status_code == 200
        assert administrator.get(f"/api/v1/quotas/{alice.id}").status_code == 200
        assert administrator.get(f"/api/v1/quotas/{admin.id}").status_code == 200
    actions = set(audit_actions(True))
    assert {"admin.users.read", "admin.teams.read", "admin.admissions.read"} <= actions
    # Foreign quota inspection is audited; the admin's own quota read is not.
    with store.db() as db:
        foreign = db.execute(
            "SELECT count(*) FROM audit_events WHERE action='admin.quota.read' AND target_id=?",
            (alice.id,),
        ).fetchone()[0]
        own = db.execute(
            "SELECT count(*) FROM audit_events WHERE action='admin.quota.read' AND target_id=?",
            (admin.id,),
        ).fetchone()[0]
    assert foreign == 1 and own == 0


def test_suspended_team_hides_roster_and_mutations_from_members(http_product):
    server, runtime, store, admin, alice, team, _launched = http_product
    bob = store.register("bob", PASSWORD, "Bob")
    store.update_user(admin, bob.id, status="active")
    invitation = store.invite(alice, team, "bob")
    store.respond_invitation(bob, invitation["id"], accept=True)

    with http_client(server, "bob") as member:
        assert member.get(f"/api/v1/teams/{team}").status_code == 200  # active roster read
    store.update_team(admin, team, status="suspended")
    with http_client(server, "bob") as member:
        assert member.get(f"/api/v1/teams/{team}").status_code == 404
        assert member.get(f"/api/v1/scopes/{team}/projects").status_code == 404
        denied = member.post(f"/api/v1/scopes/{team}/drafts", json={"title": "T", "goal": "G"})
        assert denied.status_code == 404
    with http_client(server, "admin") as administrator:
        inspected = administrator.get(f"/api/v1/teams/{team}")
        assert inspected.status_code == 200  # administrative inspection remains
        assert any(m["user_id"] == bob.id for m in inspected.json()["team"]["members"])
        restored = administrator.post(f"/api/v1/admin/teams/{team}", json={"status": "active"})
        assert restored.status_code == 200
    with http_client(server, "bob") as member:
        assert member.get(f"/api/v1/teams/{team}").status_code == 200
        assert member.get(f"/api/v1/scopes/{team}/projects").status_code == 200
    with store.db() as db:
        reads = db.execute(
            "SELECT count(*) FROM audit_events WHERE action='admin.team.read' AND scope_id=?",
            (team,),
        ).fetchone()[0]
    assert reads >= 1  # the suspended-team inspection was audited
