"""Stage 01 Target Bundle 的首个机器契约。"""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from easydesign.backends.structure_prediction import (
    MsaMode,
    PredictionParameterProfile,
    TemplateMode,
)
from easydesign.backends.target_sources import SequenceSourceKind
from easydesign.core import ArtifactRef
from easydesign.core.artifacts import ATTEMPT_PATTERN, ID_PATTERN, SHA256_PATTERN

STAGE_ID = "01-target-preparation"


class TargetStructureOrigin(StrEnum):
    EXPERIMENTAL = "experimental"
    IMPORTED = "imported"
    PREDICTED = "predicted"


class ResidueMappingEntry(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    sequence_index: int = Field(ge=1)
    amino_acid: str = Field(pattern=r"^[ACDEFGHIKLMNPQRSTVWY]$")
    label_chain_id: str = Field(min_length=1, max_length=16)
    label_seq_id: int = Field(ge=1)
    author_chain_id: str = Field(min_length=1, max_length=16)
    author_residue_id: str = Field(min_length=1, max_length=32)
    insertion_code: str | None = Field(default=None, max_length=8)


class ResidueMapping(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: str = "0.1"
    target_id: str = Field(pattern=ID_PATTERN)
    sequence_sha256: str = Field(pattern=SHA256_PATTERN)
    entries: tuple[ResidueMappingEntry, ...]

    @model_validator(mode="after")
    def validate_mapping(self) -> Self:
        indices = [entry.sequence_index for entry in self.entries]
        if indices != list(range(1, len(self.entries) + 1)):
            raise ValueError("残基映射 sequence_index 必须从 1 连续递增")
        return self


class StructureQualityReport(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: str = "0.1"
    backend_name: str = Field(pattern=ID_PATTERN)
    backend_version: str = Field(min_length=1, max_length=128)
    model_name: str = Field(pattern=ID_PATTERN)
    seed: int = Field(ge=0)
    sample_index: int = Field(ge=0)
    plddt: float
    gpde: float
    ptm: float
    iptm: float
    ranking_score: float
    has_clash: bool
    recycle_count: int = Field(ge=0)


class PredictionProvenance(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: str = "0.1"
    source_kind: SequenceSourceKind
    source_label: str
    sequence_sha256: str = Field(pattern=SHA256_PATTERN)
    backend_name: str = Field(pattern=ID_PATTERN)
    backend_version: str = Field(min_length=1, max_length=128)
    model_name: str = Field(pattern=ID_PATTERN)
    model_checkpoint_sha256: str = Field(pattern=SHA256_PATTERN)
    msa_mode: MsaMode
    msa_input_sha256: str | None = Field(default=None, pattern=SHA256_PATTERN)
    msa_server_mode: str | None = Field(default=None, pattern=ID_PATTERN)
    template_mode: TemplateMode
    parameter_profile: PredictionParameterProfile
    resolved_cycle_count: int = Field(ge=1)
    resolved_diffusion_step_count: int = Field(ge=1)
    seed: int = Field(ge=0)
    sample_index: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_msa_evidence(self) -> Self:
        if self.msa_mode is MsaMode.DISABLED:
            if self.msa_input_sha256 is not None or self.msa_server_mode is not None:
                raise ValueError("disabled MSA 不能声明 MSA 产物或服务")
        elif self.msa_input_sha256 is None:
            raise ValueError("启用 MSA 时必须声明消费的 MSA input SHA-256")
        if self.msa_mode is MsaMode.REMOTE and self.msa_server_mode is None:
            raise ValueError("remote MSA 必须声明服务模式")
        return self


class TargetBundle(BaseModel):
    """Stage 02 可消费的规范 Target Bundle 引用集合。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: str = "0.1"
    target_id: str = Field(pattern=ID_PATTERN)
    origin: TargetStructureOrigin
    sequence_length: int = Field(ge=1)
    sequence_sha256: str = Field(pattern=SHA256_PATTERN)
    producer_attempt: str = Field(pattern=ATTEMPT_PATTERN)
    target_structure: ArtifactRef
    sequence: ArtifactRef
    residue_mapping: ArtifactRef
    quality_report: ArtifactRef
    provenance: ArtifactRef

    @model_validator(mode="after")
    def validate_artifact_producers(self) -> Self:
        artifacts = (
            self.target_structure,
            self.sequence,
            self.residue_mapping,
            self.quality_report,
            self.provenance,
        )
        for artifact in artifacts:
            if artifact.producer_stage != STAGE_ID:
                raise ValueError(f"Target Bundle artifact 必须由 {STAGE_ID} 产生")
            if artifact.producer_attempt != self.producer_attempt:
                raise ValueError("Target Bundle artifact 必须来自同一 attempt")
        return self


class BuiltTargetBundle(BaseModel):
    """写入完成后的 bundle 和 bundle 自身引用。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    bundle: TargetBundle
    bundle_path: Path
    bundle_artifact: ArtifactRef
