from __future__ import annotations

from pathlib import Path

import pytest

from easydesign.core import ConfigurationError
from easydesign.orchestration import (
    initialize_runtime_profile,
    load_runtime_profile,
    runtime_setup,
)
from easydesign.orchestration.runtime_setup import EnvironmentRecord


@pytest.fixture(autouse=True)
def _declare_test_workspace(tmp_path: Path) -> None:
    (tmp_path / "easydesign-workspace.yaml").write_text(
        "\n".join(
            (
                'schema_version: "0.1"',
                "workspace_id: test-workspace",
                "runtime_root: runtime",
                "projects_root: workspace/projects",
                "runs_root: workspace/runs",
                "archives_root: workspace/archives",
                "",
            )
        ),
        encoding="utf-8",
    )


def test_runtime_profile_is_exclusive_and_path_identity_is_stable(
    tmp_path: Path,
) -> None:
    profile_path = tmp_path / "runtime/profile.yaml"
    runs_root = (tmp_path / "workspace/runs").resolve()
    created = initialize_runtime_profile(
        profile_path, profile_id="test-local", runs_root=runs_root
    )
    loaded = load_runtime_profile(created)
    assert loaded.profile.profile_id == "test-local"
    assert loaded.profile.runs_root == runs_root
    assert loaded.profile.backends.protenix_v2 is None
    assert len(loaded.identity.sha256) == 64
    with pytest.raises(ConfigurationError, match="禁止覆盖"):
        initialize_runtime_profile(profile_path)


def test_runtime_profile_rejects_relative_paths(tmp_path: Path) -> None:
    profile = tmp_path / "profile.yaml"
    profile.write_text(
        """
schema_version: "0.1"
profile_id: bad
runs_root: relative/runs
backends:
  pymol_pse:
    python: relative/python
""".lstrip(),
        encoding="utf-8",
    )
    with pytest.raises(ConfigurationError, match="绝对路径"):
        load_runtime_profile(profile)


def test_runtime_profile_rejects_unexpected_fields(tmp_path: Path) -> None:
    profile = tmp_path / "profile.yaml"
    profile.write_text(
        f"""
schema_version: "0.1"
profile_id: invalid-extra-field
runs_root: {(tmp_path / 'workspace/runs').resolve()}
unexpected_scheduler:
  mode: forbidden
""".lstrip(),
        encoding="utf-8",
    )
    with pytest.raises(ConfigurationError, match="extra_forbidden"):
        load_runtime_profile(profile)


def test_runtime_profile_resolves_current_local_component_registry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    profile_path = initialize_runtime_profile(
        tmp_path / "runtime/profile.yaml",
        profile_id="fresh-clone",
        runs_root=(tmp_path / "workspace/runs").resolve(),
    )
    prefix = tmp_path / "runtime/envs/pymol-pse-lock123"
    python = prefix / "bin/python"
    python.parent.mkdir(parents=True)
    python.write_text("", encoding="utf-8")
    record = EnvironmentRecord(
        environment_id="pymol-pse",
        lock_sha256="a" * 64,
        relative_prefix=prefix.relative_to(tmp_path),
        status="available",
        probe_command=(str(python), "--version"),
        recorded_at="2026-08-10T00:00:00Z",
    )
    monkeypatch.setattr(
        runtime_setup,
        "latest_environment_records",
        lambda _context: {"pymol-pse": record},
    )
    monkeypatch.setattr(runtime_setup, "latest_asset_records", lambda _context: {})
    monkeypatch.setattr(
        runtime_setup,
        "expected_environment_lock_sha256",
        lambda _context, _environment_id: "a" * 64,
    )

    loaded = load_runtime_profile(profile_path)

    assert loaded.profile.backends.pymol_pse is not None
    assert loaded.profile.backends.pymol_pse.python == python.resolve()
