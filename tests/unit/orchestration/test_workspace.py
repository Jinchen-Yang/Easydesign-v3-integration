from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from easydesign.backends.structure_prediction import ProtenixV2Adapter
from easydesign.backends.target_sources import PyMOLPseAdapter
from easydesign.core import (
    CodeIdentity,
    CodeIdentitySource,
    ManifestStateError,
    RunManifest,
    RuntimeProfileRef,
    StageId,
    load_model,
)
from easydesign.orchestration import (
    ResolvedRunConfig,
    RunIndex,
    initialize_pse_run,
    initialize_sequence_run,
)

ROOT = Path(__file__).resolve().parents[3]
APOE_CONFIG = ROOT / "examples/stage01-apoe/input/easydesign.yaml"


def adapter() -> ProtenixV2Adapter:
    return ProtenixV2Adapter(
        executable=Path("/envs/protenix-v2/bin/protenix"),
        model_root=Path("/models/protenix"),
    )


def test_initialize_sequence_run_creates_one_shallow_workspace(tmp_path: Path) -> None:
    prepared = initialize_sequence_run(
        config_path=APOE_CONFIG,
        runs_root=tmp_path / "runs",
        input_writer=adapter(),
        code_commit="d1b46f9",
        easydesign_version="0.1.0.dev0",
        run_id="20260724-001",
        created_at=datetime(2026, 7, 24, 8, 0, tzinfo=UTC),
    )
    workspace = prepared.workspace

    assert workspace.run_root == tmp_path / "runs/apoe/20260724-001"
    assert workspace.config_snapshot.is_file()
    assert workspace.input_snapshot.is_file()
    assert workspace.resolved_config.is_file()
    assert all(workspace.stage_root(stage).is_dir() for stage in StageId)
    assert (workspace.run_root / "results").is_dir()
    assert prepared.protenix_input == (
        workspace.run_root
        / "01-target-preparation/attempt-0001/inputs/protenix-input.json"
    )
    assert prepared.protenix_input.is_file()
    assert not (workspace.run_root / "01-target-preparation/attempts").exists()

    protenix = json.loads(prepared.protenix_input.read_text(encoding="utf-8"))
    assert protenix[0]["name"] == "apoe4-fragment-41-183"
    assert len(protenix[0]["sequences"][0]["proteinChain"]["sequence"]) == 143

    manifest = load_model(workspace.run_manifest, RunManifest)
    assert manifest.project_id == "apoe"
    assert manifest.run_id == "20260724-001"
    assert manifest.config_snapshot.verify(workspace.run_root) == workspace.config_snapshot
    resolved = load_model(workspace.resolved_config, ResolvedRunConfig)
    assert resolved.schema_version == "0.3"
    assert resolved.prediction_request is not None
    assert resolved.prediction_request.msa_mode == "remote"
    assert len(resolved.msa_execution_plan) == 1
    assert resolved.msa_execution_plan[0].endpoint == "https://api.colabfold.com"

    index = load_model(tmp_path / "runs/run-index.json", RunIndex)
    assert index.entries[0].path == "apoe/20260724-001"


def test_initialize_sequence_run_refuses_existing_run(tmp_path: Path) -> None:
    kwargs = {
        "config_path": APOE_CONFIG,
        "runs_root": tmp_path / "runs",
        "input_writer": adapter(),
        "code_commit": "d1b46f9",
        "easydesign_version": "0.1.0.dev0",
        "run_id": "20260724-001",
        "created_at": datetime(2026, 7, 24, 8, 0, tzinfo=UTC),
    }
    initialize_sequence_run(**kwargs)

    with pytest.raises(ManifestStateError, match="不能覆盖"):
        initialize_sequence_run(**kwargs)


def test_initialize_workspace_uses_manifest_12_for_packaged_execution(
    tmp_path: Path,
) -> None:
    identity = CodeIdentity(
        version="0.1.0.dev1",
        source=CodeIdentitySource.INSTALLED_PACKAGE,
        dirty=False,
        content_sha256="a" * 64,
    )
    profile = RuntimeProfileRef(profile_id="test-local", sha256="b" * 64)
    prepared = initialize_sequence_run(
        config_path=APOE_CONFIG,
        runs_root=tmp_path / "runs",
        input_writer=adapter(),
        easydesign_version="0.1.0.dev1",
        code_identity=identity,
        runtime_profile=profile,
        run_id="run-packaged",
        created_at=datetime(2026, 7, 25, 8, 0, tzinfo=UTC),
    )

    manifest = load_model(prepared.workspace.run_manifest, RunManifest)
    resolved = load_model(prepared.workspace.resolved_config, ResolvedRunConfig)
    assert manifest.schema_version == "1.2"
    assert manifest.code_identity == identity
    assert manifest.runtime_profile == profile
    assert resolved.schema_version == "0.4"
    assert resolved.runtime_profile == profile


def test_initialize_pse_run_creates_request_without_prediction(tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    pse = input_dir / "target.pse"
    pse.write_bytes(b"synthetic-pse")
    config = input_dir / "easydesign.yaml"
    config.write_text(
        """
schema_version: "0.1"
project_id: demo
target:
  id: demo-pse
  source: target.pse
  format: auto
workflow:
  stop_after_stage: 1
""".lstrip(),
        encoding="utf-8",
    )
    pymol = PyMOLPseAdapter(
        python_executable=Path("/envs/pymol-pse/bin/python")
    )

    prepared = initialize_pse_run(
        config_path=config,
        runs_root=tmp_path / "runs",
        request_writer=pymol,
        code_commit="428e98f",
        easydesign_version="0.1.0.dev0",
        run_id="20260724-002-stage01-pse",
        created_at=datetime(2026, 7, 24, 9, 0, tzinfo=UTC),
    )

    request = json.loads(prepared.pse_request.read_text(encoding="utf-8"))
    assert request["source_relative_path"] == "input-snapshot/target.pse"
    assert request["target_id"] == "demo-pse"
    assert prepared.pse_request.name == "pse-request.json"
    assert not list(prepared.workspace.run_root.rglob("protenix-input.json"))
    resolved = load_model(prepared.workspace.resolved_config, ResolvedRunConfig)
    assert resolved.detected_input_format == "pse"
    assert resolved.target is None
    assert resolved.prediction_request is None
    assert prepared.workspace.latest_manifest_pointer.read_text() == (
        "run-manifest.v0001.json\n"
    )
