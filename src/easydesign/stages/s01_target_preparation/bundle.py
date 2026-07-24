"""把一个已验证结构预测结果发布为不可覆盖的 Target Bundle。"""

from __future__ import annotations

import shutil
from collections import Counter
from pathlib import Path
from typing import Any

import gemmi
from Bio.PDB.MMCIF2Dict import MMCIF2Dict

from easydesign.backends.structure_prediction import (
    MsaMode,
    PredictionParameterProfile,
    StructurePredictionProduct,
    TemplateMode,
)
from easydesign.backends.target_sources import (
    NormalizedProteinSequence,
    PseExtractionProduct,
    normalize_raw_sequence,
)
from easydesign.core import (
    ArtifactRef,
    ManifestStateError,
    PredictionOutputError,
    dump_model,
    verify_sha256,
)

from .models import (
    BuiltTargetBundle,
    ColorCount,
    ImportedStructureProvenance,
    ImportedStructureQualityReport,
    PredictionProvenance,
    PseSourceAnnotations,
    ResidueColorAnnotation,
    ResidueMapping,
    ResidueMappingEntry,
    SessionInventoryRecord,
    StructureQualityReport,
    TargetBundle,
    TargetStructureOrigin,
)

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


def _exclusive_copy(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        with source.open("rb") as input_handle, destination.open("xb") as output_handle:
            shutil.copyfileobj(input_handle, output_handle)
    except FileExistsError as error:
        message = f"不可覆盖已存在的 Target Bundle artifact: {destination}"
        raise ManifestStateError(message) from error


def _exclusive_text(text: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        with destination.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
    except FileExistsError as error:
        message = f"不可覆盖已存在的 Target Bundle artifact: {destination}"
        raise ManifestStateError(message) from error


def _column(raw: dict[str, Any], name: str) -> list[str]:
    value = raw.get(name)
    if value is None:
        raise PredictionOutputError(f"预测 CIF 缺少必需列: {name}")
    if isinstance(value, str):
        return [value]
    return [str(item) for item in value]


def _build_residue_mapping(
    structure_path: Path,
    target: NormalizedProteinSequence,
) -> ResidueMapping:
    try:
        raw: dict[str, Any] = MMCIF2Dict(  # type: ignore[no-untyped-call]
            str(structure_path)
        )
    except Exception as error:
        raise PredictionOutputError(f"无法解析预测 CIF: {structure_path}") from error

    groups = _column(raw, "_atom_site.group_PDB")
    label_comp_ids = _column(raw, "_atom_site.label_comp_id")
    label_chain_ids = _column(raw, "_atom_site.label_asym_id")
    label_seq_ids = _column(raw, "_atom_site.label_seq_id")
    author_chain_ids = _column(raw, "_atom_site.auth_asym_id")
    author_residue_ids = _column(raw, "_atom_site.auth_seq_id")
    insertion_codes = _column(raw, "_atom_site.pdbx_PDB_ins_code")
    columns = (
        groups,
        label_comp_ids,
        label_chain_ids,
        label_seq_ids,
        author_chain_ids,
        author_residue_ids,
        insertion_codes,
    )
    if len({len(column) for column in columns}) != 1:
        raise PredictionOutputError("预测 CIF atom_site 列长度不一致")

    residues: dict[tuple[str, int], ResidueMappingEntry] = {}
    for group, comp, chain, seq_id, author_chain, author_id, insertion in zip(
        *columns,
        strict=True,
    ):
        if group != "ATOM" or seq_id in {".", "?"}:
            continue
        try:
            sequence_index = int(seq_id)
            amino_acid = THREE_TO_ONE[comp]
        except (ValueError, KeyError) as error:
            raise PredictionOutputError(
                f"预测 CIF 含无法映射的标准残基: comp={comp}, seq_id={seq_id}"
            ) from error
        key = (chain, sequence_index)
        residues.setdefault(
            key,
            ResidueMappingEntry(
                sequence_index=sequence_index,
                amino_acid=amino_acid,
                label_chain_id=chain,
                label_seq_id=sequence_index,
                author_chain_id=author_chain,
                author_residue_id=author_id,
                insertion_code=None if insertion in {".", "?"} else insertion,
            ),
        )

    chains = {chain for chain, _ in residues}
    if len(chains) != 1:
        raise PredictionOutputError(
            f"当前单序列 Target Bundle 需要恰好一条链，发现: {sorted(chains)}"
        )
    entries = tuple(sorted(residues.values(), key=lambda entry: entry.sequence_index))
    observed = "".join(entry.amino_acid for entry in entries)
    if observed != target.sequence:
        raise PredictionOutputError(
            "预测 CIF 残基序列与规范输入不一致: "
            f"expected_length={target.length}, observed_length={len(observed)}"
        )
    return ResidueMapping(
        target_id=target.target_id,
        sequence_sha256=target.sequence_sha256,
        entries=entries,
    )


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


def build_predicted_target_bundle(
    *,
    run_root: Path,
    attempt_id: str,
    target: NormalizedProteinSequence,
    product: StructurePredictionProduct,
    model_checkpoint_sha256: str,
    msa_mode: MsaMode,
    msa_input_sha256: str | None,
    msa_server_mode: str | None,
    template_mode: TemplateMode,
    parameter_profile: PredictionParameterProfile,
    resolved_cycle_count: int,
    resolved_diffusion_step_count: int,
) -> BuiltTargetBundle:
    """发布 sequence、CIF、映射、质量、溯源和 bundle；任何目标已存在都失败。"""

    resolved_run_root = run_root.resolve()
    artifact_dir = (
        resolved_run_root
        / "01-target-preparation"
        / attempt_id
        / "artifacts"
    )
    target_cif = artifact_dir / "target.cif"
    sequence_fasta = artifact_dir / "sequence.fasta"
    mapping_json = artifact_dir / "residue-mapping.json"
    quality_json = artifact_dir / "structure-quality.json"
    provenance_json = artifact_dir / "provenance.json"
    bundle_json = artifact_dir / "target-bundle.json"

    if not product.structure_path.is_file() or not product.confidence_path.is_file():
        raise PredictionOutputError(f"预测结构不存在: {product.structure_path}")
    verify_sha256(product.structure_path, product.structure_sha256)
    verify_sha256(product.confidence_path, product.confidence_sha256)
    _exclusive_copy(product.structure_path, target_cif)
    _exclusive_text(target.to_fasta(), sequence_fasta)

    mapping = _build_residue_mapping(target_cif, target)
    quality = StructureQualityReport(
        backend_name=product.backend_name,
        backend_version=product.backend_version,
        model_name=product.model_name,
        seed=product.seed,
        sample_index=product.sample_index,
        plddt=product.plddt,
        gpde=product.gpde,
        ptm=product.ptm,
        iptm=product.iptm,
        ranking_score=product.ranking_score,
        has_clash=product.has_clash,
        recycle_count=product.recycle_count,
    )
    provenance = PredictionProvenance(
        source_kind=target.source_kind,
        source_label=target.source_label,
        sequence_sha256=target.sequence_sha256,
        backend_name=product.backend_name,
        backend_version=product.backend_version,
        model_name=product.model_name,
        model_checkpoint_sha256=model_checkpoint_sha256,
        msa_mode=msa_mode,
        msa_input_sha256=msa_input_sha256,
        msa_server_mode=msa_server_mode,
        template_mode=template_mode,
        parameter_profile=parameter_profile,
        resolved_cycle_count=resolved_cycle_count,
        resolved_diffusion_step_count=resolved_diffusion_step_count,
        seed=product.seed,
        sample_index=product.sample_index,
    )
    dump_model(mapping, mapping_json)
    dump_model(quality, quality_json)
    dump_model(provenance, provenance_json)

    bundle = TargetBundle(
        target_id=target.target_id,
        origin=TargetStructureOrigin.PREDICTED,
        sequence_length=target.length,
        sequence_sha256=target.sequence_sha256,
        producer_attempt=attempt_id,
        target_structure=_artifact(
            run_root=resolved_run_root,
            path=target_cif,
            artifact_id="target-structure",
            role="canonical-target",
            file_format="mmcif",
            attempt_id=attempt_id,
        ),
        sequence=_artifact(
            run_root=resolved_run_root,
            path=sequence_fasta,
            artifact_id="target-sequence",
            role="canonical-sequence",
            file_format="fasta",
            attempt_id=attempt_id,
        ),
        residue_mapping=_artifact(
            run_root=resolved_run_root,
            path=mapping_json,
            artifact_id="residue-mapping",
            role="residue-mapping",
            file_format="json",
            attempt_id=attempt_id,
        ),
        quality_report=_artifact(
            run_root=resolved_run_root,
            path=quality_json,
            artifact_id="structure-quality",
            role="structure-quality",
            file_format="json",
            attempt_id=attempt_id,
        ),
        provenance=_artifact(
            run_root=resolved_run_root,
            path=provenance_json,
            artifact_id="target-provenance",
            role="provenance",
            file_format="json",
            attempt_id=attempt_id,
        ),
    )
    dump_model(bundle, bundle_json)
    bundle_artifact = _artifact(
        run_root=resolved_run_root,
        path=bundle_json,
        artifact_id="target-bundle",
        role="target-bundle",
        file_format="json",
        attempt_id=attempt_id,
    )
    return BuiltTargetBundle(
        bundle=bundle,
        bundle_path=bundle_json,
        bundle_artifact=bundle_artifact,
    )


def _pdb_to_normalized_cif(source: Path, destination: Path) -> None:
    try:
        structure = gemmi.read_structure(str(source))
    except Exception as error:
        raise PredictionOutputError(f"无法解析 PyMOL worker PDB: {source}") from error
    if len(structure) != 1:
        raise PredictionOutputError(
            f"PyMOL worker PDB 必须恰好一个 model，发现 {len(structure)} 个"
        )
    model = structure[0]
    chains = [chain for chain in model if len(chain) > 0]
    if len(chains) != 1 or not chains[0].name:
        raise PredictionOutputError(
            f"PyMOL worker PDB 必须恰好一条非空 chain，发现 {len(chains)} 条"
        )
    try:
        structure.setup_entities()
        if len(structure.entities) != 1:
            raise ValueError(
                f"规范化 PSE PDB 需要恰好一个 polymer entity，发现 {len(structure.entities)}"
            )
        structure.entities[0].full_sequence = [residue.name for residue in chains[0]]
        structure.assign_label_seq_id()
        document = structure.make_mmcif_document()
        _exclusive_text(document.as_string(), destination)
    except Exception as error:
        raise PredictionOutputError("PyMOL PDB 无法规范化为 mmCIF") from error


def _validate_pse_mapping(
    mapping: ResidueMapping,
    product: PseExtractionProduct,
) -> None:
    if len(mapping.entries) != len(product.response.residues):
        raise PredictionOutputError(
            "规范 CIF 与 PyMOL residue annotation 数量不一致"
        )
    for mapped, annotated in zip(
        mapping.entries,
        product.response.residues,
        strict=True,
    ):
        if (
            mapped.sequence_index != annotated.sequence_index
            or mapped.amino_acid != annotated.amino_acid
            or mapped.author_chain_id != annotated.author_chain_id
            or mapped.author_residue_id != annotated.author_residue_id
            or mapped.insertion_code != annotated.insertion_code
        ):
            raise PredictionOutputError(
                "规范 CIF residue mapping 与 PyMOL annotation 不一致: "
                f"sequence_index={annotated.sequence_index}"
            )


def build_imported_pse_target_bundle(
    *,
    run_root: Path,
    attempt_id: str,
    target_id: str,
    source_label: str,
    product: PseExtractionProduct,
) -> BuiltTargetBundle:
    """把严格验证的单 Target PSE 发布为 imported Target Bundle 0.2。"""

    resolved_run_root = run_root.resolve()
    artifact_dir = (
        resolved_run_root
        / "01-target-preparation"
        / attempt_id
        / "artifacts"
    )
    target_cif = artifact_dir / "target.cif"
    sequence_fasta = artifact_dir / "sequence.fasta"
    mapping_json = artifact_dir / "residue-mapping.json"
    quality_json = artifact_dir / "structure-quality.json"
    provenance_json = artifact_dir / "provenance.json"
    annotations_json = artifact_dir / "source-annotations.json"
    bundle_json = artifact_dir / "target-bundle.json"

    target = normalize_raw_sequence(
        product.response.sequence,
        target_id=target_id,
        source_label=source_label,
    )
    _pdb_to_normalized_cif(product.raw_pdb_path, target_cif)
    _exclusive_text(target.to_fasta(), sequence_fasta)
    mapping = _build_residue_mapping(target_cif, target)
    _validate_pse_mapping(mapping, product)

    residue_count = len(product.response.residues)
    quality = ImportedStructureQualityReport(
        coordinate_state_count=1,
        protein_chain_count=1,
        residue_count=residue_count,
        canonical_residue_count=residue_count,
        residues_with_ca=residue_count,
        missing_ca_count=0,
        ligand_heavy_atom_count=product.response.ligand_heavy_atom_count,
        water_residue_count=product.response.water_residue_count,
    )
    provenance = ImportedStructureProvenance(
        source_sha256=product.response.source_sha256,
        backend_version=product.response.pymol_version,
        selected_object=product.response.selected_object,
        author_chain_id=product.response.chain_id,
        coordinate_state=product.response.state,
        inventory=tuple(
            SessionInventoryRecord.model_validate(entry.model_dump())
            for entry in product.response.inventory
        ),
        worker_runtime_seconds=product.response.worker_runtime_seconds,
        adapter_runtime_seconds=product.adapter_runtime_seconds,
    )
    color_counter = Counter(
        (
            residue.ca_color_index,
            residue.ca_color_rgb,
            residue.ca_color_hex,
        )
        for residue in product.response.residues
    )
    annotations = PseSourceAnnotations(
        residues=tuple(
            ResidueColorAnnotation(
                label_seq_id=residue.sequence_index,
                author_chain_id=residue.author_chain_id,
                author_residue_id=residue.author_residue_id,
                insertion_code=residue.insertion_code,
                ca_color_index=residue.ca_color_index,
                ca_color_rgb=residue.ca_color_rgb,
                ca_color_hex=residue.ca_color_hex,
            )
            for residue in product.response.residues
        ),
        color_counts=tuple(
            ColorCount(
                ca_color_index=color_index,
                ca_color_rgb=rgb,
                ca_color_hex=hex_color,
                residue_count=count,
            )
            for (color_index, rgb, hex_color), count in sorted(
                color_counter.items(),
                key=lambda item: (-item[1], item[0][0]),
            )
        ),
    )
    dump_model(mapping, mapping_json)
    dump_model(quality, quality_json)
    dump_model(provenance, provenance_json)
    dump_model(annotations, annotations_json)

    target_structure_ref = _artifact(
        run_root=resolved_run_root,
        path=target_cif,
        artifact_id="target-structure",
        role="canonical-target",
        file_format="mmcif",
        attempt_id=attempt_id,
    )
    sequence_ref = _artifact(
        run_root=resolved_run_root,
        path=sequence_fasta,
        artifact_id="target-sequence",
        role="canonical-sequence",
        file_format="fasta",
        attempt_id=attempt_id,
    )
    mapping_ref = _artifact(
        run_root=resolved_run_root,
        path=mapping_json,
        artifact_id="residue-mapping",
        role="residue-mapping",
        file_format="json",
        attempt_id=attempt_id,
    )
    quality_ref = _artifact(
        run_root=resolved_run_root,
        path=quality_json,
        artifact_id="structure-quality",
        role="structure-quality",
        file_format="json",
        attempt_id=attempt_id,
    )
    provenance_ref = _artifact(
        run_root=resolved_run_root,
        path=provenance_json,
        artifact_id="target-provenance",
        role="provenance",
        file_format="json",
        attempt_id=attempt_id,
    )
    annotations_ref = _artifact(
        run_root=resolved_run_root,
        path=annotations_json,
        artifact_id="source-annotations",
        role="source-annotations",
        file_format="json",
        attempt_id=attempt_id,
    )
    bundle = TargetBundle(
        schema_version="0.2",
        target_id=target.target_id,
        origin=TargetStructureOrigin.IMPORTED,
        sequence_length=target.length,
        sequence_sha256=target.sequence_sha256,
        producer_attempt=attempt_id,
        target_structure=target_structure_ref,
        sequence=sequence_ref,
        residue_mapping=mapping_ref,
        quality_report=quality_ref,
        provenance=provenance_ref,
        source_annotations=annotations_ref,
    )
    dump_model(bundle, bundle_json)
    bundle_artifact = _artifact(
        run_root=resolved_run_root,
        path=bundle_json,
        artifact_id="target-bundle",
        role="target-bundle",
        file_format="json",
        attempt_id=attempt_id,
    )
    return BuiltTargetBundle(
        bundle=bundle,
        bundle_path=bundle_json,
        bundle_artifact=bundle_artifact,
    )
