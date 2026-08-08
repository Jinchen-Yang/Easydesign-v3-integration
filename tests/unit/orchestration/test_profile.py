from __future__ import annotations

from pathlib import Path

import pytest

from easydesign.core import ConfigurationError
from easydesign.orchestration import initialize_runtime_profile, load_runtime_profile


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


def test_runtime_profile_rejects_remote_executor_fields(tmp_path: Path) -> None:
    profile = tmp_path / "profile.yaml"
    profile.write_text(
        f"""
schema_version: "0.1"
profile_id: controller
runs_root: {(tmp_path / 'workspace/runs').resolve()}
remote_executors:
  forbidden: {{host: 192.0.2.10}}
""".lstrip(),
        encoding="utf-8",
    )
    with pytest.raises(ConfigurationError, match="extra_forbidden"):
        load_runtime_profile(profile)
