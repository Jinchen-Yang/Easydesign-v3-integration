from __future__ import annotations

import json
from pathlib import Path

import pytest

from easydesign.backends.structure_prediction import (
    ComplexStructurePredictionRequest,
    MsaMode,
    OpenFold3Af3JaxAdapter,
    ProteinPredictionChain,
    StructurePredictionRequest,
)
from easydesign.backends.target_sources import normalize_raw_sequence
from easydesign.core import BackendContractError, ManifestStateError


def adapter() -> OpenFold3Af3JaxAdapter:
    return OpenFold3Af3JaxAdapter(
        python=Path("/runtime/envs/openfold3/bin/python"),
        runner=Path("/runtime/models/openfold3/runner/run_alphafold.py"),
        model_root=Path("/runtime/models/openfold3/weights"),
        cache_root=Path("/runtime/cache/openfold3"),
        release_id="afo-3-1-4-of3-p2-155k",
        backend_version="3.1.4",
        model_name="of3-p2-155k",
        adapter_contract_version="openfold3-af3-jax-cli-v1",
        release_manifest_sha256="d" * 64,
        conversion_receipt_sha256="e" * 64,
        raw_checkpoint_sha256="a" * 64,
        converted_weight_sha256="b" * 64,
        wheel_sha256="c" * 64,
        environment_lock_sha256="f" * 64,
        runner_commit="bc32b22ff5902e3daffd5d1f7203d7f2ab6cb997",
        runner_tree_sha256="1" * 64,
        cuda_visible_devices="0",
    )


def single_request(msa_mode: MsaMode = MsaMode.DISABLED) -> StructurePredictionRequest:
    return StructurePredictionRequest(
        job_name="target-one",
        target=normalize_raw_sequence("ACDEFGHIK", target_id="target-one"),
        seeds=(101,),
        sample_count=1,
        msa_mode=msa_mode,
    )


def complex_request(
    tmp_path: Path,
    *,
    samples: int = 1,
    seeds: tuple[int, ...] = (101,),
) -> ComplexStructurePredictionRequest:
    target_msa = tmp_path / "target.a3m"
    binder_msa = tmp_path / "binder.a3m"
    target_msa.write_text(">query\nACDEFGHIK\n>hit\nAC-EFGHIK\n", encoding="utf-8")
    binder_msa.write_text(">query\nLMNPQRSTV\n", encoding="utf-8")
    return ComplexStructurePredictionRequest(
        job_name="complex-one",
        chains=(
            ProteinPredictionChain(
                chain_id="A",
                role="target",
                sequence="ACDEFGHIK",
                unpaired_msa_path=target_msa,
            ),
            ProteinPredictionChain(
                chain_id="B",
                role="binder",
                sequence="LMNPQRSTV",
                unpaired_msa_path=binder_msa,
            ),
        ),
        seeds=seeds,
        sample_count=samples,
        msa_mode=MsaMode.PRECOMPUTED,
    )


def test_renders_af3_v4_with_templates_disabled_and_query_only_binder(
    tmp_path: Path,
) -> None:
    payload = adapter().render_input(complex_request(tmp_path))

    assert payload["dialect"] == "alphafold3"
    assert payload["version"] == 4
    assert payload["modelSeeds"] == [101]
    target = payload["sequences"][0]["protein"]
    binder = payload["sequences"][1]["protein"]
    assert target["id"] == "A"
    assert target["templates"] == []
    assert ">hit" in target["unpairedMsa"]
    assert binder == {
        "id": "B",
        "sequence": "LMNPQRSTV",
        "templates": [],
        "unpairedMsa": ">query\nLMNPQRSTV\n",
        "pairedMsa": "",
    }


def test_remote_msa_and_prediction_are_separate_explicit_invocations() -> None:
    selected = adapter()
    request = single_request(MsaMode.REMOTE)
    msa = selected.msa_invocation(
        request,
        input_json=Path("/run/target-one.json"),
        output_dir=Path("/run/msa"),
    )
    prediction = selected.prediction_invocation(
        request,
        input_json=Path("/run/msa/target-one/target-one_data.json"),
        output_dir=Path("/run/prediction"),
    )

    assert "--run_inference=false" in msa.argv
    assert "--use_msa_server=true" in msa.argv
    assert "--run_data_pipeline=false" in msa.argv
    assert "--run_inference=true" in prediction.argv
    assert "--use_msa_server=false" in prediction.argv
    assert not any("protenix" in value.lower() for value in prediction.argv)


def test_write_input_is_append_only(tmp_path: Path) -> None:
    path = tmp_path / "target-one.json"
    adapter().write_input(single_request(), path)
    with pytest.raises(ManifestStateError, match="不可覆盖"):
        adapter().write_input(single_request(), path)


def test_adapter_rejects_non_ab_complex(tmp_path: Path) -> None:
    request = complex_request(tmp_path).model_copy(
        update={
            "chains": (
                complex_request(tmp_path).chains[0].model_copy(
                    update={"chain_id": "X"}
                ),
                complex_request(tmp_path).chains[1],
            )
        }
    )
    with pytest.raises(BackendContractError, match="target=A"):
        adapter().render_input(request)


def test_collects_all_samples_and_computes_true_cross_chain_pae(
    tmp_path: Path,
) -> None:
    request = complex_request(tmp_path, samples=2)
    output_root = tmp_path / "output"
    for sample in range(2):
        sample_dir = output_root / "complex-one" / f"seed-101_sample-{sample}"
        sample_dir.mkdir(parents=True)
        prefix = f"complex-one_seed-101_sample-{sample}_"
        (sample_dir / f"{prefix}model.cif").write_text(
            "data_prediction\n", encoding="utf-8"
        )
        (sample_dir / f"{prefix}summary_confidences.json").write_text(
            json.dumps(
                {
                    "ptm": 0.71,
                    "iptm": 0.68,
                    "ranking_score": 0.70 + sample / 100,
                    "fraction_disordered": 0.03,
                    "has_clash": 0.0,
                    "chain_pair_iptm": [[0.8, 0.72], [0.71, 0.79]],
                    "chain_pair_pae_min": [[0.2, 1.0], [1.0, 0.2]],
                    "chain_ptm": [0.74, 0.81],
                    "chain_ids": ["A", "B"],
                }
            ),
            encoding="utf-8",
        )
        (sample_dir / f"{prefix}confidences.json").write_text(
            json.dumps(
                {
                    "atom_plddts": [80.0, 90.0],
                    "token_chain_ids": ["A", "A", "B", "B"],
                    "pae": [
                        [0.0, 1.0, 8.0, 7.0],
                        [1.0, 0.0, 6.0, 5.0],
                        [9.0, 4.0, 0.0, 1.0],
                        [10.0, 11.0, 1.0, 0.0],
                    ],
                }
            ),
            encoding="utf-8",
        )

    products = adapter().collect_products(request, output_dir=output_root)

    assert len(products) == 2
    assert products[0].gpde is None
    assert products[0].mean_plddt == 85.0
    assert products[0].complex_confidence is not None
    assert products[0].complex_confidence.pairwise_iptm == pytest.approx(0.72)
    assert products[0].complex_confidence.minimum_interface_pae_angstrom == 4.0
    assert products[0].complex_confidence.binder_ptm == pytest.approx(0.81)
    assert products[0].backend_version == "3.1.4"
    assert products[0].model_name == "of3-p2-155k"
    assert products[0].native_metrics["release_id"] == "afo-3-1-4-of3-p2-155k"
    assert products[0].native_metrics["environment_lock_sha256"] == "f" * 64
    assert products[1].ranking_score > products[0].ranking_score


def test_collects_complete_five_by_five_evidence(tmp_path: Path) -> None:
    seeds = (101, 202, 303, 404, 505)
    request = complex_request(tmp_path, samples=5, seeds=seeds)
    output_root = tmp_path / "output"
    for seed in seeds:
        for sample in range(5):
            sample_dir = output_root / "complex-one" / f"seed-{seed}_sample-{sample}"
            sample_dir.mkdir(parents=True)
            prefix = f"complex-one_seed-{seed}_sample-{sample}_"
            (sample_dir / f"{prefix}model.cif").write_text(
                "data_prediction\n", encoding="utf-8"
            )
            (sample_dir / f"{prefix}summary_confidences.json").write_text(
                json.dumps(
                    {
                        "ptm": 0.71,
                        "iptm": 0.68,
                        "ranking_score": 0.70 + sample / 100,
                        "fraction_disordered": 0.03,
                        "has_clash": 0.0,
                        "chain_pair_iptm": [[0.8, 0.72], [0.71, 0.79]],
                        "chain_pair_pae_min": [[0.2, 1.0], [1.0, 0.2]],
                        "chain_ptm": [0.74, 0.81],
                        "chain_ids": ["A", "B"],
                    }
                ),
                encoding="utf-8",
            )
            (sample_dir / f"{prefix}confidences.json").write_text(
                json.dumps(
                    {
                        "atom_plddts": [80.0, 90.0],
                        "token_chain_ids": ["A", "A", "B", "B"],
                        "pae": [
                            [0.0, 1.0, 8.0, 7.0],
                            [1.0, 0.0, 6.0, 5.0],
                            [9.0, 4.0, 0.0, 1.0],
                            [10.0, 11.0, 1.0, 0.0],
                        ],
                    }
                ),
                encoding="utf-8",
            )

    products = adapter().collect_products(request, output_dir=output_root)

    assert len(products) == 25
    assert {(item.seed, item.sample_index) for item in products} == {
        (seed, sample) for seed in seeds for sample in range(5)
    }
