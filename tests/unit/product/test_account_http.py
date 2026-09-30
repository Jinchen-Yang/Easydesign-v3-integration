from __future__ import annotations

import json
import threading
from contextlib import contextmanager
from pathlib import Path

import httpx
import pytest

from easydesign.core import ArtifactRef
from easydesign.product.account_server import MultiUserServer
from easydesign.product.accounts import AccountStore
from easydesign.product.domain import NativeGateway
from easydesign.product.tenancy import MultiUserRuntime
from easydesign.workspace_context import WorkspaceContext

PASSWORD = "Fixture-password-2026!"


@pytest.fixture
def product(tmp_path: Path):
    (tmp_path / "easydesign-workspace.yaml").write_text('schema_version: "0.1"\n')
    context = WorkspaceContext.from_root(tmp_path)
    context.ensure_layout()
    accounts = AccountStore(context.runtime_root / "state/accounts/accounts.sqlite")
    admin = accounts.bootstrap_admin("admin", PASSWORD, "管理员")
    users = [accounts.register(name, PASSWORD, name) for name in ("alice", "bob")]
    for user in users:
        accounts.update_user(admin, user.id, status="active")
    runtime = MultiUserRuntime(
        context, accounts, lambda c: NativeGateway(c, tmp_path / "models.yaml")
    )
    server = MultiUserServer(runtime, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server, accounts, admin, users, context
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@contextmanager
def client(server, username: str | None = None):
    origin = f"http://127.0.0.1:{server.server_port}"
    with httpx.Client(
        base_url=origin, headers={"Origin": origin}, timeout=10, trust_env=False
    ) as value:
        if username:
            result = value.post(
                "/api/v1/accounts/login", json={"username": username, "password": PASSWORD}
            )
            assert result.status_code == 200
            value.headers["X-CSRF-Token"] = result.json()["csrf_token"]
        yield value


def test_account_api_requires_individual_sessions_and_disables_workspace_token(product):
    server, _accounts, _admin, _users, _context = product
    with client(server) as anonymous:
        assert anonymous.get("/api/v1/accounts/config").json()["mode"] == "multi-user"
        assert anonymous.get("/api/v1/accounts/config").json()["registration"] == "open"
        assert anonymous.get("/api/v1/health").status_code == 401
        assert (
            anonymous.get(
                "/api/v1/health", headers={"Authorization": "Bearer " + server.token}
            ).status_code
            == 401
        )
        assert anonymous.post("/api/v1/session", json={"token": server.token}).status_code == 401
        created = anonymous.post(
            "/api/v1/accounts/register",
            json={
                "username": "carol",
                "password": PASSWORD,
                "display_name": "Carol",
            },
        )
        assert created.status_code == 201
        assert created.json()["status"] == "registered"
        assert created.json()["user"]["status"] == "active"
        assert (
            anonymous.post(
                "/api/v1/accounts/login", json={"username": "carol", "password": PASSWORD}
            ).status_code
            == 200
        )
        assert anonymous.get("/api/v1/accounts/me").json()["user"]["username"] == "carol"


def test_successful_account_login_and_private_scope_are_not_cacheable(product):
    server, _accounts, _admin, users, _context = product
    with client(server) as browser:
        response = browser.post(
            "/api/v1/accounts/login", json={"username": "alice", "password": PASSWORD}
        )
        assert response.status_code == 200
        assert "Set-Cookie" in response.headers
        assert response.headers["Cache-Control"] == "no-store"
        for path in ("/api/v1/accounts/me", f"/api/v1/scopes/{users[0].id}/usage"):
            private = browser.get(path)
            assert private.status_code == 200
            assert private.headers["Cache-Control"] == "no-store"


def test_member_can_leave_team_without_a_post_mutation_read_failure(product):
    server, accounts, _admin, users, _context = product
    alice, bob = users
    team = accounts.create_team(alice, "Self-leave fixture")
    invitation = accounts.invite(alice, team["id"], "bob")
    accounts.respond_invitation(bob, invitation["id"], accept=True)
    with client(server, "bob") as member:
        response = member.post(
            f"/api/v1/teams/{team['id']}/members/{bob.id}", json={"remove": True}
        )
        assert response.status_code == 200
        assert response.json() == {"status": "left-team"}
        assert all(
            scope["id"] != team["id"]
            for scope in member.get("/api/v1/accounts/me").json()["scopes"]
        )
        assert member.get(f"/api/v1/teams/{team['id']}").status_code == 404
        assert member.get(f"/api/v1/scopes/{team['id']}/usage").status_code == 404
    with client(server, "alice") as owner:
        assert owner.get(f"/api/v1/teams/{team['id']}").status_code == 200


def test_admin_approval_does_not_grant_other_users_administration(product):
    server, accounts, _admin, users, _context = product
    with client(server, "alice") as alice:
        assert alice.get("/api/v1/admin/users").status_code == 403
        assert (
            alice.post(f"/api/v1/admin/users/{users[1].id}", json={"role": "admin"}).status_code
            == 403
        )
    with client(server, "admin") as admin:
        response = admin.get("/api/v1/admin/users")
        assert response.status_code == 200
        assert all("password_hash" not in item for item in response.json()["users"])
        assert (
            admin.post(
                f"/api/v1/admin/users/{users[0].id}", json={"status": "suspended"}
            ).status_code
            == 200
        )
    assert accounts.user(users[0].id).status == "suspended"


def test_csrf_origin_and_disabled_sessions_are_enforced_by_the_http_server(product):
    server, accounts, admin, users, _context = product
    with client(server, "alice") as alice:
        response = alice.get("/api/v1/accounts/me")
        assert response.status_code == 200
        alice.headers.pop("X-CSRF-Token")
        assert alice.post("/api/v1/teams", json={"name": "Forged"}).status_code == 403
        alice.headers["X-CSRF-Token"] = response.json()["csrf_token"]
        assert (
            alice.post(
                "/api/v1/teams",
                json={"name": "Cross site"},
                headers={"Origin": "https://invalid.example"},
            ).status_code
            == 403
        )
        accounts.update_user(admin, users[0].id, status="suspended")
        assert alice.get("/api/v1/accounts/me").status_code == 401


def test_artifact_access_is_scope_bound_and_admin_reads_are_audited(product):
    server, accounts, _admin, users, context = product
    alice, bob = users
    with server.runtime.bind(alice, alice.id) as service:
        path = service.context.runs_root / "fixture/report.json"
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps({"private": "alice-only"}))
        ref = ArtifactRef.from_file(
            run_root=path.parent,
            relative_path=path.name,
            artifact_id="fixture",
            role="test",
            file_format="json",
        )
        artifact = service.catalog.register(
            project="private-project",
            evidence="fixture",
            root=path.parent,
            ref=ref,
            label="Private report",
        )
    url = f"/api/v1/scopes/{alice.id}/artifacts/{artifact.id}"
    with client(server, "alice") as owner, client(server, "bob") as other:
        private = owner.get(url)
        assert private.status_code == 200
        assert private.json() == {"private": "alice-only"}
        assert private.headers["Cache-Control"] == "no-store"
        assert other.get(url).status_code == 404
        assert other.get(f"/api/v1/scopes/{bob.id}/artifacts/{artifact.id}").status_code == 404
        assert other.get(artifact.url).status_code == 404
    with client(server, "admin") as administrator:
        private = administrator.get(url)
        assert private.status_code == 200
        assert private.json() == {"private": "alice-only"}
        assert private.headers["Cache-Control"] == "no-store"
        assert (
            administrator.post(
                f"/api/v1/scopes/{alice.id}/projects/private-project/title",
                json={"title": "Forbidden"},
            ).status_code
            == 403
        )
        events = administrator.get("/api/v1/admin/audit").json()["events"]
        assert any(e["action"] == "admin.scope.read" and e["scope_id"] == alice.id for e in events)
    assert not (context.runtime_root / "state/product/access-token").exists()


def test_team_scope_shared_reads_and_member_write_authority_are_distinct(product):
    server, accounts, _admin, users, _context = product
    alice, bob = users
    team = accounts.create_team(alice, "Team")
    invitation = accounts.invite(alice, team["id"], "bob")
    accounts.respond_invitation(bob, invitation["id"], accept=True)
    base = f"/api/v1/scopes/{team['id']}"
    with client(server, "bob") as member:
        assert member.get(base + "/projects?surface=easy").status_code == 200
        create = member.post(
            base + "/projects",
            json={
                "request_id": "create-request-000001",
                "title": "Unauthorized compute",
                "goal": "Fixture goal",
            },
        )
        assert create.status_code == 403
        assert create.json()["error"]["code"] == "team_admin_required"
        assert member.post(base + "/session", json={"token": server.token}).status_code == 404
        assert member.get(base + "/projects").json()["total"] == 0
        accounts.set_member(alice, team["id"], bob.id, remove=True)
        assert member.get(base + "/projects").status_code == 404


def test_scoped_response_urls_cannot_fall_back_to_the_unscoped_api(product):
    from easydesign.product.account_server import _scoped_urls

    scope = "user-" + "a" * 32
    response = {"artifacts": [{"url": "/api/v1/artifacts/abc", "sha256": "b" * 64}]}
    rendered = _scoped_urls(response, scope)
    assert rendered["artifacts"][0]["url"] == f"/api/v1/scopes/{scope}/artifacts/abc"
    assert response["artifacts"][0]["url"] == "/api/v1/artifacts/abc"
    assert rendered["artifacts"][0]["sha256"] == "b" * 64


def test_migrated_easy_delete_requires_csrf_scope_and_retains_evidence(product):
    server, accounts, _admin, users, _context = product
    alice, bob = users
    with server.runtime.bind(alice, alice.id) as service:
        journal = service.journal()
        try:
            journal.register_project(
                "idle-easy",
                request_id="synthetic-hide-request",
                title="Idle design",
                goal="Synthetic goal",
                thread="thread",
                input_id=None,
                surface="easy",
            )
            journal.update_projection("idle-easy", {"status": "awaiting_scientist"})
        finally:
            journal.close()
        evidence = service.context.projects_root / "idle-easy" / "keep.txt"
        evidence.parent.mkdir(parents=True, exist_ok=True)
        evidence.write_text("Synthetic scientific evidence remains unchanged.")
    path = f"/api/v1/scopes/{alice.id}/projects/idle-easy"
    with client(server, "alice") as owner:
        assert owner.delete(path, headers={"X-CSRF-Token": ""}).status_code == 403
        with client(server, "bob") as outsider:
            assert outsider.delete(path).status_code == 404
        with client(server, "admin") as administrator:
            assert administrator.delete(path).status_code == 403
        result = owner.delete(path)
        assert result.status_code == 200, result.text
        assert result.json()["recoverable"] is True
        assert owner.get(path + "/workbench").status_code == 404
        assert owner.get(f"/api/v1/scopes/{alice.id}/projects?surface=easy").json()["items"] == []
    assert evidence.read_text() == "Synthetic scientific evidence remains unchanged."
    with server.runtime.bind(alice, alice.id) as service:
        journal = service.journal()
        try:
            assert journal.project("idle-easy") is None
            assert journal.project("idle-easy", include_deleted=True)["deleted_at"] is not None
        finally:
            journal.close()


def test_migrated_localization_stays_in_authorized_scope(product):
    from easydesign.product.rabbit_chat import RabbitChatService

    server, _accounts, _admin, users, _context = product
    calls = []

    def provider(request):
        calls.append(request)
        yield {
            "type": "delta",
            "text": json.dumps({"items": [{"id": "why", "text": "保持科学结论。"}]}),
        }
        yield {"type": "done"}

    server.rabbit_chat = RabbitChatService(provider)
    payload = {
        "locale": "zh",
        "passages": [{"id": "why", "text": "Keep the scientific conclusion."}],
        "context": {"stage": "Site", "goal": "Synthetic design"},
    }
    alice = users[0]
    with client(server, "bob") as outsider:
        assert (
            outsider.post(f"/api/v1/scopes/{alice.id}/rabbit/localize", json=payload).status_code
            == 404
        )
    with client(server, "admin") as administrator:
        assert (
            administrator.post(
                f"/api/v1/scopes/{alice.id}/rabbit/localize", json=payload
            ).status_code
            == 403
        )
    with client(server, "alice") as owner:
        path = f"/api/v1/scopes/{alice.id}/rabbit/localize"
        first = owner.post(path, json=payload)
        assert first.status_code == 200, first.text
        assert owner.post(path, json=payload).json() == first.json()
    assert len(calls) == 1
