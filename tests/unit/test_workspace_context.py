from __future__ import annotations

import os
from pathlib import Path

import pytest
import yaml

from easydesign.core import PathPolicyError
from easydesign.workspace_context import WorkspaceContext


def _workspace(tmp_path: Path) -> WorkspaceContext:
    (tmp_path / "easydesign-workspace.yaml").write_text(
        yaml.safe_dump(
            {
                "schema_version": "0.1",
                "workspace_id": "test-workspace",
                "runtime_root": "runtime",
                "projects_root": "projects",
                "runs_root": "runs",
                "archives_root": "archives",
            }
        ),
        encoding="utf-8",
    )
    return WorkspaceContext.from_root(tmp_path)


def test_child_environment_is_repository_local_and_does_not_mutate_parent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _workspace(tmp_path)
    original_home = os.environ.get("HOME")
    monkeypatch.setenv("HTTPS_PROXY", "http://user-owned-proxy.invalid:7898")

    child_overrides = context.child_environment()
    child = {**os.environ, **child_overrides}

    assert os.environ.get("HOME") == original_home
    assert os.environ["HTTPS_PROXY"] == "http://user-owned-proxy.invalid:7898"
    for key in (
        "HOME",
        "TMPDIR",
        "CONDA_PKGS_DIRS",
        "PIP_CACHE_DIR",
        "XDG_CACHE_HOME",
        "COREPACK_HOME",
        "PLAYWRIGHT_BROWSERS_PATH",
    ):
        Path(child[key]).resolve().relative_to(context.runtime_root)
    assert Path(child["GIT_CONFIG_GLOBAL"]).is_relative_to(context.runtime_root)
    git_config = Path(child["GIT_CONFIG_GLOBAL"]).read_text(encoding="utf-8")
    assert "[safe]" in git_config
    assert "[include]" not in git_config
    assert "proxy" not in git_config.lower()
    assert child["PIP_CONFIG_FILE"] == os.devnull
    assert child["PIP_INDEX_URL"] == "https://pypi.org/simple"
    assert child["PYTHONNOUSERSITE"] == "1"
    assert child["HTTPS_PROXY"] == "http://user-owned-proxy.invalid:7898"
    assert "HTTPS_PROXY" not in child_overrides
    assert child.get("NODE_EXTRA_CA_CERTS") in {
        None,
        "/etc/ssl/certs/ca-certificates.crt",
    }


def test_write_boundary_rejects_external_path(tmp_path: Path) -> None:
    context = _workspace(tmp_path)

    with pytest.raises(PathPolicyError, match="工作区外"):
        context.assert_write_path(tmp_path.parent / "external-output")


def test_quarantine_moves_without_destroying_bytes(tmp_path: Path) -> None:
    context = _workspace(tmp_path)
    context.ensure_layout()
    staging = context.runtime_root / "tmp" / "partial-download.bin"
    payload = b"preserve-this-failed-download"
    staging.write_bytes(payload)

    quarantine = context.quarantine(
        staging,
        operation="unit-test",
        reason="intentional fixture",
    )

    moved = quarantine / staging.name
    assert moved.read_bytes() == payload
    assert (quarantine / "quarantine.yaml").is_file()
    assert not staging.exists()
