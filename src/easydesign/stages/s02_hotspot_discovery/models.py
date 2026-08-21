"""Stage 02 候选表面区域、逐残基证据和方法对比契约。"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from easydesign.core.artifacts import ID_PATTERN, SHA256_PATTERN

STAGE_ID = "02-hotspot-discovery"


class RegionMethod(StrEnum):
    SASA_SURFACE_DIVERSITY = "sasa-surface-diversity"
    SCANNET_EPITOPE_NO_MSA = "scannet-epitope-no-msa"


class AnnotationStatus(StrEnum):
    NOT_IMPLEMENTED = "not_implemented"
    NOT_REQUESTED = "not_requested"
    SUCCEEDED = "succeeded"
    PARTIAL = "partial"
    MAPPING_REQUIRES_REVIEW = "mapping_requires_review"
    FAILED = "failed"


class EvidenceLevel(StrEnum):
    STRUCTURAL_ONLY = "structural_only"
    STRUCTURAL_WITH_ANNOTATION = "structural_with_annotation"


class IdentityResolutionStatus(StrEnum):
    NOT_ATTEMPTED = "not_attempted"
    EXPLICIT_ACCESSION = "explicit_accession"
    MAPPING_REQUIRES_REVIEW = "mapping_requires_review"


class RegionReviewStatus(StrEnum):
    NEEDS_HUMAN_VISUAL_CONFIRMATION = "needs_human_visual_confirmation"
    INSUFFICIENT_SURFACE = "insufficient_surface_for_requested_regions"
    AWAITING_REGION_SELECTION = "awaiting_region_selection"


class DesignGoal(StrEnum):
    BLOCKING = "blocking"
    AFFINITY_SUPPORT = "affinity_support"
    NONBLOCKING = "nonblocking"
    DETECTION = "detection"
    IMAGING = "imaging"
    EXPLORATORY = "exploratory"


class ResidueIdentity(BaseModel):
    """Stage 01 编号映射在 Stage 02 中的不可歧义表示。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    sequence_index: int = Field(ge=1)
    amino_acid: str = Field(pattern=r"^[ACDEFGHIKLMNPQRSTVWY]$")
    label_asym_id: str = Field(min_length=1, max_length=16)
    label_seq_id: int = Field(ge=1)
    auth_asym_id: str = Field(min_length=1, max_length=16)
    auth_seq_id: str = Field(min_length=1, max_length=32)
    source_auth_asym_id: str | None = Field(default=None, max_length=16)
    source_auth_seq_id: str | None = Field(default=None, max_length=32)
    insertion_code: str | None = Field(default=None, max_length=8)

    @model_validator(mode="after")
    def validate_source_author_identity(self) -> Self:
        if (self.source_auth_asym_id is None) != (self.source_auth_seq_id is None):
            raise ValueError(
                "source PDB author identity 必须同时包含 chain 和 residue id"
            )
        return self

    @property
    def preferred_author_identity(self) -> tuple[str, str]:
        """Return source-PDB identity when available, otherwise normalized identity."""

        return (
            self.source_auth_asym_id or self.auth_asym_id,
            self.source_auth_seq_id or self.auth_seq_id,
        )


class ResidueModelEvidence(BaseModel):
    """单个 coordinate model 对一个残基的 SASA/存在证据。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    model_id: str = Field(min_length=1, max_length=32)
    present: bool
    raw_sasa: float | None = Field(default=None, ge=0)
    rsasa: float | None = Field(default=None, ge=0)
    exposed_default: bool = False
    exposed_relaxed: bool = False

    @model_validator(mode="after")
    def validate_presence(self) -> Self:
        if self.present and (self.raw_sasa is None or self.rsasa is None):
            raise ValueError("present model evidence 必须包含 SASA/rSASA")
        if not self.present and (
            self.raw_sasa is not None
            or self.rsasa is not None
            or self.exposed_default
            or self.exposed_relaxed
        ):
            raise ValueError("缺失模型残基不得伪造 SASA 或暴露状态")
        return self


class MappedAnnotationFeature(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    feature_type: str = Field(min_length=1, max_length=64)
    description: str | None = Field(default=None, max_length=1024)
    uniprot_start: int = Field(ge=1)
    uniprot_end: int = Field(ge=1)
    label_seq_ids: tuple[int, ...]
    evidence_codes: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_range(self) -> Self:
        if self.uniprot_end < self.uniprot_start:
            raise ValueError("UniProt feature end 不能小于 start")
        if tuple(sorted(set(self.label_seq_ids))) != self.label_seq_ids:
            raise ValueError("annotation label_seq_ids 必须升序且唯一")
        return self


class SequenceMotifWarning(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    motif_type: str = Field(default="n-x-s-t", pattern=r"^n-x-s-t$")
    label_seq_ids: tuple[int, int, int]
    interpretation: str = Field(
        default="sequence-motif-only",
        pattern=r"^sequence-motif-only$",
    )


class AnnotationReport(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: str = "0.1"
    status: AnnotationStatus
    evidence_level: EvidenceLevel
    identity_resolution: IdentityResolutionStatus
    accession: str | None = None
    source_url: str | None = None
    source_sha256: str | None = Field(default=None, pattern=SHA256_PATTERN)
    uniprot_release: str | None = None
    canonical_sequence_length: int | None = Field(default=None, ge=1)
    target_coverage: float | None = Field(default=None, ge=0, le=1)
    sequence_identity: float | None = Field(default=None, ge=0, le=1)
    sequence_mismatches: tuple[str, ...] = ()
    mapped_features: tuple[MappedAnnotationFeature, ...] = ()
    motif_warnings: tuple[SequenceMotifWarning, ...] = ()
    error: str | None = Field(default=None, max_length=4096)

    @model_validator(mode="after")
    def validate_status(self) -> Self:
        if self.status is AnnotationStatus.NOT_REQUESTED:
            if self.evidence_level is not EvidenceLevel.STRUCTURAL_ONLY:
                raise ValueError("未请求 annotation 时只能是 structural_only")
            if self.source_sha256 is not None:
                raise ValueError("未请求 annotation 时不得伪造来源")
        if self.status is AnnotationStatus.SUCCEEDED:
            required = (
                self.accession,
                self.source_url,
                self.source_sha256,
                self.canonical_sequence_length,
                self.target_coverage,
                self.sequence_identity,
            )
            if any(value is None for value in required):
                raise ValueError("成功 annotation 缺少来源或映射指标")
            if self.evidence_level is not EvidenceLevel.STRUCTURAL_WITH_ANNOTATION:
                raise ValueError("成功 annotation 必须提升 evidence_level")
        if self.status is AnnotationStatus.FAILED and not self.error:
            raise ValueError("失败 annotation 必须记录 error")
        return self


class ResidueEvidence(BaseModel):
    """一个方法对一个结构残基的原始证据；两种方法不共享分数。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    method: RegionMethod
    residue: ResidueIdentity
    raw_sasa: float | None = Field(default=None, ge=0)
    rsasa: float | None = Field(default=None, ge=0)
    model_presence_fraction: float | None = Field(default=None, ge=0, le=1)
    exposure_frequency_default: float | None = Field(default=None, ge=0, le=1)
    exposure_frequency_relaxed: float | None = Field(default=None, ge=0, le=1)
    model_evidence: tuple[ResidueModelEvidence, ...] = ()
    scannet_probability: float | None = Field(default=None, ge=0, le=1)
    eligible: bool
    excluded_reasons: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_method_evidence(self) -> Self:
        if self.method is RegionMethod.SASA_SURFACE_DIVERSITY:
            if self.raw_sasa is None or self.rsasa is None:
                raise ValueError("SASA residue evidence 必须包含 raw_sasa 和 rsasa")
            if (
                self.model_presence_fraction is None
                or self.exposure_frequency_default is None
                or self.exposure_frequency_relaxed is None
                or not self.model_evidence
            ):
                raise ValueError("SASA residue evidence 必须包含逐模型共识证据")
            if self.scannet_probability is not None:
                raise ValueError("SASA residue evidence 禁止包含 ScanNet 概率")
        else:
            if self.scannet_probability is None:
                raise ValueError("ScanNet residue evidence 必须包含原始概率")
            if self.raw_sasa is not None or self.rsasa is not None:
                raise ValueError("ScanNet residue evidence 禁止包含 SASA 分数")
            if self.model_evidence:
                raise ValueError("ScanNet v0.1 禁止伪造多模型证据")
        return self


class ResidueEvidenceReport(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: str = "0.2"
    method: RegionMethod
    method_version: str = Field(min_length=1, max_length=128)
    target_structure_sha256: str = Field(pattern=SHA256_PATTERN)
    annotation_status: AnnotationStatus = AnnotationStatus.NOT_IMPLEMENTED
    coordinate_model_count: int = Field(default=1, ge=1)
    ensemble_consensus_fraction: float | None = Field(default=None, gt=0, le=1)
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
        if (
            self.method is RegionMethod.SASA_SURFACE_DIVERSITY
            and self.ensemble_consensus_fraction is None
        ):
            raise ValueError("SASA evidence report 必须声明 ensemble consensus")
        if (
            self.method is RegionMethod.SCANNET_EPITOPE_NO_MSA
            and self.coordinate_model_count != 1
        ):
            raise ValueError("ScanNet v0.1 residue evidence 只接受单模型")
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
    minimum_region_count: int = Field(default=2, ge=1)
    relaxation_tier: str | None = Field(default=None, pattern=ID_PATTERN)
    regions: tuple[CandidateSurfaceRegion, ...]
    pairwise_separation: tuple[PairwiseSeparation, ...] = ()
    requires_human_confirmation: bool = True

    @model_validator(mode="after")
    def validate_recommendations(self) -> Self:
        if any(item.method is not self.method for item in self.regions):
            raise ValueError("Recommended region method 必须一致")
        if self.minimum_region_count > self.requested_region_count:
            raise ValueError("minimum_region_count 不能高于 requested_region_count")
        if self.status is RegionReviewStatus.NEEDS_HUMAN_VISUAL_CONFIRMATION:
            if not (
                self.minimum_region_count
                <= len(self.regions)
                <= self.requested_region_count
            ):
                raise ValueError("可审阅推荐必须达到最少区域数且不超过请求数")
        elif len(self.regions) >= self.minimum_region_count:
            raise ValueError("不足状态不能包含达到最低门槛的区域")
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


class AutomaticRegionSource(BaseModel):
    """自动方法产物的不可变身份。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    type: Literal["automatic"] = "automatic"
    method: RegionMethod
    recommendation_artifact_id: str = Field(pattern=ID_PATTERN)
    recommendation_sha256: str = Field(pattern=SHA256_PATTERN)


class PseColorRegionSource(BaseModel):
    """PSE CA 颜色 annotation 的不可变来源身份。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    type: Literal["pse-color-annotation"] = "pse-color-annotation"
    color_scheme: Literal["easydesign-rby-v1"] = "easydesign-rby-v1"
    source_annotation_sha256: str = Field(pattern=SHA256_PATTERN)


class ManualResidueListRegionSource(BaseModel):
    """初始 YAML 中人工残基列表的不可变来源身份。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    type: Literal["manual-residue-list"] = "manual-residue-list"
    numbering: Literal["sequence", "label", "auth", "uniprot"]
    chain: str | None = Field(default=None, min_length=1, max_length=16)
    input_config_sha256: str = Field(pattern=SHA256_PATTERN)


RegionSource = Annotated[
    AutomaticRegionSource | PseColorRegionSource | ManualResidueListRegionSource,
    Field(discriminator="type"),
]

UserRegionSource = Annotated[
    PseColorRegionSource | ManualResidueListRegionSource,
    Field(discriminator="type"),
]


class UserProvidedRegion(BaseModel):
    """不扩展、不删减、不重排的一个用户区域。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(pattern=r"^[ABC]$")
    source_region_id: str = Field(pattern=ID_PATTERN)
    members: tuple[ResidueIdentity, ...] = Field(min_length=1)
    source_selectors: tuple[str, ...] = Field(min_length=1)
    centroid_angstrom: tuple[float, float, float]
    warnings: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_members(self) -> Self:
        labels = [member.label_seq_id for member in self.members]
        if labels != sorted(labels) or len(labels) != len(set(labels)):
            raise ValueError("用户区域成员必须按 label_seq_id 升序且不能重复")
        if len(self.source_selectors) != len(self.members):
            raise ValueError("用户区域 selector 数量必须与成员数量一致")
        return self


class UserProvidedRegionSet(BaseModel):
    """PSE 颜色和 YAML 残基列表共享的标准化结果。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["0.1"] = "0.1"
    target_id: str = Field(pattern=ID_PATTERN)
    target_structure_sha256: str = Field(pattern=SHA256_PATTERN)
    sequence_sha256: str = Field(pattern=SHA256_PATTERN)
    coordinate_model_ids: tuple[str, ...] = Field(min_length=1)
    representative_model_id: str = Field(min_length=1, max_length=32)
    region_source: UserRegionSource
    regions: tuple[UserProvidedRegion, ...] = Field(min_length=1, max_length=3)
    warnings: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_regions(self) -> Self:
        ids = [region.id for region in self.regions]
        order = {"A": 0, "B": 1, "C": 2}
        if ids != sorted(ids, key=order.__getitem__) or len(ids) != len(set(ids)):
            raise ValueError("用户区域 id 必须是按 A/B/C 排序的唯一非空子集")
        if self.representative_model_id not in self.coordinate_model_ids:
            raise ValueError("代表模型必须属于 coordinate_model_ids")
        return self


class UserRegionSourceEvidence(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["0.1"] = "0.1"
    target_id: str = Field(pattern=ID_PATTERN)
    region_source: UserRegionSource
    source_artifact_id: str | None = Field(default=None, pattern=ID_PATTERN)
    source_artifact_sha256: str | None = Field(default=None, pattern=SHA256_PATTERN)
    configured_selectors: dict[str, tuple[str, ...]] = Field(default_factory=dict)
    background_color_counts: dict[str, int] = Field(default_factory=dict)
    standard_color_counts: dict[str, int] = Field(default_factory=dict)


class UserRegionValidationReport(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["0.1"] = "0.1"
    status: Literal["succeeded"] = "succeeded"
    target_id: str = Field(pattern=ID_PATTERN)
    representative_model_id: str = Field(min_length=1, max_length=32)
    region_count: int = Field(ge=1, le=3)
    member_counts: dict[str, int]
    spatial_component_counts: dict[str, int]
    all_members_uniquely_mapped: bool = True
    all_members_present_in_representative_model: bool = True
    cross_region_overlaps: dict[str, tuple[int, ...]] = Field(default_factory=dict)
    warnings: tuple[str, ...] = ()


class ProviderExecutionStatus(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    provider: str = Field(default="automatic", pattern=ID_PATTERN)
    method: RegionMethod | None = None
    status: str = Field(pattern=ID_PATTERN)
    message: str


class Stage02Report(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: str = "0.3"
    target_id: str = Field(pattern=ID_PATTERN)
    resolved_region_source: str = Field(
        default="automatic",
        pattern=r"^(automatic|pse-color-annotation|manual-residue-list)$",
    )
    annotation_status: AnnotationStatus = AnnotationStatus.NOT_IMPLEMENTED
    evidence_level: EvidenceLevel = EvidenceLevel.STRUCTURAL_ONLY
    identity_resolution: IdentityResolutionStatus = (
        IdentityResolutionStatus.NOT_ATTEMPTED
    )
    comparison_status: str = Field(
        default="not-applicable",
        pattern=r"^(generated|not-applicable)$",
    )
    pse_source_annotations_consumed: bool = False
    fused_ranking_generated: bool = False
    stage03_handoff: RegionReviewStatus = RegionReviewStatus.AWAITING_REGION_SELECTION
    providers: tuple[ProviderExecutionStatus, ...]
    warnings: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_boundaries(self) -> Self:
        if (
            self.resolved_region_source != "pse-color-annotation"
            and self.pse_source_annotations_consumed
        ):
            raise ValueError("只有 PSE color 路线可以声明消费 PSE annotation")
        if (
            self.resolved_region_source == "pse-color-annotation"
            and not self.pse_source_annotations_consumed
        ):
            raise ValueError("PSE color 路线必须如实声明已消费 annotation")
        if (
            self.resolved_region_source == "automatic"
            and self.pse_source_annotations_consumed
        ):
            raise ValueError("automatic Stage 02 禁止消费 PSE 颜色 annotation")
        if self.fused_ranking_generated:
            raise ValueError("Stage 02 v0.1 禁止融合排名")
        if self.stage03_handoff is not RegionReviewStatus.AWAITING_REGION_SELECTION:
            raise ValueError("人工批准前 Stage 03 必须等待区域选择")
        return self


class HotspotReviewSelection(BaseModel):
    """人工只选择完整自动区域并补充用途与理由，不允许手抄残基。"""

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    id: str = Field(pattern=r"^[ABC]$")
    source_region_id: str = Field(pattern=ID_PATTERN)
    design_goal: DesignGoal = DesignGoal.EXPLORATORY
    biological_rationale: str = Field(default="", max_length=4096)
    structural_rationale: str = Field(default="", max_length=4096)


class HotspotReviewRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    schema_version: str = Field(default="0.2", pattern=r"^0\.[12]$")
    project_id: str = Field(pattern=ID_PATTERN)
    run_id: str = Field(pattern=ID_PATTERN)
    target_id: str = Field(pattern=ID_PATTERN)
    method: RegionMethod | None = None
    region_source: RegionSource
    source_stage_manifest_sha256: str = Field(pattern=SHA256_PATTERN)
    source_regions_artifact_id: str = Field(pattern=ID_PATTERN)
    source_regions_sha256: str = Field(pattern=SHA256_PATTERN)
    selection_basis: EvidenceLevel
    annotation_status: AnnotationStatus
    approved_by: str = Field(default="", max_length=256)
    acknowledge_user_provided_regions: bool = False
    acknowledge_evidence_limitations: bool = False
    selections: tuple[HotspotReviewSelection, ...] = Field(min_length=1, max_length=3)

    @model_validator(mode="after")
    def validate_selections(self) -> Self:
        ids = [selection.id for selection in self.selections]
        order = {"A": 0, "B": 1, "C": 2}
        if ids != sorted(ids, key=order.__getitem__) or len(ids) != len(set(ids)):
            raise ValueError("审批区域 id 必须是按 A/B/C 排序的唯一非空子集")
        region_ids = [selection.source_region_id for selection in self.selections]
        if len(region_ids) != len(set(region_ids)):
            raise ValueError("同一自动区域不能重复选择")
        if isinstance(self.region_source, AutomaticRegionSource):
            if self.method is None or self.method is not self.region_source.method:
                raise ValueError("automatic review 的 method/region_source 必须一致")
        elif self.method is not None:
            raise ValueError("用户提供区域不得伪造 automatic method")
        return self


class HotspotEvidence(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    type: str = Field(pattern=ID_PATTERN)
    source: str = Field(min_length=1, max_length=512)
    description: str = Field(min_length=1, max_length=2048)


class ApprovedHotspotSet(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    # The built-in Stage 02 review UI currently assigns A/B/C, but the stable
    # Stage 02 -> Stage 03 handoff must not make that UI convention a
    # scientific contract. Imported/third-party approved handoffs may use any
    # valid stable ID.
    id: str = Field(
        pattern=r"^(?:[ABC]|[a-z0-9][a-z0-9._-]{0,127})$"
    )
    slug: str = Field(pattern=ID_PATTERN)
    source_region_id: str = Field(pattern=ID_PATTERN)
    design_goal: DesignGoal
    biological_rationale: str = Field(min_length=1, max_length=4096)
    structural_rationale: str = Field(min_length=1, max_length=4096)
    auth_residues: tuple[str, ...] = Field(min_length=1)
    label_seq_ids: tuple[int, ...] = Field(min_length=1)
    label_ranges: str = Field(min_length=1)
    evidence: tuple[HotspotEvidence, ...] = Field(min_length=1)
    risk_flags: tuple[str, ...] = ()


class HotspotsFile(BaseModel):
    """人工或确定性策略批准后供 Stage 03 消费的唯一类型化交接物。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: str = Field(default="0.3", pattern=r"^0\.[123]$")
    project_id: str = Field(pattern=ID_PATTERN)
    run_id: str = Field(pattern=ID_PATTERN)
    target_id: str = Field(pattern=ID_PATTERN)
    target_structure_sha256: str = Field(pattern=SHA256_PATTERN)
    coordinate_model_ids: tuple[str, ...] = Field(min_length=1)
    method: RegionMethod | None = None
    region_source: RegionSource
    selection_basis: EvidenceLevel
    annotation_status: AnnotationStatus
    approval_request_sha256: str = Field(pattern=SHA256_PATTERN)
    approved_by: str = Field(min_length=1, max_length=256)
    approval_authority: str = Field(
        default="human",
        pattern=r"^(human|deterministic-policy)$",
    )
    approval_source: str = Field(
        default="explicit-review",
        pattern=r"^(explicit-review|initial-run-config|deterministic-policy)$",
    )
    policy_id: str | None = Field(default=None, pattern=ID_PATTERN)
    needs_human_review: bool = False
    ready_for_stage03: bool = True
    hotspot_sets: tuple[ApprovedHotspotSet, ...] = Field(min_length=1, max_length=3)

    @model_validator(mode="before")
    @classmethod
    def migrate_legacy_region_source(cls, raw: Any) -> Any:
        if not isinstance(raw, dict) or "region_source" in raw:
            return raw
        method = raw.get("method")
        if method is None:
            return raw
        migrated = dict(raw)
        migrated["region_source"] = {
            "type": "automatic",
            "method": method,
            "recommendation_artifact_id": (
                "sasa-recommended-regions"
                if method == RegionMethod.SASA_SURFACE_DIVERSITY
                else "scannet-recommended-regions"
            ),
            "recommendation_sha256": raw.get(
                "approval_request_sha256",
                "0" * 64,
            ),
        }
        return migrated

    @model_validator(mode="after")
    def validate_ready(self) -> Self:
        if self.needs_human_review or not self.ready_for_stage03:
            raise ValueError("hotspots.yaml 只能表示已经人工批准的 Stage 03 输入")
        ids = [hotspot.id for hotspot in self.hotspot_sets]
        if len(ids) != len(set(ids)):
            raise ValueError("hotspot set id 必须唯一")
        if isinstance(self.region_source, AutomaticRegionSource):
            if self.method is None or self.method is not self.region_source.method:
                raise ValueError("automatic hotspots 的 method/region_source 必须一致")
            if len(self.hotspot_sets) < 2:
                raise ValueError("automatic hotspots 至少需要两个区域")
        elif self.method is not None:
            raise ValueError("用户提供区域不得伪造 automatic method")
        if self.approval_authority == "deterministic-policy":
            if self.policy_id is None:
                raise ValueError("deterministic-policy hotspots 必须记录 policy_id")
            if self.approval_source != "deterministic-policy":
                raise ValueError("deterministic-policy authority/source 必须一致")
        elif self.policy_id is not None:
            raise ValueError("human hotspots 不得伪造 policy_id")
        if self.approval_source == "initial-run-config" and self.approval_authority != "human":
            raise ValueError("初始配置审批必须记录 human authority")
        return self


class ApprovalRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: str = Field(default="0.3", pattern=r"^0\.[123]$")
    status: str = Field(default="approved", pattern=r"^approved$")
    approved_at: datetime
    approved_by: str = Field(min_length=1, max_length=256)
    method: RegionMethod | None = None
    region_source: RegionSource
    source_stage_manifest_sha256: str = Field(pattern=SHA256_PATTERN)
    approval_input_sha256: str = Field(pattern=SHA256_PATTERN)
    selected_region_ids: tuple[str, ...] = Field(min_length=1, max_length=3)
    acknowledge_user_provided_regions: bool = False
    acknowledge_evidence_limitations: bool = False
    authority: str = Field(default="human", pattern=r"^(human|deterministic-policy)$")
    approval_source: str = Field(
        default="explicit-review",
        pattern=r"^(explicit-review|initial-run-config|deterministic-policy)$",
    )
    policy_id: str | None = Field(default=None, pattern=ID_PATTERN)

    @model_validator(mode="after")
    def validate_authority(self) -> Self:
        if isinstance(self.region_source, AutomaticRegionSource):
            if self.method is None or self.method is not self.region_source.method:
                raise ValueError("automatic approval 的 method/region_source 必须一致")
        elif self.method is not None:
            raise ValueError("用户提供区域不得伪造 automatic method")
        if self.authority == "deterministic-policy":
            if self.policy_id is None:
                raise ValueError("deterministic-policy approval 必须记录 policy_id")
            if self.approval_source != "deterministic-policy":
                raise ValueError("deterministic-policy authority/source 必须一致")
        elif self.policy_id is not None:
            raise ValueError("human approval 不得伪造 policy_id")
        return self
