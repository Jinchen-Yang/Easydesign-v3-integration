from __future__ import annotations

from pathlib import Path

import pytest

from easydesign.core import ConfigurationError, TargetInputError
from easydesign.orchestration import (
    TargetInputFormat,
    detect_target_input_format,
    load_run_config,
)

ROOT = Path(__file__).resolve().parents[3]
APOE_INPUT = ROOT / "examples/stage01-apoe/input"
APOE_SHA256 = "7cfb40e9e78b05724e328df0af5ca673f4379ab7011b7655a2922f494668115a"


def test_apoe_user_yaml_resolves_sequence_and_prediction_request() -> None:
    loaded = load_run_config(APOE_INPUT / "easydesign.yaml")

    assert loaded.detected_format is TargetInputFormat.FASTA
    assert loaded.target.length == 143
    assert loaded.target.sequence_sha256 == APOE_SHA256
    assert loaded.prediction_request.job_name == "apoe4-fragment-41-183"
    assert loaded.prediction_request.msa_mode == "disabled"
    assert loaded.prediction_request.template_mode == "disabled"
    assert loaded.prediction_request.cycle_count == 1
    assert loaded.config.workflow.stop_after_stage == 1


def test_auto_detection_supports_content_based_raw_sequence(tmp_path: Path) -> None:
    source = tmp_path / "target.txt"
    source.write_text(" acd\nefghik \n", encoding="utf-8")

    assert detect_target_input_format(source) is TargetInputFormat.SEQUENCE


def test_auto_detection_recognizes_future_structure_without_fallback(
    tmp_path: Path,
) -> None:
    source = tmp_path / "target.cif"
    source.write_text("data_target\n#\n", encoding="utf-8")
    config = tmp_path / "easydesign.yaml"
    config.write_text(
        """
schema_version: "0.1"
project_id: demo
target:
  id: demo
  source: target.cif
  format: auto
structure_prediction:
  backend: protenix-v2
  msa_mode: disabled
  template_mode: disabled
""".lstrip(),
        encoding="utf-8",
    )

    with pytest.raises(TargetInputError, match="format=mmcif.*尚未实现"):
        load_run_config(config)


def test_unknown_target_format_requires_explicit_declaration(tmp_path: Path) -> None:
    source = tmp_path / "target.unknown"
    source.write_text("this is not a protein sequence\n", encoding="utf-8")

    with pytest.raises(TargetInputError, match="无法自动识别"):
        detect_target_input_format(source)


def test_yaml_rejects_unknown_or_missing_scientific_controls(tmp_path: Path) -> None:
    source = tmp_path / "target.fasta"
    source.write_text(">target\nACDE\n", encoding="utf-8")
    config = tmp_path / "easydesign.yaml"
    config.write_text(
        """
schema_version: "0.1"
project_id: demo
target:
  id: demo
  source: target.fasta
structure_prediction:
  backend: protenix-v2
  template_mode: disabled
  silent_fallback: true
""".lstrip(),
        encoding="utf-8",
    )

    with pytest.raises(ConfigurationError, match="msa_mode|extra"):
        load_run_config(config)
