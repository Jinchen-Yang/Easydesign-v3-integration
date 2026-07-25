from __future__ import annotations

import json
from pathlib import Path

import pytest

from easydesign.core import ManifestStateError
from easydesign.filtering import extract_protenix_complex_confidence


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
