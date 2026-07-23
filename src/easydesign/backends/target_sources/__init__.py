"""Target source adapters."""

from .sequence import (
    NormalizedProteinSequence,
    SequenceSourceKind,
    normalize_fasta,
    normalize_raw_sequence,
)

__all__ = [
    "NormalizedProteinSequence",
    "SequenceSourceKind",
    "normalize_fasta",
    "normalize_raw_sequence",
]
