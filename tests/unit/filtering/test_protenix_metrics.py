from __future__ import annotations

import json
from pathlib import Path

import pytest

from easydesign.backends.structure_prediction import (
    ComplexConfidenceMetrics,
    StructurePredictionProduct,
)
from easydesign.core import ManifestStateError
from easydesign.filtering import (
    extract_complex_confidence,
    extract_protenix_complex_confidence,
)


def _write(path: Path, value: object) -> Path:
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def test_extracts_true_cross_chain_minimum_pae(tmp_path: Path) -> None:
    summary = _write(
        tmp_path / "summary.json",
        {
            "chain_pair_iptm": [[0.0, 0.73], [0.73, 0.0]],
            "chain_ptm": [0.81, 0.76],
        },
    )
    full = _write(
        tmp_path / "full.json",
        {
            "token_asym_id": [0, 0, 1, 1],
            "token_has_frame": [1, 1, 1, 1],
            "token_pair_pae": [
                [0.0, 1.0, 8.0, 6.0],
                [1.0, 0.0, 5.0, 7.0],
                [9.0, 4.0, 0.0, 1.0],
                [10.0, 11.0, 1.0, 0.0],
            ],
        },
    )

    result = extract_protenix_complex_confidence(
        summary_path=summary,
        full_confidence_path=full,
    )

    assert result.pairwise_iptm == pytest.approx(0.73)
    assert result.minimum_interface_pae_angstrom == pytest.approx(4.0)
    assert result.binder_ptm == pytest.approx(0.76)
    assert result.target_token_count == 2
    assert result.binder_token_count == 2


def test_rejects_missing_full_confidence_matrix(tmp_path: Path) -> None:
    summary = _write(
        tmp_path / "summary.json",
        {
            "chain_pair_iptm": [[0.0, 0.73], [0.73, 0.0]],
            "chain_ptm": [0.81, 0.76],
        },
    )
    full = _write(
        tmp_path / "full.json",
        {
            "token_asym_id": [0, 1],
            "token_has_frame": [1, 1],
        },
    )

    with pytest.raises(ManifestStateError, match="schema"):
        extract_protenix_complex_confidence(
            summary_path=summary,
            full_confidence_path=full,
        )


def test_extract_complex_confidence_prefers_normalized_adapter_metrics(
    tmp_path: Path,
) -> None:
    structure = tmp_path / "prediction.cif"
    summary = tmp_path / "summary.json"
    full = tmp_path / "full.json"
    structure.write_text("data_prediction\n", encoding="utf-8")
    summary.write_text("{}\n", encoding="utf-8")
    full.write_text("{}\n", encoding="utf-8")
    normalized = ComplexConfidenceMetrics(
        metric_definition_version="openfold3-p2-af3-jax-complex-confidence-v1",
        pairwise_iptm=0.72,
        minimum_interface_pae_angstrom=7.5,
        binder_ptm=0.81,
        target_token_count=20,
        binder_token_count=10,
    )
    product = StructurePredictionProduct(
        backend_name="openfold3-af3-jax",
        backend_version="3.1.4",
        model_name="of3-p2-155k",
        seed=101,
        sample_index=0,
        structure_path=structure,
        structure_sha256="0" * 64,
        confidence_path=summary,
        confidence_sha256="1" * 64,
        full_confidence_path=full,
        full_confidence_sha256="2" * 64,
        plddt=85.0,
        gpde=None,
        ptm=0.78,
        iptm=0.72,
        ranking_score=0.74,
        has_clash=False,
        recycle_count=10,
        complex_confidence=normalized,
        native_metrics={"fraction_disordered": 0.03},
    )

    assert product.gpde is None
    assert product.mean_plddt == 85.0
    assert product.backend_identity == "openfold3-af3-jax@3.1.4"
    assert extract_complex_confidence(product) == normalized
