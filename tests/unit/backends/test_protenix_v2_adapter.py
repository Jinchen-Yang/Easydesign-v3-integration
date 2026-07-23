from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from easydesign.backends.structure_prediction import (
    MsaMode,
    PredictionParameterProfile,
    ProtenixV2Adapter,
    StructurePredictionRequest,
    TemplateMode,
)
from easydesign.backends.target_sources import normalize_raw_sequence
from easydesign.core import (
    BackendContractError,
    ManifestStateError,
    PredictionOutputError,
)


def target():
    return normalize_raw_sequence(
        "ACDEFGHIKLMNPQRSTVWY",
        target_id="apoe-smoke",
    )


def request(
    *,
    msa_mode: MsaMode = MsaMode.DISABLED,
    profile: PredictionParameterProfile = PredictionParameterProfile.MODEL_DEFAULT,
) -> StructurePredictionRequest:
    kwargs: dict[str, object] = {}
    if profile is PredictionParameterProfile.CUSTOM:
        kwargs.update(cycle_count=1, diffusion_step_count=5)
    return StructurePredictionRequest(
        job_name="apoe-smoke",
        target=target(),
        seeds=(101,),
        sample_count=1,
        msa_mode=msa_mode,
        template_mode=TemplateMode.DISABLED,
        parameter_profile=profile,
        **kwargs,
    )


def adapter() -> ProtenixV2Adapter:
    return ProtenixV2Adapter(
        executable=Path("/opt/conda/envs/protenix-v2/bin/protenix"),
        model_root=Path("/data/models/protenix"),
        cuda_visible_devices="0",
    )


def option_value(argv: tuple[str, ...], option: str) -> str:
    return argv[argv.index(option) + 1]


def test_adapter_renders_official_sequence_json() -> None:
    payload = adapter().render_input(request())
    assert payload == [
        {
            "name": "apoe-smoke",
            "sequences": [
                {
                    "proteinChain": {
                        "sequence": "ACDEFGHIKLMNPQRSTVWY",
                        "count": 1,
                    }
                }
            ],
        }
    ]


def test_input_write_is_exclusive(tmp_path) -> None:
    path = tmp_path / "input.json"
    adapter().write_input(request(), path)
    with pytest.raises(ManifestStateError, match="不可覆盖"):
        adapter().write_input(request(), path)


def test_version_probe_requires_exact_pinned_version() -> None:
    adapter().validate_version_output("protenix, version 2.0.0\n")
    with pytest.raises(BackendContractError, match="版本不匹配"):
        adapter().validate_version_output("protenix, version 2.1.0\n")


def test_no_msa_smoke_invocation_is_explicit() -> None:
    invocation = adapter().prediction_invocation(
        request(profile=PredictionParameterProfile.CUSTOM),
        input_json=Path("/run/input.json"),
        output_dir=Path("/run/output"),
    )
    assert invocation.argv[:2] == (
        "/opt/conda/envs/protenix-v2/bin/protenix",
        "pred",
    )
    assert option_value(invocation.argv, "--model_name") == "protenix-v2"
    assert option_value(invocation.argv, "--use_msa") == "false"
    assert option_value(invocation.argv, "--use_template") == "false"
    assert option_value(invocation.argv, "--use_default_params") == "false"
    assert option_value(invocation.argv, "--cycle") == "1"
    assert option_value(invocation.argv, "--step") == "5"
    assert dict(invocation.environment) == {
        "PROTENIX_ROOT_DIR": "/data/models/protenix",
        "CUDA_VISIBLE_DEVICES": "0",
    }


def test_remote_msa_and_default_prediction_are_separate_invocations() -> None:
    remote_request = request(msa_mode=MsaMode.REMOTE)
    msa = adapter().msa_invocation(
        remote_request,
        input_json=Path("/run/input.json"),
        output_dir=Path("/run/msa"),
    )
    prediction = adapter().prediction_invocation(
        remote_request,
        input_json=Path("/run/msa/input-update-msa.json"),
        output_dir=Path("/run/output"),
    )

    assert msa.argv[1] == "msa"
    assert option_value(msa.argv, "--msa_server_mode") == "protenix"
    assert option_value(prediction.argv, "--use_msa") == "true"
    assert option_value(prediction.argv, "--use_template") == "false"
    assert option_value(prediction.argv, "--use_default_params") == "true"
    assert "--cycle" not in prediction.argv
    assert "--step" not in prediction.argv
    assert adapter().updated_msa_input_path(
        Path("/run/input.json"), Path("/run/msa")
    ) == Path("/run/msa/input-update-msa.json")


def test_remote_msa_invocation_rejects_other_modes() -> None:
    with pytest.raises(BackendContractError, match="remote MSA"):
        adapter().msa_invocation(
            request(),
            input_json=Path("/run/input.json"),
            output_dir=Path("/run/msa"),
        )


def test_adapter_can_explicitly_select_colabfold_remote_msa() -> None:
    selected = ProtenixV2Adapter(
        executable=Path("/opt/conda/envs/protenix-v2/bin/protenix"),
        model_root=Path("/data/models/protenix"),
        remote_msa_server_mode="colabfold",
    )
    invocation = selected.msa_invocation(
        request(msa_mode=MsaMode.REMOTE),
        input_json=Path("/run/input.json"),
        output_dir=Path("/run/msa"),
    )
    assert option_value(invocation.argv, "--msa_server_mode") == "colabfold"


def test_collect_products_uses_deterministic_protenix_layout(tmp_path) -> None:
    output_dir = tmp_path / "output"
    prediction_dir = output_dir / "apoe-smoke" / "seed_101" / "predictions"
    prediction_dir.mkdir(parents=True)
    structure = prediction_dir / "apoe-smoke_sample_0.cif"
    confidence = prediction_dir / "apoe-smoke_summary_confidence_sample_0.json"
    structure.write_text("data_apoe\n", encoding="utf-8")
    confidence.write_text(
        json.dumps(
            {
                "plddt": 80.0,
                "gpde": 3.5,
                "ptm": 0.7,
                "iptm": 0.0,
                "ranking_score": 0.7,
                "has_clash": False,
                "num_recycles": 10,
            }
        ),
        encoding="utf-8",
    )

    products = adapter().collect_products(request(), output_dir=output_dir)
    assert len(products) == 1
    product = products[0]
    assert product.structure_path == structure
    assert product.structure_sha256 == hashlib.sha256(b"data_apoe\n").hexdigest()
    assert product.plddt == 80.0
    assert product.recycle_count == 10


def test_collect_products_rejects_missing_output(tmp_path) -> None:
    with pytest.raises(PredictionOutputError, match="正式输出缺失"):
        adapter().collect_products(request(), output_dir=tmp_path)
