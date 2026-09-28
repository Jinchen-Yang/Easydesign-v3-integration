"""End-to-end multi-user acceptance through the real account HTTP transport.

Every request below crosses the real ``MultiUserServer`` socket (ephemeral
loopback port) with ``trust_env=False`` clients. Compute dispatch is a MOCKED
launcher that records admissions; no real scientific worker, GPU job, or model
inference runs in this module, and every project/result here is synthetic.
Namespace/write-confinement checks spawn real subprocesses running production
``WorkspaceContext`` code.
"""

from __future__ import annotations

import json
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from easydesign.execution_scope import EXECUTION_SCOPE_ENV, ExecutionScope
from easydesign.product.account_server import MultiUserServer
from easydesign.product.accounts import AccountStore
from easydesign.product.domain import NativeGateway
from easydesign.product.tenancy import MultiUserRuntime
from easydesign.workspace_context import WorkspaceContext
from tests.agent_support import scripted_config, structure

PASSWORD = "Fixture-password-2026!"


@pytest.fixture
def multiuser(tmp_path: Path):
    (tmp_path / "easydesign-workspace.yaml").write_text('schema_version: "0.1"\n')
    context = WorkspaceContext.from_root(tmp_path)
    context.ensure_layout()
    accounts = AccountStore(context.runtime_root / "state/accounts/accounts.sqlite")
    admin = accounts.bootstrap_admin("admin", PASSWORD, "Platform Administrator")
    users = {}
    for name in ("alice", "bob", "carol"):
        user = accounts.register(name, PASSWORD, name)
        accounts.update_user(admin, user.id, status="active")
        users[name] = accounts.user(user.id)
    team_a = accounts.create_team(users["alice"], "Team Alpha")
    invitation = accounts.invite(users["alice"], team_a["id"], "bob")  # ordinary member
    accounts.respond_invitation(users["bob"], invitation["id"], accept=True)
    team_b = accounts.create_team(users["carol"], "Team Beta")
    models = tmp_path / "models.yaml"
    models.write_text(json.dumps(scripted_config().model_dump(mode="json")))
    launched: list[tuple[str, str]] = []  # mocked compute dispatch (admission, scope)

    def launcher(admission, service):
        launched.append((admission.id, service.scope_id))

    runtime = MultiUserRuntime(
        context, accounts, lambda c: NativeGateway(c, models), launcher=launcher
    )
    server = MultiUserServer(runtime, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield SimpleNamespace(
            server=server,
            accounts=accounts,
            runtime=runtime,
            context=context,
            admin=admin,
            users=users,
            team_a=team_a,
            team_b=team_b,
            launched=launched,
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@contextmanager
def client(server, username: str | None = None):
    origin = f"http://127.0.0.1:{server.server_port}"
    with httpx.Client(
        base_url=origin, headers={"Origin": origin}, timeout=30, trust_env=False
    ) as value:
        if username:
            result = value.post(
                "/api/v1/accounts/login", json={"username": username, "password": PASSWORD}
            )
            assert result.status_code == 200, result.text
            value.headers["X-CSRF-Token"] = result.json()["csrf_token"]
        yield value


def create_project(client_value, scope_id: str, request_id: str, **extra):
    payload = {
        "request_id": request_id,
        "title": extra.pop("title", "Integration program"),
        "goal": extra.pop("goal", "Synthetic multi-user acceptance goal."),
        "surface": "easy",
        **extra,
    }
    return client_value.post(f"/api/v1/scopes/{scope_id}/projects", json=payload)


def test_administration_only_mode_guards_compute_without_side_effects(tmp_path):
    """Accounts-only deployments advertise compute_available=false and every
    scientific start fails with the explicit compute_unavailable guard BEFORE
    any admission is reserved, so no quota is consumed or dispatched."""
    import threading

    (tmp_path / "easydesign-workspace.yaml").write_text('schema_version: "0.1"\n')
    context = WorkspaceContext.from_root(tmp_path)
    context.ensure_layout()
    accounts = AccountStore(context.runtime_root / "state/accounts/accounts.sqlite")
    admin = accounts.bootstrap_admin("admin", PASSWORD, "Administrator")
    user = accounts.register("erin", PASSWORD, "Erin")
    accounts.update_user(admin, user.id, status="active")
    runtime = MultiUserRuntime(
        context, accounts, lambda c: NativeGateway(c, tmp_path / "models.yaml")
    )
    server = MultiUserServer(runtime, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with client(server) as anonymous:
            assert anonymous.get("/api/v1/accounts/config").json()["compute_available"] is False
        with client(server, "erin") as erin:
            refused = create_project(erin, user.id, "no-compute-create-001")
            assert refused.status_code == 503
            assert refused.json()["error"]["code"] == "compute_unavailable"
            draft = erin.post(
                f"/api/v1/scopes/{user.id}/drafts",
                json={"title": "Draft before compute", "goal": "Synthetic goal."},
            )
            assert draft.status_code == 200
            denied = erin.post(
                f"/api/v1/scopes/{user.id}/drafts/{draft.json()['draft']['id']}/start",
                json={"revision": 1, "request_id": "no-compute-start-001"},
            )
            assert denied.status_code == 503
            assert denied.json()["error"]["code"] == "compute_unavailable"
            usage = erin.get(f"/api/v1/scopes/{user.id}/usage").json()
            assert usage["admissions"] == []
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_registration_approval_and_session_revocation_over_http(multiuser):
    server = multiuser.server
    with client(server) as anonymous:
        register = anonymous.post(
            "/api/v1/accounts/register",
            json={"username": "dave", "password": PASSWORD, "display_name": "Dave"},
        )
        assert register.status_code == 201
        dave_id = register.json()["user"]["id"]
        denied = anonymous.post(
            "/api/v1/accounts/login", json={"username": "dave", "password": PASSWORD}
        )
        assert denied.status_code == 403
        assert denied.json()["error"]["code"] == "account_pending"
        assert anonymous.get("/api/v1/scopes/" + dave_id + "/projects").status_code == 401

    with client(server, "admin") as admin:
        assert (
            admin.post(f"/api/v1/admin/users/{dave_id}", json={"status": "active"}).status_code
            == 200
        )
    with client(server) as fresh:
        first = fresh.post(
            "/api/v1/accounts/login", json={"username": "dave", "password": PASSWORD}
        )
        assert first.status_code == 200
        stale_token = first.headers["set-cookie"].split(";")[0].split("=", 1)[1]
        stale_csrf = first.json()["csrf_token"]

        second = fresh.post(
            "/api/v1/accounts/login", json={"username": "dave", "password": PASSWORD}
        )
        assert second.status_code == 200
        fresh.headers["X-CSRF-Token"] = second.json()["csrf_token"]
        # Logging in again revokes only the previous individual session.
        replay = fresh.get(
            "/api/v1/accounts/me",
            headers={
                "Cookie": f"easydesign_identity={stale_token}",
                "X-CSRF-Token": stale_csrf,
            },
        )
        assert replay.status_code == 401

        changed = fresh.post(
            "/api/v1/accounts/password",
            json={"current_password": PASSWORD, "password": "Rotated-fixture-pass!"},
        )
        assert changed.status_code == 200
        current_token = second.headers["set-cookie"].split(";")[0].split("=", 1)[1]
        invalidated = fresh.get(
            "/api/v1/accounts/me",
            headers={
                "Cookie": f"easydesign_identity={current_token}",
                "X-CSRF-Token": second.json()["csrf_token"],
            },
        )
        assert invalidated.status_code == 401

    with client(server) as relogin:
        final = relogin.post(
            "/api/v1/accounts/login",
            json={"username": "dave", "password": "Rotated-fixture-pass!"},
        )
        assert final.status_code == 200
        relogin.headers["X-CSRF-Token"] = final.json()["csrf_token"]
        assert relogin.post("/api/v1/accounts/logout", json={}).status_code == 200
        assert relogin.get("/api/v1/accounts/me").status_code == 401


def test_personal_projects_requests_events_and_uploads_are_scope_isolated(multiuser):
    server, alice, bob = multiuser.server, multiuser.users["alice"], multiuser.users["bob"]
    scope, other = alice.id, bob.id
    with client(server, "alice") as alice_client:
        created = create_project(alice_client, scope, "iso-alice-create-0001")
        assert created.status_code == 202, created.text
        project = created.json()["project"]
        assert create_project(alice_client, scope, "iso-alice-create-0001").json()["project"] == (
            project
        )
        assert multiuser.launched == [(multiuser.launched[0][0], scope)]

        uploaded = alice_client.post(
            f"/api/v1/scopes/{scope}/inputs?filename=seed.pdb",
            content=structure("A").encode(),
        )
        assert uploaded.status_code == 201, uploaded.text
        input_id = uploaded.json()["id"]
        assert (
            alice_client.post(
                f"/api/v1/scopes/{scope}/inputs?filename=seed.pdb",
                content=structure("A").encode(),
            ).json()["id"]
            == input_id
        )

        listing = alice_client.get(f"/api/v1/scopes/{scope}/projects?surface=easy").json()
        assert listing["total"] == 1 and listing["items"][0]["id"] == project
        assert (
            alice_client.get(f"/api/v1/scopes/{scope}/projects/{project}/workbench").status_code
            == 200
        )
        events = alice_client.get(f"/api/v1/scopes/{scope}/projects/{project}/events")
        assert events.status_code == 200 and events.json()["items"]
        assert (
            alice_client.get(f"/api/v1/scopes/{scope}/requests/iso-alice-create-0001").json()[
                "state"
            ]
            == "accepted"
        )
        usage = alice_client.get(f"/api/v1/scopes/{scope}/usage").json()
        assert usage["stored_upload_bytes"] == len(structure("A").encode())
        assert len(usage["admissions"]) == 1


    with client(server, "bob") as bob_client:
        # Unknown scope membership, foreign namespace, and cross-scope reuse all fail.
        assert (
            bob_client.get(f"/api/v1/scopes/{scope}/projects/{project}/workbench").status_code
            == 404
        )
        assert (
            bob_client.get(f"/api/v1/scopes/{other}/projects/{project}/workbench").status_code
            == 404
        )
        assert (
            bob_client.get(f"/api/v1/scopes/{other}/projects/{project}/events").status_code == 404
        )
        assert (
            bob_client.get(f"/api/v1/scopes/{other}/requests/iso-alice-create-0001").status_code
            == 404
        )
        assert bob_client.get(f"/api/v1/scopes/{other}/artifacts/{input_id}").status_code == 404
        borrowed = create_project(bob_client, other, "iso-bob-create-00001", input_id=input_id)
        assert borrowed.status_code == 400
        assert borrowed.json()["error"]["code"] == "input_missing"
        assert bob_client.get(f"/api/v1/scopes/{other}/projects?surface=easy").json()["total"] == 0


def test_scoped_easy_sequence_upload_and_typed_create_preserve_account_ledger(multiuser):
    server, alice = multiuser.server, multiuser.users["alice"]
    sequence = b">target\nACDEFGHIKLMNPQRSTVWY\n"
    with client(server, "alice") as owner:
        uploaded = owner.post(
            f"/api/v1/scopes/{alice.id}/inputs?filename=target.fasta", content=sequence
        )
        assert uploaded.status_code == 201, uploaded.text
        artifact = uploaded.json()
        assert artifact["kind"] == "sequence"
        created = create_project(
            owner,
            alice.id,
            "typed-sequence-account-0001",
            target_input={"kind": "sequence", "artifact_id": artifact["id"]},
        )
        assert created.status_code == 202, created.text
        usage = owner.get(f"/api/v1/scopes/{alice.id}/usage").json()
        assert usage["stored_upload_bytes"] == len(sequence)
        assert len(usage["admissions"]) == 1
        assert multiuser.launched[0][1] == alice.id


def test_team_draft_collaboration_separates_editing_from_scientific_startup(multiuser):
    server = multiuser.server
    team = multiuser.team_a["id"]
    base = f"/api/v1/scopes/{team}"
    with client(server, "bob") as member:
        saved = member.post(
            base + "/drafts",
            json={"title": "Shared binder draft", "goal": "Synthetic team goal."},
        )
        assert saved.status_code == 200, saved.text
        draft = saved.json()["draft"]
        assert draft["revision"] == 1
        assert member.get(base + "/drafts").json()["drafts"][0]["id"] == draft["id"]

    with client(server, "alice") as owner:
        updated = owner.post(
            f"{base}/drafts/{draft['id']}",
            json={
                "title": "Reviewed binder draft",
                "goal": "Synthetic team goal, reviewed.",
                "revision": 1,
            },
        )
        assert updated.status_code == 200
        assert updated.json()["draft"]["revision"] == 2

    with client(server, "bob") as member:
        stale = member.post(
            f"{base}/drafts/{draft['id']}",
            json={
                "title": "Conflicting edit",
                "goal": "Synthetic team goal.",
                "revision": 1,
            },
        )
        assert stale.status_code == 409
        assert stale.json()["error"]["code"] == "stale_draft"
        denied = member.post(
            f"{base}/drafts/{draft['id']}/start",
            json={"revision": 2, "request_id": "draft-bob-start-00001"},
        )
        assert denied.status_code == 403
        assert denied.json()["error"]["code"] == "team_admin_required"
    assert multiuser.launched == []

    with client(server, "alice") as owner:
        started = owner.post(
            f"{base}/drafts/{draft['id']}/start",
            json={"revision": 2, "request_id": "draft-alice-start-001"},
        )
        assert started.status_code == 202, started.text
        project = started.json()["project"]
        retried = owner.post(
            f"{base}/drafts/{draft['id']}/start",
            json={"revision": 2, "request_id": "draft-alice-start-001"},
        )
        assert retried.status_code == 202
        assert retried.json()["project"] == project
        assert (
            owner.post(
                f"{base}/drafts/{draft['id']}/start",
                json={"revision": 2, "request_id": "draft-alice-start-002"},
            ).status_code
            == 409
        )
        frozen = owner.post(
            f"{base}/drafts/{draft['id']}",
            json={"title": "Late edit", "goal": "Synthetic team goal.", "revision": 2},
        )
        assert frozen.status_code == 409
        assert frozen.json()["error"]["code"] == "draft_frozen"
        view = owner.get(f"{base}/drafts/{draft['id']}").json()["draft"]
        assert view["state"] == "started" and view["project_id"] == project
        assert owner.get(f"{base}/projects?surface=easy").json()["total"] == 1
    assert [scope for _, scope in multiuser.launched] == [team]


def test_conflicting_draft_start_reports_conflict_without_adopting(multiuser):
    """A start whose request id is already bound to another payload fails with
    ``idempotency_conflict`` and must not adopt the unrelated journal row's
    project (regression for findings #1, fixed upstream)."""
    server = multiuser.server
    team = multiuser.team_a["id"]
    base = f"/api/v1/scopes/{team}"
    with client(server, "alice") as owner:
        draft = owner.post(
            base + "/drafts",
            json={"title": "Recovery draft", "goal": "Synthetic recovery goal."},
        ).json()["draft"]
        create_project(owner, team, "draft-conflict-seed-01", title="Existing program")
        conflict = owner.post(
            f"{base}/drafts/{draft['id']}/start",
            json={"revision": 1, "request_id": "draft-conflict-seed-01"},
        )
        assert conflict.status_code == 409
        assert conflict.json()["error"]["code"] == "idempotency_conflict"
        assert multiuser.launched  # only the seed project dispatched
        refreshed = owner.get(f"{base}/drafts/{draft['id']}").json()["draft"]
        assert refreshed["state"] == "draft"
        assert refreshed["project_id"] is None


def test_failed_draft_startup_recovers_and_does_not_freeze_the_draft(multiuser):
    """A conflicting draft start must leave the draft editable; recovery via a
    fresh request id succeeds (regression for findings #1, fixed upstream)."""
    server, alice = multiuser.server, multiuser.users["alice"]
    team = multiuser.team_a["id"]
    base = f"/api/v1/scopes/{team}"
    with client(server, "admin") as admin:
        # Recovery needs a second personal slot: the seed create holds the
        # default one, and personal quotas span every team scope.
        raised = admin.post(
            f"/api/v1/admin/quotas/{alice.id}",
            json={"max_active_jobs": 2, "max_gpu_devices": 2},
        )
        assert raised.status_code == 200
    with client(server, "alice") as owner:
        draft = owner.post(
            base + "/drafts",
            json={"title": "Recovery draft", "goal": "Synthetic recovery goal."},
        ).json()["draft"]
        create_project(owner, team, "draft-conflict-seed-01", title="Existing program")
        conflict = owner.post(
            f"{base}/drafts/{draft['id']}/start",
            json={"revision": 1, "request_id": "draft-conflict-seed-01"},
        )
        assert conflict.status_code == 409
        assert conflict.json()["error"]["code"] == "idempotency_conflict"
        refreshed = owner.get(f"{base}/drafts/{draft['id']}").json()["draft"]
        assert refreshed["state"] == "draft", "failed startup must reset the draft"
        started = owner.post(
            f"{base}/drafts/{draft['id']}/start",
            json={"revision": 1, "request_id": "draft-retry-start-0001"},
        )
        assert started.status_code == 202, started.text


def test_concurrent_draft_saves_resolve_to_exactly_one_revision(multiuser):
    server = multiuser.server
    team = multiuser.team_a["id"]
    with client(server, "alice") as owner:
        draft = owner.post(
            f"/api/v1/scopes/{team}/drafts",
            json={"title": "Race draft", "goal": "Synthetic concurrent draft."},
        ).json()["draft"]

    def save(client_value, title):
        return client_value.post(
            f"/api/v1/scopes/{team}/drafts/{draft['id']}",
            json={"title": title, "goal": "Synthetic concurrent draft.", "revision": 1},
        )

    with (
        client(server, "alice") as alice_client,
        client(server, "bob") as bob_client,
    ):
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [
                pool.submit(save, alice_client, "Alice concurrent edit"),
                pool.submit(save, bob_client, "Bob concurrent edit"),
            ]
            outcomes = [future.result() for future in futures]
        codes = sorted(response.status_code for response in outcomes)
        assert codes == [200, 409]
        final = alice_client.get(f"/api/v1/scopes/{team}/drafts/{draft['id']}").json()["draft"]
        assert final["revision"] == 2
        assert final["updated_by"] in {multiuser.users["alice"].id, multiuser.users["bob"].id}
        winner = next(r for r in outcomes if r.status_code == 200).json()["draft"]
        assert winner["payload"]["title"] == final["payload"]["title"]


def test_platform_admin_reads_every_scope_but_cannot_write_or_approve(multiuser):
    server, alice = multiuser.server, multiuser.users["alice"]
    with client(server, "alice") as owner:
        project = create_project(owner, alice.id, "admin-read-create-001").json()["project"]

    with client(server, "admin") as admin, client(server, "bob") as bob:
        base = f"/api/v1/scopes/{alice.id}"
        assert admin.get(f"{base}/projects/{project}/workbench").status_code == 200
        assert admin.get(f"{base}/projects/{project}/events").status_code == 200
        assert admin.get(f"{base}/usage").json()["scope"]["role"] == "observer"
        assert admin.get(f"{base}/drafts").status_code == 200
        denied_write = admin.post(
            f"{base}/projects/{project}/title", json={"title": "Admin override"}
        )
        assert denied_write.status_code == 403
        assert denied_write.json()["error"]["code"] == "read_only_scope"
        denied_create = create_project(admin, alice.id, "admin-create-attempt1")
        assert denied_create.status_code == 403
        denied_draft = admin.post(
            f"{base}/drafts", json={"title": "Admin draft", "goal": "Synthetic goal."}
        )
        assert denied_draft.status_code == 403
        admissions = admin.get("/api/v1/admin/admissions").json()["admissions"]
        assert admissions and all(item["scope_id"] for item in admissions)
        events = admin.get("/api/v1/admin/audit").json()["events"]
        assert any(e["action"] == "admin.scope.read" and e["scope_id"] == alice.id for e in events)
        assert bob.get("/api/v1/admin/audit").status_code == 403
        assert bob.get("/api/v1/admin/admissions").status_code == 403
        assert bob.get(f"{base}/projects/{project}/workbench").status_code == 404


def test_quota_admission_idempotency_and_failure_rollback_over_http(multiuser):
    server, alice, bob = (
        multiuser.server,
        multiuser.users["alice"],
        multiuser.users["bob"],
    )
    with client(server, "admin") as admin:
        lowered = admin.post(f"/api/v1/admin/quotas/{alice.id}", json={"max_active_jobs": 1})
        assert lowered.status_code == 200
        assert lowered.json()["limits"]["max_active_jobs"] == 1

    with client(server, "alice") as alice_client:
        first = create_project(alice_client, alice.id, "quota-alice-create-001")
        assert first.status_code == 202
        blocked = create_project(alice_client, alice.id, "quota-alice-create-002")
        assert blocked.status_code == 409
        assert blocked.json()["error"]["code"] == "quota_exceeded"
        admissions = alice_client.get(f"/api/v1/scopes/{alice.id}/usage").json()["admissions"]
        assert [item["request_id"] for item in admissions] == ["quota-alice-create-001"]

        # Controller-side simulation of the worker finishing native work.
        multiuser.runtime.resources.transition(admissions[0]["id"], "released")
        after_release = create_project(alice_client, alice.id, "quota-alice-create-002")
        assert after_release.status_code == 202

    with client(server, "bob") as bob_client:
        failed = create_project(bob_client, bob.id, "quota-bob-fail-000001", input_id="f" * 64)
        assert failed.status_code == 400
        assert failed.json()["error"]["code"] == "input_missing"
        usage = bob_client.get(f"/api/v1/scopes/{bob.id}/usage").json()
        assert [item["state"] for item in usage["admissions"]] == ["failed"]
        # The failed admission must not hold the default single job slot.
        recovered = create_project(bob_client, bob.id, "quota-bob-create-00001")
        assert recovered.status_code == 202
        # Concurrent identical creates are covered separately (race regression).


@pytest.mark.parametrize("workers", [6, 12])
def test_concurrent_identical_creates_are_idempotent_over_http(multiuser, workers):
    """Concurrent identical creates must all return the winner's 202 (regression
    for findings #4, fixed via bounded WAL-bootstrap retry and idempotent
    thread seeding in ProductService)."""
    server, carol = multiuser.server, multiuser.users["carol"]
    payload = {
        "request_id": f"race-carol-create-{workers:06d}",
        "title": "Concurrent acceptance",
        "goal": "Synthetic concurrent goal.",
        "surface": "easy",
    }
    url = f"/api/v1/scopes/{carol.id}/projects"
    with client(server, "carol") as carol_client, ThreadPoolExecutor(max_workers=workers) as pool:
        responses = list(pool.submit(carol_client.post, url, json=payload) for _ in range(workers))
        results = [response.result() for response in responses]
        assert all(response.status_code == 202 for response in results), [
            (r.status_code, r.text[:200]) for r in results
        ]
        assert len({response.json()["project"] for response in results}) == 1
        assert (
            carol_client.get(f"/api/v1/scopes/{carol.id}/projects?surface=easy").json()["total"]
            == 1
        )
    assert len(multiuser.launched) == 1


def test_request_ids_are_namespaced_per_scope_and_per_user(multiuser):
    server, alice, bob, carol = (
        multiuser.server,
        multiuser.users["alice"],
        multiuser.users["bob"],
        multiuser.users["carol"],
    )
    shared_request = "shared-request-id-0001"
    with client(server, "admin") as admin:
        # Personal quotas (jobs AND GPU slots) span every team the user acts
        # in; give headroom so this test exercises identity namespacing, not
        # quota rejection.
        for user in (alice, bob, carol):
            raised = admin.post(
                f"/api/v1/admin/quotas/{user.id}",
                json={"max_active_jobs": 8, "max_gpu_devices": 4},
            )
            assert raised.status_code == 200
    with client(server, "alice") as alice_client, client(server, "bob") as bob_client:
        alice_response = create_project(alice_client, alice.id, shared_request)
        bob_response = create_project(bob_client, bob.id, shared_request)
        assert alice_response.status_code == bob_response.status_code == 202
        alice_project = alice_response.json()["project"]
        bob_project = bob_response.json()["project"]
        # The same request id in another personal scope is fully independent:
        # both journals recorded their own accepted create, and each project is
        # only addressable inside its owner's scope namespace.
        alice_list = alice_client.get(f"/api/v1/scopes/{alice.id}/projects").json()["items"]
        bob_list = bob_client.get(f"/api/v1/scopes/{bob.id}/projects").json()["items"]
        assert alice_list[0]["id"] == alice_project
        assert bob_list[0]["id"] == bob_project
        assert (
            alice_client.get(
                f"/api/v1/scopes/{bob.id}/projects/{bob_project}/workbench"
            ).status_code
            == 404
        )
    with (
        client(server, "alice") as alice_client,
        client(server, "bob") as bob_client,
        client(server, "carol") as carol_client,
    ):
        team_project = create_project(alice_client, multiuser.team_a["id"], shared_request).json()[
            "project"
        ]
        # The same identity in another team and another personal scope is independent.
        other_team = create_project(carol_client, multiuser.team_b["id"], shared_request).json()[
            "project"
        ]
        personal = create_project(carol_client, carol.id, shared_request).json()["project"]
        assert other_team and personal
        team_listing = alice_client.get(f"/api/v1/scopes/{multiuser.team_a['id']}/projects").json()[
            "items"
        ]
        assert [item["id"] for item in team_listing] == [team_project]
        # A member cannot start science in the team, and reusing another
        # operation's request id for a different payload is rejected.
        hijack = create_project(bob_client, multiuser.team_a["id"], shared_request)
        assert hijack.status_code == 403  # member cannot start science in the team
        replay = create_project(
            alice_client,
            multiuser.team_a["id"],
            shared_request,
            title="Different payload",
        )
        assert replay.status_code == 409
        assert replay.json()["error"]["code"] == "idempotency_conflict"


def test_scope_namespaces_on_disk_and_real_subprocess_write_confinement(multiuser, tmp_path):
    server, alice, bob = multiuser.server, multiuser.users["alice"], multiuser.users["bob"]
    with client(server, "alice") as alice_client, client(server, "bob") as bob_client:
        alice_project = create_project(alice_client, alice.id, "ns-alice-create-000001").json()[
            "project"
        ]
        bob_project = create_project(bob_client, bob.id, "ns-bob-create-0000001").json()["project"]
    scopes_root = multiuser.context.projects_root / "scopes"
    alice_root = scopes_root / alice.id / alice_project
    bob_root = scopes_root / bob.id / bob_project
    assert (alice_root / "metadata/agent.sqlite").is_file()
    assert (bob_root / "metadata/agent.sqlite").is_file()
    assert not (scopes_root / bob.id / alice_project).exists()
    assert not (scopes_root / alice.id / bob_project).exists()

    alice_context = multiuser.context.with_execution_scope(
        ExecutionScope(scope_id=alice.id, actor_id=alice.id)
    )
    alice_context.ensure_layout()
    env = alice_context.subprocess_environment()
    probe = """
import json, sys
from easydesign.workspace_context import WorkspaceContext
context = WorkspaceContext.discover()
result = {"projects": str(context.projects_root), "scope": context.execution_scope.scope_id}
target = sys.argv[1]
try:
    context.assert_write_path(__import__("pathlib").Path(target))
except Exception as error:
    result["write"] = type(error).__name__
else:
    result["write"] = "allowed"
print(json.dumps(result))
"""
    completed = subprocess.run(
        [sys.executable, "-B", "-c", probe, str(bob_root / "foreign")],
        capture_output=True,
        text=True,
        check=True,
        cwd=multiuser.context.root,
        env=env,
    )
    observed = json.loads(completed.stdout)
    assert observed["projects"] == str(alice_context.projects_root)
    assert observed["scope"] == alice.id
    assert observed["write"] == "PathPolicyError"
    assert Path(env[EXECUTION_SCOPE_ENV]).is_relative_to(multiuser.context.shared_runtime_root)


def test_scoped_response_rewriting_covers_declared_link_fields():
    """Every declared link field must be scope-qualified; details_url was the
    known gap (backend fixed it as SCOPED_LINK_KEYS while this suite landed)."""
    from easydesign.product.account_server import _scoped_urls

    scope = "user-" + "d" * 32
    payload = {
        "decision": {
            "url": "/api/v1/artifacts/" + "a" * 64,
            "details_url": "/api/v1/artifacts/" + "b" * 64,
            "unrelated": "/api/v1/never-touched",
        }
    }
    rendered = _scoped_urls(payload, scope)
    assert rendered["decision"]["url"] == f"/api/v1/scopes/{scope}/artifacts/" + "a" * 64
    assert rendered["decision"]["details_url"] == (f"/api/v1/scopes/{scope}/artifacts/" + "b" * 64)
    assert rendered["decision"]["unrelated"] == "/api/v1/never-touched"
