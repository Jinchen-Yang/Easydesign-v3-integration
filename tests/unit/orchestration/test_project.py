from __future__ import annotations

from pathlib import Path

import pytest

from easydesign.core import ConfigurationError
from easydesign.orchestration import (
    LoadedPseRunConfig,
    LoadedSequenceRunConfig,
    LoadedTargetBundleRunConfig,
    initialize_project,
    load_run_config,
)


def test_initialize_sequence_project_has_no_prediction_default(tmp_path: Path) -> None:
    fasta = tmp_path / "apoe.fasta"
    fasta.write_text(">apoe\nACDEFGHIKLMNPQRSTVWY\n", encoding="utf-8")

    initialized = initialize_project(
        project_root=tmp_path / "apoe-project",
        target=fasta,
        stop_after_stage=2,
    )
    loaded = load_run_config(initialized.config_path)

    assert isinstance(loaded, LoadedSequenceRunConfig)
    assert loaded.config.prediction_policy.selection_mode == "explicit-per-stage"
    assert loaded.config.structure_prediction is None
    assert loaded.config.stage02 is not None
    assert loaded.config.stage02.automatic is not None
    assert loaded.config.stage02.automatic.patch.target_member_count == 12
    config_text = initialized.config_path.read_text(encoding="utf-8")
    assert config_text.startswith("schema_version: '0.9'")
    assert "execution_mode: review-gated" in config_text
    assert "type: local-file" in config_text
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


def test_initialize_unattended_stage02_defaults_to_single_sasa(
    tmp_path: Path,
) -> None:
    fasta = tmp_path / "target.fasta"
    fasta.write_text(">target\nACDEFGHIKLMNPQRSTVWY\n", encoding="utf-8")

    initialized = initialize_project(
        project_root=tmp_path / "unattended",
        target=fasta,
        stop_after_stage=2,
        execution_mode="unattended",
    )
    loaded = load_run_config(initialized.config_path)

    assert loaded.config.stage02 is not None
    assert tuple(str(method) for method in loaded.config.stage02.methods) == ("sasa",)
    assert loaded.config.stage02.unattended_approval is not None


def test_initialize_project_refuses_nonempty_destination(tmp_path: Path) -> None:
    fasta = tmp_path / "target.fasta"
    fasta.write_text(">target\nACDEFGHIKLMNPQRSTVWY\n", encoding="utf-8")
    destination = tmp_path / "existing"
    destination.mkdir()
    (destination / "keep.txt").write_text("keep", encoding="utf-8")

    with pytest.raises(ConfigurationError, match="非空"):
        initialize_project(project_root=destination, target=fasta)

    assert (destination / "keep.txt").read_text() == "keep"


def test_initialize_project_allows_only_explicit_bootstrap_metadata(tmp_path: Path) -> None:
    fasta = tmp_path / "target.fasta"
    fasta.write_text(">target\nACDEFGHIKLMNPQRSTVWY\n", encoding="utf-8")
    destination = tmp_path / "bootstrap"
    metadata = destination / "metadata"
    metadata.mkdir(parents=True)
    ledger = metadata / "agent.sqlite"
    ledger.write_bytes(b"persistent bootstrap identity")

    initialized = initialize_project(
        project_root=destination,
        target=fasta,
        allow_existing_metadata=True,
    )

    assert initialized.config_path.is_file()
    assert ledger.read_bytes() == b"persistent bootstrap identity"


def test_initialize_project_bootstrap_allowance_rejects_extra_content(tmp_path: Path) -> None:
    fasta = tmp_path / "target.fasta"
    fasta.write_text(">target\nACDEFGHIKLMNPQRSTVWY\n", encoding="utf-8")
    destination = tmp_path / "bootstrap"
    (destination / "metadata").mkdir(parents=True)
    (destination / "unexpected.txt").write_text("keep", encoding="utf-8")

    with pytest.raises(ConfigurationError, match="非空"):
        initialize_project(
            project_root=destination,
            target=fasta,
            allow_existing_metadata=True,
        )

    assert (destination / "unexpected.txt").read_text() == "keep"


def test_initialize_target_bundle_project_inherits_identity_and_source_root(
    tmp_path: Path,
) -> None:
    source_run = tmp_path / "source-run"
    source_run.mkdir()
    bundle = tmp_path / "target-bundle.json"
    bundle.write_text(
        """{
  "schema_version": "0.4",
  "target_id": "ubiquitin",
  "producer_attempt": "attempt-0001",
  "sequence_sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "target_structure": {}
}
""",
        encoding="utf-8",
    )

    initialized = initialize_project(
        project_root=tmp_path / "bundle-project",
        target_bundle=bundle,
        source_run_root=source_run,
    )
    loaded = load_run_config(initialized.config_path)

    assert isinstance(loaded, LoadedTargetBundleRunConfig)
    assert loaded.config.target.target_id == "ubiquitin"
    assert loaded.source_run_root == source_run.resolve()
    assert initialized.target_path is not None
    assert initialized.target_path.read_bytes() == bundle.read_bytes()


def test_initialize_local_structure_materializes_identity_chain_namespace_and_feature(
    tmp_path: Path,
) -> None:
    structure = tmp_path / "target.cif"
    structure.write_text(
        "data_target\nloop_\n_atom_site.group_PDB\nATOM\n#\n",
        encoding="utf-8",
    )

    initialized = initialize_project(
        project_root=tmp_path / "structure-project",
        target=structure,
        chain="A",
        chain_namespace="label",
        identity_uniprot="P0CG48",
        scope_feature_type="Domain",
        scope_feature_name="Ubiquitin",
    )
    loaded = load_run_config(initialized.config_path)
    source = loaded.config.target.source.model_dump(mode="json")
    scope = loaded.config.target.scope.model_dump(mode="json")

    assert source["chain"] == "A"
    assert source["chain_namespace"] == "label"
    assert source["identity"]["uniprot_accession"] == "P0CG48"
    assert scope == {
        "type": "uniprot-feature",
        "feature_type": "Domain",
        "feature_name": "Ubiquitin",
    }


def test_initialize_sequence_project_can_materialize_precomputed_msa(
    tmp_path: Path,
) -> None:
    fasta = tmp_path / "target.fasta"
    sequence = "ACDEFGHIKLMNPQRSTVWY"
    fasta.write_text(f">target\n{sequence}\n", encoding="utf-8")
    a3m = tmp_path / "target.a3m"
    a3m.write_text(
        f">query\n{sequence}\n>homolog\n{sequence}\n",
        encoding="utf-8",
    )

    initialized = initialize_project(
        project_root=tmp_path / "precomputed-project",
        target=fasta,
        precomputed_msa=a3m,
        stage01_prediction_backend="protenix-v2",
    )
    loaded = load_run_config(initialized.config_path)

    assert isinstance(loaded, LoadedSequenceRunConfig)
    assert initialized.msa_path is not None
    assert initialized.msa_path.read_bytes() == a3m.read_bytes()
    assert loaded.precomputed_msa_path == initialized.msa_path
    assert loaded.prediction_request.msa_mode == "precomputed"


def test_initialize_stage04_project_materializes_pilot_executor(
    tmp_path: Path,
) -> None:
    fasta = tmp_path / "target.fasta"
    fasta.write_text(">target\nACDEFGHIKLMNPQRSTVWY\n", encoding="utf-8")

    initialized = initialize_project(
        project_root=tmp_path / "pilot-project",
        target=fasta,
        stop_after_stage=4,
    )
    loaded = load_run_config(initialized.config_path)

    assert loaded.config.stage03 is not None
    assert loaded.config.stage04 is not None
    assert loaded.config.stage04.executor.devices is None
    assert loaded.config.stage04.executor.workers_per_device == 1
    assert loaded.config.stage04.required_complete_candidates_per_strategy == 40


def test_initialize_stage07_project_materializes_all_late_stage_profiles(
    tmp_path: Path,
) -> None:
    fasta = tmp_path / "target.fasta"
    fasta.write_text(">target\nACDEFGHIKLMNPQRSTVWY\n", encoding="utf-8")

    initialized = initialize_project(
        project_root=tmp_path / "final-project",
        target=fasta,
        stop_after_stage=7,
        execution_mode="unattended",
        stage06_candidate_count=37,
        stage01_prediction_backend="protenix-v2",
        stage05_prediction_backend="protenix-v2",
        stage07_de_novo_backend="protenix-v2",
        stage07_target_conditioned_backend="protenix-v2",
    )
    loaded = load_run_config(initialized.config_path)

    assert loaded.config.stage03 is not None
    assert loaded.config.stage04 is not None
    assert loaded.config.stage05 is not None
    assert loaded.config.stage06 is not None
    assert loaded.config.stage07 is not None
    assert loaded.config.stage05.filter_profile == "nanobody-filter-standard-v1.6"
    assert loaded.config.stage05.advisory_validation is not None
    assert loaded.config.stage05.advisory_validation.expanded_total_per_strategy == 100
    assert loaded.config.stage05.advisory_validation.full_target_refold_top_n == 10
    assert loaded.config.stage06.scale_profile == "user-defined-v1"
    assert loaded.config.stage06.total_candidate_count == 37
    assert loaded.config.stage06.allocation_policy == "equal-across-promoted-v1"
    assert loaded.config.stage06.preauthorized_candidate_limit is None
    assert loaded.config.stage07.primary_count == 20
    assert loaded.config.stage07.backup_count == 20
    assert loaded.config.stage07.tnp_required is True


def test_initialize_afo_project_propagates_backend_and_scientific_profiles(
    tmp_path: Path,
) -> None:
    fasta = tmp_path / "target.fasta"
    fasta.write_text(">target\nACDEFGHIKLMNPQRSTVWY\n", encoding="utf-8")

    initialized = initialize_project(
        project_root=tmp_path / "afo-project",
        target=fasta,
        stop_after_stage=7,
        execution_mode="unattended",
        stage01_prediction_backend="protenix-v2",
        stage05_prediction_backend="openfold3-af3-jax",
        stage07_de_novo_backend="openfold3-af3-jax",
        stage07_target_conditioned_backend="protenix-v2",
    )
    loaded = load_run_config(initialized.config_path)

    assert loaded.config.prediction_policy.selection_mode == "explicit-per-stage"
    assert loaded.config.structure_prediction is not None
    assert loaded.config.structure_prediction.backend == "protenix-v2"
    assert loaded.config.stage05 is not None
    assert loaded.config.stage05.filter_profile == "nanobody-filter-standard-v1.7"
    assert loaded.config.stage05.full_target_prediction.backend == "openfold3-af3-jax"
    assert loaded.config.stage07 is not None
    assert loaded.config.stage07.final_filter_profile == "nanobody-final-v1.6"
    assert loaded.config.stage07.full_target_prediction.backend == "openfold3-af3-jax"
    assert (
        loaded.config.stage07.target_conditioned_prediction.backend
        == "protenix-v2"
    )
