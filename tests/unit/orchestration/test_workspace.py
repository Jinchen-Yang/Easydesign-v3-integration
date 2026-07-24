from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from easydesign.backends.structure_prediction import ProtenixV2Adapter
from easydesign.core import ManifestStateError, RunManifest, StageId, load_model
from easydesign.orchestration import RunIndex, initialize_sequence_run

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
