"""Manifest-verified pilot and final structures for the read-only local viewer."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from easydesign.core import RunManifest, StageManifest, load_model
from easydesign.safe_writes import read_last_text_line
from easydesign.stages.s04_pilot_generation import CandidateIndex, CandidateRecord
from easydesign.stages.s07_final_filtering_and_selection import (
    FinalCandidatePackage,
    FinalCandidatePackageV0_2,
)


class EvidenceStructure(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
    label: str = Field(min_length=1, max_length=256)
    kind: Literal["pilot-representative", "final-selection"]
    strategy_id: str
    structure_url: str = Field(pattern=r"^/evidence-structures/[A-Za-z0-9._-]+\.cif$")
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class EvidenceViewerOverlay(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["0.1"] = "0.1"
    structures: tuple[EvidenceStructure, ...]


@dataclass(frozen=True, slots=True)
class EvidenceViewerPayload:
    overlay: EvidenceViewerOverlay
    files: dict[str, Path]


def _latest_run(root: Path) -> RunManifest:
    name = read_last_text_line(root / "manifests/LATEST")
    return load_model(root / "manifests" / name, RunManifest)


def _stage(root: Path, run: RunManifest, stage_id: str) -> StageManifest | None:
    reference = next(
        (item for item in run.stage_manifest_refs if item.producer_stage == stage_id),
        None,
    )
    return None if reference is None else load_model(reference.verify(root), StageManifest)


def build_evidence_viewer_payload(run_root: Path) -> EvidenceViewerPayload | None:
    """Expose only structures whose ArtifactRef checksums verify in this run."""

    root = run_root.resolve()
    run = _latest_run(root)
    structures: list[EvidenceStructure] = []
    files: dict[str, Path] = {}

    stage04 = _stage(root, run, "04-pilot-generation")
    if stage04 is not None:
        index = load_model(stage04.require_output("candidate-index").verify(root), CandidateIndex)
        first_by_strategy: dict[str, CandidateRecord] = {}
        for candidate in index.candidates:
            first_by_strategy.setdefault(candidate.strategy_id, candidate)
        for candidate in first_by_strategy.values():
            path = candidate.refolded_structure.verify(root)
            url = f"/evidence-structures/pilot-{candidate.candidate_id}.cif"
            structures.append(
                EvidenceStructure(
                    id=f"pilot-{candidate.candidate_id}",
                    label=f"Pilot · {candidate.strategy_id}",
                    kind="pilot-representative",
                    strategy_id=candidate.strategy_id,
                    structure_url=url,
                    sha256=candidate.refolded_structure.sha256,
                )
            )
            files[url] = path

    stage07 = _stage(root, run, "07-final-filtering-and-selection")
    if stage07 is not None:
        package_ref = stage07.require_output("final-candidate-package")
        package_path = package_ref.verify(root)
        schema = json.loads(package_path.read_text(encoding="utf-8")).get("schema_version")
        package: FinalCandidatePackage | FinalCandidatePackageV0_2
        if schema == "0.2":
            package = load_model(package_path, FinalCandidatePackageV0_2)
        else:
            package = load_model(package_path, FinalCandidatePackage)
        for final_candidate in (*package.primary, *package.backup):
            reference = final_candidate.prediction_structures[0]
            path = reference.verify(root)
            url = f"/evidence-structures/final-{final_candidate.candidate_id}.cif"
            structures.append(
                EvidenceStructure(
                    id=f"final-{final_candidate.candidate_id}",
                    label=(
                        f"Final {final_candidate.selection.selection_class} "
                        f"#{final_candidate.selection.selection_rank} · "
                        f"{final_candidate.candidate_id}"
                    ),
                    kind="final-selection",
                    strategy_id=final_candidate.strategy_id,
                    structure_url=url,
                    sha256=reference.sha256,
                )
            )
            files[url] = path

    if not structures:
        return None
    return EvidenceViewerPayload(
        overlay=EvidenceViewerOverlay(structures=tuple(structures)),
        files=files,
    )


__all__ = [
    "EvidenceStructure",
    "EvidenceViewerOverlay",
    "EvidenceViewerPayload",
    "build_evidence_viewer_payload",
]
