"""Strict BoltzGen candidate collection without mutating backend outputs."""

from __future__ import annotations

import csv
import math
from pathlib import Path

from easydesign.core import ArtifactRef, ManifestStateError

from .models import CandidateRecord, MetricValue

STAGE_ID = "04-pilot-generation"


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
    stage_attempt_id: str,
) -> ArtifactRef:
    return ArtifactRef.from_file(
        run_root=run_root,
        relative_path=path.relative_to(run_root).as_posix(),
        artifact_id=artifact_id,
        role=role,
        file_format="mmcif",
        producer_stage=STAGE_ID,
        producer_attempt=stage_attempt_id,
    )


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
        if (
            not original.is_file()
            or original.stat().st_size == 0
            or not refolded.is_file()
            or refolded.stat().st_size == 0
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
                    stage_attempt_id=stage_attempt_id,
                ),
                refolded_structure=_artifact(
                    run_root,
                    refolded,
                    artifact_id=f"{candidate_id}-refolded",
                    role="boltzgen-refolded-complex",
                    stage_attempt_id=stage_attempt_id,
                ),
                metrics=metrics,
                pass_filters=pass_filters,
            )
        )
        if len(collected) == maximum_candidates:
            break
    return tuple(collected)
