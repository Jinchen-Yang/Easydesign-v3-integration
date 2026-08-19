"""Typed contracts for GPCR-aware Stage 02 site analysis.

The GPCR dossier is richer than a generic ``CandidateSurfaceRegion``. It is
kept as an immutable scientific artifact and only projected into the existing
site-proposal contract after a researcher selects one hypothesis.
"""

from __future__ import annotations

import re
from datetime import datetime
from enum import StrEnum
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from easydesign.core.artifacts import SHA256_PATTERN


class GpcrDesignMode(StrEnum):
    INHIBIT = "inhibit"
    ACTIVATE = "activate"
    BOTH = "both"


class GpcrCandidateClassification(StrEnum):
    PRIMARY = "primary"
    BACKUP = "backup"
    AVOID = "avoid"
    UNRESOLVED = "unresolved"


class GpcrGateStatus(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    UNRESOLVED = "unresolved"


class GpcrConfidence(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNRESOLVED = "unresolved"


class GpcrResidueReference(BaseModel):
    """One residue with structure and optional GPCRdb numbering."""

    model_config = ConfigDict(frozen=True, extra="allow")

    key: str | None = None
    model_id: str | None = None
    chain_id: str | None = None
    auth_asym_id: str | None = None
    auth_seq_id: int | str | None = None
    insertion_code: str | None = None
    hetero_flag: str | None = None
    label_chain_id: str | None = None
    label_asym_id: str | None = None
    label_seq_id: int | None = Field(default=None, ge=1)
    sequence_index: int | None = Field(default=None, ge=1)
    amino_acid: str | None = None
    gpcrdb_sequence_number: int | None = Field(default=None, ge=1)
    sequence_number: int | None = Field(default=None, ge=1)
    generic_number: str | None = None
    gpcrdb_generic_number: str | None = None
    alternative_generic_numbers: tuple[dict[str, Any], ...] = ()
    protein_segment: str | None = None
    segment: str | None = None
    observed: bool | None = None
    mapping_status: str | None = None
    mapping_note: str | None = None
    membrane_facing: str | None = None
    functional_role: str | None = None
    evidence_ids: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_structure_identity(self) -> Self:
        chain = self.auth_asym_id or self.chain_id
        if self.auth_seq_id is not None and not chain:
            raise ValueError("auth_seq_id 必须同时保留 author chain")
        if self.label_seq_id is not None and not (
            self.label_asym_id or self.label_chain_id
        ):
            raise ValueError("label_seq_id 必须同时保留 label chain")
        return self


class GpcrHardGate(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(min_length=1, max_length=128)
    status: GpcrGateStatus
    reason: str | None = Field(default=None, max_length=2048)


class GpcrApproachChecks(BaseModel):
    model_config = ConfigDict(frozen=True, extra="allow")

    status: GpcrGateStatus
    required: tuple[str, ...] = ()
    binder_format: str | None = None
    access_side: str | None = None
    deep_cavity: bool | None = None
    framework_clearance: str | None = None
    allow_deep_cavity: bool | None = None


class GpcrSiteCandidate(BaseModel):
    """A mechanism hypothesis, not a fused numerical winner."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(min_length=1, max_length=256)
    mode: Literal["inhibit", "activate"]
    classification: GpcrCandidateClassification
    role: str = Field(min_length=1, max_length=256)
    hypothesis: str = Field(min_length=1, max_length=4096)
    functional_site: str = Field(min_length=1, max_length=4096)
    residues: tuple[GpcrResidueReference, ...] = ()
    target_state: str | None = None
    counterstate: str | None = None
    approach_direction: Any
    approach_checks: GpcrApproachChecks
    evidence_tier: str = Field(pattern=r"^(T1|T2|T3|T4|UNRESOLVED)$")
    evidence: tuple[dict[str, Any], ...] = ()
    evidence_ids: tuple[str, ...] = ()
    hard_gates: tuple[GpcrHardGate, ...] = ()
    risks: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()
    confidence: GpcrConfidence
    falsifier: str = Field(min_length=1, max_length=4096)
    assays: tuple[str, ...] = ()
    recommended_assays: tuple[str, ...] = ()
    geometry_metrics: dict[str, Any] = Field(default_factory=dict)
    sources: tuple[str, ...] = ()
    family_applicability: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_primary_gates(self) -> Self:
        if self.classification is not GpcrCandidateClassification.PRIMARY:
            return self
        if not self.residues:
            raise ValueError("primary GPCR candidate 必须包含 conditioning residues")
        if not self.hard_gates or any(
            gate.status is not GpcrGateStatus.PASS for gate in self.hard_gates
        ):
            raise ValueError("primary GPCR candidate 的 hard gates 必须全部通过")
        if self.approach_checks.status is not GpcrGateStatus.PASS:
            raise ValueError("primary GPCR candidate 必须通过完整 scaffold approach 检查")
        if not self.target_state or not self.counterstate:
            raise ValueError("primary GPCR candidate 必须声明 target/counterstate")
        if not self.assays:
            raise ValueError("primary GPCR candidate 必须声明可证伪 assay")
        return self


class GpcrCandidateCollection(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    inhibit: tuple[GpcrSiteCandidate, ...] = ()
    activate: tuple[GpcrSiteCandidate, ...] = ()

    @model_validator(mode="after")
    def validate_modes_and_ids(self) -> Self:
        if any(item.mode != "inhibit" for item in self.inhibit):
            raise ValueError("candidates.inhibit 只能包含 inhibit candidate")
        if any(item.mode != "activate" for item in self.activate):
            raise ValueError("candidates.activate 只能包含 activate candidate")
        for label, rows in (("inhibit", self.inhibit), ("activate", self.activate)):
            ids = [item.id for item in rows]
            if len(ids) != len(set(ids)):
                raise ValueError(f"candidates.{label} 的 id 不能重复")
        return self


class GpcrSiteAnalysis(BaseModel):
    """Canonical, immutable GPCR analysis used by handoff and reporting."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["1.0"] = "1.0"
    analysis_id: str = Field(min_length=1, max_length=256)
    generated_at: datetime
    mode: GpcrDesignMode
    structure: dict[str, Any]
    identity: dict[str, Any]
    topology: dict[str, Any]
    state: dict[str, Any]
    membrane: dict[str, Any]
    chain_graph: dict[str, Any]
    decision_context: dict[str, Any]
    residue_regions: tuple[dict[str, Any], ...] = ()
    candidates: GpcrCandidateCollection
    avoid: tuple[dict[str, Any], ...] = ()
    evidence: tuple[dict[str, Any], ...] = ()
    warnings: tuple[Any, ...] = ()
    provenance: dict[str, Any]
    analysis_notes: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_analysis_contract(self) -> Self:
        structure_sha = self.structure.get("sha256")
        if not isinstance(structure_sha, str) or re.fullmatch(
            SHA256_PATTERN, structure_sha
        ) is None:
            raise ValueError("structure.sha256 必须是小写 SHA-256")
        if not self.structure.get("path"):
            raise ValueError("structure.path 不能为空")
        if not self.structure.get("receptor_chain"):
            raise ValueError("structure.receptor_chain 不能为空")

        if self.mode is GpcrDesignMode.INHIBIT and self.candidates.activate:
            raise ValueError("inhibit analysis 不得发布 activate candidates")
        if self.mode is GpcrDesignMode.ACTIVATE and self.candidates.inhibit:
            raise ValueError("activate analysis 不得发布 inhibit candidates")

        primaries = tuple(
            item
            for item in (*self.candidates.inhibit, *self.candidates.activate)
            if item.classification is GpcrCandidateClassification.PRIMARY
        )
        if self.membrane.get("status") != "resolved" and primaries:
            raise ValueError("膜方向未解决时不得发布 primary GPCR candidate")
        if self.decision_context.get("status") != "resolved" and primaries:
            raise ValueError("decision context 未解决时不得发布 primary GPCR candidate")
        return self


__all__ = [
    "GpcrApproachChecks",
    "GpcrCandidateClassification",
    "GpcrCandidateCollection",
    "GpcrConfidence",
    "GpcrDesignMode",
    "GpcrGateStatus",
    "GpcrHardGate",
    "GpcrResidueReference",
    "GpcrSiteAnalysis",
    "GpcrSiteCandidate",
]
