from __future__ import annotations

import os
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from easydesign.core import ConfigurationError, PathPolicyError
from easydesign.execution_scope import ExecutionScope, load_scope
from easydesign.workspace_context import WorkspaceContext


def workspace(tmp_path: Path) -> WorkspaceContext:
    (tmp_path / "easydesign-workspace.yaml").write_text('schema_version: "0.1"\n')
    return WorkspaceContext.from_root(tmp_path)


def identity() -> ExecutionScope:
    return ExecutionScope(scope_id="user-" + "a" * 32, actor_id="user-" + "a" * 32)


def test_repeated_layout_resolves_each_validated_root_once(tmp_path, monkeypatch):
    scoped = workspace(tmp_path).with_execution_scope(identity())
    scoped.ensure_layout()
    original = Path.resolve
    calls = []

    def resolve(path, *args, **kwargs):
        calls.append(path)
        return original(path, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(Path, "resolve", resolve)
        scoped.ensure_layout()

    # Four declared roots, each with both declaration and scoped symlink checks.
    assert len(calls) == 8
    for root in (scoped.runtime_root, scoped.projects_root, scoped.runs_root, scoped.archives_root):
        assert root.is_dir()
    for name in ("cache", "state", "logs", "tmp", "validation", "quarantine", "home"):
        assert (scoped.runtime_root / name).is_dir()


def test_republishing_verified_scope_is_read_only(tmp_path, monkeypatch):
    base = workspace(tmp_path)
    first = base.with_execution_scope(identity())
    path = first.execution_scope_path
    assert path is not None
    before = path.stat()
    operations = []

    def observe(owner, name):
        original = getattr(owner, name)

        def call(*args, **kwargs):
            operations.append(name)
            return original(*args, **kwargs)

        monkeypatch.setattr(owner, name, call)

    observe(Path, "mkdir")
    observe(tempfile, "mkstemp")
    observe(os, "fsync")
    second = base.with_execution_scope(identity())

    assert second.execution_scope_path == path
    assert second.execution_scope == first.execution_scope
    assert operations == []
    after = path.stat()
    assert (after.st_ino, after.st_mtime_ns, after.st_mode) == (
        before.st_ino,
        before.st_mtime_ns,
        before.st_mode,
    )


@pytest.mark.parametrize("root_name", ["runtime", "projects", "runs", "archives"])
def test_layout_revalidates_all_roots_before_any_mkdir(tmp_path, monkeypatch, root_name):
    directory = tmp_path / "workspace"
    directory.mkdir()
    scoped = workspace(directory).with_execution_scope(identity())
    scoped.ensure_layout()
    root = getattr(scoped, root_name + "_root")
    root.rename(root.with_name(root.name + "-original"))
    outside = tmp_path / "outside"
    outside.mkdir()
    root.symlink_to(outside, target_is_directory=True)
    calls = []
    original = Path.mkdir

    def mkdir(path, *args, **kwargs):
        calls.append(path)
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "mkdir", mkdir)
    with pytest.raises(PathPolicyError):
        scoped.ensure_layout()
    assert calls == []
    assert list(outside.iterdir()) == []


def test_publish_reloads_declaration_bytes_for_every_call(tmp_path):
    base = workspace(tmp_path)
    first = base.with_execution_scope(identity()).execution_scope_path
    assert first is not None
    original = first.read_bytes()
    base.declaration_path.write_text('schema_version: "0.1"\n# changed declaration bytes\n')

    second = base.with_execution_scope(identity()).execution_scope_path

    assert second is not None and second != first
    assert first.read_bytes() == original
    assert load_scope(
        runtime_root=base.runtime_root, declaration_path=base.declaration_path, path=second
    ) == identity()


def test_publish_rejects_corrupt_existing_record_without_repair(tmp_path):
    base = workspace(tmp_path)
    path = base.with_execution_scope(identity()).execution_scope_path
    assert path is not None
    altered = path.read_bytes() + b"unexpected trailing bytes"
    path.write_bytes(altered)
    before = path.stat()

    with pytest.raises(ConfigurationError, match="identity conflict"):
        base.with_execution_scope(identity())

    assert path.read_bytes() == altered
    after = path.stat()
    assert (after.st_ino, after.st_mtime_ns, after.st_mode) == (
        before.st_ino, before.st_mtime_ns, before.st_mode
    )


def test_publish_rejects_matching_record_symlink_without_following(tmp_path):
    base = workspace(tmp_path)
    path = base.with_execution_scope(identity()).execution_scope_path
    assert path is not None
    target = tmp_path / "same-content-outside-registry"
    path.rename(target)
    contents = target.read_bytes()
    path.symlink_to(target)

    with pytest.raises(PathPolicyError, match="symlinks"):
        base.with_execution_scope(identity())

    assert path.is_symlink()
    assert target.read_bytes() == contents


def test_publish_rechecks_registry_containment_after_earlier_valid_publication(tmp_path):
    directory = tmp_path / "workspace"
    directory.mkdir()
    base = workspace(directory)
    path = base.with_execution_scope(identity()).execution_scope_path
    assert path is not None
    parent = path.parent
    parent.rename(parent.with_name("original-registry"))
    outside = tmp_path / "outside"
    outside.mkdir()
    parent.symlink_to(outside, target_is_directory=True)

    with pytest.raises(PathPolicyError, match="registry escaped"):
        base.with_execution_scope(identity())

    assert parent.is_symlink()
    assert list(outside.iterdir()) == []


def test_concurrent_first_publish_accepts_same_content_and_leaves_no_temporaries(
    tmp_path, monkeypatch
):
    base = workspace(tmp_path)
    barrier = threading.Barrier(8)
    original = tempfile.mkstemp

    def synchronize(*args, **kwargs):
        result = original(*args, **kwargs)
        barrier.wait(timeout=20)
        return result

    monkeypatch.setattr(tempfile, "mkstemp", synchronize)
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(base.with_execution_scope, identity()) for _ in range(8)]
        paths = [future.result(timeout=30).execution_scope_path for future in futures]

    path = paths[0]
    assert path is not None and all(candidate == path for candidate in paths)
    assert load_scope(
        runtime_root=base.runtime_root, declaration_path=base.declaration_path, path=path
    ) == identity()
    assert list(path.parent.iterdir()) == [path]


@pytest.mark.parametrize("collision", ["corrupt", "symlink"])
def test_publish_revalidates_record_that_appears_during_link_race(tmp_path, monkeypatch, collision):
    base = workspace(tmp_path)
    collided = []
    target = tmp_path / "race-target"

    def collide(source, destination):
        path = Path(destination)
        if collision == "corrupt":
            path.write_bytes(b"conflicting record")
        else:
            target.write_bytes(Path(source).read_bytes())
            path.symlink_to(target)
        collided.append(path)
        raise FileExistsError("concurrent publisher")

    monkeypatch.setattr(os, "link", collide)
    error = ConfigurationError if collision == "corrupt" else PathPolicyError
    with pytest.raises(error):
        base.with_execution_scope(identity())
    assert len(collided) == 1
    path = collided[0]
    assert list(path.parent.iterdir()) == [path]
    if collision == "corrupt":
        assert path.read_bytes() == b"conflicting record"
    else:
        assert path.is_symlink()
        assert target.read_bytes() == path.read_bytes()


def test_existing_valid_record_is_accepted_during_link_unlink_window(tmp_path, monkeypatch):
    base = workspace(tmp_path)
    linked = threading.Event()
    release = threading.Event()
    original = os.link
    destinations = []

    def pause_after_link(source, destination):
        original(source, destination)
        destinations.append(Path(destination))
        linked.set()
        assert release.wait(timeout=20)

    monkeypatch.setattr(os, "link", pause_after_link)
    with ThreadPoolExecutor(max_workers=1) as executor:
        publisher = executor.submit(base.with_execution_scope, identity())
        try:
            assert linked.wait(timeout=20)
            path = destinations[0]
            assert path.stat().st_nlink == 2
            second = base.with_execution_scope(identity())
            assert second.execution_scope_path == path
        finally:
            release.set()
        assert publisher.result(timeout=20).execution_scope_path == path
    assert path.stat().st_nlink == 1
    assert list(path.parent.iterdir()) == [path]
