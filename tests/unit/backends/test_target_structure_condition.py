from __future__ import annotations

import hashlib
import json
from datetime import date
from pathlib import Path

import pytest

from easydesign.backends.structure_prediction import (
    ComplexStructurePredictionRequest,
    MsaMode,
    OpenFold3Af3JaxAdapter,
    ProteinPredictionChain,
    ProtenixV2Adapter,
    ScientificMode,
    TargetResidueNumbering,
    TargetStructureCondition,
    TemplateMode,
)
from easydesign.core import BackendContractError


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _condition(tmp_path: Path) -> TargetStructureCondition:
    structure = (tmp_path / "target.cif").resolve()
    structure.write_text("data_target\n#\n", encoding="utf-8")
    template = (tmp_path / "target-template.json").resolve()
    template_structure = (tmp_path / "target-template.cif").resolve()
    template_structure.write_text(
        "data_target\n_pdbx_audit_revision_history.revision_date 1970-01-01\n#\n",
        encoding="utf-8",
    )
    template.write_text(
        json.dumps(
            [
                {
                    "mmcif": template_structure.read_text(encoding="utf-8"),
                    "queryIndices": [0, 1],
                    "templateIndices": [0, 1],
                }
            ],
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    binder_template = (tmp_path / "binder-no-templates.json").resolve()
    binder_template.write_text("[]\n", encoding="utf-8")
    return TargetStructureCondition(
        source_origin="experimental",
        source_structure_kind="experimental",
        source_structure_sha256=_sha(structure),
        snapshot_structure_path=structure,
        snapshot_structure_sha256=_sha(structure),
        template_structure_path=template_structure,
        template_structure_sha256=_sha(template_structure),
        template_release_date=date(1970, 1, 1),
        template_release_date_source="synthetic-conservative",
        template_data_path=template,
        template_data_sha256=_sha(template),
        binder_template_data_path=binder_template,
        binder_template_data_sha256=_sha(binder_template),
        run_snapshot_relative_path="05-pilot/work/target-condition",
        template_chain_id="A",
        query_indices=(0, 1),
        template_indices=(0, 1),
        residue_numbering=(
            TargetResidueNumbering(
                sequence_index=1,
                query_index=0,
                template_index=0,
                label_seq_id=1,
                author_chain_id="A",
                author_residue_id="10",
            ),
            TargetResidueNumbering(
                sequence_index=2,
                query_index=1,
                template_index=1,
                label_seq_id=2,
                author_chain_id="A",
                author_residue_id="11",
            ),
        ),
    )


def _request(tmp_path: Path) -> ComplexStructurePredictionRequest:
    target_query = (tmp_path / "target-query.a3m").resolve()
    target_query.write_text(">query\nAC\n", encoding="utf-8")
    binder_query = (tmp_path / "binder-query.a3m").resolve()
    binder_query.write_text(">query\nDE\n", encoding="utf-8")
    return ComplexStructurePredictionRequest(
        job_name="conditioned-complex",
        chains=(
            ProteinPredictionChain(
                chain_id="A",
                role="target",
                sequence="AC",
                paired_msa_path=target_query,
                unpaired_msa_path=target_query,
            ),
            ProteinPredictionChain(
                chain_id="B",
                role="binder",
                sequence="DE",
                paired_msa_path=binder_query,
                unpaired_msa_path=binder_query,
            ),
        ),
        msa_mode=MsaMode.PRECOMPUTED,
        template_mode=TemplateMode.PRECOMPUTED,
        scientific_mode=ScientificMode.TARGET_CONDITIONED,
        target_structure_condition=_condition(tmp_path),
    )


def _afo() -> OpenFold3Af3JaxAdapter:
    return OpenFold3Af3JaxAdapter(
        python=Path("/runtime/bin/python"),
        runner=Path("/runtime/run_alphafold.py"),
        model_root=Path("/runtime/model"),
        cache_root=Path("/runtime/cache"),
        release_id="afo-3-1-4-of3-p2-155k",
        backend_version="3.1.4",
        model_name="of3-p2-155k",
        adapter_contract_version="openfold3-af3-jax-cli-v1",
        release_manifest_sha256="1" * 64,
        conversion_receipt_sha256="2" * 64,
        raw_checkpoint_sha256="3" * 64,
        converted_weight_sha256="4" * 64,
        wheel_sha256="5" * 64,
        environment_lock_sha256="6" * 64,
        runner_commit="bc32b22",
        runner_tree_sha256="7" * 64,
    )


def _protenix() -> ProtenixV2Adapter:
    return ProtenixV2Adapter(
        executable=Path("/runtime/bin/protenix"),
        model_root=Path("/runtime/protenix"),
    )


def test_adapters_condition_only_target_and_enable_template_flag(tmp_path: Path) -> None:
    request = _request(tmp_path)
    afo_payload = _afo().render_input(request)
    afo_target = afo_payload["sequences"][0]["protein"]
    afo_binder = afo_payload["sequences"][1]["protein"]
    assert afo_target["templates"][0]["queryIndices"] == [0, 1]
    assert afo_binder["templates"] == []

    protenix_payload = _protenix().render_input(request)
    protenix_target = protenix_payload[0]["sequences"][0]["proteinChain"]
    protenix_binder = protenix_payload[0]["sequences"][1]["proteinChain"]
    assert protenix_target["templatesPath"] == str(
        request.target_structure_condition.template_data_path
    )
    assert "templatesPath" not in protenix_binder
    invocation = _protenix().prediction_invocation(
        request,
        input_json=tmp_path / "input.json",
        output_dir=tmp_path / "output",
    )
    assert invocation.argv[invocation.argv.index("--use_template") + 1] == "true"
    assert invocation.argv[
        invocation.argv.index("--kalign_binary_path") + 1
    ] == "/runtime/bin/kalign"


def test_conditioned_request_rejects_corrupt_snapshot(tmp_path: Path) -> None:
    request = _request(tmp_path)
    request.target_structure_condition.snapshot_structure_path.write_text(
        "corrupt\n", encoding="utf-8"
    )
    with pytest.raises(BackendContractError, match="structure SHA-256"):
        _afo().render_input(request)
    with pytest.raises(BackendContractError, match="structure SHA-256"):
        _protenix().render_input(request)


def test_scientific_label_does_not_restrict_feature_combination(tmp_path: Path) -> None:
    base = _request(tmp_path)
    payload = base.model_dump()
    payload.update(scientific_mode=ScientificMode.DE_NOVO)
    request = ComplexStructurePredictionRequest.model_validate(payload)

    rendered = _afo().render_input(request)
    assert rendered["sequences"][0]["protein"]["templates"]
