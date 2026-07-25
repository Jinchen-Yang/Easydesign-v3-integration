"""EasyDesign 用户 YAML、target 自动识别和 Stage 01 请求解析。"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any, Self, TypeAlias

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
from easydesign.core.artifacts import ID_PATTERN


class TargetInputFormat(StrEnum):
    """用户声明或 EasyDesign 自动识别的 target source 类型。"""

    AUTO = "auto"
    SEQUENCE = "sequence"
    FASTA = "fasta"
    MMCIF = "mmcif"
    PDB = "pdb"
    PSE = "pse"
    TARGET_BUNDLE = "target-bundle"


class TargetIdentityConfig(BaseModel):
    """用户明确提供的生物学身份；首版禁止按名称静默猜测。"""

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    uniprot_accession: str | None = Field(
        default=None,
        pattern=r"^[A-Z0-9]{6,10}(?:-[0-9]+)?$",
    )


class TargetSourceConfig(BaseModel):
    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        populate_by_name=True,
        str_strip_whitespace=True,
    )

    target_id: str = Field(alias="id", pattern=ID_PATTERN)
    source: Path
    format: TargetInputFormat = TargetInputFormat.AUTO
    identity: TargetIdentityConfig = TargetIdentityConfig()


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


class ProtenixMsaConfig(BaseModel):
    """sequence/FASTA 用户路径的 MSA 硬性策略；当前不允许 no-MSA。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    mode: MsaMode = MsaMode.REMOTE
    providers: tuple[ProtenixMsaProviderConfig, ...] = (
        ProtenixMsaProviderConfig(),
    )
    no_msa_fallback: bool = False

    @model_validator(mode="after")
    def validate_msa_policy(self) -> Self:
        if self.mode is not MsaMode.REMOTE:
            raise ValueError(
                "EasyDesign sequence/FASTA 主线当前必须使用 mode=remote；"
                "no-MSA 只允许内部工程 smoke"
            )
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


class StructurePredictionConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    backend: str = Field(pattern=ID_PATTERN)
    msa: ProtenixMsaConfig
    template_mode: TemplateMode
    parameter_profile: PredictionParameterProfile = (
        PredictionParameterProfile.MODEL_DEFAULT
    )
    seeds: tuple[int, ...] = (101,)
    sample_count: int = Field(default=1, ge=1)
    prediction_timeout_seconds: int = Field(default=7200, ge=60, le=86400)
    cycle_count: int | None = Field(default=None, ge=1)
    diffusion_step_count: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def validate_backend(self) -> Self:
        if self.backend != "protenix-v2":
            raise ValueError("当前 sequence 路径只实现 backend=protenix-v2")
        if len(self.seeds) != 1 or self.sample_count != 1:
            raise ValueError(
                "Stage 01 v0.1 必须恰好一个 seed 和一个 sample，避免静默选择预测结构"
            )
        return self


class WorkflowConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    stop_after_stage: int = Field(default=1, ge=1, le=7)


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


class Stage01Config(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    target: TargetSourceConfig
    structure_prediction: StructurePredictionConfig | None = None


class RegionProposalMode(StrEnum):
    AUTOMATIC = "automatic"
    PSE_ANNOTATIONS = "pse_annotations"
    MANUAL = "manual"


class Stage02Method(StrEnum):
    SASA = "sasa"
    SCANNET = "scannet"


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
                raise ValueError(
                    "region_count 与 requested_region_count 不能同时出现"
                )
            migrated["requested_region_count"] = migrated.pop("region_count")
            return migrated
        return value

    @model_validator(mode="after")
    def validate_avoid(self) -> Self:
        if self.minimum_region_count > self.requested_region_count:
            raise ValueError(
                "minimum_region_count 不能高于 requested_region_count"
            )
        if any(value < 1 for value in self.avoid_label_seq_ids):
            raise ValueError("avoid_label_seq_ids 必须为正整数")
        if len(self.avoid_label_seq_ids) != len(set(self.avoid_label_seq_ids)):
            raise ValueError("avoid_label_seq_ids 不能重复")
        return self

    @property
    def region_count(self) -> int:
        """兼容内部 v0.1 调用；序列化只使用 requested_region_count。"""

        return self.requested_region_count


class Stage02Config(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    mode: RegionProposalMode = RegionProposalMode.AUTOMATIC
    methods: tuple[Stage02Method, ...] = ()
    annotations: Stage02AnnotationConfig = Stage02AnnotationConfig()
    automatic: Stage02AutomaticConfig | None = Stage02AutomaticConfig()

    @model_validator(mode="before")
    @classmethod
    def default_methods_for_mode(cls, value: Any) -> Any:
        if not isinstance(value, dict) or "methods" in value:
            return value
        migrated = dict(value)
        mode = migrated.get("mode", RegionProposalMode.AUTOMATIC)
        migrated["methods"] = (
            [Stage02Method.SASA, Stage02Method.SCANNET]
            if mode == RegionProposalMode.AUTOMATIC
            or mode == str(RegionProposalMode.AUTOMATIC)
            else []
        )
        return migrated

    @model_validator(mode="after")
    def validate_mode(self) -> Self:
        if self.mode is RegionProposalMode.AUTOMATIC and self.automatic is None:
            raise ValueError("Stage 02 automatic 模式必须提供 automatic 配置")
        if self.mode is RegionProposalMode.AUTOMATIC and not self.methods:
            raise ValueError("Stage 02 automatic 模式至少选择一种 methods")
        if len(self.methods) != len(set(self.methods)):
            raise ValueError("Stage 02 methods 不能重复")
        if self.mode is not RegionProposalMode.AUTOMATIC and self.automatic is not None:
            raise ValueError("未实现的 Stage 02 模式不得携带 automatic 配置")
        if self.mode is not RegionProposalMode.AUTOMATIC and self.methods:
            raise ValueError("未实现的 Stage 02 模式不得选择 automatic methods")
        return self


class EasyDesignRunConfig(BaseModel):
    """用户维护的唯一 run 配置；不包含 Protenix 私有 JSON。"""

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    schema_version: str = Field(default="0.3", pattern=r"^0\.3$")
    project_id: str = Field(pattern=ID_PATTERN)
    design: DesignConfig = DesignConfig()
    stage01: Stage01Config
    stage02: Stage02Config | None = None
    stage03: None = None
    stage04: None = None
    stage05: None = None
    stage06: None = None
    stage07: None = None
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
            migrated["schema_version"] = "0.3"
        return migrated

    @model_validator(mode="after")
    def validate_stage_sequence(self) -> Self:
        if self.workflow.stop_after_stage >= 2 and self.stage02 is None:
            raise ValueError("stop_after_stage >= 2 时必须显式提供 stage02")
        if self.workflow.stop_after_stage >= 3:
            raise ValueError(
                "Stage 03–07 尚未实现；对应配置必须为 null，"
                "stop_after_stage 当前不能高于 2"
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
    prediction_request: StructurePredictionRequest
    msa_execution_plan: tuple[ResolvedProtenixMsaProviderConfig, ...]


@dataclass(frozen=True, slots=True)
class LoadedPseRunConfig:
    config_path: Path
    config: EasyDesignRunConfig
    source_path: Path
    detected_format: TargetInputFormat


LoadedRunConfig: TypeAlias = LoadedSequenceRunConfig | LoadedPseRunConfig


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
    if any(
        stripped.startswith(prefix)
        for prefix in ("HEADER", "TITLE ", "ATOM  ", "HETATM")
    ):
        return TargetInputFormat.PDB
    if _json_is_target_bundle(text):
        return TargetInputFormat.TARGET_BUNDLE
    raise TargetInputError(
        f"无法自动识别 Target 文件格式，请在 easydesign.yaml 显式声明 format: {path}"
    )


def _resolve_source_path(config_path: Path, source: Path) -> Path:
    candidate = source if source.is_absolute() else config_path.parent / source
    try:
        resolved = candidate.resolve(strict=True)
    except OSError as error:
        raise ConfigurationError(
            f"target.source 不存在或无法解析: source={source}, config={config_path}"
        ) from error
    if not resolved.is_file():
        raise ConfigurationError(f"target.source 必须是文件: {resolved}")
    return resolved


def load_run_config(path: Path) -> LoadedRunConfig:
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

    source_path = _resolve_source_path(config_path, config.target.source)
    detected = (
        detect_target_input_format(source_path)
        if config.target.format is TargetInputFormat.AUTO
        else config.target.format
    )
    if detected is TargetInputFormat.PSE:
        if config.structure_prediction is not None:
            raise ConfigurationError(
                "PSE 使用导入坐标，必须省略 structure_prediction；禁止启动结构预测"
            )
        if config.workflow.stop_after_stage >= 2 and config.stage02 is None:
            raise ConfigurationError(
                "stop_after_stage >= 2 时必须显式提供 stage02 配置"
            )
        return LoadedPseRunConfig(
            config_path=config_path,
            config=config,
            source_path=source_path,
            detected_format=detected,
        )
    if detected not in {TargetInputFormat.SEQUENCE, TargetInputFormat.FASTA}:
        raise TargetInputError(
            f"已识别 target format={detected}，但该入口尚未实现；禁止回退到序列预测"
        )
    if config.structure_prediction is None:
        raise ConfigurationError(
            "sequence/FASTA 输入必须显式提供 structure_prediction"
        )
    if config.workflow.stop_after_stage >= 2 and config.stage02 is None:
        raise ConfigurationError(
            "stop_after_stage >= 2 时必须显式提供 stage02 配置"
        )

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
    return LoadedSequenceRunConfig(
        config_path=config_path,
        config=config,
        source_path=source_path,
        detected_format=detected,
        target=target,
        prediction_request=request,
        msa_execution_plan=prediction.msa.resolved_providers(),
    )


def migrate_run_config(source: Path, destination: Path) -> Path:
    """将旧配置显式写成 canonical 0.3；禁止覆盖原文件或目标文件。"""

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
    target["source"] = os.path.relpath(loaded.source_path, target_path.parent)
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
        raise ConfigurationError(
            f"无法写入迁移配置: path={target_path}, error={error}"
        ) from error
    return target_path
