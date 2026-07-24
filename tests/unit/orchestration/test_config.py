from __future__ import annotations

from pathlib import Path

import pytest

from easydesign.core import ConfigurationError, TargetInputError
from easydesign.orchestration import (
    LoadedPseRunConfig,
    LoadedSequenceRunConfig,
    RegionProposalMode,
    TargetInputFormat,
    detect_target_input_format,
    load_run_config,
)

ROOT = Path(__file__).resolve().parents[3]
APOE_INPUT = ROOT / "examples/stage01-apoe/input"
APOE_SHA256 = "7cfb40e9e78b05724e328df0af5ca673f4379ab7011b7655a2922f494668115a"


def test_apoe_user_yaml_resolves_sequence_and_prediction_request() -> None:
    loaded = load_run_config(APOE_INPUT / "easydesign.yaml")

    assert isinstance(loaded, LoadedSequenceRunConfig)
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


def test_pse_yaml_selects_import_branch_without_prediction(tmp_path: Path) -> None:
    source = tmp_path / "target.pse"
    source.write_bytes(b"runtime-only-pse-placeholder")
    config = tmp_path / "easydesign.yaml"
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

    loaded = load_run_config(config)

    assert isinstance(loaded, LoadedPseRunConfig)
    assert loaded.detected_format is TargetInputFormat.PSE
    assert loaded.source_path == source
    assert loaded.config.structure_prediction is None


def test_pse_yaml_rejects_structure_prediction(tmp_path: Path) -> None:
    source = tmp_path / "target.pse"
    source.write_bytes(b"runtime-only-pse-placeholder")
    config = tmp_path / "easydesign.yaml"
    config.write_text(
        """
schema_version: "0.1"
project_id: demo
target:
  id: demo-pse
  source: target.pse
structure_prediction:
  backend: protenix-v2
  msa_mode: disabled
  template_mode: disabled
""".lstrip(),
        encoding="utf-8",
    )

    with pytest.raises(ConfigurationError, match="必须省略 structure_prediction"):
        load_run_config(config)


def test_stage02_automatic_config_is_explicit_and_no_msa(tmp_path: Path) -> None:
    source = tmp_path / "target.pse"
    source.write_bytes(b"runtime-only-pse-placeholder")
    config = tmp_path / "easydesign.yaml"
    config.write_text(
        """
schema_version: "0.1"
project_id: demo
target:
  id: demo-pse
  source: target.pse
workflow:
  stop_after_stage: 2
stage02:
  mode: automatic
  automatic:
    region_count: 3
    evidence:
      scannet_mode: epitope
      use_msa: false
""".lstrip(),
        encoding="utf-8",
    )

    loaded = load_run_config(config)

    assert isinstance(loaded, LoadedPseRunConfig)
    assert loaded.config.stage02 is not None
    assert loaded.config.stage02.mode is RegionProposalMode.AUTOMATIC
    assert loaded.config.stage02.automatic is not None
    assert loaded.config.stage02.automatic.patch.target_member_count == 12


def test_stage02_requested_without_config_fails(tmp_path: Path) -> None:
    source = tmp_path / "target.pse"
    source.write_bytes(b"runtime-only-pse-placeholder")
    config = tmp_path / "easydesign.yaml"
    config.write_text(
        """
schema_version: "0.1"
project_id: demo
target:
  id: demo-pse
  source: target.pse
workflow:
  stop_after_stage: 2
""".lstrip(),
        encoding="utf-8",
    )

    with pytest.raises(ConfigurationError, match="必须显式提供 stage02"):
        load_run_config(config)


def test_stage02_unimplemented_mode_requires_no_automatic_payload(tmp_path: Path) -> None:
    source = tmp_path / "target.pse"
    source.write_bytes(b"runtime-only-pse-placeholder")
    config = tmp_path / "easydesign.yaml"
    config.write_text(
        """
schema_version: "0.1"
project_id: demo
target:
  id: demo-pse
  source: target.pse
workflow:
  stop_after_stage: 2
stage02:
  mode: manual
  automatic: null
""".lstrip(),
        encoding="utf-8",
    )

    loaded = load_run_config(config)

    assert isinstance(loaded, LoadedPseRunConfig)
    assert loaded.config.stage02 is not None
    assert loaded.config.stage02.mode is RegionProposalMode.MANUAL


def test_sequence_yaml_requires_structure_prediction(tmp_path: Path) -> None:
    source = tmp_path / "target.fasta"
    source.write_text(">target\nACDEFGHIKLMNPQRSTVWY\n", encoding="utf-8")
    config = tmp_path / "easydesign.yaml"
    config.write_text(
        """
schema_version: "0.1"
project_id: demo
target:
  id: demo-sequence
  source: target.fasta
""".lstrip(),
        encoding="utf-8",
    )

    with pytest.raises(ConfigurationError, match="必须显式提供 structure_prediction"):
        load_run_config(config)
