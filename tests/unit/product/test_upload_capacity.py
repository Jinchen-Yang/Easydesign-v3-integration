from __future__ import annotations

import json
import os
import socket
import socketserver
import threading
import time
from contextlib import ExitStack, contextmanager
from http.client import HTTPResponse
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

PASSWORD = "Upload-capacity-fixture-password!"
FASTA = b">fixture\nACDEFGHIK\n"


class SlotProbe:
    """Observe the real semaphore without changing its admission behavior."""

    def __init__(self, semaphore):
        self.semaphore = semaphore
        self.condition = threading.Condition()
        self.attempted = self.entered = self.released = self.active = self.peak = 0

    def acquire(self, *args, **kwargs):
        with self.condition:
            self.attempted += 1
            self.condition.notify_all()
        admitted = self.semaphore.acquire(*args, **kwargs)
        if admitted:
            with self.condition:
                self.entered += 1
                self.active += 1
                self.peak = max(self.peak, self.active)
                self.condition.notify_all()
        return admitted

    def release(self):
        with self.condition:
            self.released += 1
            self.active -= 1
            self.semaphore.release()
            self.condition.notify_all()

    def wait(self, field, count):
        with self.condition:
            assert self.condition.wait_for(lambda: getattr(self, field) >= count, timeout=3)


@contextmanager
def site(root: Path, policy: TransportPolicy):
    (root / "easydesign-workspace.yaml").write_text('schema_version: "0.1"\n')
    context = WorkspaceContext.from_root(root)
    context.ensure_layout()
    accounts = AccountStore(context.runtime_root / "state/accounts/accounts.sqlite")
    admin = accounts.bootstrap_admin("admin", PASSWORD, "Synthetic admin")
    runtime = MultiUserRuntime(context, accounts, lambda c: NativeGateway(c, root / "models.yaml"))
    server = MultiUserServer(runtime, port=0, transport_policy=policy)
    probe = SlotProbe(server.upload_slots)
    server.upload_slots = probe
    server.upload_admissions = SlotProbe(server.upload_admissions)
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
            client.headers["X-CSRF-Token"] = login.json()["csrf_token"]
            yield server, client, admin, probe
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def upload_path(scope):
    return f"/api/v1/scopes/{scope}/inputs?filename=fixture.fasta"


@contextmanager
def partial_upload(client, path, body=FASTA, *, headers=None):
    request = client.build_request("POST", path, content=body, headers=headers)
    address = (request.url.host, request.url.port)
    with socket.create_connection(address, timeout=5) as connection:
        head = f"POST {request.url.raw_path.decode()} HTTP/1.1\r\n"
        head += "".join(f"{key}: {value}\r\n" for key, value in request.headers.multi_items())
        connection.sendall((head + "\r\n").encode() + body[:1])
        yield connection


def response(connection):
    result = HTTPResponse(connection)
    result.begin()
    body = result.read()
    return result.status, result.headers, body


def test_default_upload_policy_waits_for_a_slot_then_publishes_without_duplicate_quota(tmp_path):
    policy = TransportPolicy(max_connections=4, max_uploads=1, body_timeout=3)
    with site(tmp_path, policy) as (_server, client, admin, probe):
        path = upload_path(admin.id)
        completed = threading.Event()
        replies = []

        def second_upload():
            replies.append(client.post(path, content=FASTA))
            completed.set()

        with partial_upload(client, path) as first:
            probe.wait("entered", 1)
            second = threading.Thread(target=second_upload)
            second.start()
            try:
                probe.wait("attempted", 2)
                assert not completed.wait(0.2), "A short burst must wait, not immediately reject"
                assert client.get("/api/v1/accounts/config").status_code == 200
                first.sendall(FASTA[1:])
                assert response(first)[0] == 201
            finally:
                first.shutdown(socket.SHUT_WR)
                second.join(timeout=5)
            assert not second.is_alive()
            assert replies[0].status_code == 201
        assert probe.peak == 1
        usage = client.get(f"/api/v1/scopes/{admin.id}/usage").json()
        assert usage["stored_upload_bytes"] == len(FASTA)


def test_capacity_file_enables_bounded_waiting_by_default_and_clamps_to_connection_headroom(
    tmp_path,
):
    default = load_capacity_config(tmp_path, None).http.policy()
    assert (default.max_uploads, default.max_pending_uploads, default.upload_wait_timeout) == (
        4,
        300,
        10,
    )
    assert default.effective_pending_uploads == 300
    assert default.max_connections - default.max_uploads - default.effective_pending_uploads == 80
    path = tmp_path / "capacity.json"
    path.write_text(
        json.dumps(
            {
                "http": {
                    "max_connections": 4,
                    "max_uploads": 1,
                    "max_pending_uploads": 300,
                    "upload_wait_timeout": 0.25,
                }
            }
        )
    )
    small = load_capacity_config(tmp_path, path).http.policy()
    assert small.effective_pending_uploads == 2
    assert small.upload_wait_timeout == 0.25
    assert TransportPolicy(max_connections=2, max_uploads=1).effective_pending_uploads == 0
    assert TransportPolicy(max_connections=384, max_uploads=383).effective_pending_uploads == 0
    assert TransportPolicy(max_pending_uploads=0).effective_pending_uploads == 0
    for field, value in [
        ("max_pending_uploads", True),
        ("max_pending_uploads", -1),
        ("max_pending_uploads", 1.5),
        ("max_pending_uploads", 4097),
        ("upload_wait_timeout", True),
        ("upload_wait_timeout", -0.1),
        ("upload_wait_timeout", 121),
        ("upload_wait_timeout", float("nan")),
    ]:
        path.write_text(json.dumps({"http": {field: value}}))
        with pytest.raises(ProductError, match="容量配置"):
            load_capacity_config(tmp_path, path)
        with pytest.raises(ValueError):
            TransportPolicy(**{field: value})


@pytest.mark.parametrize(
    "headers,status",
    [
        ({"Content-Length": str(32 * 1024**2 + 1)}, 413),
        ({"Content-Length": "-1"}, 400),
        ({"Transfer-Encoding": "chunked"}, 400),
        ([("Content-Length", "17"), ("Content-Length", "18")], 400),
    ],
)
def test_invalid_upload_headers_are_rejected_before_waiting_for_body_capacity(
    tmp_path, headers, status
):
    with site(tmp_path, TransportPolicy(max_connections=5, max_uploads=1, body_timeout=2)) as (
        _server,
        client,
        admin,
        probe,
    ):
        path = upload_path(admin.id)
        with partial_upload(client, path) as first:
            probe.wait("entered", 1)
            try:
                with partial_upload(client, path, headers=headers) as invalid:
                    invalid.settimeout(0.5)
                    result, response_headers, _body = response(invalid)
                    assert result == status
                    assert response_headers["Connection"] == "close"
            finally:
                first.shutdown(socket.SHUT_WR)
                response(first)
        assert client.get(f"/api/v1/scopes/{admin.id}/usage").json()["stored_upload_bytes"] == 0
        assert client.post(path, content=FASTA).status_code == 201


def test_upload_wait_and_body_share_one_absolute_deadline(tmp_path):
    policy = TransportPolicy(max_connections=5, max_uploads=1, body_timeout=2)
    with site(tmp_path, policy) as (_server, client, admin, probe):
        path = upload_path(admin.id)
        with partial_upload(client, path) as first:
            probe.wait("entered", 1)
            started = time.monotonic()
            with partial_upload(client, path) as second:
                probe.wait("attempted", 2)
                # Deliberately spend over half the total body budget in the queue.
                time.sleep(1.1)
                first.sendall(FASTA[1:])
                assert response(first)[0] == 201
                status, headers, body = response(second)
                elapsed = time.monotonic() - started
                assert status == 408
                assert json.loads(body)["error"]["code"] == "body_timeout"
                assert headers["Connection"] == "close"
                assert elapsed < 2.7, "Acquiring a slot must not reset the two-second body budget"
        assert probe.peak == 1
        assert client.get(f"/api/v1/scopes/{admin.id}/usage").json()["stored_upload_bytes"] == len(
            FASTA
        )
        assert client.post(path, content=FASTA).status_code == 201


def test_upload_pending_bound_rejects_early_preserves_reads_and_releases_cancelled_waiters(
    tmp_path,
):
    policy = TransportPolicy(
        max_connections=5, max_uploads=1, max_pending_uploads=1, body_timeout=3
    )
    with site(tmp_path, policy) as (_server, client, admin, probe):
        path = upload_path(admin.id)
        with partial_upload(client, path) as first:
            probe.wait("entered", 1)
            with partial_upload(client, path) as second:
                probe.wait("attempted", 2)
                try:
                    rejected = client.post(path, content=FASTA)
                    assert rejected.status_code == 503
                    assert rejected.json()["error"]["code"] == "upload_busy"
                    assert rejected.headers["Connection"] == "close"
                    assert rejected.headers["Retry-After"] == "2"
                    assert client.get("/api/v1/accounts/config").status_code == 200
                    assert probe.peak == 1
                finally:
                    second.shutdown(socket.SHUT_WR)
                    first.shutdown(socket.SHUT_WR)
                    assert response(first)[0] == 400
                    assert response(second)[0] == 400
        assert client.get(f"/api/v1/scopes/{admin.id}/usage").json()["stored_upload_bytes"] == 0
        assert client.post(path, content=FASTA).status_code == 201


def test_upload_wait_timeout_is_retryable_without_reserving_storage(tmp_path):
    policy = TransportPolicy(
        max_connections=5, max_uploads=1, upload_wait_timeout=0.15, body_timeout=3
    )
    with site(tmp_path, policy) as (_server, client, admin, probe):
        path = upload_path(admin.id)
        with partial_upload(client, path) as first:
            probe.wait("entered", 1)
            try:
                rejected = client.post(path, content=FASTA)
                assert rejected.status_code == 503
                assert rejected.json()["error"]["code"] == "upload_busy"
                assert rejected.headers["Retry-After"] == "2"
                assert probe.entered == 1
            finally:
                first.shutdown(socket.SHUT_WR)
                assert response(first)[0] == 400
        assert client.get(f"/api/v1/scopes/{admin.id}/usage").json()["stored_upload_bytes"] == 0
        assert client.post(path, content=FASTA).status_code == 201


@pytest.mark.parametrize("rejection", ["read_only", "csrf", "session"])
def test_upload_auth_and_edit_permission_precede_waiting_and_body_reads(tmp_path, rejection):
    policy = TransportPolicy(
        max_connections=5, max_uploads=1, max_pending_uploads=0, body_timeout=2
    )
    with site(tmp_path, policy) as (server, client, admin, probe):
        own_path = upload_path(admin.id)
        path, headers, expected = own_path, {}, 403
        if rejection == "read_only":
            other = server.accounts.register("other", PASSWORD, "Other synthetic user")
            path = upload_path(other.id)  # Admin observation is explicitly read-only.
        elif rejection == "csrf":
            headers = {"X-CSRF-Token": "invalid"}
        else:
            headers, expected = {"Cookie": ""}, 401
        with partial_upload(client, own_path) as first:
            probe.wait("entered", 1)
            try:
                with partial_upload(client, path, headers=headers) as denied:
                    denied.settimeout(0.5)
                    assert response(denied)[0] == expected
                    assert probe.attempted == 1
            finally:
                first.shutdown(socket.SHUT_WR)
                assert response(first)[0] == 400
        assert server.runtime.resources.usage(admin, admin.id)["stored_upload_bytes"] == 0


@pytest.mark.parametrize("phase", ["reading", "waiting"])
def test_logged_out_upload_is_rejected_before_persistence_and_before_reading_a_queued_body(
    tmp_path, phase
):
    policy = TransportPolicy(max_connections=5, max_uploads=1, body_timeout=2)
    with site(tmp_path, policy) as (server, client, admin, probe):
        path = upload_path(admin.id)
        with partial_upload(client, path) as first:
            probe.wait("entered", 1)
            if phase == "waiting":
                with partial_upload(client, path) as second:
                    probe.wait("attempted", 2)
                    assert probe.entered == 1
                    assert client.post("/api/v1/accounts/logout", json={}).status_code == 200
                    first.sendall(FASTA[1:])
                    assert response(first)[0] == 401
                    second.settimeout(0.5)
                    assert response(second)[0] == 401  # No remaining body bytes were sent.
            else:
                assert client.post("/api/v1/accounts/logout", json={}).status_code == 200
                first.sendall(FASTA[1:])
                assert response(first)[0] == 401
        assert server.runtime.resources.usage(admin, admin.id)["stored_upload_bytes"] == 0
        assert probe.active == 0


def test_slow_responses_release_processing_slots_but_keep_upload_connection_admission(
    tmp_path, monkeypatch
):
    policy = TransportPolicy(
        max_connections=5, max_uploads=1, max_pending_uploads=1, body_timeout=4
    )
    with site(tmp_path, policy) as (_server, client, admin, probe):
        path = upload_path(admin.id)
        blocked = [threading.Event(), threading.Event()]
        release, lock = threading.Event(), threading.Lock()
        writers = []
        original_write = socketserver._SocketWriter.write

        def slow_write(writer, data):
            if bytes(data).startswith(b"HTTP/1.0 201"):
                with lock:
                    index = len(writers)
                    writers.append(threading.get_ident())
                if index < 2:
                    blocked[index].set()
                    assert release.wait(8)
            return original_write(writer, data)

        # Only wrap the network output boundary; service/quota operations remain real.
        monkeypatch.setattr(socketserver._SocketWriter, "write", slow_write)
        replies = []
        first = threading.Thread(target=lambda: replies.append(client.post(path, content=FASTA)))
        second = threading.Thread(target=lambda: replies.append(client.post(path, content=FASTA)))
        first.start()
        try:
            assert blocked[0].wait(3)
            second.start()
            probe.wait("attempted", 2)
            assert blocked[1].wait(1.5), "Slow response must not hold the body processing slot"
            rejected = client.post(path, content=FASTA)
            assert rejected.status_code == 503  # Both admitted uploads are still sending.
            assert rejected.json()["error"]["code"] == "upload_busy"
            assert client.get("/api/v1/accounts/config").status_code == 200
        finally:
            release.set()
            first.join(timeout=5)
            if second.ident is not None:
                second.join(timeout=5)
        assert not first.is_alive() and not second.is_alive()
        assert [reply.status_code for reply in replies] == [201, 201]
        assert probe.peak == 1
        assert client.post(path, content=FASTA).status_code == 201
        assert client.get(f"/api/v1/scopes/{admin.id}/usage").json()["stored_upload_bytes"] == len(
            FASTA
        )


@pytest.mark.parametrize("revocation", ["password_reset", "team_removal", "suspend"])
def test_queued_upload_rechecks_live_identity_and_scope_before_reading_body(tmp_path, revocation):
    policy = TransportPolicy(max_connections=6, max_uploads=1, body_timeout=3)
    with site(tmp_path, policy) as (server, client, admin, probe):
        bob = server.accounts.register("bob", PASSWORD, "Synthetic Bob")
        server.accounts.update_user(admin, bob.id, status="active")
        scope = bob.id
        if revocation == "team_removal":
            team = server.accounts.create_team(admin, "Synthetic team")
            invitation = server.accounts.invite(admin, team["id"], "bob", role="member")
            server.accounts.respond_invitation(bob, invitation["id"], accept=True)
            scope = team["id"]
        with httpx.Client(
            base_url=client.base_url,
            headers={"Origin": str(client.base_url).rstrip("/")},
            trust_env=False,
        ) as bob_client:
            login = bob_client.post(
                "/api/v1/accounts/login", json={"username": "bob", "password": PASSWORD}
            )
            bob_client.headers["X-CSRF-Token"] = login.json()["csrf_token"]
            with partial_upload(client, upload_path(admin.id)) as first:
                probe.wait("entered", 1)
                with partial_upload(bob_client, upload_path(scope)) as queued:
                    probe.wait("attempted", 2)
                    assert probe.entered == 1  # Revoke only after the waiter reached the gate.
                    if revocation == "password_reset":
                        server.accounts.reset_password(admin, bob.id, "New-fixture-password-2026!")
                    elif revocation == "team_removal":
                        server.accounts.set_member(admin, scope, bob.id, remove=True)
                    else:
                        server.accounts.update_user(admin, bob.id, status="suspended")
                    first.shutdown(socket.SHUT_WR)
                    assert response(first)[0] == 400
                    queued.settimeout(0.5)
                    status, headers, _body = response(queued)
                    assert status in {401, 403, 404}  # Never reads the unsent body remainder.
                    assert headers["Connection"] == "close"
            assert server.runtime.resources.usage(admin, scope)["stored_upload_bytes"] == 0
        assert probe.active == 0
        assert client.post(upload_path(admin.id), content=FASTA).status_code == 201


def test_default_four_processing_slots_remain_bounded_with_a_waiter(tmp_path):
    with site(tmp_path, TransportPolicy(max_connections=8, body_timeout=3)) as (
        _server,
        client,
        admin,
        probe,
    ):
        path = upload_path(admin.id)
        with ExitStack() as stack:
            connections = []
            for index in range(4):
                connections.append(stack.enter_context(partial_upload(client, path)))
                probe.wait("entered", index + 1)
            queued = stack.enter_context(partial_upload(client, path))
            probe.wait("attempted", 5)
            try:
                assert probe.entered == probe.peak == 4
                assert client.get("/api/v1/accounts/config").status_code == 200
            finally:
                queued.shutdown(socket.SHUT_WR)
                for connection in connections:
                    connection.shutdown(socket.SHUT_WR)
                for connection in [*connections, queued]:
                    assert response(connection)[0] == 400
        assert probe.active == 0
        assert client.get(f"/api/v1/scopes/{admin.id}/usage").json()["stored_upload_bytes"] == 0
        assert client.post(path, content=FASTA).status_code == 201


def test_failed_parse_retains_existing_quota_semantics_without_leaking_upload_slots(tmp_path):
    with site(tmp_path, TransportPolicy(max_connections=2, max_uploads=1)) as (
        server,
        client,
        admin,
        probe,
    ):
        path = upload_path(admin.id)
        invalid = b">fixture\nINVALID123\n"
        rejected = client.post(path, content=invalid)
        assert rejected.status_code == 400
        assert rejected.json()["error"]["code"] == "invalid_sequence"
        server.upload_admissions.wait("released", 1)
        assert probe.active == 0
        assert client.post(path, content=FASTA).status_code == 201
        assert probe.entered == probe.released == 2
        # Failed scientific input is retained/quarantined, not silently deleted or uncharged.
        assert client.get(f"/api/v1/scopes/{admin.id}/usage").json()["stored_upload_bytes"] == len(
            invalid
        ) + len(FASTA)


def test_disk_write_failure_releases_both_gates_and_same_input_can_be_retried(
    tmp_path, monkeypatch
):
    with site(tmp_path, TransportPolicy(max_connections=2, max_uploads=1)) as (
        server,
        client,
        admin,
        probe,
    ):
        original_link = os.link
        failed = threading.Event()

        def fail_first_publish(source, destination, *args, **kwargs):
            if Path(destination).name == "sequence.fasta" and not failed.is_set():
                failed.set()
                raise OSError("Synthetic disk publication failure")
            return original_link(source, destination, *args, **kwargs)

        # Fault the external disk boundary; HTTP, service and quota logic remain real.
        monkeypatch.setattr(os, "link", fail_first_publish)
        path = upload_path(admin.id)
        rejected = client.post(path, content=FASTA)
        assert rejected.status_code == 500
        assert rejected.json()["error"]["code"] == "operational_error"
        assert failed.is_set()
        server.upload_admissions.wait("released", 1)
        assert probe.active == server.upload_admissions.active == 0
        assert client.post(path, content=FASTA).status_code == 201
        server.upload_admissions.wait("released", 2)
        assert probe.entered == probe.released == 2
        assert server.upload_admissions.active == 0
        assert client.get(f"/api/v1/scopes/{admin.id}/usage").json()["stored_upload_bytes"] == len(
            FASTA
        )


@pytest.mark.parametrize("failure,status", [("format", 400), ("disk", 500)])
def test_slow_error_response_keeps_retained_body_inside_processing_limit(
    tmp_path, monkeypatch, failure, status
):
    policy = TransportPolicy(
        max_connections=5, max_uploads=1, max_pending_uploads=1, body_timeout=4
    )
    with site(tmp_path, policy) as (server, client, admin, probe):
        blocked, release, completed = threading.Event(), threading.Event(), threading.Event()
        original_write, original_link = socketserver._SocketWriter.write, os.link
        write_failed = threading.Event()

        def slow_error_write(writer, data):
            if bytes(data).startswith(f"HTTP/1.0 {status}".encode()):
                blocked.set()
                assert release.wait(8)
            return original_write(writer, data)

        def fail_first_publish(source, destination, *args, **kwargs):
            if Path(destination).name == "sequence.fasta" and not write_failed.is_set():
                write_failed.set()
                raise OSError("Synthetic disk publication failure")
            return original_link(source, destination, *args, **kwargs)

        monkeypatch.setattr(socketserver._SocketWriter, "write", slow_error_write)
        if failure == "disk":
            monkeypatch.setattr(os, "link", fail_first_publish)
        payload = b">fixture\n" + b"X" * (64 * 1024) if failure == "format" else FASTA
        path, replies = upload_path(admin.id), []
        first = threading.Thread(target=lambda: replies.append(client.post(path, content=payload)))

        def second_upload():
            replies.append(client.post(path, content=FASTA))
            completed.set()

        second = threading.Thread(target=second_upload)
        first.start()
        try:
            assert blocked.wait(3)
            assert probe.active == 1, "Error tracebacks retain body bytes until response completion"
            second.start()
            probe.wait("attempted", 2)
            assert probe.entered == 1
            assert not completed.wait(0.2)
            assert client.get("/api/v1/accounts/config").status_code == 200
        finally:
            release.set()
            first.join(timeout=5)
            if second.ident is not None:
                second.join(timeout=5)
        assert not first.is_alive() and not second.is_alive()
        assert sorted(reply.status_code for reply in replies) == [201, status]
        server.upload_admissions.wait("released", 2)
        assert probe.entered == probe.released == 2
        assert probe.active == server.upload_admissions.active == 0
        assert probe.peak == 1
