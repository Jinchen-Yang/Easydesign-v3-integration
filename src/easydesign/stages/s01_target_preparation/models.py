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


class CoordinateEnsemble(BaseModel):
    """规范 target.cif 中的 coordinate model 集合。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    model_count: int = Field(ge=1)
    model_ids: tuple[str, ...] = Field(min_length=1)
    representative_model_id: str = Field(min_length=1, max_length=32)
    residue_identity_policy: str = Field(
        default="shared-label-seq-id",
        pattern=r"^shared-label-seq-id$",
    )

    @model_validator(mode="after")
    def validate_models(self) -> Self:
        if self.model_count != len(self.model_ids):
            raise ValueError("coordinate ensemble model_count 与 model_ids 数量不一致")
        if len(self.model_ids) != len(set(self.model_ids)):
            raise ValueError("coordinate ensemble model_ids 不能重复")
        if self.representative_model_id not in self.model_ids:
            raise ValueError("representative_model_id 必须属于 model_ids")
        return self


class ResidueMappingEntry(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    sequence_index: int = Field(ge=1)
    amino_acid: str = Field(pattern=r"^[ACDEFGHIKLMNPQRSTVWY]$")
    label_chain_id: str = Field(min_length=1, max_length=16)
    label_seq_id: int = Field(ge=1)
    author_chain_id: str = Field(min_length=1, max_length=16)
    author_residue_id: str = Field(min_length=1, max_length=32)
    insertion_code: str | None = Field(default=None, max_length=8)
    source_label_chain_id: str | None = Field(default=None, max_length=16)
    source_author_chain_id: str | None = Field(default=None, max_length=16)
    source_author_residue_id: str | None = Field(default=None, max_length=32)
    reference_position: int | None = Field(default=None, ge=1)
    coordinate_present: bool = Field(
        default=True,
        exclude_if=lambda value: value is True,
    )
    model_presence: tuple[str, ...] = ()
    source_residue_name: str | None = Field(default=None, max_length=8)


class ResidueMapping(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: str = "0.2"
    target_id: str = Field(pattern=ID_PATTERN)
    sequence_sha256: str = Field(pattern=SHA256_PATTERN)
    entries: tuple[ResidueMappingEntry, ...]

    @model_validator(mode="after")
    def validate_mapping(self) -> Self:
        if self.schema_version not in {"0.1", "0.2", "0.3"}:
            raise ValueError(f"不支持 ResidueMapping schema: {self.schema_version}")
        indices = [entry.sequence_index for entry in self.entries]
        if indices != list(range(1, len(self.entries) + 1)):
            raise ValueError("残基映射 sequence_index 必须从 1 连续递增")
        if any(
            not entry.coordinate_present and entry.model_presence
            for entry in self.entries
        ):
            raise ValueError("无坐标残基不能声明 model_presence")
        return self


class StructureQualityReport(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: str = "0.2"
    origin: TargetStructureOrigin = TargetStructureOrigin.PREDICTED
    backend_name: str = Field(pattern=ID_PATTERN)
    backend_version: str = Field(min_length=1, max_length=128)
    model_name: str = Field(pattern=ID_PATTERN)
    seed: int = Field(ge=0)
    sample_index: int = Field(ge=0)
    plddt: float
    gpde: float | None = None
    ptm: float | None = None
    iptm: float | None = None
    ranking_score: float
    has_clash: bool
    recycle_count: int = Field(ge=0)
    coordinate_model_count: int = Field(default=1, ge=1)
    scope_coverage: float = Field(default=1.0, ge=0, le=1)
    scope_sequence_identity: float = Field(default=1.0, ge=0, le=1)


class ImportedStructureQualityReport(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: str = "0.1"
    origin: TargetStructureOrigin = TargetStructureOrigin.IMPORTED
    coordinate_state_count: int = Field(ge=1)
    protein_chain_count: int = Field(ge=1)
    residue_count: int = Field(ge=1)
    canonical_residue_count: int = Field(ge=1)
    residues_with_ca: int = Field(ge=1)
    missing_ca_count: int = Field(ge=0)
    ligand_heavy_atom_count: int = Field(ge=0)
    water_residue_count: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_imported_quality(self) -> Self:
        if self.coordinate_state_count != 1 or self.protein_chain_count != 1:
            raise ValueError("当前 imported PSE quality 必须是单 state、单 chain")
        if not (
            self.residue_count
            == self.canonical_residue_count
            == self.residues_with_ca
        ):
            raise ValueError("imported PSE residue/标准残基/CA 计数必须一致")
        if self.missing_ca_count != 0 or self.ligand_heavy_atom_count != 0:
            raise ValueError("当前 imported PSE 不允许缺失 CA 或配体重原子")
        return self


class SessionInventoryRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(min_length=1)
    object_type: str = Field(min_length=1)
    state_count: int = Field(ge=0)
    atom_count: int = Field(ge=0)
    protein_atom_count: int = Field(ge=0)
    ignored: bool


class ImportedStructureProvenance(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: str = "0.1"
    source_format: str = Field(default="pse", pattern=r"^pse$")
    source_sha256: str = Field(pattern=SHA256_PATTERN)
    backend_name: str = Field(default="pymol-pse", pattern=ID_PATTERN)
    backend_version: str = Field(min_length=1, max_length=128)
    selected_object: str = Field(min_length=1)
    author_chain_id: str = Field(min_length=1, max_length=16)
    coordinate_state: int = Field(ge=1)
    inventory: tuple[SessionInventoryRecord, ...]
    worker_runtime_seconds: float = Field(ge=0)
    adapter_runtime_seconds: float = Field(ge=0)
    fallback_used: bool = False

    @model_validator(mode="after")
    def validate_imported_provenance(self) -> Self:
        if self.coordinate_state != 1:
            raise ValueError("当前 PSE provenance 只接受 coordinate_state=1")
        if self.fallback_used:
            raise ValueError("PSE 导入禁止 fallback")
        return self


class ResidueColorAnnotation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    label_seq_id: int = Field(ge=1)
    author_chain_id: str = Field(min_length=1, max_length=16)
    author_residue_id: str = Field(min_length=1, max_length=32)
    insertion_code: str | None = Field(default=None, max_length=8)
    ca_color_index: int = Field(ge=0)
    ca_color_rgb: tuple[float, float, float]
    ca_color_hex: str = Field(pattern=r"^#[0-9A-F]{6}$")


class ColorCount(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    ca_color_index: int = Field(ge=0)
    ca_color_rgb: tuple[float, float, float]
    ca_color_hex: str = Field(pattern=r"^#[0-9A-F]{6}$")
    residue_count: int = Field(ge=1)


class PseSourceAnnotations(BaseModel):
    """只保存来源颜色，不赋予 hotspot 或能量学语义。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: str = "0.1"
    annotation_type: str = Field(default="pymol-ca-color", pattern=r"^pymol-ca-color$")
    interpretation: str = Field(default="uninterpreted", pattern=r"^uninterpreted$")
    residues: tuple[ResidueColorAnnotation, ...]
    color_counts: tuple[ColorCount, ...]

    @model_validator(mode="after")
    def validate_annotations(self) -> Self:
        indices = [residue.label_seq_id for residue in self.residues]
        if indices != list(range(1, len(self.residues) + 1)):
            raise ValueError("PSE color annotation label_seq_id 必须连续")
        if sum(group.residue_count for group in self.color_counts) != len(self.residues):
            raise ValueError("PSE color count 与逐残基 annotation 数量不一致")
        return self


class PredictionProvenance(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: str = "0.2"
    source_kind: SequenceSourceKind
    source_label: str
    sequence_sha256: str = Field(pattern=SHA256_PATTERN)
    backend_name: str = Field(pattern=ID_PATTERN)
    backend_version: str = Field(min_length=1, max_length=128)
    model_name: str = Field(pattern=ID_PATTERN)
    model_checkpoint_sha256: str = Field(pattern=SHA256_PATTERN)
    raw_checkpoint_sha256: str | None = Field(default=None, pattern=SHA256_PATTERN)
    converted_weight_sha256: str | None = Field(default=None, pattern=SHA256_PATTERN)
    wheel_sha256: str | None = Field(default=None, pattern=SHA256_PATTERN)
    runner_commit: str | None = None
    release_identity: dict[str, str] = Field(default_factory=dict)
    msa_mode: MsaMode
    msa_input_sha256: str | None = Field(default=None, pattern=SHA256_PATTERN)
    msa_server_mode: str | None = Field(default=None, pattern=ID_PATTERN)
    msa_provider: str | None = Field(default=None, pattern=ID_PATTERN)
    msa_endpoint: str | None = None
    msa_depth: int | None = Field(default=None, ge=1)
    msa_query_sha256: str | None = Field(default=None, pattern=SHA256_PATTERN)
    msa_ticket: str | None = Field(default=None, min_length=1, max_length=256)
    msa_ticket_status: str | None = Field(default=None, min_length=1, max_length=128)
    paired_msa_mode: MsaMode = MsaMode.DISABLED
    paired_msa_input_sha256: str | None = Field(
        default=None,
        pattern=SHA256_PATTERN,
    )
    template_mode: TemplateMode
    template_data_sha256: str | None = Field(default=None, pattern=SHA256_PATTERN)
    parameter_profile: PredictionParameterProfile
    resolved_cycle_count: int = Field(ge=1)
    resolved_diffusion_step_count: int = Field(ge=1)
    seed: int = Field(ge=0)
    sample_index: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_msa_evidence(self) -> Self:
        if self.backend_name == "openfold3-af3-jax" and set(self.release_identity) != {
            "release_id",
            "backend_id",
            "backend_version",
            "model_id",
            "adapter_contract_version",
            "release_manifest_sha256",
            "conversion_receipt_sha256",
            "raw_checkpoint_sha256",
            "converted_weight_sha256",
            "wheel_sha256",
            "environment_lock_sha256",
            "runner_commit",
            "runner_tree_sha256",
        }:
            raise ValueError("AFO prediction provenance 缺少完整 release identity")
        detailed_values = (
            self.msa_provider,
            self.msa_endpoint,
            self.msa_depth,
            self.msa_query_sha256,
            self.msa_ticket,
            self.msa_ticket_status,
        )
        if self.msa_mode is MsaMode.DISABLED:
            if (
                self.msa_input_sha256 is not None
                or self.msa_server_mode is not None
                or any(value is not None for value in detailed_values)
            ):
                raise ValueError("disabled MSA 不能声明 MSA 产物或服务")
        elif self.msa_input_sha256 is None:
            raise ValueError("启用 MSA 时必须声明消费的 MSA input SHA-256")
        if self.msa_mode is MsaMode.REMOTE and self.msa_server_mode is None:
            raise ValueError("remote MSA 必须声明服务模式")
        if self.schema_version != "0.1" and self.msa_mode is MsaMode.REMOTE:
            required = (
                self.msa_provider,
                self.msa_endpoint,
                self.msa_depth,
                self.msa_query_sha256,
                self.msa_ticket_status,
            )
            if any(value is None for value in required):
                raise ValueError(
                    "remote MSA provenance 0.2 "
                    "缺少 provider/endpoint/depth/query/status"
                )
        if self.paired_msa_mode is MsaMode.DISABLED:
            if self.paired_msa_input_sha256 is not None:
                raise ValueError("disabled paired MSA 不能声明 input SHA-256")
        elif self.paired_msa_mode in {
            MsaMode.PRECOMPUTED,
            MsaMode.QUERY_ONLY,
        } and self.paired_msa_input_sha256 is None:
            raise ValueError("paired MSA 启用时必须冻结 input SHA-256")
        if self.template_mode is TemplateMode.DISABLED:
            if self.template_data_sha256 is not None:
                raise ValueError("disabled template 不能声明 data SHA-256")
        elif self.template_data_sha256 is None:
            raise ValueError("precomputed template 必须冻结 data SHA-256")
        return self


class TargetBundle(BaseModel):
    """Stage 02 可消费的规范 Target Bundle 引用集合。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: str = "0.3"
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
    source_annotations: ArtifactRef | None = None
    coordinate_ensemble: CoordinateEnsemble | None = None
    reference_sequence: ArtifactRef | None = None
    residue_mapping_tsv: ArtifactRef | None = None
    identity_report: ArtifactRef | None = None
    scope_report: ArtifactRef | None = None
    structure_candidates: ArtifactRef | None = None
    structure_candidates_tsv: ArtifactRef | None = None
    retrieval_manifest: ArtifactRef | None = None
    source_context: ArtifactRef | None = None
    design_context: ArtifactRef | None = None
    prediction_confidence: ArtifactRef | None = None
    target_pdb: ArtifactRef | None = None

    @model_validator(mode="after")
    def validate_artifact_producers(self) -> Self:
        artifacts = (
            self.target_structure,
            self.sequence,
            self.residue_mapping,
            self.quality_report,
            self.provenance,
        )
        optional_artifacts = tuple(
            artifact
            for artifact in (
                self.source_annotations,
                self.reference_sequence,
                self.residue_mapping_tsv,
                self.identity_report,
                self.scope_report,
                self.structure_candidates,
                self.structure_candidates_tsv,
                self.retrieval_manifest,
                self.source_context,
                self.design_context,
                self.prediction_confidence,
                self.target_pdb,
            )
            if artifact is not None
        )
        all_artifacts = artifacts + optional_artifacts
        for artifact in all_artifacts:
            if artifact.producer_stage != STAGE_ID:
                raise ValueError(f"Target Bundle artifact 必须由 {STAGE_ID} 产生")
            if artifact.producer_attempt != self.producer_attempt:
                raise ValueError("Target Bundle artifact 必须来自同一 attempt")
        if self.schema_version == "0.1" and self.source_annotations is not None:
            raise ValueError("Target Bundle 0.1 不支持 source_annotations")
        if self.schema_version in {"0.1", "0.2"}:
            if self.coordinate_ensemble is not None:
                raise ValueError(
                    f"Target Bundle {self.schema_version} 不支持 coordinate_ensemble"
                )
        elif self.schema_version in {"0.3", "0.4"}:
            if self.coordinate_ensemble is None:
                raise ValueError(
                    f"Target Bundle {self.schema_version} 必须声明 coordinate_ensemble"
                )
        else:
            raise ValueError(f"不支持 Target Bundle schema: {self.schema_version}")
        if self.schema_version != "0.4" and any(
            artifact is not None
            for artifact in (
                self.reference_sequence,
                self.residue_mapping_tsv,
                self.identity_report,
                self.scope_report,
                self.structure_candidates,
                self.structure_candidates_tsv,
                self.retrieval_manifest,
                self.source_context,
                self.design_context,
                self.prediction_confidence,
                self.target_pdb,
            )
        ):
            raise ValueError("Target Bundle 0.1–0.3 不支持 Stage 01 evidence artifact 扩展")
        return self


class BuiltTargetBundle(BaseModel):
    """写入完成后的 bundle 和 bundle 自身引用。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    bundle: TargetBundle
    bundle_path: Path
    bundle_artifact: ArtifactRef
