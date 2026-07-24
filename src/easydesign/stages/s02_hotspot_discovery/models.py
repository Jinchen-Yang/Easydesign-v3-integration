"""Stage 02 候选表面区域、逐残基证据和方法对比契约。"""

from __future__ import annotations

from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from easydesign.core.artifacts import ID_PATTERN, SHA256_PATTERN

STAGE_ID = "02-hotspot-discovery"


class RegionMethod(StrEnum):
    SASA_SURFACE_DIVERSITY = "sasa-surface-diversity"
    SCANNET_EPITOPE_NO_MSA = "scannet-epitope-no-msa"


class AnnotationStatus(StrEnum):
    NOT_IMPLEMENTED = "not_implemented"


class RegionReviewStatus(StrEnum):
    NEEDS_HUMAN_VISUAL_CONFIRMATION = "needs_human_visual_confirmation"
    INSUFFICIENT_SURFACE = "insufficient_surface_for_requested_regions"
    AWAITING_REGION_SELECTION = "awaiting_region_selection"


class ResidueIdentity(BaseModel):
    """Stage 01 编号映射在 Stage 02 中的不可歧义表示。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    sequence_index: int = Field(ge=1)
    amino_acid: str = Field(pattern=r"^[ACDEFGHIKLMNPQRSTVWY]$")
    label_asym_id: str = Field(min_length=1, max_length=16)
    label_seq_id: int = Field(ge=1)
    auth_asym_id: str = Field(min_length=1, max_length=16)
    auth_seq_id: str = Field(min_length=1, max_length=32)
    insertion_code: str | None = Field(default=None, max_length=8)


class ResidueEvidence(BaseModel):
    """一个方法对一个结构残基的原始证据；两种方法不共享分数。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    method: RegionMethod
    residue: ResidueIdentity
    raw_sasa: float | None = Field(default=None, ge=0)
    rsasa: float | None = Field(default=None, ge=0)
    scannet_probability: float | None = Field(default=None, ge=0, le=1)
    eligible: bool
    excluded_reasons: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_method_evidence(self) -> Self:
        if self.method is RegionMethod.SASA_SURFACE_DIVERSITY:
            if self.raw_sasa is None or self.rsasa is None:
                raise ValueError("SASA residue evidence 必须包含 raw_sasa 和 rsasa")
            if self.scannet_probability is not None:
                raise ValueError("SASA residue evidence 禁止包含 ScanNet 概率")
        else:
            if self.scannet_probability is None:
                raise ValueError("ScanNet residue evidence 必须包含原始概率")
            if self.raw_sasa is not None or self.rsasa is not None:
                raise ValueError("ScanNet residue evidence 禁止包含 SASA 分数")
        return self


class ResidueEvidenceReport(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: str = "0.1"
    method: RegionMethod
    method_version: str = Field(min_length=1, max_length=128)
    target_structure_sha256: str = Field(pattern=SHA256_PATTERN)
    annotation_status: AnnotationStatus = AnnotationStatus.NOT_IMPLEMENTED
    residues: tuple[ResidueEvidence, ...]

    @model_validator(mode="after")
    def validate_residues(self) -> Self:
        if not self.residues:
            raise ValueError("Residue evidence 不能为空")
        labels = [item.residue.label_seq_id for item in self.residues]
        if len(labels) != len(set(labels)):
            raise ValueError("Residue evidence label_seq_id 不能重复")
        if any(item.method is not self.method for item in self.residues):
            raise ValueError("Residue evidence method 必须与报告一致")
        return self


class RegionMetrics(BaseModel):
    """方法专属指标；字段为空表示该方法没有计算，不表示数值为零。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    mean_rsasa: float | None = Field(default=None, ge=0)
    q25_rsasa: float | None = Field(default=None, ge=0)
    graph_density: float | None = Field(default=None, ge=0, le=1)
    compactness_score: float | None = Field(default=None, ge=0, le=1)
    radius_gyration_angstrom: float = Field(ge=0)
    mean_scannet_probability: float | None = Field(default=None, ge=0, le=1)
    q25_scannet_probability: float | None = Field(default=None, ge=0, le=1)


class CandidateSurfaceRegion(BaseModel):
    """区域成员只描述几何边界，不代表 binding residues。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    region_id: str = Field(pattern=ID_PATTERN)
    method: RegionMethod
    seed_label_seq_id: int = Field(ge=1)
    members: tuple[ResidueIdentity, ...] = Field(min_length=1)
    centroid_angstrom: tuple[float, float, float]
    ranking_score: float
    metrics: RegionMetrics

    @model_validator(mode="after")
    def validate_members(self) -> Self:
        labels = [member.label_seq_id for member in self.members]
        if labels != sorted(labels) or len(labels) != len(set(labels)):
            raise ValueError("区域成员必须按 label_seq_id 排序且不能重复")
        if self.seed_label_seq_id not in labels:
            raise ValueError("区域 seed 必须属于 region_members")
        is_sasa = self.method is RegionMethod.SASA_SURFACE_DIVERSITY
        if is_sasa:
            required = (
                self.metrics.mean_rsasa,
                self.metrics.q25_rsasa,
                self.metrics.graph_density,
                self.metrics.compactness_score,
            )
            if any(value is None for value in required):
                raise ValueError("SASA 区域必须包含完整几何/SASA 指标")
            if self.metrics.mean_scannet_probability is not None:
                raise ValueError("SASA 区域禁止包含 ScanNet 指标")
        else:
            if (
                self.metrics.mean_scannet_probability is None
                or self.metrics.q25_scannet_probability is None
            ):
                raise ValueError("ScanNet 区域必须包含概率指标")
            if self.metrics.mean_rsasa is not None:
                raise ValueError("ScanNet 区域禁止包含 SASA 指标")
        return self


class CandidateRegionPool(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: str = "0.1"
    method: RegionMethod
    method_version: str = Field(min_length=1, max_length=128)
    requested_region_count: int = Field(ge=1)
    requested_member_count: int = Field(ge=1)
    selected_member_count: int | None = Field(default=None, ge=1)
    relaxation_tier: str | None = Field(default=None, pattern=ID_PATTERN)
    candidates: tuple[CandidateSurfaceRegion, ...]

    @model_validator(mode="after")
    def validate_candidates(self) -> Self:
        ids = [item.region_id for item in self.candidates]
        if len(ids) != len(set(ids)):
            raise ValueError("Candidate region_id 不能重复")
        if any(item.method is not self.method for item in self.candidates):
            raise ValueError("Candidate method 必须与候选池一致")
        return self


class PairwiseSeparation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    left_region_id: str = Field(pattern=ID_PATTERN)
    right_region_id: str = Field(pattern=ID_PATTERN)
    centroid_distance_angstrom: float = Field(ge=0)
    minimum_heavy_atom_distance_angstrom: float = Field(ge=0)


class RecommendedRegionSet(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: str = "0.1"
    method: RegionMethod
    status: RegionReviewStatus
    requested_region_count: int = Field(ge=1)
    relaxation_tier: str | None = Field(default=None, pattern=ID_PATTERN)
    regions: tuple[CandidateSurfaceRegion, ...]
    pairwise_separation: tuple[PairwiseSeparation, ...] = ()
    requires_human_confirmation: bool = True

    @model_validator(mode="after")
    def validate_recommendations(self) -> Self:
        if any(item.method is not self.method for item in self.regions):
            raise ValueError("Recommended region method 必须一致")
        if self.status is RegionReviewStatus.NEEDS_HUMAN_VISUAL_CONFIRMATION:
            if len(self.regions) != self.requested_region_count:
                raise ValueError("成功推荐必须达到 requested_region_count")
        elif len(self.regions) >= self.requested_region_count:
            raise ValueError("不足状态不能包含足量区域")
        if not self.requires_human_confirmation:
            raise ValueError("Stage 02 v0.1 禁止自动批准区域")
        return self


class RegionOverlap(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    sasa_region_id: str = Field(pattern=ID_PATTERN)
    scannet_region_id: str = Field(pattern=ID_PATTERN)
    shared_members: tuple[ResidueIdentity, ...]
    shared_member_count: int = Field(ge=0)
    jaccard_overlap: float = Field(ge=0, le=1)
    sasa_coverage: float = Field(ge=0, le=1)
    scannet_coverage: float = Field(ge=0, le=1)
    centroid_distance_angstrom: float = Field(ge=0)
    minimum_heavy_atom_distance_angstrom: float = Field(ge=0)


class MethodComparison(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: str = "0.1"
    comparison_type: str = Field(
        default="independent-region-overlap",
        pattern=r"^independent-region-overlap$",
    )
    fused_score: None = None
    winner: None = None
    overlaps: tuple[RegionOverlap, ...]
    best_matches: tuple[RegionOverlap, ...]


class ProviderExecutionStatus(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    method: RegionMethod
    status: str = Field(pattern=ID_PATTERN)
    message: str


class Stage02Report(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: str = "0.1"
    target_id: str = Field(pattern=ID_PATTERN)
    annotation_status: AnnotationStatus = AnnotationStatus.NOT_IMPLEMENTED
    pse_source_annotations_consumed: bool = False
    fused_ranking_generated: bool = False
    stage03_handoff: RegionReviewStatus = RegionReviewStatus.AWAITING_REGION_SELECTION
    providers: tuple[ProviderExecutionStatus, ...]
    warnings: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_boundaries(self) -> Self:
        if self.pse_source_annotations_consumed:
            raise ValueError("automatic Stage 02 禁止消费 PSE 颜色 annotation")
        if self.fused_ranking_generated:
            raise ValueError("Stage 02 v0.1 禁止融合排名")
        if self.stage03_handoff is not RegionReviewStatus.AWAITING_REGION_SELECTION:
            raise ValueError("人工批准前 Stage 03 必须等待区域选择")
        return self
