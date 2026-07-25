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
from easydesign.orchestration.config import migrate_run_config

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
    assert loaded.prediction_request.msa_mode == "remote"
    assert loaded.prediction_request.template_mode == "disabled"
    assert loaded.prediction_request.cycle_count is None
    assert len(loaded.msa_execution_plan) == 1
    assert loaded.msa_execution_plan[0].provider == "colabfold-public"
    assert loaded.msa_execution_plan[0].endpoint == "https://api.colabfold.com"
    assert loaded.msa_execution_plan[0].server_mode == "colabfold"
    assert loaded.msa_execution_plan[0].max_attempts == 3
    assert loaded.config.structure_prediction is not None
    assert loaded.config.structure_prediction.prediction_timeout_seconds == 7200
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
  msa:
    mode: remote
    providers:
      - provider: colabfold-public
  template_mode: disabled
workflow:
  stop_after_stage: 1
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
  msa:
    mode: remote
    providers:
      - provider: colabfold-public
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


def test_sequence_yaml_forbids_no_msa_fallback(tmp_path: Path) -> None:
    source = tmp_path / "target.fasta"
    source.write_text(">target\nACDEFGHIKLMNPQRSTVWY\n", encoding="utf-8")
    config = tmp_path / "easydesign.yaml"
    config.write_text(
        """
schema_version: "0.2"
project_id: demo
target:
  id: demo-sequence
  source: target.fasta
structure_prediction:
  backend: protenix-v2
  msa:
    mode: disabled
    providers:
      - provider: colabfold-public
    no_msa_fallback: true
  template_mode: disabled
""".lstrip(),
        encoding="utf-8",
    )

    with pytest.raises(ConfigurationError, match="mode=remote|no-MSA"):
        load_run_config(config)


def test_sequence_yaml_resolves_explicit_provider_fallback_order(
    tmp_path: Path,
) -> None:
    source = tmp_path / "target.fasta"
    source.write_text(">target\nACDEFGHIKLMNPQRSTVWY\n", encoding="utf-8")
    config = tmp_path / "easydesign.yaml"
    config.write_text(
        """
schema_version: "0.2"
project_id: demo
target:
  id: demo-sequence
  source: target.fasta
structure_prediction:
  backend: protenix-v2
  msa:
    mode: remote
    providers:
      - provider: colabfold-public
        timeout_seconds: 900
        max_attempts: 2
      - provider: custom-colabfold
        endpoint: https://msa.example.org/api
        timeout_seconds: 1200
        max_attempts: 1
    no_msa_fallback: false
  template_mode: disabled
workflow:
  stop_after_stage: 1
""".lstrip(),
        encoding="utf-8",
    )

    loaded = load_run_config(config)

    assert isinstance(loaded, LoadedSequenceRunConfig)
    assert [item.provider for item in loaded.msa_execution_plan] == [
        "colabfold-public",
        "custom-colabfold",
    ]
    assert loaded.msa_execution_plan[1].endpoint == "https://msa.example.org/api"
    assert loaded.msa_execution_plan[1].server_mode == "colabfold"


def test_sequence_yaml_rejects_duplicate_msa_providers(tmp_path: Path) -> None:
    source = tmp_path / "target.fasta"
    source.write_text(">target\nACDEFGHIKLMNPQRSTVWY\n", encoding="utf-8")
    config = tmp_path / "easydesign.yaml"
    config.write_text(
        """
schema_version: "0.2"
project_id: demo
target:
  id: demo-sequence
  source: target.fasta
structure_prediction:
  backend: protenix-v2
  msa:
    mode: remote
    providers:
      - provider: colabfold-public
      - provider: colabfold-public
  template_mode: disabled
""".lstrip(),
        encoding="utf-8",
    )

    with pytest.raises(ConfigurationError, match="providers 不能重复"):
        load_run_config(config)


def test_canonical_03_exposes_all_seven_stage_keys_and_optional_identity(
    tmp_path: Path,
) -> None:
    source = tmp_path / "target.pse"
    source.write_bytes(b"runtime-only-pse-placeholder")
    config = tmp_path / "easydesign.yaml"
    config.write_text(
        """
schema_version: "0.3"
project_id: demo
design:
  binder_profile: vhh
  intent: blocking
workflow:
  stop_after_stage: 2
stage01:
  target:
    id: demo-pse
    source: target.pse
    format: auto
    identity:
      uniprot_accession: null
  structure_prediction: null
stage02:
  mode: automatic
  methods: [sasa]
  annotations:
    uniprot: if_available
  automatic:
    requested_region_count: 3
    minimum_region_count: 2
    sasa:
      ensemble_consensus_fraction: 0.70
    patch:
      target_member_count: 12
      minimum_member_count: 5
stage03: null
stage04: null
stage05: null
stage06: null
stage07: null
""".lstrip(),
        encoding="utf-8",
    )

    loaded = load_run_config(config)

    assert isinstance(loaded, LoadedPseRunConfig)
    assert loaded.config.schema_version == "0.3"
    assert loaded.config.stage01.target.identity.uniprot_accession is None
    assert loaded.config.stage02 is not None
    assert loaded.config.stage02.methods == ("sasa",)
    assert loaded.config.stage03 is None
    assert loaded.config.stage07 is None


def test_non_null_future_stage_is_rejected_as_not_implemented(
    tmp_path: Path,
) -> None:
    source = tmp_path / "target.pse"
    source.write_bytes(b"runtime-only-pse-placeholder")
    config = tmp_path / "easydesign.yaml"
    config.write_text(
        """
schema_version: "0.3"
project_id: demo
workflow:
  stop_after_stage: 1
stage01:
  target:
    id: demo
    source: target.pse
  structure_prediction: null
stage02: null
stage03:
  arbitrary: value
stage04: null
stage05: null
stage06: null
stage07: null
""".lstrip(),
        encoding="utf-8",
    )

    with pytest.raises(ConfigurationError, match="stage03|none_required"):
        load_run_config(config)


def test_config_migrate_writes_canonical_03_without_overwriting(
    tmp_path: Path,
) -> None:
    source = tmp_path / "target.pse"
    source.write_bytes(b"runtime-only-pse-placeholder")
    old = tmp_path / "old.yaml"
    old.write_text(
        """
schema_version: "0.1"
project_id: demo
target:
  id: demo
  source: target.pse
workflow:
  stop_after_stage: 1
""".lstrip(),
        encoding="utf-8",
    )
    migrated = tmp_path / "nested/new.yaml"

    migrate_run_config(old, migrated)
    loaded = load_run_config(migrated)

    assert loaded.config.schema_version == "0.3"
    assert loaded.config.stage01.target.target_id == "demo"
    text = migrated.read_text(encoding="utf-8")
    assert "stage01:" in text
    assert "stage07: null" in text
    assert old.read_text(encoding="utf-8").startswith('schema_version: "0.1"')
    with pytest.raises(ConfigurationError, match="禁止覆盖"):
        migrate_run_config(old, migrated)
