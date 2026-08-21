"""PSE 颜色与 YAML 人工残基的统一、确定性区域规范化。"""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Iterable
from pathlib import Path
from typing import TypeVar

from easydesign.core import ManifestStateError, load_model
from easydesign.stages.s01_target_preparation import (
    PseSourceAnnotations,
    ResidueMapping,
    ResidueMappingEntry,
    TargetBundle,
)

from .geometry import ResidueGeometry, StructureContext
from .models import (
    ManualResidueListRegionSource,
    PseColorRegionSource,
    ResidueIdentity,
    UserProvidedRegion,
    UserProvidedRegionSet,
    UserRegionSourceEvidence,
    UserRegionValidationReport,
)

PSE_COLOR_SCHEME = "easydesign-rby-v1"
PSE_REGION_COLORS = {
    "#FF0000": "A",
    "#0000FF": "B",
    "#FFFF00": "C",
}
REGION_ORDER = {"A": 0, "B": 1, "C": 2}
KeyT = TypeVar("KeyT")
ValueT = TypeVar("ValueT")


def _distance(
    left: tuple[float, float, float],
    right: tuple[float, float, float],
) -> float:
    return math.sqrt(
        sum((a - b) ** 2 for a, b in zip(left, right, strict=True))
    )


def _minimum_atom_distance(
    left: ResidueGeometry,
    right: ResidueGeometry,
) -> float:
    return min(
        _distance(left_atom.xyz, right_atom.xyz)
        for left_atom in left.atoms
        for right_atom in right.atoms
    )


def _component_count(
    context: StructureContext,
    labels: tuple[int, ...],
) -> int:
    """只报告区域的 3D 连续性；不会据此改写或拒绝用户成员。"""

    if not labels:
        return 0
    model = context.models[context.representative_model_id]
    graph: dict[int, set[int]] = {label: set() for label in labels}
    for index, left_label in enumerate(labels):
        left = model.residues[left_label]
        for right_label in labels[index + 1 :]:
            right = model.residues[right_label]
            if (
                _distance(left.center, right.center) <= 12.0
                and _minimum_atom_distance(left, right) <= 5.0
            ):
                graph[left_label].add(right_label)
                graph[right_label].add(left_label)
    remaining = set(labels)
    count = 0
    while remaining:
        count += 1
        pending = [remaining.pop()]
        while pending:
            current = pending.pop()
            neighbors = graph[current].intersection(remaining)
            remaining.difference_update(neighbors)
            pending.extend(neighbors)
    return count


def _centroid(
    context: StructureContext,
    labels: tuple[int, ...],
) -> tuple[float, float, float]:
    model = context.models[context.representative_model_id]
    centers = [model.residues[label].center for label in labels]
    return tuple(
        sum(center[axis] for center in centers) / len(centers)
        for axis in range(3)
    )  # type: ignore[return-value]


def _mapping_identity(entry: ResidueMappingEntry) -> ResidueIdentity:
    return ResidueIdentity(
        sequence_index=entry.sequence_index,
        amino_acid=entry.amino_acid,
        label_asym_id=entry.label_chain_id,
        label_seq_id=entry.label_seq_id,
        auth_asym_id=entry.author_chain_id,
        auth_seq_id=entry.author_residue_id,
        source_auth_asym_id=entry.source_author_chain_id,
        source_auth_seq_id=entry.source_author_residue_id,
        insertion_code=entry.insertion_code,
    )


def _build_results(
    *,
    bundle: TargetBundle,
    context: StructureContext,
    region_source: PseColorRegionSource | ManualResidueListRegionSource,
    region_members: dict[str, tuple[tuple[ResidueIdentity, str], ...]],
    source_artifact_id: str | None,
    source_artifact_sha256: str | None,
    background_color_counts: dict[str, int] | None = None,
    standard_color_counts: dict[str, int] | None = None,
) -> tuple[
    UserProvidedRegionSet,
    UserRegionSourceEvidence,
    UserRegionValidationReport,
]:
    representative = context.models[context.representative_model_id]
    regions: list[UserProvidedRegion] = []
    component_counts: dict[str, int] = {}
    all_warnings: list[str] = []
    labels_by_region: dict[str, set[int]] = {}
    for region_id in sorted(region_members, key=REGION_ORDER.__getitem__):
        pairs = sorted(
            region_members[region_id],
            key=lambda pair: pair[0].label_seq_id,
        )
        identities = tuple(pair[0] for pair in pairs)
        selectors = tuple(pair[1] for pair in pairs)
        labels = tuple(identity.label_seq_id for identity in identities)
        missing = [label for label in labels if label not in representative.residues]
        if missing:
            raise ManifestStateError(
                f"区域 {region_id} 的残基不在代表模型 "
                f"{context.representative_model_id} 中: {missing}"
            )
        components = _component_count(context, labels)
        component_counts[region_id] = components
        region_warnings: list[str] = []
        if components > 1:
            warning = (
                f"region-{region_id}-has-{components}-spatial-components;"
                "user-members-preserved"
            )
            region_warnings.append(warning)
            all_warnings.append(warning)
        regions.append(
            UserProvidedRegion(
                id=region_id,
                source_region_id=f"user-region-{region_id.lower()}",
                members=identities,
                source_selectors=selectors,
                centroid_angstrom=_centroid(context, labels),
                warnings=tuple(region_warnings),
            )
        )
        labels_by_region[region_id] = set(labels)

    overlaps: dict[str, tuple[int, ...]] = {}
    region_ids = sorted(labels_by_region, key=REGION_ORDER.__getitem__)
    for index, left in enumerate(region_ids):
        for right in region_ids[index + 1 :]:
            shared = tuple(sorted(labels_by_region[left] & labels_by_region[right]))
            if shared:
                overlaps[f"{left}-{right}"] = shared
                all_warnings.append(
                    f"regions-{left}-{right}-overlap-at-label-seq-ids:"
                    + ",".join(str(label) for label in shared)
                    + ";user-members-preserved"
                )

    model_ids = (
        bundle.coordinate_ensemble.model_ids
        if bundle.coordinate_ensemble is not None
        else ("1",)
    )
    region_set = UserProvidedRegionSet(
        target_id=bundle.target_id,
        target_structure_sha256=bundle.target_structure.sha256,
        sequence_sha256=bundle.sequence_sha256,
        coordinate_model_ids=model_ids,
        representative_model_id=context.representative_model_id,
        region_source=region_source,
        regions=tuple(regions),
        warnings=tuple(all_warnings),
    )
    evidence = UserRegionSourceEvidence(
        target_id=bundle.target_id,
        region_source=region_source,
        source_artifact_id=source_artifact_id,
        source_artifact_sha256=source_artifact_sha256,
        configured_selectors={
            region.id: region.source_selectors for region in region_set.regions
        },
        background_color_counts=background_color_counts or {},
        standard_color_counts=standard_color_counts or {},
    )
    validation = UserRegionValidationReport(
        target_id=bundle.target_id,
        representative_model_id=context.representative_model_id,
        region_count=len(region_set.regions),
        member_counts={
            region.id: len(region.members) for region in region_set.regions
        },
        spatial_component_counts=component_counts,
        cross_region_overlaps=overlaps,
        warnings=tuple(all_warnings),
    )
    return region_set, evidence, validation


def has_standard_pse_colors(
    *,
    run_root: Path,
    bundle: TargetBundle,
) -> bool:
    """校验 annotation artifact 后判断是否存在固定红/蓝/黄。"""

    if bundle.source_annotations is None:
        return False
    path = bundle.source_annotations.verify(run_root)
    annotations = load_model(path, PseSourceAnnotations)
    return any(
        residue.ca_color_hex.upper() in PSE_REGION_COLORS
        for residue in annotations.residues
    )


def normalize_pse_color_regions(
    *,
    run_root: Path,
    bundle: TargetBundle,
    context: StructureContext,
    mapping: ResidueMapping,
) -> tuple[
    UserProvidedRegionSet,
    UserRegionSourceEvidence,
    UserRegionValidationReport,
]:
    if bundle.source_annotations is None:
        raise ManifestStateError(
            "pse-colors 需要 Target Bundle 声明 source-annotations artifact"
        )
    annotations_path = bundle.source_annotations.verify(run_root)
    annotations = load_model(annotations_path, PseSourceAnnotations)
    entries = {entry.label_seq_id: entry for entry in mapping.entries}
    grouped: dict[str, list[tuple[ResidueIdentity, str]]] = {}
    standard_counts: Counter[str] = Counter()
    background_counts: Counter[str] = Counter()
    for annotation in annotations.residues:
        entry = entries.get(annotation.label_seq_id)
        if entry is None:
            raise ManifestStateError(
                "PSE annotation 引用了 mapping 中不存在的 label_seq_id="
                f"{annotation.label_seq_id}"
            )
        if (
            annotation.author_chain_id != entry.author_chain_id
            or annotation.author_residue_id != entry.author_residue_id
            or annotation.insertion_code != entry.insertion_code
        ):
            raise ManifestStateError(
                "PSE annotation 与 residue mapping 的 author 编号不一致: "
                f"label_seq_id={annotation.label_seq_id}"
            )
        hex_color = annotation.ca_color_hex.upper()
        region_id = PSE_REGION_COLORS.get(hex_color)
        if region_id is None:
            background_counts[hex_color] += 1
            continue
        standard_counts[hex_color] += 1
        grouped.setdefault(region_id, []).append(
            (
                _mapping_identity(entry),
                (
                    f"{annotation.author_chain_id}:"
                    f"{annotation.author_residue_id}"
                    f"{annotation.insertion_code or ''}"
                    f"@{hex_color}"
                ),
            )
        )
    if not grouped:
        raise ManifestStateError(
            "PSE annotation 中没有 easydesign-rby-v1 标准红/蓝/黄区域"
        )
    source = PseColorRegionSource(
        source_annotation_sha256=bundle.source_annotations.sha256,
    )
    return _build_results(
        bundle=bundle,
        context=context,
        region_source=source,
        region_members={
            region_id: tuple(members) for region_id, members in grouped.items()
        },
        source_artifact_id=bundle.source_annotations.artifact_id,
        source_artifact_sha256=bundle.source_annotations.sha256,
        background_color_counts=dict(sorted(background_counts.items())),
        standard_color_counts=dict(sorted(standard_counts.items())),
    )


def _unique_index(
    pairs: Iterable[tuple[KeyT, ValueT]],
    *,
    namespace: str,
) -> dict[KeyT, ValueT]:
    index: dict[KeyT, ValueT] = {}
    duplicates: set[KeyT] = set()
    for key, value in pairs:
        if key in index:
            duplicates.add(key)
        index[key] = value
    if duplicates:
        raise ManifestStateError(
            f"{namespace} numbering 在 Target Bundle 中不唯一: "
            + ", ".join(str(value) for value in sorted(duplicates, key=str))
        )
    return index


def normalize_manual_regions(
    *,
    bundle: TargetBundle,
    context: StructureContext,
    mapping: ResidueMapping,
    numbering: str,
    chain: str | None,
    configured_regions: Iterable[tuple[str, tuple[str, ...]]],
    input_config_sha256: str,
) -> tuple[
    UserProvidedRegionSet,
    UserRegionSourceEvidence,
    UserRegionValidationReport,
]:
    entries = mapping.entries
    if numbering == "sequence":
        index = _unique_index(
            ((str(entry.sequence_index), entry) for entry in entries),
            namespace="sequence",
        )
    elif numbering == "label":
        index = _unique_index(
            ((str(entry.label_seq_id), entry) for entry in entries),
            namespace="label",
        )
    elif numbering == "auth":
        if chain is None:
            raise ManifestStateError("auth numbering 必须显式提供 chain")
        source_entries = tuple(
            entry
            for entry in entries
            if entry.source_author_chain_id == chain
            and entry.source_author_residue_id is not None
        )
        normalized_entries = tuple(
            entry for entry in entries if entry.author_chain_id == chain
        )
        selected_entries = source_entries or normalized_entries
        namespace = (
            f"source-auth-chain-{chain}"
            if source_entries
            else f"normalized-auth-chain-{chain}"
        )
        index = _unique_index(
            (
                (
                    (entry.source_author_residue_id or entry.author_residue_id)
                    + (entry.insertion_code or ""),
                    entry,
                )
                for entry in selected_entries
            ),
            namespace=namespace,
        )
        if not index:
            raise ManifestStateError(
                f"Target Bundle 中不存在 source 或 normalized auth chain={chain}"
            )
    elif numbering == "uniprot":
        if any(entry.reference_position is None for entry in entries):
            raise ManifestStateError(
                "uniprot numbering 需要完整、可靠的 UniProt residue mapping"
            )
        index = _unique_index(
            ((str(entry.reference_position), entry) for entry in entries),
            namespace="uniprot",
        )
    else:
        raise ManifestStateError(f"未知人工区域 numbering: {numbering}")

    grouped: dict[str, tuple[tuple[ResidueIdentity, str], ...]] = {}
    for region_id, selectors in configured_regions:
        resolved: list[tuple[ResidueIdentity, str]] = []
        for selector in selectors:
            entry = index.get(selector)
            if entry is None:
                chain_text = f", chain={chain}" if chain is not None else ""
                raise ManifestStateError(
                    f"区域 {region_id} 的 {numbering} selector 无法唯一映射: "
                    f"{selector}{chain_text}"
                )
            resolved.append((_mapping_identity(entry), selector))
        grouped[region_id] = tuple(resolved)

    source = ManualResidueListRegionSource(
        numbering=numbering,  # type: ignore[arg-type]
        chain=chain,
        input_config_sha256=input_config_sha256,
    )
    return _build_results(
        bundle=bundle,
        context=context,
        region_source=source,
        region_members=grouped,
        source_artifact_id="resolved-run-config",
        source_artifact_sha256=input_config_sha256,
    )
