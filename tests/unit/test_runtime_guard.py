from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from easydesign.runtime_guard import (
    LOCAL_WRITE_ROOTS_ENV,
    READ_ONLY_RUNTIME_ENV,
    install_python_startup_guard,
    landlock_abi_version,
)
from easydesign.workspace_context import WorkspaceContext


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="Landlock is Linux-only")
def test_worker_landlock_allows_local_write_and_denies_shared_runtime(
    tmp_path: Path,
) -> None:
    local = tmp_path / "local"
    shared = tmp_path / "shared"
    local.mkdir()
    shared.mkdir()
    script = """
from pathlib import Path
from easydesign.runtime_guard import apply_local_write_sandbox
apply_local_write_sandbox((Path({local!r}),))
Path({allowed!r}).write_text("local")
try:
    Path({denied!r}).write_text("forbidden")
except PermissionError:
    raise SystemExit(0)
raise SystemExit(3)
""".format(
        local=str(local),
        allowed=str(local / "allowed.txt"),
        denied=str(shared / "denied.txt"),
    )
    completed = subprocess.run(
        [sys.executable, "-c", script],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    assert (local / "allowed.txt").read_text(encoding="utf-8") == "local"
    assert not (shared / "denied.txt").exists()


def test_linked_profile_installs_python_probe_guard(tmp_path: Path) -> None:
    shared = tmp_path / "shared-runtime"
    shared.mkdir()
    root = tmp_path / "checkout"
    root.mkdir()
    (root / "easydesign-workspace.yaml").write_text(
        'schema_version: "0.1"\nworkspace_id: guard-test\n', encoding="utf-8"
    )
    (root / "runtime").mkdir()
    (root / "runtime/profile.yaml").write_text(
        "\n".join(
            (
                'schema_version: "0.1"',
                "profile_id: guard-test",
                f"runs_root: {root / 'workspace/runs'}",
                f"runtime_link_source: {shared}",
                "backends: {}",
                "",
            )
        ),
        encoding="utf-8",
    )
    context = WorkspaceContext.from_root(root)
    environment = context.child_environment()

    assert environment[READ_ONLY_RUNTIME_ENV] == str(shared)
    assert environment[LOCAL_WRITE_ROOTS_ENV].split(os.pathsep) == [
        str(context.runtime_root),
        str(context.projects_root),
        str(context.runs_root),
        str(context.archives_root),
    ]
    assert Path(environment["PYTHONPATH"]).joinpath("sitecustomize.py").is_file()
    assert Path(environment["TORCH_EXTENSIONS_DIR"]).is_dir()

    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            "import os,sys; sys.exit(0 if not os.access(sys.argv[1], os.W_OK) else 4)",
            str(shared),
        ],
        check=False,
        env={**os.environ, **environment},
    )
    assert completed.returncode == 0


def test_python_startup_guard_is_content_addressed(tmp_path: Path) -> None:
    first = install_python_startup_guard(tmp_path)
    second = install_python_startup_guard(tmp_path)
    assert first == second
    assert (first / "sitecustomize.py").is_file()


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="Landlock is Linux-only")
def test_python_guard_preserves_cross_directory_atomic_file_publish(
    tmp_path: Path,
) -> None:
    local = tmp_path / "local"
    source = local / "temporary/payload.bin"
    target = local / "cache/payload.bin"
    source.parent.mkdir(parents=True)
    target.parent.mkdir(parents=True)
    source.write_bytes(b"verified-cache")
    startup = install_python_startup_guard(tmp_path / "state")
    script = f"""
import os
from pathlib import Path
from easydesign.runtime_guard import apply_local_write_sandbox
apply_local_write_sandbox((Path({str(local)!r}),))
os.replace({str(source)!r}, {str(target)!r})
"""
    environment = {
        **os.environ,
        READ_ONLY_RUNTIME_ENV: str(tmp_path / "unused-shared-runtime"),
        LOCAL_WRITE_ROOTS_ENV: str(local),
        "PYTHONPATH": str(startup),
    }
    (tmp_path / "unused-shared-runtime").mkdir()
    completed = subprocess.run(
        [sys.executable, "-c", script],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )
    assert completed.returncode == 0, completed.stderr
    assert target.read_bytes() == b"verified-cache"
    assert not source.exists()


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="Landlock is Linux-only")
def test_landlock_abi_is_available() -> None:
    assert landlock_abi_version() >= 1
