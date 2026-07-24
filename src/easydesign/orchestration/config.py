"""EasyDesign 用户 YAML、target 自动识别和 Stage 01 请求解析。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any, Self, TypeAlias

import yaml  # type: ignore[import-untyped]
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from easydesign.backends.structure_prediction import (
    MsaMode,
    PredictionParameterProfile,
    StructurePredictionRequest,
    TemplateMode,
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


class StructurePredictionConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    backend: str = Field(pattern=ID_PATTERN)
    msa_mode: MsaMode
    template_mode: TemplateMode
    parameter_profile: PredictionParameterProfile = (
        PredictionParameterProfile.MODEL_DEFAULT
    )
    seeds: tuple[int, ...] = (101,)
    sample_count: int = Field(default=1, ge=1)
    cycle_count: int | None = Field(default=None, ge=1)
    diffusion_step_count: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def validate_backend(self) -> Self:
        if self.backend != "protenix-v2":
            raise ValueError("当前 sequence 路径只实现 backend=protenix-v2")
        return self


class WorkflowConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    stop_after_stage: int = Field(default=7, ge=1, le=7)


class EasyDesignRunConfig(BaseModel):
    """用户维护的唯一 run 配置；不包含 Protenix 私有 JSON。"""

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    schema_version: str = Field(default="0.1", pattern=r"^[0-9]+\.[0-9]+$")
    project_id: str = Field(pattern=ID_PATTERN)
    target: TargetSourceConfig
    structure_prediction: StructurePredictionConfig | None = None
    workflow: WorkflowConfig = WorkflowConfig()


@dataclass(frozen=True, slots=True)
class LoadedSequenceRunConfig:
    config_path: Path
    config: EasyDesignRunConfig
    source_path: Path
    detected_format: TargetInputFormat
    target: NormalizedProteinSequence
    prediction_request: StructurePredictionRequest


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
            msa_mode=prediction.msa_mode,
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
    )
