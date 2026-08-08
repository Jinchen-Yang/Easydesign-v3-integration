"""与具体模型无关的结构预测请求、调用和结果契约。"""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Literal, Self, TypeAlias

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
    require_full_confidence: bool = False

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


class ProteinPredictionChain(BaseModel):
    """A typed protein chain for a complex-prediction file protocol."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    chain_id: str = Field(pattern=r"^[A-Za-z0-9]{1,4}$")
    role: Literal["target", "binder"]
    sequence: str = Field(pattern=r"^[ACDEFGHIKLMNPQRSTVWY]+$")
    paired_msa_path: Path | None = None
    unpaired_msa_path: Path | None = None

    @model_validator(mode="after")
    def validate_msa_paths(self) -> Self:
        for path in (self.paired_msa_path, self.unpaired_msa_path):
            if path is not None and not path.is_absolute():
                raise ValueError("complex prediction MSA path 必须是绝对路径")
        return self


class ComplexStructurePredictionRequest(BaseModel):
    """Target+binder prediction request shared by Stage 05 and Stage 07."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    job_name: str = Field(pattern=ID_PATTERN)
    chains: tuple[ProteinPredictionChain, ...] = Field(min_length=2)
    seeds: tuple[int, ...] = (101,)
    sample_count: int = Field(default=1, ge=1)
    msa_mode: MsaMode
    template_mode: TemplateMode = TemplateMode.DISABLED
    parameter_profile: PredictionParameterProfile = (
        PredictionParameterProfile.MODEL_DEFAULT
    )
    cycle_count: int | None = Field(default=None, ge=1)
    diffusion_step_count: int | None = Field(default=None, ge=1)
    require_full_confidence: Literal[True] = True

    @model_validator(mode="after")
    def validate_request(self) -> Self:
        chain_ids = [chain.chain_id for chain in self.chains]
        if len(chain_ids) != len(set(chain_ids)):
            raise ValueError("complex prediction chain_id 不能重复")
        roles = [chain.role for chain in self.chains]
        if roles.count("target") != 1 or roles.count("binder") != 1:
            raise ValueError("首版 complex prediction 必须恰好一个 target 和一个 binder")
        if len(self.chains) != 2:
            raise ValueError("首版 complex prediction 只接受 target+binder 两条链")
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
        if self.msa_mode is MsaMode.DISABLED:
            raise ValueError("Stage 05/07 complex prediction 禁止 no-MSA")
        return self

    def require_role(self, role: Literal["target", "binder"]) -> ProteinPredictionChain:
        return next(chain for chain in self.chains if chain.role == role)


PredictionRequest = StructurePredictionRequest | ComplexStructurePredictionRequest

NativeMetricValue: TypeAlias = str | int | float | bool | None


class ComplexConfidenceMetrics(BaseModel):
    """跨结构预测后端可比较的 target(A)-binder(B) 置信度。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    metric_definition_version: str = Field(pattern=ID_PATTERN)
    pairwise_iptm: float
    minimum_interface_pae_angstrom: float = Field(ge=0)
    binder_ptm: float
    target_token_count: int = Field(ge=1)
    binder_token_count: int = Field(ge=1)


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
    full_confidence_path: Path | None = None
    full_confidence_sha256: str | None = Field(default=None, pattern=SHA256_PATTERN)
    plddt: float
    gpde: float | None = None
    ptm: float | None
    iptm: float | None
    ranking_score: float
    has_clash: bool
    recycle_count: int = Field(ge=0)
    complex_confidence: ComplexConfidenceMetrics | None = None
    native_metrics: dict[str, NativeMetricValue] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_full_confidence(self) -> Self:
        if (self.full_confidence_path is None) != (
            self.full_confidence_sha256 is None
        ):
            raise ValueError("full confidence path/hash 必须同时存在或同时缺失")
        return self

    @property
    def backend_identity(self) -> str:
        return f"{self.backend_name}@{self.backend_version}"

    @property
    def model_identity(self) -> str:
        return self.model_name

    @property
    def mean_plddt(self) -> float:
        return self.plddt
