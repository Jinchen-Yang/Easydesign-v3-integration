"""本地/远程实验结构的严格 inventory、scope 提取和 chain A 规范化。"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import gemmi

from easydesign.core import ArtifactRef, ManifestStateError, TargetInputError, dump_model
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


@dataclass(frozen=True, slots=True)
class ChainInventory:
    author_chain_id: str
    label_chain_id: str
    residue_count: int
    canonical_residue_count: int
    sequence: str
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
        ligands: set[str] = set()
        waters = 0
        altloc = 0
        label_chain_ids: set[str] = set()
        for residue in chain:
            if residue.name in THREE_TO_ONE:
                sequence.append(THREE_TO_ONE[residue.name])
                if residue.subchain:
                    label_chain_ids.add(residue.subchain)
            elif residue.is_water():
                waters += 1
            else:
                ligands.add(residue.name)
            altloc += sum(1 for atom in residue if atom.altloc not in {"\x00", " ", ""})
        all_ligands.update(ligands)
        total_waters += waters
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
            if expected_sequence in chain.sequence
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

    atoms_by_name: dict[str, list[gemmi.Atom]] = {}
    for atom in residue:
        atoms_by_name.setdefault(atom.name, []).append(atom)
    for name, atoms in atoms_by_name.items():
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


def _scope_slice(
    observed: str,
    expected: str | None,
) -> tuple[int, int, str]:
    if expected is None:
        return 0, len(observed), observed
    start = observed.find(expected)
    if start < 0:
        raise TargetInputError(
            "experimental-sequence-mismatch: design scope 必须 100% identity 且 100% coverage; "
            f"expected_length={len(expected)}, observed_length={len(observed)}"
        )
    return start, start + len(expected), expected


def _clone_scoped_structure(
    source: gemmi.Structure,
    *,
    source_chain_id: str,
    start_index: int,
    end_index: int,
) -> gemmi.Structure:
    result = gemmi.Structure()
    result.name = source.name or "easydesign_target"
    result.cell = source.cell
    result.spacegroup_hm = source.spacegroup_hm
    representative_chain = _model_chain(source[0], source_chain_id)
    representative_residues = _canonical_residues(representative_chain)
    if len(representative_residues) < end_index:
        raise TargetInputError(
            "experimental-scope-missing: representative model 缺少 design scope residue"
        )
    scope_residues = representative_residues[start_index:end_index]
    scope_keys = tuple(
        (residue.seqid.num, residue.seqid.icode, residue.name)
        for residue in scope_residues
    )
    for model_index, model in enumerate(source):
        source_chain = _model_chain(model, source_chain_id)
        residues = _canonical_residues(source_chain)
        by_key = {
            (residue.seqid.num, residue.seqid.icode, residue.name): residue
            for residue in residues
        }
        output_model = gemmi.Model(model.num)
        output_chain = gemmi.Chain("A")
        for label_seq_id, key in enumerate(scope_keys, start=1):
            residue = by_key.get(key)
            if residue is None:
                if model_index == 0:
                    raise TargetInputError(
                        "representative model scope identity changed during normalization"
                    )
                continue
            if not any(atom.name.strip() == "CA" for atom in residue):
                if model_index != 0:
                    continue
                raise TargetInputError(
                    "experimental-scope-missing-ca: "
                    f"model={model.num}, chain={source_chain_id}, residue={residue.seqid}"
                )
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
    result.setup_entities()
    if result.entities:
        result.entities[0].full_sequence = [
            residue.name for residue in result[0][0]
        ]
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
) -> ResidueMapping:
    entries: list[ResidueMappingEntry] = []
    first = scoped[0][0]
    model_ids = tuple(str(model.num) for model in scoped)
    model_presence: dict[int, tuple[str, ...]] = {}
    for index in range(1, len(first) + 1):
        present = []
        for model in scoped:
            if any(
                residue.label_seq == index
                for residue in model[0]
            ):
                present.append(str(model.num))
        model_presence[index] = tuple(present)
    for index, residue in enumerate(first, start=1):
        original = residue.seqid
        amino_acid = THREE_TO_ONE[residue.name]
        entries.append(
            ResidueMappingEntry(
                sequence_index=index,
                amino_acid=amino_acid,
                label_chain_id="A",
                label_seq_id=index,
                author_chain_id="A",
                author_residue_id=str(original.num),
                source_label_chain_id=source_label_chain_id,
                source_author_chain_id=source_chain_id,
                source_author_residue_id=str(original.num),
                insertion_code=(
                    None
                    if original.icode in {"\x00", " ", ""}
                    else original.icode
                ),
                reference_position=(
                    None if reference_start is None else reference_start + index - 1
                ),
                model_presence=model_presence[index] or (model_ids[0],),
                source_residue_name=residue.name,
            )
        )
    return ResidueMapping(
        schema_version="0.2",
        target_id=target_id,
        sequence_sha256=sequence.sequence_sha256,
        entries=tuple(entries),
    )


def _mapping_tsv(mapping: ResidueMapping) -> str:
    header = (
        "sequence_index\tamino_acid\tlabel_chain_id\tlabel_seq_id\t"
        "source_auth_chain\tsource_auth_residue\tinsertion_code\t"
        "reference_position\tmodel_presence\n"
    )
    rows = []
    for entry in mapping.entries:
        rows.append(
            "\t".join(
                (
                    str(entry.sequence_index),
                    entry.amino_acid,
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
) -> StructureNormalizationResult:
    """发布 protein-only chain A Target Bundle 0.4 和完整 evidence 投影。"""

    root = run_root.resolve()
    artifact_dir = root / "01-target-preparation" / attempt_id / "artifacts"
    source = read_structure(source_path)
    inventory = inventory_structure(source_path)
    chain_info = next(
        chain for chain in inventory.chains if chain.author_chain_id == selected_chain
    )
    start_index, end_index, scope_sequence = _scope_slice(
        chain_info.sequence,
        expected_scope_sequence,
    )
    scoped = _clone_scoped_structure(
        source,
        source_chain_id=selected_chain,
        start_index=start_index,
        end_index=end_index,
    )
    normalized = normalize_raw_sequence(
        scope_sequence,
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
        "scope_coverage": 1.0,
        "scope_sequence_identity": 1.0,
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
        schema_version="0.4",
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
