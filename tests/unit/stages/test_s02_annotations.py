from __future__ import annotations

from easydesign.backends.uniprot import FetchedUniProtRecord
from easydesign.stages.s01_target_preparation import (
    ResidueMapping,
    ResidueMappingEntry,
)
from easydesign.stages.s02_hotspot_discovery import (
    AnnotationStatus,
    EvidenceLevel,
    build_annotation_report,
)


def mapping(sequence: str) -> ResidueMapping:
    return ResidueMapping(
        target_id="target",
        sequence_sha256="a" * 64,
        entries=tuple(
            ResidueMappingEntry(
                sequence_index=index,
                amino_acid=amino_acid,
                label_chain_id="A",
                label_seq_id=index,
                author_chain_id="A",
                author_residue_id=str(index + 10),
            )
            for index, amino_acid in enumerate(sequence, start=1)
        ),
    )


class NeverFetch:
    calls = 0

    def fetch(self, accession: str) -> FetchedUniProtRecord:
        self.calls += 1
        raise AssertionError(f"unexpected network request: {accession}")


class StaticFetch:
    def __init__(self, sequence: str) -> None:
        self.sequence = sequence

    def fetch(self, accession: str) -> FetchedUniProtRecord:
        return FetchedUniProtRecord(
            accession=accession,
            source_url=f"https://example.test/{accession}.json",
            source_sha256="b" * 64,
            uniprot_release="2026_03",
            payload={
                "primaryAccession": accession,
                "sequence": {"value": self.sequence},
                "features": [
                    {
                        "type": "Active site",
                        "description": "catalytic test site",
                        "location": {
                            "start": {"value": 2},
                            "end": {"value": 2},
                        },
                        "evidences": [{"evidenceCode": "ECO:0000269"}],
                    }
                ],
            },
        )


def test_missing_accession_performs_no_fetch_and_reports_structural_only() -> None:
    sequence = "ANSTA"
    fetcher = NeverFetch()

    report = build_annotation_report(
        target_sequence=sequence,
        residue_mapping=mapping(sequence),
        accession=None,
        fetcher=fetcher,
    )

    assert fetcher.calls == 0
    assert report.status is AnnotationStatus.NOT_REQUESTED
    assert report.evidence_level is EvidenceLevel.STRUCTURAL_ONLY
    assert report.identity_resolution == "not_attempted"
    assert report.motif_warnings[0].label_seq_ids == (2, 3, 4)


def test_explicit_accession_maps_features_without_changing_structural_data() -> None:
    sequence = "ACDEFG"

    report = build_annotation_report(
        target_sequence=sequence,
        residue_mapping=mapping(sequence),
        accession="P12345",
        fetcher=StaticFetch(sequence),
    )

    assert report.status is AnnotationStatus.SUCCEEDED
    assert report.evidence_level is EvidenceLevel.STRUCTURAL_WITH_ANNOTATION
    assert report.target_coverage == 1.0
    assert report.sequence_identity == 1.0
    assert report.mapped_features[0].label_seq_ids == (2,)
    assert report.mapped_features[0].evidence_codes == ("ECO:0000269",)


def test_low_identity_mapping_requires_review_instead_of_guessing() -> None:
    sequence = "ACDEFG"

    report = build_annotation_report(
        target_sequence=sequence,
        residue_mapping=mapping(sequence),
        accession="P12345",
        fetcher=StaticFetch("YYYYYY"),
    )

    assert report.status is AnnotationStatus.MAPPING_REQUIRES_REVIEW
    assert report.evidence_level is EvidenceLevel.STRUCTURAL_ONLY
    assert report.mapped_features == ()
