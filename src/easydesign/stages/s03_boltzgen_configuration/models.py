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
    hotspot_strategy: Literal["H_all"] = "H_all"
    crop_strategy: Literal["C_full"] = "C_full"
    crop_enabled: Literal[False] = False
    target_chain: Literal["A"] = "A"
    binding_label_seq_ids: tuple[int, ...] = Field(min_length=1)
    neutral_residue_policy: Literal["unmarked"] = "unmarked"
    candidates_per_strategy: int = Field(ge=1)
    design_specification_path: str = Field(min_length=1)
    design_specification_sha256: str = Field(pattern=SHA256_PATTERN)

    @model_validator(mode="after")
    def validate_binding_residues(self) -> Self:
        if (
            tuple(sorted(set(self.binding_label_seq_ids)))
            != self.binding_label_seq_ids
        ):
            raise ValueError("binding_label_seq_ids 必须升序且唯一")
        return self


class StrategyBundle(BaseModel):
    """Stage 04 consumes this manifest instead of scanning strategy directories."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["0.1"] = "0.1"
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
    boltzgen_commit: Literal[
        "a3149cf18eeb58648d1abbb27539bd73f746cdda"
    ] = "a3149cf18eeb58648d1abbb27539bd73f746cdda"
    scaffold_assets: tuple[ScaffoldAsset, ...] = Field(min_length=1)
    strategies: tuple[StrategyRecord, ...] = Field(min_length=1)
    random_seed_status: Literal["unsupported-by-boltzgen-0.3.2"] = (
        "unsupported-by-boltzgen-0.3.2"
    )

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
        pairs = {
            (strategy.region_id, strategy.scaffold_id)
            for strategy in self.strategies
        }
        regions = {strategy.region_id for strategy in self.strategies}
        if len(pairs) != len(regions) * len(known):
            raise ValueError("strategy matrix 必须是 region × scaffold 完整笛卡尔积")
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
    backend_commit: Literal[
        "a3149cf18eeb58648d1abbb27539bd73f746cdda"
    ] = "a3149cf18eeb58648d1abbb27539bd73f746cdda"
    checked_at: datetime
    status: Literal["passed", "failed"]
    items: tuple[StrategyValidationItem, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_summary(self) -> Self:
        expected = "passed" if all(item.status == "passed" for item in self.items) else "failed"
        if self.status != expected:
            raise ValueError("validation report 汇总状态与 item 不一致")
        return self
