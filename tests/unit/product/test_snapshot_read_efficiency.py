"""A scoped live snapshot reuses connections only for its current request."""

import sqlite3
from collections import Counter

import pytest

from easydesign.agent.session_store import SessionStore
from easydesign.product import service as service_module
from easydesign.product.accounts import AccountStore
from easydesign.product.contracts import CreateProject, ProductError
from easydesign.product.domain import NativeGateway
from easydesign.product.journal import RequestJournal
from easydesign.product.resource_supervisor import ResourceSupervisor
from easydesign.product.service import ProductService
from easydesign.product.tenancy import MultiUserRuntime
from easydesign.workspace_context import WorkspaceContext


@pytest.fixture
def queued_project(tmp_path, monkeypatch):
    (tmp_path / "easydesign-workspace.yaml").write_text('schema_version: "0.1"\n')
    (tmp_path / "models.yaml").write_text(
        "default:\n  provider: openai\n  model: fixture\n"
        "  secret_env: EASYDESIGN_SNAPSHOT_FIXTURE_KEY\n"
    )
    monkeypatch.delenv("EASYDESIGN_SNAPSHOT_FIXTURE_KEY", raising=False)
    context = WorkspaceContext.from_root(tmp_path)
    context.ensure_layout()
    accounts = AccountStore(context.runtime_root / "state/accounts/accounts.sqlite")
    password = "Snapshot-fixture-password-2026!"
    admin = accounts.bootstrap_admin("admin", password, "Admin")
    alice = accounts.register("alice", password, "Alice")
    accounts.update_user(admin, alice.id, status="active")

    def no_models(*_args, **_kwargs):
        pytest.fail("A queued snapshot must not invoke scientific models")

    runtime = MultiUserRuntime(
        context,
        accounts,
        lambda scoped: NativeGateway(scoped, tmp_path / "models.yaml", model_factory=no_models),
    )

    class Busy:
        def snapshots(self):
            return ()

    supervisor = ResourceSupervisor(runtime, probe=Busy())
    runtime.launcher = supervisor.launch
    with runtime.bind(alice, alice.id) as service:
        accepted = service.create(
            CreateProject(
                request_id="snapshot-efficiency-request-01",
                title="Synthetic queued project",
                goal="Synthetic target",
            )
        )
    yield runtime, accounts, admin, alice, accepted
    supervisor.close()


def test_queued_snapshot_opens_each_database_once_without_losing_queue_projection(
    queued_project, monkeypatch
):
    runtime, _accounts, _admin, alice, accepted = queued_project
    opens = Counter()
    for cls, key in ((RequestJournal, "journal"), (SessionStore, "session")):
        original = cls.__init__

        def counted(self, *args, _original=original, _key=key, **kwargs):
            opens[_key] += 1
            _original(self, *args, **kwargs)

        monkeypatch.setattr(cls, "__init__", counted)
    with runtime.bind(alice, alice.id) as service:
        snapshot = service.snapshot(accepted["project"])
    row = snapshot["requests"][0]
    assert row["id"] == accepted["id"]
    assert row["state"] == "accepted"
    assert row["result"]["queue"] == {
        "state": "queued",
        "position": 1,
        "reason": "waiting_for_resources",
        "cancellable": True,
    }
    assert opens == {"journal": 1, "session": 1}


def test_snapshot_rejects_legacy_invalid_request_identity_before_worker_lock(queued_project):
    runtime, _accounts, _admin, alice, accepted = queued_project
    with runtime.bind(alice, alice.id) as scoped:
        native = ProductService(scoped.gateway)
        journal = native.journal()
        try:
            journal.db.execute(
                "UPDATE requests SET id=?,updated=updated-60 WHERE id=?",
                ("../outside-allowed-workers", accepted["id"]),
            )
            journal.db.commit()
        finally:
            journal.close()
        (native.root / "workers").mkdir(exist_ok=True)
        outside = native.root / "outside-allowed-workers.lock"
        with pytest.raises(ProductError) as error:
            native.snapshot(accepted["project"])
        assert error.value.code == "not_found"
        assert not outside.exists()


@pytest.mark.parametrize("failure_stage", ["activity_read", "projection_write"])
def test_snapshot_closes_owned_connections_and_preserves_errors(
    queued_project, monkeypatch, failure_stage
):
    runtime, _accounts, _admin, alice, accepted = queued_project
    connections = []
    for cls in (RequestJournal, SessionStore):
        original = cls.__init__

        def opened(self, *args, _original=original, **kwargs):
            _original(self, *args, **kwargs)
            connections.append(self.db)

        monkeypatch.setattr(cls, "__init__", opened)

    def fail(*_args, **_kwargs):
        raise sqlite3.OperationalError("synthetic projection boundary failure")

    if failure_stage == "activity_read":
        monkeypatch.setattr(service_module, "activity_rows", fail)
    else:
        monkeypatch.setattr(RequestJournal, "update_projection", fail)
    with runtime.bind(alice, alice.id) as service:
        with pytest.raises(sqlite3.OperationalError, match="synthetic projection boundary failure"):
            service.snapshot(accepted["project"])
    assert len(connections) == 2
    for connection in connections:
        with pytest.raises(sqlite3.ProgrammingError, match="closed"):
            connection.execute("SELECT 1")


def test_active_snapshot_reloads_new_events_and_queue_state(queued_project):
    runtime, _accounts, _admin, alice, accepted = queued_project
    with runtime.bind(alice, alice.id) as service:
        first = service.snapshot(accepted["project"])
        store = SessionStore(service.context.projects_root / accepted["project"])
        try:
            store.event(first["project"]["thread_id"], "user", {"text": "Later synthetic input"})
        finally:
            store.close()
        admission = runtime.resources.latest(alice.id, accepted["id"])
        runtime.resources.transition(admission.id, "starting")
        second = service.snapshot(accepted["project"])
    assert second["event_cursor"] > first["event_cursor"]
    assert second["revision"] != first["revision"]
    assert first["requests"][0]["result"]["queue"]["state"] == "queued"
    assert second["requests"][0]["result"]["queue"] == {
        "state": "starting",
        "position": None,
        "reason": "worker_starting",
        "cancellable": False,
    }


def test_snapshot_hook_rechecks_scope_after_account_revocation(queued_project):
    runtime, accounts, admin, alice, accepted = queued_project
    with runtime.bind(alice, alice.id) as service:
        assert service.snapshot(accepted["project"])["requests"][0]["state"] == "accepted"
        accounts.update_user(admin, alice.id, status="suspended")
        with pytest.raises(ProductError) as error:
            service.snapshot(accepted["project"])
    assert error.value.code == "unauthorized"


def test_native_snapshot_retains_interrupted_worker_reconciliation(queued_project):
    runtime, _accounts, _admin, alice, accepted = queued_project
    with runtime.bind(alice, alice.id) as scoped:
        native = ProductService(scoped.gateway)
        journal = native.journal()
        try:
            journal.db.execute(
                "UPDATE requests SET updated=updated-60 WHERE id=?", (accepted["id"],)
            )
            journal.db.commit()
        finally:
            journal.close()
        snapshot = native.snapshot(accepted["project"])
        assert snapshot["requests"][0]["state"] == "interrupted"
        assert snapshot["requests"][0]["result"]["code"] == "worker_interrupted"
        assert native.request(accepted["id"])["state"] == "interrupted"


def test_scoped_snapshot_retains_failed_admission_journal_repair(queued_project):
    runtime, _accounts, _admin, alice, accepted = queued_project
    admission = runtime.resources.latest(alice.id, accepted["id"])
    runtime.resources.transition(admission.id, "failed", reason="worker_start_timeout")
    with runtime.bind(alice, alice.id) as service:
        snapshot = service.snapshot(accepted["project"])
        assert snapshot["requests"][0]["state"] == "failed"
        assert snapshot["requests"][0]["result"]["code"] == "worker_start_timeout"
        journal = service.journal()
        try:
            assert journal.get(accepted["id"])["state"] == "failed"
        finally:
            journal.close()
