from __future__ import annotations

from pathlib import Path

import pytest

from easydesign.core import ConfigurationError
from easydesign.orchestration import (
    LoadedPseRunConfig,
    LoadedSequenceRunConfig,
    initialize_project,
    load_run_config,
)


def test_initialize_sequence_project_materializes_explicit_defaults(tmp_path: Path) -> None:
    fasta = tmp_path / "apoe.fasta"
    fasta.write_text(">apoe\nACDEFGHIKLMNPQRSTVWY\n", encoding="utf-8")

    initialized = initialize_project(
        project_root=tmp_path / "apoe-project",
        target=fasta,
        stop_after_stage=2,
    )
    loaded = load_run_config(initialized.config_path)

    assert isinstance(loaded, LoadedSequenceRunConfig)
    assert loaded.config.structure_prediction is not None
    assert loaded.config.structure_prediction.msa.no_msa_fallback is False
    assert loaded.config.stage02 is not None
    assert loaded.config.stage02.automatic is not None
    assert loaded.config.stage02.automatic.patch.target_member_count == 12
    config_text = initialized.config_path.read_text(encoding="utf-8")
    assert config_text.startswith("schema_version: '0.3'")
    assert all(f"stage0{number}:" in config_text for number in range(1, 8))
    assert "stage03: null" in config_text
    assert initialized.target_path.read_bytes() == fasta.read_bytes()
    assert (initialized.project_root / ".gitignore").read_text() == "runs/\n"


def test_initialize_pse_project_omits_prediction(tmp_path: Path) -> None:
    pse = tmp_path / "target.pse"
    pse.write_bytes(b"synthetic-pse")

    initialized = initialize_project(
        project_root=tmp_path / "pse-project",
        target=pse,
        stop_after_stage=1,
    )
    loaded = load_run_config(initialized.config_path)

    assert isinstance(loaded, LoadedPseRunConfig)
    assert loaded.config.structure_prediction is None


def test_initialize_project_refuses_nonempty_destination(tmp_path: Path) -> None:
    fasta = tmp_path / "target.fasta"
    fasta.write_text(">target\nACDEFGHIKLMNPQRSTVWY\n", encoding="utf-8")
    destination = tmp_path / "existing"
    destination.mkdir()
    (destination / "keep.txt").write_text("keep", encoding="utf-8")

    with pytest.raises(ConfigurationError, match="非空"):
        initialize_project(project_root=destination, target=fasta)

    assert (destination / "keep.txt").read_text() == "keep"
