"""与具体模型无关的结构预测请求、调用和结果契约。"""

from __future__ import annotations

from datetime import date
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


class ScientificMode(StrEnum):
    """Backward-compatible evidence label; it never gates chain features."""

    DE_NOVO = "de-novo"
    TARGET_CONDITIONED = "target-conditioned"


class TargetResidueNumbering(BaseModel):
    """Auditable conversion from Stage 01 numbering to template indices."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    sequence_index: int = Field(ge=1)
    query_index: int = Field(ge=0)
    template_index: int = Field(ge=0)
    label_seq_id: int = Field(ge=1)
    author_chain_id: str = Field(min_length=1, max_length=16)
    author_residue_id: str = Field(min_length=1, max_length=32)
    insertion_code: str | None = Field(default=None, max_length=8)


class TargetStructureCondition(BaseModel):
    """Frozen target-only provenance shared by AFO and Protenix.

    The binder empty-template fields remain only for schema-0.3 resume.  Binder
    template capability is controlled independently by ``ProteinPredictionChain``.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["0.3"] = "0.3"
    template_mode: Literal["target-conditioned"] = "target-conditioned"
    source_origin: Literal["experimental", "imported", "predicted"]
    source_structure_kind: Literal[
        "experimental", "predicted", "imported-unknown"
    ]
    source_backend_name: str | None = Field(default=None, pattern=ID_PATTERN)
    source_structure_sha256: str = Field(pattern=SHA256_PATTERN)
    snapshot_structure_path: Path
    snapshot_structure_sha256: str = Field(pattern=SHA256_PATTERN)
    snapshot_pdb_path: Path | None = None
    snapshot_pdb_sha256: str | None = Field(default=None, pattern=SHA256_PATTERN)
    template_structure_path: Path
    template_structure_sha256: str = Field(pattern=SHA256_PATTERN)
    template_release_date: date
    template_release_date_source: Literal[
        "source-mmcif", "synthetic-conservative"
    ]
    template_data_path: Path
    template_data_sha256: str = Field(pattern=SHA256_PATTERN)
    binder_template_data_path: Path
    binder_template_data_sha256: str = Field(pattern=SHA256_PATTERN)
    run_snapshot_relative_path: str = Field(min_length=1)
    target_chain_id: Literal["A"] = "A"
    template_chain_id: str = Field(min_length=1, max_length=16)
    query_indices: tuple[int, ...] = Field(min_length=1)
    template_indices: tuple[int, ...] = Field(min_length=1)
    missing_query_indices: tuple[int, ...] = ()
    residue_numbering: tuple[TargetResidueNumbering, ...] = Field(min_length=1)
    screening_profile_id: Literal["target-conditioned-evidence-v1"] = (
        "target-conditioned-evidence-v1"
    )
    automatic_template_search: Literal[False] = False
    binder_templates_enabled: Literal[False] = False

    @model_validator(mode="after")
    def validate_condition(self) -> Self:
        if not self.snapshot_structure_path.is_absolute():
            raise ValueError("target condition structure path 必须是绝对路径")
        if not self.template_data_path.is_absolute():
            raise ValueError("target condition template data path 必须是绝对路径")
        if not self.binder_template_data_path.is_absolute():
            raise ValueError("binder empty-template data path 必须是绝对路径")
        if not self.template_structure_path.is_absolute():
            raise ValueError("target condition template structure path 必须是绝对路径")
        if (self.snapshot_pdb_path is None) != (self.snapshot_pdb_sha256 is None):
            raise ValueError("target condition PDB path/SHA 必须同时存在或缺失")
        if self.snapshot_pdb_path is not None and not self.snapshot_pdb_path.is_absolute():
            raise ValueError("target condition PDB path 必须是绝对路径")
        if self.source_structure_sha256 != self.snapshot_structure_sha256:
            raise ValueError("target condition source/snapshot SHA-256 必须一致")
        if len(self.query_indices) != len(self.template_indices):
            raise ValueError("target condition query/template indices 数量必须一致")
        if tuple(sorted(set(self.query_indices))) != self.query_indices:
            raise ValueError("target condition query indices 必须严格递增且唯一")
        if len(set(self.template_indices)) != len(self.template_indices):
            raise ValueError("target condition template indices 不能重复")
        if tuple(sorted(set(self.missing_query_indices))) != self.missing_query_indices:
            raise ValueError("target condition missing query indices 必须递增且唯一")
        if set(self.query_indices).intersection(self.missing_query_indices):
            raise ValueError("target condition mapped/missing query indices 不能重叠")
        if tuple(item.query_index for item in self.residue_numbering) != (
            self.query_indices
        ):
            raise ValueError("target condition numbering 与 query indices 不一致")
        if tuple(item.template_index for item in self.residue_numbering) != (
            self.template_indices
        ):
            raise ValueError("target condition numbering 与 template indices 不一致")
        if self.source_origin == "predicted" and self.source_backend_name is None:
            raise ValueError("predicted target condition 必须记录 source backend")
        if self.source_origin != "predicted" and self.source_backend_name is not None:
            raise ValueError("非 predicted target condition 不能伪造 source backend")
        expected_kind = {
            "experimental": "experimental",
            "predicted": "predicted",
            "imported": "imported-unknown",
        }[self.source_origin]
        if self.source_structure_kind != expected_kind:
            raise ValueError("target condition source origin/kind 不一致")
        return self

    def is_self_conditioned_for(self, backend_name: str) -> bool:
        return (
            self.source_origin == "predicted"
            and self.source_backend_name == backend_name
        )


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
    """One independently configurable protein chain in a complex request.

    The global ``msa_mode``/``template_mode`` fields on the enclosing request are
    retained as a legacy default.  New callers should set the per-chain modes so
    target and binder features can be combined without a scientific-mode gate.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    chain_id: str = Field(pattern=r"^[A-Za-z0-9]{1,4}$")
    role: Literal["target", "binder"]
    sequence: str = Field(pattern=r"^[ACDEFGHIKLMNPQRSTVWY]+$")
    unpaired_msa_mode: MsaMode | None = None
    unpaired_msa_path: Path | None = None
    paired_msa_mode: MsaMode | None = None
    paired_msa_path: Path | None = None
    template_mode: TemplateMode | None = None
    template_data_path: Path | None = None
    template_data_sha256: str | None = Field(default=None, pattern=SHA256_PATTERN)

    @model_validator(mode="after")
    def validate_feature_inputs(self) -> Self:
        msa_inputs = (
            ("unpaired", self.unpaired_msa_mode, self.unpaired_msa_path),
            ("paired", self.paired_msa_mode, self.paired_msa_path),
        )
        for label, mode, path in msa_inputs:
            if path is not None and not path.is_absolute():
                raise ValueError("complex prediction MSA path 必须是绝对路径")
            if mode is MsaMode.PRECOMPUTED and path is None:
                raise ValueError(f"{label} precomputed MSA 必须提供 path")
            if mode in {MsaMode.DISABLED, MsaMode.REMOTE} and path is not None:
                raise ValueError(f"{label} {mode} MSA 不能同时提供 path")
        if (self.template_data_path is None) != (
            self.template_data_sha256 is None
        ):
            raise ValueError("template data path/SHA-256 必须同时存在或缺失")
        if (
            self.template_data_path is not None
            and not self.template_data_path.is_absolute()
        ):
            raise ValueError("complex prediction template data path 必须是绝对路径")
        if (
            self.template_mode is TemplateMode.PRECOMPUTED
            and self.template_data_path is None
        ):
            raise ValueError("precomputed template 必须提供 data path/SHA-256")
        if (
            self.template_mode is TemplateMode.DISABLED
            and self.template_data_path is not None
        ):
            raise ValueError("disabled template 不能同时提供 data path")
        return self

    @staticmethod
    def _resolved_msa_mode(
        explicit_mode: MsaMode | None,
        path: Path | None,
        legacy_mode: MsaMode,
    ) -> MsaMode:
        if explicit_mode is not None:
            return explicit_mode
        if path is not None:
            return MsaMode.PRECOMPUTED
        if legacy_mode is MsaMode.REMOTE:
            return MsaMode.REMOTE
        return MsaMode.DISABLED

    def resolved_unpaired_msa_mode(self, legacy_mode: MsaMode) -> MsaMode:
        return self._resolved_msa_mode(
            self.unpaired_msa_mode,
            self.unpaired_msa_path,
            legacy_mode,
        )

    def resolved_paired_msa_mode(self, legacy_mode: MsaMode) -> MsaMode:
        return self._resolved_msa_mode(
            self.paired_msa_mode,
            self.paired_msa_path,
            legacy_mode,
        )

    def resolved_template_mode(
        self,
        legacy_mode: TemplateMode,
        *,
        legacy_target_condition_available: bool,
    ) -> TemplateMode:
        if self.template_mode is not None:
            return self.template_mode
        if self.template_data_path is not None:
            return TemplateMode.PRECOMPUTED
        if legacy_target_condition_available and self.role == "target":
            return legacy_mode
        return TemplateMode.DISABLED


class ComplexStructurePredictionRequest(BaseModel):
    """Target+binder prediction request shared by Stage 05 and Stage 07."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    job_name: str = Field(pattern=ID_PATTERN)
    chains: tuple[ProteinPredictionChain, ...] = Field(min_length=2)
    seeds: tuple[int, ...] = (101,)
    sample_count: int = Field(default=1, ge=1)
    msa_mode: MsaMode
    template_mode: TemplateMode = TemplateMode.DISABLED
    scientific_mode: ScientificMode = ScientificMode.DE_NOVO
    target_structure_condition: TargetStructureCondition | None = None
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
        if self.target_structure_condition is not None:
            target = self.require_role("target")
            if target.chain_id != self.target_structure_condition.target_chain_id:
                raise ValueError("target condition chain 与 target chain 不一致")
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
