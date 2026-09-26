"""Frozen target/binder template protocol for AFO complex predictions.

This module is deliberately deterministic.  The target template search remains
inside AFO's native DataPipeline; the only transformation performed here is
validation/snapshotting of its processed JSON.  Binder templates are extracted
from the same candidate's BoltzGen stage-1 complex and must match the exact
sequence sent to AFO.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Literal

import gemmi
from pydantic import BaseModel, ConfigDict, Field

from easydesign.backends.structure_prediction import (
    MsaMode,
    OpenFold3Af3JaxAdapter,
    OpenFold3TemplatePipelineAssets,
)
from easydesign.core import ManifestStateError, dump_model, sha256_file
from easydesign.core.artifacts import SHA256_PATTERN

from .complex_prediction_support import (
    _exclusive_write_or_verify,
    _template_ready_mmcif,
    resolve_complex_msa_input,
    run_checked_backend_invocation,
)
from .config import ComplexMsaConfig, ComplexTemplateConfig

PROTOCOL_ID: Literal["afo-native-target-boltzgen-vhh-v1"] = (
    "afo-native-target-boltzgen-vhh-v1"
)

_PROTEIN_RESIDUES = {
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


class AfoTemplateMappingAudit(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    template_index: int = Field(ge=0)
    inline_mmcif_sha256: str = Field(pattern=SHA256_PATTERN)
    mapped_residues: int = Field(ge=1)
    minimum_query_index: int = Field(ge=0)
    maximum_query_index: int = Field(ge=0)


class AfoTargetTemplateReceipt(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["0.1"] = "0.1"
    protocol_id: Literal["afo-native-target-boltzgen-vhh-v1"] = (
        "afo-native-target-boltzgen-vhh-v1"
    )
    target_sequence_sha256: str = Field(pattern=SHA256_PATTERN)
    target_unpaired_a3m_sha256: str = Field(pattern=SHA256_PATTERN)
    target_paired_a3m_sha256: str = Field(pattern=SHA256_PATTERN)
    source_input_json_sha256: str = Field(pattern=SHA256_PATTERN)
    processed_json_sha256: str = Field(pattern=SHA256_PATTERN)
    template_data_sha256: str = Field(pattern=SHA256_PATTERN)
    template_count: int = Field(ge=1)
    templates: tuple[AfoTemplateMappingAudit, ...] = Field(min_length=1)
    component_receipt_sha256: str = Field(pattern=SHA256_PATTERN)
    hmmer_version: str
    hmmbuild_sha256: str = Field(pattern=SHA256_PATTERN)
    hmmsearch_sha256: str = Field(pattern=SHA256_PATTERN)
    hmmalign_sha256: str = Field(pattern=SHA256_PATTERN)
    seqres_database_version: str
    seqres_database_sha256: str = Field(pattern=SHA256_PATTERN)
    mmcif_database_version: str
    mmcif_manifest_sha256: str = Field(pattern=SHA256_PATTERN)
    max_template_date: str


class AfoBinderTemplateReceipt(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["0.1"] = "0.1"
    protocol_id: Literal["afo-native-target-boltzgen-vhh-v1"] = (
        "afo-native-target-boltzgen-vhh-v1"
    )
    source_stage1_complex_sha256: str = Field(pattern=SHA256_PATTERN)
    source_chain_id: str
    binder_sequence_sha256: str = Field(pattern=SHA256_PATTERN)
    binder_length: int = Field(ge=1)
    binder_template_mmcif_sha256: str = Field(pattern=SHA256_PATTERN)
    binder_template_data_sha256: str = Field(pattern=SHA256_PATTERN)
    mapped_residues: int = Field(ge=1)


class AfoChainInputAudit(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    chain_id: str
    role: Literal["target", "binder"]
    sequence_length: int = Field(ge=1)
    sequence_sha256: str = Field(pattern=SHA256_PATTERN)
    unpaired_msa_depth: int = Field(ge=0)
    paired_msa_depth: int = Field(ge=0)
    template_count: int = Field(ge=0)
    template_source: Literal[
        "afo-native-local-datapipeline",
        "boltzgen-stage1-vhh",
    ]
    mapped_residues: int = Field(ge=0)


class AfoFinalInputAudit(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["0.1"] = "0.1"
    protocol_id: Literal["afo-native-target-boltzgen-vhh-v1"] = (
        "afo-native-target-boltzgen-vhh-v1"
    )
    input_json_sha256: str = Field(pattern=SHA256_PATTERN)
    model_seeds: tuple[int, ...] = Field(min_length=1)
    chains: tuple[AfoChainInputAudit, ...] = Field(min_length=2, max_length=2)


def _sequence_sha256(sequence: str) -> str:
    return hashlib.sha256(sequence.encode("ascii")).hexdigest()


def _a3m_depth(value: str) -> int:
    return sum(1 for line in value.splitlines() if line.strip().startswith(">"))


def _protein_from_payload(payload: dict[str, Any]) -> dict[str, Any]:
    try:
        sequences = payload["sequences"]
        if not isinstance(sequences, list) or len(sequences) != 1:
            raise TypeError("target-only payload must contain exactly one sequence")
        protein = sequences[0]["protein"]
        if not isinstance(protein, dict):
            raise TypeError("protein is not a mapping")
    except (KeyError, IndexError, TypeError) as error:
        raise ManifestStateError("AFO target processed.json schema 不合法") from error
    return protein


def validate_target_processed_json(
    *,
    source_input_json: Path,
    processed_json: Path,
    target_sequence: str,
    target_unpaired_a3m: Path,
    target_paired_a3m: Path,
    assets: OpenFold3TemplatePipelineAssets,
    output_root: Path,
) -> tuple[Path, AfoTargetTemplateReceipt]:
    """Validate AFO's native target output and snapshot its inline templates."""

    try:
        source_payload = json.loads(source_input_json.read_text(encoding="utf-8"))
        processed_payload = json.loads(processed_json.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ManifestStateError("AFO target template pipeline JSON 无法读取") from error
    source_protein = _protein_from_payload(source_payload)
    processed_protein = _protein_from_payload(processed_payload)
    expected_unpaired = target_unpaired_a3m.read_text(encoding="utf-8")
    expected_paired = target_paired_a3m.read_text(encoding="utf-8")
    if not expected_unpaired.endswith("\n"):
        expected_unpaired += "\n"
    if not expected_paired.endswith("\n"):
        expected_paired += "\n"
    required_identity = {
        "id": "A",
        "sequence": target_sequence,
        "unpairedMsa": expected_unpaired,
        "pairedMsa": expected_paired,
    }
    for field, expected in required_identity.items():
        if source_protein.get(field) != expected:
            raise ManifestStateError(
                f"AFO target DataPipeline source input 改写了冻结字段: {field}"
            )
        if processed_protein.get(field) != expected:
            raise ManifestStateError(
                f"AFO target DataPipeline processed.json 改写了冻结字段: {field}"
            )
    templates = processed_protein.get("templates")
    if not isinstance(templates, list) or not templates:
        raise ManifestStateError(
            "AFO target template search zero-hit；标准协议禁止静默 fallback"
        )
    audits: list[AfoTemplateMappingAudit] = []
    for index, template in enumerate(templates):
        if not isinstance(template, dict) or set(template) != {
            "mmcif",
            "queryIndices",
            "templateIndices",
        }:
            raise ManifestStateError(f"AFO target template[{index}] schema 不合法")
        mmcif = template["mmcif"]
        query = template["queryIndices"]
        mapped = template["templateIndices"]
        if (
            not isinstance(mmcif, str)
            or not mmcif.strip()
            or not isinstance(query, list)
            or not isinstance(mapped, list)
            or not query
            or len(query) != len(mapped)
            or any(type(value) is not int for value in (*query, *mapped))
            or len(set(query)) != len(query)
            or any(value < 0 or value >= len(target_sequence) for value in query)
            or any(value < 0 for value in mapped)
        ):
            raise ManifestStateError(
                f"AFO target template[{index}] mapping/mmCIF 不合法"
            )
        try:
            gemmi.cif.read_string(mmcif).sole_block()
        except (RuntimeError, ValueError) as error:
            raise ManifestStateError(
                f"AFO target template[{index}] inline mmCIF 无法解析"
            ) from error
        audits.append(
            AfoTemplateMappingAudit(
                template_index=index,
                inline_mmcif_sha256=hashlib.sha256(
                    mmcif.encode("utf-8")
                ).hexdigest(),
                mapped_residues=len(query),
                minimum_query_index=min(query),
                maximum_query_index=max(query),
            )
        )
    template_path = output_root / "target-templates.json"
    template_content = json.dumps(
        templates,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    ) + "\n"
    template_sha = _exclusive_write_or_verify(template_path, template_content)
    receipt = AfoTargetTemplateReceipt(
        target_sequence_sha256=_sequence_sha256(target_sequence),
        target_unpaired_a3m_sha256=sha256_file(target_unpaired_a3m),
        target_paired_a3m_sha256=sha256_file(target_paired_a3m),
        source_input_json_sha256=sha256_file(source_input_json),
        processed_json_sha256=sha256_file(processed_json),
        template_data_sha256=template_sha,
        template_count=len(templates),
        templates=tuple(audits),
        component_receipt_sha256=assets.component_receipt_sha256,
        hmmer_version=assets.hmmer_version,
        hmmbuild_sha256=assets.hmmbuild_sha256,
        hmmsearch_sha256=assets.hmmsearch_sha256,
        hmmalign_sha256=assets.hmmalign_sha256,
        seqres_database_version=assets.seqres_database_version,
        seqres_database_sha256=assets.seqres_database_sha256,
        mmcif_database_version=assets.mmcif_database_version,
        mmcif_manifest_sha256=assets.mmcif_manifest_sha256,
        max_template_date=assets.max_template_date.isoformat(),
    )
    receipt_path = output_root / "target-template-receipt.json"
    if receipt_path.exists():
        existing = AfoTargetTemplateReceipt.model_validate_json(
            receipt_path.read_text(encoding="utf-8")
        )
        if existing != receipt:
            raise ManifestStateError("AFO target template receipt 已存在但身份不一致")
    else:
        dump_model(receipt, receipt_path)
    return template_path.resolve(), receipt


def prepare_target_template_pipeline(
    *,
    adapter: OpenFold3Af3JaxAdapter,
    job_name: str,
    target_sequence: str,
    target_unpaired_a3m: Path,
    target_paired_a3m: Path,
    output_root: Path,
) -> tuple[Path, AfoTargetTemplateReceipt]:
    """Run or resume the one-time target template search for a prediction cohort."""

    assets = adapter.template_pipeline_assets()
    input_json = output_root / "target-template-input.json"
    pipeline_output = output_root / "pipeline-output"
    processed_json = adapter.target_template_processed_path(
        job_name=job_name,
        output_dir=pipeline_output,
    )
    receipt_path = output_root / "target-template-receipt.json"
    if receipt_path.is_file():
        if not input_json.is_file() or not processed_json.is_file():
            raise ManifestStateError(
                "AFO target template receipt 存在但 input/processed JSON 缺失"
            )
        return validate_target_processed_json(
            source_input_json=input_json,
            processed_json=processed_json,
            target_sequence=target_sequence,
            target_unpaired_a3m=target_unpaired_a3m,
            target_paired_a3m=target_paired_a3m,
            assets=assets,
            output_root=output_root,
        )
    if input_json.exists():
        try:
            existing = json.loads(input_json.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ManifestStateError(
                "AFO target template partial input 无法读取"
            ) from error
        protein = _protein_from_payload(existing)
        expected_unpaired = target_unpaired_a3m.read_text(encoding="utf-8")
        expected_paired = target_paired_a3m.read_text(encoding="utf-8")
        if not expected_unpaired.endswith("\n"):
            expected_unpaired += "\n"
        if not expected_paired.endswith("\n"):
            expected_paired += "\n"
        if any(
            (
                protein.get("id") != "A",
                protein.get("sequence") != target_sequence,
                protein.get("unpairedMsa") != expected_unpaired,
                protein.get("pairedMsa") != expected_paired,
                protein.get("templates") is not None,
            )
        ):
            raise ManifestStateError(
                "AFO target template partial input 与当前冻结输入不一致"
            )
    else:
        adapter.write_target_template_pipeline_input(
            job_name=job_name,
            target_sequence=target_sequence,
            unpaired_msa_path=target_unpaired_a3m,
            paired_msa_path=target_paired_a3m,
            path=input_json,
        )
    if not processed_json.is_file():
        invocation = adapter.target_template_pipeline_invocation(
            input_json=input_json,
            output_dir=pipeline_output,
        )
        run_checked_backend_invocation(invocation)
    if not processed_json.is_file():
        raise ManifestStateError(
            f"AFO target DataPipeline 未产生冻结路径: {processed_json}"
        )
    return validate_target_processed_json(
        source_input_json=input_json,
        processed_json=processed_json,
        target_sequence=target_sequence,
        target_unpaired_a3m=target_unpaired_a3m,
        target_paired_a3m=target_paired_a3m,
        assets=assets,
        output_root=output_root,
    )


def prepare_target_template_config(
    *,
    adapter: OpenFold3Af3JaxAdapter,
    job_name: str,
    target_sequence: str,
    target_unpaired_a3m: Path,
    target_paired_msa: ComplexMsaConfig,
    output_root: Path,
) -> ComplexTemplateConfig:
    """Resolve the frozen paired feature and return a precomputed template config."""

    paired_mode, paired_path = resolve_complex_msa_input(
        target_paired_msa,
        sequence=target_sequence,
        query_only_path=output_root / "target-paired-query-only.a3m",
    )
    if paired_mode is not MsaMode.PRECOMPUTED or paired_path is None:
        raise ManifestStateError(
            "AFO target template protocol 要求冻结的本地 target paired A3M"
        )
    template_path, receipt = prepare_target_template_pipeline(
        adapter=adapter,
        job_name=job_name,
        target_sequence=target_sequence,
        target_unpaired_a3m=target_unpaired_a3m,
        target_paired_a3m=paired_path,
        output_root=output_root,
    )
    return ComplexTemplateConfig(
        mode="precomputed",
        data_path=template_path,
        data_sha256=receipt.template_data_sha256,
    )


def prepare_binder_template_config(
    *,
    source_complex: Path,
    binder_sequence: str,
    output_root: Path,
) -> ComplexTemplateConfig:
    template_path, receipt = prepare_binder_stage1_template(
        source_complex=source_complex,
        binder_sequence=binder_sequence,
        output_root=output_root,
    )
    return ComplexTemplateConfig(
        mode="precomputed",
        data_path=template_path,
        data_sha256=receipt.binder_template_data_sha256,
    )


def prepare_binder_stage1_template(
    *,
    source_complex: Path,
    binder_sequence: str,
    output_root: Path,
) -> tuple[Path, AfoBinderTemplateReceipt]:
    """Extract exactly one matching VHH chain from a BoltzGen stage-1 complex."""

    try:
        structure = gemmi.read_structure(str(source_complex))
    except (RuntimeError, ValueError) as error:
        raise ManifestStateError("BoltzGen stage-1 complex 无法解析") from error
    if len(structure) != 1:
        raise ManifestStateError("BoltzGen stage-1 binder template 必须恰好一个 model")
    matches: list[gemmi.Chain] = []
    for chain in structure[0]:
        sequence = "".join(
            _PROTEIN_RESIDUES[residue.name.upper()]
            for residue in chain
            if residue.name.upper() in _PROTEIN_RESIDUES
        )
        if sequence == binder_sequence:
            matches.append(chain)
    if len(matches) != 1:
        raise ManifestStateError(
            "BoltzGen stage-1 binder chain 无法按最终 AFO sequence 唯一映射: "
            f"matches={len(matches)}"
        )
    source_chain = matches[0]
    output = gemmi.Structure()
    output.name = "easydesign_boltzgen_stage1_vhh"
    output.cell = structure.cell
    output.spacegroup_hm = structure.spacegroup_hm
    model = gemmi.Model(structure[0].num)
    chain = gemmi.Chain("B")
    copied = 0
    for residue in source_chain:
        if residue.name.upper() not in _PROTEIN_RESIDUES:
            continue
        if not any(atom.name.strip() == "CA" for atom in residue):
            raise ManifestStateError(
                "BoltzGen stage-1 binder template 含无 CA 的蛋白残基"
            )
        copied += 1
        cloned = residue.clone()
        cloned.subchain = "B"
        cloned.label_seq = copied
        chain.add_residue(cloned)
    if copied != len(binder_sequence):
        raise ManifestStateError(
            "BoltzGen stage-1 binder template 残基数与最终 AFO sequence 不一致"
        )
    model.add_chain(chain)
    output.add_model(model)
    output.setup_entities()
    if len(output.entities) != 1:
        raise ManifestStateError("BoltzGen stage-1 VHH template entity 构建失败")
    output.entities[0].full_sequence = [residue.name for residue in chain]
    output.assign_label_seq_id()
    output_root.mkdir(parents=True, exist_ok=True)
    raw_path = output_root / "binder-stage1-chain.cif"
    raw_content = output.make_mmcif_document().as_string()
    _exclusive_write_or_verify(raw_path, raw_content)
    template_content, _, _ = _template_ready_mmcif(raw_path)
    template_structure = output_root / "binder-template.cif"
    template_structure_sha = _exclusive_write_or_verify(
        template_structure,
        template_content,
    )
    indices = list(range(len(binder_sequence)))
    template_payload = [
        {
            "mmcif": template_content,
            "queryIndices": indices,
            "templateIndices": indices,
        }
    ]
    template_path = output_root / "binder-template.json"
    template_sha = _exclusive_write_or_verify(
        template_path,
        json.dumps(
            template_payload,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
    )
    receipt = AfoBinderTemplateReceipt(
        source_stage1_complex_sha256=sha256_file(source_complex),
        source_chain_id=source_chain.name,
        binder_sequence_sha256=_sequence_sha256(binder_sequence),
        binder_length=len(binder_sequence),
        binder_template_mmcif_sha256=template_structure_sha,
        binder_template_data_sha256=template_sha,
        mapped_residues=len(indices),
    )
    receipt_path = output_root / "binder-template-receipt.json"
    if receipt_path.exists():
        existing = AfoBinderTemplateReceipt.model_validate_json(
            receipt_path.read_text(encoding="utf-8")
        )
        if existing != receipt:
            raise ManifestStateError("AFO binder template receipt 已存在但身份不一致")
    else:
        dump_model(receipt, receipt_path)
    return template_path.resolve(), receipt


def audit_final_input(
    *,
    input_json: Path,
    output_path: Path,
) -> AfoFinalInputAudit:
    """Create the required chain-level audit table for one final AFO input."""

    try:
        payload = json.loads(input_json.read_text(encoding="utf-8"))
        sequences = payload["sequences"]
        seeds = payload["modelSeeds"]
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, KeyError) as error:
        raise ManifestStateError("最终 AFO input.json 无法审计") from error
    if not isinstance(sequences, list) or len(sequences) != 2 or not isinstance(seeds, list):
        raise ManifestStateError("最终 AFO input.json 必须恰好包含 target/binder")
    audits: list[AfoChainInputAudit] = []
    expected: tuple[
        tuple[str, Literal["target", "binder"]],
        tuple[str, Literal["target", "binder"]],
    ] = (("A", "target"), ("B", "binder"))
    for item, (chain_id, role) in zip(sequences, expected, strict=True):
        protein = item.get("protein") if isinstance(item, dict) else None
        if not isinstance(protein, dict) or protein.get("id") != chain_id:
            raise ManifestStateError("最终 AFO input.json chain order/id 不合法")
        sequence = protein.get("sequence")
        unpaired = protein.get("unpairedMsa")
        paired = protein.get("pairedMsa")
        templates = protein.get("templates")
        if (
            not isinstance(sequence, str)
            or not isinstance(unpaired, str)
            or not isinstance(paired, str)
            or not isinstance(templates, list)
            or not templates
        ):
            raise ManifestStateError("最终 AFO input.json feature schema 不合法")
        mapped_query_indices: set[int] = set()
        for template in templates:
            query_indices = (
                template.get("queryIndices") if isinstance(template, dict) else None
            )
            if (
                not isinstance(query_indices, list)
                or not query_indices
                or any(type(value) is not int for value in query_indices)
                or any(value < 0 or value >= len(sequence) for value in query_indices)
            ):
                raise ManifestStateError("最终 AFO input.json template mapping 不合法")
            mapped_query_indices.update(query_indices)
        audits.append(
            AfoChainInputAudit(
                chain_id=chain_id,
                role=role,
                sequence_length=len(sequence),
                sequence_sha256=_sequence_sha256(sequence),
                unpaired_msa_depth=_a3m_depth(unpaired),
                paired_msa_depth=_a3m_depth(paired),
                template_count=len(templates),
                template_source=(
                    "afo-native-local-datapipeline"
                    if role == "target"
                    else "boltzgen-stage1-vhh"
                ),
                mapped_residues=len(mapped_query_indices),
            )
        )
    audit = AfoFinalInputAudit(
        input_json_sha256=sha256_file(input_json),
        model_seeds=tuple(int(seed) for seed in seeds),
        chains=tuple(audits),
    )
    if output_path.exists():
        existing = AfoFinalInputAudit.model_validate_json(
            output_path.read_text(encoding="utf-8")
        )
        if existing != audit:
            raise ManifestStateError("最终 AFO input audit 已存在但身份不一致")
    else:
        dump_model(audit, output_path)
    return audit
