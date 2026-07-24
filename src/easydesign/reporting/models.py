"""Stage 01 便携式 Target Viewer 的机器契约。"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from easydesign.core import ArtifactRef, ErrorInfo, ExecutionStatus
from easydesign.core.artifacts import ID_PATTERN, SHA256_PATTERN
from easydesign.core.timestamps import normalize_aware_datetime

REPORT_ID = "stage01-target-viewer"
MOLSTAR_VERSION = "5.11.0"
GENERATOR_VERSION = "0.1"


class ViewerMetric(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    key: str = Field(pattern=ID_PATTERN)
    label: str = Field(min_length=1, max_length=128)
    value: str | int | float | bool


class ViewerResidue(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    sequence_index: int = Field(ge=1)
    amino_acid: str = Field(pattern=r"^[ACDEFGHIKLMNPQRSTVWY]$")
    label_asym_id: str = Field(min_length=1, max_length=16)
    label_seq_id: int = Field(ge=1)
    auth_asym_id: str = Field(min_length=1, max_length=16)
    auth_seq_id: str = Field(min_length=1, max_length=32)
    insertion_code: str | None = Field(default=None, max_length=8)
    pse_color_hex: str | None = Field(default=None, pattern=r"^#[0-9A-F]{6}$")


class ViewerColorCount(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    color_hex: str = Field(pattern=r"^#[0-9A-F]{6}$")
    residue_count: int = Field(ge=1)


class ViewerAnnotationSummary(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: Literal["available", "not_applicable"]
    annotation_type: str | None = Field(default=None, max_length=128)
    interpretation: Literal["uninterpreted"] | None = None
    color_counts: tuple[ViewerColorCount, ...] = ()

    @model_validator(mode="after")
    def validate_status(self) -> Self:
        if self.status == "available":
            if self.annotation_type is None or self.interpretation != "uninterpreted":
                raise ValueError("available annotation 必须声明类型和 uninterpreted")
            if not self.color_counts:
                raise ValueError("available annotation 必须声明颜色计数")
        elif (
            self.annotation_type is not None
            or self.interpretation is not None
            or self.color_counts
        ):
            raise ValueError("not_applicable annotation 不能伪造 annotation 数据")
        return self


class ViewerDownload(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    label: str = Field(min_length=1, max_length=128)
    relative_path: str = Field(pattern=r"^data/[a-z0-9][a-z0-9._-]*$")
    sha256: str = Field(pattern=SHA256_PATTERN)


class TargetViewerData(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: str = "0.1"
    target_id: str = Field(pattern=ID_PATTERN)
    origin: Literal["experimental", "imported", "predicted"]
    sequence_length: int = Field(ge=1)
    sequence_sha256: str = Field(pattern=SHA256_PATTERN)
    structure_relative_path: str = Field(
        default="data/target.cif",
        pattern=r"^data/target\.cif$",
    )
    structure_format: Literal["mmcif"] = "mmcif"
    structure_sha256: str = Field(pattern=SHA256_PATTERN)
    quality_metrics: tuple[ViewerMetric, ...]
    provenance_metrics: tuple[ViewerMetric, ...]
    annotation: ViewerAnnotationSummary
    residues: tuple[ViewerResidue, ...]
    downloads: tuple[ViewerDownload, ...]

    @model_validator(mode="after")
    def validate_residues(self) -> Self:
        if len(self.residues) != self.sequence_length:
            raise ValueError("Viewer residue 数量必须等于 sequence_length")
        indices = [residue.sequence_index for residue in self.residues]
        if indices != list(range(1, self.sequence_length + 1)):
            raise ValueError("Viewer residue sequence_index 必须从 1 连续递增")
        label_identities = [
            (residue.label_asym_id, residue.label_seq_id)
            for residue in self.residues
        ]
        if len(label_identities) != len(set(label_identities)):
            raise ValueError("Viewer residue label identity 不能重复")
        has_color = any(residue.pse_color_hex is not None for residue in self.residues)
        if (self.annotation.status == "available") != has_color:
            raise ValueError("Viewer annotation 状态与逐残基颜色不一致")
        return self


class TargetViewerReportManifest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    schema_version: str = "0.1"
    report_id: str = Field(default=REPORT_ID, pattern=r"^stage01-target-viewer$")
    revision: int = Field(ge=1)
    status: ExecutionStatus
    created_at: datetime
    completed_at: datetime
    generator_version: str = Field(default=GENERATOR_VERSION, min_length=1)
    viewer_name: str = Field(default="molstar", pattern=r"^molstar$")
    viewer_version: str = Field(default=MOLSTAR_VERSION, pattern=r"^5\.11\.0$")
    source_run_manifest_sha256: str | None = Field(default=None, pattern=SHA256_PATTERN)
    source_stage_manifest_sha256: str | None = Field(default=None, pattern=SHA256_PATTERN)
    source_target_bundle_sha256: str | None = Field(default=None, pattern=SHA256_PATTERN)
    source_target_structure_sha256: str | None = Field(
        default=None,
        pattern=SHA256_PATTERN,
    )
    output_artifacts: tuple[ArtifactRef, ...] = ()
    warnings: tuple[str, ...] = ()
    error: ErrorInfo | None = None

    @field_validator("created_at", "completed_at")
    @classmethod
    def normalize_datetime(cls, value: datetime) -> datetime:
        return normalize_aware_datetime(value)

    @model_validator(mode="after")
    def validate_manifest(self) -> Self:
        if self.status not in {ExecutionStatus.SUCCEEDED, ExecutionStatus.FAILED}:
            raise ValueError("Target Viewer report 必须是终态")
        if self.completed_at < self.created_at:
            raise ValueError("Target Viewer report 完成时间不能早于创建时间")
        sources = (
            self.source_run_manifest_sha256,
            self.source_stage_manifest_sha256,
            self.source_target_bundle_sha256,
            self.source_target_structure_sha256,
        )
        if self.status is ExecutionStatus.SUCCEEDED:
            if any(value is None for value in sources):
                raise ValueError("成功 report 必须声明完整 source identity")
            if self.error is not None or not self.output_artifacts:
                raise ValueError("成功 report 必须有输出且不能有错误")
        else:
            if self.error is None:
                raise ValueError("失败 report 必须记录 error")
            if self.output_artifacts:
                raise ValueError("失败 report 不能发布 output artifact")
        ids = [artifact.artifact_id for artifact in self.output_artifacts]
        if len(ids) != len(set(ids)):
            raise ValueError("Target Viewer report output artifact_id 不能重复")
        return self


class TargetViewerOutcome(BaseModel):
    """自动 reporting 的非科学结果；失败不改变 Stage 01 状态。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    status: ExecutionStatus
    report_root: Path
    manifest_path: Path
    entrypoint: Path | None = None
    error: ErrorInfo | None = None

    @model_validator(mode="after")
    def validate_outcome(self) -> Self:
        if self.status is ExecutionStatus.SUCCEEDED:
            if self.entrypoint is None or self.error is not None:
                raise ValueError("成功 Viewer outcome 必须有 entrypoint 且没有错误")
        elif self.status is ExecutionStatus.FAILED:
            if self.entrypoint is not None or self.error is None:
                raise ValueError("失败 Viewer outcome 必须有错误且没有 entrypoint")
        else:
            raise ValueError("Viewer outcome 必须是 succeeded 或 failed")
        return self
