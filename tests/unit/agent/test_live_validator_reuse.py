"""Mock backend probe only: reusing a fixture runtime must not overwrite its files."""

import json
from types import SimpleNamespace
from typing import Any

import pytest


def test_live_fixture_reuses_verified_runtime_and_refuses_different_executable(
    bridge: Any, monkeypatch: Any, tmp_path: Any
) -> None:
    from easydesign.backends.boltzgen.check import BoltzGenCheckAdapter
    from easydesign.workspace_context import WorkspaceContext
    from tests.agent_phase2_support import configure_live_validation

    supplied = tmp_path / "supplied-backend"
    supplied.mkdir()
    executable = supplied / "boltzgen"
    executable.write_text("synthetic console entry point")
    source = supplied / "source"
    source.mkdir()
    cache = supplied / "cache"
    cache.mkdir()
    (cache / "mols.zip").write_bytes(b"synthetic dataset; not a real backend")
    config = supplied / "runtime.json"
    config.write_text(
        json.dumps(
            {
                "executable": str(executable),
                "repository_root": str(source),
                "cache_root": str(cache),
            }
        )
    )
    monkeypatch.setenv("EASYDESIGN_AGENT_BOLTZGEN_RUNTIME", str(config))
    monkeypatch.setattr(
        BoltzGenCheckAdapter,
        "probe",
        lambda self: {
            "version": "0.3.2",
            "commit": "synthetic-probe",
            "molecule_dataset_sha256": "fixture",
        },
    )
    monkeypatch.setattr(
        BoltzGenCheckAdapter,
        "artifact_paths",
        lambda self: SimpleNamespace(molecule_dataset=self.cache_root / "mols.zip"),
    )
    configure_live_validation()
    context = WorkspaceContext.discover()
    local = context.runtime_root / "live-boltzgen-validation"
    original = (local / "boltzgen").read_bytes()
    revision = context.profile_path.with_name(context.profile_path.name + ".revisions")
    profile = revision / "revision-000001.yaml"
    before = profile.read_bytes()
    result = configure_live_validation()
    assert result["reused_verified_runtime"] is True
    assert (local / "boltzgen").read_bytes() == original and profile.read_bytes() == before
    executable.write_text("different entry point; not authorized to replace the existing copy")
    with pytest.raises(AssertionError):
        configure_live_validation()
    assert (local / "boltzgen").read_bytes() == original and profile.read_bytes() == before
