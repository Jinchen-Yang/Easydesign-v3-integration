"""Stage 03 strategy bundle and validation contracts."""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from easydesign.core.artifacts import ID_PATTERN, SHA256_PATTERN

STAGE_ID = "03-boltzgen-configuration"
BOLTZGEN_VERSION = "0.3.2"
BOLTZGEN_COMMIT = "a3149cf18eeb58648d1abbb27539bd73f746cdda"
SCAFFOLD_REGISTRY_ID = "official-vhh7-v1"
STRATEGY_PROFILE_ID = "boltzgen-vhh-basic-v1"
ExperimentRole = Literal[
    "baseline",
    "diagnostic",
    "integrated-alternative",
    "confirmatory",
]


class TargetCrop(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    start: int = Field(ge=1)
    end: int = Field(ge=1)

    @model_validator(mode="after")
    def validate_order(self) -> Self:
        if self.end < self.start:
            raise ValueError("target crop end 不能小于 start")
        return self


class CdrOverride(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    cdr: Literal[1, 2, 3]
    design_res_index: str = Field(pattern=r"^[0-9]+(?:\.\.[0-9]+)?(?:,[0-9]+(?:\.\.[0-9]+)?)*$")
    insertion_num_residues: str = Field(pattern=r"^[0-9]+(?:\.\.[0-9]+)?$")


class ExplicitStrategyVariant(BaseModel):
    """One intentional experiment; scaffold expansion is local to this variant."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    variant_id: str = Field(pattern=ID_PATTERN)
    hotspot_set_id: str | None = None
    binding_label_seq_ids: tuple[int, ...] | None = None
    scaffold_ids: tuple[str, ...] = Field(min_length=1)
    target_crop: TargetCrop | None = None
    cdr_overrides: tuple[CdrOverride, ...] = ()
    candidates_per_strategy: int = Field(default=40, ge=1)
    hypothesis_id: str | None = Field(default=None, pattern=ID_PATTERN)
    role: ExperimentRole | None = None
    evidence_refs: tuple[str, ...] = ()
    changed_factors: tuple[str, ...] = ()
    held_constant: tuple[str, ...] = ()
    rationale: str | None = Field(default=None, min_length=1, max_length=4096)
    expected_result: str | None = Field(default=None, min_length=1, max_length=4096)
    failure_interpretation: str | None = Field(default=None, min_length=1, max_length=4096)

    @model_validator(mode="after")
    def validate_selection(self) -> Self:
        if self.hotspot_set_id is None and self.binding_label_seq_ids is None:
            raise ValueError("variant 必须选择 hotspot_set_id 或 binding residues")
        if len(self.scaffold_ids) != len(set(self.scaffold_ids)):
            raise ValueError("variant scaffold_ids 不能重复")
        if self.binding_label_seq_ids is not None:
            normalized = tuple(sorted(set(self.binding_label_seq_ids)))
            if normalized != self.binding_label_seq_ids or any(value < 1 for value in normalized):
                raise ValueError("binding residues 必须升序、唯一且为正整数")
        cdrs = [item.cdr for item in self.cdr_overrides]
        if len(cdrs) != len(set(cdrs)):
            raise ValueError("同一 CDR 只能覆盖一次")
        _validate_experiment_metadata(self)
        return self


class NativeStrategyVariant(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    variant_id: str = Field(pattern=ID_PATTERN)
    scaffold_id: str = Field(pattern=ID_PATTERN)
    yaml_text: str = Field(min_length=1)
    source_sha256: str = Field(pattern=SHA256_PATTERN)
    candidates_per_strategy: int = Field(default=40, ge=1)
    hypothesis_id: str | None = Field(default=None, pattern=ID_PATTERN)
    role: ExperimentRole | None = None
    evidence_refs: tuple[str, ...] = ()
    changed_factors: tuple[str, ...] = ()
    held_constant: tuple[str, ...] = ()
    rationale: str | None = Field(default=None, min_length=1, max_length=4096)
    expected_result: str | None = Field(default=None, min_length=1, max_length=4096)
    failure_interpretation: str | None = Field(default=None, min_length=1, max_length=4096)

    @model_validator(mode="after")
    def validate_source_identity(self) -> Self:
        import hashlib

        if hashlib.sha256(self.yaml_text.encode("utf-8")).hexdigest() != self.source_sha256:
            raise ValueError("native BoltzGen YAML 文本与 source_sha256 不一致")
        _validate_experiment_metadata(self)
        return self


def _validate_experiment_metadata(
    value: ExplicitStrategyVariant | NativeStrategyVariant | StrategyRecord,
) -> None:
    """Allow old technical callers, but reject partially recorded experiments."""

    present = (
        value.hypothesis_id is not None,
        value.role is not None,
        bool(value.evidence_refs),
        bool(value.changed_factors),
        bool(value.held_constant),
        value.rationale is not None,
        value.expected_result is not None,
        value.failure_interpretation is not None,
    )
    if any(present) and not all(present):
        raise ValueError("experiment metadata 必须完整记录，不能只填写部分字段")
    for field_name in ("evidence_refs", "changed_factors", "held_constant"):
        items = getattr(value, field_name)
        if any(not item.strip() for item in items):
            raise ValueError(f"{field_name} 不能包含空值")
        if len(items) != len(set(items)):
            raise ValueError(f"{field_name} 不能重复")


class ScaffoldAsset(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    scaffold_id: str = Field(pattern=ID_PATTERN)
    specification_path: str = Field(min_length=1)
    specification_sha256: str = Field(pattern=SHA256_PATTERN)
    structure_path: str = Field(min_length=1)
    structure_sha256: str = Field(pattern=SHA256_PATTERN)
    source_repository: str = Field(min_length=1)
    source_commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    license: Literal["MIT"] = "MIT"


class StrategyRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    strategy_id: str = Field(pattern=ID_PATTERN)
    region_id: str = Field(pattern=ID_PATTERN)
    source_hotspot_set_id: str = Field(min_length=1, max_length=64)
    scaffold_id: str = Field(pattern=ID_PATTERN)
    hotspot_strategy: str = Field(default="H_all", min_length=1)
    crop_strategy: str = Field(default="C_full", min_length=1)
    crop_enabled: bool = False
    target_chain: Literal["A"] = "A"
    binding_label_seq_ids: tuple[int, ...] = Field(min_length=1)
    neutral_residue_policy: Literal["unmarked"] = "unmarked"
    candidates_per_strategy: int = Field(ge=1)
    design_specification_path: str = Field(min_length=1)
    design_specification_sha256: str = Field(pattern=SHA256_PATTERN)
    variant_scaffold_path: str | None = None
    variant_scaffold_sha256: str | None = Field(default=None, pattern=SHA256_PATTERN)
    native_source_sha256: str | None = Field(default=None, pattern=SHA256_PATTERN)
    hypothesis_id: str | None = Field(default=None, pattern=ID_PATTERN)
    role: ExperimentRole | None = None
    evidence_refs: tuple[str, ...] = ()
    changed_factors: tuple[str, ...] = ()
    held_constant: tuple[str, ...] = ()
    rationale: str | None = Field(default=None, min_length=1, max_length=4096)
    expected_result: str | None = Field(default=None, min_length=1, max_length=4096)
    failure_interpretation: str | None = Field(default=None, min_length=1, max_length=4096)

    @model_validator(mode="after")
    def validate_variant_scaffold(self) -> Self:
        if (self.variant_scaffold_path is None) != (self.variant_scaffold_sha256 is None):
            raise ValueError("variant scaffold path 与 checksum 必须同时存在")
        return self

    @model_validator(mode="after")
    def validate_binding_residues(self) -> Self:
        if tuple(sorted(set(self.binding_label_seq_ids))) != self.binding_label_seq_ids:
            raise ValueError("binding_label_seq_ids 必须升序且唯一")
        _validate_experiment_metadata(self)
        return self


class StrategyBundle(BaseModel):
    """Stage 04 consumes this manifest instead of scanning strategy directories."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["0.1", "0.2", "0.3"] = "0.3"
    generated_at: datetime
    project_id: str = Field(pattern=ID_PATTERN)
    run_id: str = Field(pattern=ID_PATTERN)
    target_id: str = Field(pattern=ID_PATTERN)
    target_structure_sha256: str = Field(pattern=SHA256_PATTERN)
    target_bundle_sha256: str = Field(pattern=SHA256_PATTERN)
    hotspots_sha256: str = Field(pattern=SHA256_PATTERN)
    source_stage02_manifest_sha256: str = Field(pattern=SHA256_PATTERN)
    validation_report_sha256: str = Field(pattern=SHA256_PATTERN)
    strategy_profile: Literal["boltzgen-vhh-basic-v1"] = "boltzgen-vhh-basic-v1"
    scaffold_registry: Literal["official-vhh7-v1"] = "official-vhh7-v1"
    boltzgen_version: Literal["0.3.2"] = "0.3.2"
    boltzgen_commit: Literal["a3149cf18eeb58648d1abbb27539bd73f746cdda"] = (
        "a3149cf18eeb58648d1abbb27539bd73f746cdda"
    )
    scaffold_assets: tuple[ScaffoldAsset, ...] = Field(min_length=1)
    strategies: tuple[StrategyRecord, ...] = Field(min_length=1)
    random_seed_status: Literal["unsupported-by-boltzgen-0.3.2"] = "unsupported-by-boltzgen-0.3.2"

    @model_validator(mode="after")
    def validate_matrix(self) -> Self:
        scaffold_ids = [asset.scaffold_id for asset in self.scaffold_assets]
        if len(scaffold_ids) != len(set(scaffold_ids)):
            raise ValueError("scaffold asset ID 不能重复")
        strategy_ids = [strategy.strategy_id for strategy in self.strategies]
        if len(strategy_ids) != len(set(strategy_ids)):
            raise ValueError("strategy_id 不能重复")
        known = set(scaffold_ids)
        if any(strategy.scaffold_id not in known for strategy in self.strategies):
            raise ValueError("strategy 引用了 registry 外的 scaffold")
        if self.schema_version == "0.1":
            pairs = {(strategy.region_id, strategy.scaffold_id) for strategy in self.strategies}
            regions = {strategy.region_id for strategy in self.strategies}
            if len(pairs) != len(regions) * len(known):
                raise ValueError("0.1 strategy matrix 必须是 region × scaffold 完整笛卡尔积")
        return self


class StrategyValidationItem(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    strategy_id: str = Field(pattern=ID_PATTERN)
    status: Literal["passed", "failed"]
    return_code: int
    stdout_sha256: str = Field(pattern=SHA256_PATTERN)
    stderr_sha256: str = Field(pattern=SHA256_PATTERN)
    stdout_path: str | None = None
    stderr_path: str | None = None
    message: str = Field(max_length=4096)


class StrategyValidationReport(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["0.1"] = "0.1"
    backend_name: Literal["boltzgen"] = "boltzgen"
    backend_version: Literal["0.3.2"] = "0.3.2"
    backend_commit: Literal["a3149cf18eeb58648d1abbb27539bd73f746cdda"] = (
        "a3149cf18eeb58648d1abbb27539bd73f746cdda"
    )
    checked_at: datetime
    status: Literal["passed", "failed"]
    items: tuple[StrategyValidationItem, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_summary(self) -> Self:
        expected = "passed" if all(item.status == "passed" for item in self.items) else "failed"
        if self.status != expected:
            raise ValueError("validation report 汇总状态与 item 不一致")
        return self
