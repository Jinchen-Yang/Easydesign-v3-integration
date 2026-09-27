"""Stage 01 本地结构、RCSB、UniProt 与 Target Bundle 的统一编排。"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from easydesign.backends.target_sources.remote import (
    RCSB_SEQUENCE_RESULT_LIMIT,
    ScientificHttpClient,
    rcsb_entry,
    rcsb_mmcif,
    rcsb_polymer_entity,
    rcsb_sequence_search,
    uniprot_accession,
    uniprot_search,
)
from easydesign.backends.target_sources.sequence import (
    NormalizedProteinSequence,
    normalize_raw_sequence,
)
from easydesign.backends.target_sources.structure import (
    build_experimental_target_bundle,
    choose_chain,
    inventory_structure,
    scope_coordinate_evidence,
)
from easydesign.core import (
    ArtifactRef,
    Attempt,
    BackendContractError,
    ConfigurationError,
    DecisionOption,
    DecisionRequest,
    DesignResidueMapping,
    ErrorInfo,
    ExecutionStatus,
    RunManifest,
    StageId,
    StageManifest,
    TargetIdentityReport,
    TargetInputError,
    WorkflowState,
    WorkflowStateType,
    dump_model,
    load_model,
    resolve_target_identity,
    sha256_file,
)
from easydesign.core.target_identity import (
    CanonicalIdentityStatus,
    ConstructRelationship,
    ReviewRequirement,
)
from easydesign.reporting import generate_stage01_target_viewer_nonblocking
from easydesign.safe_writes import append_pointer_revision
from easydesign.stages.s01_target_preparation import (
    BuiltTargetBundle,
    CoordinateEnsemble,
    TargetBundle,
)

from .config import (
    ExecutionMode,
    FullSequenceScope,
    LoadedRemoteRunConfig,
    LoadedSequenceRunConfig,
    LoadedStructureRunConfig,
    LoadedTargetBundleRunConfig,
    LocalFileSourceConfig,
    PdbIdSourceConfig,
    ResidueRangeScope,
    UniProtFeatureScope,
    UniProtSearchSourceConfig,
    UniProtSourceConfig,
)
from .decisions import publish_decision_request
from .workspace import (
    PreparedRun,
    ResolvedRunConfig,
    RunIndexEntry,
    upsert_run_index_entries,
)

ATTEMPT_ID = "attempt-0001"


def _prediction_backend_presentation(config: Any) -> tuple[str, str] | None:
    prediction = config.stage01.structure_prediction
    if prediction is None:
        return None
    backend = str(prediction.backend)
    if backend == "openfold3-af3-jax":
        return "predict-openfold3-af3-jax", "AFO (OpenFold3 AF3 JAX)"
    return "predict-protenix-v2", "Protenix-v2"


def _require_prediction_backend(config: Any) -> None:
    if config.stage01.structure_prediction is None:
        raise ConfigurationError(
            "Stage 1 检索后确认需要预测 target；请带 "
            "--prediction-backend afo 或 protenix 重新运行 target prepare"
        )


@dataclass(frozen=True, slots=True)
class PredictionFallback:
    target: NormalizedProteinSequence
    reference_sequence: str
    identity_report: dict[str, Any]
    scope_report: dict[str, Any]
    candidates: list[dict[str, Any]]
    retrieval_records: list[dict[str, Any]]
    reason: str


@dataclass(frozen=True, slots=True)
class Stage01SourceOutcome:
    status: str
    run_root: Path
    run_manifest: Path
    built_bundle: BuiltTargetBundle | None = None
    prediction_fallback: PredictionFallback | None = None
    viewer_status: str | None = None
    decision_request: Path | None = None


@dataclass(frozen=True, slots=True)
class _ExperimentalSelection:
    source_path: Path
    selected_chain: str
    expected_scope_sequence: str | None
    reference_sequence: str | None
    reference_start: int | None
    identity_report: dict[str, Any]
    scope_report: dict[str, Any]
    candidates: list[dict[str, Any]]
    quality_report: dict[str, Any]
    provenance: dict[str, Any]
    retrieval_records: list[dict[str, Any]]
    identity_mapping: tuple[DesignResidueMapping, ...] | None = None


def _strictly_later(candidate: datetime, previous: datetime) -> datetime:
    return candidate if candidate > previous else previous + timedelta(microseconds=1)


def _atomic_pointer(text: str, path: Path) -> None:
    append_pointer_revision(path, text)


def _artifact(
    *,
    run_root: Path,
    path: Path,
    artifact_id: str,
    role: str,
    file_format: str,
    attempt_id: str = ATTEMPT_ID,
) -> ArtifactRef:
    return ArtifactRef.from_file(
        run_root=run_root,
        relative_path=path.relative_to(run_root).as_posix(),
        artifact_id=artifact_id,
        role=role,
        file_format=file_format,
        producer_stage=str(StageId.TARGET_PREPARATION),
        producer_attempt=attempt_id,
    )


def _current_manifest(prepared: PreparedRun) -> RunManifest:
    return load_model(prepared.workspace.run_manifest, RunManifest)


def _publish_run(
    prepared: PreparedRun,
    *,
    stage_manifest: Path,
    ended_at: datetime,
    attempt_id: str = ATTEMPT_ID,
) -> Path:
    current = _current_manifest(prepared)
    stage_ref = _artifact(
        run_root=prepared.workspace.run_root,
        path=stage_manifest,
        artifact_id="stage-01-manifest",
        role="stage-manifest",
        file_format="json",
        attempt_id=attempt_id,
    )
    updated = _strictly_later(ended_at, current.updated_at)
    stop_after = prepared.loaded_config.config.workflow.stop_after_stage
    next_manifest = current.next_revision(
        updated_at=updated,
        status=(
            ExecutionStatus.SUCCEEDED
            if stop_after == 1
            else ExecutionStatus.RUNNING
        ),
        completed_at=updated if stop_after == 1 else None,
        stage_manifest_refs=(stage_ref,),
        clear_workflow_state=True,
    )
    path = (
        prepared.workspace.run_root
        / "manifests"
        / f"run-manifest.v{next_manifest.revision:04d}.json"
    )
    dump_model(next_manifest, path)
    _atomic_pointer(f"{path.name}\n", prepared.workspace.latest_manifest_pointer)
    upsert_run_index_entries(
        prepared.workspace.runs_root,
        (
            RunIndexEntry(
                category="project-run",
                path=prepared.workspace.run_root.relative_to(
                    prepared.workspace.runs_root
                ).as_posix(),
                layout_version="1",
                status=str(next_manifest.status),
                project_id=prepared.workspace.project_id,
                run_id=prepared.workspace.run_id,
                notes=("Stage 01 source normalized and Target Bundle published.",),
            ),
        ),
        generated_at=updated,
    )
    return path


def _pause_for_decision(
    prepared: PreparedRun,
    *,
    gate: str,
    message: str,
    options: tuple[DecisionOption, ...],
    attempt_id: str = ATTEMPT_ID,
) -> Stage01SourceOutcome:
    timestamp = datetime.now(UTC)
    prepared.workspace.attempt_root(
        StageId.TARGET_PREPARATION,
        attempt_id,
    ).mkdir(parents=True, exist_ok=True)
    request = DecisionRequest(
        decision_id=f"stage01-{gate}",
        stage_id=str(StageId.TARGET_PREPARATION),
        gate=gate,
        created_at=timestamp,
        message=message,
        options=options,
    )
    request_path = publish_decision_request(prepared.workspace.run_root, request)
    current = _current_manifest(prepared)
    updated = _strictly_later(timestamp, current.updated_at)
    next_manifest = current.next_revision(
        updated_at=updated,
        status=ExecutionStatus.RUNNING,
        workflow_state=WorkflowState(
            state=WorkflowStateType.AWAITING_HUMAN_APPROVAL,
            stage_id=StageId.TARGET_PREPARATION,
            action="approve-decision",
            message=message,
        ),
    )
    manifest_path = (
        prepared.workspace.run_root
        / "manifests"
        / f"run-manifest.v{next_manifest.revision:04d}.json"
    )
    dump_model(next_manifest, manifest_path)
    _atomic_pointer(
        f"{manifest_path.name}\n",
        prepared.workspace.latest_manifest_pointer,
    )
    upsert_run_index_entries(
        prepared.workspace.runs_root,
        (
            RunIndexEntry(
                category="project-run",
                path=prepared.workspace.run_root.relative_to(
                    prepared.workspace.runs_root
                ).as_posix(),
                layout_version="1",
                status="awaiting-human-approval",
                project_id=prepared.workspace.project_id,
                run_id=prepared.workspace.run_id,
                notes=(f"Stage 01 decision gate: {gate}; attempt={attempt_id}.",),
            ),
        ),
        generated_at=updated,
    )
    return Stage01SourceOutcome(
        status="awaiting-human-approval",
        run_root=prepared.workspace.run_root,
        run_manifest=manifest_path,
        decision_request=request_path,
    )


def _scope(
    config: Any,
    *,
    reference_sequence: str,
    features: list[dict[str, Any]] | None = None,
) -> tuple[str, int, int, dict[str, Any]]:
    scope = config.stage01.target.scope
    if isinstance(scope, FullSequenceScope):
        start, end = 1, len(reference_sequence)
    elif isinstance(scope, ResidueRangeScope):
        start, end = scope.start, scope.end
        if end > len(reference_sequence):
            raise TargetInputError(
                f"design scope 超出 reference sequence: end={end}, length={len(reference_sequence)}"
            )
    else:
        assert isinstance(scope, UniProtFeatureScope)
        if features is None:
            raise TargetInputError("uniprot-feature scope 需要已冻结的 UniProt features")
        matches = []
        for feature in features:
            if feature.get("type") != scope.feature_type:
                continue
            description = feature.get("description")
            if scope.feature_name is not None and description != scope.feature_name:
                continue
            matches.append(feature)
        if len(matches) != 1:
            raise TargetInputError(
                "uniprot-feature scope 必须唯一匹配；"
                f"type={scope.feature_type}, name={scope.feature_name}, matches={len(matches)}"
            )
        location = matches[0].get("location", {})
        try:
            start = int(location["start"]["value"])
            end = int(location["end"]["value"])
        except (KeyError, TypeError, ValueError) as error:
            raise TargetInputError("UniProt feature 缺少确定性 start/end") from error
    scoped = reference_sequence[start - 1 : end]
    return scoped, start, end, {
        "schema_version": "0.1",
        "type": scope.type,
        "start": start,
        "end": end,
        "length": len(scoped),
        "coverage_requirement": 1.0,
        "identity_requirement": 1.0,
    }


def _scope_with_decision(
    prepared: PreparedRun,
    *,
    reference_sequence: str,
    features: list[dict[str, Any]] | None,
    approved_option: DecisionOption | None,
    attempt_id: str,
) -> tuple[str, int, int, dict[str, Any]] | Stage01SourceOutcome:
    """为多匹配 UniProt feature 建立可恢复选择门。"""

    scope = prepared.loaded_config.config.target.scope
    if not isinstance(scope, UniProtFeatureScope):
        return _scope(
            prepared.loaded_config.config,
            reference_sequence=reference_sequence,
            features=features,
        )
    if features is None:
        raise TargetInputError("uniprot-feature scope 需要已冻结的 UniProt features")
    matches: list[tuple[int, dict[str, Any], int, int]] = []
    for index, feature in enumerate(features):
        if feature.get("type") != scope.feature_type:
            continue
        description = feature.get("description")
        if scope.feature_name is not None and description != scope.feature_name:
            continue
        try:
            start = int(feature["location"]["start"]["value"])
            end = int(feature["location"]["end"]["value"])
        except (KeyError, TypeError, ValueError) as error:
            raise TargetInputError("UniProt feature 缺少确定性 start/end") from error
        matches.append((index, feature, start, end))
    approved_index = (
        int(approved_option.payload["feature_index"])
        if approved_option is not None
        and approved_option.payload.get("action") == "select-uniprot-feature"
        and approved_option.payload.get("feature_index") is not None
        else None
    )
    if approved_index is not None:
        matches = [item for item in matches if item[0] == approved_index]
        if len(matches) != 1:
            raise TargetInputError("已批准的 UniProt feature 不再匹配当前冻结记录")
    if len(matches) == 1:
        _, feature, start, end = matches[0]
        scoped = reference_sequence[start - 1 : end]
        return scoped, start, end, {
            "schema_version": "0.1",
            "type": scope.type,
            "feature_type": scope.feature_type,
            "feature_name": feature.get("description"),
            "start": start,
            "end": end,
            "length": len(scoped),
            "coverage_requirement": 1.0,
            "identity_requirement": 1.0,
        }
    if not matches:
        raise TargetInputError(
            "uniprot-feature scope 没有匹配项；"
            f"type={scope.feature_type}, name={scope.feature_name}"
        )
    if (
        prepared.loaded_config.config.workflow.execution_mode
        is ExecutionMode.UNATTENDED
    ):
        raise TargetInputError(
            "uniprot-feature-ambiguous: unattended 要求 feature 唯一匹配"
        )
    return _pause_for_decision(
        prepared,
        gate="scope-selection",
        message="UniProt feature scope 存在多个匹配项，请确认 design scope。",
        options=tuple(
            DecisionOption(
                option_id=f"feature-{index:04d}-{start}-{end}",
                label=f"{scope.feature_type} {start}–{end}",
                description=str(feature.get("description") or "无名称"),
                payload={
                    "action": "select-uniprot-feature",
                    "feature_index": index,
                    "start": start,
                    "end": end,
                },
            )
            for index, feature, start, end in matches
        ),
        attempt_id=attempt_id,
    )


def _is_reviewed_uniprot_entry(entry_type: object) -> bool:
    normalized = str(entry_type).strip().casefold()
    return normalized == "reviewed" or normalized.startswith(
        "uniprotkb reviewed "
    )


def _uniprot_identity(payload: dict[str, Any]) -> tuple[str, str, dict[str, Any]]:
    try:
        accession = str(payload["primaryAccession"])
        sequence = str(payload["sequence"]["value"]).upper()
        taxon_id = int(payload["organism"]["taxonId"])
    except (KeyError, TypeError, ValueError) as error:
        raise TargetInputError("UniProt 响应缺少 accession/sequence/taxonomy") from error
    reviewed = _is_reviewed_uniprot_entry(payload.get("entryType"))
    report = {
        "schema_version": "0.1",
        "status": "resolved",
        "accession": accession,
        "reviewed": reviewed,
        "taxonomy_id": taxon_id,
        "entry_type": payload.get("entryType"),
        "identity_resolution": "explicit-accession",
    }
    return accession, sequence, report


def _search_matches(payload: dict[str, Any], query: str) -> list[dict[str, Any]]:
    results = payload.get("results", [])
    if not isinstance(results, list):
        raise TargetInputError("UniProt search 响应 results 不是 list")
    needle = query.casefold()
    matches = []
    for item in results:
        if not isinstance(item, dict):
            continue
        genes = item.get("genes", [])
        gene_names = {
            str(gene.get("geneName", {}).get("value", "")).casefold()
            for gene in genes
            if isinstance(gene, dict)
        }
        accession = str(item.get("primaryAccession", ""))
        entry_id = str(item.get("uniProtkbId", ""))
        protein = item.get("proteinDescription", {})
        recommended = (
            protein.get("recommendedName", {}).get("fullName", {}).get("value", "")
            if isinstance(protein, dict)
            else ""
        )
        exact = needle in {
            accession.casefold(),
            entry_id.casefold(),
            str(recommended).casefold(),
            *gene_names,
        }
        reviewed = _is_reviewed_uniprot_entry(item.get("entryType"))
        matches.append(
            {
                "payload": item,
                "accession": accession,
                "entry_id": entry_id,
                "recommended_name": recommended,
                "gene_names": sorted(gene_names),
                "reviewed": reviewed,
                "exact": exact,
            }
        )
    return sorted(
        matches,
        key=lambda item: (
            not item["exact"],
            not item["reviewed"],
            item["accession"],
        ),
    )


def resolve_unique_reviewed_uniprot_seed(
    *,
    evidence_dir: Path,
    query: str,
    taxon_id: int,
    cache_mode: str = "prefer-cache",
) -> dict[str, Any]:
    """Resolve a typed structural input to one reviewed exact UniProt seed.

    This is deliberately only a seed for native Stage 01.  Stage 01 still has to
    verify that the submitted sequence/structure maps to this identity before it
    can become Target authority.
    """

    with ScientificHttpClient(
        evidence_dir=evidence_dir,
        cache_mode=cache_mode,
    ) as client:
        payload = uniprot_search(client, query=query, taxon_id=taxon_id).json()
        if not isinstance(payload, dict):
            raise TargetInputError("UniProt search 响应必须是 mapping")
        matches = _search_matches(payload, query)
        exact = [item for item in matches if item["exact"] and item["reviewed"]]
        if len(exact) != 1:
            candidates = ", ".join(item["accession"] for item in matches[:5]) or "none"
            raise TargetInputError(
                "typed-target-canonical-identity-ambiguous: "
                f"query={query!r}, taxon_id={taxon_id}, "
                f"reviewed_exact_matches={len(exact)}, candidates={candidates}"
            )
        selected = exact[0]
        return {
            "schema_version": "0.1",
            "status": "verified-seed",
            "authority": "stage01-input-only",
            "query": query,
            "taxon_id": taxon_id,
            "accession": selected["accession"],
            "entry_id": selected["entry_id"],
            "recommended_name": selected["recommended_name"],
            "gene_names": selected["gene_names"],
            "reviewed": True,
            "resolution": "unique-reviewed-exact-search",
            "retrieval_records": [
                record.model_dump(mode="json") for record in client.records
            ],
        }


def _entry_method(entry: dict[str, Any]) -> tuple[str, float | None]:
    methods = entry.get("exptl", [])
    method = (
        str(methods[0].get("method", "unknown"))
        if isinstance(methods, list) and methods
        else "unknown"
    )
    resolutions = entry.get("rcsb_entry_info", {}).get("resolution_combined")
    resolution = (
        float(resolutions[0])
        if isinstance(resolutions, list) and resolutions
        else None
    )
    return method, resolution


def _candidate_deposition_facts(
    entry_payload: dict[str, Any], entity_payload: dict[str, Any]
) -> dict[str, Any]:
    """Project exact RCSB annotations needed for a bounded structure decision."""

    struct = entry_payload.get("struct", {})
    keywords = entry_payload.get("struct_keywords", {})
    polymer = entity_payload.get("rcsb_polymer_entity", {})
    entity_poly = entity_payload.get("entity_poly", {})
    identifiers = entity_payload.get("rcsb_polymer_entity_container_identifiers", {})
    citations = entry_payload.get("citation", [])
    if not isinstance(struct, dict):
        struct = {}
    if not isinstance(keywords, dict):
        keywords = {}
    if not isinstance(polymer, dict):
        polymer = {}
    if not isinstance(entity_poly, dict):
        entity_poly = {}
    if not isinstance(identifiers, dict):
        identifiers = {}
    if not isinstance(citations, list):
        citations = []
    primary = next(
        (
            item
            for item in citations
            if isinstance(item, dict) and str(item.get("rcsb_is_primary", "")).upper() == "Y"
        ),
        next((item for item in citations if isinstance(item, dict)), {}),
    )
    reference_identifiers = identifiers.get("reference_sequence_identifiers", [])
    if not isinstance(reference_identifiers, list):
        reference_identifiers = []
    references = [
        {
            "database_name": item.get("database_name"),
            "database_accession": item.get("database_accession"),
            "entity_sequence_coverage": item.get("entity_sequence_coverage"),
            "reference_sequence_coverage": item.get("reference_sequence_coverage"),
            "provenance_source": item.get("provenance_source"),
        }
        for item in reference_identifiers
        if isinstance(item, dict)
    ]
    uniprot_ids = identifiers.get("uniprot_ids", [])
    if not isinstance(uniprot_ids, list):
        uniprot_ids = []
    return {
        "deposited_title": struct.get("title"),
        "deposited_keywords": keywords.get("text") or keywords.get("pdbx_keywords"),
        "entity_description": polymer.get("pdbx_description"),
        "multiple_source_flag": polymer.get("rcsb_multiple_source_flag"),
        "source_part_count": polymer.get("rcsb_source_part_count"),
        "uniprot_ids": [str(value) for value in uniprot_ids],
        "reference_sequence_identifiers": references,
        "artifact_monomer_count": entity_poly.get("rcsb_artifact_monomer_count"),
        "mutation_count": entity_poly.get("rcsb_mutation_count"),
        "conflict_count": entity_poly.get("rcsb_conflict_count"),
        "deletion_count": entity_poly.get("rcsb_deletion_count"),
        "insertion_count": entity_poly.get("rcsb_insertion_count"),
        "primary_citation_title": primary.get("title") if isinstance(primary, dict) else None,
        "primary_citation_doi": (
            primary.get("pdbx_database_id_DOI") if isinstance(primary, dict) else None
        ),
        "primary_citation_pubmed": (
            primary.get("pdbx_database_id_PubMed") if isinstance(primary, dict) else None
        ),
    }


def _structure_selection_option(item: dict[str, Any]) -> DecisionOption:
    """Build a compact decision card without reducing quality to resolution alone."""

    def short(value: Any, limit: int = 280) -> str:
        text = str(value).replace("\n", " ").strip()
        return text if len(text) <= limit else text[: limit - 1] + "…"

    references = [
        {
            key: reference.get(key)
            for key in (
                "database_accession",
                "entity_sequence_coverage",
                "reference_sequence_coverage",
                "provenance_source",
            )
        }
        for reference in item.get("reference_sequence_identifiers", [])
        if isinstance(reference, dict)
    ]
    summary = {
        key: item.get(key)
        for key in (
            "method",
            "resolution_angstrom",
            "deposited_title",
            "deposited_keywords",
            "entity_description",
            "entity_sequence_length",
            "scope_sequence_coverage",
            "scope_identity",
            "scope_coordinate_coverage",
            "target_structure_status",
            "multiple_source_flag",
            "source_part_count",
            "uniprot_ids",
            "artifact_monomer_count",
            "mutation_count",
            "conflict_count",
            "deletion_count",
            "insertion_count",
            "primary_citation_title",
            "primary_citation_doi",
            "primary_citation_pubmed",
            "warnings",
        )
    }
    summary["reference_sequence_identifiers"] = references
    description_parts = [
        f"method={short(item.get('method'))}",
        f"resolution={short(item.get('resolution_angstrom'))} Å",
        f"construct_length={short(item.get('entity_sequence_length'))}",
        f"canonical_alignment_coverage={short(item.get('scope_sequence_coverage'))}",
        f"coordinate_coverage={short(item.get('scope_coordinate_coverage'))}",
        f"entity={short(item.get('entity_description'))}",
        f"source_parts={short(item.get('source_part_count'))}",
        f"artifacts={short(item.get('artifact_monomer_count'))}",
        f"mutations={short(item.get('mutation_count'))}",
        f"deposited_title={short(item.get('deposited_title'))}",
        f"deposited_keywords={short(item.get('deposited_keywords'))}",
    ]
    return DecisionOption(
        option_id=(
            f"pdb-{str(item['pdb_id']).lower()}-"
            f"entity-{str(item['entity_id']).lower()}"
        ),
        label=f"{item['pdb_id']} chain {item['chain']}",
        description="; ".join(description_parts),
        payload={
            "action": "select-experimental",
            "pdb_id": item["pdb_id"],
            "entity_id": item["entity_id"],
            "chain": item["chain"],
            "candidate_summary": summary,
        },
        eligible=True,
    )


def _quality_eligible(method: str, resolution: float | None) -> tuple[bool, list[str]]:
    normalized = method.upper()
    reasons: list[str] = []
    if "X-RAY" in normalized:
        if resolution is None or resolution > 3.5:
            reasons.append("xray-resolution-above-3.5-or-missing")
    elif "ELECTRON MICROSCOPY" in normalized:
        if resolution is None or resolution > 4.0:
            reasons.append("cryoem-resolution-above-4.0-or-missing")
    elif "NMR" in normalized:
        reasons.append("nmr-review-only")
    else:
        reasons.append("unsupported-experimental-method")
    return not reasons, reasons


def _entity_fields(
    payload: dict[str, Any],
    *,
    chain_namespace: str = "auth",
) -> tuple[str, tuple[str, ...]]:
    try:
        sequence = str(payload["entity_poly"]["pdbx_seq_one_letter_code_can"])
        identifiers = payload["rcsb_polymer_entity_container_identifiers"]
        chains = (
            identifiers.get("auth_asym_ids")
            if chain_namespace == "auth"
            else identifiers.get("asym_ids")
        )
        if not isinstance(chains, list) or not chains:
            raise ValueError("missing chains")
    except (KeyError, TypeError, ValueError) as error:
        raise TargetInputError("RCSB polymer entity 缺少 sequence/chain") from error
    clean = "".join(sequence.split()).replace("?", "X")
    return clean, tuple(str(chain) for chain in chains)


def _candidate(
    *,
    client: ScientificHttpClient,
    pdb_id: str,
    entity_id: str,
    expected_scope: str,
    preferred_chain: str | None = None,
    preferred_chain_namespace: str = "auth",
    biological_identity_resolved: bool = True,
    declared_relationship: ConstructRelationship | None = None,
    accession: str | None = None,
    canonical_scope_start: int | None = None,
    canonical_scope_end: int | None = None,
    canonical_sequence: str | None = None,
) -> tuple[dict[str, Any], Path | None]:
    entry_payload = rcsb_entry(client, pdb_id).json()
    entity_payload = rcsb_polymer_entity(client, pdb_id, entity_id).json()
    if not isinstance(entry_payload, dict) or not isinstance(entity_payload, dict):
        raise TargetInputError("RCSB entry/entity 响应必须是 mapping")
    method, resolution = _entry_method(entry_payload)
    entity_sequence, chains = _entity_fields(
        entity_payload,
        chain_namespace=preferred_chain_namespace,
    )
    chain = preferred_chain if preferred_chain in chains else chains[0]
    eligible, reasons = _quality_eligible(method, resolution)
    review_eligible = reasons == ["nmr-review-only"]
    identity = resolve_target_identity(
        target_id=f"{pdb_id.lower()}-{entity_id.lower()}",
        canonical_sequence=(
            (canonical_sequence or expected_scope)
            if biological_identity_resolved
            else None
        ),
        construct_sequence=entity_sequence,
        canonical_status=(
            CanonicalIdentityStatus.RESOLVED
            if biological_identity_resolved
            else CanonicalIdentityStatus.UNRESOLVED
        ),
        source_identity_status="resolved",
        source_kind="pdb",
        accession=accession,
        pdb_id=pdb_id.upper(),
        entity_id=entity_id,
        auth_chain_id=chain if preferred_chain_namespace == "auth" else None,
        label_chain_id=chain if preferred_chain_namespace == "label" else None,
        canonical_scope_start=canonical_scope_start,
        canonical_scope_end=canonical_scope_end,
        declared_relationship=declared_relationship,
    )
    design_sequence = identity.design_scope.sequence
    if biological_identity_resolved:
        if identity.review_requirement is ReviewRequirement.REJECT:
            eligible = False
            review_eligible = False
            reasons.append(f"target-identity-{identity.relationship}")
        elif identity.review_requirement is ReviewRequirement.HUMAN_REQUIRED:
            review_eligible = eligible or review_eligible
            eligible = False
            reasons.append("target-identity-human-review-required")
    warnings: list[str] = []
    coordinate_coverage = 0.0
    observed_scope_residue_count = 0
    missing_coordinate_ranges: list[dict[str, Any]] = []
    structure_path: Path | None = None
    selected_author_chain: str | None = None
    if eligible or review_eligible:
        structure_path = rcsb_mmcif(client, pdb_id).artifact_path
        inventory = inventory_structure(structure_path)
        try:
            selected = choose_chain(
                inventory,
                explicit_chain=chain,
                expected_sequence=design_sequence,
                chain_namespace=preferred_chain_namespace,
            )
            selected_author_chain = selected
            chain_info = next(
                item
                for item in inventory.chains
                if item.author_chain_id == selected
            )
            evidence = scope_coordinate_evidence(chain_info, design_sequence)
            coordinate_coverage = evidence.coordinate_coverage
            observed_scope_residue_count = evidence.observed_residue_count
            missing_coordinate_ranges = list(evidence.missing_coordinate_ranges)
            if coordinate_coverage < 1.0:
                warnings.append("scope-coordinate-coverage-partial")
        except TargetInputError as error:
            eligible = False
            review_eligible = False
            reasons.append(str(error))
    return {
        "pdb_id": pdb_id,
        "entity_id": entity_id,
        "chain": selected_author_chain or chain,
        "requested_chain": preferred_chain,
        "requested_chain_namespace": preferred_chain_namespace,
        "method": method,
        "resolution_angstrom": resolution,
        "entity_sequence_length": len(entity_sequence),
        "scope_coverage": identity.alignment.canonical_coverage if identity.alignment else 1.0,
        "scope_sequence_coverage": (
            identity.alignment.canonical_coverage if identity.alignment else 1.0
        ),
        "scope_identity": identity.alignment.sequence_identity if identity.alignment else 1.0,
        "scope_coordinate_coverage": coordinate_coverage,
        "observed_scope_residue_count": observed_scope_residue_count,
        "missing_coordinate_ranges": missing_coordinate_ranges,
        "target_structure_status": (
            "experimental-complete"
            if coordinate_coverage == 1.0
            else "experimental-partial"
        ),
        "eligible": eligible,
        "review_eligible": review_eligible,
        "reasons": reasons,
        "warnings": warnings,
        "identity_report": identity.model_dump(mode="json"),
        "design_scope_sequence": design_sequence,
        **_candidate_deposition_facts(entry_payload, entity_payload),
    }, structure_path


def _candidate_from_pdb_cross_reference(
    *,
    client: ScientificHttpClient,
    pdb_id: str,
    expected_scope: str,
    canonical_sequence: str | None = None,
    canonical_scope_start: int | None = None,
    canonical_scope_end: int | None = None,
    accession: str | None = None,
) -> tuple[dict[str, Any], Path | None] | None:
    entry_payload = rcsb_entry(client, pdb_id).json()
    if not isinstance(entry_payload, dict):
        raise TargetInputError("RCSB entry 响应必须是 mapping")
    entity_ids = entry_payload.get(
        "rcsb_entry_container_identifiers", {}
    ).get("polymer_entity_ids", [])
    if not isinstance(entity_ids, list):
        raise TargetInputError("RCSB entry 缺少 polymer_entity_ids")
    matches: list[tuple[str, tuple[str, ...]]] = []
    for entity_id in entity_ids:
        entity = rcsb_polymer_entity(client, pdb_id, str(entity_id)).json()
        if not isinstance(entity, dict):
            continue
        sequence, chains = _entity_fields(entity)
        identity = resolve_target_identity(
            target_id=f"{pdb_id.lower()}-{str(entity_id).lower()}",
            canonical_sequence=canonical_sequence or expected_scope,
            construct_sequence=sequence,
            canonical_status=CanonicalIdentityStatus.RESOLVED,
            source_identity_status="resolved",
            source_kind="pdb",
            accession=accession,
            pdb_id=pdb_id.upper(),
            entity_id=str(entity_id),
            canonical_scope_start=canonical_scope_start,
            canonical_scope_end=canonical_scope_end,
        )
        if identity.review_requirement is not ReviewRequirement.REJECT:
            matches.append((str(entity_id), chains))
    if len(matches) != 1:
        return None
    entity_id, chains = matches[0]
    return _candidate(
        client=client,
        pdb_id=pdb_id,
        entity_id=entity_id,
        expected_scope=expected_scope,
        preferred_chain=chains[0],
        canonical_sequence=canonical_sequence,
        canonical_scope_start=canonical_scope_start,
        canonical_scope_end=canonical_scope_end,
        accession=accession,
    )


def _remote_selection(
    prepared: PreparedRun,
    *,
    attempt_id: str = ATTEMPT_ID,
    approved_option: DecisionOption | None = None,
) -> _ExperimentalSelection | PredictionFallback | Stage01SourceOutcome:
    loaded = prepared.loaded_config
    assert isinstance(loaded, LoadedRemoteRunConfig)
    config = loaded.config
    source = config.stage01.target.source
    approved_payload = (
        approved_option.payload if approved_option is not None else {}
    )
    work = (
        prepared.workspace.attempt_root(StageId.TARGET_PREPARATION, attempt_id)
        / "work"
        / "retrieval"
    )
    work.mkdir(parents=True, exist_ok=False)
    with ScientificHttpClient(
        evidence_dir=work,
        cache_mode=str(config.workflow.cache_mode),
    ) as client:
        if isinstance(source, PdbIdSourceConfig):
            entry = rcsb_entry(client, source.pdb_id.upper()).json()
            if not isinstance(entry, dict):
                raise TargetInputError("RCSB entry 响应必须是 mapping")
            entity_ids = entry.get(
                "rcsb_entry_container_identifiers", {}
            ).get("polymer_entity_ids", [])
            if not isinstance(entity_ids, list):
                raise TargetInputError("RCSB entry 缺少 polymer_entity_ids")
            entity_matches: list[tuple[str, str, tuple[str, ...]]] = []
            for entity_id in entity_ids:
                entity = rcsb_polymer_entity(
                    client,
                    source.pdb_id.upper(),
                    str(entity_id),
                ).json()
                if not isinstance(entity, dict):
                    continue
                entity_sequence, chains = _entity_fields(
                    entity,
                    chain_namespace=source.chain_namespace,
                )
                if source.chain is None or source.chain in chains:
                    entity_matches.append((str(entity_id), entity_sequence, chains))
            approved_entity = (
                str(approved_payload.get("entity_id"))
                if approved_payload.get("entity_id") is not None
                else None
            )
            approved_chain = (
                str(approved_payload.get("chain"))
                if approved_payload.get("chain") is not None
                else None
            )
            if approved_entity is not None:
                entity_matches = [
                    item for item in entity_matches if item[0] == approved_entity
                ]
                if len(entity_matches) != 1:
                    raise TargetInputError(
                        "已批准的 PDB entity 不再匹配当前冻结配置"
                    )
            if len(entity_matches) != 1 and source.chain is None:
                if config.workflow.execution_mode is ExecutionMode.REVIEW_GATED:
                    return _pause_for_decision(
                        prepared,
                        gate="chain-selection",
                        message="PDB 含多条可设计 protein entity，请确认目标 chain。",
                        options=tuple(
                            DecisionOption(
                                option_id=(
                                    f"entity-{entity_id.lower()}-"
                                    f"chain-{chain.lower()}"
                                ),
                                label=(
                                    f"{source.pdb_id.upper()} entity {entity_id} "
                                    f"chain {chain}"
                                ),
                                description=f"length={len(sequence)}",
                                payload={
                                    "entity_id": entity_id,
                                    "chain": chain,
                                },
                            )
                            for entity_id, sequence, chains in entity_matches
                            for chain in chains
                        ),
                        attempt_id=attempt_id,
                    )
                raise TargetInputError("structure-chain-ambiguous")
            if len(entity_matches) != 1:
                raise TargetInputError("显式 PDB chain 无法唯一映射到 polymer entity")
            entity_id, reference, chains = entity_matches[0]
            selected_direct_chain = source.chain or approved_chain
            if selected_direct_chain is None and len(chains) > 1:
                if config.workflow.execution_mode is ExecutionMode.REVIEW_GATED:
                    return _pause_for_decision(
                        prepared,
                        gate="chain-selection",
                        message="PDB entity 映射到多个 chain，请确认目标 chain。",
                        options=tuple(
                            DecisionOption(
                                option_id=f"chain-{chain.lower()}",
                                label=f"{source.pdb_id.upper()} chain {chain}",
                                description=f"entity={entity_id}; length={len(reference)}",
                                payload={"entity_id": entity_id, "chain": chain},
                            )
                            for chain in chains
                        ),
                        attempt_id=attempt_id,
                    )
                raise TargetInputError("structure-chain-ambiguous")
            canonical_reference: str | None = None
            canonical_accession: str | None = None
            if source.identity.uniprot_accession is not None:
                identity_payload = uniprot_accession(
                    client,
                    source.identity.uniprot_accession,
                ).json()
                if not isinstance(identity_payload, dict):
                    raise TargetInputError("UniProt accession 响应必须是 mapping")
                canonical_accession, canonical_reference, canonical_identity = (
                    _uniprot_identity(identity_payload)
                )
                if not canonical_identity["reviewed"]:
                    raise TargetInputError(
                        "显式 PDB canonical identity 必须是 reviewed UniProt entry"
                    )
                if (
                    source.identity.taxon_id is not None
                    and canonical_identity["taxonomy_id"] != source.identity.taxon_id
                ):
                    raise TargetInputError("显式 PDB UniProt taxonomy 与配置不一致")
                resolved_scope = _scope_with_decision(
                    prepared,
                    reference_sequence=canonical_reference,
                    features=(
                        identity_payload.get("features")
                        if isinstance(identity_payload.get("features"), list)
                        else None
                    ),
                    approved_option=approved_option,
                    attempt_id=attempt_id,
                )
                if isinstance(resolved_scope, Stage01SourceOutcome):
                    return resolved_scope
                expected, start, end, scope_report = resolved_scope
            else:
                expected, start, end, scope_report = _scope(
                    config,
                    reference_sequence=reference,
                )
            candidate, path = _candidate(
                client=client,
                pdb_id=source.pdb_id.upper(),
                entity_id=entity_id,
                expected_scope=expected,
                preferred_chain=selected_direct_chain,
                preferred_chain_namespace=source.chain_namespace,
                biological_identity_resolved=canonical_reference is not None,
                declared_relationship=(
                    None
                    if source.identity.relationship is None
                    else ConstructRelationship(source.identity.relationship)
                ),
                accession=canonical_accession,
                canonical_scope_start=start if canonical_reference is not None else None,
                canonical_scope_end=end if canonical_reference is not None else None,
                canonical_sequence=canonical_reference,
            )
            identity_review_reason = "target-identity-human-review-required"
            identity_review_only = (
                canonical_reference is not None
                and candidate.get("review_eligible") is True
                and identity_review_reason in candidate["reasons"]
                and all(reason == identity_review_reason for reason in candidate["reasons"])
            )
            identity_review_approved = (
                approved_payload.get("action") == "approve-target-identity"
            )
            if identity_review_only and not identity_review_approved:
                if config.workflow.execution_mode is ExecutionMode.UNATTENDED:
                    raise TargetInputError("target-identity-review-required: unattended 停止")
                return _pause_for_decision(
                    prepared,
                    gate="target-identity-review",
                    message=(
                        "显式 PDB construct 与 canonical target 非 exact；"
                        "请审核 residue mapping 与 construct edits。"
                    ),
                    options=(
                        DecisionOption(
                            option_id=(
                                f"pdb-{source.pdb_id.lower()}-"
                                f"chain-{str(candidate['chain']).lower()}"
                            ),
                            label=(
                                f"Approve mapped {source.pdb_id.upper()} "
                                f"chain {candidate['chain']}"
                            ),
                            description=(
                                f"relationship={candidate['identity_report']['relationship']}; "
                                "canonical residue mapping will remain authoritative"
                            ),
                            payload={
                                "action": "approve-target-identity",
                                "entity_id": entity_id,
                                "chain": candidate["chain"],
                            },
                        ),
                    ),
                    attempt_id=attempt_id,
                )
            if (
                (not candidate["eligible"] and not identity_review_only)
                or path is None
            ):
                raise TargetInputError(
                    "显式 PDB ID 未通过 experimental-strict-v1；禁止自动换结构: "
                    f"{candidate['reasons']}"
                )
            direct_identity = candidate["identity_report"]
            return _ExperimentalSelection(
                source_path=path,
                selected_chain=str(candidate["chain"]),
                expected_scope_sequence=expected,
                reference_sequence=canonical_reference or reference,
                reference_start=start,
                identity_report=direct_identity,
                scope_report=scope_report,
                candidates=[candidate],
                quality_report={
                    "schema_version": "0.2",
                    "origin": "experimental",
                    "eligibility": "eligible",
                    "quality_profile": "experimental-strict-v1",
                    **candidate,
                },
                provenance={
                    "schema_version": "0.2",
                    "origin": "experimental",
                    "source": "rcsb-pdb-id",
                    "pdb_id": source.pdb_id.upper(),
                    "selected_chain": candidate["chain"],
                    "fallback_used": False,
                },
                retrieval_records=[
                    record.model_dump(mode="json") for record in client.records
                ],
            )

        assert isinstance(source, (UniProtSourceConfig, UniProtSearchSourceConfig))
        approved_accession = (
            str(approved_payload.get("accession"))
            if approved_payload.get("accession") is not None
            else None
        )
        if isinstance(source, UniProtSourceConfig) or approved_accession is not None:
            requested_accession = (
                source.accession
                if isinstance(source, UniProtSourceConfig)
                else approved_accession
            )
            assert requested_accession is not None
            response = uniprot_accession(client, requested_accession)
            payload = response.json()
            if not isinstance(payload, dict):
                raise TargetInputError("UniProt accession 响应必须是 mapping")
            accession, reference, identity = _uniprot_identity(payload)
            configured_taxon = source.organism_taxon_id
            configured_reviewed = source.reviewed
            if configured_taxon is not None and (
                identity["taxonomy_id"] != configured_taxon
            ):
                raise TargetInputError("UniProt taxonomy 与配置不一致")
            if configured_reviewed == "required" and not identity["reviewed"]:
                raise TargetInputError("UniProt entry 不是 reviewed")
            features = payload.get("features")
        else:
            assert isinstance(source, UniProtSearchSourceConfig)
            search = uniprot_search(
                client,
                query=source.query,
                taxon_id=source.organism_taxon_id,
            ).json()
            if not isinstance(search, dict):
                raise TargetInputError("UniProt search 响应必须是 mapping")
            search_matches = _search_matches(search, source.query)
            high_confidence = [
                item
                for item in search_matches
                if item["exact"] and (item["reviewed"] or source.reviewed != "required")
            ]
            if len(high_confidence) != 1:
                if config.workflow.execution_mode is ExecutionMode.REVIEW_GATED:
                    return _pause_for_decision(
                        prepared,
                        gate="identity-selection",
                        message=(
                            "UniProt 名称/基因检索没有唯一 reviewed 高置信命中，"
                            "请确认 accession。"
                        ),
                        options=tuple(
                            DecisionOption(
                                option_id=f"uniprot-{item['accession'].lower()}",
                                label=f"{item['accession']} {item['entry_id']}",
                                description=(
                                    f"reviewed={item['reviewed']}; "
                                    f"genes={','.join(item['gene_names'])}; "
                                    f"name={item['recommended_name']}"
                                ),
                                payload={"accession": item["accession"]},
                            )
                            for item in search_matches[:10]
                        ),
                        attempt_id=attempt_id,
                    )
                raise TargetInputError(
                    "uniprot-identity-ambiguous: unattended 仅接受唯一 reviewed 精确命中"
                )
            payload = high_confidence[0]["payload"]
            accession, reference, identity = _uniprot_identity(payload)
            identity["identity_resolution"] = "unique-reviewed-exact-search"
            features = payload.get("features")
        resolved_scope = _scope_with_decision(
            prepared,
            reference_sequence=reference,
            features=features if isinstance(features, list) else None,
            approved_option=approved_option,
            attempt_id=attempt_id,
        )
        if isinstance(resolved_scope, Stage01SourceOutcome):
            return resolved_scope
        expected, start, end, scope_report = resolved_scope
        search_payload = rcsb_sequence_search(client, expected).json()
        if not isinstance(search_payload, dict):
            raise TargetInputError("RCSB sequence search 响应必须是 mapping")
        raw_results = search_payload.get("result_set", [])
        if not isinstance(raw_results, list):
            raise TargetInputError("RCSB sequence search result_set 不是 list")
        candidates: list[dict[str, Any]] = []
        paths: dict[tuple[str, str], Path] = {}
        seen_entities: set[tuple[str, str]] = set()
        cross_references = payload.get("uniProtKBCrossReferences", [])
        pdb_cross_references = [
            item
            for item in cross_references
            if isinstance(item, dict) and item.get("database") == "PDB"
        ]
        for reference_item in pdb_cross_references[:16]:
            pdb_id = str(reference_item.get("id", ""))
            if not pdb_id:
                continue
            resolved_candidate = _candidate_from_pdb_cross_reference(
                client=client,
                pdb_id=pdb_id,
                expected_scope=expected,
                canonical_sequence=reference,
                canonical_scope_start=start,
                canonical_scope_end=end,
                accession=accession,
            )
            if resolved_candidate is None:
                continue
            candidate, path = resolved_candidate
            key = (str(candidate["pdb_id"]), str(candidate["entity_id"]))
            if key in seen_entities:
                continue
            seen_entities.add(key)
            candidates.append(candidate)
            if path is not None:
                paths[key] = path
        for result in raw_results[:RCSB_SEQUENCE_RESULT_LIMIT]:
            identifier = str(result.get("identifier", ""))
            if "_" not in identifier:
                continue
            pdb_id, entity_id = identifier.split("_", maxsplit=1)
            if (pdb_id, entity_id) in seen_entities:
                continue
            candidate, path = _candidate(
                client=client,
                pdb_id=pdb_id,
                entity_id=entity_id,
                expected_scope=expected,
                accession=accession,
                canonical_sequence=reference,
                canonical_scope_start=start,
                canonical_scope_end=end,
            )
            seen_entities.add((pdb_id, entity_id))
            candidates.append(candidate)
            if path is not None:
                paths[(pdb_id, entity_id)] = path
        eligible = [candidate for candidate in candidates if candidate["eligible"]]
        review_candidates = [
            candidate
            for candidate in candidates
            if candidate.get("review_eligible") is True
        ]
        selectable = eligible + review_candidates
        retrieval = [record.model_dump(mode="json") for record in client.records]
        fallback = PredictionFallback(
            target=normalize_raw_sequence(
                expected,
                target_id=config.target.target_id,
                source_label=f"UniProt:{accession}:{start}-{end}",
            ),
            reference_sequence=reference,
            identity_report=identity,
            scope_report=scope_report,
            candidates=candidates,
            retrieval_records=retrieval,
            reason=(
                "no-eligible-experimental-candidate"
                if not eligible
                else "ambiguous-experimental-candidates"
            ),
        )
        approved_action = (
            str(approved_payload.get("action"))
            if approved_payload.get("action") is not None
            else None
        )
        if approved_action == "predict":
            return fallback
        if approved_action == "select-experimental":
            selected_pdb = str(approved_payload.get("pdb_id", ""))
            selected_entity = str(approved_payload.get("entity_id", ""))
            approved_matches = [
                candidate
                for candidate in selectable
                if str(candidate["pdb_id"]) == selected_pdb
                and str(candidate["entity_id"]) == selected_entity
            ]
            if len(approved_matches) != 1:
                raise TargetInputError(
                    "已批准的实验结构不再属于当前 eligible 候选集"
                )
            selected = approved_matches[0]
            key = (str(selected["pdb_id"]), str(selected["entity_id"]))
            return _ExperimentalSelection(
                source_path=paths[key],
                selected_chain=str(selected["chain"]),
                expected_scope_sequence=expected,
                reference_sequence=reference,
                reference_start=start,
                identity_report=identity,
                scope_report=scope_report,
                candidates=candidates,
                quality_report={
                    "schema_version": "0.2",
                    "origin": "experimental",
                    "quality_profile": "experimental-strict-v1",
                    **selected,
                    "selection_status": "human-approved",
                },
                provenance={
                    "schema_version": "0.2",
                    "origin": "experimental",
                    "source": "uniprot-rcsb-selection",
                    "uniprot_accession": accession,
                    "pdb_id": selected["pdb_id"],
                    "selected_chain": selected["chain"],
                    "fallback_used": False,
                    "decision_authority": "human",
                },
                retrieval_records=retrieval,
            )
        if len(eligible) == 1:
            selected = eligible[0]
            key = (str(selected["pdb_id"]), str(selected["entity_id"]))
            return _ExperimentalSelection(
                source_path=paths[key],
                selected_chain=str(selected["chain"]),
                expected_scope_sequence=expected,
                reference_sequence=reference,
                reference_start=start,
                identity_report=identity,
                scope_report=scope_report,
                candidates=candidates,
                quality_report={
                    "schema_version": "0.2",
                    "origin": "experimental",
                    "eligibility": "eligible",
                    "quality_profile": "experimental-strict-v1",
                    **selected,
                },
                provenance={
                    "schema_version": "0.2",
                    "origin": "experimental",
                    "source": "uniprot-rcsb-selection",
                    "uniprot_accession": accession,
                    "pdb_id": selected["pdb_id"],
                    "selected_chain": selected["chain"],
                    "fallback_used": False,
                },
                retrieval_records=retrieval,
            )
        selection_policy = config.stage01.structure_selection
        if (
            not eligible
            and selection_policy.on_no_eligible_candidate == "fail"
        ) or (
            len(eligible) > 1
            and selection_policy.on_ambiguous_candidates == "fail"
        ):
            raise TargetInputError(
                f"{fallback.reason}: structure_selection policy=fail"
            )
        if config.workflow.execution_mode is ExecutionMode.UNATTENDED:
            _require_prediction_backend(config)
            return fallback
        prediction_presentation = _prediction_backend_presentation(config)
        options = tuple(_structure_selection_option(item) for item in selectable)
        if prediction_presentation is not None:
            prediction_option_id, prediction_label = prediction_presentation
            options += (
                DecisionOption(
                    option_id=prediction_option_id,
                    label=f"使用 {prediction_label} 预测",
                    description=(
                        f"没有唯一 eligible 实验结构；按 required-MSA {prediction_label} "
                        "预测 design scope。"
                    ),
                    payload={"action": "predict", "reason": fallback.reason},
                ),
            )
        elif not options:
            raise ConfigurationError(
                "Stage 1 检索后确认需要预测 target；请带 "
                "--prediction-backend afo 或 protenix 重新运行 target prepare"
            )
        return _pause_for_decision(
            prepared,
            gate="structure-selection",
            message=(
                "已按确定性证据排序推荐首选实验结构；请审核并批准，"
                "或选择其他结构/预测后端。"
            ),
            options=options,
            attempt_id=attempt_id,
        )


def _sequence_selection(
    prepared: PreparedRun,
    *,
    attempt_id: str = ATTEMPT_ID,
    approved_option: DecisionOption | None = None,
) -> _ExperimentalSelection | PredictionFallback | Stage01SourceOutcome:
    """对 FASTA/裸序列先执行官方 RCSB exact-scope 实验结构检索。"""

    loaded = prepared.loaded_config
    assert isinstance(loaded, LoadedSequenceRunConfig)
    config = loaded.config
    approved_payload = (
        approved_option.payload if approved_option is not None else {}
    )
    source = config.target.source
    assert isinstance(source, LocalFileSourceConfig)
    reference = loaded.target.sequence
    expected = reference
    start = 1
    end = len(reference)
    scope_report: dict[str, Any]
    identity: dict[str, Any] = {
        "schema_version": "0.1",
        "status": "explicit-sequence",
        "identity_resolution": "user-input",
        "sequence_sha256": loaded.target.sequence_sha256,
    }
    work = (
        prepared.workspace.attempt_root(StageId.TARGET_PREPARATION, attempt_id)
        / "work"
        / "retrieval"
    )
    work.mkdir(parents=True, exist_ok=False)
    with ScientificHttpClient(
        evidence_dir=work,
        cache_mode=str(config.workflow.cache_mode),
    ) as client:
        if source.identity.uniprot_accession is None:
            expected, start, end, scope_report = _scope(
                config,
                reference_sequence=reference,
            )
            scope_report["coordinate_frame"] = "input-sequence"
        else:
            payload = uniprot_accession(
                client,
                source.identity.uniprot_accession,
            ).json()
            if not isinstance(payload, dict):
                raise TargetInputError("UniProt accession 响应必须是 mapping")
            accession, canonical, identity = _uniprot_identity(payload)
            offsets = [
                index + 1
                for index in range(len(canonical))
                if canonical.startswith(loaded.target.sequence, index)
            ]
            if len(offsets) != 1:
                raise TargetInputError(
                    "本地 sequence/FASTA 必须与 UniProt canonical sequence "
                    f"形成唯一精确全长或子序列映射: accession={accession}, "
                    f"matches={len(offsets)}"
                )
            input_reference_start = offsets[0]
            reference = canonical
            if isinstance(config.target.scope, UniProtFeatureScope):
                resolved_scope = _scope_with_decision(
                    prepared,
                    reference_sequence=canonical,
                    features=(
                        payload.get("features")
                        if isinstance(payload.get("features"), list)
                        else None
                    ),
                    approved_option=approved_option,
                    attempt_id=attempt_id,
                )
                if isinstance(resolved_scope, Stage01SourceOutcome):
                    return resolved_scope
                expected, start, end, scope_report = resolved_scope
                input_reference_end = (
                    input_reference_start + len(loaded.target.sequence) - 1
                )
                if start < input_reference_start or end > input_reference_end:
                    raise TargetInputError(
                        "UniProt feature scope 不完全包含在本地输入 sequence 中"
                    )
            else:
                expected, local_start, local_end, scope_report = _scope(
                    config,
                    reference_sequence=loaded.target.sequence,
                )
                start = input_reference_start + local_start - 1
                end = input_reference_start + local_end - 1
                scope_report["start"] = start
                scope_report["end"] = end
            scope_report["coordinate_frame"] = "uniprot-canonical"
            identity["input_sequence_reference_start"] = input_reference_start
            identity["input_sequence_reference_end"] = (
                input_reference_start + len(loaded.target.sequence) - 1
            )
        search_payload = rcsb_sequence_search(client, expected).json()
        if not isinstance(search_payload, dict):
            raise TargetInputError("RCSB sequence search 响应必须是 mapping")
        raw_results = search_payload.get("result_set", [])
        if not isinstance(raw_results, list):
            raise TargetInputError("RCSB sequence search result_set 不是 list")
        candidates: list[dict[str, Any]] = []
        paths: dict[tuple[str, str], Path] = {}
        seen_entities: set[tuple[str, str]] = set()
        for result in raw_results[:RCSB_SEQUENCE_RESULT_LIMIT]:
            identifier = str(result.get("identifier", ""))
            if "_" not in identifier:
                continue
            pdb_id, entity_id = identifier.split("_", maxsplit=1)
            key = (pdb_id, entity_id)
            if key in seen_entities:
                continue
            candidate, structure_path = _candidate(
                client=client,
                pdb_id=pdb_id,
                entity_id=entity_id,
                expected_scope=expected,
                accession=config.target.identity.uniprot_accession,
                canonical_sequence=reference,
                canonical_scope_start=start,
                canonical_scope_end=end,
                declared_relationship=(
                    None
                    if config.target.identity.relationship is None
                    else ConstructRelationship(config.target.identity.relationship)
                ),
            )
            seen_entities.add(key)
            candidates.append(candidate)
            if structure_path is not None:
                paths[key] = structure_path
        retrieval = [record.model_dump(mode="json") for record in client.records]

    eligible = [candidate for candidate in candidates if candidate["eligible"]]
    review_candidates = [
        candidate
        for candidate in candidates
        if candidate.get("review_eligible") is True
    ]
    selectable = eligible + review_candidates
    reason = (
        "no-eligible-experimental-candidate"
        if not eligible
        else "ambiguous-experimental-candidates"
    )
    fallback = PredictionFallback(
        target=normalize_raw_sequence(
            expected,
            target_id=config.target.target_id,
            source_label=f"sequence:{start}-{end}",
        ),
        reference_sequence=reference,
        identity_report=identity,
        scope_report=scope_report,
        candidates=candidates,
        retrieval_records=retrieval,
        reason=reason,
    )
    approved_action = (
        str(approved_payload.get("action"))
        if approved_payload.get("action") is not None
        else None
    )
    if approved_action == "predict":
        return fallback
    if approved_action == "select-experimental":
        selected_pdb = str(approved_payload.get("pdb_id", ""))
        selected_entity = str(approved_payload.get("entity_id", ""))
        eligible = [
            candidate
            for candidate in selectable
            if str(candidate["pdb_id"]) == selected_pdb
            and str(candidate["entity_id"]) == selected_entity
        ]
        if len(eligible) != 1:
            raise TargetInputError(
                "已批准的实验结构不再属于当前 eligible 候选集"
            )
        identity["selection_authority"] = "human"
    if len(eligible) == 1:
        selected = eligible[0]
        key = (str(selected["pdb_id"]), str(selected["entity_id"]))
        return _ExperimentalSelection(
            source_path=paths[key],
            selected_chain=str(selected["chain"]),
            expected_scope_sequence=expected,
            reference_sequence=reference,
            reference_start=start,
            identity_report=identity,
            scope_report=scope_report,
            candidates=candidates,
            quality_report={
                "schema_version": "0.2",
                "origin": "experimental",
                "eligibility": "eligible",
                "quality_profile": "experimental-strict-v1",
                **selected,
            },
            provenance={
                "schema_version": "0.2",
                "origin": "experimental",
                "source": "sequence-rcsb-selection",
                "pdb_id": selected["pdb_id"],
                "selected_chain": selected["chain"],
                "fallback_used": False,
            },
            retrieval_records=retrieval,
        )
    selection_policy = config.stage01.structure_selection
    if (
        not eligible
        and selection_policy.on_no_eligible_candidate == "fail"
    ) or (
        len(eligible) > 1
        and selection_policy.on_ambiguous_candidates == "fail"
    ):
        raise TargetInputError(f"{reason}: structure_selection policy=fail")
    if config.workflow.execution_mode is ExecutionMode.UNATTENDED:
        _require_prediction_backend(config)
        return fallback
    prediction_presentation = _prediction_backend_presentation(config)
    options = tuple(_structure_selection_option(item) for item in selectable)
    if prediction_presentation is not None:
        prediction_option_id, prediction_label = prediction_presentation
        options += (
            DecisionOption(
                option_id=prediction_option_id,
                label=f"使用 {prediction_label} 预测",
                description=f"按 required-MSA {prediction_label} 预测 design scope。",
                payload={"action": "predict", "reason": reason},
            ),
        )
    elif not options:
        raise ConfigurationError(
            "Stage 1 检索后确认需要预测 target；请带 "
            "--prediction-backend afo 或 protenix 重新运行 target prepare"
        )
    return _pause_for_decision(
        prepared,
        gate="structure-selection",
        message=(
            "序列检索已按确定性证据排序推荐首选实验结构；请审核并批准，"
            "或选择其他结构/预测后端。"
        ),
        options=options,
        attempt_id=attempt_id,
    )


def _execute_experimental(
    prepared: PreparedRun,
    selection: _ExperimentalSelection,
    *,
    attempt_id: str = ATTEMPT_ID,
) -> Stage01SourceOutcome:
    start = datetime.now(UTC)
    identity_payload = selection.quality_report.get(
        "identity_report",
        selection.identity_report,
    )
    identity_mapping = selection.identity_mapping
    expected_scope_sequence = selection.expected_scope_sequence
    if isinstance(identity_payload, dict) and identity_payload.get("schema_version") == "0.2":
        identity_v2 = TargetIdentityReport.model_validate(identity_payload)
        identity_v2 = identity_v2.model_copy(
            update={"target_id": prepared.loaded_config.config.target.target_id}
        )
        identity_payload = identity_v2.model_dump(mode="json")
        identity_mapping = identity_v2.design_scope.residues
        expected_scope_sequence = identity_v2.design_scope.sequence
    result = build_experimental_target_bundle(
        run_root=prepared.workspace.run_root,
        attempt_id=attempt_id,
        target_id=prepared.loaded_config.config.target.target_id,
        source_path=selection.source_path,
        source_format=selection.source_path.suffix.lower().lstrip("."),
        selected_chain=selection.selected_chain,
        expected_scope_sequence=expected_scope_sequence,
        reference_sequence=selection.reference_sequence,
        reference_start=selection.reference_start,
        identity_report=identity_payload,
        scope_report=selection.scope_report,
        candidates=selection.candidates,
        quality_report=selection.quality_report,
        provenance=selection.provenance,
        retrieval_records=selection.retrieval_records,
        preserve_source_context=(
            prepared.loaded_config.config.stage01.structure_selection.preserve_source_context
        ),
        keep_ligands=(
            prepared.loaded_config.config.stage01.structure_selection.keep_ligands
        ),
        identity_mapping=identity_mapping,
    )
    ended = _strictly_later(datetime.now(UTC), start)
    attempt = Attempt(
        attempt_id=attempt_id,
        status=ExecutionStatus.SUCCEEDED,
        created_at=start,
        started_at=start,
        ended_at=ended,
        backend_name="easydesign-structure-normalizer",
        backend_version="0.1",
        executor_name="in-process",
    )
    attempt_root = prepared.workspace.attempt_root(
        StageId.TARGET_PREPARATION,
        attempt_id,
    )
    dump_model(attempt, attempt_root / "attempt-manifest.json")
    resolved = load_model(prepared.workspace.resolved_config, ResolvedRunConfig)
    stage = StageManifest(
        stage_id=StageId.TARGET_PREPARATION,
        contract_version="0.5",
        status=ExecutionStatus.SUCCEEDED,
        created_at=start,
        completed_at=ended,
        input_artifacts=(resolved.input_snapshot,),
        output_artifacts=result.output_artifacts,
        attempts=(attempt,),
        selected_attempt_id=attempt_id,
    )
    stage_path = dump_model(
        stage,
        prepared.workspace.stage_root(StageId.TARGET_PREPARATION)
        / "stage-manifest.v0001.json",
    )
    run_manifest = _publish_run(
        prepared,
        stage_manifest=stage_path,
        ended_at=ended,
        attempt_id=attempt_id,
    )
    viewer = generate_stage01_target_viewer_nonblocking(prepared.workspace.run_root)
    return Stage01SourceOutcome(
        status="succeeded",
        run_root=prepared.workspace.run_root,
        run_manifest=run_manifest,
        built_bundle=result.built_bundle,
        viewer_status=str(viewer.status),
    )


def _local_selection(
    prepared: PreparedRun,
    *,
    attempt_id: str = ATTEMPT_ID,
    approved_option: DecisionOption | None = None,
) -> _ExperimentalSelection | Stage01SourceOutcome:
    loaded = prepared.loaded_config
    assert isinstance(loaded, LoadedStructureRunConfig)
    inventory = inventory_structure(loaded.source_path)
    protein_chain_ids = frozenset(inventory.protein_chain_ids)
    if not protein_chain_ids:
        raise TargetInputError("local structure 不包含可用的 protein chain")
    protein_chains = tuple(
        chain
        for chain in inventory.chains
        if chain.author_chain_id in protein_chain_ids
        and bool(chain.deposited_sequence or chain.sequence)
    )
    if {chain.author_chain_id for chain in protein_chains} != protein_chain_ids:
        raise TargetInputError(
            "local structure protein chain 缺少非空 canonical amino-acid sequence"
        )
    source = loaded.config.stage01.target.source
    assert isinstance(source, LocalFileSourceConfig)
    identity = source.identity
    expected: str | None = None
    reference: str | None = None
    reference_start: int | None = None
    scope_report: dict[str, Any]
    if identity.uniprot_accession is None:
        if not isinstance(
            loaded.config.stage01.target.scope,
            FullSequenceScope,
        ):
            raise TargetInputError(
                "structural-only 本地结构只能使用 full-sequence scope；"
                "residue-range/uniprot-feature 需要可验证的 UniProt 身份"
            )
        approved_chain = source.chain or (
            str(approved_option.payload.get("chain"))
            if approved_option is not None
            and approved_option.payload.get("chain") is not None
            else None
        )
        if approved_chain is not None:
            approved_namespace = (
                source.chain_namespace
                if source.chain is not None
                else str(
                    approved_option.payload.get("chain_namespace", "auth")
                    if approved_option is not None
                    else "auth"
                )
            )
            selected = choose_chain(
                inventory,
                explicit_chain=approved_chain,
                expected_sequence=None,
                chain_namespace=approved_namespace,
            )
        elif len(inventory.protein_chain_ids) != 1:
            if loaded.config.workflow.execution_mode is ExecutionMode.UNATTENDED:
                raise TargetInputError(
                    "ambiguous-local-protein-chain: unattended 必须显式提供 chain"
                )
            return _pause_for_decision(
                prepared,
                gate="chain-selection",
                message="本地结构含多条 protein chain，请确认目标 chain。",
                options=tuple(
                    DecisionOption(
                        option_id=f"chain-{chain.lower()}",
                        label=f"chain {chain}",
                        description="本地结构 protein chain",
                        payload={"chain": chain, "chain_namespace": "auth"},
                    )
                    for chain in inventory.protein_chain_ids
                ),
                attempt_id=attempt_id,
            )
        else:
            selected = inventory.protein_chain_ids[0]
        observed = next(
            chain.sequence
            for chain in inventory.chains
            if chain.author_chain_id == selected
        )
        selected_chain_info = next(
            chain for chain in inventory.chains if chain.author_chain_id == selected
        )
        expected = observed
        scope_report = {
            "schema_version": "0.1",
            "type": "structural-observed",
            "start": 1,
            "end": len(observed),
            "length": len(observed),
            "reference_completeness": "unknown",
            "evidence_limitations": ["reference-completeness-unknown"],
        }
        identity_v2 = resolve_target_identity(
            target_id=loaded.config.stage01.target.target_id,
            canonical_sequence=None,
            construct_sequence=selected_chain_info.deposited_sequence or observed,
            canonical_status=CanonicalIdentityStatus.UNRESOLVED,
            source_identity_status="user-declared",
            source_kind="local-structure",
            auth_chain_id=selected_chain_info.author_chain_id,
            label_chain_id=selected_chain_info.label_chain_id,
            coordinate_present_construct_positions=(
                selected_chain_info.coordinate_label_seq_ids
            ),
        )
        identity_report = identity_v2.model_dump(mode="json")
    else:
        work = (
            prepared.workspace.attempt_root(
                StageId.TARGET_PREPARATION,
                attempt_id,
            )
            / "work"
            / "retrieval"
        )
        work.mkdir(parents=True, exist_ok=False)
        with ScientificHttpClient(
            evidence_dir=work,
            cache_mode=str(loaded.config.workflow.cache_mode),
        ) as client:
            payload = uniprot_accession(client, identity.uniprot_accession).json()
            if not isinstance(payload, dict):
                raise TargetInputError("UniProt accession 响应必须是 mapping")
            _, reference, identity_report = _uniprot_identity(payload)
            resolved_scope = _scope_with_decision(
                prepared,
                reference_sequence=reference,
                features=(
                    payload.get("features")
                    if isinstance(payload.get("features"), list)
                    else None
                ),
                approved_option=approved_option,
                attempt_id=attempt_id,
            )
            if isinstance(resolved_scope, Stage01SourceOutcome):
                return resolved_scope
            expected, reference_start, reference_end, scope_report = resolved_scope
            retrieval = [record.model_dump(mode="json") for record in client.records]
        approved_chain = (
            str(approved_option.payload.get("chain"))
            if approved_option is not None
            and approved_option.payload.get("chain") is not None
            else None
        )
        declared_relationship = (
            None
            if identity.relationship is None
            else ConstructRelationship(identity.relationship)
        )
        identity_by_chain = {
            chain.author_chain_id: resolve_target_identity(
                target_id=loaded.config.stage01.target.target_id,
                canonical_sequence=reference,
                construct_sequence=chain.deposited_sequence or chain.sequence,
                canonical_status=CanonicalIdentityStatus.RESOLVED,
                source_identity_status="resolved",
                source_kind="local-structure",
                accession=identity.uniprot_accession,
                isoform=identity.isoform,
                taxon_id=identity.taxon_id,
                auth_chain_id=chain.author_chain_id,
                label_chain_id=chain.label_chain_id,
                coordinate_present_construct_positions=chain.coordinate_label_seq_ids,
                declared_relationship=declared_relationship,
                canonical_scope_start=reference_start,
                canonical_scope_end=reference_end,
            )
            for chain in protein_chains
        }
        selectable_chains = tuple(
            chain_id
            for chain_id, report in identity_by_chain.items()
            if report.review_requirement is not ReviewRequirement.REJECT
        )
        requested_chain = source.chain or approved_chain
        if requested_chain is not None:
            selected = choose_chain(
                inventory,
                explicit_chain=requested_chain,
                expected_sequence=None,
                chain_namespace=(
                    source.chain_namespace if source.chain is not None else "auth"
                ),
            )
            if selected not in selectable_chains:
                raise TargetInputError("指定 chain 与 canonical target 无法建立可靠 mapping")
        elif len(selectable_chains) == 1:
            selected = selectable_chains[0]
        elif len(selectable_chains) > 1:
            if loaded.config.workflow.execution_mode is ExecutionMode.UNATTENDED:
                raise TargetInputError("ambiguous-local-identity-chain: unattended 停止")
            return _pause_for_decision(
                prepared,
                gate="chain-selection",
                message="多条本地 protein chain 可映射到 design scope，请审核 identity 后选择。",
                options=tuple(
                    DecisionOption(
                        option_id=f"chain-{chain.lower()}",
                        label=f"chain {chain}",
                        description=(
                            f"relationship={identity_by_chain[chain].relationship}; "
                            f"review={identity_by_chain[chain].review_requirement}"
                        ),
                        payload={"chain": chain, "chain_namespace": "auth"},
                    )
                    for chain in selectable_chains
                ),
                attempt_id=attempt_id,
            )
        else:
            raise TargetInputError("local structure 没有可解释的 canonical/design mapping")
        identity_v2 = identity_by_chain[selected]
        if (
            identity_v2.review_requirement is ReviewRequirement.HUMAN_REQUIRED
            and approved_option is None
        ):
            if loaded.config.workflow.execution_mode is ExecutionMode.UNATTENDED:
                raise TargetInputError("target-identity-review-required: unattended 停止")
            return _pause_for_decision(
                prepared,
                gate="target-identity-review",
                message="实验 construct 与 canonical target 非 exact；请审核 mapping/edits。",
                options=(
                    DecisionOption(
                        option_id=f"chain-{selected.lower()}",
                        label=f"Approve mapped chain {selected}",
                        description=(
                            f"relationship={identity_v2.relationship}; "
                            f"mapping={identity_v2.design_scope.mapping_status}"
                        ),
                        payload={"chain": selected, "chain_namespace": "auth"},
                    ),
                ),
                attempt_id=attempt_id,
            )
        return _ExperimentalSelection(
            source_path=loaded.source_path,
            selected_chain=selected,
            expected_scope_sequence=identity_v2.design_scope.sequence,
            reference_sequence=reference,
            reference_start=reference_start,
            identity_report=identity_v2.model_dump(mode="json"),
            scope_report=scope_report,
            candidates=[],
            quality_report={
                "schema_version": "0.2",
                "origin": "experimental",
                "eligibility": "eligible",
                "quality_profile": "local-explicit-structure",
                "reference_completeness": "known",
                "identity_report": identity_v2.model_dump(mode="json"),
            },
            provenance={
                "schema_version": "0.2",
                "origin": "experimental",
                "source": "local-file",
                "selected_chain": selected,
                "fallback_used": False,
            },
            retrieval_records=retrieval,
            identity_mapping=identity_v2.design_scope.residues,
        )
    return _ExperimentalSelection(
        source_path=loaded.source_path,
        selected_chain=selected,
        expected_scope_sequence=expected,
        reference_sequence=reference,
        reference_start=reference_start,
        identity_report=identity_report,
        scope_report=scope_report,
        candidates=[],
        quality_report={
            "schema_version": "0.2",
            "origin": "experimental",
            "eligibility": "structural-only-warning",
            "quality_profile": "local-structural-only",
            "reference_completeness": "unknown",
        },
        provenance={
            "schema_version": "0.2",
            "origin": "experimental",
            "source": "local-file",
            "selected_chain": selected,
            "fallback_used": False,
        },
        retrieval_records=[],
        identity_mapping=identity_v2.design_scope.residues,
    )


def _import_bundle(
    prepared: PreparedRun,
    *,
    attempt_id: str = ATTEMPT_ID,
) -> Stage01SourceOutcome:
    loaded = prepared.loaded_config
    assert isinstance(loaded, LoadedTargetBundleRunConfig)
    source_bundle = load_model(loaded.source_path, TargetBundle)
    if source_bundle.target_id != loaded.config.target.target_id:
        raise TargetInputError(
            "Target Bundle target_id 与配置不一致；禁止静默重命名编号身份: "
            f"bundle={source_bundle.target_id}, config={loaded.config.target.target_id}"
        )
    source_bundle.target_structure.verify(loaded.source_run_root)
    source_bundle.sequence.verify(loaded.source_run_root)
    source_bundle.residue_mapping.verify(loaded.source_run_root)
    source_bundle.quality_report.verify(loaded.source_run_root)
    source_bundle.provenance.verify(loaded.source_run_root)
    attempt_root = prepared.workspace.attempt_root(
        StageId.TARGET_PREPARATION,
        attempt_id,
    )
    artifacts = attempt_root / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=False)
    copied: dict[str, Path] = {}
    for name, reference in (
        ("target.cif", source_bundle.target_structure),
        ("sequence.fasta", source_bundle.sequence),
        ("residue-mapping.json", source_bundle.residue_mapping),
        ("structure-quality.json", source_bundle.quality_report),
        ("provenance.json", source_bundle.provenance),
    ):
        source = reference.verify(loaded.source_run_root)
        destination = artifacts / name
        shutil.copyfile(source, destination)
        copied[name] = destination
    def copy_optional(
        reference: ArtifactRef | None,
        *,
        name: str,
        artifact_id: str,
        role: str,
        file_format: str,
    ) -> ArtifactRef | None:
        if reference is None:
            return None
        destination = artifacts / name
        shutil.copyfile(reference.verify(loaded.source_run_root), destination)
        return _artifact(
            run_root=prepared.workspace.run_root,
            path=destination,
            artifact_id=artifact_id,
            role=role,
            file_format=file_format,
            attempt_id=attempt_id,
        )

    source_annotations_ref = copy_optional(
        source_bundle.source_annotations,
        name="source-annotations.json",
        artifact_id="source-annotations",
        role="source-annotations",
        file_format="json",
    )
    reference_sequence_ref = copy_optional(
        source_bundle.reference_sequence,
        name="reference-sequence.fasta",
        artifact_id="reference-sequence",
        role="reference-sequence",
        file_format="fasta",
    )
    residue_mapping_tsv_ref = copy_optional(
        source_bundle.residue_mapping_tsv,
        name="residue-map.tsv",
        artifact_id="residue-map-tsv",
        role="residue-mapping-projection",
        file_format="tsv",
    )
    identity_report_ref = copy_optional(
        source_bundle.identity_report,
        name="identity-report.json",
        artifact_id="identity-report",
        role="identity-evidence",
        file_format="json",
    )
    scope_report_ref = copy_optional(
        source_bundle.scope_report,
        name="scope-report.json",
        artifact_id="scope-report",
        role="scope-evidence",
        file_format="json",
    )
    structure_candidates_ref = copy_optional(
        source_bundle.structure_candidates,
        name="structure-candidates.json",
        artifact_id="structure-candidates",
        role="structure-candidate-report",
        file_format="json",
    )
    structure_candidates_tsv_ref = copy_optional(
        source_bundle.structure_candidates_tsv,
        name="structure-candidates.tsv",
        artifact_id="structure-candidates-tsv",
        role="structure-candidate-projection",
        file_format="tsv",
    )
    source_context_ref = copy_optional(
        source_bundle.source_context,
        name="source-context.cif",
        artifact_id="source-context",
        role="source-structure-context",
        file_format="mmcif",
    )
    design_context_ref = copy_optional(
        source_bundle.design_context,
        name="design-context.cif",
        artifact_id="design-context",
        role="selected-design-context",
        file_format="mmcif",
    )
    prediction_confidence_ref = copy_optional(
        source_bundle.prediction_confidence,
        name="prediction-confidence.json",
        artifact_id="prediction-confidence",
        role="backend-confidence",
        file_format="json",
    )
    target_pdb_ref = copy_optional(
        source_bundle.target_pdb,
        name="target.pdb",
        artifact_id="target-pdb",
        role="compatibility-target",
        file_format="pdb",
    )
    retrieval_manifest_ref: ArtifactRef | None = None
    retrieval_response_refs: list[ArtifactRef] = []
    if source_bundle.retrieval_manifest is not None:
        source_manifest = source_bundle.retrieval_manifest.verify(
            loaded.source_run_root
        )
        try:
            retrieval_payload = json.loads(
                source_manifest.read_text(encoding="utf-8")
            )
        except (OSError, json.JSONDecodeError) as error:
            raise TargetInputError(
                "Target Bundle retrieval-manifest 不是合法 JSON"
            ) from error
        if not isinstance(retrieval_payload, dict):
            raise TargetInputError("Target Bundle retrieval-manifest 顶层必须是 mapping")
        requests = retrieval_payload.get("requests", [])
        if not isinstance(requests, list):
            raise TargetInputError("Target Bundle retrieval requests 必须是 list")
        rewritten_requests = []
        for index, request in enumerate(requests, start=1):
            if not isinstance(request, dict):
                raise TargetInputError("Target Bundle retrieval request 必须是 mapping")
            rewritten = dict(request)
            relative = request.get("run_artifact_path")
            if isinstance(relative, str):
                source_response = (
                    loaded.source_run_root / relative
                ).resolve()
                if not source_response.is_relative_to(
                    loaded.source_run_root.resolve()
                ) or not source_response.is_file():
                    raise TargetInputError(
                        "Target Bundle retrieval response 越界或不存在"
                    )
                expected_sha = request.get("response_sha256")
                if (
                    isinstance(expected_sha, str)
                    and sha256_file(source_response) != expected_sha
                ):
                    raise TargetInputError(
                        "Target Bundle retrieval response SHA-256 不匹配"
                    )
                destination = (
                    artifacts
                    / "retrieval"
                    / f"{index:04d}-{source_response.name}"
                )
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source_response, destination)
                rewritten["run_artifact_path"] = destination.relative_to(
                    prepared.workspace.run_root
                ).as_posix()
                retrieval_response_refs.append(
                    _artifact(
                        run_root=prepared.workspace.run_root,
                        path=destination,
                        artifact_id=f"retrieval-response-{index:04d}",
                        role="remote-response-snapshot",
                        file_format=(
                            destination.suffix.lower().lstrip(".") or "binary"
                        ),
                        attempt_id=attempt_id,
                    )
                )
            rewritten_requests.append(rewritten)
        retrieval_payload["requests"] = rewritten_requests
        retrieval_path = artifacts / "retrieval-manifest.json"
        retrieval_path.write_text(
            json.dumps(
                retrieval_payload,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        retrieval_manifest_ref = _artifact(
            run_root=prepared.workspace.run_root,
            path=retrieval_path,
            artifact_id="retrieval-manifest",
            role="remote-retrieval-evidence",
            file_format="json",
            attempt_id=attempt_id,
        )

    def ref(name: str, artifact_id: str, role: str, file_format: str) -> ArtifactRef:
        return _artifact(
            run_root=prepared.workspace.run_root,
            path=copied[name],
            artifact_id=artifact_id,
            role=role,
            file_format=file_format,
            attempt_id=attempt_id,
        )

    bundle = TargetBundle(
        schema_version=(
            "0.5"
            if source_bundle.schema_version == "0.5"
            else "0.4"
        ),
        target_id=loaded.config.target.target_id,
        origin=source_bundle.origin,
        sequence_length=source_bundle.sequence_length,
        sequence_sha256=source_bundle.sequence_sha256,
        producer_attempt=attempt_id,
        target_structure=ref(
            "target.cif", "target-structure", "canonical-target", "mmcif"
        ),
        sequence=ref(
            "sequence.fasta", "target-sequence", "canonical-sequence", "fasta"
        ),
        residue_mapping=ref(
            "residue-mapping.json", "residue-mapping", "residue-mapping", "json"
        ),
        quality_report=ref(
            "structure-quality.json",
            "structure-quality",
            "structure-quality",
            "json",
        ),
        provenance=ref(
            "provenance.json", "target-provenance", "provenance", "json"
        ),
        source_annotations=source_annotations_ref,
        coordinate_ensemble=(
            source_bundle.coordinate_ensemble
            or CoordinateEnsemble(
                model_count=1,
                model_ids=("1",),
                representative_model_id="1",
            )
        ),
        reference_sequence=reference_sequence_ref,
        residue_mapping_tsv=residue_mapping_tsv_ref,
        identity_report=identity_report_ref,
        scope_report=scope_report_ref,
        structure_candidates=structure_candidates_ref,
        structure_candidates_tsv=structure_candidates_tsv_ref,
        retrieval_manifest=retrieval_manifest_ref,
        source_context=source_context_ref,
        design_context=design_context_ref,
        prediction_confidence=prediction_confidence_ref,
        target_pdb=target_pdb_ref,
    )
    bundle_path = dump_model(bundle, artifacts / "target-bundle.json")
    bundle_ref = _artifact(
        run_root=prepared.workspace.run_root,
        path=bundle_path,
        artifact_id="target-bundle",
        role="target-bundle",
        file_format="json",
        attempt_id=attempt_id,
    )
    built = BuiltTargetBundle(
        bundle=bundle,
        bundle_path=bundle_path,
        bundle_artifact=bundle_ref,
    )
    now = datetime.now(UTC)
    attempt = Attempt(
        attempt_id=attempt_id,
        status=ExecutionStatus.SUCCEEDED,
        created_at=now,
        started_at=now,
        ended_at=_strictly_later(datetime.now(UTC), now),
        backend_name="target-bundle-import",
        backend_version="0.1",
        executor_name="in-process",
    )
    dump_model(attempt, attempt_root / "attempt-manifest.json")
    resolved = load_model(prepared.workspace.resolved_config, ResolvedRunConfig)
    optional_outputs = tuple(
        artifact
        for artifact in (
            source_annotations_ref,
            reference_sequence_ref,
            residue_mapping_tsv_ref,
            identity_report_ref,
            scope_report_ref,
            structure_candidates_ref,
            structure_candidates_tsv_ref,
            retrieval_manifest_ref,
            source_context_ref,
            design_context_ref,
            prediction_confidence_ref,
            target_pdb_ref,
        )
        if artifact is not None
    )
    outputs = (
        bundle.target_structure,
        bundle.sequence,
        bundle.residue_mapping,
        bundle.quality_report,
        bundle.provenance,
    ) + optional_outputs + tuple(retrieval_response_refs) + (
        bundle_ref,
    )
    stage = StageManifest(
        stage_id=StageId.TARGET_PREPARATION,
        contract_version="0.4",
        status=ExecutionStatus.SUCCEEDED,
        created_at=now,
        completed_at=attempt.ended_at,
        input_artifacts=(resolved.input_snapshot,),
        output_artifacts=outputs,
        attempts=(attempt,),
        selected_attempt_id=attempt_id,
    )
    stage_path = dump_model(
        stage,
        prepared.workspace.stage_root(StageId.TARGET_PREPARATION)
        / "stage-manifest.v0001.json",
    )
    run_manifest = _publish_run(
        prepared,
        stage_manifest=stage_path,
        ended_at=attempt.ended_at or now,
        attempt_id=attempt_id,
    )
    viewer = generate_stage01_target_viewer_nonblocking(prepared.workspace.run_root)
    return Stage01SourceOutcome(
        status="succeeded",
        run_root=prepared.workspace.run_root,
        run_manifest=run_manifest,
        built_bundle=built,
        viewer_status=str(viewer.status),
    )


def _publish_source_failure(
    prepared: PreparedRun,
    *,
    attempt_id: str,
    started_at: datetime,
    error: Exception,
) -> None:
    """远程/本地/Bundle 入口失败也发布完整终态 manifest 链。"""

    ended = _strictly_later(datetime.now(UTC), started_at)
    attempt_root = prepared.workspace.attempt_root(
        StageId.TARGET_PREPARATION,
        attempt_id,
    )
    logs = attempt_root / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    error_path = logs / "source-error.json"
    error_path.write_text(
        json.dumps(
            {
                "error_type": type(error).__name__,
                "message": str(error)[:4096] or type(error).__name__,
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    log_paths = [error_path]
    retrieval_root = attempt_root / "work" / "retrieval"
    if retrieval_root.is_dir():
        log_paths.extend(
            path
            for path in sorted(retrieval_root.rglob("*"))
            if path.is_file()
        )
    log_refs = tuple(
        _artifact(
            run_root=prepared.workspace.run_root,
            path=path,
            artifact_id=(
                "stage01-source-error"
                if index == 1
                else f"stage01-retrieval-evidence-{index - 1:04d}"
            ),
            role="backend-log",
            file_format=path.suffix.lower().lstrip(".") or "binary",
            attempt_id=attempt_id,
        )
        for index, path in enumerate(log_paths, start=1)
    )
    error_code = (
        "stage01-backend-failed"
        if isinstance(error, BackendContractError)
        else "stage01-target-input-failed"
        if isinstance(error, TargetInputError)
        else "stage01-source-failed"
    )
    attempt = Attempt(
        attempt_id=attempt_id,
        status=ExecutionStatus.FAILED,
        created_at=started_at,
        started_at=started_at,
        ended_at=ended,
        backend_name="stage01-source",
        backend_version="0.4",
        executor_name="in-process",
        log_artifacts=log_refs,
        error=ErrorInfo(
            code=error_code,
            message=str(error)[:4096] or type(error).__name__,
            retryable=False,
        ),
    )
    dump_model(attempt, attempt_root / "attempt-manifest.json")
    resolved = load_model(prepared.workspace.resolved_config, ResolvedRunConfig)
    existing_stage_revisions = [
        int(path.stem.removeprefix("stage-manifest.v"))
        for path in prepared.workspace.stage_root(
            StageId.TARGET_PREPARATION
        ).glob("stage-manifest.v*.json")
        if path.stem.removeprefix("stage-manifest.v").isdigit()
    ]
    stage_revision = max(existing_stage_revisions, default=0) + 1
    stage = StageManifest(
        stage_id=StageId.TARGET_PREPARATION,
        contract_version="0.4",
        status=ExecutionStatus.FAILED,
        created_at=started_at,
        completed_at=ended,
        input_artifacts=(resolved.input_snapshot,),
        output_artifacts=(),
        attempts=(attempt,),
        selected_attempt_id=None,
    )
    stage_path = dump_model(
        stage,
        prepared.workspace.stage_root(StageId.TARGET_PREPARATION)
        / f"stage-manifest.v{stage_revision:04d}.json",
    )
    current = _current_manifest(prepared)
    updated = _strictly_later(ended, current.updated_at)
    stage_ref = _artifact(
        run_root=prepared.workspace.run_root,
        path=stage_path,
        artifact_id="stage-01-manifest",
        role="stage-manifest",
        file_format="json",
        attempt_id=attempt_id,
    )
    next_manifest = current.next_revision(
        updated_at=updated,
        status=ExecutionStatus.FAILED,
        completed_at=updated,
        stage_manifest_refs=(stage_ref,),
        clear_workflow_state=True,
    )
    manifest_path = (
        prepared.workspace.run_root
        / "manifests"
        / f"run-manifest.v{next_manifest.revision:04d}.json"
    )
    dump_model(next_manifest, manifest_path)
    _atomic_pointer(
        f"{manifest_path.name}\n",
        prepared.workspace.latest_manifest_pointer,
    )
    upsert_run_index_entries(
        prepared.workspace.runs_root,
        (
            RunIndexEntry(
                category="project-run",
                path=prepared.workspace.run_root.relative_to(
                    prepared.workspace.runs_root
                ).as_posix(),
                layout_version="1",
                status="failed",
                project_id=prepared.workspace.project_id,
                run_id=prepared.workspace.run_id,
                notes=(
                    f"Stage 01 source failed; attempt={attempt_id}; "
                    f"error={error_code}.",
                ),
            ),
        ),
        generated_at=updated,
    )


def _execute_stage01_source(
    prepared: PreparedRun,
    *,
    attempt_id: str = ATTEMPT_ID,
    approved_option: DecisionOption | None = None,
) -> Stage01SourceOutcome:
    """兼容门面：实际分派由六入口 handler package 完成。"""

    from .stage01_handlers import dispatch_stage01_source

    return dispatch_stage01_source(
        prepared,
        attempt_id=attempt_id,
        approved_option=approved_option,
    )


def execute_stage01_source(
    prepared: PreparedRun,
    *,
    attempt_id: str = ATTEMPT_ID,
    approved_option: DecisionOption | None = None,
) -> Stage01SourceOutcome:
    """执行统一入口；失败时先发布终态证据，再重新抛出原始错误。"""

    started = datetime.now(UTC)
    try:
        return _execute_stage01_source(
            prepared,
            attempt_id=attempt_id,
            approved_option=approved_option,
        )
    except Exception as error:
        try:
            _publish_source_failure(
                prepared,
                attempt_id=attempt_id,
                started_at=started,
                error=error,
            )
        except Exception as publication_error:
            error.add_note(
                "Stage 01 failure manifest publication also failed: "
                f"{publication_error}"
            )
        raise
