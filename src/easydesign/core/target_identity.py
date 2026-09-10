"""Deterministic four-layer Target Identity v2 alignment contracts."""

from __future__ import annotations

import hashlib
from enum import StrEnum
from typing import Literal, Self

from Bio.Align import PairwiseAligner
from pydantic import BaseModel, ConfigDict, Field, model_validator

from .artifacts import ID_PATTERN, SHA256_PATTERN

AMINO_ACIDS = frozenset("ACDEFGHIKLMNPQRSTVWY")
ALIGNMENT_ALGORITHM = "biopython-pairwise-global-v1"
ALIGNMENT_PARAMETERS = {
    "match_score": 2.0,
    "mismatch_score": -1.0,
    "open_gap_score": -4.0,
    "extend_gap_score": -0.5,
}


class CanonicalIdentityStatus(StrEnum):
    RESOLVED = "resolved"
    USER_DECLARED = "user-declared"
    UNRESOLVED = "unresolved"
    AMBIGUOUS = "ambiguous"


class ConstructRelationship(StrEnum):
    EXACT_NATIVE = "exact_native"
    EXACT_SUBSEQUENCE = "exact_subsequence"
    ENGINEERED_CONSTRUCT = "engineered_construct"
    ISOFORM = "isoform"
    ORTHOLOG = "ortholog"
    CHIMERA = "chimera"
    AMBIGUOUS = "ambiguous"
    MISMATCH = "mismatch"
    UNRESOLVED = "unresolved"


class MappingStatus(StrEnum):
    EXACT = "exact"
    UNIQUE_ALIGNED = "unique-aligned"
    REVIEW_REQUIRED = "review-required"
    AMBIGUOUS = "ambiguous"
    UNRESOLVED = "unresolved"


class ReviewRequirement(StrEnum):
    NONE = "none"
    HUMAN_REQUIRED = "human-required"
    REJECT = "reject"


class EditType(StrEnum):
    NATIVE = "native"
    SUBSTITUTION = "substitution"
    INSERTION = "insertion"
    DELETION = "deletion"
    UNRESOLVED = "unresolved"
    NOT_APPLICABLE = "not-applicable"


class CanonicalIdentity(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: CanonicalIdentityStatus
    accession: str | None = None
    isoform: str | None = None
    taxon_id: int | None = Field(default=None, ge=1)
    sequence_sha256: str | None = Field(default=None, pattern=SHA256_PATTERN)
    sequence_length: int | None = Field(default=None, ge=1)


class ExperimentalConstructIdentity(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    source_kind: Literal["pdb", "local-structure", "prediction", "sequence"]
    pdb_id: str | None = None
    entity_id: str | None = None
    auth_chain_id: str | None = None
    label_chain_id: str | None = None
    sequence_sha256: str = Field(pattern=SHA256_PATTERN)
    sequence_length: int = Field(ge=1)


class ObservedCoordinateIdentity(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    coordinate_frame: str = "construct-sequence"
    observed_construct_positions: tuple[int, ...] = ()
    missing_construct_positions: tuple[int, ...] = ()
    auth_numbering_available: bool = False
    label_numbering_available: bool = False


class SequenceEdit(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    edit_type: Literal["substitution", "insertion", "deletion"]
    canonical_position: int | None = Field(default=None, ge=1)
    canonical_residue: str | None = Field(default=None, pattern=r"^[A-Z]$")
    construct_position: int | None = Field(default=None, ge=1)
    construct_residue: str | None = Field(default=None, pattern=r"^[A-Z]$")


class DesignResidueMapping(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    design_position: int = Field(ge=1)
    design_residue: str = Field(pattern=r"^[ACDEFGHIKLMNPQRSTVWY]$")
    canonical_position: int | None = Field(default=None, ge=1)
    canonical_residue: str | None = Field(
        default=None,
        pattern=r"^[ACDEFGHIKLMNPQRSTVWY]$",
    )
    construct_position: int = Field(ge=1)
    construct_residue: str = Field(pattern=r"^[ACDEFGHIKLMNPQRSTVWY]$")
    coordinate_present: bool
    mapping_status: MappingStatus
    edit_type: EditType


class AlignmentIdentity(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    algorithm: str = ALIGNMENT_ALGORITHM
    parameters: dict[str, float] = Field(default_factory=lambda: dict(ALIGNMENT_PARAMETERS))
    alignment_score: float
    equally_optimal_mapping_count: int = Field(ge=1, le=2)
    sequence_identity: float = Field(ge=0, le=1)
    canonical_coverage: float = Field(ge=0, le=1)
    construct_coverage: float = Field(ge=0, le=1)
    substitutions: tuple[SequenceEdit, ...] = ()
    deletions: tuple[SequenceEdit, ...] = ()
    insertions: tuple[SequenceEdit, ...] = ()


class DesignScopeIdentity(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    coordinate_frame: str = "normalized-chain-A-label-seq-id"
    canonical_start: int | None = Field(default=None, ge=1)
    canonical_end: int | None = Field(default=None, ge=1)
    construct_start: int = Field(ge=1)
    construct_end: int = Field(ge=1)
    sequence: str = Field(min_length=1)
    sequence_sha256: str = Field(pattern=SHA256_PATTERN)
    mapping_status: MappingStatus
    residues: tuple[DesignResidueMapping, ...]
    artificial_surface_flags: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_scope(self) -> Self:
        if self.construct_end < self.construct_start:
            raise ValueError("construct scope end 不能小于 start")
        if self.canonical_start is not None and self.canonical_end is not None:
            if self.canonical_end < self.canonical_start:
                raise ValueError("canonical scope end 不能小于 start")
        if hashlib.sha256(self.sequence.encode("ascii")).hexdigest() != self.sequence_sha256:
            raise ValueError("design scope sequence SHA-256 不一致")
        if [item.design_position for item in self.residues] != list(
            range(1, len(self.residues) + 1)
        ):
            raise ValueError("design residue mapping 必须连续")
        if "".join(item.design_residue for item in self.residues) != self.sequence:
            raise ValueError("design residue mapping sequence 不一致")
        return self


class TargetIdentityReport(BaseModel):
    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        populate_by_name=True,
        serialize_by_alias=True,
    )

    schema_version: str = Field(default="0.2", pattern=r"^0\.2$")
    target_id: str = Field(pattern=ID_PATTERN)
    source_identity_status: Literal["resolved", "user-declared", "unresolved"]
    biological_identity_status: CanonicalIdentityStatus
    canonical: CanonicalIdentity
    construct_identity: ExperimentalConstructIdentity = Field(alias="construct")
    observed: ObservedCoordinateIdentity
    relationship: ConstructRelationship
    alignment: AlignmentIdentity | None = None
    design_scope: DesignScopeIdentity
    ambiguities: tuple[str, ...] = ()
    review_requirement: ReviewRequirement
    notes: tuple[str, ...] = ()


def _clean_sequence(value: str, *, label: str) -> str:
    sequence = "".join(value.split()).upper()
    invalid = sorted(set(sequence) - AMINO_ACIDS)
    if not sequence or invalid:
        raise ValueError(f"{label} 必须是非空 canonical amino-acid sequence: {invalid}")
    return sequence


def _hash(sequence: str) -> str:
    return hashlib.sha256(sequence.encode("ascii")).hexdigest()


def _unique_substring_mapping(
    canonical: str,
    construct: str,
) -> tuple[dict[int, int], bool] | None:
    if canonical == construct:
        return ({index: index for index in range(1, len(canonical) + 1)}, True)
    offset = canonical.find(construct)
    if offset >= 0:
        unique = offset == canonical.rfind(construct)
        return (
            {
                offset + index: index
                for index in range(1, len(construct) + 1)
            },
            unique,
        )
    offset = construct.find(canonical)
    if offset >= 0:
        unique = offset == construct.rfind(canonical)
        return (
            {
                index: offset + index
                for index in range(1, len(canonical) + 1)
            },
            unique,
        )
    return None


def _aligned_mapping(
    canonical: str,
    construct: str,
) -> tuple[dict[int, int], float, bool]:
    aligner = PairwiseAligner()  # type: ignore[no-untyped-call]
    aligner.mode = "global"
    for name, value in ALIGNMENT_PARAMETERS.items():
        setattr(aligner, name, value)
    alignments = aligner.align(canonical, construct)  # type: ignore[no-untyped-call]
    first = alignments[0]
    first_coordinates = tuple(
        tuple(int(value) for value in row) for row in first.coordinates
    )
    ambiguous = False
    try:
        second = alignments[1]
    except IndexError:
        second = None
    if second is not None:
        second_coordinates = tuple(
            tuple(int(value) for value in row) for row in second.coordinates
        )
        ambiguous = second_coordinates != first_coordinates
    mapping: dict[int, int] = {}
    canonical_coordinates, construct_coordinates = first_coordinates
    for index in range(len(canonical_coordinates) - 1):
        canonical_start = canonical_coordinates[index]
        canonical_end = canonical_coordinates[index + 1]
        construct_start = construct_coordinates[index]
        construct_end = construct_coordinates[index + 1]
        canonical_length = canonical_end - canonical_start
        construct_length = construct_end - construct_start
        if canonical_length == construct_length and canonical_length > 0:
            for offset in range(canonical_length):
                mapping[canonical_start + offset + 1] = construct_start + offset + 1
    return mapping, float(first.score), ambiguous


def resolve_target_identity(
    *,
    target_id: str,
    canonical_sequence: str | None,
    construct_sequence: str,
    canonical_status: CanonicalIdentityStatus = CanonicalIdentityStatus.RESOLVED,
    source_identity_status: Literal["resolved", "user-declared", "unresolved"] = "resolved",
    source_kind: Literal["pdb", "local-structure", "prediction", "sequence"] = "pdb",
    accession: str | None = None,
    isoform: str | None = None,
    taxon_id: int | None = None,
    pdb_id: str | None = None,
    entity_id: str | None = None,
    auth_chain_id: str | None = None,
    label_chain_id: str | None = None,
    canonical_scope_start: int | None = None,
    canonical_scope_end: int | None = None,
    coordinate_present_construct_positions: tuple[int, ...] | None = None,
    declared_relationship: ConstructRelationship | None = None,
) -> TargetIdentityReport:
    """Resolve a deterministic relationship and design-to-canonical residue map."""

    construct = _clean_sequence(construct_sequence, label="construct sequence")
    present = set(
        range(1, len(construct) + 1)
        if coordinate_present_construct_positions is None
        else coordinate_present_construct_positions
    )
    construct_identity = ExperimentalConstructIdentity(
        source_kind=source_kind,
        pdb_id=pdb_id,
        entity_id=entity_id,
        auth_chain_id=auth_chain_id,
        label_chain_id=label_chain_id,
        sequence_sha256=_hash(construct),
        sequence_length=len(construct),
    )
    observed = ObservedCoordinateIdentity(
        observed_construct_positions=tuple(sorted(present)),
        missing_construct_positions=tuple(
            index for index in range(1, len(construct) + 1) if index not in present
        ),
        auth_numbering_available=auth_chain_id is not None,
        label_numbering_available=label_chain_id is not None,
    )
    if canonical_sequence is None:
        residues = tuple(
            DesignResidueMapping(
                design_position=index,
                design_residue=residue,
                construct_position=index,
                construct_residue=residue,
                coordinate_present=index in present,
                mapping_status=MappingStatus.UNRESOLVED,
                edit_type=EditType.UNRESOLVED,
            )
            for index, residue in enumerate(construct, start=1)
        )
        scope = DesignScopeIdentity(
            construct_start=1,
            construct_end=len(construct),
            sequence=construct,
            sequence_sha256=_hash(construct),
            mapping_status=MappingStatus.UNRESOLVED,
            residues=residues,
        )
        return TargetIdentityReport(
            target_id=target_id,
            source_identity_status=source_identity_status,
            biological_identity_status=canonical_status,
            canonical=CanonicalIdentity(status=canonical_status),
            construct=construct_identity,
            observed=observed,
            relationship=ConstructRelationship.UNRESOLVED,
            design_scope=scope,
            ambiguities=("canonical-biological-sequence-unresolved",),
            review_requirement=ReviewRequirement.HUMAN_REQUIRED,
            notes=("PDB/source identity does not establish canonical biological identity",),
        )
    canonical = _clean_sequence(canonical_sequence, label="canonical sequence")
    requested_start = 1 if canonical_scope_start is None else canonical_scope_start
    requested_end = len(canonical) if canonical_scope_end is None else canonical_scope_end
    start = requested_start
    end = requested_end
    if start < 1 or end < start or end > len(canonical):
        raise ValueError("canonical design scope 超出 sequence")
    substring = _unique_substring_mapping(canonical, construct)
    score: float
    ambiguous: bool
    if substring is not None:
        mapping, unique = substring
        score = float(sum(canonical[c - 1] == construct[q - 1] for c, q in mapping.items()) * 2)
        ambiguous = not unique
    else:
        mapping, score, ambiguous = _aligned_mapping(canonical, construct)
    reverse = {
        construct_position: canonical_position
        for canonical_position, construct_position in mapping.items()
    }
    construct_is_native_subsequence = (
        canonical.find(construct) >= 0
        and canonical.find(construct) == canonical.rfind(construct)
    )
    if construct_is_native_subsequence:
        start = max(start, min(mapping))
        end = min(end, max(mapping))
    mapped_scope_positions = [
        mapping[position] for position in range(start, end + 1) if position in mapping
    ]
    paired = len(mapping)
    matches = sum(
        canonical[canonical_position - 1] == construct[construct_position - 1]
        for canonical_position, construct_position in mapping.items()
    )
    substitutions = tuple(
        SequenceEdit(
            edit_type="substitution",
            canonical_position=canonical_position,
            canonical_residue=canonical[canonical_position - 1],
            construct_position=construct_position,
            construct_residue=construct[construct_position - 1],
        )
        for canonical_position, construct_position in sorted(mapping.items())
        if canonical[canonical_position - 1] != construct[construct_position - 1]
    )
    deletions = tuple(
        SequenceEdit(
            edit_type="deletion",
            canonical_position=position,
            canonical_residue=canonical[position - 1],
        )
        for position in range(1, len(canonical) + 1)
        if position not in mapping
    )
    insertions = tuple(
        SequenceEdit(
            edit_type="insertion",
            construct_position=position,
            construct_residue=construct[position - 1],
        )
        for position in range(1, len(construct) + 1)
        if position not in reverse
    )
    alignment = AlignmentIdentity(
        alignment_score=score,
        equally_optimal_mapping_count=2 if ambiguous else 1,
        sequence_identity=0.0 if paired == 0 else matches / paired,
        canonical_coverage=paired / len(canonical),
        construct_coverage=paired / len(construct),
        substitutions=substitutions,
        deletions=deletions,
        insertions=insertions,
    )
    if not mapped_scope_positions:
        construct_start = 1
        construct_end = len(construct)
        mapping_status = MappingStatus.UNRESOLVED
        relationship = ConstructRelationship.MISMATCH
        review = ReviewRequirement.REJECT
    else:
        construct_start = min(mapped_scope_positions)
        construct_end = max(mapped_scope_positions)
        if ambiguous:
            mapping_status = MappingStatus.AMBIGUOUS
        elif substitutions or deletions or insertions:
            mapping_status = MappingStatus.UNIQUE_ALIGNED
        else:
            mapping_status = MappingStatus.EXACT
        if declared_relationship is not None:
            relationship = declared_relationship
        elif canonical == construct:
            relationship = ConstructRelationship.EXACT_NATIVE
        elif construct_is_native_subsequence and not ambiguous:
            relationship = ConstructRelationship.EXACT_SUBSEQUENCE
        elif substring is not None and not ambiguous:
            relationship = ConstructRelationship.ENGINEERED_CONSTRUCT
        elif ambiguous:
            relationship = ConstructRelationship.AMBIGUOUS
        elif alignment.sequence_identity < 0.3:
            relationship = ConstructRelationship.MISMATCH
        else:
            relationship = ConstructRelationship.ENGINEERED_CONSTRUCT
        review = ReviewRequirement.NONE
    design_sequence = construct[construct_start - 1 : construct_end]
    scope_residues: list[DesignResidueMapping] = []
    for design_position, construct_position in enumerate(
        range(construct_start, construct_end + 1),
        start=1,
    ):
        canonical_position = reverse.get(construct_position)
        canonical_residue = (
            None if canonical_position is None else canonical[canonical_position - 1]
        )
        construct_residue = construct[construct_position - 1]
        if canonical_position is None:
            edit_type = EditType.INSERTION
        elif canonical_residue == construct_residue:
            edit_type = EditType.NATIVE
        else:
            edit_type = EditType.SUBSTITUTION
        scope_residues.append(
            DesignResidueMapping(
                design_position=design_position,
                design_residue=construct_residue,
                canonical_position=canonical_position,
                canonical_residue=canonical_residue,
                construct_position=construct_position,
                construct_residue=construct_residue,
                coordinate_present=construct_position in present,
                mapping_status=mapping_status,
                edit_type=edit_type,
            )
        )
    scope_edits = any(
        item.canonical_position is not None and start <= item.canonical_position <= end
        for item in (*substitutions, *deletions)
    ) or any(
        construct_start <= (item.construct_position or 0) <= construct_end
        for item in insertions
    )
    artificial_flags: list[str] = []
    for item in insertions:
        position = item.construct_position or 0
        distance = min(abs(position - construct_start), abs(position - construct_end))
        if position < construct_start or position > construct_end:
            artificial_flags.append(
                "insertion-near-design-scope" if distance <= 5 else "insertion-outside-design-scope"
            )
    if relationship in {
        ConstructRelationship.ENGINEERED_CONSTRUCT,
        ConstructRelationship.ISOFORM,
        ConstructRelationship.ORTHOLOG,
        ConstructRelationship.CHIMERA,
        ConstructRelationship.AMBIGUOUS,
    } or scope_edits or "insertion-near-design-scope" in artificial_flags:
        review = ReviewRequirement.HUMAN_REQUIRED
    if relationship is ConstructRelationship.MISMATCH:
        review = ReviewRequirement.REJECT
    if any(not item.coordinate_present for item in scope_residues):
        review = ReviewRequirement.HUMAN_REQUIRED
    final_mapping_status = mapping_status
    if review is ReviewRequirement.HUMAN_REQUIRED and mapping_status not in {
        MappingStatus.AMBIGUOUS,
        MappingStatus.UNRESOLVED,
    }:
        final_mapping_status = MappingStatus.REVIEW_REQUIRED
        scope_residues = [
            item.model_copy(update={"mapping_status": final_mapping_status})
            for item in scope_residues
        ]
    scope = DesignScopeIdentity(
        canonical_start=start,
        canonical_end=end,
        construct_start=construct_start,
        construct_end=construct_end,
        sequence=design_sequence,
        sequence_sha256=_hash(design_sequence),
        mapping_status=final_mapping_status,
        residues=tuple(scope_residues),
        artificial_surface_flags=tuple(sorted(set(artificial_flags))),
    )
    ambiguities = (
        ("multiple-equally-optimal-sequence-alignments",) if ambiguous else ()
    )
    return TargetIdentityReport(
        target_id=target_id,
        source_identity_status=source_identity_status,
        biological_identity_status=canonical_status,
        canonical=CanonicalIdentity(
            status=canonical_status,
            accession=accession,
            isoform=isoform,
            taxon_id=taxon_id,
            sequence_sha256=_hash(canonical),
            sequence_length=len(canonical),
        ),
        construct=construct_identity,
        observed=observed,
        relationship=relationship,
        alignment=alignment,
        design_scope=scope,
        ambiguities=ambiguities,
        review_requirement=review,
    )


__all__ = [
    "ALIGNMENT_ALGORITHM",
    "ALIGNMENT_PARAMETERS",
    "CanonicalIdentity",
    "CanonicalIdentityStatus",
    "ConstructRelationship",
    "DesignResidueMapping",
    "DesignScopeIdentity",
    "EditType",
    "MappingStatus",
    "ReviewRequirement",
    "TargetIdentityReport",
    "resolve_target_identity",
]
