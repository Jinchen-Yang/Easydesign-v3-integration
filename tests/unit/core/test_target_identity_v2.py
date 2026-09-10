from __future__ import annotations

import pytest

from easydesign.core import (
    CanonicalIdentityStatus,
    ConstructRelationship,
    MappingStatus,
    ReviewRequirement,
    resolve_target_identity,
)


def _resolve(canonical: str | None, construct: str, **kwargs: object):
    return resolve_target_identity(
        target_id="target-one",
        canonical_sequence=canonical,
        construct_sequence=construct,
        **kwargs,  # type: ignore[arg-type]
    )


def test_exact_native_and_unique_terminal_truncation_are_automatic() -> None:
    exact = _resolve("ACDEFGHIK", "ACDEFGHIK")
    truncation = _resolve("MACDEFGHIKL", "ACDEFGHIK")

    assert exact.relationship is ConstructRelationship.EXACT_NATIVE
    assert exact.review_requirement is ReviewRequirement.NONE
    assert exact.design_scope.mapping_status is MappingStatus.EXACT
    assert truncation.relationship is ConstructRelationship.EXACT_SUBSEQUENCE
    assert truncation.review_requirement is ReviewRequirement.NONE
    assert truncation.design_scope.canonical_start == 2
    assert truncation.design_scope.canonical_end == 10


@pytest.mark.parametrize(
    ("canonical", "construct"),
    (
        ("ACDEFGHIK", "ACNEFGHIK"),
        ("ACDEFGHIK", "ACDFGHIK"),
    ),
)
def test_engineered_substitution_or_deletion_requires_review(
    canonical: str,
    construct: str,
) -> None:
    report = _resolve(canonical, construct)

    assert report.relationship is ConstructRelationship.ENGINEERED_CONSTRUCT
    assert report.review_requirement is ReviewRequirement.HUMAN_REQUIRED
    assert report.design_scope.mapping_status is MappingStatus.REVIEW_REQUIRED
    assert report.alignment is not None
    assert report.alignment.substitutions or report.alignment.deletions


def test_fusion_is_recorded_and_not_silently_called_native() -> None:
    report = _resolve("ACDEFGHIK", "GGGGGGACDEFGHIK")

    assert report.relationship is ConstructRelationship.ENGINEERED_CONSTRUCT
    assert report.review_requirement is ReviewRequirement.HUMAN_REQUIRED
    assert report.alignment is not None and report.alignment.insertions
    assert "insertion-outside-design-scope" in report.design_scope.artificial_surface_flags


def test_insertion_outside_scope_and_insertion_in_scope_remain_distinct() -> None:
    outside = _resolve(
        "ACDEFGHIKLMNPQRSTVWY",
        "GGACDEFGHIKLMNPQRSTVWY",
        canonical_scope_start=10,
        canonical_scope_end=15,
    )
    in_scope = _resolve(
        "ACDEFGHIKLMNPQRSTVWY",
        "ACDEFGHIKLMANPQRSTVWY",
        canonical_scope_start=10,
        canonical_scope_end=15,
    )

    assert outside.design_scope.artificial_surface_flags == (
        "insertion-outside-design-scope",
    )
    assert outside.review_requirement is ReviewRequirement.HUMAN_REQUIRED
    assert any(
        residue.edit_type.value == "insertion" for residue in in_scope.design_scope.residues
    )
    assert in_scope.review_requirement is ReviewRequirement.HUMAN_REQUIRED


@pytest.mark.parametrize(
    "relationship",
    (
        ConstructRelationship.ISOFORM,
        ConstructRelationship.ORTHOLOG,
        ConstructRelationship.CHIMERA,
    ),
)
def test_declared_biological_relationships_remain_review_gated(
    relationship: ConstructRelationship,
) -> None:
    report = _resolve(
        "ACDEFGHIK",
        "ACNEFGHIK",
        declared_relationship=relationship,
    )

    assert report.relationship is relationship
    assert report.review_requirement is ReviewRequirement.HUMAN_REQUIRED


def test_ambiguous_alignment_and_missing_coordinates_fail_closed() -> None:
    ambiguous = _resolve("ACACAC", "ACAC")
    missing = _resolve(
        "ACDEFG",
        "ACDEFG",
        coordinate_present_construct_positions=(1, 2, 3, 5, 6),
    )

    assert ambiguous.relationship is ConstructRelationship.AMBIGUOUS
    assert ambiguous.design_scope.mapping_status is MappingStatus.AMBIGUOUS
    assert ambiguous.review_requirement is ReviewRequirement.HUMAN_REQUIRED
    assert missing.review_requirement is ReviewRequirement.HUMAN_REQUIRED
    assert missing.observed.missing_construct_positions == (4,)


def test_pdb_source_identity_does_not_claim_canonical_biological_identity() -> None:
    report = _resolve(
        None,
        "ACDEFG",
        canonical_status=CanonicalIdentityStatus.UNRESOLVED,
        source_identity_status="resolved",
        source_kind="pdb",
        pdb_id="1ABC",
        entity_id="1",
    )

    payload = report.model_dump(mode="json")
    assert payload["construct"]["pdb_id"] == "1ABC"
    assert report.source_identity_status == "resolved"
    assert report.biological_identity_status is CanonicalIdentityStatus.UNRESOLVED
    assert report.relationship is ConstructRelationship.UNRESOLVED
    assert report.review_requirement is ReviewRequirement.HUMAN_REQUIRED
