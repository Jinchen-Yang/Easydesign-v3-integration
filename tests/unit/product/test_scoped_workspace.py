from __future__ import annotations

import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from easydesign.core import ConfigurationError, PathPolicyError
from easydesign.execution_scope import EXECUTION_SCOPE_ENV, ExecutionScope
from easydesign.workspace_context import WorkspaceContext


@pytest.fixture
def workspace(tmp_path: Path) -> WorkspaceContext:
    (tmp_path / "easydesign-workspace.yaml").write_text('schema_version: "0.1"\n')
    context = WorkspaceContext.from_root(tmp_path)
    context.ensure_layout()
    return context


def scope(context: WorkspaceContext, digit: str) -> WorkspaceContext:
    return context.with_execution_scope(
        ExecutionScope(
            scope_id="user-" + digit * 32,
            actor_id="user-" + digit * 32,
        )
    )


def test_scope_roots_are_private_but_assets_and_device_leases_are_clone_shared(workspace):
    alice, bob = scope(workspace, "a"), scope(workspace, "b")
    alice.ensure_layout()
    bob.ensure_layout()
    for name in ("runtime_root", "projects_root", "runs_root", "archives_root"):
        assert getattr(alice, name) != getattr(bob, name)
        assert getattr(alice, name).is_relative_to(workspace.root)
        with pytest.raises(PathPolicyError):
            alice.assert_write_path(getattr(bob, name) / "foreign")
    assert alice.environment_registry_root == bob.environment_registry_root
    assert alice.asset_registry_root == workspace.asset_registry_root
    assert alice.gpu_lease_root == workspace.gpu_lease_root
    assert alice.profile_path == workspace.profile_path
    with pytest.raises(PathPolicyError):
        alice.assert_write_path(workspace.runtime_root / "models/protected-model.bin")
    with pytest.raises(PathPolicyError):
        alice.assert_write_path(workspace.root / ".git/config", allow_git=True)


def test_scope_environment_is_private_and_propagates_to_a_real_subprocess(workspace):
    alice, bob = scope(workspace, "a"), scope(workspace, "b")
    aenv, benv = alice.subprocess_environment(), bob.subprocess_environment()
    for key in ("HOME", "TMPDIR", "XDG_CACHE_HOME", "TORCH_EXTENSIONS_DIR"):
        assert aenv[key] != benv[key]
        assert Path(aenv[key]).resolve().is_relative_to(alice.runtime_root)
    assert aenv["CUDA_VISIBLE_DEVICES"] == ""
    assert Path(aenv[EXECUTION_SCOPE_ENV]).is_relative_to(workspace.shared_runtime_root)
    result = subprocess.run(
        [
            sys.executable,
            "-B",
            "-c",
            "import json; from easydesign.workspace_context import WorkspaceContext; "
            "c=WorkspaceContext.discover(); "
            "print(json.dumps([str(c.projects_root),str(c.runs_root),c.execution_scope.scope_id]))",
        ],
        cwd=workspace.root,
        env=aenv,
        capture_output=True,
        text=True,
        check=True,
    )
    assert json.loads(result.stdout) == [
        str(alice.projects_root),
        str(alice.runs_root),
        alice.execution_scope.scope_id,
    ]


def test_request_contexts_are_thread_local_and_base_read_helpers_keep_the_scope(workspace):
    contexts = [scope(workspace, "a"), scope(workspace, "b")]

    def observe(context):
        with context.activate():
            current = WorkspaceContext.discover(workspace.root)
            helper_env = current.base_context().child_environment()
            return current.runs_root, helper_env[EXECUTION_SCOPE_ENV]

    with ThreadPoolExecutor(max_workers=2) as pool:
        values = list(pool.map(observe, contexts))
    assert values == [(c.runs_root, str(c.execution_scope_path)) for c in contexts]
    assert WorkspaceContext.discover(workspace.root).execution_scope is None


def test_scope_file_tampering_and_foreign_scope_files_fail_closed(workspace, tmp_path, monkeypatch):
    alice = scope(workspace, "a")
    monkeypatch.setenv("EASYDESIGN_WORKSPACE", str(workspace.root))
    monkeypatch.setenv(EXECUTION_SCOPE_ENV, str(alice.execution_scope_path))
    payload = json.loads(alice.execution_scope_path.read_text())
    payload["scope"]["scope_id"] = "user-" + "b" * 32
    alice.execution_scope_path.write_text(json.dumps(payload))
    with pytest.raises(ConfigurationError, match="checksum"):
        WorkspaceContext.discover()
    outside = tmp_path / "outside-scope.json"
    outside.write_text(json.dumps(payload))
    monkeypatch.setenv(EXECUTION_SCOPE_ENV, str(outside))
    with pytest.raises(PathPolicyError):
        WorkspaceContext.discover()


def test_scoped_namespace_cannot_be_redirected_with_a_symlink(workspace):
    alice, bob = scope(workspace, "a"), scope(workspace, "b")
    bob.ensure_layout()
    parent = workspace.projects_root / "scopes"
    parent.mkdir(exist_ok=True)
    (parent / alice.execution_scope.scope_id).symlink_to(bob.projects_root)
    with pytest.raises(PathPolicyError):
        alice.ensure_layout()


def test_landlock_scoped_worker_cannot_write_foreign_data_or_shared_models(workspace):
    from easydesign.runtime_guard import landlock_abi_version

    try:
        landlock_abi_version()
    except OSError:
        pytest.skip("Host cannot run the Linux Landlock integration check")
    alice, bob = scope(workspace, "a"), scope(workspace, "b")
    alice.ensure_layout()
    bob.ensure_layout()
    models = workspace.runtime_root / "models"
    models.mkdir()
    model = models / "fixture-model"
    model.write_text("immutable fixture")
    env = alice.subprocess_environment()
    code = """
import os,sys
from pathlib import Path
from easydesign.runtime_guard import apply_local_write_sandbox
roots=[Path(p) for p in os.environ['EASYDESIGN_LOCAL_WRITE_ROOTS'].split(os.pathsep)]
apply_local_write_sandbox(roots)
Path(sys.argv[1]).write_text('owned')
for path in sys.argv[2:]:
    try:
        Path(path).write_text('forbidden')
    except PermissionError:
        continue
    raise AssertionError('cross-scope write was allowed')
"""
    subprocess.run(
        [
            sys.executable,
            "-B",
            "-c",
            code,
            str(alice.projects_root / "owned"),
            str(bob.projects_root / "foreign"),
            str(model),
        ],
        cwd=workspace.root,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    assert model.read_text() == "immutable fixture"
    assert not (bob.projects_root / "foreign").exists()
