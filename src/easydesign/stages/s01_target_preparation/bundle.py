"""把一个已验证结构预测结果发布为不可覆盖的 Target Bundle。"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from Bio.PDB.MMCIF2Dict import MMCIF2Dict

from easydesign.backends.structure_prediction import (
    MsaMode,
    PredictionParameterProfile,
    StructurePredictionProduct,
    TemplateMode,
)
from easydesign.backends.target_sources import NormalizedProteinSequence
from easydesign.core import (
    ArtifactRef,
    ManifestStateError,
    PredictionOutputError,
    dump_model,
    verify_sha256,
)

from .models import (
    BuiltTargetBundle,
    PredictionProvenance,
    ResidueMapping,
    ResidueMappingEntry,
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
        / "attempts"
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
