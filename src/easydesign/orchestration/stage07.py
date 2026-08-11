"""Stage 07 deterministic deep filtering, multi-seed validation, and packaging."""

from __future__ import annotations

import hashlib
import json
import os
import threading
from collections.abc import Callable
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from importlib import resources
from pathlib import Path
from typing import Any, Literal, TypeVar

import yaml  # type: ignore[import-untyped]
from pydantic import BaseModel, ConfigDict

from easydesign.backends.executors import execute_on_devices
from easydesign.backends.structure_prediction import (
    ComplexStructurePredictionRequest,
    MsaMode,
    OpenFold3Af3JaxAdapter,
    ProteinPredictionChain,
    ProtenixV2Adapter,
)
from easydesign.backends.tnp import TnpAdapter, TnpBatchRequest
from easydesign.core import (
    ArtifactRef,
    Attempt,
    ErrorInfo,
    ExecutionStatus,
    ManifestStateError,
    ProgressSnapshot,
    RunManifest,
    StageId,
    StageManifest,
    TaskAttemptRecord,
    TaskEvent,
    TaskRecord,
    TaskStatus,
    dump_model,
    load_model,
    sha256_file,
)
from easydesign.filtering import (
    FINAL_PROFILE_SOURCE_SHA256,
    FINAL_PROFILE_SOURCE_SHA256_V1_6,
    FullPredictionEvidence,
    InterfaceMetricValues,
    build_multi_seed_consensus,
    compute_full_target_structure_metrics,
    compute_interface_metrics,
    contacted_hotspot_residue_ids,
    convert_deep_filter_records,
    evaluate_pilot_candidates,
    evaluate_sequence_prefilter,
    extract_complex_confidence,
    final_prediction_decisions,
    final_prediction_metrics,
    lazy_greedy_select,
    parse_protein_chain,
    score_full_prediction_evidence,
    unpaired_designed_cysteine_residue_ids,
)
from easydesign.filtering.structure_metrics import ParsedChain
from easydesign.safe_writes import read_last_text_line
from easydesign.stages.s03_boltzgen_configuration import StrategyBundle
from easydesign.stages.s04_pilot_generation import CandidateIndex, CandidateRecord
from easydesign.stages.s05_pilot_filtering import (
    ScientificStop,
    ScientificStopCode,
    Stage05Bundle,
    Stage05BundleV0_2,
)
from easydesign.stages.s06_scale_generation_and_refolding import (
    MultiStrategyCandidateIndex,
    ScaleBundle,
    ScaleBundleV0_2,
    ScalePlan,
    ScalePlanV0_2,
    ScaleStrategyAuthorization,
)
from easydesign.stages.s07_final_filtering_and_selection import (
    FinalCandidate,
    FinalCandidatePackage,
    FinalCandidatePackageV0_2,
    FinalFilterReport,
    FinalPredictionRecord,
    FinalSelectionRecord,
    MultiSeedConsensusRecord,
    OperationalFailure,
    RawFinalPrediction,
    ScaleCandidateLineage,
    Seed101Normalization,
    SeedPairConsistency,
    Stage07Bundle,
    Stage07BundleV0_2,
    Stage07PredictionState,
    Stage07ScaleInput,
    TnpReport,
    normalize_scale_bundle_for_stage07,
    summarize_selected_sources,
    validate_scale_candidate_lineage,
)

from .complex_prediction_support import (
    prediction_release_identity,
    prepare_query_only_a3m,
    read_fasta_sequence,
    run_checked_backend_invocation,
)
from .config import ResolvedProtenixMsaProviderConfig
from .stage04 import _atomic_text
from .task_tracking import (
    TaskEventJournal,
    atomic_dump_runtime_model,
    load_latest_runtime_model,
)
from .workspace import (
    ResolvedRunConfig,
    RunIndexEntry,
    load_resolved_run_config,
    upsert_run_index_entries,
)

ModelT = TypeVar("ModelT", bound=BaseModel)
ComplexAdapterBuilder = Callable[
    [ResolvedProtenixMsaProviderConfig, int],
    ProtenixV2Adapter | OpenFold3Af3JaxAdapter,
]


class Stage07Execution(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: str
    run_root: Path
    run_manifest: Path
    stage_manifest: Path
    stage07_bundle: Path
    primary_count: int
    backup_count: int


class _LocalMetricCache(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    candidate_id: str
    candidate_structure_sha256: str
    target_structure_sha256: str
    design_mask_sha256: str
    hotspot_residue_ids: tuple[int, ...]
    unpaired_new_cysteines: tuple[int, ...]
    interface: InterfaceMetricValues


class _TnpAttemptReceipt(BaseModel):
    """Immutable proof that one TNP attempt was fully collected."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["0.1"] = "0.1"
    status: Literal["succeeded"] = "succeeded"
    candidate_ids: tuple[str, ...]
    input_fasta_sha256: str
    result_sha256: str
    started_at: datetime
    ended_at: datetime
    executable_identity: dict[str, str]


@dataclass(frozen=True, slots=True)
class _Upstream:
    run: RunManifest
    run_path: Path
    stage01: StageManifest
    stage03: StageManifest
    stage05: StageManifest
    stage06: StageManifest
    target_structure_ref: ArtifactRef
    target_sequence_ref: ArtifactRef
    target_msa_ref: ArtifactRef
    strategy_bundle_ref: ArtifactRef
    strategy_bundle: StrategyBundle
    stage05_bundle_ref: ArtifactRef
    stage05_bundle: Stage05Bundle | Stage05BundleV0_2
    scale_bundle_ref: ArtifactRef
    scale_bundle: ScaleBundle | ScaleBundleV0_2
    scale_candidate_index_ref: ArtifactRef
    scale_candidate_index: CandidateIndex | MultiStrategyCandidateIndex
    scale_input: Stage07ScaleInput
    hotspot_residue_ids_by_strategy: dict[str, tuple[int, ...]]


@dataclass(frozen=True, slots=True)
class _PredictionBatch:
    """One prediction phase with every sample and one representative per seed."""

    representatives: tuple[RawFinalPrediction, ...]
    all_samples: tuple[RawFinalPrediction, ...]


def _latest_manifest(root: Path) -> tuple[RunManifest, Path]:
    pointer = root / "manifests" / "LATEST"
    try:
        name = read_last_text_line(pointer)
    except OSError as error:
        raise ManifestStateError(f"无法读取 RunManifest LATEST: {pointer}") from error
    path = root / "manifests" / name
    return load_model(path, RunManifest), path


def _stage(root: Path, run: RunManifest, stage_id: StageId) -> StageManifest:
    reference = next(
        (item for item in run.stage_manifest_refs if item.producer_stage == str(stage_id)),
        None,
    )
    if reference is None:
        raise ManifestStateError(f"Stage 07 缺少上游 {stage_id}")
    manifest = load_model(reference.verify(root), StageManifest)
    if manifest.status is not ExecutionStatus.SUCCEEDED:
        raise ManifestStateError(f"Stage 07 上游 {stage_id} 未成功")
    return manifest


def _load_upstream(root: Path) -> _Upstream:
    run, run_path = _latest_manifest(root)
    stage01 = _stage(root, run, StageId.TARGET_PREPARATION)
    stage03 = _stage(root, run, StageId.BOLTZGEN_CONFIGURATION)
    stage05 = _stage(root, run, StageId.PILOT_FILTERING)
    stage06 = _stage(root, run, StageId.SCALE_GENERATION_AND_REFOLDING)
    target_structure = stage01.require_output("target-structure")
    target_sequence = stage01.require_output("target-sequence")
    target_msa = stage05.require_output("stage05-target-msa")
    strategy_ref = stage03.require_output("strategy-bundle")
    strategy = load_model(strategy_ref.verify(root), StrategyBundle)
    stage05_ref = stage05.require_output("stage05-bundle")
    stage05_path = stage05_ref.verify(root)
    stage05_schema = json.loads(stage05_path.read_text(encoding="utf-8")).get(
        "schema_version"
    )
    stage05_bundle: Stage05Bundle | Stage05BundleV0_2
    if stage05_schema == "0.2":
        stage05_bundle = load_model(stage05_path, Stage05BundleV0_2)
    else:
        stage05_bundle = load_model(stage05_path, Stage05Bundle)
    scale_ref = stage06.require_output("scale-bundle")
    scale_path = scale_ref.verify(root)
    scale_schema = json.loads(scale_path.read_text(encoding="utf-8")).get(
        "schema_version"
    )
    scale: ScaleBundle | ScaleBundleV0_2
    candidate_index: CandidateIndex | MultiStrategyCandidateIndex
    if scale_schema == "0.2":
        scale = load_model(scale_path, ScaleBundleV0_2)
    else:
        scale = load_model(scale_path, ScaleBundle)
    index_ref = stage06.require_output("scale-candidate-index")
    if scale_schema == "0.2":
        candidate_index = load_model(
            index_ref.verify(root),
            MultiStrategyCandidateIndex,
        )
    else:
        candidate_index = load_model(index_ref.verify(root), CandidateIndex)
    if scale.stage05_bundle != stage05_ref:
        raise ManifestStateError("ScaleBundle 与 Stage05Bundle identity 不一致")
    if scale.candidate_index != index_ref:
        raise ManifestStateError("ScaleBundle candidate index 与 StageManifest 不一致")
    scale_input = normalize_scale_bundle_for_stage07(
        scale_bundle=scale,
        scale_bundle_sha256=scale_ref.sha256,
        candidate_index_sha256=index_ref.sha256,
    )
    authorized_strategy_ids = tuple(
        item.strategy_id for item in scale_input.strategy_allocations
    )
    if isinstance(scale, ScaleBundleV0_2):
        if not isinstance(stage05_bundle, Stage05BundleV0_2):
            raise ManifestStateError("ScaleBundle 0.2 必须来自 Stage05Bundle 0.2")
        if stage05_bundle.status != "strategies-promoted":
            raise ManifestStateError("Stage 05 没有晋级策略；Stage 07 不允许继续")
        if stage05_bundle.promoted_strategy_ids != authorized_strategy_ids:
            raise ManifestStateError("Stage 05 晋级策略与 Stage 06 allocation 不一致")
    else:
        if not isinstance(stage05_bundle, Stage05Bundle):
            raise ManifestStateError("ScaleBundle 0.1 必须来自 Stage05Bundle 0.1")
        if stage05_bundle.status == "stopped-no-tier-a":
            raise ManifestStateError("Stage 05 没有 Tier A；Stage 07 不允许继续")
        if stage05_bundle.status == "winner-selected":
            if stage05_bundle.winner_strategy_id != scale.strategy_id:
                raise ManifestStateError("ScaleBundle 与 Stage 05 winner 不一致")
        elif stage05_bundle.status == "stopped-no-scale-winner":
            authority = load_model(
                scale.strategy_authorization.verify(root),
                ScaleStrategyAuthorization,
            )
            if (
                authority.mode != "manual-stage05-stop-override"
                or authority.strategy_id != scale.strategy_id
            ):
                raise ManifestStateError(
                    "旧 scientific-stop 只有具备显式人工授权时才能进入 Stage 07"
                )
        else:
            raise ManifestStateError("Stage 05 status 不支持 Stage 07")
    strategy_by_id = {
        item.strategy_id: item for item in strategy.strategies
    }
    if any(
        strategy_id not in strategy_by_id
        for strategy_id in authorized_strategy_ids
    ):
        raise ManifestStateError("Stage 06 strategy 不在 StrategyBundle")
    lineage: list[ScaleCandidateLineage] = []
    for candidate in candidate_index.candidates:
        candidate.original_structure.verify(root)
        candidate.refolded_structure.verify(root)
        if candidate.design_mask_source is None:
            raise ManifestStateError(
                f"candidate={candidate.candidate_id} 缺少 design-mask artifact"
            )
        candidate.design_mask_source.verify(root)
        sequence = candidate.metrics.get("designed_chain_sequence")
        if not isinstance(sequence, str) or not sequence.strip():
            sequence = candidate.metrics.get("designed_sequence")
        if not isinstance(sequence, str) or not sequence.strip():
            raise ManifestStateError(
                f"candidate={candidate.candidate_id} 缺少可审计序列"
            )
        lineage.append(
            ScaleCandidateLineage(
                candidate_id=candidate.candidate_id,
                strategy_id=candidate.strategy_id,
                strategy_ordinal=candidate.ordinal_within_strategy,
                sequence_sha256=hashlib.sha256(
                    sequence.strip().upper().encode("ascii")
                ).hexdigest(),
            )
        )
    validate_scale_candidate_lineage(
        scale_input=scale_input,
        candidates=tuple(lineage),
    )
    for reference in (
        target_structure,
        target_sequence,
        target_msa,
        strategy_ref,
        stage05_ref,
        scale_ref,
        index_ref,
    ):
        reference.verify(root)
    return _Upstream(
        run=run,
        run_path=run_path,
        stage01=stage01,
        stage03=stage03,
        stage05=stage05,
        stage06=stage06,
        target_structure_ref=target_structure,
        target_sequence_ref=target_sequence,
        target_msa_ref=target_msa,
        strategy_bundle_ref=strategy_ref,
        strategy_bundle=strategy,
        stage05_bundle_ref=stage05_ref,
        stage05_bundle=stage05_bundle,
        scale_bundle_ref=scale_ref,
        scale_bundle=scale,
        scale_candidate_index_ref=index_ref,
        scale_candidate_index=candidate_index,
        scale_input=scale_input,
        hotspot_residue_ids_by_strategy={
            strategy_id: strategy_by_id[strategy_id].binding_label_seq_ids
            for strategy_id in authorized_strategy_ids
        },
    )


def _artifact(
    root: Path,
    path: Path,
    *,
    artifact_id: str,
    role: str,
    file_format: str,
) -> ArtifactRef:
    return ArtifactRef.from_file(
        run_root=root,
        relative_path=path.relative_to(root).as_posix(),
        artifact_id=artifact_id,
        role=role,
        file_format=file_format,
        producer_stage=str(StageId.FINAL_FILTERING_AND_SELECTION),
        producer_attempt="attempt-0001",
    )


def _dump_or_verify(
    model: ModelT,
    path: Path,
    model_type: type[ModelT],
    *,
    ignore: frozenset[str] = frozenset(),
) -> ModelT:
    if not path.exists():
        dump_model(model, path)
        return model
    existing = load_model(path, model_type)
    excluded_fields = set(ignore)
    if existing.model_dump(exclude=excluded_fields) != model.model_dump(exclude=excluded_fields):
        raise ManifestStateError(f"Stage 07 已有 immutable artifact 不一致: {path}")
    return existing


def _profile_bytes(profile_id: str) -> bytes:
    content = (
        resources.files("easydesign.resources")
        .joinpath(f"filter_profiles/{profile_id}.yaml")
        .read_bytes()
    )
    payload: Any = yaml.safe_load(content)
    try:
        source_hash = payload["source_document"]["sha256"]
    except (KeyError, TypeError) as error:
        raise ManifestStateError("Stage 07 profile 缺少 source document identity") from error
    expected = (
        FINAL_PROFILE_SOURCE_SHA256_V1_6
        if profile_id == "nanobody-final-v1.6"
        else FINAL_PROFILE_SOURCE_SHA256
    )
    if source_hash != expected:
        raise ManifestStateError("Stage 07 profile source SHA-256 不一致")
    return content


def _compute_local_metrics(
    *,
    candidate: CandidateRecord,
    structure_path: Path,
    reference_target: ParsedChain,
    hotspot_ids: tuple[int, ...],
) -> tuple[tuple[int, ...], InterfaceMetricValues]:
    if candidate.design_mask_source is None:
        raise ManifestStateError("Stage 07 candidate 缺少 design-mask source")
    unpaired = unpaired_designed_cysteine_residue_ids(
        candidate_structure=structure_path,
        designed_residue_ids=candidate.designed_binder_residue_ids,
    )
    interface = compute_interface_metrics(
        candidate_structure=structure_path,
        reference_target=reference_target,
        hotspot_residue_ids=hotspot_ids,
        cdr_residue_ids=candidate.designed_binder_residue_ids,
    )
    return unpaired, interface


def _batch_local_metrics(
    *,
    root: Path,
    upstream: _Upstream,
    runtime: Path,
    created_at: datetime,
) -> tuple[dict[str, tuple[int, ...]], dict[str, InterfaceMetricValues]]:
    cache_root = runtime / "local-metrics"
    cache_root.mkdir(parents=True, exist_ok=True)
    reference = parse_protein_chain(
        upstream.target_structure_ref.verify(root),
        "A",
    )
    candidate_by_id = {
        item.candidate_id: item for item in upstream.scale_candidate_index.candidates
    }
    unpaired: dict[str, tuple[int, ...]] = {}
    metrics: dict[str, InterfaceMetricValues] = {}
    missing: list[CandidateRecord] = []
    for candidate in upstream.scale_candidate_index.candidates:
        assert candidate.design_mask_source is not None
        cache_path = cache_root / f"{candidate.candidate_id}.json"
        if not cache_path.exists():
            missing.append(candidate)
            continue
        cached = load_model(cache_path, _LocalMetricCache)
        hotspot_residue_ids = upstream.hotspot_residue_ids_by_strategy[
            candidate.strategy_id
        ]
        expected = {
            "candidate_id": candidate.candidate_id,
            "candidate_structure_sha256": candidate.refolded_structure.sha256,
            "target_structure_sha256": upstream.target_structure_ref.sha256,
            "design_mask_sha256": candidate.design_mask_source.sha256,
            "hotspot_residue_ids": hotspot_residue_ids,
        }
        if cached.model_dump(include=set(expected)) != expected:
            raise ManifestStateError(
                f"candidate={candidate.candidate_id} Stage 07 metric cache identity 不一致"
            )
        unpaired[candidate.candidate_id] = cached.unpaired_new_cysteines
        metrics[candidate.candidate_id] = cached.interface

    progress_path = runtime / "progress.json"

    def persist(failed: int = 0) -> None:
        updated = datetime.now(UTC)
        completed = len(metrics)
        total = len(candidate_by_id)
        elapsed = max((updated - created_at).total_seconds(), 0.0)
        throughput = completed / elapsed * 3600 if completed and elapsed else None
        remaining = total - completed - failed
        running = min(max(os.cpu_count() or 1, 1), 8, remaining)
        atomic_dump_runtime_model(
            ProgressSnapshot(
                stage_id=str(StageId.FINAL_FILTERING_AND_SELECTION),
                phase="local-deep-metrics",
                updated_at=updated,
                status="running" if remaining else "phase-succeeded",
                total_tasks=total,
                pending_tasks=max(remaining - running, 0),
                waiting_tasks=0,
                running_tasks=running,
                succeeded_tasks=completed,
                failed_tasks=failed,
                planned_candidates=total,
                collected_candidates=completed,
                elapsed_seconds=elapsed,
                throughput_candidates_per_hour=throughput,
                estimated_remaining_seconds=(
                    remaining / throughput * 3600
                    if throughput and remaining
                    else (0.0 if remaining == 0 else None)
                ),
            ),
            progress_path,
        )

    persist()
    if missing:
        workers = min(max(os.cpu_count() or 1, 1), 8)
        with ProcessPoolExecutor(max_workers=workers) as executor:
            future_to_candidate = {
                executor.submit(
                    _compute_local_metrics,
                    candidate=candidate,
                    structure_path=candidate.refolded_structure.verify(root),
                    reference_target=reference,
                    hotspot_ids=upstream.hotspot_residue_ids_by_strategy[
                        candidate.strategy_id
                    ],
                ): candidate
                for candidate in missing
            }
            for future in as_completed(future_to_candidate):
                candidate = future_to_candidate[future]
                try:
                    cysteines, values = future.result()
                except Exception:
                    persist(failed=1)
                    raise
                assert candidate.design_mask_source is not None
                record = _LocalMetricCache(
                    candidate_id=candidate.candidate_id,
                    candidate_structure_sha256=candidate.refolded_structure.sha256,
                    target_structure_sha256=upstream.target_structure_ref.sha256,
                    design_mask_sha256=candidate.design_mask_source.sha256,
                    hotspot_residue_ids=upstream.hotspot_residue_ids_by_strategy[
                        candidate.strategy_id
                    ],
                    unpaired_new_cysteines=cysteines,
                    interface=values,
                )
                dump_model(record, cache_root / f"{candidate.candidate_id}.json")
                unpaired[candidate.candidate_id] = cysteines
                metrics[candidate.candidate_id] = values
                persist()
    return unpaired, metrics


def _raw_evidence(raw: RawFinalPrediction) -> FullPredictionEvidence:
    return FullPredictionEvidence(
        candidate_id=raw.candidate_id,
        seed=raw.seed,
        pairwise_iptm=raw.pairwise_iptm,
        minimum_interface_pae_angstrom=raw.minimum_interface_pae_angstrom,
        binder_ptm=raw.binder_ptm,
        binder_pose_rmsd_angstrom=raw.binder_pose_rmsd_angstrom,
        target_ca_rmsd_angstrom=raw.target_ca_rmsd_angstrom,
        contacted_hotspot_residue_ids=raw.contacted_hotspot_residue_ids,
        interface=InterfaceMetricValues(
            target_ca_rmsd_angstrom=raw.target_ca_rmsd_angstrom,
            hotspot_coverage=raw.hotspot_coverage,
            contacted_hotspot_count=len(raw.contacted_hotspot_residue_ids),
            hotspot_count=raw.hotspot_count,
            binder_contact_coverage=raw.binder_contact_coverage,
            cdr_dominance=raw.cdr_dominance,
            cdr_utilization=raw.cdr_utilization,
            residue_pair_contact_count=raw.residue_pair_contact_count,
            atom_contact_count=raw.atom_contact_count,
            severe_clash_count=raw.severe_clash_count,
            moderate_clash_count=raw.moderate_clash_count,
            hydrogen_bond_count=raw.hydrogen_bond_count,
            salt_bridge_count=raw.salt_bridge_count,
            polar_contact_fraction=raw.polar_contact_fraction,
            interface_bsa_angstrom2=raw.interface_bsa_angstrom2,
            interface_bsa_missing_reason=None,
        ),
        confidence_metric_definition_version=(
            raw.confidence_metric_definition_version
        ),
    )


def _prediction_key(candidate_id: str, seed: int) -> str:
    raw = f"{candidate_id}-seed-{seed}"
    if len(raw) <= 128:
        return raw
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
    return f"{candidate_id[:101]}-{digest}-s{seed}"


def _qualified_artifact_id(base: str, suffix: str) -> str:
    raw = f"{base}-{suffix}"
    if len(raw) <= 128:
        return raw
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
    return f"{base[:110]}-{digest}"


def _execute_predictions(
    *,
    root: Path,
    upstream: _Upstream,
    candidates: tuple[CandidateRecord, ...],
    seeds: tuple[Literal[101, 202, 303, 404, 505], ...],
    sample_count: int,
    phase_id: str,
    work: Path,
    runtime: Path,
    adapter_builder: ComplexAdapterBuilder,
    provider: ResolvedProtenixMsaProviderConfig,
    devices: tuple[int, ...],
    maximum_attempts: int,
    created_at: datetime,
) -> _PredictionBatch:
    requested_keys = tuple(
        sorted(
            _prediction_key(candidate.candidate_id, seed)
            for candidate in candidates
            for seed in seeds
        )
    )
    target_sequence = read_fasta_sequence(upstream.target_sequence_ref.verify(root))
    target_msa = upstream.target_msa_ref.verify(root)
    target_query = prepare_query_only_a3m(
        target_sequence,
        work / "structure-prediction" / phase_id / "target-query-only.a3m",
    )
    reference_target = parse_protein_chain(
        upstream.target_structure_ref.verify(root),
        "A",
    )
    phase_runtime = runtime / "predictions" / phase_id
    state_path = phase_runtime / "prediction-state.json"
    progress_path = phase_runtime / "progress.json"
    journal = TaskEventJournal(phase_runtime / "task-events.jsonl")
    prediction_by_key: dict[str, RawFinalPrediction]
    samples_by_key: dict[str, tuple[RawFinalPrediction, ...]]
    if state_path.exists():
        state = load_model(state_path, Stage07PredictionState)
        if state.target_msa_sha256 != upstream.target_msa_ref.sha256:
            raise ManifestStateError("Stage 07 prediction state target MSA 不一致")
        tasks = {item.strategy_id: item for item in state.tasks}
        prediction_by_key = {
            _prediction_key(item.candidate_id, item.seed): item for item in state.predictions
        }
        sample_values = state.sample_predictions or state.predictions
        samples_by_key = {}
        for item in sample_values:
            key = _prediction_key(item.candidate_id, item.seed)
            samples_by_key[key] = (*samples_by_key.get(key, ()), item)
        for item in sample_values:
            item.predicted_structure.verify(root)
            item.summary_confidence.verify(root)
            item.full_confidence.verify(root)
    else:
        tasks = {}
        prediction_by_key = {}
        samples_by_key = {}
    for key in requested_keys:
        if key not in tasks:
            tasks[key] = TaskRecord(
                task_id=f"structure-prediction-{key}"[:128],
                strategy_id=key,
                requested_candidates=1,
            )
    planned_keys = tuple(sorted(tasks))
    lock = threading.RLock()
    recent_errors: list[str] = []

    def ordered_tasks() -> tuple[TaskRecord, ...]:
        return tuple(tasks[key] for key in planned_keys)

    def persist(status: str, phase: str) -> None:
        values = ordered_tasks()
        counts = {item: 0 for item in TaskStatus}
        per_device: dict[str, str | None] = {}
        for task in values:
            counts[task.status] += 1
            if task.status is TaskStatus.RUNNING:
                assert task.current_device is not None
                per_device[str(task.current_device)] = task.strategy_id
        updated = datetime.now(UTC)
        elapsed = max((updated - created_at).total_seconds(), 0.0)
        completed = len(prediction_by_key)
        throughput = completed / elapsed * 3600 if completed and elapsed else None
        remaining = len(values) - completed
        snapshot = ProgressSnapshot(
            stage_id=str(StageId.FINAL_FILTERING_AND_SELECTION),
            phase=phase,
            updated_at=updated,
            status=status,
            total_tasks=len(values),
            pending_tasks=counts[TaskStatus.PENDING],
            waiting_tasks=counts[TaskStatus.WAITING_RESOURCE],
            running_tasks=counts[TaskStatus.RUNNING],
            succeeded_tasks=counts[TaskStatus.SUCCEEDED],
            failed_tasks=counts[TaskStatus.FAILED],
            planned_candidates=len(values),
            collected_candidates=completed,
            per_device=per_device,
            elapsed_seconds=elapsed,
            throughput_candidates_per_hour=throughput,
            estimated_remaining_seconds=(
                remaining / throughput * 3600
                if throughput and remaining
                else (0.0 if remaining == 0 else None)
            ),
            recent_errors=tuple(recent_errors[-10:]),
        )
        atomic_dump_runtime_model(snapshot, progress_path)
        atomic_dump_runtime_model(
            Stage07PredictionState(
                created_at=created_at,
                updated_at=updated,
                target_msa_sha256=upstream.target_msa_ref.sha256,
                planned_prediction_keys=planned_keys,
                tasks=values,
                predictions=tuple(prediction_by_key[key] for key in sorted(prediction_by_key)),
                sample_predictions=tuple(
                    sample
                    for key in sorted(samples_by_key)
                    for sample in sorted(
                        samples_by_key[key], key=lambda item: item.sample_index
                    )
                ),
                progress=snapshot,
            ),
            state_path,
        )

    def event(
        event_type: str,
        task: TaskRecord,
        message: str,
        *,
        attempt_number: int | None = None,
        device: int | None = None,
        from_status: TaskStatus | None = None,
        to_status: TaskStatus | None = None,
        error: ErrorInfo | None = None,
    ) -> None:
        journal.append(
            TaskEvent(
                sequence=journal.next_sequence,
                occurred_at=datetime.now(UTC),
                event_type=event_type,
                task_id=task.task_id,
                strategy_id=task.strategy_id,
                task_attempt_number=attempt_number,
                device=device,
                from_status=from_status,
                to_status=to_status,
                message=message,
                error=error,
            )
        )

    for key, task in tuple(tasks.items()):
        if task.status is TaskStatus.RUNNING:
            running_attempt = task.attempts[-1]
            interruption = ErrorInfo(
                code="interrupted-before-resume",
                message="Previous Stage 07 process ended before backend terminal state.",
                retryable=True,
            )
            closed = running_attempt.model_copy(
                update={
                    "status": TaskStatus.FAILED,
                    "ended_at": datetime.now(UTC),
                    "return_code": 130,
                    "error": interruption,
                }
            )
            tasks[key] = task.model_copy(
                update={
                    "status": TaskStatus.PENDING,
                    "attempts": (*task.attempts[:-1], closed),
                    "current_device": None,
                }
            )
            event(
                "task-interrupted",
                tasks[key],
                "Closed interrupted Stage 07 structure-prediction attempt.",
                attempt_number=running_attempt.attempt_number,
                device=running_attempt.device,
                from_status=TaskStatus.RUNNING,
                to_status=TaskStatus.PENDING,
                error=interruption,
            )
        elif task.status is TaskStatus.FAILED and key not in prediction_by_key:
            tasks[key] = task.model_copy(update={"status": TaskStatus.PENDING})
    persist("running", phase_id)

    def predict(
        pair: tuple[CandidateRecord, Literal[101, 202, 303, 404, 505]],
        device: int,
    ) -> TaskRecord:
        candidate, seed = pair
        key = _prediction_key(candidate.candidate_id, seed)
        current = tasks[key]
        sequence_value = candidate.metrics.get("designed_chain_sequence")
        if not isinstance(sequence_value, str) or not sequence_value:
            raise ManifestStateError(f"candidate={candidate.candidate_id} 缺少 binder sequence")
        sequence = sequence_value.strip().upper()
        invocation_attempts = 0
        while current.status is not TaskStatus.SUCCEEDED and invocation_attempts < maximum_attempts:
            invocation_attempts += 1
            attempt_number = len(current.attempts) + 1
            task_root = (
                work
                / "structure-prediction"
                / phase_id
                / candidate.candidate_id
                / f"seed-{seed}"
                / f"attempt-{attempt_number:04d}"
            )
            binder_query = prepare_query_only_a3m(
                sequence,
                task_root / "binder-query-only.a3m",
            )
            request = ComplexStructurePredictionRequest(
                job_name=f"{candidate.candidate_id}-s{seed}"[:128],
                chains=(
                    ProteinPredictionChain(
                        chain_id="A",
                        role="target",
                        sequence=target_sequence,
                        paired_msa_path=target_query,
                        unpaired_msa_path=target_msa,
                    ),
                    ProteinPredictionChain(
                        chain_id="B",
                        role="binder",
                        sequence=sequence,
                        paired_msa_path=binder_query,
                        unpaired_msa_path=binder_query,
                    ),
                ),
                seeds=(seed,),
                sample_count=sample_count,
                msa_mode=MsaMode.PRECOMPUTED,
            )
            adapter = adapter_builder(provider, device)
            input_path = adapter.write_input(request, task_root / "input.json")
            output = task_root / "output"
            invocation = adapter.prediction_invocation(
                request,
                input_json=input_path,
                output_dir=output,
            )
            command_hash = hashlib.sha256(
                json.dumps(
                    invocation.argv,
                    ensure_ascii=True,
                    separators=(",", ":"),
                ).encode("utf-8")
            ).hexdigest()
            started = datetime.now(UTC)
            running_attempt = TaskAttemptRecord(
                attempt_number=attempt_number,
                status=TaskStatus.RUNNING,
                requested_candidates=1,
                device=device,
                command_sha256=command_hash,
                output_relative_path=output.relative_to(root).as_posix(),
                started_at=started,
            )
            with lock:
                current = current.model_copy(
                    update={
                        "status": TaskStatus.RUNNING,
                        "attempts": (*current.attempts, running_attempt),
                        "current_device": device,
                    }
                )
                tasks[key] = current
                event(
                    "task-started",
                    current,
                    f"Started structure-prediction seed {seed} with {sample_count} samples.",
                    attempt_number=attempt_number,
                    device=device,
                    from_status=TaskStatus.PENDING,
                    to_status=TaskStatus.RUNNING,
                )
                persist("running", phase_id)
            error: ErrorInfo | None = None
            seed_samples: tuple[RawFinalPrediction, ...] = ()
            representative: RawFinalPrediction | None = None
            return_code = 1
            try:
                completed = run_checked_backend_invocation(invocation)
                return_code = completed.returncode
                products = adapter.collect_products(request, output_dir=output)
                if len(products) != sample_count:
                    raise ManifestStateError(
                        f"Stage 07 expected {sample_count} samples, collected {len(products)}"
                    )
                collected_samples: list[RawFinalPrediction] = []
                for product in products:
                    if (
                        product.full_confidence_path is None
                        or product.full_confidence_sha256 is None
                    ):
                        raise ManifestStateError(
                            "Stage 07 structure backend 缺少 full confidence"
                        )
                    sample_suffix = f"sample-{product.sample_index}"
                    structure_ref = _artifact(
                        root,
                        product.structure_path,
                        artifact_id=_qualified_artifact_id(
                            key, f"{sample_suffix}-structure"
                        ),
                        role="stage07-structure-prediction",
                        file_format="mmcif",
                    )
                    summary_ref = _artifact(
                        root,
                        product.confidence_path,
                        artifact_id=_qualified_artifact_id(
                            key, f"{sample_suffix}-summary"
                        ),
                        role="structure-summary-confidence",
                        file_format="json",
                    )
                    full_ref = _artifact(
                        root,
                        product.full_confidence_path,
                        artifact_id=_qualified_artifact_id(
                            key, f"{sample_suffix}-confidence"
                        ),
                        role="structure-full-confidence",
                        file_format="json",
                    )
                    confidence = extract_complex_confidence(product)
                    structure = compute_full_target_structure_metrics(
                        designed_complex=candidate.refolded_structure.verify(root),
                        predicted_complex=product.structure_path,
                        reference_target=reference_target,
                    )
                    interface = compute_interface_metrics(
                        candidate_structure=product.structure_path,
                        reference_target=reference_target,
                        hotspot_residue_ids=upstream.hotspot_residue_ids_by_strategy[
                            candidate.strategy_id
                        ],
                        cdr_residue_ids=candidate.designed_binder_residue_ids,
                    )
                    if interface.interface_bsa_angstrom2 is None:
                        raise ManifestStateError(
                            "Stage 07 structure backend 无法计算标准 interface BSA: "
                            f"{interface.interface_bsa_missing_reason}"
                        )
                    contacts = contacted_hotspot_residue_ids(
                        candidate_structure=product.structure_path,
                        hotspot_residue_ids=upstream.hotspot_residue_ids_by_strategy[
                            candidate.strategy_id
                        ],
                    )
                    collected_samples.append(
                        RawFinalPrediction(
                            candidate_id=candidate.candidate_id,
                            seed=seed,
                            prediction_phase=phase_id,
                            sample_index=product.sample_index,
                            samples_per_seed=sample_count,
                            recycles=product.recycle_count,
                            ranking_score=product.ranking_score,
                            is_seed_representative=False,
                            backend_identity=product.backend_identity,
                            model_identity=product.model_identity,
                            confidence_metric_definition_version=(
                                confidence.metric_definition_version
                            ),
                            raw_checkpoint_sha256=(
                                str(product.native_metrics["raw_checkpoint_sha256"])
                                if isinstance(
                                    product.native_metrics.get("raw_checkpoint_sha256"),
                                    str,
                                )
                                else None
                            ),
                            converted_weight_sha256=(
                                str(product.native_metrics["converted_weight_sha256"])
                                if isinstance(
                                    product.native_metrics.get("converted_weight_sha256"),
                                    str,
                                )
                                else None
                            ),
                            wheel_sha256=(
                                str(product.native_metrics["wheel_sha256"])
                                if isinstance(
                                    product.native_metrics.get("wheel_sha256"), str
                                )
                                else None
                            ),
                            runner_commit=(
                                str(product.native_metrics["runner_commit"])
                                if isinstance(
                                    product.native_metrics.get("runner_commit"), str
                                )
                                else None
                            ),
                            release_identity=prediction_release_identity(product),
                            msa_provider=(
                                str(product.native_metrics["msa_provider"])
                                if isinstance(
                                    product.native_metrics.get("msa_provider"), str
                                )
                                else "precomputed"
                            ),
                            msa_endpoint=(
                                str(product.native_metrics["msa_endpoint"])
                                if isinstance(
                                    product.native_metrics.get("msa_endpoint"), str
                                )
                                else None
                            ),
                            predicted_structure=structure_ref,
                            summary_confidence=summary_ref,
                            full_confidence=full_ref,
                            pairwise_iptm=confidence.pairwise_iptm,
                            minimum_interface_pae_angstrom=(
                                confidence.minimum_interface_pae_angstrom
                            ),
                            binder_ptm=confidence.binder_ptm,
                            binder_pose_rmsd_angstrom=(
                                structure.binder_pose_rmsd_angstrom
                            ),
                            target_ca_rmsd_angstrom=(
                                structure.target_ca_rmsd_angstrom
                            ),
                            contacted_hotspot_residue_ids=contacts,
                            hotspot_coverage=interface.hotspot_coverage,
                            hotspot_count=interface.hotspot_count,
                            binder_contact_coverage=interface.binder_contact_coverage,
                            cdr_dominance=interface.cdr_dominance,
                            cdr_utilization=interface.cdr_utilization,
                            residue_pair_contact_count=(
                                interface.residue_pair_contact_count
                            ),
                            atom_contact_count=interface.atom_contact_count,
                            severe_clash_count=interface.severe_clash_count,
                            moderate_clash_count=interface.moderate_clash_count,
                            hydrogen_bond_count=interface.hydrogen_bond_count,
                            salt_bridge_count=interface.salt_bridge_count,
                            polar_contact_fraction=interface.polar_contact_fraction,
                            interface_bsa_angstrom2=interface.interface_bsa_angstrom2,
                        )
                    )
                selected = max(
                    collected_samples,
                    key=lambda item: (item.ranking_score, -item.sample_index),
                )
                representative = selected.model_copy(
                    update={"is_seed_representative": True}
                )
                seed_samples = tuple(
                    representative if item.sample_index == representative.sample_index else item
                    for item in sorted(
                        collected_samples, key=lambda value: value.sample_index
                    )
                )
            except Exception as exception:
                error = ErrorInfo(
                    code="stage07-structure-prediction-failed",
                    message=str(exception)[:4096] or exception.__class__.__name__,
                    retryable=True,
                )
            ended = datetime.now(UTC)
            succeeded = representative is not None and return_code == 0
            terminal_attempt = running_attempt.model_copy(
                update={
                    "status": (TaskStatus.SUCCEEDED if succeeded else TaskStatus.FAILED),
                    "collected_candidates": 1 if succeeded else 0,
                    "ended_at": ended,
                    "return_code": return_code,
                    "error": None if succeeded else error,
                }
            )
            with lock:
                current = current.model_copy(
                    update={
                        "status": (TaskStatus.SUCCEEDED if succeeded else TaskStatus.PENDING),
                        "collected_candidates": 1 if succeeded else 0,
                        "candidate_ids": (key,) if succeeded else (),
                        "attempts": (*current.attempts[:-1], terminal_attempt),
                        "current_device": None,
                    }
                )
                tasks[key] = current
                if representative is not None:
                    prediction_by_key[key] = representative
                    samples_by_key[key] = seed_samples
                if error is not None:
                    recent_errors.append(f"{key}: {error.message}")
                event(
                    "task-succeeded" if succeeded else "task-attempt-failed",
                    current,
                    (
                        "Collected complete structure-prediction products."
                        if succeeded
                        else "Structure-prediction attempt failed."
                    ),
                    attempt_number=attempt_number,
                    device=device,
                    from_status=TaskStatus.RUNNING,
                    to_status=current.status,
                    error=error,
                )
                persist("running", phase_id)
            if succeeded:
                return current
        if current.status is not TaskStatus.SUCCEEDED:
            exhausted = ErrorInfo(
                code="task-attempt-budget-exhausted",
                message=f"Structure-prediction task exhausted {maximum_attempts} attempts.",
                retryable=True,
            )
            with lock:
                current = current.model_copy(update={"status": TaskStatus.FAILED})
                tasks[key] = current
                recent_errors.append(f"{key}: {exhausted.message}")
                event(
                    "task-incomplete",
                    current,
                    exhausted.message,
                    from_status=TaskStatus.PENDING,
                    to_status=TaskStatus.FAILED,
                    error=exhausted,
                )
                persist("incomplete", phase_id)
        return current

    pairs = tuple(
        (candidate, seed)
        for candidate in candidates
        for seed in seeds
        if tasks[_prediction_key(candidate.candidate_id, seed)].status is not TaskStatus.SUCCEEDED
    )
    execute_on_devices(pairs, devices=devices, worker=predict)
    if any(tasks[key].status is not TaskStatus.SUCCEEDED for key in requested_keys):
        persist("incomplete", phase_id)
        raise ManifestStateError("Stage 07 structure tasks 未全部完成，可使用 runs resume")
    persist("phase-succeeded", phase_id)
    return _PredictionBatch(
        representatives=tuple(prediction_by_key[key] for key in requested_keys),
        all_samples=tuple(
            sample
            for key in requested_keys
            for sample in sorted(samples_by_key[key], key=lambda item: item.sample_index)
        ),
    )


def _scored_prediction_records(
    *,
    raw: tuple[RawFinalPrediction, ...],
    score_refold_by_id: dict[str, float],
    reference: dict[str, tuple[float, ...]] | None,
) -> tuple[
    tuple[FinalPredictionRecord, ...],
    dict[str, tuple[float, ...]],
]:
    evidence = tuple(_raw_evidence(item) for item in raw)
    scores, normalized_reference = score_full_prediction_evidence(
        evidence=evidence,
        score_refold_by_candidate=score_refold_by_id,
        seed101_reference=reference,
    )
    records = tuple(
        FinalPredictionRecord(
            candidate_id=item.candidate_id,
            seed=item.seed,
            prediction_phase=item.prediction_phase,
            sample_index=item.sample_index,
            samples_per_seed=item.samples_per_seed,
            recycles=item.recycles,
            ranking_score=item.ranking_score,
            backend_identity=item.backend_identity,
            model_identity=item.model_identity,
            confidence_metric_definition_version=(
                item.confidence_metric_definition_version
            ),
            raw_checkpoint_sha256=item.raw_checkpoint_sha256,
            converted_weight_sha256=item.converted_weight_sha256,
            wheel_sha256=item.wheel_sha256,
            runner_commit=item.runner_commit,
            release_identity=item.release_identity,
            msa_provider=item.msa_provider,
            msa_endpoint=item.msa_endpoint,
            predicted_structure=item.predicted_structure,
            summary_confidence=item.summary_confidence,
            full_confidence=item.full_confidence,
            pairwise_iptm=item.pairwise_iptm,
            minimum_interface_pae_angstrom=item.minimum_interface_pae_angstrom,
            binder_ptm=item.binder_ptm,
            binder_pose_rmsd_angstrom=item.binder_pose_rmsd_angstrom,
            target_ca_rmsd_angstrom=item.target_ca_rmsd_angstrom,
            hotspot_coverage=item.hotspot_coverage,
            contacted_hotspot_residue_ids=item.contacted_hotspot_residue_ids,
            severe_clash_count=item.severe_clash_count,
            moderate_clash_count=item.moderate_clash_count,
            metrics=final_prediction_metrics(_raw_evidence(item)),
            seed101_gate_decisions=final_prediction_decisions(
                _raw_evidence(item),
                consensus=False,
            ),
            seed101_gate_pass=all(
                decision.passed
                for decision in final_prediction_decisions(
                    _raw_evidence(item),
                    consensus=False,
                )
            ),
            consensus_gate_decisions=final_prediction_decisions(
                _raw_evidence(item),
                consensus=True,
            ),
            consensus_seed_pass=all(
                decision.passed
                for decision in final_prediction_decisions(
                    _raw_evidence(item),
                    consensus=True,
                )
            ),
            score_full=scores[(item.candidate_id, item.seed)],
        )
        for item in raw
    )
    return records, normalized_reference


def _seed_pairs(
    *,
    root: Path,
    predictions: tuple[FinalPredictionRecord, ...],
    reference_target: ParsedChain,
) -> tuple[SeedPairConsistency, ...]:
    ordered = sorted(predictions, key=lambda item: item.seed)
    results: list[SeedPairConsistency] = []
    for index, first in enumerate(ordered):
        for second in ordered[index + 1 :]:
            geometry = compute_full_target_structure_metrics(
                designed_complex=first.predicted_structure.verify(root),
                predicted_complex=second.predicted_structure.verify(root),
                reference_target=reference_target,
            )
            first_contacts = set(first.contacted_hotspot_residue_ids)
            second_contacts = set(second.contacted_hotspot_residue_ids)
            union = first_contacts.union(second_contacts)
            jaccard = (
                len(first_contacts.intersection(second_contacts)) / len(union) if union else 0.0
            )
            results.append(
                SeedPairConsistency(
                    first_seed=first.seed,
                    second_seed=second.seed,
                    binder_ca_rmsd_angstrom=geometry.binder_pose_rmsd_angstrom,
                    hotspot_contact_jaccard=jaccard,
                    passed=(geometry.binder_pose_rmsd_angstrom <= 3.0 and jaccard >= 0.50),
                )
            )
    return tuple(results)


def _run_tnp(
    *,
    root: Path,
    work: Path,
    artifacts: Path,
    candidates: tuple[CandidateRecord, ...],
    adapter: TnpAdapter,
    generated_at: datetime,
) -> tuple[TnpReport, tuple[ArtifactRef, ...]]:
    tnp_root = work / "tnp"
    sequences = tuple(
        (
            candidate.candidate_id,
            str(candidate.metrics["designed_chain_sequence"]).strip().upper(),
        )
        for candidate in candidates
    )
    candidate_ids = tuple(candidate_id for candidate_id, _sequence in sequences)
    existing_attempts = tuple(
        sorted(
            (item for item in tnp_root.glob("attempt-*") if item.is_dir()),
            key=lambda item: item.name,
        )
    )
    completed_attempt = next(
        (item for item in reversed(existing_attempts) if (item / "attempt-receipt.json").is_file()),
        None,
    )
    task_root = (
        completed_attempt
        if completed_attempt is not None
        else tnp_root / f"attempt-{len(existing_attempts) + 1:04d}"
    )
    request = TnpBatchRequest(
        sequences=sequences,
        output_directory=task_root / "output",
        input_fasta=task_root / "input.fasta",
        stdout_path=task_root / "stdout.log",
        stderr_path=task_root / "stderr.log",
    )
    if completed_attempt is not None:
        receipt = load_model(
            completed_attempt / "attempt-receipt.json",
            _TnpAttemptReceipt,
        )
        if receipt.candidate_ids != candidate_ids:
            raise ManifestStateError("TNP completed-attempt candidate identity 不一致")
        result_path = request.output_directory / "TNP_Results_Multientry.json"
        if (
            not request.input_fasta.is_file()
            or sha256_file(request.input_fasta) != receipt.input_fasta_sha256
            or not result_path.is_file()
            or sha256_file(result_path) != receipt.result_sha256
        ):
            raise ManifestStateError("TNP completed-attempt receipt/checksum 损坏")
        from easydesign.backends.tnp import TnpBatchResult

        result = TnpBatchResult(
            started_at=receipt.started_at,
            ended_at=receipt.ended_at,
            return_code=0,
            result_path=result_path,
            stdout_path=request.stdout_path,
            stderr_path=request.stderr_path,
        )
        identity = adapter.probe()
        if identity != receipt.executable_identity:
            raise ManifestStateError("TNP completed-attempt backend identity 已变化")
        records = adapter.collect(request, result)
    else:
        identity = adapter.probe()
        result = adapter.execute(request)
        records = adapter.collect(request, result)
        if result.result_path is None or not request.input_fasta.is_file():
            raise ManifestStateError("TNP succeeded attempt 缺少 input/result")
        atomic_dump_runtime_model(
            _TnpAttemptReceipt(
                candidate_ids=candidate_ids,
                input_fasta_sha256=sha256_file(request.input_fasta),
                result_sha256=sha256_file(result.result_path),
                started_at=result.started_at,
                ended_at=result.ended_at,
                executable_identity=identity,
            ),
            task_root / "attempt-receipt.json",
        )
    assert result.result_path is not None
    raw_ref = _artifact(
        root,
        result.result_path,
        artifact_id="tnp-raw-result",
        role="tnp-upstream-result",
        file_format="json",
    )
    liability_refs = tuple(
        _artifact(
            root,
            request.output_directory
            / "Final_Models"
            / f"{candidate_id}_NanoBodyBuilder2_Sequence_Liabilities.json",
            artifact_id=_qualified_artifact_id(candidate_id, "tnp-liabilities"),
            role="tnp-cdr-vernier-liability-evidence",
            file_format="csv",
        )
        for candidate_id, _sequence in request.sequences
    )
    stdout_ref = _artifact(
        root,
        result.stdout_path,
        artifact_id="tnp-stdout",
        role="tnp-standard-output",
        file_format="text",
    )
    stderr_ref = _artifact(
        root,
        result.stderr_path,
        artifact_id="tnp-stderr",
        role="tnp-standard-error",
        file_format="text",
    )
    report = TnpReport(
        generated_at=generated_at,
        executable_identity=identity,
        raw_result=raw_ref,
        candidates=records,
    )
    report_path = artifacts / "tnp-report.json"
    report = _dump_or_verify(
        report,
        report_path,
        TnpReport,
        ignore=frozenset({"generated_at"}),
    )
    report_ref = _artifact(
        root,
        report_path,
        artifact_id="tnp-report",
        role="required-developability-evidence",
        file_format="json",
    )
    return report, (raw_ref, *liability_refs, stdout_ref, stderr_ref, report_ref)


def _publish(
    *,
    root: Path,
    upstream: _Upstream,
    resolved: ResolvedRunConfig,
    artifacts: Path,
    created_at: datetime,
    output_refs: tuple[ArtifactRef, ...],
    bundle_path: Path,
    progress_ref: ArtifactRef,
    event_ref: ArtifactRef,
    status: str,
) -> Stage07Execution:
    completed = max(datetime.now(UTC), created_at + timedelta(microseconds=1))
    bundle_schema = json.loads(bundle_path.read_text(encoding="utf-8")).get(
        "schema_version"
    )
    bundle: Stage07Bundle | Stage07BundleV0_2
    package: FinalCandidatePackage | FinalCandidatePackageV0_2
    if bundle_schema == "0.2":
        bundle = load_model(bundle_path, Stage07BundleV0_2)
        package = load_model(
            bundle.final_candidate_package.verify(root),
            FinalCandidatePackageV0_2,
        )
    else:
        bundle = load_model(bundle_path, Stage07Bundle)
        package = load_model(
            bundle.final_candidate_package.verify(root),
            FinalCandidatePackage,
        )
    bundle_ref = _artifact(
        root,
        bundle_path,
        artifact_id="stage07-bundle",
        role="stage07-handoff",
        file_format="json",
    )
    all_outputs = (*output_refs, progress_ref, event_ref, bundle_ref)
    stage07_config = resolved.user_config.stage07
    if stage07_config is None:
        raise ManifestStateError("resolved config 缺少 Stage 07")
    attempt = Attempt(
        attempt_id="attempt-0001",
        status=ExecutionStatus.SUCCEEDED,
        created_at=created_at,
        started_at=created_at,
        ended_at=completed,
        backend_name="easydesign-final-filter",
        backend_version=stage07_config.final_filter_profile,
        executor_name="local-multi-gpu",
    )
    dump_model(attempt, artifacts.parent / "attempt-manifest.json")
    manifest = StageManifest(
        stage_id=StageId.FINAL_FILTERING_AND_SELECTION,
        contract_version="0.2" if bundle_schema == "0.2" else "0.1",
        status=ExecutionStatus.SUCCEEDED,
        created_at=created_at,
        completed_at=completed,
        input_artifacts=(
            upstream.target_structure_ref,
            upstream.target_sequence_ref,
            upstream.target_msa_ref,
            upstream.strategy_bundle_ref,
            upstream.stage05_bundle_ref,
            upstream.scale_bundle_ref,
            upstream.scale_candidate_index_ref,
        ),
        output_artifacts=all_outputs,
        attempts=(attempt,),
        selected_attempt_id="attempt-0001",
        warnings=(
            "smoke-review-package is not a production order package",
            "ordering remains a separate human action",
        ),
    )
    manifest.validate_inputs_declared_by(
        (upstream.stage01, upstream.stage03, upstream.stage05, upstream.stage06)
    )
    manifest_path = artifacts / "stage-manifest.json"
    dump_model(manifest, manifest_path)
    manifest_ref = _artifact(
        root,
        manifest_path,
        artifact_id="stage-07-manifest",
        role="stage-manifest",
        file_format="json",
    )
    timestamp = max(completed, upstream.run.updated_at + timedelta(microseconds=1))
    next_run = upstream.run.next_revision(
        updated_at=timestamp,
        status=ExecutionStatus.SUCCEEDED,
        completed_at=timestamp,
        stage_manifest_refs=(*upstream.run.stage_manifest_refs, manifest_ref),
        clear_workflow_state=True,
    )
    run_path = root / "manifests" / f"run-manifest.v{next_run.revision:04d}.json"
    dump_model(next_run, run_path)
    _atomic_text(run_path.name + "\n", root / "manifests" / "LATEST")
    upsert_run_index_entries(
        root.parents[1],
        (
            RunIndexEntry(
                category="project-run",
                path=root.relative_to(root.parents[1]).as_posix(),
                layout_version="1",
                status="succeeded",
                project_id=upstream.run.project_id,
                run_id=upstream.run.run_id,
                notes=(
                    f"Stage 07 status={status}",
                    f"primary={len(package.primary)},backup={len(package.backup)}",
                ),
            ),
        ),
        generated_at=timestamp,
    )
    return Stage07Execution(
        status=status,
        run_root=root,
        run_manifest=run_path,
        stage_manifest=manifest_path,
        stage07_bundle=bundle_path,
        primary_count=len(package.primary),
        backup_count=len(package.backup),
    )


def _execute_stage07(
    *,
    run_root: Path,
    prediction_adapter_builder: ComplexAdapterBuilder,
    tnp_adapter: TnpAdapter,
    executed_at: datetime | None = None,
) -> Stage07Execution:
    """Execute/resume the frozen v1.5 final-filter pipeline."""

    root = run_root.resolve()
    upstream = _load_upstream(root)
    if upstream.run.status is not ExecutionStatus.RUNNING:
        raise ManifestStateError("Stage 07 只能写入 running run")
    if any(
        item.producer_stage == str(StageId.FINAL_FILTERING_AND_SELECTION)
        for item in upstream.run.stage_manifest_refs
    ):
        raise ManifestStateError("Stage 07 已发布，禁止覆盖")
    resolved, _ = load_resolved_run_config(root)
    config = resolved.user_config.stage07
    stage04_config = resolved.user_config.stage04
    if config is None or stage04_config is None:
        raise ManifestStateError("run config 缺少 Stage 04/07")
    providers = config.full_target_prediction.target_msa.resolved_providers()
    if not providers:
        raise ManifestStateError("Stage 07 target MSA provider identity 缺失")
    now = datetime.now(UTC) if executed_at is None else executed_at
    attempt_root = root / str(StageId.FINAL_FILTERING_AND_SELECTION) / "attempt-0001"
    artifacts = attempt_root / "artifacts"
    work = attempt_root / "work"
    runtime = attempt_root / "runtime"
    artifacts.mkdir(parents=True, exist_ok=True)
    runtime.mkdir(parents=True, exist_ok=True)
    profile_path = artifacts / "filter-profile.yaml"
    profile_bytes = _profile_bytes(config.final_filter_profile)
    profile_sha256 = (
        FINAL_PROFILE_SOURCE_SHA256_V1_6
        if config.final_filter_profile == "nanobody-final-v1.6"
        else FINAL_PROFILE_SOURCE_SHA256
    )
    if profile_path.exists():
        if profile_path.read_bytes() != profile_bytes:
            raise ManifestStateError("Stage 07 existing profile bytes 不一致")
    else:
        profile_path.write_bytes(profile_bytes)
    profile_ref = _artifact(
        root,
        profile_path,
        artifact_id="nanobody-final-profile",
        role="versioned-final-filter-profile",
        file_format="yaml",
    )
    multi_strategy = isinstance(upstream.scale_bundle, ScaleBundleV0_2)
    scale_input_ref: ArtifactRef | None = None
    if multi_strategy:
        scale_input_path = artifacts / "stage07-scale-input.json"
        _dump_or_verify(
            upstream.scale_input,
            scale_input_path,
            Stage07ScaleInput,
        )
        scale_input_ref = _artifact(
            root,
            scale_input_path,
            artifact_id="stage07-scale-input",
            role="normalized-multi-strategy-scale-input",
            file_format="json",
        )

    unpaired, structural = _batch_local_metrics(
        root=root,
        upstream=upstream,
        runtime=runtime,
        created_at=now,
    )
    candidates = upstream.scale_candidate_index.candidates
    sequence_records = evaluate_sequence_prefilter(
        candidates=candidates,
        unpaired_new_cysteines=unpaired,
    )
    candidate_by_id = {item.candidate_id: item for item in candidates}
    selected_for_deep = tuple(
        candidate_by_id[item.candidate_id] for item in sequence_records if item.selected_for_deep
    )
    if selected_for_deep:
        shared_report = evaluate_pilot_candidates(
            candidates=selected_for_deep,
            structural_metrics={
                item.candidate_id: structural[item.candidate_id] for item in selected_for_deep
            },
            profile_sha256=profile_sha256,
            candidate_index_sha256=upstream.scale_candidate_index_ref.sha256,
            maximum_tier_a_strategies=len(
                upstream.scale_input.strategy_allocations
            ),
            generated_at=now,
        )
        deep_records = convert_deep_filter_records(
            pilot_records=shared_report.candidate_records,
        )
    else:
        deep_records = ()
    seed101_candidates = tuple(
        candidate_by_id[item.candidate_id] for item in deep_records if item.selected_for_seed101
    )
    score_refold = {item.candidate_id: item.score_refold for item in sequence_records}
    all_prediction_records: tuple[FinalPredictionRecord, ...] = ()
    all_sample_predictions: tuple[RawFinalPrediction, ...] = ()
    consensus_records: tuple[MultiSeedConsensusRecord, ...] = ()
    tnp_report: TnpReport | None = None
    tnp_refs: tuple[ArtifactRef, ...] = ()
    normalization_ref: ArtifactRef | None = None
    selections: tuple[FinalSelectionRecord, ...] = ()
    scale_plan: ScalePlanV0_2 | ScalePlan
    if isinstance(upstream.scale_bundle, ScaleBundleV0_2):
        scale_plan = load_model(
            upstream.scale_bundle.scale_plan.verify(root),
            ScalePlanV0_2,
        )
    else:
        scale_plan = load_model(
            upstream.scale_bundle.scale_plan.verify(root),
            ScalePlan,
        )
    execution_devices = scale_plan.devices

    if seed101_candidates:
        seed101_batch = _execute_predictions(
            root=root,
            upstream=upstream,
            candidates=seed101_candidates,
            seeds=(101,),
            sample_count=1,
            phase_id="seed101-screen",
            work=work,
            runtime=runtime,
            adapter_builder=prediction_adapter_builder,
            provider=providers[0],
            devices=execution_devices,
            maximum_attempts=stage04_config.executor.max_task_attempts,
            created_at=now,
        )
        seed101_records, reference = _scored_prediction_records(
            raw=seed101_batch.representatives,
            score_refold_by_id=score_refold,
            reference=None,
        )
        normalization = Seed101Normalization(
            generated_at=now,
            source_candidate_ids=tuple(
                item.candidate_id for item in seed101_batch.representatives
            ),
            metric_reference_values=reference,
        )
        normalization_path = artifacts / "seed101-normalization.json"
        normalization = _dump_or_verify(
            normalization,
            normalization_path,
            Seed101Normalization,
            ignore=frozenset({"generated_at"}),
        )
        normalization_ref = _artifact(
            root,
            normalization_path,
            artifact_id="seed101-normalization",
            role="frozen-empirical-score-reference",
            file_format="json",
        )
        additional_candidates = tuple(
            candidate_by_id[item.candidate_id]
            for item in sorted(
                (record for record in seed101_records if record.seed101_gate_pass),
                key=lambda item: (-item.score_full, item.candidate_id),
            )[:60]
        )
        if additional_candidates:
            afo_final = config.final_filter_profile == "nanobody-final-v1.6"
            additional_batch = _execute_predictions(
                root=root,
                upstream=upstream,
                candidates=additional_candidates,
                seeds=(101, 202, 303, 404, 505) if afo_final else (202, 303),
                sample_count=5 if afo_final else 1,
                phase_id="deep-5x5" if afo_final else "additional-seeds",
                work=work,
                runtime=runtime,
                adapter_builder=prediction_adapter_builder,
                provider=providers[0],
                devices=execution_devices,
                maximum_attempts=stage04_config.executor.max_task_attempts,
                created_at=now,
            )
            additional_records, _ = _scored_prediction_records(
                raw=additional_batch.representatives,
                score_refold_by_id=score_refold,
                reference=reference,
            )
        else:
            afo_final = config.final_filter_profile == "nanobody-final-v1.6"
            additional_batch = _PredictionBatch(representatives=(), all_samples=())
            additional_records = ()
        deep_candidate_ids = {item.candidate_id for item in additional_records}
        screen_records = tuple(
            item
            for item in seed101_records
            if not afo_final or item.candidate_id not in deep_candidate_ids
        )
        all_prediction_records = tuple(
            sorted(
                (*screen_records, *additional_records),
                key=lambda item: (item.candidate_id, item.seed, item.sample_index),
            )
        )
        all_sample_predictions = tuple(
            sorted(
                (*seed101_batch.all_samples, *additional_batch.all_samples),
                key=lambda item: (
                    item.candidate_id,
                    item.prediction_phase,
                    item.seed,
                    item.sample_index,
                ),
            )
        )
        by_candidate: dict[str, list[FinalPredictionRecord]] = {}
        for item in all_prediction_records:
            by_candidate.setdefault(item.candidate_id, []).append(item)
        deep_by_id = {item.candidate_id: item for item in deep_records}
        reference_target = parse_protein_chain(
            upstream.target_structure_ref.verify(root),
            "A",
        )
        consensus_records = tuple(
            build_multi_seed_consensus(
                candidate_id=candidate_id,
                predictions=tuple(records),
                score_deep=deep_by_id[candidate_id].score_deep,
                pair_metrics=_seed_pairs(
                    root=root,
                    predictions=tuple(records),
                    reference_target=reference_target,
                ),
                required_individually_passing_seeds=3 if afo_final else 2,
            )
            for candidate_id, records in sorted(by_candidate.items())
        )
        passing_ids = {item.candidate_id for item in consensus_records if item.consensus_pass}
        if passing_ids:
            tnp_candidates = tuple(
                candidate_by_id[candidate_id] for candidate_id in sorted(passing_ids)
            )
            tnp_report, tnp_refs = _run_tnp(
                root=root,
                work=work,
                artifacts=artifacts,
                candidates=tnp_candidates,
                adapter=tnp_adapter,
                generated_at=now,
            )
            design_sequences = {
                candidate_id: str(candidate_by_id[candidate_id].metrics["designed_sequence"])
                .strip()
                .upper()
                for candidate_id in passing_ids
            }
            selections = lazy_greedy_select(
                consensus=tuple(item for item in consensus_records if item.consensus_pass),
                tnp=tnp_report.candidates,
                design_sequences=design_sequences,
                primary_count=config.primary_count,
                backup_count=config.backup_count,
            )

    status: Literal["candidates-selected", "stopped-no-final-candidate"] = (
        "candidates-selected" if selections else "stopped-no-final-candidate"
    )
    report = FinalFilterReport(
        generated_at=now,
        profile_id=config.final_filter_profile,
        profile_sha256=profile_sha256,
        scale_candidate_index_sha256=upstream.scale_candidate_index_ref.sha256,
        sequence_prefilter=sequence_records,
        deep_filter=deep_records,
        predictions=all_prediction_records,
        sample_predictions=all_sample_predictions,
        consensus=consensus_records,
        selections=selections,
        status=status,
    )
    report_path = artifacts / "final-filter-report.json"
    report = _dump_or_verify(
        report,
        report_path,
        FinalFilterReport,
        ignore=frozenset({"generated_at"}),
    )
    report_ref = _artifact(
        root,
        report_path,
        artifact_id="final-filter-report",
        role="complete-candidate-disposition",
        file_format="json",
    )
    stop_ref: ArtifactRef | None = None
    if status == "stopped-no-final-candidate":
        stop_path = artifacts / "scientific-stop.json"
        stop = ScientificStop(
            stage_id=str(StageId.FINAL_FILTERING_AND_SELECTION),
            code=ScientificStopCode.NO_FINAL_CANDIDATE,
            occurred_at=now,
            message="No candidate satisfied the frozen Stage 07 final pipeline.",
            evidence_artifact_sha256=(report_ref.sha256,),
        )
        stop = _dump_or_verify(
            stop,
            stop_path,
            ScientificStop,
            ignore=frozenset({"occurred_at"}),
        )
        stop_ref = _artifact(
            root,
            stop_path,
            artifact_id="stage07-scientific-stop",
            role="scientific-negative-result",
            file_format="json",
        )

    sequence_by_id = {item.candidate_id: item for item in sequence_records}
    deep_by_id = {item.candidate_id: item for item in deep_records}
    consensus_by_id = {item.candidate_id: item for item in consensus_records}
    tnp_by_id = (
        {item.candidate_id: item for item in tnp_report.candidates}
        if tnp_report is not None
        else {}
    )
    prediction_by_id: dict[str, list[FinalPredictionRecord]] = {}
    for item in all_prediction_records:
        prediction_by_id.setdefault(item.candidate_id, []).append(item)

    def candidate_package_item(selection: FinalSelectionRecord) -> FinalCandidate:
        candidate = candidate_by_id[selection.candidate_id]
        final_score = consensus_by_id[candidate.candidate_id].score_final
        assert final_score is not None
        return FinalCandidate(
            candidate_id=candidate.candidate_id,
            strategy_id=candidate.strategy_id,
            sequence=sequence_by_id[candidate.candidate_id].sequence,
            design_sequence=sequence_by_id[candidate.candidate_id].design_sequence,
            source_refolded_structure=candidate.refolded_structure,
            prediction_structures=tuple(
                item.predicted_structure
                for item in sorted(
                    prediction_by_id[candidate.candidate_id],
                    key=lambda value: value.seed,
                )
                if item.seed in consensus_by_id[candidate.candidate_id].consensus_seed_ids
            ),
            score_refold=sequence_by_id[candidate.candidate_id].score_refold,
            score_deep=deep_by_id[candidate.candidate_id].score_deep,
            score_final=final_score,
            consensus=consensus_by_id[candidate.candidate_id],
            tnp=tnp_by_id[candidate.candidate_id],
            selection=selection,
            warnings=tuple(
                item.name for item in sequence_by_id[candidate.candidate_id].liabilities
            ),
        )

    biosafety_pending = "biosafety" in resolved.user_config.design.required_reviews
    scale_candidate_count = (
        upstream.scale_bundle.total_candidate_budget
        if isinstance(upstream.scale_bundle, ScaleBundleV0_2)
        else upstream.scale_bundle.requested_new_candidates
    )
    package_type: Literal[
        "smoke-review-package",
        "draft-order-package",
        "empty-review-package",
    ] = (
        "empty-review-package"
        if not selections
        else (
            "draft-order-package"
            if biosafety_pending or scale_candidate_count >= 50_000
            else "smoke-review-package"
        )
    )
    scale_profile: Literal[
        "user-defined-v1",
        "smoke-1000",
        "production-50000",
    ] = upstream.scale_bundle.profile.value
    biosafety_status: Literal["not-required", "pending"] = (
        "pending" if biosafety_pending else "not-required"
    )
    primary_candidates = tuple(
        candidate_package_item(item)
        for item in selections
        if item.selection_class == "primary"
    )
    backup_candidates = tuple(
        candidate_package_item(item)
        for item in selections
        if item.selection_class == "backup"
    )
    if multi_strategy:
        package: FinalCandidatePackage | FinalCandidatePackageV0_2 = (
            FinalCandidatePackageV0_2(
                generated_at=now,
                package_type=package_type,
                scale_profile=scale_profile,
                primary=primary_candidates,
                backup=backup_candidates,
                requested_primary_count=config.primary_count,
                requested_backup_count=config.backup_count,
                source_distribution=summarize_selected_sources(
                    primary=primary_candidates,
                    backup=backup_candidates,
                ),
                biosafety_review_status=biosafety_status,
                status=status,
            )
        )
    else:
        package = FinalCandidatePackage(
            generated_at=now,
            package_type=package_type,
            scale_profile=scale_profile,
            primary=primary_candidates,
            backup=backup_candidates,
            requested_primary_count=config.primary_count,
            requested_backup_count=config.backup_count,
            biosafety_review_status=biosafety_status,
            status=status,
        )
    package_path = artifacts / "final-candidate-package.json"
    if isinstance(package, FinalCandidatePackageV0_2):
        package = _dump_or_verify(
            package,
            package_path,
            FinalCandidatePackageV0_2,
            ignore=frozenset({"generated_at"}),
        )
    else:
        package = _dump_or_verify(
            package,
            package_path,
            FinalCandidatePackage,
            ignore=frozenset({"generated_at"}),
        )
    package_ref = _artifact(
        root,
        package_path,
        artifact_id="final-candidate-package",
        role="human-review-package",
        file_format="json",
    )
    terminal_time = max(datetime.now(UTC), now + timedelta(microseconds=1))
    runtime_progress_path = runtime / "progress.json"
    if runtime_progress_path.is_file():
        observed_progress = load_latest_runtime_model(
            runtime_progress_path,
            ProgressSnapshot,
        )
    else:
        observed_progress = ProgressSnapshot(
            stage_id=str(StageId.FINAL_FILTERING_AND_SELECTION),
            phase="final-selection",
            updated_at=terminal_time,
            status="phase-succeeded",
            total_tasks=len(candidates),
            pending_tasks=0,
            waiting_tasks=0,
            running_tasks=0,
            succeeded_tasks=len(candidates),
            failed_tasks=0,
            planned_candidates=len(candidates),
            collected_candidates=len(candidates),
            elapsed_seconds=max((terminal_time - now).total_seconds(), 0.0),
            estimated_remaining_seconds=0.0,
        )
    terminal_progress = observed_progress.model_copy(
        update={
            "phase": "stage07-complete",
            "updated_at": terminal_time,
            "status": status,
            "pending_tasks": 0,
            "waiting_tasks": 0,
            "running_tasks": 0,
            "failed_tasks": 0,
            "succeeded_tasks": observed_progress.total_tasks,
            "collected_candidates": observed_progress.planned_candidates,
            "per_device": {},
            "estimated_remaining_seconds": 0.0,
        }
    )
    progress_path = artifacts / "progress-final.json"
    terminal_progress = _dump_or_verify(
        terminal_progress,
        progress_path,
        ProgressSnapshot,
        ignore=frozenset({"updated_at", "elapsed_seconds"}),
    )
    progress_ref = _artifact(
        root,
        progress_path,
        artifact_id="stage07-progress-final",
        role="terminal-progress",
        file_format="json",
    )
    runtime_events = runtime / "task-events.jsonl"
    events_path = artifacts / "task-events.jsonl"
    event_bytes = runtime_events.read_bytes() if runtime_events.is_file() else b""
    if events_path.exists():
        if events_path.read_bytes() != event_bytes:
            raise ManifestStateError("Stage 07 frozen task events 不一致")
    else:
        with events_path.open("xb") as handle:
            handle.write(event_bytes)
            handle.flush()
            os.fsync(handle.fileno())
    event_ref = _artifact(
        root,
        events_path,
        artifact_id="stage07-task-events",
        role="append-only-task-events",
        file_format="jsonl",
    )
    runtime_failures = runtime / "operational-failures.jsonl"
    failure_ref: ArtifactRef | None = None
    if runtime_failures.is_file():
        failure_path = artifacts / "operational-failures.jsonl"
        failure_bytes = runtime_failures.read_bytes()
        if failure_path.exists():
            if failure_path.read_bytes() != failure_bytes:
                raise ManifestStateError("Stage 07 frozen operational failure evidence 不一致")
        else:
            with failure_path.open("xb") as handle:
                handle.write(failure_bytes)
                handle.flush()
                os.fsync(handle.fileno())
        failure_ref = _artifact(
            root,
            failure_path,
            artifact_id="stage07-operational-failures",
            role="recovered-operational-failure-evidence",
            file_format="jsonl",
        )
    bundle_path = artifacts / "stage07-bundle.json"
    tnp_report_ref = next(
        (item for item in tnp_refs if item.artifact_id == "tnp-report"),
        None,
    )
    if multi_strategy:
        assert scale_input_ref is not None
        bundle: Stage07Bundle | Stage07BundleV0_2 = Stage07BundleV0_2(
            generated_at=now,
            scale_bundle=upstream.scale_bundle_ref,
            scale_input=scale_input_ref,
            filter_profile=profile_ref,
            final_filter_report=report_ref,
            final_candidate_package=package_ref,
            seed101_normalization=normalization_ref,
            tnp_report=tnp_report_ref,
            progress_final=progress_ref,
            task_events=event_ref,
            operational_failures=failure_ref,
            scientific_stop=stop_ref,
            status=status,
        )
        bundle = _dump_or_verify(
            bundle,
            bundle_path,
            Stage07BundleV0_2,
            ignore=frozenset({"generated_at"}),
        )
    else:
        bundle = Stage07Bundle(
            generated_at=now,
            scale_bundle=upstream.scale_bundle_ref,
            filter_profile=profile_ref,
            final_filter_report=report_ref,
            final_candidate_package=package_ref,
            seed101_normalization=normalization_ref,
            tnp_report=tnp_report_ref,
            progress_final=progress_ref,
            task_events=event_ref,
            operational_failures=failure_ref,
            scientific_stop=stop_ref,
            status=status,
        )
        bundle = _dump_or_verify(
            bundle,
            bundle_path,
            Stage07Bundle,
            ignore=frozenset({"generated_at"}),
        )
    base_output_refs = (
        profile_ref,
        *((scale_input_ref,) if scale_input_ref is not None else ()),
        report_ref,
        package_ref,
        *((normalization_ref,) if normalization_ref is not None else ()),
        *tnp_refs,
        *((failure_ref,) if failure_ref is not None else ()),
        *((stop_ref,) if stop_ref is not None else ()),
        *tuple(
            reference
            for prediction in all_prediction_records
            for reference in (
                prediction.predicted_structure,
                prediction.summary_confidence,
                prediction.full_confidence,
            )
        ),
    )
    return _publish(
        root=root,
        upstream=upstream,
        resolved=resolved,
        artifacts=artifacts,
        created_at=now,
        output_refs=base_output_refs,
        bundle_path=bundle_path,
        progress_ref=progress_ref,
        event_ref=event_ref,
        status=status,
    )


def execute_stage07(
    *,
    run_root: Path,
    prediction_adapter_builder: ComplexAdapterBuilder,
    tnp_adapter: TnpAdapter,
    executed_at: datetime | None = None,
) -> Stage07Execution:
    """Execute Stage 07 and append structured operational evidence on failure."""

    try:
        return _execute_stage07(
            run_root=run_root,
            prediction_adapter_builder=prediction_adapter_builder,
            tnp_adapter=tnp_adapter,
            executed_at=executed_at,
        )
    except Exception as error:
        root = run_root.expanduser().resolve()
        if (root / "manifests").is_dir():
            runtime = root / str(StageId.FINAL_FILTERING_AND_SELECTION) / "attempt-0001" / "runtime"
            runtime.mkdir(parents=True, exist_ok=True)
            progress_path = runtime / "progress.json"
            progress: ProgressSnapshot | None = None
            if progress_path.is_file():
                try:
                    progress = load_latest_runtime_model(
                        progress_path,
                        ProgressSnapshot,
                    )
                except Exception:
                    progress = None
            message = str(error)[:4096] or error.__class__.__name__
            lower = message.lower()
            failure = OperationalFailure(
                occurred_at=datetime.now(UTC),
                code="stage07-execution-failed",
                error_type=error.__class__.__name__,
                message=message,
                retryable=any(
                    token in lower
                    for token in (
                        "timeout",
                        "未全部完成",
                        "exhausted",
                        "resource",
                        "returncode",
                    )
                ),
                planned_tasks=(progress.total_tasks if progress is not None else None),
                completed_tasks=(progress.succeeded_tasks if progress is not None else None),
                required_tool=(
                    "TNP" if "tnp" in lower else ("Protenix-v2" if "protenix" in lower else None)
                ),
            )
            failure_path = runtime / "operational-failures.jsonl"
            with failure_path.open("a", encoding="utf-8", newline="\n") as handle:
                handle.write(failure.model_dump_json())
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
        raise
