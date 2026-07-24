"""与具体模型无关的结构预测请求、调用和结果契约。"""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from easydesign.backends.target_sources import NormalizedProteinSequence
from easydesign.core.artifacts import ID_PATTERN, SHA256_PATTERN


class MsaMode(StrEnum):
    DISABLED = "disabled"
    REMOTE = "remote"
    PRECOMPUTED = "precomputed"


class TemplateMode(StrEnum):
    DISABLED = "disabled"
    PRECOMPUTED = "precomputed"


class PredictionParameterProfile(StrEnum):
    MODEL_DEFAULT = "model-default"
    CUSTOM = "custom"


class StructurePredictionRequest(BaseModel):
    """Stage 可向任意兼容结构预测后端提交的最小请求。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    job_name: str = Field(pattern=ID_PATTERN)
    target: NormalizedProteinSequence
    seeds: tuple[int, ...] = (101,)
    sample_count: int = Field(default=1, ge=1)
    msa_mode: MsaMode
    template_mode: TemplateMode = TemplateMode.DISABLED
    parameter_profile: PredictionParameterProfile = (
        PredictionParameterProfile.MODEL_DEFAULT
    )
    cycle_count: int | None = Field(default=None, ge=1)
    diffusion_step_count: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def validate_request(self) -> Self:
        if not self.seeds or len(self.seeds) != len(set(self.seeds)):
            raise ValueError("seeds 必须非空且不能重复")
        if any(seed < 0 for seed in self.seeds):
            raise ValueError("seed 不能为负数")
        custom_values = (self.cycle_count, self.diffusion_step_count)
        if self.parameter_profile is PredictionParameterProfile.CUSTOM:
            if any(value is None for value in custom_values):
                raise ValueError("custom profile 必须同时声明 cycle_count 和 diffusion_step_count")
        elif any(value is not None for value in custom_values):
            raise ValueError("model-default profile 不能覆盖 cycle/step")
        return self


class BackendInvocation(BaseModel):
    """交给 executor 的无 shell 调用计划。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    backend_name: str = Field(pattern=ID_PATTERN)
    backend_version: str = Field(min_length=1, max_length=128)
    argv: tuple[str, ...]
    environment: tuple[tuple[str, str], ...] = ()
    timeout_seconds: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def validate_invocation(self) -> Self:
        if not self.argv or any(not value for value in self.argv):
            raise ValueError("argv 不能为空且不能包含空参数")
        keys = [key for key, _ in self.environment]
        if len(keys) != len(set(keys)):
            raise ValueError("environment 变量名不能重复")
        if any(not key or not value for key, value in self.environment):
            raise ValueError("environment 变量名和值都不能为空")
        return self


class StructurePredictionProduct(BaseModel):
    """一个 seed/sample 的规范化结构预测结果。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    backend_name: str = Field(pattern=ID_PATTERN)
    backend_version: str = Field(min_length=1, max_length=128)
    model_name: str = Field(pattern=ID_PATTERN)
    seed: int = Field(ge=0)
    sample_index: int = Field(ge=0)
    structure_path: Path
    structure_sha256: str = Field(pattern=SHA256_PATTERN)
    confidence_path: Path
    confidence_sha256: str = Field(pattern=SHA256_PATTERN)
    plddt: float
    gpde: float
    ptm: float
    iptm: float
    ranking_score: float
    has_clash: bool
    recycle_count: int = Field(ge=0)
