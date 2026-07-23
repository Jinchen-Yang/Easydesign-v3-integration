"""裸蛋白序列和单记录 FASTA 的严格规范化。"""

from __future__ import annotations

import hashlib
from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from easydesign.core.artifacts import ID_PATTERN, SHA256_PATTERN
from easydesign.core.errors import SequenceInputError

CANONICAL_AMINO_ACIDS = frozenset("ACDEFGHIKLMNPQRSTVWY")


class SequenceSourceKind(StrEnum):
    RAW_SEQUENCE = "sequence"
    FASTA = "fasta"


class NormalizedProteinSequence(BaseModel):
    """与 FASTA 标题和输入空白无关的蛋白序列身份。"""

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    target_id: str = Field(pattern=ID_PATTERN)
    source_kind: SequenceSourceKind
    source_label: str = Field(min_length=1, max_length=512)
    sequence: str = Field(min_length=1)
    sequence_sha256: str = Field(pattern=SHA256_PATTERN)

    @model_validator(mode="after")
    def validate_sequence_identity(self) -> Self:
        invalid = sorted(set(self.sequence) - CANONICAL_AMINO_ACIDS)
        if invalid:
            raise ValueError(f"当前只接受 20 种标准氨基酸，发现: {''.join(invalid)}")
        expected = hashlib.sha256(self.sequence.encode("ascii")).hexdigest()
        if self.sequence_sha256 != expected:
            raise ValueError("sequence_sha256 与规范序列不一致")
        return self

    @property
    def length(self) -> int:
        return len(self.sequence)

    def to_fasta(self) -> str:
        return f">{self.target_id}\n{self.sequence}\n"


def _normalize_letters(text: str) -> str:
    sequence = "".join(text.split()).upper()
    if not sequence:
        raise SequenceInputError("蛋白序列不能为空")
    invalid = sorted(set(sequence) - CANONICAL_AMINO_ACIDS)
    if invalid:
        raise SequenceInputError(
            f"当前只接受 20 种标准氨基酸，发现: {''.join(invalid)}"
        )
    return sequence


def _build_sequence(
    *,
    target_id: str,
    source_kind: SequenceSourceKind,
    source_label: str,
    sequence_text: str,
) -> NormalizedProteinSequence:
    sequence = _normalize_letters(sequence_text)
    try:
        return NormalizedProteinSequence(
            target_id=target_id,
            source_kind=source_kind,
            source_label=source_label,
            sequence=sequence,
            sequence_sha256=hashlib.sha256(sequence.encode("ascii")).hexdigest(),
        )
    except ValidationError as error:
        raise SequenceInputError(f"序列身份字段不符合契约: {error}") from error


def normalize_raw_sequence(
    text: str,
    *,
    target_id: str,
    source_label: str = "inline-sequence",
) -> NormalizedProteinSequence:
    """规范化裸序列；FASTA 标题必须走 normalize_fasta。"""

    if any(line.lstrip().startswith(">") for line in text.splitlines()):
        raise SequenceInputError("裸序列输入不能包含 FASTA 标题")
    return _build_sequence(
        target_id=target_id,
        source_kind=SequenceSourceKind.RAW_SEQUENCE,
        source_label=source_label,
        sequence_text=text,
    )


def normalize_fasta(text: str, *, target_id: str) -> NormalizedProteinSequence:
    """规范化恰好一个有标题的 FASTA 记录。"""

    header: str | None = None
    sequence_lines: list[str] = []
    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith(">"):
            if header is not None:
                raise SequenceInputError("当前 sequence/FASTA 切片只接受一个 FASTA 记录")
            header = line[1:].strip()
            if not header:
                raise SequenceInputError(f"FASTA 第 {line_number} 行标题为空")
            continue
        if header is None:
            raise SequenceInputError("FASTA 序列必须位于标题行之后")
        sequence_lines.append(line)

    if header is None:
        raise SequenceInputError("FASTA 缺少标题行")
    if not sequence_lines:
        raise SequenceInputError("FASTA 记录没有序列")
    return _build_sequence(
        target_id=target_id,
        source_kind=SequenceSourceKind.FASTA,
        source_label=header,
        sequence_text="".join(sequence_lines),
    )
