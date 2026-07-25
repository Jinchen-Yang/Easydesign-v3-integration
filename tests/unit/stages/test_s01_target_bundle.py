from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from easydesign.backends.structure_prediction import (
    MsaMode,
    PredictionParameterProfile,
    StructurePredictionProduct,
    TemplateMode,
)
from easydesign.backends.target_sources import normalize_raw_sequence
from easydesign.core import ManifestStateError, PredictionOutputError, load_model
from easydesign.stages.s01_target_preparation import (
    ResidueMapping,
    TargetBundle,
    build_predicted_target_bundle,
)

MINIMAL_CIF = """data_target
loop_
_atom_site.group_PDB
_atom_site.label_comp_id
_atom_site.label_asym_id
_atom_site.label_seq_id
_atom_site.auth_asym_id
_atom_site.auth_seq_id
_atom_site.pdbx_PDB_ins_code
ATOM ALA A 1 A 1 .
ATOM CYS A 2 A 2 .
#
"""


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prediction_product(tmp_path: Path) -> StructurePredictionProduct:
    structure = tmp_path / "prediction.cif"
    confidence = tmp_path / "confidence.json"
    structure.write_text(MINIMAL_CIF, encoding="utf-8")
    confidence.write_text("{}\n", encoding="utf-8")
    return StructurePredictionProduct(
        backend_name="protenix",
        backend_version="2.0.0",
        model_name="protenix-v2",
        seed=101,
        sample_index=0,
        structure_path=structure,
        structure_sha256=sha256(structure),
        confidence_path=confidence,
        confidence_sha256=sha256(confidence),
        plddt=80.0,
        gpde=3.5,
        ptm=0.7,
        iptm=0.0,
        ranking_score=0.7,
        has_clash=False,
        recycle_count=10,
    )


def test_build_predicted_target_bundle(tmp_path) -> None:
    run_root = tmp_path / "run"
    target = normalize_raw_sequence("AC", target_id="target")
    built = build_predicted_target_bundle(
        run_root=run_root,
        attempt_id="attempt-0001",
        target=target,
        product=prediction_product(tmp_path),
        model_checkpoint_sha256="8" * 64,
        msa_mode=MsaMode.DISABLED,
        msa_input_sha256=None,
        msa_server_mode=None,
        template_mode=TemplateMode.DISABLED,
        parameter_profile=PredictionParameterProfile.CUSTOM,
        resolved_cycle_count=1,
        resolved_diffusion_step_count=5,
    )

    assert built.bundle.sequence_length == 2
    assert built.bundle.origin == "predicted"
    assert built.bundle.schema_version == "0.4"
    assert built.bundle.identity_report is not None
    assert built.bundle.residue_mapping_tsv is not None
    assert built.bundle.coordinate_ensemble is not None
    assert built.bundle.coordinate_ensemble.model_ids == ("1",)
    assert built.bundle_path == (
        run_root
        / "01-target-preparation/attempt-0001/artifacts/target-bundle.json"
    )
    assert not (run_root / "01-target-preparation/attempts").exists()
    assert built.bundle_artifact.verify(run_root) == built.bundle_path
    mapping = load_model(
        built.bundle.residue_mapping.verify(run_root),
        ResidueMapping,
    )
    assert [entry.amino_acid for entry in mapping.entries] == ["A", "C"]
    assert json.loads(
        built.bundle.quality_report.verify(run_root).read_text(encoding="utf-8")
    )["backend_version"] == "2.0.0"


def test_bundle_refuses_to_overwrite_attempt_artifacts(tmp_path) -> None:
    run_root = tmp_path / "run"
    kwargs = {
        "run_root": run_root,
        "attempt_id": "attempt-0001",
        "target": normalize_raw_sequence("AC", target_id="target"),
        "product": prediction_product(tmp_path),
        "model_checkpoint_sha256": "8" * 64,
        "msa_mode": MsaMode.DISABLED,
        "msa_input_sha256": None,
        "msa_server_mode": None,
        "template_mode": TemplateMode.DISABLED,
        "parameter_profile": PredictionParameterProfile.CUSTOM,
        "resolved_cycle_count": 1,
        "resolved_diffusion_step_count": 5,
    }
    build_predicted_target_bundle(**kwargs)
    with pytest.raises(ManifestStateError, match="不可覆盖"):
        build_predicted_target_bundle(**kwargs)


def test_predicted_adapter_rejects_multi_model_output(tmp_path: Path) -> None:
    product = prediction_product(tmp_path)
    product.structure_path.write_text(
        """data_target
loop_
_atom_site.group_PDB
_atom_site.label_comp_id
_atom_site.label_asym_id
_atom_site.label_seq_id
_atom_site.auth_asym_id
_atom_site.auth_seq_id
_atom_site.pdbx_PDB_ins_code
_atom_site.pdbx_PDB_model_num
ATOM ALA A 1 A 1 . 1
ATOM CYS A 2 A 2 . 1
ATOM ALA A 1 A 1 . 2
ATOM CYS A 2 A 2 . 2
#
""",
        encoding="utf-8",
    )
    product = product.model_copy(
        update={"structure_sha256": sha256(product.structure_path)}
    )

    with pytest.raises(PredictionOutputError, match="coordinate model"):
        build_predicted_target_bundle(
            run_root=tmp_path / "run",
            attempt_id="attempt-0001",
            target=normalize_raw_sequence("AC", target_id="target"),
            product=product,
            model_checkpoint_sha256="8" * 64,
            msa_mode=MsaMode.DISABLED,
            msa_input_sha256=None,
            msa_server_mode=None,
            template_mode=TemplateMode.DISABLED,
            parameter_profile=PredictionParameterProfile.CUSTOM,
            resolved_cycle_count=1,
            resolved_diffusion_step_count=5,
        )


def test_target_bundle_02_loader_accepts_legacy_01_without_annotations(
    tmp_path: Path,
) -> None:
    built = build_predicted_target_bundle(
        run_root=tmp_path / "run",
        attempt_id="attempt-0001",
        target=normalize_raw_sequence("AC", target_id="target"),
        product=prediction_product(tmp_path),
        model_checkpoint_sha256="8" * 64,
        msa_mode=MsaMode.DISABLED,
        msa_input_sha256=None,
        msa_server_mode=None,
        template_mode=TemplateMode.DISABLED,
        parameter_profile=PredictionParameterProfile.CUSTOM,
        resolved_cycle_count=1,
        resolved_diffusion_step_count=5,
    )
    payload = built.bundle.model_dump(mode="python")
    payload["schema_version"] = "0.1"
    payload.pop("coordinate_ensemble")
    for key in (
        "reference_sequence",
        "residue_mapping_tsv",
        "identity_report",
        "scope_report",
        "structure_candidates",
        "structure_candidates_tsv",
        "retrieval_manifest",
        "source_context",
        "design_context",
        "prediction_confidence",
        "target_pdb",
    ):
        payload.pop(key)

    legacy = TargetBundle.model_validate(payload)

    assert legacy.schema_version == "0.1"
    assert legacy.source_annotations is None
