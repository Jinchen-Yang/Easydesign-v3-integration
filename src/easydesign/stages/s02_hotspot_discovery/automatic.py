"""SASA 与 ScanNet 两条互不融合的候选表面区域生成算法。"""

from __future__ import annotations

import heapq
import itertools
import math
from dataclasses import dataclass

import Bio
from Bio.PDB.SASA import ShrakeRupley

from .geometry import (
    StructureContext,
    build_residue_graph,
    center_distance,
    minimum_region_atom_distance,
    radius_gyration,
    region_centroid,
    shell_overlap,
)
from .models import (
    AnnotationStatus,
    CandidateRegionPool,
    CandidateSurfaceRegion,
    MethodComparison,
    PairwiseSeparation,
    RecommendedRegionSet,
    RegionMethod,
    RegionMetrics,
    RegionOverlap,
    RegionReviewStatus,
    ResidueEvidence,
    ResidueEvidenceReport,
)

MAX_ASA = {
    "ALA": 129.0,
    "ARG": 274.0,
    "ASN": 195.0,
    "ASP": 193.0,
    "CYS": 167.0,
    "GLN": 225.0,
    "GLU": 223.0,
    "GLY": 104.0,
    "HIS": 224.0,
    "ILE": 197.0,
    "LEU": 201.0,
    "LYS": 236.0,
    "MET": 224.0,
    "PHE": 240.0,
    "PRO": 159.0,
    "SER": 155.0,
    "THR": 172.0,
    "TRP": 285.0,
    "TYR": 263.0,
    "VAL": 174.0,
}


@dataclass(frozen=True, slots=True)
class RegionParameters:
    requested_region_count: int = 3
    target_member_count: int = 12
    minimum_member_count: int = 6
    heavy_atom_neighbor_angstrom: float = 5.0
    anchor_neighbor_angstrom: float = 12.0
    compactness_radius_angstrom: float = 14.0


@dataclass(frozen=True, slots=True)
class SasaParameters:
    rsasa_threshold: float = 0.25
    relaxed_threshold: float = 0.20
    probe_radius_angstrom: float = 1.4
    sphere_points: int = 960


@dataclass(frozen=True, slots=True)
class DiversityTier:
    name: str
    centroid_distance_angstrom: float
    maximum_shell_overlap: float
    minimum_atom_distance_angstrom: float = 6.0


DIVERSITY_TIERS = (
    DiversityTier("tier0", 18.0, 0.10),
    DiversityTier("tier1", 15.0, 0.20),
    DiversityTier("tier2", 12.0, 0.30),
)
DEFAULT_REGION_PARAMETERS = RegionParameters()
DEFAULT_SASA_PARAMETERS = SasaParameters()


def _q25(values: list[float]) -> float:
    ordered = sorted(values)
    return ordered[int((len(ordered) - 1) * 0.25)]


def _edge_count(labels: tuple[int, ...], graph: dict[int, set[int]]) -> int:
    return sum(
        right in graph[left]
        for index, left in enumerate(labels)
        for right in labels[index + 1 :]
    )


def _grow_nearest_patch(
    *,
    seed: int,
    size: int,
    graph: dict[int, set[int]],
    context: StructureContext,
) -> tuple[int, ...] | None:
    distances = {seed: 0.0}
    queue: list[tuple[float, int]] = [(0.0, seed)]
    while queue:
        current_distance, current = heapq.heappop(queue)
        if current_distance != distances[current]:
            continue
        for neighbor in sorted(graph[current]):
            edge = math.dist(
                context.residues[current].center,
                context.residues[neighbor].center,
            )
            candidate = current_distance + edge
            if candidate < distances.get(neighbor, math.inf):
                distances[neighbor] = candidate
                heapq.heappush(queue, (candidate, neighbor))
    if len(distances) < size:
        return None
    return tuple(sorted(sorted(distances, key=lambda x: (distances[x], x))[:size]))


def _grow_probability_patch(
    *,
    seed: int,
    size: int,
    graph: dict[int, set[int]],
    probabilities: dict[int, float],
) -> tuple[int, ...] | None:
    selected = {seed}
    while len(selected) < size:
        frontier = {
            neighbor
            for label in selected
            for neighbor in graph[label]
            if neighbor not in selected
        }
        if not frontier:
            return None
        chosen = min(frontier, key=lambda label: (-probabilities[label], label))
        selected.add(chosen)
    return tuple(sorted(selected))


def _region(
    *,
    region_id: str,
    method: RegionMethod,
    seed: int,
    labels: tuple[int, ...],
    score: float,
    metrics: RegionMetrics,
    context: StructureContext,
) -> CandidateSurfaceRegion:
    return CandidateSurfaceRegion(
        region_id=region_id,
        method=method,
        seed_label_seq_id=seed,
        members=tuple(context.residues[label].identity for label in labels),
        centroid_angstrom=region_centroid(context, labels),
        ranking_score=score,
        metrics=metrics,
    )


def _labels(region: CandidateSurfaceRegion) -> tuple[int, ...]:
    return tuple(member.label_seq_id for member in region.members)


def _candidate_pair_compatible(
    context: StructureContext,
    left: CandidateSurfaceRegion,
    right: CandidateSurfaceRegion,
    tier: DiversityTier,
) -> bool:
    left_labels = _labels(left)
    right_labels = _labels(right)
    if set(left_labels) & set(right_labels):
        return False
    return (
        center_distance(context, left_labels, right_labels)
        >= tier.centroid_distance_angstrom
        and shell_overlap(
            context,
            left_labels,
            right_labels,
            shell_radius=8.0,
        )
        <= tier.maximum_shell_overlap
        and minimum_region_atom_distance(context, left_labels, right_labels)
        >= tier.minimum_atom_distance_angstrom
    )


def _select_diverse(
    *,
    context: StructureContext,
    candidates: tuple[CandidateSurfaceRegion, ...],
    count: int,
    tier: DiversityTier,
) -> tuple[CandidateSurfaceRegion, ...]:
    compatible: dict[tuple[int, int], bool] = {}
    for left in range(len(candidates)):
        for right in range(left + 1, len(candidates)):
            compatible[(left, right)] = _candidate_pair_compatible(
                context,
                candidates[left],
                candidates[right],
                tier,
            )
    best: tuple[int, ...] | None = None
    best_score = -math.inf
    for indices in itertools.combinations(range(len(candidates)), count):
        if not all(
            compatible[(left, right)]
            for left, right in itertools.combinations(indices, 2)
        ):
            continue
        score = sum(candidates[index].ranking_score for index in indices)
        canonical = tuple(_labels(candidates[index]) for index in indices)
        if (
            best is None
            or score > best_score + 1e-12
            or (
                abs(score - best_score) <= 1e-12
                and canonical < tuple(_labels(candidates[index]) for index in best)
            )
        ):
            best = indices
            best_score = score
    if best is None:
        return ()
    selected = [candidates[index] for index in best]
    selected.sort(key=lambda item: (-item.ranking_score, item.region_id))
    return tuple(selected)


def _partial_diverse(
    *,
    context: StructureContext,
    candidates: tuple[CandidateSurfaceRegion, ...],
    count: int,
) -> tuple[CandidateSurfaceRegion, ...]:
    for requested in range(count - 1, 0, -1):
        selected = _select_diverse(
            context=context,
            candidates=candidates,
            count=requested,
            tier=DIVERSITY_TIERS[-1],
        )
        if selected:
            return selected
    return ()


def _separations(
    context: StructureContext,
    regions: tuple[CandidateSurfaceRegion, ...],
) -> tuple[PairwiseSeparation, ...]:
    result = []
    for left, right in itertools.combinations(regions, 2):
        left_labels = _labels(left)
        right_labels = _labels(right)
        result.append(
            PairwiseSeparation(
                left_region_id=left.region_id,
                right_region_id=right.region_id,
                centroid_distance_angstrom=center_distance(
                    context, left_labels, right_labels
                ),
                minimum_heavy_atom_distance_angstrom=minimum_region_atom_distance(
                    context, left_labels, right_labels
                ),
            )
        )
    return tuple(result)


def run_sasa_surface_diversity(
    *,
    context: StructureContext,
    region_parameters: RegionParameters = DEFAULT_REGION_PARAMETERS,
    sasa_parameters: SasaParameters = DEFAULT_SASA_PARAMETERS,
    avoid_label_seq_ids: frozenset[int] = frozenset(),
) -> tuple[ResidueEvidenceReport, CandidateRegionPool, RecommendedRegionSet]:
    """仅使用 SASA/几何生成候选区域。"""

    if not (
        0 < sasa_parameters.relaxed_threshold
        <= sasa_parameters.rsasa_threshold
        <= 1
    ):
        raise ValueError("SASA 阈值必须满足 0 < relaxed <= default <= 1")
    unknown_avoid = avoid_label_seq_ids - set(context.residues)
    if unknown_avoid:
        raise ValueError(f"avoid label_seq_id 不在 target 中: {sorted(unknown_avoid)}")
    ShrakeRupley(
        probe_radius=sasa_parameters.probe_radius_angstrom,
        n_points=sasa_parameters.sphere_points,
    ).compute(context.bio_structure[0], level="R")
    raw_sasa: dict[int, float] = {
        int(residue.id[1]): float(getattr(residue, "sasa", 0.0))
        for residue in context.bio_structure[0]["A"].get_residues()
    }
    rsasa = {
        label: raw_sasa[label] / MAX_ASA[geometry.residue_name]
        for label, geometry in context.residues.items()
    }
    evidence = ResidueEvidenceReport(
        method=RegionMethod.SASA_SURFACE_DIVERSITY,
        method_version=f"biopython-{Bio.__version__}",
        target_structure_sha256=context.target_structure_sha256,
        annotation_status=AnnotationStatus.NOT_IMPLEMENTED,
        residues=tuple(
            ResidueEvidence(
                method=RegionMethod.SASA_SURFACE_DIVERSITY,
                residue=context.residues[label].identity,
                raw_sasa=raw_sasa[label],
                rsasa=rsasa[label],
                eligible=(
                    rsasa[label] >= sasa_parameters.relaxed_threshold
                    and label not in avoid_label_seq_ids
                ),
                excluded_reasons=(
                    ("explicit-user-avoid",)
                    if label in avoid_label_seq_ids
                    else (
                        ("below-relaxed-rsasa-threshold",)
                        if rsasa[label] < sasa_parameters.relaxed_threshold
                        else ()
                    )
                ),
            )
            for label in sorted(context.residues)
        ),
    )

    final_candidates: tuple[CandidateSurfaceRegion, ...] = ()
    final_selected: tuple[CandidateSurfaceRegion, ...] = ()
    final_tier: DiversityTier | None = None
    final_size: int | None = None
    threshold_tiers = (
        ("strict-surface", sasa_parameters.rsasa_threshold, DIVERSITY_TIERS[:2]),
        ("relaxed-surface", sasa_parameters.relaxed_threshold, DIVERSITY_TIERS[2:]),
    )
    for threshold_name, threshold, diversity_tiers in threshold_tiers:
        eligible = {
            label
            for label, value in rsasa.items()
            if value >= threshold and label not in avoid_label_seq_ids
        }
        graph = build_residue_graph(
            context,
            eligible,
            heavy_atom_distance=region_parameters.heavy_atom_neighbor_angstrom,
            anchor_distance=region_parameters.anchor_neighbor_angstrom,
        )
        maximum_size = min(
            region_parameters.target_member_count,
            len(eligible) // region_parameters.requested_region_count,
        )
        for size in range(maximum_size, region_parameters.minimum_member_count - 1, -1):
            unique: dict[tuple[int, ...], tuple[int, float, RegionMetrics]] = {}
            for seed in sorted(eligible):
                labels = _grow_nearest_patch(
                    seed=seed,
                    size=size,
                    graph=graph,
                    context=context,
                )
                if labels is None:
                    continue
                values = [rsasa[label] for label in labels]
                possible_edges = size * (size - 1) / 2
                density = (
                    _edge_count(labels, graph) / possible_edges
                    if possible_edges
                    else 0.0
                )
                rg = radius_gyration(context, labels)
                compactness = max(
                    0.0,
                    1.0 - rg / region_parameters.compactness_radius_angstrom,
                )
                mean = sum(values) / len(values)
                q25 = _q25(values)
                score = (
                    0.35 * min(mean, 1.0)
                    + 0.25 * min(q25, 1.0)
                    + 0.20 * density
                    + 0.20 * compactness
                )
                metrics = RegionMetrics(
                    mean_rsasa=mean,
                    q25_rsasa=q25,
                    graph_density=density,
                    compactness_score=compactness,
                    radius_gyration_angstrom=rg,
                )
                previous = unique.get(labels)
                if previous is None or (score, -seed) > (previous[1], -previous[0]):
                    unique[labels] = (seed, score, metrics)
            ranked = sorted(
                unique.items(),
                key=lambda item: (-item[1][1], item[0], item[1][0]),
            )
            candidates = tuple(
                _region(
                    region_id=f"sasa-candidate-{index:04d}",
                    method=RegionMethod.SASA_SURFACE_DIVERSITY,
                    seed=seed,
                    labels=labels,
                    score=score,
                    metrics=metrics,
                    context=context,
                )
                for index, (labels, (seed, score, metrics)) in enumerate(
                    ranked, start=1
                )
            )
            final_candidates = candidates
            final_size = size
            for diversity_tier in diversity_tiers:
                selected = _select_diverse(
                    context=context,
                    candidates=candidates,
                    count=region_parameters.requested_region_count,
                    tier=diversity_tier,
                )
                if selected:
                    final_selected = selected
                    final_tier = DiversityTier(
                        name=f"{threshold_name}-{diversity_tier.name}",
                        centroid_distance_angstrom=diversity_tier.centroid_distance_angstrom,
                        maximum_shell_overlap=diversity_tier.maximum_shell_overlap,
                    )
                    break
            if final_selected:
                break
        if final_selected:
            break

    if not final_selected:
        final_selected = _partial_diverse(
            context=context,
            candidates=final_candidates,
            count=region_parameters.requested_region_count,
        )
    status = (
        RegionReviewStatus.NEEDS_HUMAN_VISUAL_CONFIRMATION
        if len(final_selected) == region_parameters.requested_region_count
        else RegionReviewStatus.INSUFFICIENT_SURFACE
    )
    pool = CandidateRegionPool(
        method=RegionMethod.SASA_SURFACE_DIVERSITY,
        method_version=f"biopython-{Bio.__version__}",
        requested_region_count=region_parameters.requested_region_count,
        requested_member_count=region_parameters.target_member_count,
        selected_member_count=final_size,
        relaxation_tier=None if final_tier is None else final_tier.name,
        candidates=final_candidates,
    )
    recommended = RecommendedRegionSet(
        method=RegionMethod.SASA_SURFACE_DIVERSITY,
        status=status,
        requested_region_count=region_parameters.requested_region_count,
        relaxation_tier=None if final_tier is None else final_tier.name,
        regions=final_selected,
        pairwise_separation=_separations(context, final_selected),
    )
    return evidence, pool, recommended


def run_scannet_region_proposals(
    *,
    context: StructureContext,
    probabilities: dict[int, float],
    method_version: str,
    region_parameters: RegionParameters = DEFAULT_REGION_PARAMETERS,
) -> tuple[ResidueEvidenceReport, CandidateRegionPool, RecommendedRegionSet]:
    """只使用 ScanNet probability 排名；不读取或计算 SASA。"""

    if set(probabilities) != set(context.residues):
        missing = sorted(set(context.residues) - set(probabilities))
        extra = sorted(set(probabilities) - set(context.residues))
        raise ValueError(f"ScanNet residue 集合不完整: missing={missing}, extra={extra}")
    if any(not 0 <= value <= 1 for value in probabilities.values()):
        raise ValueError("ScanNet probability 必须位于 [0, 1]")
    graph = build_residue_graph(
        context,
        set(context.residues),
        heavy_atom_distance=region_parameters.heavy_atom_neighbor_angstrom,
        anchor_distance=region_parameters.anchor_neighbor_angstrom,
    )
    evidence = ResidueEvidenceReport(
        method=RegionMethod.SCANNET_EPITOPE_NO_MSA,
        method_version=method_version,
        target_structure_sha256=context.target_structure_sha256,
        annotation_status=AnnotationStatus.NOT_IMPLEMENTED,
        residues=tuple(
            ResidueEvidence(
                method=RegionMethod.SCANNET_EPITOPE_NO_MSA,
                residue=context.residues[label].identity,
                scannet_probability=probabilities[label],
                eligible=True,
            )
            for label in sorted(context.residues)
        ),
    )

    final_candidates: tuple[CandidateSurfaceRegion, ...] = ()
    final_selected: tuple[CandidateSurfaceRegion, ...] = ()
    final_tier: DiversityTier | None = None
    final_size: int | None = None
    maximum_size = min(
        region_parameters.target_member_count,
        len(context.residues) // region_parameters.requested_region_count,
    )
    for size in range(maximum_size, region_parameters.minimum_member_count - 1, -1):
        unique: dict[tuple[int, ...], tuple[int, float, RegionMetrics]] = {}
        for seed in sorted(context.residues, key=lambda label: (-probabilities[label], label)):
            labels = _grow_probability_patch(
                seed=seed,
                size=size,
                graph=graph,
                probabilities=probabilities,
            )
            if labels is None:
                continue
            values = [probabilities[label] for label in labels]
            mean = sum(values) / len(values)
            metrics = RegionMetrics(
                radius_gyration_angstrom=radius_gyration(context, labels),
                mean_scannet_probability=mean,
                q25_scannet_probability=_q25(values),
            )
            previous = unique.get(labels)
            if previous is None or (mean, -seed) > (previous[1], -previous[0]):
                unique[labels] = (seed, mean, metrics)
        ranked = sorted(
            unique.items(),
            key=lambda item: (-item[1][1], item[0], item[1][0]),
        )
        candidates = tuple(
            _region(
                region_id=f"scannet-candidate-{index:04d}",
                method=RegionMethod.SCANNET_EPITOPE_NO_MSA,
                seed=seed,
                labels=labels,
                score=score,
                metrics=metrics,
                context=context,
            )
            for index, (labels, (seed, score, metrics)) in enumerate(
                ranked, start=1
            )
        )
        final_candidates = candidates
        final_size = size
        for tier in DIVERSITY_TIERS:
            selected = _select_diverse(
                context=context,
                candidates=candidates,
                count=region_parameters.requested_region_count,
                tier=tier,
            )
            if selected:
                final_selected = selected
                final_tier = tier
                break
        if final_selected:
            break
    if not final_selected:
        final_selected = _partial_diverse(
            context=context,
            candidates=final_candidates,
            count=region_parameters.requested_region_count,
        )
    status = (
        RegionReviewStatus.NEEDS_HUMAN_VISUAL_CONFIRMATION
        if len(final_selected) == region_parameters.requested_region_count
        else RegionReviewStatus.INSUFFICIENT_SURFACE
    )
    pool = CandidateRegionPool(
        method=RegionMethod.SCANNET_EPITOPE_NO_MSA,
        method_version=method_version,
        requested_region_count=region_parameters.requested_region_count,
        requested_member_count=region_parameters.target_member_count,
        selected_member_count=final_size,
        relaxation_tier=None if final_tier is None else final_tier.name,
        candidates=final_candidates,
    )
    recommended = RecommendedRegionSet(
        method=RegionMethod.SCANNET_EPITOPE_NO_MSA,
        status=status,
        requested_region_count=region_parameters.requested_region_count,
        relaxation_tier=None if final_tier is None else final_tier.name,
        regions=final_selected,
        pairwise_separation=_separations(context, final_selected),
    )
    return evidence, pool, recommended


def compare_independent_methods(
    *,
    context: StructureContext,
    sasa: RecommendedRegionSet,
    scannet: RecommendedRegionSet,
) -> MethodComparison:
    """只计算重合关系；不产生融合分数、赢家或默认方法。"""

    overlaps: list[RegionOverlap] = []
    for sasa_region in sasa.regions:
        sasa_labels = set(_labels(sasa_region))
        for scannet_region in scannet.regions:
            scannet_labels = set(_labels(scannet_region))
            shared = sasa_labels & scannet_labels
            union = sasa_labels | scannet_labels
            overlaps.append(
                RegionOverlap(
                    sasa_region_id=sasa_region.region_id,
                    scannet_region_id=scannet_region.region_id,
                    shared_members=tuple(
                        context.residues[label].identity for label in sorted(shared)
                    ),
                    shared_member_count=len(shared),
                    jaccard_overlap=len(shared) / max(1, len(union)),
                    sasa_coverage=len(shared) / len(sasa_labels),
                    scannet_coverage=len(shared) / len(scannet_labels),
                    centroid_distance_angstrom=center_distance(
                        context,
                        tuple(sorted(sasa_labels)),
                        tuple(sorted(scannet_labels)),
                    ),
                    minimum_heavy_atom_distance_angstrom=minimum_region_atom_distance(
                        context,
                        tuple(sorted(sasa_labels)),
                        tuple(sorted(scannet_labels)),
                    ),
                )
            )
    best: tuple[RegionOverlap, ...] = ()
    if sasa.regions and scannet.regions:
        count = min(len(sasa.regions), len(scannet.regions))
        best_key: tuple[float, float] | None = None
        for selection in itertools.permutations(range(len(scannet.regions)), count):
            pairs = []
            for sasa_index, scannet_index in enumerate(selection):
                sasa_id = sasa.regions[sasa_index].region_id
                scannet_id = scannet.regions[scannet_index].region_id
                pairs.append(
                    next(
                        overlap
                        for overlap in overlaps
                        if overlap.sasa_region_id == sasa_id
                        and overlap.scannet_region_id == scannet_id
                    )
                )
            key = (
                sum(item.jaccard_overlap for item in pairs),
                -sum(item.centroid_distance_angstrom for item in pairs),
            )
            if best_key is None or key > best_key:
                best_key = key
                best = tuple(pairs)
    return MethodComparison(overlaps=tuple(overlaps), best_matches=best)
