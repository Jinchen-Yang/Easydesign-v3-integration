"""Stage 05 pilot filtering, expansion, and unique scale-strategy selection."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import threading
import time
from collections.abc import Callable
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from importlib import resources
from pathlib import Path
from typing import Any, Literal, cast

import yaml  # type: ignore[import-untyped]
from pydantic import BaseModel, ConfigDict, Field

from easydesign.backends.boltzgen import BoltzGenGenerationAdapter
from easydesign.backends.executors import NvidiaSmiProbe, execute_on_devices
from easydesign.backends.structure_prediction import (
    BackendInvocation,
    ComplexStructurePredictionRequest,
    MsaMode,
    OpenFold3Af3JaxAdapter,
    PredictionParameterProfile,
    ProtenixV2Adapter,
    ScientificMode,
    StructurePredictionRequest,
    TargetStructureCondition,
    TemplateMode,
)
from easydesign.backends.target_sources import normalize_raw_sequence
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
    METRIC_DEFINITION_VERSION,
    PROFILE_SOURCE_SHA256,
    PROFILE_SOURCE_SHA256_V1_6,
    PROFILE_SOURCE_SHA256_V1_7,
    InterfaceMetricValues,
    build_advisory_validation_report,
    compute_full_target_structure_metrics,
    compute_interface_metrics,
    evaluate_expansion_candidates,
    evaluate_pilot_candidates,
    evaluate_pilot_candidates_v1_6,
    extract_complex_confidence,
    parse_protein_chain,
    promotion_records,
    select_scale_strategy,
)
from easydesign.filtering.structure_metrics import ParsedChain
from easydesign.safe_writes import read_last_text_line
from easydesign.stages.s01_target_preparation import TargetBundle
from easydesign.stages.s03_boltzgen_configuration import StrategyBundle
from easydesign.stages.s04_pilot_generation import (
    CandidateIndex,
    CandidateRecord,
    PilotBundle,
    PilotPlan,
)
from easydesign.stages.s05_pilot_filtering import (
    AdvisoryValidationReport,
    ExpansionExecutionState,
    ExpansionValidationReport,
    FilterDecision,
    FullTargetExecutionState,
    FullTargetPredictionRecord,
    PilotFilterReport,
    PilotFilterReportV1_6,
    ScientificStop,
    ScientificStopCode,
    Stage05Bundle,
    Stage05BundleV0_2,
    TargetConditionedStage05Evidence,
)

from .afo_template_protocol import (
    PROTOCOL_ID as AFO_TEMPLATE_PROTOCOL_ID,
)
from .afo_template_protocol import (
    audit_final_input,
    prepare_binder_template_config,
    prepare_target_template_config,
)
from .boltzgen_tasks import (
    TaskTransition,
    execute_boltzgen_candidate_task,
    recover_interrupted_boltzgen_task,
)
from .complex_prediction_support import (
    configured_prediction_chain,
    prediction_release_identity,
    prepare_query_only_a3m,
    read_fasta_sequence,
    run_checked_backend_invocation,
    snapshot_target_structure_condition,
)
from .config import (
    ComplexPredictionConfig,
    ComplexTemplateConfig,
    PrecomputedComplexMsaConfig,
    ResolvedProtenixMsaProviderConfig,
    Stage05Config,
)
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

ComplexAdapterBuilder = Callable[
    [ResolvedProtenixMsaProviderConfig, int],
    ProtenixV2Adapter | OpenFold3Af3JaxAdapter,
]


class Stage05Execution(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: str
    run_root: Path
    run_manifest: Path
    stage_manifest: Path
    stage05_bundle: Path
    selected_strategy_id: str | None = None
    promoted_strategy_ids: tuple[str, ...] = ()
    review_dashboard: Path | None = None
    reporting_warning: str | None = None
    next_actions: tuple[str, ...] = ()


def _with_review_dashboard(
    execution: Stage05Execution,
    *,
    generated_at: datetime,
) -> Stage05Execution:
    from easydesign.reporting.review_dashboard import (
        generate_review_dashboard_nonblocking,
    )

    dashboard = generate_review_dashboard_nonblocking(
        execution.run_root,
        report_kind="stage05",
        generated_at=generated_at,
    )
    if dashboard.entrypoint is not None:
        return execution.model_copy(update={"review_dashboard": dashboard.entrypoint})
    message = (
        "Stage 05 科学产物已发布，但 review dashboard 生成失败："
        f"{dashboard.error.message if dashboard.error is not None else 'unknown error'}"
    )
    return execution.model_copy(
        update={
            "reporting_warning": message,
            "next_actions": (
                "运行 easydesign report build PROJECT --run RUN --report stage05 重建页面",
            ),
        }
    )


class _StructureMetricCacheRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: str = "0.1"
    candidate_id: str
    candidate_structure_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    reference_target_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    design_mask_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    hotspot_residue_ids: tuple[int, ...]
    definition_version: str
    metrics: InterfaceMetricValues


def _stage05_filter_profile(config: Stage05Config) -> str:
    """Read the profile without coupling execution to one config schema."""

    return str(config.filter_profile)


def _diagnostic_expanded_total(config: Stage05Config) -> int:
    value = getattr(config, "diagnostic_expanded_total_per_strategy", None)
    if value is None:
        value = getattr(config, "expanded_total_per_strategy", None)
    if not isinstance(value, int):
        raise ManifestStateError("Stage 05 缺少 diagnostic expansion 总数")
    return value


def _diagnostic_full_target_top_n(config: Stage05Config) -> int:
    value = getattr(config, "diagnostic_full_target_refold_top_n", None)
    if value is None:
        strategy_selection = getattr(config, "strategy_selection", None)
        value = getattr(strategy_selection, "full_target_refold_top_n", None)
    if not isinstance(value, int):
        raise ManifestStateError("Stage 05 缺少 full-target diagnostic 数量")
    return value


class _TargetMsaState(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: str = "0.1"
    provider: ResolvedProtenixMsaProviderConfig
    source_relative_path: str
    target_sequence_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    a3m_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    depth: int = Field(ge=2)


@dataclass(frozen=True, slots=True)
class _Upstream:
    run: RunManifest
    run_manifest_path: Path
    stage01: StageManifest
    stage03: StageManifest
    stage04: StageManifest
    target_structure_ref: ArtifactRef
    target_sequence_ref: ArtifactRef
    target_bundle_ref: ArtifactRef | None
    target_bundle: TargetBundle | None
    strategy_bundle_ref: ArtifactRef
    strategy_bundle_path: Path
    strategy_bundle: StrategyBundle
    pilot_bundle_ref: ArtifactRef
    pilot_bundle: PilotBundle
    candidate_index_ref: ArtifactRef
    candidate_index: CandidateIndex


def _latest_manifest(root: Path) -> tuple[RunManifest, Path]:
    pointer = root / "manifests" / "LATEST"
    try:
        name = read_last_text_line(pointer)
    except OSError as error:
        raise ManifestStateError(f"无法读取 RunManifest LATEST: {pointer}") from error
    path = root / "manifests" / name
    return load_model(path, RunManifest), path


def _stage_from_run(
    root: Path,
    run: RunManifest,
    stage_id: StageId,
) -> tuple[StageManifest, ArtifactRef]:
    reference = next(
        (item for item in run.stage_manifest_refs if item.producer_stage == str(stage_id)),
        None,
    )
    if reference is None:
        raise ManifestStateError(f"Stage 05 缺少上游 {stage_id} manifest")
    manifest = load_model(reference.verify(root), StageManifest)
    if manifest.status is not ExecutionStatus.SUCCEEDED:
        raise ManifestStateError(f"上游 {stage_id} 未成功")
    return manifest, reference


def _load_upstream(root: Path) -> _Upstream:
    run, run_path = _latest_manifest(root)
    stage01, _ = _stage_from_run(root, run, StageId.TARGET_PREPARATION)
    stage03, _ = _stage_from_run(root, run, StageId.BOLTZGEN_CONFIGURATION)
    stage04, _ = _stage_from_run(root, run, StageId.PILOT_GENERATION)
    target_structure_ref = stage01.require_output("target-structure")
    target_sequence_ref = stage01.require_output("target-sequence")
    target_bundle_ref = next(
        (
            item
            for item in stage01.output_artifacts
            if item.artifact_id == "target-bundle"
        ),
        None,
    )
    target_bundle = (
        None
        if target_bundle_ref is None
        else load_model(target_bundle_ref.verify(root), TargetBundle)
    )
    strategy_bundle_ref = stage03.require_output("strategy-bundle")
    strategy_bundle_path = strategy_bundle_ref.verify(root)
    strategy_bundle = load_model(strategy_bundle_path, StrategyBundle)
    pilot_bundle_ref = stage04.require_output("pilot-bundle")
    pilot_bundle = load_model(pilot_bundle_ref.verify(root), PilotBundle)
    candidate_index_ref = stage04.require_output("candidate-index")
    if pilot_bundle.candidate_index != candidate_index_ref:
        raise ManifestStateError("PilotBundle candidate index 与 StageManifest 不一致")
    candidate_index = load_model(candidate_index_ref.verify(root), CandidateIndex)
    if candidate_index.strategy_bundle_sha256 != strategy_bundle_ref.sha256:
        raise ManifestStateError("CandidateIndex 与 StrategyBundle identity 不一致")
    for candidate in candidate_index.candidates:
        candidate.original_structure.verify(root)
        candidate.refolded_structure.verify(root)
    return _Upstream(
        run=run,
        run_manifest_path=run_path,
        stage01=stage01,
        stage03=stage03,
        stage04=stage04,
        target_structure_ref=target_structure_ref,
        target_sequence_ref=target_sequence_ref,
        target_bundle_ref=target_bundle_ref,
        target_bundle=target_bundle,
        strategy_bundle_ref=strategy_bundle_ref,
        strategy_bundle_path=strategy_bundle_path,
        strategy_bundle=strategy_bundle,
        pilot_bundle_ref=pilot_bundle_ref,
        pilot_bundle=pilot_bundle,
        candidate_index_ref=candidate_index_ref,
        candidate_index=candidate_index,
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
        producer_stage=str(StageId.PILOT_FILTERING),
        producer_attempt="attempt-0001",
    )


def _publish_final_execution_evidence(
    *,
    root: Path,
    artifacts: Path,
    runtime: Path,
    status: str,
    completed_at: datetime,
) -> tuple[ArtifactRef, ArtifactRef]:
    """Freeze mutable progress/event evidence before publishing Stage 05."""

    runtime_progress = runtime / "progress.json"
    if not runtime_progress.is_file():
        raise ManifestStateError("Stage 05 缺少 runtime progress，不能发布终态")
    observed = load_latest_runtime_model(runtime_progress, ProgressSnapshot)
    final_progress = observed.model_copy(
        update={
            "updated_at": completed_at,
            "phase": "stage05-complete",
            "status": status,
            "per_device": {},
            "estimated_remaining_seconds": 0.0,
        }
    )
    progress_path = artifacts / "progress-final.json"
    if progress_path.exists():
        final_progress = load_model(progress_path, ProgressSnapshot)
        if final_progress.phase != "stage05-complete" or final_progress.status != status:
            raise ManifestStateError("Stage 05 已冻结 progress 与当前终态不一致")
    else:
        dump_model(final_progress, progress_path)

    runtime_events = runtime / "task-events.jsonl"
    events_path = artifacts / "task-events.jsonl"
    event_bytes = runtime_events.read_bytes() if runtime_events.is_file() else b""
    if events_path.exists():
        if events_path.read_bytes() != event_bytes:
            raise ManifestStateError("Stage 05 已冻结 task events 与 runtime 不一致")
    else:
        events_path.parent.mkdir(parents=True, exist_ok=True)
        with events_path.open("xb") as handle:
            handle.write(event_bytes)
            handle.flush()
            os.fsync(handle.fileno())

    return (
        _artifact(
            root,
            progress_path,
            artifact_id="stage05-progress-final",
            role="terminal-progress-snapshot",
            file_format="json",
        ),
        _artifact(
            root,
            events_path,
            artifact_id="stage05-task-events",
            role="append-only-task-events",
            file_format="jsonl",
        ),
    )


def _profile_bytes(profile_id: str) -> bytes:
    expected_hash = {
        "nanobody-filter-standard-v1.5": PROFILE_SOURCE_SHA256,
        "nanobody-filter-standard-v1.6": PROFILE_SOURCE_SHA256_V1_6,
        "nanobody-filter-standard-v1.7": PROFILE_SOURCE_SHA256_V1_7,
    }.get(profile_id)
    if expected_hash is None:
        raise ManifestStateError(f"未知 Stage 05 filter profile: {profile_id}")
    source = resources.files("easydesign.resources").joinpath(
        f"filter_profiles/{profile_id}.yaml"
    )
    content = source.read_bytes()
    payload: Any = yaml.safe_load(content)
    try:
        source_hash = payload["source_document"]["sha256"]
    except (KeyError, TypeError) as error:
        raise ManifestStateError("filter profile 缺少 source document identity") from error
    if source_hash != expected_hash:
        raise ManifestStateError("filter profile 内的 standard SHA-256 不一致")
    return content


def _candidate_structure_metrics(
    *,
    root: Path,
    candidate: CandidateRecord,
    strategy_hotspots: tuple[int, ...],
    reference_target: ParsedChain,
) -> tuple[str, object]:
    if candidate.design_mask_source is None or not candidate.designed_binder_residue_ids:
        raise ManifestStateError(
            f"candidate={candidate.candidate_id} 缺少 Stage 04 design-mask evidence；"
            "请用当前版本重新收集 Stage 04 candidate index"
        )
    candidate.design_mask_source.verify(root)
    metrics = compute_interface_metrics(
        candidate_structure=candidate.refolded_structure.verify(root),
        reference_target=reference_target,
        hotspot_residue_ids=strategy_hotspots,
        cdr_residue_ids=candidate.designed_binder_residue_ids,
    )
    return candidate.candidate_id, metrics


def _batch_structure_metrics(
    *,
    root: Path,
    upstream: _Upstream,
    candidates: tuple[CandidateRecord, ...],
    runtime_root: Path,
    phase: str,
    created_at: datetime,
) -> dict[str, InterfaceMetricValues]:
    strategy_by_id = {
        strategy.strategy_id: strategy for strategy in upstream.strategy_bundle.strategies
    }
    reference = parse_protein_chain(
        upstream.target_structure_ref.verify(root),
        "A",
    )
    cache_root = runtime_root / "structure-metrics"
    cache_root.mkdir(parents=True, exist_ok=True)
    progress_path = runtime_root / "progress.json"
    results: dict[str, InterfaceMetricValues] = {}
    missing: list[CandidateRecord] = []
    identity_by_id: dict[str, _StructureMetricCacheRecord] = {}
    for candidate in candidates:
        strategy = strategy_by_id[candidate.strategy_id]
        if candidate.design_mask_source is None:
            raise ManifestStateError(
                f"candidate={candidate.candidate_id} 缺少 design-mask ArtifactRef"
            )
        identity = _StructureMetricCacheRecord(
            candidate_id=candidate.candidate_id,
            candidate_structure_sha256=candidate.refolded_structure.sha256,
            reference_target_sha256=upstream.target_structure_ref.sha256,
            design_mask_sha256=candidate.design_mask_source.sha256,
            hotspot_residue_ids=strategy.binding_label_seq_ids,
            definition_version=METRIC_DEFINITION_VERSION,
            metrics=InterfaceMetricValues(
                target_ca_rmsd_angstrom=0,
                hotspot_coverage=0,
                contacted_hotspot_count=0,
                hotspot_count=len(strategy.binding_label_seq_ids),
                binder_contact_coverage=0,
                cdr_dominance=0,
                cdr_utilization=0,
                residue_pair_contact_count=0,
                atom_contact_count=0,
                severe_clash_count=0,
                moderate_clash_count=0,
                hydrogen_bond_count=0,
                salt_bridge_count=0,
                polar_contact_fraction=0,
                interface_bsa_angstrom2=None,
                interface_bsa_missing_reason="identity-placeholder",
            ),
        )
        identity_by_id[candidate.candidate_id] = identity
        cache_path = cache_root / f"{candidate.candidate_id}.json"
        if not cache_path.exists():
            missing.append(candidate)
            continue
        cached = load_model(cache_path, _StructureMetricCacheRecord)
        expected_identity = identity.model_dump(exclude={"metrics"})
        observed_identity = cached.model_dump(exclude={"metrics"})
        if observed_identity != expected_identity:
            raise ManifestStateError(
                f"candidate={candidate.candidate_id} structure metric cache identity 不一致"
            )
        results[candidate.candidate_id] = InterfaceMetricValues.model_validate(cached.metrics)

    recent_errors: list[str] = []

    def persist_progress(*, failed: int = 0) -> None:
        updated_at = datetime.now(UTC)
        completed = len(results)
        total = len(candidates)
        elapsed = max((updated_at - created_at).total_seconds(), 0.0)
        throughput = completed / elapsed * 3600 if completed and elapsed else None
        remaining = total - completed - failed
        running = min(workers, remaining)
        eta = (
            remaining / throughput * 3600
            if throughput is not None and throughput > 0 and remaining > 0
            else (0.0 if remaining == 0 else None)
        )
        atomic_dump_runtime_model(
            ProgressSnapshot(
                stage_id=str(StageId.PILOT_FILTERING),
                phase=phase,
                updated_at=updated_at,
                status="running" if remaining else "phase-succeeded",
                total_tasks=total,
                pending_tasks=remaining - running,
                waiting_tasks=0,
                running_tasks=running,
                succeeded_tasks=completed,
                failed_tasks=failed,
                planned_candidates=total,
                collected_candidates=completed,
                elapsed_seconds=elapsed,
                throughput_candidates_per_hour=throughput,
                estimated_remaining_seconds=eta,
                recent_errors=tuple(recent_errors[-10:]),
            ),
            progress_path,
        )

    workers = min(8, max(os.cpu_count() or 1, 1))
    persist_progress()
    if not missing:
        return results
    with ProcessPoolExecutor(
        max_workers=workers,
    ) as executor:
        futures = {
            executor.submit(
                _candidate_structure_metrics,
                root=root,
                candidate=candidate,
                strategy_hotspots=(strategy_by_id[candidate.strategy_id].binding_label_seq_ids),
                reference_target=reference,
            ): candidate
            for candidate in missing
        }
        for future in as_completed(futures):
            candidate = futures[future]
            try:
                candidate_id, metrics = future.result()
            except Exception as error:
                recent_errors.append(
                    f"{candidate.candidate_id}: {error.__class__.__name__}: {error}"
                )
                persist_progress(failed=1)
                raise
            if not isinstance(metrics, InterfaceMetricValues):
                raise ManifestStateError("structure metric worker 返回了未知类型")
            cache_path = cache_root / f"{candidate_id}.json"
            identity = identity_by_id[candidate_id]
            dump_model(
                identity.model_copy(update={"metrics": metrics}),
                cache_path,
            )
            results[candidate_id] = metrics
            persist_progress()
    return results


def _read_fasta(path: Path) -> str:
    return read_fasta_sequence(path)


def _run_invocation(
    invocation: BackendInvocation,
) -> subprocess.CompletedProcess[str]:
    return run_checked_backend_invocation(invocation)


def _a3m_depth_and_query(path: Path) -> tuple[int, str]:
    records: list[str] = []
    current = -1
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith(">"):
            records.append("")
            current += 1
        elif current < 0:
            raise ManifestStateError("A3M 在首个 header 前出现序列")
        else:
            records[current] += line
    if len(records) < 2 or not records[0]:
        raise ManifestStateError("target required-MSA 必须至少包含 query 和一个同源序列")
    return len(records), records[0]


def _prepare_target_msa(
    *,
    artifacts: Path,
    work: Path,
    target_id: str,
    target_sequence: str,
    providers: tuple[ResolvedProtenixMsaProviderConfig, ...],
    adapter_builder: ComplexAdapterBuilder,
) -> tuple[Path, int, ResolvedProtenixMsaProviderConfig]:
    if not providers:
        raise ManifestStateError("Stage 05 target required-MSA 没有 provider")
    state_path = work / "target-msa" / "selected-provider.json"
    destination = artifacts / "target-msa.a3m"
    target_sha256 = hashlib.sha256(target_sequence.encode("ascii")).hexdigest()

    def publish_copy(source: Path, expected_sha256: str) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            if sha256_file(destination) != expected_sha256:
                raise ManifestStateError("Stage 05 已存在 target MSA checksum 不一致")
            return
        temporary = destination.with_name(f".{destination.name}.tmp-{os.getpid()}")
        with source.open("rb") as source_handle, temporary.open("xb") as destination_handle:
            shutil.copyfileobj(source_handle, destination_handle)
            destination_handle.flush()
            os.fsync(destination_handle.fileno())
        temporary.rename(destination)

    if state_path.exists():
        state = load_model(state_path, _TargetMsaState)
        if state.provider not in providers:
            raise ManifestStateError("Stage 05 cached MSA provider 不在当前 resolved config")
        if state.target_sequence_sha256 != target_sha256:
            raise ManifestStateError("Stage 05 cached MSA target identity 不一致")
        source = (work / state.source_relative_path).resolve()
        if not source.is_relative_to(work.resolve()) or not source.is_file():
            raise ManifestStateError("Stage 05 cached MSA source 路径无效")
        depth, query = _a3m_depth_and_query(source)
        if (
            depth != state.depth
            or query != target_sequence
            or sha256_file(source) != state.a3m_sha256
        ):
            raise ManifestStateError("Stage 05 cached MSA evidence 已损坏")
        publish_copy(source, state.a3m_sha256)
        return destination, state.depth, state.provider

    target = normalize_raw_sequence(target_sequence, target_id=target_id)
    request = StructurePredictionRequest(
        job_name=f"{target_id}-stage05-msa",
        target=target,
        seeds=(101,),
        sample_count=1,
        msa_mode=MsaMode.REMOTE,
        template_mode=TemplateMode.DISABLED,
        parameter_profile=PredictionParameterProfile.MODEL_DEFAULT,
    )
    errors: list[str] = []
    for provider in providers:
        for attempt in range(1, provider.max_attempts + 1):
            provider_root = work / "target-msa" / str(provider.provider) / f"attempt-{attempt:04d}"
            input_json = provider_root / "input.json"
            output_dir = provider_root / "output"
            adapter = adapter_builder(provider, 0)
            adapter.write_input(request, input_json)
            try:
                _run_invocation(
                    adapter.msa_invocation(
                        request,
                        input_json=input_json,
                        output_dir=output_dir,
                    )
                )
                _, source = adapter.remote_msa_artifacts(
                    input_json=input_json,
                    msa_output_dir=output_dir,
                )
                if not source.is_file() or not source.is_relative_to(output_dir.resolve()):
                    raise ManifestStateError("结构后端 MSA path 逃逸当前 work 目录")
                depth, query = _a3m_depth_and_query(source)
                if query != target_sequence:
                    raise ManifestStateError("target MSA query 与 target sequence 不一致")
                source_sha256 = sha256_file(source)
                dump_model(
                    _TargetMsaState(
                        provider=provider,
                        source_relative_path=source.relative_to(work).as_posix(),
                        target_sequence_sha256=target_sha256,
                        a3m_sha256=source_sha256,
                        depth=depth,
                    ),
                    state_path,
                )
                publish_copy(source, source_sha256)
                return destination, depth, provider
            except Exception as error:
                errors.append(f"provider={provider.provider},attempt={attempt}: {error}")
                if attempt < provider.max_attempts:
                    time.sleep(provider.retry_backoff_seconds)
    raise ManifestStateError("Stage 05 target required-MSA 全部失败: " + "; ".join(errors))


def _query_only_a3m(sequence: str, path: Path) -> Path:
    return prepare_query_only_a3m(sequence, path)


def _target_msa_artifact_id(scientific_mode: ScientificMode) -> str:
    return (
        "stage05-target-msa"
        if scientific_mode is ScientificMode.DE_NOVO
        else f"stage05-target-msa-{scientific_mode}"
    )


def _filter_decision(
    *,
    rule_id: str,
    metric_id: str,
    threshold: float | int,
    observed: float | int,
    passed: bool,
) -> FilterDecision:
    return FilterDecision(
        rule_id=rule_id,
        metric_id=metric_id,
        operator="le" if rule_id != "require-zero-severe-clash" else "eq",
        threshold=threshold,
        observed=observed,
        passed=passed,
        reason=f"{metric_id}={observed}; threshold={threshold}",
    )


def _predict_selected_candidates(
    *,
    root: Path,
    artifacts: Path,
    work: Path,
    runtime: Path,
    upstream: _Upstream,
    candidates: tuple[CandidateRecord, ...],
    selected_ids: set[str],
    providers: tuple[ResolvedProtenixMsaProviderConfig, ...],
    prediction_config: ComplexPredictionConfig,
    adapter_builder: ComplexAdapterBuilder,
    devices: tuple[int, ...],
    maximum_attempts: int,
    created_at: datetime,
    scientific_mode: ScientificMode = ScientificMode.DE_NOVO,
    target_condition: TargetStructureCondition | None = None,
) -> tuple[
    tuple[FullTargetPredictionRecord, ...],
    tuple[ArtifactRef, ...],
    tuple[ArtifactRef, ArtifactRef],
]:
    if (scientific_mode is ScientificMode.DE_NOVO) != (target_condition is None):
        raise ManifestStateError("Stage 05 scientific mode/target condition 不一致")
    mode_suffix = str(scientific_mode)
    target_sequence = _read_fasta(upstream.target_sequence_ref.verify(root))
    target_msa, msa_depth, provider = _prepare_target_msa(
        artifacts=artifacts,
        work=work,
        target_id=upstream.strategy_bundle.target_id,
        target_sequence=target_sequence,
        providers=providers,
        adapter_builder=adapter_builder,
    )
    target_unpaired = PrecomputedComplexMsaConfig(
        path=target_msa.resolve(),
        sha256=sha256_file(target_msa),
    )
    remote_feature_providers = tuple(
        source.resolved_providers()[0]
        for source in (
            prediction_config.target_paired_msa,
            prediction_config.binder_msa,
            prediction_config.binder_paired_msa,
        )
        if source.resolved_providers()
    )
    if len(set(remote_feature_providers)) > 1:
        raise ManifestStateError(
            "同一次 complex prediction 的 remote MSA chain 必须使用同一 provider 配置"
        )
    request_provider = (
        remote_feature_providers[0] if remote_feature_providers else provider
    )
    target_templates: ComplexTemplateConfig = prediction_config.target_templates
    target_template_receipt_sha256: str | None = None
    if prediction_config.template_protocol == AFO_TEMPLATE_PROTOCOL_ID:
        protocol_adapter = adapter_builder(request_provider, devices[0])
        if not isinstance(protocol_adapter, OpenFold3Af3JaxAdapter):
            raise ManifestStateError("AFO template protocol 解析到了非 AFO backend")
        protocol_root = work / "afo-template-protocol" / mode_suffix / "target"
        target_templates = prepare_target_template_config(
            adapter=protocol_adapter,
            job_name=f"{upstream.strategy_bundle.target_id}-template"[:128],
            target_sequence=target_sequence,
            target_unpaired_a3m=target_msa,
            target_paired_msa=prediction_config.target_paired_msa,
            output_root=protocol_root,
        )
        target_template_receipt_sha256 = sha256_file(
            protocol_root / "target-template-receipt.json"
        )
    target_msa_ref = _artifact(
        root,
        target_msa,
        artifact_id=_target_msa_artifact_id(scientific_mode),
        role="protenix-required-target-msa",
        file_format="a3m",
    )
    candidate_by_id = {candidate.candidate_id: candidate for candidate in candidates}
    selected_candidates = tuple(
        candidate_by_id[candidate_id] for candidate_id in sorted(selected_ids)
    )
    reference_target = parse_protein_chain(
        upstream.target_structure_ref.verify(root),
        "A",
    )
    selected_candidate_ids = tuple(candidate.candidate_id for candidate in selected_candidates)
    state_path = runtime / (
        "full-target-state.json"
        if scientific_mode is ScientificMode.DE_NOVO
        else f"full-target-state-{mode_suffix}.json"
    )
    progress_path = runtime / (
        "progress.json"
        if scientific_mode is ScientificMode.DE_NOVO
        else f"progress-{mode_suffix}.json"
    )
    journal = TaskEventJournal(
        runtime
        / (
            "task-events.jsonl"
            if scientific_mode is ScientificMode.DE_NOVO
            else f"task-events-{mode_suffix}.jsonl"
        )
    )
    prediction_by_id: dict[str, FullTargetPredictionRecord]
    if state_path.exists():
        state = load_model(state_path, FullTargetExecutionState)
        if state.target_msa_sha256 != sha256_file(target_msa):
            raise ManifestStateError("Stage 05 full-target state MSA identity 不一致")
        if state.selected_candidate_ids != selected_candidate_ids:
            raise ManifestStateError(
                "Stage 05 full-target state selected candidate identity 不一致"
            )
        expected_condition_sha = (
            None if target_condition is None else target_condition.template_data_sha256
        )
        if (
            state.scientific_mode != mode_suffix
            or state.target_condition_sha256 != expected_condition_sha
            or state.template_protocol_id
            != (
                AFO_TEMPLATE_PROTOCOL_ID
                if prediction_config.template_protocol == AFO_TEMPLATE_PROTOCOL_ID
                else None
            )
            or state.target_template_receipt_sha256
            != target_template_receipt_sha256
        ):
            raise ManifestStateError("Stage 05 full-target state scientific mode 不一致")
        tasks = {item.strategy_id: item for item in state.tasks}
        prediction_by_id = {item.candidate_id: item for item in state.predictions}
        for prediction in state.predictions:
            prediction.predicted_structure.verify(root)
            prediction.summary_confidence.verify(root)
            prediction.full_confidence.verify(root)
    else:
        tasks = {
            candidate_id: TaskRecord(
                task_id=f"full-target-{candidate_id}",
                strategy_id=candidate_id,
                requested_candidates=1,
            )
            for candidate_id in selected_candidate_ids
        }
        prediction_by_id = {}

    lock = threading.RLock()
    recent_errors: list[str] = []

    def ordered_tasks() -> tuple[TaskRecord, ...]:
        return tuple(tasks[candidate_id] for candidate_id in selected_candidate_ids)

    def persist(status: str) -> None:
        task_values = ordered_tasks()
        counts = {item: 0 for item in TaskStatus}
        per_device: dict[str, str | None] = {}
        for task in task_values:
            counts[task.status] += 1
            if task.status is TaskStatus.RUNNING:
                assert task.current_device is not None
                per_device[str(task.current_device)] = task.strategy_id
        updated_at = datetime.now(UTC)
        elapsed = max((updated_at - created_at).total_seconds(), 0.0)
        completed = len(prediction_by_id)
        total = len(selected_candidate_ids)
        throughput = completed / elapsed * 3600 if completed and elapsed else None
        remaining = total - completed
        eta = (
            remaining / throughput * 3600
            if throughput is not None and throughput > 0 and remaining > 0
            else (0.0 if remaining == 0 else None)
        )
        snapshot = ProgressSnapshot(
            stage_id=str(StageId.PILOT_FILTERING),
            phase="full-target-prediction",
            updated_at=updated_at,
            status=status,
            total_tasks=total,
            pending_tasks=counts[TaskStatus.PENDING],
            waiting_tasks=counts[TaskStatus.WAITING_RESOURCE],
            running_tasks=counts[TaskStatus.RUNNING],
            succeeded_tasks=counts[TaskStatus.SUCCEEDED],
            failed_tasks=counts[TaskStatus.FAILED],
            planned_candidates=total,
            collected_candidates=completed,
            per_device=per_device,
            elapsed_seconds=elapsed,
            throughput_candidates_per_hour=throughput,
            estimated_remaining_seconds=eta,
            recent_errors=tuple(recent_errors[-10:]),
        )
        atomic_dump_runtime_model(snapshot, progress_path)
        atomic_dump_runtime_model(
            FullTargetExecutionState(
                created_at=created_at,
                updated_at=updated_at,
                target_msa_sha256=sha256_file(target_msa),
                selected_candidate_ids=selected_candidate_ids,
                scientific_mode=cast(
                    Literal["de-novo", "target-conditioned"], mode_suffix
                ),
                target_condition_sha256=(
                    None
                    if target_condition is None
                    else target_condition.template_data_sha256
                ),
                template_protocol_id=(
                    AFO_TEMPLATE_PROTOCOL_ID
                    if prediction_config.template_protocol == AFO_TEMPLATE_PROTOCOL_ID
                    else None
                ),
                target_template_receipt_sha256=target_template_receipt_sha256,
                tasks=task_values,
                predictions=tuple(
                    prediction_by_id[candidate_id]
                    for candidate_id in selected_candidate_ids
                    if candidate_id in prediction_by_id
                ),
                progress=snapshot,
            ),
            state_path,
        )

    def append_event(
        *,
        event_type: str,
        task: TaskRecord,
        message: str,
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

    for candidate_id, task in tuple(tasks.items()):
        if task.status is not TaskStatus.RUNNING:
            continue
        running_attempt = task.attempts[-1]
        error = ErrorInfo(
            code="interrupted-before-resume",
            message="Previous EasyDesign process ended before Protenix task terminal state.",
            retryable=True,
        )
        closed_attempt = running_attempt.model_copy(
            update={
                "status": TaskStatus.FAILED,
                "collected_candidates": 0,
                "ended_at": datetime.now(UTC),
                "return_code": 130,
                "error": error,
            }
        )
        recovered = task.model_copy(
            update={
                "status": TaskStatus.PENDING,
                "attempts": (*task.attempts[:-1], closed_attempt),
                "current_device": None,
            }
        )
        tasks[candidate_id] = recovered
        append_event(
            event_type="task-interrupted",
            task=recovered,
            message="Closed interrupted Protenix attempt; a new attempt is required.",
            attempt_number=running_attempt.attempt_number,
            device=running_attempt.device,
            from_status=TaskStatus.RUNNING,
            to_status=TaskStatus.PENDING,
            error=error,
        )
    for candidate_id, task in tuple(tasks.items()):
        if task.status is TaskStatus.FAILED and candidate_id not in prediction_by_id:
            tasks[candidate_id] = task.model_copy(update={"status": TaskStatus.PENDING})
    persist("running")

    def predict(candidate: CandidateRecord, device: int) -> TaskRecord:
        current = tasks[candidate.candidate_id]
        sequence = candidate.metrics.get("designed_chain_sequence")
        if not isinstance(sequence, str):
            raise ManifestStateError(f"candidate={candidate.candidate_id} 缺少 binder sequence")
        attempts_this_invocation = 0
        while (
            current.status is not TaskStatus.SUCCEEDED
            and attempts_this_invocation < maximum_attempts
        ):
            attempts_this_invocation += 1
            attempt_number = len(current.attempts) + 1
            candidate_root = (
                work
                / (
                    "full-target"
                    if scientific_mode is ScientificMode.DE_NOVO
                    else f"full-target-{mode_suffix}"
                )
                / candidate.candidate_id
                / f"attempt-{attempt_number:04d}"
            )
            target_chain = configured_prediction_chain(
                chain_id="A",
                role="target",
                sequence=target_sequence,
                unpaired_msa=target_unpaired,
                paired_msa=prediction_config.target_paired_msa,
                templates=target_templates,
                query_only_root=candidate_root,
                target_condition=target_condition,
            )
            binder_templates = prediction_config.binder_templates
            if prediction_config.template_protocol == AFO_TEMPLATE_PROTOCOL_ID:
                binder_templates = prepare_binder_template_config(
                    source_complex=candidate.original_structure.verify(root),
                    binder_sequence=sequence,
                    output_root=candidate_root / "binder-template-protocol",
                )
            binder_chain = configured_prediction_chain(
                chain_id="B",
                role="binder",
                sequence=sequence,
                unpaired_msa=prediction_config.binder_msa,
                paired_msa=prediction_config.binder_paired_msa,
                templates=binder_templates,
                query_only_root=candidate_root,
                target_condition=target_condition,
            )
            uses_templates = any(
                chain.template_mode is TemplateMode.PRECOMPUTED
                for chain in (target_chain, binder_chain)
            )
            request = ComplexStructurePredictionRequest(
                job_name=candidate.candidate_id,
                chains=(target_chain, binder_chain),
                seeds=(101,),
                sample_count=1,
                msa_mode=MsaMode.DISABLED,
                scientific_mode=scientific_mode,
                template_mode=(
                    TemplateMode.PRECOMPUTED
                    if uses_templates
                    else TemplateMode.DISABLED
                ),
                target_structure_condition=target_condition,
            )
            adapter = adapter_builder(request_provider, device)
            input_path = adapter.write_input(
                request,
                candidate_root / "input.json",
            )
            if prediction_config.template_protocol == AFO_TEMPLATE_PROTOCOL_ID:
                audit_final_input(
                    input_json=input_path,
                    output_path=candidate_root / "input-audit.json",
                )
            remote_invocation: BackendInvocation | None = None
            prediction_input = input_path
            if any(
                mode is MsaMode.REMOTE
                for chain in request.chains
                for mode in (
                    chain.resolved_unpaired_msa_mode(request.msa_mode),
                    chain.resolved_paired_msa_mode(request.msa_mode),
                )
            ):
                msa_output = candidate_root / "msa-output"
                remote_invocation = adapter.msa_invocation(
                    request,
                    input_json=input_path,
                    output_dir=msa_output,
                )
                prediction_input = adapter.updated_msa_input_path(
                    input_path,
                    msa_output,
                )
            output = candidate_root / "output"
            invocation = adapter.prediction_invocation(
                request,
                input_json=prediction_input,
                output_dir=output,
            )
            command_sha256 = hashlib.sha256(
                json.dumps(
                    (
                        remote_invocation.argv if remote_invocation is not None else (),
                        invocation.argv,
                    ),
                    ensure_ascii=True,
                    separators=(",", ":"),
                ).encode("utf-8")
            ).hexdigest()
            started_at = datetime.now(UTC)
            running_attempt = TaskAttemptRecord(
                attempt_number=attempt_number,
                status=TaskStatus.RUNNING,
                requested_candidates=1,
                device=device,
                command_sha256=command_sha256,
                output_relative_path=output.relative_to(root).as_posix(),
                started_at=started_at,
            )
            with lock:
                current = current.model_copy(
                    update={
                        "status": TaskStatus.RUNNING,
                        "attempts": (*current.attempts, running_attempt),
                        "current_device": device,
                    }
                )
                tasks[candidate.candidate_id] = current
                append_event(
                    event_type="task-started",
                    task=current,
                    message="Started structure-prediction full-target seed 101.",
                    attempt_number=attempt_number,
                    device=device,
                    from_status=TaskStatus.PENDING,
                    to_status=TaskStatus.RUNNING,
                )
                persist("running")
            error: ErrorInfo | None = None
            return_code = 1
            record: FullTargetPredictionRecord | None = None
            try:
                if remote_invocation is not None:
                    _run_invocation(remote_invocation)
                    if not prediction_input.is_file():
                        raise ManifestStateError(
                            "complex remote MSA 没有生成 updated prediction input"
                        )
                completed = _run_invocation(invocation)
                return_code = completed.returncode
                product = adapter.collect_products(request, output_dir=output)[0]
                if product.full_confidence_path is None or product.full_confidence_sha256 is None:
                    raise ManifestStateError("Stage 05 structure backend 没有 full confidence")
                structure_ref = _artifact(
                    root,
                    product.structure_path,
                    artifact_id=(
                        f"{candidate.candidate_id}-full-target-structure-{mode_suffix}"
                    ),
                    role="stage05-full-target-prediction",
                    file_format="mmcif",
                )
                summary_ref = _artifact(
                    root,
                    product.confidence_path,
                    artifact_id=f"{candidate.candidate_id}-full-target-summary-{mode_suffix}",
                    role="structure-summary-confidence",
                    file_format="json",
                )
                full_ref = _artifact(
                    root,
                    product.full_confidence_path,
                    artifact_id=(
                        f"{candidate.candidate_id}-full-target-confidence-{mode_suffix}"
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
                decisions = (
                    _filter_decision(
                        rule_id="require-binder-pose-rmsd",
                        metric_id="binder-pose-rmsd",
                        threshold=3.0,
                        observed=structure.binder_pose_rmsd_angstrom,
                        passed=structure.binder_pose_rmsd_angstrom <= 3.0,
                    ),
                    _filter_decision(
                        rule_id="require-target-ca-rmsd",
                        metric_id="target-ca-rmsd",
                        threshold=3.0,
                        observed=structure.target_ca_rmsd_angstrom,
                        passed=structure.target_ca_rmsd_angstrom <= 3.0,
                    ),
                    _filter_decision(
                        rule_id="require-zero-severe-clash",
                        metric_id="severe-clash-count",
                        threshold=0,
                        observed=structure.severe_clash_count,
                        passed=structure.severe_clash_count == 0,
                    ),
                    _filter_decision(
                        rule_id="limit-moderate-clash",
                        metric_id="moderate-clash-count",
                        threshold=3,
                        observed=structure.moderate_clash_count,
                        passed=structure.moderate_clash_count <= 3,
                    ),
                )
                reference_pass = (
                    confidence.pairwise_iptm >= 0.50
                    or confidence.minimum_interface_pae_angstrom <= 15.0
                    or confidence.binder_ptm >= 0.70
                )
                record = FullTargetPredictionRecord(
                    candidate_id=candidate.candidate_id,
                    strategy_id=candidate.strategy_id,
                    scientific_mode=cast(
                        Literal["de-novo", "target-conditioned"], mode_suffix
                    ),
                    template_mode=cast(
                        Literal["disabled", "precomputed"],
                        str(request.template_mode),
                    ),
                    screening_profile_id=(
                        "nanobody-filter-standard-v1.7"
                        if scientific_mode is ScientificMode.DE_NOVO
                        else "target-conditioned-evidence-v1"
                    ),
                    target_condition_sha256=(
                        None
                        if target_condition is None
                        else target_condition.template_data_sha256
                    ),
                    template_protocol_id=(
                        AFO_TEMPLATE_PROTOCOL_ID
                        if prediction_config.template_protocol
                        == AFO_TEMPLATE_PROTOCOL_ID
                        else None
                    ),
                    target_template_receipt_sha256=(
                        target_template_receipt_sha256
                    ),
                    target_condition_source_origin=(
                        None if target_condition is None else target_condition.source_origin
                    ),
                    target_condition_self_conditioned=(
                        False
                        if target_condition is None
                        else target_condition.is_self_conditioned_for(
                            product.backend_name
                        )
                    ),
                    backend_identity=product.backend_identity,
                    model_identity=product.model_identity,
                    confidence_metric_definition_version=(
                        confidence.metric_definition_version
                    ),
                    raw_checkpoint_sha256=(
                        str(product.native_metrics["raw_checkpoint_sha256"])
                        if isinstance(
                            product.native_metrics.get("raw_checkpoint_sha256"), str
                        )
                        else None
                    ),
                    converted_weight_sha256=(
                        str(product.native_metrics["converted_weight_sha256"])
                        if isinstance(
                            product.native_metrics.get("converted_weight_sha256"), str
                        )
                        else None
                    ),
                    wheel_sha256=(
                        str(product.native_metrics["wheel_sha256"])
                        if isinstance(product.native_metrics.get("wheel_sha256"), str)
                        else None
                    ),
                    runner_commit=(
                        str(product.native_metrics["runner_commit"])
                        if isinstance(product.native_metrics.get("runner_commit"), str)
                        else None
                    ),
                    release_identity=prediction_release_identity(product),
                    msa_provider=(
                        str(product.native_metrics["msa_provider"])
                        if isinstance(product.native_metrics.get("msa_provider"), str)
                        else "precomputed"
                    ),
                    msa_endpoint=(
                        str(product.native_metrics["msa_endpoint"])
                        if isinstance(product.native_metrics.get("msa_endpoint"), str)
                        else None
                    ),
                    target_unpaired_msa_mode=cast(
                        Literal["disabled", "remote", "precomputed"],
                        product.native_metrics.get(
                            "target_unpaired_msa_mode",
                            request.require_role("target")
                            .resolved_unpaired_msa_mode(request.msa_mode)
                            .value,
                        ),
                    ),
                    target_paired_msa_mode=cast(
                        Literal["disabled", "remote", "precomputed"],
                        product.native_metrics.get(
                            "target_paired_msa_mode",
                            request.require_role("target")
                            .resolved_paired_msa_mode(request.msa_mode)
                            .value,
                        ),
                    ),
                    binder_unpaired_msa_mode=cast(
                        Literal["disabled", "remote", "precomputed"],
                        product.native_metrics.get(
                            "binder_unpaired_msa_mode",
                            request.require_role("binder")
                            .resolved_unpaired_msa_mode(request.msa_mode)
                            .value,
                        ),
                    ),
                    binder_paired_msa_mode=cast(
                        Literal["disabled", "remote", "precomputed"],
                        product.native_metrics.get(
                            "binder_paired_msa_mode",
                            request.require_role("binder")
                            .resolved_paired_msa_mode(request.msa_mode)
                            .value,
                        ),
                    ),
                    target_template_data_sha256=(
                        str(product.native_metrics["target_template_data_sha256"])
                        if isinstance(
                            product.native_metrics.get("target_template_data_sha256"),
                            str,
                        )
                        else request.require_role("target").template_data_sha256
                    ),
                    binder_template_data_sha256=(
                        str(product.native_metrics["binder_template_data_sha256"])
                        if isinstance(
                            product.native_metrics.get("binder_template_data_sha256"),
                            str,
                        )
                        else request.require_role("binder").template_data_sha256
                    ),
                    predicted_structure=structure_ref,
                    summary_confidence=summary_ref,
                    full_confidence=full_ref,
                    pairwise_iptm=confidence.pairwise_iptm,
                    minimum_interface_pae_angstrom=(confidence.minimum_interface_pae_angstrom),
                    binder_ptm=confidence.binder_ptm,
                    binder_pose_rmsd_angstrom=structure.binder_pose_rmsd_angstrom,
                    target_ca_rmsd_angstrom=structure.target_ca_rmsd_angstrom,
                    severe_clash_count=structure.severe_clash_count,
                    moderate_clash_count=structure.moderate_clash_count,
                    structure_gate_decisions=decisions,
                    structure_gate_pass=all(item.passed for item in decisions),
                    confidence_reference_pass=reference_pass,
                    confidence_label=(
                        "reference-supported" if reference_pass else "low-confidence"
                    ),
                )
            except Exception as exception:
                error = ErrorInfo(
                    code="structure-full-target-failed",
                    message=str(exception)[:4096] or exception.__class__.__name__,
                    retryable=True,
                )
            ended_at = datetime.now(UTC)
            succeeded = record is not None and return_code == 0
            final_attempt = running_attempt.model_copy(
                update={
                    "status": (TaskStatus.SUCCEEDED if succeeded else TaskStatus.FAILED),
                    "collected_candidates": 1 if succeeded else 0,
                    "ended_at": ended_at,
                    "return_code": return_code,
                    "error": None if succeeded else error,
                }
            )
            next_status = TaskStatus.SUCCEEDED if succeeded else TaskStatus.PENDING
            with lock:
                current = current.model_copy(
                    update={
                        "status": next_status,
                        "collected_candidates": 1 if succeeded else 0,
                        "candidate_ids": ((candidate.candidate_id,) if succeeded else ()),
                        "attempts": (*current.attempts[:-1], final_attempt),
                        "current_device": None,
                    }
                )
                tasks[candidate.candidate_id] = current
                if record is not None:
                    prediction_by_id[candidate.candidate_id] = record
                if error is not None:
                    recent_errors.append(f"{current.task_id}: {error.code}: {error.message}")
                append_event(
                    event_type=("task-succeeded" if succeeded else "task-attempt-failed"),
                    task=current,
                    message=(
                        "Collected full-target prediction."
                        if succeeded
                        else "Protenix full-target attempt failed."
                    ),
                    attempt_number=attempt_number,
                    device=device,
                    from_status=TaskStatus.RUNNING,
                    to_status=next_status,
                    error=error,
                )
                persist("running")
            if succeeded:
                return current
        if current.status is not TaskStatus.SUCCEEDED:
            exhausted = ErrorInfo(
                code="task-attempt-budget-exhausted",
                message=(
                    f"Protenix task exhausted {maximum_attempts} attempts without "
                    "a complete prediction."
                ),
                retryable=True,
            )
            with lock:
                current = current.model_copy(update={"status": TaskStatus.FAILED})
                tasks[candidate.candidate_id] = current
                recent_errors.append(f"{current.task_id}: {exhausted.code}: {exhausted.message}")
                append_event(
                    event_type="task-incomplete",
                    task=current,
                    message=exhausted.message,
                    from_status=TaskStatus.PENDING,
                    to_status=TaskStatus.FAILED,
                    error=exhausted,
                )
                persist("incomplete")
        return current

    scheduled = tuple(
        candidate
        for candidate in selected_candidates
        if tasks[candidate.candidate_id].status is not TaskStatus.SUCCEEDED
    )
    execute_on_devices(
        scheduled,
        devices=devices,
        worker=predict,
    )
    if any(task.status is not TaskStatus.SUCCEEDED for task in tasks.values()):
        persist("incomplete")
        raise ManifestStateError(
            "Stage 05 Protenix full-target tasks 未全部完成，可使用 runs resume"
        )
    persist("phase-succeeded")
    records = tuple(prediction_by_id[candidate_id] for candidate_id in selected_candidate_ids)
    artifacts_out = tuple(
        artifact
        for record in records
        for artifact in (
            record.predicted_structure,
            record.summary_confidence,
            record.full_confidence,
        )
    )
    msa_evidence_path = artifacts / (
        "target-msa-evidence.json"
        if scientific_mode is ScientificMode.DE_NOVO
        else f"target-msa-evidence-{mode_suffix}.json"
    )
    msa_evidence = {
        "schema_version": "0.1",
        "provider": str(provider.provider),
        "endpoint": provider.endpoint,
        "depth": msa_depth,
        "target_sequence_sha256": hashlib.sha256(target_sequence.encode("ascii")).hexdigest(),
        "a3m_sha256": sha256_file(target_msa),
        "binder_msa": str(prediction_config.binder_msa.mode),
        "target_paired_msa": str(prediction_config.target_paired_msa.mode),
        "binder_paired_msa": str(prediction_config.binder_paired_msa.mode),
        "no_msa_fallback": False,
        "scientific_mode": mode_suffix,
        "target_templates": prediction_config.target_templates.mode,
        "binder_templates": prediction_config.binder_templates.mode,
        "target_condition_sha256": (
            None if target_condition is None else target_condition.template_data_sha256
        ),
    }
    serialized_msa_evidence = json.dumps(msa_evidence, indent=2, sort_keys=True) + "\n"
    if msa_evidence_path.exists():
        if msa_evidence_path.read_text(encoding="utf-8") != serialized_msa_evidence:
            raise ManifestStateError("Stage 05 MSA evidence 与恢复状态不一致")
    else:
        msa_evidence_path.write_text(
            serialized_msa_evidence,
            encoding="utf-8",
        )
    evidence_ref = _artifact(
        root,
        msa_evidence_path,
        artifact_id=f"stage05-msa-evidence-{mode_suffix}",
        role="full-target-msa-provenance",
        file_format="json",
    )
    return records, artifacts_out, (target_msa_ref, evidence_ref)


def _expand_candidates(
    *,
    root: Path,
    attempt_root: Path,
    runtime_root: Path,
    upstream: _Upstream,
    selected_strategy_ids: tuple[str, ...],
    total_per_strategy: int,
    adapter: BoltzGenGenerationAdapter,
    devices: tuple[int, ...],
    maximum_attempts: int,
    created_at: datetime,
) -> tuple[CandidateRecord, ...]:
    by_strategy: dict[str, list[CandidateRecord]] = {}
    for candidate in upstream.candidate_index.candidates:
        if candidate.strategy_id in selected_strategy_ids:
            by_strategy.setdefault(candidate.strategy_id, []).append(candidate)
    for strategy_id in selected_strategy_ids:
        existing_count = len(by_strategy.get(strategy_id, ()))
        if existing_count >= total_per_strategy:
            raise ManifestStateError(f"strategy={strategy_id} expansion total 必须大于 pilot count")

    state_path = runtime_root / "expansion-state.json"
    progress_path = runtime_root / "progress.json"
    journal = TaskEventJournal(runtime_root / "task-events.jsonl")
    if state_path.exists():
        state = load_model(state_path, ExpansionExecutionState)
        if state.strategy_bundle_sha256 != upstream.strategy_bundle_ref.sha256:
            raise ManifestStateError("Stage 05 expansion state 与 StrategyBundle 不一致")
        tasks = {item.strategy_id: item for item in state.tasks}
        new_candidates = list(state.new_candidates)
        if set(tasks) != set(selected_strategy_ids):
            raise ManifestStateError("Stage 05 expansion state strategy 集合不一致")
        for candidate in new_candidates:
            candidate.original_structure.verify(root)
            candidate.refolded_structure.verify(root)
            if candidate.design_mask_source is None:
                raise ManifestStateError("Stage 05 expansion candidate 缺少 design mask")
            candidate.design_mask_source.verify(root)
    else:
        tasks = {
            strategy_id: TaskRecord(
                task_id=f"expand-{strategy_id}",
                strategy_id=strategy_id,
                requested_candidates=(total_per_strategy - len(by_strategy[strategy_id])),
            )
            for strategy_id in selected_strategy_ids
        }
        new_candidates = []

    lock = threading.RLock()
    recent_errors: list[str] = []

    def ordered_tasks() -> tuple[TaskRecord, ...]:
        return tuple(tasks[strategy_id] for strategy_id in selected_strategy_ids)

    def persist(status: str) -> None:
        task_values = ordered_tasks()
        counts = {item: 0 for item in TaskStatus}
        per_device: dict[str, str | None] = {}
        for task in task_values:
            counts[task.status] += 1
            if task.status is TaskStatus.RUNNING:
                assert task.current_device is not None
                per_device[str(task.current_device)] = task.strategy_id
        updated_at = datetime.now(UTC)
        elapsed = max((updated_at - created_at).total_seconds(), 0.0)
        planned = sum(item.requested_candidates for item in task_values)
        collected = sum(item.collected_candidates for item in task_values)
        throughput = collected / elapsed * 3600 if collected and elapsed else None
        remaining = planned - collected
        eta = (
            remaining / throughput * 3600
            if throughput is not None and throughput > 0 and remaining > 0
            else (0.0 if remaining == 0 else None)
        )
        snapshot = ProgressSnapshot(
            stage_id=str(StageId.PILOT_FILTERING),
            phase="expansion-generation",
            updated_at=updated_at,
            status=status,
            total_tasks=len(task_values),
            pending_tasks=counts[TaskStatus.PENDING],
            waiting_tasks=counts[TaskStatus.WAITING_RESOURCE],
            running_tasks=counts[TaskStatus.RUNNING],
            succeeded_tasks=counts[TaskStatus.SUCCEEDED],
            failed_tasks=counts[TaskStatus.FAILED],
            planned_candidates=planned,
            collected_candidates=collected,
            per_device=per_device,
            elapsed_seconds=elapsed,
            throughput_candidates_per_hour=throughput,
            estimated_remaining_seconds=eta,
            recent_errors=tuple(recent_errors[-10:]),
        )
        atomic_dump_runtime_model(snapshot, progress_path)
        atomic_dump_runtime_model(
            ExpansionExecutionState(
                created_at=created_at,
                updated_at=updated_at,
                strategy_bundle_sha256=upstream.strategy_bundle_ref.sha256,
                tasks=task_values,
                new_candidates=tuple(new_candidates),
                progress=snapshot,
            ),
            state_path,
        )

    def apply_transition(transition: TaskTransition) -> None:
        with lock:
            tasks[transition.task.strategy_id] = transition.task
            new_candidates.extend(transition.new_candidates)
            if transition.error is not None:
                recent_errors.append(
                    f"{transition.task.task_id}: {transition.error.code}: "
                    f"{transition.error.message}"
                )
            journal.append(
                TaskEvent(
                    sequence=journal.next_sequence,
                    occurred_at=datetime.now(UTC),
                    event_type=transition.event_type,
                    task_id=transition.task.task_id,
                    strategy_id=transition.task.strategy_id,
                    task_attempt_number=transition.attempt_number,
                    device=transition.device,
                    from_status=transition.from_status,
                    to_status=transition.to_status,
                    message=transition.message,
                    error=transition.error,
                )
            )
            persist("incomplete" if transition.event_type == "task-incomplete" else "running")

    for strategy_id, task in tuple(tasks.items()):
        transition = recover_interrupted_boltzgen_task(
            root=root,
            task=task,
            stage_attempt_id="attempt-0001",
            producer_stage=str(StageId.PILOT_FILTERING),
            ordinal_offset=len(by_strategy[strategy_id]),
        )
        if transition is not None:
            apply_transition(transition)
    for strategy_id, task in tuple(tasks.items()):
        if (
            task.status is TaskStatus.FAILED
            and task.collected_candidates < task.requested_candidates
        ):
            tasks[strategy_id] = task.model_copy(update={"status": TaskStatus.PENDING})
    persist("running")

    def expand(strategy_id: str, device: int) -> TaskRecord:
        task = tasks[strategy_id]
        specification = upstream.stage03.require_output(f"strategy-{strategy_id}").verify(root)
        return execute_boltzgen_candidate_task(
            root=root,
            task=task,
            design_specification=specification,
            task_root=attempt_root / "tasks" / task.task_id,
            stage_attempt_id="attempt-0001",
            producer_stage=str(StageId.PILOT_FILTERING),
            adapter=adapter,
            device=device,
            maximum_attempts_this_invocation=maximum_attempts,
            on_transition=apply_transition,
            ordinal_offset=len(by_strategy[strategy_id]),
        )

    scheduled = tuple(
        strategy_id
        for strategy_id in selected_strategy_ids
        if tasks[strategy_id].status is not TaskStatus.SUCCEEDED
    )
    results = execute_on_devices(
        scheduled,
        devices=devices,
        worker=expand,
    )
    for result in results:
        tasks[scheduled[result.input_index]] = result.result
    if any(task.status is not TaskStatus.SUCCEEDED for task in tasks.values()):
        persist("incomplete")
        raise ManifestStateError("Stage 05 expansion tasks 未全部完成，可使用 runs resume")
    persist("phase-succeeded")
    combined = tuple(
        candidate
        for strategy_id in selected_strategy_ids
        for candidate in (
            *sorted(
                by_strategy[strategy_id],
                key=lambda item: item.ordinal_within_strategy,
            ),
            *sorted(
                (item for item in new_candidates if item.strategy_id == strategy_id),
                key=lambda item: item.ordinal_within_strategy,
            ),
        )
    )
    return combined


def _publish_stage05(
    *,
    root: Path,
    upstream: _Upstream,
    resolved: ResolvedRunConfig,
    artifacts: Path,
    created_at: datetime,
    output_refs: tuple[ArtifactRef, ...],
    bundle_path: Path,
    warnings: tuple[str, ...],
    scientific_stop: bool,
    filter_profile: str,
) -> Stage05Execution:
    completed_at = max(datetime.now(UTC), created_at + timedelta(microseconds=1))
    attempt = Attempt(
        attempt_id="attempt-0001",
        status=ExecutionStatus.SUCCEEDED,
        created_at=created_at,
        started_at=created_at,
        ended_at=completed_at,
        backend_name="easydesign-filtering",
        backend_version=filter_profile,
        executor_name="local-multi-gpu",
    )
    attempt_path = artifacts.parent / "attempt-manifest.json"
    if attempt_path.exists():
        observed_attempt = load_model(attempt_path, Attempt)
        if observed_attempt.model_dump(
            exclude={"created_at", "started_at", "ended_at"}
        ) != attempt.model_dump(exclude={"created_at", "started_at", "ended_at"}):
            raise ManifestStateError(
                "Stage 05 partial publish attempt manifest 与当前执行不一致"
            )
        attempt = observed_attempt
        created_at = attempt.created_at
        assert attempt.ended_at is not None
        completed_at = attempt.ended_at
    else:
        dump_model(attempt, attempt_path)
    stage_manifest = StageManifest(
        stage_id=StageId.PILOT_FILTERING,
        contract_version=(
            "0.2"
            if filter_profile
            in {
                "nanobody-filter-standard-v1.6",
                "nanobody-filter-standard-v1.7",
            }
            else "0.1"
        ),
        status=ExecutionStatus.SUCCEEDED,
        created_at=created_at,
        completed_at=completed_at,
        input_artifacts=(
            upstream.target_structure_ref,
            upstream.target_sequence_ref,
            upstream.strategy_bundle_ref,
            upstream.pilot_bundle_ref,
            upstream.candidate_index_ref,
        ),
        output_artifacts=output_refs,
        attempts=(attempt,),
        selected_attempt_id="attempt-0001",
        warnings=warnings,
    )
    stage_manifest.validate_inputs_declared_by(
        (upstream.stage01, upstream.stage03, upstream.stage04)
    )
    stage_manifest_path = artifacts / "stage-manifest.json"
    if stage_manifest_path.exists():
        observed_stage = load_model(stage_manifest_path, StageManifest)
        if observed_stage != stage_manifest:
            raise ManifestStateError(
                "Stage 05 partial publish stage manifest 与当前结果不一致"
            )
        stage_manifest = observed_stage
    else:
        dump_model(stage_manifest, stage_manifest_path)
    stage_ref = _artifact(
        root,
        stage_manifest_path,
        artifact_id="stage-05-manifest",
        role="stage-manifest",
        file_format="json",
    )
    timestamp = max(
        completed_at,
        upstream.run.updated_at + timedelta(microseconds=1),
    )
    terminal = resolved.stop_after_stage == 5 or scientific_stop
    next_run = upstream.run.next_revision(
        updated_at=timestamp,
        status=ExecutionStatus.SUCCEEDED if terminal else ExecutionStatus.RUNNING,
        completed_at=timestamp if terminal else None,
        stage_manifest_refs=(*upstream.run.stage_manifest_refs, stage_ref),
        clear_workflow_state=True,
    )
    run_manifest_path = root / "manifests" / f"run-manifest.v{next_run.revision:04d}.json"
    if run_manifest_path.exists():
        observed_run = load_model(run_manifest_path, RunManifest)
        if observed_run != next_run:
            raise ManifestStateError(
                "Stage 05 partial publish run manifest 与当前结果不一致"
            )
        next_run = observed_run
    else:
        dump_model(next_run, run_manifest_path)
    _atomic_text(run_manifest_path.name + "\n", root / "manifests" / "LATEST")
    use_v1_6 = filter_profile in {
        "nanobody-filter-standard-v1.6",
        "nanobody-filter-standard-v1.7",
    }
    bundle_status: str
    if use_v1_6:
        bundle_v1_6 = load_model(bundle_path, Stage05BundleV0_2)
        bundle_status = bundle_v1_6.status
        winner_strategy_id = None
        promoted_strategy_ids = bundle_v1_6.promoted_strategy_ids
    else:
        bundle_v1_5 = load_model(bundle_path, Stage05Bundle)
        bundle_status = bundle_v1_5.status
        winner_strategy_id = bundle_v1_5.winner_strategy_id
        promoted_strategy_ids = ()
    upsert_run_index_entries(
        root.parents[1],
        (
            RunIndexEntry(
                category="project-run",
                path=root.relative_to(root.parents[1]).as_posix(),
                layout_version="1",
                status="succeeded" if terminal else "running",
                project_id=upstream.run.project_id,
                run_id=upstream.run.run_id,
                notes=(f"Stage 05 status={bundle_status}",),
            ),
        ),
        generated_at=timestamp,
    )
    return Stage05Execution(
        status=bundle_status,
        run_root=root,
        run_manifest=run_manifest_path,
        stage_manifest=stage_manifest_path,
        stage05_bundle=bundle_path,
        selected_strategy_id=winner_strategy_id,
        promoted_strategy_ids=promoted_strategy_ids,
    )


def execute_stage05(
    *,
    run_root: Path,
    boltzgen_adapter: BoltzGenGenerationAdapter,
    prediction_adapter_builder: ComplexAdapterBuilder,
    gpu_probe: NvidiaSmiProbe | None = None,
    executed_at: datetime | None = None,
) -> Stage05Execution:
    """Execute v1.5 pilot filter; scientific stops are successful terminal outputs."""

    root = run_root.resolve()
    upstream = _load_upstream(root)
    if upstream.run.status is not ExecutionStatus.RUNNING:
        raise ManifestStateError("Stage 05 只能写入 running run")
    if any(
        item.producer_stage == str(StageId.PILOT_FILTERING)
        for item in upstream.run.stage_manifest_refs
    ):
        raise ManifestStateError("Stage 05 已发布，禁止覆盖")
    resolved, _ = load_resolved_run_config(root)
    config = resolved.user_config.stage05
    stage04_config = resolved.user_config.stage04
    if config is None or stage04_config is None:
        raise ManifestStateError("run config 缺少 Stage 04/05")
    filter_profile = _stage05_filter_profile(config)
    use_v1_6 = filter_profile in {
        "nanobody-filter-standard-v1.6",
        "nanobody-filter-standard-v1.7",
    }
    now = datetime.now(UTC) if executed_at is None else executed_at
    attempt_root = root / str(StageId.PILOT_FILTERING) / "attempt-0001"
    artifacts = attempt_root / "artifacts"
    work = attempt_root / "work"
    runtime = attempt_root / "runtime"
    artifacts.mkdir(parents=True, exist_ok=True)
    runtime.mkdir(parents=True, exist_ok=True)
    profile_path = artifacts / "filter-profile.yaml"
    if not profile_path.exists():
        profile_path.write_bytes(_profile_bytes(filter_profile))
    profile_ref = _artifact(
        root,
        profile_path,
        artifact_id="nanobody-filter-profile",
        role="versioned-filter-profile",
        file_format="yaml",
    )
    pilot_report_path = artifacts / "pilot-filter-report.json"
    pilot_report: PilotFilterReport | PilotFilterReportV1_6
    if pilot_report_path.exists():
        if use_v1_6:
            pilot_report = load_model(pilot_report_path, PilotFilterReportV1_6)
        else:
            pilot_report = load_model(pilot_report_path, PilotFilterReport)
    else:
        pilot_metrics = _batch_structure_metrics(
            root=root,
            upstream=upstream,
            candidates=upstream.candidate_index.candidates,
            runtime_root=runtime,
            phase="pilot-structure-metrics",
            created_at=now,
        )
        if use_v1_6:
            pilot_report = evaluate_pilot_candidates_v1_6(
                candidates=upstream.candidate_index.candidates,
                structural_metrics=pilot_metrics,
                candidate_index_sha256=upstream.candidate_index_ref.sha256,
                maximum_tier_a_strategies=config.maximum_tier_a_strategies,
                generated_at=now,
                profile_id=cast(
                    Literal[
                        "nanobody-filter-standard-v1.6",
                        "nanobody-filter-standard-v1.7",
                    ],
                    filter_profile,
                ),
                profile_sha256=(
                    PROFILE_SOURCE_SHA256_V1_7
                    if filter_profile == "nanobody-filter-standard-v1.7"
                    else PROFILE_SOURCE_SHA256_V1_6
                ),
            )
        else:
            pilot_report = evaluate_pilot_candidates(
                candidates=upstream.candidate_index.candidates,
                structural_metrics=pilot_metrics,
                profile_sha256=PROFILE_SOURCE_SHA256,
                candidate_index_sha256=upstream.candidate_index_ref.sha256,
                maximum_tier_a_strategies=config.maximum_tier_a_strategies,
                generated_at=now,
            )
        dump_model(pilot_report, pilot_report_path)
    pilot_report_ref = _artifact(
        root,
        pilot_report_path,
        artifact_id="pilot-filter-report",
        role="pilot-filter-audit",
        file_format="json",
    )
    if pilot_report.status == "stopped-no-tier-a":
        stop_path = artifacts / "scientific-stop.json"
        stop = ScientificStop(
            stage_id=str(StageId.PILOT_FILTERING),
            code=ScientificStopCode.NO_TIER_A,
            occurred_at=now,
            message=(
                f"No Tier A strategy satisfied {filter_profile}."
            ),
            evidence_artifact_sha256=(pilot_report_ref.sha256,),
        )
        if stop_path.exists():
            observed_stop = load_model(stop_path, ScientificStop)
            if (
                observed_stop.code is not ScientificStopCode.NO_TIER_A
                or observed_stop.evidence_artifact_sha256 != (pilot_report_ref.sha256,)
            ):
                raise ManifestStateError("Stage 05 scientific stop 与当前 evidence 不一致")
            stop = observed_stop
        else:
            dump_model(stop, stop_path)
        tier_stop_ref = _artifact(
            root,
            stop_path,
            artifact_id="stage05-scientific-stop",
            role="scientific-negative-result",
            file_format="json",
        )
        progress_ref, events_ref = _publish_final_execution_evidence(
            root=root,
            artifacts=artifacts,
            runtime=runtime,
            status="scientific-stop",
            completed_at=datetime.now(UTC),
        )
        bundle_path = artifacts / "stage05-bundle.json"
        stop_bundle: Stage05Bundle | Stage05BundleV0_2
        if use_v1_6:
            stop_bundle = Stage05BundleV0_2(
                generated_at=now,
                pilot_bundle=upstream.pilot_bundle_ref,
                strategy_bundle=upstream.strategy_bundle_ref,
                filter_profile=profile_ref,
                pilot_filter_report=pilot_report_ref,
                progress_final=progress_ref,
                task_events=events_ref,
                scientific_stop=tier_stop_ref,
                promoted_strategy_ids=(),
                promotion_rank=(),
                status="stopped-no-tier-a",
            )
        else:
            stop_bundle = Stage05Bundle(
                generated_at=now,
                pilot_bundle=upstream.pilot_bundle_ref,
                strategy_bundle=upstream.strategy_bundle_ref,
                filter_profile=profile_ref,
                pilot_filter_report=pilot_report_ref,
                progress_final=progress_ref,
                task_events=events_ref,
                scientific_stop=tier_stop_ref,
                status="stopped-no-tier-a",
            )
        if bundle_path.exists():
            observed_bundle: Stage05Bundle | Stage05BundleV0_2
            if use_v1_6:
                observed_bundle = load_model(bundle_path, Stage05BundleV0_2)
            else:
                observed_bundle = load_model(bundle_path, Stage05Bundle)
            if (
                observed_bundle.status != stop_bundle.status
                or observed_bundle.pilot_filter_report != pilot_report_ref
                or observed_bundle.scientific_stop != tier_stop_ref
            ):
                raise ManifestStateError("Stage 05 Bundle 与当前 scientific stop 不一致")
            stop_bundle = observed_bundle
        else:
            dump_model(stop_bundle, bundle_path)
        bundle_ref = _artifact(
            root,
            bundle_path,
            artifact_id="stage05-bundle",
            role="stage06-strategy-input-or-stop",
            file_format="json",
        )
        return _with_review_dashboard(
            _publish_stage05(
                root=root,
                upstream=upstream,
                resolved=resolved,
                artifacts=artifacts,
                created_at=now,
                output_refs=(
                    profile_ref,
                    pilot_report_ref,
                    progress_ref,
                    events_ref,
                    tier_stop_ref,
                    bundle_ref,
                ),
                bundle_path=bundle_path,
                warnings=(
                    "Scientific stop: stopped-no-tier-a.",
                    "Software execution succeeded; no scale strategy was published.",
                ),
                scientific_stop=True,
                filter_profile=filter_profile,
            ),
            generated_at=now,
        )

    pilot_plan = load_model(upstream.pilot_bundle.pilot_plan.verify(root), PilotPlan)
    execution_devices = pilot_plan.devices
    probe = NvidiaSmiProbe() if gpu_probe is None else gpu_probe
    probe.wait_until_idle(
        execution_devices,
        max_memory_used_mib=stage04_config.executor.max_memory_used_mib,
        max_utilization_percent=stage04_config.executor.max_utilization_percent,
        timeout_seconds=stage04_config.executor.resource_wait_timeout_seconds,
        poll_seconds=stage04_config.executor.resource_poll_seconds,
    )
    if use_v1_6:
        if not isinstance(pilot_report, PilotFilterReportV1_6):
            raise ManifestStateError("v1.6 profile 必须引用 PilotFilterReportV1_6")
        selected_strategy_ids = pilot_report.promoted_strategy_ids
    else:
        if not isinstance(pilot_report, PilotFilterReport):
            raise ManifestStateError("v1.5 profile 必须引用 PilotFilterReport")
        selected_strategy_ids = pilot_report.selected_strategy_ids
    expanded = _expand_candidates(
        root=root,
        attempt_root=attempt_root,
        runtime_root=runtime,
        upstream=upstream,
        selected_strategy_ids=selected_strategy_ids,
        total_per_strategy=_diagnostic_expanded_total(config),
        adapter=boltzgen_adapter,
        devices=execution_devices,
        maximum_attempts=stage04_config.executor.max_task_attempts,
        created_at=now,
    )
    expanded_index = CandidateIndex(
        generated_at=datetime.now(UTC),
        strategy_bundle_sha256=upstream.strategy_bundle_ref.sha256,
        required_per_strategy=_diagnostic_expanded_total(config),
        candidates=tuple(
            sorted(
                expanded,
                key=lambda item: (
                    item.strategy_id,
                    item.ordinal_within_strategy,
                ),
            )
        ),
    )
    expanded_index_path = artifacts / "expansion-candidate-index.json"
    if expanded_index_path.exists():
        observed_index = load_model(expanded_index_path, CandidateIndex)
        if (
            observed_index.strategy_bundle_sha256 != expanded_index.strategy_bundle_sha256
            or observed_index.required_per_strategy != expanded_index.required_per_strategy
            or observed_index.candidates != expanded_index.candidates
        ):
            raise ManifestStateError("Stage 05 已发布 expansion candidate index 与恢复结果不一致")
        expanded_index = observed_index
    else:
        dump_model(expanded_index, expanded_index_path)
    expanded_index_ref = _artifact(
        root,
        expanded_index_path,
        artifact_id="expansion-candidate-index",
        role="stage05-expanded-candidates",
        file_format="json",
    )
    expansion_metrics = _batch_structure_metrics(
        root=root,
        upstream=upstream,
        candidates=expanded_index.candidates,
        runtime_root=runtime,
        phase="expansion-structure-metrics",
        created_at=now,
    )
    scored = evaluate_expansion_candidates(
        candidates=expanded_index.candidates,
        structural_metrics=expansion_metrics,
        full_target_top_n=_diagnostic_full_target_top_n(config),
    )
    selected_ids = {item.candidate_id for item in scored if item.selected_for_full_target}
    prediction_records: tuple[FullTargetPredictionRecord, ...]
    prediction_refs: tuple[ArtifactRef, ...]
    msa_refs: tuple[ArtifactRef, ...]
    conditioned_refs: tuple[ArtifactRef, ...]
    conditioned_evidence_ref: ArtifactRef | None
    if selected_ids:
        prediction_records, prediction_refs, msa_refs = _predict_selected_candidates(
            root=root,
            artifacts=artifacts,
            work=work,
            runtime=runtime,
            upstream=upstream,
            candidates=expanded_index.candidates,
            selected_ids=selected_ids,
            providers=config.full_target_prediction.target_msa.resolved_providers(),
            prediction_config=config.full_target_prediction,
            adapter_builder=prediction_adapter_builder,
            devices=execution_devices,
            maximum_attempts=stage04_config.executor.max_task_attempts,
            created_at=now,
        )
        if (
            upstream.target_bundle is None
            or config.full_target_prediction.template_protocol
            == AFO_TEMPLATE_PROTOCOL_ID
        ):
            # The frozen AFO protocol defines the standard condition as native
            # local-DataPipeline target templates plus the candidate's own
            # BoltzGen VHH template.  Re-running the same protocol under the
            # historical target-conditioned label would create two identical
            # inputs with different scientific labels.  A source-structure
            # condition therefore needs its own explicitly configured
            # experimental arm instead of being injected automatically here.
            conditioned_refs = ()
            conditioned_evidence_ref = None
        else:
            target_condition = snapshot_target_structure_condition(
                run_root=root,
                snapshot_root=work / "target-structure-condition",
                target_bundle=upstream.target_bundle,
            )
            (
                conditioned_records,
                conditioned_prediction_refs,
                conditioned_msa_refs,
            ) = _predict_selected_candidates(
                root=root,
                artifacts=artifacts,
                work=work,
                runtime=runtime,
                upstream=upstream,
                candidates=expanded_index.candidates,
                selected_ids=selected_ids,
                providers=config.full_target_prediction.target_msa.resolved_providers(),
                prediction_config=config.full_target_prediction,
                adapter_builder=prediction_adapter_builder,
                devices=execution_devices,
                maximum_attempts=stage04_config.executor.max_task_attempts,
                created_at=now,
                scientific_mode=ScientificMode.TARGET_CONDITIONED,
                target_condition=target_condition,
            )
            conditioned_evidence = TargetConditionedStage05Evidence(
                generated_at=datetime.now(UTC),
                target_condition=target_condition,
                predictions=conditioned_records,
            )
            conditioned_evidence_path = artifacts / "target-conditioned-evidence.json"
            if conditioned_evidence_path.exists():
                observed_conditioned = load_model(
                    conditioned_evidence_path,
                    TargetConditionedStage05Evidence,
                )
                if observed_conditioned.model_dump(exclude={"generated_at"}) != (
                    conditioned_evidence.model_dump(exclude={"generated_at"})
                ):
                    raise ManifestStateError(
                        "Stage 05 target-conditioned evidence 与 resume 不一致"
                    )
                conditioned_evidence = observed_conditioned
            else:
                dump_model(conditioned_evidence, conditioned_evidence_path)
            conditioned_evidence_ref = _artifact(
                root,
                conditioned_evidence_path,
                artifact_id="stage05-target-conditioned-evidence",
                role="target-conditioned-advisory-evidence",
                file_format="json",
            )
            condition_path = work / "target-structure-condition" / "condition.json"
            conditioned_refs = (
                *conditioned_prediction_refs,
                *conditioned_msa_refs,
                _artifact(
                    root,
                    target_condition.snapshot_structure_path,
                    artifact_id="stage05-target-condition-structure",
                    role="target-condition-run-snapshot",
                    file_format="mmcif",
                ),
                *(
                    (
                        _artifact(
                            root,
                            target_condition.snapshot_pdb_path,
                            artifact_id="stage05-target-condition-pdb",
                            role="target-condition-run-snapshot",
                            file_format="pdb",
                        ),
                    )
                    if target_condition.snapshot_pdb_path is not None
                    else ()
                ),
                _artifact(
                    root,
                    target_condition.template_structure_path,
                    artifact_id="stage05-target-condition-template-structure",
                    role="target-condition-template-snapshot",
                    file_format="mmcif",
                ),
                _artifact(
                    root,
                    target_condition.template_data_path,
                    artifact_id="stage05-target-condition-template-data",
                    role="target-condition-residue-mapping",
                    file_format="json",
                ),
                _artifact(
                    root,
                    target_condition.binder_template_data_path,
                    artifact_id="stage05-binder-empty-template-data",
                    role="binder-no-template-snapshot",
                    file_format="json",
                ),
                _artifact(
                    root,
                    condition_path,
                    artifact_id="stage05-target-condition",
                    role="target-condition-provenance",
                    file_format="json",
                ),
            )
    else:
        prediction_records = ()
        prediction_refs = ()
        msa_refs = ()
        conditioned_refs = ()
        conditioned_evidence_ref = None
    if use_v1_6:
        assert isinstance(pilot_report, PilotFilterReportV1_6)
        promotions = promotion_records(pilot_report)
    else:
        assert isinstance(pilot_report, PilotFilterReport)
        promotions = ()
    expansion_report: AdvisoryValidationReport | ExpansionValidationReport
    if use_v1_6:
        expansion_report = build_advisory_validation_report(
            promoted_strategies=promotions,
            expanded_total_per_strategy=(
                _diagnostic_expanded_total(config)
            ),
            full_target_top_n=_diagnostic_full_target_top_n(config),
            candidates=scored,
            predictions=prediction_records,
            generated_at=datetime.now(UTC),
            profile_id=cast(
                Literal[
                    "nanobody-filter-standard-v1.6",
                    "nanobody-filter-standard-v1.7",
                ],
                filter_profile,
            ),
        )
        expansion_report_path = artifacts / "advisory-validation-report.json"
    else:
        expansion_report = select_scale_strategy(
            expanded_total_per_strategy=(
                _diagnostic_expanded_total(config)
            ),
            full_target_top_n=_diagnostic_full_target_top_n(config),
            candidates=scored,
            predictions=prediction_records,
            generated_at=datetime.now(UTC),
        )
        expansion_report_path = artifacts / "expansion-validation-report.json"
    if expansion_report_path.exists():
        observed_report: AdvisoryValidationReport | ExpansionValidationReport
        if use_v1_6:
            observed_report = load_model(
                expansion_report_path,
                AdvisoryValidationReport,
            )
        else:
            observed_report = load_model(
                expansion_report_path,
                ExpansionValidationReport,
            )
        if observed_report.model_dump(exclude={"generated_at"}) != (
            expansion_report.model_dump(exclude={"generated_at"})
        ):
            raise ManifestStateError("Stage 05 expansion report 与恢复结果不一致")
        expansion_report = observed_report
    else:
        dump_model(expansion_report, expansion_report_path)
    expansion_report_ref = _artifact(
        root,
        expansion_report_path,
        artifact_id=(
            "advisory-validation-report"
            if use_v1_6
            else "expansion-validation-report"
        ),
        role=(
            "stage05-advisory-evidence"
            if use_v1_6
            else "stage05-scale-strategy-evidence"
        ),
        file_format="json",
    )
    scale_stop_ref: ArtifactRef | None = None
    if not use_v1_6:
        assert isinstance(expansion_report, ExpansionValidationReport)
        if expansion_report.status == "stopped-no-scale-winner":
            stop_path = artifacts / "scientific-stop.json"
            scale_stop = ScientificStop(
                stage_id=str(StageId.PILOT_FILTERING),
                code=ScientificStopCode.NO_SCALE_WINNER,
                occurred_at=datetime.now(UTC),
                message="No strategy passed full-target expansion validation.",
                evidence_artifact_sha256=(expansion_report_ref.sha256,),
            )
            if stop_path.exists():
                scale_stop = load_model(stop_path, ScientificStop)
                if (
                    scale_stop.code is not ScientificStopCode.NO_SCALE_WINNER
                    or scale_stop.evidence_artifact_sha256
                    != (expansion_report_ref.sha256,)
                ):
                    raise ManifestStateError("Stage 05 scale stop evidence 不一致")
            else:
                dump_model(scale_stop, stop_path)
            scale_stop_ref = _artifact(
                root,
                stop_path,
                artifact_id="stage05-scientific-stop",
                role="scientific-negative-result",
                file_format="json",
            )
    progress_ref, events_ref = _publish_final_execution_evidence(
        root=root,
        artifacts=artifacts,
        runtime=runtime,
        status=("scientific-stop" if scale_stop_ref is not None else "succeeded"),
        completed_at=datetime.now(UTC),
    )
    bundle_path = artifacts / "stage05-bundle.json"
    bundle: Stage05Bundle | Stage05BundleV0_2
    if use_v1_6:
        assert isinstance(expansion_report, AdvisoryValidationReport)
        bundle = Stage05BundleV0_2(
            generated_at=datetime.now(UTC),
            pilot_bundle=upstream.pilot_bundle_ref,
            strategy_bundle=upstream.strategy_bundle_ref,
            filter_profile=profile_ref,
            pilot_filter_report=pilot_report_ref,
            expansion_candidate_index=expanded_index_ref,
            advisory_validation_report=expansion_report_ref,
            target_conditioned_evidence=conditioned_evidence_ref,
            progress_final=progress_ref,
            task_events=events_ref,
            promoted_strategy_ids=tuple(
                item.strategy_id for item in promotions
            ),
            promotion_rank=promotions,
            warnings=expansion_report.warnings,
            status="strategies-promoted",
        )
    else:
        assert isinstance(expansion_report, ExpansionValidationReport)
        bundle = Stage05Bundle(
            generated_at=datetime.now(UTC),
            pilot_bundle=upstream.pilot_bundle_ref,
            strategy_bundle=upstream.strategy_bundle_ref,
            filter_profile=profile_ref,
            pilot_filter_report=pilot_report_ref,
            expansion_candidate_index=expanded_index_ref,
            expansion_validation_report=expansion_report_ref,
            target_conditioned_evidence=conditioned_evidence_ref,
            progress_final=progress_ref,
            task_events=events_ref,
            scientific_stop=scale_stop_ref,
            winner_strategy_id=expansion_report.winner_strategy_id,
            status=expansion_report.status,
        )
    if bundle_path.exists():
        if use_v1_6:
            bundle_v1_6 = load_model(bundle_path, Stage05BundleV0_2)
            assert isinstance(expansion_report, AdvisoryValidationReport)
            if (
                bundle_v1_6.advisory_validation_report != expansion_report_ref
                or bundle_v1_6.target_conditioned_evidence
                != conditioned_evidence_ref
                or bundle_v1_6.status != "strategies-promoted"
            ):
                raise ManifestStateError(
                    "Stage 05 已存在 v1.6 Bundle 与当前结果不一致"
                )
            bundle = bundle_v1_6
        else:
            bundle_v1_5 = load_model(bundle_path, Stage05Bundle)
            assert isinstance(expansion_report, ExpansionValidationReport)
            if (
                bundle_v1_5.expansion_validation_report != expansion_report_ref
                or bundle_v1_5.target_conditioned_evidence
                != conditioned_evidence_ref
                or bundle_v1_5.status != expansion_report.status
            ):
                raise ManifestStateError(
                    "Stage 05 已存在 v1.5 Bundle 与当前结果不一致"
                )
            bundle = bundle_v1_5
    else:
        dump_model(bundle, bundle_path)
    bundle_ref = _artifact(
        root,
        bundle_path,
        artifact_id="stage05-bundle",
        role="stage06-strategy-input-or-stop",
        file_format="json",
    )
    output_refs = (
        profile_ref,
        pilot_report_ref,
        expanded_index_ref,
        progress_ref,
        events_ref,
        *msa_refs,
        *prediction_refs,
        *conditioned_refs,
        *((conditioned_evidence_ref,) if conditioned_evidence_ref is not None else ()),
        expansion_report_ref,
        *((scale_stop_ref,) if scale_stop_ref is not None else ()),
        bundle_ref,
    )
    if use_v1_6:
        assert isinstance(expansion_report, AdvisoryValidationReport)
        warning = (
            f"{len(promotions)} Tier A strategies promoted by F_YAML.",
            *tuple(item.message for item in expansion_report.warnings),
            "Diagnostic Protenix evidence does not revoke Tier A promotion.",
        )
    elif scale_stop_ref is not None:
        warning = (
            "Scientific stop: stopped-no-scale-winner.",
            "Software execution succeeded; no scale strategy was published.",
        )
    else:
        warning = (
            "Exactly one deterministic scale strategy was selected.",
            "Protenix confidence is structural evidence, not binding affinity.",
        )
    execution = _publish_stage05(
        root=root,
        upstream=upstream,
        resolved=resolved,
        artifacts=artifacts,
        created_at=now,
        output_refs=output_refs,
        bundle_path=bundle_path,
        warnings=warning,
        scientific_stop=scale_stop_ref is not None,
        filter_profile=filter_profile,
    )
    return _with_review_dashboard(execution, generated_at=now)
