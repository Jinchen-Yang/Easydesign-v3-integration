"""End-to-end synthetic native Gate flow through the real multi-user transport.

Evidence boundary labels:
- Stage-01/Stage-02 native evidence is produced by the REAL detached local
  worker subprocesses running the canonical pipelines inside the team's
  scoped namespace (Landlock-sandboxed). Target preparation here is
  deterministic local parsing; no remote services are contacted.
- Model providers on the agent path are scripted test doubles
  (``NoInference``); no real model, GPU, or scientific inference is invoked.
- The human Gate approval is performed by TEST ACTORS over the real scoped
  HTTP API: ordinary member ``bob`` is refused, team admin ``alice`` approves.
- A mocked launcher records compute dispatch (admission, scope); the native
  response application runs the same in-process code path a scoped worker
  would run. This is engineering acceptance, NOT a real GPU science run.
"""

from __future__ import annotations

import asyncio
import json
import threading
from pathlib import Path

import pytest

from easydesign.execution_scope import ExecutionScope
from easydesign.product.account_server import MultiUserServer
from easydesign.product.accounts import AccountStore
from easydesign.product.domain import NativeGateway
from easydesign.product.tenancy import MultiUserRuntime
from easydesign.workspace_context import WorkspaceContext
from tests.agent_support import (
    ScriptedModel,
    scripted_config,
    structure,
    terminal,
)
from tests.unit.agent.test_site_portfolio import review_card, setup_portfolio

pytest.importorskip("deepagents")

from easydesign.agent.cli import run_session  # noqa: E402
from easydesign.agent.harness import fingerprint  # noqa: E402

PASSWORD = "Fixture-password-2026!"
ROLES = ("coordinator", "target", "site", "binder", "judge", "pilot-diagnosis", "final-selection")
GOAL = "Synthetic multi-user Gate acceptance goal"


class NoInference(ScriptedModel):
    """Scripted provider double; refuses any unplanned scientific inference."""

    def bind_tools(self, tools, **kwargs):
        return self

    def answer(self, messages):
        raise AssertionError("This acceptance path must not trigger new model inference")


def scripted_models():
    return {role: NoInference(role=role) for role in ROLES}


def build_workspace(tmp_path: Path, monkeypatch) -> WorkspaceContext:
    (tmp_path / "easydesign-workspace.yaml").write_text(
        'schema_version: "0.1"\nworkspace_id: multiuser-native-gate\n'
    )
    monkeypatch.setenv("EASYDESIGN_WORKSPACE", str(tmp_path))
    context = WorkspaceContext.from_root(tmp_path)
    context.ensure_layout()
    from easydesign.orchestration.profile import initialize_runtime_profile

    initialize_runtime_profile(context.profile_path)
    return context


@pytest.fixture
def gate_product(tmp_path: Path, monkeypatch):
    from easydesign.agent.phase2 import Phase2Bridge
    from easydesign.agent.session_store import SessionStore
    from easydesign.agent.tools import TargetBridge
    from easydesign.orchestration.research import initialize_research_project

    context = build_workspace(tmp_path, monkeypatch)
    accounts = AccountStore(context.runtime_root / "state/accounts/accounts.sqlite")
    admin = accounts.bootstrap_admin("admin", PASSWORD, "Platform Administrator")
    alice = accounts.register("alice", PASSWORD, "Alice")
    bob = accounts.register("bob", PASSWORD, "Bob")
    for user in (alice, bob):
        accounts.update_user(admin, user.id, status="active")
    team = accounts.create_team(alice, "Gate Team")
    invitation = accounts.invite(alice, team["id"], "bob")  # ordinary member
    accounts.respond_invitation(bob, invitation["id"], accept=True)
    alice, bob = accounts.user(alice.id), accounts.user(bob.id)

    # Build the synthetic native Site Gate project INSIDE the team namespace.
    # The scoped context stays active so the REAL local worker executes
    # Stage-01 with its team-scoped write roots and Landlock sandbox.
    scoped = context.with_execution_scope(ExecutionScope(scope_id=team["id"], actor_id=alice.id))
    scoped.ensure_layout()
    with scoped.activate():
        source = scoped.runtime_root / "tmp/gate-input.pdb"
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text(structure("A"))
        project = scoped.projects_root / "target-test"
        initialize_research_project(project_root=project, target=source)
        store = SessionStore(project)
        try:
            target = TargetBridge(project, "gate-thread", store)
            target.prepare_target()
            terminal(target)
            bridge = Phase2Bridge(project, "gate-thread", store)
            setup_portfolio(bridge)
            review_card(bridge)
            # Advance the native session to the pending Site decision card
            # without any model inference (scripted provider doubles only).
            with bridge.store.db:
                bridge.store.db.execute(
                    "UPDATE threads SET fingerprint=?,goal=? WHERE id=?",
                    (fingerprint(scripted_config()), GOAL, bridge.thread),
                )
            result = asyncio.run(run_session(bridge, scripted_config(), scripted_models(), GOAL))
            assert result["status"] == "awaiting-human-approval", result
        finally:
            store.close()
        # Bridges bind their WorkspaceContext at construction; build the
        # fixture's reader bridge while the team scope is still active.
        fixture_bridge = Phase2Bridge(project, "gate-thread", SessionStore(project))

    models = tmp_path / "models.yaml"
    models.write_text(json.dumps(scripted_config().model_dump(mode="json")))
    launched: list[tuple[str, str]] = []

    def launcher(admission, service):
        launched.append((admission.id, service.scope_id))

    runtime = MultiUserRuntime(
        context,
        accounts,
        lambda c: NativeGateway(c, models, model_factory=lambda *a, **k: scripted_models()),
        launcher=launcher,
    )
    server = MultiUserServer(runtime, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        from types import SimpleNamespace

        yield SimpleNamespace(
            server=server,
            runtime=runtime,
            bridge=fixture_bridge,
            context=context,
            scoped=scoped,
            team=team["id"],
            alice=alice,
            bob=bob,
            launched=launched,
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def login_client(server, username: str):
    import httpx

    origin = f"http://127.0.0.1:{server.server_port}"
    value = httpx.Client(base_url=origin, headers={"Origin": origin}, timeout=60, trust_env=False)
    result = value.post("/api/v1/accounts/login", json={"username": username, "password": PASSWORD})
    assert result.status_code == 200, result.text
    value.headers["X-CSRF-Token"] = result.json()["csrf_token"]
    return value


def test_native_site_gate_approval_requires_team_admin_over_http(gate_product):
    ns = gate_product
    base = f"/api/v1/scopes/{ns.team}/projects/target-test"
    alice = login_client(ns.server, "alice")
    bob = login_client(ns.server, "bob")
    try:
        # Both team members can READ the pending native decision...
        for client_value in (alice, bob):
            snapshot = client_value.get(base + "/workbench")
            assert snapshot.status_code == 200, snapshot.text
            assert snapshot.json()["decision"]["gate"] == 2
        decision = alice.get(base + "/workbench").json()["decision"]
        chosen = next(o for o in decision["options"] if o["rank"] == "B")
        assert "approve" in chosen["actions"]
        revision = alice.get(base + "/workbench").json()["revision"]
        payload = {
            "request_id": "gate-approve-request-001",
            "revision": revision,
            "action": "approve",
            "card_id": decision["id"],
            "selected_option_id": chosen["option_id"],
        }

        # ...but only a team admin may answer the native Gate.
        refused = bob.post(base + "/actions", json=payload)
        assert refused.status_code == 403
        assert refused.json()["error"]["code"] == "team_admin_required"
        assert ns.bridge.approved_site() is None

        accepted = alice.post(base + "/actions", json=payload)
        assert accepted.status_code == 202, accepted.text
        assert alice.post(base + "/actions", json=payload).json()["id"] == accepted.json()["id"]
        assert [scope for _, scope in ns.launched] == [ns.team]

        # Scoped-worker simulation: apply the native response through the same
        # in-process code path a detached scoped worker would run.
        with ns.runtime.bind(ns.alice, ns.team) as service:
            service.run(payload["request_id"])

        status = alice.get(f"/api/v1/scopes/{ns.team}/requests/{payload['request_id']}").json()
        assert status["state"] == "succeeded", status
        # Native evidence readers discover the scoped workspace context, so
        # the readback runs under the same activation the server uses.
        with ns.scoped.activate():
            approved = ns.bridge.approved_site()
        assert approved is not None
        assert approved["hotspots"]["hotspot_sets"][0]["label_seq_ids"] == chosen["design_labels"]
        refreshed = alice.get(base + "/workbench").json()
        assert refreshed["decision"] is None
        assert refreshed["scientific_context"]["approved_site"]["selected_rank"] == "B"
    finally:
        alice.close()
        bob.close()


def test_native_stage_evidence_stays_inside_the_team_namespace(gate_product):
    ns = gate_product
    # The real Stage-01 worker published its run only in the team scope.
    assert (ns.scoped.runs_root / "target-test").is_dir()
    assert not (ns.context.runs_root / "target-test").exists()
    alice = login_client(ns.server, "alice")
    try:
        events = alice.get("/api/v1/scopes/" + ns.team + "/projects/target-test/events")
        assert events.status_code == 200
        assert events.json()["items"]
        carol_free = alice.get("/api/v1/scopes/" + ns.alice.id + "/projects")
        assert carol_free.json()["total"] == 0  # nothing leaked to personal scope
    finally:
        alice.close()
