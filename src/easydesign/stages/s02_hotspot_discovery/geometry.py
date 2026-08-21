"""Stage 02 共用的结构读取、编号校验和纯几何基础设施。"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
from Bio.PDB.Atom import Atom
from Bio.PDB.Chain import Chain
from Bio.PDB.MMCIF2Dict import MMCIF2Dict
from Bio.PDB.Model import Model
from Bio.PDB.Residue import Residue
from Bio.PDB.Structure import Structure

from easydesign.core import ManifestStateError, load_model
from easydesign.stages.s01_target_preparation import ResidueMapping, TargetBundle

from .models import ResidueIdentity

ONE_TO_THREE = {
    "A": "ALA",
    "C": "CYS",
    "D": "ASP",
    "E": "GLU",
    "F": "PHE",
    "G": "GLY",
    "H": "HIS",
    "I": "ILE",
    "K": "LYS",
    "L": "LEU",
    "M": "MET",
    "N": "ASN",
    "P": "PRO",
    "Q": "GLN",
    "R": "ARG",
    "S": "SER",
    "T": "THR",
    "V": "VAL",
    "W": "TRP",
    "Y": "TYR",
}


@dataclass(frozen=True, slots=True)
class AtomCoordinate:
    name: str
    element: str
    xyz: tuple[float, float, float]
    occupancy: float


@dataclass(frozen=True, slots=True)
class ResidueGeometry:
    identity: ResidueIdentity
    residue_name: str
    atoms: tuple[AtomCoordinate, ...]
    center: tuple[float, float, float]


@dataclass(frozen=True, slots=True)
class CoordinateModelGeometry:
    model_id: str
    residues: dict[int, ResidueGeometry]
    bio_model: Model


@dataclass(frozen=True, slots=True)
class StructureContext:
    target_id: str
    target_structure: Path
    target_structure_sha256: str
    mapping_path: Path
    label_asym_id: str
    model_ids: tuple[str, ...]
    representative_model_id: str
    models: dict[str, CoordinateModelGeometry]
    residues: dict[int, ResidueGeometry]
    bio_structure: Structure
    minimum_atom_distance_cache: dict[tuple[str, int, int], float] = field(
        default_factory=dict,
        repr=False,
        compare=False,
    )


def _column(raw: dict[str, Any], key: str, row_count: int, default: str) -> list[str]:
    value = raw.get(key)
    if value is None:
        return [default] * row_count
    values = value if isinstance(value, list) else [value]
    if len(values) != row_count:
        raise ManifestStateError(f"mmCIF atom_site 列长度不一致: {key}")
    return [str(item) for item in values]


def _distance(left: tuple[float, float, float], right: tuple[float, float, float]) -> float:
    return math.sqrt(sum((a - b) ** 2 for a, b in zip(left, right, strict=True)))


def _minimum_atom_distance(left: ResidueGeometry, right: ResidueGeometry) -> float:
    return min(_distance(a.xyz, b.xyz) for a in left.atoms for b in right.atoms)


def _cached_minimum_atom_distance(
    context: StructureContext,
    model_id: str,
    left_label: int,
    right_label: int,
) -> float:
    key = (
        (model_id, left_label, right_label)
        if left_label <= right_label
        else (model_id, right_label, left_label)
    )
    cached = context.minimum_atom_distance_cache.get(key)
    if cached is None:
        model = context.models[model_id]
        cached = _minimum_atom_distance(
            model.residues[left_label],
            model.residues[right_label],
        )
        context.minimum_atom_distance_cache[key] = cached
    return cached


def _model_sort_key(model_id: str) -> tuple[int, int | str]:
    try:
        return (0, int(model_id))
    except ValueError:
        return (1, model_id)


def _choose_atoms(rows: list[AtomCoordinate]) -> tuple[AtomCoordinate, ...]:
    """同名 atom 保留最高 occupancy；同分时优先坐标字典序，确保确定性。"""

    chosen: dict[str, AtomCoordinate] = {}
    for atom in rows:
        previous = chosen.get(atom.name)
        if previous is None or (atom.occupancy, tuple(-x for x in atom.xyz)) > (
            previous.occupancy,
            tuple(-x for x in previous.xyz),
        ):
            chosen[atom.name] = atom
    return tuple(chosen[name] for name in sorted(chosen))


def _center(atoms: tuple[AtomCoordinate, ...], residue_name: str) -> tuple[float, float, float]:
    by_name = {atom.name: atom for atom in atoms}
    preferred = "CA" if residue_name == "GLY" else "CB"
    atom = by_name.get(preferred) or by_name.get("CA")
    if atom is None:
        raise ManifestStateError(f"Stage 02 结构残基缺少 CA/CB anchor: {residue_name}")
    return atom.xyz


def load_structure_context(
    *,
    run_root: Path,
    target_bundle_path: Path,
) -> tuple[TargetBundle, StructureContext]:
    """只从 Target Bundle 声明的 artifact 加载结构和编号映射。"""

    bundle = load_model(target_bundle_path, TargetBundle)
    structure_path = bundle.target_structure.verify(run_root)
    mapping_path = bundle.residue_mapping.verify(run_root)
    mapping = load_model(mapping_path, ResidueMapping)
    if mapping.target_id != bundle.target_id:
        raise ManifestStateError("Target Bundle 与 residue mapping 的 target_id 不一致")
    if mapping.sequence_sha256 != bundle.sequence_sha256:
        raise ManifestStateError("Target Bundle 与 residue mapping 的 sequence SHA-256 不一致")
    if len(mapping.entries) != bundle.sequence_length:
        raise ManifestStateError("Target Bundle sequence_length 与 residue mapping 数量不一致")

    label_chains = {entry.label_chain_id for entry in mapping.entries}
    if len(label_chains) != 1:
        raise ManifestStateError("Stage 02 v0.1 只接受单条 label chain")
    label_chain = next(iter(label_chains))

    try:
        raw: dict[str, Any] = MMCIF2Dict(str(structure_path))  # type: ignore[no-untyped-call]
    except Exception as error:
        raise ManifestStateError(f"Stage 02 无法解析 target.cif: {structure_path}") from error
    atom_names_value = raw.get("_atom_site.label_atom_id")
    if atom_names_value is None:
        raise ManifestStateError("target.cif 缺少 _atom_site.label_atom_id")
    atom_names = atom_names_value if isinstance(atom_names_value, list) else [atom_names_value]
    row_count = len(atom_names)
    columns = {
        "group": _column(raw, "_atom_site.group_PDB", row_count, "ATOM"),
        "atom": [str(value).strip() for value in atom_names],
        "element": _column(raw, "_atom_site.type_symbol", row_count, ""),
        "residue": _column(raw, "_atom_site.label_comp_id", row_count, "UNK"),
        "label_chain": _column(raw, "_atom_site.label_asym_id", row_count, ""),
        "label_seq": _column(raw, "_atom_site.label_seq_id", row_count, "."),
        "x": _column(raw, "_atom_site.Cartn_x", row_count, "0"),
        "y": _column(raw, "_atom_site.Cartn_y", row_count, "0"),
        "z": _column(raw, "_atom_site.Cartn_z", row_count, "0"),
        "occupancy": _column(raw, "_atom_site.occupancy", row_count, "1"),
        "model": _column(raw, "_atom_site.pdbx_PDB_model_num", row_count, "1"),
    }
    actual_model_ids = {
        columns["model"][index]
        for index in range(row_count)
        if columns["group"][index] == "ATOM"
        and columns["label_chain"][index] == label_chain
    }
    if not actual_model_ids:
        raise ManifestStateError("target.cif 没有可用 coordinate model")
    model_ids: tuple[str, ...]
    representative_model_id: str
    if bundle.coordinate_ensemble is None:
        if actual_model_ids != {"1"}:
            raise ManifestStateError(
                "旧版 Target Bundle 只能表示单模型 target.cif；"
                f"实际模型为 {sorted(actual_model_ids, key=_model_sort_key)}"
            )
        model_ids = ("1",)
        representative_model_id = "1"
    else:
        model_ids = bundle.coordinate_ensemble.model_ids
        representative_model_id = bundle.coordinate_ensemble.representative_model_id
        if set(model_ids) != actual_model_ids:
            raise ManifestStateError(
                "Target Bundle coordinate_ensemble 与 target.cif 模型不一致: "
                f"declared={list(model_ids)}, "
                f"actual={sorted(actual_model_ids, key=_model_sort_key)}"
            )

    rows_by_model: dict[str, dict[int, list[AtomCoordinate]]] = {
        model_id: {} for model_id in model_ids
    }
    residue_names: dict[int, str] = {}
    for index in range(row_count):
        if (
            columns["group"][index] != "ATOM"
            or columns["label_chain"][index] != label_chain
            or columns["label_seq"][index] in {".", "?"}
        ):
            continue
        model_id = columns["model"][index]
        if model_id not in rows_by_model:
            continue
        label = int(columns["label_seq"][index])
        element = columns["element"][index].strip().upper()
        if not element:
            element = columns["atom"][index][0].upper()
        if element in {"H", "D"}:
            continue
        residue_name = columns["residue"][index].upper()
        previous_name = residue_names.setdefault(label, residue_name)
        if previous_name != residue_name:
            raise ManifestStateError(f"label_seq_id={label} 对应多个 residue name")
        occupancy_text = columns["occupancy"][index]
        occupancy = 1.0 if occupancy_text in {".", "?"} else float(occupancy_text)
        rows_by_model[model_id].setdefault(label, []).append(
            AtomCoordinate(
                name=columns["atom"][index],
                element=element,
                xyz=(
                    float(columns["x"][index]),
                    float(columns["y"][index]),
                    float(columns["z"][index]),
                ),
                occupancy=occupancy,
            )
        )

    structure = Structure("stage02-target")  # type: ignore[no-untyped-call]
    identities = {
        entry.label_seq_id: ResidueIdentity(
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
        for entry in mapping.entries
    }
    models: dict[str, CoordinateModelGeometry] = {}
    for model_index, model_id in enumerate(model_ids):
        model = Model(model_index)  # type: ignore[no-untyped-call]
        chain = Chain("A")  # type: ignore[no-untyped-call]
        model.add(chain)
        structure.add(model)
        residues: dict[int, ResidueGeometry] = {}
        for entry in mapping.entries:
            label = entry.label_seq_id
            rows = rows_by_model[model_id].get(label)
            if not rows:
                continue
            residue_name = residue_names[label]
            expected_name = ONE_TO_THREE[entry.amino_acid]
            if residue_name != expected_name:
                raise ManifestStateError(
                    f"结构/映射氨基酸不一致: model={model_id}, "
                    f"label_seq_id={label}, structure={residue_name}, "
                    f"mapping={expected_name}"
                )
            atoms = _choose_atoms(rows)
            geometry = ResidueGeometry(
                identity=identities[label],
                residue_name=residue_name,
                atoms=atoms,
                center=_center(atoms, residue_name),
            )
            residues[label] = geometry
            bio_residue = Residue(  # type: ignore[no-untyped-call]
                (" ", label, " "), residue_name, ""
            )
            for serial, atom in enumerate(atoms, start=1):
                bio_residue.add(  # type: ignore[no-untyped-call]
                    Atom(
                        atom.name,
                        np.asarray(atom.xyz, dtype=float),
                        0.0,
                        atom.occupancy,
                        " ",
                        f"{atom.name:>4}"[-4:],
                        serial,
                        element=atom.element,
                    )
                )
            chain.add(bio_residue)
        models[model_id] = CoordinateModelGeometry(
            model_id=model_id,
            residues=residues,
            bio_model=model,
        )

    expected_labels = [
        entry.label_seq_id for entry in mapping.entries if entry.coordinate_present
    ]
    observed_labels = {
        label for model in models.values() for label in model.residues
    }
    if observed_labels != set(expected_labels):
        missing = sorted(set(expected_labels) - observed_labels)
        unexpected = sorted(observed_labels - set(expected_labels))
        raise ManifestStateError(
            "Stage 02 coordinate-present 残基与 Stage 01 mapping 不一致: "
            f"missing={missing}, unexpected={unexpected}"
        )
    if mapping.schema_version == "0.3":
        for entry in mapping.entries:
            actual_presence = tuple(
                model_id
                for model_id in model_ids
                if entry.label_seq_id in models[model_id].residues
            )
            if actual_presence != entry.model_presence:
                raise ManifestStateError(
                    "Stage 02 coordinate model presence 与 Stage 01 mapping 不一致: "
                    f"label_seq_id={entry.label_seq_id}, "
                    f"declared={list(entry.model_presence)}, "
                    f"actual={list(actual_presence)}"
                )
    representative = models[representative_model_id]
    reference_residues = {
        label: (
            representative.residues[label]
            if label in representative.residues
            else next(
                model.residues[label]
                for model in models.values()
                if label in model.residues
            )
        )
        for label in sorted(expected_labels)
    }
    return bundle, StructureContext(
        target_id=bundle.target_id,
        target_structure=structure_path,
        target_structure_sha256=bundle.target_structure.sha256,
        mapping_path=mapping_path,
        label_asym_id=label_chain,
        model_ids=model_ids,
        representative_model_id=representative_model_id,
        models=models,
        residues=reference_residues,
        bio_structure=structure,
    )


def build_residue_graph(
    context: StructureContext,
    labels: set[int],
    *,
    heavy_atom_distance: float,
    anchor_distance: float,
    consensus_fraction: float = 1.0,
) -> dict[int, set[int]]:
    if not 0 < consensus_fraction <= 1:
        raise ValueError("consensus_fraction 必须位于 (0, 1]")
    graph: dict[int, set[int]] = {label: set() for label in labels}
    minimum_support = math.ceil(len(context.model_ids) * consensus_fraction)
    ordered = sorted(labels)
    for index, left_label in enumerate(ordered):
        for right_label in ordered[index + 1 :]:
            support = 0
            for model_id in context.model_ids:
                model = context.models[model_id]
                if (
                    left_label not in model.residues
                    or right_label not in model.residues
                ):
                    continue
                left = model.residues[left_label]
                right = model.residues[right_label]
                if _distance(left.center, right.center) > anchor_distance:
                    continue
                if (
                    _cached_minimum_atom_distance(
                        context,
                        model_id,
                        left_label,
                        right_label,
                    )
                    > heavy_atom_distance
                ):
                    continue
                support += 1
            if support >= minimum_support:
                graph[left_label].add(right_label)
                graph[right_label].add(left_label)
    return graph


def consensus_edge_length(
    context: StructureContext,
    left_label: int,
    right_label: int,
) -> float:
    values = [
        _distance(
            context.models[model_id].residues[left_label].center,
            context.models[model_id].residues[right_label].center,
        )
        for model_id in context.model_ids
        if left_label in context.models[model_id].residues
        and right_label in context.models[model_id].residues
    ]
    if not values:
        return math.inf
    return float(statistics.median(values))


def model_completeness_fraction(
    context: StructureContext,
    labels: tuple[int, ...],
) -> float:
    return sum(
        all(label in context.models[model_id].residues for label in labels)
        for model_id in context.model_ids
    ) / len(context.model_ids)


def _residue_centroid(
    residues: dict[int, ResidueGeometry],
    labels: tuple[int, ...],
) -> tuple[float, float, float]:
    values = tuple(
        sum((residues[label].center[axis] for label in labels), 0.0)
        / len(labels)
        for axis in range(3)
    )
    return values[0], values[1], values[2]


def region_centroid(
    context: StructureContext,
    labels: tuple[int, ...],
) -> tuple[float, float, float]:
    representative = context.models[context.representative_model_id]
    if all(label in representative.residues for label in labels):
        return _residue_centroid(representative.residues, labels)
    model_centroids = [
        _residue_centroid(model.residues, labels)
        for model in context.models.values()
        if all(label in model.residues for label in labels)
    ]
    if not model_centroids:
        raise ManifestStateError("没有模型包含区域完整坐标，无法输出 centroid")
    values = tuple(
        float(statistics.median(value[axis] for value in model_centroids))
        for axis in range(3)
    )
    return values[0], values[1], values[2]


def radius_gyration(context: StructureContext, labels: tuple[int, ...]) -> float:
    values = []
    for model_id in context.model_ids:
        model = context.models[model_id]
        if not all(label in model.residues for label in labels):
            continue
        centroid = _residue_centroid(model.residues, labels)
        values.append(
            math.sqrt(
                sum(
                    (
                        _distance(model.residues[label].center, centroid) ** 2
                        for label in labels
                    ),
                    0.0,
                )
                / len(labels)
            )
        )
    if not values:
        raise ManifestStateError("没有模型包含区域的完整几何")
    return float(statistics.median(values))


def minimum_region_atom_distance(
    context: StructureContext,
    left: tuple[int, ...],
    right: tuple[int, ...],
) -> float:
    values = [
        min(
            _cached_minimum_atom_distance(context, model_id, a, b)
            for a in left
            for b in right
        )
        for model_id in context.model_ids
        if all(
            label in context.models[model_id].residues
            for label in left + right
        )
    ]
    if not values:
        raise ManifestStateError("没有模型同时包含两个区域的完整几何")
    return min(values)


def region_shell(
    context: StructureContext,
    region: tuple[int, ...],
    *,
    shell_radius: float,
    model_id: str | None = None,
) -> frozenset[int]:
    selected_model_id = (
        context.representative_model_id if model_id is None else model_id
    )
    model = context.models[selected_model_id]
    if not all(label in model.residues for label in region):
        raise ManifestStateError(
            f"model={selected_model_id} 不包含完整区域，无法计算 shell"
        )
    return frozenset(
        label
        for label in model.residues
        if any(
            _cached_minimum_atom_distance(
                context,
                selected_model_id,
                label,
                member,
            )
            <= shell_radius
            for member in region
        )
    )


def shell_overlap(
    context: StructureContext,
    left: tuple[int, ...],
    right: tuple[int, ...],
    *,
    shell_radius: float,
) -> float:
    values = []
    for model_id in context.model_ids:
        model = context.models[model_id]
        if not all(label in model.residues for label in left + right):
            continue
        left_shell = region_shell(
            context,
            left,
            shell_radius=shell_radius,
            model_id=model_id,
        )
        right_shell = region_shell(
            context,
            right,
            shell_radius=shell_radius,
            model_id=model_id,
        )
        values.append(
            len(left_shell & right_shell)
            / max(1, min(len(left_shell), len(right_shell)))
        )
    if not values:
        raise ManifestStateError("没有模型同时包含两个区域，无法计算 shell overlap")
    return max(values)


def center_distance(
    context: StructureContext,
    left: tuple[int, ...],
    right: tuple[int, ...],
) -> float:
    values = []
    for model_id in context.model_ids:
        model = context.models[model_id]
        if not all(label in model.residues for label in left + right):
            continue
        left_centroid = _residue_centroid(model.residues, left)
        right_centroid = _residue_centroid(model.residues, right)
        values.append(_distance(left_centroid, right_centroid))
    if not values:
        raise ManifestStateError("没有模型同时包含两个区域，无法计算中心距离")
    return min(values)
