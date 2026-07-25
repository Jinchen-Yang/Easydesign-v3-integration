from __future__ import annotations

from pathlib import Path

import pytest

from easydesign.core import ConfigurationError
from easydesign.orchestration import (
    initialize_runtime_profile,
    load_runtime_profile,
)


def test_runtime_profile_is_exclusive_and_path_identity_is_stable(tmp_path: Path) -> None:
    profile_path = tmp_path / "profile.yaml"
    runs_root = (tmp_path / "runs").resolve()
    created = initialize_runtime_profile(
        profile_path,
        profile_id="test-local",
        runs_root=runs_root,
    )
    loaded = load_runtime_profile(created)

    assert loaded.profile.profile_id == "test-local"
    assert loaded.profile.runs_root == runs_root
    assert loaded.identity.profile_id == "test-local"
    assert len(loaded.identity.sha256) == 64
    with pytest.raises(ConfigurationError, match="禁止覆盖"):
        initialize_runtime_profile(profile_path)


def test_runtime_profile_rejects_relative_backend_paths(tmp_path: Path) -> None:
    profile = tmp_path / "profile.yaml"
    profile.write_text(
        """
schema_version: "0.1"
profile_id: bad
backends:
  pymol_pse:
    python: relative/python
""".lstrip(),
        encoding="utf-8",
    )

    with pytest.raises(ConfigurationError, match="绝对路径"):
        load_runtime_profile(profile)


def test_runtime_profile_accepts_only_explicit_absolute_tnp_paths(tmp_path: Path) -> None:
    profile = tmp_path / "profile.yaml"
    profile.write_text(
        f"""
schema_version: "0.1"
profile_id: tnp-test
backends:
  tnp:
    python: {(tmp_path / "tnp/bin/python").resolve()}
    executable: {(tmp_path / "TNP/bin/TNP").resolve()}
    repository_root: {(tmp_path / "TNP").resolve()}
    timeout_seconds: 7200
    ncores: 8
""".lstrip(),
        encoding="utf-8",
    )

    loaded = load_runtime_profile(profile)

    assert loaded.profile.backends.tnp is not None
    assert loaded.profile.backends.tnp.ncores == 8
    assert loaded.profile.backends.tnp.python.is_absolute()
