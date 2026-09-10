"""本地/远程实验结构的严格 inventory、scope 提取和 chain A 规范化。"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import gemmi

from easydesign.core import (
    ArtifactRef,
    DesignResidueMapping,
    ManifestStateError,
    TargetInputError,
    dump_model,
)
from easydesign.stages.s01_target_preparation.models import (
    BuiltTargetBundle,
    CoordinateEnsemble,
    ResidueMapping,
    ResidueMappingEntry,
    TargetBundle,
    TargetStructureOrigin,
)

from .sequence import NormalizedProteinSequence, normalize_raw_sequence

THREE_TO_ONE = {
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
ONE_TO_THREE = {one: three for three, one in THREE_TO_ONE.items()}


@dataclass(frozen=True, slots=True)
class ChainInventory:
    author_chain_id: str
    label_chain_id: str
    residue_count: int
    canonical_residue_count: int
    sequence: str
    deposited_sequence: str | None
    coordinate_label_seq_ids: tuple[int, ...]
    ca_label_seq_ids: tuple[int, ...]
    model_ids: tuple[str, ...]
    ligand_names: tuple[str, ...]
    water_count: int
    altloc_atom_count: int


@dataclass(frozen=True, slots=True)
class StructureInventory:
    model_ids: tuple[str, ...]
    chains: tuple[ChainInventory, ...]
    protein_chain_ids: tuple[str, ...]
    ligand_names: tuple[str, ...]
    water_count: int


@dataclass(frozen=True, slots=True)
class StructureNormalizationResult:
    built_bundle: BuiltTargetBundle
    target_pdb: Path | None
    residue_mapping_tsv: Path
    output_artifacts: tuple[ArtifactRef, ...]


@dataclass(frozen=True, slots=True)
class _ResolvedScope:
    sequence: str
    source_label_seq_start: int | None
    observed_start_index: int | None


@dataclass(frozen=True, slots=True)
class ScopeCoordinateEvidence:
    sequence_identity: float
    coordinate_coverage: float
    observed_residue_count: int
    missing_coordinate_ranges: tuple[dict[str, Any], ...]


def _exclusive_text(text: str, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
    except FileExistsError as error:
        raise ManifestStateError(f"Stage 01 artifact 已存在，禁止覆盖: {path}") from error
    return path


def _exclusive_copy(source: Path, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with source.open("rb") as input_handle, path.open("xb") as output_handle:
            shutil.copyfileobj(input_handle, output_handle)
    except FileExistsError as error:
        raise ManifestStateError(f"Stage 01 artifact 已存在，禁止覆盖: {path}") from error
    return path


def _artifact(
    *,
    run_root: Path,
    path: Path,
    artifact_id: str,
    role: str,
    file_format: str,
    attempt_id: str,
) -> ArtifactRef:
    return ArtifactRef.from_file(
        run_root=run_root,
        relative_path=path.relative_to(run_root).as_posix(),
        artifact_id=artifact_id,
        role=role,
        file_format=file_format,
        producer_stage="01-target-preparation",
        producer_attempt=attempt_id,
    )


def read_structure(path: Path) -> gemmi.Structure:
    try:
        structure = gemmi.read_structure(str(path))
    except Exception as error:
        raise TargetInputError(f"无法解析结构文件: {path}") from error
    if len(structure) < 1:
        raise TargetInputError("结构文件不包含 coordinate model")
    return structure


def inventory_structure(path: Path) -> StructureInventory:
    structure = read_structure(path)
    model_ids = tuple(str(model.num) for model in structure)
    first = structure[0]
    chains: list[ChainInventory] = []
    all_ligands: set[str] = set()
    total_waters = 0
    for chain in first:
        sequence: list[str] = []
        coordinate_label_seq_ids: list[int] = []
        ca_label_seq_ids: list[int] = []
        ligands: set[str] = set()
        waters = 0
        altloc = 0
        label_chain_ids: set[str] = set()
        for residue in chain:
            if residue.name in THREE_TO_ONE:
                sequence.append(THREE_TO_ONE[residue.name])
                if residue.label_seq is not None:
                    label_seq_id = int(residue.label_seq)
                    coordinate_label_seq_ids.append(label_seq_id)
                    if any(atom.name.strip() == "CA" for atom in residue):
                        ca_label_seq_ids.append(label_seq_id)
                if residue.subchain:
                    label_chain_ids.add(residue.subchain)
            elif residue.is_water():
                waters += 1
            else:
                ligands.add(residue.name)
            altloc += sum(1 for atom in residue if atom.altloc not in {"\x00", " ", ""})
        all_ligands.update(ligands)
        total_waters += waters
        deposited_sequence: str | None = None
        try:
            polymer = chain.get_polymer()
            entity = structure.get_entity_of(polymer) if len(polymer) > 0 else None
        except (AttributeError, RuntimeError):
            entity = None
        if entity is not None and entity.full_sequence:
            try:
                deposited_sequence = "".join(
                    THREE_TO_ONE[residue_name]
                    for residue_name in entity.full_sequence
                )
            except KeyError:
                deposited_sequence = None
        chains.append(
            ChainInventory(
                author_chain_id=chain.name,
                label_chain_id=(
                    next(iter(label_chain_ids))
                    if len(label_chain_ids) == 1
                    else chain.name
                ),
                residue_count=len(chain),
                canonical_residue_count=len(sequence),
                sequence="".join(sequence),
                deposited_sequence=deposited_sequence,
                coordinate_label_seq_ids=tuple(coordinate_label_seq_ids),
                ca_label_seq_ids=tuple(ca_label_seq_ids),
                model_ids=model_ids,
                ligand_names=tuple(sorted(ligands)),
                water_count=waters,
                altloc_atom_count=altloc,
            )
        )
    protein = tuple(
        item.author_chain_id for item in chains if item.canonical_residue_count > 0
    )
    return StructureInventory(
        model_ids=model_ids,
        chains=tuple(chains),
        protein_chain_ids=protein,
        ligand_names=tuple(sorted(all_ligands)),
        water_count=total_waters,
    )


def choose_chain(
    inventory: StructureInventory,
    *,
    explicit_chain: str | None,
    expected_sequence: str | None,
    chain_namespace: str = "auth",
) -> str:
    if explicit_chain is not None:
        if chain_namespace not in {"auth", "label"}:
            raise TargetInputError(f"未知 chain namespace: {chain_namespace}")
        matches = tuple(
            item.author_chain_id
            for item in inventory.chains
            if item.canonical_residue_count > 0
            and (
                item.author_chain_id
                if chain_namespace == "auth"
                else item.label_chain_id
            )
            == explicit_chain
        )
        if len(matches) != 1:
            raise TargetInputError(
                f"显式 {chain_namespace} chain={explicit_chain} "
                "无法唯一映射到 protein chain"
            )
        return matches[0]
    if len(inventory.protein_chain_ids) == 1:
        return inventory.protein_chain_ids[0]
    if expected_sequence is not None:
        matches = tuple(
            chain.author_chain_id
            for chain in inventory.chains
            if expected_sequence in (chain.deposited_sequence or chain.sequence)
        )
        if len(matches) == 1:
            return matches[0]
    raise TargetInputError(
        "structure-chain-ambiguous: 多条 protein chain 无法唯一选择；"
        f"candidates={inventory.protein_chain_ids}"
    )


def _canonical_residues(chain: gemmi.Chain) -> list[gemmi.Residue]:
    return [residue for residue in chain if residue.name in THREE_TO_ONE]


def _select_residue_altlocs(residue: gemmi.Residue) -> None:
    """每个 atom name 选择最高 occupancy；并列时按空白、A、B…确定性选择。"""

    # gemmi atom wrappers can be invalidated when a preceding atom is removed.
    # Keep only stable names across mutations, and rebuild each atom group from
    # the current residue immediately before selecting/removing its altlocs.
    atom_names = tuple(dict.fromkeys(atom.name for atom in residue))
    for name in atom_names:
        atoms = [atom for atom in residue if atom.name == name]
        if len(atoms) == 1:
            atoms[0].altloc = "\x00"
            continue
        selected = min(
            atoms,
            key=lambda atom: (
                -float(atom.occ),
                "" if atom.altloc in {"\x00", " ", ""} else atom.altloc,
                atom.element.name,
            ),
        )
        selected_altloc = selected.altloc
        selected_element = selected.element
        for atom in atoms:
            if atom is selected:
                continue
            residue.remove_atom(name, atom.altloc, atom.element)
        kept = residue.find_atom(name, selected_altloc, selected_element)
        if kept is None:
            raise TargetInputError(
                f"altloc 选择后无法定位保留原子: residue={residue.seqid}, atom={name}"
            )
        kept.altloc = "\x00"


def _model_chain(model: gemmi.Model, chain_id: str) -> gemmi.Chain:
    matches = [chain for chain in model if chain.name == chain_id]
    if len(matches) != 1:
        raise TargetInputError(
            f"每个 coordinate model 必须恰好含一个 source chain={chain_id}"
        )
    return matches[0]


def _resolve_scope(
    chain: ChainInventory,
    expected: str | None,
) -> _ResolvedScope:
    if expected is None:
        if chain.deposited_sequence is not None:
            return _ResolvedScope(
                sequence=chain.deposited_sequence,
                source_label_seq_start=1,
                observed_start_index=None,
            )
        return _ResolvedScope(
            sequence=chain.sequence,
            source_label_seq_start=None,
            observed_start_index=0,
        )
    if chain.deposited_sequence is not None:
        deposited_start = chain.deposited_sequence.find(expected)
        if deposited_start >= 0:
            return _ResolvedScope(
                sequence=expected,
                source_label_seq_start=deposited_start + 1,
                observed_start_index=None,
            )
    start = chain.sequence.find(expected)
    if start < 0:
        raise TargetInputError(
            "experimental-sequence-mismatch: design scope 必须与 deposited polymer "
            "sequence 形成 100% identity 映射；坐标缺失本身不属于序列不一致；"
            f"expected_length={len(expected)}, observed_length={len(chain.sequence)}, "
            "deposited_length="
            f"{None if chain.deposited_sequence is None else len(chain.deposited_sequence)}"
        )
    return _ResolvedScope(
        sequence=expected,
        source_label_seq_start=None,
        observed_start_index=start,
    )


def _missing_coordinate_ranges(
    present_label_seq_ids: set[int],
    sequence_length: int,
) -> tuple[dict[str, Any], ...]:
    ranges: list[dict[str, Any]] = []
    range_start: int | None = None
    for label_seq_id in range(1, sequence_length + 2):
        missing = (
            label_seq_id <= sequence_length
            and label_seq_id not in present_label_seq_ids
        )
        if missing and range_start is None:
            range_start = label_seq_id
        if not missing and range_start is not None:
            range_end = label_seq_id - 1
            ranges.append(
                {
                    "start": range_start,
                    "end": range_end,
                    "kind": (
                        "terminal"
                        if range_start == 1 or range_end == sequence_length
                        else "internal"
                    ),
                }
            )
            range_start = None
    return tuple(ranges)


def scope_coordinate_evidence(
    chain: ChainInventory,
    expected_sequence: str,
) -> ScopeCoordinateEvidence:
    """Separately establish polymer identity and representative-coordinate coverage."""

    scope = _resolve_scope(chain, expected_sequence)
    if scope.source_label_seq_start is None:
        present = set(range(1, len(scope.sequence) + 1))
    else:
        source_start = scope.source_label_seq_start
        source_end = source_start + len(scope.sequence) - 1
        present = {
            source_label - source_start + 1
            for source_label in chain.ca_label_seq_ids
            if source_start <= source_label <= source_end
        }
    return ScopeCoordinateEvidence(
        sequence_identity=1.0,
        coordinate_coverage=len(present) / len(scope.sequence),
        observed_residue_count=len(present),
        missing_coordinate_ranges=_missing_coordinate_ranges(
            present,
            len(scope.sequence),
        ),
    )


def _clone_scoped_structure(
    source: gemmi.Structure,
    *,
    source_chain_id: str,
    scope: _ResolvedScope,
) -> gemmi.Structure:
    result = gemmi.Structure()
    result.name = source.name or "easydesign_target"
    result.cell = source.cell
    result.spacegroup_hm = source.spacegroup_hm
    scope_keys: tuple[tuple[int | None, str, str], ...] | None = None
    if scope.source_label_seq_start is None:
        assert scope.observed_start_index is not None
        representative_chain = _model_chain(source[0], source_chain_id)
        representative_residues = _canonical_residues(representative_chain)
        end_index = scope.observed_start_index + len(scope.sequence)
        if len(representative_residues) < end_index:
            raise TargetInputError(
                "experimental-scope-missing: representative model 缺少 design scope residue"
            )
        scope_residues = representative_residues[
            scope.observed_start_index : end_index
        ]
        scope_keys = tuple(
            (residue.seqid.num, residue.seqid.icode, residue.name)
            for residue in scope_residues
        )
    for model in source:
        source_chain = _model_chain(model, source_chain_id)
        residues = _canonical_residues(source_chain)
        selected: list[tuple[int, gemmi.Residue]] = []
        if scope.source_label_seq_start is not None:
            source_start = scope.source_label_seq_start
            source_end = source_start + len(scope.sequence) - 1
            seen_labels: set[int] = set()
            for residue in residues:
                if residue.label_seq is None:
                    continue
                source_label = int(residue.label_seq)
                if source_label < source_start or source_label > source_end:
                    continue
                target_label = source_label - source_start + 1
                if target_label in seen_labels:
                    raise TargetInputError(
                        "experimental-label-seq-duplicate: "
                        f"model={model.num}, label_seq_id={source_label}"
                    )
                seen_labels.add(target_label)
                expected_name = ONE_TO_THREE[scope.sequence[target_label - 1]]
                if residue.name != expected_name:
                    raise TargetInputError(
                        "experimental-coordinate-identity-mismatch: "
                        f"model={model.num}, source_label_seq_id={source_label}, "
                        f"expected={expected_name}, observed={residue.name}"
                    )
                selected.append((target_label, residue))
        else:
            assert scope_keys is not None
            by_key = {
                (residue.seqid.num, residue.seqid.icode, residue.name): residue
                for residue in residues
            }
            for target_label, key in enumerate(scope_keys, start=1):
                mapped_residue = by_key.get(key)
                if mapped_residue is not None:
                    selected.append((target_label, mapped_residue))
        output_model = gemmi.Model(model.num)
        output_chain = gemmi.Chain("A")
        for label_seq_id, residue in sorted(selected, key=lambda item: item[0]):
            if not any(atom.name.strip() == "CA" for atom in residue):
                continue
            cloned = residue.clone()
            _select_residue_altlocs(cloned)
            # gemmi may synthesize a label subchain such as ``Axp`` for PDB
            # input when entities are rebuilt. The Stage 01 contract requires
            # both coordinate label/auth chain identity to be canonical ``A``.
            cloned.subchain = "A"
            cloned.label_seq = label_seq_id
            output_chain.add_residue(cloned)
        output_model.add_chain(output_chain)
        result.add_model(output_model)
    if len(result[0][0]) == 0:
        raise TargetInputError(
            "experimental-scope-no-coordinate-anchor: representative model 在 design scope "
            "内没有带 CA 的残基"
        )
    result.setup_entities()
    if result.entities:
        result.entities[0].full_sequence = [ONE_TO_THREE[aa] for aa in scope.sequence]
    result.assign_label_seq_id()
    return result


def _write_cif(structure: gemmi.Structure, path: Path) -> Path:
    try:
        content = structure.make_mmcif_document().as_string()
    except Exception as error:
        raise TargetInputError("结构无法序列化为规范 mmCIF") from error
    return _exclusive_text(content, path)


def _write_source_context(source: Path, structure: gemmi.Structure, path: Path) -> Path:
    if source.suffix.lower() in {".cif", ".mmcif"}:
        return _exclusive_copy(source, path)
    return _write_cif(structure, path)


def _write_design_context(
    source: gemmi.Structure,
    scoped: gemmi.Structure,
    *,
    keep_ligands: tuple[str, ...],
    path: Path,
) -> Path | None:
    if not keep_ligands:
        return None
    allowed = {name.upper() for name in keep_ligands}
    result = scoped.clone()
    found: set[str] = set()
    for model_index, source_model in enumerate(source):
        ligand_chain = gemmi.Chain("L")
        for chain in source_model:
            for residue in chain:
                if residue.is_water() or residue.name in THREE_TO_ONE:
                    continue
                if residue.name.upper() not in allowed:
                    continue
                ligand_chain.add_residue(residue.clone())
                found.add(residue.name.upper())
        if len(ligand_chain) > 0:
            result[model_index].add_chain(ligand_chain)
    missing = sorted(allowed - found)
    if missing:
        raise TargetInputError(
            f"keep_ligands 在 source context 中不存在: {missing}"
        )
    result.setup_entities()
    return _write_cif(result, path)


def _mapping(
    *,
    target_id: str,
    sequence: NormalizedProteinSequence,
    scoped: gemmi.Structure,
    source_chain_id: str,
    source_label_chain_id: str,
    reference_start: int | None,
    identity_mapping: tuple[DesignResidueMapping, ...] | None = None,
) -> ResidueMapping:
    entries: list[ResidueMappingEntry] = []
    model_presence: dict[int, tuple[str, ...]] = {}
    residue_by_label: dict[int, gemmi.Residue] = {}
    for index in range(1, sequence.length + 1):
        present = []
        for model in scoped:
            residue = next(
                (
                    item
                    for item in model[0]
                    if item.label_seq == index
                ),
                None,
            )
            if residue is not None:
                present.append(str(model.num))
                residue_by_label.setdefault(index, residue)
        model_presence[index] = tuple(present)
    for index, amino_acid in enumerate(sequence.sequence, start=1):
        identity = (
            None
            if identity_mapping is None or index > len(identity_mapping)
            else identity_mapping[index - 1]
        )
        residue = residue_by_label.get(index)
        original = residue.seqid if residue is not None else None
        entries.append(
            ResidueMappingEntry(
                sequence_index=index,
                amino_acid=amino_acid,
                label_chain_id="A",
                label_seq_id=index,
                author_chain_id="A",
                author_residue_id=(
                    str(index) if original is None else str(original.num)
                ),
                source_label_chain_id=source_label_chain_id,
                source_author_chain_id=(
                    None if original is None else source_chain_id
                ),
                source_author_residue_id=(
                    None if original is None else str(original.num)
                ),
                insertion_code=(
                    None
                    if original is None
                    or original.icode in {"\x00", " ", ""}
                    else original.icode
                ),
                reference_position=(
                    identity.canonical_position
                    if identity is not None
                    else None if reference_start is None else reference_start + index - 1
                ),
                coordinate_present=bool(model_presence[index]),
                model_presence=model_presence[index],
                source_residue_name=(
                    ONE_TO_THREE[amino_acid]
                    if residue is None
                    else residue.name
                ),
                canonical_position=(None if identity is None else identity.canonical_position),
                canonical_residue=(None if identity is None else identity.canonical_residue),
                construct_position=(index if identity is None else identity.construct_position),
                construct_residue=(amino_acid if identity is None else identity.construct_residue),
                mapping_status=(None if identity is None else identity.mapping_status.value),
                edit_type=(None if identity is None else identity.edit_type.value),
            )
        )
    return ResidueMapping(
        schema_version="0.4" if identity_mapping is not None else "0.3",
        target_id=target_id,
        sequence_sha256=sequence.sequence_sha256,
        entries=tuple(entries),
    )


def _mapping_tsv(mapping: ResidueMapping) -> str:
    header = (
        "sequence_index\tamino_acid\tcanonical_position\tcanonical_residue\t"
        "construct_position\tconstruct_residue\tlabel_chain_id\tlabel_seq_id\t"
        "source_auth_chain\tsource_auth_residue\tinsertion_code\t"
        "reference_position\tcoordinate_present\tmapping_status\tedit_type\tmodel_presence\n"
    )
    rows = []
    for entry in mapping.entries:
        rows.append(
            "\t".join(
                (
                    str(entry.sequence_index),
                    entry.amino_acid,
                    "" if entry.canonical_position is None else str(entry.canonical_position),
                    entry.canonical_residue or "",
                    "" if entry.construct_position is None else str(entry.construct_position),
                    entry.construct_residue or "",
                    entry.label_chain_id,
                    str(entry.label_seq_id),
                    entry.source_author_chain_id or "",
                    entry.source_author_residue_id or "",
                    entry.insertion_code or "",
                    (
                        ""
                        if entry.reference_position is None
                        else str(entry.reference_position)
                    ),
                    str(entry.coordinate_present).lower(),
                    entry.mapping_status or "",
                    entry.edit_type or "",
                    ",".join(entry.model_presence),
                )
            )
        )
    return header + "\n".join(rows) + "\n"


def _json(payload: dict[str, Any] | list[Any], path: Path) -> Path:
    return _exclusive_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        path,
    )


def build_experimental_target_bundle(
    *,
    run_root: Path,
    attempt_id: str,
    target_id: str,
    source_path: Path,
    source_format: str,
    selected_chain: str,
    expected_scope_sequence: str | None,
    reference_sequence: str | None,
    reference_start: int | None,
    identity_report: dict[str, Any],
    scope_report: dict[str, Any],
    candidates: list[dict[str, Any]],
    quality_report: dict[str, Any],
    provenance: dict[str, Any],
    retrieval_records: list[dict[str, Any]],
    preserve_source_context: bool,
    keep_ligands: tuple[str, ...] = (),
    identity_mapping: tuple[DesignResidueMapping, ...] | None = None,
) -> StructureNormalizationResult:
    """发布 protein-only chain A Target Bundle 0.4 和完整 evidence 投影。"""

    root = run_root.resolve()
    artifact_dir = root / "01-target-preparation" / attempt_id / "artifacts"
    source = read_structure(source_path)
    inventory = inventory_structure(source_path)
    chain_info = next(
        chain for chain in inventory.chains if chain.author_chain_id == selected_chain
    )
    scope = _resolve_scope(chain_info, expected_scope_sequence)
    scoped = _clone_scoped_structure(
        source,
        source_chain_id=selected_chain,
        scope=scope,
    )
    normalized = normalize_raw_sequence(
        scope.sequence,
        target_id=target_id,
        source_label=source_path.name,
    )
    target_cif = _write_cif(scoped, artifact_dir / "target.cif")
    target_pdb: Path | None = artifact_dir / "target.pdb"
    try:
        scoped.write_pdb(str(target_pdb))
    except Exception:
        target_pdb = None
    sequence_path = _exclusive_text(
        normalized.to_fasta(),
        artifact_dir / "sequence.fasta",
    )
    reference_path: Path | None = None
    if reference_sequence is not None:
        reference = normalize_raw_sequence(
            reference_sequence,
            target_id=f"{target_id}-reference",
            source_label="reference",
        )
        reference_path = _exclusive_text(
            reference.to_fasta(),
            artifact_dir / "reference-sequence.fasta",
        )
    mapping = _mapping(
        target_id=target_id,
        sequence=normalized,
        scoped=scoped,
        source_chain_id=selected_chain,
        source_label_chain_id=chain_info.label_chain_id,
        reference_start=reference_start,
        identity_mapping=identity_mapping,
    )
    mapping_json = dump_model(mapping, artifact_dir / "residue-mapping.json")
    mapping_tsv = _exclusive_text(
        _mapping_tsv(mapping),
        artifact_dir / "residue-map.tsv",
    )
    identity_path = _json(identity_report, artifact_dir / "identity-report.json")
    scope_path = _json(scope_report, artifact_dir / "scope-report.json")
    candidate_search_status = (
        "not_requested"
        if provenance.get("source") == "local-file"
        else "completed"
    )
    candidates_json = _json(
        {
            "schema_version": "0.2",
            "search_status": candidate_search_status,
            "reason": (
                "explicit-local-structure"
                if candidate_search_status == "not_requested"
                else None
            ),
            "candidates": candidates,
        },
        artifact_dir / "structure-candidates.json",
    )
    candidates_tsv = _exclusive_text(
        "pdb_id\tchain\teligible\treasons\n"
        + "".join(
            f"{item.get('pdb_id', '')}\t{item.get('chain', '')}\t"
            f"{str(item.get('eligible', False)).lower()}\t"
            f"{';'.join(str(reason) for reason in item.get('reasons', []))}\n"
            for item in candidates
        ),
        artifact_dir / "structure-candidates.tsv",
    )
    missing_by_model = {
        model_id: [
            entry.label_seq_id
            for entry in mapping.entries
            if model_id not in entry.model_presence
        ]
        for model_id in (str(model.num) for model in scoped)
    }
    representative_model_id = str(scoped[0].num)
    representative_present = {
        entry.label_seq_id
        for entry in mapping.entries
        if representative_model_id in entry.model_presence
    }
    coordinate_coverage = len(representative_present) / normalized.length
    missing_ranges = _missing_coordinate_ranges(
        representative_present,
        normalized.length,
    )
    missing_backbone_by_model: dict[str, list[int]] = {}
    missing_sidechain_by_model: dict[str, list[int]] = {}
    for model in scoped:
        missing_backbone: list[int] = []
        missing_sidechain: list[int] = []
        for residue in model[0]:
            atom_names = {atom.name.strip() for atom in residue}
            label = int(residue.label_seq or 0)
            if not {"N", "CA", "C", "O"}.issubset(atom_names):
                missing_backbone.append(label)
            if residue.name != "GLY" and "CB" not in atom_names:
                missing_sidechain.append(label)
        missing_backbone_by_model[str(model.num)] = missing_backbone
        missing_sidechain_by_model[str(model.num)] = missing_sidechain
    effective_quality = {
        **quality_report,
        "coordinate_model_count": len(scoped),
        "coordinate_model_ids": [str(model.num) for model in scoped],
        "scope_residue_count": normalized.length,
        "observed_scope_residue_count": len(representative_present),
        "scope_coverage": coordinate_coverage,
        "scope_sequence_coverage": 1.0,
        "scope_coordinate_coverage": coordinate_coverage,
        "scope_sequence_identity": 1.0,
        "target_structure_status": (
            "experimental-complete"
            if coordinate_coverage == 1.0
            else "experimental-partial"
        ),
        "missing_coordinate_ranges": missing_ranges,
        "missing_label_seq_ids_by_model": missing_by_model,
        "missing_backbone_label_seq_ids_by_model": missing_backbone_by_model,
        "missing_sidechain_anchor_label_seq_ids_by_model": missing_sidechain_by_model,
        "source_protein_chain_count": len(inventory.protein_chain_ids),
        "source_ligand_names": list(inventory.ligand_names),
        "source_water_count": inventory.water_count,
        "altloc_selection": "highest-occupancy-then-altloc-lexicographic-v1",
        "source_altloc_atom_count": chain_info.altloc_atom_count,
        "unsupported_nonstandard_residues": [],
        "ptm_annotation_status": "not_available_from-coordinate-only",
        "membrane_overlap_status": "not_implemented",
    }
    quality_path = _json(
        effective_quality,
        artifact_dir / "structure-quality.json",
    )
    provenance_path = _json(provenance, artifact_dir / "provenance.json")
    published_retrieval: list[dict[str, Any]] = []
    retrieval_response_paths: list[Path] = []
    for index, record in enumerate(retrieval_records, start=1):
        published = dict(record)
        artifact_name = record.get("artifact_name")
        if isinstance(artifact_name, str):
            source_response = (
                root
                / "01-target-preparation"
                / attempt_id
                / "work"
                / "retrieval"
                / artifact_name
            )
            if source_response.is_file():
                destination = artifact_dir / "retrieval" / artifact_name
                _exclusive_copy(source_response, destination)
                published["run_artifact_path"] = destination.relative_to(root).as_posix()
                published["artifact_id"] = f"retrieval-response-{index:04d}"
                retrieval_response_paths.append(destination)
        published_retrieval.append(published)
    retrieval_path = _json(
        {
            "schema_version": "0.1",
            "status": (
                "completed" if published_retrieval else "not_requested"
            ),
            "requests": published_retrieval,
        },
        artifact_dir / "retrieval-manifest.json",
    )
    source_context_path: Path | None = None
    if preserve_source_context:
        source_context_path = _write_source_context(
            source_path,
            source,
            artifact_dir / "source-context.cif",
        )
    design_context_path = _write_design_context(
        source,
        scoped,
        keep_ligands=keep_ligands,
        path=artifact_dir / "design-context.cif",
    )

    def ref(
        path: Path,
        artifact_id: str,
        role: str,
        file_format: str,
    ) -> ArtifactRef:
        return _artifact(
            run_root=root,
            path=path,
            artifact_id=artifact_id,
            role=role,
            file_format=file_format,
            attempt_id=attempt_id,
        )

    target_ref = ref(target_cif, "target-structure", "canonical-target", "mmcif")
    sequence_ref = ref(sequence_path, "target-sequence", "canonical-sequence", "fasta")
    mapping_ref = ref(mapping_json, "residue-mapping", "residue-mapping", "json")
    quality_ref = ref(quality_path, "structure-quality", "structure-quality", "json")
    provenance_ref = ref(provenance_path, "target-provenance", "provenance", "json")
    model_ids = tuple(str(model.num) for model in scoped)
    bundle = TargetBundle(
        schema_version=(
            "0.5"
            if identity_report.get("schema_version") == "0.2"
            and identity_mapping is not None
            else "0.4"
        ),
        target_id=target_id,
        origin=TargetStructureOrigin.EXPERIMENTAL,
        sequence_length=normalized.length,
        sequence_sha256=normalized.sequence_sha256,
        producer_attempt=attempt_id,
        target_structure=target_ref,
        sequence=sequence_ref,
        residue_mapping=mapping_ref,
        quality_report=quality_ref,
        provenance=provenance_ref,
        coordinate_ensemble=CoordinateEnsemble(
            model_count=len(model_ids),
            model_ids=model_ids,
            representative_model_id=model_ids[0],
        ),
        reference_sequence=(
            None
            if reference_path is None
            else ref(
                reference_path,
                "reference-sequence",
                "reference-sequence",
                "fasta",
            )
        ),
        residue_mapping_tsv=ref(
            mapping_tsv,
            "residue-map-tsv",
            "residue-mapping-projection",
            "tsv",
        ),
        identity_report=ref(identity_path, "identity-report", "identity-evidence", "json"),
        scope_report=ref(scope_path, "scope-report", "scope-evidence", "json"),
        structure_candidates=ref(
            candidates_json,
            "structure-candidates",
            "structure-candidate-report",
            "json",
        ),
        structure_candidates_tsv=ref(
            candidates_tsv,
            "structure-candidates-tsv",
            "structure-candidate-projection",
            "tsv",
        ),
        retrieval_manifest=ref(
            retrieval_path,
            "retrieval-manifest",
            "remote-retrieval-evidence",
            "json",
        ),
        source_context=(
            None
            if source_context_path is None
            else ref(
                source_context_path,
                "source-context",
                "source-structure-context",
                "mmcif",
            )
        ),
        design_context=(
            None
            if design_context_path is None
            else ref(
                design_context_path,
                "design-context",
                "selected-ligand-context",
                "mmcif",
            )
        ),
        target_pdb=(
            None
            if target_pdb is None
            else ref(
                target_pdb,
                "target-pdb",
                "compatibility-target",
                "pdb",
            )
        ),
    )
    bundle_path = dump_model(bundle, artifact_dir / "target-bundle.json")
    bundle_ref = ref(bundle_path, "target-bundle", "target-bundle", "json")
    output = [
        target_ref,
        sequence_ref,
        mapping_ref,
        quality_ref,
        provenance_ref,
        ref(mapping_tsv, "residue-map-tsv", "residue-mapping-projection", "tsv"),
        ref(identity_path, "identity-report", "identity-evidence", "json"),
        ref(scope_path, "scope-report", "scope-evidence", "json"),
        ref(
            candidates_json,
            "structure-candidates",
            "structure-candidate-report",
            "json",
        ),
        ref(
            candidates_tsv,
            "structure-candidates-tsv",
            "structure-candidate-projection",
            "tsv",
        ),
        ref(
            retrieval_path,
            "retrieval-manifest",
            "remote-retrieval-evidence",
            "json",
        ),
    ]
    if reference_path is not None:
        output.append(
            ref(reference_path, "reference-sequence", "reference-sequence", "fasta")
        )
    if source_context_path is not None:
        output.append(
            ref(
                source_context_path,
                "source-context",
                "source-structure-context",
                "mmcif",
            )
        )
    if design_context_path is not None:
        output.append(
            ref(
                design_context_path,
                "design-context",
                "selected-ligand-context",
                "mmcif",
            )
        )
    if target_pdb is not None and target_pdb.is_file():
        output.append(ref(target_pdb, "target-pdb", "compatibility-target", "pdb"))
    for index, response_path in enumerate(retrieval_response_paths, start=1):
        output.append(
            ref(
                response_path,
                f"retrieval-response-{index:04d}",
                "remote-response-snapshot",
                response_path.suffix.lower().lstrip(".") or "binary",
            )
        )
    output.append(bundle_ref)
    return StructureNormalizationResult(
        built_bundle=BuiltTargetBundle(
            bundle=bundle,
            bundle_path=bundle_path,
            bundle_artifact=bundle_ref,
        ),
        target_pdb=target_pdb,
        residue_mapping_tsv=mapping_tsv,
        output_artifacts=tuple(output),
    )
