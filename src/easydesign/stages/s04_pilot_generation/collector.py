"""Strict BoltzGen candidate collection without mutating backend outputs."""

from __future__ import annotations

import csv
import math
from pathlib import Path

import gemmi
import numpy as np

from easydesign.core import ArtifactRef, ManifestStateError

from .models import CandidateRecord, MetricValue

STAGE_ID = "04-pilot-generation"
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


def _metric_scalar(value: str) -> MetricValue:
    normalized = value.strip()
    if not normalized:
        return None
    lowered = normalized.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    if lowered in {"nan", "na", "n/a", "none", "null"}:
        return None
    try:
        integer = int(normalized)
    except ValueError:
        try:
            floating = float(normalized)
        except ValueError:
            return normalized
        return None if not math.isfinite(floating) else floating
    return integer


def _artifact(
    run_root: Path,
    path: Path,
    *,
    artifact_id: str,
    role: str,
    file_format: str,
    stage_attempt_id: str,
    producer_stage: str,
) -> ArtifactRef:
    return ArtifactRef.from_file(
        run_root=run_root,
        relative_path=path.relative_to(run_root).as_posix(),
        artifact_id=artifact_id,
        role=role,
        file_format=file_format,
        producer_stage=producer_stage,
        producer_attempt=stage_attempt_id,
    )


def _chain_sequences(path: Path) -> tuple[tuple[str, str], ...]:
    try:
        structure = gemmi.read_structure(str(path))
    except (RuntimeError, ValueError) as error:
        raise ManifestStateError(f"BoltzGen candidate CIF 无法解析: {path}") from error
    if len(structure) != 1:
        raise ManifestStateError(f"BoltzGen candidate 必须恰好一个 model: {path}")
    chains: list[tuple[str, str]] = []
    for chain in structure[0]:
        sequence = "".join(
            _PROTEIN_RESIDUES[residue.name.upper()]
            for residue in chain
            if residue.name.upper() in _PROTEIN_RESIDUES
        )
        if sequence:
            chains.append((chain.name, sequence))
    if len(chains) < 2:
        raise ManifestStateError(f"BoltzGen candidate 缺少 target/binder protein chain: {path}")
    return tuple(chains)


def _design_mask_evidence(
    *,
    structure_path: Path,
    mask_path: Path,
    designed_chain_sequence: str,
    designed_sequence: str,
    expected_design_count: int | None,
) -> tuple[int, ...]:
    """Recover exact binder design identities from BoltzGen's official token mask."""

    try:
        with np.load(mask_path, allow_pickle=False) as payload:
            if "design_mask" not in payload.files:
                raise ManifestStateError(f"BoltzGen NPZ 缺少 design_mask: {mask_path}")
            mask = np.asarray(payload["design_mask"], dtype=np.float64).reshape(-1)
    except (OSError, ValueError) as error:
        raise ManifestStateError(f"BoltzGen design mask 无法读取: {mask_path}") from error
    if not np.isin(mask, (0.0, 1.0)).all():
        raise ManifestStateError(f"BoltzGen design_mask 不是二值 mask: {mask_path}")

    chains = _chain_sequences(structure_path)
    matching_binders = [
        index
        for index, (_, sequence) in enumerate(chains)
        if sequence == designed_chain_sequence
    ]
    if len(matching_binders) != 1:
        raise ManifestStateError(
            "designed_chain_sequence 无法唯一映射到 candidate chain: "
            f"matches={len(matching_binders)}"
        )
    binder_index = matching_binders[0]
    token_count = sum(len(sequence) for _, sequence in chains)
    if len(mask) != token_count:
        raise ManifestStateError(
            f"design_mask token 数与 candidate residue 数不一致: {len(mask)} != {token_count}"
        )
    offsets: list[int] = []
    current = 0
    for _, sequence in chains:
        offsets.append(current)
        current += len(sequence)
    binder_start = offsets[binder_index]
    binder_end = binder_start + len(designed_chain_sequence)
    outside = np.concatenate((mask[:binder_start], mask[binder_end:]))
    if bool(outside.any()):
        raise ManifestStateError("基础 VHH candidate 在 binder 之外出现 designed residue")
    binder_mask = mask[binder_start:binder_end].astype(bool)
    residue_ids = tuple(int(index) + 1 for index in np.flatnonzero(binder_mask))
    if not residue_ids:
        raise ManifestStateError("BoltzGen design_mask 没有 binder designed residue")
    if expected_design_count is not None and len(residue_ids) != expected_design_count:
        raise ManifestStateError(
            "BoltzGen design_mask 与 num_design 不一致: "
            f"{len(residue_ids)} != {expected_design_count}"
        )
    recovered = "".join(designed_chain_sequence[index - 1] for index in residue_ids)
    if recovered != designed_sequence:
        raise ManifestStateError(
            "BoltzGen design_mask 与 designed_sequence 不一致，不能建立 CDR identity"
        )
    return residue_ids


def collect_boltzgen_candidates(
    *,
    run_root: Path,
    backend_output: Path,
    strategy_id: str,
    task_id: str,
    task_attempt_number: int,
    stage_attempt_id: str,
    ordinal_start: int,
    maximum_candidates: int,
    producer_stage: str = STAGE_ID,
) -> tuple[CandidateRecord, ...]:
    """Collect only candidates with metric row + original CIF + refold CIF."""

    metrics_path = backend_output / "final_ranked_designs" / "all_designs_metrics.csv"
    if not metrics_path.is_file():
        return ()
    try:
        with metrics_path.open("r", encoding="utf-8", newline="") as handle:
            rows = tuple(csv.DictReader(handle))
    except (OSError, UnicodeDecodeError, csv.Error) as error:
        raise ManifestStateError(f"BoltzGen candidate metrics 无法读取: {metrics_path}") from error
    if not rows or maximum_candidates < 1:
        return ()
    seen_backend_ids: set[str] = set()
    collected: list[CandidateRecord] = []
    for row in rows:
        backend_id = (row.get("id") or "").strip()
        file_name = (row.get("file_name") or "").strip()
        if not backend_id or not file_name:
            continue
        if backend_id in seen_backend_ids:
            raise ManifestStateError(f"BoltzGen metrics candidate id 重复: {backend_id}")
        seen_backend_ids.add(backend_id)
        if Path(file_name).name != file_name or not file_name.endswith(".cif"):
            raise ManifestStateError(f"BoltzGen candidate file_name 不安全或非 CIF: {file_name}")
        original = backend_output / "intermediate_designs_inverse_folded" / file_name
        refolded = backend_output / "intermediate_designs_inverse_folded" / "refold_cif" / file_name
        design_mask_source = original.with_suffix(".npz")
        if (
            not original.is_file()
            or original.stat().st_size == 0
            or not refolded.is_file()
            or refolded.stat().st_size == 0
            or not design_mask_source.is_file()
            or design_mask_source.stat().st_size == 0
        ):
            continue
        ordinal = ordinal_start + len(collected)
        candidate_id = f"{strategy_id}-candidate-{ordinal:04d}"
        metrics = {
            key: _metric_scalar(value)
            for key, value in row.items()
            if key is not None and value is not None
        }
        pass_value = metrics.get("pass_filters")
        pass_filters = pass_value if isinstance(pass_value, bool) else None
        full_sequence = metrics.get("designed_chain_sequence")
        designed_sequence = metrics.get("designed_sequence")
        design_count_value = metrics.get("num_design")
        if not isinstance(full_sequence, str) or not isinstance(designed_sequence, str):
            raise ManifestStateError(
                f"BoltzGen candidate={backend_id} 缺少 sequence/design mask 对照"
            )
        expected_design_count = (
            design_count_value
            if isinstance(design_count_value, int)
            and not isinstance(design_count_value, bool)
            else None
        )
        designed_residue_ids = _design_mask_evidence(
            structure_path=original,
            mask_path=design_mask_source,
            designed_chain_sequence=full_sequence,
            designed_sequence=designed_sequence,
            expected_design_count=expected_design_count,
        )
        collected.append(
            CandidateRecord(
                candidate_id=candidate_id,
                backend_candidate_id=backend_id,
                strategy_id=strategy_id,
                task_id=task_id,
                task_attempt_number=task_attempt_number,
                ordinal_within_strategy=ordinal,
                original_structure=_artifact(
                    run_root,
                    original,
                    artifact_id=f"{candidate_id}-original",
                    role="boltzgen-original-complex",
                    file_format="mmcif",
                    stage_attempt_id=stage_attempt_id,
                    producer_stage=producer_stage,
                ),
                refolded_structure=_artifact(
                    run_root,
                    refolded,
                    artifact_id=f"{candidate_id}-refolded",
                    role="boltzgen-refolded-complex",
                    file_format="mmcif",
                    stage_attempt_id=stage_attempt_id,
                    producer_stage=producer_stage,
                ),
                design_mask_source=_artifact(
                    run_root,
                    design_mask_source,
                    artifact_id=f"{candidate_id}-design-mask",
                    role="boltzgen-design-mask",
                    file_format="npz",
                    stage_attempt_id=stage_attempt_id,
                    producer_stage=producer_stage,
                ),
                designed_binder_residue_ids=designed_residue_ids,
                metrics=metrics,
                pass_filters=pass_filters,
            )
        )
        if len(collected) == maximum_candidates:
            break
    return tuple(collected)
