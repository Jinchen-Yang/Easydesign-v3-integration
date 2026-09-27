"""Real-subprocess regressions for the scoped native worker write-root boundary.

Evidence boundary labels:
- Every test here drives REAL ``easydesign.local_worker`` subprocesses. No
  models, predictions or GPU science run: Stage-01 with a two-chain local PDB
  deterministically freezes at the human chain-selection approval gate.
- No human approvals are performed; the tests stop at that boundary.
- The production worker must derive its expected writable roots ONLY from the
  trusted workspace context (marker declaration plus controller-published
  execution scope), never from the ``EASYDESIGN_LOCAL_WRITE_ROOTS`` declaration
  it is checking, and must keep exact equality plus the real Landlock sandbox.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest

from easydesign.execution_scope import EXECUTION_SCOPE_ENV, ExecutionScope
from easydesign.orchestration.local_jobs import (
    LocalStepJob,
    LocalStepJobController,
)
from easydesign.orchestration.task_tracking import atomic_dump_runtime_model
from easydesign.runtime_guard import LOCAL_WRITE_ROOTS_ENV
from easydesign.workspace_context import WorkspaceContext

pytest.importorskip("deepagents")

ACTIVE_JOB_STATUSES = {"queued", "running", "drain-requested"}


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch):
    from easydesign.agent.session_store import SessionStore
    from easydesign.agent.tools import TargetBridge
    from easydesign.orchestration.profile import initialize_runtime_profile
    from easydesign.orchestration.research import initialize_research_project
    from tests.agent_support import structure

    (tmp_path / "easydesign-workspace.yaml").write_text(
        'schema_version: "0.1"\nworkspace_id: scoped-worker-boundary-test\n'
    )
    monkeypatch.setenv("EASYDESIGN_WORKSPACE", str(tmp_path))
    monkeypatch.delenv(EXECUTION_SCOPE_ENV, raising=False)
    base = WorkspaceContext.from_root(tmp_path)
    base.ensure_layout()
    initialize_runtime_profile(base.profile_path)

    scope_a = base.with_execution_scope(
        ExecutionScope(
            scope_id="team-" + "a" * 32,
            actor_id="user-" + "b" * 32,
        )
    )
    scope_b = base.with_execution_scope(
        ExecutionScope(
            scope_id="team-" + "c" * 32,
            actor_id="user-" + "d" * 32,
        )
    )
    scope_a.ensure_layout()
    scope_b.ensure_layout()

    def build(context: WorkspaceContext, project_name: str) -> object:
        source = context.runtime_root / f"tmp/{project_name}-input.pdb"
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text(structure("AB"))
        project = context.projects_root / project_name
        initialize_research_project(project_root=project, target=source)
        return TargetBridge(project, "boundary-thread", SessionStore(project))

    return base, scope_a, scope_b, build


def wait_terminal(bridge, timeout: float = 120.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = bridge.get_job_status()
        if result["status"] not in ACTIVE_JOB_STATUSES:
            return result
        time.sleep(0.2)
    raise AssertionError("worker did not reach a terminal state")


def spawn_worker(
    context: WorkspaceContext,
    *,
    project_root: Path,
    declared_roots: tuple[Path, ...],
) -> tuple[str, subprocess.CompletedProcess[str]]:
    """Run the real worker binary against one forged write-root declaration."""

    job_id = f"job-{uuid4().hex[:16]}"
    controller = LocalStepJobController(context)
    revisions = sorted((project_root / "config-revisions").glob("easydesign.rev-*.yaml"))
    assert revisions, "project must own an immutable canonical config revision"
    now = datetime.now(UTC)
    record = LocalStepJob(
        job_id=job_id,
        operation="run",
        status="queued",
        project_id=project_root.name,
        project_root=project_root,
        step=1,
        config_path=revisions[-1],
        branch="boundary-test",
        log_path=context.runtime_root / "logs/local-jobs" / f"{job_id}.log",
        drain_path=context.runtime_root / "state/local-jobs" / f"{job_id}.drain",
        created_at=now,
        updated_at=now,
    )
    atomic_dump_runtime_model(record, controller.path(job_id))
    environment = os.environ.copy()
    environment.update(context.child_environment())
    environment.update(
        {
            "EASYDESIGN_LOCAL_DRAIN_FILE": str(record.drain_path),
            "PYTHONDONTWRITEBYTECODE": "1",
            "HF_HUB_OFFLINE": "1",
            "TRANSFORMERS_OFFLINE": "1",
            LOCAL_WRITE_ROOTS_ENV: os.pathsep.join(str(path) for path in declared_roots),
        }
    )
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "easydesign.local_worker",
            "--job-record",
            str(controller.path(job_id)),
        ],
        cwd=context.root,
        env=environment,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=120,
    )
    return job_id, completed


def rejected_before_any_run(
    context: WorkspaceContext,
    *,
    project_root: Path,
    declared_roots: tuple[Path, ...],
) -> str:
    job_id, completed = spawn_worker(
        context,
        project_root=project_root,
        declared_roots=declared_roots,
    )
    assert completed.returncode != 0, completed.stderr
    job = LocalStepJobController(context).load(job_id)
    assert job.status == "operational-failed"
    assert "write-root declaration does not match workspace" in (job.error or "")
    assert job.run_root is None
    return job_id


def test_scoped_stage01_reaches_human_target_approval_inside_its_namespace(
    workspace,
):
    base, scope_a, _scope_b, build = workspace
    with scope_a.activate():
        bridge = build(scope_a, "scoped-boundary")
        bridge.prepare_target()
        outcome = wait_terminal(bridge)
    assert outcome["status"] == "awaiting-human-approval", outcome
    assert outcome["error"] is None
    run_id = outcome["run_id"]
    assert run_id is not None
    run_root = scope_a.runs_root / "scoped-boundary" / run_id
    assert (run_root / "manifests" / "LATEST").is_file()
    decision_requests = list(
        (run_root / "decisions" / "stage01-chain-selection").glob("request.v*.json")
    )
    assert decision_requests, "the frozen chain-selection human gate must be published"
    assert not (base.runs_root / "scoped-boundary").exists()


def test_scoped_worker_rejects_cross_scope_write_root_declaration(workspace):
    base, scope_a, scope_b, build = workspace
    with scope_a.activate():
        bridge = build(scope_a, "cross-scope")
        project = bridge.project
    rejected_before_any_run(
        scope_a,
        project_root=project,
        declared_roots=scope_b.write_roots(),
    )
    assert not (scope_a.runs_root / "cross-scope").exists()
    assert not (scope_b.runs_root / "cross-scope").exists()


def test_scoped_worker_rejects_dropped_lease_root_and_extra_forged_root(workspace):
    base, scope_a, _scope_b, build = workspace
    with scope_a.activate():
        bridge = build(scope_a, "forged-roots")
        project = bridge.project
    rejected_before_any_run(
        scope_a,
        project_root=project,
        declared_roots=(
            scope_a.runtime_root,
            scope_a.projects_root,
            scope_a.runs_root,
            scope_a.archives_root,
        ),
    )
    evil_root = base.runtime_root.parent / "attacker-root"
    evil_root.mkdir(parents=True, exist_ok=True)
    rejected_before_any_run(
        scope_a,
        project_root=project,
        declared_roots=(*scope_a.write_roots(), evil_root),
    )
    assert list(evil_root.iterdir()) == []
    assert not (scope_a.runs_root / "forged-roots").exists()


def test_unscoped_worker_rejects_lease_root_in_declaration(workspace):
    base, _scope_a, _scope_b, build = workspace
    bridge = build(base, "unscoped-lease")
    project = bridge.project
    rejected_before_any_run(
        base,
        project_root=project,
        declared_roots=(*base.write_roots(), base.gpu_lease_root),
    )
    assert not (base.runs_root / "unscoped-lease").exists()
