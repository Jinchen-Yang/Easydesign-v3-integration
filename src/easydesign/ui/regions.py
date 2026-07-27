"""Stage 02 人工重选区的 manifest-only 只读投影。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

from easydesign.core import ArtifactRef, ManifestStateError, StageManifest, load_model

from .models import ArtifactProjection, RegionEditorProjection, RegionEditorResidue
from .projections import _latest_run_manifest
from .security import ArtifactTokenSigner

_STANDARD_COLORS = {
    "#FF0000": "A",
    "#0000FF": "B",
    "#FFFF00": "C",
}


def _stage(
    run_root: Path,
    stage_id: str,
) -> StageManifest | None:
    run, _ = _latest_run_manifest(run_root)
    reference = next(
        (item for item in run.stage_manifest_refs if item.producer_stage == stage_id),
        None,
    )
    return None if reference is None else load_model(reference.verify(run_root), StageManifest)


def _artifact_map(stage: StageManifest) -> dict[str, ArtifactRef]:
    return {item.artifact_id: item for item in stage.output_artifacts}


def _read_json(run_root: Path, reference: ArtifactRef) -> dict[str, Any]:
    value = json.loads(reference.verify(run_root).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ManifestStateError(f"{reference.artifact_id} 必须是 object")
    return value


def get_region_editor_projection(
    run_root: Path,
    *,
    run_key: str,
    signer: ArtifactTokenSigner,
) -> RegionEditorProjection:
    root = run_root.resolve()
    stage01 = _stage(root, "01-target-preparation")
    if stage01 is None:
        raise ManifestStateError("区域编辑器需要 succeeded Stage 01")
    artifacts = _artifact_map(stage01)
    structure = artifacts.get("target-structure")
    mapping_ref = artifacts.get("residue-mapping")
    bundle_ref = artifacts.get("target-bundle")
    if structure is None or mapping_ref is None or bundle_ref is None:
        raise ManifestStateError("Stage 01 缺少结构、编号映射或 Target Bundle")
    structure.verify(root)
    mapping = _read_json(root, mapping_ref)
    bundle = _read_json(root, bundle_ref)

    source_colors: dict[int, str] = {}
    annotation_ref = artifacts.get("source-annotations")
    annotation_status = "not_applicable"
    if annotation_ref is not None:
        annotation = _read_json(root, annotation_ref)
        annotation_status = str(annotation.get("interpretation") or "uninterpreted")
        for row in annotation.get("residues") or []:
            if not isinstance(row, dict):
                continue
            color = str(row.get("ca_color_hex") or "").upper()
            label = row.get("label_seq_id")
            if color in _STANDARD_COLORS and isinstance(label, int):
                source_colors[label] = color

    current_regions: dict[int, str] = {}
    current_source: str | None = None
    stage02 = _stage(root, "02-hotspot-discovery")
    if stage02 is not None:
        hotspots_ref = _artifact_map(stage02).get("hotspots")
        if hotspots_ref is not None:
            hotspots = yaml.safe_load(
                hotspots_ref.verify(root).read_text(encoding="utf-8")
            )
            if isinstance(hotspots, dict):
                region_source = hotspots.get("region_source") or {}
                if isinstance(region_source, dict):
                    current_source = str(region_source.get("type") or "") or None
                for region in hotspots.get("hotspot_sets") or []:
                    if not isinstance(region, dict):
                        continue
                    region_id = str(region.get("id") or "")
                    if region_id not in {"A", "B", "C"}:
                        continue
                    for label in region.get("label_seq_ids") or []:
                        if isinstance(label, int):
                            current_regions[label] = region_id

    rows: list[RegionEditorResidue] = []
    for item in mapping.get("entries") or []:
        if not isinstance(item, dict):
            continue
        label = item.get("label_seq_id")
        sequence_index = item.get("sequence_index")
        if not isinstance(label, int) or not isinstance(sequence_index, int):
            raise ManifestStateError("residue mapping 缺少规范编号")
        rows.append(
            RegionEditorResidue(
                label_seq_id=label,
                amino_acid=str(item.get("amino_acid") or "?"),
                sequence_index=sequence_index,
                auth_chain_id=str(
                    item.get("source_author_chain_id")
                    or item.get("author_chain_id")
                    or "A"
                ),
                auth_residue_id=str(
                    item.get("source_author_residue_id")
                    or item.get("author_residue_id")
                    or label
                ),
                insertion_code=(
                    None
                    if item.get("insertion_code") in {None, "", "?"}
                    else str(item["insertion_code"])
                ),
                reference_position=(
                    item.get("reference_position")
                    if isinstance(item.get("reference_position"), int)
                    else None
                ),
                source_color=source_colors.get(label),
                current_region=current_regions.get(label),
            )
        )
    if not rows:
        raise ManifestStateError("residue mapping 没有可编辑残基")

    return RegionEditorProjection(
        run_key=run_key,
        target_id=str(bundle.get("target_id") or "target"),
        target_structure_sha256=structure.sha256,
        structure=ArtifactProjection(
            artifact_id=structure.artifact_id,
            role=structure.role,
            file_format=structure.file_format,
            size_bytes=structure.size_bytes,
            sha256=structure.sha256,
            token=signer.sign(run_key, structure),
        ),
        source_annotation_status=annotation_status,
        current_region_source=current_source,
        residues=tuple(sorted(rows, key=lambda item: item.label_seq_id)),
    )
