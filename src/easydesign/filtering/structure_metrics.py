"""可复用的跨链结构指标；定义版本 ``interface-geometry-v1``。"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from pathlib import Path

import gemmi
import numpy as np
from Bio.PDB.MMCIFParser import MMCIFParser
from Bio.PDB.SASA import ShrakeRupley
from pydantic import BaseModel, ConfigDict, Field

from easydesign.core import ManifestStateError

CONTACT_ANGSTROM = 5.0
SEVERE_CLASH_ANGSTROM = 1.5
MODERATE_CLASH_ANGSTROM = 1.8
HYDROGEN_BOND_ANGSTROM = 3.5
SALT_BRIDGE_ANGSTROM = 4.0
SASA_PROBE_RADIUS_ANGSTROM = 1.4
SASA_SPHERE_POINTS = 960
METRIC_DEFINITION_VERSION = "interface-geometry-v1"

_AMINO_ACID_3_TO_1 = {
    "ALA": "A",
    "ARG": "R",
    "ASN": "N",
    "ASP": "D",
    "CYS": "C",
    "GLN": "Q",
    "GLU": "E",
    "GLY": "G",
    "HIS": "H",
    "ILE": "I",
    "LEU": "L",
    "LYS": "K",
    "MET": "M",
    "PHE": "F",
    "PRO": "P",
    "SER": "S",
    "THR": "T",
    "TRP": "W",
    "TYR": "Y",
    "VAL": "V",
}
_POLAR_ELEMENTS = {"N", "O", "S"}
_ACIDIC_ATOMS = {
    ("ASP", "OD1"),
    ("ASP", "OD2"),
    ("GLU", "OE1"),
    ("GLU", "OE2"),
}
_BASIC_ATOMS = {
    ("ARG", "NE"),
    ("ARG", "NH1"),
    ("ARG", "NH2"),
    ("HIS", "ND1"),
    ("HIS", "NE2"),
    ("LYS", "NZ"),
}


@dataclass(frozen=True, slots=True)
class AtomPoint:
    residue_id: int
    residue_name: str
    atom_name: str
    element: str
    coordinate: tuple[float, float, float]


@dataclass(frozen=True, slots=True)
class ResiduePoint:
    residue_id: int
    residue_name: str
    one_letter: str
    ca: tuple[float, float, float] | None


@dataclass(frozen=True, slots=True)
class ParsedChain:
    chain_id: str
    residues: tuple[ResiduePoint, ...]
    atoms: tuple[AtomPoint, ...]

    @property
    def sequence(self) -> str:
        return "".join(residue.one_letter for residue in self.residues)


class InterfaceMetricValues(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    target_ca_rmsd_angstrom: float = Field(ge=0)
    hotspot_coverage: float = Field(ge=0, le=1)
    contacted_hotspot_count: int = Field(ge=0)
    hotspot_count: int = Field(ge=1)
    binder_contact_coverage: float = Field(ge=0, le=1)
    cdr_dominance: float = Field(ge=0, le=1)
    cdr_utilization: float = Field(ge=0, le=1)
    residue_pair_contact_count: int = Field(ge=0)
    atom_contact_count: int = Field(ge=0)
    severe_clash_count: int = Field(ge=0)
    moderate_clash_count: int = Field(ge=0)
    hydrogen_bond_count: int = Field(ge=0)
    salt_bridge_count: int = Field(ge=0)
    polar_contact_fraction: float = Field(ge=0, le=1)
    interface_bsa_angstrom2: float | None = Field(default=None, ge=0)
    interface_bsa_missing_reason: str | None


class FullTargetStructureMetrics(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    binder_pose_rmsd_angstrom: float = Field(ge=0)
    target_ca_rmsd_angstrom: float = Field(ge=0)
    severe_clash_count: int = Field(ge=0)
    moderate_clash_count: int = Field(ge=0)


def _selected_atoms(chain: gemmi.Chain) -> tuple[AtomPoint, ...]:
    selected: dict[tuple[int, str], tuple[float, str, AtomPoint]] = {}
    observed_residue_ids: set[int] = set()
    for residue in chain:
        residue_name = residue.name.upper()
        if residue_name not in _AMINO_ACID_3_TO_1:
            continue
        if residue.label_seq is None or residue.label_seq < 1:
            raise ManifestStateError(f"candidate chain={chain.name} 缺少有效 label_seq_id")
        residue_id = int(residue.label_seq)
        if residue_id in observed_residue_ids:
            raise ManifestStateError(
                f"candidate chain={chain.name} label_seq_id 重复: {residue_id}"
            )
        observed_residue_ids.add(residue_id)
        for atom in residue:
            element = atom.element.name.upper()
            if element in {"H", "D"}:
                continue
            altloc = str(atom.altloc).strip().replace("\x00", "")
            point = AtomPoint(
                residue_id=residue_id,
                residue_name=residue_name,
                atom_name=atom.name.strip().upper(),
                element=element,
                coordinate=(atom.pos.x, atom.pos.y, atom.pos.z),
            )
            key = (residue_id, point.atom_name)
            ranking = (float(atom.occ), "" if altloc in {"", ".", "?"} else altloc)
            previous = selected.get(key)
            if (
                previous is None
                or ranking[0] > previous[0]
                or (ranking[0] == previous[0] and ranking[1] < previous[1])
            ):
                selected[key] = (ranking[0], ranking[1], point)
    return tuple(
        value[2]
        for _, value in sorted(
            selected.items(),
            key=lambda item: (item[0][0], item[0][1]),
        )
    )


def parse_protein_chain(path: Path, chain_id: str) -> ParsedChain:
    """读取首个 coordinate model 的标准蛋白重原子和 CA。"""

    try:
        structure = gemmi.read_structure(str(path))
    except (RuntimeError, ValueError) as error:
        raise ManifestStateError(f"结构无法解析: {path}") from error
    if len(structure) != 1:
        raise ManifestStateError(f"候选结构必须恰好一个 coordinate model: {path}")
    model = structure[0]
    matches = [chain for chain in model if chain.name == chain_id]
    if len(matches) != 1:
        raise ManifestStateError(f"结构 chain={chain_id} 必须唯一: {path}")
    chain = matches[0]
    atoms = _selected_atoms(chain)
    atoms_by_residue: dict[int, list[AtomPoint]] = {}
    names: dict[int, str] = {}
    for atom in atoms:
        atoms_by_residue.setdefault(atom.residue_id, []).append(atom)
        names[atom.residue_id] = atom.residue_name
    residues: list[ResiduePoint] = []
    for residue_id in sorted(atoms_by_residue):
        residue_name = names[residue_id]
        ca = next(
            (atom.coordinate for atom in atoms_by_residue[residue_id] if atom.atom_name == "CA"),
            None,
        )
        residues.append(
            ResiduePoint(
                residue_id=residue_id,
                residue_name=residue_name,
                one_letter=_AMINO_ACID_3_TO_1[residue_name],
                ca=ca,
            )
        )
    if not residues or not atoms:
        raise ManifestStateError(f"结构 chain={chain_id} 没有标准蛋白坐标: {path}")
    return ParsedChain(chain_id=chain_id, residues=tuple(residues), atoms=atoms)


def _coordinate_array(atoms: tuple[AtomPoint, ...]) -> np.ndarray:
    return np.asarray([atom.coordinate for atom in atoms], dtype=np.float64)


def _pairwise_distances(
    first: tuple[AtomPoint, ...],
    second: tuple[AtomPoint, ...],
) -> np.ndarray:
    first_coordinates = _coordinate_array(first)
    second_coordinates = _coordinate_array(second)
    delta = first_coordinates[:, None, :] - second_coordinates[None, :, :]
    return np.asarray(
        np.sqrt(np.einsum("ijk,ijk->ij", delta, delta)),
        dtype=np.float64,
    )


def _kabsch_rmsd(
    reference: np.ndarray,
    mobile: np.ndarray,
) -> float:
    if reference.shape != mobile.shape or reference.ndim != 2 or reference.shape[1] != 3:
        raise ManifestStateError("Kabsch RMSD 坐标形状不一致")
    if len(reference) < 3:
        raise ManifestStateError("target CA RMSD 至少需要三个共同残基")
    reference_centered = reference - reference.mean(axis=0)
    mobile_centered = mobile - mobile.mean(axis=0)
    covariance = mobile_centered.T @ reference_centered
    left, _, right = np.linalg.svd(covariance)
    correction = np.eye(3)
    if np.linalg.det(left @ right) < 0:
        correction[-1, -1] = -1
    rotation = left @ correction @ right
    aligned = mobile_centered @ rotation
    return float(np.sqrt(np.mean(np.sum((aligned - reference_centered) ** 2, axis=1))))


def _kabsch_transform(
    reference: np.ndarray,
    mobile: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    if reference.shape != mobile.shape or reference.ndim != 2 or reference.shape[1] != 3:
        raise ManifestStateError("Kabsch transform 坐标形状不一致")
    if len(reference) < 3:
        raise ManifestStateError("Kabsch transform 至少需要三个共同坐标")
    reference_center = reference.mean(axis=0)
    mobile_center = mobile.mean(axis=0)
    reference_centered = reference - reference_center
    mobile_centered = mobile - mobile_center
    covariance = mobile_centered.T @ reference_centered
    left, _, right = np.linalg.svd(covariance)
    correction = np.eye(3)
    if np.linalg.det(left @ right) < 0:
        correction[-1, -1] = -1
    return left @ correction @ right, mobile_center, reference_center


def _common_ca_coordinates(
    reference: ParsedChain,
    mobile: ParsedChain,
) -> tuple[np.ndarray, np.ndarray]:
    reference_ca = {
        residue.residue_id: residue.ca for residue in reference.residues if residue.ca is not None
    }
    mobile_ca = {
        residue.residue_id: residue.ca for residue in mobile.residues if residue.ca is not None
    }
    if set(reference_ca) != set(mobile_ca):
        raise ManifestStateError("target CA identity 不完整，不能建立 target-aligned frame")
    reference_names = {residue.residue_id: residue.one_letter for residue in reference.residues}
    mobile_names = {residue.residue_id: residue.one_letter for residue in mobile.residues}
    if reference_names != mobile_names:
        raise ManifestStateError("target residue identity 不一致，不能建立 target-aligned frame")
    identifiers = sorted(reference_ca)
    return (
        np.asarray([reference_ca[item] for item in identifiers], dtype=np.float64),
        np.asarray([mobile_ca[item] for item in identifiers], dtype=np.float64),
    )


def target_ca_rmsd(reference: ParsedChain, candidate: ParsedChain) -> float:
    reference_ca = {
        residue.residue_id: residue.ca for residue in reference.residues if residue.ca is not None
    }
    candidate_ca = {
        residue.residue_id: residue.ca for residue in candidate.residues if residue.ca is not None
    }
    if set(reference_ca) != set(candidate_ca):
        missing = sorted(set(reference_ca) - set(candidate_ca))
        extra = sorted(set(candidate_ca) - set(reference_ca))
        raise ManifestStateError(
            f"candidate target CA identity 不完整: missing={missing[:10]}, extra={extra[:10]}"
        )
    reference_names = {residue.residue_id: residue.one_letter for residue in reference.residues}
    candidate_names = {residue.residue_id: residue.one_letter for residue in candidate.residues}
    if reference_names != candidate_names:
        raise ManifestStateError("candidate target residue identity 与 reference 不一致")
    identifiers = sorted(reference_ca)
    reference_coordinates = np.asarray(
        [reference_ca[identifier] for identifier in identifiers],
        dtype=np.float64,
    )
    candidate_coordinates = np.asarray(
        [candidate_ca[identifier] for identifier in identifiers],
        dtype=np.float64,
    )
    return _kabsch_rmsd(reference_coordinates, candidate_coordinates)


def compute_full_target_structure_metrics(
    *,
    designed_complex: Path,
    predicted_complex: Path,
    reference_target: ParsedChain,
    target_chain_id: str = "A",
    binder_chain_id: str = "B",
) -> FullTargetStructureMetrics:
    """Align predicted target to the designed complex and compare binder backbone."""

    designed_target = parse_protein_chain(designed_complex, target_chain_id)
    designed_binder = parse_protein_chain(designed_complex, binder_chain_id)
    predicted_target = parse_protein_chain(predicted_complex, target_chain_id)
    predicted_binder = parse_protein_chain(predicted_complex, binder_chain_id)
    if {residue.residue_id: residue.one_letter for residue in designed_binder.residues} != {
        residue.residue_id: residue.one_letter for residue in predicted_binder.residues
    }:
        raise ManifestStateError("predicted binder residue identity 与 designed candidate 不一致")
    target_reference, target_mobile = _common_ca_coordinates(
        designed_target,
        predicted_target,
    )
    rotation, mobile_center, reference_center = _kabsch_transform(
        target_reference,
        target_mobile,
    )
    backbone_names = {"N", "CA", "C", "O"}
    designed_backbone = {
        (atom.residue_id, atom.atom_name): atom.coordinate
        for atom in designed_binder.atoms
        if atom.atom_name in backbone_names
    }
    predicted_backbone = {
        (atom.residue_id, atom.atom_name): atom.coordinate
        for atom in predicted_binder.atoms
        if atom.atom_name in backbone_names
    }
    if set(designed_backbone) != set(predicted_backbone):
        raise ManifestStateError("predicted binder backbone identity 与 designed candidate 不一致")
    if len(designed_backbone) < 3:
        raise ManifestStateError("binder backbone RMSD 至少需要三个共同原子")
    identities = sorted(designed_backbone)
    binder_reference = np.asarray(
        [designed_backbone[item] for item in identities],
        dtype=np.float64,
    )
    binder_mobile = np.asarray(
        [predicted_backbone[item] for item in identities],
        dtype=np.float64,
    )
    binder_aligned = (binder_mobile - mobile_center) @ rotation + reference_center
    binder_rmsd = float(np.sqrt(np.mean(np.sum((binder_aligned - binder_reference) ** 2, axis=1))))
    distances = _pairwise_distances(predicted_target.atoms, predicted_binder.atoms)
    return FullTargetStructureMetrics(
        binder_pose_rmsd_angstrom=binder_rmsd,
        target_ca_rmsd_angstrom=target_ca_rmsd(
            reference_target,
            predicted_target,
        ),
        severe_clash_count=int((distances < SEVERE_CLASH_ANGSTROM).sum()),
        moderate_clash_count=int(
            ((distances >= SEVERE_CLASH_ANGSTROM) & (distances < MODERATE_CLASH_ANGSTROM)).sum()
        ),
    )


def _interface_bsa(
    path: Path,
    *,
    target_chain_id: str,
    binder_chain_id: str,
) -> tuple[float | None, str | None]:
    try:
        parser = MMCIFParser(QUIET=True)  # type: ignore[no-untyped-call]
        structure = parser.get_structure(  # type: ignore[no-untyped-call]
            "complex",
            str(path),
        )
        model = next(structure.get_models())
        if target_chain_id not in model or binder_chain_id not in model:
            raise KeyError("required chain missing")
        calculator = ShrakeRupley(  # type: ignore[no-untyped-call]
            probe_radius=SASA_PROBE_RADIUS_ANGSTROM,
            n_points=SASA_SPHERE_POINTS,
        )
        complex_copy = copy.deepcopy(structure)
        calculator.compute(complex_copy, level="A")  # type: ignore[no-untyped-call]
        complex_model = next(complex_copy.get_models())
        complex_sasa = sum(
            float(atom.sasa)
            for chain_id in (target_chain_id, binder_chain_id)
            for atom in complex_model[chain_id].get_atoms()
        )
        unbound_sasa = 0.0
        for retained_chain in (target_chain_id, binder_chain_id):
            isolated = copy.deepcopy(structure)
            isolated_model = next(isolated.get_models())
            for chain in tuple(isolated_model):
                if chain.id != retained_chain:
                    isolated_model.detach_child(chain.id)
            calculator.compute(isolated, level="A")  # type: ignore[no-untyped-call]
            unbound_sasa += sum(
                float(atom.sasa) for atom in next(isolated.get_models())[retained_chain].get_atoms()
            )
        bsa = (unbound_sasa - complex_sasa) / 2.0
        return max(float(bsa), 0.0), None
    except Exception as error:  # fallback is explicit in the caller's audit record
        return None, f"{error.__class__.__name__}: {str(error)[:512]}"


def compute_interface_metrics(
    *,
    candidate_structure: Path,
    reference_target: ParsedChain,
    hotspot_residue_ids: tuple[int, ...],
    cdr_residue_ids: tuple[int, ...],
    target_chain_id: str = "A",
    binder_chain_id: str = "B",
) -> InterfaceMetricValues:
    """计算 v1.5 pilot 所需的结构、界面和 clash 指标。"""

    target = parse_protein_chain(candidate_structure, target_chain_id)
    binder = parse_protein_chain(candidate_structure, binder_chain_id)
    if len(hotspot_residue_ids) != len(set(hotspot_residue_ids)) or not hotspot_residue_ids:
        raise ManifestStateError("hotspot residue identity 必须非空且不能重复")
    binder_ids = {residue.residue_id for residue in binder.residues}
    cdr_ids = set(cdr_residue_ids)
    if not cdr_ids or not cdr_ids.issubset(binder_ids):
        raise ManifestStateError("CDR mask 必须是 candidate binder residue 的非空子集")
    distances = _pairwise_distances(target.atoms, binder.atoms)
    contact_mask = distances <= CONTACT_ANGSTROM
    severe_mask = distances < SEVERE_CLASH_ANGSTROM
    moderate_mask = (distances >= SEVERE_CLASH_ANGSTROM) & (distances < MODERATE_CLASH_ANGSTROM)
    target_contacted = {
        target.atoms[index].residue_id for index in np.flatnonzero(contact_mask.any(axis=1))
    }
    binder_contacted = {
        binder.atoms[index].residue_id for index in np.flatnonzero(contact_mask.any(axis=0))
    }
    hotspot_set = set(hotspot_residue_ids)
    contacted_hotspots = hotspot_set.intersection(target_contacted)
    residue_pairs = {
        (target.atoms[first].residue_id, binder.atoms[second].residue_id)
        for first, second in np.argwhere(contact_mask)
    }
    polar_contacts = sum(
        1
        for first, second in np.argwhere(contact_mask)
        if target.atoms[first].element in _POLAR_ELEMENTS
        and binder.atoms[second].element in _POLAR_ELEMENTS
    )
    hydrogen_bonds = sum(
        1
        for first, second in np.argwhere(distances <= HYDROGEN_BOND_ANGSTROM)
        if target.atoms[first].element in _POLAR_ELEMENTS
        and binder.atoms[second].element in _POLAR_ELEMENTS
    )
    salt_bridges = sum(
        1
        for first, second in np.argwhere(distances <= SALT_BRIDGE_ANGSTROM)
        if (
            (
                (target.atoms[first].residue_name, target.atoms[first].atom_name) in _ACIDIC_ATOMS
                and (binder.atoms[second].residue_name, binder.atoms[second].atom_name)
                in _BASIC_ATOMS
            )
            or (
                (target.atoms[first].residue_name, target.atoms[first].atom_name) in _BASIC_ATOMS
                and (binder.atoms[second].residue_name, binder.atoms[second].atom_name)
                in _ACIDIC_ATOMS
            )
        )
    )
    interface_bsa, bsa_error = _interface_bsa(
        candidate_structure,
        target_chain_id=target_chain_id,
        binder_chain_id=binder_chain_id,
    )
    binder_contact_count = len(binder_contacted)
    cdr_contact_count = len(cdr_ids.intersection(binder_contacted))
    atom_contact_count = int(contact_mask.sum())
    return InterfaceMetricValues(
        target_ca_rmsd_angstrom=target_ca_rmsd(reference_target, target),
        hotspot_coverage=len(contacted_hotspots) / len(hotspot_set),
        contacted_hotspot_count=len(contacted_hotspots),
        hotspot_count=len(hotspot_set),
        binder_contact_coverage=binder_contact_count / len(binder.residues),
        cdr_dominance=(cdr_contact_count / binder_contact_count if binder_contact_count else 0.0),
        cdr_utilization=cdr_contact_count / len(cdr_ids),
        residue_pair_contact_count=len(residue_pairs),
        atom_contact_count=atom_contact_count,
        severe_clash_count=int(severe_mask.sum()),
        moderate_clash_count=int(moderate_mask.sum()),
        hydrogen_bond_count=hydrogen_bonds,
        salt_bridge_count=salt_bridges,
        polar_contact_fraction=(polar_contacts / atom_contact_count if atom_contact_count else 0.0),
        interface_bsa_angstrom2=interface_bsa,
        interface_bsa_missing_reason=bsa_error,
    )


def contacted_hotspot_residue_ids(
    *,
    candidate_structure: Path,
    hotspot_residue_ids: tuple[int, ...],
    target_chain_id: str = "A",
    binder_chain_id: str = "B",
) -> tuple[int, ...]:
    """Return target hotspot label IDs with a cross-chain heavy-atom contact."""

    if not hotspot_residue_ids or len(hotspot_residue_ids) != len(set(hotspot_residue_ids)):
        raise ManifestStateError("hotspot residue identity 必须非空且不能重复")
    target = parse_protein_chain(candidate_structure, target_chain_id)
    binder = parse_protein_chain(candidate_structure, binder_chain_id)
    distances = _pairwise_distances(target.atoms, binder.atoms)
    contact_mask = distances <= CONTACT_ANGSTROM
    contacted_target = {
        target.atoms[index].residue_id for index in np.flatnonzero(contact_mask.any(axis=1))
    }
    return tuple(sorted(set(hotspot_residue_ids).intersection(contacted_target)))


def unpaired_designed_cysteine_residue_ids(
    *,
    candidate_structure: Path,
    designed_residue_ids: tuple[int, ...],
    binder_chain_id: str = "B",
    disulfide_min_angstrom: float = 1.8,
    disulfide_max_angstrom: float = 2.3,
) -> tuple[int, ...]:
    """Identify newly designed cysteines without a structure-supported S–S partner."""

    if not designed_residue_ids:
        raise ManifestStateError("designed residue identity 不能为空")
    binder = parse_protein_chain(candidate_structure, binder_chain_id)
    designed = set(designed_residue_ids)
    binder_ids = {item.residue_id for item in binder.residues}
    if not designed.issubset(binder_ids):
        raise ManifestStateError("designed residue identity 不是 binder residue 子集")
    cysteine_sg = {
        atom.residue_id: atom
        for atom in binder.atoms
        if atom.residue_name == "CYS" and atom.atom_name == "SG"
    }
    designed_cysteines = {
        item.residue_id
        for item in binder.residues
        if item.residue_id in designed and item.residue_name == "CYS"
    }
    unpaired: list[int] = []
    for residue_id in sorted(designed_cysteines):
        sulfur = cysteine_sg.get(residue_id)
        if sulfur is None:
            unpaired.append(residue_id)
            continue
        paired = False
        sulfur_coordinate = np.asarray(sulfur.coordinate, dtype=np.float64)
        for partner_id, partner in cysteine_sg.items():
            if partner_id == residue_id:
                continue
            distance = float(
                np.linalg.norm(sulfur_coordinate - np.asarray(partner.coordinate, dtype=np.float64))
            )
            if disulfide_min_angstrom <= distance <= disulfide_max_angstrom:
                paired = True
                break
        if not paired:
            unpaired.append(residue_id)
    return tuple(unpaired)
