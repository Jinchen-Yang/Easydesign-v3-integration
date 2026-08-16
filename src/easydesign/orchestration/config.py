"""EasyDesign 用户 YAML、target 自动识别和 Stage 01 请求解析。"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Any, Literal, Self, TypeAlias

import yaml  # type: ignore[import-untyped]
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from easydesign.backends.structure_prediction import (
    MsaMode,
    PredictionParameterProfile,
    ProtenixMsaProvider,
    StructurePredictionRequest,
    TemplateMode,
    resolve_protenix_msa_provider,
)
from easydesign.backends.target_sources import (
    NormalizedProteinSequence,
    normalize_fasta,
    normalize_raw_sequence,
)
from easydesign.backends.target_sources.sequence import CANONICAL_AMINO_ACIDS
from easydesign.core import ConfigurationError, TargetInputError
from easydesign.core.artifacts import ID_PATTERN, SHA256_PATTERN
from easydesign.stages.s03_boltzgen_configuration import (
    ExplicitStrategyVariant,
    NativeStrategyVariant,
)


class TargetInputFormat(StrEnum):
    """用户声明或 EasyDesign 自动识别的 target source 类型。"""

    AUTO = "auto"
    SEQUENCE = "sequence"
    FASTA = "fasta"
    MMCIF = "mmcif"
    PDB = "pdb"
    PSE = "pse"
    PDB_ID = "pdb-id"
    UNIPROT = "uniprot"
    UNIPROT_SEARCH = "uniprot-search"
    TARGET_BUNDLE = "target-bundle"


class ExecutionMode(StrEnum):
    """全流程只共享一套科学逻辑；差别只在科学选择点的 authority。"""

    REVIEW_GATED = "review-gated"
    UNATTENDED = "unattended"


class CacheMode(StrEnum):
    ONLINE = "online"
    PREFER_CACHE = "prefer-cache"
    OFFLINE = "offline"


class TargetIdentityConfig(BaseModel):
    """兼容 0.3 本地文件 identity，并给 Stage 02 提供统一 accession 读取入口。"""

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    uniprot_accession: str | None = Field(
        default=None,
        pattern=r"^[A-Z0-9]{6,10}(?:-[0-9]+)?$",
    )


class FullSequenceScope(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    type: Literal["full-sequence"] = "full-sequence"


class ResidueRangeScope(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    type: Literal["residue-range"]
    start: int = Field(ge=1)
    end: int = Field(ge=1)

    @model_validator(mode="after")
    def validate_range(self) -> Self:
        if self.end < self.start:
            raise ValueError("scope residue-range 的 end 不能小于 start")
        return self


class UniProtFeatureScope(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    type: Literal["uniprot-feature"]
    feature_type: str = Field(pattern=r"^(Domain|Chain|Topological domain)$")
    feature_name: str | None = Field(default=None, min_length=1, max_length=256)


TargetScope: TypeAlias = Annotated[
    FullSequenceScope | ResidueRangeScope | UniProtFeatureScope,
    Field(discriminator="type"),
]


class LocalFileSourceConfig(BaseModel):
    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        str_strip_whitespace=True,
    )

    type: Literal["local-file"]
    path: Path
    format: TargetInputFormat = TargetInputFormat.AUTO
    chain: str | None = Field(default=None, min_length=1, max_length=16)
    chain_namespace: Literal["auth", "label"] = "auth"
    identity: TargetIdentityConfig = TargetIdentityConfig()

    @model_validator(mode="after")
    def validate_local_format(self) -> Self:
        if self.format in {
            TargetInputFormat.PDB_ID,
            TargetInputFormat.UNIPROT,
            TargetInputFormat.UNIPROT_SEARCH,
        }:
            raise ValueError("local-file 不接受远程 source format")
        return self


class PdbIdSourceConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    type: Literal["pdb-id"]
    pdb_id: str = Field(pattern=r"^[0-9][A-Za-z0-9]{3}$")
    chain: str | None = Field(default=None, min_length=1, max_length=16)
    chain_namespace: Literal["auth", "label"] = "auth"


class UniProtSourceConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    type: Literal["uniprot"]
    accession: str = Field(pattern=r"^[A-Z0-9]{6,10}$")
    organism_taxon_id: int | None = Field(default=None, ge=1)
    isoform: Literal["canonical"] = "canonical"
    reviewed: Literal["required", "preferred", "any"] = "required"


class UniProtSearchSourceConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    type: Literal["uniprot-search"]
    query: str = Field(min_length=1, max_length=256)
    organism_taxon_id: int = Field(ge=1)
    isoform: Literal["canonical"] = "canonical"
    reviewed: Literal["required", "preferred", "any"] = "required"


class TargetBundleSourceConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    type: Literal["target-bundle"]
    path: Path
    source_run_root: Path


TargetSource: TypeAlias = Annotated[
    LocalFileSourceConfig
    | PdbIdSourceConfig
    | UniProtSourceConfig
    | UniProtSearchSourceConfig
    | TargetBundleSourceConfig,
    Field(discriminator="type"),
]


class TargetSourceConfig(BaseModel):
    """schema 0.4 的 Stage 01 target；名称保留以兼容已有 Python import。"""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        populate_by_name=True,
        str_strip_whitespace=True,
    )

    target_id: str = Field(alias="id", pattern=ID_PATTERN)
    source: TargetSource
    scope: TargetScope = FullSequenceScope()

    @model_validator(mode="before")
    @classmethod
    def accept_legacy_python_shape(cls, value: Any) -> Any:
        if not isinstance(value, dict) or isinstance(value.get("source"), dict):
            return value
        migrated = dict(value)
        path = migrated.pop("source")
        migrated["source"] = {
            "type": "local-file",
            "path": path,
            "format": migrated.pop("format", "auto"),
            "identity": migrated.pop("identity", {}),
        }
        return migrated

    @property
    def identity(self) -> TargetIdentityConfig:
        source = self.source
        if isinstance(source, LocalFileSourceConfig):
            return source.identity
        if isinstance(source, UniProtSourceConfig):
            return TargetIdentityConfig(uniprot_accession=source.accession)
        return TargetIdentityConfig()


class ProtenixMsaProviderConfig(BaseModel):
    """一个 remote-MSA provider 的有界重试配置。providers 的顺序就是显式兜底顺序。"""

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    provider: ProtenixMsaProvider = ProtenixMsaProvider.COLABFOLD_PUBLIC
    endpoint: str | None = None
    timeout_seconds: int = Field(default=1800, ge=60, le=7200)
    max_attempts: int = Field(default=3, ge=1, le=5)
    retry_backoff_seconds: int = Field(default=30, ge=0, le=600)

    @model_validator(mode="after")
    def validate_provider(self) -> Self:
        resolve_protenix_msa_provider(
            self.provider,
            custom_endpoint=self.endpoint,
        )
        return self


class ResolvedProtenixMsaProviderConfig(BaseModel):
    """写入 resolved-config.json 的实际 provider/endpoint 与重试预算。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    provider: ProtenixMsaProvider
    endpoint: str
    server_mode: str = Field(pattern=r"^(colabfold|protenix)$")
    timeout_seconds: int = Field(ge=60, le=7200)
    max_attempts: int = Field(ge=1, le=5)
    retry_backoff_seconds: int = Field(ge=0, le=600)


class RemoteProtenixMsaConfig(BaseModel):
    """远程 MSA 与显式 sequence-hash cache 策略。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    mode: Literal[MsaMode.REMOTE] = MsaMode.REMOTE
    cache_mode: CacheMode = CacheMode.ONLINE
    providers: tuple[ProtenixMsaProviderConfig, ...] = (ProtenixMsaProviderConfig(),)
    no_msa_fallback: bool = False

    @model_validator(mode="after")
    def validate_msa_policy(self) -> Self:
        if not self.providers:
            raise ValueError("remote MSA 至少需要一个 provider")
        provider_names = [provider.provider for provider in self.providers]
        if len(provider_names) != len(set(provider_names)):
            raise ValueError("MSA providers 不能重复")
        if self.no_msa_fallback:
            raise ValueError("禁止把 remote MSA 失败回退为 no-MSA")
        return self

    def resolved_providers(self) -> tuple[ResolvedProtenixMsaProviderConfig, ...]:
        resolved: list[ResolvedProtenixMsaProviderConfig] = []
        for item in self.providers:
            provider = resolve_protenix_msa_provider(
                item.provider,
                custom_endpoint=item.endpoint,
            )
            resolved.append(
                ResolvedProtenixMsaProviderConfig(
                    provider=provider.provider,
                    endpoint=provider.endpoint,
                    server_mode=provider.server_mode,
                    timeout_seconds=item.timeout_seconds,
                    max_attempts=item.max_attempts,
                    retry_backoff_seconds=item.retry_backoff_seconds,
                )
            )
        return tuple(resolved)


class PrecomputedProtenixMsaConfig(BaseModel):
    """用户显式提供并按规范 query 校验的 A3M。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    mode: Literal[MsaMode.PRECOMPUTED]
    path: Path

    def resolved_providers(self) -> tuple[ResolvedProtenixMsaProviderConfig, ...]:
        return ()


ProtenixMsaConfig: TypeAlias = Annotated[
    RemoteProtenixMsaConfig | PrecomputedProtenixMsaConfig,
    Field(discriminator="mode"),
]


class QueryOnlyComplexMsaConfig(BaseModel):
    """Use only the query row for one complex chain."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    mode: Literal["query-only"] = "query-only"

    def resolved_providers(self) -> tuple[ResolvedProtenixMsaProviderConfig, ...]:
        return ()


class DisabledComplexMsaConfig(BaseModel):
    """Explicitly omit one complex chain MSA feature."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    mode: Literal[MsaMode.DISABLED] = MsaMode.DISABLED

    def resolved_providers(self) -> tuple[ResolvedProtenixMsaProviderConfig, ...]:
        return ()


class PrecomputedComplexMsaConfig(BaseModel):
    """An immutable A3M selected for one complex chain."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    mode: Literal[MsaMode.PRECOMPUTED] = MsaMode.PRECOMPUTED
    path: Path
    sha256: str = Field(pattern=SHA256_PATTERN)

    @model_validator(mode="after")
    def validate_path(self) -> Self:
        if not self.path.is_absolute():
            raise ValueError("complex precomputed MSA path 必须是绝对路径")
        return self

    def resolved_providers(self) -> tuple[ResolvedProtenixMsaProviderConfig, ...]:
        return ()


ComplexMsaConfig: TypeAlias = Annotated[
    RemoteProtenixMsaConfig
    | PrecomputedComplexMsaConfig
    | QueryOnlyComplexMsaConfig
    | DisabledComplexMsaConfig,
    Field(discriminator="mode"),
]


class ComplexTemplateConfig(BaseModel):
    """Per-chain template source; combinations are never gated by scientific labels."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    mode: Literal["disabled", "precomputed", "target-structure"] = "disabled"
    data_path: Path | None = None
    data_sha256: str | None = Field(default=None, pattern=SHA256_PATTERN)

    @model_validator(mode="after")
    def validate_source(self) -> Self:
        supplied = self.data_path is not None or self.data_sha256 is not None
        if self.mode == "precomputed":
            if self.data_path is None or self.data_sha256 is None:
                raise ValueError("precomputed template 必须提供 data_path/data_sha256")
            if not self.data_path.is_absolute():
                raise ValueError("precomputed template data_path 必须是绝对路径")
        elif supplied:
            raise ValueError(f"template mode={self.mode} 不能提供 precomputed data")
        return self

PredictionBackend: TypeAlias = Literal["protenix-v2", "openfold3-af3-jax"]


class PredictionPolicyConfig(BaseModel):
    """Project-wide selection contract; it never names a prediction backend."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    selection_mode: Literal["explicit-per-stage"] = "explicit-per-stage"


class StructurePredictionConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    backend: PredictionBackend
    msa: ProtenixMsaConfig
    template_mode: TemplateMode
    parameter_profile: PredictionParameterProfile = PredictionParameterProfile.MODEL_DEFAULT
    seeds: tuple[int, ...] = (101,)
    sample_count: int = Field(default=1, ge=1)
    prediction_timeout_seconds: int = Field(default=7200, ge=60, le=86400)
    cycle_count: int | None = Field(default=None, ge=1)
    diffusion_step_count: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def validate_backend(self) -> Self:
        if len(self.seeds) != 1 or self.sample_count != 1:
            raise ValueError("Stage 01 v0.1 必须恰好一个 seed 和一个 sample，避免静默选择预测结构")
        return self


class WorkflowConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    execution_mode: ExecutionMode = ExecutionMode.REVIEW_GATED
    stop_after_stage: int = Field(default=1, ge=1, le=7)
    cache_mode: CacheMode = CacheMode.ONLINE
    max_strategy_rounds: int = Field(default=1, ge=1)

    @model_validator(mode="after")
    def validate_strategy_rounds(self) -> Self:
        if self.max_strategy_rounds != 1:
            raise ValueError(
                "EasyDesign 1.0 只实现 max_strategy_rounds=1；多轮自适应策略属于后续版本"
            )
        return self


class BinderProfile(StrEnum):
    VHH = "vhh"


class DesignIntent(StrEnum):
    BLOCKING = "blocking"
    NONBLOCKING = "nonblocking"
    DETECTION = "detection"
    IMAGING = "imaging"
    EXPLORATORY = "exploratory"


class DesignConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    binder_profile: BinderProfile = BinderProfile.VHH
    intent: DesignIntent = DesignIntent.EXPLORATORY
    required_reviews: tuple[str, ...] = ()


class StructureQualityProfile(StrEnum):
    EXPERIMENTAL_STRICT_V1 = "experimental-strict-v1"


class StructureSelectionConfig(BaseModel):
    """实验结构与预测之间的显式、版本化策略。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    policy: Literal["experimental-first"] = "experimental-first"
    quality_profile: StructureQualityProfile = StructureQualityProfile.EXPERIMENTAL_STRICT_V1
    on_no_eligible_candidate: Literal["predict", "fail"] = "predict"
    on_ambiguous_candidates: Literal["predict", "fail"] = "predict"
    preserve_source_context: bool = True
    keep_ligands: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_ligands(self) -> Self:
        normalized = tuple(value.upper() for value in self.keep_ligands)
        if len(normalized) != len(set(normalized)):
            raise ValueError("keep_ligands 不能重复")
        return self


class Stage01Config(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    target: TargetSourceConfig
    structure_selection: StructureSelectionConfig = StructureSelectionConfig()
    structure_prediction: StructurePredictionConfig | None = None


class RegionProposalMode(StrEnum):
    DETECT = "detect"
    AUTOMATIC = "automatic"
    USER_PROVIDED = "user-provided"


class Stage02Method(StrEnum):
    SASA = "sasa"
    SCANNET = "scannet"


class UserRegionNumbering(StrEnum):
    SEQUENCE = "sequence"
    LABEL = "label"
    AUTH = "auth"
    UNIPROT = "uniprot"


class UserRegionDesignGoal(StrEnum):
    BLOCKING = "blocking"
    AFFINITY_SUPPORT = "affinity_support"
    NONBLOCKING = "nonblocking"
    DETECTION = "detection"
    IMAGING = "imaging"
    EXPLORATORY = "exploratory"


class ManualRegionConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    id: Literal["A", "B", "C"]
    residues: tuple[str, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_residues(self) -> Self:
        normalized = tuple(str(value).strip() for value in self.residues)
        if any(not value for value in normalized):
            raise ValueError("人工区域 residue 不能为空")
        if len(normalized) != len(set(normalized)):
            raise ValueError(f"人工区域 {self.id} 内 residue 不能重复")
        return self


class PseColorRegionSourceConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    type: Literal["pse-colors"] = "pse-colors"
    color_scheme: Literal["easydesign-rby-v1"] = "easydesign-rby-v1"


class ManualResidueRegionSourceConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    type: Literal["residue-list"] = "residue-list"
    numbering: UserRegionNumbering
    chain: str | None = Field(default=None, min_length=1, max_length=16)
    regions: tuple[ManualRegionConfig, ...] = Field(min_length=1, max_length=3)

    @model_validator(mode="after")
    def validate_regions(self) -> Self:
        ids = [region.id for region in self.regions]
        if len(ids) != len(set(ids)):
            raise ValueError("人工区域 id 不能重复")
        if ids != sorted(ids, key="ABC".index):
            raise ValueError("人工区域必须按 A、B、C 顺序声明")
        if self.numbering is UserRegionNumbering.AUTH and self.chain is None:
            raise ValueError("auth 编号必须显式提供 chain")
        if self.numbering is not UserRegionNumbering.AUTH and self.chain is not None:
            raise ValueError("只有 auth 编号可以声明 chain")
        return self


UserRegionSourceConfig: TypeAlias = Annotated[
    PseColorRegionSourceConfig | ManualResidueRegionSourceConfig,
    Field(discriminator="type"),
]


class UserRegionApprovalSelectionConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    id: Literal["A", "B", "C"]
    design_goal: UserRegionDesignGoal = UserRegionDesignGoal.EXPLORATORY
    biological_rationale: str = Field(min_length=1, max_length=4096)
    structural_rationale: str = Field(min_length=1, max_length=4096)


class UserRegionInitialApprovalConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    approved_by: str = Field(min_length=1, max_length=256)
    acknowledge_user_provided_regions: Literal[True]
    acknowledge_evidence_limitations: Literal[True]
    selections: tuple[UserRegionApprovalSelectionConfig, ...] = Field(
        min_length=1,
        max_length=3,
    )

    @model_validator(mode="after")
    def validate_selections(self) -> Self:
        ids = [selection.id for selection in self.selections]
        if len(ids) != len(set(ids)):
            raise ValueError("配置内批准的区域 id 不能重复")
        if ids != sorted(ids, key="ABC".index):
            raise ValueError("配置内批准区域必须按 A、B、C 顺序声明")
        return self


class UserProvidedRegionsConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    source: UserRegionSourceConfig
    approval: UserRegionInitialApprovalConfig | None = None


class UniProtAnnotationMode(StrEnum):
    OFF = "off"
    IF_AVAILABLE = "if_available"
    REQUIRED = "required"


class Stage02AnnotationConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    uniprot: UniProtAnnotationMode = UniProtAnnotationMode.IF_AVAILABLE


class Stage02SasaConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    rsasa_threshold: float = Field(default=0.25, gt=0, le=1)
    relaxed_threshold: float = Field(default=0.20, gt=0, le=1)
    probe_radius_angstrom: float = Field(default=1.4, gt=0)
    sphere_points: int = Field(default=960, ge=100)
    ensemble_consensus_fraction: float = Field(default=0.70, gt=0, le=1)

    @model_validator(mode="after")
    def validate_thresholds(self) -> Self:
        if self.relaxed_threshold > self.rsasa_threshold:
            raise ValueError("Stage 02 relaxed_threshold 不能高于 rsasa_threshold")
        return self


class Stage02PatchConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    target_member_count: int = Field(default=12, ge=5)
    minimum_member_count: int = Field(default=5, ge=5)
    heavy_atom_neighbor_angstrom: float = Field(default=5.0, gt=0)
    anchor_neighbor_angstrom: float = Field(default=12.0, gt=0)
    compactness_radius_angstrom: float = Field(default=14.0, gt=0)

    @model_validator(mode="after")
    def validate_member_counts(self) -> Self:
        if self.minimum_member_count > self.target_member_count:
            raise ValueError("minimum_member_count 不能高于 target_member_count")
        return self


class Stage02EvidenceConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    scannet_mode: str = Field(default="epitope", pattern=r"^epitope$")
    use_msa: bool = False

    @model_validator(mode="after")
    def forbid_msa(self) -> Self:
        if self.use_msa:
            raise ValueError("Stage 02 v0.1 只实现 ScanNet epitope no-MSA")
        return self


class Stage02AutomaticConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    requested_region_count: int = Field(default=3, ge=1, le=3)
    minimum_region_count: int = Field(default=2, ge=1, le=3)
    sasa: Stage02SasaConfig = Stage02SasaConfig()
    patch: Stage02PatchConfig = Stage02PatchConfig()
    evidence: Stage02EvidenceConfig = Stage02EvidenceConfig()
    avoid_label_seq_ids: tuple[int, ...] = ()

    @model_validator(mode="before")
    @classmethod
    def migrate_region_count(cls, value: Any) -> Any:
        if isinstance(value, dict) and "region_count" in value:
            migrated = dict(value)
            if "requested_region_count" in migrated:
                raise ValueError("region_count 与 requested_region_count 不能同时出现")
            migrated["requested_region_count"] = migrated.pop("region_count")
            return migrated
        return value

    @model_validator(mode="after")
    def validate_avoid(self) -> Self:
        if self.minimum_region_count > self.requested_region_count:
            raise ValueError("minimum_region_count 不能高于 requested_region_count")
        if any(value < 1 for value in self.avoid_label_seq_ids):
            raise ValueError("avoid_label_seq_ids 必须为正整数")
        if len(self.avoid_label_seq_ids) != len(set(self.avoid_label_seq_ids)):
            raise ValueError("avoid_label_seq_ids 不能重复")
        return self

    @property
    def region_count(self) -> int:
        """兼容内部 v0.1 调用；序列化只使用 requested_region_count。"""

        return self.requested_region_count


class Stage02UnattendedApprovalConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    region_count: int = Field(default=3, ge=2, le=3)
    allow_structural_only: bool = False


class Stage02Config(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    mode: RegionProposalMode = RegionProposalMode.AUTOMATIC
    methods: tuple[Stage02Method, ...] = ()
    annotations: Stage02AnnotationConfig = Stage02AnnotationConfig()
    automatic: Stage02AutomaticConfig | None = Stage02AutomaticConfig()
    user_regions: UserProvidedRegionsConfig | None = None
    unattended_approval: Stage02UnattendedApprovalConfig | None = None

    @model_validator(mode="before")
    @classmethod
    def default_methods_for_mode(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        migrated = dict(value)
        legacy_mode = migrated.get("mode")
        if legacy_mode == "pse_annotations":
            migrated["mode"] = RegionProposalMode.USER_PROVIDED
            migrated.setdefault(
                "user_regions",
                {"source": {"type": "pse-colors"}},
            )
        elif legacy_mode == "manual":
            migrated["mode"] = RegionProposalMode.USER_PROVIDED
        if migrated.get("mode") in {
            RegionProposalMode.USER_PROVIDED,
            str(RegionProposalMode.USER_PROVIDED),
        }:
            migrated.setdefault("automatic", None)
            migrated.setdefault("methods", [])
        if migrated.get("mode") in {
            RegionProposalMode.DETECT,
            str(RegionProposalMode.DETECT),
        }:
            migrated.setdefault(
                "user_regions",
                {"source": {"type": "pse-colors"}},
            )
        if "methods" in migrated:
            return migrated
        mode = migrated.get("mode", RegionProposalMode.AUTOMATIC)
        migrated["methods"] = (
            [Stage02Method.SASA, Stage02Method.SCANNET]
            if mode
            in {
                RegionProposalMode.AUTOMATIC,
                RegionProposalMode.DETECT,
                str(RegionProposalMode.AUTOMATIC),
                str(RegionProposalMode.DETECT),
            }
            else []
        )
        return migrated

    @model_validator(mode="after")
    def validate_mode(self) -> Self:
        if len(self.methods) != len(set(self.methods)):
            raise ValueError("Stage 02 methods 不能重复")
        if self.mode in {
            RegionProposalMode.AUTOMATIC,
            RegionProposalMode.DETECT,
        }:
            if self.automatic is None or not self.methods:
                raise ValueError(f"Stage 02 {self.mode} 模式必须提供 automatic 配置和 methods")
        if self.mode is RegionProposalMode.AUTOMATIC and self.user_regions is not None:
            raise ValueError("automatic 模式不得携带 user_regions")
        if self.mode is RegionProposalMode.USER_PROVIDED:
            if self.user_regions is None:
                raise ValueError("user-provided 模式必须提供 user_regions")
            if self.automatic is not None or self.methods:
                raise ValueError("user-provided 模式不得携带 automatic 配置或 methods")
        if self.mode is RegionProposalMode.DETECT:
            if self.user_regions is None or not isinstance(
                self.user_regions.source,
                PseColorRegionSourceConfig,
            ):
                raise ValueError("detect 模式的 user_regions 只能使用 pse-colors")
        return self


class Stage03Config(BaseModel):
    """Stage 02 已批准区域到 BoltzGen design specification 的基础模板。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    profile: Literal["boltzgen-vhh-basic-v1"] = "boltzgen-vhh-basic-v1"
    scaffold_registry: Literal["official-vhh7-v1"] = "official-vhh7-v1"
    scaffold_ids: (
        tuple[
            Literal[
                "7eow",
                "7xl0",
                "8coh",
                "8z8v",
                "gontivimab",
                "isecarosmab",
                "sonelokimab",
            ],
            ...,
        ]
        | None
    ) = None
    candidates_per_strategy: int = Field(default=40, ge=1)
    variants: tuple[ExplicitStrategyVariant, ...] | None = None
    native_variants: tuple[NativeStrategyVariant, ...] = ()

    @model_validator(mode="after")
    def validate_scaffold_subset(self) -> Self:
        if self.scaffold_ids is not None:
            if not self.scaffold_ids:
                raise ValueError("scaffold_ids 至少包含一个官方 VHH scaffold")
            if len(self.scaffold_ids) != len(set(self.scaffold_ids)):
                raise ValueError("scaffold_ids 不能重复")
        identifiers = [
            *(item.variant_id for item in self.variants or ()),
            *(item.variant_id for item in self.native_variants),
        ]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("Stage 03 variant_id 不能重复")
        if self.variants is not None and not self.variants and not self.native_variants:
            raise ValueError("显式 strategy plan 至少包含一个 variant")
        return self


class LocalMultiGpuExecutorConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    type: Literal["local-multi-gpu"] = "local-multi-gpu"
    devices: tuple[int, ...] | None = None
    maximum_devices: int | None = Field(default=None, ge=1)
    workers_per_device: Literal[1] = 1
    max_memory_used_mib: int = Field(default=1024, ge=0)
    max_utilization_percent: int = Field(default=10, ge=0, le=100)
    resource_wait_timeout_seconds: float = Field(default=21_600, gt=0)
    resource_poll_seconds: float = Field(default=15, gt=0, le=300)
    max_task_attempts: int = Field(default=3, ge=1, le=10)

    @model_validator(mode="after")
    def validate_devices(self) -> Self:
        if self.devices is None:
            return self
        if not self.devices:
            raise ValueError("GPU devices 不能是空列表")
        if any(device < 0 for device in self.devices):
            raise ValueError("GPU device 必须是非负整数")
        if len(self.devices) != len(set(self.devices)):
            raise ValueError("GPU device 不能重复")
        return self


class Stage04Config(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    backend: Literal["boltzgen-0.3.2"] = "boltzgen-0.3.2"
    executor: LocalMultiGpuExecutorConfig = LocalMultiGpuExecutorConfig()
    required_complete_candidates_per_strategy: int = Field(default=40, ge=1)


class Stage05StrategySelectionConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    full_target_refold_top_n: int = Field(default=10, ge=1)
    require_unique_winner: Literal[True] = True


class Stage05AdvisoryValidationConfig(BaseModel):
    """v1.6 diagnostic expansion; scientific negatives are warnings."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    expanded_total_per_strategy: int = Field(default=100, ge=1)
    full_target_refold_top_n: int = Field(default=10, ge=1)

    @model_validator(mode="after")
    def validate_top_n(self) -> Self:
        if self.full_target_refold_top_n > self.expanded_total_per_strategy:
            raise ValueError("full_target_refold_top_n 不能超过 diagnostic expansion 总数")
        return self


class ComplexPredictionConfig(BaseModel):
    """Uniform per-chain feature policy for Stage 05/07 complex prediction."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    backend: PredictionBackend
    target_msa: RemoteProtenixMsaConfig = RemoteProtenixMsaConfig()
    target_paired_msa: ComplexMsaConfig = QueryOnlyComplexMsaConfig()
    binder_msa: ComplexMsaConfig = QueryOnlyComplexMsaConfig()
    binder_paired_msa: ComplexMsaConfig = QueryOnlyComplexMsaConfig()
    target_templates: ComplexTemplateConfig = ComplexTemplateConfig()
    binder_templates: ComplexTemplateConfig = ComplexTemplateConfig()
    template_mode: TemplateMode = TemplateMode.DISABLED
    parameter_profile: PredictionParameterProfile = PredictionParameterProfile.MODEL_DEFAULT
    prediction_timeout_seconds: int = Field(default=7200, ge=60, le=86400)

    @model_validator(mode="before")
    @classmethod
    def accept_legacy_scalar_msa(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        migrated = dict(value)
        for field in ("target_msa", "target_paired_msa", "binder_msa", "binder_paired_msa"):
            if isinstance(migrated.get(field), str):
                migrated[field] = {"mode": migrated[field]}
        if "target_templates" not in migrated:
            legacy_template_mode = migrated.get("template_mode")
            if legacy_template_mode == TemplateMode.PRECOMPUTED:
                migrated["target_templates"] = {"mode": "target-structure"}
            elif legacy_template_mode == TemplateMode.DISABLED:
                migrated["target_templates"] = {"mode": "disabled"}
        return migrated


class TargetConditionedPredictionConfig(ComplexPredictionConfig):
    """Compatibility name; it exposes the same freely composable chain features."""

    target_templates: ComplexTemplateConfig = ComplexTemplateConfig(
        mode="target-structure"
    )
    template_mode: TemplateMode = TemplateMode.PRECOMPUTED


class Stage05Config(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    filter_profile: Literal[
        "nanobody-filter-standard-v1.5",
        "nanobody-filter-standard-v1.6",
        "nanobody-filter-standard-v1.7",
    ] = "nanobody-filter-standard-v1.6"
    maximum_tier_a_strategies: int = Field(default=3, ge=1, le=3)
    advisory_validation: Stage05AdvisoryValidationConfig | None = None
    expanded_total_per_strategy: int | None = Field(default=None, ge=1)
    strategy_selection: Stage05StrategySelectionConfig | None = None
    full_target_prediction: ComplexPredictionConfig

    @model_validator(mode="before")
    @classmethod
    def populate_profile_defaults(cls, value: Any) -> Any:
        """Apply defaults without leaking v1.6 fields into legacy v1.5 configs."""

        if not isinstance(value, dict):
            return value
        payload = dict(value)
        profile = payload.get(
            "filter_profile",
            "nanobody-filter-standard-v1.6",
        )
        if profile in {
            "nanobody-filter-standard-v1.6",
            "nanobody-filter-standard-v1.7",
        }:
            payload.setdefault("advisory_validation", {})
        elif profile == "nanobody-filter-standard-v1.5":
            payload.setdefault("expanded_total_per_strategy", 100)
            payload.setdefault("strategy_selection", {})
        return payload

    @model_validator(mode="after")
    def validate_profile_shape(self) -> Self:
        if self.filter_profile in {
            "nanobody-filter-standard-v1.6",
            "nanobody-filter-standard-v1.7",
        }:
            if self.advisory_validation is None:
                raise ValueError("v1.6/v1.7 必须声明 advisory_validation")
            if self.expanded_total_per_strategy is not None or self.strategy_selection is not None:
                raise ValueError("v1.6/v1.7 不接受旧版 expansion/strategy_selection 字段")
        else:
            if self.expanded_total_per_strategy is None or self.strategy_selection is None:
                raise ValueError("v1.5 必须声明旧版 expansion/strategy_selection 字段")
            if self.advisory_validation is not None:
                raise ValueError("v1.5 不接受 advisory_validation")
        return self

    @property
    def diagnostic_expanded_total_per_strategy(self) -> int:
        if self.advisory_validation is not None:
            return self.advisory_validation.expanded_total_per_strategy
        assert self.expanded_total_per_strategy is not None
        return self.expanded_total_per_strategy

    @property
    def diagnostic_full_target_refold_top_n(self) -> int:
        if self.advisory_validation is not None:
            return self.advisory_validation.full_target_refold_top_n
        assert self.strategy_selection is not None
        return self.strategy_selection.full_target_refold_top_n


class Stage06ManualStrategyAuthorizationConfig(BaseModel):
    """Explicit human authority to scale a selected Tier A after a scientific stop."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        str_strip_whitespace=True,
    )

    strategy_id: str = Field(pattern=ID_PATTERN)
    authorized_by: str = Field(min_length=1, max_length=256)
    reason: str = Field(min_length=20, max_length=4096)
    source_stage05_bundle_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    acknowledge_stage05_scientific_stop: Literal[True]
    acknowledge_not_scientifically_eligible: Literal[True]


class Stage06Config(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    scale_profile: Literal[
        "user-defined-v1",
        "smoke-1000",
        "production-50000",
    ] = "user-defined-v1"
    total_candidate_count: int = Field(default=50_000, ge=1)
    allocation_policy: Literal["equal-across-promoted-v1"] | None = None
    preauthorized_candidate_limit: int | None = Field(default=None, ge=1)
    manual_strategy_authorization: Stage06ManualStrategyAuthorizationConfig | None = None
    human_promoted_strategy_ids: tuple[str, ...] | None = Field(
        default=None,
        min_length=1,
        max_length=3,
    )
    human_promotion_receipt_sha256: str | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{64}$",
    )

    @model_validator(mode="before")
    @classmethod
    def migrate_fixed_scale_profiles(cls, value: Any) -> Any:
        """Read dev34 fixed profiles without changing their frozen budget."""

        if not isinstance(value, dict) or "total_candidate_count" in value:
            return value
        migrated = dict(value)
        profile = migrated.get("scale_profile")
        if profile == "smoke-1000":
            migrated["total_candidate_count"] = 1_000
        elif profile == "production-50000":
            migrated["total_candidate_count"] = 50_000
        return migrated

    @model_validator(mode="after")
    def validate_authorized_limit(self) -> Self:
        fixed_count = {
            "smoke-1000": 1_000,
            "production-50000": 50_000,
        }.get(self.scale_profile)
        if fixed_count is not None and self.total_candidate_count != fixed_count:
            raise ValueError("旧版 scale profile 的候选数不可改写")
        if (
            self.preauthorized_candidate_limit is not None
            and self.total_candidate_count > self.preauthorized_candidate_limit
        ):
            raise ValueError(
                "total_candidate_count 超过 preauthorized_candidate_limit；"
                "高成本运行必须在初始配置中获得显式授权"
            )
        if (self.human_promoted_strategy_ids is None) != (
            self.human_promotion_receipt_sha256 is None
        ):
            raise ValueError("human promotion strategy IDs 与 receipt SHA-256 必须同时提供")
        if self.human_promoted_strategy_ids is not None and len(
            self.human_promoted_strategy_ids
        ) != len(set(self.human_promoted_strategy_ids)):
            raise ValueError("human promoted strategy_id 不能重复")
        return self

    @property
    def authorized_candidate_limit(self) -> int:
        """Return the immutable authorization recorded in the scale plan."""

        return self.preauthorized_candidate_limit or self.total_candidate_count


class Stage07Config(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    final_filter_profile: Literal[
        "nanobody-final-v1.5",
        "nanobody-final-v1.6",
    ] = "nanobody-final-v1.5"
    primary_count: int = Field(default=20, ge=0)
    backup_count: int = Field(default=20, ge=0)
    review_cohort_size: int = Field(default=200, ge=1, le=400)
    tnp_required: Literal[True] = True
    full_target_prediction: ComplexPredictionConfig
    target_conditioned_prediction: TargetConditionedPredictionConfig

    @model_validator(mode="after")
    def validate_package_size(self) -> Self:
        if self.primary_count + self.backup_count < 1:
            raise ValueError("最终候选包至少请求一个候选")
        return self


def stage05_config_for_backend(backend: PredictionBackend) -> Stage05Config:
    if backend == "openfold3-af3-jax":
        return Stage05Config.model_validate(
            {
                "filter_profile": "nanobody-filter-standard-v1.7",
                "full_target_prediction": {"backend": backend},
            }
        )
    return Stage05Config.model_validate(
        {
            "filter_profile": "nanobody-filter-standard-v1.6",
            "full_target_prediction": {"backend": backend},
        }
    )


def stage07_config_for_backends(
    de_novo_backend: PredictionBackend,
    target_conditioned_backend: PredictionBackend,
    *,
    primary_count: int = 20,
    backup_count: int = 20,
) -> Stage07Config:
    if de_novo_backend == "openfold3-af3-jax":
        return Stage07Config.model_validate(
            {
                "final_filter_profile": "nanobody-final-v1.6",
                "primary_count": primary_count,
                "backup_count": backup_count,
                "full_target_prediction": {"backend": de_novo_backend},
                "target_conditioned_prediction": {
                    "backend": target_conditioned_backend,
                },
            }
        )
    return Stage07Config.model_validate(
        {
            "final_filter_profile": "nanobody-final-v1.5",
            "primary_count": primary_count,
            "backup_count": backup_count,
            "full_target_prediction": {"backend": de_novo_backend},
            "target_conditioned_prediction": {
                "backend": target_conditioned_backend,
            },
        }
    )


def stage07_config_for_backend(
    backend: PredictionBackend,
    *,
    primary_count: int = 20,
    backup_count: int = 20,
) -> Stage07Config:
    """Compatibility helper for frozen callers that selected one backend for both modes."""

    return stage07_config_for_backends(
        backend,
        backend,
        primary_count=primary_count,
        backup_count=backup_count,
    )


class EasyDesignRunConfig(BaseModel):
    """用户维护的唯一 run 配置；不包含 Protenix 私有 JSON。"""

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    schema_version: str = Field(default="0.9", pattern=r"^0\.9$")
    project_id: str = Field(pattern=ID_PATTERN)
    design: DesignConfig = DesignConfig()
    prediction_policy: PredictionPolicyConfig = PredictionPolicyConfig()
    stage01: Stage01Config
    stage02: Stage02Config | None = None
    stage03: Stage03Config | None = None
    stage04: Stage04Config | None = None
    stage05: Stage05Config | None = None
    stage06: Stage06Config | None = None
    stage07: Stage07Config | None = None
    workflow: WorkflowConfig = WorkflowConfig()

    @model_validator(mode="before")
    @classmethod
    def migrate_legacy_layout(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        migrated = dict(value)
        legacy_keys = {"target", "structure_prediction"} & migrated.keys()
        if "stage01" in migrated and legacy_keys:
            raise ValueError("stage01 不能与旧 target/structure_prediction 同时出现")
        if "stage01" not in migrated and "target" in migrated:
            migrated["stage01"] = {
                "target": migrated.pop("target"),
                "structure_prediction": migrated.pop(
                    "structure_prediction",
                    None,
                ),
            }
        stage01 = migrated.get("stage01")
        if isinstance(stage01, dict):
            stage01 = dict(stage01)
            target = stage01.get("target")
            if isinstance(target, dict) and not isinstance(target.get("source"), dict):
                legacy_target = dict(target)
                legacy_source = legacy_target.pop("source", None)
                if legacy_source is not None:
                    legacy_format = legacy_target.pop("format", "auto")
                    legacy_identity = legacy_target.pop("identity", {})
                    stage01["target"] = {
                        **legacy_target,
                        "source": {
                            "type": "local-file",
                            "path": legacy_source,
                            "format": legacy_format,
                            "identity": legacy_identity,
                        },
                        "scope": {"type": "full-sequence"},
                    }
            migrated["stage01"] = stage01
        source_schema = str(migrated.get("schema_version") or "")
        legacy_prediction_policy = migrated.get("prediction_policy")
        legacy_backend: PredictionBackend | None = None
        if isinstance(legacy_prediction_policy, dict):
            candidate = legacy_prediction_policy.get("backend")
            if candidate in {"protenix-v2", "openfold3-af3-jax"}:
                legacy_backend = candidate
        if legacy_backend is None and isinstance(stage01, dict):
            legacy_prediction = stage01.get("structure_prediction")
            if isinstance(legacy_prediction, dict):
                candidate = legacy_prediction.get("backend")
                if candidate in {"protenix-v2", "openfold3-af3-jax"}:
                    legacy_backend = candidate
        if source_schema != "0.9":
            migrated["prediction_policy"] = {
                "selection_mode": "explicit-per-stage",
            }
            stage01 = migrated.get("stage01")
            if isinstance(stage01, dict):
                prediction = stage01.get("structure_prediction")
                if isinstance(prediction, dict) and legacy_backend is not None:
                    prediction = dict(prediction)
                    prediction.setdefault("backend", legacy_backend)
                    stage01 = dict(stage01)
                    stage01["structure_prediction"] = prediction
                    migrated["stage01"] = stage01
        stage05 = migrated.get("stage05")
        if (
            source_schema != "0.8"
            and isinstance(stage05, dict)
            and stage05.get("filter_profile") is None
        ):
            stage05 = dict(stage05)
            stage05["filter_profile"] = "nanobody-filter-standard-v1.5"
            stage05.setdefault("expanded_total_per_strategy", 100)
            stage05.setdefault(
                "strategy_selection",
                {
                    "full_target_refold_top_n": 10,
                    "require_unique_winner": True,
                },
            )
            migrated["stage05"] = stage05
        if (
            source_schema != "0.9"
            and isinstance(stage05, dict)
            and legacy_backend is not None
        ):
            stage05 = dict(stage05)
            stage05.setdefault(
                "full_target_prediction",
                {"backend": legacy_backend},
            )
            migrated["stage05"] = stage05
        stage07 = migrated.get("stage07")
        if (
            source_schema != "0.9"
            and isinstance(stage07, dict)
            and legacy_backend is not None
        ):
            stage07 = dict(stage07)
            de_novo = stage07.setdefault(
                "full_target_prediction",
                {"backend": legacy_backend},
            )
            conditioned_backend = legacy_backend
            if isinstance(de_novo, dict) and de_novo.get("backend") in {
                "protenix-v2",
                "openfold3-af3-jax",
            }:
                conditioned_backend = de_novo["backend"]
            stage07.setdefault(
                "target_conditioned_prediction",
                {
                    "backend": conditioned_backend,
                    "template_mode": "precomputed",
                },
            )
            migrated["stage07"] = stage07
        migrated["schema_version"] = "0.9"
        return migrated

    @model_validator(mode="after")
    def validate_stage_sequence(self) -> Self:
        if self.workflow.stop_after_stage >= 2 and self.stage02 is None:
            raise ValueError("stop_after_stage >= 2 时必须显式提供 stage02")
        stages = (
            self.stage01,
            self.stage02,
            self.stage03,
            self.stage04,
            self.stage05,
            self.stage06,
            self.stage07,
        )
        for stage_number in range(2, self.workflow.stop_after_stage + 1):
            if stages[stage_number - 1] is None:
                raise ValueError(
                    f"stop_after_stage={self.workflow.stop_after_stage} 时 "
                    f"stage{stage_number:02d} 不能为 null"
                )
        for stage_number in range(self.workflow.stop_after_stage + 1, 8):
            if stages[stage_number - 1] is not None:
                raise ValueError(
                    f"stage{stage_number:02d} 已配置，但 stop_after_stage="
                    f"{self.workflow.stop_after_stage}"
                )
        if self.stage03 is not None and self.design.binder_profile is not BinderProfile.VHH:
            raise ValueError("Stage 03 1.0 只实现 binder_profile=vhh")
        if (
            self.stage03 is not None
            and self.stage04 is not None
            and self.stage03.candidates_per_strategy
            != self.stage04.required_complete_candidates_per_strategy
        ):
            raise ValueError(
                "Stage 03 candidates_per_strategy 必须与 Stage 04 "
                "required_complete_candidates_per_strategy 一致"
            )
        if self.stage04 is not None and self.stage05 is not None:
            if (
                self.stage05.diagnostic_expanded_total_per_strategy
                <= self.stage04.required_complete_candidates_per_strategy
            ):
                raise ValueError("Stage 05 expanded_total_per_strategy 必须大于 Stage 04 pilot 数")
            if (
                self.stage05.diagnostic_full_target_refold_top_n
                > self.stage05.diagnostic_expanded_total_per_strategy
            ):
                raise ValueError("Stage 05 full_target_refold_top_n 不能超过 expansion 总数")
        if self.stage05 is not None:
            stage05_afo = (
                self.stage05.full_target_prediction.backend
                == "openfold3-af3-jax"
            )
            if stage05_afo != (
                self.stage05.filter_profile
                == "nanobody-filter-standard-v1.7"
            ):
                raise ValueError(
                    "Stage 05 OpenFold3 必须与 nanobody-filter-standard-v1.7 配对；"
                    "Protenix 必须保留 v1.5/v1.6"
                )
        if self.stage07 is not None:
            stage07_afo = (
                self.stage07.full_target_prediction.backend
                == "openfold3-af3-jax"
            )
            if stage07_afo != (
                self.stage07.final_filter_profile == "nanobody-final-v1.6"
            ):
                raise ValueError(
                    "Stage 07 OpenFold3 必须与 nanobody-final-v1.6 配对；"
                    "Protenix 必须保留 v1.5"
                )
        if (
            self.stage05 is not None
            and self.stage05.filter_profile
            in {
                "nanobody-filter-standard-v1.6",
                "nanobody-filter-standard-v1.7",
            }
            and self.stage06 is not None
        ):
            if self.stage06.allocation_policy != "equal-across-promoted-v1":
                raise ValueError(
                    "Stage 05 v1.6 进入 Stage 06 时必须声明 "
                    "allocation_policy=equal-across-promoted-v1"
                )
            if self.stage06.manual_strategy_authorization is not None:
                raise ValueError("Stage 05 v1.6 不接受旧版单策略 manual authorization")
        source = self.stage01.target.source
        if (
            isinstance(
                source,
                (PdbIdSourceConfig, TargetBundleSourceConfig),
            )
            and self.stage01.structure_prediction is not None
        ):
            raise ValueError("显式 PDB ID/Target Bundle 输入不得携带 structure_prediction")
        if self.workflow.execution_mode is ExecutionMode.UNATTENDED:
            stage02 = self.stage02
            if stage02 is not None:
                if stage02.mode in {
                    RegionProposalMode.AUTOMATIC,
                    RegionProposalMode.DETECT,
                }:
                    if len(stage02.methods) != 1:
                        raise ValueError(
                            "unattended automatic/detect Stage 02 必须恰好配置一种 method"
                        )
                    if stage02.unattended_approval is None:
                        raise ValueError(
                            "unattended automatic/detect Stage 02 必须提供 unattended_approval"
                        )
                if stage02.mode in {
                    RegionProposalMode.USER_PROVIDED,
                    RegionProposalMode.DETECT,
                }:
                    assert stage02.user_regions is not None
                    if stage02.user_regions.approval is None:
                        raise ValueError(
                            "unattended user-provided/detect Stage 02 "
                            "必须在 user_regions 提供 approval"
                        )
        return self

    @property
    def target(self) -> TargetSourceConfig:
        """兼容现有内部调用；规范 YAML 只使用 stage01.target。"""

        return self.stage01.target

    @property
    def structure_prediction(self) -> StructurePredictionConfig | None:
        """兼容现有内部调用；规范 YAML 只使用 stage01.structure_prediction。"""

        return self.stage01.structure_prediction


@dataclass(frozen=True, slots=True)
class LoadedSequenceRunConfig:
    config_path: Path
    config: EasyDesignRunConfig
    source_path: Path
    detected_format: TargetInputFormat
    target: NormalizedProteinSequence
    prediction_request: StructurePredictionRequest | None
    msa_execution_plan: tuple[ResolvedProtenixMsaProviderConfig, ...]
    precomputed_msa_path: Path | None = None
    identity_report: dict[str, Any] | None = None
    scope_report: dict[str, Any] | None = None
    structure_candidates: tuple[dict[str, Any], ...] = ()
    retrieval_records: tuple[dict[str, Any], ...] = ()
    reference_sequence: str | None = None
    prediction_fallback_reason: str | None = None


@dataclass(frozen=True, slots=True)
class LoadedPseRunConfig:
    config_path: Path
    config: EasyDesignRunConfig
    source_path: Path
    detected_format: TargetInputFormat


@dataclass(frozen=True, slots=True)
class LoadedStructureRunConfig:
    config_path: Path
    config: EasyDesignRunConfig
    source_path: Path
    detected_format: TargetInputFormat


@dataclass(frozen=True, slots=True)
class LoadedTargetBundleRunConfig:
    config_path: Path
    config: EasyDesignRunConfig
    source_path: Path
    source_run_root: Path
    detected_format: TargetInputFormat = TargetInputFormat.TARGET_BUNDLE


@dataclass(frozen=True, slots=True)
class LoadedRemoteRunConfig:
    config_path: Path
    config: EasyDesignRunConfig
    source_path: None
    detected_format: TargetInputFormat
    precomputed_msa_path: Path | None = None


LoadedRunConfig: TypeAlias = (
    LoadedSequenceRunConfig
    | LoadedPseRunConfig
    | LoadedStructureRunConfig
    | LoadedTargetBundleRunConfig
    | LoadedRemoteRunConfig
)


_SUFFIX_FORMATS = {
    ".fa": TargetInputFormat.FASTA,
    ".faa": TargetInputFormat.FASTA,
    ".fas": TargetInputFormat.FASTA,
    ".fasta": TargetInputFormat.FASTA,
    ".cif": TargetInputFormat.MMCIF,
    ".mmcif": TargetInputFormat.MMCIF,
    ".pdb": TargetInputFormat.PDB,
    ".ent": TargetInputFormat.PDB,
    ".pse": TargetInputFormat.PSE,
}


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError as error:
        raise TargetInputError(f"Target 文件不是 UTF-8 文本: {path}") from error
    except OSError as error:
        raise TargetInputError(f"Target 文件无法读取: path={path}, error={error}") from error


def _looks_like_sequence(text: str) -> bool:
    letters = "".join(text.split()).upper()
    return bool(letters) and set(letters) <= CANONICAL_AMINO_ACIDS


def _json_is_target_bundle(text: str) -> bool:
    try:
        value: Any = json.loads(text)
    except json.JSONDecodeError:
        return False
    return (
        isinstance(value, dict)
        and "target_structure" in value
        and "sequence_sha256" in value
        and "producer_attempt" in value
    )


def detect_target_input_format(path: Path) -> TargetInputFormat:
    """使用强证据识别输入；无法确定时明确失败，不静默猜测。"""

    suffix = path.suffix.lower()
    declared_by_suffix = _SUFFIX_FORMATS.get(suffix)
    if declared_by_suffix is not None:
        return declared_by_suffix

    text = _read_text(path)
    stripped = text.lstrip()
    if stripped.startswith(">"):
        return TargetInputFormat.FASTA
    if _looks_like_sequence(text):
        return TargetInputFormat.SEQUENCE
    if stripped.startswith("data_") and "_atom_site." in text:
        return TargetInputFormat.MMCIF
    if any(stripped.startswith(prefix) for prefix in ("HEADER", "TITLE ", "ATOM  ", "HETATM")):
        return TargetInputFormat.PDB
    if _json_is_target_bundle(text):
        return TargetInputFormat.TARGET_BUNDLE
    raise TargetInputError(
        f"无法自动识别 Target 文件格式，请在 easydesign.yaml 显式声明 format: {path}"
    )


def _default_source_base_dir(config_path: Path) -> Path:
    """Choose the directory used for relative user-declared source paths."""

    parent = config_path.parent
    if parent.name == "config-revisions":
        candidate = parent.parent
        if (candidate / "easydesign.yaml").is_file() or (candidate / "CONFIG_CURRENT").is_file():
            return candidate
    return parent


def _source_base_dir(config_path: Path, source_base_dir: Path | None) -> Path:
    if source_base_dir is None:
        return _default_source_base_dir(config_path)
    return source_base_dir.expanduser().resolve(strict=True)


def _resolve_source_path(
    config_path: Path,
    source: Path,
    *,
    source_base_dir: Path | None = None,
) -> Path:
    base_dir = _source_base_dir(config_path, source_base_dir)
    candidate = source if source.is_absolute() else base_dir / source
    try:
        resolved = candidate.resolve(strict=True)
    except OSError as error:
        raise ConfigurationError(
            f"target.source 不存在或无法解析: source={source}, config={config_path}"
        ) from error
    if not resolved.is_file():
        raise ConfigurationError(f"target.source 必须是文件: {resolved}")
    return resolved


def _resolve_precomputed_msa_path(
    config_path: Path,
    config: EasyDesignRunConfig,
    *,
    source_base_dir: Path | None = None,
) -> Path | None:
    prediction = config.structure_prediction
    if prediction is None or not isinstance(prediction.msa, PrecomputedProtenixMsaConfig):
        return None
    return _resolve_source_path(
        config_path,
        prediction.msa.path,
        source_base_dir=source_base_dir,
    )


def load_run_config(path: Path, *, source_base_dir: Path | None = None) -> LoadedRunConfig:
    """读取用户 YAML，并返回与已识别 target 类型匹配的排他配置分支。"""

    try:
        config_path = path.resolve(strict=True)
        raw: Any = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as error:
        raise ConfigurationError(f"EasyDesign YAML 无法读取: path={path}, error={error}") from error
    if not isinstance(raw, dict):
        raise ConfigurationError("EasyDesign YAML 顶层必须是 mapping")
    try:
        config = EasyDesignRunConfig.model_validate(raw)
    except ValidationError as error:
        raise ConfigurationError(f"EasyDesign YAML 校验失败: {error}") from error

    source = config.target.source
    if isinstance(source, PdbIdSourceConfig):
        return LoadedRemoteRunConfig(
            config_path=config_path,
            config=config,
            source_path=None,
            detected_format=TargetInputFormat.PDB_ID,
        )
    if isinstance(source, UniProtSourceConfig):
        return LoadedRemoteRunConfig(
            config_path=config_path,
            config=config,
            source_path=None,
            detected_format=TargetInputFormat.UNIPROT,
            precomputed_msa_path=_resolve_precomputed_msa_path(
                config_path,
                config,
                source_base_dir=source_base_dir,
            ),
        )
    if isinstance(source, UniProtSearchSourceConfig):
        return LoadedRemoteRunConfig(
            config_path=config_path,
            config=config,
            source_path=None,
            detected_format=TargetInputFormat.UNIPROT_SEARCH,
            precomputed_msa_path=_resolve_precomputed_msa_path(
                config_path,
                config,
                source_base_dir=source_base_dir,
            ),
        )
    if isinstance(source, TargetBundleSourceConfig):
        source_path = _resolve_source_path(
            config_path,
            source.path,
            source_base_dir=source_base_dir,
        )
        base_dir = _source_base_dir(config_path, source_base_dir)
        run_root = (
            source.source_run_root
            if source.source_run_root.is_absolute()
            else base_dir / source.source_run_root
        )
        try:
            resolved_run_root = run_root.resolve(strict=True)
        except OSError as error:
            raise ConfigurationError(f"target-bundle source_run_root 不存在: {run_root}") from error
        return LoadedTargetBundleRunConfig(
            config_path=config_path,
            config=config,
            source_path=source_path,
            source_run_root=resolved_run_root,
        )
    assert isinstance(source, LocalFileSourceConfig)
    source_path = _resolve_source_path(
        config_path,
        source.path,
        source_base_dir=source_base_dir,
    )
    detected = (
        detect_target_input_format(source_path)
        if source.format is TargetInputFormat.AUTO
        else source.format
    )
    if detected is TargetInputFormat.PSE:
        if config.structure_prediction is not None:
            raise ConfigurationError(
                "PSE 使用导入坐标，必须省略 structure_prediction；禁止启动结构预测"
            )
        if config.workflow.stop_after_stage >= 2 and config.stage02 is None:
            raise ConfigurationError("stop_after_stage >= 2 时必须显式提供 stage02 配置")
        if not isinstance(config.target.scope, FullSequenceScope):
            raise ConfigurationError("Stage 01 1.0 的 PSE 输入只支持 full-sequence scope")
        return LoadedPseRunConfig(
            config_path=config_path,
            config=config,
            source_path=source_path,
            detected_format=detected,
        )
    if detected in {TargetInputFormat.PDB, TargetInputFormat.MMCIF}:
        if config.structure_prediction is not None:
            raise ConfigurationError("本地 PDB/mmCIF 是显式结构选择，必须省略 structure_prediction")
        return LoadedStructureRunConfig(
            config_path=config_path,
            config=config,
            source_path=source_path,
            detected_format=detected,
        )
    if detected is TargetInputFormat.TARGET_BUNDLE:
        raise ConfigurationError(
            "Target Bundle 必须使用 source.type=target-bundle 并显式提供 source_run_root"
        )
    if detected not in {TargetInputFormat.SEQUENCE, TargetInputFormat.FASTA}:
        raise TargetInputError(f"不支持的本地 target format={detected}")
    if config.workflow.stop_after_stage >= 2 and config.stage02 is None:
        raise ConfigurationError("stop_after_stage >= 2 时必须显式提供 stage02 配置")

    text = _read_text(source_path)
    if detected is TargetInputFormat.FASTA:
        target = normalize_fasta(text, target_id=config.target.target_id)
    else:
        target = normalize_raw_sequence(
            text,
            target_id=config.target.target_id,
            source_label=source_path.name,
        )

    prediction = config.structure_prediction
    request: StructurePredictionRequest | None = None
    if prediction is not None:
        try:
            request = StructurePredictionRequest(
                job_name=config.target.target_id,
                target=target,
                seeds=prediction.seeds,
                sample_count=prediction.sample_count,
                msa_mode=prediction.msa.mode,
                template_mode=prediction.template_mode,
                parameter_profile=prediction.parameter_profile,
                cycle_count=prediction.cycle_count,
                diffusion_step_count=prediction.diffusion_step_count,
            )
        except ValidationError as error:
            raise ConfigurationError(f"结构预测配置不符合通用请求契约: {error}") from error
    precomputed_msa_path = _resolve_precomputed_msa_path(
        config_path,
        config,
        source_base_dir=source_base_dir,
    )
    return LoadedSequenceRunConfig(
        config_path=config_path,
        config=config,
        source_path=source_path,
        detected_format=detected,
        target=target,
        prediction_request=request,
        msa_execution_plan=(
            prediction.msa.resolved_providers() if prediction is not None else ()
        ),
        precomputed_msa_path=precomputed_msa_path,
    )


def migrate_run_config(source: Path, destination: Path) -> Path:
    """将旧配置显式写成 canonical 0.7；禁止覆盖原文件或目标文件。"""

    source_path = source.resolve(strict=True)
    target_path = destination.expanduser().resolve()
    if source_path == target_path:
        raise ConfigurationError("config migrate 禁止覆盖原配置")
    if target_path.exists():
        raise ConfigurationError(f"config migrate 目标已存在，禁止覆盖: {target_path}")
    loaded = load_run_config(source_path)
    payload = loaded.config.model_dump(mode="json", by_alias=True, exclude_none=False)
    stage01 = payload["stage01"]
    assert isinstance(stage01, dict)
    target = stage01["target"]
    assert isinstance(target, dict)
    target_source = target["source"]
    assert isinstance(target_source, dict)
    if isinstance(
        loaded,
        (
            LoadedSequenceRunConfig,
            LoadedPseRunConfig,
            LoadedStructureRunConfig,
        ),
    ):
        target_source["path"] = os.path.relpath(
            loaded.source_path,
            target_path.parent,
        )
    elif isinstance(loaded, LoadedTargetBundleRunConfig):
        target_source["path"] = os.path.relpath(
            loaded.source_path,
            target_path.parent,
        )
        target_source["source_run_root"] = os.path.relpath(
            loaded.source_run_root,
            target_path.parent,
        )
    loaded_precomputed_msa = getattr(loaded, "precomputed_msa_path", None)
    if loaded_precomputed_msa is not None:
        prediction = payload["stage01"]["structure_prediction"]
        assert isinstance(prediction, dict)
        msa = prediction["msa"]
        assert isinstance(msa, dict)
        msa["path"] = os.path.relpath(
            loaded_precomputed_msa,
            target_path.parent,
        )
    target_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with target_path.open("x", encoding="utf-8", newline="\n") as handle:
            yaml.safe_dump(
                payload,
                handle,
                allow_unicode=True,
                sort_keys=False,
            )
    except OSError as error:
        raise ConfigurationError(f"无法写入迁移配置: path={target_path}, error={error}") from error
    return target_path
