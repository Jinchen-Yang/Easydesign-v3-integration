"""可选 UniProt 证据映射；不得参与 SASA/ScanNet 原始排名。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from easydesign.backends.uniprot import FetchedUniProtRecord
from easydesign.stages.s01_target_preparation import ResidueMapping

from .models import (
    AnnotationReport,
    AnnotationStatus,
    EvidenceLevel,
    IdentityResolutionStatus,
    MappedAnnotationFeature,
    SequenceMotifWarning,
)

FEATURE_TYPES = frozenset(
    {
        "Active site",
        "Binding site",
        "Chain",
        "Disulfide bond",
        "Domain",
        "Glycosylation",
        "Lipidation",
        "Metal binding",
        "Modified residue",
        "Propeptide",
        "Region",
        "Signal peptide",
        "Site",
        "Topological domain",
        "Transmembrane",
    }
)


class UniProtFetcher(Protocol):
    def fetch(self, accession: str) -> FetchedUniProtRecord: ...


@dataclass(frozen=True, slots=True)
class SequenceMapping:
    target_to_uniprot: dict[int, int]
    coverage: float
    identity: float
    mismatches: tuple[str, ...]
    unique: bool


def sequence_motif_warnings(sequence: str) -> tuple[SequenceMotifWarning, ...]:
    """报告 N-X-[ST] 序列 motif，不解释为实际 PTM。"""

    return tuple(
        SequenceMotifWarning(label_seq_ids=(index + 1, index + 2, index + 3))
        for index in range(len(sequence) - 2)
        if sequence[index] == "N"
        and sequence[index + 1] != "P"
        and sequence[index + 2] in {"S", "T"}
    )


def align_target_to_uniprot(
    target: str,
    canonical: str,
) -> SequenceMapping:
    """半全局比对：完整消费 target，UniProt 前后端 gap 免费。"""

    if not target or not canonical:
        raise ValueError("target 和 UniProt canonical sequence 不能为空")
    match_score = 2
    mismatch_score = -1
    gap_score = -2
    target_length = len(target)
    traces = [bytearray(target_length + 1) for _ in range(len(canonical) + 1)]
    previous_scores = [gap_score * index for index in range(target_length + 1)]
    previous_counts = [1] * (target_length + 1)
    for index in range(1, target_length + 1):
        traces[0][index] = 3
    end_scores = [previous_scores[target_length]]
    end_counts = [previous_counts[target_length]]
    for canonical_index, canonical_aa in enumerate(canonical, start=1):
        scores = [0] + [0] * target_length
        counts = [1] + [0] * target_length
        traces[canonical_index][0] = 2
        for target_index, target_aa in enumerate(target, start=1):
            candidates = (
                (
                    previous_scores[target_index - 1]
                    + (
                        match_score
                        if canonical_aa == target_aa
                        else mismatch_score
                    ),
                    previous_counts[target_index - 1],
                    1,
                ),
                (
                    previous_scores[target_index] + gap_score,
                    previous_counts[target_index],
                    2,
                ),
                (
                    scores[target_index - 1] + gap_score,
                    counts[target_index - 1],
                    3,
                ),
            )
            best = max(item[0] for item in candidates)
            winners = [item for item in candidates if item[0] == best]
            path_count = min(2, sum(item[1] for item in winners))
            scores[target_index] = best
            counts[target_index] = path_count
            traces[canonical_index][target_index] = (
                winners[0][2] if path_count == 1 else 0
            )
        previous_scores = scores
        previous_counts = counts
        end_scores.append(scores[target_length])
        end_counts.append(counts[target_length])

    best_end_score = max(end_scores)
    best_ends = [
        index for index, score in enumerate(end_scores) if score == best_end_score
    ]
    unique = (
        len(best_ends) == 1
        and end_counts[best_ends[0]] == 1
    )
    if not unique:
        return SequenceMapping(
            target_to_uniprot={},
            coverage=0.0,
            identity=0.0,
            mismatches=(),
            unique=False,
        )

    canonical_index = best_ends[0]
    target_index = target_length
    mapping: dict[int, int] = {}
    mismatches: list[str] = []
    matches = 0
    while target_index > 0:
        direction = traces[canonical_index][target_index]
        if direction == 1:
            mapping[target_index] = canonical_index
            if target[target_index - 1] == canonical[canonical_index - 1]:
                matches += 1
            else:
                mismatches.append(
                    f"target:{target_index}={target[target_index - 1]},"
                    f"uniprot:{canonical_index}={canonical[canonical_index - 1]}"
                )
            canonical_index -= 1
            target_index -= 1
        elif direction == 2:
            canonical_index -= 1
        elif direction == 3:
            target_index -= 1
        else:
            return SequenceMapping(
                target_to_uniprot={},
                coverage=0.0,
                identity=0.0,
                mismatches=(),
                unique=False,
            )
    coverage = len(mapping) / target_length
    identity = matches / max(1, len(mapping))
    return SequenceMapping(
        target_to_uniprot=mapping,
        coverage=coverage,
        identity=identity,
        mismatches=tuple(reversed(mismatches)),
        unique=True,
    )


def _feature_position(value: object) -> int | None:
    if isinstance(value, dict):
        position = value.get("value")
        if isinstance(position, int):
            return position
    return None


def _evidence_codes(feature: dict[str, object]) -> tuple[str, ...]:
    raw = feature.get("evidences")
    if not isinstance(raw, list):
        return ()
    values = {
        str(item["evidenceCode"])
        for item in raw
        if isinstance(item, dict) and item.get("evidenceCode")
    }
    return tuple(sorted(values))


def _mapped_features(
    payload: dict[str, object],
    mapping: SequenceMapping,
    sequence_to_label: dict[int, int],
) -> tuple[MappedAnnotationFeature, ...]:
    inverse = {
        uniprot_position: sequence_to_label[target_position]
        for target_position, uniprot_position in mapping.target_to_uniprot.items()
    }
    raw_features = payload.get("features")
    if not isinstance(raw_features, list):
        return ()
    result = []
    for raw in raw_features:
        if not isinstance(raw, dict):
            continue
        feature: dict[str, object] = raw
        feature_type = feature.get("type")
        location = feature.get("location")
        if feature_type not in FEATURE_TYPES or not isinstance(location, dict):
            continue
        start = _feature_position(location.get("start"))
        end = _feature_position(location.get("end"))
        if start is None or end is None:
            continue
        labels = tuple(
            sorted(
                inverse[position]
                for position in range(start, end + 1)
                if position in inverse
            )
        )
        if not labels:
            continue
        description = feature.get("description")
        result.append(
            MappedAnnotationFeature(
                feature_type=str(feature_type),
                description=(
                    str(description)[:1024]
                    if description is not None
                    else None
                ),
                uniprot_start=start,
                uniprot_end=end,
                label_seq_ids=labels,
                evidence_codes=_evidence_codes(feature),
            )
        )
    return tuple(
        sorted(
            result,
            key=lambda item: (
                item.uniprot_start,
                item.uniprot_end,
                item.feature_type,
            ),
        )
    )


def build_annotation_report(
    *,
    target_sequence: str,
    residue_mapping: ResidueMapping,
    accession: str | None,
    fetcher: UniProtFetcher | None,
) -> AnnotationReport:
    sequence_to_label = {
        entry.sequence_index: entry.label_seq_id
        for entry in residue_mapping.entries
    }
    motifs = tuple(
        warning.model_copy(
            update={
                "label_seq_ids": tuple(
                    sequence_to_label[position]
                    for position in warning.label_seq_ids
                )
            }
        )
        for warning in sequence_motif_warnings(target_sequence)
    )
    if accession is None:
        return AnnotationReport(
            status=AnnotationStatus.NOT_REQUESTED,
            evidence_level=EvidenceLevel.STRUCTURAL_ONLY,
            identity_resolution=IdentityResolutionStatus.NOT_ATTEMPTED,
            motif_warnings=motifs,
        )
    if fetcher is None:
        raise ValueError("提供 UniProt accession 时必须提供 fetcher")
    try:
        record = fetcher.fetch(accession)
        sequence_payload = record.payload.get("sequence")
        if not isinstance(sequence_payload, dict):
            raise ValueError("UniProt record 缺少 sequence")
        canonical_value = sequence_payload.get("value")
        if not isinstance(canonical_value, str) or not canonical_value:
            raise ValueError("UniProt record sequence.value 无效")
        canonical = canonical_value.strip().upper()
        alignment = align_target_to_uniprot(target_sequence, canonical)
        if (
            not alignment.unique
            or alignment.coverage < 0.95
            or alignment.identity < 0.90
        ):
            return AnnotationReport(
                status=AnnotationStatus.MAPPING_REQUIRES_REVIEW,
                evidence_level=EvidenceLevel.STRUCTURAL_ONLY,
                identity_resolution=(
                    IdentityResolutionStatus.MAPPING_REQUIRES_REVIEW
                ),
                accession=accession,
                source_url=record.source_url,
                source_sha256=record.source_sha256,
                uniprot_release=record.uniprot_release,
                canonical_sequence_length=len(canonical),
                target_coverage=alignment.coverage,
                sequence_identity=alignment.identity,
                sequence_mismatches=alignment.mismatches,
                motif_warnings=motifs,
                error="UniProt 到 target 的编号映射不唯一或低于阈值",
            )
        labels = {entry.sequence_index for entry in residue_mapping.entries}
        if not set(alignment.target_to_uniprot).issubset(labels):
            raise ValueError("序列比对位置不属于 residue mapping")
        return AnnotationReport(
            status=AnnotationStatus.SUCCEEDED,
            evidence_level=EvidenceLevel.STRUCTURAL_WITH_ANNOTATION,
            identity_resolution=IdentityResolutionStatus.EXPLICIT_ACCESSION,
            accession=accession,
            source_url=record.source_url,
            source_sha256=record.source_sha256,
            uniprot_release=record.uniprot_release,
            canonical_sequence_length=len(canonical),
            target_coverage=alignment.coverage,
            sequence_identity=alignment.identity,
            sequence_mismatches=alignment.mismatches,
            mapped_features=_mapped_features(
                record.payload,
                alignment,
                sequence_to_label,
            ),
            motif_warnings=motifs,
        )
    except Exception as error:
        return AnnotationReport(
            status=AnnotationStatus.FAILED,
            evidence_level=EvidenceLevel.STRUCTURAL_ONLY,
            identity_resolution=IdentityResolutionStatus.EXPLICIT_ACCESSION,
            accession=accession,
            motif_warnings=motifs,
            error=str(error)[:4096] or type(error).__name__,
        )
