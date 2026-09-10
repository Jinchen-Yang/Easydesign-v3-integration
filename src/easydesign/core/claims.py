"""Typed scientific claim and evidence-governance contracts."""

from __future__ import annotations

from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .artifacts import ID_PATTERN, SHA256_PATTERN


class ClaimType(StrEnum):
    OBSERVATION = "observation"
    INFERENCE = "inference"
    HYPOTHESIS = "hypothesis"
    HUMAN_DECISION = "human_decision"
    EXTERNAL_FACT = "external_fact"


class ClaimStatus(StrEnum):
    PROPOSED = "proposed"
    VERIFIED = "verified"
    HUMAN_APPROVED = "human-approved"


class AssertionDomain(StrEnum):
    GENERAL = "general"
    COMPUTATIONAL_METRIC = "computational-metric"
    AFFINITY = "affinity"
    FUNCTION = "function"


class EvidenceKind(StrEnum):
    COMPUTATIONAL = "computational"
    EXPERIMENTAL_AFFINITY = "experimental-affinity"
    EXPERIMENTAL_FUNCTION = "experimental-function"
    EXTERNAL_SOURCE = "external-source"
    HUMAN_RECORD = "human-record"


class ClaimEvidenceRef(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    evidence_id: str = Field(pattern=ID_PATTERN)
    sha256: str = Field(pattern=SHA256_PATTERN)
    kind: EvidenceKind
    path: str | None = Field(default=None, min_length=1)


class ClaimReceipt(BaseModel):
    """A claim carries its epistemic role and exact supporting evidence."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: str = Field(default="1.0", pattern=r"^1\.0$")
    claim_id: str = Field(pattern=ID_PATTERN)
    claim_type: ClaimType
    statement: str = Field(min_length=1, max_length=8192)
    scope: str = Field(min_length=1, max_length=4096)
    assertion_domain: AssertionDomain = AssertionDomain.GENERAL
    evidence_refs: tuple[ClaimEvidenceRef, ...] = ()
    source_run_ids: tuple[str, ...] = ()
    analysis_identity: str | None = Field(default=None, min_length=1)
    limitations: tuple[str, ...] = ()
    contradictions: tuple[str, ...] = ()
    alternative_explanations: tuple[str, ...] = ()
    status: ClaimStatus = ClaimStatus.PROPOSED

    @model_validator(mode="after")
    def validate_evidence_boundary(self) -> Self:
        if self.claim_type is ClaimType.OBSERVATION:
            if not self.evidence_refs:
                raise ValueError("observation 必须引用真实 evidence")
            if self.status is ClaimStatus.PROPOSED:
                raise ValueError("observation 必须是 checksum-verified，而不是 proposed")
        elif self.status is ClaimStatus.VERIFIED:
            raise ValueError("只有 observation/external fact 可标记 verified")
        if self.claim_type is ClaimType.INFERENCE and not self.alternative_explanations:
            raise ValueError("inference 必须记录 alternative explanations")
        kinds = {reference.kind for reference in self.evidence_refs}
        if (
            self.claim_type is ClaimType.OBSERVATION
            and self.assertion_domain is AssertionDomain.AFFINITY
            and EvidenceKind.EXPERIMENTAL_AFFINITY not in kinds
        ):
            raise ValueError("affinity observation 必须有 experimental-affinity evidence")
        if (
            self.claim_type is ClaimType.OBSERVATION
            and self.assertion_domain is AssertionDomain.FUNCTION
            and EvidenceKind.EXPERIMENTAL_FUNCTION not in kinds
        ):
            raise ValueError("function observation 必须有 experimental-function evidence")
        return self


__all__ = [
    "AssertionDomain",
    "ClaimEvidenceRef",
    "ClaimReceipt",
    "ClaimStatus",
    "ClaimType",
    "EvidenceKind",
]
