"""Thin orchestration for one GPCR-aware Stage 02 analysis."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, cast

import yaml  # type: ignore[import-untyped]
from pydantic import BaseModel, ConfigDict

from easydesign.backends.gpcrdb import GpcrdbAdapter
from easydesign.backends.target_sources.remote import ScientificHttpClient
from easydesign.core import (
    BackendContractError,
    ContractError,
    ExecutionStatus,
    RunManifest,
    StageManifest,
    load_model,
    sha256_file,
)
from easydesign.orchestration.config import Stage02Config, load_run_config
from easydesign.orchestration.local_project import project_config_path
from easydesign.reporting.gpcr_site_review import (
    generate_review_report,
    validate_review_report,
)
from easydesign.safe_writes import append_pointer_revision, read_last_text_line
from easydesign.stages.s01_target_preparation import (
    ResidueMapping,
    ResidueMappingEntry,
    TargetBundle,
)
from easydesign.stages.s02_hotspot_discovery.gpcr import (
    GpcrSiteAnalysis,
    StructureAnalysisError,
    analyze_structure,
    generate_candidates,
    parse_structure,
)

from .research import project_status

PDB_CODE_RE = re.compile(r"(?:^|[^A-Za-z0-9])(?P<code>[0-9][A-Za-z0-9]{3})(?:[^A-Za-z0-9]|$)")
MODES = frozenset({"both", "inhibit", "activate"})
ACCESS_SIDES = frozenset({"extracellular", "intracellular", "both"})
APPROACH_CLEARANCE = frozenset({"pass", "fail", "unresolved"})
CONFIDENCE_BY_TIER = {
    "T1": "high",
    "T2": "medium",
    "T3": "low",
    "T4": "low",
    "UNRESOLVED": "unresolved",
}
GPCR_SITE_DIRECTORY = "gpcr-site"
GPCR_SITE_POINTER = "LATEST"
ANALYSIS_MANIFEST_SCHEMA = "gpcr-site-analysis-manifest-v1"
SELECTION_SCHEMA = "gpcr-site-selection-v1"
PROVIDER_RESOLUTION_SCHEMA = "gpcr-provider-resolution-v1"


class AnalysisWorkflowError(ContractError):
    """Raised when an input cannot be converted into an auditable dossier."""


@dataclass(frozen=True, slots=True)
class GpcrSiteRequest:
    evidence_dir: Path
    structure: Path | None = None
    mode: str = "both"
    gpcr_entry: str | None = None
    accession: str | None = None
    receptor_chain: str | None = None
    selection: Path | None = None
    project: Path | None = None
    membrane_orientation: Path | None = None
    state: str | None = None
    cache_mode: str = "online"
    cache_root: Path | None = None
    strict_gpcrdb: bool = False


AnalyzeRequest = GpcrSiteRequest


class GpcrPrepareContext(BaseModel):
    """Verified prepare-phase inputs used by the GPCR analyzer."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    project_status: dict[str, Any]
    project_path: Path
    run_root: Path
    run_manifest: Path
    run_manifest_sha256: str
    stage01_manifest: Path
    stage01_manifest_sha256: str
    target_bundle: Path
    target_bundle_sha256: str
    target_structure: Path
    target_structure_sha256: str
    source_context: Path | None
    source_context_sha256: str | None
    analysis_structure: Path
    analysis_structure_sha256: str
    analysis_structure_role: str
    receptor_chain: str
    residue_mapping: Path
    residue_mapping_sha256: str
    residue_mapping_entries: tuple[dict[str, Any], ...]
    coordinate_model_ids: tuple[str, ...]
    representative_model_id: str | None
    source_pdb_code: str | None = None
    source_accession: str | None = None


@dataclass(frozen=True, slots=True)
class PublishedGpcrAnalysis:
    analysis_root: Path
    manifest_path: Path
    analysis_path: Path
    handoff_path: Path
    context_path: Path
    selection_path: Path
    report_root: Path
    revision: int


@dataclass(frozen=True, slots=True)
class GpcrProviderResolution:
    provider: str
    status: str
    reason: str
    evidence_dir: Path
    request_path: Path | None = None
    gpcr_entry: str | None = None
    accession: str | None = None
    pdb_code: str | None = None


def load_document(path: Path) -> Any:
    """Load a declared JSON/YAML input without searching adjacent files."""

    if not path.is_file():
        raise AnalysisWorkflowError(f"declared input does not exist: {path}")
    try:
        text = path.read_text(encoding="utf-8")
        if path.suffix.lower() in {".yaml", ".yml"}:
            return yaml.safe_load(text)
        return json.loads(text)
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise AnalysisWorkflowError(f"cannot parse input {path}: {error}") from error


def _mapping(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise AnalysisWorkflowError(f"{label} must be an object")
    return value


def _rows(value: object, label: str) -> list[Mapping[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise AnalysisWorkflowError(f"{label} must be an array")
    return [_mapping(item, f"{label}[{index}]") for index, item in enumerate(value)]


def _run_root_from_manifest(path: Path) -> Path:
    manifest = path.resolve(strict=True)
    if manifest.parent.name != "manifests":
        raise AnalysisWorkflowError(
            f"project status returned an unexpected run manifest path: {manifest}"
        )
    return manifest.parent.parent


def resolve_gpcr_prepare_context(
    project: Path,
    structure_path: Path | None = None,
) -> GpcrPrepareContext:
    """Resolve prepare inputs through typed manifests without a CLI subprocess.

    ``source-context`` is preferred because GPCR partner, ligand and fusion
    interpretation requires the deposited complex.  ``target-structure`` remains
    the canonical receptor-only coordinate source used by downstream design.
    """

    project_root = project.expanduser().resolve(strict=True)
    status = project_status(project_root)
    if status.status == "legacy-stage-project":
        raise AnalysisWorkflowError(
            "legacy-stage-project is read-only and cannot supply a GPCR dossier"
        )

    selected: tuple[Path, Path, Path, RunManifest, StageManifest] | None = None
    for evidence in reversed(status.evidence):
        if evidence.path is None or evidence.kind not in {
            "target-foundation",
            "site-foundation",
        }:
            continue
        run_manifest_path = evidence.path.expanduser().resolve(strict=True)
        run_root = _run_root_from_manifest(run_manifest_path)
        run_manifest = load_model(run_manifest_path, RunManifest)
        stage_ref = next(
            (
                item
                for item in run_manifest.stage_manifest_refs
                if item.producer_stage == "01-target-preparation"
            ),
            None,
        )
        if stage_ref is None:
            continue
        stage_path = stage_ref.verify(run_root)
        stage_manifest = load_model(stage_path, StageManifest)
        if (
            stage_manifest.stage_id == "01-target-preparation"
            and stage_manifest.status is ExecutionStatus.SUCCEEDED
        ):
            selected = (
                run_root,
                run_manifest_path,
                stage_path,
                run_manifest,
                stage_manifest,
            )
            break
    if selected is None:
        raise AnalysisWorkflowError(
            "project status does not declare a succeeded prepare target foundation"
        )

    run_root, run_manifest_path, stage_path, _, stage_manifest = selected
    stage_ref = next(
        (
            item
            for item in stage_manifest.output_artifacts
            if item.artifact_id == "target-bundle"
        ),
        None,
    )
    if stage_ref is None:
        raise AnalysisWorkflowError(
            "prepare target foundation does not declare the target-bundle artifact"
        )
    bundle_path = stage_ref.verify(run_root)
    bundle = load_model(bundle_path, TargetBundle)
    target_path = bundle.target_structure.verify(run_root)
    mapping_path = bundle.residue_mapping.verify(run_root)
    mapping = load_model(mapping_path, ResidueMapping)
    source_path = (
        None if bundle.source_context is None else bundle.source_context.verify(run_root)
    )

    declared: list[tuple[str, Path, str]] = [
        ("canonical-target", target_path, bundle.target_structure.sha256)
    ]
    if source_path is not None and bundle.source_context is not None:
        declared.append(("source-context", source_path, bundle.source_context.sha256))
    if structure_path is None:
        structure_role, analysis_path, analysis_sha = declared[-1]
    else:
        supplied = structure_path.expanduser().resolve(strict=True)
        supplied_sha = sha256_file(supplied)
        matches = [item for item in declared if item[2] == supplied_sha]
        if len(matches) != 1:
            raise AnalysisWorkflowError(
                "--structure must match the prepare target_structure or source_context "
                "SHA-256"
            )
        structure_role, _, analysis_sha = matches[0]
        analysis_path = supplied

    if structure_role == "source-context":
        chains = {
            item.source_author_chain_id or item.author_chain_id
            for item in mapping.entries
        }
    else:
        chains = {item.author_chain_id for item in mapping.entries}
    if len(chains) != 1:
        raise AnalysisWorkflowError(
            "prepare residue mapping does not resolve one receptor chain: "
            f"{sorted(chains)}"
        )
    receptor_chain = next(iter(chains))
    ensemble = bundle.coordinate_ensemble
    project_config = load_run_config(
        project_config_path(project_root), source_base_dir=project_root
    ).config
    source: Any = project_config.stage01.target.source
    source_pdb_code = (
        str(source.pdb_id).upper() if source.type == "pdb-id" else None
    )
    source_accession = (
        str(source.accession).upper() if source.type == "uniprot" else None
    )
    return GpcrPrepareContext(
        project_status=status.model_dump(mode="json"),
        project_path=project_root,
        run_root=run_root,
        run_manifest=run_manifest_path,
        run_manifest_sha256=sha256_file(run_manifest_path),
        stage01_manifest=stage_path,
        stage01_manifest_sha256=sha256_file(stage_path),
        target_bundle=bundle_path,
        target_bundle_sha256=sha256_file(bundle_path),
        target_structure=target_path,
        target_structure_sha256=bundle.target_structure.sha256,
        source_context=source_path,
        source_context_sha256=(
            None if bundle.source_context is None else bundle.source_context.sha256
        ),
        analysis_structure=analysis_path,
        analysis_structure_sha256=analysis_sha,
        analysis_structure_role=structure_role,
        receptor_chain=receptor_chain,
        residue_mapping=mapping_path,
        residue_mapping_sha256=bundle.residue_mapping.sha256,
        residue_mapping_entries=tuple(
            item.model_dump(mode="python") for item in mapping.entries
        ),
        coordinate_model_ids=(
            () if ensemble is None else tuple(ensemble.model_ids)
        ),
        representative_model_id=(
            None if ensemble is None else ensemble.representative_model_id
        ),
        source_pdb_code=source_pdb_code,
        source_accession=source_accession,
    )


def _pdb_code(path: Path) -> str | None:
    match = PDB_CODE_RE.search(path.stem)
    return match.group("code").upper() if match else None


def _load_optional(path: Path | None, label: str) -> Mapping[str, Any] | None:
    if path is None:
        return None
    value = load_document(path)
    return dict(_mapping(value, label))


def _explicit_identifier(request: GpcrSiteRequest, structure: Path) -> bool:
    return bool(request.gpcr_entry or request.accession or _pdb_code(structure))


def _fallback_context(
    request: GpcrSiteRequest,
    structure: Path,
    error: BackendContractError,
    *,
    gpcr_entry: str | None = None,
    accession: str | None = None,
    pdb_code: str | None = None,
) -> dict[str, Any]:
    """Keep an explicit, visible failure while allowing geometry-only review."""

    resolved_entry = gpcr_entry or request.gpcr_entry
    resolved_accession = accession or request.accession
    if not (resolved_entry or resolved_accession):
        raise AnalysisWorkflowError(
            "GPCRdb could not resolve the structure identifier; provide --gpcr-entry or "
            "--accession instead of guessing from a local filename"
        ) from error
    entry = resolved_entry
    return {
        "schema_version": "gpcr-receptor-context-v1",
        "identity": {
            "entry_name": entry,
            "accession": resolved_accession,
            "pdb_code": pdb_code or _pdb_code(structure),
            "preferred_chain": request.receptor_chain,
        },
        "receptor": None,
        "family": {
            "slug": None,
            "record": None,
            "class": None,
            "numbering_scheme": None,
        },
        "topology": {"residues": None, "source": None},
        "state": {"selected": None, "source": None},
        "structures": {"selected": None, "representative_by_state": None},
        "interactions": {"ligand": None, "peptide": None, "gprotein": None},
        "ligands": None,
        "mutations": None,
        "warnings": [
            {
                "code": "gpcrdb_unavailable_geometry_only",
                "message": str(error),
                "error": {
                    "type": type(error).__name__,
                    "message": str(error),
                },
            }
        ],
        "provenance": [
            {
                "source": "GPCRdb",
                "status": "failed",
                "error_type": type(error).__name__,
                "message": str(error),
            }
        ],
    }


def _choose_chain(path: Path, requested: str | None, preferred: str | None) -> str:
    parsed = parse_structure(path)
    polymer = parsed.chain_ids(polymer_only=True)
    if requested:
        if requested not in polymer:
            raise AnalysisWorkflowError(
                f"receptor chain {requested!r} is absent; available polymer chains: {polymer}"
            )
        return requested
    if preferred and preferred in polymer:
        return preferred
    if len(polymer) == 1:
        return polymer[0]
    raise AnalysisWorkflowError(
        "multiple polymer chains are present; pass --receptor-chain explicitly "
        f"(available: {polymer})"
    )


def _selection_key(value: Mapping[str, Any]) -> str | None:
    if isinstance(value.get("key"), str) and value.get("key"):
        return str(value["key"])
    chain = value.get("chain_id", value.get("auth_chain", value.get("chain")))
    seq = value.get("auth_seq_id", value.get("seq_num", value.get("number")))
    if chain in (None, "") or seq in (None, ""):
        return None
    model = str(value.get("model_id", "1"))
    hetero = str(value.get("hetero_flag", "ATOM"))
    insertion = str(value.get("insertion_code", ""))
    label_chain = value.get("label_chain_id")
    label_seq = value.get("label_seq_id")
    suffix = ""
    if label_chain is not None or label_seq is not None:
        suffix = f"|{label_chain or ''}:{label_seq if label_seq is not None else ''}"
    return f"{model}|{chain}|{hetero}|{int(seq)}{insertion}{suffix}"


def _normalize_selection(path: Path | None, parsed: Any) -> Mapping[str, Any] | None:
    if path is None:
        return None
    raw = _mapping(load_document(path), "selection")
    valid = {residue.identity.key() for residue in parsed.residues}
    normalized: dict[str, Any] = {"include": [], "exclude": []}
    for label in normalized:
        values = raw.get(label, raw.get(f"{label}_residues", []))
        if isinstance(values, Mapping):
            values = [values]
        if not isinstance(values, Sequence) or isinstance(values, (str, bytes, bytearray)):
            raise AnalysisWorkflowError(f"selection.{label} must be an array")
        for item in values:
            if isinstance(item, str):
                resolved_key: str | None = item
            else:
                resolved_key = _selection_key(_mapping(item, f"selection.{label} item"))
            if not resolved_key:
                raise AnalysisWorkflowError(f"selection.{label} contains an unmappable residue")
            if resolved_key not in valid:
                raise AnalysisWorkflowError(
                    f"selection residue is not present in structure: {resolved_key}"
                )
            normalized[label].append(resolved_key)
    for key in ("allow_intracellular", "notes"):
        if key in raw:
            normalized[key] = raw[key]
    review_value = raw.get("review_context")
    if review_value is not None:
        review = _mapping(review_value, "selection.review_context")
        binder_format = str(review.get("binder_format") or "").strip()
        access_side = str(review.get("access_side") or "").strip().lower()
        if access_side and access_side not in ACCESS_SIDES:
            raise AnalysisWorkflowError(
                f"selection.review_context.access_side must be one of {sorted(ACCESS_SIDES)}"
            )
        modes_value = review.get("modes", {})
        modes = _mapping(modes_value, "selection.review_context.modes")
        normalized_modes: dict[str, Any] = {}
        for candidate_mode in ("inhibit", "activate"):
            if candidate_mode not in modes:
                continue
            mode_value = _mapping(
                modes[candidate_mode],
                f"selection.review_context.modes.{candidate_mode}",
            )
            assays_value = mode_value.get("assays", [])
            if not isinstance(assays_value, Sequence) or isinstance(
                assays_value, (str, bytes, bytearray)
            ):
                raise AnalysisWorkflowError(
                    f"selection.review_context.modes.{candidate_mode}.assays must be an array"
                )
            clearance = str(mode_value.get("approach_clearance") or "").strip().lower()
            if clearance and clearance not in APPROACH_CLEARANCE:
                raise AnalysisWorkflowError(
                    "selection.review_context.modes."
                    f"{candidate_mode}.approach_clearance must be one of "
                    f"{sorted(APPROACH_CLEARANCE)}"
                )
            normalized_modes[candidate_mode] = {
                "target_state": str(mode_value.get("target_state") or "").strip() or None,
                "counterstate": str(mode_value.get("counterstate") or "").strip() or None,
                "assays": [str(value).strip() for value in assays_value if str(value).strip()],
                "falsifier": str(mode_value.get("falsifier") or "").strip() or None,
                "approach_clearance": clearance or "unresolved",
                "allow_deep_cavity": bool(mode_value.get("allow_deep_cavity", False)),
            }
        normalized["review_context"] = {
            "binder_format": binder_format or None,
            "access_side": access_side or None,
            "modes": normalized_modes,
        }
    return normalized


def _review_context_summary(
    selection: Mapping[str, Any] | None, requested_mode: str
) -> dict[str, Any]:
    review = (
        selection.get("review_context")
        if isinstance(selection, Mapping)
        and isinstance(selection.get("review_context"), Mapping)
        else {}
    )
    review_mapping = dict(review) if isinstance(review, Mapping) else {}
    binder_format = review_mapping.get("binder_format")
    access_side = review_mapping.get("access_side")
    modes_value = review_mapping.get("modes")
    modes_mapping = modes_value if isinstance(modes_value, Mapping) else {}
    requested = ("inhibit", "activate") if requested_mode == "both" else (requested_mode,)
    mode_summaries: dict[str, Any] = {}
    for candidate_mode in requested:
        value = modes_mapping.get(candidate_mode)
        mode_context = dict(value) if isinstance(value, Mapping) else {}
        missing: list[str] = []
        if not binder_format:
            missing.append("binder_format")
        if not access_side:
            missing.append("access_side")
        for field in ("target_state", "counterstate", "falsifier"):
            if not mode_context.get(field):
                missing.append(field)
        assays = mode_context.get("assays")
        if not isinstance(assays, Sequence) or isinstance(assays, (str, bytes)) or not assays:
            missing.append("assays")
        if mode_context.get("approach_clearance") != "pass":
            missing.append("approach_clearance=pass")
        mode_summaries[candidate_mode] = {
            **mode_context,
            "binder_format": binder_format,
            "access_side": access_side,
            "status": "resolved" if not missing else "unresolved",
            "missing": missing,
        }
    return {
        "status": (
            "resolved"
            if mode_summaries
            and all(value["status"] == "resolved" for value in mode_summaries.values())
            else "unresolved"
        ),
        "selection_supplied": selection is not None,
        "modes": mode_summaries,
    }


def _identity_context(context: Mapping[str, Any], receptor_chain: str) -> dict[str, Any]:
    raw_identity = _mapping(context.get("identity", {}), "GPCRdb identity")
    receptor = context.get("receptor")
    receptor_obj = _mapping(receptor, "GPCRdb receptor") if isinstance(receptor, Mapping) else {}
    family = _mapping(context.get("family", {}), "GPCRdb family")
    family_record = family.get("record")
    family_obj = (
        _mapping(family_record, "GPCRdb family record")
        if isinstance(family_record, Mapping)
        else {}
    )
    entry = raw_identity.get("entry_name") or receptor_obj.get("entry_name")
    accession = raw_identity.get("accession") or receptor_obj.get("accession")
    return {
        "entry_name": entry,
        "accession": accession,
        "receptor_class": family.get("class") or receptor_obj.get("class"),
        "receptor_family": receptor_obj.get("family") or family.get("slug"),
        "family_name": family_obj.get("name") or family.get("slug"),
        "subfamily": receptor_obj.get("subfamily"),
        "numbering_scheme": family.get("numbering_scheme")
        or receptor_obj.get("residue_numbering_scheme"),
        "receptor_chain": receptor_chain,
        "source": "GPCRdb" if receptor_obj else "user identifier / geometry-only fallback",
        "confidence": "high" if receptor_obj else "low",
    }


def _state_context(context: Mapping[str, Any], override: str | None) -> dict[str, Any]:
    state = _mapping(context.get("state", {}), "GPCRdb state")
    if override:
        return {
            "label": override.lower(),
            "source": "user_manifest",
            "confidence": "explicit-input",
            "note": "state override is not evidence that ligand function is causal",
        }
    value = state.get("selected")
    return {
        "label": str(value).lower() if value else "unknown",
        "source": state.get("source"),
        "confidence": "medium" if value else "unresolved",
        "note": "GPCRdb structure state is a conformation annotation, not a hotspot proof",
    }


def _region_indexes(
    analysis: Mapping[str, Any],
) -> tuple[dict[str, Mapping[str, Any]], dict[str, Mapping[str, Any]]]:
    by_key: dict[str, Mapping[str, Any]] = {}
    topology_by_key: dict[str, Mapping[str, Any]] = {}
    for raw in analysis.get("residue_regions", []):
        if not isinstance(raw, Mapping) or not isinstance(raw.get("residue"), Mapping):
            continue
        residue = raw["residue"]
        key = residue.get("key")
        if isinstance(key, str):
            by_key[key] = raw
    topology = _mapping(analysis.get("topology", {}), "topology")
    for raw in topology.get("residues", []):
        if not isinstance(raw, Mapping) or not isinstance(raw.get("residue"), Mapping):
            continue
        residue = raw["residue"]
        key = residue.get("key")
        if isinstance(key, str):
            topology_by_key[key] = raw
    return by_key, topology_by_key


def _project_mapping_index(
    project_context: Mapping[str, Any] | None,
) -> dict[tuple[str, str, str], Mapping[str, Any]]:
    if not project_context:
        return {}
    result: dict[tuple[str, str, str], Mapping[str, Any]] = {}
    for raw in project_context.get("residue_mapping_entries", []):
        if not isinstance(raw, Mapping):
            continue
        key = (
            str(raw.get("author_chain_id", "")),
            str(raw.get("author_residue_id", "")),
            str(raw.get("insertion_code") or ""),
        )
        result[key] = raw
    return result


def _enrich_residue(
    raw: Mapping[str, Any],
    region_index: Mapping[str, Mapping[str, Any]],
    topology_index: Mapping[str, Mapping[str, Any]],
    project_index: Mapping[tuple[str, str, str], Mapping[str, Any]],
) -> dict[str, Any]:
    nested = raw.get("residue") if isinstance(raw.get("residue"), Mapping) else raw
    value = dict(_mapping(nested, "candidate residue"))
    key = value.get("key")
    region = region_index.get(str(key)) if key else None
    topo = topology_index.get(str(key)) if key else None
    if region:
        for field in (
            "resname",
            "amino_acid",
            "protein_segment",
            "generic_number",
            "region",
            "pore_lining",
            "axial_distance",
            "radial_distance",
        ):
            if field in region and field not in value:
                value[field] = region[field]
    if topo:
        for field in ("protein_segment", "generic_number", "sequence_number", "amino_acid"):
            if field in topo and field not in value:
                value[field] = topo[field]
    value["gpcrdb_generic_number"] = value.get("generic_number")
    value["segment"] = value.get("protein_segment")
    author_key = (
        str(value.get("chain_id", "")),
        str(value.get("auth_seq_id", "")),
        str(value.get("insertion_code") or ""),
    )
    mapping = project_index.get(author_key)
    if mapping:
        value.update(
            {
                "label_chain_id": mapping.get("label_chain_id"),
                "label_seq_id": mapping.get("label_seq_id"),
                "sequence_index": mapping.get("sequence_index"),
                "mapping_source": "EasyDesign prepare ResidueMapping",
            }
        )
    return value


def _confidence(row: Mapping[str, Any]) -> str:
    explicit = row.get("confidence")
    if explicit:
        return str(explicit)
    return CONFIDENCE_BY_TIER.get(str(row.get("evidence_tier", "UNRESOLVED")), "unresolved")


def _normalise_candidates(
    raw: Mapping[str, Any],
    analysis: Mapping[str, Any],
    mode: str,
    project_context: Mapping[str, Any] | None,
    decision_context: Mapping[str, Any] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    region_index, topology_index = _region_indexes(analysis)
    project_index = _project_mapping_index(project_context)
    membrane = _mapping(analysis.get("membrane", {}), "membrane")
    direction = membrane.get("extracellular_axis") if membrane.get("reliable") else None
    direction_label = "unresolved"
    if isinstance(direction, Sequence) and not isinstance(direction, (str, bytes, bytearray)):
        direction_label = (
            "extracellular ["
            + ", ".join(f"{float(component):.3f}" for component in direction)
            + "]"
        )
    output: dict[str, list[dict[str, Any]]] = {"inhibit": [], "activate": []}
    raw_candidates = _mapping(raw.get("candidates", {}), "candidate output")
    decision_modes_value = (
        decision_context.get("modes") if isinstance(decision_context, Mapping) else {}
    )
    decision_modes = decision_modes_value if isinstance(decision_modes_value, Mapping) else {}
    for candidate_mode in output:
        if mode == "inhibit" and candidate_mode != "inhibit":
            continue
        if mode == "activate" and candidate_mode != "activate":
            continue
        value = raw_candidates.get(candidate_mode, [])
        rows: list[Mapping[str, Any]] = []
        if isinstance(value, Mapping):
            for classification, children in value.items():
                if isinstance(children, Sequence) and not isinstance(
                    children, (str, bytes, bytearray)
                ):
                    rows.extend(
                        {**_mapping(child, "candidate"), "classification": str(classification)}
                        for child in children
                    )
        elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
            rows = [_mapping(child, "candidate") for child in value]
        mode_context_value = decision_modes.get(candidate_mode)
        mode_context = (
            dict(mode_context_value) if isinstance(mode_context_value, Mapping) else {}
        )
        for raw_row in rows:
            classification = str(
                raw_row.get("classification", raw_row.get("disposition", "unresolved"))
            )
            if classification not in {"primary", "backup", "avoid", "unresolved"}:
                classification = "unresolved"
            residues_value = raw_row.get("residues", [])
            residues = (
                [
                    _enrich_residue(
                        _mapping(item, "candidate residue"),
                        region_index,
                        topology_index,
                        project_index,
                    )
                    for item in residues_value
                    if isinstance(item, Mapping)
                ]
                if isinstance(residues_value, Sequence)
                and not isinstance(residues_value, (str, bytes, bytearray))
                else []
            )
            limitations = (
                [str(item) for item in raw_row.get("limitations", [])]
                if isinstance(raw_row.get("limitations"), Sequence)
                and not isinstance(raw_row.get("limitations"), (str, bytes, bytearray))
                else []
            )
            raw_risks = raw_row.get("risks", [])
            if isinstance(raw_risks, Sequence) and not isinstance(
                raw_risks, (str, bytes, bytearray)
            ):
                limitations.extend(str(item) for item in raw_risks)
            mismatch_count = sum(
                item.get("mapping_status") == "sequence_mismatch" for item in residues
            )
            if mismatch_count:
                limitations.append(
                    f"{mismatch_count} residue(s) have unresolved canonical/structure mismatch"
                )
            if not membrane.get("reliable") and classification == "primary":
                classification = "unresolved"
                limitations.append("membrane orientation is unresolved; primary is prohibited")
            evidence = raw_row.get("evidence", [])
            tiers = (
                [
                    str(item.get("tier"))
                    for item in evidence
                    if isinstance(item, Mapping) and item.get("tier")
                ]
                if isinstance(evidence, Sequence)
                and not isinstance(evidence, (str, bytes, bytearray))
                else []
            )
            tier = (
                min(tiers, key=lambda item: {"T1": 1, "T2": 2, "T3": 3, "T4": 4}.get(item, 99))
                if tiers
                else str(raw_row.get("evidence_tier", "UNRESOLVED"))
            )
            if tier.lower() == "unresolved":
                tier = "UNRESOLVED"
            role = raw_row.get("mechanism", raw_row.get("role", "unresolved"))
            approach = direction_label
            if role in {"intracellular-effector-face", "gprotein-is-not-dimer"}:
                approach = "intracellular; hard avoid for the default extracellular binder"
            deep_cavity = role == "core-pore-activation"
            binder_format = str(mode_context.get("binder_format") or "").strip().lower()
            access_side = str(mode_context.get("access_side") or "").strip().lower()
            clearance = str(mode_context.get("approach_clearance") or "unresolved").lower()
            approach_status = clearance if clearance in APPROACH_CLEARANCE else "unresolved"
            protein_formats = {
                "antibody",
                "binder",
                "nanobody",
                "protein",
                "scfv",
                "vhh",
            }
            if deep_cavity and access_side == "extracellular" and binder_format in protein_formats:
                if not bool(mode_context.get("allow_deep_cavity", False)):
                    approach_status = "fail"
                    limitations.append(
                        "deep 7TM cavity is not framework-accessible for the declared "
                        "extracellular protein binder without an explicit reviewed override"
                    )
            if mode_context.get("status") != "resolved":
                missing = mode_context.get("missing", [])
                missing_text = ", ".join(str(item) for item in missing) or "review context"
                limitations.append(f"decision context unresolved: {missing_text}")
            raw_hard_gates = raw_row.get("hard_gates", [])
            hard_gates = (
                [dict(item) for item in raw_hard_gates if isinstance(item, Mapping)]
                if isinstance(raw_hard_gates, Sequence)
                and not isinstance(raw_hard_gates, (str, bytes, bytearray))
                else []
            )
            hard_gates.extend(
                [
                    {
                        "name": "decision_context",
                        "status": "pass"
                        if mode_context.get("status") == "resolved"
                        else "unresolved",
                    },
                    {"name": "approach_feasibility", "status": approach_status},
                    {
                        "name": "sequence_identity",
                        "status": "pass" if mismatch_count == 0 else "fail",
                    },
                ]
            )
            if classification == "primary" and any(
                gate.get("status") != "pass" for gate in hard_gates
            ):
                classification = "unresolved"
                limitations.append("one or more primary hard gates did not pass")
            evidence_ids = sorted(
                {
                    str(item.get("id"))
                    for item in evidence
                    if isinstance(item, Mapping) and item.get("id")
                }
            ) if isinstance(evidence, Sequence) else []
            approach_checks = {
                "status": approach_status,
                "binder_format": mode_context.get("binder_format"),
                "access_side": mode_context.get("access_side"),
                "deep_cavity": deep_cavity,
                "framework_clearance": clearance,
                "allow_deep_cavity": bool(mode_context.get("allow_deep_cavity", False)),
                "required": [
                    "CDR access",
                    "framework-membrane collision",
                    "ECD/glycan collision",
                    "partner/protomer collision",
                ],
            }
            row = {
                "id": raw_row.get("id", raw_row.get("candidate_id")),
                "mode": candidate_mode,
                "classification": classification,
                "role": role,
                "hypothesis": raw_row.get("hypothesis", raw_row.get("label", "")),
                "functional_site": raw_row.get(
                    "functional_site", raw_row.get("label", raw_row.get("hypothesis", ""))
                ),
                "residues": residues,
                "evidence_tier": tier,
                "evidence": evidence if isinstance(evidence, Sequence) else [],
                "confidence": (
                    "unresolved"
                    if classification == "unresolved"
                    else _confidence({**raw_row, "evidence_tier": tier})
                ),
                "target_state": mode_context.get("target_state"),
                "counterstate": mode_context.get("counterstate"),
                "approach_direction": approach,
                "approach_checks": approach_checks,
                "evidence_ids": evidence_ids,
                "hard_gates": hard_gates,
                "falsifier": mode_context.get("falsifier")
                or raw_row.get("falsifier")
                or (
                    "Reject if a state-matched functional assay shows no "
                    "mechanism-consistent effect."
                ),
                "risks": sorted(set(limitations)),
                "geometry_metrics": {
                    "residue_count": len(residues),
                    "pore_lining_count": sum(bool(item.get("pore_lining")) for item in residues),
                    "axial_range": [
                        min(
                            (
                                float(item["axial_distance"])
                                for item in residues
                                if item.get("axial_distance") is not None
                            ),
                            default=None,
                        ),
                        max(
                            (
                                float(item["axial_distance"])
                                for item in residues
                                if item.get("axial_distance") is not None
                            ),
                            default=None,
                        ),
                    ],
                },
                "sources": [
                    str(item.get("source"))
                    for item in evidence
                    if isinstance(item, Mapping) and item.get("source")
                ]
                if isinstance(evidence, Sequence)
                else [],
                "assays": list(mode_context.get("assays", []))
                if isinstance(mode_context.get("assays"), Sequence)
                and not isinstance(mode_context.get("assays"), (str, bytes, bytearray))
                else [],
                "recommended_assays": raw_row.get("assays", []),
                "family_applicability": raw_row.get("family_applicability", []),
            }
            output[candidate_mode].append(row)
        output[candidate_mode].sort(
            key=lambda item: (
                {"primary": 0, "backup": 1, "avoid": 2, "unresolved": 3}.get(
                    item["classification"], 9
                ),
                {"T1": 0, "T2": 1, "T3": 2, "T4": 3}.get(item["evidence_tier"], 9),
                str(item["id"]),
            )
        )
    return output


def _hard_avoid_masks(analysis: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Add explicit non-pocket-facing TM masks without claiming all surfaces are lipid."""

    residues: list[dict[str, Any]] = []
    for item in analysis.get("residue_regions", []):
        if not isinstance(item, Mapping):
            continue
        segment = str(item.get("protein_segment", ""))
        if not segment.upper().startswith("TM") or bool(item.get("pore_lining")):
            continue
        radial = item.get("radial_distance")
        if radial is None or float(radial) < 18.0:
            continue
        residue = item.get("residue")
        if not isinstance(residue, Mapping):
            continue
        residues.append(
            {
                **dict(residue),
                "segment": segment,
                "generic_number": item.get("generic_number"),
                "radial_distance": radial,
            }
        )
    if not residues:
        return []
    return [
        {
            "id": "avoid.probable-lipid-facing-tm",
            "level": "hard",
            "reason": (
                "radial geometry places these TM side chains outside the pore-facing surface"
            ),
            "evidence_tier": "T2",
            "residues": residues,
            "risks": ["interhelical-versus-lipid exposure requires structure review"],
        }
    ]


def _warning_items(context: Mapping[str, Any], analysis: Mapping[str, Any]) -> list[Any]:
    values: list[Any] = []
    for item in context.get("warnings", []):
        values.append(item)
    values.extend(str(item) for item in analysis.get("warnings", []))
    if analysis.get("membrane", {}).get("direction_source") == "GPCR TM parity consensus":
        values.append(
            {
                "code": "membrane_direction_derived",
                "message": (
                    "signed membrane direction was inferred from TM parity and "
                    "loop topology, not OPM/PPM"
                ),
            }
        )
    decision_context = analysis.get("decision_context")
    if isinstance(decision_context, Mapping) and decision_context.get("status") != "resolved":
        missing_by_mode = {
            str(mode): list(value.get("missing", []))
            for mode, value in decision_context.get("modes", {}).items()
            if isinstance(value, Mapping) and value.get("missing")
        }
        values.append(
            {
                "code": "decision_context_unresolved",
                "message": (
                    "primary candidates are withheld until binder format, access side, "
                    "state contrast, assays, falsifier, and approach clearance are reviewed"
                ),
                "missing_by_mode": missing_by_mode,
            }
        )
    topology = analysis.get("topology")
    topology_rows = topology.get("residues", []) if isinstance(topology, Mapping) else []
    mismatch_count = (
        sum(
            isinstance(item, Mapping) and item.get("mapping_status") == "sequence_mismatch"
            for item in topology_rows
        )
        if isinstance(topology_rows, Sequence)
        and not isinstance(topology_rows, (str, bytes, bytearray))
        else 0
    )
    if mismatch_count:
        values.append(
            {
                "code": "sequence_mismatch_construct_risk",
                "message": (
                    f"{mismatch_count} mapped residue(s) differ between GPCRdb and the "
                    "observed structure and were excluded from automatic hotspot anchors"
                ),
            }
        )
    return values


def build_gpcr_site_analysis(request: GpcrSiteRequest) -> GpcrSiteAnalysis:
    """Run one typed analysis in memory without publishing or approving a site."""

    if request.mode not in MODES:
        raise AnalysisWorkflowError(f"mode must be one of {sorted(MODES)}")
    project_details: GpcrPrepareContext | None = None
    if request.project is not None:
        project_details = resolve_gpcr_prepare_context(
            request.project,
            request.structure,
        )
        structure = project_details.analysis_structure
        if (
            request.receptor_chain is not None
            and request.receptor_chain != project_details.receptor_chain
        ):
            raise AnalysisWorkflowError(
                "explicit receptor_chain conflicts with prepare residue mapping"
            )
    else:
        if request.structure is None:
            raise AnalysisWorkflowError("structure or project is required")
        structure = request.structure.expanduser().resolve(strict=True)
    if not structure.is_file():
        raise AnalysisWorkflowError(f"structure does not exist: {structure}")
    project_context: Mapping[str, Any] | None = (
        None
        if project_details is None
        else project_details.model_dump(mode="json")
    )

    code = (
        project_details.source_pdb_code
        if project_details is not None and project_details.source_pdb_code
        else _pdb_code(structure)
    )
    accession = request.accession or (
        project_details.source_accession if project_details is not None else None
    )
    if not (request.gpcr_entry or accession or code):
        raise AnalysisWorkflowError(
            "provide gpcr_entry/accession, or use a four-character PDB filename "
            "for GPCRdb resolution"
        )
    http = ScientificHttpClient(
        evidence_dir=request.evidence_dir,
        cache_mode=request.cache_mode,
        cache_root=request.cache_root,
    )
    try:
        try:
            resolved = GpcrdbAdapter(http).fetch_receptor_context(
                entry=request.gpcr_entry,
                accession=accession,
                pdb_code=code,
            )
            context = resolved.legacy_projection()
        except BackendContractError as error:
            if request.strict_gpcrdb:
                raise AnalysisWorkflowError(
                    f"GPCR provider identity resolution failed: {error}"
                ) from error
            context = _fallback_context(
                request,
                structure,
                error,
                gpcr_entry=request.gpcr_entry,
                accession=accession,
                pdb_code=code,
            )
            context["provenance"].extend(
                record.model_dump(mode="json") for record in http.records
            )
    finally:
        http.close()

    raw_identity = _mapping(context.get("identity", {}), "GPCRdb identity")
    preferred = (
        project_details.receptor_chain
        if project_details is not None
        else raw_identity.get("preferred_chain")
    )
    chain = _choose_chain(
        structure,
        request.receptor_chain,
        str(preferred) if preferred else None,
    )
    parsed = parse_structure(structure)
    orientation = _load_optional(request.membrane_orientation, "membrane orientation")
    selection = _normalize_selection(request.selection, parsed)
    decision_context = _review_context_summary(selection, request.mode)
    try:
        local = analyze_structure(
            structure,
            chain,
            gpcr_residues=_mapping(context.get("topology", {}), "GPCRdb topology").get("residues"),
            membrane_orientation=orientation,
        )
    except StructureAnalysisError as error:
        raise AnalysisWorkflowError(str(error)) from error

    local["identity"]["receptor_chain"] = chain
    local["structure"]["receptor_chain"] = chain
    if isinstance(local.get("provenance"), Mapping):
        local["provenance"] = [dict(local["provenance"])]
    generated = generate_candidates(local, context, request.mode, selection)
    candidates = _normalise_candidates(
        generated,
        generated,
        request.mode,
        project_context,
        decision_context,
    )
    local["candidates"] = candidates
    local["decision_context"] = decision_context
    local["avoid"] = list(generated.get("avoid", [])) + _hard_avoid_masks(generated)
    local["state"] = _state_context(context, request.state)
    local["identity"] = _identity_context(context, chain)
    local["identity"]["mapping_confidence"] = (
        "high" if local["topology"].get("mapping_reliable") else "unresolved"
    )
    local["membrane"] = {
        **_mapping(local.get("membrane", {}), "membrane frame"),
        "status": "resolved" if local.get("membrane", {}).get("reliable") else "unresolved",
        "orientation_status": "resolved"
        if local.get("membrane", {}).get("reliable")
        else "unresolved",
        "input_file": str(request.membrane_orientation) if request.membrane_orientation else None,
    }
    local["warnings"] = _warning_items(context, local)
    local["evidence"] = list(generated.get("evidence", []))
    local["provenance"] = {
        "tool": "easydesign-gpcr-site-provider",
        "schema_version": "1.0",
        "structure": {
            "path": str(structure),
            "sha256": sha256_file(structure),
        },
        "gpcrdb": list(context.get("provenance", [])),
        "project": dict(project_context) if project_context else None,
        "selection": {
            "path": str(request.selection.resolve()) if request.selection else None,
            "sha256": sha256_file(request.selection) if request.selection else None,
        },
    }
    local["mode"] = request.mode
    local["analysis_id"] = hashlib.sha256(
        json.dumps(
            {
                "structure": local["structure"].get("sha256"),
                "chain": chain,
                "entry": local["identity"].get("entry_name"),
                "mode": request.mode,
                "context_sha256": (
                    sha256_file(request.selection) if request.selection else None
                ),
                "state_override": request.state,
            },
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()[:24]
    local["generated_at"] = (
        datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    )
    local["analysis_notes"] = {
        "no_fused_score": True,
        "candidate_ordering": "classification, evidence tier, fixed mechanism order, id",
        "approval_status": "awaiting_human_review",
    }
    return GpcrSiteAnalysis.model_validate(local)


def build_analysis(request: GpcrSiteRequest) -> dict[str, Any]:
    """Compatibility projection for callers migrating from the Skill script."""

    return build_gpcr_site_analysis(request).model_dump(mode="json")


def resolve_project_gpcr_provider(
    project: Path,
    *,
    offline: bool = False,
) -> GpcrProviderResolution:
    """Resolve auto routing once and retain the exact GET evidence."""

    project_root = project.expanduser().resolve(strict=True)
    base = project_root / GPCR_SITE_DIRECTORY / "provider-resolution"
    base.mkdir(parents=True, exist_ok=True)
    revision = _next_revision(base, "resolution")
    final_root = base / f"resolution-r{revision:06d}"
    staging = Path(tempfile.mkdtemp(prefix=f".resolution-r{revision:06d}.creating-", dir=base))
    details = resolve_gpcr_prepare_context(project_root)
    pdb_code = details.source_pdb_code or _pdb_code(details.analysis_structure)
    accession = details.source_accession
    provider = "unresolved"
    status = "provider-resolution-required"
    reason = "Stage 01 does not declare a PDB or UniProt identity usable by GPCRdb"
    entry: str | None = None
    http = ScientificHttpClient(
        evidence_dir=staging / "evidence" / "gpcrdb",
        cache_mode="offline" if offline else "online",
    )
    try:
        try:
            context = GpcrdbAdapter(http).fetch_receptor_context(
                accession=accession,
                pdb_code=pdb_code,
            )
        except BackendContractError as first_error:
            error: BackendContractError | None = first_error
            first_codes = [record.status_code for record in http.records]
            if pdb_code and accession and first_codes and first_codes[-1] == 404:
                try:
                    context = GpcrdbAdapter(http).fetch_receptor_context(
                        accession=accession
                    )
                except BackendContractError as second_error:
                    error = second_error
                    context = None
                else:
                    error = None
            else:
                context = None
                error = first_error
            if context is None:
                codes = [record.status_code for record in http.records]
                only_not_found = (
                    accession is not None
                    and bool(codes)
                    and all(code == 404 for code in codes)
                )
                if only_not_found:
                    provider = "generic"
                    status = "resolved"
                    reason = (
                        "GPCRdb returned a definitive 404 for the declared UniProt "
                        "identity"
                    )
                else:
                    suffix = (
                        "; a PDB-only 404 is not evidence that the target is non-GPCR"
                        if pdb_code and accession is None
                        else ""
                    )
                    reason = f"GPCRdb identity resolution was inconclusive: {error}{suffix}"
        if context is not None:
            entry = context.identity.entry_name
            accession = context.identity.accession or accession
            if context.status == "identifier_conflict":
                reason = "GPCRdb returned conflicting PDB/accession/receptor identities"
            else:
                provider = "gpcr"
                status = "resolved"
                reason = "Stage 01 identity resolved to a GPCRdb receptor"
    finally:
        http.close()
    payload = {
        "schema_version": PROVIDER_RESOLUTION_SCHEMA,
        "revision": revision,
        "provider": provider,
        "status": status,
        "reason": reason,
        "identity": {
            "gpcr_entry": entry,
            "accession": accession,
            "pdb_code": pdb_code,
            "receptor_chain": details.receptor_chain,
        },
        "stage01": {
            "manifest": str(details.stage01_manifest),
            "manifest_sha256": details.stage01_manifest_sha256,
            "target_bundle": str(details.target_bundle),
            "target_bundle_sha256": details.target_bundle_sha256,
            "structure_sha256": details.analysis_structure_sha256,
        },
        "retrieval_records": [record.model_dump(mode="json") for record in http.records],
    }
    request_path = staging / "provider-resolution.json"
    _write_json(request_path, payload)
    if provider == "unresolved":
        _write_yaml(staging / "gpcr-context-template.yaml", _context_template("both"))
    os.replace(staging, final_root)
    return GpcrProviderResolution(
        provider=provider,
        status=status,
        reason=reason,
        evidence_dir=final_root / "evidence" / "gpcrdb",
        request_path=final_root / "provider-resolution.json",
        gpcr_entry=entry,
        accession=accession,
        pdb_code=pdb_code,
    )


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())


def _write_yaml(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        yaml.safe_dump(value, handle, allow_unicode=True, sort_keys=False)
        handle.flush()
        os.fsync(handle.fileno())


def _copy_exclusive(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with source.open("rb") as reader, destination.open("xb") as writer:
        shutil.copyfileobj(reader, writer)
        writer.flush()
        os.fsync(writer.fileno())


def _next_revision(root: Path, prefix: str) -> int:
    revisions: list[int] = []
    pattern = re.compile(rf"^{re.escape(prefix)}-r(?P<revision>[0-9]{{6}})$")
    if root.is_dir():
        for path in root.iterdir():
            match = pattern.fullmatch(path.name)
            if match:
                revisions.append(int(match.group("revision")))
    return max(revisions, default=0) + 1


def _file_allowlist(root: Path, *, exclude: frozenset[str] = frozenset()) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        relative = path.relative_to(root).as_posix()
        if relative in exclude:
            continue
        rows.append(
            {
                "path": relative,
                "sha256": sha256_file(path),
                "size_bytes": path.stat().st_size,
            }
        )
    return rows


def _context_template(mode: str) -> dict[str, Any]:
    requested = ("inhibit", "activate") if mode == "both" else (mode,)
    return {
        "schema_version": "gpcr-decision-context-v1",
        "review_context": {
            "binder_format": None,
            "access_side": None,
            "modes": {
                item: {
                    "target_state": None,
                    "counterstate": None,
                    "assays": [],
                    "falsifier": None,
                    "approach_clearance": "unresolved",
                    "allow_deep_cavity": False,
                }
                for item in requested
            },
        },
    }


def _selection_template(
    analysis: GpcrSiteAnalysis,
    *,
    manifest_relative: str,
    manifest_sha256: str | None,
) -> dict[str, Any]:
    selectable = [
        {
            "id": item.id,
            "mode": item.mode,
            "classification": item.classification.value,
            "role": item.role,
            "residue_count": len(item.residues),
        }
        for item in (*analysis.candidates.inhibit, *analysis.candidates.activate)
        if item.classification.value in {"primary", "backup"}
    ]
    return {
        "schema_version": SELECTION_SCHEMA,
        "analysis_id": analysis.analysis_id,
        "analysis_manifest": manifest_relative,
        "analysis_manifest_sha256": manifest_sha256,
        "candidate_ids": [],
        "selectable_candidates": selectable,
    }


def _handoff(analysis: GpcrSiteAnalysis) -> dict[str, Any]:
    return {
        "schema_version": "gpcr-hotspot-handoff-v1",
        "analysis_id": analysis.analysis_id,
        "mode": analysis.mode.value,
        "approval_status": "awaiting_human_review",
        "ready_for_strategize": False,
        "ready_for_stage03": False,
        "candidates": {
            mode: [
                {
                    "id": item.id,
                    "classification": item.classification.value,
                    "role": item.role,
                    "residues": [residue.model_dump(mode="json") for residue in item.residues],
                }
                for item in getattr(analysis.candidates, mode)
            ]
            for mode in ("inhibit", "activate")
        },
        "avoid": list(analysis.avoid),
    }


def publish_gpcr_analysis(
    request: GpcrSiteRequest,
    output_root: Path,
    *,
    project_root: Path | None = None,
) -> PublishedGpcrAnalysis:
    """Publish one immutable dossier and a read-only Mol* report revision."""

    base = output_root.expanduser().resolve()
    base.mkdir(parents=True, exist_ok=True)
    revision = _next_revision(base, "analysis")
    final_root = base / f"analysis-r{revision:06d}"
    staging = Path(tempfile.mkdtemp(prefix=f".analysis-r{revision:06d}.creating-", dir=base))
    try:
        effective = replace(request, evidence_dir=staging / "evidence" / "gpcrdb")
        analysis = build_gpcr_site_analysis(effective)
        analysis_path = staging / "gpcr-hotspot-analysis.json"
        _write_json(analysis_path, analysis.model_dump(mode="json"))
        handoff_path = staging / "gpcr_hotspot_handoff.yaml"
        _write_yaml(handoff_path, _handoff(analysis))
        _write_yaml(staging / "gpcr-context-template.yaml", _context_template(request.mode))

        review = generate_review_report(
            analysis_path,
            staging / "review",
            mode=cast(Literal["both", "inhibit", "activate"], request.mode),
        )
        validate_review_report(review.report_root)
        manifest_path = staging / "analysis-manifest.json"
        manifest_relative = (
            f"{GPCR_SITE_DIRECTORY}/{final_root.name}/analysis-manifest.json"
            if project_root is not None
            else f"{final_root.name}/analysis-manifest.json"
        )
        placeholder = _selection_template(
            analysis,
            manifest_relative=manifest_relative,
            manifest_sha256=None,
        )
        _write_yaml(staging / "gpcr-site-selection-template.yaml", placeholder)
        manifest = {
            "schema_version": ANALYSIS_MANIFEST_SCHEMA,
            "analysis_id": analysis.analysis_id,
            "revision": revision,
            "created_at": analysis.generated_at.isoformat(),
            "mode": analysis.mode.value,
            "provider": "gpcr",
            "approval_status": "awaiting_human_review",
            "ready_for_strategize": False,
            "source": {
                "structure_sha256": analysis.structure["sha256"],
                "stage01": analysis.provenance.get("project"),
            },
            "review_manifest": review.manifest_path.relative_to(staging).as_posix(),
            "files": _file_allowlist(
                staging,
                exclude=frozenset({"analysis-manifest.json"}),
            ),
        }
        _write_json(manifest_path, manifest)
        os.replace(staging, final_root)

        final_manifest = final_root / "analysis-manifest.json"
        manifest_sha = sha256_file(final_manifest)
        selection_value = _selection_template(
            analysis,
            manifest_relative=manifest_relative,
            manifest_sha256=manifest_sha,
        )
        context_template = final_root / "gpcr-context-template.yaml"
        if project_root is not None:
            context_path = project_root / f"gpcr-context.{analysis.analysis_id}.yaml"
            selection_path = project_root / (
                f"gpcr-site-selection.{analysis.analysis_id}.r{revision:06d}.yaml"
            )
        else:
            context_path = base / f"gpcr-context.{analysis.analysis_id}.yaml"
            selection_path = base / (
                f"gpcr-site-selection.{analysis.analysis_id}.r{revision:06d}.yaml"
            )
        if not context_path.exists():
            _copy_exclusive(context_template, context_path)
        _write_yaml(selection_path, selection_value)
        append_pointer_revision(
            base / GPCR_SITE_POINTER,
            f"{final_root.name}/analysis-manifest.json",
        )
        validate_gpcr_analysis_bundle(final_root)
        return PublishedGpcrAnalysis(
            analysis_root=final_root,
            manifest_path=final_manifest,
            analysis_path=final_root / "gpcr-hotspot-analysis.json",
            handoff_path=final_root / "gpcr_hotspot_handoff.yaml",
            context_path=context_path,
            selection_path=selection_path,
            report_root=final_root / "review" / review.report_root.name,
            revision=revision,
        )
    except Exception:
        if staging.exists():
            shutil.rmtree(staging)
        raise


def publish_project_gpcr_analysis(
    project: Path,
    *,
    mode: str = "both",
    context_path: Path | None = None,
    offline: bool = False,
    gpcr_entry: str | None = None,
    accession: str | None = None,
) -> PublishedGpcrAnalysis:
    project_root = project.expanduser().resolve(strict=True)
    return publish_gpcr_analysis(
        GpcrSiteRequest(
            evidence_dir=project_root / GPCR_SITE_DIRECTORY / ".unused-evidence",
            project=project_root,
            mode=mode,
            gpcr_entry=gpcr_entry,
            accession=accession,
            selection=context_path,
            cache_mode="offline" if offline else "prefer-cache",
            strict_gpcrdb=True,
        ),
        project_root / GPCR_SITE_DIRECTORY,
        project_root=project_root,
    )


def resolve_latest_gpcr_analysis(project_or_root: Path) -> Path:
    supplied = project_or_root.expanduser().resolve(strict=True)
    base = supplied / GPCR_SITE_DIRECTORY if (supplied / "PROJECT.yaml").is_file() else supplied
    relative = read_last_text_line(base / GPCR_SITE_POINTER)
    candidate = (base / relative).resolve(strict=True)
    if not candidate.is_relative_to(base) or candidate.name != "analysis-manifest.json":
        raise AnalysisWorkflowError("invalid GPCR analysis LATEST pointer")
    validate_gpcr_analysis_bundle(candidate.parent)
    return candidate.parent


def _selection_residue_mapping(
    project_root: Path,
    manifest: Mapping[str, Any],
) -> tuple[ResidueMapping, str]:
    """Load the exact Stage 01 mapping frozen into the selected GPCR analysis."""

    source = _mapping(manifest.get("source"), "analysis manifest source")
    stage01 = _mapping(source.get("stage01"), "analysis manifest Stage 01 source")
    role = str(stage01.get("analysis_structure_role") or "")
    if role not in {"canonical-target", "source-context"}:
        raise AnalysisWorkflowError(
            "GPCR analysis does not declare a supported Stage 01 structure role"
        )
    raw_path = str(stage01.get("residue_mapping") or "")
    expected_sha = str(stage01.get("residue_mapping_sha256") or "")
    if not raw_path or not expected_sha:
        raise AnalysisWorkflowError(
            "GPCR analysis does not declare its frozen Stage 01 residue mapping"
        )
    mapping_path = Path(raw_path).expanduser().resolve(strict=True)
    workspace_root = project_root.parent.parent.resolve(strict=True)
    if (
        not mapping_path.is_relative_to(workspace_root)
        or not mapping_path.is_file()
        or mapping_path.is_symlink()
    ):
        raise AnalysisWorkflowError(
            "GPCR analysis Stage 01 residue mapping is outside the current workspace"
        )
    if sha256_file(mapping_path) != expected_sha:
        raise AnalysisWorkflowError(
            "GPCR analysis Stage 01 residue mapping SHA-256 mismatch"
        )
    mapping = load_model(mapping_path, ResidueMapping)
    declared_entries = tuple(
        ResidueMappingEntry.model_validate(item).model_dump(mode="json")
        for item in _rows(
            stage01.get("residue_mapping_entries"),
            "analysis manifest Stage 01 residue mapping entries",
        )
    )
    artifact_entries = tuple(item.model_dump(mode="json") for item in mapping.entries)
    if declared_entries != artifact_entries:
        raise AnalysisWorkflowError(
            "GPCR analysis Stage 01 residue mapping entries differ from the frozen artifact"
        )
    return mapping, role


def _candidate_target_labels(
    candidate_id: str,
    residues: Sequence[Any],
    mapping: ResidueMapping,
    structure_role: str,
) -> list[int]:
    """Project source/canonical candidate identities into normalized target labels."""

    index: dict[tuple[str, str, str], list[Any]] = {}
    for entry in mapping.entries:
        if structure_role == "source-context":
            chain = entry.source_author_chain_id
            residue_id = entry.source_author_residue_id
        else:
            chain = entry.author_chain_id
            residue_id = entry.author_residue_id
        if chain is None or residue_id is None:
            continue
        key = (chain, residue_id, entry.insertion_code or "")
        index.setdefault(key, []).append(entry)

    labels: list[int] = []
    outside_scope: list[str] = []
    for residue in residues:
        chain = str(residue.auth_asym_id or residue.chain_id)
        residue_id = str(residue.auth_seq_id)
        insertion_code = str(residue.insertion_code or "")
        matches = index.get((chain, residue_id, insertion_code), [])
        residue_name = f"{chain}:{residue_id}{insertion_code}"
        if not matches:
            outside_scope.append(residue_name)
            continue
        if len(matches) != 1:
            raise AnalysisWorkflowError(
                f"GPCR candidate {candidate_id} residue {residue_name} maps ambiguously "
                "into the Stage 01 target"
            )
        entry = matches[0]
        if residue.amino_acid != entry.amino_acid:
            raise AnalysisWorkflowError(
                f"GPCR candidate {candidate_id} residue {residue_name} amino acid "
                "differs from the Stage 01 target mapping"
            )
        labels.append(entry.label_seq_id)
    if outside_scope:
        raise AnalysisWorkflowError(
            f"GPCR candidate {candidate_id} contains residues outside the current "
            f"Stage 01 target scope: {outside_scope}"
        )
    if len(set(labels)) != len(residues) or not labels:
        raise AnalysisWorkflowError(
            f"GPCR candidate {candidate_id} does not map uniquely into Stage 01 label numbering"
        )
    return sorted(labels)


def validate_gpcr_analysis_bundle(bundle: Path) -> dict[str, Any]:
    root = bundle.expanduser().resolve(strict=True)
    if (root / GPCR_SITE_POINTER).is_file() or (root / f"{GPCR_SITE_POINTER}.revisions").is_dir():
        root = resolve_latest_gpcr_analysis(root)
    manifest = _mapping(load_document(root / "analysis-manifest.json"), "analysis manifest")
    if manifest.get("schema_version") != ANALYSIS_MANIFEST_SCHEMA:
        raise AnalysisWorkflowError("unsupported GPCR analysis manifest schema")
    declared: set[str] = set()
    for item in _rows(manifest.get("files"), "analysis manifest files"):
        relative = str(item.get("path") or "")
        path = (root / relative).resolve()
        if not relative or relative in declared or not path.is_relative_to(root):
            raise AnalysisWorkflowError(f"invalid analysis manifest path: {relative!r}")
        if not path.is_file() or path.is_symlink():
            raise AnalysisWorkflowError(f"declared GPCR artifact is missing: {relative}")
        if item.get("sha256") != sha256_file(path) or item.get("size_bytes") != path.stat().st_size:
            raise AnalysisWorkflowError(f"GPCR artifact integrity failure: {relative}")
        declared.add(relative)
    actual = {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file() and path.name != "analysis-manifest.json"
    }
    if actual != declared:
        raise AnalysisWorkflowError("GPCR analysis manifest allowlist mismatch")
    analysis = GpcrSiteAnalysis.model_validate(
        load_document(root / "gpcr-hotspot-analysis.json")
    )
    if analysis.analysis_id != manifest.get("analysis_id"):
        raise AnalysisWorkflowError("GPCR analysis identity differs from manifest")
    handoff = _mapping(
        load_document(root / "gpcr_hotspot_handoff.yaml"), "GPCR handoff"
    )
    if handoff.get("approval_status") != "awaiting_human_review" or handoff.get(
        "ready_for_strategize"
    ) is not False:
        raise AnalysisWorkflowError("GPCR handoff must remain awaiting human review")
    validate_review_report((root / str(manifest["review_manifest"])).parent)
    return dict(manifest)


def gpcr_selection_to_stage02_config(project: Path, selection_path: Path) -> Stage02Config:
    """Validate selected candidate IDs and project them into A/B/C label regions."""

    project_root = project.expanduser().resolve(strict=True)
    selected_path = selection_path.expanduser().resolve(strict=True)
    if not selected_path.is_relative_to(project_root):
        raise AnalysisWorkflowError("GPCR selection must be stored inside the project")
    selection = _mapping(load_document(selected_path), "GPCR selection")
    if selection.get("schema_version") != SELECTION_SCHEMA:
        raise AnalysisWorkflowError("unsupported GPCR selection schema")
    relative_manifest = str(selection.get("analysis_manifest") or "")
    manifest_path = (project_root / relative_manifest).resolve(strict=True)
    if not manifest_path.is_relative_to(project_root):
        raise AnalysisWorkflowError("GPCR selection manifest escapes project")
    expected_sha = str(selection.get("analysis_manifest_sha256") or "")
    if expected_sha != sha256_file(manifest_path):
        raise AnalysisWorkflowError("GPCR selection analysis manifest SHA-256 mismatch")
    validate_gpcr_analysis_bundle(manifest_path.parent)
    manifest = _mapping(load_document(manifest_path), "analysis manifest")
    if selection.get("analysis_id") != manifest.get("analysis_id"):
        raise AnalysisWorkflowError("GPCR selection analysis_id mismatch")
    raw_ids = selection.get("candidate_ids")
    if not isinstance(raw_ids, Sequence) or isinstance(raw_ids, (str, bytes, bytearray)):
        raise AnalysisWorkflowError("candidate_ids must be an array")
    candidate_ids = [str(value).strip() for value in raw_ids if str(value).strip()]
    if not 1 <= len(candidate_ids) <= 3 or len(candidate_ids) != len(set(candidate_ids)):
        raise AnalysisWorkflowError("select 1-3 unique GPCR candidate IDs")
    analysis = GpcrSiteAnalysis.model_validate(
        load_document(manifest_path.parent / "gpcr-hotspot-analysis.json")
    )
    residue_mapping, structure_role = _selection_residue_mapping(project_root, manifest)
    candidates = {
        item.id: item for item in (*analysis.candidates.inhibit, *analysis.candidates.activate)
    }
    regions: list[dict[str, Any]] = []
    used_labels: set[int] = set()
    for region_id, candidate_id in zip("ABC", candidate_ids, strict=False):
        candidate = candidates.get(candidate_id)
        if candidate is None:
            raise AnalysisWorkflowError(f"unknown GPCR candidate ID: {candidate_id}")
        if candidate.classification.value not in {"primary", "backup"}:
            raise AnalysisWorkflowError(
                f"GPCR candidate {candidate_id} is {candidate.classification.value}; "
                "only primary/backup candidates can be proposed"
            )
        labels = _candidate_target_labels(
            candidate_id,
            candidate.residues,
            residue_mapping,
            structure_role,
        )
        overlap = used_labels.intersection(labels)
        if overlap:
            raise AnalysisWorkflowError(
                f"selected GPCR candidates overlap at label residues: {sorted(overlap)}"
            )
        used_labels.update(labels)
        regions.append(
            {"id": region_id, "residues": [str(value) for value in labels]}
        )
    return Stage02Config.model_validate(
        {
            "mode": "user-provided",
            "methods": [],
            "automatic": None,
            "annotations": {"uniprot": "if_available"},
            "user_regions": {
                "source": {
                    "type": "residue-list",
                    "numbering": "label",
                    "regions": regions,
                }
            },
        }
    )


__all__ = [
    "AnalyzeRequest",
    "AnalysisWorkflowError",
    "GpcrProviderResolution",
    "GpcrSiteRequest",
    "GpcrPrepareContext",
    "PublishedGpcrAnalysis",
    "MODES",
    "build_analysis",
    "build_gpcr_site_analysis",
    "gpcr_selection_to_stage02_config",
    "load_document",
    "publish_gpcr_analysis",
    "publish_project_gpcr_analysis",
    "resolve_project_gpcr_provider",
    "resolve_gpcr_prepare_context",
    "resolve_latest_gpcr_analysis",
    "validate_gpcr_analysis_bundle",
]
