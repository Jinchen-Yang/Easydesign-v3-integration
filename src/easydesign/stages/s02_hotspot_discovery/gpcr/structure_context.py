"""Conservative GPCR structure parsing and geometry analysis.

The public ``analyze_structure`` entry point emits JSON-friendly data. Membrane
regions are intentionally withheld unless residue topology, seven-helix geometry,
and extracellular/intracellular direction are all supported.
"""

from __future__ import annotations

import hashlib
import math
import re
from collections import defaultdict
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

ANALYSIS_SCHEMA = "1.0"
Vec3 = tuple[float, float, float]


AMINO_ACID_3_TO_1 = {
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
    "MSE": "M",
    "SEC": "U",
    "PYL": "O",
    "ASX": "B",
    "GLX": "Z",
}
BACKBONE_ATOMS = {"N", "CA", "C", "O", "OXT"}
TM_PATTERN = re.compile(r"^TM([1-7])$", re.IGNORECASE)
LARGE_ECD_MINIMUM_RESIDUES = 60


class StructureAnalysisError(RuntimeError):
    """Raised when a structure cannot be parsed or analyzed faithfully."""


@dataclass(frozen=True)
class ResidueIdentity:
    model_id: str
    chain_id: str
    seq_num: int
    insertion_code: str = ""
    hetero_flag: str = "ATOM"
    label_chain_id: str | None = None
    label_seq_id: int | None = None

    def sort_key(self) -> tuple[Any, ...]:
        return (
            self.model_id,
            self.chain_id,
            self.seq_num,
            self.insertion_code,
            self.hetero_flag,
            self.label_chain_id or "",
            self.label_seq_id if self.label_seq_id is not None else -(10**12),
        )

    def key(self) -> str:
        label = ""
        if self.label_chain_id is not None or self.label_seq_id is not None:
            label_seq = self.label_seq_id if self.label_seq_id is not None else ""
            label = f"|{self.label_chain_id or ''}:{label_seq}"
        return (
            f"{self.model_id}|{self.chain_id}|{self.hetero_flag}|"
            f"{self.seq_num}{self.insertion_code}{label}"
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key(),
            "model_id": self.model_id,
            "chain_id": self.chain_id,
            "auth_asym_id": self.chain_id,
            "auth_seq_id": self.seq_num,
            "insertion_code": self.insertion_code,
            "hetero_flag": self.hetero_flag,
            "label_chain_id": self.label_chain_id,
            "label_asym_id": self.label_chain_id,
            "label_seq_id": self.label_seq_id,
        }


@dataclass(frozen=True)
class AtomRecord:
    name: str
    element: str
    coord: Vec3
    altloc: str = ""
    occupancy: float | None = None
    b_factor: float | None = None
    serial: int | None = None

    @property
    def is_hydrogen(self) -> bool:
        element = self.element.upper().strip()
        return element in {"H", "D"} or (
            not element and self.name.lstrip("0123456789").startswith("H")
        )


@dataclass
class ResidueRecord:
    identity: ResidueIdentity
    resname: str
    atoms: list[AtomRecord]
    is_polymer: bool

    @property
    def one_letter(self) -> str | None:
        return AMINO_ACID_3_TO_1.get(self.resname.upper())

    def selected_atoms(self, *, heavy_only: bool = False) -> list[AtomRecord]:
        selected: dict[str, AtomRecord] = {}
        for atom in self.atoms:
            if heavy_only and atom.is_hydrogen:
                continue
            current = selected.get(atom.name)
            if current is None:
                selected[atom.name] = atom
                continue
            atom_rank = (
                atom.occupancy if atom.occupancy is not None else -1.0,
                atom.altloc == "",
                atom.altloc == "A",
                -ord(atom.altloc[0]) if atom.altloc else 0,
            )
            current_rank = (
                current.occupancy if current.occupancy is not None else -1.0,
                current.altloc == "",
                current.altloc == "A",
                -ord(current.altloc[0]) if current.altloc else 0,
            )
            if atom_rank > current_rank:
                selected[atom.name] = atom
        return [selected[name] for name in sorted(selected)]

    def atom(self, name: str) -> AtomRecord | None:
        for atom in self.selected_atoms():
            if atom.name == name:
                return atom
        return None

    def representative_point(self) -> Vec3 | None:
        ca = self.atom("CA")
        if ca:
            return ca.coord
        atoms = self.selected_atoms(heavy_only=True)
        return _centroid(atom.coord for atom in atoms) if atoms else None

    def sidechain_point(self) -> Vec3 | None:
        atoms = [
            atom.coord
            for atom in self.selected_atoms(heavy_only=True)
            if atom.name not in BACKBONE_ATOMS
        ]
        return _centroid(atoms) if atoms else self.representative_point()

    def to_dict(self, *, include_atoms: bool = False) -> dict[str, Any]:
        value: dict[str, Any] = {
            "identity": self.identity.to_dict(),
            "resname": self.resname,
            "amino_acid": self.one_letter,
            "is_polymer": self.is_polymer,
            "atom_count": len(self.atoms),
        }
        if include_atoms:
            value["atoms"] = [
                {
                    "name": atom.name,
                    "element": atom.element,
                    "coord": list(atom.coord),
                    "altloc": atom.altloc,
                    "occupancy": atom.occupancy,
                    "b_factor": atom.b_factor,
                    "serial": atom.serial,
                }
                for atom in self.atoms
            ]
        return value


@dataclass
class ParsedStructure:
    path: Path
    file_format: str
    parser: str
    model_id: str
    residues: list[ResidueRecord]
    sha256: str
    parser_warnings: list[str] = field(default_factory=list)

    def chain_ids(self, *, polymer_only: bool = False) -> list[str]:
        return sorted(
            {
                residue.identity.chain_id
                for residue in self.residues
                if not polymer_only or residue.is_polymer
            }
        )

    def residue_lookup(self) -> dict[str, ResidueRecord]:
        return {residue.identity.key(): residue for residue in self.residues}


@dataclass(frozen=True)
class TopologyAssignment:
    residue: ResidueIdentity
    segment: str
    generic_number: str | None
    sequence_number: int | None
    amino_acid: str | None
    observed_amino_acid: str | None
    mapping_method: str
    alternative_generic_numbers: tuple[Mapping[str, Any], ...] = ()

    def to_dict(self) -> dict[str, Any]:
        identity = self.residue.to_dict()
        sequence_matches_structure = (
            self.amino_acid is None
            or self.observed_amino_acid is None
            or self.amino_acid == self.observed_amino_acid
        )
        return {
            "residue": identity,
            "label_asym_id": identity["label_asym_id"],
            "label_seq_id": identity["label_seq_id"],
            "auth_asym_id": identity["auth_asym_id"],
            "auth_seq_id": identity["auth_seq_id"],
            "insertion_code": identity["insertion_code"],
            "protein_segment": self.segment,
            "segment": self.segment,
            "generic_number": self.generic_number,
            "display_generic_number": self.generic_number,
            "sequence_number": self.sequence_number,
            "gpcrdb_sequence_number": self.sequence_number,
            "sequence_index": self.sequence_number - 1 if self.sequence_number else None,
            "amino_acid": self.amino_acid,
            "observed_amino_acid": self.observed_amino_acid,
            "alternative_generic_numbers": [
                dict(value) for value in self.alternative_generic_numbers
            ],
            "observed": True,
            "mapping_status": "exact" if sequence_matches_structure else "sequence_mismatch",
            "mapping_note": (
                None
                if sequence_matches_structure
                else (
                    f"GPCRdb amino acid {self.amino_acid} differs from observed "
                    f"structure amino acid {self.observed_amino_acid}; treat as a construct, "
                    "variant, or identity-conflict risk"
                )
            ),
            "mapping_method": self.mapping_method,
        }


@dataclass
class TopologyMap:
    assignments: dict[str, TopologyAssignment]
    mapping_reliable: bool
    mapped_count: int
    unmapped_count: int
    amino_acid_match_fraction: float | None
    methods: list[str]
    warnings: list[str]
    unmapped_residues: list[dict[str, Any]] = field(default_factory=list)

    def segment_for(self, residue: ResidueRecord | ResidueIdentity) -> str | None:
        identity = residue.identity if isinstance(residue, ResidueRecord) else residue
        assignment = self.assignments.get(identity.key())
        return assignment.segment if assignment else None

    def assignment_for(self, residue: ResidueRecord | ResidueIdentity) -> TopologyAssignment | None:
        identity = residue.identity if isinstance(residue, ResidueRecord) else residue
        return self.assignments.get(identity.key())

    def to_dict(self) -> dict[str, Any]:
        total = self.mapped_count + self.unmapped_count
        residue_rows = [
            assignment.to_dict()
            for assignment in sorted(
                self.assignments.values(), key=lambda item: item.residue.sort_key()
            )
        ] + [dict(value) for value in self.unmapped_residues]
        residue_rows.sort(
            key=lambda item: (
                item.get("gpcrdb_sequence_number") is None,
                item.get("gpcrdb_sequence_number") or 10**12,
                str(item.get("auth_asym_id") or ""),
                item.get("auth_seq_id") or 10**12,
            )
        )
        return {
            "mapping_status": (
                "resolved"
                if self.mapping_reliable
                else "partial"
                if self.mapped_count
                else "unresolved"
            ),
            "mapping_coverage": self.mapped_count / total if total else 0.0,
            "mapping_reliable": self.mapping_reliable,
            "mapped_count": self.mapped_count,
            "unmapped_count": self.unmapped_count,
            "amino_acid_match_fraction": self.amino_acid_match_fraction,
            "mapping_methods": sorted(self.methods),
            "warnings": list(self.warnings),
            "residues": residue_rows,
            "unmapped_residues": [dict(value) for value in self.unmapped_residues],
        }


@dataclass
class MembraneFrame:
    reliable: bool
    center: Vec3 | None
    extracellular_axis: Vec3 | None
    intracellular_axis: Vec3 | None
    extracellular_boundary: float | None
    intracellular_boundary: float | None
    half_span: float | None
    direction_source: str | None
    topology_reliable: bool
    helix_count: int
    helix_direction_consistency: float | None
    loop_separation: float | None
    reasons: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": "resolved" if self.reliable else "unresolved",
            "reliable": self.reliable,
            "center": list(self.center) if self.center else None,
            "extracellular_axis": list(self.extracellular_axis)
            if self.extracellular_axis
            else None,
            "intracellular_axis": list(self.intracellular_axis)
            if self.intracellular_axis
            else None,
            "normal_extracellular_to_intracellular": (
                list(self.intracellular_axis) if self.intracellular_axis else None
            ),
            "bilayer_midplane": list(self.center) if self.center else None,
            "headgroup_boundaries": (
                [self.intracellular_boundary, self.extracellular_boundary]
                if self.reliable
                else None
            ),
            "extracellular_boundary": self.extracellular_boundary,
            "intracellular_boundary": self.intracellular_boundary,
            "half_span": self.half_span,
            "direction_source": self.direction_source,
            "source": self.direction_source,
            "confidence": "high" if self.reliable else "unresolved",
            "topology_reliable": self.topology_reliable,
            "helix_count": self.helix_count,
            "helix_direction_consistency": self.helix_direction_consistency,
            "loop_separation": self.loop_separation,
            "reasons": list(self.reasons),
        }


def _normalize_text(value: Any) -> str:
    text = str(value or "").strip()
    return "" if text in {".", "?", "\x00"} else text


def _float_or_none(value: Any) -> float | None:
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (TypeError, ValueError):
        return None


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _centroid(points: Iterable[Vec3]) -> Vec3 | None:
    values = list(points)
    if not values:
        return None
    return (
        sum(point[0] for point in values) / len(values),
        sum(point[1] for point in values) / len(values),
        sum(point[2] for point in values) / len(values),
    )


def _add(a: Vec3, b: Vec3) -> Vec3:
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def _sub(a: Vec3, b: Vec3) -> Vec3:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _scale(vector: Vec3, factor: float) -> Vec3:
    return (vector[0] * factor, vector[1] * factor, vector[2] * factor)


def _dot(a: Vec3, b: Vec3) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _norm(vector: Vec3) -> float:
    return math.sqrt(_dot(vector, vector))


def _normalize(vector: Vec3) -> Vec3 | None:
    length = _norm(vector)
    return _scale(vector, 1.0 / length) if length > 1e-8 else None


def _distance(a: Vec3, b: Vec3) -> float:
    return _norm(_sub(a, b))


def _quantile(values: Sequence[float], fraction: float) -> float:
    if not values:
        raise ValueError("quantile requires values")
    ordered = sorted(values)
    position = min(1.0, max(0.0, fraction)) * (len(ordered) - 1)
    lower = int(math.floor(position))
    upper = int(math.ceil(position))
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def _hetero_flag(record_type: str, resname: str) -> str:
    return "ATOM" if record_type == "ATOM" else f"HETATM:{resname.upper()}"


def _parse_pdb_standard(path: Path, model_index: int) -> ParsedStructure:
    residues: dict[tuple[Any, ...], ResidueRecord] = {}
    current_model_index = 0
    current_model_id = "1"
    saw_model = False
    selected_model_id: str | None = None

    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            record_type = line[0:6].strip().upper()
            if record_type == "MODEL":
                saw_model = True
                model_id = line[10:14].strip() or str(current_model_index + 1)
                current_model_id = model_id
                if current_model_index == model_index:
                    selected_model_id = model_id
                current_model_index += 1
                continue
            if record_type == "ENDMDL":
                continue
            active_index = current_model_index - 1 if saw_model else 0
            if active_index != model_index or record_type not in {"ATOM", "HETATM"}:
                continue
            if len(line) < 54:
                continue
            try:
                seq_num = int(line[22:26].strip())
                coord = (
                    float(line[30:38]),
                    float(line[38:46]),
                    float(line[46:54]),
                )
            except ValueError:
                continue
            model_id = selected_model_id or current_model_id or str(model_index + 1)
            chain_id = line[21:22].strip()
            insertion_code = _normalize_text(line[26:27])
            resname = line[17:20].strip().upper()
            hetero = _hetero_flag(record_type, resname)
            identity = ResidueIdentity(model_id, chain_id, seq_num, insertion_code, hetero)
            key = (identity.key(), resname)
            residue = residues.get(key)
            if residue is None:
                residue = ResidueRecord(
                    identity=identity,
                    resname=resname,
                    atoms=[],
                    is_polymer=record_type == "ATOM" or resname in AMINO_ACID_3_TO_1,
                )
                residues[key] = residue
            atom_name = line[12:16].strip()
            element = line[76:78].strip().upper() if len(line) >= 78 else ""
            if not element:
                element = atom_name.lstrip("0123456789")[:1].upper()
            residue.atoms.append(
                AtomRecord(
                    name=atom_name,
                    element=element,
                    coord=coord,
                    altloc=_normalize_text(line[16:17]),
                    occupancy=_float_or_none(line[54:60].strip()),
                    b_factor=_float_or_none(line[60:66].strip()),
                    serial=_int_or_none(line[6:11].strip()),
                )
            )

    if not residues:
        raise StructureAnalysisError(f"no atoms found for model index {model_index} in {path}")
    ordered = sorted(residues.values(), key=lambda item: item.identity.sort_key())
    model_id = ordered[0].identity.model_id
    return ParsedStructure(path, "pdb", "standard-pdb", model_id, ordered, _sha256_file(path))


def _parse_with_gemmi(path: Path, model_index: int) -> ParsedStructure:
    import gemmi

    structure = gemmi.read_structure(str(path))
    if len(structure) <= model_index:
        raise StructureAnalysisError(f"model index {model_index} is absent from {path}")
    model = structure[model_index]
    model_id = _normalize_text(getattr(model, "name", "")) or str(model_index + 1)
    residues: list[ResidueRecord] = []

    for chain in model:
        chain_id = _normalize_text(getattr(chain, "name", ""))
        for residue in chain:
            seq_num = int(cast(int, residue.seqid.num))
            insertion_code = _normalize_text(residue.seqid.icode)
            resname = str(residue.name).strip().upper()
            entity_name = str(getattr(residue, "entity_type", "")).split(".")[-1].lower()
            is_polymer = entity_name == "polymer" or resname in AMINO_ACID_3_TO_1
            record_type = "ATOM" if is_polymer else "HETATM"
            label_chain_id = _normalize_text(getattr(residue, "subchain", "")) or None
            label_seq_id = _int_or_none(getattr(residue, "label_seq", None))
            identity = ResidueIdentity(
                model_id=model_id,
                chain_id=chain_id,
                seq_num=seq_num,
                insertion_code=insertion_code,
                hetero_flag=_hetero_flag(record_type, resname),
                label_chain_id=label_chain_id,
                label_seq_id=label_seq_id,
            )
            atoms: list[AtomRecord] = []
            for atom in residue:
                element = _normalize_text(getattr(atom.element, "name", "")).upper()
                atoms.append(
                    AtomRecord(
                        name=str(atom.name).strip(),
                        element=element,
                        coord=(float(atom.pos.x), float(atom.pos.y), float(atom.pos.z)),
                        altloc=_normalize_text(atom.altloc),
                        occupancy=_float_or_none(atom.occ),
                        b_factor=_float_or_none(atom.b_iso),
                        serial=_int_or_none(getattr(atom, "serial", None)),
                    )
                )
            if atoms:
                residues.append(ResidueRecord(identity, resname, atoms, is_polymer))

    if not residues:
        raise StructureAnalysisError(f"gemmi found no atoms in model {model_id} of {path}")
    file_format = "mmcif" if path.suffix.lower() in {".cif", ".mmcif"} else "pdb"
    return ParsedStructure(
        path,
        file_format,
        "gemmi",
        model_id,
        sorted(residues, key=lambda item: item.identity.sort_key()),
        _sha256_file(path),
    )


def _parse_with_biopython(path: Path, model_index: int) -> ParsedStructure:
    from Bio.PDB.MMCIFParser import MMCIFParser
    from Bio.PDB.PDBParser import PDBParser

    is_cif = path.suffix.lower() in {".cif", ".mmcif"}
    parser_factory: Any = MMCIFParser if is_cif else PDBParser
    parser: Any = (
        parser_factory(QUIET=True, auth_chains=True, auth_residues=True)
        if is_cif
        else parser_factory(QUIET=True)
    )
    structure = parser.get_structure(path.stem, str(path))
    models = list(structure.get_models())
    if len(models) <= model_index:
        raise StructureAnalysisError(f"model index {model_index} is absent from {path}")
    model = models[model_index]
    model_id = str(getattr(model, "serial_num", None) or getattr(model, "id", model_index) + 1)
    residues: list[ResidueRecord] = []

    for chain in model:
        chain_id = _normalize_text(chain.id)
        for residue in chain:
            hetero_id, seq_num, insertion_code = residue.id
            resname = str(residue.resname).strip().upper()
            is_polymer = str(hetero_id).strip() in {"", " "} or resname in AMINO_ACID_3_TO_1
            record_type = "ATOM" if is_polymer else "HETATM"
            identity = ResidueIdentity(
                model_id=model_id,
                chain_id=chain_id,
                seq_num=int(seq_num),
                insertion_code=_normalize_text(insertion_code),
                hetero_flag=_hetero_flag(record_type, resname),
            )
            atoms: list[AtomRecord] = []
            for atom in residue.get_unpacked_list():
                coord = atom.get_coord()
                atoms.append(
                    AtomRecord(
                        name=str(atom.get_name()).strip(),
                        element=_normalize_text(getattr(atom, "element", "")).upper(),
                        coord=(float(coord[0]), float(coord[1]), float(coord[2])),
                        altloc=_normalize_text(atom.get_altloc()),
                        occupancy=_float_or_none(atom.get_occupancy()),
                        b_factor=_float_or_none(atom.get_bfactor()),
                        serial=_int_or_none(atom.get_serial_number()),
                    )
                )
            if atoms:
                residues.append(ResidueRecord(identity, resname, atoms, is_polymer))

    if not residues:
        raise StructureAnalysisError(f"Biopython found no atoms in model {model_id} of {path}")
    return ParsedStructure(
        path,
        "mmcif" if is_cif else "pdb",
        "biopython",
        model_id,
        sorted(residues, key=lambda item: item.identity.sort_key()),
        _sha256_file(path),
    )


def parse_structure(
    path: str | Path,
    *,
    model_index: int = 0,
    parser: str = "auto",
) -> ParsedStructure:
    """Parse PDB/mmCIF while preserving author chain, number, and insertion code."""

    source = Path(path).expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    if model_index < 0:
        raise ValueError("model_index must be non-negative")
    parser = parser.lower()
    if parser not in {"auto", "gemmi", "biopython", "pdb"}:
        raise ValueError("parser must be auto, gemmi, biopython, or pdb")

    attempts: list[tuple[str, Callable[[Path, int], ParsedStructure]]] = []
    if parser in {"auto", "gemmi"}:
        attempts.append(("gemmi", _parse_with_gemmi))
    if parser in {"auto", "biopython"}:
        attempts.append(("biopython", _parse_with_biopython))
    if parser == "pdb" or (parser == "auto" and source.suffix.lower() not in {".cif", ".mmcif"}):
        attempts.append(("standard-pdb", _parse_pdb_standard))

    errors: list[str] = []
    for name, loader in attempts:
        try:
            parsed = loader(source, model_index)
            parsed.parser_warnings.extend(errors)
            return parsed
        except (ImportError, OSError, RuntimeError, ValueError) as exc:
            errors.append(f"{name}: {exc}")
            if parser != "auto":
                break
    raise StructureAnalysisError(
        f"unable to parse {source.name}; "
        + ("; ".join(errors) if errors else "no parser available")
    )


def _extract_topology_records(gpcr_residues: Any) -> list[Mapping[str, Any]]:
    if gpcr_residues is None:
        return []
    if isinstance(gpcr_residues, Mapping):
        if "residues" in gpcr_residues:
            return _extract_topology_records(gpcr_residues["residues"])
        if "topology" in gpcr_residues:
            return _extract_topology_records(gpcr_residues["topology"])
        records: list[Mapping[str, Any]] = []
        for key, value in gpcr_residues.items():
            if isinstance(value, str):
                records.append({"residue_key": key, "protein_segment": value})
            elif isinstance(value, Mapping):
                records.append({"residue_key": key, **value})
        return records
    if isinstance(gpcr_residues, Sequence) and not isinstance(gpcr_residues, (str, bytes)):
        return [item for item in gpcr_residues if isinstance(item, Mapping)]
    raise TypeError("gpcr_residues must be a residue list or mapping")


def _identity_from_mapping(
    value: Mapping[str, Any],
    *,
    default_chain: str,
    default_model: str,
) -> ResidueIdentity | None:
    nested = value.get("residue") or value.get("identity") or value.get("residue_id")
    source = nested if isinstance(nested, Mapping) else value
    seq_num = _int_or_none(
        source.get("auth_seq_id", source.get("author_residue_number", source.get("residue_number")))
    )
    if seq_num is None:
        return None
    chain = _normalize_text(
        source.get("chain_id", source.get("auth_asym_id", source.get("chain", default_chain)))
    )
    model_id = _normalize_text(source.get("model_id", default_model)) or default_model
    insertion = _normalize_text(
        source.get("insertion_code", source.get("icode", source.get("pdb_ins_code", "")))
    )
    hetero = _normalize_text(source.get("hetero_flag", "ATOM")) or "ATOM"
    return ResidueIdentity(
        model_id=model_id,
        chain_id=chain,
        seq_num=seq_num,
        insertion_code=insertion,
        hetero_flag=hetero,
        label_chain_id=_normalize_text(source.get("label_chain_id")) or None,
        label_seq_id=_int_or_none(source.get("label_seq_id")),
    )


def _align_gpcr_records_to_chain(
    records: Sequence[Mapping[str, Any]],
    chain_residues: Sequence[ResidueRecord],
) -> tuple[dict[int, ResidueRecord], str | None]:
    """Align a GPCRdb sequence to observed polymer residues without renumbering them."""

    gpcr_rows = [
        record
        for record in sorted(
            records,
            key=lambda item: _int_or_none(item.get("sequence_number")) or 10**12,
        )
        if _int_or_none(record.get("sequence_number")) is not None
        and len(_normalize_text(record.get("amino_acid"))) == 1
    ]
    observed = [
        residue
        for residue in sorted(chain_residues, key=lambda item: item.identity.sort_key())
        if residue.one_letter is not None
    ]
    if len(gpcr_rows) < 20 or len(observed) < 20:
        return {}, None
    gpcr_sequence = "".join(_normalize_text(row.get("amino_acid")).upper() for row in gpcr_rows)
    observed_sequence = "".join(str(residue.one_letter) for residue in observed)
    try:
        from Bio.Align import PairwiseAligner

        aligner_factory: Any = PairwiseAligner
        aligner: Any = aligner_factory()
        aligner.mode = "global"
        aligner.match_score = 2.0
        aligner.mismatch_score = -2.0
        aligner.open_gap_score = -6.0
        aligner.extend_gap_score = -0.5
        alignment = aligner.align(gpcr_sequence, observed_sequence)[0]
    except (ImportError, IndexError, RuntimeError, ValueError) as exc:
        return {}, f"sequence-alignment mapping unavailable: {exc}"

    mapping: dict[int, ResidueRecord] = {}
    target_blocks, query_blocks = alignment.aligned
    for target_block, query_block in zip(target_blocks, query_blocks, strict=True):
        target_start, target_end = (int(target_block[0]), int(target_block[1]))
        query_start, query_end = (int(query_block[0]), int(query_block[1]))
        block_length = min(target_end - target_start, query_end - query_start)
        for offset in range(block_length):
            row = gpcr_rows[target_start + offset]
            sequence_number = _int_or_none(row.get("sequence_number"))
            if sequence_number is not None:
                mapping[sequence_number] = observed[query_start + offset]
    return mapping, None


def map_gpcr_topology(
    structure: ParsedStructure,
    receptor_chain: str,
    gpcr_residues: Any,
) -> TopologyMap:
    """Map GPCRdb-style residue annotations onto exact structure identities.

    Raw GPCRdb sequence numbers are accepted only as a verified mapping: present
    amino-acid labels must agree with structure author numbering for at least 90% of
    mapped residues. Explicit author identifiers are considered reliable directly.
    """

    records = _extract_topology_records(gpcr_residues)
    warnings: list[str] = []
    if not records:
        return TopologyMap({}, False, 0, 0, None, [], ["no GPCR topology annotations supplied"])

    chain_residues = [
        residue
        for residue in structure.residues
        if residue.identity.chain_id == receptor_chain and residue.is_polymer
    ]
    by_author: dict[tuple[int, str], list[ResidueRecord]] = defaultdict(list)
    by_key = structure.residue_lookup()
    for residue in chain_residues:
        by_author[(residue.identity.seq_num, residue.identity.insertion_code)].append(residue)
    alignment_map, alignment_warning = _align_gpcr_records_to_chain(records, chain_residues)
    if alignment_warning:
        warnings.append(alignment_warning)

    assignments: dict[str, TopologyAssignment] = {}
    unmapped_rows: list[dict[str, Any]] = []
    methods: set[str] = set()
    unmapped = 0
    explicit_count = 0
    sequence_count = 0
    aa_compared = 0
    aa_matched = 0

    def unresolved_row(record: Mapping[str, Any], mapping_status: str, note: str) -> dict[str, Any]:
        identity = _identity_from_mapping(
            record, default_chain=receptor_chain, default_model=structure.model_id
        )
        identity_fields = identity.to_dict() if identity is not None else {}
        alternative = record.get("alternative_generic_numbers")
        if not isinstance(alternative, Sequence) or isinstance(alternative, (str, bytes)):
            alternative = []
        sequence_number = _int_or_none(record.get("sequence_number"))
        return {
            **identity_fields,
            "residue": identity_fields or None,
            "label_asym_id": identity_fields.get("label_asym_id"),
            "label_seq_id": identity_fields.get("label_seq_id"),
            "auth_asym_id": identity_fields.get("auth_asym_id"),
            "auth_seq_id": identity_fields.get("auth_seq_id"),
            "insertion_code": identity_fields.get("insertion_code"),
            "protein_segment": record.get("protein_segment", record.get("segment")),
            "segment": record.get("protein_segment", record.get("segment")),
            "generic_number": record.get("display_generic_number", record.get("generic_number")),
            "display_generic_number": record.get(
                "display_generic_number", record.get("generic_number")
            ),
            "sequence_number": sequence_number,
            "gpcrdb_sequence_number": sequence_number,
            "sequence_index": sequence_number - 1 if sequence_number else None,
            "amino_acid": _normalize_text(record.get("amino_acid")).upper() or None,
            "alternative_generic_numbers": [
                dict(value) for value in alternative if isinstance(value, Mapping)
            ],
            "observed": False,
            "mapping_status": mapping_status,
            "mapping_note": note,
        }

    for record in records:
        segment = _normalize_text(
            record.get("protein_segment", record.get("segment", record.get("topology")))
        )
        if not segment:
            unmapped += 1
            unmapped_rows.append(unresolved_row(record, "unresolved", "topology segment is absent"))
            continue
        generic = (
            _normalize_text(record.get("display_generic_number", record.get("generic_number")))
            or None
        )
        alternative_numbers = record.get("alternative_generic_numbers")
        if not isinstance(alternative_numbers, Sequence) or isinstance(
            alternative_numbers, (str, bytes)
        ):
            alternative_numbers = []
        sequence_number = _int_or_none(record.get("sequence_number"))
        amino_acid = _normalize_text(record.get("amino_acid")).upper() or None

        exact_identity = _identity_from_mapping(
            record, default_chain=receptor_chain, default_model=structure.model_id
        )
        mapped_residue: ResidueRecord | None = None
        method = ""
        if exact_identity is not None:
            mapped_residue = by_key.get(exact_identity.key())
            if mapped_residue is None:
                candidates = by_author.get(
                    (exact_identity.seq_num, exact_identity.insertion_code), []
                )
                mapped_residue = candidates[0] if len(candidates) == 1 else None
            method = "explicit_author_identity"
            explicit_count += 1
        elif sequence_number is not None:
            if alignment_map:
                mapped_residue = alignment_map.get(sequence_number)
                method = (
                    "global_sequence_alignment"
                    if mapped_residue is not None
                    else "global_sequence_alignment_gap"
                )
            else:
                candidates = by_author.get((sequence_number, ""), [])
                mapped_residue = candidates[0] if len(candidates) == 1 else None
                method = "sequence_number_equals_author_number"
            sequence_count += 1
        elif record.get("residue_key"):
            mapped_residue = by_key.get(str(record["residue_key"]))
            method = "exact_residue_key"
            explicit_count += 1

        if mapped_residue is None:
            unmapped += 1
            status = (
                "missing_coordinates"
                if method == "global_sequence_alignment_gap" or exact_identity is not None
                else "unresolved"
            )
            unmapped_rows.append(
                unresolved_row(record, status, "no unambiguous observed structure residue")
            )
            continue
        if amino_acid and mapped_residue.one_letter:
            aa_compared += 1
            aa_matched += int(amino_acid == mapped_residue.one_letter)
        assignment = TopologyAssignment(
            residue=mapped_residue.identity,
            segment=segment,
            generic_number=generic,
            sequence_number=sequence_number,
            amino_acid=amino_acid,
            observed_amino_acid=mapped_residue.one_letter or None,
            mapping_method=method,
            alternative_generic_numbers=tuple(
                dict(value) for value in alternative_numbers if isinstance(value, Mapping)
            ),
        )
        assignments[mapped_residue.identity.key()] = assignment
        methods.add(method)

    aa_fraction = aa_matched / aa_compared if aa_compared else None
    segments = {assignment.segment.upper() for assignment in assignments.values()}
    tm_count = sum(1 for index in range(1, 8) if f"TM{index}" in segments)
    coverage_fraction = len(assignments) / max(1, len(records))
    explicit_reliable = explicit_count > 0 and sequence_count == 0
    explicit_amino_acids_consistent = aa_fraction is None or aa_compared < 5 or aa_fraction >= 0.90
    sequence_reliable = (
        sequence_count > 0
        and aa_compared >= min(20, max(5, len(assignments) // 2))
        and aa_fraction is not None
        and aa_fraction >= 0.90
    )
    mapping_reliable = (
        len(assignments) >= 20
        and coverage_fraction >= 0.50
        and tm_count >= 5
        and (explicit_reliable or sequence_reliable)
        and explicit_amino_acids_consistent
    )
    if not explicit_amino_acids_consistent:
        warnings.append("explicit residue mapping conflicts with supplied amino-acid identities")
    if sequence_count and not sequence_reliable:
        warnings.append(
            "raw GPCRdb sequence numbering was not verified against enough matching "
            "structure residues"
        )
    if tm_count < 5:
        warnings.append("fewer than five TM helices were mapped")
    if coverage_fraction < 0.50:
        warnings.append(
            "less than half of supplied topology annotations mapped to the receptor chain"
        )
    if not mapping_reliable:
        warnings.append("topology mapping is insufficient for membrane-axis derivation")
    return TopologyMap(
        assignments=assignments,
        mapping_reliable=mapping_reliable,
        mapped_count=len(assignments),
        unmapped_count=unmapped,
        amino_acid_match_fraction=aa_fraction,
        methods=sorted(methods),
        warnings=warnings,
        unmapped_residues=unmapped_rows,
    )


def _segment_kind(segment: str | None) -> str:
    value = _normalize_text(segment).upper()
    if TM_PATTERN.match(value):
        return "tm"
    if value.startswith("ECL"):
        return "extracellular_loop"
    if value.startswith("ICL") or value in {"H8", "C-TERM", "C_TERM", "CTERM"}:
        return "intracellular"
    if (
        value in {"N-TERM", "N_TERM", "NTERM", "ECD", "VFT", "CRD", "GAIN", "GPS"}
        or value.startswith(("ECD", "VFT", "CRD", "GAIN", "GPS", "A.", "B."))
        or ".GPS" in value
    ):
        return "extracellular_domain"
    return "other"


def _helix_axis(residues: Sequence[ResidueRecord]) -> Vec3 | None:
    ordered = sorted(residues, key=lambda item: item.identity.sort_key())
    points: list[Vec3] = []
    for residue in ordered:
        ca = residue.atom("CA")
        if ca is not None:
            points.append(ca.coord)
    if len(points) < 4:
        return None
    flank = max(2, min(4, len(points) // 3))
    start = _centroid(points[:flank])
    end = _centroid(points[-flank:])
    if start is None or end is None or _distance(start, end) < 8.0:
        return None
    return _normalize(_sub(end, start))


def _orientation_axis(value: Any) -> tuple[Vec3 | None, str | None, bool]:
    if not isinstance(value, Mapping) or not bool(value.get("reliable", False)):
        return None, None, False
    axis_value = value.get("extracellular_axis", value.get("axis", value.get("normal")))
    source = _normalize_text(value.get("source")) or "explicit membrane orientation"
    if isinstance(axis_value, Sequence) and len(axis_value) == 3:
        try:
            axis = _normalize((float(axis_value[0]), float(axis_value[1]), float(axis_value[2])))
        except (TypeError, ValueError):
            axis = None
        if axis and str(value.get("axis_points_to", "extracellular")).lower().startswith("intra"):
            axis = _scale(axis, -1.0)
        return axis, source, axis is not None
    extracellular = value.get("extracellular_point")
    intracellular = value.get("intracellular_point")
    if (
        isinstance(extracellular, Sequence)
        and isinstance(intracellular, Sequence)
        and len(extracellular) == 3
        and len(intracellular) == 3
    ):
        try:
            ext: Vec3 = (
                float(extracellular[0]),
                float(extracellular[1]),
                float(extracellular[2]),
            )
            inner: Vec3 = (
                float(intracellular[0]),
                float(intracellular[1]),
                float(intracellular[2]),
            )
            axis = _normalize(_sub(ext, inner))
        except (TypeError, ValueError):
            axis = None
        return axis, source, axis is not None
    return None, None, False


def derive_tm_frame(
    structure: ParsedStructure,
    receptor_chain: str,
    topology: TopologyMap,
    membrane_orientation: Any = None,
) -> MembraneFrame:
    """Derive a signed 7TM frame only when topology and direction are reliable."""

    reasons: list[str] = []
    if not topology.mapping_reliable:
        reasons.append("topology mapping is not reliable")

    lookup = structure.residue_lookup()
    helices: dict[int, list[ResidueRecord]] = defaultdict(list)
    extracellular_loops: list[Vec3] = []
    intracellular_loops: list[Vec3] = []
    tm_points: list[Vec3] = []
    for assignment in topology.assignments.values():
        residue = lookup.get(assignment.residue.key())
        if residue is None or residue.identity.chain_id != receptor_chain:
            continue
        point = residue.representative_point()
        match = TM_PATTERN.match(assignment.segment.upper())
        if match:
            helices[int(match.group(1))].append(residue)
            if point:
                tm_points.append(point)
        elif point and _segment_kind(assignment.segment) in {
            "extracellular_loop",
            "extracellular_domain",
        }:
            extracellular_loops.append(point)
        elif point and _segment_kind(assignment.segment) == "intracellular":
            intracellular_loops.append(point)

    outward_axes: list[Vec3] = []
    for helix_index in sorted(helices):
        sequence_axis = _helix_axis(helices[helix_index])
        if sequence_axis is None:
            continue
        # Odd GPCR helices run extracellular->intracellular in sequence; even ones reverse.
        outward_axes.append(_scale(sequence_axis, -1.0 if helix_index % 2 else 1.0))

    helix_count = len(outward_axes)
    if helix_count < 5:
        reasons.append("fewer than five well-resolved TM helix axes")
    consensus = (
        _normalize(
            (
                sum(vector[0] for vector in outward_axes),
                sum(vector[1] for vector in outward_axes),
                sum(vector[2] for vector in outward_axes),
            )
        )
        if outward_axes
        else None
    )
    consistency = (
        sum(max(-1.0, min(1.0, _dot(vector, consensus))) for vector in outward_axes)
        / len(outward_axes)
        if consensus and outward_axes
        else None
    )
    if consistency is None or consistency < 0.70:
        reasons.append("TM helix directions do not form a consistent seven-helix bundle")

    explicit_axis, explicit_source, explicit_reliable = _orientation_axis(membrane_orientation)
    direction_source: str | None = None
    axis = consensus
    if explicit_reliable and explicit_axis:
        if consensus and abs(_dot(explicit_axis, consensus)) < 0.70:
            reasons.append("explicit membrane axis conflicts with TM helix geometry")
        else:
            axis = explicit_axis
            direction_source = explicit_source
    elif consensus:
        direction_source = "GPCR TM parity consensus"

    loop_separation: float | None = None
    if axis and extracellular_loops and intracellular_loops:
        ext_center = _centroid(extracellular_loops)
        int_center = _centroid(intracellular_loops)
        if ext_center and int_center:
            loop_separation = _dot(_sub(ext_center, int_center), axis)
            if loop_separation < 0:
                if explicit_reliable:
                    reasons.append(
                        "explicit direction places annotated extracellular loops intracellular"
                    )
                else:
                    axis = _scale(axis, -1.0)
                    loop_separation = -loop_separation
            if loop_separation < 4.0:
                reasons.append(
                    "extracellular and intracellular annotations do not separate along the axis"
                )
            else:
                direction_source = (
                    f"{direction_source} validated by extracellular/intracellular annotations"
                    if direction_source
                    else "extracellular/intracellular annotation centroids"
                )

    center = _centroid(tm_points)
    if center is None or len(tm_points) < 20:
        reasons.append("too few mapped TM coordinates")
    reliable = not reasons and axis is not None and center is not None and topology.mapping_reliable
    if not reliable:
        return MembraneFrame(
            False,
            None,
            None,
            None,
            None,
            None,
            None,
            direction_source,
            topology.mapping_reliable,
            helix_count,
            consistency,
            loop_separation,
            reasons,
        )

    resolved_axis = cast(Vec3, axis)
    resolved_center = cast(Vec3, center)
    projections = [_dot(_sub(point, resolved_center), resolved_axis) for point in tm_points]
    lower = _quantile(projections, 0.05)
    upper = _quantile(projections, 0.95)
    half_span = max(abs(lower), abs(upper))
    if half_span < 8.0:
        return MembraneFrame(
            False,
            None,
            None,
            None,
            None,
            None,
            None,
            direction_source,
            topology.mapping_reliable,
            helix_count,
            consistency,
            loop_separation,
            ["mapped TM span is too short for a membrane region"],
        )
    return MembraneFrame(
        True,
        resolved_center,
        resolved_axis,
        _scale(resolved_axis, -1.0),
        upper,
        lower,
        half_span,
        direction_source,
        topology.mapping_reliable,
        helix_count,
        consistency,
        loop_separation,
        [],
    )


def _project(point: Vec3, frame: MembraneFrame) -> tuple[float, float]:
    if not frame.reliable or frame.center is None or frame.extracellular_axis is None:
        raise ValueError("a reliable membrane frame is required")
    relative = _sub(point, frame.center)
    axial = _dot(relative, frame.extracellular_axis)
    radial_vector = _sub(relative, _scale(frame.extracellular_axis, axial))
    return axial, _norm(radial_vector)


def derive_residue_regions(
    structure: ParsedStructure,
    receptor_chain: str,
    topology: TopologyMap,
    frame: MembraneFrame,
) -> list[dict[str, Any]]:
    """Classify receptor residues only when a signed membrane frame is reliable."""

    if not frame.reliable or frame.half_span is None:
        return []
    regions: list[dict[str, Any]] = []
    for residue in structure.residues:
        if residue.identity.chain_id != receptor_chain or not residue.is_polymer:
            continue
        assignment = topology.assignment_for(residue)
        if assignment is None:
            continue
        point = residue.sidechain_point()
        ca_point = residue.representative_point()
        if point is None or ca_point is None:
            continue
        axial, radial = _project(point, frame)
        _, ca_radial = _project(ca_point, frame)
        normalized_axial = axial / frame.half_span
        kind = _segment_kind(assignment.segment)
        pore_lining = kind == "tm" and radial <= 15.0 and radial <= ca_radial + 1.0

        if kind == "tm":
            if normalized_axial >= 0.30:
                region = "outer_pore" if pore_lining else "extracellular_tm_surface"
            elif normalized_axial <= -0.30:
                region = "inner_pore" if pore_lining else "intracellular_tm_surface"
            else:
                region = "core_pore" if pore_lining else "tm_core_surface"
        elif kind == "extracellular_loop":
            region = "outer_vestibule" if radial <= 22.0 and axial >= -2.0 else "extracellular_loop"
        elif kind == "extracellular_domain":
            region = "extracellular_domain"
        elif kind == "intracellular":
            region = "intracellular"
        else:
            region = "other"
        regions.append(
            {
                "residue": residue.identity.to_dict(),
                "resname": residue.resname,
                "amino_acid": residue.one_letter,
                "protein_segment": assignment.segment,
                "generic_number": assignment.generic_number,
                "region": region,
                "pore_lining": pore_lining,
                "axial_distance": round(axial, 4),
                "normalized_axial": round(normalized_axial, 4),
                "radial_distance": round(radial, 4),
            }
        )
    return sorted(regions, key=lambda item: _identity_sort_from_dict(item["residue"]))


def _identity_sort_from_dict(value: Mapping[str, Any]) -> tuple[Any, ...]:
    return (
        str(value.get("model_id", "")),
        str(value.get("chain_id", "")),
        int(value.get("auth_seq_id", -(10**12))),
        str(value.get("insertion_code", "")),
        str(value.get("hetero_flag", "")),
    )


def _contact_pairs(
    residues_a: Sequence[ResidueRecord],
    residues_b: Sequence[ResidueRecord],
    *,
    cutoff: float,
    exclude_same_residue: bool = True,
    minimum_sequence_separation: int = 0,
) -> list[dict[str, Any]]:
    if cutoff <= 0:
        raise ValueError("contact cutoff must be positive")
    cell_size = cutoff
    grid: dict[tuple[int, int, int], list[tuple[ResidueRecord, AtomRecord]]] = defaultdict(list)
    for residue in residues_b:
        for atom in residue.selected_atoms(heavy_only=True):
            cell = (
                int(math.floor(atom.coord[0] / cell_size)),
                int(math.floor(atom.coord[1] / cell_size)),
                int(math.floor(atom.coord[2] / cell_size)),
            )
            grid[cell].append((residue, atom))

    pairs: dict[tuple[str, str], dict[str, Any]] = {}
    cutoff_sq = cutoff * cutoff
    for residue_a in residues_a:
        for atom_a in residue_a.selected_atoms(heavy_only=True):
            base = (
                int(math.floor(atom_a.coord[0] / cell_size)),
                int(math.floor(atom_a.coord[1] / cell_size)),
                int(math.floor(atom_a.coord[2] / cell_size)),
            )
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    for dz in (-1, 0, 1):
                        for residue_b, atom_b in grid.get(
                            (base[0] + dx, base[1] + dy, base[2] + dz), []
                        ):
                            if (
                                exclude_same_residue
                                and residue_a.identity.key() == residue_b.identity.key()
                            ):
                                continue
                            if (
                                minimum_sequence_separation
                                and residue_a.identity.chain_id == residue_b.identity.chain_id
                                and abs(residue_a.identity.seq_num - residue_b.identity.seq_num)
                                < minimum_sequence_separation
                            ):
                                continue
                            delta = _sub(atom_a.coord, atom_b.coord)
                            distance_sq = _dot(delta, delta)
                            if distance_sq > cutoff_sq:
                                continue
                            key = (residue_a.identity.key(), residue_b.identity.key())
                            item = pairs.setdefault(
                                key,
                                {
                                    "residue_a": residue_a.identity.to_dict(),
                                    "resname_a": residue_a.resname,
                                    "residue_b": residue_b.identity.to_dict(),
                                    "resname_b": residue_b.resname,
                                    "minimum_distance": float("inf"),
                                    "atom_contact_count": 0,
                                },
                            )
                            item["minimum_distance"] = min(
                                item["minimum_distance"], math.sqrt(distance_sq)
                            )
                            item["atom_contact_count"] += 1
    output = list(pairs.values())
    for item in output:
        item["minimum_distance"] = round(item["minimum_distance"], 4)
    return sorted(
        output,
        key=lambda item: (
            _identity_sort_from_dict(item["residue_a"]),
            _identity_sort_from_dict(item["residue_b"]),
        ),
    )


def build_chain_graph(
    structure: ParsedStructure,
    receptor_chain: str,
    *,
    receptor_like_chains: Sequence[str] = (),
    gprotein_chains: Sequence[str] = (),
    contact_cutoff: float = 5.0,
) -> dict[str, Any]:
    """Build actual inter-chain contacts; labels never rely on family alone."""

    polymer_by_chain: dict[str, list[ResidueRecord]] = defaultdict(list)
    for residue in structure.residues:
        if residue.is_polymer:
            polymer_by_chain[residue.identity.chain_id].append(residue)
    receptor_like = {_normalize_text(chain) for chain in receptor_like_chains}
    receptor_like.add(receptor_chain)
    gproteins = {_normalize_text(chain) for chain in gprotein_chains}

    chains = [
        {
            "chain_id": chain,
            "polymer_residue_count": len(polymer_by_chain[chain]),
            "role": (
                "receptor"
                if chain == receptor_chain
                else "gprotein"
                if chain in gproteins
                else "receptor_like"
                if chain in receptor_like
                else "other_protein"
            ),
        }
        for chain in sorted(polymer_by_chain)
    ]
    edges: list[dict[str, Any]] = []
    chain_ids = sorted(polymer_by_chain)
    for index, chain_a in enumerate(chain_ids):
        for chain_b in chain_ids[index + 1 :]:
            contacts = _contact_pairs(
                polymer_by_chain[chain_a], polymer_by_chain[chain_b], cutoff=contact_cutoff
            )
            if not contacts:
                continue
            residues_a = {item["residue_a"]["key"] for item in contacts}
            residues_b = {item["residue_b"]["key"] for item in contacts}
            if chain_a in gproteins or chain_b in gproteins:
                interface_type = "gprotein"
            elif chain_a in receptor_like and chain_b in receptor_like:
                interface_type = "gpcr_dimer"
            else:
                interface_type = "other_protein"
            observed = len(contacts) >= 3 and min(len(residues_a), len(residues_b)) >= 2
            edges.append(
                {
                    "chain_a": chain_a,
                    "chain_b": chain_b,
                    "interface_type": interface_type,
                    "geometry_observed": observed,
                    "residue_pair_count": len(contacts),
                    "residue_count_a": len(residues_a),
                    "residue_count_b": len(residues_b),
                    "minimum_distance": min(item["minimum_distance"] for item in contacts),
                    "contacts": contacts,
                    "evidence": "heavy-atom contacts from supplied coordinates",
                }
            )
    edges.sort(key=lambda item: (item["chain_a"], item["chain_b"], item["interface_type"]))
    return {"chains": chains, "edges": edges, "contact_cutoff": contact_cutoff}


def detect_self_occlusion(
    structure: ParsedStructure,
    receptor_chain: str,
    topology: TopologyMap,
    residue_regions: Sequence[Mapping[str, Any]],
    *,
    contact_cutoff: float = 5.0,
) -> dict[str, Any]:
    """Detect an ECD-to-7TM mouth interface from coordinates, never family alone."""

    lookup = structure.residue_lookup()
    ecd: list[ResidueRecord] = []
    mouth: list[ResidueRecord] = []
    region_by_key = {str(item.get("residue", {}).get("key")): item for item in residue_regions}
    for assignment in topology.assignments.values():
        residue = lookup.get(assignment.residue.key())
        if residue is None or residue.identity.chain_id != receptor_chain:
            continue
        kind = _segment_kind(assignment.segment)
        region = region_by_key.get(residue.identity.key(), {}).get("region")
        if kind == "extracellular_domain":
            ecd.append(residue)
        elif kind == "extracellular_loop" or region in {"outer_vestibule", "outer_pore"}:
            mouth.append(residue)
    if not ecd or not mouth:
        return {
            "observed": False,
            "reason": "both mapped extracellular-domain and 7TM-mouth residues are required",
            "ecd_total_residue_count": len(ecd),
            "large_ecd_supported": False,
            "large_ecd_minimum_residues": LARGE_ECD_MINIMUM_RESIDUES,
            "contacts": [],
            "contact_cutoff": contact_cutoff,
        }
    contacts = _contact_pairs(
        ecd,
        mouth,
        cutoff=contact_cutoff,
        minimum_sequence_separation=10,
    )
    ecd_keys = {item["residue_a"]["key"] for item in contacts}
    mouth_keys = {item["residue_b"]["key"] for item in contacts}
    large_ecd_supported = len(ecd) >= LARGE_ECD_MINIMUM_RESIDUES
    observed = (
        large_ecd_supported and len(contacts) >= 3 and len(ecd_keys) >= 2 and len(mouth_keys) >= 2
    )
    return {
        "observed": observed,
        "reason": (
            "coordinate-derived ECD-to-7TM-mouth contact interface"
            if observed
            else (
                "the resolved extracellular domain is too small for a large-ECD "
                "self-occlusion claim"
            )
            if not large_ecd_supported
            else "contact geometry did not meet the self-occlusion evidence threshold"
        ),
        "ecd_total_residue_count": len(ecd),
        "large_ecd_supported": large_ecd_supported,
        "large_ecd_minimum_residues": LARGE_ECD_MINIMUM_RESIDUES,
        "residue_pair_count": len(contacts),
        "ecd_residue_count": len(ecd_keys),
        "mouth_residue_count": len(mouth_keys),
        "contacts": contacts,
        "contact_cutoff": contact_cutoff,
    }


def analyze_structure(
    path: str | Path,
    receptor_chain: str,
    gpcr_residues: Any = None,
    membrane_orientation: Any = None,
) -> dict[str, Any]:
    """Parse and conservatively analyze one GPCR structure.

    ``membrane_orientation`` may include a reliable signed axis plus optional
    ``receptor_like_chains`` and ``gprotein_chains``. The latter roles affect only
    contact labels; a G-protein contact is never emitted as a GPCR dimer.
    """

    receptor_chain = _normalize_text(receptor_chain)
    if receptor_chain is None:
        receptor_chain = ""
    parsed = parse_structure(path)
    warnings = list(parsed.parser_warnings)
    polymer_chains = parsed.chain_ids(polymer_only=True)
    if receptor_chain not in polymer_chains:
        raise StructureAnalysisError(
            f"receptor chain {receptor_chain!r} is absent; polymer chains are {polymer_chains}"
        )

    topology = map_gpcr_topology(parsed, receptor_chain, gpcr_residues)
    warnings.extend(topology.warnings)
    membrane = derive_tm_frame(parsed, receptor_chain, topology, membrane_orientation)
    warnings.extend(membrane.reasons)
    residue_regions = derive_residue_regions(parsed, receptor_chain, topology, membrane)
    if not membrane.reliable:
        warnings.append("axis-derived pore/core/outer regions were not emitted")

    orientation = membrane_orientation if isinstance(membrane_orientation, Mapping) else {}
    receptor_like_chains = orientation.get("receptor_like_chains") or []
    gprotein_chains = orientation.get("gprotein_chains") or []
    chain_graph = build_chain_graph(
        parsed,
        receptor_chain,
        receptor_like_chains=receptor_like_chains,
        gprotein_chains=gprotein_chains,
    )
    self_occlusion = detect_self_occlusion(parsed, receptor_chain, topology, residue_regions)
    chain_graph["self_occlusion"] = self_occlusion

    dimer_edges = [
        edge
        for edge in chain_graph["edges"]
        if edge["interface_type"] == "gpcr_dimer" and edge["geometry_observed"]
    ]
    gprotein_edges = [edge for edge in chain_graph["edges"] if edge["interface_type"] == "gprotein"]
    avoid: list[dict[str, Any]] = []
    if gprotein_edges:
        avoid.append(
            {
                "id": "avoid-gprotein-as-dimer",
                "classification": "avoid",
                "scope": "interface",
                "role": "intracellular-transducer-interface",
                "residues": [],
                "reason": (
                    "G-protein interfaces are effector contacts and must never be "
                    "classified as GPCR dimers"
                ),
                "source_ids": ["evidence-gprotein-interface-role"],
                "interfaces": [
                    {"chain_a": edge["chain_a"], "chain_b": edge["chain_b"]}
                    for edge in gprotein_edges
                ],
            }
        )

    chain_summaries = []
    for chain in parsed.chain_ids():
        residues = [item for item in parsed.residues if item.identity.chain_id == chain]
        chain_summaries.append(
            {
                "chain_id": chain,
                "residue_count": len(residues),
                "polymer_residue_count": sum(item.is_polymer for item in residues),
                "first_residue": residues[0].identity.to_dict() if residues else None,
                "last_residue": residues[-1].identity.to_dict() if residues else None,
            }
        )

    evidence: list[dict[str, Any]] = []
    if topology.mapping_reliable:
        evidence.append(
            {
                "id": "evidence-topology-mapping",
                "tier": "T2",
                "type": "topology_mapping",
                "detail": (
                    "GPCR residue topology mapped and identity-checked against structure "
                    "coordinates"
                ),
            }
        )
    if membrane.reliable:
        evidence.append(
            {
                "id": "evidence-membrane-frame",
                "tier": "T2",
                "type": "membrane_frame",
                "detail": "signed membrane frame derived from at least five consistent TM helices",
            }
        )
    if dimer_edges:
        evidence.append(
            {
                "id": "evidence-dimer-geometry",
                "tier": "T2",
                "type": "gpcr_dimer_geometry",
                "detail": "receptor-like chains form a coordinate-derived heavy-atom interface",
            }
        )
    if gprotein_edges:
        evidence.append(
            {
                "id": "evidence-gprotein-interface-role",
                "tier": "T2",
                "type": "gprotein_interface_role",
                "detail": "explicit G-protein chain roles prevent receptor-dimer misclassification",
            }
        )
    if self_occlusion["observed"]:
        evidence.append(
            {
                "id": "evidence-self-occlusion-geometry",
                "tier": "T2",
                "type": "self_occlusion_geometry",
                "detail": "mapped ECD residues contact the extracellular 7TM mouth",
            }
        )

    generated_at = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    analysis_id = f"{parsed.path.stem}-{receptor_chain or 'blank'}-{parsed.sha256[:12]}"
    return {
        "schema_version": ANALYSIS_SCHEMA,
        "analysis_id": analysis_id,
        "generated_at": generated_at,
        "mode": "both",
        "structure": {
            "path": str(parsed.path),
            "id": parsed.path.stem,
            "sha256": parsed.sha256,
            "format": parsed.file_format,
            "parser": parsed.parser,
            "model_id": parsed.model_id,
            "receptor_chain": receptor_chain,
        },
        "identity": {
            "receptor_chain": receptor_chain,
            "status": "partial" if topology.mapped_count else "unresolved",
            "chains": chain_summaries,
            "exact_residue_identity": "model_id+auth_chain+auth_seq_id+insertion_code+hetero_flag",
        },
        "topology": topology.to_dict(),
        "state": {
            "assignment": None,
            "target": None,
            "counterstate": None,
            "confidence": "unresolved",
            "evidence_ids": [],
            "source": None,
            "note": (
                "structural state is supplied by receptor context, not inferred from "
                "ligand function"
            ),
        },
        "membrane": membrane.to_dict(),
        "residue_regions": residue_regions,
        "chain_graph": chain_graph,
        "candidates": {"inhibit": [], "activate": []},
        "avoid": avoid,
        "evidence": evidence,
        "warnings": sorted(set(warnings)),
        "provenance": {
            "tool": "gpcr-hotspot-selection.structure-analysis",
            "local_structure": {
                "source": "local_structure",
                "path": str(parsed.path),
                "sha256": parsed.sha256,
                "parser": parsed.parser,
            },
        },
    }


load_structure = parse_structure
analyze_gpcr_structure = analyze_structure
derive_membrane_axis = derive_tm_frame
detect_self_occlusion_geometry = detect_self_occlusion


__all__ = [
    "ANALYSIS_SCHEMA",
    "AtomRecord",
    "LARGE_ECD_MINIMUM_RESIDUES",
    "MembraneFrame",
    "ParsedStructure",
    "ResidueIdentity",
    "ResidueRecord",
    "StructureAnalysisError",
    "TopologyAssignment",
    "TopologyMap",
    "analyze_gpcr_structure",
    "analyze_structure",
    "build_chain_graph",
    "derive_membrane_axis",
    "derive_residue_regions",
    "derive_tm_frame",
    "detect_self_occlusion",
    "detect_self_occlusion_geometry",
    "load_structure",
    "map_gpcr_topology",
    "parse_structure",
]
