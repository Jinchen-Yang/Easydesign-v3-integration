from __future__ import annotations

import json
import socket
import threading
import time
from contextlib import contextmanager
from http.client import HTTPResponse
from pathlib import Path

import httpx
import pytest

from easydesign.product.account_server import MultiUserServer
from easydesign.product.accounts import AccountStore
from easydesign.product.domain import NativeGateway
from easydesign.product.rabbit_capacity import RabbitCapacityLimits
from easydesign.product.rabbit_chat import RabbitChatService
from easydesign.product.resource_control import ResourceLedger
from easydesign.product.tenancy import MultiUserRuntime
from easydesign.product.transport_policy import TransportPolicy
from easydesign.workspace_context import WorkspaceContext

PASSWORD = "Http-capacity-test-password!"


@contextmanager
def site(tmp_path: Path, *, policy: TransportPolicy | None = None, **options):
    (tmp_path / "easydesign-workspace.yaml").write_text('schema_version: "0.1"\n')
    context = WorkspaceContext.from_root(tmp_path)
    context.ensure_layout()
    accounts = AccountStore(context.runtime_root / "state/accounts/accounts.sqlite")
    admin = accounts.bootstrap_admin("admin", PASSWORD, "Test administrator")
    runtime = MultiUserRuntime(
        context, accounts, lambda c: NativeGateway(c, tmp_path / "models.yaml")
    )
    server = MultiUserServer(runtime, port=0, transport_policy=policy, **options)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    origin = f"http://127.0.0.1:{server.server_port}"
    try:
        with httpx.Client(base_url=origin, headers={"Origin": origin}, trust_env=False) as client:
            yield server, client, admin, context
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@pytest.mark.parametrize("trusted", [False, True])
def test_login_uses_only_explicitly_trusted_proxy_identity(tmp_path, trusted):
    policy = TransportPolicy(trusted_proxies=("127.0.0.1/32",) if trusted else ())
    with site(tmp_path, policy=policy) as (_server, client, _admin, _context):
        for _ in range(5):
            failed = client.post(
                "/api/v1/accounts/login",
                headers={"X-Real-IP": "198.51.100.1"},
                json={"username": "admin", "password": "wrong"},
            )
            assert failed.status_code == 401
        result = client.post(
            "/api/v1/accounts/login",
            headers={"X-Real-IP": "198.51.100.2"},
            json={"username": "admin", "password": PASSWORD},
        )
        assert result.status_code == (200 if trusted else 429)


def test_slow_headers_have_bounded_admission_and_an_absolute_deadline(tmp_path):
    policy = TransportPolicy(max_connections=2, max_uploads=1, header_timeout=0.6)
    with site(tmp_path, policy=policy) as (server, client, _admin, _context):
        address = ("127.0.0.1", server.server_port)
        with (
            socket.create_connection(address, timeout=2) as first,
            socket.create_connection(address, timeout=2) as second,
        ):
            first.sendall(b"GET /api/v1/accounts/config HTTP/1.1\r\nX-Slow: ")
            second.sendall(b"G")
            time.sleep(0.05)
            overloaded = client.get("/api/v1/accounts/config")
            assert overloaded.status_code == 503
            assert overloaded.json()["error"]["code"] == "http_busy"
            assert overloaded.headers["Connection"] == "close"
            # Bytes arrive below the inactivity timeout, but cannot extend the
            # absolute header deadline indefinitely.
            for _ in range(8):
                time.sleep(0.1)
                try:
                    first.sendall(b"x")
                except OSError:
                    break
            assert first.recv(1024) == b""
        assert client.get("/api/v1/accounts/config").status_code == 200


def test_slow_upload_is_bounded_without_blocking_reads_or_leaking_quota(tmp_path):
    policy = TransportPolicy(max_connections=4, max_uploads=1, body_timeout=3)
    with site(tmp_path, policy=policy) as (server, client, admin, _context):
        login = client.post(
            "/api/v1/accounts/login", json={"username": "admin", "password": PASSWORD}
        )
        csrf = login.json()["csrf_token"]
        client.headers["X-CSRF-Token"] = csrf
        path = f"/api/v1/scopes/{admin.id}/inputs?filename=test.fasta"
        request = client.build_request("POST", path, content=b">test\nACDEFGHIK\n")
        cookie = request.headers["Cookie"]
        origin = str(client.base_url).rstrip("/")
        with socket.create_connection(("127.0.0.1", server.server_port), timeout=5) as conn:
            conn.sendall(
                (
                    f"POST {path} HTTP/1.1\r\nHost: 127.0.0.1:{server.server_port}\r\n"
                    f"Origin: {origin}\r\nCookie: {cookie}\r\nX-CSRF-Token: {csrf}\r\n"
                    "Content-Length: 100\r\n\r\nx"
                ).encode()
            )
            time.sleep(0.1)
            rejected = client.post(path, content=b">test\nACDEFGHIK\n")
            assert rejected.status_code == 503
            assert rejected.json()["error"]["code"] == "upload_busy"
            assert rejected.headers["Connection"] == "close"
            assert client.get("/api/v1/accounts/config").status_code == 200
            conn.shutdown(socket.SHUT_WR)
            response = HTTPResponse(conn)
            response.begin()
            assert response.status == 400
            response.read()
        usage = f"/api/v1/scopes/{admin.id}/usage"
        assert client.get(usage).json()["stored_upload_bytes"] == 0
        complete = client.post(path, content=b">test\nACDEFGHIK\n")
        assert complete.status_code == 201
        assert client.get(usage).json()["stored_upload_bytes"] == len(b">test\nACDEFGHIK\n")


def test_explicit_old_build_serves_only_hashed_assets_and_detects_conflicts(tmp_path):
    current, previous = tmp_path / "current", tmp_path / "previous"
    for root in (current, previous):
        (root / "assets").mkdir(parents=True)
    (current / "index.html").write_text("current html")
    (previous / "index.html").write_text("old html")
    (previous / "assets/retained-BAsZliUl.js").write_text("export const retained = true;")
    (previous / "assets/unversioned.js").write_text("must not be served")
    with site(tmp_path, web_root=current, web_history=(previous,)) as (
        _server,
        client,
        _admin,
        _context,
    ):
        assert client.get("/").text == "current html"
        retained = client.get("/assets/retained-BAsZliUl.js")
        assert retained.status_code == 200
        assert retained.headers["Cache-Control"].endswith("immutable")
        assert "retained" in retained.text
        assert client.get("/assets/unversioned.js").status_code != 200
    (current / "assets/retained-BAsZliUl.js").write_text("conflicting same hash name")
    with pytest.raises((ValueError, RuntimeError), match="conflict"):
        MultiUserServer(_server.runtime, port=0, web_root=current, web_history=(previous,))


def test_static_gzip_varies_by_acceptance_without_compressing_private_responses(tmp_path):
    web = tmp_path / "current"
    (web / "assets").mkdir(parents=True)
    data = "export const example = 'read-only static fixture';\n" * 200
    (web / "assets/app-BAsZliUl.js").write_text(data)
    with site(tmp_path, web_root=web) as (_server, client, _admin, _context):
        compressed = client.get("/assets/app-BAsZliUl.js", headers={"Accept-Encoding": "gzip"})
        assert compressed.headers["Content-Encoding"] == "gzip"
        assert compressed.headers["Vary"] == "Accept-Encoding"
        assert compressed.text == data
        assert int(compressed.headers["Content-Length"]) < len(data)
        identity = client.get(
            "/assets/app-BAsZliUl.js", headers={"Accept-Encoding": "gzip;q=0, *;q=1"}
        )
        assert "Content-Encoding" not in identity.headers
        assert identity.headers["Vary"] == "Accept-Encoding"
        assert identity.text == data
        private = client.get("/api/v1/accounts/config", headers={"Accept-Encoding": "gzip"})
        assert "Content-Encoding" not in private.headers
        assert private.headers["Cache-Control"] == "no-store"


def test_chat_http_binds_stable_identity_to_authenticated_user_and_scope(tmp_path):
    calls = []

    def provider(payload):
        calls.append(payload)
        yield {"type": "delta", "text": "fixture"}
        yield {"type": "done"}

    rabbit = RabbitChatService(provider, ledger_path=tmp_path / "chat.sqlite")
    try:
        with site(tmp_path, rabbit_chat=rabbit) as (server, client, admin, _context):
            login = client.post(
                "/api/v1/accounts/login", json={"username": "admin", "password": PASSWORD}
            )
            client.headers["X-CSRF-Token"] = login.json()["csrf_token"]
            base = f"/api/v1/scopes/{admin.id}/rabbit"
            payload = {
                "locale": "zh",
                "messages": [{"role": "user", "content": "fixture"}],
                "context": {"stage": "Idle", "status": "idle", "goal": "fixture"},
                "actor_id": "forged",
                "scope_id": "forged",
            }
            assert client.post(base + "/chat", json=payload).status_code == 400
            identity = "chat-http-fixture-0001"
            response = client.post(base + "/chat", json=payload, headers={"X-Request-ID": identity})
            assert response.status_code == 200
            assert json.loads(response.text.splitlines()[-1])["type"] == "done"
            status = client.get(f"{base}/requests/{identity}")
            assert status.status_code == 200
            assert status.json()["dispatched"] is True
            assert (
                client.post(
                    base + "/chat", json=payload, headers={"X-Request-ID": identity}
                ).status_code
                == 409
            )
            assert len(calls) == 1
            assert "actor_id" not in calls[0]
            admission = server.runtime.resources.latest(admin.id, identity)
            assert admission.dispatch_channel == "web_stream"
            assert admission.state == "released"
            bob = server.accounts.register("bob", PASSWORD, "Bob")
            server.accounts.update_user(admin, bob.id, status="active")
            login = client.post(
                "/api/v1/accounts/login", json={"username": "bob", "password": PASSWORD}
            )
            client.headers["X-CSRF-Token"] = login.json()["csrf_token"]
            assert (
                client.get(f"/api/v1/scopes/{bob.id}/rabbit/requests/{identity}").status_code == 404
            )
            assert (
                client.post(
                    f"/api/v1/scopes/{bob.id}/rabbit/requests/{identity}/cancel", json={}
                ).status_code
                == 404
            )
    finally:
        rabbit.close()


def test_upload_timeout_releases_admission_without_charging_storage(tmp_path):
    policy = TransportPolicy(max_connections=4, max_uploads=1, body_timeout=0.2)
    with site(tmp_path, policy=policy) as (server, client, admin, _context):
        login = client.post(
            "/api/v1/accounts/login", json={"username": "admin", "password": PASSWORD}
        )
        csrf = login.json()["csrf_token"]
        client.headers["X-CSRF-Token"] = csrf
        path = f"/api/v1/scopes/{admin.id}/inputs?filename=deadline.fasta"
        cookie = client.build_request("POST", path).headers["Cookie"]
        origin = str(client.base_url).rstrip("/")
        with socket.create_connection(("127.0.0.1", server.server_port), timeout=2) as conn:
            conn.sendall(
                (
                    f"POST {path} HTTP/1.1\r\nHost: 127.0.0.1:{server.server_port}\r\n"
                    f"Origin: {origin}\r\nCookie: {cookie}\r\nX-CSRF-Token: {csrf}\r\n"
                    "Content-Length: 100\r\n\r\nx"
                ).encode()
            )
            response = HTTPResponse(conn)
            response.begin()
            assert response.status == 408
            assert response.headers["Connection"] == "close"
            assert json.loads(response.read())["error"]["code"] == "body_timeout"
        assert client.get(f"/api/v1/scopes/{admin.id}/usage").json()["stored_upload_bytes"] == 0
        assert client.post(path, content=b">fixture\nACDEFGHIK\n").status_code == 201


def test_full_computational_queue_does_not_reject_web_chat_and_queued_chat_can_cancel(tmp_path):
    started, release = threading.Event(), threading.Event()
    calls = []

    def provider(payload):
        calls.append(payload)
        started.set()
        assert release.wait(timeout=8)
        yield {"type": "delta", "text": "synthetic"}
        yield {"type": "done"}

    rabbit = RabbitChatService(
        provider,
        limits=RabbitCapacityLimits(max_active=1),
        ledger_path=tmp_path / "chat.sqlite",
    )
    with site(tmp_path, rabbit_chat=rabbit) as (server, client, admin, _context):
        login = client.post(
            "/api/v1/accounts/login", json={"username": "admin", "password": PASSWORD}
        )
        client.headers["X-CSRF-Token"] = login.json()["csrf_token"]
        # A small bound deterministically exercises the same channel isolation
        # as a full 300-place compute queue; this is not a 300-client load test.
        server.runtime.resources = ResourceLedger(server.accounts, max_active_admissions=1)
        server.runtime.resources.reserve(
            admin,
            admin.id,
            "scientific-queue-full-001",
            {"fixture": True},
            dispatch_channel="scoped_worker",
        )
        base = f"/api/v1/scopes/{admin.id}/rabbit"
        payload = {
            "locale": "zh",
            "messages": [{"role": "user", "content": "fixture"}],
            "context": {"stage": "Idle", "status": "idle", "goal": "fixture"},
        }
        responses = {}

        def post(identity):
            with httpx.Client(
                base_url=client.base_url,
                headers=client.headers,
                cookies=client.cookies,
                trust_env=False,
                timeout=10,
            ) as writer:
                responses[identity] = writer.post(
                    base + "/chat", json=payload, headers={"X-Request-ID": identity}
                )

        first_id, queued_id = "http-ai-running-001", "http-ai-queued-0001"
        first = threading.Thread(target=post, args=(first_id,))
        second = threading.Thread(target=post, args=(queued_id,))
        first.start()
        try:
            assert started.wait(timeout=3)
            second.start()
            deadline = time.monotonic() + 3
            while time.monotonic() < deadline:
                status = client.get(f"{base}/requests/{queued_id}")
                if status.status_code == 200:
                    break
                time.sleep(0.01)
            assert status.json()["state"] == "queued"
            cancelled = client.post(f"{base}/requests/{queued_id}/cancel", json={})
            assert cancelled.status_code == 200
            assert cancelled.json()["dispatched"] is False
            second.join(timeout=3)
            assert not second.is_alive()
            assert '"cancelled"' in responses[queued_id].text
            assert len(calls) == 1
            assert server.runtime.resources.latest(admin.id, queued_id).state == "failed"
            assert client.get("/api/v1/accounts/config").status_code == 200
        finally:
            release.set()
            first.join(timeout=5)
            if second.ident is not None:
                second.join(timeout=5)
        assert responses[first_id].status_code == 200
        assert len(calls) == 1


@pytest.mark.parametrize("revocation", ["logout", "suspend", "password_reset", "team_removal"])
def test_queued_chat_rechecks_live_session_and_scope_before_provider_dispatch(tmp_path, revocation):
    started, release = threading.Event(), threading.Event()
    calls = []

    def provider(payload):
        calls.append(payload)
        started.set()
        assert release.wait(timeout=10)
        yield {"type": "done"}

    rabbit = RabbitChatService(
        provider, limits=RabbitCapacityLimits(max_active=1), ledger_path=tmp_path / "chat.sqlite"
    )
    with site(tmp_path, rabbit_chat=rabbit) as (server, client, admin, _context):
        login = client.post(
            "/api/v1/accounts/login", json={"username": "admin", "password": PASSWORD}
        )
        client.headers["X-CSRF-Token"] = login.json()["csrf_token"]
        bob = server.accounts.register("bob", PASSWORD, "Bob")
        server.accounts.update_user(admin, bob.id, status="active")
        scope = bob.id
        if revocation == "team_removal":
            team = server.accounts.create_team(admin, "Synthetic team")
            invite = server.accounts.invite(admin, team["id"], "bob", role="member")
            server.accounts.respond_invitation(bob, invite["id"], accept=True)
            scope = team["id"]
        payload = {
            "locale": "zh",
            "messages": [{"role": "user", "content": "fixture"}],
            "context": {"stage": "Idle", "status": "idle", "goal": "fixture"},
        }
        replies = {}
        first_id, queued_id = "guard-running-request", "guard-queued-request"

        def post(client_to_copy, target_scope, identity):
            with httpx.Client(
                base_url=client.base_url,
                headers=client_to_copy.headers,
                cookies=client_to_copy.cookies,
                trust_env=False,
                timeout=12,
            ) as writer:
                replies[identity] = writer.post(
                    f"/api/v1/scopes/{target_scope}/rabbit/chat",
                    json=payload,
                    headers={"X-Request-ID": identity},
                )

        with httpx.Client(
            base_url=client.base_url,
            headers={"Origin": str(client.base_url).rstrip("/")},
            trust_env=False,
        ) as bob_client:
            login = bob_client.post(
                "/api/v1/accounts/login", json={"username": "bob", "password": PASSWORD}
            )
            bob_client.headers["X-CSRF-Token"] = login.json()["csrf_token"]
            first = threading.Thread(target=post, args=(client, admin.id, first_id))
            second = threading.Thread(target=post, args=(bob_client, scope, queued_id))
            first.start()
            try:
                assert started.wait(timeout=3)
                second.start()
                deadline = time.monotonic() + 3
                while time.monotonic() < deadline:
                    status = bob_client.get(f"/api/v1/scopes/{scope}/rabbit/requests/{queued_id}")
                    if status.status_code == 200:
                        break
                    time.sleep(0.01)
                assert status.json()["state"] == "queued"
                if revocation == "logout":
                    assert bob_client.post("/api/v1/accounts/logout", json={}).status_code == 200
                elif revocation == "suspend":
                    server.accounts.update_user(admin, bob.id, status="suspended")
                elif revocation == "password_reset":
                    server.accounts.reset_password(admin, bob.id, "New-fixture-password-2026!")
                else:
                    server.accounts.set_member(admin, scope, bob.id, remove=True)
            finally:
                release.set()
                first.join(timeout=5)
                if second.ident is not None:
                    second.join(timeout=5)
            assert not second.is_alive()
            assert len(calls) == 1
            assert '"authorization_revoked"' in replies[queued_id].text
            status = rabbit.request_status(actor_id=bob.id, scope_id=scope, request_id=queued_id)
            assert status["dispatched"] is False
            assert rabbit.capacity_status()["dispatched_requests"] == 1
