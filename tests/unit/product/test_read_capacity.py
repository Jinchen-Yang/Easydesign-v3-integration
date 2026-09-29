"""Bounded HTTP reads retain fresh authorization and independent write capacity."""

from __future__ import annotations

import json
import socket
import sqlite3
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path

import httpx
import pytest

from easydesign.product.account_server import MultiUserServer
from easydesign.product.accounts import AccountStore
from easydesign.product.capacity_config import load_capacity_config
from easydesign.product.contracts import ProductError
from easydesign.product.domain import NativeGateway
from easydesign.product.tenancy import MultiUserRuntime
from easydesign.product.transport_policy import TransportPolicy
from easydesign.workspace_context import WorkspaceContext

PASSWORD = "Read-capacity-synthetic-password!"
REQUEST_ID = "read-capacity-request-0001"
PROJECT_ID = "synthetic-read-project"


@contextmanager
def site(root: Path, policy: TransportPolicy):
    (root / "easydesign-workspace.yaml").write_text('schema_version: "0.1"\n')
    context = WorkspaceContext.from_root(root)
    context.ensure_layout()
    accounts = AccountStore(context.runtime_root / "state/accounts/accounts.sqlite")
    admin = accounts.bootstrap_admin("admin", PASSWORD, "Synthetic administrator")
    runtime = MultiUserRuntime(context, accounts, lambda c: NativeGateway(c, root / "models.yaml"))
    with runtime.bind(admin, admin.id) as service:
        (service.context.projects_root / PROJECT_ID).mkdir(parents=True)
        journal = service.journal()
        try:
            journal.reserve(PROJECT_ID, {"request_id": REQUEST_ID})
            journal.update(REQUEST_ID, "succeeded", {"message": "Synthetic completed request"})
            journal.register_project(
                PROJECT_ID,
                request_id=REQUEST_ID,
                title="Synthetic read-only fixture",
                goal="Synthetic target",
                thread="synthetic-thread",
                input_id=None,
                surface="easy",
            )
        finally:
            journal.close()
    server = MultiUserServer(runtime, port=0, transport_policy=policy)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    origin = f"http://127.0.0.1:{server.server_port}"
    try:
        with httpx.Client(
            base_url=origin, headers={"Origin": origin}, trust_env=False, timeout=8
        ) as client:
            login = client.post(
                "/api/v1/accounts/login", json={"username": "admin", "password": PASSWORD}
            )
            assert login.status_code == 200
            client.headers["X-CSRF-Token"] = login.json()["csrf_token"]
            yield server, client, admin
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


class JournalReadPause:
    """Pause real SQLite reads at the storage boundary; never replace product behavior."""

    def __init__(self, monkeypatch):
        self.entered = threading.Event()
        self.release = threading.Event()
        connect = sqlite3.connect

        def open_database(database, *args, **kwargs):
            db = connect(database, *args, **kwargs)
            if str(database).endswith("requests.sqlite"):
                db.set_trace_callback(self.trace)
            return db

        monkeypatch.setattr(sqlite3, "connect", open_database)

    def trace(self, statement):
        if statement.startswith("SELECT * FROM requests WHERE id="):
            self.entered.set()
            self.release.wait(timeout=4)


class LeaseProbe:
    """Observe a real bounded semaphore without changing admission decisions."""

    def __init__(self, semaphore):
        self.semaphore = semaphore
        self.condition = threading.Condition()
        self.attempts = self.entered = self.released = self.active = self.peak = 0

    def acquire(self, *args, **kwargs):
        with self.condition:
            self.attempts += 1
            self.condition.notify_all()
        acquired = self.semaphore.acquire(*args, **kwargs)
        if acquired:
            with self.condition:
                self.entered += 1
                self.active += 1
                self.peak = max(self.peak, self.active)
                self.condition.notify_all()
        return acquired

    def release(self):
        with self.condition:
            self.released += 1
            self.active -= 1
            self.semaphore.release()
            self.condition.notify_all()

    def wait(self, field, value):
        with self.condition:
            assert self.condition.wait_for(lambda: getattr(self, field) >= value, timeout=3)


def observe_read_slots(server):
    probe = LeaseProbe(server.read_slots)
    server.read_slots = probe
    return probe


def test_status_read_waits_in_http_then_times_out_without_entering_the_full_reader(
    tmp_path, monkeypatch
):
    policy = TransportPolicy(max_readers=1, read_wait_timeout=0.15)
    with site(tmp_path, policy) as (server, client, admin):
        probe = observe_read_slots(server)
        path = f"/api/v1/scopes/{admin.id}/requests/{REQUEST_ID}"
        paused = JournalReadPause(monkeypatch)
        with ThreadPoolExecutor(max_workers=1) as executor:
            first = executor.submit(client.get, path)
            try:
                assert paused.entered.wait(timeout=3)
                started = time.monotonic()
                overloaded = client.get(path)
                elapsed = time.monotonic() - started
                assert overloaded.status_code == 503
                assert overloaded.json()["error"]["code"] == "read_busy"
                assert overloaded.headers["Retry-After"] == "2"
                assert overloaded.headers["Cache-Control"] == "no-store"
                assert 0.1 <= elapsed < 2
                assert not first.done()
            finally:
                paused.release.set()
            assert first.result(timeout=3).status_code == 200
        assert client.get(path).status_code == 200
        probe.wait("released", 2)
        assert (probe.attempts, probe.entered, probe.released, probe.peak) == (3, 2, 2, 1)


def test_readers_wait_for_processing_slots_and_http_time_includes_the_wait(tmp_path, monkeypatch):
    with site(tmp_path, TransportPolicy(max_readers=2, read_wait_timeout=2)) as (
        server,
        client,
        admin,
    ):
        probe = observe_read_slots(server)
        paused = JournalReadPause(monkeypatch)
        path = f"/api/v1/scopes/{admin.id}/requests/{REQUEST_ID}"
        with ThreadPoolExecutor(max_workers=3) as executor:
            first = [executor.submit(client.get, path) for _ in range(2)]
            try:
                probe.wait("entered", 2)
                assert paused.entered.wait(timeout=3)
                started = time.monotonic()
                third = executor.submit(client.get, path)
                probe.wait("attempts", 3)
                with pytest.raises(TimeoutError):
                    third.result(timeout=0.1)
                assert probe.peak == 2
                assert client.get("/api/v1/accounts/config").status_code == 200
            finally:
                paused.release.set()
            assert [reply.result(timeout=3).status_code for reply in first] == [200, 200]
            assert third.result(timeout=3).status_code == 200
            assert time.monotonic() - started >= 0.1
        probe.wait("released", 3)
        assert (probe.entered, probe.released, probe.active, probe.peak) == (3, 3, 0, 2)


def test_waiting_readers_remain_bounded_by_existing_http_connection_limit(tmp_path, monkeypatch):
    policy = TransportPolicy(max_connections=2, max_uploads=1, max_readers=1, read_wait_timeout=2)
    with site(tmp_path, policy) as (server, client, admin):
        probe = observe_read_slots(server)
        paused = JournalReadPause(monkeypatch)
        path = f"/api/v1/scopes/{admin.id}/requests/{REQUEST_ID}"
        with ThreadPoolExecutor(max_workers=2) as executor:
            first = executor.submit(client.get, path)
            try:
                assert paused.entered.wait(timeout=3)
                second = executor.submit(client.get, path)
                probe.wait("attempts", 2)
                rejected = client.get("/api/v1/accounts/config")
                assert rejected.status_code == 503
                assert rejected.json()["error"]["code"] == "http_busy"
            finally:
                paused.release.set()
            assert first.result(timeout=3).status_code == 200
            assert second.result(timeout=3).status_code == 200
        probe.wait("released", 2)
        assert (probe.attempts, probe.entered, probe.released, probe.peak) == (2, 2, 2, 1)


def test_logout_while_waiting_is_checked_after_read_capacity_is_available(tmp_path, monkeypatch):
    with site(tmp_path, TransportPolicy(max_readers=1, read_wait_timeout=2)) as (
        server,
        client,
        admin,
    ):
        probe = observe_read_slots(server)
        paused = JournalReadPause(monkeypatch)
        path = f"/api/v1/scopes/{admin.id}/requests/{REQUEST_ID}"
        with ThreadPoolExecutor(max_workers=2) as executor:
            first = executor.submit(client.get, path)
            try:
                assert paused.entered.wait(timeout=3)
                waiting = executor.submit(client.get, path)
                probe.wait("attempts", 2)
                assert client.post("/api/v1/accounts/logout", json={}).status_code == 200
            finally:
                paused.release.set()
            assert first.result(timeout=3).status_code == 200
            rejected = waiting.result(timeout=3)
            assert rejected.status_code == 401
            assert rejected.json()["error"]["code"] == "unauthorized"
        probe.wait("released", 2)
        assert probe.entered == probe.released == 2


def test_team_removal_while_waiting_does_not_reuse_old_scope_access(tmp_path, monkeypatch):
    with site(tmp_path, TransportPolicy(max_readers=1, read_wait_timeout=2)) as (
        server,
        client,
        admin,
    ):
        accounts = server.accounts
        alice = accounts.register("alice", PASSWORD, "Synthetic member")
        accounts.update_user(admin, alice.id, status="active")
        team = accounts.create_team(admin, "Synthetic reader team")
        invitation = accounts.invite(admin, team["id"], "alice")
        accounts.respond_invitation(alice, invitation["id"], accept=True)
        with server.runtime.bind(admin, team["id"]) as service:
            (service.context.projects_root / PROJECT_ID).mkdir(parents=True)
            journal = service.journal()
            try:
                journal.register_project(
                    PROJECT_ID,
                    request_id=REQUEST_ID,
                    title="Synthetic team read fixture",
                    goal="Synthetic target",
                    thread="synthetic-team-thread",
                    input_id=None,
                    surface="easy",
                )
            finally:
                journal.close()
        team_path = f"/api/v1/scopes/{team['id']}/projects/{PROJECT_ID}/workbench"
        origin = str(client.base_url).rstrip("/")
        with httpx.Client(base_url=origin, headers={"Origin": origin}, trust_env=False) as member:
            login = member.post(
                "/api/v1/accounts/login", json={"username": "alice", "password": PASSWORD}
            )
            assert login.status_code == 200
            member.headers["X-CSRF-Token"] = login.json()["csrf_token"]
            assert member.get(f"/api/v1/scopes/{team['id']}/usage").status_code == 200
            before = member.get(team_path)
            assert before.status_code == 200
            assert before.json()["project"]["id"] == PROJECT_ID
            probe = observe_read_slots(server)
            paused = JournalReadPause(monkeypatch)
            with ThreadPoolExecutor(max_workers=2) as executor:
                first = executor.submit(
                    client.get, f"/api/v1/scopes/{admin.id}/requests/{REQUEST_ID}"
                )
                try:
                    assert paused.entered.wait(timeout=3)
                    waiting = executor.submit(member.get, team_path)
                    probe.wait("attempts", 2)
                    removed = client.post(
                        f"/api/v1/teams/{team['id']}/members/{alice.id}", json={"remove": True}
                    )
                    assert removed.status_code == 200
                finally:
                    paused.release.set()
                assert first.result(timeout=3).status_code == 200
                rejected = waiting.result(timeout=3)
                assert rejected.status_code == 404
                assert rejected.json()["error"]["code"] == "not_found"
            probe.wait("released", 2)
            assert probe.entered == probe.released == 2


def test_workspace_capacity_file_configures_reads_without_invalidating_small_connections(tmp_path):
    path = tmp_path / "capacity.json"
    path.write_text(
        json.dumps(
            {
                "http": {
                    "max_connections": 2,
                    "max_uploads": 1,
                    "max_readers": 16,
                    "read_wait_timeout": 0.25,
                }
            }
        )
    )
    policy = load_capacity_config(tmp_path, path).http.policy()
    assert policy.max_readers == 16
    assert policy.read_wait_timeout == 0.25
    assert policy.max_connections == 2
    defaults = load_capacity_config(tmp_path, None).http.policy()
    assert defaults.max_readers == 16
    assert defaults.read_wait_timeout == 10.0


@pytest.mark.parametrize(
    "field,value",
    [
        ("max_readers", True),
        ("max_readers", False),
        ("max_readers", 0),
        ("max_readers", -1),
        ("max_readers", 4097),
        ("max_readers", 1.5),
        ("max_readers", "16"),
        ("read_wait_timeout", True),
        ("read_wait_timeout", False),
        ("read_wait_timeout", -0.01),
        ("read_wait_timeout", 121),
        ("read_wait_timeout", float("nan")),
        ("read_wait_timeout", float("inf")),
        ("read_wait_timeout", float("-inf")),
        ("read_wait_timeout", "10"),
    ],
)
def test_read_capacity_rejects_invalid_file_and_direct_policy_values(tmp_path, field, value):
    path = tmp_path / "capacity.json"
    path.write_text(json.dumps({"http": {field: value}}))
    with pytest.raises(ProductError) as error:
        load_capacity_config(tmp_path, path)
    assert error.value.code == "invalid_capacity_config"
    with pytest.raises(ValueError):
        TransportPolicy(**{field: value})


def test_route_aliases_share_the_same_capacity_gate_as_the_actual_dispatcher(tmp_path):
    with site(tmp_path, TransportPolicy(max_readers=1, read_wait_timeout=0)) as (
        server,
        client,
        admin,
    ):
        prefix = f"/api/v1/scopes/{admin.id}"
        aliases = [
            f"{prefix}/requests/{REQUEST_ID}",
            httpx.URL(client.base_url).copy_with(
                raw_path=f"/{prefix}/requests/{REQUEST_ID}".encode()
            ),
            f"{prefix}/requests/{REQUEST_ID}///?ignored=true",
            f"/api/v1/%73copes/{admin.id}/%72equests/{REQUEST_ID}",
            f"/api/v1/scopes%2F{admin.id}%2Frequests%2F{REQUEST_ID}",
            f"{prefix}/projects/{PROJECT_ID}/workbench",
            f"{prefix}/projects/{PROJECT_ID}/workbench///?ignored=true",
            f"{prefix}/projects/{PROJECT_ID}/%77orkbench",
            f"{prefix}/projects%2F{PROJECT_ID}%2Fworkbench",
        ]
        for path in aliases:
            # Prove that each spelling actually routes, not only that a matcher
            # classifies it; the fixture contains no science workers or models.
            assert client.get(path).status_code == 200, path
            # The response reaches the client before the serving thread reaches
            # its finally-release, so wait briefly instead of racing the assert.
            deadline = time.monotonic() + 2.0
            while not server.read_slots.acquire(blocking=False):
                if time.monotonic() > deadline:
                    pytest.fail(f"read slot was not released after: {path}")
                time.sleep(0.005)
            try:
                result = client.get(path)
                assert result.status_code == 503, path
                assert result.json()["error"]["code"] == "read_busy"
                assert result.headers["Retry-After"] == "2"
            finally:
                server.read_slots.release()
        with server.read_slots:
            for path in (
                f"{prefix}/%2572equests/{REQUEST_ID}",
                f"{prefix}/requests/%00{REQUEST_ID}",
                f"{prefix}/requests/%5c{REQUEST_ID}",
                f"{prefix}/requests/%2e%2e/{REQUEST_ID}",
            ):
                result = client.get(path)
                assert result.status_code == 403
                assert result.json()["error"]["code"] == "invalid_path"


def test_nonmatching_gets_posts_login_upload_and_ai_do_not_take_read_capacity(tmp_path):
    with site(tmp_path, TransportPolicy(max_readers=1, read_wait_timeout=0)) as (
        server,
        client,
        admin,
    ):
        prefix = f"/api/v1/scopes/{admin.id}"
        probe = observe_read_slots(server)
        assert probe.acquire(blocking=False)
        try:
            for path, expected in (
                ("/api/v1/accounts/config", 200),
                ("/api/v1/accounts/me", 200),
                (f"{prefix}/health", 200),
                (f"{prefix}/usage", 200),
                (f"{prefix}/projects", 200),
                (f"{prefix}/requests/{REQUEST_ID}/not-a-resource", 404),
                (f"{prefix}/rabbit/requests/not-an-ai-request", 404),
                (f"{prefix}/projects/{PROJECT_ID}/events", 200),
                ("/not-built-static", 404),
            ):
                assert client.get(path).status_code == expected, path
            ai = client.post(f"{prefix}/rabbit/chat", json={})
            assert ai.status_code == 400
            invalid_write = client.post(f"{prefix}/projects", json={})
            assert invalid_write.status_code == 400
            assert client.post(f"{prefix}/requests/{REQUEST_ID}", json={}).status_code == 404
            upload = client.post(
                f"{prefix}/inputs?filename=synthetic.fasta", content=b">synthetic\nACDEFGHIK\n"
            )
            assert upload.status_code == 201
            login = client.post(
                "/api/v1/accounts/login", json={"username": "admin", "password": PASSWORD}
            )
            assert login.status_code == 200
            assert probe.attempts == 1
        finally:
            probe.release()


@pytest.mark.parametrize("failure", ["business", "storage", "disconnect"])
def test_http_errors_and_disconnect_release_each_acquired_read_slot_once(
    tmp_path, monkeypatch, failure
):
    with site(tmp_path, TransportPolicy(max_readers=1, read_wait_timeout=0)) as (
        server,
        client,
        admin,
    ):
        probe = observe_read_slots(server)
        path = f"/api/v1/scopes/{admin.id}/requests/{REQUEST_ID}"
        if failure == "business":
            failed = client.get(f"/api/v1/scopes/{admin.id}/requests/not-a-known-request")
            assert failed.status_code == 404
        elif failure == "storage":
            connect = sqlite3.connect
            failed_once = False

            def open_database(database, *args, **kwargs):
                nonlocal failed_once
                if str(database).endswith("requests.sqlite") and not failed_once:
                    failed_once = True
                    raise sqlite3.OperationalError("Synthetic storage read failure")
                return connect(database, *args, **kwargs)

            monkeypatch.setattr(sqlite3, "connect", open_database)
            assert client.get(path).status_code == 500
        else:
            send = socket.socket.sendall
            failed_once = False

            def sendall(connection, *args, **kwargs):
                nonlocal failed_once
                if connection.getsockname()[1] == server.server_port and not failed_once:
                    failed_once = True
                    raise BrokenPipeError("Synthetic client disconnected")
                return send(connection, *args, **kwargs)

            monkeypatch.setattr(socket.socket, "sendall", sendall)
            with pytest.raises(httpx.RemoteProtocolError):
                client.get(path)
        probe.wait("released", 1)
        assert (probe.entered, probe.released, probe.active) == (1, 1, 0)
        assert client.get(path).status_code == 200
        probe.wait("released", 2)
        assert (probe.entered, probe.released, probe.active) == (2, 2, 0)
