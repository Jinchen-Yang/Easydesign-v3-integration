from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

from easydesign.backends.structure_prediction import (
    ComplexStructurePredictionRequest,
    MsaMode,
    PredictionParameterProfile,
    ProteinPredictionChain,
    ProtenixMsaProvider,
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


def test_stage01_write_input_snapshots_independent_msa_and_template_features(
    tmp_path: Path,
) -> None:
    paired = (tmp_path / "paired.a3m").resolve()
    paired.write_text(">query\nACDEFGHIKLMNPQRSTVWY\n", encoding="utf-8")
    templates = (tmp_path / "templates.json").resolve()
    templates.write_text("[]\n", encoding="utf-8")
    configured = StructurePredictionRequest(
        job_name="apoe-smoke",
        target=target(),
        msa_mode=MsaMode.QUERY_ONLY,
        template_mode=TemplateMode.PRECOMPUTED,
        target_unpaired_msa_mode=MsaMode.QUERY_ONLY,
        target_paired_msa_mode=MsaMode.PRECOMPUTED,
        target_paired_msa_path=paired,
        target_template_data_path=templates,
        target_template_data_sha256=hashlib.sha256(
            templates.read_bytes()
        ).hexdigest(),
    )
    input_json = tmp_path / "attempt" / "input.json"

    adapter().write_input(configured, input_json)
    protein = json.loads(input_json.read_text(encoding="utf-8"))[0]["sequences"][0][
        "proteinChain"
    ]

    assert Path(protein["unpairedMsaPath"]).read_text(encoding="utf-8") == (
        ">query\nACDEFGHIKLMNPQRSTVWY\n"
    )
    assert Path(protein["pairedMsaPath"]).read_text(encoding="utf-8") == (
        paired.read_text(encoding="utf-8")
    )
    assert Path(protein["templatesPath"]).read_bytes() == templates.read_bytes()


def adapter() -> ProtenixV2Adapter:
    return ProtenixV2Adapter(
        executable=Path("/opt/conda/envs/protenix-v2/bin/protenix"),
        model_root=Path("/data/models/protenix"),
        cuda_visible_devices="0",
    )


def test_complex_request_preserves_target_msa_and_query_only_binder(
    tmp_path: Path,
) -> None:
    query = tmp_path / "binder-query.a3m"
    query.write_text(">query\nACDEFG\n", encoding="utf-8")
    request = ComplexStructurePredictionRequest(
        job_name="complex-one",
        chains=(
            ProteinPredictionChain(
                chain_id="A",
                role="target",
                sequence="ACDEFGHIK",
            ),
            ProteinPredictionChain(
                chain_id="B",
                role="binder",
                sequence="ACDEFG",
                paired_msa_path=query,
                unpaired_msa_path=query,
            ),
        ),
        seeds=(101,),
        sample_count=1,
        msa_mode=MsaMode.REMOTE,
    )

    payload = adapter().render_input(request)
    invocation = adapter().prediction_invocation(
        request,
        input_json=tmp_path / "input.json",
        output_dir=tmp_path / "output",
    )

    target = payload[0]["sequences"][0]["proteinChain"]
    binder = payload[0]["sequences"][1]["proteinChain"]
    assert "unpairedMsaPath" not in target
    assert binder["pairedMsaPath"] == str(query)
    assert binder["unpairedMsaPath"] == str(query)
    assert invocation.argv[-2:] == ("--use_default_params", "true")
    assert invocation.argv[
        invocation.argv.index("--need_atom_confidence") + 1
    ] == "true"


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
    invocation = adapter().version_invocation()

    assert invocation.argv[:2] == (
        "/opt/conda/envs/protenix-v2/bin/python",
        "-c",
    )
    assert invocation.environment[1][0] == "PATH"
    adapter().validate_version_output("2.0.0\n")
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
    assert invocation.timeout_seconds == 7200
    environment = dict(invocation.environment)
    assert environment["PROTENIX_ROOT_DIR"] == "/data/models/protenix"
    assert environment["CUDA_VISIBLE_DEVICES"] == "0"
    assert environment["PATH"].split(":", maxsplit=1)[0] == (
        "/opt/conda/envs/protenix-v2/bin"
    )


def test_extra_toolchain_path_is_merged_after_the_protenix_bin() -> None:
    selected = ProtenixV2Adapter(
        executable=Path("/opt/conda/envs/protenix-v2/bin/protenix"),
        model_root=Path("/data/models/protenix"),
        extra_environment=(("PATH", "/opt/cuda/nvvm/bin"), ("CC", "conda-cc")),
    )
    invocation = selected.prediction_invocation(
        request(),
        input_json=Path("/run/input.json"),
        output_dir=Path("/run/output"),
    )
    environment = dict(invocation.environment)

    assert environment["PATH"].split(os.pathsep)[:2] == [
        "/opt/conda/envs/protenix-v2/bin",
        "/opt/cuda/nvvm/bin",
    ]
    assert environment["CC"] == "conda-cc"


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
    assert option_value(msa.argv, "--msa_server_mode") == "colabfold"
    assert dict(msa.environment)["MMSEQS_SERVICE_HOST_URL"] == (
        "https://api.colabfold.com"
    )
    assert msa.timeout_seconds == 1800
    assert option_value(prediction.argv, "--use_msa") == "true"
    assert option_value(prediction.argv, "--use_template") == "false"
    assert option_value(prediction.argv, "--use_default_params") == "true"
    assert "--cycle" not in prediction.argv
    assert "--step" not in prediction.argv
    assert adapter().updated_msa_input_path(
        Path("/run/input.json"), Path("/run/msa")
    ) == Path("/run/input-update-msa.json")


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
        remote_msa_provider=ProtenixMsaProvider.CUSTOM_COLABFOLD,
        remote_msa_endpoint="https://msa.example.org/api/",
        remote_msa_timeout_seconds=900,
    )
    invocation = selected.msa_invocation(
        request(msa_mode=MsaMode.REMOTE),
        input_json=Path("/run/input.json"),
        output_dir=Path("/run/msa"),
    )
    assert option_value(invocation.argv, "--msa_server_mode") == "colabfold"
    assert dict(invocation.environment)["MMSEQS_SERVICE_HOST_URL"] == (
        "https://msa.example.org/api"
    )
    assert invocation.timeout_seconds == 900


def test_adapter_can_explicitly_select_protenix_official_endpoint() -> None:
    selected = ProtenixV2Adapter(
        executable=Path("/opt/conda/envs/protenix-v2/bin/protenix"),
        model_root=Path("/data/models/protenix"),
        remote_msa_provider=ProtenixMsaProvider.PROTENIX_OFFICIAL,
    )
    invocation = selected.msa_invocation(
        request(msa_mode=MsaMode.REMOTE),
        input_json=Path("/run/input.json"),
        output_dir=Path("/run/msa"),
    )

    assert option_value(invocation.argv, "--msa_server_mode") == "protenix"
    assert dict(invocation.environment)["MMSEQS_SERVICE_HOST_URL"] == (
        "https://protenix-server.com/api/msa"
    )


def test_adapter_rejects_ambiguous_or_overridden_msa_endpoint() -> None:
    with pytest.raises(BackendContractError, match="固定 endpoint"):
        ProtenixV2Adapter(
            executable=Path("/opt/conda/envs/protenix-v2/bin/protenix"),
            model_root=Path("/data/models/protenix"),
            remote_msa_provider=ProtenixMsaProvider.COLABFOLD_PUBLIC,
            remote_msa_endpoint="https://other.example.org",
        )
    with pytest.raises(BackendContractError, match="MMSEQS_SERVICE_HOST_URL"):
        ProtenixV2Adapter(
            executable=Path("/opt/conda/envs/protenix-v2/bin/protenix"),
            model_root=Path("/data/models/protenix"),
            extra_environment=(
                ("MMSEQS_SERVICE_HOST_URL", "https://other.example.org"),
            ),
        )
    with pytest.raises(BackendContractError, match="不能内嵌凭据"):
        ProtenixV2Adapter(
            executable=Path("/opt/conda/envs/protenix-v2/bin/protenix"),
            model_root=Path("/data/models/protenix"),
            remote_msa_provider=ProtenixMsaProvider.CUSTOM_COLABFOLD,
            remote_msa_endpoint="https://token@msa.example.org/api?secret=value",
        )


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
