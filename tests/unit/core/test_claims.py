from __future__ import annotations

import pytest
from pydantic import ValidationError

from easydesign.core import (
    AssertionDomain,
    ClaimEvidenceRef,
    ClaimReceipt,
    ClaimStatus,
    ClaimType,
    EvidenceKind,
)


def test_observation_without_evidence_is_rejected() -> None:
    with pytest.raises(ValidationError, match="observation 必须引用"):
        ClaimReceipt(
            claim_id="missing-evidence",
            claim_type=ClaimType.OBSERVATION,
            statement="A result occurred.",
            scope="run:test",
            status=ClaimStatus.VERIFIED,
        )


def test_computational_metric_cannot_be_promoted_to_affinity_observation() -> None:
    computational = ClaimEvidenceRef(
        evidence_id="filter-report",
        sha256="a" * 64,
        kind=EvidenceKind.COMPUTATIONAL,
    )
    with pytest.raises(ValidationError, match="experimental-affinity"):
        ClaimReceipt(
            claim_id="false-affinity",
            claim_type=ClaimType.OBSERVATION,
            statement="High affinity was observed.",
            scope="run:test",
            assertion_domain=AssertionDomain.AFFINITY,
            evidence_refs=(computational,),
            status=ClaimStatus.VERIFIED,
        )


def test_inference_is_typed_separately_and_carries_alternatives() -> None:
    inference = ClaimReceipt(
        claim_id="interpretation-one",
        claim_type=ClaimType.INFERENCE,
        statement="A medium loop may be preferred.",
        scope="pilot:test",
        alternative_explanations=("The scaffold rather than loop length may dominate.",),
    )

    assert inference.claim_type is ClaimType.INFERENCE
    assert inference.status is ClaimStatus.PROPOSED
