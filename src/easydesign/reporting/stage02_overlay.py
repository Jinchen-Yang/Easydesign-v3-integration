"""Manifest-verified, read-only Stage 02 region projection for Target Viewer."""

from __future__ import annotations

from pathlib import Path
from typing import Literal, cast

import yaml  # type: ignore[import-untyped]
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from easydesign.core import (
    ArtifactRef,
    RunManifest,
    SerializationError,
    StageManifest,
    load_model,
)
from easydesign.safe_writes import read_last_text_line
from easydesign.stages.s01_target_preparation import ResidueMapping, TargetBundle
from easydesign.stages.s02_hotspot_discovery import (
    HotspotsFile,
    RecommendedRegionSet,
    UserProvidedRegionSet,
)

RegionId = Literal["A", "B", "C"]
LayerId = Literal["sasa", "scannet"]
REGION_IDS: tuple[RegionId, ...] = ("A", "B", "C")
REGION_COLORS: dict[RegionId, str] = {
    "A": "#EF4444",
    "B": "#3B82F6",
    "C": "#FACC15",
}


class ViewerRegionResidue(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    label_asym_id: str
    label_seq_id: int = Field(ge=1)


class ViewerRegion(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: RegionId
    color_hex: str
    source_region_id: str
    residues: tuple[ViewerRegionResidue, ...] = Field(min_length=1)


class ViewerRegionLayer(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: Literal["sasa", "scannet", "manual", "approved"]
    label: str
    approved: bool = False
    regions: tuple[ViewerRegion, ...] = Field(min_length=1, max_length=3)


class Stage02ViewerOverlay(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["0.1"] = "0.1"
    layers: tuple[ViewerRegionLayer, ...]


def _latest_run(root: Path) -> RunManifest:
    name = read_last_text_line(root / "manifests/LATEST")
    return load_model(root / "manifests" / name, RunManifest)


def _layers_from_recommendations(
    value: RecommendedRegionSet,
    *,
    layer_id: LayerId,
    label: str,
) -> ViewerRegionLayer | None:
    regions: list[ViewerRegion] = []
    for region_id, source in zip(REGION_IDS, value.regions, strict=False):
        regions.append(
            ViewerRegion(
                id=region_id,
                color_hex=REGION_COLORS[region_id],
                source_region_id=source.region_id,
                residues=tuple(
                    ViewerRegionResidue(
                        label_asym_id=item.label_asym_id,
                        label_seq_id=item.label_seq_id,
                    )
                    for item in source.members
                ),
            )
        )
    return (
        None
        if not regions
        else ViewerRegionLayer(id=layer_id, label=label, regions=tuple(regions))
    )


def _load_hotspots(reference: ArtifactRef, root: Path) -> HotspotsFile:
    path = reference.verify(root)
    if reference.file_format != "yaml":
        raise SerializationError(
            "hotspots artifact 必须由 manifest 声明为 YAML: "
            f"path={path}, file_format={reference.file_format}"
        )
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
        raise SerializationError(
            f"Hotspots YAML 读取失败: path={path}, error={error}"
        ) from error
    try:
        return HotspotsFile.model_validate(raw)
    except ValidationError as error:
        raise SerializationError(
            f"Hotspots 模型校验失败: path={path}, error={error}"
        ) from error


def build_stage02_viewer_overlay(run_root: Path) -> Stage02ViewerOverlay | None:
    root = run_root.resolve()
    run = _latest_run(root)
    stage01_ref = next(
        (
            item
            for item in run.stage_manifest_refs
            if item.producer_stage == "01-target-preparation"
        ),
        None,
    )
    stage02_ref = next(
        (item for item in run.stage_manifest_refs if item.producer_stage == "02-hotspot-discovery"),
        None,
    )
    if stage01_ref is None or stage02_ref is None:
        return None
    stage01 = load_model(stage01_ref.verify(root), StageManifest)
    stage02 = load_model(stage02_ref.verify(root), StageManifest)
    bundle = load_model(stage01.require_output("target-bundle").verify(root), TargetBundle)
    mapping = load_model(bundle.residue_mapping.verify(root), ResidueMapping)
    mapping_by_label = {item.label_seq_id: item for item in mapping.entries}
    artifacts = {item.artifact_id: item for item in stage02.output_artifacts}
    layers: list[ViewerRegionLayer] = []
    layer_specs: tuple[tuple[str, LayerId, str], ...] = (
        ("sasa-recommended-regions", "sasa", "SASA surface diversity"),
        ("scannet-recommended-regions", "scannet", "ScanNet epitope no-MSA"),
    )
    for artifact_id, layer_id, label in layer_specs:
        reference = artifacts.get(artifact_id)
        if reference is None:
            continue
        recommended = load_model(reference.verify(root), RecommendedRegionSet)
        layer = _layers_from_recommendations(
            recommended, layer_id=layer_id, label=label
        )
        if layer is not None:
            layers.append(layer)
    user_reference = artifacts.get("user-provided-regions")
    if user_reference is not None:
        user_regions = load_model(user_reference.verify(root), UserProvidedRegionSet)
        regions = tuple(
            ViewerRegion(
                id=cast(RegionId, item.id),
                color_hex=REGION_COLORS[cast(RegionId, item.id)],
                source_region_id=item.source_region_id,
                residues=tuple(
                    ViewerRegionResidue(
                        label_asym_id=member.label_asym_id,
                        label_seq_id=member.label_seq_id,
                    )
                    for member in item.members
                ),
            )
            for item in user_regions.regions
        )
        layers.append(ViewerRegionLayer(id="manual", label="Manual regions", regions=regions))
    hotspots_reference = artifacts.get("hotspots")
    if hotspots_reference is not None:
        hotspots = _load_hotspots(hotspots_reference, root)
        approved_regions: list[ViewerRegion] = []
        for item in hotspots.hotspot_sets:
            if item.id not in REGION_COLORS:
                continue
            approved_id = item.id
            residues = []
            for label_seq_id in item.label_seq_ids:
                mapped = mapping_by_label.get(label_seq_id)
                if mapped is None:
                    raise ValueError("hotspots.yaml 引用了 mapping 中不存在的 label_seq_id")
                residues.append(
                    ViewerRegionResidue(
                        label_asym_id=mapped.label_chain_id,
                        label_seq_id=label_seq_id,
                    )
                )
            approved_regions.append(
                ViewerRegion(
                    id=approved_id,
                    color_hex=REGION_COLORS[approved_id],
                    source_region_id=item.source_region_id,
                    residues=tuple(residues),
                )
            )
        if approved_regions:
            layers.append(
                ViewerRegionLayer(
                    id="approved",
                    label="Approved hotspots",
                    approved=True,
                    regions=tuple(approved_regions),
                )
            )
    return None if not layers else Stage02ViewerOverlay(layers=tuple(layers))


__all__ = ["Stage02ViewerOverlay", "build_stage02_viewer_overlay"]
