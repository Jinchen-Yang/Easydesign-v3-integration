"""Stage 06 sharded, resumable BoltzGen scale generation."""

from __future__ import annotations

import json
import math
import os
import shutil
import tempfile
import threading
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel, ConfigDict

from easydesign.backends.boltzgen import BoltzGenGenerationAdapter
from easydesign.backends.executors import (
    NvidiaSmiProbe,
    execute_on_devices,
    ui_drain_requested,
)
from easydesign.core import (
    ArtifactRef,
    Attempt,
    ExecutionStatus,
    ManifestStateError,
    ProgressSnapshot,
    RunManifest,
    StageId,
    StageManifest,
    TaskEvent,
    TaskHeartbeat,
    TaskRecord,
    TaskStatus,
    dump_model,
    load_model,
    sha256_file,
)
from easydesign.stages.s03_boltzgen_configuration import StrategyBundle
from easydesign.stages.s04_pilot_generation import CandidateIndex
from easydesign.stages.s05_pilot_filtering import PilotFilterReport, Stage05Bundle
from easydesign.stages.s06_scale_generation_and_refolding import (
    ScaleBundle,
    ScaleCoverageReport,
    ScaleExecutionState,
    ScalePlan,
    ScaleProfile,
    ScaleResourceReport,
    ScaleShard,
    ScaleStrategyAuthorization,
    ScaleTaskTable,
)

from .boltzgen_tasks import (
    TaskTransition,
    execute_boltzgen_candidate_task,
    recover_interrupted_boltzgen_task,
)
from .config import Stage06Config
from .stage04 import _atomic_text
from .task_tracking import TaskEventJournal, atomic_dump_runtime_model
from .workspace import ResolvedRunConfig, RunIndexEntry, upsert_run_index_entries

ModelT = TypeVar("ModelT", bound=BaseModel)


class Stage06Execution(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: str
    run_root: Path
    run_manifest: Path
    stage_manifest: Path | None = None
    scale_bundle: Path | None = None
    complete_candidate_count: int = 0


@dataclass(frozen=True, slots=True)
class _Upstream:
    run: RunManifest
    run_manifest_path: Path
    stage03: StageManifest
    stage04: StageManifest
    stage05: StageManifest
    strategy_bundle_ref: ArtifactRef
    strategy_bundle: StrategyBundle
    pilot_candidate_index_ref: ArtifactRef
    pilot_candidate_index: CandidateIndex
    stage05_bundle_ref: ArtifactRef
    stage05_bundle: Stage05Bundle
    pilot_filter_report: PilotFilterReport


def _latest_manifest(root: Path) -> tuple[RunManifest, Path]:
    pointer = root / "manifests" / "LATEST"
    try:
        name = pointer.read_text(encoding="utf-8").strip()
    except OSError as error:
        raise ManifestStateError(f"无法读取 RunManifest LATEST: {pointer}") from error
    path = root / "manifests" / name
    return load_model(path, RunManifest), path


def _stage(
    root: Path,
    run: RunManifest,
    stage_id: StageId,
) -> StageManifest:
    reference = next(
        (item for item in run.stage_manifest_refs if item.producer_stage == str(stage_id)),
        None,
    )
    if reference is None:
        raise ManifestStateError(f"Stage 06 缺少上游 {stage_id}")
    manifest = load_model(reference.verify(root), StageManifest)
    if manifest.status is not ExecutionStatus.SUCCEEDED:
        raise ManifestStateError(f"Stage 06 上游 {stage_id} 未成功")
    return manifest


def _load_upstream(root: Path) -> _Upstream:
    run, run_path = _latest_manifest(root)
    stage03 = _stage(root, run, StageId.BOLTZGEN_CONFIGURATION)
    stage04 = _stage(root, run, StageId.PILOT_GENERATION)
    stage05 = _stage(root, run, StageId.PILOT_FILTERING)
    strategy_ref = stage03.require_output("strategy-bundle")
    strategy = load_model(strategy_ref.verify(root), StrategyBundle)
    pilot_index_ref = stage04.require_output("candidate-index")
    pilot_index = load_model(pilot_index_ref.verify(root), CandidateIndex)
    stage05_ref = stage05.require_output("stage05-bundle")
    stage05_bundle = load_model(stage05_ref.verify(root), Stage05Bundle)
    if stage05_bundle.strategy_bundle != strategy_ref:
        raise ManifestStateError("Stage05Bundle 与 StrategyBundle identity 不一致")
    pilot_filter_report = load_model(
        stage05_bundle.pilot_filter_report.verify(root),
        PilotFilterReport,
    )
    if stage05_bundle.winner_strategy_id is not None and not any(
        item.strategy_id == stage05_bundle.winner_strategy_id
        for item in strategy.strategies
    ):
        raise ManifestStateError("Stage05Bundle winner 不在 StrategyBundle")
    for candidate in pilot_index.candidates:
        candidate.original_structure.verify(root)
        candidate.refolded_structure.verify(root)
        if candidate.design_mask_source is None:
            raise ManifestStateError("Stage 04 candidate 缺少 design mask")
        candidate.design_mask_source.verify(root)
    return _Upstream(
        run=run,
        run_manifest_path=run_path,
        stage03=stage03,
        stage04=stage04,
        stage05=stage05,
        strategy_bundle_ref=strategy_ref,
        strategy_bundle=strategy,
        pilot_candidate_index_ref=pilot_index_ref,
        pilot_candidate_index=pilot_index,
        stage05_bundle_ref=stage05_ref,
        stage05_bundle=stage05_bundle,
        pilot_filter_report=pilot_filter_report,
    )


def _resolve_strategy_authorization(
    *,
    upstream: _Upstream,
    config: Stage06Config,
    authorized_at: datetime,
) -> ScaleStrategyAuthorization:
    bundle = upstream.stage05_bundle
    manual = config.manual_strategy_authorization
    if bundle.status == "winner-selected":
        if bundle.winner_strategy_id is None:
            raise ManifestStateError("Stage 05 winner-selected 缺少 winner strategy")
        if manual is not None:
            raise ManifestStateError("Stage 05 已有 winner 时不得声明 manual override")
        return ScaleStrategyAuthorization(
            mode="stage05-winner",
            strategy_id=bundle.winner_strategy_id,
            authorized_at=authorized_at,
            authorized_by="stage05-deterministic-policy",
            reason="Stage 05 published the unique scientifically eligible scale winner.",
            source_stage05_status=bundle.status,
            source_stage05_bundle_sha256=upstream.stage05_bundle_ref.sha256,
        )
    if bundle.status == "stopped-no-tier-a":
        raise ManifestStateError("Stage 05 没有 Tier A；Stage 06 不允许人工越过该边界")
    if bundle.status != "stopped-no-scale-winner":
        raise ManifestStateError(f"Stage 05 status={bundle.status} 不支持 Stage 06")
    if manual is None:
        raise ManifestStateError(
            "Stage 05 stopped-no-scale-winner；缺少显式 manual strategy authorization"
        )
    if manual.source_stage05_bundle_sha256 != upstream.stage05_bundle_ref.sha256:
        raise ManifestStateError("manual strategy authorization 的 Stage05Bundle SHA-256 不一致")
    if manual.strategy_id not in upstream.pilot_filter_report.selected_strategy_ids:
        raise ManifestStateError(
            "manual strategy authorization 只能选择 Stage 05 已扩展的 Tier A strategy"
        )
    if not any(
        item.strategy_id == manual.strategy_id
        for item in upstream.strategy_bundle.strategies
    ):
        raise ManifestStateError("manual strategy authorization 不在 StrategyBundle")
    return ScaleStrategyAuthorization(
        mode="manual-stage05-stop-override",
        strategy_id=manual.strategy_id,
        authorized_at=authorized_at,
        authorized_by=manual.authorized_by,
        reason=manual.reason,
        source_stage05_status=bundle.status,
        source_stage05_bundle_sha256=manual.source_stage05_bundle_sha256,
        acknowledge_stage05_scientific_stop=(
            manual.acknowledge_stage05_scientific_stop
        ),
        acknowledge_not_scientifically_eligible=(
            manual.acknowledge_not_scientifically_eligible
        ),
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
        producer_stage=str(StageId.SCALE_GENERATION_AND_REFOLDING),
        producer_attempt="attempt-0001",
    )


def _dump_or_verify_model(
    model: ModelT,
    path: Path,
    model_type: type[ModelT],
    *,
    ignore_fields: frozenset[str] = frozenset(),
) -> ModelT:
    """Publish once, or verify a compatible artifact left by an interrupted publish."""

    if not path.exists():
        dump_model(model, path)
        return model
    existing = load_model(path, model_type)
    excluded = set(ignore_fields)
    if existing.model_dump(exclude=excluded) != model.model_dump(exclude=excluded):
        raise ManifestStateError(f"Stage 06 已有终态 artifact identity 不一致: {path}")
    return existing


def _write_or_verify_bytes(content: bytes, path: Path) -> None:
    """Create an immutable byte artifact atomically, or verify the frozen bytes."""

    if path.exists():
        if path.read_bytes() != content:
            raise ManifestStateError(f"Stage 06 已有终态 artifact bytes 不一致: {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
            temporary_path = Path(handle.name)
        os.link(temporary_path, path)
        temporary_path.unlink()
    except FileExistsError as error:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        if path.read_bytes() != content:
            raise ManifestStateError(
                f"Stage 06 并发发布的 artifact bytes 不一致: {path}"
            ) from error
    except OSError:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        raise


def _resource_report(
    *,
    root: Path,
    upstream: _Upstream,
    requested_candidates: int,
    measured_at: datetime,
) -> ScaleResourceReport:
    measured_refs = tuple(
        reference
        for candidate in upstream.pilot_candidate_index.candidates
        for reference in (
            candidate.original_structure,
            candidate.refolded_structure,
            candidate.design_mask_source,
        )
        if reference is not None
    )
    measured_bytes = sum(item.size_bytes for item in measured_refs)
    measured_count = len(upstream.pilot_candidate_index.candidates)
    if measured_bytes < 1 or measured_count < 1:
        raise ManifestStateError("Stage 06 无法从 Stage 04 artifact 测量存储基线")
    per_candidate = measured_bytes / measured_count
    estimated = max(math.ceil(per_candidate * requested_candidates * 20), 1)
    disk = shutil.disk_usage(root)
    projected = max(disk.free - estimated, 0)
    passed = disk.free >= estimated and projected >= int(disk.total * 0.25)
    return ScaleResourceReport(
        measured_at=measured_at,
        measured_candidate_count=measured_count,
        measured_candidate_bytes=measured_bytes,
        measured_bytes_per_candidate=per_candidate,
        estimated_peak_bytes=estimated,
        filesystem_total_bytes=disk.total,
        filesystem_free_bytes=disk.free,
        projected_free_bytes=projected,
        passed=passed,
        reason=(
            "Projected free space remains at or above 25% after the conservative "
            "declared-artifact estimate."
            if passed
            else "Projected free space would fall below the required 25% reserve."
        ),
    )


def build_scale_plan(
    *,
    profile: ScaleProfile,
    strategy_id: str,
    strategy_bundle_sha256: str,
    stage05_bundle_sha256: str,
    design_specification: ArtifactRef,
    resource_report: ArtifactRef,
    devices: tuple[int, ...],
    preauthorized_candidate_limit: int,
    generated_at: datetime,
    strategy_authorization: ScaleStrategyAuthorization | None = None,
) -> ScalePlan:
    """Build the deterministic 2×500 or 20×2500 shard layout."""

    requested = profile.requested_candidates
    shard_size = profile.shard_size
    shards = tuple(
        ScaleShard(
            shard_id=f"shard-{index + 1:04d}",
            task_id=f"scale-shard-{index + 1:04d}",
            strategy_id=strategy_id,
            ordinal_start=index * shard_size + 1,
            ordinal_end=(index + 1) * shard_size,
            requested_candidates=shard_size,
        )
        for index in range(requested // shard_size)
    )
    authorization = strategy_authorization or ScaleStrategyAuthorization(
        mode="stage05-winner",
        strategy_id=strategy_id,
        authorized_at=generated_at,
        authorized_by="stage05-deterministic-policy",
        reason="Stage 05 published the unique scientifically eligible scale winner.",
        source_stage05_status="winner-selected",
        source_stage05_bundle_sha256=stage05_bundle_sha256,
    )
    return ScalePlan(
        generated_at=generated_at,
        profile=profile,
        strategy_id=strategy_id,
        strategy_bundle_sha256=strategy_bundle_sha256,
        stage05_bundle_sha256=stage05_bundle_sha256,
        strategy_authorization=authorization,
        design_specification=design_specification,
        requested_new_candidates=requested,
        preauthorized_candidate_limit=preauthorized_candidate_limit,
        devices=devices,
        shards=shards,
        resource_report=resource_report,
        execution_authorized=True,
    )


def _snapshot(
    *,
    tasks: tuple[TaskRecord, ...],
    created_at: datetime,
    status: str,
    task_heartbeats: tuple[TaskHeartbeat, ...] = (),
    recent_errors: tuple[str, ...] = (),
) -> ProgressSnapshot:
    updated_at = datetime.now(UTC)
    counts = {item: 0 for item in TaskStatus}
    per_device: dict[str, str | None] = {}
    for task in tasks:
        counts[task.status] += 1
        if task.status is TaskStatus.RUNNING:
            assert task.current_device is not None
            per_device[str(task.current_device)] = task.task_id
    planned = sum(item.requested_candidates for item in tasks)
    collected = sum(item.collected_candidates for item in tasks)
    elapsed = max((updated_at - created_at).total_seconds(), 0.0)
    throughput = collected / elapsed * 3600 if collected and elapsed else None
    remaining = planned - collected
    eta = (
        remaining / throughput * 3600
        if throughput is not None and throughput > 0 and remaining > 0
        else (0.0 if remaining == 0 else None)
    )
    return ProgressSnapshot(
        stage_id=str(StageId.SCALE_GENERATION_AND_REFOLDING),
        phase="scale-generation",
        updated_at=updated_at,
        status=status,
        total_tasks=len(tasks),
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
        task_heartbeats=task_heartbeats,
        recent_errors=recent_errors[-10:],
    )


def execute_stage06(
    *,
    run_root: Path,
    adapter: BoltzGenGenerationAdapter,
    gpu_probe: NvidiaSmiProbe | None = None,
    executed_at: datetime | None = None,
) -> Stage06Execution:
    """Execute/resume one manifest-declared scale winner in immutable shards."""

    root = run_root.resolve()
    upstream = _load_upstream(root)
    if upstream.run.status is not ExecutionStatus.RUNNING:
        raise ManifestStateError("Stage 06 只能写入 running run")
    if any(
        item.producer_stage == str(StageId.SCALE_GENERATION_AND_REFOLDING)
        for item in upstream.run.stage_manifest_refs
    ):
        raise ManifestStateError("Stage 06 已发布，禁止覆盖")
    resolved = load_model(
        root / "config-snapshot" / "resolved-config.json",
        ResolvedRunConfig,
    )
    config = resolved.user_config.stage06
    stage04_config = resolved.user_config.stage04
    if config is None or stage04_config is None:
        raise ManifestStateError("Stage 06 缺少 stage04/stage06 config")
    now = datetime.now(UTC) if executed_at is None else executed_at
    profile = ScaleProfile(config.scale_profile)
    authorization = _resolve_strategy_authorization(
        upstream=upstream,
        config=config,
        authorized_at=now,
    )
    winner = authorization.strategy_id
    strategy = next(
        item for item in upstream.strategy_bundle.strategies if item.strategy_id == winner
    )
    specification = upstream.stage03.require_output(f"strategy-{winner}")
    specification.verify(root)
    if specification.sha256 != strategy.design_specification_sha256:
        raise ManifestStateError("Stage 06 winner YAML identity 不一致")

    attempt_root = root / str(StageId.SCALE_GENERATION_AND_REFOLDING) / "attempt-0001"
    artifacts = attempt_root / "artifacts"
    runtime = attempt_root / "runtime"
    resource_path = artifacts / "resource-report.json"
    authorization_path = artifacts / "scale-strategy-authorization.json"
    plan_path = artifacts / "scale-plan.json"
    authorization = _dump_or_verify_model(
        authorization,
        authorization_path,
        ScaleStrategyAuthorization,
        ignore_fields=frozenset({"authorized_at"}),
    )
    authorization_ref = _artifact(
        root,
        authorization_path,
        artifact_id="scale-strategy-authorization",
        role="human-or-policy-scale-authority",
        file_format="json",
    )
    if plan_path.exists():
        plan = load_model(plan_path, ScalePlan)
        report = load_model(resource_path, ScaleResourceReport)
        resource_ref = _artifact(
            root,
            resource_path,
            artifact_id="scale-resource-report",
            role="scale-storage-preflight",
            file_format="json",
        )
        plan.resource_report.verify(root)
        if (
            plan.strategy_bundle_sha256 != upstream.strategy_bundle_ref.sha256
            or plan.stage05_bundle_sha256 != upstream.stage05_bundle_ref.sha256
            or plan.strategy_id != winner
            or plan.profile is not profile
            or plan.strategy_authorization != authorization
            or plan.design_specification != specification
            or plan.resource_report != resource_ref
            or plan.devices != stage04_config.executor.devices
            or plan.preauthorized_candidate_limit != config.preauthorized_candidate_limit
        ):
            raise ManifestStateError("Stage 06 已有 ScalePlan identity 不一致")
    else:
        report = _resource_report(
            root=root,
            upstream=upstream,
            requested_candidates=profile.requested_candidates,
            measured_at=now,
        )
        atomic_dump_runtime_model(report, runtime / "resource-preflight.json")
        if not report.passed:
            raise ManifestStateError("Stage 06 disk preflight 失败；未创建任何 generation task")
        dump_model(report, resource_path)
        resource_ref = _artifact(
            root,
            resource_path,
            artifact_id="scale-resource-report",
            role="scale-storage-preflight",
            file_format="json",
        )
        plan = build_scale_plan(
            profile=profile,
            strategy_id=winner,
            strategy_bundle_sha256=upstream.strategy_bundle_ref.sha256,
            stage05_bundle_sha256=upstream.stage05_bundle_ref.sha256,
            design_specification=specification,
            resource_report=resource_ref,
            devices=stage04_config.executor.devices,
            preauthorized_candidate_limit=config.preauthorized_candidate_limit,
            generated_at=now,
            strategy_authorization=authorization,
        )
        dump_model(plan, plan_path)
    if not report.passed or not plan.execution_authorized:
        raise ManifestStateError("Stage 06 ScalePlan 未获执行授权")
    current_disk = shutil.disk_usage(root)
    if (
        current_disk.free < report.estimated_peak_bytes
        or current_disk.free - report.estimated_peak_bytes
        < int(current_disk.total * report.required_reserve_fraction)
    ):
        raise ManifestStateError("Stage 06 当前磁盘不再满足冻结 plan 的 25% reserve")

    state_path = runtime / "scale-state.json"
    progress_path = runtime / "progress.json"
    events_path = runtime / "task-events.jsonl"
    journal = TaskEventJournal(events_path)
    plan_sha256 = sha256_file(plan_path)
    heartbeats: dict[str, TaskHeartbeat]
    if state_path.exists():
        state = load_model(state_path, ScaleExecutionState)
        if state.plan_sha256 != plan_sha256:
            raise ManifestStateError("Stage 06 runtime state 与 ScalePlan 不一致")
        tasks = {item.task_id: item for item in state.tasks}
        candidates = list(state.candidates)
        created_at = state.created_at
        heartbeats = {
            item.task_id: item
            for item in state.progress.task_heartbeats
            if item.task_id in tasks
        }
        if set(tasks) != {item.task_id for item in plan.shards}:
            raise ManifestStateError("Stage 06 runtime shard identity 不一致")
        for candidate in candidates:
            candidate.original_structure.verify(root)
            candidate.refolded_structure.verify(root)
            if candidate.design_mask_source is None:
                raise ManifestStateError("Stage 06 candidate 缺少 design mask")
            candidate.design_mask_source.verify(root)
    else:
        tasks = {
            shard.task_id: TaskRecord(
                task_id=shard.task_id,
                strategy_id=winner,
                requested_candidates=shard.requested_candidates,
            )
            for shard in plan.shards
        }
        candidates = []
        created_at = now
        heartbeats = {}

    lock = threading.RLock()
    recent_errors: list[str] = []

    def ordered_tasks() -> tuple[TaskRecord, ...]:
        return tuple(tasks[item.task_id] for item in plan.shards)

    def persist(status: str) -> None:
        snapshot = _snapshot(
            tasks=ordered_tasks(),
            created_at=created_at,
            status=status,
            task_heartbeats=tuple(
                heartbeats[key] for key in sorted(heartbeats)
            ),
            recent_errors=tuple(recent_errors),
        )
        atomic_dump_runtime_model(snapshot, progress_path)
        atomic_dump_runtime_model(
            ScaleExecutionState(
                created_at=created_at,
                updated_at=snapshot.updated_at,
                plan_sha256=plan_sha256,
                tasks=ordered_tasks(),
                candidates=tuple(candidates),
                progress=snapshot,
            ),
            state_path,
        )

    def transition(update: TaskTransition) -> None:
        with lock:
            tasks[update.task.task_id] = update.task
            if update.task.status is not TaskStatus.RUNNING:
                heartbeats.pop(update.task.task_id, None)
            candidates.extend(update.new_candidates)
            if update.error is not None:
                recent_errors.append(
                    f"{update.task.task_id}: {update.error.code}: {update.error.message}"
                )
            journal.append(
                TaskEvent(
                    sequence=journal.next_sequence,
                    occurred_at=datetime.now(UTC),
                    event_type=update.event_type,
                    task_id=update.task.task_id,
                    strategy_id=update.task.strategy_id,
                    task_attempt_number=update.attempt_number,
                    device=update.device,
                    from_status=update.from_status,
                    to_status=update.to_status,
                    message=update.message,
                    error=update.error,
                )
            )
            persist("incomplete" if update.event_type == "task-incomplete" else "running")

    def heartbeat(update: TaskHeartbeat) -> None:
        with lock:
            task = tasks.get(update.task_id)
            if task is None or task.status is not TaskStatus.RUNNING:
                return
            heartbeats[update.task_id] = update
            persist("running")

    for shard in plan.shards:
        update = recover_interrupted_boltzgen_task(
            root=root,
            task=tasks[shard.task_id],
            stage_attempt_id="attempt-0001",
            producer_stage=str(StageId.SCALE_GENERATION_AND_REFOLDING),
            ordinal_offset=shard.ordinal_start - 1,
        )
        if update is not None:
            transition(update)
    for shard in plan.shards:
        task = tasks[shard.task_id]
        if (
            task.status is TaskStatus.FAILED
            and task.collected_candidates < task.requested_candidates
        ):
            tasks[shard.task_id] = task.model_copy(update={"status": TaskStatus.PENDING})
    persist("running")

    probe = NvidiaSmiProbe() if gpu_probe is None else gpu_probe
    probe.wait_until_idle(
        plan.devices,
        max_memory_used_mib=stage04_config.executor.max_memory_used_mib,
        max_utilization_percent=stage04_config.executor.max_utilization_percent,
        timeout_seconds=stage04_config.executor.resource_wait_timeout_seconds,
        poll_seconds=stage04_config.executor.resource_poll_seconds,
    )

    def run_shard(shard: ScaleShard, device: int) -> TaskRecord:
        return execute_boltzgen_candidate_task(
            root=root,
            task=tasks[shard.task_id],
            design_specification=specification.verify(root),
            task_root=attempt_root / "tasks" / shard.task_id,
            stage_attempt_id="attempt-0001",
            producer_stage=str(StageId.SCALE_GENERATION_AND_REFOLDING),
            adapter=adapter,
            device=device,
            maximum_attempts_this_invocation=stage04_config.executor.max_task_attempts,
            on_transition=transition,
            on_heartbeat=heartbeat,
            ordinal_offset=shard.ordinal_start - 1,
        )

    pending = tuple(
        item for item in plan.shards if tasks[item.task_id].status is not TaskStatus.SUCCEEDED
    )
    results = execute_on_devices(
        pending,
        devices=plan.devices,
        worker=run_shard,
        should_stop=ui_drain_requested,
    )
    for result in results:
        tasks[pending[result.input_index].task_id] = result.result
    final_tasks = ordered_tasks()
    if any(item.status is not TaskStatus.SUCCEEDED for item in final_tasks):
        persist("incomplete")
        return Stage06Execution(
            status="incomplete",
            run_root=root,
            run_manifest=upstream.run_manifest_path,
            complete_candidate_count=len(candidates),
        )

    ordered_candidates = tuple(sorted(candidates, key=lambda item: item.ordinal_within_strategy))
    proposed_candidate_index = CandidateIndex(
        generated_at=datetime.now(UTC),
        strategy_bundle_sha256=upstream.strategy_bundle_ref.sha256,
        required_per_strategy=plan.requested_new_candidates,
        candidates=ordered_candidates,
    )
    if len(ordered_candidates) != plan.requested_new_candidates:
        raise ManifestStateError("Stage 06 merge candidate count 不一致")
    if [item.ordinal_within_strategy for item in ordered_candidates] != list(
        range(1, plan.requested_new_candidates + 1)
    ):
        raise ManifestStateError("Stage 06 merge 存在 candidate ordinal 缺口或重复")

    candidate_index_path = artifacts / "scale-candidate-index.json"
    task_table_path = artifacts / "scale-task-table.json"
    coverage_path = artifacts / "scale-coverage-report.json"
    progress_final_path = artifacts / "progress-final.json"
    events_artifact = artifacts / "task-events.jsonl"
    backend_path = artifacts / "backend-environment.json"
    _dump_or_verify_model(
        proposed_candidate_index,
        candidate_index_path,
        CandidateIndex,
        ignore_fields=frozenset({"generated_at"}),
    )
    _dump_or_verify_model(
        ScaleTaskTable(generated_at=datetime.now(UTC), tasks=final_tasks),
        task_table_path,
        ScaleTaskTable,
        ignore_fields=frozenset({"generated_at"}),
    )
    coverage = ScaleCoverageReport(
        strategy_id=winner,
        requested_new_candidates=plan.requested_new_candidates,
        complete_new_candidates=len(ordered_candidates),
        candidate_ids_unique=(
            len({item.candidate_id for item in ordered_candidates}) == len(ordered_candidates)
        ),
        ordinal_min=ordered_candidates[0].ordinal_within_strategy,
        ordinal_max=ordered_candidates[-1].ordinal_within_strategy,
    )
    _dump_or_verify_model(coverage, coverage_path, ScaleCoverageReport)
    final_progress = _snapshot(
        tasks=final_tasks,
        created_at=created_at,
        status="succeeded",
        recent_errors=tuple(recent_errors),
    )
    if progress_final_path.exists():
        frozen_progress = load_model(progress_final_path, ProgressSnapshot)
        if (
            frozen_progress.stage_id != str(StageId.SCALE_GENERATION_AND_REFOLDING)
            or frozen_progress.status != "succeeded"
            or frozen_progress.total_tasks != len(final_tasks)
            or frozen_progress.succeeded_tasks != len(final_tasks)
            or frozen_progress.failed_tasks != 0
            or frozen_progress.planned_candidates != plan.requested_new_candidates
            or frozen_progress.collected_candidates != plan.requested_new_candidates
        ):
            raise ManifestStateError("Stage 06 已有 terminal progress 与成功任务不一致")
        final_progress = frozen_progress
    else:
        dump_model(final_progress, progress_final_path)
    _write_or_verify_bytes(events_path.read_bytes(), events_artifact)
    backend_bytes = (json.dumps(adapter.probe(), indent=2, sort_keys=True) + "\n").encode("utf-8")
    _write_or_verify_bytes(
        backend_bytes,
        backend_path,
    )

    output_refs = (
        _artifact(
            root,
            plan_path,
            artifact_id="scale-plan",
            role="scale-execution-plan",
            file_format="json",
        ),
        _artifact(
            root,
            resource_path,
            artifact_id="scale-resource-report",
            role="scale-storage-preflight",
            file_format="json",
        ),
        authorization_ref,
        _artifact(
            root,
            task_table_path,
            artifact_id="scale-task-table",
            role="scale-task-terminal-records",
            file_format="json",
        ),
        _artifact(
            root,
            candidate_index_path,
            artifact_id="scale-candidate-index",
            role="stage07-candidate-input",
            file_format="json",
        ),
        _artifact(
            root,
            coverage_path,
            artifact_id="scale-coverage-report",
            role="scale-merge-coverage",
            file_format="json",
        ),
        _artifact(
            root,
            progress_final_path,
            artifact_id="scale-progress-final",
            role="terminal-progress",
            file_format="json",
        ),
        _artifact(
            root,
            events_artifact,
            artifact_id="scale-task-events",
            role="append-only-task-events",
            file_format="jsonl",
        ),
        _artifact(
            root,
            backend_path,
            artifact_id="scale-backend-environment",
            role="backend-environment",
            file_format="json",
        ),
    )
    bundle_path = artifacts / "scale-bundle.json"
    proposed_bundle = ScaleBundle(
        generated_at=datetime.now(UTC),
        stage05_bundle=upstream.stage05_bundle_ref,
        strategy_bundle=upstream.strategy_bundle_ref,
        scale_plan=output_refs[0],
        resource_report=output_refs[1],
        strategy_authorization=output_refs[2],
        task_table=output_refs[3],
        candidate_index=output_refs[4],
        coverage_report=output_refs[5],
        progress_final=output_refs[6],
        task_events=output_refs[7],
        backend_environment=output_refs[8],
        profile=profile,
        strategy_id=winner,
        requested_new_candidates=plan.requested_new_candidates,
        complete_new_candidates=len(ordered_candidates),
        shard_count=len(plan.shards),
    )
    _dump_or_verify_model(
        proposed_bundle,
        bundle_path,
        ScaleBundle,
        ignore_fields=frozenset({"generated_at"}),
    )
    bundle_ref = _artifact(
        root,
        bundle_path,
        artifact_id="scale-bundle",
        role="stage07-scale-input",
        file_format="json",
    )
    log_refs: list[ArtifactRef] = []
    for task in final_tasks:
        for task_attempt in task.attempts:
            task_root = (
                attempt_root / "tasks" / task.task_id / f"attempt-{task_attempt.attempt_number:04d}"
            )
            for suffix in ("stdout", "stderr"):
                log = task_root / f"{suffix}.log"
                if log.is_file():
                    log_refs.append(
                        _artifact(
                            root,
                            log,
                            artifact_id=(
                                f"{task.task_id}-attempt-{task_attempt.attempt_number:04d}-{suffix}"
                            ),
                            role="backend-log",
                            file_format="text",
                        )
                    )
    proposed_completed_at = max(
        datetime.now(UTC),
        created_at + timedelta(microseconds=1),
    )
    remote_executor_id = os.environ.get("EASYDESIGN_REMOTE_EXECUTOR_ID")
    proposed_attempt = Attempt(
        attempt_id="attempt-0001",
        status=ExecutionStatus.SUCCEEDED,
        created_at=created_at,
        started_at=created_at,
        ended_at=proposed_completed_at,
        backend_name="boltzgen",
        backend_version="0.3.2",
        executor_name=(
            "local-multi-gpu"
            if remote_executor_id is None
            else f"ssh-remote-{remote_executor_id}"
        ),
        log_artifacts=tuple(log_refs),
    )
    attempt = _dump_or_verify_model(
        proposed_attempt,
        attempt_root / "attempt-manifest.json",
        Attempt,
        ignore_fields=frozenset({"ended_at"}),
    )
    assert attempt.ended_at is not None
    completed_at = attempt.ended_at
    proposed_stage_manifest = StageManifest(
        stage_id=StageId.SCALE_GENERATION_AND_REFOLDING,
        contract_version="0.1",
        status=ExecutionStatus.SUCCEEDED,
        created_at=created_at,
        completed_at=completed_at,
        input_artifacts=(
            upstream.strategy_bundle_ref,
            upstream.pilot_candidate_index_ref,
            upstream.stage05_bundle_ref,
        ),
        output_artifacts=(*output_refs, bundle_ref),
        attempts=(attempt,),
        selected_attempt_id="attempt-0001",
        warnings=tuple(
            (
                "Stage 06 generated new candidates only; Stage 04/05 candidates are not counted.",
                (
                    "production-50000 is a generated candidate population, not a "
                    "scientifically validated order package."
                    if profile is ScaleProfile.PRODUCTION_50000
                    else "smoke-1000 is an engineering smoke, not a production order package."
                ),
                *(
                    (
                        "Human override scaled a Stage 05 Tier A despite "
                        "stopped-no-scale-winner; scientific eligibility remains false.",
                    )
                    if authorization.mode == "manual-stage05-stop-override"
                    else ()
                ),
            )
        ),
    )
    proposed_stage_manifest.validate_inputs_declared_by(
        (upstream.stage03, upstream.stage04, upstream.stage05)
    )
    stage_manifest_path = artifacts / "stage-manifest.json"
    _dump_or_verify_model(
        proposed_stage_manifest,
        stage_manifest_path,
        StageManifest,
    )
    stage_ref = _artifact(
        root,
        stage_manifest_path,
        artifact_id="stage-06-manifest",
        role="stage-manifest",
        file_format="json",
    )
    timestamp = max(
        completed_at,
        upstream.run.updated_at + timedelta(microseconds=1),
    )
    terminal = resolved.stop_after_stage == 6
    proposed_next_run = upstream.run.next_revision(
        updated_at=timestamp,
        status=ExecutionStatus.SUCCEEDED if terminal else ExecutionStatus.RUNNING,
        completed_at=timestamp if terminal else None,
        stage_manifest_refs=(*upstream.run.stage_manifest_refs, stage_ref),
        clear_workflow_state=True,
    )
    run_manifest_path = root / "manifests" / f"run-manifest.v{proposed_next_run.revision:04d}.json"
    _dump_or_verify_model(
        proposed_next_run,
        run_manifest_path,
        RunManifest,
    )
    _atomic_text(run_manifest_path.name + "\n", root / "manifests" / "LATEST")
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
                notes=(f"Stage 06 generated {len(ordered_candidates)} new candidates.",),
            ),
        ),
        generated_at=timestamp,
    )
    return Stage06Execution(
        status="succeeded",
        run_root=root,
        run_manifest=run_manifest_path,
        stage_manifest=stage_manifest_path,
        scale_bundle=bundle_path,
        complete_candidate_count=len(ordered_candidates),
    )
