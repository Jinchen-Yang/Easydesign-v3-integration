from __future__ import annotations

import json
from pathlib import Path

import pytest

from easydesign.backends.target_sources import (
    SequenceSourceKind,
    normalize_fasta,
    normalize_raw_sequence,
)
from easydesign.core import SequenceInputError

APOE_SEQUENCE = (
    "GQRWELALGRFWDYLRWVQTLSEQVQEELLSSQVTQELRALMDETMKELKAYKSELEEQLTPVAEETR"
    "ARLSKELQAAQARLGADMEDVRGRLVQYRGEVQAMLGQSTEELRVRLASHLRKLRKRLLRDADDLQKRL"
    "AVYQAG"
)
ROOT = Path(__file__).resolve().parents[3]


def test_raw_and_fasta_have_same_sequence_identity() -> None:
    raw = normalize_raw_sequence(
        APOE_SEQUENCE.lower(),
        target_id="apoe4-fragment-41-183",
    )
    fasta = normalize_fasta(
        f">source-specific title\n{APOE_SEQUENCE[:70]}\n{APOE_SEQUENCE[70:]}\n",
        target_id="apoe4-fragment-41-183",
    )

    assert raw.source_kind is SequenceSourceKind.RAW_SEQUENCE
    assert fasta.source_kind is SequenceSourceKind.FASTA
    assert raw.sequence == fasta.sequence == APOE_SEQUENCE
    assert raw.sequence_sha256 == fasta.sequence_sha256
    assert raw.length == 143


def test_committed_apoe_fixture_matches_its_source_record() -> None:
    input_dir = ROOT / "examples/stage01-apoe"
    normalized = normalize_fasta(
        (input_dir / "apoe4-fragment-41-183.fasta").read_text(encoding="utf-8"),
        target_id="apoe4-fragment-41-183",
    )
    source = json.loads((input_dir / "source.json").read_text(encoding="utf-8"))

    assert normalized.sequence == APOE_SEQUENCE
    assert normalized.length == source["sequence_length"]
    assert normalized.sequence_sha256 == source["sequence_sha256"]


@pytest.mark.parametrize(
    "text, message",
    [
        (">first\nACDE\n>second\nFGHI\n", "只接受一个"),
        ("ACDE", "标题"),
        (">\nACDE", "标题为空"),
        (">first\n", "没有序列"),
    ],
)
def test_fasta_rejects_ambiguous_or_incomplete_records(
    text: str,
    message: str,
) -> None:
    with pytest.raises(SequenceInputError, match=message):
        normalize_fasta(text, target_id="target")


def test_sequence_rejects_noncanonical_amino_acid() -> None:
    with pytest.raises(SequenceInputError, match="标准氨基酸"):
        normalize_raw_sequence("ACDEX", target_id="target")


def test_raw_sequence_rejects_fasta_header() -> None:
    with pytest.raises(SequenceInputError, match="FASTA 标题"):
        normalize_raw_sequence(">target\nACDE", target_id="target")


def test_sequence_rejects_invalid_target_id_with_stable_error() -> None:
    with pytest.raises(SequenceInputError, match="身份字段"):
        normalize_raw_sequence("ACDE", target_id="INVALID TARGET")
